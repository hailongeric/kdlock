"""Guest-only production spin batch/frame/ticket test with a substituted JIT body.

KD word and ticket operations are real extracted code around deterministic
CPU/lock primitives. Capacity-refusal cases fill the real frame allocator through
its API and compare full guest pt_regs and contexts across combiner return.
This is not natural JIT nesting, concurrent kernel or return-assembly execution.
The existing fixture also observes release publication before node reuse; its
primitive substitute checks API/packet ordering, not a hardware memory litmus.
The removed map-exhaustion cases remain in Git history. Ticket capacity,
PENDING recovery and frame retirement still use production code.
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
    kernel = Path(f"/lib/modules/{os.uname().release}/build")
    ptrace = (kernel / "arch/x86/include/asm/ptrace.h").read_text()
    ptrace = ptrace.split("#else /* __i386__ */", 1)[1]
    types = definition(ptrace, "struct pt_regs {").rstrip() + ";\n"
    for name in (
        "include/kd_spin_entry.h",
        "include/kd_call.h",
        "include/kd_exec.h",
        "include/kd_spinlock.h",
    ):
        types += without_includes(read_source((ROOT / name))) + "\n"
    types += (
        "\n".join(
            line
            for line in read_source((ROOT / "include/exe.h")).splitlines()
            if line.startswith("#define KD_EXE_")
        )
        + "\n"
    )
    for marker in ("enum kd_entry_abi {", "enum kd_packet_state {"):
        types += definition((ROOT / "include/exe_info.h").read_text(), marker).rstrip() + ";\n"
    types += (ROOT / "include/kd_jit_batch.h").read_text()
    spin = read_source((ROOT / "kernel_module/kd_spinlock.c"))
    for marker in ("struct shadow_stack {", "struct kd_spin_jit_context {", "struct kd_spin_request {"):
        types += definition(spin, marker).rstrip() + ";\n"
    if "kd_spin_entry_reclaim(" not in types:
        types += "#define kd_spin_entry_reclaim kd_spin_entry_claim\n"
    code = read_source(ROOT / "kernel_module/spin/request.inc") + definition(spin, "static void kd_spin_prepare_regs(struct kd_spin_node *node)") + "\n"
    for name in ("kernel_module/kd_spin_entry.c",):
        code += without_includes(read_source((ROOT / name))) + "\n"
    frame = read_source((ROOT / "kernel_module/kd_exec.c"))
    pool = "\n".join(
        definition(frame, marker)
        for marker in (
            "static bool kd_exec_context_validate(const struct kd_exec_context *ctx)",
            "static struct kd_exec_context *kd_exec_current_context(void)",
            "struct kd_exec_frame *kd_exec_current_frame(void)",
            "bool kd_exec_context_busy(void)",
            "void kd_exec_frame_prepare_complex(struct kd_exec_frame *frame)",
        "void kd_exec_frame_prepare(struct kd_exec_frame *frame, unsigned long entry_ip,",
            "int kd_exec_frame_bind(struct kd_exec_frame *frame, unsigned int lock_depth,",
            "static struct kd_exec_frame *kd_exec_frame_push_internal(",
            "kd_exec_frame_push(const struct pt_regs *regs, unsigned long entry_ip,",
            "kd_exec_frame_push_borrowed(struct pt_regs *regs, unsigned long entry_ip,",
            "int kd_exec_frame_pop(struct kd_exec_frame *frame, struct pt_regs *regs)",
        )
    )
    pool = pool.replace(
        "\nkd_exec_frame_push(", "\nstruct kd_exec_frame *\nkd_exec_frame_push("
    )
    pool = pool.replace("\nkd_exec_frame_push_borrowed(", "\nstruct kd_exec_frame *\nkd_exec_frame_push_borrowed(")
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
        "int kd_exec_frame_complete_single_spin(struct kd_exec_frame *frame)",
        "int kd_exec_frame_retire_single_spin(struct kd_exec_frame *frame)",
        "int kd_exec_frame_abort(struct kd_exec_frame *frame)",
    ):
        code += definition(frame, marker) + "\n"
    for marker, prefix in (
        ("static struct qspinlock *kd_spin_request_word(const struct kd_spin_ref *ref)", ""),
        ("static struct qspinlock *kd_spin_word(struct qspinlock *lock)", ""),
        ("static void kd_spin_claim_origin(const struct kd_spin_request *request)", ""),
        ("static void kd_spin_release_origin(struct kd_spin_request *request)", ""),
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
        ("void kd_spin_jit_prepare_complex(struct kd_exec_frame *frame)", ""),
        ("clear_locked_set_completed(struct kd_spin_node *lock)", "static void\n"),
        ("static __always_inline void set_locked(struct qspinlock *word)", ""),
        (
            "__always_inline static void add_to_local_queue(struct kd_spin_node *node)",
            "#ifdef NUMA_AWARE\n",
        ),
        (
            "get_next_node(struct kd_spin_node *my_node)",
            "static struct kd_spin_node *\n",
        ),
        ("static __always_inline int kd_spin_trylock(struct qspinlock *word)", ""),
    ):
        code += prefix + definition(spin, marker) + "\n"
        if "add_to_local_queue" in marker:
            code += "#endif\n"
    code += definition(spin, "static struct kd_spin_node *kd_spin_linked_successor(struct qspinlock *word,")
    if "struct kd_spin_batch {" in spin:
        code += definition(spin, "struct kd_spin_batch {").rstrip() + ";\n"
        code += "static struct kd_exe_info *\n" + definition(
            spin, "kd_spin_batch_lookup(struct kd_spin_batch *batch, unsigned long entry_ip)"
        )
        code += "static struct kd_exe_info *\n" + definition(
            spin, "kd_spin_batch_find_ready(struct kd_spin_batch *batch, unsigned long entry_ip)"
        )
        for name in ("kd_spin_release_outer", "kd_spin_reclaim_outer"):
            marker = next(
                line
                for line in spin.splitlines()
                if line.startswith("static ") and name + "(" in line
            )
            code += definition(spin, marker) + "\n"
    code += definition(spin, "static void kd_spin_batch_run(void *opaque)")
    for name, prefix in (
        ("execute_cs", "static int\n"),
        ("run_combiner", "static void\n"),
    ):
        marker = next(line for line in spin.splitlines() if line.startswith(name + "("))
        part = definition(spin, marker)
        if name == "execute_cs":
            # Model the omitted enqueue producer, using its production decoder.
            part = part.replace("\tstruct qspinlock *word = batch->request->word;", '\tstruct pt_regs *packet = curr_node->execution->frame.regs_ref;\n\tif (!curr_node->execution->jit_waiter && !curr_node->execution->native_regs_decoded)\n\t\tkd_spin_prepare_regs(curr_node);\n\tkd_exec_frame_prepare(&curr_node->execution->frame,\n\t\tcurr_node->execution->jit_waiter ? curr_node->execution->jit_context->requester->entry_ip : packet->ip,\n\t\t(unsigned long)lock, curr_node->execution->frame.gsbase,\n\t\tcurr_node->execution->frame.logical_task);\n\tcurr_node->execution->frame.regs_ref = packet;\n\tstruct qspinlock *word = batch->request->word;', 1)
        code += prefix + part + "\n"
    code += definition(
        read_source((ROOT / "kernel_module/kd_lock.c")),
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
    refusal = 'if (kd_exec_frame_bind(frame, frame_lock_depth, true)) {\n\t\tKD_PR_ERR("spin JIT frame stack overflow'
    cancel = definition(
        frame, "void kd_exec_remote_cancel(struct kd_exec_frame *frame)"
    )
    mutations = {
        "tail-before-link-misclassified": (
            "code",
            "if (tail && decode_tail(tail) != node) {",
            "if (tail && decode_tail(tail) != node && false) {",
        ),
        "completion-plain-write": (
            "code",
            "smp_store_release(&lock->locked_completed, 1);",
            "WRITE_ONCE(lock->locked_completed, 1);",
        ),
        "early-handoff-plain-write": (
            "code",
            "smp_store_release(&curr_node->locked, false);",
            "curr_node->locked = false;",
        ),
        "batch-handoff-plain-write": (
            "code",
            "smp_store_release(&next_node->locked, false);",
            "next_node->locked = false;",
        ),
        "completion-packet-not-ready": (
            "code",
            "smp_store_release(&lock->locked_completed, 1);",
            "lock->execution->frame.regs_ref->ax ^= 1;\n\t"
            "smp_store_release(&lock->locked_completed, 1);",
        ),
        "packet-overwrite-after-wake": (
            "code",
            "smp_store_release(&lock->locked_completed, 1);",
            "smp_store_release(&lock->locked_completed, 1);\n\t"
            "lock->execution->frame.regs_ref->ax = 0;",
        ),
        "refusal-writes-parent": (
            "pool",
            "\t    lock_depth > KD_EXEC_MAX_LOCK_DEPTH ||\n\t    ctx->depth >= KD_EXEC_MAX_NESTING",
            "\t    lock_depth > KD_EXEC_MAX_LOCK_DEPTH ||\n\t    (ctx->depth >= KD_EXEC_MAX_NESTING && (ctx->frames[0].regs.ax = 0, true))",
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
                "{\n\t\tif (curr_node->execution->jit_waiter)\n"
                "\t\t\tjit_context->requester->remote_result = KD_EXEC_REMOTE_IDLE;\n",
            ),
        ),
        "virtual-native-trampoline": (
            "code",
            "curr_node->execution->jit_retry = !curr_node->execution->jit_waiter &&",
            "curr_node->execution->jit_retry =",
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
    code = code.replace("per_cpu_ptr(&kd_spin_fast_cpu, cpu)", "per_cpu_ptr(kd_spin_fast_cpu, cpu)")
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
                str(ROOT / "tests/unit/spin/spin_outer_progress_fixture.c"),
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
