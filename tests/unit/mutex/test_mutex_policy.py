"""Guest-only locality-epoch state/routing checks using production C.

Clock, CPU pinning and competing policy publications are deterministic models;
the fixture is not evidence of live queue/owner concurrency or native fairness.
"""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def main():
    code = without_includes((ROOT / 'kernel_module/lock/mutex_policy.inc').read_text())
    hook = read_source(ROOT / 'kernel_module/kd_lock.c')
    for marker in (
        'static __always_inline bool kd_mutex_contended_eligible(void)',
        'static __always_inline struct kd_mutex *kd_mutex_contended_select(',
        'static __always_inline unsigned long kd_mutex_contended_queue(',
        'static unsigned long kd_mutex_contended_acquire(struct mutex *lock, unsigned long ret_rsp,',
    ):
        code += definition(hook, marker)
    mutations = {
        'remote-veto-lost': ('&& node != home)', '&& false && node != home)'),
        'native-never-expires': ('time_before(now, deadline)',
                                 '(mode == KD_MUTEX_POLICY_NATIVE || time_before(now, deadline))'),
        'deadline-truncated': ('unsigned long now = jiffies;',
                               'unsigned long now = (unsigned int)jiffies;'),
        'updating-enters-native': ('if (mode == KD_MUTEX_POLICY_UPDATING)\n\t\t\treturn false;',
                                   'if (mode == KD_MUTEX_POLICY_UPDATING)\n\t\t\treturn true;'),
        'stale-transition-published': ('atomic_long_cmpxchg(&slot->word, old, updating) == old',
                                       '(atomic_long_cmpxchg(&slot->word, old, updating), true)'),
        'native-cookie-routed': ('if (!kd_mtx)\n\t\treturn (unsigned long)current;',
                                'if (!kd_mtx)\n\t\treturn 0;'),
        'missing-locality-pin': ('preempt_disable();\n\tnative = kd_mutex_policy_native_pinned(lock);\n\tpreempt_enable();',
                                 'native = kd_mutex_policy_native_pinned(lock);'),
    }
    with tempfile.TemporaryDirectory(prefix='kd-mutex-policy-') as directory:
        directory = Path(directory)
        for hz in (250, 1000):
            for name, mutation in [('production', None), *mutations.items()]:
                candidate = code
                if mutation:
                    before, after = mutation
                    assert candidate.count(before) == 1, (name, candidate.count(before))
                    candidate = candidate.replace(before, after)
                (directory / 'policy_code.h').write_text(candidate)
                binary = directory / f'{name}-{hz}'
                subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                    '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                    f'-DTEST_HZ={hz}', '-I'+str(directory),
                    str(ROOT / 'tests/unit/mutex/mutex_policy_fixture.c'),
                    '-o', str(binary)], check=True, timeout=30)
                result = subprocess.run([str(binary)], capture_output=True,
                                        text=True, timeout=10, check=False)
                if mutation:
                    assert result.returncode == 1 and 'FAIL line' in result.stderr, (
                        name, hz, result.returncode, result.stdout, result.stderr)
                    print(f'mutex policy mutation detected ({hz} Hz): {name}')
                else:
                    assert result.returncode == 0, result.stderr
                    print(result.stdout, end='')


if __name__ == '__main__':
    main()
