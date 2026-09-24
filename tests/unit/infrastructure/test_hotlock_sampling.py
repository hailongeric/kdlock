"""Compile adaptive-only hot-lock sampling with a deterministic TSC in the guest.

Clock/allocation/CPU-local primitives are substitutes. The fixture checks ordinary
sampling cadence, admission and table safety, not exact IRQ statistics or kernel
hooks. The live JIT suite independently requires natural lock promotion.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, without_includes


def main():
    source = "\n".join(
        without_includes((ROOT / name).read_text())
        for name in ("include/kd_hotlock.h", "kernel_module/kd_hotlock.c")
    )
    queue = (ROOT / "kernel_module/spin/queue.inc").read_text()
    source += "\n" + queue[
        queue.index("static __always_inline u32 xchg_tail"):
        queue.index("/**\n * clear_pending")
    ]
    # A small set of policy mutations checks that these tests reject a wrong
    # result. IRQ ownership and lossless profiling are intentionally not tested.
    mutations = {
        "table-busy-guard": ("if (READ_ONCE(t->busy))", "if (false)", 1),
        "late-spin-threshold": ("++slot->count >= target", "++slot->count > target", 1),
        "mutex-uses-spin-target": ("kind ? KD_HOTLOCK_SAMPLE_TARGET + 1U :", "kind ? KD_HOTLOCK_SPIN_SAMPLE_TARGET :", 1),
        "ignore-lock-time": ("now - slot->begin < window", "((void)window, true)", 1),
        "missing-mcs-count": ("this_cpu_inc(kd_hotlock_spin_mcs);", "(void)0;", 1),
        "early-mcs-comparison": ("KD_HOTLOCK_SPIN_MCS_INTERVAL - 1U", "KD_HOTLOCK_SPIN_MCS_INTERVAL / 2U - 1U", 1),
        "missing-entry-count": ("this_cpu_inc(kd_hotlock_spin_entries);", "(void)0;", 1),
        "stale-ratio-origin": ("r->entry_begin = entries;", "(void)entries;", 1),
        "threshold-equality-rejected": ("mcs_delta * 100UL >= entry_delta * spin_contention_pct", "mcs_delta * 100UL > entry_delta * spin_contention_pct", 1),
        "ignore-contention-ratio": ("mcs_delta * 100UL >= entry_delta * spin_contention_pct", "((void)entry_delta, true)", 1),
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
                    "-pthread",
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
