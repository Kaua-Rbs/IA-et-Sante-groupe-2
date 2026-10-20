"""Correctness gates for the opt-in S1/S2 experiment; synthetic data only."""
import itertools
import random
import unittest

import pandas as pd

from optimiseur.optimizer import PlanningProblem
from optimiseur.feasibility import FullStayPlanningProblem, run_validated_sa
from optimiseur.validation import validate_full_stay


def counterexample():
    patients = pd.DataFrame({"patient_id": [0, 1], "specialite": ["X", "X"],
                             "duree_operatoire": [1000, 1000], "duree_sejour": [0, 0]})
    sessions = pd.DataFrame({"vacation_id": [10, 11], "jour": [0, 1],
                             "specialite": ["X", "X"], "capacite_min": [2000, 2000]})
    return patients, sessions, [2, 0], [[0], [0, 1]]


class TestFeasibility(unittest.TestCase):
    def test_original_counterexample(self):
        p, v, beds, options = counterexample()
        legacy = PlanningProblem(p, v, lits_capacity=beds, patient_options=options)
        self.assertEqual(legacy.fitness({0: 0, 1: 0}), -50)
        self.assertEqual(legacy.fitness({0: 0, 1: 1}), -3)
        self.assertGreater(legacy.fitness({0: 0, 1: 1}), legacy.fitness({0: 0, 1: 0}))

    def test_feasibility_first_reverses_invalid_preference(self):
        p, v, beds, options = counterexample()
        problem = FullStayPlanningProblem(p, v, beds, patient_options=options,
                                           objective_mode="feasibility_first")
        self.assertGreater(problem.fitness({0: 0, 1: 0}), problem.fitness({0: 0, 1: 1}))
        self.assertTrue(validate_full_stay(p, v, beds, {0: 0, 1: 0}, options).feasible)
        self.assertFalse(validate_full_stay(p, v, beds, {0: 0, 1: 1}, options).feasible)

    def test_tail_same_day_and_legacy_values(self):
        p, v, _, options = counterexample()
        p.loc[1, "duree_sejour"] = 3  # day 1 through day 4 inclusive
        beds = [2, 2, 0, 0, 0]
        sol = {0: 0, 1: 1}
        legacy = PlanningProblem(p, v, lits_capacity=beds[:2], patient_options=options)
        full = FullStayPlanningProblem(p, v, beds, patient_options=options)
        self.assertEqual(legacy.fitness(sol), 0)
        self.assertEqual(legacy.violations(sol), (0, 0))
        self.assertEqual(full.n_days, 2)
        self.assertEqual(full.n_bed_days, 5)
        self.assertEqual(full.occupation_lits(sol).tolist(), [1, 1, 1, 1, 1])
        self.assertEqual(full.violations(sol), (0, 3))
        report = validate_full_stay(p, v, beds, sol, options)
        self.assertTrue(report.valid)
        self.assertFalse(report.feasible)
        self.assertEqual(report.bed_overload_days, 3)
        self.assertEqual(report.tail_bed_overload_days, 3)
        self.assertEqual(full.fitness(sol), -9)

    def test_reject_bad_capacity_vectors(self):
        p, v, _, options = counterexample()
        p.loc[1, "duree_sejour"] = 2
        for beds in (2, [2, 2], [2, 2, -1, 2], [2, 2, float("nan"), 2],
                     [[2, 2, 2, 2]], [2, 2, 2.5, 2], [True, 2, 2, 2]):
            with self.subTest(beds=beds):
                with self.assertRaises(ValueError):
                    FullStayPlanningProblem(p, v, beds, patient_options=options)
                self.assertFalse(validate_full_stay(p, v, beds, {0: 0, 1: 1}, options).feasible)

    def test_invalid_assignments_never_feasible(self):
        p, v, beds, options = counterexample()
        problem = FullStayPlanningProblem(p, v, beds, patient_options=options)
        for sol in ({0: 0}, {0: 1, 1: 0}, {0: 0, 1: -1}, {0: 0, 1: 99},
                    {0: 0, 1: 0, 2: 0}, {0: 0, 1: 0.0}, {False: 0, 1: 0}):
            with self.subTest(sol=sol):
                self.assertFalse(validate_full_stay(p, v, beds, sol, options).feasible)
                with self.assertRaises(ValueError):
                    problem.fitness(sol)

    def test_specialty_mismatch_and_no_options(self):
        p, v, beds, options = counterexample()
        v.loc[1, "specialite"] = "Y"
        for opts in (options, [[0], []], [[0], [1]], [[0], [0.5]]):
            with self.subTest(options=opts):
                with self.assertRaises(ValueError):
                    FullStayPlanningProblem(p, v, beds, patient_options=opts)
        report = validate_full_stay(p, v, beds, {0: 0, 1: 1})
        self.assertFalse(report.feasible)

    def test_bad_los_and_days_rejected(self):
        p, v, beds, options = counterexample()
        for column, value in (("duree_sejour", -1), ("duree_sejour", 0.5),
                              ("duree_operatoire", float("nan"))):
            changed = p.copy()
            changed[column] = changed[column].astype(float)
            changed.loc[0, column] = value
            with self.assertRaises(ValueError):
                FullStayPlanningProblem(changed, v, beds, patient_options=options)
        v["jour"] = [-1, 1]
        with self.assertRaises(ValueError):
            FullStayPlanningProblem(p, v, beds, patient_options=options)

    def test_gradient_and_all_feasible_outrank_infeasible(self):
        p, v, beds, _ = counterexample()
        options = [[0, 1], [0, 1]]
        problem = FullStayPlanningProblem(p, v, beds, patient_options=options,
                                           objective_mode="feasibility_first")
        feasible, infeasible = [], []
        for choices in itertools.product(range(2), repeat=2):
            sol = dict(enumerate(choices))
            score = problem.fitness(sol)
            (feasible if validate_full_stay(p, v, beds, sol, options).feasible else infeasible).append(score)
        self.assertGreater(min(feasible), max(infeasible))
        self.assertGreater(problem.fitness({0: 0, 1: 1}), problem.fitness({0: 1, 1: 1}))

    def test_calendar_oracle_matches_vectorized_occupancy(self):
        rng = random.Random(30)
        for _ in range(25):
            p, v, _, _ = counterexample()
            p["duree_sejour"] = [rng.randrange(5), rng.randrange(5)]
            options = [[0, 1], [0, 1]]
            horizon = 2 + int(p.duree_sejour.max())
            beds = [rng.randrange(3) for _ in range(horizon)]
            problem = FullStayPlanningProblem(p, v, beds, patient_options=options)
            for choices in itertools.product(range(2), repeat=2):
                sol = dict(enumerate(choices))
                report = validate_full_stay(p, v, beds, sol, options)
                self.assertEqual(tuple(problem.occupation_lits(sol)), report.occupancy)
                self.assertEqual(problem.violations(sol), (report.or_overload_minutes, report.bed_overload_days))

    def test_determinism_budget_and_feasible_incumbent(self):
        p, v, beds, options = counterexample()
        results = []
        for _ in range(2):
            problem = FullStayPlanningProblem(p, v, beds, patient_options=options,
                                               objective_mode="feasibility_first")
            results.append(run_validated_sa(problem, seed=7, initial_solution={0: 0, 1: 1},
                                             max_evaluations=60))
        a, b = results
        self.assertEqual(a.result.meilleure_solution, b.result.meilleure_solution)
        self.assertEqual(a.result.meilleure_fitness, b.result.meilleure_fitness)
        self.assertEqual(a.result.evaluations, 60)
        self.assertEqual(a.first_feasible_evaluation, b.first_feasible_evaluation)
        self.assertIsNotNone(a.best_feasible_solution)
        self.assertTrue(a.validation.feasible)
        self.assertEqual(a.result.stop_reason, "evaluations")
        self.assertEqual(a.best_feasible_solution, {0: 0, 1: 0})

    def test_weighted_full_equals_legacy_without_tail(self):
        p, v, beds, options = counterexample()
        legacy = PlanningProblem(p, v, lits_capacity=beds, patient_options=options)
        full = FullStayPlanningProblem(p, v, beds, patient_options=options)
        for sol in ({0: 0, 1: 0}, {0: 0, 1: 1}):
            self.assertEqual(legacy.fitness(sol), full.fitness(sol))

    def test_bad_search_settings_and_empty_workload(self):
        p, v, beds, options = counterexample()
        problem = FullStayPlanningProblem(p, v, beds, patient_options=options)
        for kwargs in ({"max_evaluations": 0}, {"max_evaluations": 1.5},
                       {"max_evaluations": True}, {"alpha": 0}, {"T0": float("nan")},
                       {"safety_seconds": -1}):
            with self.assertRaises(ValueError):
                run_validated_sa(problem, initial_solution={0: 0, 1: 0}, **kwargs)
        empty = FullStayPlanningProblem(p.iloc[:0], v, beds)
        run = run_validated_sa(empty, initial_solution={})
        self.assertTrue(run.validation.feasible)
        self.assertEqual(run.result.evaluations, 1)


if __name__ == "__main__":
    unittest.main()
