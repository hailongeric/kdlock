"""Guest-only inline cold gate and compiler-owned clobber ABI checks.

Hardware contention is substituted; live MCS/JIT acceptance is checked by the
direct benchmark. The ABI fixture executes the real header with destructive
hot acquisition and generic unlock callees, so an incorrect compiler clobber
contract corrupts live values on both cold and hot releases.
Its GS base models two CPU-local pointer slots through the kernel per-CPU
primitive substitute; the real header owns the C admission branch.
"""
import re
import subprocess
import tempfile
from pathlib import Path

from test_spin_shadow import definition

ROOT = Path(__file__).resolve().parents[3]


def main():
    source = (ROOT / 'kernel_module/kd_spinlock.c').read_text()
    code = 'void ' + definition(source, 'kd_spin_direct_native_lock(kd_spinlock_t *lock)')
    code += 'void ' + definition(source, 'kd_spin_direct_native_unlock(kd_spinlock_t *lock)')
    code += 'void ' + definition(source,
        'kd_spin_unlock_clobber_v1(struct qspinlock *lock, unsigned long sp,')
    code += definition((ROOT / 'include/kd_spin_fast.h').read_text(),
                       'static inline bool kd_spin_fast_idle(void)')
    header = re.sub(r'^#include .*$', '',
                    (ROOT / 'include/kd_spin_direct.h').read_text(), flags=re.M)
    with tempfile.TemporaryDirectory(prefix='kd-cold-') as directory:
        path = Path(directory)
        (path / 'cold_route.h').write_text(code)
        (path / 'paired.h').write_text(header)
        for fixture in ('spin_cold_route_fixture', 'spin_paired_abi_fixture'):
            binary = path / fixture
            # These userspace fixtures call libc, whose ABI requires a
            # 16-byte call-site stack alignment. The kernel's 8-byte build
            # convention is checked separately in real module code and runs.
            subprocess.run(['cc', '-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                            '-Wno-unused-parameter',
                            '-fno-omit-frame-pointer', '-fno-optimize-sibling-calls',
                            '-mno-red-zone', '-mpreferred-stack-boundary=4',
                            '-I', directory, str(ROOT / 'tests/unit/spin' / (fixture + '.c')),
                            '-o', str(binary)], check=True, timeout=30)
            subprocess.run([binary], check=True, timeout=10)


if __name__ == '__main__':
    main()
