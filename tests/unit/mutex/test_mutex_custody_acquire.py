"""Guest-only composed native acquisition-to-custody accounting regression.

Compile the production C entry aliases, fast/helper chain, local acquisition,
trylock, release and exact custody ledger together. Atomics, task routing and
the blocking/contended boundary are explicit deterministic substitutes; the
assembly clobber contract and live ownership exchange are checked elsewhere.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT, read_source
from test_spin_shadow import definition


def main():
    header = read_source(ROOT / "include/kd_mutex.h")
    direct = read_source(ROOT / "include/kd_mutex_direct.h")
    lock = read_source(ROOT / "kernel_module/kd_lock.c")
    local = read_source(ROOT / "kernel_module/kd_mutex_local.c")
    custody = read_source(ROOT / "kernel_module/mutex/custody.inc")
    types = definition(read_source(ROOT / "include/kd_mutex_types.h"),
                       "struct kd_mutex {") + ";\n"
    for marker in ("enum kd_mutex_custody_phase {", "struct kd_mutex_custody {",
                   "struct kd_mutex_osq_node {", "struct kd_mutex_node {"):
        types += definition(header, marker) + ";\n"
    types += definition(read_source(ROOT / "include/exe_info.h"),
                        "enum kd_entry_abi {") + ";\n"
    constants = "\n".join(line for line in header.splitlines() if line.startswith((
        "#define KD_MUTEX_CUSTODY_LOCKS ", "#define KD_MUTEX_GATE_COMBINER ")))
    assert len(constants.splitlines()) == 2
    code = ""
    for marker in (
        "static struct kd_mutex_node *kd_mutex_custody_current(void)",
        "void kd_mutex_custody_native_acquire(struct kd_mutex *lock)",
        "void kd_mutex_custody_native_release(struct kd_mutex *lock)",
    ):
        code += definition(custody, marker) + "\n"
    for marker in (
        "static __always_inline void kd_mutex_note_native_acquire(struct kd_mutex *lock)",
        "static __always_inline void kd_mutex_note_native_release(struct kd_mutex *lock)",
    ):
        code += definition(header, marker) + "\n"
    code += "static __always_inline bool\n" + definition(
        direct, "kd_mutex_outer_trylock(struct kd_mutex *lock, unsigned long owner)")
    code += definition(lock,
        "static __always_inline bool kd_mutex_trylock_fast(struct kd_mutex *lock)")
    for marker in (
        "static struct task_struct *kd_owner(struct kd_mutex *lock)",
        "static __always_inline struct task_struct *kd_try_common(struct kd_mutex *lock, bool handoff)",
        "static int kd_local_lock_state(struct kd_mutex *lock, unsigned int state,",
        "int kd_mutex_trylock(struct kd_mutex *lock)",
        "void kd_mutex_local_unlock(struct kd_mutex *lock)",
    ):
        code += definition(local, marker) + "\n"
    entry = definition(lock,
        "static void kd_mutex_lock_entry(struct kd_mutex *lock, unsigned long ret_rsp,")
    # Exactly one successful primitive owns the ledger update. Reintroduce the
    # actual live regression at its original extra call site, not in a mock.
    assert "kd_mutex_note_native_acquire(lock);" not in entry
    trigger = "\t\tkd_hotlock_mutex_entry();"
    assert entry.count(trigger) == 1
    code += entry + "\n"
    for marker in (
        "void __kd_mutex_lock(struct kd_mutex *lock, unsigned long ret_rsp,",
        "void __kd_mutex_lock_clobber_v1(struct kd_mutex *lock, unsigned long sp,",
    ):
        code += definition(lock, marker) + "\n"
    code += "void\n" + definition(lock,
        "kd_mutex_direct_lock_clobber_v1(struct kd_mutex *lock, unsigned long sp,")
    variants = {
        "production": code,
        "duplicate-entry-note": code.replace(entry, entry.replace(trigger,
            trigger + "\n\t\tkd_mutex_note_native_acquire(lock);", 1), 1),
    }
    duplicate = "BUG custody acquire: custody->native_locks[i] == lock"
    with tempfile.TemporaryDirectory(prefix="kd-custody-acquire-") as directory:
        path = Path(directory)
        (path / "custody_acquire_types.h").write_text(constants + "\n" + types)
        for name, candidate in variants.items():
            assert name == "production" or candidate != code
            (path / "custody_acquire_production.h").write_text(candidate)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
                "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-I" + directory, "-I" + str(ROOT / "include"),
                str(ROOT / "tests/unit/mutex/mutex_custody_acquire_fixture.c"),
                "-o", str(binary)], check=True, timeout=30)
            result = subprocess.run([binary], capture_output=True, text=True, timeout=10)
            if name == "production":
                assert result.returncode == 0, (result.stdout, result.stderr)
                print(result.stdout, end="")
                misuse = subprocess.run([binary, "duplicate"], capture_output=True,
                                        text=True, timeout=10)
                assert misuse.returncode == 86 and duplicate in misuse.stderr, misuse
                print("custody acquisition: genuine duplicate still triggers production BUG")
            else:
                assert result.returncode == 86 and duplicate in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print("custody acquisition mutation detected:", name)


if __name__ == "__main__":
    main()
