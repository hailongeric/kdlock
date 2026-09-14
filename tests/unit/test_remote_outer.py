"""Guest-only production remote protocol with full x86-64 software packets.

CPU switches, native ownership and release observations are substitutes; these
checks do not restore hardware flags or prove arbitrary concurrent lifetimes.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from test_spin_gate import ROOT, without_includes
from test_spin_shadow import definition
from test_exe_registry import timing_code


def main():
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
    types += (
        "\n".join(
            line
            for line in (ROOT / "include/kd_spinlock.h").read_text().splitlines()
            if line.startswith("#define KD_SPIN_NESTED_")
        )
        + "\n"
    )
    frame = (ROOT / "kernel_module/kd_exec.c").read_text()
    code = definition(frame, "struct kd_remote_request {") + ";\n"
    code += definition(frame, "struct kd_native_request {") + ";\n"
    for marker in (
        "static int kd_exec_invariant_failure(void)",
        "static bool kd_exec_frame_state_is_active(int state)",
        "int kd_exec_frame_state(const struct kd_exec_frame *frame)",
        "static void kd_exec_frame_set_state(struct kd_exec_frame *frame, int state)",
        "bool kd_exec_frame_validate(const struct kd_exec_frame *frame)",
        "int kd_exec_frame_lock_pop(struct kd_exec_frame *frame, unsigned long lock_addr)",
        "int kd_exec_frame_lock_mark_released(struct kd_exec_frame *frame,",
        "enum kd_exec_lock_kind\nkd_exec_frame_lock_kind(const struct kd_exec_frame *frame,",
        "bool kd_exec_frame_has_unreleased_nested(const struct kd_exec_frame *frame)",
        "bool kd_exec_frame_remote_pending(const struct kd_exec_frame *frame)",
        "bool kd_exec_frame_locks_released(const struct kd_exec_frame *frame)",
        "bool kd_exec_frame_can_complete(const struct kd_exec_frame *frame)",
        "int kd_exec_frame_record_event(struct kd_exec_frame *frame,",
        "int kd_exec_frame_complete(struct kd_exec_frame *frame)",
        "int kd_exec_remote_unlock(struct kd_exec_frame *frame, unsigned long lock_addr)",
        "void kd_exec_remote_poll(struct kd_exec_frame *frame)",
        "int kd_exec_remote_native(struct kd_exec_frame *frame)",
        "int kd_exec_remote_complete(struct kd_exec_frame *frame)",
        "void kd_exec_remote_cancel(struct kd_exec_frame *frame)",
        "bool kd_exec_frame_can_borrow_locks(const struct kd_exec_frame *frame)",
        "int kd_exec_native_begin(struct kd_exec_frame *frame, bool mutex)",
        "bool kd_exec_native_unlock(unsigned long lock_addr, bool mutex)",
        "static int kd_exec_native_finish(struct kd_exec_frame *frame)",
        "int kd_exec_native_wait(struct kd_exec_frame *frame)",
    ):
        code += definition(frame, marker) + "\n"
    code += definition(
        (ROOT / "kernel_module/kd_lock.c").read_text(),
        "int kd_spin_jit_nested_unlock_ctx(raw_spinlock_t *lock,",
    )
    spin = (ROOT / "kernel_module/kd_spinlock.c").read_text()
    for marker in (
        "static int kd_spin_advance_jit_node(struct kd_spin_node *node,",
        "static int kd_spin_finish_remote_node(struct kd_spin_node *node,",
    ):
        code += definition(spin, marker) + "\n"
    # Mutate temporary extracted functions, never the production sources.
    # Each variant must reach an explicit assertion; crashes are not detection.
    cancel = definition(
        frame, "void kd_exec_remote_cancel(struct kd_exec_frame *frame)"
    )
    complete = definition(
        frame, "int kd_exec_remote_complete(struct kd_exec_frame *frame)"
    )
    native = definition(frame, "int kd_exec_native_wait(struct kd_exec_frame *frame)")
    finish = definition(
        spin, "static int kd_spin_finish_remote_node(struct kd_spin_node *node,"
    )
    done_store = "smp_store_release(&parent->remote_result, KD_EXEC_REMOTE_DONE);"
    mutations = {
        "remote-poll-clobbers-r12": (
            "WRITE_ONCE(frame->remote_request, NULL);",
            "frame->regs.r12 ^= 1;\n\tWRITE_ONCE(frame->remote_request, NULL);",
        ),
        "cancel-clobbers-r13": (
            cancel,
            cancel.replace(
                "frame->resume_target = NULL;",
                "frame->regs.r13 ^= 1;\n\tframe->resume_target = NULL;",
            ),
        ),
        # Move detach past DONE so the observer tests order, not final state.
        "done-before-detach": (
            complete,
            complete.replace("\tframe->resume_target = NULL;\n", "").replace(
                done_store, done_store + "\n\tframe->resume_target = NULL;"
            ),
        ),
        "write-after-done": (
            done_store,
            done_store + "\n\tparent->remote_result = KD_EXEC_REMOTE_DONE;",
        ),
        "advance-loses-r15": (
            "*regs = node->regs;\n\treturn 0;",
            "*regs = node->regs;\n\tregs->r15 = 0;\n\treturn 0;",
        ),
        "terminal-copy-loses-rax": (
            finish,
            finish.replace(
                "*regs = node->regs;", "*regs = node->regs;\n\t\tregs->ax = 0;"
            ),
        ),
        "native-begin-clobbers-r10": (
            "frame->native_request = NULL;",
            "frame->regs.r10 ^= 1;\n\tframe->native_request = NULL;",
        ),
        "native-ack-clobbers-rbx": (
            native,
            native.replace(
                "request->result = ret < 0 ? ret : 0;",
                "frame->regs.bx ^= 1;\n\t\t\trequest->result = ret < 0 ? ret : 0;",
            ),
        ),
        "native-wait-not-measured": (
            "kd_exe_native_timing_end(mutex, start);",
            "(void)mutex; (void)start; /* injected missing interval */",
        ),
        "native-wait-wrong-backend": (
            "kd_exe_native_timing_end(mutex, start);",
            "kd_exe_native_timing_end(!mutex, start);",
        ),
        "native-wait-loses-error": (
            native, native.replace("\treturn result;", "\treturn result < 0 ? 0 : result;"),
        ),
    }
    with tempfile.TemporaryDirectory(prefix="kdlock-remote-outer-unit-") as directory:
        path = Path(directory)
        (path / "remote_types.h").write_text(types)
        (path / "timing_code.h").write_text(timing_code())
        variants = [("production", None), *mutations.items(), ("bug-only", None)]
        for name, mutation in variants:
            candidate = code
            if mutation:
                before, after = mutation
                assert candidate.count(before) == 1 and before != after, name
                candidate = candidate.replace(before, after)
            (path / "remote_code.h").write_text(candidate)
            binary = path / name
            command = shlex.split(os.environ.get("CC", "cc")) + [
                "-std=gnu11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(path),
                str(ROOT / "tests/unit/remote_outer_fixture.c"),
                "-o",
                str(binary),
            ]
            if mutation:
                command.append("-DKD_REMOTE_MUTATION")
            if name == "bug-only":
                command.append("-DKD_REMOTE_BUG_ONLY")
            subprocess.run(command, check=True, timeout=30)
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True, timeout=10
            )
            if name == "bug-only":
                assert result.returncode == 2 and "BUG line=" in result.stderr, result
                assert "FAIL line=" not in result.stderr, result
                print("remote control: BUG-only exit is not assertion detection")
            elif mutation:
                assert result.returncode == 1 and "FAIL line=" in result.stderr, (
                    name,
                    result,
                )
                print(f"remote mutation detected: {name}")
            else:
                print(result.stdout, end="")
                assert result.returncode == 0, (result.returncode, result.stderr)


if __name__ == "__main__":
    main()
