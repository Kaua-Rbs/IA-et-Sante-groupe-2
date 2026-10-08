"""Shared decoder, budgets, processes and paired experiment regression tests."""

import asyncio
from dataclasses import asdict, replace
from datetime import date
import itertools
import multiprocessing as mp
import random
import time
import unittest
from unittest.mock import patch

from optimiseur import optimizer as op
from optimiseur.search_control import SearchControl
from hospital_sim.contracts import Proposal, SchedulingRequest, Snapshot
from hospital_sim.domain import Assignment, CaseState, Outage, RoomState, Schedule, SimulationConfig
from hospital_sim.experiment import plan_initial
from hospital_sim.instances import exact_reference, opening_request, small_reference
from hospital_sim.metaheuristics import METHODS, MetaheuristicScheduler, SearchSettings
from hospital_sim.room_problem import RoomAllocationProblem
from hospital_sim.scheduling import RoomValidator
from hospital_sim.simulation import run_day
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


class InstanceTests(unittest.TestCase):
    def test_sampling_keeps_pairs_and_scales_capacity(self):
        from types import SimpleNamespace
        import pandas as pd
        from hospital_sim.instances import sampled_scenario, scale_rooms
        data = SimpleNamespace(
            frame=pd.DataFrame({"date": pd.to_datetime(["2021-01-01", "2022-01-01", "2022-01-02"]),
                                "procedure": ["TRAIN_ONLY", "A", "B"], "duration": [999, 20, 70]}),
            medians={"A": 30, "B": 60}, fallback=45,
        )
        first = sampled_scenario(data, 100, 3)
        self.assertEqual(first, sampled_scenario(data, 100, 3))
        for case in first.cases:
            self.assertEqual(first.realized_minutes[case.case_id], {"A": 20, "B": 70}[case.procedure])
            self.assertEqual(case.predicted_minutes, {"A": 30, "B": 60}[case.procedure])
        self.assertEqual(len({c.case_id for c in first.cases}), 100)
        light = scale_rooms(SimulationConfig(), first, 0.8)
        heavy = scale_rooms(SimulationConfig(), first, 1.1)
        self.assertGreater(light.rooms, heavy.rooms)
        with self.assertRaises(ValueError):
            scale_rooms(SimulationConfig(), first, 0)

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

    async def test_saved_initial_plan_and_hidden_duration_separation(self):
        config = SimulationConfig(closing=600)
        settings = SearchSettings("annealing", 3, 60)
        inputs = scenario((30, 40, 50, 60))
        initial, report = await plan_initial(inputs, config, settings, 15)
        altered = replace(inputs, realized_minutes={k: 100 for k in inputs.realized_minutes})
        other, _ = await plan_initial(altered, config, settings, 15)
        self.assertEqual(initial, other)
        static = await run_day(inputs, config, "static", MetaheuristicScheduler(settings),
                               initial_schedule=initial, initial_report=report)
        reactive = await run_day(inputs, config, "reactive", MetaheuristicScheduler(settings),
                                 initial_schedule=initial, initial_report=report)
        static["policy"] = "reactive"
        self.assertEqual(strip_times(static), strip_times(reactive))
        self.assertEqual(static["metrics"]["initial_planning_seconds"], report["elapsed_seconds"])

    async def test_initial_failure_returns_explicit_unassigned_plan(self):
        with patch("hospital_sim.experiment.MetaheuristicScheduler.propose", side_effect=ValueError):
            plan, report = await plan_initial(scenario(), SimulationConfig(), SearchSettings("aco"), 1)
        self.assertEqual(len(plan.unassigned), 4)
        self.assertEqual(report["stop_reason"], "initial_failure")

    async def test_closure_at_opening_preserves_shared_initial_plan(self):
        inputs = scenario((30, 40))
        config = SimulationConfig(rooms=1, closing=600)
        initial, report = await plan_initial(inputs, config, SearchSettings(), 10)
        closed = replace(config, outage=Outage("room-1", 480, 540))
        result = await run_day(inputs, closed, "static", MetaheuristicScheduler(),
                               initial_schedule=initial, initial_report=report)
        self.assertEqual(result["schedule_history"][0]["assignments"], [asdict(a) for a in initial.assignments])
        self.assertEqual(result["executed_schedule"][0]["start"], 540)
        self.assertEqual(result["metrics"]["failures"], 0)


if __name__ == "__main__":
    unittest.main()
