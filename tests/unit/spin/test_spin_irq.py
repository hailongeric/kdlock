"""Guest-only IRQ/BH public-header contracts with recorded kernel primitives.

The real header owns acquisition, release, flags and nesting decisions. IRQ/BH
instructions and the contended finisher are substitutes; real MCS and live
kernel context tests remain separate evidence.
"""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def main():
    header = (ROOT / "include/kd_spin_direct.h").read_text()
    header = re.sub(r"^#include .*$", "", header, flags=re.M)
    kernel = Path(f"/lib/modules/{os.uname().release}/build")
    typecheck = (kernel / "include/linux/typecheck.h").read_text()
    with tempfile.TemporaryDirectory(prefix="kd-spin-irq-") as directory:
        path = Path(directory)
        (path / "irq_production.h").write_text(header)
        (path / "irq_typecheck.h").write_text(typecheck)
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-O2", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
            "-I", str(path), str(ROOT / "tests/unit/spin/spin_irq_fixture.c"),
        ]
        binary = path / "spin-irq"
        subprocess.run(command + ["-o", str(binary)], check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=10)
        # Use the captured kernel's real typecheck macro: narrowing the saved
        # flags lvalue must fail compilation, independently of runtime cases.
        rejected = subprocess.run(
            command + ["-DKD_IRQ_WRONG_FLAGS", "-c", "-o", str(path / "bad.o")],
            capture_output=True, text=True, timeout=30,
        )
        if rejected.returncode == 0 or not re.search(
            r"distinct pointer types|incompatible pointer", rejected.stderr
        ):
            raise AssertionError("wrong flags type was not rejected by typecheck:\n" + rejected.stderr)
        print("PASS IRQ flags: unsigned-long lvalue required by real kernel typecheck")


if __name__ == "__main__":
    main()
