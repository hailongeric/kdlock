"""Production pinned mutex balances and drain, with two substituted CPUs.

Resource tests cover real reserve/release decisions. This fixture checks that
independent CPU balances, slot lifetime and underflow cannot authorize drain.
Scheduling/CPU affinity are substitutes; live benchmark drain is separate.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT, read_source
from test_spin_shadow import definition


def main():
    source = read_source(ROOT / 'kernel_module/kd_mutex.c')
    for name in ('active_waiters', 'reserved_nodes'):
        assert f'static DEFINE_PER_CPU(int, kd_mutex_{name});' in source
    markers = (
        'static void kd_mutex_update_max_waiters(int active)',
        'static void kd_mutex_waiter_enter(struct kd_mutex *lock)',
        'static void kd_mutex_waiter_exit(struct kd_mutex *lock)',
        'bool kd_mutex_check_idle(void)',
    )
    code = '\n'.join(definition(source, marker) for marker in markers)
    mutations = {
        'ignores-second-cpu': ('for_each_possible_cpu(cpu)',
                              'for (cpu = 0; cpu < 1; cpu++)'),
        'ignores-reservation': (
            'READ_ONCE(per_cpu(kd_mutex_reserved_nodes, cpu))', 'false'),
        'ignores-slot-lifetime': (
            'READ_ONCE(per_cpu(kd_mutex_shadows, cpu).node_slots)', 'false'),
        'ignores-registered-sleeper': ('if (rcuwait_active(', 'if (false && rcuwait_active('),
        'drops-exit-balance': (
            'this_cpu_dec_return(kd_mutex_active_waiters)',
            'this_cpu_read(kd_mutex_active_waiters)'),
        'opposite-balances-cancel': (
            'READ_ONCE(per_cpu(kd_mutex_active_waiters, cpu))',
            '(per_cpu(kd_mutex_active_waiters, 0) + '
            'per_cpu(kd_mutex_active_waiters, 1))'),
    }
    with tempfile.TemporaryDirectory(prefix='kdlock-mutex-balances-') as tmp:
        path = Path(tmp)
        for name, mutation in [('production', None), *mutations.items()]:
            candidate = code
            if mutation:
                before, after = mutation
                assert candidate.count(before) == 1
                candidate = candidate.replace(before, after)
            (path / 'mutex_balances_production.h').write_text(candidate)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-I', str(path),
                str(ROOT / 'tests/unit/mutex/mutex_balances_fixture.c'),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True,
                                    text=True, timeout=10)
            if mutation:
                assert result.returncode == 1 and 'FAIL line' in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print('mutex balance mutation detected:', name)
            else:
                assert result.returncode == 0, result.stderr
                print(result.stdout, end='')


if __name__ == '__main__':
    main()
