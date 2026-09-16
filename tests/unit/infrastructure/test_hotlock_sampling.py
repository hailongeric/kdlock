"""Compile actual hot-lock sampling with a deterministic TSC in the guest.

The clock/allocation/atomic primitives are substitutes, not a concurrent kernel
test. The live JIT suite independently requires natural lock promotion.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from test_spin_gate import ROOT, without_includes


def main():
    source = "\n".join(
        without_includes((ROOT / name).read_text())
        for name in ("include/kd_hotlock.h", "kernel_module/kd_hotlock.c")
    )
    mutations = {
        "unserialized-timestamp": (
            "now = rdtsc_ordered();\n\tstate->samples++;",
            "state->samples++;",
            1,
        ),
        "narrowed-window": (
            "state->sample_window = KD_HOTLOCK_INITIAL_WINDOW;",
            "state->sample_window = KD_HOTLOCK_INITIAL_WINDOW / 1000;",
            1,
        ),
        "deadline-equality-promoted": (
            ">= state->sample_window", "> state->sample_window", 1,
        ),
        "sample-quota-shortened": (
            "state->samples == KD_HOTLOCK_SAMPLE_TARGET",
            "state->samples == KD_HOTLOCK_SAMPLE_TARGET - 1",
            2,
        ),
    }
    with tempfile.TemporaryDirectory(prefix="kdlock-hotlock-sampling-") as directory:
        path = Path(directory)
        for name, mutation in [("production", None), *mutations.items()]:
            code = source
            if mutation:
                before, after, count = mutation
                assert code.count(before) == count
                code = code.replace(before, after)
            (path / "hotlock_production.h").write_text(code)
            binary = path / name
            subprocess.run(
                shlex.split(os.environ.get("CC", "cc"))
                + [
                    "-std=gnu11",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(path),
                    str(ROOT / "tests/unit/infrastructure/hotlock_sampling_fixture.c"),
                    "-o",
                    str(binary),
                ],
                check=True,
                timeout=30,
            )
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True,
                check=False, timeout=15,
            )
            # Prove the gates detect a wrong policy, not a build error, crash
            # or timeout. Timing and kernel primitives remain substitutes.
            if mutation:
                assert result.returncode == 1 and "FAIL line" in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr,
                )
                print(f"hotlock mutation detected: {name}")
            else:
                print(result.stdout, end="")
                assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    main()
