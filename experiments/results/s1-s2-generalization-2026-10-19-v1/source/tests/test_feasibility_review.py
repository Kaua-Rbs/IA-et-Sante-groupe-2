"""Review regressions: reject ambiguous supply and retain strict constraints."""
import itertools
import unittest

import numpy as np
import pandas as pd

from optimiseur.feasibility import FullStayPlanningProblem, run_validated_sa
from optimiseur.validation import validate_full_stay
from tests.test_feasibility import counterexample


class TestReview(unittest.TestCase):
    def test_mapping_and_set_cannot_be_mistaken_for_capacity_values(self):
        p, v, _, options = counterexample()
        for beds in ({2: 0, 3: 0}, {2, 3}, frozenset((2, 3))):
            with self.subTest(beds=beds):
                with self.assertRaisesRegex(ValueError, "ordered vector"):
                    FullStayPlanningProblem(p, v, beds, patient_options=options)
                report = validate_full_stay(p, v, beds, {0: 0, 1: 0}, options)
                self.assertFalse(report.valid)
                self.assertFalse(report.feasible)

    def test_ordered_numpy_capacity_and_nonpositional_external_ids(self):
        p, v, beds, options = counterexample()
        p["patient_id"] = [90, 12]
        v["vacation_id"] = [501, 73]
        problem = FullStayPlanningProblem(p, v, np.asarray(beds), patient_options=options,
                                           objective_mode="feasibility_first")
        self.assertEqual(problem.bed_capacities, (2, 0))
        run = run_validated_sa(problem, initial_solution={0: 0, 1: 0}, max_evaluations=30)
        self.assertTrue(run.validation.feasible)
        self.assertEqual(set(run.result.meilleure_solution), {0, 1})

    def test_restrictive_options_long_tail_and_fixed_assignment(self):
        p, v, _, _ = counterexample()
        p["duree_sejour"] = [2, 5]
        beds = [1, 2, 2, 1, 1, 1, 1]
        options = [[0], [1]]
        problem = FullStayPlanningProblem(p, v, beds, patient_options=options,
                                           objective_mode="feasibility_first")
        run = run_validated_sa(problem, initial_solution={0: 0, 1: 1}, max_evaluations=50)
        self.assertTrue(run.validation.feasible)
        self.assertEqual(run.validation.occupancy, (1, 2, 2, 1, 1, 1, 1))
        self.assertEqual(run.result.meilleure_solution, {0: 0, 1: 1})

    def test_medium_size_scalar_fitness_finite_and_oracle_agrees(self):
        n = 60
        p = pd.DataFrame({"patient_id": range(n), "specialite": ["X"] * n,
                          "duree_operatoire": [30 + 15 * (i % 5) for i in range(n)],
                          "duree_sejour": [i % 8 for i in range(n)]})
        v = pd.DataFrame({"vacation_id": range(10), "specialite": ["X"] * 10,
                          "jour": range(10), "capacite_min": [500] * 10})
        options = [[i // 6] for i in range(n)]
        beds = [60] * 17
        sol = {i: i // 6 for i in range(n)}
        problem = FullStayPlanningProblem(p, v, beds, patient_options=options,
                                           objective_mode="feasibility_first")
        report = validate_full_stay(p, v, beds, sol, options)
        self.assertTrue(report.feasible)
        self.assertTrue(np.isfinite(problem.fitness(sol)))
        self.assertGreater(problem.fitness(sol), -1)
        self.assertEqual(tuple(problem.occupation_lits(sol)), report.occupancy)


if __name__ == "__main__":
    unittest.main()
