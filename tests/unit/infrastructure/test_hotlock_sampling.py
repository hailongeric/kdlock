"""Compile actual hot-lock sampling with a deterministic TSC in the guest.

The clock/allocation/CPU-local primitives are substitutes, including deterministic
IRQ reentry and dropped non-task samples; this does not exercise kernel hooks.
The live JIT suite independently requires natural lock promotion.
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
    mutations = {
        "interrupt-table-access": ("if (!in_task())\n    return admitted;", "if (false)\n    return admitted;", 1),
        "interrupt-mcs-sample": ("if (!in_task())\n    return;", "if (false)\n    return;", 1),
        "redundant-preemption-pair": ("pin = !preempt_count();", "pin = true;", 1),
        "early-lock-threshold": ("++slot->count > KD_HOTLOCK_SAMPLE_TARGET", "++slot->count >= KD_HOTLOCK_SAMPLE_TARGET", 1),
        "ignore-lock-time": ("now - slot->begin < KD_HOTLOCK_INITIAL_WINDOW", "true", 1),
        "cpu-deadline-equality": ("now - t->rate_begin < KD_HOTLOCK_CPU_WINDOW", "now - t->rate_begin <= KD_HOTLOCK_CPU_WINDOW", 1),
        "window-deadline-equality": ("now - slot->begin < KD_HOTLOCK_INITIAL_WINDOW", "now - slot->begin <= KD_HOTLOCK_INITIAL_WINDOW", 1),
        "tick-every-record": ("  if (++t->rate_samples <", "  rdtsc_ordered();\n  if (++t->rate_samples <", 1),
        "spin-entry-ticks": ("record && kind == 1 &&", "record &&", 1),
        "query-ticks": ("record && kind == 1 &&", "kind == 1 &&", 1),
        "spin-reuses-mcs-time": ("if (kind == 0 || t->rate_samples)", "if (t->rate_samples)", 1),
        "mutex-double-clock": ("if (kind == 0 || t->rate_samples)", "if (true)", 1),
        "early-spin-cpu-threshold": ("#define KD_HOTLOCK_SPIN_MCS_INTERVAL 4U", "#define KD_HOTLOCK_SPIN_MCS_INTERVAL 1U", 1),
        "late-spin-cpu-threshold": ("#define KD_HOTLOCK_SPIN_MCS_INTERVAL 4U", "#define KD_HOTLOCK_SPIN_MCS_INTERVAL 32U", 1),
        "old-cpu-window": ("#define KD_HOTLOCK_CPU_WINDOW 4000000000UL", "#define KD_HOTLOCK_CPU_WINDOW 40000000000UL", 1),
        "restart-lock-on-cpu-tick": ("if (!continuous)", "if (!continuous || t->rate_hot)", 1),
        "collision-alias": ("slot->address == address", "kd_hotlock_bucket(slot->address) == kd_hotlock_bucket(address)", 1),
        "capacity-overwrites-entry": ("if (t->used == KD_HOTLOCK_ENTRIES)\n    return NULL;", "if (t->used == KD_HOTLOCK_ENTRIES)\n    return &t->entries[0];", 1),
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
