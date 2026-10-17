"""Cross-day bed occupancy around the existing minute-step room simulation.

One Mesa agent represents each episode across arrival, room execution and
discharge. At each operating day, only current bed occupancy and predicted
LOS/duration are available to the admission policy. Actual LOS is private
until the corresponding discharge date.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import mesa

from .historical_data import DailyScenario


class WardEpisodeAgent(mesa.Agent):
    def __init__(self, model, case, arrival: date, room_minutes: int,
                 actual_los_days: int):
        super().__init__(model)
        self.case = case
        self.arrival = arrival
        self._room_minutes = room_minutes
        self._actual_los_days = actual_los_days
        self.status = "not_arrived"
        self.admitted: date | None = None
        self.discharge: date | None = None


@dataclass(frozen=True)
class WardDay:
    day: date
    arrivals: int
    discharged: int
    occupied_before: int
    beds_available: int
    offered: int
    started: int
    waiting_after: int
    occupied_after: int
    overtime_minutes: int
    room_replans: int
    room_failures: int


class HospitalWardModel(mesa.Model):
    """Admission and discharge state; actual outcomes stay outside requests."""

    def __init__(self, scenarios: list[DailyScenario], bed_capacity: int):
        super().__init__(rng=0)
        if bed_capacity < 1:
            raise ValueError("Bed capacity must be positive")
        if not scenarios or len({scenario.date for scenario in scenarios}) != len(scenarios):
            raise ValueError("Require nonempty, unique operating dates")
        self.bed_capacity = bed_capacity
        self.episodes: dict[str, WardEpisodeAgent] = {}
        self.by_date: dict[date, list[WardEpisodeAgent]] = {}
        self.last_day: date | None = None
        self._next_day: date | None = None
        self._last_transition: tuple[int, int, int] | None = None
        for scenario in sorted(scenarios, key=lambda item: item.date):
            if scenario.realized_los_days is None or set(scenario.realized_los_days) != {
                case.case_id for case in scenario.cases
            }:
                raise ValueError("Every ward case requires a private observed LOS")
            for case in scenario.cases:
                if case.case_id in self.episodes:
                    raise ValueError("Ward case IDs must be unique across days")
                actual_los = scenario.realized_los_days[case.case_id]
                if actual_los < 1:
                    raise ValueError("Observed LOS must be at least one inclusive day")
                agent = WardEpisodeAgent(self, case, scenario.date,
                                         scenario.realized_minutes[case.case_id], actual_los)
                self.episodes[case.case_id] = agent
                self.by_date.setdefault(scenario.date, []).append(agent)

    def begin_day(self, day: date) -> tuple[int, int, int]:
        if self.last_day is not None and day <= self.last_day:
            raise ValueError("Ward days must advance chronologically")
        discharged = 0
        for agent in self.episodes.values():
            if agent.status == "admitted" and agent.discharge <= day:
                agent.status = "discharged"
                discharged += 1
        arrivals = self.by_date.get(day, [])
        for agent in arrivals:
            agent.status = "waiting"
        self.last_day = day
        occupied = self.occupied
        if occupied > self.bed_capacity:
            raise AssertionError("Observed bed occupancy exceeded capacity")
        return len(arrivals), discharged, occupied

    def step(self) -> None:
        """Mesa's scheduled day step; the runner sets the calendar date first."""
        if self._next_day is None:
            raise ValueError("Set the next operating date before advancing Mesa")
        self._last_transition = self.begin_day(self._next_day)
        self._next_day = None

    def advance_day(self, day: date) -> tuple[int, int, int]:
        self._next_day = day
        self.step()  # Mesa 3.5.1 runs the saved user step and increments model time.
        assert self._last_transition is not None
        return self._last_transition

    @property
    def occupied(self) -> int:
        return sum(agent.status == "admitted" for agent in self.episodes.values())

    def offer(self) -> list[WardEpisodeAgent]:
        """Older waits first, then shorter predicted stays within each cohort."""
        available = self.bed_capacity - self.occupied
        waiting = (agent for agent in self.episodes.values() if agent.status == "waiting")
        ordered = sorted(waiting, key=lambda agent: (
            agent.arrival, agent.case.predicted_los_days,
            agent.case.predicted_minutes, agent.case.case_id))
        return ordered[:available]

    def daily_scenario(self, day: date, offered: list[WardEpisodeAgent]) -> DailyScenario:
        return DailyScenario(day, tuple(agent.case for agent in offered),
                             {agent.case.case_id: agent._room_minutes for agent in offered},
                             {agent.case.case_id: agent._actual_los_days for agent in offered})

    def accept_execution(self, day: date, offered: list[WardEpisodeAgent], executed: list[dict]) -> int:
        by_id = {agent.case.case_id: agent for agent in offered}
        if set(by_id) != {row["case_id"] for row in executed}:
            raise ValueError("Room execution must conserve offered cases")
        started = 0
        for row in executed:
            if row["start"] is None:
                continue
            if row["status"] != "completed":
                raise ValueError("A started room case must finish before the next day")
            agent = by_id[row["case_id"]]
            agent.status = "admitted"
            agent.admitted = day
            agent.discharge = day + timedelta(days=agent._actual_los_days)
            started += 1
        if self.occupied > self.bed_capacity:
            raise AssertionError("Admission overfilled the ward")
        return started

    def summary(self, end: date) -> dict:
        started = [agent for agent in self.episodes.values() if agent.admitted]
        waiting = [agent for agent in self.episodes.values() if agent.status == "waiting"]
        return {
            "cases": len(self.episodes), "surgeries_completed": len(started),
            "never_started": len(waiting),
            "still_admitted": self.occupied,
            "discharged": sum(agent.status == "discharged" for agent in self.episodes.values()),
            "mean_wait_days_started": (
                sum((agent.admitted - agent.arrival).days for agent in started) / len(started)
                if started else None),
            "occupied_bed_days_within_horizon": sum(
                max(0, (min(agent.discharge, end + timedelta(days=1)) - agent.admitted).days)
                for agent in started),
            "waiting_case_days_at_horizon": sum((end - agent.arrival).days + 1 for agent in waiting),
        }
