"""Guest-only extraction of frame/ancestor-unlock code with deterministic CPUs."""

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
    with tempfile.TemporaryDirectory(prefix="kdlock-remote-outer-unit-") as directory:
        path = Path(directory)
        (path / "remote_types.h").write_text(types)
        (path / "remote_code.h").write_text(code)
        binary = path / "remote"
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
                str(ROOT / "tests/unit/remote_outer_fixture.c"),
                "-o",
                str(binary),
            ],
            check=True,
            timeout=30,
        )
        subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    main()
