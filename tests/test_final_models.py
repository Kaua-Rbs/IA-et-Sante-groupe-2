"""Synthetic regression checks; no confidential input or trained artifact needed."""
import unittest
import numpy as np
import pandas as pd

from consultation_features import consultation_features, CONSULTATION_FEATURES
from duration_features import MISSING
from los_model import predict_los_loaded
from surgery_duration import MedianBaseline, predict_schedule_loaded
from prediction_planning import prediction_problem
from optimiseur.validation import validate_full_stay


class FinalModelTests(unittest.TestCase):
    def saved(self, value, log=False):
        X = pd.DataFrame({"age_years": [40.]})
        model = MedianBaseline(()).fit(X, [np.log1p(value) if log else value])
        return {"model": model, "features": ["age_years"], "log_target": log,
                "interval_half_width_days": 1.5, "category_mapping": {}}

    def test_missing_optional_raw_features(self):
        X = consultation_features(pd.DataFrame(index=[0, 1]))
        self.assertEqual(list(X), CONSULTATION_FEATURES)
        self.assertTrue(X.age_years.isna().all())
        self.assertTrue(X.sexe.eq(MISSING).all())

    def test_consultation_whitelist_excludes_outcomes(self):
        X = pd.DataFrame({"age_years": [40], "ccam_1": ["abcd 123"], "sexe": ["féminin"]})
        polluted = X.assign(date_inter="2022-01-01", date_sortie="2050-01-01",
                            anesth_type="CHANGED", nom_chir="SECRET", target_los_days=9999)
        pd.testing.assert_frame_equal(consultation_features(X), consultation_features(polluted))
        self.assertEqual(consultation_features(X).ccam_1.iloc[0], "ABCD123")

    def test_los_direct_and_legacy_log_targets(self):
        X = pd.DataFrame({"age_years": [40.]})
        self.assertAlmostEqual(predict_los_loaded(X, self.saved(3)).los_point_days.iloc[0], 3)
        old = self.saved(3, True)
        old.pop("log_target")
        self.assertAlmostEqual(predict_los_loaded(X, old).los_point_days.iloc[0], 3)

    def test_invalid_interval_width_rejected(self):
        for width in (-1, np.nan, np.inf, [1, 2]):
            saved = self.saved(3)
            saved["interval_half_width_days"] = width
            with self.subTest(width=width), self.assertRaises(ValueError):
                predict_los_loaded(pd.DataFrame({"age_years": [40.]}), saved)

    def test_point_residual_bounds_and_old_bound_schema(self):
        saved = self.saved(40)
        saved["bounds"] = {"p80": {"base": "point", "offset": 10},
                           "p95": {"base": "point", "offset": 20}}
        X = pd.DataFrame({"age_years": [40.]})
        result = predict_schedule_loaded(X, saved)
        self.assertEqual(result.duration_p95_min.iloc[0], 60)
        saved["bounds"] = {"p80": {"model": self.saved(45)["model"], "offset": 5}}
        self.assertEqual(predict_schedule_loaded(X, saved).duration_p80_min.iloc[0], 50)

    def inputs(self):
        patients = pd.DataFrame({"patient_id": ["p1", "p2"], "specialite": ["A", "A"]})
        sessions = pd.DataFrame({"vacation_id": ["v1"], "specialite": ["A"], "jour": [1], "capacite_min": [100]})
        room = pd.DataFrame({"duration_point_min": [20.2, 30.]})
        los = pd.DataFrame({"los_point_days": [1., 4.2]})
        return patients, sessions, room, los

    def test_synthetic_predictions_through_full_stay_validator(self):
        p, s, r, l = self.inputs()
        problem = prediction_problem(p, s, r, l, [2]*6,
                                     known_preop_days=pd.Series([0, 1]))
        self.assertEqual(problem.patients.duree_operatoire.tolist(), [21, 30])
        self.assertEqual(problem.patients.duree_sejour.tolist(), [0, 3])
        verified = validate_full_stay(problem.patients, s, [2]*6, {0: 0, 1: 0})
        self.assertTrue(verified.feasible)
        self.assertEqual(verified.occupancy, (0, 2, 1, 1, 1, 0))
        self.assertTrue("duree_sejour" not in p)

    def test_tail_capacities_are_required(self):
        with self.assertRaises(ValueError):
            prediction_problem(*self.inputs(), [2, 2])

    def test_bad_predictions_alignment_and_preop_rejected(self):
        for bad in (0, -1, np.nan, np.inf):
            p, s, r, l = self.inputs()
            r.loc[0, "duration_point_min"] = bad
            with self.assertRaises(ValueError):
                prediction_problem(p, s, r, l, [2]*8)
        p, s, r, l = self.inputs()
        with self.assertRaises(ValueError):
            prediction_problem(p, s, r.iloc[::-1], l, [2]*8)
        with self.assertRaises(ValueError):
            prediction_problem(p, s, r, l, [2]*8, known_preop_days=pd.Series([0, .5]))


if __name__ == "__main__":
    unittest.main()
