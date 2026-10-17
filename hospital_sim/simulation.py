"""Minute-step Mesa execution; the async runner pauses time during planning."""

import asyncio
from dataclasses import asdict, dataclass, replace
from math import ceil
from statistics import mean

import mesa

from .contracts import EventKind, HospitalEvent, Proposal, Snapshot
from .coordinator import Coordinator
from .domain import CaseState, HospitalState, RoomState, Schedule, SimulationConfig
from .historical_data import DailyScenario
from .scheduling import BaselineScheduler, ObservationAdapter, RoomValidator


class EpisodeAgent(mesa.Agent):
    def __init__(self, model, case):
        super().__init__(model)
        self.case = case
        self.status = "waiting"
        self.actual_start = None
        self.actual_finish = None
        self.actual_room = None

    def observed(self):
        return CaseState(self.case, self.status, self.actual_start,
                         self.actual_finish, self.actual_room)


@dataclass
class Room:
    room_id: str
    current_case: str | None = None
    cooldown_until: int = 0


class HospitalModel(mesa.Model):
    def __init__(self, scenario: DailyScenario, config: SimulationConfig):
        super().__init__(rng=0)
        identifiers = [c.case_id for c in scenario.cases]
        if len(identifiers) != len(set(identifiers)) or set(identifiers) != set(scenario.realized_minutes):
            raise ValueError("Cases and execution outcomes must match one-to-one")
        self._realized = {key: ceil(value) for key, value in scenario.realized_minutes.items()}
        if any(value <= 0 or value > 1440 for value in self._realized.values()):
            raise ValueError("Realized durations must be positive and at most one day")
        self.config = config
        self.minute = config.opening - 1
        self.episodes = {c.case_id: EpisodeAgent(self, c) for c in scenario.cases}
        self.rooms = {key: Room(key, cooldown_until=config.opening) for key in config.room_ids}
        self.events = []
        self.availability_changed = False

    def log(self, kind, **values):
        self.events.append({"minute": self.minute, "event": kind, **values})

    def step(self):
        """Finish work, release turnover, then observe availability changes."""
        self.minute += 1
        self.availability_changed = False
        for room in self.rooms.values():
            if room.current_case:
                agent = self.episodes[room.current_case]
                if self.minute >= agent.actual_start + self._realized[agent.case.case_id]:
                    agent.status = "completed"
                    agent.actual_finish = self.minute
                    room.current_case = None
                    room.cooldown_until = self.minute + self.config.turnover
                    self.log("completed", case_id=agent.case.case_id, room_id=room.room_id)
            if room.cooldown_until == self.minute and self.minute > self.config.opening:
                self.log("turnover_complete", room_id=room.room_id)
        outage = self.config.outage
        if outage and self.minute in (outage.start, outage.end):
            self.availability_changed = True
            self.log("closure_started" if self.minute == outage.start else "closure_ended",
                     room_id=outage.room_id)

    def observed_state(self):
        rooms = []
        for room in self.rooms.values():
            available = max(self.minute, room.cooldown_until)
            if room.current_case:
                agent = self.episodes[room.current_case]
                # Knowledge of continued occupancy, not the hidden actual finish.
                available = max(self.minute + 1, agent.actual_start + agent.case.predicted_minutes)
                available += self.config.turnover
            rooms.append(RoomState(room.room_id, available))
        outage = self.config.outage
        known = (outage,) if outage and self.minute >= outage.start else ()
        return HospitalState(
            self.minute, tuple(a.observed() for a in self.episodes.values()),
            tuple(rooms), self.config.opening, self.config.closing,
            self.config.turnover, known,
        )

    def start_cases(self, schedule: Schedule):
        if not self.config.opening <= self.minute < self.config.closing:
            return
        for room in self.rooms.values():
            if room.current_case or room.cooldown_until > self.minute:
                continue
            if self.config.outage and self.config.outage.blocks(room.room_id, self.minute):
                continue
            queue = sorted((a for a in schedule.assignments
                            if a.room_id == room.room_id and self.episodes[a.case_id].status == "waiting"),
                           key=lambda a: (a.start, a.case_id))
            if not queue or queue[0].start > self.minute:
                continue
            agent = self.episodes[queue[0].case_id]
            agent.status = "running"
            agent.actual_room = room.room_id
            agent.actual_start = self.minute
            room.current_case = agent.case.case_id
            self.log("started", case_id=agent.case.case_id, room_id=room.room_id)

    def has_work(self):
        return (self.minute < self.config.closing
                or any(r.current_case or r.cooldown_until > self.minute for r in self.rooms.values()))


def schedule_record(schedule, minute, kind):
    return {
        "minute": minute, "kind": kind,
        "assignments": [asdict(a) for a in schedule.assignments],
        "unassigned": list(schedule.unassigned),
    }


def metrics(model, initial, schedules, outcomes, replans):
    completed = [a for a in model.episodes.values() if a.status == "completed"]
    initial_map = {a.case_id: a for a in initial.assignments}
    delays = [max(0, a.actual_start - initial_map[a.case.case_id].start)
              for a in completed if a.case.case_id in initial_map]
    occupancy = sum(max(0, min(a.actual_finish, model.config.closing)
                        - max(a.actual_start, model.config.opening)) for a in completed)
    overtime = sum(max(0, a.actual_finish + model.config.turnover
                       - max(a.actual_start, model.config.closing)) for a in completed)
    changed, shift, room_changes = 0, 0, 0
    previous = initial_map
    for entry in schedules[1:]:
        current = {a["case_id"]: a for a in entry["assignments"]}
        for identifier in set(previous) | set(current):
            old, new = previous.get(identifier), current.get(identifier)
            if old is not None and not isinstance(old, dict):
                old = asdict(old)
            if old != new:
                changed += 1
                if old and new:
                    shift += abs(new["start"] - old["start"])
                    room_changes += old["room_id"] != new["room_id"]
        previous = current
    failures = {"failed", "timeout", "rejected", "invalid_result",
                "acceptance_rejected", "acceptance_stale", "no_proposal", "stale"}
    return {
        "cases": len(model.episodes), "completed": len(completed),
        "unstarted": sum(a.status == "waiting" for a in model.episodes.values()),
        "delay_measured_cases": len(delays),
        "mean_start_delay_minutes": mean(delays) if delays else None,
        "total_start_delay_minutes": sum(delays),
        "room_occupancy_minutes_in_hours": occupancy,
        "room_utilization_fraction": occupancy / (
            model.config.rooms * (model.config.closing - model.config.opening)),
        "overtime_minutes_including_turnover": overtime,
        "changed_assignment_decisions": changed, "room_change_decisions": room_changes,
        "total_planned_start_shift_minutes": shift, "replanning_count": replans,
        "solver_seconds": sum(o.solver_seconds for o in outcomes),
        "failures": sum(o.status in failures for o in outcomes),
        "timeouts": sum(o.status == "timeout" for o in outcomes),
    }


class _InitialReplay:
    """Replay a saved plan through the same validation and acceptance boundary."""
    def __init__(self, initial, scheduler):
        self.initial = initial
        self.scheduler = scheduler

    async def propose(self, request):
        if self.initial is not None:
            schedule, self.initial = self.initial, None
            return Proposal(schedule, request.snapshot.version)
        return await self.scheduler.propose(request)


async def run_day(scenario, config, policy="reactive", scheduler=None, timeout_seconds=5.0,
                  initial_schedule=None, initial_report=None):
    """Run a deterministic scenario; injected schedulers use only public state."""
    if policy not in ("static", "reactive"):
        raise ValueError("Policy must be static or reactive")
    model = HospitalModel(scenario, config)
    adapter = ObservationAdapter()
    initial_state = replace(model.observed_state(), minute=config.opening)
    scheduler = scheduler or BaselineScheduler()
    replay = _InitialReplay(initial_schedule, scheduler)
    coordinator = Coordinator(Snapshot(config.opening, 0, initial_state),
                              adapter, replay, RoomValidator(),
                              timeout_seconds=timeout_seconds)
    schedules = []
    initial = Schedule((), tuple(c.case_id for c in scenario.cases))
    replans = 0
    outcome_index = 0
    async with coordinator:
        if initial_schedule is not None:
            # Accept the common initial plan before the first disruption is revealed.
            coordinator.submit(HospitalEvent(
                "initial-plan", config.opening, EventKind.SIMULATION_OBSERVATION,
                {"state": initial_state},
            ))
            await coordinator.wait_idle()
            if coordinator.proposal is not None:
                coordinator.accept(coordinator.snapshot.version)
            initial = coordinator.snapshot.accepted_schedule or initial
            schedules.append(schedule_record(initial, config.opening, "initial"))
        while model.has_work():
            model.step()
            first = model.minute == config.opening and initial_schedule is None
            replan = first or (policy == "reactive" and model.availability_changed)
            if replan and not first:
                replans += 1
            coordinator.submit(
                HospitalEvent(f"observation-{model.minute}", model.minute,
                              EventKind.SIMULATION_OBSERVATION, {"state": model.observed_state()}),
                replan=replan,
            )
            if replan:
                await coordinator.wait_idle()
                if coordinator.proposal is not None:
                    coordinator.accept(coordinator.snapshot.version)
                schedule = coordinator.snapshot.accepted_schedule or initial
                # Initial fallback is explicitly empty if no valid proposal exists.
                if first:
                    initial = schedule
                schedules.append(schedule_record(schedule, model.minute, "initial" if first else "replan"))
            for outcome in coordinator.outcomes[outcome_index:]:
                model.log("coordinator", **asdict(outcome))
            outcome_index = len(coordinator.outcomes)
            model.start_cases(coordinator.snapshot.accepted_schedule or initial)
            await asyncio.sleep(0)
    executed = [{
        "case_id": a.case.case_id, "status": a.status,
        "room_id": a.actual_room, "start": a.actual_start, "finish": a.actual_finish,
    } for a in model.episodes.values()]
    measured = metrics(model, initial, schedules, coordinator.outcomes, replans)
    reports = list(getattr(scheduler, "reports", []))
    if initial_report is not None:
        initial_seconds = initial_report["elapsed_seconds"]
        initial_solver_seconds = next((o.solver_seconds for o in coordinator.outcomes
                                       if o.request_version == 1 and o.solver_seconds), 0.0)
        measured["initial_planning_seconds"] = initial_seconds
        measured["replanning_solver_seconds"] = measured["solver_seconds"] - initial_solver_seconds
        measured["solver_seconds"] = initial_seconds + measured["replanning_solver_seconds"]
        reports = [initial_report] + reports
    if reports:
        measured["fitness_evaluations"] = sum(r["evaluations"] for r in reports)
        measured["search_failures"] = sum(r["stop_reason"] in
            ("worker_error", "invalid_result", "cancelled", "initial_failure") for r in reports)
        measured["search_deadline_stops"] = sum(r["stop_reason"] == "deadline" for r in reports)
    return {
        "date": scenario.date.isoformat(), "policy": policy,
        "scenario": "outage" if config.outage else "no_outage",
        "metrics": measured, "search_reports": reports,
        "schedule_history": schedules, "executed_schedule": executed,
        "events": model.events,
    }
