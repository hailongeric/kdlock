"""VM-only checks of the exact general GS read/context selection policy."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT, read_source
from test_spin_shadow import definition


def main():
    source = read_source(ROOT / "kernel_module/service_memory.inc")
    body = definition(source, "static int kd_service_memory_prepare(struct kd_service_root *root)")
    with tempfile.TemporaryDirectory(prefix="kd-origin-read-policy-") as temporary:
        directory = Path(temporary)
        (directory / "production.h").write_text(body)
        binary = directory / "policy"
        subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
            "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "include"), "-I", str(directory),
            str(ROOT / "tests/unit/execution/origin_read_policy_fixture.c"),
            "-o", str(binary),
        ], check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=15)


if __name__ == "__main__":
    main()
