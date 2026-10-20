"""Meaningful checks of synthetic experiment construction and comparability."""
import unittest

import pandas as pd

from experiments.run_feasibility import ARMS, execute_run, generate_workload
from optimiseur.feasibility import FullStayPlanningProblem, run_validated_sa
from optimiseur.optimizer import PlanningProblem, simulated_annealing
from optimiseur.search_control import SearchControl
from optimiseur.validation import validate_full_stay


class TestExperiment(unittest.TestCase):
    def test_all_workloads_have_independently_feasible_witness(self):
        for seed in range(1100, 1112):
            workload = generate_workload(seed)
            self.assertEqual(workload, generate_workload(seed))
            p, v = pd.DataFrame(workload["patients"]), pd.DataFrame(workload["sessions"])
            self.assertTrue(validate_full_stay(p, v, workload["bed_capacities"],
                            workload["feasible_witness"], workload["patient_options"]).feasible)
            for sol in workload["initial_assignments"].values():
                self.assertEqual(set(sol), set(range(len(p))))

    def test_baseline_returns_identical_legacy_search(self):
        w = generate_workload(1100)
        p, v = pd.DataFrame(w["patients"]), pd.DataFrame(w["sessions"])
        initial = w["initial_assignments"]["0"]
        legacy = PlanningProblem(p, v, lits_capacity=w["bed_capacities"][:4], patient_options=w["patient_options"])
        result = simulated_annealing(legacy, seed=0, initial_solution=initial,
                                     control=SearchControl(max_evaluations=100), n_iter=100)
        full = FullStayPlanningProblem(p, v, w["bed_capacities"], patient_options=w["patient_options"])
        checked = run_validated_sa(full, seed=0, initial_solution=initial,
                                   max_evaluations=100, legacy_accounting=True)
        self.assertEqual(result.meilleure_solution, checked.result.meilleure_solution)
        self.assertEqual(result.meilleure_fitness, checked.result.meilleure_fitness)
        self.assertEqual(result.evaluations, checked.result.evaluations)

    def test_equal_starts_and_budget_all_arms(self):
        w = generate_workload(1108)
        schedules = []
        for arm in ARMS:
            row, schedule = execute_run(w, 0, arm, 50, 30)
            self.assertEqual(row["evaluations"], 50)
            self.assertEqual(row["termination_reason"], "evaluations")
            self.assertTrue(row["valid"])
            schedules.append(schedule)
        self.assertEqual(schedules[0]["initial_assignment"], schedules[1]["initial_assignment"])
        self.assertEqual(schedules[0]["initial_assignment"], schedules[2]["initial_assignment"])

    def test_separate_incumbent_preserved_when_weighted_best_is_infeasible(self):
        from tests.test_feasibility import counterexample
        p, v, beds, options = counterexample()
        problem = FullStayPlanningProblem(p, v, beds, patient_options=options)
        run = run_validated_sa(problem, initial_solution={0: 0, 1: 0}, max_evaluations=60, seed=7)
        self.assertFalse(run.validation.feasible)
        self.assertEqual(run.first_feasible_evaluation, 1)
        self.assertEqual(run.best_feasible_solution, {0: 0, 1: 0})


if __name__ == "__main__":
    unittest.main()
