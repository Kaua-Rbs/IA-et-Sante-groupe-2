"""Synthetic fixtures exercise decisions and invariants without private source data."""

import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, time
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from hospital_sim.contracts import EventKind, HospitalEvent, Proposal, Snapshot
from hospital_sim.coordinator import Coordinator
from hospital_sim.domain import (
    Assignment, CaseInput, CaseState, HospitalState, Outage, RoomState, Schedule, SimulationConfig,
)
from hospital_sim.historical_data import (
    DailyScenario, ROOM_IN, ROOM_OUT, clock_minutes, load_historical,
)
from hospital_sim.scheduling import BaselineScheduler, ObservationAdapter, RoomValidator
from hospital_sim.simulation import HospitalModel, run_day


def scenario(predictions=(30, 30, 30, 30), actual=None):
    cases = tuple(CaseInput(f"case-{i:04d}", "TEST", p) for i, p in enumerate(predictions, 1))
    return DailyScenario(date(2022, 1, 3), cases,
                         {c.case_id: value for c, value in zip(cases, actual or predictions)})


def without_timing(result):
    result = deepcopy(result)
    result["metrics"].pop("solver_seconds")
    for event in result["events"]:
        event.pop("solver_seconds", None)
        event.pop("event_to_proposal_seconds", None)
    return result


class HistoricalDataTests(unittest.TestCase):
    def test_clock_parsing(self):
        for value in ("09:30:30", time(9, 30, 30), datetime(2020, 1, 1, 9, 30, 30)):
            self.assertEqual(clock_minutes(value), 570.5)
        self.assertEqual(clock_minutes(0.5), 720)
        for value in (None, float("nan"), float("inf"), "", "25:00", -0.1, 1):
            self.assertIsNone(clock_minutes(value))

    def test_training_fallback_exclusions_and_source_privacy(self):
        rows = []
        def add(identifier, day, procedure, start="08:00", end="08:40"):
            rows.append({"no_cas": identifier, "date_inter": day, "interv_type": procedure,
                         ROOM_IN: start, ROOM_OUT: end, "id_patient": "PRIVATE_PATIENT",
                         "nom_chir": "PRIVATE_SURGEON"})
        for i in range(10):
            add(i, "2021-01-04", " Opération  A ")
        add(20, "2021-02-03", "RARE", end="09:40")
        add(21, "2018-01-03", "OTHER", end="20:00")
        add(30, "2022-01-03", "OPERATION A", end="10:00")
        add(31, "2022-01-03", "UNSEEN", end="11:00")
        add(32, "2022-01-03", "RARE", end="12:00")
        add(40, "2022-01-03", "BAD", start="00:00")
        add(41, "2022-01-03", "BAD", end="07:00")
        add(42, "2022-01-03", "BAD", start=None)
        add(43, "2022-01-03", "BAD", end="08:00")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.xlsx"
            path.write_bytes(b"synthetic fingerprint")
            with patch("hospital_sim.historical_data.pd.read_excel", return_value=pd.DataFrame(rows)):
                data = load_historical(path)
            result = data.scenario(date(2022, 1, 3))
        self.assertEqual(data.quality["training_rows"], 11)
        self.assertEqual(data.quality["excluded_rows"], 4)
        self.assertEqual([c.predicted_minutes for c in result.cases], [40, 40, 40])
        self.assertEqual(list(result.realized_minutes.values()), [120, 180, 240])
        self.assertNotIn("PRIVATE", repr(result))
        self.assertNotIn("source_id", repr(result))
        with self.assertRaises(ValueError):
            data.scenario(date(2021, 1, 4))

    def test_duplicate_case_ids_rejected(self):
        frame = pd.DataFrame([{"no_cas": 1, "date_inter": "2021-01-01", "interv_type": "A",
                               ROOM_IN: "08:00", ROOM_OUT: "09:00"}] * 2)
        with patch("hospital_sim.historical_data.pd.read_excel", return_value=frame):
            with self.assertRaisesRegex(ValueError, "unique"):
                load_historical(Path("unused.xlsx"))


class SimulationTests(unittest.IsolatedAsyncioTestCase):
    async def test_mesa_agents_and_no_hidden_outcomes_in_state(self):
        model = HospitalModel(scenario(), SimulationConfig())
        self.assertEqual(len(model.agents), 4)
        self.assertNotIn("realized", repr(model.observed_state()))
        self.assertIsNone(model.observed_state().cases[0].actual_finish)
        short = await run_day(scenario(actual=(10, 10, 10, 10)), SimulationConfig())
        long = await run_day(scenario(actual=(90, 90, 90, 90)), SimulationConfig())
        self.assertEqual(short["schedule_history"][0], long["schedule_history"][0])

    async def test_no_outage_policies_and_repeated_runs_match(self):
        inputs = scenario(actual=(45, 60, 35, 15))
        config = SimulationConfig()
        static = await run_day(inputs, config, "static")
        reactive = await run_day(inputs, config, "reactive")
        repeated = await run_day(inputs, config, "reactive")
        self.assertEqual(without_timing(reactive), without_timing(repeated))
        static["policy"] = "reactive"
        self.assertEqual(without_timing(static), without_timing(reactive))
        self.assertEqual(reactive["metrics"]["failures"], 0)
        self.assertEqual(reactive["metrics"]["replanning_count"], 0)

    async def test_occupancy_turnover_closing_and_case_conservation(self):
        config = SimulationConfig(rooms=1, opening=480, closing=540, turnover=10)
        result = await run_day(scenario((20, 20, 20), (50, 30, 20)), config)
        executed = result["executed_schedule"]
        self.assertEqual(executed[0]["start"], 480)
        self.assertEqual(executed[0]["finish"], 530)
        self.assertIsNone(executed[1]["start"])  # Turnover releases at closing.
        self.assertEqual(result["metrics"]["completed"], 1)
        self.assertEqual(result["metrics"]["unstarted"], 2)
        self.assertEqual(result["metrics"]["overtime_minutes_including_turnover"], 0)
        overtime = await run_day(scenario((20,), (80,)), config)
        self.assertEqual(overtime["metrics"]["overtime_minutes_including_turnover"], 30)
        self.assertEqual(overtime["metrics"]["room_occupancy_minutes_in_hours"], 60)

    async def test_reactive_reassignment_improves_crafted_outage(self):
        inputs = scenario((30,) * 8)
        config = SimulationConfig(rooms=2, opening=480, closing=720, turnover=0,
                                  outage=Outage("room-1", 510, 600))
        static = await run_day(inputs, config, "static")
        reactive = await run_day(inputs, config, "reactive")
        self.assertEqual(static["schedule_history"][0], reactive["schedule_history"][0])
        self.assertEqual(static["metrics"]["completed"], 8)
        self.assertEqual(reactive["metrics"]["completed"], 8)
        self.assertLess(reactive["metrics"]["total_start_delay_minutes"],
                        static["metrics"]["total_start_delay_minutes"])
        self.assertEqual(reactive["metrics"]["replanning_count"], 2)
        self.assertEqual(reactive["metrics"]["failures"], 0)
        self.assertGreater(reactive["metrics"]["room_change_decisions"], 0)

    async def test_running_case_finishes_during_outage_and_next_waits(self):
        inputs = scenario((60, 60, 60), (90, 60, 60))
        config = SimulationConfig(rooms=1, opening=480, closing=780, turnover=15,
                                  outage=Outage("room-1", 510, 600))
        for policy in ("static", "reactive"):
            result = await run_day(inputs, config, policy)
            executed = result["executed_schedule"]
            self.assertEqual(executed[0]["start"], 480)
            self.assertEqual(executed[0]["finish"], 570)
            self.assertEqual(executed[1]["start"], 600)
            self.assertEqual(result["metrics"]["failures"], 0)
            for prev, curr in zip(executed, executed[1:]):
                self.assertGreaterEqual(curr["start"], prev["finish"] + config.turnover)
            self.assertEqual(result["metrics"]["completed"] + result["metrics"]["unstarted"], 3)

    async def test_replan_running_estimate_does_not_reveal_actual_finish(self):
        model = HospitalModel(scenario((20,), (120,)), SimulationConfig(rooms=1))
        model.step()
        model.start_cases(Schedule((Assignment("case-0001", "room-1", 480, 20),)))
        for _ in range(30):
            model.step()
        state = model.observed_state()
        self.assertEqual(state.rooms[0].available_at, 526)  # now+1+turnover
        self.assertIsNone(state.cases[0].actual_finish)

    async def test_invalid_replan_keeps_old_plan_and_execution_guards(self):
        class InvalidAfterInitial:
            def __init__(self):
                self.calls = 0
            async def propose(self, request):
                self.calls += 1
                if self.calls == 1:
                    return await BaselineScheduler().propose(request)
                return Proposal(Schedule(), request.snapshot.version)
        config = SimulationConfig(rooms=1, opening=480, closing=720, turnover=0,
                                  outage=Outage("room-1", 510, 600))
        result = await run_day(scenario((30, 30, 30)), config, scheduler=InvalidAfterInitial())
        self.assertEqual(result["metrics"]["failures"], 2)
        self.assertEqual(result["executed_schedule"][1]["start"], 600)
        self.assertEqual(result["schedule_history"][0]["assignments"],
                         result["schedule_history"][-1]["assignments"])

    async def test_timeout_is_reported_and_cases_remain_unstarted(self):
        class Slow:
            async def propose(self, request):
                await asyncio.sleep(10)
        result = await run_day(scenario(), SimulationConfig(opening=480, closing=485),
                               scheduler=Slow(), timeout_seconds=0.001)
        self.assertEqual(result["metrics"]["timeouts"], 1)
        self.assertEqual(result["metrics"]["unstarted"], 4)

    async def test_observation_without_replan_and_pending_request(self):
        model = HospitalModel(scenario(), SimulationConfig())
        model.step()
        initial = Snapshot(480, 0, model.observed_state())
        async with Coordinator(initial, ObservationAdapter(), BaselineScheduler(), RoomValidator()) as core:
            def event(identifier):
                return HospitalEvent(identifier, 480, EventKind.SIMULATION_OBSERVATION,
                                     {"state": model.observed_state()})
            core.submit(event("observe"), replan=False)
            await core.wait_idle()
            self.assertEqual(core.snapshot.version, 1)
            self.assertEqual(core.outcomes, ())
            core.submit(event("request"))
            core.submit(event("new-observation"), replan=False)
            await core.wait_idle()
            self.assertEqual(core.proposal.base_version, 3)


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.state = HospitalState(480, tuple(CaseState(c) for c in scenario((30, 30)).cases),
                                   (RoomState("room-1", 480),), 480, 600, 15)
        self.snapshot = Snapshot(480, 0, self.state)
        self.valid = Schedule((Assignment("case-0001", "room-1", 480, 30),
                               Assignment("case-0002", "room-1", 525, 30)))

    def test_valid_and_rejected_schedules(self):
        validator = RoomValidator()
        self.assertTrue(validator.validate(self.snapshot, Proposal(self.valid, 0)).feasible)
        bad = [
            Schedule(self.valid.assignments[:1]),  # Missing case.
            replace(self.valid, unassigned=("case-0001",)),  # Duplicate.
            replace(self.valid, assignments=(replace(self.valid.assignments[0], room_id="unknown"),
                                             self.valid.assignments[1])),
            replace(self.valid, assignments=(self.valid.assignments[0],
                                             replace(self.valid.assignments[1], start=510))),
            replace(self.valid, assignments=(replace(self.valid.assignments[0], duration=1),
                                             self.valid.assignments[1])),
            replace(self.valid, assignments=(self.valid.assignments[0],
                                             replace(self.valid.assignments[1], start=600))),
        ]
        for schedule in bad:
            self.assertFalse(validator.validate(self.snapshot, Proposal(schedule, 0)).feasible)
        closed = replace(self.snapshot, domain=replace(
            self.state, known_outages=(Outage("room-1", 480, 500),)))
        self.assertFalse(validator.validate(closed, Proposal(self.valid, 0)).feasible)

    def test_fixed_running_assignment_cannot_change(self):
        running = replace(self.state.cases[0], status="running", actual_start=480, actual_room="room-1")
        state = replace(self.state, cases=(running, self.state.cases[1]),
                        rooms=(RoomState("room-1", 525),))
        snapshot = Snapshot(480, 0, state, self.valid)
        changed = replace(self.valid, assignments=(replace(self.valid.assignments[0], start=481),
                                                  self.valid.assignments[1]))
        self.assertFalse(RoomValidator().validate(snapshot, Proposal(changed, 0)).feasible)
        self.assertTrue(RoomValidator().validate(snapshot, Proposal(self.valid, 0)).feasible)


class ExperimentTests(unittest.IsolatedAsyncioTestCase):
    async def test_cli_outputs_and_no_overwrite(self):
        import csv
        import json
        from types import SimpleNamespace
        from hospital_sim.experiment import execute, parser
        inputs = scenario((10, 15))
        data = SimpleNamespace(
            dates=(date(2022, 1, 3),), fingerprint="test-fingerprint",
            quality={"usable_rows": 2, "excluded_rows": 0},
            scenario=lambda day: inputs,
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "results"
            args = parser().parse_args([
                "--date-range", "2022-01-03", "2022-01-04",
                "--opening", "08:00", "--closing", "08:30", "--turnover", "0",
                "--scenarios", "no_outage", "--output", str(output),
            ])
            with patch("hospital_sim.experiment.load_historical", return_value=data):
                await execute(args)
                with self.assertRaisesRegex(ValueError, "empty"):
                    await execute(args)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["dataset_sha256"], "test-fingerprint")
            self.assertEqual(manifest["dates"], ["2022-01-03"])
            with (output / "summary.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual({r["policy"] for r in rows}, {"static", "reactive"})
            for path in output.glob("*.json"):
                content = path.read_text()
                for forbidden in ("no_cas", "id_patient", "nom_chir", "praticien", "date_naissance"):
                    self.assertNotIn(forbidden, content)

    async def test_midnight_opening_is_supported(self):
        result = await run_day(scenario((2,), (5,)),
                               SimulationConfig(rooms=1, opening=0, closing=3, turnover=0))
        self.assertEqual(result["executed_schedule"][0]["start"], 0)
        self.assertEqual(result["metrics"]["completed"], 1)
        self.assertEqual(result["metrics"]["overtime_minutes_including_turnover"], 2)


if __name__ == "__main__":
    unittest.main()
