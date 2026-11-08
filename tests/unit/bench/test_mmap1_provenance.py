"""Offline provenance mocks; execute only in the designated development VM."""
import copy
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/mmap1'))
import provenance


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + '\n')


class Chain(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'source'
        self.root.mkdir()
        self.required = dict(entry=0x1000, call_target=0x2000, source_ip=0x3000)
        self.writer = dict(pid=101, start_ticks=1001, fd=4, device=11, inode=22, rdev=33,
                           flags=os.O_RDWR | os.O_CLOEXEC)
        self.row = dict(pid=0, tgid=44, entry=0x1000, lock_kind=2, entry_abi=2,
                        status=0, code=0x9000, generation=2, requirements=(1 << 14) | (1 << 8))
        self.expected = dict(boot_id='boot-a', registry=[self.row],
            daemon=dict(pid=101, start_ticks=1001, device_writer=self.writer),
            preparer=dict(executable='/usr/bin/python3', executable_sha256='a' * 64))
        self.observation = dict(schema=1, clock='CLOCK_MONOTONIC', boot_id='boot-a',
            read_start_ns=200, read_end_ns=210, registry=[self.row], observer=self.expected['preparer'])
        session = dict(schema=1, session_id='101-1001', boot_id='boot-a',
                        daemon=self.writer, entry=0x1000)
        write_json(self.root / 'session.json', session)
        self.compile_dir = self.root / 'compile-1'
        self.compile_dir.mkdir()
        self.context = dict(schema=1, session_id='101-1001', compile_attempt_id=1,
            entry=dict((key, self.row[key]) for key in provenance.KEY))
        self.context['entry'].update(base_generation=1, status=1, target=0x2000, jump_from=0)
        write_json(self.compile_dir / 'context.json', self.context)
        payload = bytearray(96)
        payload[9:16], payload[25:32], payload[41:45] = b'KDWB002', b'KDWC002', b'KDAB'
        payload[45:48] = bytes((2, 3, self.row['requirements'] & 255))
        struct.pack_into('<I', payload, 48, self.row['requirements'])
        self.payload = bytes(payload)
        self.upload = dict(schema=1, session_id='101-1001', upload_id=1,
            compile_attempt_id=1, cache_hit=False, entry={key: self.row[key] for key in provenance.KEY},
            base_generation=1, protocol=3, requirements=self.row['requirements'],
            image_length=len(payload), accepted_length=len(payload), upload_complete=True,
            evidence_complete=True, final_write_end_ns=100, payload='upload-1/payload.bin', error=None)
        (self.root / 'upload-1').mkdir()
        (self.root / self.upload['payload']).write_bytes(self.payload)
        self.assembly = b'/*\nloc_2000\nPUSH RBP\n*/\nloc_2000:\nPUSH RBP\nMOVABS R14, 0x3000\nMOV Stack_IJ, 16\nJMP full_exit\n'
        assembly = self.artifact('jit.S', self.assembly)
        assembly['unchanged_after_build'] = True
        histories = {}
        for name, data in (('callee_table.txt', b'0x2000\n'), ('ij_table.txt', b'')):
            histories[name] = dict(self.artifact(name, data), state='read', errno=None,
                                    parser_sha256=provenance.digest(data))
        pages = [self.artifact('service-page-%d.txt' % i, b'') for i in range(8)]
        metadata = dict(st_dev=11, st_ino=22, st_rdev=33, st_mode=0o20600)
        features = 262144 | 16384 | 16 | 8 | 2
        self.manifest = dict(schema=1, context=self.context,
            context_sha256=provenance.digest((self.compile_dir / 'context.json').read_bytes()),
            context_validated=True, complete=True, evidence_complete=True,
            errors=[], errors_truncated=False,
            translation=dict(pid=0, entry=0x1000, lock_kind='mutex', entry_abi=2, trusted_source=True),
            compiler=dict(pid=102, ppid=101, start_ticks=1002, parent_start_ticks=1001,
                interpreter=dict(path='/usr/bin/python3', resolved_path='/usr/bin/python3',
                                 proc_exe='/usr/bin/python3', sha256='a' * 64, version='test')),
            descriptor=dict(validated=True, inherited=True, relationship='inherited_description_then_dup',
                inherited_fd=4, fd=5, opened=metadata, named=metadata, inherited_stat=metadata,
                access_flags=os.O_RDWR, source_info=dict(state=0, frames=0, modules=0, writers=1)),
            capabilities=dict(raw_hex=struct.pack('<IIII', 21, features, 0, 8192).hex(),
                fd=5, result=0, validated=True, version=21, features=features, mutex_stack_bytes=0,
                percpu_module_bytes=8192, parsed=dict(source_frontier_direction=True,
                    mutex_images=True, mutex_exclusive=True)),
            service_table=dict(mode='paged', validated=True, generation=0, slots=0, active=0,
                state_before_hex=b'0 0 0\n'.hex(), state_after_hex=b'0 0 0\n'.hex(), pages=pages,
                snapshot=self.artifact('service-table.txt', b''), parsed={}),
            controls=dict(mode='read', snapshot=self.artifact('rwsem-controls.txt', b''), parsed={}),
            histories=histories, assembly=assembly,
            binary=dict(bytes=len(payload), sha256=provenance.digest(self.payload),
                        header_hex=self.payload[:64].hex()))
        self.seal()

    def artifact(self, name, data):
        (self.compile_dir / name).write_bytes(data)
        return dict(path=name, bytes=len(data), sha256=provenance.digest(data))

    def seal(self):
        write_json(self.compile_dir / 'manifest.json', self.manifest)
        value = provenance.digest((self.compile_dir / 'manifest.json').read_bytes())
        (self.compile_dir / 'manifest.sha256').write_text(value + '\n')
        self.upload['manifest_sha256'] = value
        write_json(self.root / 'upload-1/receipt.json', self.upload)

    def verify(self):
        return provenance.associate(self.root, self.observation, self.expected, self.required)

    def batch(self, *, count=1, overflow=0):
        summary = dict(token=7, revision=count, slot=4, count=count,
                       overflow_report_events=overflow)
        self.manifest['context']['learning_snapshot'] = summary
        self.upload['learning_snapshot'] = copy.deepcopy(summary)
        caps = self.manifest['capabilities']
        caps['version'] = 22
        caps['features'] |= 1 << 19
        caps['raw_hex'] = struct.pack('<IIII', 22, caps['features'],
            caps['mutex_stack_bytes'], caps['percpu_module_bytes']).hex()
        write_json(self.compile_dir / 'context.json', self.manifest['context'])
        self.manifest['context_sha256'] = provenance.digest((self.compile_dir / 'context.json').read_bytes())
        self.seal()
        self.upload_context()
        return summary

    def upload_context(self):
        names = ('schema', 'session_id', 'upload_id', 'compile_attempt_id', 'manifest_sha256',
                 'cache_hit', 'entry', 'base_generation', 'protocol', 'requirements',
                 'image_length', 'learning_snapshot')
        write_json(self.root / 'upload-1/context.json', {name: self.upload[name] for name in names})

    def test_positive_chain_and_frozen_capture(self):
        chain, files, assembly, history = self.verify()
        self.assertEqual((chain['base_generation'], chain['observed_generation']), (1, 2))
        self.assertEqual(chain['payload_sha256'], provenance.digest(self.payload))
        self.assertEqual(assembly, self.assembly)
        self.assertEqual(history, b'0x2000\n')
        self.assertFalse(chain['kernel_digest_reported'])
        destination = self.root.parent / 'fixed'
        bound = provenance.capture(self.root, destination, self.observation, self.expected, self.required)
        (self.compile_dir / 'jit.S').write_text('replaced workspace')
        self.assertEqual(provenance.associate(destination, self.observation, self.expected,
                                             self.required)[2], self.assembly)
        self.assertIn(str(destination / 'observation.json'), bound)

    def test_cache_hit_retains_original_compilation(self):
        self.upload['cache_hit'] = True
        self.seal()
        self.assertEqual(self.verify()[0]['compile_attempt_id'], 1)
        (self.root / self.upload['payload']).write_bytes(self.payload[:-1] + b'X')
        with self.assertRaisesRegex(ValueError, 'sent bytes'):
            self.verify()

    def test_v22_batch_summary_preserves_narrow_payload_association(self):
        summary = self.batch(overflow=9)
        chain, files, _, _ = self.verify()
        self.assertEqual(chain['learning_snapshot'], summary)
        self.assertIn('upload-1/context.json', files)
        self.assertEqual(chain['payload_sha256'], provenance.digest(self.payload))
        self.assertFalse(chain['batch_record_membership_proved'])
        self.assertFalse(chain['kernel_acknowledgment_witnessed'])
        self.assertFalse(chain['cumulative_history_completeness_proved'])
        self.assertFalse(chain['kernel_digest_reported'])
        self.assertFalse(chain['execution_proved'])
        destination = self.root.parent / 'fixed-v22'
        provenance.capture(self.root, destination, self.observation, self.expected, self.required)
        (self.compile_dir / 'callee_table.txt').write_bytes(b'later mutable workspace\n')
        self.assertEqual(provenance.associate(destination, self.observation, self.expected,
                                             self.required)[0]['learning_snapshot'], summary)

    def test_v22_missing_or_mismatched_batch_summary_refuses(self):
        self.batch()
        for location in ('compiler', 'upload_context', 'upload_receipt'):
            for change in (None, dict(token=8), dict(revision=2), dict(slot=5), dict(count=2),
                           dict(revision=True), dict(count=True), dict(overflow_report_events=False)):
                with self.subTest(location=location, change=change):
                    context = copy.deepcopy(self.manifest['context'])
                    receipt = copy.deepcopy(self.upload)
                    upload_context = json.loads((self.root / 'upload-1/context.json').read_text())
                    owner = context if location == 'compiler' else (
                        upload_context if location == 'upload_context' else receipt)
                    owner['learning_snapshot'] = (None if change is None else
                        dict(owner['learning_snapshot'], **change))
                    if location == 'compiler':
                        original = self.manifest['context']
                        self.manifest['context'] = context
                        write_json(self.compile_dir / 'context.json', context)
                        self.manifest['context_sha256'] = provenance.digest(
                            (self.compile_dir / 'context.json').read_bytes())
                        self.seal()
                        self.upload_context()
                    elif location == 'upload_context':
                        write_json(self.root / 'upload-1/context.json', upload_context)
                    else:
                        write_json(self.root / 'upload-1/receipt.json', receipt)
                    with self.assertRaises(ValueError):
                        self.verify()
                    if location == 'compiler':
                        self.manifest['context'] = original
                    write_json(self.compile_dir / 'context.json', self.manifest['context'])
                    self.manifest['context_sha256'] = provenance.digest(
                        (self.compile_dir / 'context.json').read_bytes())
                    self.seal()
                    self.upload_context()

    def test_v22_summary_bounds_and_legacy_cache_are_refused(self):
        self.batch()
        for change in (dict(token=0), dict(token=True), dict(token=1 << 64),
                dict(revision=-1), dict(revision=0), dict(slot=511), dict(slot=-1),
                dict(count=33), dict(count=True), dict(overflow_report_events=-1),
                dict(overflow_report_events=1 << 64)):
            with self.subTest(change=change):
                summary = dict(self.manifest['context']['learning_snapshot'], **change)
                with self.assertRaises(ValueError):
                    provenance.learning_summary(dict(self.manifest['context'], learning_snapshot=summary),
                        dict(self.upload, learning_snapshot=summary),
                        dict(self.upload, learning_snapshot=summary), 1)
        self.upload['cache_hit'] = True
        self.seal()
        self.upload_context()
        with self.assertRaisesRegex(ValueError, 'legacy command cache'):
            self.verify()

    def test_v22_upload_context_identifiers_and_source_fd_must_match(self):
        self.batch()
        path = self.root / 'upload-1/context.json'
        original = json.loads(path.read_text())
        for change in (dict(upload_id=2), dict(compile_attempt_id=2), dict(base_generation=0),
                       dict(upload_id=True), dict(compile_attempt_id=True),
                       dict(session_id='another-session'), dict(manifest_sha256='0' * 64),
                       dict(entry=dict(self.upload['entry'], pid=1))):
            with self.subTest(change=change):
                write_json(path, dict(original, **change))
                with self.assertRaises(ValueError):
                    self.verify()
        write_json(path, original)
        self.manifest['capabilities']['fd'] = 6
        self.seal()
        self.upload_context()
        with self.assertRaisesRegex(ValueError, 'descriptor lineage'):
            self.verify()
        self.manifest['capabilities']['fd'] = 5
        for name in ('opened', 'named', 'inherited_stat'):
            original = self.manifest['descriptor'][name]
            self.manifest['descriptor'][name] = dict(original, st_ino=23)
            self.seal()
            self.upload_context()
            with self.subTest(source_identity=name), self.assertRaisesRegex(ValueError, 'device identity'):
                self.verify()
            self.manifest['descriptor'][name] = original

    def test_empty_v22_batch_requires_cold_zero_generation(self):
        self.batch(count=0)
        with self.assertRaisesRegex(ValueError, 'cold root'):
            self.verify()
        self.row['generation'] = 1
        self.upload['base_generation'] = 0
        context = self.manifest['context']
        context['entry'].update(base_generation=0, status=-1, target=0, jump_from=0)
        history = self.artifact('callee_table.txt', b'')
        self.manifest['histories']['callee_table.txt'] = dict(history, state='read', errno=None,
            parser_sha256=provenance.digest(b''))
        write_json(self.compile_dir / 'context.json', context)
        self.manifest['context_sha256'] = provenance.digest((self.compile_dir / 'context.json').read_bytes())
        self.seal()
        self.upload_context()
        self.assertEqual(self.verify()[0]['learning_snapshot']['count'], 0)

    def test_partial_or_failed_upload_never_links(self):
        for update in (dict(upload_complete=False), dict(evidence_complete=False),
                       dict(accepted_length=95), dict(manifest_sha256=None)):
            with self.subTest(update=update):
                changed = dict(self.upload, **update)
                write_json(self.root / 'upload-1/receipt.json', changed)
                with self.assertRaises(ValueError):
                    self.verify()

    def test_overlap_and_later_write_rejected(self):
        for clock in (0, 201, 211, None):
            with self.subTest(clock=clock):
                write_json(self.root / 'upload-1/receipt.json', dict(self.upload, final_write_end_ns=clock))
                with self.assertRaisesRegex(ValueError, 'overlaps'):
                    self.verify()

    def test_pending_or_later_generation_rejected(self):
        for key, value in (('status', 1), ('status', 2), ('generation', 1), ('generation', 3),
                           ('generation', 1 << 64), ('code', 0)):
            before = self.row[key]
            with self.subTest(key=key, value=value):
                self.row[key] = value
                with self.assertRaises(ValueError):
                    self.verify()
                self.row[key] = before

    def test_duplicate_successful_publication_is_ambiguous(self):
        duplicate = dict(self.upload, upload_id=2, payload='upload-2/payload.bin')
        write_json(self.root / 'upload-2/receipt.json', duplicate)
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            self.verify()

    def test_boot_descriptor_and_compiler_lifetime_mismatches(self):
        for section, key, value in (('descriptor', 'inherited_fd', 9),
                ('descriptor', 'relationship', 'direct_open'), ('compiler', 'parent_start_ticks', 999)):
            original = copy.deepcopy(self.manifest)
            with self.subTest(section=section, key=key):
                self.manifest[section][key] = value
                self.seal()
                with self.assertRaises(ValueError):
                    self.verify()
            self.manifest = original
        self.seal()
        self.observation['boot_id'] = 'boot-b'
        with self.assertRaisesRegex(ValueError, 'boot'):
            self.verify()

    def test_capability_history_or_service_capture_mismatch(self):
        cases = [('capabilities', 'validated', False), ('capabilities', 'version', 20),
                 ('capabilities', 'result', False), ('capabilities', 'mutex_stack_bytes', False),
                 ('service_table', 'state_after_hex', b'1 0 0\n'.hex()),
                 ('assembly', 'unchanged_after_build', False), ('binary', 'sha256', '0' * 64)]
        for section, key, value in cases:
            original = copy.deepcopy(self.manifest)
            with self.subTest(section=section, key=key):
                self.manifest[section][key] = value
                self.seal()
                with self.assertRaises(ValueError):
                    self.verify()
            self.manifest = original
        self.seal()
        (self.compile_dir / 'callee_table.txt').write_bytes(b'0x4000\n')
        with self.assertRaisesRegex(ValueError, 'artifact bytes'):
            self.verify()

    def test_missing_or_replaced_compiler_manifest(self):
        (self.compile_dir / 'manifest.json').write_text('{}')
        with self.assertRaises(ValueError):
            self.verify()

    def test_gate_uses_captured_inputs_without_added_registry_reads(self):
        for version in (21, 22):
            with self.subTest(version=version):
                self.captured_gate(version)

    def captured_gate(self, version):
        import settled
        (self.compile_dir / 'jit.S').write_bytes(self.assembly)
        if version == 22:
            self.batch()
        destination = self.root.parent / ('fixed-' + str(version))
        bound = provenance.capture(self.root, destination, self.observation,
                                   self.expected, self.required)
        value = settled.SettledObservation.__new__(settled.SettledObservation)
        value.c, value.result = dict(required_publication=self.required), {}
        value.out = self.root.parent / ('gate-' + str(version))
        value.out.mkdir()
        value.save = Mock()
        expected = dict(self.expected, files=bound, provenance=dict(root=str(destination),
                           observation=str(destination / 'observation.json')))
        value.exact = Mock(expected=expected)
        (self.compile_dir / 'jit.S').write_text('changed current workspace')
        capability = {name: self.manifest['capabilities'][name] for name in
            ('version', 'features', 'mutex_stack_bytes', 'percpu_module_bytes')}
        with patch.object(settled, 'current_capability', return_value=capability) as caps, \
             patch.object(settled.rt, 'registry') as registry:
            value.publication_gate()
        value.exact.verify.assert_called_once()
        caps.assert_called_once()
        registry.assert_not_called()
        self.assertTrue(value.result['required_publication']['passed'])

    def test_gate_refuses_current_and_captured_capability_mismatch_without_more_reads(self):
        import settled
        destination = self.root.parent / 'fixed'
        bound = provenance.capture(self.root, destination, self.observation, self.expected, self.required)
        value = settled.SettledObservation.__new__(settled.SettledObservation)
        value.c, value.out, value.result = dict(required_publication=self.required), self.root.parent, {}
        value.save = Mock()
        value.exact = Mock(expected=dict(self.expected, files=bound,
            provenance=dict(root=str(destination), observation=str(destination / 'observation.json'))))
        bits = self.manifest['capabilities']['features']
        for capability in (dict(version=22, features=bits | (1 << 19), mutex_stack_bytes=0,
                                percpu_module_bytes=8192),
                           dict(version=21, features=bits | 1, mutex_stack_bytes=256,
                                percpu_module_bytes=8192)):
            with self.subTest(capability=capability), \
                 patch.object(settled, 'current_capability', return_value=capability) as caps, \
                 patch.object(settled.rt, 'registry') as registry:
                with self.assertRaises(settled.rt.Failure) as raised:
                    value.publication_gate()
            self.assertEqual(raised.exception.status, 'DATA_ERROR')
            self.assertFalse(value.result['required_publication']['passed'])
            caps.assert_called_once()
            registry.assert_not_called()
        self.assertEqual(value.exact.verify.call_count, 2)

    def test_v22_missing_upload_context_refuses_without_more_device_queries(self):
        import settled
        self.batch()
        (self.root / 'upload-1/context.json').unlink()
        write_json(self.root / 'observation.json', self.observation)
        value = settled.SettledObservation.__new__(settled.SettledObservation)
        value.c, value.out, value.result = dict(required_publication=self.required), self.root.parent, {}
        value.save = Mock()
        value.exact = Mock(expected=dict(self.expected,
            provenance=dict(root=str(self.root), observation=str(self.root / 'observation.json'))))
        with patch.object(settled, 'current_capability') as caps, \
             patch.object(settled.rt, 'registry') as registry:
            with self.assertRaises(settled.rt.Failure) as raised:
                value.publication_gate()
        self.assertEqual(raised.exception.status, 'DATA_ERROR')
        self.assertFalse(value.result['required_publication']['passed'])
        caps.assert_not_called()
        registry.assert_not_called()
        value.exact.verify.assert_called_once()

    def test_gate_failure_records_error_without_added_reads_or_retry(self):
        import settled
        destination = self.root.parent / 'fixed'
        bound = provenance.capture(self.root, destination, self.observation, self.expected, self.required)
        (destination / 'upload-1/payload.bin').write_bytes(b'replaced')
        value = settled.SettledObservation.__new__(settled.SettledObservation)
        value.c, value.out, value.result = dict(required_publication=self.required), self.root.parent, {}
        value.save = Mock()
        value.exact = Mock(expected=dict(self.expected, files=bound,
            provenance=dict(root=str(destination), observation=str(destination / 'observation.json'))))
        with patch.object(settled, 'current_capability') as caps, \
             patch.object(settled.rt, 'registry') as registry:
            with self.assertRaises(settled.rt.Failure) as raised:
                value.publication_gate()
        self.assertEqual(raised.exception.status, 'DATA_ERROR')
        self.assertFalse(value.result['required_publication']['passed'])
        caps.assert_not_called()
        registry.assert_not_called()
        value.exact.verify.assert_called_once()

    def test_existing_fixed_read_is_bracketed_without_another_observation(self):
        import settled
        folder = self.root.parent / 'fixed'
        shutil.copytree(self.root, self.root.parent / 'provenance')
        value = settled.SettledObservation.__new__(settled.SettledObservation)
        value.c, value.out, value.result = dict(required_publication=self.required), self.root.parent, {}
        value.args = SimpleNamespace(writer_entries=[0x1000])
        value.daemon = SimpleNamespace(daemon=SimpleNamespace(pid=101))
        value.admit_images, value.save = Mock(), Mock()
        exact = SimpleNamespace(expected=dict(self.expected, files={}),
                                path=folder / 'execution-session.json', verify=Mock())
        value.owner = SimpleNamespace(model=None, files={}, session_receipt=Mock(return_value=exact))
        with patch.object(settled.rt, 'children', return_value=[]), \
             patch.object(settled.rt, 'status', return_value=dict(state=0, frames=0, writers=1)), \
             patch.object(settled.rt, 'registry', return_value=[self.row]) as registry, \
             patch.object(settled.bench.execution, 'ready_writer_entries'), \
             patch.object(settled.bench.execution, 'ExecutionSession', return_value=exact) as receipt, \
             patch.object(settled.time, 'monotonic_ns', side_effect=[200, 210]):
            value.fixed_receipt(folder, dict(registry_after=[self.row]))
        registry.assert_called_once()
        exact.verify.assert_called_once()
        receipt.assert_called_once()
        saved = json.loads(exact.path.read_bytes())
        self.assertIn(str(folder / 'provenance/association.json'), saved['files'])

    def test_real_compiler_recorder_schema_links_without_a_compiler_or_provider(self):
        for version in (21, 22):
            with self.subTest(version=version):
                self.recorded_chain(version)

    def recorded_chain(self, version):
        sys.path.insert(0, str(ROOT / 'disassem'))
        import compiler_manifest as cm
        if version == 22:
            self.batch()
        for path in self.compile_dir.iterdir():
            if path.name != 'context.json':
                path.unlink()
        workspace = self.root.parent / 'workspace'
        workspace.mkdir(exist_ok=True)
        (workspace / 'jit.S').write_bytes(self.assembly)
        (workspace / 'jit.bin').write_bytes(self.payload)
        metadata = SimpleNamespace(st_dev=11, st_ino=22, st_rdev=33, st_mode=0o20600)
        parsed = dict(source_frontier_direction=True, mutex_images=True, mutex_exclusive=True)
        features = self.manifest['capabilities']['features']
        with patch.dict(os.environ, KD_PROVENANCE_ATTEMPT_DIR=str(self.compile_dir)), \
             patch.object(cm, '_recorder', None), patch.object(cm, '_directory', None), \
             patch.object(cm, '_start_ticks', side_effect=lambda pid: 1001 if pid == 101 else 1002), \
             patch.object(cm, '_interpreter', return_value=self.manifest['compiler']['interpreter']), \
             patch.object(cm.os, 'getpid', return_value=102), \
             patch.object(cm.os, 'getppid', return_value=101), \
             patch.object(cm.os, 'fstat', return_value=metadata), \
             patch.object(cm.fcntl, 'fcntl', return_value=os.O_RDWR):
            cm.capture('translation', **self.manifest['translation'])
            cm.capture('descriptor', fd=5, inherited_fd=4, inherited=True,
                       opened=metadata, named=metadata, source_info=dict(state=0))
            cm.capture('capabilities', fd=5, raw=struct.pack('<IIII', version, features, 0, 8192),
                       result=0, validated=True, parsed=parsed)
            cm.capture('service_table', mode='paged', generation=0, slots=0, active=0,
                       before=b'0 0 0\n', after=b'0 0 0\n', pages=[b''] * 8, raw=b'', parsed={})
            cm.capture('controls', mode='read', raw=b'', parsed={})
            for name, raw in (('callee_table.txt', b'0x2000\n'), ('ij_table.txt', b'')):
                cm.capture('history', name=name, state='read', text=raw.decode(), raw=raw)
            cm.capture_assembly(workspace / 'jit.S')
            cm.complete(workspace / 'jit.bin', {})
        self.upload['manifest_sha256'] = (self.compile_dir / 'manifest.sha256').read_text().strip()
        write_json(self.root / 'upload-1/receipt.json', self.upload)
        if version == 22:
            self.upload_context()
        self.assertEqual(self.verify()[0]['upload_id'], 1)


if __name__ == '__main__':
    unittest.main()
