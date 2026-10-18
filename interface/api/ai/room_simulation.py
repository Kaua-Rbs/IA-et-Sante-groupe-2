"""A bounded what-if preview using the existing Mesa room/coordinator engine."""

from math import ceil

from api.ai.cohort import CohortCase
from hospital_sim.domain import CaseInput, Outage, SimulationConfig
from hospital_sim.historical_data import DailyScenario
from hospital_sim.metaheuristics import METHODS, MetaheuristicScheduler, SearchSettings
from hospital_sim.scheduling import BaselineScheduler
from hospital_sim.simulation import run_day


async def simulate_room_day(
    cases: tuple[CohortCase, ...], *, day, rooms: int, booked_minutes: tuple[int, ...] = (),
    method: str = "baseline", policy: str = "reactive", realized_factor: float = 1.2,
    outage: bool = True,
) -> dict:
    """Use predictions for planning and a declared stress factor for execution.

    This is a room-only exploration with identical synthetic rooms. Existing
    bookings of the day (``booked_minutes``, their planned room time) share the
    rooms with the pending cases and are stressed by the same factor. It does
    not use historical outcomes, book clinical resources, or infer patient results.
    """
    if method not in METHODS or policy not in ("static", "reactive"):
        raise ValueError("Unknown simulation method or policy")
    if not 1 <= rooms <= 20 or not 1 <= realized_factor <= 2:
        raise ValueError("Choose 1-20 rooms and a realized-duration factor of 1-2")
    if len(cases) > 30:
        raise ValueError("Limit the room preview to 30 cases")
    if len(booked_minutes) > 200 or any(minutes < 1 for minutes in booked_minutes):
        raise ValueError("Unsupported existing bookings for the room preview")
    selected = tuple(
        case for case in cases
        if case.earliest_date <= day <= case.latest_date and day not in case.rejected_dates
    )
    pending = tuple(CaseInput(f"case-{index:04d}", str(case.specialty_id),
                              ceil(case.room_minutes), case.los_days)
                    for index, case in enumerate(selected, 1))
    booked = tuple(CaseInput(f"booked-{index:04d}", "booked", minutes)
                   for index, minutes in enumerate(booked_minutes, 1))
    inputs = pending + booked
    realized = {case.case_id: ceil(case.predicted_minutes * realized_factor)
                for case in inputs}
    if any(value > 1440 for value in realized.values()):
        raise ValueError("The stressed room duration exceeds one day")
    scenario = DailyScenario(day, inputs, realized)
    closure = Outage("room-1", 600, 720) if outage else None
    config = SimulationConfig(rooms=rooms, turnover=15, outage=closure)
    settings = SearchSettings(method=method, seed=0, max_evaluations=200)
    scheduler = (BaselineScheduler() if method == "baseline"
                 else MetaheuristicScheduler(settings))
    result = await run_day(scenario, config, policy, scheduler=scheduler,
                           timeout_seconds=2.0)
    metrics = result["metrics"]
    status = {row["case_id"]: row["status"] for row in result["executed_schedule"]}

    def count(group, value):
        return sum(status.get(case.case_id) == value for case in group)

    return {
        "date": day.isoformat(), "method": method, "policy": policy,
        "cases": len(pending), "completed": count(pending, "completed"),
        "unstarted": count(pending, "waiting"),
        "booked_cases": len(booked), "booked_completed": count(booked, "completed"),
        "overtime_minutes": metrics["overtime_minutes_including_turnover"],
        "replanning_count": metrics["replanning_count"],
        "failures": metrics["failures"],
        "assumptions": {
            "rooms": rooms, "opening": "08:00", "closing": "17:00",
            "turnover_minutes": 15, "room_1_closure": "10:00-12:00" if outage else None,
            "realized_duration_factor": realized_factor,
            "beds_and_specialty_constraints": "not simulated in this room preview",
        },
    }
