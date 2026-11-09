"""VM-only execution of the shared MM frozen-source admission code."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('mm_private_source_fixture',
                                            ROOT/'bench/mmap_fault/mm_platform.py')
platform = importlib.util.module_from_spec(spec)
spec.loader.exec_module(platform)


class PrivateSource(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.geteuid(), 0, 'this fixture runs only as root in the development VM')
        self.assertIn(os.uname().release, ('7.0.0-38-kdlock1', '7.0.0-38-kdmm1',
                      '7.0.0-38-kdscope1', '7.0.0-38-kdscope3',
                      '7.0.0-38-kdscope4', '7.0.0-38-kdscope5'))
        platform.PRIVATE_ROOTS.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='mm-source-fixture-',
                                                     dir=platform.PRIVATE_ROOTS)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root/'code').mkdir()
        (self.root/'code/entry.py').write_bytes(b'fixture = 1\n')
        (self.root/'README').write_bytes(b'Fixture bytes only.\n')
        self.manifest = {name: hashlib.sha256((self.root/name).read_bytes()).hexdigest()
                         for name in ('code/entry.py', 'README')}
        self.state = dict(git_head='a'*40, git_status='', omitted_missing_tracked_paths=[],
                          files=len(self.manifest), transfer_bytes=sum(
                              (self.root/name).stat().st_size for name in self.manifest))
        self.write_receipts()

    def write_receipts(self):
        (self.root/'source-state.json').write_text(json.dumps(self.state, sort_keys=True)+'\n')
        (self.root/'source-sha256.json').write_text(json.dumps(self.manifest, sort_keys=True)+'\n')
        self.hashes = dict(state_sha256=hashlib.sha256(
            (self.root/'source-state.json').read_bytes()).hexdigest(),
            manifest_sha256=hashlib.sha256((self.root/'source-sha256.json').read_bytes()).hexdigest())

    def admit(self):
        return platform.source_identity(self.root, **self.hashes)

    def test_canonical_route_is_unchanged(self):
        self.assertEqual(platform.source_identity(platform.CANONICAL_ROOT),
                         dict(root=str(platform.CANONICAL_ROOT), route='canonical'))

    def test_exact_private_copy_returns_separate_source_provenance(self):
        identity = self.admit()
        self.assertEqual(identity['route'], 'private-frozen')
        self.assertEqual(identity['git_head'], self.state['git_head'])
        self.assertEqual(identity['files'], 2)
        self.assertEqual(identity['transfer_bytes'], self.state['transfer_bytes'])
        self.assertEqual(identity['filesystem'], 'ext4')
        self.assertEqual(identity['source_state_sha256'], self.hashes['state_sha256'])
        self.assertEqual(identity['source_manifest_sha256'], self.hashes['manifest_sha256'])

    def test_wrong_prefix_and_nested_private_root_are_refused(self):
        for root in (Path('/tmp/kdlock-inputs/candidate'), self.root/'nested',
                     Path('/root/kdlock-inputs-extra/candidate')):
            with self.subTest(root=root), self.assertRaises(ValueError):
                platform.source_identity(root, **self.hashes)

    def test_clean_commit_and_exact_totals_are_required(self):
        original = copy.deepcopy(self.state)
        for field, value in (('git_head', 'not-a-commit'), ('git_status', ' M entry.py\n'),
                             ('omitted_missing_tracked_paths', ['missing.c']),
                             ('files', True), ('files', 3), ('transfer_bytes', -1),
                             ('transfer_bytes', self.state['transfer_bytes']+1)):
            self.state = dict(original, **{field: value})
            self.write_receipts()
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.admit()

    def test_external_hashes_are_required_and_rechecked(self):
        for field in ('state_sha256', 'manifest_sha256'):
            supplied = dict(self.hashes, **{field: '0'*64})
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'SHA256 differs'):
                platform.source_identity(self.root, **supplied)
        with self.assertRaisesRegex(ValueError, 'explicit frozen source'):
            platform.source_identity(self.root, state_sha256='wrong', manifest_sha256='wrong')

    def test_changed_file_missing_file_and_extra_file_are_refused(self):
        path = self.root/'code/entry.py'
        original = path.read_bytes()
        path.write_bytes(original.replace(b'1', b'2'))
        with self.assertRaisesRegex(ValueError, 'file SHA256 differs'):
            self.admit()
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'file set or byte count differs'):
            self.admit()
        path.write_bytes(original)
        (self.root/'extra').write_text('unlisted')
        with self.assertRaisesRegex(ValueError, 'unlisted private source file'):
            self.admit()

    def test_symlink_and_missing_receipt_are_refused(self):
        path = self.root/'code/entry.py'
        path.unlink()
        path.symlink_to('/dev/null')
        with self.assertRaisesRegex(ValueError, 'not a regular file'):
            self.admit()
        path.unlink()
        (self.root/'source-state.json').unlink()
        with self.assertRaises((OSError, ValueError)):
            self.admit()

    def test_manifest_rows_and_duplicate_receipt_keys_are_refused(self):
        for name in ('../entry.py', '/entry.py', 'code/./entry.py', 'source-state.json'):
            self.manifest = {name: 'a'*64}
            self.state['files'] = 1
            self.write_receipts()
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'manifest row differs'):
                self.admit()
        with self.assertRaisesRegex(ValueError, 'duplicate source receipt key'):
            platform._source_json(b'{"files":1,"files":2}')

    def test_private_leaf_nested_mount_and_other_filesystem_are_refused(self):
        base = '1 0 8:1 / / rw - ext4 /dev/vda1 rw\n'
        for text in (base+f'2 1 8:1 / {self.root} rw - ext4 /dev/vda1 rw\n',
                     base+f'2 1 8:1 / {self.root}/nested rw - ext4 /dev/vda1 rw\n',
                     '1 0 8:1 / / rw - tmpfs tmpfs rw\n'):
            with self.subTest(mountinfo=text), self.assertRaises(ValueError):
                platform._private_filesystem(self.root, text)


if __name__ == '__main__':
    unittest.main()
