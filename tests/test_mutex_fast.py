"""VM-only checks of production mutex fast-path and lifecycle excerpts.

The C stand-ins control queue publication, immediate reuse and task references.
They are bounded mechanism checks, separate from kernel builds and live cases.
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
    'kernel/native_status.h': ('kd_task_native_status',),
    'kernel/mutex.c': ('claim_offered', 'publish_condition', 'wait_link', 'kd_mutex_fast_init',
                       'record_fast', 'observe_fast', 'kd_mutex_fast_trylock', 'handoff_fast',
                       'kd_mutex_fast_unlock', 'kd_task_mutex_fast_root'),
    'kernel/rw_local.c': ('kd_rw_local_root',),
    'kernel/task_state.c': ('kd_task_root_context_current', 'kd_task_root_detach_unpublished',
                            'kd_task_root_detach', 'kd_task_root_revoke_cancelled'),
    'kernel/task_progress.c': ('kd_task_validate_native',),
}
TYPES = {
    'kernel/state.h': ('enum kd_execution_kind', 'enum kd_operation_kind', 'enum kd_operation_phase',
                      'enum kd_lock_family'),
    'kernel/mutex.h': ('enum kd_mutex_selection', 'struct kd_mutex', 'struct kd_mutex_fast'),
    'kernel/observation.h': ('enum kd_observation_kind', 'struct kd_observation'),
}
ENTRY_FUNCTIONS = {
    'kernel/state.h': ('kd_operation_is_lock', 'kd_operation_is_unlock', 'kd_operation_is_mode_change',
                       'kd_operation_family', 'kd_lock_family_is_atomic', 'kd_operation_is_atomic'),
    'kernel/mutex_api.c': ('prepare_current_with_image', 'prepare_current',
                           'kd_mutex_prepare_lock_slow', 'kd_mutex_prepare_unlock_slow'),
    'kernel/mutex.c': ('kd_mutex_prepare_lock_current', 'kd_mutex_prepare_unlock_current'),
}


class MutexFastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get('KDLOCK_MUTEX_FAST_TEST_CONFIG')
        if not path:
            raise RuntimeError('KDLOCK_MUTEX_FAST_TEST_CONFIG is required; VM execution only')
        config = json.loads(Path(path).read_text())
        if platform.release() != config['expected_release']:
            raise RuntimeError('running kernel differs from the explicit VM release')
        parent, compiler = Path(config['scratch_parent']), Path(config['compiler'])
        if not parent.is_absolute() or not parent.is_dir() or not compiler.is_absolute() or not compiler.is_file():
            raise ValueError('supply existing absolute VM scratch and compiler paths')
        cls.output = Path(tempfile.mkdtemp(prefix='mutex-fast-', dir=parent))
        inputs, functions, types, entry_functions = {}, [], [], {}
        for relative in dict.fromkeys((*FUNCTIONS, *TYPES, *ENTRY_FUNCTIONS)):
            raw = (ROOT / relative).read_bytes()
            inputs[relative] = hashlib.sha256(raw).hexdigest()
            source = raw.decode()
            for name in FUNCTIONS.get(relative, ()):
                match = re.search(r'^(?:static )?(?:(?:__always_inline|inline|noinline) )?(?:void|int|bool|unsigned long|struct \w+\s*\*)\s*'
                                  + name + r'\(', source, re.M)
                if match is None:
                    raise ValueError('missing production function ' + name)
                functions.append(source[match.start():source.index('\n}', match.start()) + 2])
            for name in ENTRY_FUNCTIONS.get(relative, ()):
                match = re.search(r'^(?:static )?(?:inline )?(?:void|int|bool|enum \w+|struct \w+\s*\*)\s*'
                                  + name + r'\(', source, re.M)
                if match is None:
                    raise ValueError('missing production entry function ' + name)
                entry_functions[name] = source[match.start():source.index('\n}', match.start()) + 2]
            for name in TYPES.get(relative, ()):
                match = re.search(r'^' + name + r' \{.*?^};', source, re.M | re.S)
                if match is None:
                    raise ValueError('missing production type ' + name)
                types.append(match.group())
            if relative == 'kernel/observation.h':
                types.extend(re.findall(r'^#define KD_OBS_FLAG_.*$', source, re.M))
        (cls.output / 'fast_functions.h').write_text('\n'.join(functions) + '\n')
        (cls.output / 'fast_types.h').write_text('\n'.join(types) + '\n')
        (cls.output / 'entry_functions.h').write_text('\n'.join(entry_functions[name]
            for names in ENTRY_FUNCTIONS.values() for name in names) + '\n')
        fixture = ROOT / 'tests/mutex_fast/fast_check.c'
        inputs[str(fixture.relative_to(ROOT))] = hashlib.sha256(fixture.read_bytes()).hexdigest()
        (cls.output / fixture.name).write_bytes(fixture.read_bytes())
        cls.binary = cls.output / 'fast_check'
        command = [str(compiler), '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
                   str(cls.output / fixture.name), '-o', str(cls.binary)]
        receipt = dict(command=command, release=platform.release(), inputs=inputs,
                       functions=FUNCTIONS, entry_functions=ENTRY_FUNCTIONS)
        (cls.output / 'build.json').write_text(json.dumps(receipt, indent=2) + '\n')
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
        (self.output / f'{name}.json').write_text(json.dumps(dict(
            command=command, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr),
            indent=2) + '\n')
        self.assertEqual(result.returncode, 0, f'{name}: {result.stderr}; receipts: {self.output}')
        self.assertEqual(result.stdout, f'PASS {name}\n')

    def test_empty_queue_release_and_same_record_reuse(self):
        self.check_case('reuse')

    def test_plain_spin_reuses_local_selection(self):
        self.check_case('spin_selection')

    def test_failed_claim_leaves_the_operation_and_queue_untouched(self):
        self.check_case('failed')

    def test_linked_waiter_can_retire_immediately_after_turn(self):
        self.check_case('linked')

    def test_tail_exchange_before_delayed_predecessor_link(self):
        self.check_case('delayed')

    def test_modes_context_and_retained_duties_decline_fast_entry(self):
        self.check_case('eligibility')

    def test_all_root_detach_routes_retain_a_held_fast_owner(self):
        self.check_case('lifetime')

    def test_shared_native_validation_retains_structural_checks(self):
        self.check_case('native_checks')

    def test_typed_mutex_enters_capture_only_after_failed_claim(self):
        self.check_case('typed_mutex')

    def test_retained_read_route_still_prepares_and_forwards_exact_image_use(self):
        self.check_case('read_fallback')

    def test_ordinary_rwsem_root_progresses_only_retained_duties(self):
        self.check_case('rwsem_root')


if __name__ == '__main__':
    unittest.main()
