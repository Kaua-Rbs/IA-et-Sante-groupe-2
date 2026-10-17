"""Read-only Mesa preview of pending cases across operating days and bed units."""

import datetime as dt
from math import ceil

import mesa

from api.ai.cohort import CohortCase
from api.ai.contracts import BedUnitLoad, VacationSlot
from hospital_sim.domain import CaseInput, Outage, SimulationConfig
from hospital_sim.historical_data import DailyScenario
from hospital_sim.metaheuristics import METHODS, MetaheuristicScheduler, SearchSettings
from hospital_sim.scheduling import BaselineScheduler
from hospital_sim.simulation import run_day


class WebEpisodeAgent(mesa.Agent):
    def __init__(self, model, case: CohortCase, case_id: str, realized_factor: float,
                 los_factor: float):
        super().__init__(model)
        self.case = case
        self.case_id = case_id
        self.realized_minutes = ceil(case.room_minutes * realized_factor)
        self._realized_los_days = ceil(case.los_days * los_factor)
        self.status = "not_ready"
        self.started: dt.date | None = None
        self.discharge: dt.date | None = None
        self.bed_unit_id: int | None = None


class WebWardModel(mesa.Model):
    """Bed-aware admission policy; hidden outcomes remain on the agents."""

    def __init__(self, cases: tuple[CohortCase, ...], units: tuple[BedUnitLoad, ...],
                 realized_factor: float, los_factor: float):
        super().__init__(rng=0)
        self.episodes = [
            WebEpisodeAgent(self, case, f"web-{index:04d}", realized_factor, los_factor)
            for index, case in enumerate(sorted(cases, key=lambda c: str(c.request_id)), 1)
        ]
        self.units = {unit.id: unit for unit in units if unit.capacity > 0}
        self._day: dt.date | None = None
        self._occupied: dict[tuple[int, dt.date], int] = {}

    def step(self) -> None:
        if self._day is None:
            raise ValueError("Set the day before stepping the ward")
        for agent in self.episodes:
            if agent.status == "admitted" and agent.discharge <= self._day:
                agent.status = "discharged"
            if agent.status == "not_ready" and agent.case.earliest_date <= self._day:
                agent.status = "waiting"
        self._day = None

    def advance(self, day: dt.date) -> None:
        self._day = day
        self.step()

    def occupancy(self, unit_id: int, day: dt.date) -> int:
        unit = self.units[unit_id]
        return unit.occupancy.get(day, 0) + self._occupied.get((unit_id, day), 0)

    def forecast_occupancy(self, unit_id: int, day: dt.date, as_of: dt.date) -> int:
        """Use observed presence and predicted release, never hidden future LOS."""
        occupied = self.units[unit_id].occupancy.get(day, 0)
        for agent in self.episodes:
            if agent.status != "admitted" or agent.bed_unit_id != unit_id:
                continue
            expected_release = max(
                as_of + dt.timedelta(days=1),
                agent.started + dt.timedelta(days=agent.case.los_days),
            )
            if agent.started <= day < expected_release:
                occupied += 1
        return occupied

    def offer(self, day: dt.date, vacations: tuple[VacationSlot, ...],
              emergency_margin: float) -> tuple[list[WebEpisodeAgent], dict[str, int]]:
        free_minutes = {
            slot.id: max(0, int(slot.duration_min * (1 - emergency_margin)) - slot.used_min)
            for slot in vacations if slot.date == day
        }
        tentative_beds: dict[tuple[int, dt.date], int] = {}
        offered: list[WebEpisodeAgent] = []
        selected_units: dict[str, int] = {}
        waiting = sorted(
            (agent for agent in self.episodes
             if agent.status == "waiting" and day <= agent.case.latest_date
             and day not in agent.case.rejected_dates),
            key=lambda agent: (
                agent.case.earliest_date, agent.case.los_days,
                agent.case.room_minutes, agent.case_id,
            ),
        )
        for agent in waiting:
            case = agent.case
            minutes = ceil(case.room_minutes)
            eligible = sorted(
                (slot for slot in vacations if slot.date == day
                 and slot.specialty_id == case.specialty_id
                 and slot.surgeon_id in (None, case.surgeon_id)
                 and free_minutes.get(slot.id, 0) >= minutes),
                key=lambda slot: (free_minutes[slot.id] - minutes, slot.id),
            )
            if not eligible:
                continue
            stay = [day + dt.timedelta(days=offset) for offset in range(case.los_days)]
            possible_units = sorted(
                (unit for unit in self.units.values() if unit.care_type == case.care_type
                 and all(self.forecast_occupancy(unit.id, date, day) +
                         tentative_beds.get((unit.id, date), 0) < unit.capacity
                         for date in stay)),
                key=lambda unit: (
                    max((self.forecast_occupancy(unit.id, date, day)
                         + tentative_beds.get((unit.id, date), 0) + 1) / unit.capacity
                        for date in stay),
                    unit.id,
                ),
            )
            if not possible_units:
                continue
            slot, unit = eligible[0], possible_units[0]
            free_minutes[slot.id] -= minutes
            for date in stay:
                tentative_beds[(unit.id, date)] = tentative_beds.get((unit.id, date), 0) + 1
            selected_units[agent.case_id] = unit.id
            offered.append(agent)
        return offered, selected_units

    def accept(self, day: dt.date, offered: list[WebEpisodeAgent],
               selected_units: dict[str, int], executed: list[dict]) -> int:
        by_id = {agent.case_id: agent for agent in offered}
        if set(by_id) != {row["case_id"] for row in executed}:
            raise ValueError("Room execution did not conserve offered cases")
        started = 0
        for row in executed:
            if row["start"] is None:
                continue
            if row["status"] != "completed":
                raise ValueError("A started room case must finish before the next day")
            agent = by_id[row["case_id"]]
            agent.status = "admitted"
            agent.started = day
            agent.discharge = day + dt.timedelta(days=agent._realized_los_days)
            agent.bed_unit_id = selected_units[agent.case_id]
            for offset in range(agent._realized_los_days):
                date = day + dt.timedelta(days=offset)
                key = (agent.bed_unit_id, date)
                self._occupied[key] = self._occupied.get(key, 0) + 1
            started += 1
        return started

    def overcapacity_days(self, start: dt.date, end: dt.date) -> int:
        days = tuple(start + dt.timedelta(days=offset)
                     for offset in range((end - start).days + 1))
        return sum(
            self.occupancy(unit.id, day) > unit.capacity
            and unit.occupancy.get(day, 0) <= unit.capacity
            for unit in self.units.values()
            for day in days
        )


async def simulate_ward_window(
    cases: tuple[CohortCase, ...], vacations: tuple[VacationSlot, ...],
    bed_units: tuple[BedUnitLoad, ...], *, start: dt.date, end: dt.date,
    emergency_margin: float, method: str = "baseline", policy: str = "reactive",
    realized_factor: float = 1.2, los_factor: float = 1.0, outage: bool = True,
) -> dict:
    if method not in METHODS or policy not in ("static", "reactive"):
        raise ValueError("Unknown simulation method or policy")
    if not (1 <= realized_factor <= 2 and 1 <= los_factor <= 2):
        raise ValueError("Realized-duration factors must be between 1 and 2")
    if end < start or (end - start).days > 13 or len(cases) > 30:
        raise ValueError("Choose at most 14 days and 30 pending cases")
    if any(case.los_days < 1 or case.room_minutes <= 0 for case in cases):
        raise ValueError("Cases need positive predicted room and stay durations")
    ward = WebWardModel(cases, bed_units, realized_factor, los_factor)
    if any(agent.realized_minutes > 1440 for agent in ward.episodes):
        raise ValueError("A stressed room duration exceeds one day")
    daily = []
    overtime = replans = failures = 0
    for offset in range((end - start).days + 1):
        day = start + dt.timedelta(days=offset)
        ward.advance(day)
        day_slots = tuple(slot for slot in vacations if slot.date == day)
        offered, selected_units = ward.offer(day, day_slots, emergency_margin)
        started = 0
        if offered:
            rooms = len({slot.room_name for slot in day_slots})
            if rooms < 1:
                raise ValueError("No room is available for offered cases")
            inputs = tuple(CaseInput(agent.case_id, str(agent.case.specialty_id),
                                     ceil(agent.case.room_minutes), agent.case.los_days)
                           for agent in offered)
            scenario = DailyScenario(
                day, inputs, {agent.case_id: agent.realized_minutes for agent in offered},
                {agent.case_id: agent._realized_los_days for agent in offered},
            )
            closure = Outage("room-1", 600, 720) if outage else None
            config = SimulationConfig(rooms=rooms, turnover=15, outage=closure)
            settings = SearchSettings(method=method, seed=0, max_evaluations=200)
            scheduler = (BaselineScheduler() if method == "baseline"
                         else MetaheuristicScheduler(settings))
            result = await run_day(scenario, config, policy, scheduler=scheduler,
                                   timeout_seconds=2.0)
            started = ward.accept(day, offered, selected_units, result["executed_schedule"])
            metrics = result["metrics"]
            overtime += metrics["overtime_minutes_including_turnover"]
            replans += metrics["replanning_count"]
            failures += metrics["failures"]
        daily.append({
            "date": day.isoformat(), "offered": len(offered), "started": started,
            "waiting": sum(agent.status == "waiting" for agent in ward.episodes),
            "occupied_beds": sum(
                ward.occupancy(unit.id, day) for unit in ward.units.values()
            ),
        })
    completed = sum(agent.started is not None for agent in ward.episodes)
    horizon = end + dt.timedelta(days=max(
        (agent._realized_los_days for agent in ward.episodes), default=1) - 1)
    return {
        "start": start.isoformat(), "end": end.isoformat(), "cases": len(cases),
        "completed": completed, "unstarted": len(cases) - completed,
        "overtime_minutes": overtime, "replanning_count": replans,
        "failures": failures, "overcapacity_bed_days": ward.overcapacity_days(start, horizon),
        "daily": daily,
        "assumptions": {
            "turnover_minutes": 15, "opening": "08:00", "closing": "17:00",
            "realized_room_factor": realized_factor, "realized_los_factor": los_factor,
            "room_1_closure": "10:00-12:00" if outage else None,
            "existing_bookings": "counted in vacation minutes and bed occupancy",
            "room_model": "identical rooms; vacation matching checked before Mesa execution",
        },
    }
