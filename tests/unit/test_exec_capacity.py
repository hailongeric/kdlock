"""Guest-only production frame allocation, ledger and cleanup contracts.

Physical unlocks, PID/RCU observations, scheduling and source leases remain
substitutes. Calling a cleanup helper does not authorize post-JIT rollback.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from test_spin_gate import ROOT, without_includes
from test_spin_shadow import definition


def production():
    kernel = Path(f"/lib/modules/{os.uname().release}/build")
    ptrace = (kernel / "arch/x86/include/asm/ptrace.h").read_text()
    ptrace = ptrace.split("#else /* __i386__ */", 1)[1]
    types = definition(ptrace, "struct pt_regs {").rstrip() + ";\n"
    types += (
        definition(
            (ROOT / "include/kd_spin_entry.h").read_text(), "struct kd_spin_ref {"
        ).rstrip()
        + ";\n"
    )
    for name in ("include/kd_call.h", "include/kd_exec.h"):
        types += without_includes((ROOT / name).read_text()) + "\n"
    source = (ROOT / "kernel_module/kd_exec.c").read_text()
    code = "\n".join(
        definition(source, signature)
        for signature in (
            "static int kd_exec_invariant_failure(void)",
            "static bool kd_exec_frame_state_is_active(int state)",
            "int kd_exec_frame_state(const struct kd_exec_frame *frame)",
            "static void kd_exec_frame_set_state(struct kd_exec_frame *frame, int state)",
            "bool kd_exec_frame_remote_pending(const struct kd_exec_frame *frame)",
            "bool kd_exec_frame_validate(const struct kd_exec_frame *frame)",
            "static bool kd_exec_context_validate(const struct kd_exec_context *ctx)",
            "static void kd_exec_context_reset(struct kd_exec_context *ctx)",
            "static struct kd_exec_context *kd_exec_current_context(void)",
            "struct kd_exec_frame *kd_exec_current_frame(void)",
            "bool kd_exec_context_busy(void)",
            "kd_exec_frame_push(const struct pt_regs *regs, unsigned long entry_ip,",
            "int kd_exec_frame_pop(struct kd_exec_frame *frame, struct pt_regs *regs)",
            "int kd_exec_frame_set_lock_entries(struct kd_exec_frame *frame,",
            "int kd_exec_frame_set_lock_stack(struct kd_exec_frame *frame,",
            "int kd_exec_frame_lock_push(struct kd_exec_frame *frame,",
            "int kd_exec_frame_lock_pop(struct kd_exec_frame *frame, unsigned long lock_addr)",
            "int kd_exec_frame_lock_mark_released(struct kd_exec_frame *frame,",
            "bool kd_exec_frame_lock_contains(const struct kd_exec_frame *frame,",
            "bool kd_exec_frame_has_unreleased_nested(const struct kd_exec_frame *frame)",
            "bool kd_exec_frame_locks_released(const struct kd_exec_frame *frame)",
            "bool kd_exec_frame_can_complete(const struct kd_exec_frame *frame)",
            "int kd_exec_frame_record_event(struct kd_exec_frame *frame,",
            "int kd_exec_frame_complete(struct kd_exec_frame *frame)",
            "int kd_exec_frame_abort(struct kd_exec_frame *frame)",
        )
    )
    code = code.replace(
        "\nkd_exec_frame_push(", "\nstruct kd_exec_frame *\nkd_exec_frame_push("
    )
    # Compile the actual SELFTEST observer into the real pop path. Substitute
    # only PID/RCU/time primitives; live TID detachment still needs mode 8.
    code = without_includes(
        (ROOT / "tests/kernel/exec_relay_exit_probe.c").read_text()
    ) + "\n" + code
    code += "\n#define kd_exec_frame_push counted_frame_push\n"
    code += (ROOT / "tests/kernel/exec_capacity_probe.c").read_text()
    code += "\n#undef kd_exec_frame_push\n"
    # Cleanup order belongs to the backend producer, not a copied frame model.
    # Keep its real kind/released decisions while substituting physical unlocks.
    spin = (ROOT / "include/kd_spinlock.h").read_text()
    code += (
        "\n".join(
            line for line in spin.splitlines()
            if line.startswith("#define KD_SPIN_NESTED_UNLOCK_")
        )
        + "\n"
    )
    hook = (ROOT / "kernel_module/kd_lock.c").read_text()
    for marker in (
        "int kd_mutex_jit_abort_cleanup(struct kd_exec_frame *frame)",
        "int kd_spin_jit_abort_cleanup(struct kd_exec_frame *frame)",
    ):
        code += definition(hook, marker)
    return types, code


def main():
    types, code = production()
    # A mutant must compile and fail a fixture assertion. Compiler errors,
    # crashes and timeouts are failures of this test, not detected mutations.
    mutations = {
        "early-refusal": (
            "ctx->depth >= KD_EXEC_MAX_NESTING",
            "ctx->depth >= KD_EXEC_MAX_NESTING - 1",
        ),
        "reject-writes-parent": (
            "ctx->depth >= KD_EXEC_MAX_NESTING",
            "(ctx->depth >= KD_EXEC_MAX_NESTING && (ctx->frames[0].regs.ax = 0, true))",
        ),
        "lost-registers": ("frame->regs = *regs;", "frame->regs.ax = regs->ax;"),
        "lost-parent": (
            "frame->parent = kd_exec_current_frame();",
            "frame->parent = NULL;",
        ),
        "stale-owner": (
            "if (!ctx->depth)\n\t\tctx->owner = NULL;",
            "/* stale owner */",
        ),
        "duplicate-ledger-lock": (
            "if (kd_exec_frame_lock_contains(frame, lock_addr))",
            "if (false && kd_exec_frame_lock_contains(frame, lock_addr))",
        ),
        "missing-outer-accepted": (
            "if (frame->outer_lock_addr && outer_index == KD_EXEC_MAX_LOCK_DEPTH)",
            "if (false && frame->outer_lock_addr && outer_index == KD_EXEC_MAX_LOCK_DEPTH)",
        ),
        "dense-pop-loses-kind": (
            "frame->jit_lock_kind[i - 1] = frame->jit_lock_kind[i];",
            "frame->jit_lock_kind[i - 1] = KD_EXEC_LOCK_NATIVE;",
        ),
        "repeated-unlock-accepted": (
            "if (frame->jit_lock_released[i - 1])\n\t\t\treturn -EALREADY;",
            "if (false && frame->jit_lock_released[i - 1])\n\t\t\treturn -EALREADY;",
        ),
        "premature-completion": (
            "return kd_exec_frame_locks_released(frame) &&",
            "return (kd_exec_frame_locks_released(frame) || true) &&",
        ),
        "pop-drops-logical-child": (
            "kd_exec_frame_remote_pending(frame) || frame->resume_target ||",
            "kd_exec_frame_remote_pending(frame) || false ||",
        ),
        "pop-drops-native-request": (
            "READ_ONCE(frame->native_request) ||",
            "false ||",
        ),
        "pop-drops-native-routing": (
            "!list_empty(&frame->native_link) ||",
            "false ||",
        ),
        "mutex-cleanup-double-unlock": (
            "if (!frame->jit_lock_released[i]) {",
            "if (true || !frame->jit_lock_released[i]) {",
        ),
        "child-observer-before-ack": (
            "frame != READ_ONCE(kd_relay_exit.frame) || kd_relay_exit.after_ack",
            "frame != READ_ONCE(kd_relay_exit.frame) || false",
        ),
        "child-pop-skips-observer": (
            "kd_exec_selftest_relay_pop(frame);",
            "(void)kd_exec_selftest_relay_pop; (void)frame; /* skipped observer */",
        ),
        "exit-observer-assumes-detached": (
            "detached = !pid_task(kd_relay_exit.pid, PIDTYPE_PID);",
            "detached = true;",
        ),
        "exit-observer-loses-packet-check": (
            "packet &= !memcmp(frame, &kd_relay_exit.expected, sizeof(*frame));",
            "packet &= true;",
        ),
        "exit-observer-loses-context-check": (
            "preempt_count() == kd_relay_exit.preempt",
            "true",
        ),
        "exit-observer-leaks-pid": (
            "put_pid(kd_relay_exit.pid);",
            "(void)put_pid; (void)kd_relay_exit.pid;",
        ),
    }
    with tempfile.TemporaryDirectory(prefix="kdlock-exec-capacity-unit-") as tmp:
        path = Path(tmp)
        (path / "frame_types.h").write_text(types)
        for name, mutation in [("production", None), *mutations.items()]:
            candidate = code
            if mutation:
                before, after = mutation
                assert code.count(before) == 1, (name, code.count(before))
                candidate = code.replace(before, after)
            (path / "frame_code.h").write_text(candidate)
            binary = path / name
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
                    str(ROOT / "tests/unit/exec_capacity_fixture.c"),
                    "-o",
                    str(binary),
                ],
                check=True,
                timeout=30,
            )
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True, timeout=10, check=False
            )
            if mutation:
                assert result.returncode == 1 and "FAIL line" in result.stderr, (
                    name,
                    result.returncode,
                    result.stdout,
                    result.stderr,
                )
                print(f"capacity mutation detected: {name}")
            else:
                print(result.stdout, end="")
                assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    main()
