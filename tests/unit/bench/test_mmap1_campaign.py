"""Persistent mmap1 controller boundaries; execute in the development VM."""
import importlib.util
import json
from pathlib import Path
import signal
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('mmap1_campaign_fixture', ROOT / 'bench/mmap1/campaign.py')
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


class CampaignBoundaries(unittest.TestCase):
    def test_close_bound_is_finite_and_default_is_preserved(self):
        self.assertEqual(campaign.close_limit({}), 40)
        self.assertEqual(campaign.close_limit(dict(close_timeout_seconds=600)), 600)
        for value in (0, 601, True, 1.5, '600'):
            with self.subTest(value=value), self.assertRaises(campaign.rt.Failure):
                campaign.close_limit(dict(close_timeout_seconds=value))

    def test_pool_reserves_each_root_before_an_application(self):
        campaign.require_headroom(dict(capacity=128, private=0, free_descriptors=2), 2)
        for values in (dict(capacity=64, private=0, free_descriptors=2),
                       dict(capacity=128, private=1, free_descriptors=2),
                       dict(capacity=128, private=0, free_descriptors=1)):
            with self.subTest(values=values), self.assertRaises(campaign.rt.Failure):
                campaign.require_headroom(values, 2)

    def test_unknown_application_blocks_cleanup(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            self.assertTrue(campaign.applications_drained(folder))
            (folder / 'command.json').write_text('{}')
            self.assertFalse(campaign.applications_drained(folder))
            for drained in (False, True):
                (folder / 'result.json').write_text(json.dumps(dict(drained=drained)))
                self.assertEqual(campaign.applications_drained(folder), drained)

    def test_preparation_failure_reaches_stage_aware_cleanup(self):
        value = campaign.Campaign.__new__(campaign.Campaign)
        with tempfile.TemporaryDirectory() as name:
            value.out = Path(name) / 'new'
            value.result = {}
            value.prepare = Mock(side_effect=ValueError('fixture preparation'))
            value.save = Mock()
            value.close = Mock()
            with self.assertRaisesRegex(ValueError, 'fixture preparation'):
                value.run()
            value.close.assert_called_once()
            self.assertIn('fixture preparation', value.result['error'])

    def test_existing_output_is_preserved(self):
        value = campaign.Campaign.__new__(campaign.Campaign)
        with tempfile.TemporaryDirectory() as name:
            value.out = Path(name)
            original = value.out / 'result.json'
            original.write_text('retained evidence')
            value.prepare, value.save, value.close = Mock(), Mock(), Mock()
            with self.assertRaises(campaign.rt.Failure):
                value.run()
            self.assertEqual(original.read_text(), 'retained evidence')
            value.prepare.assert_not_called()
            value.save.assert_not_called()
            value.close.assert_not_called()

    def test_cleanup_resumes_stopped_parent_to_reap_a_child(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            for key, content in dict(rwsem_provider_mode='N', service_trace='N',
                    rwsem_provider_bindings='0', service_progress='total=0 shown=0').items():
                (folder / key).write_text(content)
            value = campaign.Campaign.__new__(campaign.Campaign)
            value.out, value.provider_loaded, value.observer_loaded = folder, True, False
            value.result, value.counts, value.models = dict(points=[]), [1], ['threads']
            value.save = Mock()
            children, calls = [789], []
            def resume(paused):
                self.assertFalse(paused)
                calls.append('resume')
                children.clear()
            value.daemon = SimpleNamespace(daemon=SimpleNamespace(pid=123),
                translation_state=lambda: 'T', translation_phase=resume,
                stop=lambda: calls.append('stop'))
            with patch.object(campaign.controller, 'PARAMETERS', folder), \
                 patch.object(campaign.rt, 'children', side_effect=lambda pid: children), \
                 patch.object(campaign.rt, 'status', return_value=dict(frames=0)), \
                 patch.object(campaign.rt, 'registry', return_value=[]), \
                 patch.object(campaign.rt, 'digest', return_value='fixture-note'):
                value.close()
            self.assertEqual(calls, ['resume', 'stop'])
            self.assertEqual(value.result['state'], 'STOPPED_RETIREMENT_PENDING')

    def test_proof_requires_finished_collection_and_lifecycle_stop(self):
        for complete in (False, True):
            with self.subTest(complete=complete), tempfile.TemporaryDirectory() as name:
                folder = Path(name)
                params = folder / 'parameters'
                params.mkdir()
                for key in ('rwsem_provider_mode', 'service_trace'):
                    (params / key).write_text('N')
                value = campaign.Campaign.__new__(campaign.Campaign)
                value.out, value.current_model = folder, 'threads'
                value.c = dict(probe='/fixture/probe')
                value.inputs = {}
                value.args = SimpleNamespace(writer_entries=[1])
                value.result = dict(proofs=[])
                value.proof_key = None
                value.observer_loaded = False
                value.audit = dict(entry_sites=[1])
                value.daemon = SimpleNamespace(daemon=SimpleNamespace(pid=123), translation_phase=Mock())
                value.admit_images, value.save, value.verify = Mock(), Mock(), Mock()
                value.owner = SimpleNamespace(session_receipt=Mock(return_value=SimpleNamespace(verify=Mock())),
                    stop_observer=Mock(return_value={}), validate_services=Mock(return_value={}))
                collector = SimpleNamespace(start=Mock(), checkpoint=Mock(),
                    finish=Mock(return_value=dict(complete=complete, fault_detected=False)),
                    thread=SimpleNamespace(is_alive=lambda: False))
                def run_point(out, *args, **kwargs):
                    out.mkdir()
                    (out / 'command.json').write_text('{}')
                    (out / 'result.json').write_text('{"drained": true}')
                    (out / 'kernel.log').write_text('application only')
                    (out.parent / 'lifecycle-log/kernel.log').write_text('kd_mm_pair: event=stop ')
                    return dict(passed=True, drained=True)
                original_read = Path.read_text
                def read_text(path, *args, **kwargs):
                    if str(path) == '/proc/kallsyms':
                        return '0000000000001234 t kd_rwsem_ops [kdlock_km]\n'
                    return original_read(path, *args, **kwargs)
                def pairs(messages, *args):
                    self.assertIn('kd_mm_pair: event=stop ', messages)
                    return {}
                with patch.object(campaign.controller, 'PARAMETERS', params), \
                     patch.object(campaign.rt, 'registry', return_value=[]), \
                     patch.object(campaign.rt, 'status', return_value=dict(frames=0)), \
                     patch.object(campaign.rt, 'children', return_value=[]), \
                     patch.object(campaign.rt, 'command'), \
                     patch.object(campaign.bench.execution, 'ready_writer_entries'), \
                     patch.object(campaign.bench, 'run_point', side_effect=run_point), \
                     patch.object(campaign.bench.kernel_log, 'DiagnosticKernelLog', return_value=collector), \
                     patch.object(campaign.controller.observer, 'validate_delegated', return_value={}), \
                     patch.object(campaign.controller.pairs, 'validate', side_effect=pairs), \
                     patch.object(campaign.controller, 'require_observed_continuation', return_value={}), \
                     patch.object(campaign.os, 'open', return_value=10), \
                     patch.object(campaign.os, 'lseek'), patch.object(campaign.os, 'close'), \
                     patch.object(Path, 'read_text', read_text):
                    if complete:
                        value.proof(0)
                        self.assertEqual(len(value.result['proofs']), 1)
                    else:
                        with self.assertRaises(campaign.rt.Failure):
                            value.proof(0)
                        self.assertEqual(value.result['proofs'], [])
                        self.assertIsNone(value.proof_key)


class TranslationPhases(unittest.TestCase):
    def fixture(self, folder):
        (folder / 'rwsem_provider_active').write_text('N')
        value = campaign.controller.Daemon(folder, ROOT, Path('/fixture/daemon'))
        state = dict(stopped=True, children=[])
        value.translation_paused = True
        value.translation_state = lambda: 'T' if state['stopped'] else 'S'
        value.translation_identity = (123, 456)
        def send(number):
            state['stopped'] = number == signal.SIGSTOP
            if number == signal.SIGCONT:
                state['children'] = [789]
        value.daemon = SimpleNamespace(pid=123, poll=lambda: None,
            send_signal=Mock(side_effect=send), terminate=Mock())
        return value, state

    def test_resume_allows_immediate_and_existing_compiler_children(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            value, state = self.fixture(folder)
            with patch.object(campaign.controller, 'PARAMETERS', folder), \
                 patch.object(campaign.rt, 'status', return_value=dict(frames=0)), \
                 patch.object(campaign.rt, 'children', side_effect=lambda pid: state['children']):
                value.translation_phase(False)
                self.assertEqual(state['children'], [789])
                value.translation_phase(False)
                with self.assertRaises(campaign.rt.Failure):
                    value.translation_phase(True)

    def test_stopped_daemon_receives_termination_before_continuation(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            value, state = self.fixture(folder)
            calls = []
            value.daemon.terminate.side_effect = lambda: calls.append('terminate')
            value.daemon.send_signal.side_effect = lambda number: calls.append(number)
            with patch.object(campaign.controller, 'PARAMETERS', folder), \
                 patch.object(campaign.rt, 'status', return_value=dict(frames=0)), \
                 patch.object(campaign.rt, 'children', return_value=[]), \
                 patch.object(campaign.controller.Session, 'stop_daemon', side_effect=lambda obj: calls.append('close')):
                value.stop()
            self.assertEqual(calls, ['terminate', signal.SIGCONT, 'close'])

    def test_failed_pause_postcondition_retains_observed_stopped_state(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            value, state = self.fixture(folder)
            value.translation_paused = False
            state['stopped'] = False
            def stop(number):
                state.update(stopped=True, children=[789])
            value.daemon.send_signal.side_effect = stop
            with patch.object(campaign.controller, 'PARAMETERS', folder), \
                 patch.object(campaign.rt, 'status', return_value=dict(frames=0)), \
                 patch.object(campaign.rt, 'children', side_effect=lambda pid: state['children']):
                with self.assertRaises(campaign.rt.Failure):
                    value.translation_phase(True)
                self.assertTrue(value.translation_paused)


if __name__ == '__main__':
    unittest.main()
