"""Planning-time candidate predictions for the historical Mesa workloads.

The ignored EDA Parquet supplies the selected model features and an internal
case key for joining rows. Actual room duration and LOS never enter a
model feature frame, a CaseInput, or a scheduling request.
"""

from dataclasses import dataclass, replace
from hashlib import sha256
from math import ceil, isfinite
from pathlib import Path

import pandas as pd

from .historical_data import DailyScenario


@dataclass(frozen=True)
class ModelPredictions:
    values: pd.DataFrame  # private index: source case ID; never export
    fingerprints: dict[str, str]

    def apply(self, scenario: DailyScenario, room_risk: str = "point",
              los_risk: str = "point") -> DailyScenario:
        room_column = f"duration_{room_risk}_min"
        los_column = f"los_{los_risk}_days"
        if room_column not in self.values or los_column not in self.values:
            raise ValueError("Requested prediction bound is absent from the saved models")
        if scenario.source_ids is None or scenario.preop_days is None:
            raise ValueError("Model mode requires internal case mapping and known preoperative days")
        case_ids = {case.case_id for case in scenario.cases}
        if set(scenario.source_ids) != case_ids or set(scenario.preop_days) != case_ids:
            raise ValueError("Every case needs one private source key and preoperative elapsed time")
        if any(not isinstance(days, int) or days < 0 for days in scenario.preop_days.values()):
            raise ValueError("Preoperative elapsed days must be nonnegative integers")
        if not set(scenario.source_ids.values()).issubset(self.values.index):
            raise ValueError("Some historical cases have no preoperative prediction")
        updated = []
        for case in scenario.cases:
            row = self.values.loc[scenario.source_ids[case.case_id]]
            room = float(row[room_column])
            los = float(row[los_column]) - scenario.preop_days[case.case_id]
            if not (isfinite(room) and room > 0 and isfinite(los)):
                raise ValueError("Predictions must be finite with positive room duration")
            # Room execution uses whole minutes. Inclusive LOS is an integer;
            # round the point estimate, but round upper bounds conservatively.
            days = max(1, ceil(los)) if los_risk == "upper" else max(1, round(los))
            updated.append(replace(case, predicted_minutes=ceil(room), predicted_los_days=days))
        return replace(scenario, cases=tuple(updated))


def load_model_predictions(eda_path: Path, room_artifact: Path,
                           los_artifact: Path) -> ModelPredictions:
    from los_model import predict_los
    from surgery_duration import predict_schedule

    for path in (eda_path, room_artifact, los_artifact):
        if not path.is_file():
            raise FileNotFoundError(f"Prediction input is missing: {path}")
    eda = pd.read_parquet(eda_path)
    if "no_cas" not in eda or "date_inter" not in eda or eda["no_cas"].isna().any():
        raise ValueError("EDA data requires complete internal case keys and dates")
    eda = eda.loc[pd.to_datetime(eda["date_inter"]).dt.year.eq(2022)].copy()
    if eda.empty or not eda["no_cas"].is_unique:
        raise ValueError("2022 EDA case keys must be present and unique")
    room = predict_schedule(eda, room_artifact, raw=True)
    los = predict_los(eda, los_artifact, raw=True)
    values = pd.concat([room, los], axis=1)
    values.index = pd.Index(eda["no_cas"].to_numpy(), name="private_source_id")
    hashes = {name: sha256(path.read_bytes()).hexdigest() for name, path in (
        ("eda", eda_path), ("room_model", room_artifact), ("los_model", los_artifact))}
    return ModelPredictions(values, hashes)
