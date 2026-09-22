"""Guest-only paired ABI and production cold routing, without kernel modules.

Hardware contention is substituted; live MCS/JIT acceptance is checked by the
direct benchmark. The ABI fixture executes the real header with destructive
hot callees, so an incorrect compiler clobber contract corrupts live values.
"""
import re
import subprocess
import tempfile
from pathlib import Path

from test_spin_shadow import definition

ROOT = Path(__file__).resolve().parents[3]


def main():
    source = (ROOT / 'kernel_module/kd_spinlock.c').read_text()
    code = 'unsigned int ' + definition(source, 'kd_spin_direct_enter(kd_spinlock_t *lock)')
    code += 'void ' + definition(source, 'kd_spin_direct_native_unlock(kd_spinlock_t *lock)')
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
            subprocess.run(['cc', '-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                            '-fno-omit-frame-pointer', '-fno-optimize-sibling-calls',
                            '-mno-red-zone', '-mpreferred-stack-boundary=3',
                            '-I', directory, str(ROOT / 'tests/unit/spin' / (fixture + '.c')),
                            '-o', str(binary)], check=True, timeout=30)
            subprocess.run([binary], check=True, timeout=10)


if __name__ == '__main__':
    main()
