"""Read the cleaned workbook; train duration estimates strictly before evaluation."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time
from hashlib import sha256
from math import ceil, isfinite
from numbers import Real
from pathlib import Path
import re
import unicodedata

import pandas as pd

from .domain import CaseInput

ROOM_IN = "heure_d_entree_en_salle_d_operation_calimed"
ROOM_OUT = "heure_de_sortie_de_salle_d_operation_calimed"
REQUIRED = {"no_cas", "date_inter", "interv_type", ROOM_IN, ROOM_OUT}


def clock_minutes(value) -> float | None:
    """Accept Excel fractional days, clock strings and datetime/time objects."""
    if pd.isna(value):
        return None
    if isinstance(value, (datetime, time)):
        result = value.hour * 60 + value.minute + value.second / 60
    elif isinstance(value, Real) and not isinstance(value, bool):
        result = float(value) * 1440
    else:
        try:
            parsed = time.fromisoformat(str(value).strip())
        except ValueError:
            return None
        result = parsed.hour * 60 + parsed.minute + parsed.second / 60
    return result if isfinite(result) and 0 <= result < 1440 else None


def normalize_procedure(value) -> str:
    if pd.isna(value) or not str(value).strip():
        return "__MISSING__"
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().upper()


@dataclass(frozen=True)
class DailyScenario:
    date: date
    cases: tuple[CaseInput, ...]
    # Execution-only: never include this mapping in a SchedulingRequest.
    realized_minutes: dict[str, int]
    realized_los_days: dict[str, int] | None = field(default=None, repr=False)
    # Internal link to ignored source data; never serialize or send to a solver.
    source_ids: dict[str, int] | None = field(default=None, repr=False)
    # Days already spent in hospital when surgery begins; known at admission.
    preop_days: dict[str, int] | None = field(default=None, repr=False)


@dataclass
class HistoricalData:
    frame: pd.DataFrame
    medians: dict[str, float]
    fallback: float
    quality: dict
    fingerprint: str
    los_medians: dict[str, float] | None = None
    los_fallback: float = 1.0

    @property
    def dates(self) -> tuple[date, ...]:
        return tuple(sorted(self.frame.loc[self.frame["date"].dt.year.eq(2022), "date"].dt.date.unique()))

    def scenario(self, day: date) -> DailyScenario:
        rows = self.frame.loc[self.frame["date"].dt.date.eq(day)].sort_values("source_id")
        if day.year != 2022 or rows.empty:
            raise ValueError("Select a 2022 date with usable cases")
        cases, realized, realized_los, source_ids, preop_days = [], {}, {}, {}, {}
        for index, row in enumerate(rows.itertuples(index=False), 1):
            identifier = f"case-{index:04d}"
            predicted_los = max(1, round((self.los_medians or {}).get(row.procedure, self.los_fallback)))
            cases.append(CaseInput(identifier, row.procedure,
                                   ceil(self.medians.get(row.procedure, self.fallback)), predicted_los))
            realized[identifier] = ceil(row.duration)
            realized_los[identifier] = int(row.los_days)
            source_ids[identifier] = int(row.source_id)
            preop_days[identifier] = int(row.preop_days)
        return DailyScenario(day, tuple(cases), realized, realized_los, source_ids, preop_days)


def load_historical(path: Path) -> HistoricalData:
    raw = pd.read_excel(path)
    missing = REQUIRED - set(raw.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    if raw["no_cas"].isna().any() or raw["no_cas"].duplicated().any():
        raise ValueError("Source case identifiers must be present and unique")
    counts = Counter()
    excluded_by_date = Counter()
    records = []
    for _, row in raw.iterrows():
        start, end = clock_minutes(row[ROOM_IN]), clock_minutes(row[ROOM_OUT])
        event_date = pd.to_datetime(row["date_inter"], errors="coerce")
        reason = None
        if start is None or end is None:
            reason = "missing_or_invalid_endpoint"
        elif start == 0 or end == 0:
            reason = "zero_endpoint"
        elif end <= start:
            reason = "nonpositive_or_overnight_interval"
        elif pd.isna(event_date):
            reason = "invalid_intervention_date"
        if reason:
            counts[reason] += 1
            excluded_by_date[str(event_date.date()) if pd.notna(event_date) else "unknown"] += 1
            continue
        admission = pd.to_datetime(row.get("date_entree"), errors="coerce")
        discharge = pd.to_datetime(row.get("date_sortie"), errors="coerce")
        preop = (event_date.normalize() - admission.normalize()).days if pd.notna(admission) else None
        postop = (discharge.normalize() - event_date.normalize()).days + 1 if pd.notna(discharge) else None
        valid_stay = preop is not None and preop >= 0 and postop is not None and postop >= 1
        records.append({
            "source_id": row["no_cas"], "date": event_date.normalize(),
            "procedure": normalize_procedure(row["interv_type"]), "duration": end - start,
            "los_days": postop if valid_stay else None,
            "preop_days": preop if valid_stay else None,
        })
    frame = pd.DataFrame(records, columns=["source_id", "date", "procedure", "duration", "los_days", "preop_days"])
    frame["date"] = pd.to_datetime(frame["date"])
    missing_los = int((frame["los_days"].isna() | frame["preop_days"].isna()).sum())
    # Older room-only fixtures have no stay column. The bed experiment rejects
    # such input using this quality count rather than fabricating observations.
    frame["los_days"] = frame["los_days"].fillna(1).clip(lower=1).astype(int)
    frame["preop_days"] = frame["preop_days"].fillna(0).clip(lower=0).astype(int)
    train = frame.loc[frame["date"].ge("2019-01-01") & frame["date"].lt("2022-01-01")]
    if train.empty:
        raise ValueError("No valid 2019–2021 cases available for duration estimation")
    grouped = train.groupby("procedure")["duration"].agg(["median", "count"])
    medians = grouped.loc[grouped["count"].ge(10), "median"].to_dict()
    los_grouped = train.groupby("procedure")["los_days"].agg(["median", "count"])
    los_medians = los_grouped.loc[los_grouped["count"].ge(10), "median"].to_dict()
    quality = {
        "input_rows": len(raw), "usable_rows": len(frame),
        "excluded_rows": sum(counts.values()), "exclusions_by_reason": dict(counts),
        "exclusions_by_date": dict(sorted(excluded_by_date.items())),
        "training_rows": len(train), "training_period": ["2019-01-01", "2021-12-31"],
        "evaluation_year": 2022, "minimum_procedure_training_count": 10,
        "fallback_median_minutes": float(train["duration"].median()),
        "fallback_median_los_days": float(train["los_days"].median()),
        "missing_or_invalid_postop_los_rows": missing_los,
    }
    return HistoricalData(frame, medians, float(train["duration"].median()), quality,
                          sha256(path.read_bytes()).hexdigest(), los_medians,
                          float(train["los_days"].median()))
