"""VM-only production-excerpt spin batch checks; no live JIT/scheduler claim."""
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
    'kernel/mutex_release.c': ('observe_release', 'release_lock', 'kd_mutex_release_owner_init',
        'kd_mutex_release_bind', 'kd_mutex_release_request', 'kd_mutex_release_owner_handle',
        'kd_mutex_release_hold_return', 'kd_mutex_release_drop_return', 'kd_mutex_release_drop_source',
        'prepare_physical', 'mark_physical', 'kd_mutex_release_finish_physical',
        'kd_mutex_release_retire', 'kd_mutex_release_owner_retire'),
    'kernel/mutex_api.c': ('new_spin_policy_epoch', 'kd_spin_policy_epoch', 'kd_spin_init'),
    'kernel/mutex.c': ('node_observation_flags', 'observe_node', 'publish_condition',
        'link_request', 'detach_proxy', 'release_phase', 'bind_grant', 'start_batch', 'spin_batch_offer',
        'spin_serve_batch', 'spin_source_unlock', 'kd_mutex_finish_batch',
        'publish_retirable', 'kd_mutex_reap_batch'),
    'kernel/owner_progress.c': ('finish_ready_locked',),
}
TYPES = {
    'kernel/mutex_release.h': ('enum kd_mutex_owner_phase', 'enum kd_mutex_unlock_route',
        'enum kd_mutex_unlock_phase', 'struct kd_mutex_release_owner', 'struct kd_mutex_release'),
    'kernel/mutex.h': ('enum kd_mutex_selection', 'enum kd_mutex_outcome',
        'enum kd_mutex_unlock_action', 'enum kd_mutex_service_policy', 'struct kd_mutex_batch'),
    'kernel/observation.h': ('enum kd_observation_kind', 'struct kd_observation'),
}
CASES = ('zero', 'one', 'two', 'cap', 'second_ineligible', 'later_hole', 'miss', 'nested',
         'reacquire', 'proxy_off', 'cap_one', 'retirement', 'policy', 'light', 'not_due', 'accounting', 'head_hole', 'epoch')


def extract_definition(text, symbol):
    """Select a file-scope definition, excluding forward declarations/calls."""
    pattern = (r"^[A-Za-z_][\w *]*\b" + re.escape(symbol)
               + r"\([^;{}]*\)\s*\n\{")
    matches = list(re.finditer(pattern, text, re.M))
    if len(matches) != 1:
        raise ValueError(f"expected one definition of {symbol}, found {len(matches)}")
    match = matches[0]
    # These production excerpts use file-scope closing braces in column zero.
    return text[match.start():text.index("\n}", match.end()) + 2]


class ExtractorTests(unittest.TestCase):
    def test_forward_declaration_is_not_a_definition(self):
        source = ("static void detach_proxy(struct batch *b, struct node *n);\n"
                  "static void unrelated(void)\n{\n}\n"
                  "static void detach_proxy(struct batch *b, struct node *n)\n"
                  "{\n    consume(b, n);\n}\n")
        self.assertEqual(extract_definition(source, "detach_proxy"),
                         source[source.rindex("static void detach_proxy"):].rstrip())
        with self.assertRaises(ValueError):
            extract_definition(source.split("static void unrelated")[0], "detach_proxy")


class SpinBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get('KDLOCK_SPIN_BATCH_TEST_CONFIG')
        if not path:
            raise RuntimeError('KDLOCK_SPIN_BATCH_TEST_CONFIG required; VM execution only')
        config = json.loads(Path(path).read_text())
        if platform.release() != config['expected_release']:
            raise RuntimeError('VM release differs')
        parent, compiler = Path(config['scratch_parent']), Path(config['compiler'])
        if not parent.is_absolute() or not parent.is_dir() or not compiler.is_absolute() or not compiler.is_file():
            raise ValueError('existing absolute VM scratch and compiler paths required')
        cls.output = Path(tempfile.mkdtemp(prefix='spin-batch-', dir=parent))
        inputs, functions, types = {}, [], []
        for name in dict.fromkeys((*TYPES, *FUNCTIONS)):
            data = (ROOT / name).read_bytes()
            inputs[name] = hashlib.sha256(data).hexdigest()
            text = data.decode()
            for symbol in TYPES.get(name, ()):
                match = re.search(r'^' + symbol + r' \{.*?^};', text, re.M | re.S)
                if match is None:
                    raise ValueError('missing type ' + symbol)
                types.append(match.group())
            if name == 'kernel/observation.h':
                types += re.findall(r'^#define KD_OBS_FLAG_.*$', text, re.M)
            for symbol in FUNCTIONS.get(name, ()):
                functions.append(extract_definition(text, symbol))
        (cls.output / 'batch_types.h').write_text('\n'.join(types) + '\n')
        (cls.output / 'batch_functions.h').write_text('\n'.join(functions) + '\n')
        policy = (ROOT / 'kernel/spin_policy.h').read_bytes()
        inputs['kernel/spin_policy.h'] = hashlib.sha256(policy).hexdigest()
        (cls.output / 'spin_policy.h').write_bytes(policy)
        fixture = (ROOT / 'tests/spin_batch/batch_check.c').read_bytes()
        inputs['tests/spin_batch/batch_check.c'] = hashlib.sha256(fixture).hexdigest()
        (cls.output / 'batch_check.c').write_bytes(fixture)
        cls.binary = cls.output / 'batch_check'
        command = [str(compiler), '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                   str(cls.output / 'batch_check.c'), '-o', str(cls.binary)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        (cls.output / 'build.json').write_text(json.dumps(dict(command=command, inputs=inputs,
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2) + '\n')
        if result.returncode:
            raise RuntimeError(f'focused compilation failed; receipts: {cls.output}')

    def test_continuous_ownership_and_independent_retirement(self):
        for case in CASES:
            with self.subTest(case=case):
                command = [str(self.binary), case]
                result = subprocess.run(command, capture_output=True, text=True, timeout=10)
                (self.output / (case + '.json')).write_text(json.dumps(dict(command=command,
                    returncode=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2) + '\n')
                self.assertEqual(result.returncode, 0, f'{result.stderr}; receipts: {self.output}')
                self.assertEqual(result.stdout, f'PASS {case}\n')


if __name__ == '__main__':
    unittest.main()
