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
        guard = "if (boot_cpu_has(X86_FEATURE_CALL_DEPTH))"
        assert code.count(guard) == 1
        cases = [("ordinary", code, False, False), ("selftest", code, True, False),
                 ("missing-runtime-guard", code.replace(guard,
                     "if (boot_cpu_has(X86_FEATURE_CALL_DEPTH) && false)"), False, True),
                 ("late-runtime-guard", code.replace(guard,
                     "kd_comm_init(&kd_spin_target, target_process);\n\t" + guard), False, True)]
        for label, candidate, selftest, negative in cases:
            (directory / "provider_lifecycle.h").write_text(candidate)
            binary = directory / label
            subprocess.run(
                shlex.split(os.environ.get("CC", "cc"))
                + ["-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror"]
                + (["-DKDLOCK_SELFTEST"] if selftest else [])
                + ["-I", str(directory),
                   str(ROOT / "tests/unit/infrastructure/provider_lifecycle_fixture.c"),
                   "-o", str(binary)],
                check=True, timeout=30,
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            if negative:
                assert result.returncode == 1 and "FAIL line" in result.stderr, (
                    label, result.returncode, result.stdout, result.stderr)
                print("PASS provider policy mutation detected: " + label)
            else:
                assert result.returncode == 0, result.stderr
                print(result.stdout, end="")


if __name__ == "__main__":
    main()
