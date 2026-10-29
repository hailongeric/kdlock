"""Guest-only production combiner/outer-event tests with deterministic primitives.

The fixture replaces the JIT body, physical mutex operations, scheduling and
frame pool. The actual kd_mutex_execute_cs/kd_mutex_run_combiner/event functions are compiled.
It checks protocol control flow; the live dependency workload tests real queues.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import read_source

from source_text import ROOT, without_includes
from test_spin_shadow import definition


def main():
    types = (
        definition(
            read_source((ROOT / "include/kd_spin_entry.h")), "struct kd_spin_ref {"
        ).rstrip()
        + ";\n"
    )
    for name in ("include/exe_info.h", "include/kd_call.h", "include/kd_exec.h",
                 "include/kd_mutex_types.h", "include/kd_mutex.h"):
        types += without_includes(read_source((ROOT / name))) + "\n"
    types += without_includes(read_source(ROOT / "include/kd_jit_batch.h")) + "\n"
    # This is a source header, not a generated output. The maintained Linux 7
    # build deliberately separates source from its Kbuild output directory.
    kernel = Path(f"/lib/modules/{os.uname().release}/source")
    types += (kernel / "include/linux/kern_levels.h").read_text() + "\n"
    types += "\n".join(
        line
        for line in read_source((ROOT / "include/exe.h")).splitlines()
        if line.startswith("#define KD_EXE_")
    )
    frame = read_source((ROOT / "kernel_module/kd_exec.c"))
    code = "#define KD_MUTEX_TAIL_CPU_OFFSET 4\n"
    for marker in (
        "static int kd_exec_invariant_failure(void)",
        "static bool kd_exec_frame_state_is_active(int state)",
        "int kd_exec_frame_state(const struct kd_exec_frame *frame)",
        "static void kd_exec_frame_set_state(struct kd_exec_frame *frame, int state)",
        "bool kd_exec_frame_validate(const struct kd_exec_frame *frame)",
        "int kd_exec_frame_set_lock_entries(struct kd_exec_frame *frame,",
        "int kd_exec_frame_lock_mark_released(struct kd_exec_frame *frame,",
        "bool kd_exec_frame_has_unreleased_nested(const struct kd_exec_frame *frame)",
        "bool kd_exec_frame_remote_pending(const struct kd_exec_frame *frame)",
        "bool kd_exec_frame_locks_released(const struct kd_exec_frame *frame)",
        "bool kd_exec_frame_can_complete(const struct kd_exec_frame *frame)",
        "int kd_exec_frame_record_event(struct kd_exec_frame *frame,",
        "int kd_exec_frame_complete(struct kd_exec_frame *frame)",
        "int kd_exec_frame_abort(struct kd_exec_frame *frame)",
    ):
        code += definition(frame, marker) + "\n"
    mutex = read_source((ROOT / "kernel_module/kd_mutex.c"))
    # Compile the real trace macro too: a substitute silently missed ALERT
    # output on the hot path. Keep logging enabled; validate its severity/text.
    start = mutex.index("#ifdef DSM_DEBUG")
    end = mutex.index("#endif", start) + len("#endif")
    code = "#define DSM_DEBUG 1\n" + mutex[start:end] + "\n" + code
    code += '#define MODULE_INFO(...)\n'
    code += without_includes(read_source(ROOT/'kernel_module/mutex/pin_origin.inc'))+'\n'
    code += next(line for line in mutex.splitlines() if line.startswith("#define KD_MUTEX_EXEC_SWAPPED ")) + "\n"
    code += without_includes(read_source(ROOT/'kernel_module/mutex/batch_diag.inc'))+'\n'
    code += definition(mutex, "enum kd_mutex_batch_result {").rstrip() + ";\n"
    if "struct kd_mutex_batch {" in mutex:
        code += definition(mutex, "struct kd_mutex_batch {").rstrip() + ";\n"
    for marker in ("static void kd_mutex_wait_for_result(struct kd_mutex_node *node)",
                   "static __always_inline bool kd_mutex_proxy_request(struct kd_mutex *lock,",
                   "static __always_inline void kd_mutex_proxy_assert_claimed(struct kd_mutex_node *node)"):
        code += definition(mutex, marker) + "\n"
    code += without_includes(read_source(ROOT / "kernel_module/mutex/pin_window.inc")) + "\n"
    for marker in ("static bool kd_mutex_batch_epoch_begin(struct kd_mutex_batch *batch)",
                   "static void kd_mutex_batch_epoch_end(struct kd_mutex_batch *batch, bool keep_current)"):
        code += definition(mutex, marker) + "\n"
    for name in ('kd_mutex_batch_select', 'kd_mutex_batch_rejoin'):
        marker = next(line for line in mutex.splitlines() if line.startswith(name+'('))
        code += 'static struct kd_mutex_node *\n' + definition(mutex, marker)+'\n'
    code += "static struct kd_exe_info *\n" + definition(mutex, "kd_mutex_batch_find_ready(struct kd_mutex_batch *batch, unsigned long ip)") + "\n"
    for marker in (
        "static bool kd_mutex_batch_can_execute(struct kd_mutex_node *node)",
        "static bool kd_mutex_batch_try_retire_current(struct kd_mutex *lock,",
        "static void kd_mutex_batch_retire_current(struct kd_mutex *lock,",
        "static void kd_mutex_prefetch_successor(struct kd_mutex_node *next)",
        "bool kd_mutex_delegation_owned(struct kd_mutex *lock, struct task_struct *task)",
        "static void kd_mutex_claim_origin_node(struct kd_mutex *lock,",
        "static void kd_mutex_wait_and_lock_node(struct kd_mutex *lock,",
        "static void kd_mutex_wait_and_lock(struct kd_mutex *lock)",
    ):
        code += definition(mutex, marker) + "\n"
    code += "int\n" + definition(
        mutex, "_kd_mutex_unlock_checked(struct kd_mutex *lock)"
    )
    if "static int kd_mutex_release_outer(" in mutex:
        marker = next(
            line
            for line in mutex.splitlines()
            if line.startswith("static int kd_mutex_release_outer(")
        )
        code += definition(mutex, marker) + "\n"
    # Match the real signature, including a newly added batch parameter.
    for name, prefix in (
        ("kd_mutex_execute_cs", "static int\n"),
        ("kd_mutex_run_combiner", "static enum kd_mutex_batch_result\n"),
    ):
        marker = next(
            line for line in mutex.splitlines() if line.startswith(name + "(")
        )
        code += prefix + definition(mutex, marker) + "\n"
    # Seed only private fixture state. Exercise the unchanged real FULL-resume
    # path with each valid ring head, including successor slot zero after wrap.
    batch_init = "\tstruct kd_mutex_batch batch = {\n"
    assert code.count(batch_init) == 1
    code = code.replace(batch_init, batch_init + "\t\t.pin_head = test_pin_head,\n", 1)
    # Observe the actual loop/cold boundary without replacing its transitions.
    code = code.replace("\twhile (curr_node) {", "\tnormal_proxy_loop = true;\n\twhile (curr_node) {", 1)
    code = code.replace("\tif (completed_pending_tail) {", "\tnormal_proxy_loop = false;\n\tif (completed_pending_tail) {", 1)
    with tempfile.TemporaryDirectory(prefix="kdlock-mutex-outer-unit-") as directory:
        path = Path(directory)
        (path / "mutex_outer_types.h").write_text(types)
        (path / "mutex_state_production.h").write_text(
            without_includes(read_source(ROOT / "include/kd_mutex_state.h")))
        assert code.count("printk(KERN_INFO ") == 1
        # Each mutant must compile and then fail an explicit assertion. Turning
        # off trace records is not an acceptable cure for serial-console cost.
        candidates = {
            "production": code,
            "alert-regression": code.replace("printk(KERN_INFO ", "printk(KERN_ALERT "),
            "disabled-trace": code.replace("#define DSM_DEBUG 1", "#undef DSM_DEBUG"),
            "claim-does-not-pin": code.replace(
                "smp_store_release(&node->locked, KD_MUTEX_PROXY_CLAIMED);",
                "smp_store_release(&node->locked, KD_MUTEX_PROXY_READY);", 1),
            "reject-completed-full-tail": code.replace("curr_node->packet_state != KD_PACKET_FULL", "true", 1),
            "registration-keeps-pin": code.replace("\t\tkd_mutex_batch_epoch_end(batch, false);", "", 1),
            "resume-keeps-future-pins": code.replace(
                "\t\tkd_mutex_batch_epoch_end(batch, true);\n\t\tKD_MUTEX_PIN_INC(batch, full_resumes);\n\t\tret_flag = kd_exe_mutex_batch_resume(exe, &call);",
                "\t\tKD_MUTEX_PIN_INC(batch, full_resumes);\n\t\tret_flag = kd_exe_mutex_batch_resume(exe, &call);", 1),
            "unpin-before-frame-retirement": code.replace(
                "\tframe_ret = kd_exec_frame_pop(frame, &curr_node->regs);",
                "\tsmp_store_release(&curr_node->locked, KD_MUTEX_WAIT);\n"
                "\tframe_ret = kd_exec_frame_pop(frame, &curr_node->regs);", 1),
        }
        for name, candidate in candidates.items():
            assert name == "production" or candidate != code, name
            (path / "mutex_outer_production.h").write_text(candidate)
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
                    str(ROOT / "tests/unit/mutex/mutex_outer_progress_fixture.c"),
                    "-o",
                    str(binary),
                ],
                check=True,
                timeout=30,
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            if name == "production":
                assert result.returncode == 0, (result.stdout, result.stderr)
                print(result.stdout, end="")
            else:
                expected = 2 if name in {"claim-does-not-pin", "reject-completed-full-tail", "unpin-before-frame-retirement"} else 1
                assert result.returncode == expected and "FAIL mode=" in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print(f"mutation detected: {name}")


if __name__ == "__main__":
    main()
