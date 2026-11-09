"""Fixed-session continuation checks; execute only in the development VM."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/mmap1'))
spec = importlib.util.spec_from_file_location('mmap1_settled_fixture', ROOT / 'bench/mmap1/settled.py')
settled = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settled)


class FixedSession(unittest.TestCase):
    def test_current_capability_accepts_known_v21_and_v22_with_one_query(self):
        features = (1 << 1) | (1 << 3) | (1 << 4) | (1 << 14) | (1 << 18)
        cases = ((21, True, 0), (22, True, 0), (21, False, 0), (22, False, 0),
                 (21, True, (1 << 7) | (1 << 9)), (22, True, (1 << 8) | (1 << 9)))
        for version, has_module_arena, strings in cases:
            bits = features | strings | ((1 << 19) if version == 22 else 0)
            if not has_module_arena:
                bits &= ~2
            arena = 8192 if has_module_arena else 0
            def queried(device, command, packet, mutate):
                self.assertFalse(device.closed)
                self.assertEqual((command, mutate), (0x80104b73, True))
                packet[:] = struct.pack('<IIII', version, bits, 0, arena)
                return 0
            with self.subTest(version=version, has_module_arena=has_module_arena, strings=strings), \
                 patch('builtins.open', return_value=io.BytesIO()) as opened, \
                 patch.object(settled.fcntl, 'ioctl', side_effect=queried) as query:
                self.assertEqual(settled.current_capability(),
                    dict(version=version, features=bits, mutex_stack_bytes=0, percpu_module_bytes=arena))
            opened.assert_called_once_with('/dev/kd_dev', 'rb', buffering=0)
            query.assert_called_once()

    def test_current_capability_refuses_unknown_or_inconsistent_contracts(self):
        bits = (1 << 1) | (1 << 3) | (1 << 4) | (1 << 14) | (1 << 18)
        cases = [(20, bits, 0, 8192), (23, bits | (1 << 19), 0, 8192),
                 (21, bits | (1 << 19), 0, 8192), (22, bits, 0, 8192),
                 (22, bits | (1 << 19) | (1 << 20), 0, 8192),
                 (21, bits & ~(1 << 3), 0, 8192), (21, bits & ~(1 << 4), 0, 8192),
                 (21, bits & ~(1 << 14), 0, 8192), (21, bits & ~(1 << 18), 0, 8192),
                 (21, bits | 4, 0, 8192), (21, bits, 256, 8192),
                 (21, bits | 1, 0, 8192), (21, bits, 0, 8191),
                 (21, bits & ~2, 0, 8192),
                 (21, bits | (1 << 9), 0, 8192),
                 (21, bits | (1 << 10), 0, 8192), (21, bits | (1 << 11), 0, 8192),
                 (21, bits | (1 << 13), 0, 8192), (21, bits | (1 << 16), 0, 8192)]
        for packet in cases:
            def queried(device, command, output, mutate):
                output[:] = struct.pack('<IIII', *packet)
                return 0
            with self.subTest(packet=packet), \
                 patch('builtins.open', return_value=io.BytesIO()), \
                 patch.object(settled.fcntl, 'ioctl', side_effect=queried) as query:
                with self.assertRaises(settled.rt.Failure) as raised:
                    settled.current_capability()
            self.assertEqual(raised.exception.status, 'DATA_ERROR')
            query.assert_called_once()
        with patch('builtins.open', return_value=io.BytesIO()), \
             patch.object(settled.fcntl, 'ioctl', return_value=1) as query:
            with self.assertRaises(settled.rt.Failure):
                settled.current_capability()
        query.assert_called_once()

    def test_current_capability_refuses_incomplete_success_packet(self):
        bits = (1 << 1) | (1 << 3) | (1 << 4) | (1 << 14) | (1 << 18)
        def queried(device, command, output, mutate):
            output[:8] = struct.pack('<II', 21, bits)
            return 0
        with patch('builtins.open', return_value=io.BytesIO()), \
             patch.object(settled.fcntl, 'ioctl', side_effect=queried) as query:
            with self.assertRaises(settled.rt.Failure) as raised:
                settled.current_capability()
        self.assertEqual(raised.exception.status, 'DATA_ERROR')
        query.assert_called_once()

    def test_publication_gate_distinguishes_body_from_missing_callee_stub(self):
        marker = 'MOVABS R14, 0x3000\nMOV Stack_IJ, 16\nJMP full_exit\n'
        body = '/*\nloc_2000\nPUSH RBP\n*/\nloc_2000:\nPUSH RBP\n'
        self.assertEqual(settled.frontier_emission(body + marker, 0x2000, 0x3000),
                         dict(translated_target=True, exact_terminal=True))
        stub = 'loc_2000:\nMOVABS R14, 0x2000\nMOV Stack_IJ, 1\nJMP exit\n'
        self.assertFalse(settled.frontier_emission(stub + marker, 0x2000, 0x3000)['translated_target'])

    def test_publication_gate_ignores_comments_and_other_instruction_sites(self):
        marker = 'MOVABS R14, 0x3000\nMOV Stack_IJ, 16\nJMP full_exit\n'
        self.assertFalse(settled.frontier_emission('/*\n' + marker + '*/\n', 0x2000, 0x3000)['exact_terminal'])
        self.assertFalse(settled.frontier_emission(marker, 0x2000, 0x3001)['exact_terminal'])

    def value(self, folder):
        value = settled.SettledObservation.__new__(settled.SettledObservation)
        value.args = SimpleNamespace(writer_entries=[1])
        value.daemon = SimpleNamespace(daemon=SimpleNamespace(pid=123))
        value.admit_images, value.save = Mock(), Mock()
        value.owner = SimpleNamespace(session_receipt=Mock())
        return value

    def test_changed_registry_cannot_bind_old_image_files(self):
        with tempfile.TemporaryDirectory() as name:
            value = self.value(Path(name))
            with patch.object(settled.rt, 'children', return_value=[]), \
                 patch.object(settled.rt, 'status', return_value=dict(state=0, frames=0, writers=1)), \
                 patch.object(settled.rt, 'registry', return_value=[dict(pid=0, tgid=1, entry=1, generation=2)]), \
                 patch.object(settled.bench.execution, 'ready_writer_entries'):
                with self.assertRaises(settled.rt.Failure) as error:
                    value.fixed_receipt(Path(name) / 'receipt',
                        dict(registry_after=[dict(pid=0, tgid=1, entry=1, generation=1)]))
            self.assertEqual(error.exception.status, 'LEARNING_ADVANCED')
            value.owner.session_receipt.assert_not_called()

    def test_compiler_prevents_receipt_creation(self):
        with tempfile.TemporaryDirectory() as name:
            value = self.value(Path(name))
            with patch.object(settled.rt, 'children', return_value=[456]):
                with self.assertRaises(settled.rt.Failure):
                    value.fixed_receipt(Path(name) / 'receipt', dict(registry_after=[]))
            value.owner.session_receipt.assert_not_called()

    def test_current_receipt_is_built_and_verified_in_same_owner(self):
        with tempfile.TemporaryDirectory() as name:
            value = self.value(Path(name))
            exact = SimpleNamespace(verify=Mock())
            value.owner.session_receipt.return_value = exact
            rows = [dict(pid=0, tgid=1, entry=1, generation=2)]
            with patch.object(settled.rt, 'children', return_value=[]), \
                 patch.object(settled.rt, 'status', return_value=dict(state=0, frames=0, writers=1)), \
                 patch.object(settled.rt, 'registry', return_value=rows), \
                 patch.object(settled.bench.execution, 'ready_writer_entries'):
                self.assertIs(value.fixed_receipt(Path(name) / 'receipt', dict(registry_after=rows)), exact)
            value.owner.session_receipt.assert_called_once_with(value.daemon, rows)
            exact.verify.assert_called_once()

    def learning_value(self, folder, transitions, limit=8):
        value = self.value(folder)
        value.c = dict(learning_timeout=1800, continuation_rounds=limit, long_warmup=True)
        value.current_model, value.inputs, value.verify = 'processes', {}, Mock()
        value.result, value.deadline, value.pool = {}, 1000, Mock()
        zero = {key: 0 for key in settled.observe.FIELDS}
        done = dict(zero, selected=1, submitted=1, bound=1, jit_entered=1,
                    returned=1, dispatch_samples=1, shadow_samples=1)
        value.window_observer = Mock(side_effect=[dict(service={1: zero}), dict(service={1: done})] * 8)
        pending = iter(transitions)

        def receipt(destination):
            before, after = next(pending)
            destination.mkdir(exist_ok=True)
            application = dict(passed=True, drained=True, sample_window=dict(samples=730))
            observation = dict(registry_before=before, registry_after=after, application=application)
            (destination / 'learning.json').write_text(json.dumps([observation]))
            if before != after:
                raise settled.rt.Failure('LEARNING_ADVANCED', 'replacement published after application')
            return SimpleNamespace(), [observation]

        value.learn = Mock(side_effect=lambda workers, destination: receipt(destination))
        return value, receipt

    def test_continuations_exercise_each_settled_generation_with_one_deadline(self):
        with tempfile.TemporaryDirectory() as name:
            value, receipt = self.learning_value(Path(name), [(1, 2), (2, 3), (3, 3)])
            with patch.object(settled.time, 'monotonic', return_value=100), \
                 patch.object(settled.campaign.point, 'demand_learning',
                              side_effect=lambda config, destination, *args, **kwargs: receipt(destination)) as learn:
                learned = value.learning_to_stability(Path(name))
            self.assertEqual(learned['registry_after'], 3)
            value.learn.assert_called_once()
            self.assertEqual(learn.call_count, 2)
            for call in learn.call_args_list:
                self.assertFalse(call.args[0]['long_warmup'])
                self.assertEqual(call.args[0]['learning_rounds'], 1)
                self.assertEqual(call.kwargs['deadline'], 1000)
                self.assertEqual(call.kwargs['application_deadline'], 1000)
                self.assertIs(call.kwargs['quiescent'], value.pool)
                self.assertIs(call.kwargs['before_application'], value.admit_images)
            self.assertTrue(value.c['long_warmup'])
            self.assertEqual([row['stable'] for row in value.result['learning_continuations']], [False, True])

    def test_continuation_count_exhaustion_cannot_create_a_fixed_receipt(self):
        with tempfile.TemporaryDirectory() as name:
            value, receipt = self.learning_value(Path(name), [(1, 2), (2, 3)], limit=1)
            with patch.object(settled.time, 'monotonic', return_value=100), \
                 patch.object(settled.campaign.point, 'demand_learning',
                              side_effect=lambda config, destination, *args, **kwargs: receipt(destination)) as learn:
                with self.assertRaises(settled.rt.Failure) as error:
                    value.learning_to_stability(Path(name))
            self.assertEqual(error.exception.status, 'LEARNING_ADVANCED')
            learn.assert_called_once()
            value.owner.session_receipt.assert_not_called()

    def test_deadline_prevents_another_application_without_renewal(self):
        with tempfile.TemporaryDirectory() as name:
            value, _ = self.learning_value(Path(name), [(1, 2)])
            with patch.object(settled.time, 'monotonic', return_value=971), \
                 patch.object(settled.campaign.point, 'demand_learning') as learn:
                with self.assertRaises(settled.rt.Failure) as error:
                    value.learning_to_stability(Path(name))
            self.assertEqual(error.exception.status, 'LEARNING_ADVANCED')
            self.assertEqual(value.deadline, 1000)
            learn.assert_not_called()

    def test_failed_continuation_is_not_repeated(self):
        with tempfile.TemporaryDirectory() as name:
            value, _ = self.learning_value(Path(name), [(1, 2)])
            failure = settled.rt.Failure('UNDRAINED', 'application is still active')
            with patch.object(settled.time, 'monotonic', return_value=100), \
                 patch.object(settled.campaign.point, 'demand_learning', side_effect=failure) as learn:
                with self.assertRaises(settled.rt.Failure) as error:
                    value.learning_to_stability(Path(name))
            self.assertIs(error.exception, failure)
            learn.assert_called_once()

    def test_late_settlement_prevents_application_start_after_verification(self):
        with tempfile.TemporaryDirectory() as name:
            out = Path(name) / 'application'
            session = Mock(spec=settled.bench.execution.ExecutionSession)
            clock = [100]
            def settled_verification(**kwargs):
                clock[0] = 971
            session.verify.side_effect = settled_verification
            verify = Mock()
            with patch.object(settled.bench.time, 'monotonic', side_effect=lambda: clock[0]), \
                 patch.object(settled.bench, 'argv') as argv:
                with self.assertRaises(settled.rt.Failure) as error:
                    settled.bench.run_point(out, dict(model='processes', workers=8),
                        dict(binaries={'processes': '/unused/mmap1'}), verify,
                        execution_session=session, learning=True, application_deadline=1000)
            self.assertEqual(error.exception.status, 'LEARNING_ADVANCED')
            session.verify.assert_called_once()
            verify.assert_called_once()
            argv.assert_not_called()
            self.assertFalse(out.exists())

    def test_startup_deadline_failure_keeps_its_original_status(self):
        with tempfile.TemporaryDirectory() as name:
            value, _ = self.learning_value(Path(name), [(1, 2)])
            failure = settled.rt.Failure('LEARNING_ADVANCED', 'deadline after startup verification')
            with patch.object(settled.time, 'monotonic', return_value=100), \
                 patch.object(settled.campaign.point, 'demand_learning', side_effect=failure) as learn:
                with self.assertRaises(settled.rt.Failure) as error:
                    value.learning_to_stability(Path(name))
            self.assertIs(error.exception, failure)
            learn.assert_called_once()

    def test_stable_registry_without_image_activity_is_refused(self):
        with tempfile.TemporaryDirectory() as name:
            value, receipt = self.learning_value(Path(name), [(1, 2), (2, 2)])
            zero = {key: 0 for key in settled.observe.FIELDS}
            value.window_observer = Mock(return_value=dict(service={1: zero}))
            with patch.object(settled.time, 'monotonic', return_value=100), \
                 patch.object(settled.campaign.point, 'demand_learning',
                              side_effect=lambda config, destination, *args, **kwargs: receipt(destination)):
                with self.assertRaisesRegex(settled.rt.Failure, 'each prepared image'):
                    value.learning_to_stability(Path(name))

    def test_continuation_limit_refuses_unbounded_or_noninteger_values(self):
        for limit in (-1, 65, True, 1.5):
            value = self.value(Path('.'))
            value.c = dict(continuation_rounds=limit)
            with self.subTest(limit=limit), self.assertRaises(settled.rt.Failure):
                value.continuation_limit()

    def point_value(self, folder, after):
        value = self.value(folder)
        value.current_model, value.inputs, value.verify = 'processes', {}, Mock()
        value.result = {}
        rows = [dict(pid=0, tgid=1, entry=1, generation=2, code=123, status=0)]
        value.exact = SimpleNamespace(expected=dict(registry=rows), identity=lambda: dict(path='current'))
        counters = {key: 0 for key in settled.observe.FIELDS}
        view = dict(registry=rows, superseded_reports=0, service={1: counters})
        completed = dict(counters, selected=1, submitted=1, bound=1, jit_entered=1,
                         returned=1, dispatch_samples=1, shadow_samples=1)
        end = after or dict(registry=rows, superseded_reports=0, service={1: completed})
        value.window_observer = Mock(side_effect=[view, end])
        value.compiler_records = Mock(side_effect=[[], []])
        application = dict(passed=True, drained=True, output=dict(pairs_per_nominal_second=42),
            sample_window=dict(events=[dict(observation=view), dict(observation=end)]))
        return value, application

    def test_point_uses_fixed_receipt_and_only_one_application(self):
        with tempfile.TemporaryDirectory() as name:
            value, application = self.point_value(Path(name), None)
            row = {}
            with patch.object(settled.bench, 'run_point', return_value=application) as run:
                value.fixed_point(Path(name), row)
            run.assert_called_once()
            self.assertIs(run.call_args.kwargs['execution_session'], value.exact)
            self.assertEqual(run.call_args.args[1]['upstream_samples'], 10)
            self.assertEqual(run.call_args.args[1]['timeout_seconds'], 30)
            self.assertTrue(row['stable'])

    def test_new_image_invalidates_point_without_retry(self):
        with tempfile.TemporaryDirectory() as name:
            after = dict(registry=[dict(pid=0, tgid=1, entry=1, generation=3, code=456, status=0)],
                         superseded_reports=0, service={1: {k: 0 for k in settled.observe.FIELDS}})
            value, application = self.point_value(Path(name), after)
            row = {}
            with patch.object(settled.bench, 'run_point', return_value=application) as run:
                with self.assertRaises(settled.rt.Failure) as error:
                    value.fixed_point(Path(name), row)
            self.assertEqual(error.exception.status, 'LEARNING_ADVANCED')
            run.assert_called_once()
            self.assertFalse(row['stable'])

    def test_failed_fixed_verification_does_not_renew_or_retry(self):
        with tempfile.TemporaryDirectory() as name:
            value, application = self.point_value(Path(name), None)
            def failed(out, *args, **kwargs):
                import json
                out.mkdir()
                application['passed'] = False
                (out / 'result.json').write_text(json.dumps(application))
                raise settled.rt.Failure('LEARNING_ADVANCED', 'new miss')
            row = {}
            with patch.object(settled.bench, 'run_point',
                              side_effect=failed) as run:
                with self.assertRaises(settled.rt.Failure):
                    value.fixed_point(Path(name), row)
            run.assert_called_once()
            value.owner.session_receipt.assert_not_called()
            self.assertFalse(row['application']['passed'])
            self.assertIn('application_receipt', row)
            self.assertEqual(row['measured_delta'][0]['returned'], 1)
            self.assertFalse(row['stable'])

    def test_empty_activity_cannot_pass_as_prepared_execution(self):
        with tempfile.TemporaryDirectory() as name:
            after = dict(registry=[dict(pid=0, tgid=1, entry=1, generation=2, code=123, status=0)],
                         superseded_reports=0, service={1: {k: 0 for k in settled.observe.FIELDS}})
            value, application = self.point_value(Path(name), after)
            with patch.object(settled.bench, 'run_point', return_value=application):
                with self.assertRaisesRegex(settled.rt.Failure, 'prepared image'):
                    value.fixed_point(Path(name), {})

    def test_no_image_routing_cannot_pass_as_prepared_execution(self):
        with tempfile.TemporaryDirectory() as name:
            counters = {k: 0 for k in settled.observe.FIELDS}
            counters.update(selected=2, local=1, local_no_image=1, local_success=1,
                            submitted=1, bound=1, jit_entered=1, returned=1,
                            dispatch_samples=1, shadow_samples=1)
            after = dict(registry=[dict(pid=0, tgid=1, entry=1, generation=2, code=123, status=0)],
                         superseded_reports=0, service={1: counters})
            value, application = self.point_value(Path(name), after)
            with patch.object(settled.bench, 'run_point', return_value=application):
                with self.assertRaisesRegex(settled.rt.Failure, 'prepared image'):
                    value.fixed_point(Path(name), {})


if __name__ == '__main__':
    unittest.main()
