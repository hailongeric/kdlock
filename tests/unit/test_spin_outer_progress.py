"""Guest-only production spin batch/frame/ticket test with a substituted JIT body.

Native L and ticket operations are real extracted code around deterministic
CPU/lock primitives. Capacity-refusal cases fill the real frame allocator through
its API and compare full guest pt_regs and contexts across combiner return.
This is not natural JIT nesting, concurrent kernel or return-assembly execution.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from test_spin_gate import ROOT, without_includes
from test_spin_shadow import definition


def main():
    kernel = Path(f"/lib/modules/{os.uname().release}/build")
    ptrace = (kernel / "arch/x86/include/asm/ptrace.h").read_text()
    ptrace = ptrace.split("#else /* __i386__ */", 1)[1]
    types = definition(ptrace, "struct pt_regs {").rstrip() + ";\n"
    types += (
        definition(
            (ROOT / "include/qspinlock_i.h").read_text(), "struct orig_qspinlock {"
        ).rstrip()
        + ";\n"
    )
    for name in (
        "include/kd_spin_gate.h",
        "include/kd_spin_entry.h",
        "include/kd_call.h",
        "include/kd_exec.h",
        "include/kd_spinlock.h",
    ):
        types += without_includes((ROOT / name).read_text()) + "\n"
    types += (
        "\n".join(
            line
            for line in (ROOT / "include/exe.h").read_text().splitlines()
            if line.startswith("#define KD_EXE_")
        )
        + "\n"
    )
    spin = (ROOT / "kernel_module/kd_spinlock.c").read_text()
    for marker in ("struct shadow_stack {", "struct kd_spin_jit_context {"):
        types += definition(spin, marker).rstrip() + ";\n"
    if "kd_spin_entry_reclaim(" not in types:
        types += "#define kd_spin_entry_reclaim kd_spin_entry_claim\n"
    code = ""
    for name in ("kernel_module/kd_spin_gate.c", "kernel_module/kd_spin_entry.c"):
        code += without_includes((ROOT / name).read_text()) + "\n"
    frame = (ROOT / "kernel_module/kd_exec.c").read_text()
    pool = "\n".join(
        definition(frame, marker)
        for marker in (
            "static bool kd_exec_context_validate(const struct kd_exec_context *ctx)",
            "static struct kd_exec_context *kd_exec_current_context(void)",
            "struct kd_exec_frame *kd_exec_current_frame(void)",
            "bool kd_exec_context_busy(void)",
            "kd_exec_frame_push(const struct pt_regs *regs, unsigned long entry_ip,",
            "int kd_exec_frame_pop(struct kd_exec_frame *frame, struct pt_regs *regs)",
        )
    )
    pool = pool.replace(
        "\nkd_exec_frame_push(", "\nstruct kd_exec_frame *\nkd_exec_frame_push("
    )
    for marker in (
        "static int kd_exec_invariant_failure(void)",
        "static bool kd_exec_frame_state_is_active(int state)",
        "int kd_exec_frame_state(const struct kd_exec_frame *frame)",
        "static void kd_exec_frame_set_state(struct kd_exec_frame *frame, int state)",
        "bool kd_exec_frame_validate(const struct kd_exec_frame *frame)",
        "unsigned int kd_exec_frame_lock_depth(const struct kd_exec_frame *frame)",
        "int kd_exec_frame_set_lock_entries(struct kd_exec_frame *frame,",
        "int kd_exec_frame_set_lock_stack(struct kd_exec_frame *frame,",
        "int kd_exec_frame_lock_mark_released(struct kd_exec_frame *frame,",
        "bool kd_exec_frame_has_unreleased_nested(const struct kd_exec_frame *frame)",
        "bool kd_exec_frame_remote_pending(const struct kd_exec_frame *frame)",
        "bool kd_exec_frame_locks_released(const struct kd_exec_frame *frame)",
        "int kd_exec_remote_native(struct kd_exec_frame *frame)",
        "int kd_exec_remote_complete(struct kd_exec_frame *frame)",
        "void kd_exec_remote_cancel(struct kd_exec_frame *frame)",
        "bool kd_exec_frame_can_complete(const struct kd_exec_frame *frame)",
        "int kd_exec_frame_record_event(struct kd_exec_frame *frame,",
        "int kd_exec_frame_complete(struct kd_exec_frame *frame)",
        "int kd_exec_frame_abort(struct kd_exec_frame *frame)",
    ):
        code += definition(frame, marker) + "\n"
    for marker, prefix in (
        ("static struct qspinlock *kd_spin_word(struct qspinlock *lock)", ""),
        ("static void kd_spin_claim_origin(struct qspinlock *lock)", ""),
        ("static void kd_spin_release_origin(struct qspinlock *lock)", ""),
        (
            "kd_spin_lock_stack_depth(const struct shadow_stack *ptr)",
            "static inline unsigned int\n",
        ),
        (
            "static void kd_spin_capture_combiner_state(struct kd_combiner_state *saved,",
            "",
        ),
        (
            "kd_spin_combiner_state_matches(const struct kd_combiner_state *saved,",
            "static bool\n",
        ),
        ("static inline bool check_irq_node(struct kd_spin_node *node)", ""),
        ("clear_locked_set_completed(struct kd_spin_node *lock)", "static void\n"),
        ("static __always_inline void set_locked(struct qspinlock *lock)", ""),
        (
            "__always_inline static void add_to_local_queue(struct kd_spin_node *node)",
            "#ifdef NUMA_AWARE\n",
        ),
        (
            "get_next_node(struct kd_spin_node *my_node)",
            "static struct kd_spin_node *\n",
        ),
        ("static __always_inline int kd_spin_trylock(struct qspinlock *lock)", ""),
    ):
        code += prefix + definition(spin, marker) + "\n"
        if "add_to_local_queue" in marker:
            code += "#endif\n"
    if "struct kd_spin_batch {" in spin:
        code += definition(spin, "struct kd_spin_batch {").rstrip() + ";\n"
        for name in ("kd_spin_release_outer", "kd_spin_reclaim_outer"):
            marker = next(
                line
                for line in spin.splitlines()
                if line.startswith("static ") and name + "(" in line
            )
            code += definition(spin, marker) + "\n"
    for name, prefix in (
        ("execute_cs", "static int\n"),
        ("run_combiner", "static void\n"),
    ):
        marker = next(line for line in spin.splitlines() if line.startswith(name + "("))
        code += prefix + definition(spin, marker) + "\n"
    code += definition(
        (ROOT / "kernel_module/kd_lock.c").read_text(),
        "int kd_spin_jit_outer_unlock_ooo_ctx(raw_spinlock_t *lock, struct pt_regs *regs,",
    )
    queue = "static int\n" + definition(
        spin, "__kd_spin_lock_longjmp(struct qspinlock *lock, int tail,"
    )
    for marker in (
        "static int kd_spin_prepare_jit_node(struct kd_spin_node *node,",
        "static int kd_spin_advance_jit_node(struct kd_spin_node *node,",
        "static int kd_spin_finish_remote_node(struct kd_spin_node *node,",
        "int kd_spin_nested_lock(struct qspinlock *lock, struct pt_regs *regs,",
    ):
        queue += definition(spin, marker)
    refusal = 'if (!frame) {\n\t\tKD_PR_ERR("spin JIT frame stack overflow'
    cancel = definition(
        frame, "void kd_exec_remote_cancel(struct kd_exec_frame *frame)"
    )
    mutations = {
        "refusal-writes-parent": (
            "pool",
            "ctx->depth >= KD_EXEC_MAX_NESTING",
            "(ctx->depth >= KD_EXEC_MAX_NESTING && (ctx->frames[0].regs.ax = 0, true))",
        ),
        "refusal-publishes-completion": (
            "code",
            refusal,
            refusal.replace("{\n", "{\n\t\tcurr_node->completed = 1;\n"),
        ),
        "refusal-cancels-virtual-parent": (
            "code",
            refusal,
            refusal.replace(
                "{\n",
                "{\n\t\tif (curr_node->jit_waiter)\n"
                "\t\t\tjit_context->requester->remote_result = KD_EXEC_REMOTE_IDLE;\n",
            ),
        ),
        "virtual-native-trampoline": (
            "code",
            "curr_node->jit_retry = !curr_node->jit_waiter &&",
            "curr_node->jit_retry =",
        ),
        "child-cancel-ends-parent-wait": (
            "code",
            cancel,
            cancel.replace(
                "frame->resume_target = NULL;",
                "frame->resume_target = NULL;\n"
                "\tsmp_store_release(&parent->remote_result, KD_EXEC_REMOTE_IDLE);",
            ),
        ),
    }
    with tempfile.TemporaryDirectory(prefix="kdlock-spin-outer-unit-") as directory:
        path = Path(directory)
        (path / "spin_outer_types.h").write_text(types)
        (path / "spin_queue_return_production.h").write_text(queue)
        variants = [("production", 0, None), ("production", 1, None)]
        variants.extend((name, 1, mutation) for name, mutation in mutations.items())
        variants.append(("bug-only-control", 1, None))
        for name, numa, mutation in variants:
            candidates = {"pool": pool, "code": code}
            if mutation:
                target, before, after = mutation
                assert candidates[target].count(before) == 1, name
                candidates[target] = candidates[target].replace(before, after)
            (path / "spin_frame_pool_production.h").write_text(candidates["pool"])
            (path / "spin_outer_production.h").write_text(candidates["code"])
            binary = path / f"outer-{numa}-{name}"
            command = shlex.split(os.environ.get("CC", "cc")) + [
                "-std=gnu11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wno-sign-compare",
                "-I",
                str(path),
                str(ROOT / "tests/unit/spin_outer_progress_fixture.c"),
                "-o",
                str(binary),
            ]
            if numa:
                command.append("-DNUMA_AWARE")
            if mutation:
                # Stop at an assertion before corrupt state reaches queue cleanup.
                command.append("-DKD_OUTER_MUTATION")
            if name == "bug-only-control":
                command.extend(("-DKD_OUTER_MUTATION", "-DKD_OUTER_BUG_ONLY"))
            subprocess.run(command, check=True, timeout=30)
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True, check=False, timeout=10
            )
            if name == "bug-only-control":
                assert result.returncode == 2 and "BUG mode=" in result.stderr, result
                assert "FAIL mode=" not in result.stderr, result
                print(
                    "spin refusal control: BUG-only exit is not an assertion detection"
                )
            elif mutation:
                assert result.returncode == 1 and "FAIL mode=" in result.stderr, (
                    name,
                    result.returncode,
                    result.stdout,
                    result.stderr,
                )
                print(f"spin refusal mutation detected: {name}")
            else:
                print(result.stdout, end="")
                assert result.returncode == 0, (result.returncode, result.stderr)


if __name__ == "__main__":
    main()
