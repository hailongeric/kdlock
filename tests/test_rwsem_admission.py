"""VM-only checks of the production atomic admission and slow-wait functions."""
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


class RwsemAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get('KDLOCK_RWSEM_ADMISSION_TEST_CONFIG')
        if not path:
            raise RuntimeError('KDLOCK_RWSEM_ADMISSION_TEST_CONFIG is required; VM execution only')
        config = json.loads(Path(path).read_text())
        if platform.release() != config['expected_release']:
            raise RuntimeError('running kernel differs from supplied VM identity')
        parent, compiler = Path(config['scratch_parent']), Path(config['compiler'])
        if not parent.is_absolute() or not parent.is_dir() or not compiler.is_absolute() or not compiler.is_file():
            raise ValueError('supply existing absolute VM scratch and compiler paths')
        cls.output = Path(tempfile.mkdtemp(prefix='rwsem-admission-', dir=parent))
        inputs = {}

        def source(name):
            data = (ROOT / name).read_bytes()
            inputs[name] = hashlib.sha256(data).hexdigest()
            return data.decode()

        text = source('kernel/rw.h')
        types = []
        for kind in ('struct kd_rw', 'struct kd_rw_wait_ops'):
            match = re.search(r'^' + kind + r' \{.*?^};', text, re.M | re.S)
            if match is None:
                raise ValueError('missing production type ' + kind)
            types.append(match.group())
        header = source('kernel/rw_admission.h')
        definitions = re.findall(r'^#define KD_RW_ADMIT_.*$', header, re.M)
        declarations = header[header.index('bool kd_rw_admission_read_try'):header.rindex('#endif')]
        (cls.output / 'admission_types.h').write_text('\n'.join(types + definitions) + '\n' + declarations)
        functions = re.sub(r'^#include .*\n', '', source('kernel/rw_admission.c'), flags=re.M)
        (cls.output / 'admission_functions.h').write_text(functions)
        (cls.output / 'admission_check.c').write_text(source('tests/rwsem_admission/admission_check.c'))
        cls.binary = cls.output / 'admission_check'
        command = [str(compiler), '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
                   str(cls.output / 'admission_check.c'), '-o', str(cls.binary)]
        receipt = dict(command=command, release=platform.release(), inputs=inputs)
        (cls.output / 'build.json').write_text(json.dumps(receipt, indent=2) + '\n')
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        (cls.output / 'build.stdout').write_text(result.stdout)
        (cls.output / 'build.stderr').write_text(result.stderr)
        receipt['returncode'] = result.returncode
        (cls.output / 'build.json').write_text(json.dumps(receipt, indent=2) + '\n')
        if result.returncode:
            raise RuntimeError(f'focused C build failed; receipts: {cls.output}')

    def check_case(self, name):
        command = [str(self.binary), name]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        (self.output / f'{name}.json').write_text(json.dumps(dict(command=command,
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2) + '\n')
        self.assertEqual(result.returncode, 0, f'{name}: {result.stderr}; receipts: {self.output}')
        self.assertEqual(result.stdout, f'PASS {name}\n')

    def test_uncontended_atomic_admission_without_family_guard(self): self.check_case('fast')
    def test_release_between_failed_read_and_wait_publication(self): self.check_case('publish_recheck')
    def test_waiting_reader_phase_precedes_next_writer(self): self.check_case('reader_phase')
    def test_cancelled_read_removes_exact_wait_charge(self): self.check_case('cancel_read')
    def test_last_cancelled_writer_reopens_reader_admission(self): self.check_case('cancel_queue')
    def test_downgrade_is_continuously_read_owned(self): self.check_case('downgrade')
    def test_final_atomic_access_precedes_object_reuse(self): self.check_case('final')
    def test_field_bounds_fail_before_cross_field_carry(self): self.check_case('bounds')


if __name__ == '__main__':
    unittest.main()
