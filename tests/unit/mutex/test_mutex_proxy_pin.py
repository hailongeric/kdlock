"""Guest-only production waiter pin protocol with deterministic scheduling hooks.

The extracted helpers must permit scheduling before selection and physical
acquisition, require an origin pin acknowledgement before proxy execution, and
return with exactly the caller's pin. This fixture is not a weak-memory proof
or a substitute for the live scheduler/preemption and JIT/drain checks.
"""
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source
from test_spin_shadow import definition


def main():
    source = read_source(ROOT / 'kernel_module/kd_mutex.c')
    code = '\n'.join(definition(source, signature) for signature in (
        'static void kd_mutex_wait_for_result(struct kd_mutex_node *node)',
        'static bool kd_mutex_proxy_pin(struct kd_mutex_node *node)',
        'static void kd_mutex_wait_and_lock_node(struct kd_mutex *lock,',
    ))
    constants = '\n'.join(re.findall(
        r'^#define KD_MUTEX_(?:WAIT|PROXY_REQUEST|PROXY_PINNED) \d+$',
        (ROOT / 'include/kd_mutex.h').read_text(), re.M))
    assert len(constants.splitlines()) == 3
    mutations = {
        'queue-cannot-schedule': ('\tpreempt_enable();', '\t/* missing enable */', 1),
        'proxy-without-origin-pin': ('\t\t\tpreempt_disable();', '\t\t\t/* missing pin */', 1),
        'skip-origin-ack': (
            '\twhile (smp_load_acquire(&node->locked) != KD_MUTEX_PROXY_PINNED)\n\t\tcpu_relax();',
            '\t/* no acknowledgement wait */', 1),
        'self-cpu-selection': (' == raw_smp_processor_id())', ' == -99)', 1),
        'head-cannot-schedule': (
            '\tpreempt_enable();\n\tfor (;;) {\n\t\twhile (kd_mutex_gate_read(lock))',
            '\tfor (;;) {\n\t\twhile (kd_mutex_gate_read(lock))', 1),
    }
    with tempfile.TemporaryDirectory(prefix='kd-mutex-proxy-pin-') as directory:
        path = Path(directory)
        for name, mutation in [('production', None), *mutations.items()]:
            candidate = code
            if mutation:
                before, after, count = mutation
                assert candidate.count(before) >= count, name
                candidate = candidate.replace(before, after, count)
            (path / 'proxy_production.h').write_text(constants + '\n' + candidate)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-I' + directory,
                str(ROOT / 'tests/unit/mutex/mutex_proxy_pin_fixture.c'),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            if mutation:
                assert result.returncode == 1 and 'FAIL proxy pin' in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print('proxy pin mutation detected:', name)
            else:
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                print(result.stdout, end='')


if __name__ == '__main__':
    main()
