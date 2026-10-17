"""Prediction separation and cross-day room/bed execution invariants."""

from dataclasses import replace
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from bridge_los import build_patients_with_uncertainty
from hospital_sim.domain import CaseInput, SimulationConfig
from hospital_sim.historical_data import DailyScenario
from hospital_sim.historical_data import ROOM_IN, ROOM_OUT, load_historical
from hospital_sim.predictions import ModelPredictions
from hospital_sim.simulation import run_day
from hospital_sim.ward import HospitalWardModel


class PredictionBoundaryTests(unittest.TestCase):
    def test_bed_outcome_starts_on_surgery_day_not_admission(self):
        rows = pd.DataFrame({
            "no_cas": [1, 2], "interv_type": ["A", "A"],
            "date_entree": ["2020-01-01", "2022-01-03"],
            "date_inter": ["2020-01-03", "2022-01-05"],
            "date_sortie": ["2020-01-05", "2022-01-07"],
            ROOM_IN: ["08:00", "08:00"], ROOM_OUT: ["09:00", "09:00"],
        })
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.xlsx"
            path.write_bytes(b"fixture")
            with patch("hospital_sim.historical_data.pd.read_excel", return_value=rows):
                data = load_historical(path)
        case = data.scenario(date(2022, 1, 5))
        self.assertEqual(case.realized_los_days["case-0001"], 3)
        self.assertEqual(case.preop_days["case-0001"], 2)
        self.assertEqual(data.quality["missing_or_invalid_postop_los_rows"], 0)

    def test_hidden_outcomes_cannot_change_model_inputs(self):
        first = DailyScenario(
            date(2022, 1, 3), (CaseInput("case-1", "A", 30),),
            {"case-1": 45}, {"case-1": 2}, {"case-1": 1001}, {"case-1": 1},
        )
        lookup = ModelPredictions(pd.DataFrame({
            "duration_point_min": [42.1], "duration_p80_min": [55.0],
            "duration_p95_min": [70.0], "los_point_days": [1.8],
            "los_upper_days": [3.4],
        }, index=[1001]), {})
        different_outcomes = replace(first, realized_minutes={"case-1": 120},
                                     realized_los_days={"case-1": 8})
        self.assertEqual(lookup.apply(first).cases, lookup.apply(different_outcomes).cases)
        self.assertEqual(lookup.apply(first).cases[0].predicted_minutes, 43)
        self.assertEqual(lookup.apply(first).cases[0].predicted_los_days, 1)
        self.assertEqual(lookup.apply(first, "p95", "upper").cases[0].predicted_los_days, 3)
        self.assertNotIn("1001", repr(first))

    def test_missing_prediction_fails_without_exposing_source_key(self):
        scenario = DailyScenario(date(2022, 1, 3), (CaseInput("case-1", "A", 30),),
                                 {"case-1": 30}, {"case-1": 1}, {"case-1": 1001}, {"case-1": 0})
        lookup = ModelPredictions(pd.DataFrame({"duration_point_min": [30],
                                                "los_point_days": [1]}, index=[1002]), {})
        with self.assertRaisesRegex(ValueError, "no preoperative prediction") as context:
            lookup.apply(scenario)
        self.assertNotIn("1001", str(context.exception))

    def test_vacation_bridge_uses_both_predictions_not_observed_targets(self):
        eda = pd.DataFrame({
            "id_patient": [11, 22], "date_inter": pd.to_datetime(["2022-01-03", "2022-01-04"]),
            "date_entree": pd.to_datetime(["2022-01-02", "2022-01-04"]),
            "interv_type": ["A", "B"], "room_duration_min": [100, 200],
            "duree_sejour_corrigee": [7, 8],
        })
        los_rows = pd.DataFrame({"split_patient_id": [11, 22],
                                 "split_event_date": eda["date_inter"]})
        los_prediction = pd.DataFrame({"los_point_days": [2.0, 3.0],
                                       "los_lower_days": [1.0, 2.0],
                                       "los_upper_days": [3.0, 4.0]})
        room_prediction = pd.DataFrame({"duration_point_min": [40.0, 50.0]})
        with patch("bridge_los.pd.read_parquet", return_value=los_rows), \
             patch("bridge_los.predict_los", return_value=los_prediction), \
             patch("bridge_los.predict_schedule", return_value=room_prediction):
            with patch("bridge_los.db.load_preprocessed", return_value=eda):
                first, _, _ = build_patients_with_uncertainty(horizon_jours=2)
            changed = eda.assign(room_duration_min=[900, 1200],
                                 duree_sejour_corrigee=[20, 30])
            with patch("bridge_los.db.load_preprocessed", return_value=changed):
                second, _, _ = build_patients_with_uncertainty(horizon_jours=2)
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(first["duree_operatoire"].tolist(), [40, 50])
        self.assertEqual(first["duree_sejour"].tolist(), [1, 3])


class CrossDayBedTests(unittest.TestCase):
    def scenarios(self, first_los=2):
        first = DailyScenario(date(2022, 1, 3),
                              (CaseInput("episode-1", "A", 20, 1),),
                              {"episode-1": 25}, {"episode-1": first_los})
        second = DailyScenario(date(2022, 1, 4),
                               (CaseInput("episode-2", "A", 20, 1),),
                               {"episode-2": 25}, {"episode-2": 1})
        return [first, second]

    def test_bed_is_released_on_observed_discharge_day(self):
        ward = HospitalWardModel(self.scenarios(), bed_capacity=1)
        self.assertEqual(len(ward.agents), 2)
        self.assertEqual(ward.begin_day(date(2022, 1, 3)), (1, 0, 0))
        offered = ward.offer()
        ward.accept_execution(date(2022, 1, 3), offered,
                              [{"case_id": "episode-1", "start": 480, "status": "completed"}])
        self.assertEqual(ward.occupied, 1)
        self.assertEqual(ward.begin_day(date(2022, 1, 4)), (1, 0, 1))
        self.assertEqual(ward.offer(), [])
        self.assertEqual(ward.begin_day(date(2022, 1, 5)), (0, 1, 0))
        self.assertEqual([agent.case.case_id for agent in ward.offer()], ["episode-2"])
        ward.accept_execution(date(2022, 1, 5), ward.offer(),
                              [{"case_id": "episode-2", "start": 480, "status": "completed"}])
        result = ward.summary(date(2022, 1, 5))
        self.assertEqual(result["surgeries_completed"], 2)
        self.assertEqual(result["never_started"], 0)
        self.assertEqual(result["occupied_bed_days_within_horizon"], 3)

    def test_hidden_los_does_not_change_initial_offer(self):
        short = HospitalWardModel(self.scenarios(first_los=1), 1)
        long = HospitalWardModel(self.scenarios(first_los=7), 1)
        short.begin_day(date(2022, 1, 3))
        long.begin_day(date(2022, 1, 3))
        self.assertEqual([a.case for a in short.offer()], [a.case for a in long.offer()])

    def test_no_bed_reserved_for_unstarted_room_case(self):
        ward = HospitalWardModel(self.scenarios(), 1)
        ward.begin_day(date(2022, 1, 3))
        offered = ward.offer()
        ward.accept_execution(date(2022, 1, 3), offered,
                              [{"case_id": "episode-1", "start": None, "status": "waiting"}])
        self.assertEqual(ward.occupied, 0)
        ward.begin_day(date(2022, 1, 4))
        self.assertEqual(len(ward.offer()), 1)


class JointRoomExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_room_execution_admits_only_started_cases(self):
        ward = HospitalWardModel(CrossDayBedTests().scenarios(), 1)
        ward.advance_day(date(2022, 1, 3))
        self.assertEqual(ward.steps, 1)
        offered = ward.offer()
        result = await run_day(ward.daily_scenario(date(2022, 1, 3), offered),
                               SimulationConfig(rooms=1, opening=480, closing=540, turnover=5))
        ward.accept_execution(date(2022, 1, 3), offered, result["executed_schedule"])
        self.assertEqual(result["metrics"]["completed"], 1)
        self.assertEqual(ward.occupied, 1)
        self.assertEqual(ward.advance_day(date(2022, 1, 4)), (1, 0, 1))
        self.assertEqual(ward.steps, 2)
