"""Execute the production instruction-marker restore in guest userspace.

This checks x86 registers, arithmetic flags, stack position, and preservation
of user-observable control flags. Kernel ownership/drain need the live probe.
"""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT


def main():
    source = (ROOT / "kernel_module/spin/restore.inc").read_text()
    code = source[source.index("#define KD_RESTORE_REG_OPERANDS"):
                  source.index("#pragma GCC pop_options") + len("#pragma GCC pop_options")]
    with tempfile.TemporaryDirectory(prefix="kd-escape-restore-") as directory:
        temporary = Path(directory)
        (temporary / "production.h").write_text(code)
        for thunk in (None, "CONFIG_RETHUNK", "CONFIG_MITIGATION_RETHUNK"):
            binary = temporary / (thunk or "direct")
            subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
                "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-parameter", "-fno-stack-protector", "-no-pie",
                *(["-D" + thunk + "=1"] if thunk else []),
                "-I", str(ROOT / "include"), "-I", str(temporary),
                str(ROOT / "tests/unit/execution/native_escape_restore_fixture.c"),
                "-o", str(binary)], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=20)


if __name__ == "__main__":
    main()
