"""Run the production nondelegating pending/MCS path with x86 atomic peers.

Guest only. The C fixture has real pthread contention, but substitutes CPU
pinning and kernel atomics; live provider runs remain separate evidence.
"""
import re
import subprocess
import tempfile
from pathlib import Path

from source_text import read_source
from test_spin_shadow import definition

ROOT = Path(__file__).resolve().parents[3]


def main():
    with tempfile.TemporaryDirectory(prefix='kd-nondelegated-') as directory:
        binary = Path(directory) / 'test'
        queue = (ROOT/'kernel_module/spin/queue.inc').read_text()
        publication = queue[
            queue.index('static __always_inline u32 xchg_tail'):
            queue.index('/**\n * clear_pending')]
        (Path(directory)/'spin_mcs_tail.h').write_text(publication)
        policy = (ROOT/'include/kd_hotlock.h').read_text()
        interval = next(line for line in policy.splitlines()
                        if line.startswith('#define KD_HOTLOCK_SPIN_MCS_INTERVAL '))
        (Path(directory)/'spin_mcs_policy.h').write_text(interval + '\n')
        source = read_source(ROOT/'kernel_module/kd_spinlock.c')
        direct = (ROOT/'include/kd_spin_direct.h').read_text()
        paired = 'void ' + definition(source,
            'kd_spin_direct_native_contended(kd_spinlock_t *lock, u32 failed)')
        paired += definition(direct,
            'static __always_inline void kd_spin_direct_native_lock_inline(kd_spinlock_t *lock)')
        paired += 'void ' + definition(source,
            'kd_spin_direct_native_lock(kd_spinlock_t *lock)')
        paired += 'void ' + definition(source, 'kd_spin_direct_native_unlock(kd_spinlock_t *lock)')
        (Path(directory)/'spin_direct_native.h').write_text(paired)
        subprocess.run(['cc', '-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        '-pthread', '-I', str(ROOT), '-I', directory,
                        str(ROOT/'tests/unit/spin/spin_nondelegated_fixture.c'),
                        '-o', str(binary)], check=True, timeout=30)
        # Every real publication counts, including two/three-thread cohorts;
        # the single-thread fast path must not create an MCS sample.
        for threads in (1, 2, 3, 8):
            subprocess.run([str(binary), str(threads)], check=True, timeout=40)
        # Exercise both public-routing and direct native-bridge ownership,
        # using the real fast-record helpers and paired native API bodies.
        fast = (ROOT/'include/kd_spin_fast.h').read_text()
        fast = re.sub(r'^#include .*$', '', fast, flags=re.M)
        source = read_source(ROOT/'kernel_module/kd_spinlock.c')
        api = fast + '\n' + definition(source, 'static void kd_spin_lock_nondelegated_pinned(kd_spinlock_t *lock)')
        api += definition(source, 'void kd_spin_lock_nondelegated(kd_spinlock_t *lock)')
        api += definition(source, 'void kd_spin_unlock_nondelegated(kd_spinlock_t *lock)')
        (Path(directory)/'spin_nondelegated_api.h').write_text(api)
        subprocess.run(['cc', '-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        '-I', directory, str(ROOT/'tests/unit/spin/spin_nondelegated_owner_fixture.c'),
                        '-o', str(binary)], check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == '__main__':
    main()
