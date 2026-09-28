"""Optimizer-visible data. Realized durations must never enter these objects."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CaseInput:
    case_id: str
    procedure: str
    predicted_minutes: int

    def __post_init__(self):
        if not self.case_id or self.predicted_minutes < 1:
            raise ValueError("Cases require an identifier and a positive duration")


@dataclass(frozen=True)
class CaseState:
    case: CaseInput
    status: str = "waiting"
    actual_start: int | None = None
    actual_finish: int | None = None
    actual_room: str | None = None


@dataclass(frozen=True)
class RoomState:
    room_id: str
    available_at: int  # Estimate for running cases; observed cooldown otherwise.


@dataclass(frozen=True)
class Outage:
    room_id: str
    start: int
    end: int

    def __post_init__(self):
        if self.start >= self.end:
            raise ValueError("Outage start must precede end")

    def blocks(self, room_id: str, minute: int) -> bool:
        return self.room_id == room_id and self.start <= minute < self.end


@dataclass(frozen=True)
class SimulationConfig:
    rooms: int = 2
    opening: int = 8 * 60
    closing: int = 17 * 60
    turnover: int = 15
    outage: Outage | None = None

    def __post_init__(self):
        if self.rooms < 1 or not 0 <= self.opening < self.closing <= 1440:
            raise ValueError("Require rooms >= 1 and 0 <= opening < closing <= 24:00")
        if self.turnover < 0:
            raise ValueError("Turnover cannot be negative")
        if self.outage:
            if self.outage.room_id not in self.room_ids:
                raise ValueError("Outage references an unknown room")
            if not self.opening <= self.outage.start < self.outage.end <= self.closing:
                raise ValueError("Outage must lie within opening hours")

    @property
    def room_ids(self) -> tuple[str, ...]:
        return tuple(f"room-{i + 1}" for i in range(self.rooms))


@dataclass(frozen=True)
class HospitalState:
    minute: int
    cases: tuple[CaseState, ...]
    rooms: tuple[RoomState, ...]
    opening: int
    closing: int
    turnover: int
    known_outages: tuple[Outage, ...] = ()


@dataclass(frozen=True)
class Assignment:
    case_id: str
    room_id: str
    start: int
    duration: int


@dataclass(frozen=True)
class Schedule:
    assignments: tuple[Assignment, ...] = ()
    unassigned: tuple[str, ...] = ()
