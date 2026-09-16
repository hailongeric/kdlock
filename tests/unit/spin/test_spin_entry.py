"""Guest-only production ticket/gate lifecycle test; no simulated JIT claim."""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from test_spin_gate import ROOT, without_includes
from test_spin_shadow import definition


def main():
    source = (
        definition(
            (ROOT / "include/qspinlock_i.h").read_text(), "struct orig_qspinlock {"
        ).rstrip()
        + ";\n"
    )
    for name in (
        "include/kd_spin_gate.h",
        "kernel_module/kd_spin_gate.c",
        "include/kd_spin_entry.h",
        "kernel_module/kd_spin_entry.c",
    ):
        source += without_includes((ROOT / name).read_text()) + "\n"
    with tempfile.TemporaryDirectory(prefix="kdlock-spin-entry-unit-") as directory:
        path = Path(directory)
        (path / "entry_production.h").write_text(source)
        binary = path / "spin-entry"
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
                str(ROOT / "tests/unit/spin/spin_entry_fixture.c"),
                "-o",
                str(binary),
            ],
            check=True,
            timeout=30,
        )
        subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    main()
