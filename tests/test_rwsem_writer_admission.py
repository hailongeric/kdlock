"""VM-only production-excerpt checks for the first rwsem writer admission.

Controlled wait/progress endpoints exercise boundary ordering. They do not
replace live MCS, scheduler, source-continuation or retirement checks.
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
FUNCTIONS = ('kd_rw_read_credit_init', 'rw_context', 'credit_matches',
             'kd_rw_read_release', 'kd_rw_fast_read_init', 'kd_rw_fast_read_trylock',
             'note_candidate_cancel', 'kd_rw_writer_enter', 'kd_rw_write_grant',
             'kd_rw_writer_exit')
TYPES = {'kernel/mutex.h': ('enum kd_mutex_admission',),
         'kernel/rw.h': ('enum kd_rw_read_kind', 'struct kd_rw_read_link',
                         'struct kd_rw', 'struct kd_rw_read_credit'),
         'kernel/observation.h': ('enum kd_observation_kind', 'struct kd_observation')}


class RwsemWriterAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config_path = os.environ.get('KDLOCK_RWSEM_WRITER_ADMISSION_TEST_CONFIG')
        if not config_path:
            raise RuntimeError('KDLOCK_RWSEM_WRITER_ADMISSION_TEST_CONFIG is required; VM execution only')
        config = json.loads(Path(config_path).read_text())
        if platform.release() != config['expected_release']:
            raise RuntimeError('running kernel differs from the supplied VM release')
        parent, compiler = Path(config['scratch_parent']), Path(config['compiler'])
        if not parent.is_absolute() or not parent.is_dir() or not compiler.is_absolute() or not compiler.is_file():
            raise ValueError('supply existing absolute VM scratch and compiler paths')
        cls.output = Path(tempfile.mkdtemp(prefix='rwsem-writer-admission-', dir=parent))
        inputs = {}

        def source(name):
            data = (ROOT / name).read_bytes()
            inputs[name] = hashlib.sha256(data).hexdigest()
            return data.decode()

        text, excerpts = source('kernel/rw.c'), []
        for name in FUNCTIONS:
            match = re.search(r'^(?:static )?(?:void|int|bool)\s*' + name + r'\(', text, re.M)
            if match is None:
                raise ValueError('missing production function ' + name)
            excerpts.append(text[match.start():text.index('\n}', match.start()) + 2])
        (cls.output / 'writer_functions.h').write_text('\n'.join(excerpts) + '\n')
        types = []
        for name, names in TYPES.items():
            text = source(name)
            for kind in names:
                match = re.search(r'^' + kind + r' \{.*?^};', text, re.M | re.S)
                if match is None:
                    raise ValueError('missing production type ' + kind)
                types.append(match.group())
            if name == 'kernel/observation.h':
                types.extend(re.findall(r'^#define KD_OBS_FLAG_.*$', text, re.M))
        (cls.output / 'writer_types.h').write_text('\n'.join(types) + '\n')
        fixture = 'tests/rwsem_writer_admission/writer_check.c'
        (cls.output / 'writer_check.c').write_text(source(fixture))
        cls.binary = cls.output / 'writer_check'
        command = [str(compiler), '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                   str(cls.output / 'writer_check.c'), '-o', str(cls.binary)]
        receipt = dict(command=command, release=platform.release(), inputs=inputs, functions=FUNCTIONS)
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
        (self.output / f'{name}.json').write_text(json.dumps(dict(command=command,
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2) + '\n')
        self.assertEqual(result.returncode, 0, f'{name}: {result.stderr}; receipts: {self.output}')
        self.assertEqual(result.stdout, f'PASS {name}\n')

    def test_immediate_grant_retains_progress_without_wait_registration(self):
        self.check_case('immediate')

    def test_reader_drain_before_wait_registration_is_rechecked(self):
        self.check_case('drain_before_wait')

    def test_reader_drain_after_sleep_retains_registered_cleanup(self):
        self.check_case('drain_after_wait')

    def test_queued_successor_and_reader_admission_remain_separate(self):
        self.check_case('queued')

    def test_blocked_owner_progress_and_ready_retry_retain_cleanup(self):
        self.check_case('blocked')

    def test_killable_readiness_and_cancellation_keep_the_original_path(self):
        self.check_case('cancel')

    def test_cohort_candidate_keeps_signal_and_grant_checks(self):
        self.check_case('cohort')

    def test_nested_distinct_writers_retain_exact_outer_owner_and_state(self):
        self.check_case('nested')

    def test_native_downgrade_keeps_continuous_exact_reader_credit(self):
        self.check_case('downgrade')

    def test_atomic_writer_remains_on_its_existing_spin_path(self):
        self.check_case('atomic')

    def test_final_writer_object_access_precedes_return(self):
        self.check_case('final')


if __name__ == '__main__':
    unittest.main()
