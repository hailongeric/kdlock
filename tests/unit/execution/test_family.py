"""Guest-only exact family references and bounded reached-source cache checks."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT, read_source, without_includes


def main():
    production = "\n".join(without_includes(read_source(ROOT / name)) for name in (
        "include/kd_family.h", "kernel_module/kd_family.c"))
    with tempfile.TemporaryDirectory(prefix="kd-family-") as temporary:
        directory = Path(temporary)
        (directory / "production.h").write_text(production)
        binary = directory / "family"
        subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
            "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
            "-I", str(directory),
            str(ROOT / "tests/unit/execution/family_fixture.c"),
            "-o", str(binary),
        ], check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=30)


if __name__ == "__main__":
    main()
