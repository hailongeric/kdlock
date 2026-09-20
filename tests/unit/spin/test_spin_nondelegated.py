"""Run the production nondelegating pending/MCS path with x86 atomic peers.

Guest only. The C fixture has real pthread contention, but substitutes CPU
pinning and kernel atomics; live provider runs remain separate evidence.
"""
import re
import subprocess
import tempfile
from pathlib import Path

from test_spin_shadow import definition

ROOT = Path(__file__).resolve().parents[3]


def main():
    with tempfile.TemporaryDirectory(prefix='kd-nondelegated-') as directory:
        binary = Path(directory) / 'test'
        subprocess.run(['cc', '-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        '-pthread', '-I', str(ROOT),
                        str(ROOT/'tests/unit/spin/spin_nondelegated_fixture.c'),
                        '-o', str(binary)], check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=40)
        # Exercise both public-routing and direct native-bridge ownership,
        # using the real fast-record helpers and paired native API bodies.
        fast = (ROOT/'include/kd_spin_fast.h').read_text()
        fast = re.sub(r'^#include .*$', '', fast, flags=re.M)
        source = (ROOT/'kernel_module/kd_spinlock.c').read_text()
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
