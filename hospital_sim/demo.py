"""Synthetic adapter examples, not clinical rules or a real scheduling algorithm."""

import asyncio
from dataclasses import dataclass
from typing import Optional

from .contracts import (
    DurationPrediction, EventKind, HospitalEvent, Proposal, SchedulingRequest,
    Snapshot, ValidationResult,
)
from .coordinator import Coordinator


@dataclass(frozen=True)
class DemoState:
    available_rooms: frozenset[str]
    fixed_room: Optional[str] = None


@dataclass(frozen=True)
class DemoSchedule:
    # The whole demo schedule is one synthetic case assigned to one room.
    room: str


class DemoStateAdapter:
    def apply_event(
        self, snapshot: Snapshot[DemoState, DemoSchedule], event: HospitalEvent
    ) -> DemoState:
        if event.kind != EventKind.RESOURCE_UNAVAILABLE:
            raise NotImplementedError("The demo implements resource unavailability only")
        room = event.payload.get("resource_id")
        if not isinstance(room, str) or room not in snapshot.domain.available_rooms:
            raise ValueError("Expected a currently available demo room")
        return DemoState(snapshot.domain.available_rooms - {room}, snapshot.domain.fixed_room)

    def fixed_commitments(self, snapshot: Snapshot[DemoState, DemoSchedule]) -> object:
        return snapshot.domain.fixed_room


class DemoLOSPredictor:
    def predict(self, inputs: object) -> DurationPrediction:
        return DurationPrediction(2.0, "inclusive_calendar_days", (1.0, 3.0))


class DemoRoomDurationPredictor:
    def predict(self, inputs: object) -> DurationPrediction:
        return DurationPrediction(45.0, "minutes", (30.0, 60.0))


class DemoScheduler:
    """Choose an available room for one case; optionally gate the first request."""

    def __init__(self, *, pause_first: bool = False) -> None:
        self.pause_first = pause_first
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.request_versions: list[int] = []

    async def propose(
        self, request: SchedulingRequest[DemoState, DemoSchedule]
    ) -> Optional[Proposal[DemoSchedule]]:
        self.request_versions.append(request.snapshot.version)
        if len(self.request_versions) == 1:
            self.started.set()
            if self.pause_first:
                await self.release.wait()
        rooms = request.snapshot.domain.available_rooms
        fixed = request.fixed_commitments
        if fixed is not None:
            if not isinstance(fixed, str) or fixed not in rooms:
                return None
            room = fixed
        elif rooms:
            room = sorted(rooms)[0]
        else:
            return None
        return Proposal(DemoSchedule(room), request.snapshot.version)


class DemoValidator:
    def validate(
        self, snapshot: Snapshot[DemoState, DemoSchedule], proposal: Proposal[DemoSchedule]
    ) -> ValidationResult:
        reasons = []
        if proposal.schedule.room not in snapshot.domain.available_rooms:
            reasons.append("Proposed demo room is unavailable")
        if snapshot.domain.fixed_room is not None and proposal.schedule.room != snapshot.domain.fixed_room:
            reasons.append("Proposal changes a fixed demo commitment")
        return ValidationResult(not reasons, tuple(reasons))


def outage(event_id: str, time: float, room: str) -> HospitalEvent:
    return HospitalEvent(event_id, time, EventKind.RESOURCE_UNAVAILABLE, {"resource_id": room})


async def run_demo() -> None:
    initial = Snapshot(
        simulation_time=0.0,
        version=0,
        domain=DemoState(frozenset({"room-a", "room-b", "room-c"})),
        accepted_schedule=DemoSchedule("room-a"),
    )
    scheduler = DemoScheduler(pause_first=True)
    print("Synthetic demo: one case, three rooms; no patient data or clinical optimization.")
    print("Prediction test doubles (not used to rank rooms):")
    print(" ", DemoLOSPredictor().predict(None))
    print(" ", DemoRoomDurationPredictor().predict(None))
    async with Coordinator(initial, DemoStateAdapter(), scheduler, DemoValidator()) as coordinator:
        coordinator.submit(outage("outage-a", 10.0, "room-a"))
        await scheduler.started.wait()
        coordinator.submit(outage("outage-b", 11.0, "room-b"))
        scheduler.release.set()
        await coordinator.wait_idle()
        proposal = coordinator.proposal
        assert proposal is not None
        print("Requested state versions:", scheduler.request_versions)
        print("Accepted schedule before approval:", coordinator.snapshot.accepted_schedule)
        print("Accepted schedule needs review:", coordinator.schedule_needs_review)
        print("Validated proposal:", proposal)
        # This explicit call stands in for a future user/approval boundary.
        approval = coordinator.accept(proposal.base_version)
        assert approval.feasible
        for result in coordinator.outcomes:
            print(
                f"{result.status}: request=v{result.request_version}, "
                f"current=v{result.current_version}, solver={result.solver_seconds:.6f}s, "
                f"event_to_proposal={result.event_to_proposal_seconds}"
            )
        print("Accepted schedule after approval:", coordinator.snapshot.accepted_schedule)
        print("Metrics:", coordinator.metrics)


if __name__ == "__main__":
    asyncio.run(run_demo())
