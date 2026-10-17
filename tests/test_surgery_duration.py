"""Garanties de separation et de repli des baselines de duree."""
import unittest
import importlib.util
import numpy as np
import pandas as pd
import tempfile
from pathlib import Path
from duration_features import engineer_features, fit_category_mapping, apply_category_mapping
ML_AVAILABLE = all(importlib.util.find_spec(name) for name in ['sklearn', 'xgboost', 'catboost', 'joblib'])
if ML_AVAILABLE:
    import joblib
    from surgery_duration import MedianBaseline, validate_split
    from surgery_duration import (predict_schedule, apply_predicted_durations, calibration_split,
                                 conformal_offset, tail_metrics, FIXED_FEATURES)


@unittest.skipUnless(ML_AVAILABLE, 'Dependances ML optionnelles absentes')
class DurationEvaluationTests(unittest.TestCase):
    def dataset(self):
        return pd.DataFrame({'split': ['train', 'validation', 'test'],
            'split_patient_id': [1, 2, 3],
            'split_event_date': pd.to_datetime(['2020-01-01', '2021-01-01', '2022-01-01']),
            'target_surgery_duration_min': [50., 60., 70.]})

    def test_unseen_group_uses_training_global_median(self):
        X = pd.DataFrame({'procedure': ['A', 'A', 'B'], 'surgeon': ['S', 'S', 'T']})
        model = MedianBaseline(('procedure', 'surgeon')).fit(X, [20, 40, 100])
        future = pd.DataFrame({'procedure': ['A', 'Z'], 'surgeon': ['S', 'S']})
        np.testing.assert_array_equal(model.predict(future), [30, 40])

    def test_repeated_patient_rejected(self):
        d = self.dataset()
        d.loc[2, 'split_patient_id'] = 1
        with self.assertRaises(ValueError):
            validate_split(d)

    def test_sparse_group_uses_global_median(self):
        X = pd.DataFrame({'procedure': ['A', 'A', 'B']})
        model = MedianBaseline(('procedure',), min_count=2).fit(X, [20, 40, 100])
        np.testing.assert_array_equal(model.predict(pd.DataFrame({'procedure': ['A', 'B', 'Z']})), [30, 40, 40])

    def test_missing_patient_rejected(self):
        d = self.dataset()
        d.loc[2, 'split_patient_id'] = np.nan
        with self.assertRaises(ValueError):
            validate_split(d)

    def test_temporal_overlap_rejected(self):
        d = self.dataset()
        d.loc[2, 'split_event_date'] = pd.Timestamp('2020-01-01')
        with self.assertRaises(ValueError):
            validate_split(d)

    def test_existing_split_preserved(self):
        d = self.dataset()
        parts = validate_split(d)
        self.assertEqual([list(p.index) for p in parts], [[0], [1], [2]])

    def test_calibration_is_later_and_patient_disjoint(self):
        d = pd.DataFrame({'split_patient_id': [1, 2, 1, 3],
            'split_event_date': pd.to_datetime(['2021-01-01', '2021-02-01', '2021-03-01', '2021-04-01'])})
        selection, calibration = calibration_split(d)
        self.assertLess(selection.split_event_date.max(), calibration.split_event_date.min())
        self.assertFalse(set(selection.split_patient_id) & set(calibration.split_patient_id))

    def test_conformal_uses_finite_sample_rank(self):
        self.assertEqual(conformal_offset(np.arange(1, 21), np.zeros(20), .95), 20.)
        with self.assertRaises(ValueError):
            conformal_offset([1], [0], .95)

    def test_empty_tail_is_reported_without_crashing(self):
        self.assertEqual(tail_metrics([10], [12], 100)['tail_n'], 0)

    def test_raw_inference_saved_mapping_and_subset(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / 'model.joblib'
            model = MedianBaseline(('interv_type',)).fit(pd.DataFrame({'interv_type': ['A', '__RARE__']}), [30, 70])
            joblib.dump(dict(model=model, features=['interv_type'], log_target=False,
                             category_mapping={'interv_type': {'A'}}), artifact)
            frame = pd.DataFrame({'interv_type': [' a ', 'new']}, index=[5, 7])
            predictions = predict_schedule(frame, artifact, raw=True)
            np.testing.assert_array_equal(predictions.duration_point_min, [30, 70])
            patients = pd.DataFrame({'patient_id': [1, 2]}, index=frame.index)
            result = apply_predicted_durations(patients, frame, artifact, raw=True)
            np.testing.assert_array_equal(result.duree_operatoire, [30, 70])
            self.assertNotIn('duree_operatoire', patients)
            with self.assertRaises(ValueError):
                apply_predicted_durations(patients, frame, artifact, risk='p95', raw=True)
            with self.assertRaises(ValueError):
                apply_predicted_durations(patients, frame.iloc[::-1], artifact, raw=True)

    def test_invalid_predictions_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / 'model.joblib'
            for value in [-1, np.nan, np.inf]:
                model = MedianBaseline().fit(pd.DataFrame({'interv_type': ['A']}), [value])
                joblib.dump(dict(model=model, features=['interv_type'], log_target=False), artifact)
                with self.assertRaises(ValueError):
                    predict_schedule(pd.DataFrame({'interv_type': ['A']}), artifact)

    def test_raw_normalization_and_training_only_rarity(self):
        raw = pd.DataFrame({'ccam_1': [' ab-c123 ', None], 'interv_type': [' Chirúrgie ', 'new']})
        features = engineer_features(raw, ['ccam_1', 'ccam_1_family', 'interv_type'])
        self.assertEqual(features.ccam_1.iloc[0], 'ABC123')
        self.assertEqual(features.ccam_1_family.iloc[0], 'ABC1')
        self.assertEqual(features.interv_type.iloc[0], 'CHIRURGIE')
        mapping = fit_category_mapping(features.iloc[:1], ['interv_type'], min_count=1)
        grouped = apply_category_mapping(features, mapping)
        self.assertEqual(grouped.interv_type.iloc[1], '__RARE__')
        self.assertFalse(any(c.startswith('intervention_') for c in FIXED_FEATURES))

    def test_saved_bounds_are_ordered_and_adapter_uses_risk(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / 'model.joblib'
            frame = pd.DataFrame({'interv_type': ['A']})
            def constant(value):
                return MedianBaseline().fit(frame, [value])
            joblib.dump(dict(model=constant(60), features=['interv_type'], log_target=False,
                bounds={'p80': dict(model=constant(40), offset=10),
                        'p95': dict(model=constant(50), offset=20)}), artifact)
            result = predict_schedule(frame, artifact)
            self.assertEqual(result.duration_p80_min.iloc[0], 60)
            self.assertEqual(result.duration_p95_min.iloc[0], 70)
            patients = pd.DataFrame({'patient_id': [1]})
            self.assertEqual(apply_predicted_durations(patients, frame, artifact, risk='p95').duree_operatoire.iloc[0], 70)
            saved = joblib.load(artifact)
            saved['features'] = ['intervention_is_weekend']
            joblib.dump(saved, artifact)
            with self.assertRaises(ValueError):
                apply_predicted_durations(patients, frame, artifact)
