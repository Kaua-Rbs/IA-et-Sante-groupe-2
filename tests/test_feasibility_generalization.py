"""Check generator contracts before running fresh evaluation workloads."""
import unittest
import pandas as pd

from experiments.review_feasibility import generate_large_workload
from experiments.run_feasibility import ARMS, execute_run
from optimiseur.validation import validate_full_stay


class TestGeneralization(unittest.TestCase):
    def test_sizes_offsets_restrictions_and_planted_feasibility(self):
        for n, seed, pressure in ((60, 4400, "moderate"), (60, 4401, "near_capacity"),
                                  (300, 4402, "moderate")):
            with self.subTest(n=n, seed=seed):
                w = generate_large_workload(n, seed, pressure)
                self.assertEqual(len(w["patients"]), n)
                self.assertTrue(w["generation"]["restrictive_patient_count"] > 0)
                self.assertTrue(validate_full_stay(pd.DataFrame(w["patients"]), pd.DataFrame(w["sessions"]),
                    w["bed_capacities"], w["feasible_witness"], w["patient_options"]).feasible)
                self.assertEqual(w, generate_large_workload(n, seed, pressure))
                self.assertNotEqual(w["feasible_witness"], w["initial_assignments"]["0"])

    def test_common_initial_and_complete_budget_under_restrictions(self):
        w = generate_large_workload(60, 4403, "near_capacity")
        schedules = []
        for arm in ARMS:
            row, saved = execute_run(w, 0, arm, 40, 15)
            self.assertEqual(row["evaluations"], 40)
            self.assertEqual(row["termination_reason"], "evaluations")
            self.assertTrue(row["valid"])
            self.assertEqual(row["assigned_cases"], 60)
            schedules.append(saved)
        self.assertTrue(all(s["initial_assignment"] == schedules[0]["initial_assignment"] for s in schedules))


if __name__ == "__main__":
    unittest.main()
