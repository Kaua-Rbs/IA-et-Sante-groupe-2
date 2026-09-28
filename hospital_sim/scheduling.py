"""Room-only baseline and validation boundary for future solver adapters."""

import asyncio
from time import monotonic

from .contracts import EventKind, Proposal, ValidationResult
from .domain import Assignment, HospitalState, Schedule


def next_start(state: HospitalState, room: str, minute: int) -> int:
    """Closures prohibit starts, not continuation of already running work."""
    for outage in sorted(state.known_outages, key=lambda item: item.start):
        if outage.blocks(room, minute):
            minute = outage.end
    return minute


class ObservationAdapter:
    def apply_event(self, snapshot, event):
        if event.kind != EventKind.SIMULATION_OBSERVATION:
            raise ValueError("Expected simulation observation")
        state = event.payload.get("state")
        if not isinstance(state, HospitalState) or state.minute != event.simulation_time:
            raise ValueError("Invalid simulation observation")
        return state

    def fixed_commitments(self, snapshot):
        fixed_ids = {c.case.case_id for c in snapshot.domain.cases if c.status != "waiting"}
        schedule = snapshot.accepted_schedule or Schedule()
        return tuple(a for a in schedule.assignments if a.case_id in fixed_ids)


class BaselineScheduler:
    """Shortest predicted duration first, placed at the earliest available start."""

    async def propose(self, request):
        state = request.snapshot.domain
        available = {r.room_id: max(r.available_at, state.minute, state.opening) for r in state.rooms}
        assignments = list(request.fixed_commitments)
        unassigned = []
        waiting = sorted((c.case for c in state.cases if c.status == "waiting"),
                         key=lambda c: (c.predicted_minutes, c.case_id))
        for case in waiting:
            await asyncio.sleep(0)  # Cooperate with timeout/cancellation.
            if monotonic() >= request.deadline:
                return None
            start, room = min((next_start(state, room, minute), room)
                              for room, minute in available.items())
            if start >= state.closing:
                unassigned.append(case.case_id)
                continue
            assignments.append(Assignment(case.case_id, room, start, case.predicted_minutes))
            available[room] = start + case.predicted_minutes + state.turnover
        return Proposal(Schedule(tuple(assignments), tuple(unassigned)), request.snapshot.version)


class RoomValidator:
    def validate(self, snapshot, proposal):
        state = snapshot.domain
        schedule = proposal.schedule
        cases = {c.case.case_id: c for c in state.cases}
        rooms = {r.room_id: r for r in state.rooms}
        reasons = []
        ids = [a.case_id for a in schedule.assignments] + list(schedule.unassigned)
        if len(ids) != len(set(ids)) or set(ids) != set(cases):
            reasons.append("Schedule must cover each case exactly once")
        if proposal.base_version != snapshot.version:
            reasons.append("State version mismatch")
        previous = {a.case_id: a for a in (snapshot.accepted_schedule or Schedule()).assignments}
        proposed = {a.case_id: a for a in schedule.assignments}
        for identifier, case in cases.items():
            if case.status != "waiting":
                if identifier not in previous or proposed.get(identifier) != previous[identifier]:
                    reasons.append("Completed or running assignment changed")
        for a in schedule.assignments:
            if a.case_id not in cases or a.room_id not in rooms:
                reasons.append("Unknown case or room")
                continue
            if cases[a.case_id].status != "waiting":
                continue
            if (type(a.start) is not int or type(a.duration) is not int
                    or a.duration != cases[a.case_id].case.predicted_minutes):
                reasons.append("Invalid predicted interval")
                continue
            if not max(state.minute, state.opening) <= a.start < state.closing:
                reasons.append("Start outside scheduling window")
            if next_start(state, a.room_id, a.start) != a.start:
                reasons.append("Start during known closure")
        if reasons:
            return ValidationResult(False, tuple(sorted(set(reasons))))
        for room, resource in rooms.items():
            available = max(state.minute, resource.available_at, state.opening)
            waiting = sorted((a for a in schedule.assignments
                              if a.room_id == room and cases[a.case_id].status == "waiting"),
                             key=lambda a: (a.start, a.case_id))
            for a in waiting:
                if a.start < available:
                    reasons.append("Predicted room occupancy or turnover overlaps")
                available = a.start + a.duration + state.turnover
        return ValidationResult(not reasons, tuple(sorted(set(reasons))))
