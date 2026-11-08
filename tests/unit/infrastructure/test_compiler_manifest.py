"""Optional compiler evidence with substituted files and descriptor metadata.

No translation, build, provider or kernel text access is performed here.
Execute these focused checks only in the development VM.
"""

import contextlib
import hashlib
import importlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'disassem'))
import compiler_manifest as manifest


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class CompilerManifestTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.temporary = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.root = Path(self.temporary)
        self.attempt = self.root / 'attempt'
        self.attempt.mkdir()
        self.asm = self.root / 'asm'
        self.asm.mkdir()
        self.context = dict(schema=1, session_id='local-session', compile_attempt_id=1,
                            entry=dict(pid=0, tgid=42, entry=0xffffffff81001000,
                                       lock_kind=2, entry_abi=2, base_generation=7,
                                       status=1, target=0xffffffff81002000,
                                       jump_from=0))
        (self.attempt / 'context.json').write_text(json.dumps(self.context))
        self.stack.enter_context(patch.dict(os.environ,
            KD_PROVENANCE_ATTEMPT_DIR=str(self.attempt), KD_PROVENANCE_DIR=str(self.root)))
        self.stack.enter_context(patch.object(manifest, '_recorder', None))
        self.stack.enter_context(patch.object(manifest, '_directory', None))
        self.stack.enter_context(patch.object(manifest, '_start_ticks', return_value=123))
        self.stack.enter_context(patch.object(manifest, '_interpreter', return_value={
            'path': '/fixture/python', 'resolved_path': '/fixture/python',
            'proc_exe': '/fixture/python', 'sha256': 'a' * 64, 'version': 'fixture'}))
        self.binary = self.asm / 'jit.bin'
        self.binary.write_bytes(b'B' * 64)
        (self.asm / 'jit.S').write_bytes(b'patched assembly\n')

    def observations(self):
        manifest.capture('translation', pid=0, entry=self.context['entry']['entry'],
                         lock_kind='mutex', entry_abi=2, trusted_source=True,
                         direct_call_depth=5, body_witness=False)
        with tempfile.TemporaryFile() as stream:
            value = os.fstat(stream.fileno())
            manifest.capture('descriptor', fd=stream.fileno(), inherited=True,
                             inherited_fd=stream.fileno(), opened=value, named=value,
                             source_info=dict(state=0, modules=1, frames=0, writers=1))
        packet = struct.pack('<IIII', 21, 59 | (1 << 14) | (1 << 18), 256, 8192)
        parsed = dict(mutex_images=True, mutex_exclusive=True,
                      source_frontier_direction=True)
        manifest.capture('capabilities', fd=manifest._recorder.data['descriptor']['fd'], raw=packet,
                         result=0, validated=True, parsed=parsed)
        row = b'1 ffffffff81002000 1 1 2 primitive_call\n'
        manifest.capture('service_table', mode='paged', before=b'1 1 1\n',
                         after=b'1 1 1\n', generation=1, slots=1, active=1,
                         pages=[row] + [b''] * 7, raw=row, parsed={})
        manifest.capture('controls', mode='read', raw=b'', parsed={})
        for name in ('callee_table.txt', 'ij_table.txt'):
            manifest.capture('history', name=name, state='read', raw=b'', text='')
        manifest.capture_assembly(self.asm / 'jit.S')

    def complete(self):
        manifest.complete(self.binary, {'python': 'fixture'})
        path = self.attempt / 'manifest.json'
        raw = path.read_bytes()
        self.assertEqual((self.attempt / 'manifest.sha256').read_text(), sha(raw) + '\n')
        return json.loads(raw)

    def test_complete_manifest_retains_context_and_exact_inputs(self):
        self.observations()
        record = self.complete()
        self.assertTrue(record['complete'])
        self.assertTrue(record['evidence_complete'], record['errors'])
        self.assertEqual(record['context'], self.context)
        self.assertIsNone(record['kernel_durable_lease_id'])
        self.assertEqual(record['compiler']['pid'], os.getpid())
        self.assertNotEqual(record['compiler']['pid'], record['context']['entry']['pid'])
        self.assertEqual(record['context']['entry']['tgid'], 42)
        packet = bytes.fromhex(record['capabilities']['raw_hex'])
        self.assertEqual(struct.unpack('<IIII', packet)[0], 21)
        self.assertEqual(record['capabilities']['version'], 21)
        self.assertEqual(record['binary']['sha256'], sha(b'B' * 64))
        self.assertEqual((self.attempt / 'jit.S').read_bytes(), b'patched assembly\n')
        self.assertTrue(record['assembly']['unchanged_after_build'])
        before = (self.attempt / 'manifest.json').read_bytes()
        manifest.complete(self.binary, {})
        self.assertEqual((self.attempt / 'manifest.json').read_bytes(), before)

    def test_disabled_hooks_do_not_open_or_emit(self):
        os.environ.pop('KD_PROVENANCE_ATTEMPT_DIR')
        with patch.object(manifest, '_Recorder', side_effect=AssertionError('unexpected recorder')):
            manifest.capture('unknown')
            manifest.capture_assembly('/missing')
            manifest.complete('/missing', {})
        self.assertFalse((self.attempt / 'manifest.json').exists())

    def test_no_success_record_without_complete_build_hook(self):
        self.observations()
        # Refusal, dependency errors and any build exception skip complete().
        self.assertFalse((self.attempt / 'manifest.json').exists())
        self.assertFalse((self.attempt / 'manifest.sha256').exists())

    def test_assembly_change_marks_evidence_incomplete(self):
        self.observations()
        (self.asm / 'jit.S').write_bytes(b'changed after gcc started\n')
        record = self.complete()
        self.assertTrue(record['complete'])
        self.assertFalse(record['evidence_complete'])
        self.assertFalse(record['assembly']['unchanged_after_build'])
        self.assertEqual((self.attempt / 'jit.S').read_bytes(), b'patched assembly\n')

    def test_capture_and_manifest_failures_never_raise(self):
        self.observations()
        with patch.object(manifest._recorder, 'artifact', side_effect=OSError('capture failed')):
            manifest.capture('history', name='callee_table.txt', state='read', raw=b'x', text='x')
        with patch.object(Path, 'open', side_effect=OSError('write failed')):
            manifest.complete(self.binary, {})
        self.assertFalse((self.attempt / 'manifest.sha256').exists())

    def test_sidecar_close_failure_leaves_no_final_pair(self):
        self.observations()
        original = Path.open
        class CloseFailure:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self.stream
            def __exit__(self, *args):
                self.stream.close()
                raise OSError('sidecar close failed after writing')
        def opening(path, *args, **kwargs):
            stream = original(path, *args, **kwargs)
            if path.name == 'manifest.sha256.partial':
                return CloseFailure(stream)
            return stream
        with patch.object(Path, 'open', opening):
            manifest.complete(self.binary, {})
        self.assertFalse((self.attempt / 'manifest.json').exists())
        self.assertFalse((self.attempt / 'manifest.sha256').exists())

    def test_sidecar_rename_failure_leaves_no_final_pair(self):
        self.observations()
        original = os.rename
        def renaming(source, target):
            original(source, target)
            if Path(target).name == 'manifest.sha256':
                raise OSError('rename reported failure after taking effect')
        with patch.object(manifest.os, 'rename', side_effect=renaming):
            manifest.complete(self.binary, {})
        self.assertTrue((self.attempt / 'manifest.json').exists())
        self.assertFalse((self.attempt / 'manifest.sha256').exists())

    def test_capture_bounds_and_error_count_are_finite(self):
        with patch.object(manifest, 'MAX_ARTIFACT_BYTES', 4):
            manifest.capture('history', name='callee_table.txt', state='read', raw=b'12345', text='12345')
        for _ in range(manifest.MAX_ERRORS + 10):
            manifest.capture('unknown')
        self.assertEqual(len(manifest._recorder.errors), manifest.MAX_ERRORS)
        self.assertTrue(manifest._recorder.errors_truncated)
        self.assertFalse((self.attempt / 'callee_table.txt').exists())

    def test_capability_hook_retains_validated_raw_version_without_extra_query(self):
        session = importlib.import_module('device_session')
        for version in (20, 21):
            packet = struct.pack('<IIII', version, 59 | (1 << 14) | (1 << 18), 256, 8192)
            queries = []
            def ioctl(fd, command, value, mutate):
                queries.append((fd, command, mutate))
                value[:] = packet
                return 0
            with patch.object(session.fcntl, 'ioctl', side_effect=ioctl):
                parsed = session.query_capabilities(123)
            self.assertEqual(queries, [(123, session.CAPS, True)])
            captured = manifest._recorder.data['capabilities']
            self.assertTrue(captured['validated'])
            self.assertEqual(captured['raw_hex'], packet.hex())
            self.assertEqual(captured['version'], version)
            self.assertEqual(captured['fd'], 123)
            self.assertEqual(parsed['source_frontier_direction'], version == 21)
        with patch.object(manifest, 'capture', side_effect=OSError('optional capture failed')):
            with patch.object(session.fcntl, 'ioctl', side_effect=ioctl):
                self.assertTrue(session.query_capabilities(123)['source_frontier_direction'])

    def test_reused_attempt_cannot_overwrite_immutable_manifest(self):
        self.observations()
        self.complete()
        before = (self.attempt / 'manifest.json').read_bytes()
        manifest._recorder = None
        manifest.capture('translation', pid=123)
        manifest.complete(self.binary, {})
        self.assertEqual((self.attempt / 'manifest.json').read_bytes(), before)

    def test_history_hook_retains_raw_bytes_before_normalization_and_mutation(self):
        memread = importlib.import_module('memread')
        previous = Path.cwd()
        os.chdir(self.root)
        try:
            raw = b'0xffffffff81002000\r\n0xffffffff81002000\r\n'
            (self.asm / 'callee_table.txt').write_bytes(raw)
            text = memread._read_history('callee_table.txt')
            self.assertEqual(text, raw.decode('ascii').replace('\r\n', '\n'))
            (self.asm / 'callee_table.txt').write_bytes(b'later content\n')
            captured = manifest._recorder.data['histories']['callee_table.txt']
            self.assertEqual(captured['sha256'], sha(raw))
            self.assertEqual(captured['parser_sha256'], sha(text.encode('ascii')))
            self.assertEqual((self.attempt / 'callee_table.txt').read_bytes(), raw)
            self.assertEqual(memread._read_history('ij_table.txt'), '')
            missing = manifest._recorder.data['histories']['ij_table.txt']
            self.assertEqual(missing['state'], 'unavailable')
            self.assertNotIn('sha256', missing)
        finally:
            os.chdir(previous)

    def test_registry_reader_retains_pages_from_the_actual_snapshot(self):
        session = importlib.import_module('device_session')
        directory = self.root / 'registry'
        directory.mkdir()
        state = b'1 1 1\r\n'
        row = b'1 ffffffff81002000 1 1 2 primitive_call\r\n'
        (directory / 'service_call_table_state').write_bytes(state)
        for page in range(8):
            (directory / f'service_call_page_{page}').write_bytes(row if page == 0 else b'')
        self.assertEqual(session.read_service_call_table(directory), row.decode().replace('\r\n', '\n'))
        (directory / 'service_call_page_0').write_bytes(b'later content\n')
        record = manifest._recorder.data['service_table']
        self.assertEqual(record['generation'], 1)
        self.assertEqual(record['state_before_hex'], state.hex())
        self.assertEqual(record['snapshot']['sha256'], sha(row))
        self.assertEqual((self.attempt / record['snapshot']['path']).read_bytes(), row)


if __name__ == '__main__':
    unittest.main()
