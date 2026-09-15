"""Compile production hooks/tickets and the spin acquisition function in guest.

The fixture uses deterministic native primitives and excludes queue waiting,
JIT assembly and native-unlock rendezvous. Kernel tests cover those separately.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import read_source

from test_spin_gate import ROOT, without_includes
from test_spin_shadow import definition


def main():
    source = ""
    for name in (
        "include/qspinlock_i.h",
        "include/kd_spin_gate.h",
        "kernel_module/kd_spin_gate.c",
        "include/kd_spin_fast.h",
        "include/kd_spin_entry.h",
        "kernel_module/kd_spin_entry.c",
    ):
        source += without_includes(read_source((ROOT / name))) + "\n"
    source += "DEFINE_PER_CPU(struct kd_spin_fast_cpu, kd_spin_fast_cpu);\n"
    source += "#define qspinlock orig_qspinlock\n"
    spin = read_source((ROOT / "kernel_module/kd_spinlock.c"))
    for marker in (
        "static struct qspinlock *kd_spin_word(struct qspinlock *lock)",
        "static void kd_spin_claim_origin(struct qspinlock *lock)",
        "static void kd_spin_release_origin(struct qspinlock *lock)",
        "static __always_inline void clear_pending_set_locked(struct qspinlock *lock)",
        "static __always_inline void clear_pending(struct qspinlock *lock)",
    ):
        source += definition(spin, marker)
    source += "static unsigned int\n" + definition(
        spin, "kd_spin_fetch_set_pending_acquire(struct qspinlock *lock)"
    )
    source += "void\n" + definition(
        spin, "kd_spin_lock(struct qspinlock *lock, unsigned long rsp_value)"
    )
    source += """
static void kd_spin_unlock(struct qspinlock *lock)
{
    kd_spin_release_origin(lock);
}
"""
    hooks = read_source((ROOT / "kernel_module/kd_lock.c"))
    for marker in (
        "static void origin_raw_spin_lock(raw_spinlock_t *lock)",
        "static void origin_raw_spin_unlock(raw_spinlock_t *lock)",
        "static noinline void kd_raw_spin_unlock_slow(raw_spinlock_t *lock)",
        "static noinline void kd_raw_spin_lock_slow(raw_spinlock_t *lock,",
        "void __kd_raw_spin_unlock(raw_spinlock_t *lock, unsigned long ret_rsp,",
        "void __kd_raw_spin_lock(raw_spinlock_t *lock, unsigned long ret_rsp,",
    ):
        source += definition(hooks, marker)
    main_source = read_source((ROOT / "kernel_module/kd_main.c"))
    source += without_includes(read_source((ROOT / "include/kd_comm.h")))
    source += without_includes(read_source((ROOT / "include/kd_spin_select.h")))
    source += "struct kd_comm_key kd_spin_target;\n"
    source += definition(main_source, "static int __is_kd_test(void)")
    for marker in (
        "static noinline void kd_spin_dispatch_lock_slow(raw_spinlock_t *lock,",
        "static noinline void kd_spin_dispatch_unlock_slow(raw_spinlock_t *lock)",
        "void kd_spin_dispatch_lock(raw_spinlock_t *lock, unsigned long ret_rsp,",
        "void kd_spin_dispatch_unlock(raw_spinlock_t *lock, unsigned long ret_rsp,",
    ):
        source += definition(hooks, marker)
    with tempfile.TemporaryDirectory(prefix="kdlock-spin-routing-unit-") as directory:
        path = Path(directory)
        (path / "routing_production.h").write_text(source)
        binary = path / "spin-routing"
        subprocess.run(
            shlex.split(os.environ.get("CC", "cc"))
            + [
                "-std=gnu11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(path),
                str(ROOT / "tests/unit/spin_routing_fixture.c"),
                "-o",
                str(binary),
            ],
            check=True,
            timeout=30,
        )
        subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    main()
