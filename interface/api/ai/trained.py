"""Adapters from consultation data to the locally trained duration artifacts.

The trained artifacts are supplied by the operator; they are never committed or
loaded from the historical patient workbook by the web application.
"""

from hashlib import sha256
from pathlib import Path

import joblib
import pandas as pd

from api.ai.contracts import DurationPrediction, PredictionInput
from api.resources.models import CareType
from prediction.los_model import predict_los_loaded
from prediction.surgery_duration import predict_schedule_loaded


def _raw_features(inputs: PredictionInput) -> pd.DataFrame:
    """Map fields available at consultation into the EDA feature vocabulary.

    Anaesthesia and historical practitioner names are unavailable in KYST.
    The model's learned missing/rare-category handling is used for those fields;
    accuracy under this reduced feature set still needs prospective validation.
    """
    row = {
        "age_years": inputs.age,
        "sexe": inputs.sex,
        "interv_type": inputs.intervention_type,
        "anesth_type": None,
        "anesth_loco_reg": None,
        "praticien": None,
        "nom_chir": None,
        "cim_diag_pr": inputs.principal_diagnosis,
    }
    row.update({f"ccam_{index}": code for index, code in enumerate(inputs.ccam_codes, 1)})
    return pd.DataFrame([row])


def _version(label: str, path: Path) -> str:
    return f"{label}-{sha256(path.read_bytes()).hexdigest()[:12]}"


class TrainedRoomDurationPredictor:
    def __init__(self, artifact: Path):
        if not artifact.is_file():
            raise FileNotFoundError(f"Room-duration artifact not found: {artifact}")
        self.artifact = artifact
        self.model_version = _version("room", artifact)
        self.saved = joblib.load(artifact)

    def predict(self, inputs: PredictionInput) -> DurationPrediction:
        result = predict_schedule_loaded(_raw_features(inputs), self.saved, raw=True).iloc[0]
        # P80/P95 are one-sided upper bounds, not a two-sided confidence interval.
        return DurationPrediction(float(result["duration_point_min"]), "minutes")


class TrainedLOSPredictor:
    def __init__(self, artifact: Path):
        if not artifact.is_file():
            raise FileNotFoundError(f"LOS artifact not found: {artifact}")
        self.artifact = artifact
        self.model_version = _version("los", artifact)
        self.saved = joblib.load(artifact)

    def predict(self, inputs: PredictionInput) -> DurationPrediction:
        result = predict_los_loaded(_raw_features(inputs), self.saved, raw=True).iloc[0]
        return DurationPrediction(
            float(result["los_point_days"]), "inclusive_calendar_days",
            (float(result["los_lower_days"]), float(result["los_upper_days"])),
        )


class PredictedStayCareTypeClassifier:
    """A stay that rounds to one inclusive day uses an ambulatory place.

    The LOS model predicts a mean, floored at one day, so `<= 1` would almost never
    match: a prediction of 1.4 days is closer to a same-day discharge than to two days.
    """

    def __init__(self, los: TrainedLOSPredictor):
        self.los = los
        self.model_version = f"care-from-{los.model_version}"

    def predict(self, inputs: PredictionInput) -> CareType:
        return (CareType.ambulatory if self.los.predict(inputs).value < 1.5
                else CareType.conventional)
