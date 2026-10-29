"""Guest-only inline cold gate and compiler-owned clobber ABI checks.

Hardware contention is substituted; live MCS/JIT acceptance is checked by the
direct benchmark. The ABI fixture executes the real header with destructive
hot acquisition and generic unlock callees, so an incorrect compiler clobber
contract corrupts live values on both cold and hot releases.
Its GS base models two CPU-local scalar gates through the kernel per-CPU
primitive substitute; the real header owns the C admission branch.
"""
import re
import subprocess
import tempfile
from pathlib import Path

from source_text import read_source
from test_spin_shadow import definition

ROOT = Path(__file__).resolve().parents[3]


def main():
    source = read_source(ROOT / 'kernel_module/kd_spinlock.c')
    direct = (ROOT / 'include/kd_spin_direct.h').read_text()
    code = 'void ' + definition(source,
        'kd_spin_direct_native_contended(kd_spinlock_t *lock, u32 failed)')
    for signature in (
        'static __always_inline u32 kd_spin_direct_native_reserve_inline(kd_spinlock_t *lock)',
        'static __always_inline void kd_spin_direct_native_cancel_inline(void)',
        'static __always_inline void\nkd_spin_direct_native_finish_inline(kd_spinlock_t *lock, u32 failed)',
        'static __always_inline void kd_spin_direct_native_lock_inline(kd_spinlock_t *lock)',
    ):
        code += definition(direct, signature)
    code += 'void ' + definition(source, 'kd_spin_direct_native_lock(kd_spinlock_t *lock)')
    code += 'void ' + definition(source, 'kd_spin_direct_native_unlock(kd_spinlock_t *lock)')
    code += 'void ' + definition(source, 'kd_spin_unlock_legacy(struct qspinlock *lock)')
    code += 'void ' + definition(source,
        'kd_spin_unlock_clobber_v1(struct qspinlock *lock, unsigned long sp,')
    code += definition((ROOT / 'include/kd_spin_fast.h').read_text(),
                       'static inline bool kd_spin_fast_idle(void)')
    header = re.sub(r'^#include .*$', '', direct, flags=re.M)
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
            if fixture == 'spin_paired_abi_fixture':
                subprocess.run(['objcopy', '--dump-section',
                                f'.discard.kd_boundary={path}/annotation.bin', str(binary)],
                               check=True, timeout=10)
                annotation = (path/'annotation.bin').read_bytes()
                assert annotation == b'\0' * 3, 'code leaked into continuation annotation section'
            if fixture == 'spin_cold_route_fixture':
                # Exercise both compile-time and dynamic-preemption C targets;
                # the real module build checks static-call tail-site metadata.
                subprocess.run(['cc', '-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                '-Wno-unused-parameter', '-DKD_TEST_STATIC_CALL',
                                '-I', directory, str(ROOT / 'tests/unit/spin' / (fixture + '.c')),
                                '-o', str(binary)], check=True, timeout=30)
                subprocess.run([binary], check=True, timeout=10)


if __name__ == '__main__':
    main()
