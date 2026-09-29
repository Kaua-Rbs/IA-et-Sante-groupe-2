"""Small exact reference and larger paired historical-workload samples."""

from dataclasses import replace
from datetime import date
from math import ceil, isfinite, prod
import itertools
import random

from .contracts import SchedulingRequest, Snapshot
from .domain import CaseInput, CaseState, HospitalState, RoomState
from .historical_data import DailyScenario
from .room_problem import RoomAllocationProblem


def with_duration_mode(scenario, mode):
    """Oracle explicite : expose les durees realisees comme estimations.

    Appliquer apres le dimensionnement des salles pour comparer les modes
    avec les memes ressources. Ne modifie ni la source ni les realisations.
    """
    if mode == "median":
        return scenario
    if mode != "oracle":
        raise ValueError("Unknown duration mode")
    return replace(scenario, cases=tuple(
        replace(case, predicted_minutes=ceil(scenario.realized_minutes[case.case_id]))
        for case in scenario.cases
    ), realized_minutes=dict(scenario.realized_minutes))


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


def sampled_scenario(data, count, seed):
    if count < 1:
        raise ValueError("Synthetic case counts must be positive")
    pool = data.frame.loc[data.frame["date"].dt.year.eq(2022)]
    if pool.empty:
        raise ValueError("No held-out cases for scenario sampling")
    rng = random.Random(seed)
    cases, realized = [], {}
    # Sample complete rows, retaining procedure-duration associations.
    rows = list(pool.itertuples(index=False))
    for i in range(1, count + 1):
        row = rng.choice(rows)
        identifier = f"case-{i:04d}"
        cases.append(CaseInput(identifier, row.procedure, ceil(data.medians.get(row.procedure, data.fallback))))
        realized[identifier] = ceil(row.duration)
    return DailyScenario(date(2022, 1, 1), tuple(cases), realized)


def scale_rooms(config, scenario, target_load):
    if not isfinite(target_load) or target_load <= 0:
        raise ValueError("Target load must be finite and positive")
    work = sum(c.predicted_minutes + config.turnover for c in scenario.cases)
    rooms = max(1, ceil(work / ((config.closing - config.opening) * target_load)))
    return replace(config, rooms=rooms)
