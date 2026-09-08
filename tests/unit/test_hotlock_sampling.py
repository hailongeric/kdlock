"""Compile actual hot-lock sampling with a deterministic TSC in the guest.

The clock/allocation/atomic primitives are substitutes, not a concurrent kernel
test. The live JIT suite independently requires natural lock promotion.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from test_spin_gate import ROOT, without_includes


def main():
    source = "\n".join(
        without_includes((ROOT / name).read_text())
        for name in ("include/kd_hotlock.h", "kernel_module/kd_hotlock.c")
    )
    with tempfile.TemporaryDirectory(prefix="kdlock-hotlock-sampling-") as directory:
        path = Path(directory)
        (path / "hotlock_production.h").write_text(source)
        binary = path / "sampling"
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
                str(ROOT / "tests/unit/hotlock_sampling_fixture.c"),
                "-o",
                str(binary),
            ],
            check=True,
            timeout=30,
        )
        subprocess.run([str(binary)], check=True, timeout=15)


if __name__ == "__main__":
    main()
