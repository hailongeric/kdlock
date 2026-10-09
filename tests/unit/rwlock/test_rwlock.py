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
        release = (ROOT / "kernel_module/spin/direct.inc").read_text()
        release = release[release.index('void\nkd_rwlock_fast_write_unlock('):
                          release.index('EXPORT_SYMBOL_GPL(kd_rwlock_fast_write_unlock)')]
        (path / "rwlock_native_release.h").write_text(release)
        prelude = (ROOT / "kernel_module/spin/combiner.inc").read_text()
        prelude = prelude[prelude.index('static void kd_spin_rw_begin('):
                          prelude.index('#include "execute.inc"')]
        (path / "rwlock_prelude.h").write_text(prelude)
        binary = path / "rwlock"
        subprocess.run([
            "cc", "-O2", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
            "-pthread", "-I", str(path),
            str(ROOT / "tests/unit/rwlock/rwlock_fixture.c"), "-o", str(binary),
        ], check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=40)


if __name__ == "__main__":
    main()
