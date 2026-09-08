"""Exercise production entry/refusal decisions; lock primitives are test doubles.

Generated predicate semantics are independently executed by test_context_guards.
This fixture checks the real high-level consumer, including progressed exits
and logical remote admission, without loading kernel modules.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from test_exec_capacity import production
from test_spin_gate import ROOT, without_includes
from test_spin_shadow import definition


def main():
    types, _ = production()
    types += without_includes((ROOT / "include/exe_info.h").read_text())
    for path in ("include/exe.h", "kernel_module/exe.c"):
        types += (
            "\n".join(
                line
                for line in (ROOT / path).read_text().splitlines()
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
        ),
        "kernel_module/exe.c": (
            "static void kd_jit_log_hl_error(const char *reason,",
            "static bool kd_jit_entry_has_scope(const struct kd_exec_frame *frame,",
            "int kd_exe_on_call_hl_entry(struct pt_regs *regs, unsigned long entry_ip,",
        ),
    }.items():
        source = (ROOT / path).read_text()
        code += "\n".join(definition(source, name) for name in signatures) + "\n"
    with tempfile.TemporaryDirectory(prefix="kdlock-jit-entry-scope-") as tmp:
        directory = Path(tmp)
        (directory / "frame_types.h").write_text(types)
        (directory / "frame_code.h").write_text(code)
        binary = directory / "entry-scope"
        subprocess.run(
            shlex.split(os.environ.get("CC", "cc"))
            + [
                "-std=gnu11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(directory),
                str(ROOT / "tests/unit/jit_entry_scope_fixture.c"),
                "-o",
                str(binary),
            ],
            check=True,
            timeout=30,
        )
        subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    main()
