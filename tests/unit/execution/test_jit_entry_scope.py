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
from source_text import ROOT, without_includes
from test_spin_shadow import definition


def main(executor=None, benchmark=False):
    types, _ = production()
    types += without_includes(read_source((ROOT / "include/exe_info.h")))
    types += without_includes(read_source(ROOT / "include/kd_image.h"))
    types += without_includes(read_source(ROOT / "include/kd_jit_batch.h"))
    types += definition(read_source(ROOT / "include/kd_origin_service.h"),
                        "enum kd_origin_instruction {").rstrip() + ";\n"
    continuation = read_source(ROOT / "include/kd_exec_cont.h")
    for signature in ("enum kd_exec_cont_state {", "struct kd_exec_service_ops {"):
        types += definition(continuation, signature).rstrip() + ";\n"
    types += '#include "kd_hostcall.h"\n'
    if executor is None:
        executor = read_source(ROOT / "kernel_module/exe.c")
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
    terminals = read_source(ROOT / "kernel_module/execution/native_terminals.inc")
    code = terminals[:terminals.index("static void kd_native_terminal_init(void)")]
    code += definition(terminals, "static inline bool kd_native_terminal_target(unsigned long target)")
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
            "int kd_exec_frame_prepare_mutex_complex(struct kd_exec_frame *frame)",
        ),
        "kernel_module/exe.c": (
            "static int kd_jit_timed_control(struct kd_regs *regs, unsigned long outer)",
            "static int advance_after_known_call(struct kd_regs *regs)",
            "static int advance_and_save_continuation(struct kd_exec_frame *frame,",
            "static void kd_jit_log_hl_error(const char *reason,",
            "static bool kd_jit_entry_has_scope(const struct kd_exec_frame *frame,",
            "static int kd_jit_pending_call_native(struct kd_exec_frame *frame,",
            "static int kd_jit_call_limit_native(struct kd_exec_frame *frame,",
            "static int kd_jit_indirect_call_length(unsigned long site, unsigned int *length)",
            "static int kd_jit_indirect_call_native(struct kd_exe_info *exe,",
            "static bool kd_jit_outer_unlock(struct kd_exec_frame *frame,",
            "static int kd_jit_string_prepare(struct kd_exe_info *exe,",
            "static int kd_jit_native_escape_opcode(unsigned long ip)",
            "static bool kd_jit_root_escape_image(const struct kd_exec_frame *frame)",
            "static bool kd_jit_root_escape_owner(const struct kd_exec_frame *frame)",
            "static int kd_jit_native_escape(struct kd_exe_info *exe,",
            "static int kd_jit_origin_instruction(struct kd_exe_info *exe,",
            "static int kd_jit_address_guard(struct kd_exe_info *exe,",
            "static void kd_exe_note_body(unsigned long entry_ip, unsigned long outer_lock_addr,",
            "static void *kd_jit_bound_code(const struct kd_exe_info *exe,",
            "static const struct kd_jit_image *kd_jit_select_image(const struct kd_exe_info *exe,",
            "static inline bool kd_jit_bind_image(const struct kd_exe_info *exe,",
            "static __always_inline bool kd_jit_image_matches(const struct kd_exe_info *exe,",
            "static bool kd_jit_minimal_complete_allowed(const struct kd_exec_frame *frame)",
            "static bool kd_jit_direct_image(const struct kd_exec_frame *frame)",
            "static bool kd_jit_root_escape_entry(const struct kd_exec_frame *frame)",
            "static bool kd_jit_direct_entry(const struct kd_exec_frame *frame)",
            "static bool kd_jit_note_direct_calls(const struct kd_jit_batch_call *call,",
            "static void kd_jit_prepare_clobber(struct kd_jit_batch_call *call,",
            "bool kd_exe_spin_batch_prepare(struct kd_exe_info *exe,",
            "bool kd_exe_spin_batch_completed(const struct kd_jit_batch_call *call,",
            "static int kd_exe_dispatch(struct kd_exe_info *exe, struct kd_regs *regs,",
            "int kd_exe_on_call_hl_entry(struct kd_exe_info *exe, struct kd_regs *regs,",
            "int kd_exe_spin_batch_resume(struct kd_exe_info *exe,",
            "bool kd_exe_mutex_batch_prepare(struct kd_exe_info *exe,",
            "bool kd_exe_mutex_batch_completed(const struct kd_jit_batch_call *call,",
            "int kd_exe_mutex_batch_resume(struct kd_exe_info *exe,",
        ),
    }.items():
        source = executor if path == "kernel_module/exe.c" else read_source(ROOT / path)
        code += "\n".join(definition(source, name) for name in signatures) + "\n"
    code = code.replace("translated(regs, args);",
                        "fixture_wrapper_dispatch(translated, regs, args);")
    # Include the production manifest/table and adapters, substituting only the
    # service primitives. A handwritten dispatcher would not detect policy drift.
    hostcalls = "".join(
        definition(executor, name)
        for name in (
            "static int kd_hostcall_invoke_ktime_get(struct kd_regs *regs)",
            "static int kd_hostcall_invoke_ktime_get_ns(struct kd_regs *regs)",
            "static int kd_hostcall_invoke_int_sqrt(struct kd_regs *regs)",
            "static int kd_hostcall_invoke_strcmp(struct kd_regs *regs)",
            "static int kd_hostcall_invoke_strscpy_pad(struct kd_regs *regs)",
        )
    )
    # Only the native helper invocation is substituted. Production retains
    # ownership, image scope and exact pending CALL-word consumption.
    hostcalls = hostcalls.replace(
        "int (*callee)(const char *, const char *) = (void *)regs->ip;",
        "int (*callee)(const char *, const char *) = fixture_strcmp;",
    )
    hostcalls = hostcalls.replace(
        "long (*callee)(char *, const char *, unsigned long) = (void *)regs->ip;",
        "long (*callee)(char *, const char *, unsigned long) = fixture_strscpy_pad;",
    )
    hostcalls += executor[
        executor.index("static struct kd_hostcall_desc kd_hostcalls[] = {") : executor.index(
            "static const struct kd_hostcall_desc *kd_hostcall_lookup"
        )
    ]
    for name in (
        "static const struct kd_hostcall_desc *kd_hostcall_lookup(unsigned long addr)",
        "static int kd_hostcall_validate(const struct kd_hostcall_desc *service)",
        "static int kd_hostcall_dispatch(struct kd_regs *regs)",
    ):
        hostcalls += definition(executor, name)
    # Instrument only lookup entry; keep the production probe/ready decisions.
    lookup = lookup_code().replace(
        "\tpos = zz_hash(pid, ip) % KD_MAX_EXE;",
        "\tregistry_lookups++;\n\tpos = zz_hash(pid, ip) % KD_MAX_EXE;",
    )
    mutations = {
        "indirect-cs-accepts-four-prefixes": (
            "if (offset == 3)", "if (false)",
        ),
        "indirect-cs-accepts-memory-operand": (
            "if (cs_prefixes && mode != 3)",
            "if (false && cs_prefixes && mode != 3)",
        ),
        "indirect-accepts-jump-opcode": (
            "((modrm >> 3) & 7) != 2",
            "(((modrm >> 3) & 7) != 2 && ((modrm >> 3) & 7) != 4)",
        ),
        "indirect-accepts-wrong-return-word": (
            "(expected_return && return_ip != expected_return)",
            "(expected_return && false)",
        ),
        "indirect-skips-source-site-lease": (
            "ret = kd_source_pin_target(site);", "ret = 0;",
        ),
        "indirect-skips-source-tail-lease": (
            "ret = kd_source_pin_target(continuation - 1);", "ret = 0;",
        ),
        "indirect-learns-terminal-target": (
            "if (!kd_native_terminal_target(regs->ip) && !is_end_point(regs->ip))",
            "if (!is_end_point(regs->ip))",
        ),
        "terminal-target-never-recognized": (
            "kd_native_terminals[i].address == target", "false",
        ),
        "indirect-keeps-source-site-as-restore-tag": (
            "kd_image_report(exe, frame->image, KD_EXE_IJ_MISS, regs->ip, continuation);\n\tregs->orig_ax = 0;",
            "kd_image_report(exe, frame->image, KD_EXE_IJ_MISS, regs->ip, continuation);\n\t(void)regs;",
        ),
        "instruction-marker-still-disables": (
            "atomic64_inc(&kd_native_escape_count);",
            "kd_image_disable(exe); atomic64_inc(&kd_native_escape_count);",
        ),
        "instruction-marker-reopens-entry": (
            "atomic64_inc(&kd_native_escape_count);",
            "exe->status_code = KD_EXE_NORMAL; atomic64_inc(&kd_native_escape_count);",
        ),
        "direct-entry-executor-is-waiter": (
            "frame->logical_task && frame->logical_task != current &&",
            "frame->logical_task &&",
        ),
        "direct-counts-not-observed": (
            "atomic64_add(call->direct_strcmp, &kd_direct_strcmp);",
            "(void)call->direct_strcmp;",
        ),
        "direct-limit-accepts-under-quota": (
            "direct_strcmp == KD_STRCMP_MAX_CALLS)",
            "direct_strcmp <= KD_STRCMP_MAX_CALLS)",
        ),
        "direct-image-needs-pristine-packet": (
            "frame->packet_state == KD_PACKET_MINIMAL && regs == &frame->regs &&",
            "regs == &frame->regs &&",
        ),
        "mutex-generic-skips-materialization": (
            "kd_exec_frame_prepare_mutex_complex(frame))",
            "(false && kd_exec_frame_prepare_mutex_complex(frame)))",
        ),
        "mutex-batch-final-completion-disabled": (
            "call->complete = true;",
            "call->complete = false;",
        ),
        "mutex-batch-wrong-backend-endpoint": (
            "call->unlock = direct_mutex_unlock_addr;",
            "call->unlock = clobber_spin_unlock_addr;",
        ),
        "mutex-batch-uses-private-stack": (
            "call->entry_sp = regs->sp;\n\tcall->entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;",
            "call->entry_sp = frame->regs.sp;\n\tcall->entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;",
        ),
        "mutex-batch-skips-ledger-admission": (
            "!kd_jit_minimal_complete_allowed(frame) ||",
            "(false && !kd_jit_minimal_complete_allowed(frame)) ||",
        ),
        "batch-clobber-uses-legacy-entry": (
            "call->code = (char *)code + (clobber ? KD_JIT_CLOBBER_OFFSET :",
            "call->code = (char *)code + (clobber ? KD_JIT_BATCH_OFFSET :",
        ),
        "batch-clobber-uses-legacy-unlock": (
            "call->unlock = clobber ? clobber_spin_unlock_addr : raw_spin_unlock_addr;",
            "call->unlock = raw_spin_unlock_addr;",
        ),
        "batch-completion-abi-inverted": (
            "call->complete = clobber;",
            "call->complete = !clobber;",
        ),
        "dispatch-rehashes-entry": (
            "if (!pending && !retained_resume && !retained_entry &&\n\t    !kd_exe_entry_is_ready(exe, 0, entry_ip))",
            "if (!pending && !retained_resume && !retained_entry &&\n\t    !kd_exe_is_ready(0, entry_ip))",
        ),
        "dispatch-reuses-old-ready-result": (
            "if (!pending && !retained_resume && !retained_entry &&\n\t    !kd_exe_entry_is_ready(exe, 0, entry_ip))",
            "if (!pending && !retained_resume && !retained_entry &&\n\t    !exe)",
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
            "continuation_count >= KD_EXE_HL_MAX_CONTINUATIONS))) {",
            "(false && continuation_count >= KD_EXE_HL_MAX_CONTINUATIONS)))) {",
        ),
        "service-return-not-consumed": (
            "return_ip = READ_ONCE(*(unsigned long *)regs->sp);\n\tregs->sp += sizeof(unsigned long);",
            "return_ip = READ_ONCE(*(unsigned long *)regs->sp);\n\tregs->sp += 0;",
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
            "frame->control_call.phase = KD_CALL_NONE;\n\tkd_exec_frame_save_continuation(frame, regs);",
            "frame->control_call.phase = KD_CALL_NONE; regs->sp += sizeof(unsigned long);\n\tkd_exec_frame_save_continuation(frame, regs);",
        ),
        "quota-retains-stale-control-phase": (
            "frame->control_call.phase = KD_CALL_NONE;\n\tkd_exec_frame_save_continuation(frame, regs);",
            "frame->control_call.phase = KD_CALL_COMPLETE;\n\tkd_exec_frame_save_continuation(frame, regs);",
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
        "string-result-sign-extended": (
            "regs->ax = (unsigned int)callee(", "regs->ax = (long)callee(",
        ),
        "string-quota-bypassed": (
            "string_count >= KD_STRCMP_MAX_CALLS", "false",
        ),
        "string-requirement-bypassed": (
            "if (!(frame->image->requirements & (service->id == KD_HOSTCALL_STRCMP ?\n\t\tKD_IMAGE_REQUIRE_STRING_SERVICES : KD_IMAGE_REQUIRE_STRING_WRITE)))",
            "if (false)",
        ),
        "string-return-pin-bypassed": (
            "return kd_source_pin_target(*return_ip);", "return 0;",
        ),
        "copy-result-truncated": (
            "regs->ax = (unsigned long)callee(", "regs->ax = (unsigned int)callee(",
        ),
    }
    if benchmark:
        mutations = {
            "completion-omitted": (
                "bench_completion_root && body_reported)",
                "bench_completion_root && body_reported && false)",
            ),
            "completion-counts-native-or-error": (
                "if (ret_flag == KD_EXE_RUN_TO_UNLOCK &&\n\t    bench_completion_root",
                "if (ret_flag != KD_EXE_NO_RUN &&\n\t    bench_completion_root",
            ),
            "completion-without-witness": (
                "bench_completion_root && body_reported)",
                "bench_completion_root)",
            ),
            "completion-counts-remote-suffix": (
                "bench_completion_root = pristine_root && !frame->parent && !frame->depth &&\n\t\t!frame->resume_target && outer_lock_addr;",
                "bench_completion_root = outer_lock_addr;",
            ),
            "completion-counts-physical-child": (
                "bench_completion_root = pristine_root && !frame->parent && !frame->depth &&",
                "bench_completion_root = pristine_root &&",
            ),
            "completion-per-wrapper": (
                "if (resume_after_hostcall)\n\t\t\t\tatomic64_inc(&kd_hostcall_resumed);",
                "if (resume_after_hostcall) {\n\t\t\t\tkd_bench_note_completion(outer_lock_addr);\n\t\t\t\tatomic64_inc(&kd_hostcall_resumed);\n\t\t\t}",
            ),
            "completion-counts-unfinished-batch": (
                "if (kd_entry_abi_spin_clobber(call->entry_abi) ?",
                "kd_bench_note_completion(call->lock);\n\tif (kd_entry_abi_spin_clobber(call->entry_abi) ?",
            ),
        }
    with tempfile.TemporaryDirectory(prefix="kdlock-jit-entry-scope-") as tmp:
        directory = Path(tmp)
        (directory / "frame_types.h").write_text(types)
        if benchmark:
            # Real counter gate, with one CPU slot substituted for per-CPU storage.
            (directory / "bench_code.h").write_text(
                "#define DECLARE_PER_CPU(type, name) extern type name\n"
                "#define this_cpu_inc(name) ((name)++)\n"
                + without_includes((ROOT / "bench/spin_cacheline/provider/kd_bench.h").read_text())
                + "\nbool kd_bench_quiet, kd_bench_complete_probe;\n"
                "unsigned long kd_bench_lock_addr;\n"
                "u64 kd_bench_bodies, kd_bench_completions;\n"
            )
        for name, mutation in [("production", None), *mutations.items()]:
            sources = {"frame_code.h": code, "hostcall_code.h": hostcalls,
                       "timing_code.h": timing_code(), "registry_lookup.h": lookup}
            if mutation:
                before, after = mutation
                count = sum(source.count(before) for source in sources.values())
                # Preparation/invoke/return each record errors. Indirect CALL
                # source pinning has both legacy and retained consumers; the
                # negative control changes both, while this fixture executes
                # the legacy consumer and refuses retained-runtime doubles.
                assert count == (3 if name == "service-error-allows-replay" else
                                 2 if name in ("timing-overflow-not-marked",
                                               "indirect-skips-source-site-lease") else 1), (name, count)
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
                    *(["-DKD_BENCH_COMPLETION_FIXTURE"] if benchmark else []),
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
                assert result.returncode == 0, (
                    name, result.returncode, result.stdout, result.stderr
                )


if __name__ == "__main__":
    main()
