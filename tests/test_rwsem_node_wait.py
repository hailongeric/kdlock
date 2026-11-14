"""VM-only focused production-excerpt checks for ordinary writer turn waiting.

Controlled scheduling points check the wait transition and exact control users;
they do not establish real scheduler, weak-memory, MCS or live-kernel progress.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
CASES = ('head', 'turn_before_state', 'turn_after_state', 'turn_after_check',
         'turn_at_schedule', 'selection_before_turn', 'reader_wait',
         'reader_before_registration', 'cached_wake', 'callable', 'non_atomic',
         'unmarked', 'cancel_queued', 'cancel_selected', 'grant_before_signal',
         'start_error', 'try_miss')


class RwsemNodeWaitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        name = os.environ.get('KDLOCK_RWSEM_NODE_WAIT_TEST_CONFIG')
        if not name:
            raise RuntimeError('KDLOCK_RWSEM_NODE_WAIT_TEST_CONFIG is required; VM execution only')
        config = json.loads(Path(name).read_text())
        if platform.release() != config['expected_release']:
            raise RuntimeError('VM release differs')
        parent, compiler = Path(config['scratch_parent']), Path(config['compiler'])
        if not parent.is_absolute() or not parent.is_dir() or not compiler.is_absolute() or not compiler.is_file():
            raise ValueError('supply existing absolute VM scratch and compiler paths')
        cls.output = Path(tempfile.mkdtemp(prefix='rwsem-node-wait-', dir=parent))
        inputs = {}

        def source(name):
            data = (ROOT / name).read_bytes()
            inputs[name] = hashlib.sha256(data).hexdigest()
            return data.decode()

        def excerpt(text, name):
            match = re.search(r'^[\w *]+\b' + name + r'\(', text, re.M)
            if match is None:
                raise ValueError('production function missing: ' + name)
            return text[match.start():text.index('\n}', match.end()) + 2]

        native, mutex = source('kernel/rw_native.c'), source('kernel/mutex.c')
        functions = [excerpt(native, name) for name in
                     ('record_free_locked', 'caller_done', 'kd_rw_native_select_turn',
                      'kd_rw_native_queue_depart', 'native_start', 'write_lock_common')]
        functions.append(excerpt(mutex, 'publish_condition'))
        (cls.output / 'node_wait_functions.h').write_text('\n\n'.join(functions) + '\n')
        phase = re.search(r'enum kd_rw_native_phase \{.*?\};', source('kernel/rw_native.h'), re.S)
        if phase is None:
            raise ValueError('production native phase missing')
        (cls.output / 'node_wait_phase.h').write_text(phase.group() + '\n')
        (cls.output / 'kd_rw_wait_diag.h').write_text(source('include/kd_rw_wait_diag.h'))
        (cls.output / 'node_wait_check.c').write_text(source('tests/rwsem_node_wait/node_wait_check.c'))
        cls.binaries = {}
        for candidate in (0, 1):
            for diag in (0, 1):
                label = f'node{candidate}-diag{diag}'
                binary = cls.output / label
                command = [str(compiler), '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror']
                if candidate:
                    command += ['-DCONFIG_KDLOCK_RWSEM_NODE_WAIT']
                if diag:
                    command += ['-DCONFIG_KDLOCK_RW_WAIT_DIAG']
                command += [str(cls.output / 'node_wait_check.c'), '-o', str(binary)]
                result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                (cls.output / (label + '-build.json')).write_text(json.dumps(dict(
                    command=command, inputs=inputs, release=platform.release(),
                    returncode=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2) + '\n')
                if result.returncode:
                    raise RuntimeError(f'focused build failed; receipts: {cls.output}')
                cls.binaries[label] = binary

    def test_wait_transition_and_lifetime_boundaries(self):
        for label, binary in self.binaries.items():
            for case in CASES:
                with self.subTest(configuration=label, case=case):
                    command = [str(binary), case]
                    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
                    (self.output / f'{label}-{case}.json').write_text(json.dumps(dict(
                        command=command, returncode=result.returncode, stdout=result.stdout,
                        stderr=result.stderr), indent=2) + '\n')
                    self.assertEqual(result.returncode, 0, f'{result.stderr}; receipts: {self.output}')
                    self.assertEqual(result.stdout, f'PASS {case}\n')

    def test_snapshot_algorithm_identity_and_registration_accounting(self):
        with mock.patch.dict(sys.modules, protocol=type('Protocol', (), {'DEVICE': '/unused'})):
            spec = importlib.util.spec_from_file_location('node_wait_decoder', ROOT / 'bench/nano/wait_diag.py')
            decoder = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(decoder)
        count = len(decoder.COUNTERS)

        def collect(candidate, enabled, first=0, begin=1):
            counts = dict.fromkeys(decoder.COUNTERS, 0)
            if enabled:
                counts.update(write_prepare=first, write_first=first, write_begin=begin, write_return=begin)
            data = bytearray(72 + 64 * count * 8)
            struct.pack_into('=9Q', data, 0, 2, count, enabled, 1, 1, 2, 123, 1, candidate)
            struct.pack_into(f'={count}Q', data, 72, *(counts[key] for key in decoder.COUNTERS))

            def ioctl(device, command, buffer, mutate):
                self.assertEqual(command, 0x4210)
                self.assertTrue(mutate)
                self.assertEqual(len(buffer), len(data))
                buffer[:] = data

            with mock.patch('builtins.open', mock.mock_open()), mock.patch.object(decoder.fcntl, 'ioctl', ioctl):
                return decoder.collect(123, 1, 2, bool(enabled))

        for candidate in (0, 1):
            for enabled in (0, 1):
                result = collect(candidate, enabled, first=0 if candidate else enabled)
                self.assertEqual(result['node_wait'], bool(candidate))
                decoder.validate(result, 0, 1)
        with self.assertRaisesRegex(ValueError, 'registration/lifetime'):
            decoder.validate(collect(0, 1), 0, 1)
        with self.assertRaisesRegex(ValueError, 'registrations exceed'):
            decoder.validate(collect(1, 1, first=2), 0, 1)
        with self.assertRaisesRegex(ValueError, 'identity'):
            collect(2, 0)


if __name__ == '__main__':
    unittest.main()
