"""Compile actual hot-lock sampling with a deterministic TSC in the guest.

The clock/allocation/CPU-local primitives are substitutes, including deterministic
IRQ reentry through the CPU-local busy guard; this does not exercise kernel hooks.
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
    queue = (ROOT / "kernel_module/spin/queue.inc").read_text()
    source += "\n" + queue[
        queue.index("static __always_inline u32 xchg_tail"):
        queue.index("/**\n * clear_pending")
    ]
    mutations = {
        "entry-busy-guard": ("if (this_cpu_cmpxchg(kd_hotlock_cpu->tables[kind].busy, 0, 1))", "if (false)", 1),
        "mcs-busy-guard": ("if (this_cpu_cmpxchg(kd_hotlock_cpu->tables[0].busy, 0, 1))", "if (false)", 1),
        "busy-never-released": ("WRITE_ONCE(t->busy, 0);", "WRITE_ONCE(t->busy, 1);", 2),
        "redundant-preemption-pair": ("pin = !preempt_count();", "pin = true;", 1),
        "missing-preemption-pair": ("pin = !preempt_count();", "pin = false;", 1),
        "early-lock-threshold": ("++slot->count > target", "++slot->count >= target", 1),
        "mutex-uses-spin-target": ("kind ? KD_HOTLOCK_SAMPLE_TARGET :", "kind ? KD_HOTLOCK_SPIN_SAMPLE_TARGET :", 1),
        "spin-uses-mutex-target": ("KD_HOTLOCK_SPIN_SAMPLE_TARGET;", "KD_HOTLOCK_SAMPLE_TARGET;", 1),
        "mutex-uses-spin-window": ("kind ? KD_HOTLOCK_INITIAL_WINDOW :", "kind ? KD_HOTLOCK_SPIN_INITIAL_WINDOW :", 1),
        "spin-uses-mutex-window": ("KD_HOTLOCK_SPIN_INITIAL_WINDOW;", "KD_HOTLOCK_INITIAL_WINDOW;", 1),
        "reopen-uses-mutex-window": ("now - slot->begin < KD_HOTLOCK_SPIN_INITIAL_WINDOW)", "now - slot->begin < KD_HOTLOCK_INITIAL_WINDOW)", 1),
        "ignore-lock-time": ("now - slot->begin < window", "((void)window, true)", 1),
        "cpu-deadline-equality": ("now - t->rate_begin < KD_HOTLOCK_CPU_WINDOW", "now - t->rate_begin <= KD_HOTLOCK_CPU_WINDOW", 1),
        "window-deadline-equality": ("now - slot->begin < window", "now - slot->begin <= window", 1),
        "tick-every-record": ("  if (!spin && ++t->rate_samples <", "  rdtsc_ordered();\n  if (!spin && ++t->rate_samples <", 1),
        "spin-entry-ticks": ("record && kind == 1 &&", "record &&", 1),
        "query-ticks": ("record && kind == 1 &&", "kind == 1 &&", 1),
        "spin-reuses-mcs-time": ("if (kind == 0 || t->rate_samples)", "if (t->rate_samples)", 1),
        "mutex-double-clock": ("if (kind == 0 || t->rate_samples)", "if (true)", 1),
        "early-mutex-threshold": ("++t->rate_samples < interval", "++t->rate_samples < interval - 1U", 1),
        "late-mutex-threshold": ("++t->rate_samples < interval", "++t->rate_samples <= interval", 1),
        "spin-counts-batches-as-single-events": ("if (!spin && ++t->rate_samples < interval)", "if (++t->rate_samples < interval)", 1),
        "missing-raw-mcs-count": ("unsigned long count = this_cpu_inc_return(kd_hotlock_spin_mcs);", "unsigned long count = this_cpu_read(kd_hotlock_spin_mcs);", 1),
        "double-raw-mcs-count": ("unsigned long count = this_cpu_inc_return(kd_hotlock_spin_mcs);", "unsigned long count = this_cpu_inc_return(kd_hotlock_spin_mcs); this_cpu_inc(kd_hotlock_spin_mcs);", 1),
        "early-mcs-batch": ("count & (KD_HOTLOCK_SPIN_MCS_INTERVAL - 1U)", "count & (KD_HOTLOCK_SPIN_MCS_INTERVAL / 2U - 1U)", 1),
        "late-mcs-batch": ("count & (KD_HOTLOCK_SPIN_MCS_INTERVAL - 1U)", "count & (KD_HOTLOCK_SPIN_MCS_INTERVAL * 2U - 1U)", 1),
        "guard-every-publication": ("if (!(count & (KD_HOTLOCK_SPIN_MCS_INTERVAL - 1U)))", "if ((void)count, true)", 1),
        "raw-mcs-not-reset": ("per_cpu(kd_hotlock_spin_mcs, cpu) = 0;", "(void)per_cpu(kd_hotlock_spin_mcs, cpu);", 1),
        "restart-lock-on-cpu-tick": ("if (!continuous || reopen)", "if (!continuous || reopen || t->rate_hot)", 1),
        "ratio-discards-frequency-history": ("continuous = r->freq_hot && t->rate_hot;", "continuous = was_hot && t->rate_hot;", 1),
        "frequency-history-always-hot": ("r->freq_hot = t->rate_hot;", "r->freq_hot = true;", 1),
        "reopen-skips-expiry": ("reopen = r->ratio_enforced && !was_hot && t->rate_hot;", "reopen = false;", 1),
        "reopen-discards-valid-epochs": ("if (continuous && now >= slot->begin &&", "if (false && continuous && now >= slot->begin &&", 1),
        "reopen-deadline-equality": ("if (continuous && now >= slot->begin &&\n          now - slot->begin < KD_HOTLOCK_SPIN_INITIAL_WINDOW)", "if (continuous && now >= slot->begin &&\n          now - slot->begin <= KD_HOTLOCK_SPIN_INITIAL_WINDOW)", 1),
        "collision-alias": ("slot->address == address", "kd_hotlock_bucket(slot->address) == kd_hotlock_bucket(address)", 1),
        "capacity-overwrites-entry": ("if (t->used == KD_HOTLOCK_ENTRIES)\n    return NULL;", "if (t->used == KD_HOTLOCK_ENTRIES)\n    return &t->entries[0];", 1),
        "disabled-delegation-samples": ("if (kd_spin_delegate)", "if (true)", 1),
        "skip-cold-publication": ("if (kd_spin_delegate)", "if (kd_spin_delegate && kd_hotlock_spin_cpu_hot_pinned())", 1),
        "double-publication-sample": ("if (kd_spin_delegate)\n\t\tkd_hotlock_record_spin_mcs_pinned();", "if (kd_spin_delegate) { kd_hotlock_record_spin_mcs_pinned(); kd_hotlock_record_spin_mcs_pinned(); }", 1),
        "missing-entry-count": ("this_cpu_inc(kd_hotlock_spin_entries);", "(void)0;", 1),
        "double-entry-count": ("this_cpu_inc(kd_hotlock_spin_entries);", "this_cpu_inc(kd_hotlock_spin_entries); this_cpu_inc(kd_hotlock_spin_entries);", 1),
        "stale-ratio-origin": ("r->entry_begin = entries;", "(void)entries;", 1),
        "threshold-equality-rejected": ("delta <= r->entry_limit", "delta < r->entry_limit", 1),
        "clock-interval-as-ratio-numerator": ("KD_HOTLOCK_SPIN_RATIO_INTERVAL * 100U / spin_contention_pct", "KD_HOTLOCK_SPIN_MCS_INTERVAL * 100U / spin_contention_pct", 1),
        "zero-percentage-rejects": ("/ spin_contention_pct : ~0UL;", "/ spin_contention_pct : 0UL;", 1),
        "ignore-contention-ratio": ("t->rate_hot &= r->ratio_hot;", "(void)r->ratio_hot;", 1),
        "ratio-evaluates-every-clock": ("r->ratio_samples >= KD_HOTLOCK_SPIN_RATIO_INTERVAL", "r->ratio_samples >= interval", 1),
        "early-ratio-threshold": ("r->ratio_samples >= KD_HOTLOCK_SPIN_RATIO_INTERVAL", "r->ratio_samples >= KD_HOTLOCK_SPIN_RATIO_INTERVAL - interval", 1),
        "late-ratio-threshold": ("r->ratio_samples >= KD_HOTLOCK_SPIN_RATIO_INTERVAL", "r->ratio_samples > KD_HOTLOCK_SPIN_RATIO_INTERVAL", 1),
        "ratio-incomplete-reset": ("r->ratio_samples = 0;", "r->ratio_samples -= interval;", 1),
        "ratio-counts-clocks": ("r->ratio_samples += interval;", "r->ratio_samples++;", 1),
        "ratio-cached-verdict-lost": ("t->rate_hot &= r->ratio_hot;", "t->rate_hot &= r->ratio_hot && !r->ratio_samples;", 1),
        "startup-waits-for-ratio": ("r->ratio_hot = true;", "r->ratio_hot = false;", 1),
        "cold-low-starts-confirmation": ("else if (r->ratio_hot &&\n               ++r->ratio_low_windows >=", "else if (++r->ratio_low_windows >=", 1),
        "one-low-closes-gate": ("++r->ratio_low_windows >= KD_HOTLOCK_SPIN_COOL_WINDOWS", "++r->ratio_low_windows >= KD_HOTLOCK_SPIN_COOL_WINDOWS - 1U", 1),
        "two-lows-not-enough": ("++r->ratio_low_windows >= KD_HOTLOCK_SPIN_COOL_WINDOWS", "++r->ratio_low_windows > KD_HOTLOCK_SPIN_COOL_WINDOWS", 1),
        "low-confirmation-not-counted": ("++r->ratio_low_windows >= KD_HOTLOCK_SPIN_COOL_WINDOWS", "r->ratio_low_windows >= KD_HOTLOCK_SPIN_COOL_WINDOWS", 1),
        "high-does-not-reset-confirmation": ("else if (high)\n      {\n        r->ratio_hot = high;\n        r->ratio_low_windows = 0;", "else if (high)\n      {\n        r->ratio_hot = high;", 1),
        "confirmed-low-remains-hot": ("r->ratio_hot = false;", "r->ratio_hot = true;", 1),
        "cooldown-skipped": ("r->ratio_cooldown = KD_HOTLOCK_SPIN_RETRY_WINDOWS;", "r->ratio_cooldown = 0;", 1),
        "cooldown-early-decrement": ("r->ratio_cooldown = KD_HOTLOCK_SPIN_RETRY_WINDOWS;", "r->ratio_cooldown = KD_HOTLOCK_SPIN_RETRY_WINDOWS - 1U;", 1),
        "cooldown-never-expires": ("r->ratio_cooldown--;", "(void)r->ratio_cooldown;", 1),
        "low-window-stalls-cooldown": ("if (r->ratio_cooldown)", "if (r->ratio_cooldown && high)", 1),
        "partial-window-consumes-cooldown": ("r->ratio_samples += interval;", "r->ratio_samples += interval; if (r->ratio_cooldown) r->ratio_cooldown--;", 1),
        "native-reheat-ignores-cooldown": ("r->ratio_hot = high && !r->ratio_cooldown;", "r->ratio_hot = high;", 1),
        "cooling-transition-not-counted": ("r->ratio_cools++;", "(void)r->ratio_cools;", 1),
        "lifetime-mcs-overwritten": ("r->mcs_total += interval;", "r->mcs_total = interval;", 1),
        "dropped-batch-enters-numerator": ("r->mcs_total += interval;", "r->mcs_total = this_cpu_read(kd_hotlock_spin_mcs);", 1),
        "reject-counter-wrap": ("unsigned long delta = entries - r->entry_begin;", "unsigned long delta = entries >= r->entry_begin ? entries - r->entry_begin : ULONG_MAX;", 1),
        "observe-ratio-filter": ("!kd_hotlock_observe && spin_contention_pct", "spin_contention_pct", 1),
        "mutex-ratio-filter": ("if (spin)\n  {", "if (spin || interval == KD_HOTLOCK_CHECK_INTERVAL)\n  {", 1),
        "missing-spin-ratio": ("KD_HOTLOCK_SPIN_MCS_INTERVAL, true);", "KD_HOTLOCK_SPIN_MCS_INTERVAL, false);", 1),
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
