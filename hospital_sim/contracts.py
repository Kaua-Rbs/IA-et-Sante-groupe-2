"""Adapter boundaries; scheduling and clinical semantics belong to adapters."""

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Generic, Literal, Mapping, Optional, Protocol, TypeVar


StateT = TypeVar("StateT")
ScheduleT = TypeVar("ScheduleT")


class EventKind(str, Enum):
    SIMULATION_OBSERVATION = "simulation_observation"
    EMERGENCY_ARRIVAL = "emergency_arrival"
    CANCELLATION = "cancellation"
    SURGERY_OVERRUN = "surgery_overrun"
    DELAYED_DISCHARGE = "delayed_discharge"
    RESOURCE_UNAVAILABLE = "resource_unavailable"


@dataclass(frozen=True)
class HospitalEvent:
    event_id: str
    simulation_time: float
    kind: EventKind
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("An event identifier is required")
        if not isfinite(self.simulation_time) or self.simulation_time < 0:
            raise ValueError("Simulation time must be finite and nonnegative")


@dataclass(frozen=True)
class Snapshot(Generic[StateT, ScheduleT]):
    simulation_time: float
    version: int
    domain: StateT
    accepted_schedule: Optional[ScheduleT] = None


@dataclass(frozen=True)
class DurationPrediction:
    value: float
    unit: Literal["inclusive_calendar_days", "minutes"]
    interval: Optional[tuple[float, float]] = None

    def __post_init__(self) -> None:
        if self.unit not in ("inclusive_calendar_days", "minutes"):
            raise ValueError("Unsupported duration unit")
        if not isfinite(self.value) or self.value <= 0:
            raise ValueError("Predicted duration must be finite and positive")
        if self.interval is not None:
            lower, upper = self.interval
            if not (isfinite(lower) and isfinite(upper) and 0 <= lower <= upper):
                raise ValueError("Uncertainty interval must have ordered nonnegative bounds")


class LOSPredictor(Protocol):
    def predict(self, inputs: object) -> DurationPrediction:
        """Return total inclusive calendar days, not postoperative or remaining LOS."""
        ...


class RoomDurationPredictor(Protocol):
    def predict(self, inputs: object) -> DurationPrediction:
        """Return entry-to-exit room occupancy in minutes, excluding turnover."""
        ...


class StateAdapter(Protocol[StateT, ScheduleT]):
    def apply_event(
        self, snapshot: Snapshot[StateT, ScheduleT], event: HospitalEvent
    ) -> StateT:
        """Return updated domain state; raise for unsupported or invalid events."""
        ...

    def fixed_commitments(self, snapshot: Snapshot[StateT, ScheduleT]) -> object:
        """Return domain-specific commitments; the coordinator does not interpret them."""
        ...


@dataclass(frozen=True)
class SchedulingRequest(Generic[StateT, ScheduleT]):
    snapshot: Snapshot[StateT, ScheduleT]
    fixed_commitments: object
    deadline: float  # Absolute time from time.monotonic(), not simulation time.


@dataclass(frozen=True)
class Proposal(Generic[ScheduleT]):
    schedule: ScheduleT
    base_version: int


class Scheduler(Protocol[StateT, ScheduleT]):
    async def propose(
        self, request: SchedulingRequest[StateT, ScheduleT]
    ) -> Optional[Proposal[ScheduleT]]:
        """Return a candidate, or None when no candidate was found; cooperate with cancellation."""
        ...


@dataclass(frozen=True)
class ValidationResult:
    feasible: bool
    reasons: tuple[str, ...] = ()


class Validator(Protocol[StateT, ScheduleT]):
    def validate(
        self, snapshot: Snapshot[StateT, ScheduleT], proposal: Proposal[ScheduleT]
    ) -> ValidationResult:
        """Delegate to the shared scheduling validator in production."""
        ...


@dataclass(frozen=True)
class Outcome:
    status: str
    request_version: int
    current_version: int
    solver_seconds: float = 0.0
    event_to_proposal_seconds: Optional[float] = None
    reasons: tuple[str, ...] = ()
