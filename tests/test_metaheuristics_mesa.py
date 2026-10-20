"""Shared decoder, budgets and process regression tests."""

import asyncio
from dataclasses import replace
import itertools
import multiprocessing as mp
import random
import time
import unittest
from unittest.mock import patch

from optimiseur import optimizer as op
from optimiseur.search_control import SearchControl
from hospital_sim.contracts import Proposal, Snapshot
from hospital_sim.domain import Assignment, CaseState, Outage, RoomState, Schedule, SimulationConfig
from hospital_sim.metaheuristics import METHODS, MetaheuristicScheduler, SearchSettings
from hospital_sim.room_problem import RoomAllocationProblem
from hospital_sim.scheduling import RoomValidator
from tests.room_instances import exact_reference, opening_request, small_reference
from tests.test_historical_simulation import scenario


def stalled_worker(connection, request, settings, deadline):
    """Picklable worker used to prove deadline/cancellation cleanup."""
    time.sleep(60)


def strip_times(result):
    if isinstance(result, dict):
        return {key: strip_times(value) for key, value in result.items()
                if not key.endswith("_seconds") and key != "history"}
    if isinstance(result, list):
        return [strip_times(value) for value in result]
    return result


class RoomProblemTests(unittest.TestCase):
    def setUp(self):
        self.config = SimulationConfig(rooms=2, closing=660)
        self.request = opening_request(small_reference(), self.config, time.monotonic() + 20)

    def test_nontrivial_exact_reference_and_priority_encoding(self):
        problem = RoomAllocationProblem(self.request)
        objectives = [problem.objective(problem.decode(dict(enumerate(values))))
                      for values in itertools.product(range(2), repeat=7)]
        self.assertEqual(len(objectives), 128)
        self.assertGreater(len({o.cost for o in objectives}), 1)
        by_priority = sorted(objectives, key=lambda o: (o.unstarted, o.overtime, o.changes))
        self.assertEqual([o.cost for o in by_priority], sorted(o.cost for o in objectives))
        result = exact_reference(self.request)
        self.assertEqual(result["allocations"], 128)
        self.assertEqual(result["objective"]["cost"], min(o.cost for o in objectives))
        # Exhaustively exercise all tertiary values at adjacent primary/secondary ranks.
        n, bound = 7, problem.overtime_bound
        encode = lambda u, o, r: u + (o + r / (n + 1)) / (bound + 1)
        self.assertLess(encode(0, bound, n), encode(1, 0, 0))
        self.assertLess(encode(0, 0, n), encode(0, 1, 0))
        self.assertLess(encode(0, 0, 0), encode(0, 0, 1))

    def test_mapping_validation_and_closed_start(self):
        cases = tuple(replace(c, case_id=f"local-{i*37}") for i, c in enumerate(small_reference().cases))
        request = opening_request(replace(small_reference(), cases=cases), self.config, time.monotonic() + 20)
        state = replace(request.snapshot.domain, known_outages=(Outage("room-1", 480, 550),))
        request = replace(request, snapshot=replace(request.snapshot, domain=state))
        problem = RoomAllocationProblem(request)
        result = problem.decode({i: 0 for i in range(7)})
        self.assertEqual(result.assignments[0].start, 550)
        self.assertEqual({a.case_id for a in result.assignments} | set(result.unassigned),
                         {c.case_id for c in cases})
        for invalid in ({}, {i: 5 for i in range(7)}, {i: 0.0 for i in range(7)}):
            with self.assertRaises(ValueError):
                problem.decode(invalid)

    def test_running_fixed_and_observed_availability(self):
        original = Assignment("case-0001", "room-1", 480, 30)
        inputs = scenario((30, 40, 50))
        request = opening_request(inputs, self.config, time.monotonic() + 20)
        state = replace(request.snapshot.domain, minute=500,
                        cases=(CaseState(inputs.cases[0], "running", 480, None, "room-1"),
                               CaseState(inputs.cases[1]), CaseState(inputs.cases[2])),
                        rooms=(RoomState("room-1", 525), RoomState("room-2", 500)))
        request = replace(request, fixed_commitments=(original,), snapshot=Snapshot(
            500, 3, state, Schedule((original,), ("case-0002", "case-0003"))))
        problem = RoomAllocationProblem(request)
        result = problem.decode({0: 0, 1: 0})
        self.assertEqual(result.assignments[0], original)
        self.assertGreaterEqual(result.assignments[1].start, 525)
        self.assertTrue(RoomValidator().validate(request.snapshot, Proposal(result, 3)).feasible)
        self.assertNotIn("realized", repr(request))

    def test_equal_changes_prefer_existing_plan(self):
        request = opening_request(scenario((30, 30)), SimulationConfig(), time.monotonic() + 10)
        problem = RoomAllocationProblem(request)
        old = problem.decode({0: 0, 1: 1})
        request = replace(request, snapshot=replace(request.snapshot, accepted_schedule=old))
        problem = RoomAllocationProblem(request)
        self.assertEqual(problem.objective(old).changes, 0)
        swapped = problem.decode({0: 1, 1: 0})
        self.assertEqual(problem.objective(swapped).changes, 2)
        self.assertGreater(problem.fitness({0: 0, 1: 1}), problem.fitness({0: 1, 1: 0}))

    def test_native_singleton_genetic_and_control_budget(self):
        patients, vacations = op.small_validation_instance()
        problem = op.PlanningProblem(patients.iloc[:1], vacations)
        result = op.genetic_algorithm(problem, pop_size=4, n_gen=2)
        self.assertEqual(set(result.meilleure_solution), {0})
        problem = op.PlanningProblem(patients, vacations)
        seed = problem.random_solution(random.Random(42))
        control = SearchControl(max_evaluations=17)
        result = op.tabu_search(problem, initial_solution=seed, control=control)
        self.assertEqual(result.evaluations, 17)
        self.assertEqual(result.stop_reason, "evaluations")
        self.assertGreaterEqual(result.meilleure_fitness, problem.fitness(seed))


class SearchControlTests(unittest.TestCase):
    def test_control_deadline_is_checked_before_each_evaluation(self):
        from optimiseur.search_control import SearchStopped
        p, v = op.small_validation_instance()
        problem = op.PlanningProblem(p, v)
        control = SearchControl(deadline=10)
        with patch("optimiseur.search_control.monotonic", return_value=9):
            control.evaluate(problem, problem.random_solution(random.Random(0)))
        with patch("optimiseur.search_control.monotonic", return_value=11):
            with self.assertRaises(SearchStopped):
                control.evaluate(problem, {})
        self.assertEqual(control.evaluations, 1)
        self.assertEqual(control.reason, "deadline")


class ProcessAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_adapters_budget_feasibility_and_repeatability(self):
        request = opening_request(small_reference(), SimulationConfig(closing=660), time.monotonic() + 20)
        initial = RoomAllocationProblem(request)
        initial_fitness = initial.fitness(initial.initial_allocation())
        candidates = {}
        for method in METHODS[1:]:
            with self.subTest(method=method):
                request = replace(request, deadline=time.monotonic() + 15)
                adapter = MetaheuristicScheduler(SearchSettings(method, 7, 80))
                candidate = await adapter.propose(request)
                self.assertTrue(RoomValidator().validate(request.snapshot, candidate).feasible)
                report = adapter.reports[-1]
                self.assertEqual(report["stop_reason"], "evaluations")
                self.assertEqual(report["evaluations"], 80)
                self.assertLessEqual(report["objective"]["cost"], -initial_fitness)
                self.assertEqual(set(candidate.schedule.unassigned) |
                                 {a.case_id for a in candidate.schedule.assignments},
                                 {c.case_id for c in small_reference().cases})
                candidates[method] = candidate.schedule
        request = replace(request, deadline=time.monotonic() + 15)
        again = MetaheuristicScheduler(SearchSettings("aco", 7, 80))
        repeated = await again.propose(request)
        self.assertEqual(candidates["aco"], repeated.schedule)

    async def test_zero_one_cases_and_no_rooms_for_every_method(self):
        for method in METHODS[1:]:
            for predictions in ((), (30,)):
                inputs = scenario(predictions)
                request = opening_request(inputs, SimulationConfig(), time.monotonic() + 10)
                result = await MetaheuristicScheduler(SearchSettings(method)).propose(request)
                self.assertTrue(RoomValidator().validate(request.snapshot, result).feasible)
            request = opening_request(scenario(), SimulationConfig(), time.monotonic() + 10)
            request = replace(request, snapshot=replace(request.snapshot, domain=replace(
                request.snapshot.domain, rooms=())))
            result = await MetaheuristicScheduler(SearchSettings(method)).propose(request)
            self.assertEqual(len(result.schedule.unassigned), 4)

    async def test_deadline_and_external_cancellation_leave_no_worker(self):
        before = {p.pid for p in mp.active_children()}
        with patch("hospital_sim.metaheuristics._search_worker", stalled_worker):
            request = opening_request(scenario(), SimulationConfig(), time.monotonic() + 0.2)
            adapter = MetaheuristicScheduler(SearchSettings("aco"))
            result = await adapter.propose(request)
            self.assertTrue(RoomValidator().validate(request.snapshot, result).feasible)
            self.assertEqual(adapter.reports[-1]["stop_reason"], "deadline")
            request = replace(request, deadline=time.monotonic() + 30)
            adapter = MetaheuristicScheduler(SearchSettings("tabu"))
            task = asyncio.create_task(adapter.propose(request))
            await asyncio.sleep(0.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(adapter.reports[-1]["stop_reason"], "cancelled")
        self.assertEqual({p.pid for p in mp.active_children()}, before)



if __name__ == "__main__":
    unittest.main()
