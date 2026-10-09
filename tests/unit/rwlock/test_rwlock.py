"""Run production rwlock algorithms against C atomics and concurrent callers.

Only kernel primitives and the embedded spin engine are substituted here.
The live workload separately verifies the real queue and returned JIT bodies.
"""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def main():
    header = (ROOT / "include/kd_rwlock.h").read_text()
    header = re.sub(r"^#include .*$", "", header, flags=re.M)
    with tempfile.TemporaryDirectory(prefix="kd-rwlock-") as directory:
        path = Path(directory)
        (path / "rwlock_production.h").write_text(header)
        binary = path / "rwlock"
        subprocess.run([
            "cc", "-O2", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
            "-pthread", "-I", str(path),
            str(ROOT / "tests/unit/rwlock/rwlock_fixture.c"), "-o", str(binary),
        ], check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=40)


if __name__ == "__main__":
    main()
