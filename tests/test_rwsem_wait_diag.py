"""VM-only production-excerpt checks for temporary wait accounting.

Controlled wait/scheduler endpoints verify helper ordering and storage access;
these are not actual scheduler, kernel cancellation, or performance evidence.
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


class RwsemWaitDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        name = os.environ.get('KDLOCK_RWSEM_WAIT_DIAG_TEST_CONFIG')
        if not name:
            raise RuntimeError('KDLOCK_RWSEM_WAIT_DIAG_TEST_CONFIG is required; VM execution only')
        config = json.loads(Path(name).read_text())
        if platform.release() != config['expected_release']:
            raise RuntimeError('VM release differs')
        parent, compiler = Path(config['scratch_parent']), Path(config['compiler'])
        if not parent.is_absolute() or not parent.is_dir() or not compiler.is_absolute() or not compiler.is_file():
            raise ValueError('supply existing absolute VM scratch and compiler paths')
        cls.output = Path(tempfile.mkdtemp(prefix='rwsem-wait-diag-', dir=parent))
        inputs = {}

        def source(path):
            data = (ROOT / path).read_bytes()
            inputs[path] = hashlib.sha256(data).hexdigest()
            return data.decode()

        body = source('kernel/rw_wait_diag.c')
        (cls.output / 'diag_functions.h').write_text(body[body.index('struct kd_rw_wait_diag_wake_batch {'):])
        header = source('kernel/rw_wait_diag.h')
        row = re.search(r'struct kd_rw_wait_diag_row \{.*?\} __aligned\(128\);', header, re.S)
        if row is None:
            raise ValueError('production row missing')
        (cls.output / 'diag_row.h').write_text(row.group())
        (cls.output / 'kd_rw_wait_diag.h').write_text(source('include/kd_rw_wait_diag.h'))
        (cls.output / 'diag_check.c').write_text(source('tests/rwsem_wait_diag/diag_check.c'))
        cls.binary = cls.output / 'diag_check'
        command = [str(compiler), '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                   str(cls.output / 'diag_check.c'), '-o', str(cls.binary)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        (cls.output / 'build.json').write_text(json.dumps(dict(command=command, inputs=inputs,
            release=platform.release(), returncode=result.returncode), indent=2) + '\n')
        (cls.output / 'build.stdout').write_text(result.stdout)
        (cls.output / 'build.stderr').write_text(result.stderr)
        if result.returncode:
            raise RuntimeError(f'focused build failed; receipts: {cls.output}')

    def check_case(self, name):
        command = [str(self.binary), name]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        (self.output / (name + '.json')).write_text(json.dumps(dict(command=command,
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2) + '\n')
        self.assertEqual(result.returncode, 0, f'{name}: {result.stderr}; receipts: {self.output}')
        self.assertEqual(result.stdout, f'PASS {name}\n')

    def test_registration_categories_under_existing_queue_lock(self): self.check_case('registration')
    def test_waker_counts_read_write_visits_and_acceptance(self): self.check_case('callbacks')
    def test_no_waiter_access_after_autoremove_returns(self): self.check_case('final_callback')
    def test_disabled_helper_keeps_original_callbacks(self): self.check_case('disabled')
    def test_finished_wait_entry_gets_no_late_callback(self): self.check_case('cancel_cleanup')


if __name__ == '__main__':
    unittest.main()
