"""Guest-only production ticket/gate lifecycle test; no simulated JIT claim."""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, without_includes
from test_spin_shadow import definition


def main():
    source = ""
    for name in (
        "include/kd_spin_entry.h",
        "kernel_module/kd_spin_entry.c",
    ):
        source += without_includes((ROOT / name).read_text()) + "\n"
    source = source.replace("per_cpu_ptr(&kd_spin_fast_cpu, cpu)", "per_cpu_ptr(kd_spin_fast_cpu, cpu)")
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
