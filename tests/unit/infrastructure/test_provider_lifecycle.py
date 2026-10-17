"""Check actual provider initialization/publication and failed-start cleanup."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT, read_source
from test_spin_shadow import definition


def main():
    source = read_source(ROOT / "kernel_module/kd_main.c")
    code = "\n".join(definition(source, signature) for signature in (
        "static int __init kdlock_km_init(void)",
        "static void __exit kdlock_km_exit(void)",
    ))
    with tempfile.TemporaryDirectory(prefix="kd-provider-lifecycle-") as tmp:
        directory = Path(tmp)
        (directory / "provider_lifecycle.h").write_text(code)
        for selftest in (False, True):
            binary = directory / ("selftest" if selftest else "ordinary")
            subprocess.run(
                shlex.split(os.environ.get("CC", "cc"))
                + ["-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror"]
                + (["-DKDLOCK_SELFTEST"] if selftest else [])
                + ["-I", str(directory),
                   str(ROOT / "tests/unit/infrastructure/provider_lifecycle_fixture.c"),
                   "-o", str(binary)],
                check=True, timeout=30,
            )
            subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    main()
