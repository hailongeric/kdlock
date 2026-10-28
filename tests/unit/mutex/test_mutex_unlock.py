"""Guest-only production provider unlock routing and exact gate interleavings.

Physical release, task records and native ACKs are deterministic substitutes.
The actual native request protocol is covered by test_remote_outer.py; this
fixture isolates whether the provider is allowed to bypass that protocol.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def main():
    types = without_includes(read_source(ROOT / "include/kd_mutex_types.h"))
    mutex_header = read_source(ROOT / "include/kd_mutex.h")
    types += mutex_header[mutex_header.index("#define KD_MUTEX_GATE_COMBINER"):
                          mutex_header.index("#include <linux/atomic.h>")]
    types += next(line + "\n" for line in read_source(ROOT / "include/kd_lock.h").splitlines()
                  if line.startswith("#define KD_MUTEX_OWNER_FLAGS "))
    state = read_source(ROOT / "include/kd_mutex_state.h")
    source = "\n".join(definition(state, marker) for marker in (
        "static __always_inline u32 kd_mutex_gate_read(struct kd_mutex *lock)",
        "static __always_inline bool kd_mutex_gate_trylock(struct kd_mutex *lock)",
        "static __always_inline void kd_mutex_gate_set(struct kd_mutex *lock, u32 phase)",
    ))
    mutex = read_source(ROOT / "kernel_module/kd_mutex.c")
    source += definition(mutex, "bool kd_mutex_delegation_owned(struct kd_mutex *lock, struct task_struct *task)")
    source += "\nint " + definition(mutex, "_kd_mutex_unlock_checked(struct kd_mutex *lock)")
    source += "\nvoid " + definition(mutex, "_kd_mutex_unlock(struct kd_mutex *lock)")
    router = definition(read_source(ROOT / "kernel_module/kd_lock.c"),
                        "void __kd_mutex_unlock(struct kd_mutex *lock, unsigned long ret_rsp,")
    physical = "kd_origin_mutex_unlock(lock, ret_addr);\n\t\treturn;"
    mutations = {
        "local-fast-route-disabled": (
            "!(owner & 4UL) &&", "false && !(owner & 4UL) &&"),
        "foreign-owner-fast-route": (
            "(owner & ~KD_MUTEX_OWNER_FLAGS) == (unsigned long)current &&",
            "true &&"),
        "pickup-fast-route": ("!(owner & 4UL) &&", "!(owner & 0UL) &&"),
        "transferred-fast-route": (
            "atomic_read_acquire(&lock->delegation_state) == KD_MUTEX_GATE_FREE",
            "(atomic_read_acquire(&lock->delegation_state) == KD_MUTEX_GATE_FREE || "
            "atomic_read_acquire(&lock->delegation_state) == KD_MUTEX_GATE_COMBINER)"),
        "fast-route-drops-unrelated-record": (
            physical, "kd_mutex_task_put(current);\n\t\t" + physical),
        "fast-route-clears-new-gate": (
            physical, "kd_origin_mutex_unlock(lock, ret_addr);\n\t\t"
            "kd_mutex_gate_set(lock, KD_MUTEX_GATE_FREE);\n\t\treturn;"),
        "native-route-bypassed": (
            "if (kd_exec_native_unlock((unsigned long)lock, true))",
            "if (false && kd_exec_native_unlock((unsigned long)lock, true))"),
        "retained-record-ignored": (
            "if (!kd_mutex_task_reroute(current))",
            "if (!(false && kd_mutex_task_reroute(current)))"),
    }
    with tempfile.TemporaryDirectory(prefix="kd-mutex-unlock-") as tmp:
        path = Path(tmp)
        (path / "mutex_unlock_types.h").write_text(types)
        for name, mutation in [("production", None), *mutations.items()]:
            candidate = router
            if mutation:
                before, after = mutation
                # The physical release text occurs in both local returns; only
                # mutate the new first branch, preserving the old fallback.
                expected = 2 if before == physical else 1
                assert candidate.count(before) == expected, (name, candidate.count(before))
                candidate = candidate.replace(before, after, 1)
            (path / "mutex_unlock_actual.h").write_text(source + candidate)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
                "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-I", str(path),
                str(ROOT / "tests/unit/mutex/mutex_unlock_fixture.c"),
                "-o", str(binary)], check=True, timeout=30)
            result = subprocess.run([binary], text=True, capture_output=True, timeout=15)
            if mutation:
                assert result.returncode == 1 and "FAIL line" in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print("mutex unlock mutation detected:", name)
            else:
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                print(result.stdout, end="")


if __name__ == "__main__":
    main()
