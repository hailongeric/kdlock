"""Guest-only exact mixed controls and concurrent no-gap mutex owner transfer.

Compile the production functions. Scheduler pins, ticket allocation and queue
peers are explicit substitutes; the kernel mixed escape probe covers JIT/ACK.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def functions(path, markers):
    source = read_source(ROOT / path)
    return "\n".join(definition(source, marker) for marker in markers)


def main():
    owner = functions("kernel_module/kd_mutex_local.c", (
        "static __always_inline struct task_struct *kd_try_common(struct kd_mutex *lock, bool handoff)",
        "int kd_mutex_transfer_owner(struct kd_mutex *lock, struct task_struct *next)",
        "int kd_mutex_transfer_pickup(struct kd_mutex *lock)",
    ))
    spin = functions("kernel_module/spin/ticket_origin.inc", (
        "int kd_spin_nested_try_once(raw_spinlock_t *lock, struct kd_spin_ref *ref)",
        "int kd_spin_nested_release_exact(raw_spinlock_t *lock,",
    ))
    types = definition(read_source(ROOT / "include/kd_spin_entry.h"), "struct kd_spin_ref {") + ";\n"
    types += definition(read_source(ROOT / "include/exe_info.h"), "enum kd_entry_abi {") + ";\n"
    types += without_includes(read_source(ROOT / "include/kd_call.h"))
    types += without_includes(read_source(ROOT / "include/kd_exec.h"))
    ledger = functions("kernel_module/kd_exec.c", (
        "int kd_exec_frame_lock_push(struct kd_exec_frame *frame,",
        "bool kd_exec_frame_lock_contains(const struct kd_exec_frame *frame,",
        "int kd_exec_frame_lock_pop(struct kd_exec_frame *frame, unsigned long lock_addr)",
        "bool kd_exec_frame_has_unreleased_nested(const struct kd_exec_frame *frame)",
        "bool kd_exec_frame_locks_released(const struct kd_exec_frame *frame)",
        "bool kd_exec_frame_can_complete(const struct kd_exec_frame *frame)",
        "bool kd_exec_frame_can_borrow_locks(const struct kd_exec_frame *frame)",
        "unsigned int kd_exec_mutex_spin_count(const struct kd_exec_frame *frame)",
        "bool kd_exec_mutex_transfer_allowed(const struct kd_exec_frame *frame)",
    ))
    controls = functions("kernel_module/kd_lock.c", (
        "static int kd_jit_begin_call(struct kd_exec_frame *frame, struct kd_regs *regs)",
        "static int kd_jit_advance_call(struct kd_exec_frame *frame,",
        "int kd_mutex_jit_spin_lock_ctx(raw_spinlock_t *lock, struct kd_regs *regs,",
        "int kd_mutex_jit_spin_unlock_ctx(raw_spinlock_t *lock,",
    ))
    with tempfile.TemporaryDirectory(prefix="kd-mixed-") as tmp:
        path = Path(tmp)
        (path / "mixed_types.h").write_text(types)
        (path / "mixed_production.h").write_text(spin + ledger + controls)
        candidates = {
            "owner": owner,
            "owner-loses-waiters": owner.replace("(owner & KD_FLAGS) | KD_PICKUP", "KD_PICKUP"),
            "owner-without-pickup": owner.replace(" | KD_PICKUP;", ";"),
            "owner-opens-gap": owner.replace("transferred = (unsigned long)next | (owner & KD_FLAGS) | KD_PICKUP;", "transferred = 0;"),
        }
        cc = shlex.split(os.environ.get("CC", "cc"))
        for name, code in candidates.items():
            assert name == "owner" or code != owner, name
            (path / "owner_production.h").write_text(code)
            binary = path / name
            subprocess.run(cc + ["-std=gnu11", "-O2", "-pthread", "-Wall", "-Wextra", "-Werror",
                           "-I" + str(path), str(ROOT / "tests/unit/mutex/mutex_transfer_fixture.c"),
                           "-o", str(binary)], check=True, timeout=30)
            result = subprocess.run([binary], text=True, capture_output=True, timeout=15)
            if name == "owner":
                assert result.returncode == 0, result.stdout + result.stderr
                print(result.stdout, end="")
            else:
                assert result.returncode == 1 and "FAIL" in result.stderr, (name, result)
                print("mutation detected:", name)
        binary = path / "mixed"
        subprocess.run(cc + ["-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                       "-I" + str(path), "-I" + str(ROOT / "include"),
                       str(ROOT / "tests/unit/mutex/mutex_mixed_fixture.c"), "-o", str(binary)],
                       check=True, timeout=30)
        subprocess.run([binary], check=True, timeout=10)


if __name__ == "__main__":
    main()
