"""Image-pilot retirement boundaries; execute only in the development VM."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, mock_open, patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('mmap1_image_point', ROOT / 'bench/mmap1/delegated_point.py')
point = importlib.util.module_from_spec(spec)
spec.loader.exec_module(point)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class FixtureFailure(Exception):
    status = 'DATA_ERROR'


class ImageRetirement(unittest.TestCase):
    def run_case(self, *, bindings=0, changed_registry=False, drained=True):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            params = out / 'parameters'
            params.mkdir()
            for name, value in dict(rwsem_provider_active='N', rwsem_provider_bindings=str(bindings),
                                    service_progress='total=0 shown=0').items():
                (params / name).write_text(value)
            note, provider = out / 'note', out / 'provider'
            note.write_text('image-note')
            provider.write_text('provider-file')
            config = dict(mode='kd', boot_id='boot', variant='kdscope5-kd', kdir='/build',
                bundle='/bundle', host_state='/host', host_sha256='host-hash', sites='/sites',
                sites_sha256='site-hash', source_commit='1' * 40, state_sha256='state-hash',
                manifest_sha256='manifest-hash', model='threads', workers=2, profile=False,
                provider=str(provider))
            config_bytes = json.dumps(config).encode()
            rows = [dict(entry=10, generation=3)]
            session = out / 'execution-session.json'
            expected = dict(source=dict(state=0, modules=7, writers=1), registry=rows,
                            files={str(provider): digest(provider)})
            session.write_text(json.dumps(expected))
            original = dict(state='MEASURED_RETIREMENT_PENDING', passed=False,
                config_sha256=hashlib.sha256(config_bytes).hexdigest(),
                application=dict(passed=True, drained=drained),
                environment=dict(kernel_identity=dict(runtime_policy={})),
                execution_session=dict(path=str(session), sha256=digest(session)))
            (out / 'result.json').write_text(json.dumps(original))
            calls = []
            rt = SimpleNamespace(digest=digest, RETIRE=123, Failure=FixtureFailure,
                status=lambda: dict(state=0, modules=7, frames=0, writers=0),
                registry=lambda: [dict(entry=10, generation=4)] if changed_registry else rows,
                info=lambda fd: dict(state=2, modules=0, frames=0, writers=0),
                command=lambda argv, log, timeout: calls.append(('unload', argv)),
                write_json=lambda path, value: Path(path).write_text(json.dumps(value)))
            def verified(files):
                self.assertTrue(all(digest(name) == wanted for name, wanted in files.items()))
            execution = SimpleNamespace(registry=lambda value: value, NOTE=note,
                module_note_sha256=lambda path: digest(note))
            bench = SimpleNamespace(rt=rt, MODELS=('threads', 'processes'), WORKERS=(1, 2),
                load=lambda path: json.loads(Path(path).read_text()), execution=execution,
                verified_files=verified, verify_boot=Mock(), idle=lambda: calls.append(('idle',)))
            controller = SimpleNamespace(bench=bench, rt=rt, PYTHON=sys.executable,
                PARAMETERS=params, source_manifest=Mock())
            device = mock_open()
            device.return_value.fileno.return_value = 4
            with patch.object(point.os, 'geteuid', return_value=0), \
                 patch.object(point.time, 'monotonic', side_effect=[0, 11]), \
                 patch.object(point.fcntl, 'ioctl', side_effect=lambda *args: calls.append(('retire',))), \
                 patch('builtins.open', device):
                error = None
                try:
                    point.image_point(config, config_bytes, out, out, controller, True)
                except AssertionError as caught:
                    error = caught
            return error, calls, json.loads((out / 'finalization.json').read_text())

    def test_source_module_pins_remain_until_retire(self):
        error, calls, result = self.run_case()
        self.assertIsNone(error)
        self.assertEqual([row[0] for row in calls], ['retire', 'unload', 'idle'])
        self.assertEqual(result['retirement_observation']['source']['modules'], 7)
        self.assertEqual(result['retired'], dict(state=2, modules=0, frames=0, writers=0))
        self.assertTrue(result['passed'] and result['drained'])
        self.assertFalse(result['accepted'] or result['delegation_proved'])

    def test_live_binding_prevents_retirement(self):
        error, calls, result = self.run_case(bindings=1)
        self.assertIsNotNone(error)
        self.assertEqual(calls, [])
        self.assertEqual(result['state'], 'FAILED')

    def test_image_change_prevents_retirement(self):
        error, calls, result = self.run_case(changed_registry=True)
        self.assertIsNotNone(error)
        self.assertEqual(calls, [])
        self.assertFalse(result['passed'])

    def test_undrained_application_prevents_retirement(self):
        error, calls, result = self.run_case(drained=False)
        self.assertIsNotNone(error)
        self.assertEqual(calls, [])
        self.assertFalse(result['drained'])


if __name__ == '__main__':
    unittest.main()
