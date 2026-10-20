"""Fixtures de test : petite instance de salles et sa référence exacte par énumération."""

from datetime import date
from math import prod
import itertools

from hospital_sim.contracts import SchedulingRequest, Snapshot
from hospital_sim.domain import CaseInput, CaseState, HospitalState, RoomState
from hospital_sim.historical_data import DailyScenario
from hospital_sim.room_problem import RoomAllocationProblem


def opening_request(scenario, config, deadline):
    # No future closure is observable at initial planning.
    state = HospitalState(
        config.opening, tuple(CaseState(c) for c in scenario.cases),
        tuple(RoomState(room, config.opening) for room in config.room_ids),
        config.opening, config.closing, config.turnover,
    )
    return SchedulingRequest(Snapshot(config.opening, 1, state), (), deadline)


def small_reference():
    predicted = (30, 40, 50, 60, 70, 80, 90)
    realized = (35, 50, 45, 80, 65, 100, 120)
    cases = tuple(CaseInput(f"case-{i:04d}", "REFERENCE", p) for i, p in enumerate(predicted, 1))
    return DailyScenario(date(2022, 1, 1), cases,
                         {case.case_id: r for case, r in zip(cases, realized)})


def exact_reference(request, max_allocations=100_000):
    problem = RoomAllocationProblem(request)
    count = prod(len(problem._options_for(i)) for i in range(problem.n_patients))
    if count > max_allocations:
        raise ValueError("Exact reference exceeds enumeration limit")
    best, score = None, float("-inf")
    for values in itertools.product(range(problem.n_vacations), repeat=problem.n_patients):
        allocation = dict(enumerate(values))
        value = problem.fitness(allocation)
        if value > score:
            best, score = allocation, value
    return {"allocations": count, "fitness": score, "objective": problem.describe(best),
            "allocation": best}

