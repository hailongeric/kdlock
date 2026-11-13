"""VM-only production-excerpt checks for the single ordinary-read bridge.

Controlled image, entry and physical-release endpoints exercise exact transfer
and rollback. These checks do not replace live MCS or generated-path evidence.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = {
    'kernel/rw.c': ('kd_rw_read_link_init', 'kd_rw_read_link_task', 'kd_rw_read_unlink_task',
        'kd_rw_read_credit_init', 'rw_context', 'credit_matches', 'kd_rw_read_credit_check',
        'kd_rw_read_credit_unlink', 'kd_rw_read_release', 'kd_rw_last_owned_read'),
    'kernel/state.c': ('kd_source_grant_init', 'grant_modes_valid', 'kd_state_link_grant',
        'kd_state_find_grant_typed', 'kd_state_find_operation_grant',
        'kd_state_close_grant', 'kd_state_unlink_grant'),
    'kernel/rw_admission.c': ('admission', 'kd_rw_admission_read_try', 'kd_rw_admission_write_try'),
    'kernel/rw_local.c': ('kd_rw_local_init', 'reserve_local', 'link_local', 'free_local',
        'observe_local', 'kd_rw_local_done', 'kd_rw_local_read_lock', 'kd_rw_local_write_try',
        'kd_rw_local_write_lock', 'kd_rw_local_read_release', 'kd_rw_local_read_candidate',
        'drop_promoted_read', 'kd_rw_local_read_promoted', 'kd_rw_local_read_rollback',
        'kd_rw_local_read_promote', 'kd_rw_local_read_commit', 'kd_rw_local_read_release_promoted'),
    'kernel/mutex_api.c': ('prepare_rwsem_read_bridge', 'prepare_rwsem_writer'),
}
TYPES = {
    'kernel/state.h': ('enum kd_lock_family', 'enum kd_grant_mode', 'enum kd_grant_physical',
        'enum kd_operation_kind', 'struct kd_source_grant'),
    'kernel/mutex_release.h': ('enum kd_mutex_unlock_phase', 'enum kd_mutex_unlock_route'),
    'kernel/rw.h': ('enum kd_rw_read_kind', 'struct kd_rw_read_link', 'struct kd_rw',
        'struct kd_rwsem', 'struct kd_rw_read_credit'),
    'kernel/rw_native.h': ('enum kd_rw_native_phase', 'struct kd_rw_native_record', 'struct kd_rw_native_pool'),
    'kernel/rw_local.h': ('struct kd_rw_local',),
    'kernel/observation.h': ('enum kd_observation_kind', 'struct kd_observation'),
}


class RwsemReadBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get('KDLOCK_RWSEM_READ_BRIDGE_TEST_CONFIG')
        if not path:
            raise RuntimeError('KDLOCK_RWSEM_READ_BRIDGE_TEST_CONFIG is required; VM execution only')
        config = json.loads(Path(path).read_text())
        if platform.release() != config['expected_release']:
            raise RuntimeError('running kernel differs from the supplied VM release')
        parent, compiler = Path(config['scratch_parent']), Path(config['compiler'])
        if not parent.is_absolute() or not parent.is_dir() or not compiler.is_absolute() or not compiler.is_file():
            raise ValueError('supply existing absolute VM scratch and compiler paths')
        cls.output = Path(tempfile.mkdtemp(prefix='rwsem-read-bridge-', dir=parent))
        inputs = {}
        def source(name):
            raw = (ROOT / name).read_bytes()
            inputs[name] = hashlib.sha256(raw).hexdigest()
            return raw.decode()
        types = []
        for name, names in TYPES.items():
            text = source(name)
            for kind in names:
                match = re.search(r'^' + kind + r' \{', text, re.M)
                if not match:
                    raise ValueError('missing production type ' + kind)
                depth = 0
                for end in range(text.index('{', match.start()), len(text)):
                    depth += (text[end] == '{') - (text[end] == '}')
                    if not depth:
                        if text[end:end + 2] != '};':
                            raise ValueError('unterminated production type ' + kind)
                        types.append(text[match.start():end + 2])
                        break
            if name == 'kernel/observation.h':
                types.extend(re.findall(r'^#define KD_OBS_FLAG_.*$', text, re.M))
        types.extend(re.findall(r'^#define KD_RW_ADMIT_.*$', source('kernel/rw_admission.h'), re.M))
        (cls.output / 'types.h').write_text('\n'.join(types) + '\n')
        for name, functions in FUNCTIONS.items():
            text, excerpts = source(name), []
            for function in functions:
                match = re.search(r'^(?:static )?(?:void|int|bool|unsigned long|enum \w+|struct \w+\s*\*)\s*'
                    + function + r'\(', text, re.M)
                if not match:
                    raise ValueError('missing production function ' + function)
                excerpts.append(text[match.start():text.index('\n}', match.start()) + 2])
            (cls.output / (Path(name).stem + '_functions.h')).write_text('\n'.join(excerpts) + '\n')
        fixture = 'tests/rwsem_read_bridge/bridge_check.c'
        (cls.output / 'bridge_check.c').write_text(source(fixture))
        cls.binary = cls.output / 'bridge_check'
        command = [str(compiler), '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
            str(cls.output / 'bridge_check.c'), '-o', str(cls.binary)]
        receipt = dict(command=command, release=platform.release(), inputs=inputs, functions=FUNCTIONS)
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        (cls.output / 'build.stdout').write_text(result.stdout)
        (cls.output / 'build.stderr').write_text(result.stderr)
        receipt['returncode'] = result.returncode
        (cls.output / 'build.json').write_text(json.dumps(receipt, indent=2) + '\n')
        if result.returncode:
            raise RuntimeError(f'focused C build failed; retained output: {cls.output}')

    def check_case(self, name):
        command = [str(self.binary), name]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        (self.output / f'{name}.json').write_text(json.dumps(dict(command=command,
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2) + '\n')
        self.assertEqual(result.returncode, 0, f'{name}: {result.stderr}; receipts: {self.output}')
        self.assertEqual(result.stdout, f'PASS {name}\n')

    def test_fast_read_keeps_its_original_acquisition_and_physical_charge(self):
        self.check_case('fast')

    def test_slow_read_uses_the_same_writer_boundary_bridge(self):
        self.check_case('slow')

    def test_repeated_callable_downgraded_and_same_object_reads_stay_local(self):
        self.check_case('scope')

    def test_disabled_delegation_absent_image_and_uncontended_write_do_not_promote(self):
        self.check_case('ineligible')

    def test_frame_image_and_auxiliary_preparation_failures_restore_the_read(self):
        self.check_case('rollback')

    def test_foreign_release_is_refused_and_native_release_occurs_once(self):
        self.check_case('owner')

    def test_final_object_access_precedes_completion_and_record_reuse(self):
        self.check_case('final')


if __name__ == '__main__':
    unittest.main()
