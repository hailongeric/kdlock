"""VM-only production-excerpt checks for native rwsem fast reader credits."""
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
RW_FUNCTIONS = ('kd_rw_read_credit_init', 'rw_context', 'prepare_credit', 'credit_matches',
                'rw_progress', 'kd_rw_read_acquire', 'kd_rw_read_release', 'kd_rw_last_owned_read',
                'kd_rw_fast_read_init', 'kd_rw_fast_read_trylock', 'kd_rw_fast_read_is_last',
                'kd_rw_fast_read_release')
LINUX_FUNCTIONS = ('fast_read_grant', 'kd_linux_rwsem_source_release',
                   'kd_linux_rwsem_prepare_up_read_current', 'kd_linux_rwsem_up_read')
TYPES = {'kernel/rw.h': ('enum kd_rw_read_kind', 'struct kd_rw_read_link', 'struct kd_rw',
                        'struct kd_rwsem', 'struct kd_rw_read_credit', 'struct kd_rw_wait_ops'),
         'kernel/observation.h': ('enum kd_observation_kind', 'struct kd_observation')}


class RwsemFastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config_path = os.environ.get('KDLOCK_RWSEM_FAST_TEST_CONFIG')
        if not config_path:
            raise RuntimeError('KDLOCK_RWSEM_FAST_TEST_CONFIG is required; VM execution only')
        config = json.loads(Path(config_path).read_text())
        if platform.release() != config['expected_release']:
            raise RuntimeError('running kernel differs from the supplied VM release')
        parent, compiler = Path(config['scratch_parent']), Path(config['compiler'])
        if not parent.is_absolute() or not parent.is_dir() or not compiler.is_absolute() or not compiler.is_file():
            raise ValueError('supply existing absolute VM scratch and compiler paths')
        cls.output = Path(tempfile.mkdtemp(prefix='rwsem-fast-', dir=parent))
        inputs = {}
        def source(name):
            data = (ROOT / name).read_bytes()
            inputs[name] = hashlib.sha256(data).hexdigest()
            return data.decode()
        for name, functions, output in (('kernel/rw.c', RW_FUNCTIONS, 'read_functions.h'),
                                        ('kernel/linux_rwsem.c', LINUX_FUNCTIONS, 'linux_functions.h')):
            text, excerpts = source(name), []
            for function in functions:
                match = re.search(r'^(?:static )?(?:void|int|bool|enum \w+|struct \w+\s*\*)\s*'
                                  + function + r'\(', text, re.M)
                if match is None:
                    raise ValueError('missing production function ' + function)
                excerpts.append(text[match.start():text.index('\n}', match.start()) + 2])
            (cls.output / output).write_text('\n'.join(excerpts) + '\n')
        types = []
        for name, names in TYPES.items():
            text = source(name)
            for kind in names:
                match = re.search(r'^' + kind + r' \{.*?};', text, re.M | re.S)
                if match is None:
                    raise ValueError('missing production type ' + kind)
                types.append(match.group())
            if name == 'kernel/observation.h':
                types.extend(re.findall(r'^#define KD_OBS_FLAG_.*$', text, re.M))
        (cls.output / 'read_types.h').write_text('\n'.join(types) + '\n')
        fixture = 'tests/rwsem_fast/read_check.c'
        (cls.output / 'read_check.c').write_text(source(fixture))
        cls.binary = cls.output / 'read_check'
        command = [str(compiler), '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
                   str(cls.output / 'read_check.c'), '-o', str(cls.binary)]
        receipt = dict(command=command, release=platform.release(), inputs=inputs)
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

    def test_concurrent_credits_and_reuse_without_wait_setup(self):
        self.check_case('credits')

    def test_writer_states_decline_before_slow_acquisition(self):
        self.check_case('fallback')

    def test_arriving_writer_waits_for_the_exact_fast_credit(self):
        self.check_case('writer')

    def test_latest_managed_native_and_nonowner_credit_routing(self):
        self.check_case('routing')

    def test_final_object_access_precedes_done_and_record_reuse(self):
        self.check_case('final')


if __name__ == '__main__':
    unittest.main()
