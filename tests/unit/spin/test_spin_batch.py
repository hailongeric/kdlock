"""Guest-only batch cache, prefetch and drained per-CPU accounting checks.

Compile production helpers and layouts with deterministic CPU/publication
primitives. This checks invalidation and hint addresses, not hardware cache
latency or concurrent kernel ordering; live nested tests cover the full path.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import read_source
from test_spin_shadow import ROOT, definition


def main():
    spin = read_source(ROOT / "kernel_module/kd_spinlock.c")
    registry = read_source(ROOT / "kernel_module/execution/registry_lifecycle.inc")
    kernel = Path(f"/lib/modules/{os.uname().release}/build")
    ptrace = (kernel / "arch/x86/include/asm/ptrace.h").read_text()
    types = definition(ptrace.split("#else /* __i386__ */", 1)[1], "struct pt_regs {").rstrip() + ";\n"
    types += (ROOT / "include/exe_info.h").read_text()
    types += (ROOT / "include/kd_jit_batch.h").read_text()
    types += "\n#define KD_EXEC_MAX_LOCK_DEPTH 8\n#define KD_SPIN_DIAG_SLOTS 32\n"
    types += "struct kd_exec_frame;\n"
    for source, markers in (
        (read_source(ROOT / "include/kd_spin_entry.h"), ("struct kd_spin_ref {",)),
        (read_source(ROOT / "include/kd_call.h"), ("enum kd_call_phase {", "struct kd_call_state {")),
        (read_source(ROOT / "include/kd_exec.h"), (
            "enum kd_exec_frame_state {", "enum kd_exec_lock_kind {", "struct kd_combiner_state {",
            "enum kd_request_role {", "struct kd_exec_outer_unlock {", "struct kd_exec_frame {")),
        (read_source(ROOT / "include/kd_spinlock.h"), (
            "enum kd_spin_cont_kind {", "enum kd_spin_resume_result {", "struct kd_spin_jit_context {", "struct kd_spin_continuation {", "struct kd_spin_node {")),
        (spin, ("struct kd_spin_batch {", "enum kd_spin_diag_event {",
                "struct kd_spin_diag_slot {", "struct kd_spin_diag_counts {",
                "struct kd_spin_diag_cpu {")),
    ):
        for marker in markers:
            types += definition(source, marker).rstrip() + ";\n"
    body = ""
    for source, marker, prefix in (
        (registry, "bool kd_exe_entry_is_ready(const struct kd_exe_info *exe, unsigned int pid,", ""),
        (registry, "struct kd_exe_info *kd_exe_find_ready(unsigned int pid, unsigned long ip)", ""),
        (spin, "kd_spin_batch_lookup(struct kd_spin_batch *batch, unsigned long entry_ip)", "static struct kd_exe_info *\n"),
        (spin, "kd_spin_batch_find_ready(struct kd_spin_batch *batch, unsigned long entry_ip)", "static struct kd_exe_info *\n"),
        (spin, "static inline bool check_irq_node(struct kd_spin_node *node)", ""),
        (spin, "static void kd_spin_prepare_prefetch(struct kd_spin_node *node,", ""),
        (spin, "static void kd_spin_prefetch_lookup(struct kd_spin_node *node)", ""),
        (spin, "static void kd_spin_prefetch_request(struct kd_spin_node *node)", ""),
        (spin, "static __always_inline void kd_spin_diag_invariant_failure(void)", ""),
        (spin, "static struct kd_spin_diag_slot *kd_spin_diag_find(unsigned long addr)", ""),
        (spin, "static void kd_spin_diag_record_slot(struct kd_spin_diag_slot *slot,", ""),
        (spin, "static void kd_spin_diag_record_addr(unsigned long addr,", ""),
        (spin, "static void kd_spin_debug_combiner(struct kd_spin_diag_slot *slot, unsigned int depth)", ""),
        (spin, "static void kd_spin_debug_jit_success(struct kd_spin_diag_slot *slot,", ""),
        (spin, "kd_spin_debug_jit_success_simple(struct kd_spin_diag_slot *slot)", "static __always_inline void\n"),
        (spin, "static void kd_spin_diag_sum(unsigned int index, struct kd_spin_diag_counts *sum)", ""),
        (spin, "static void kd_spin_diag_waiter_enter(struct kd_spin_diag_slot *slot)", ""),
        (spin, "static void kd_spin_diag_waiter_exit(struct kd_spin_diag_slot *slot)", ""),
        (spin, "static s64 kd_spin_diag_waiter_balance(unsigned int index)", ""),
        (spin, "static u64 kd_spin_diag_waiter_mismatches(void)", ""),
        (spin, "int kd_spin_debug_waiter_count(raw_spinlock_t *lock)", ""),
        (spin, "static bool kd_spin_jit_is_disabled(const struct kd_spin_diag_slot *slot)", ""),
    ):
        body += prefix + definition(source, marker) + "\n"
    # Preserve the final diagnostic oracle after independent lifecycle drain.
    assert "invariant_failures += kd_spin_diag_waiter_mismatches();" in spin
    assert "(long long)(sum.waiter_enter - sum.waiter_exit)" in spin
    frame = read_source(ROOT / "kernel_module/kd_exec.c")
    for marker in (
        "int kd_exec_frame_complete_single_spin(struct kd_exec_frame *frame)",
        "int kd_exec_frame_retire_single_spin(struct kd_exec_frame *frame)",
    ):
        body += definition(frame, marker) + "\n"
    with tempfile.TemporaryDirectory(prefix="kdlock-spin-batch-") as directory:
        path = Path(directory)
        (path / "spin_batch_types.h").write_text(types)
        (path / "spin_batch_production.h").write_text(body)
        binary = path / "batch"
        subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
            "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-Wno-sign-compare", "-I", str(path),
            str(ROOT / "tests/unit/spin/spin_batch_fixture.c"), "-o", str(binary),
        ], check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    main()
