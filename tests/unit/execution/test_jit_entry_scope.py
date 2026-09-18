"""Exercise production entry/refusal and typed hostcall decisions.

Generated predicate semantics are independently executed by test_context_guards.
This fixture checks the real high-level consumer, including progressed exits
and logical remote admission, without loading kernel modules. Wrapper/service
primitives are substitutes; the allowlist, adapters and CALL advance are real.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import read_source

from test_exe_registry import lookup_code, timing_code
from test_exec_capacity import production
from test_spin_gate import ROOT, without_includes
from test_spin_shadow import definition


def main():
    types, _ = production()
    types += without_includes(read_source((ROOT / "include/exe_info.h")))
    types += without_includes(read_source(ROOT / "include/kd_jit_batch.h"))
    types += '#include "kd_hostcall.h"\n'
    executor = read_source((ROOT / "kernel_module/exe.c"))
    types += definition(executor, "struct kd_hostcall_desc {").rstrip() + ";\n"
    for path in ("include/exe.h", "kernel_module/exe.c"):
        types += (
            "\n".join(
                line
                for line in read_source((ROOT / path)).splitlines()
                if line.startswith("#define KD_EXE_")
            )
            + "\n"
        )
    code = ""
    for path, signatures in {
        "kernel_module/kd_exec.c": (
            "int kd_exec_frame_state(const struct kd_exec_frame *frame)",
            "static bool kd_exec_frame_state_is_active(int state)",
            "bool kd_exec_frame_validate(const struct kd_exec_frame *frame)",
            "bool kd_exec_frame_has_unreleased_nested(const struct kd_exec_frame *frame)",
            "bool kd_exec_frame_can_borrow_locks(const struct kd_exec_frame *frame)",
            "bool kd_exec_frame_remote_pending(const struct kd_exec_frame *frame)",
            "static void kd_exec_frame_set_state(struct kd_exec_frame *frame, int state)",
            "void kd_exec_frame_save_continuation(struct kd_exec_frame *frame,",
        ),
        "kernel_module/exe.c": (
            "static int kd_jit_timed_control(struct pt_regs *regs, unsigned long outer)",
            "static int advance_after_known_call(struct pt_regs *regs)",
            "static int advance_and_save_continuation(struct kd_exec_frame *frame,",
            "static void kd_jit_log_hl_error(const char *reason,",
            "static bool kd_jit_entry_has_scope(const struct kd_exec_frame *frame,",
            "static int kd_jit_call_limit_native(struct kd_exec_frame *frame,",
            "static void kd_exe_note_body(unsigned long entry_ip, unsigned long outer_lock_addr,",
            "static bool kd_jit_image_matches(const struct kd_exe_info *exe,",
            "static void kd_jit_prepare_clobber(struct kd_jit_batch_call *call,",
            "bool kd_exe_spin_batch_prepare(struct kd_exe_info *exe,",
            "static int kd_exe_dispatch(struct kd_exe_info *exe, struct pt_regs *regs,",
            "int kd_exe_on_call_hl_entry(struct kd_exe_info *exe, struct pt_regs *regs,",
            "int kd_exe_spin_batch_resume(struct kd_exe_info *exe,",
        ),
    }.items():
        source = read_source((ROOT / path))
        code += "\n".join(definition(source, name) for name in signatures) + "\n"
    # Include the production manifest/table and adapters, substituting only the
    # service primitives. A handwritten dispatcher would not detect policy drift.
    hostcalls = "".join(
        definition(executor, name)
        for name in (
            "static int kd_hostcall_invoke_ktime_get(struct pt_regs *regs)",
            "static int kd_hostcall_invoke_ktime_get_ns(struct pt_regs *regs)",
            "static int kd_hostcall_invoke_int_sqrt(struct pt_regs *regs)",
        )
    )
    hostcalls += executor[
        executor.index("static struct kd_hostcall_desc kd_hostcalls[] = {") : executor.index(
            "static const struct kd_hostcall_desc *kd_hostcall_lookup"
        )
    ]
    for name in (
        "static const struct kd_hostcall_desc *kd_hostcall_lookup(unsigned long addr)",
        "static int kd_hostcall_validate(const struct kd_hostcall_desc *service)",
        "static int kd_hostcall_dispatch(struct pt_regs *regs)",
    ):
        hostcalls += definition(executor, name)
    # Instrument only lookup entry; keep the production probe/ready decisions.
    lookup = lookup_code().replace(
        "\tpos = zz_hash(pid, ip) % KD_MAX_EXE;",
        "\tregistry_lookups++;\n\tpos = zz_hash(pid, ip) % KD_MAX_EXE;",
    )
    mutations = {
        "dispatch-rehashes-entry": (
            "if (!pending && !kd_exe_entry_is_ready(exe, 0, entry_ip))",
            "if (!kd_exe_is_ready(0, entry_ip))",
        ),
        "dispatch-reuses-old-ready-result": (
            "if (!pending && !kd_exe_entry_is_ready(exe, 0, entry_ip))",
            "if (!exe)",
        ),
        "ready-ignores-closing": (
            "if (!exe || !ip || !kd_source_is_open())",
            "if (!exe || !ip || (!kd_source_is_open() && false))",
        ),
        "ready-plain-status-read": (
            "if (smp_load_acquire(&exe->status_code) != KD_EXE_NORMAL)",
            "if (READ_ONCE(exe->status_code) != KD_EXE_NORMAL)",
        ),
        "timing-clock-ignores-disable": (
            "unlikely(kd_jit_timing) ? ktime_get_ns() : 0",
            "ktime_get_ns()",
        ),
        "timing-wrapper-not-counted": (
            "kd_jit_timing_end(KD_JIT_TIME_WRAPPER, boundary_start);",
            "(void)boundary_start;",
        ),
        "timing-overflow-not-marked": (
            "atomic_set(&stat->invalid, 1);",
            "atomic_set(&stat->invalid, 0);",
        ),
        "timing-hostcall-misclassified": (
            "kd_jit_timing_end(KD_JIT_TIME_HOSTCALL, boundary_start);",
            "kd_jit_timing_end(KD_JIT_TIME_CONTROL, boundary_start);",
        ),
        "scalar-argument-truncated": (
            "int_sqrt(regs->di)",
            "int_sqrt((unsigned int)regs->di)",
        ),
        "scalar-wrong-argument-register": (
            "int_sqrt(regs->di)",
            "int_sqrt(regs->si)",
        ),
        "scalar-result-sign-extended": (
            "regs->ax = int_sqrt(regs->di);",
            "regs->ax = (long)(int)int_sqrt(regs->di);",
        ),
        "service-flags-bypassed": (
            "if ((service->flags & required_flags) != required_flags)",
            "if (false && (service->flags & required_flags) != required_flags)",
        ),
        "unresolved-service-matched": (
            "kd_hostcalls[i].addr && kd_hostcalls[i].addr == addr",
            "kd_hostcalls[i].addr == addr",
        ),
        "shared-service-budget-bypassed": (
            "continuation_count >= KD_EXE_HL_MAX_CONTINUATIONS) {",
            "(false && continuation_count >= KD_EXE_HL_MAX_CONTINUATIONS)) {",
        ),
        "service-return-not-consumed": (
            "regs->sp += sizeof(unsigned long);",
            "regs->sp += 0;",
        ),
        "service-error-ignored": (
            "if (call_ret) {\n\t\t\t\tif (call_ret == -ENOENT",
            "if (false && call_ret) {\n\t\t\t\tif (call_ret == -ENOENT",
        ),
        "service-error-allows-replay": (
            "atomic64_inc(&kd_hostcall_failed);",
            "{ frame->executed = false; atomic64_inc(&kd_hostcall_failed); }",
        ),
        "quota-invokes-excess-service": (
            "kd_hostcall_validate(kd_hostcall_lookup(regs->ip))",
            "kd_hostcall_dispatch(regs)",
        ),
        "quota-consumes-pending-return": (
            "frame->control_call.phase = KD_CALL_NONE;",
            "frame->control_call.phase = KD_CALL_NONE; regs->sp += sizeof(unsigned long);",
        ),
        "quota-retains-stale-control-phase": (
            "frame->control_call.phase = KD_CALL_NONE;",
            "frame->control_call.phase = KD_CALL_COMPLETE;",
        ),
        "quota-skips-return-source-pin": (
            "ret = kd_source_pin_target(return_ip);",
            "ret = 0;",
        ),
        "quota-requests-callee-learning": (
            "kd_exec_frame_save_continuation(frame, regs);\n\tpr_warn_ratelimited(",
            "kd_exec_frame_save_continuation(frame, regs);\n"
            "\tkd_exe_publish_status(kd_get_exe(0, frame->entry_ip), KD_EXE_CALL_MISS);\n"
            "\tpr_warn_ratelimited(",
        ),
    }
    with tempfile.TemporaryDirectory(prefix="kdlock-jit-entry-scope-") as tmp:
        directory = Path(tmp)
        (directory / "frame_types.h").write_text(types)
        for name, mutation in [("production", None), *mutations.items()]:
            sources = {"frame_code.h": code, "hostcall_code.h": hostcalls,
                       "timing_code.h": timing_code(), "registry_lookup.h": lookup}
            if mutation:
                before, after = mutation
                count = sum(source.count(before) for source in sources.values())
                # The error counter occurs on both invoke and return failure.
                assert count == (2 if name in ("service-error-allows-replay",
                                               "timing-overflow-not-marked") else 1)
                sources = {
                    path: text.replace(before, after)
                    for path, text in sources.items()
                }
            for path, source in sources.items():
                (directory / path).write_text(source)
            binary = directory / name
            subprocess.run(
                shlex.split(os.environ.get("CC", "cc"))
                + [
                    "-std=gnu11",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    *(["-DKD_ENTRY_MUTATION"] if mutation else []),
                    "-I",
                    str(directory),
                    "-I",
                    str(ROOT / "include"),
                    str(ROOT / "tests/unit/execution/jit_entry_scope_fixture.c"),
                    "-o",
                    str(binary),
                ],
                check=True,
                timeout=30,
            )
            result = subprocess.run(
                [str(binary)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            # Compile failures, crashes and timeouts cannot count as detection.
            if mutation:
                assert result.returncode == 1 and "FAIL line" in result.stderr, (
                    name,
                    result.returncode,
                    result.stdout,
                    result.stderr,
                )
                print(f"entry/hostcall mutation detected: {name}")
            else:
                print(result.stdout, end="")
                assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    main()
