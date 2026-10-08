"""Boundary between the API and the prediction / scheduling work of the other teams.

The API only talks to these protocols. Implementations live elsewhere: `fixtures.py` for
now, the trained models and the optimisation solver later. Units follow
`hospital_sim/contracts.py` so both sides can share adapters.
"""

import datetime as dt
from dataclasses import dataclass, field
from math import isfinite
from typing import Literal, Protocol

from api.resources.models import CareType


@dataclass(frozen=True)
class PredictionInput:
    """What is known at the preparatory consultation (the "devis"), before admission."""

    age: int
    sex: int  # 1 = male, 2 = female (source data convention)
    principal_diagnosis: str  # CIM-10
    ccam_codes: tuple[str, ...]
    specialty: str
    intervention_type: str | None = None


@dataclass(frozen=True)
class DurationPrediction:
    value: float
    unit: Literal["inclusive_calendar_days", "minutes"]
    interval: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        if not isfinite(self.value) or self.value <= 0:
            raise ValueError("Predicted duration must be finite and positive")
        if self.interval is not None:
            lower, upper = self.interval
            if not (isfinite(lower) and isfinite(upper) and 0 <= lower <= upper):
                raise ValueError("Uncertainty interval must have ordered nonnegative bounds")


class LOSPredictor(Protocol):
    model_version: str

    def predict(self, inputs: PredictionInput) -> DurationPrediction:
        """Total length of stay in inclusive calendar days (ambulatory = 1)."""
        ...


class RoomDurationPredictor(Protocol):
    model_version: str

    def predict(self, inputs: PredictionInput) -> DurationPrediction:
        """Room entry-to-exit minutes, excluding turnover."""
        ...


class CareTypeClassifier(Protocol):
    model_version: str

    def predict(self, inputs: PredictionInput) -> CareType:
        ...


# --- Scheduling ---

@dataclass(frozen=True)
class VacationSlot:
    id: int
    date: dt.date
    room_name: str
    specialty_id: int
    surgeon_id: int | None
    duration_min: int
    used_min: int  # already planned in this vacation


@dataclass(frozen=True)
class BedUnitLoad:
    id: int
    name: str
    care_type: CareType
    capacity: int
    occupancy: dict[dt.date, int] = field(default_factory=dict)  # occupied beds per day


@dataclass(frozen=True)
class SchedulingInput:
    """Self-contained snapshot: a solver needs no database access."""

    specialty_id: int
    surgeon_id: int
    room_minutes: float
    los_days: int  # inclusive calendar days
    care_type: CareType
    earliest_date: dt.date
    latest_date: dt.date
    vacations: tuple[VacationSlot, ...]
    bed_units: tuple[BedUnitLoad, ...]
    emergency_margin: float  # share of each vacation kept free for emergencies


@dataclass(frozen=True)
class Candidate:
    vacation_id: int
    bed_unit_id: int
    admission_date: dt.date
    discharge_date: dt.date
    score: float  # higher is better
    reasons: tuple[str, ...]  # displayable, without patient or staff identifiers


class Scheduler(Protocol):
    name: str

    def propose(self, request: SchedulingInput, count: int) -> list[Candidate]:
        """Return up to `count` candidates, best first; an empty list proves nothing."""
        ...
