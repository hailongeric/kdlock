"""Fixed-session continuation checks; execute only in the development VM."""
import importlib.util
from pathlib import Path
import sys
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
