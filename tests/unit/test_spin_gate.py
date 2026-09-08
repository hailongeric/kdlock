"""Compile the production gate map/owner helpers with deterministic primitives.

Run in the guest. This checks state transitions, not native queue concurrency.
"""

import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

from test_spin_shadow import definition

ROOT = Path(__file__).resolve().parents[2]


def without_includes(source):
    return re.sub(r'^#include [<"].*$', "", source, flags=re.MULTILINE)


def main():
    types = (
        definition(
            (ROOT / "include/qspinlock_i.h").read_text(), "struct orig_qspinlock {"
        ).rstrip()
        + ";\n"
    )
    header = without_includes((ROOT / "include/kd_spin_gate.h").read_text())
    source = without_includes((ROOT / "kernel_module/kd_spin_gate.c").read_text())
    with tempfile.TemporaryDirectory(prefix="kdlock-spin-gate-unit-") as directory:
        path = Path(directory)
        (path / "gate_production.h").write_text(types + header + source)
        binary = path / "spin-gate"
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
                str(ROOT / "tests/unit/spin_gate_fixture.c"),
                "-o",
                str(binary),
            ],
            check=True,
            timeout=30,
        )
        subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    main()
