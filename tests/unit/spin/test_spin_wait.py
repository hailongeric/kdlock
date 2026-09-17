"""Guest-only x86 execution of the production stack-free waiter assembly."""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main():
    source = (ROOT / "kernel_module/spin/wait.inc").read_text()
    with tempfile.TemporaryDirectory(prefix="kdlock-spin-wait-") as directory:
        path = Path(directory)
        (path / "wait_production.h").write_text(source)
        binary = path / "spin-wait"
        subprocess.run(
            shlex.split(os.environ.get("CC", "cc"))
            + [
                "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-mno-red-zone", "-fno-stack-protector", "-pthread",
                "-I", str(path),
                str(ROOT / "tests/unit/spin/spin_wait_fixture.c"),
                "-o", str(binary),
            ],
            check=True, timeout=30,
        )
        subprocess.run([str(binary)], check=True, timeout=15)


if __name__ == "__main__":
    main()
