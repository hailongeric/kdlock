"""Guest-only: admission/refusal must retain exactly one acquisition pin.

Compile production entry routing and native ownership helpers. Hardware queue
and ticket peers are substitutes; live delegated completion is checked separately.
"""
import re
import subprocess
import tempfile
from pathlib import Path

from test_spin_shadow import definition

ROOT = Path(__file__).resolve().parents[3]


def main():
    source = (ROOT / 'kernel_module/kd_spinlock.c').read_text()
    fast = re.sub(r'^#include .*$', '', (ROOT / 'include/kd_spin_fast.h').read_text(), flags=re.M)
    code = fast
    for name in ('static void kd_spin_lock_nondelegated_pinned(kd_spinlock_t *lock)',
                 'void kd_spin_lock_nondelegated(kd_spinlock_t *lock)',
                 'void kd_spin_unlock_nondelegated(kd_spinlock_t *lock)'):
        code += definition(source, name)
    code += 'void ' + definition(source, 'kd_spin_lock_abi(struct qspinlock *lock, unsigned long rsp_value,')
    code += 'void ' + definition(source, 'kd_spin_unlock(struct qspinlock *lock)')
    with tempfile.TemporaryDirectory(prefix='kd-preempt-') as directory:
        path = Path(directory)
        (path / 'spin_preempt_api.h').write_text(code)
        binary = path / 'test'
        subprocess.run(['cc', '-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        '-I', directory, str(ROOT / 'tests/unit/spin/spin_preempt_fixture.c'),
                        '-o', str(binary)], check=True, timeout=30)
        subprocess.run([binary], check=True, timeout=10)


if __name__ == '__main__':
    main()
