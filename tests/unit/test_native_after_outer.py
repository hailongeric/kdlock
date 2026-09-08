"""Guest-only tests of real frame/known-call code with mocked lock primitives.

These tests do not model Linux ownership, concurrency, or assembly entry/exit.
The OOO kernel workloads separately exercise those paths with real JIT code.
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
    for name in ("include/kd_call.h", "include/kd_exec.h"):
        types += without_includes((ROOT / name).read_text()) + "\n"
    types += "\n".join(
        line
        for line in (ROOT / "include/exe.h").read_text().splitlines()
        if line.startswith("#define KD_EXE_")
    )
    code = ""
    functions = {
        "kernel_module/kd_exec.c": (
            "static int kd_exec_invariant_failure(void)",
            "static bool kd_exec_frame_state_is_active(int state)",
            "int kd_exec_frame_state(const struct kd_exec_frame *frame)",
            "static void kd_exec_frame_set_state(struct kd_exec_frame *frame, int state)",
            "bool kd_exec_frame_validate(const struct kd_exec_frame *frame)",
            "void kd_exec_frame_save_continuation(struct kd_exec_frame *frame,",
            "int kd_exec_frame_lock_pop(struct kd_exec_frame *frame, unsigned long lock_addr)",
            "int kd_exec_frame_lock_mark_released(struct kd_exec_frame *frame,",
            "kd_exec_frame_lock_kind(const struct kd_exec_frame *frame,",
            "void *kd_exec_frame_lock_node(const struct kd_exec_frame *frame,",
            "bool kd_exec_frame_has_unreleased_nested(const struct kd_exec_frame *frame)",
            "bool kd_exec_frame_remote_pending(const struct kd_exec_frame *frame)",
            "bool kd_exec_frame_locks_released(const struct kd_exec_frame *frame)",
            "bool kd_exec_frame_can_complete(const struct kd_exec_frame *frame)",
            "int kd_exec_frame_record_event(struct kd_exec_frame *frame,",
            "int kd_exec_frame_complete(struct kd_exec_frame *frame)",
            "bool kd_exec_frame_can_borrow_locks(const struct kd_exec_frame *frame)",
            "int kd_exec_native_begin(struct kd_exec_frame *frame, bool mutex)",
        ),
        "kernel_module/kd_lock.c": (
            "int kd_mutex_jit_nested_unlock_ctx(struct mutex *lock,",
        ),
        "kernel_module/exe.c": (
            "static int advance_after_known_call(struct pt_regs *regs)",
            "static int advance_and_save_continuation(struct kd_exec_frame *frame,",
            "static int finish_known_lock_call(struct kd_exec_frame *frame,",
            "static int handle_known_call(struct pt_regs *regs,",
        ),
    }
    for name, signatures in functions.items():
        source = (ROOT / name).read_text()
        for signature in signatures:
            if signature.startswith("kd_exec_frame_lock_kind("):
                code += "enum kd_exec_lock_kind\n"
            code += definition(source, signature) + "\n"
    with tempfile.TemporaryDirectory(prefix="kdlock-after-outer-unit-") as directory:
        path = Path(directory)
        (path / "frame_types.h").write_text(types)
        (path / "frame_code.h").write_text(code)
        binary = path / "after-outer"
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
                str(ROOT / "tests/unit/native_after_outer_fixture.c"),
                "-o",
                str(binary),
            ],
            check=True,
            timeout=30,
        )
        subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    main()
