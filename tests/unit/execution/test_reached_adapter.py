"""Guest-only checks of the reference reached-frame entry/run adapter.

The bounded scalar engine has a separate Native differential kernel fixture.
Here only its begin/run calls and enclosing frame-readiness checks are replaced
so exact packet ownership and progress bookkeeping can be observed directly.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT, read_source
from test_spin_shadow import definition


def main():
    source = read_source(ROOT / "tests/unit/execution/reached_reference_adapter.inc")
    production = "\n".join(definition(source, signature) for signature in (
        "int kd_exe_reached_begin(struct kd_exec_frame *frame,",
        "enum kd_reached_result kd_exe_reached_run(struct kd_exec_frame *frame,",
    ))
    with tempfile.TemporaryDirectory(prefix="kd-reached-adapter-") as temporary:
        directory = Path(temporary)
        (directory / "production.h").write_text(production)
        binary = directory / "reached-adapter"
        subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
            "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "include"), "-I", str(directory),
            str(ROOT / "tests/unit/execution/reached_adapter_fixture.c"),
            "-o", str(binary),
        ], check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=15)


if __name__ == "__main__":
    main()
