"""Guest-only production combiner/outer-event tests with deterministic primitives.

The fixture replaces the JIT body, physical mutex operations, scheduling and
frame pool. The actual execute_cs/run_combiner/event functions are compiled.
It checks protocol control flow; the live dependency workload tests real queues.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from test_spin_gate import ROOT, without_includes
from test_spin_shadow import definition


def main():
    types = (
        definition(
            (ROOT / "include/kd_spin_entry.h").read_text(), "struct kd_spin_ref {"
        ).rstrip()
        + ";\n"
    )
    for name in ("include/kd_call.h", "include/kd_exec.h", "include/kd_mutex.h"):
        types += without_includes((ROOT / name).read_text()) + "\n"
    types += "\n".join(
        line
        for line in (ROOT / "include/exe.h").read_text().splitlines()
        if line.startswith("#define KD_EXE_")
    )
    frame = (ROOT / "kernel_module/kd_exec.c").read_text()
    code = ""
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
    mutex = (ROOT / "kernel_module/kd_mutex.c").read_text()
    if "struct kd_mutex_batch {" in mutex:
        code += definition(mutex, "struct kd_mutex_batch {").rstrip() + ";\n"
    for marker in (
        "static void kd_mutex_claim_origin(struct kd_mutex *lock)",
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
        ("execute_cs", "static int\n"),
        ("run_combiner", "static void\n"),
    ):
        marker = next(
            line for line in mutex.splitlines() if line.startswith(name + "(")
        )
        code += prefix + definition(mutex, marker) + "\n"
    with tempfile.TemporaryDirectory(prefix="kdlock-mutex-outer-unit-") as directory:
        path = Path(directory)
        (path / "mutex_outer_types.h").write_text(types)
        (path / "mutex_outer_production.h").write_text(code)
        binary = path / "outer-progress"
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
                str(ROOT / "tests/unit/mutex_outer_progress_fixture.c"),
                "-o",
                str(binary),
            ],
            check=True,
            timeout=30,
        )
        subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    main()
