"""Oracle de duree : information parfaite explicite, ressources et issues fixes."""
import asyncio
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hospital_sim.domain import Outage, SimulationConfig
from hospital_sim.experiment import execute, parser
from hospital_sim.instances import opening_request, small_reference, with_duration_mode
from hospital_sim.scheduling import BaselineScheduler
from hospital_sim.simulation import run_day
from tests.test_historical_simulation import scenario


class OracleTests(unittest.TestCase):
    def test_explicit_conversion_without_mutating_inputs(self):
        original = scenario((10, 20), (15.2, 40))
        oracle = with_duration_mode(original, 'oracle')
        self.assertEqual([c.predicted_minutes for c in oracle.cases], [16, 40])
        self.assertEqual([c.predicted_minutes for c in original.cases], [10, 20])
        self.assertEqual(oracle.realized_minutes, original.realized_minutes)
        self.assertEqual([(c.case_id, c.procedure) for c in oracle.cases],
                         [(c.case_id, c.procedure) for c in original.cases])
        self.assertIs(with_duration_mode(original, 'median'), original)
        self.assertEqual(parser().parse_args([]).duration_mode, 'median')
        with self.assertRaises(ValueError):
            with_duration_mode(original, 'unknown')

    def test_outcomes_change_visible_durations_only_in_oracle(self):
        original = small_reference()
        changed = replace(original, realized_minutes={k: v + 20 for k, v in original.realized_minutes.items()})
        config = SimulationConfig()
        def visible(s, mode):
            return opening_request(with_duration_mode(s, mode), config, 1).snapshot.domain
        self.assertEqual(visible(original, 'median'), visible(changed, 'median'))
        self.assertNotEqual(visible(original, 'oracle'), visible(changed, 'oracle'))
        self.assertEqual(visible(original, 'oracle').known_outages, ())

    def test_cli_outputs_reference_and_resource_pairing(self):
        # Deliberately large prediction error: resizing AFTER oracle conversion
        # would change resources and invalidate the information-only comparison.
        source = scenario((100,) * 7, (30,) * 7)
        configs = []
        with tempfile.TemporaryDirectory() as folder:
            for mode in ('median', 'oracle'):
                output = Path(folder) / mode
                args = parser().parse_args(['--synthetic-cases', '7', '--duration-mode', mode,
                                            '--output', str(output)])
                with patch('hospital_sim.experiment.load_historical') as load, \
                     patch('hospital_sim.experiment.sampled_scenario', return_value=source), \
                     redirect_stdout(StringIO()):
                    load.return_value.fingerprint = 'test'
                    load.return_value.quality = {'usable_rows': 7, 'excluded_rows': 0}
                    rows = asyncio.run(execute(args))
                manifest = json.loads((output / 'manifest.json').read_text())
                self.assertEqual(manifest['duration_mode'], mode)
                configs.append(manifest['instances']['sample-7-0']['configurations'])
                self.assertEqual(len(rows), 4)
                self.assertTrue(all(row['duration_mode'] == mode for row in rows))
                for path in output.glob('sample-*.json'):
                    self.assertEqual(json.loads(path.read_text())['duration_mode'], mode)
                if mode == 'oracle':
                    initial = json.loads(next(output.glob('*-initial.json')).read_text())['schedule']
                    self.assertEqual({a['duration'] for a in initial['assignments']}, {30})
            self.assertEqual(configs[0], configs[1])
            self.assertEqual(configs[0][0]['rooms'], 2)

        # Exact reference must also be computed with the selected duration mode.
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(StringIO()):
            args = parser().parse_args(['--small-reference', '--duration-mode', 'oracle',
                                        '--closing', '11:00', '--outage-start', '09:00',
                                        '--outage-end', '10:00', '--output', folder])
            asyncio.run(execute(args))
            manifest = json.loads((Path(folder) / 'manifest.json').read_text())
            from hospital_sim.instances import exact_reference
            expected = exact_reference(opening_request(with_duration_mode(small_reference(), 'oracle'),
                                                      SimulationConfig(closing=660), float('inf')))
            self.assertEqual(manifest['exact_references']['small-reference']['objective'], expected['objective'])

    def test_perfect_durations_match_execution_and_replanning_information(self):
        source = with_duration_mode(scenario((20, 20, 20), (80, 30, 40)), 'oracle')
        class RecordingScheduler(BaselineScheduler):
            def __init__(self):
                self.requests = []
            async def propose(self, request):
                self.requests.append(request)
                return await super().propose(request)
        config = SimulationConfig(rooms=1, closing=720, outage=Outage('room-1', 490, 520))
        scheduler = RecordingScheduler()
        result = asyncio.run(run_day(source, config, 'reactive', scheduler))
        self.assertEqual(result['metrics']['completed'], 3)
        self.assertEqual(scheduler.requests[0].snapshot.domain.known_outages, ())
        self.assertEqual(len(scheduler.requests), 3)
        for request in scheduler.requests:
            state = request.snapshot.domain
            self.assertEqual([c.case.predicted_minutes for c in state.cases], [80, 30, 40])
            for case in state.cases:
                if case.status == 'running':
                    self.assertIsNone(case.actual_finish)
                    room = next(r for r in state.rooms if r.room_id == case.actual_room)
                    self.assertEqual(room.available_at, case.actual_start + case.case.predicted_minutes + 15)
        executed = sorted(result['executed_schedule'], key=lambda x: x['start'])
        for item in executed:
            self.assertEqual(item['finish'] - item['start'], source.realized_minutes[item['case_id']])
            self.assertFalse(490 <= item['start'] < 520)
        self.assertTrue(all(a['finish'] + 15 <= b['start'] for a, b in zip(executed, executed[1:])))
        plain = asyncio.run(run_day(source, replace(config, outage=None), 'static'))
        initial = {a['case_id']: a for a in plain['schedule_history'][0]['assignments']}
        self.assertTrue(all(a['start'] == initial[a['case_id']]['start'] for a in plain['executed_schedule']))
        self.assertEqual(plain['metrics']['total_start_delay_minutes'], 0)


if __name__ == '__main__':
    unittest.main()
