# Main adaptive spin comparison, 2026-11-17

Candidate `20e9db0c` on `main`, after importing the committed clean rewrite in
`ac0c7c4d`. The original `master` working tree and its changes were not used or
modified. The old `main` remains at `archive/main-before-clean-rewrite-20261117`.

The candidate tracks Native closely at 1–3 workers in this workload. It does
not match Native at every contention level: short sections lose about 21–24%
at 8/32 workers. Sixteen-line sections gain about 11% at 8 workers and are near
parity at 32. This is a candidate-versus-Native comparison, not an A/B against
the clean rewrite before this change; it does not establish the improvement
caused by the patch itself.

## Identity and method

* Kernel `7.0.0-38-kdmainspin1 #86`, built from an isolated copy of the existing
  `kdc` Linux source/output plus the exact archived main inputs. Guest directory:
  `/mnt/kdlock-builds/main-spin-20e9db0c-20261117`.
* Configuration SHA-256
  `6e79093df66cd0f150c81b7e46b1fdf0b5ce083a4aa55765daef663de70832d9`;
  byte-identical to the pre-existing kdc configuration. Whole-kernel lock
  replacement is disabled. Native and KD ran in the same boot. Preemption:
  `full (lazy)`. The existing installed toolchain and Python environment were used.
* Kernel ELF SHA-256
  `103675c0e5bf9311217959429b9ac0c86115d09afe8714851aaeb01edb1d0746`.
  Benchmark module SHA-256
  `e1a33c59a383765b008d476d16305918acc405e2ffff4fbfc51d5b617b7223b3`.
* 64 vCPUs, individually pinned to host CPUs 0–63; worker i on guest CPU i.
  This sweep uses 0–31 on one guest NUMA node. Host CPU 0 policy min/max was
  2.7 GHz, governor performance; the recorded current frequency was 2.563 GHz
  during build. No constant achieved frequency or host-wide exclusivity is claimed.
* Three alternating Native/KD rounds per cell, 250 ms warmup and 1000 ms timing;
  1/2/3/5/8/32 workers, 1/16 data cache lines, 100% writes, `post=64`.
  Each shared data line is 128-byte aligned. Rates include the whole benchmark
  loop and work outside the critical section, not isolated lock latency.
* Both benchmark bodies use out-of-line lock and unlock calls. Native targets
  `_raw_spin_lock/_raw_spin_unlock`, KD targets `kd_spin_lock/kd_spin_unlock`.
  Identical compiler instrumentation is retained. The daemon was active for
  timing and used only the main candidate's committed translator.
* Default adaptive settings were retained: enter depth 5, exit depth 2,
  `kd_adapt=1`. No tuning was performed from these results.

## Timing

Mops/s, median of three samples. Raw samples and ranges are in `summary.json`,
`summary.csv` and the archived `evidence/points.jsonl`. Ratios are KD/Native;
three samples are not a confidence interval or a general parity guarantee.

| Data lines | Workers | Native Mops/s | KD Mops/s | KD/Native | KD completed elsewhere / KD ops |
| --- | --- | --- | --- | --- | --- |
| 1 | 1 | 10.408 | 10.410 | 1.000 | 0 / 32,187,973 |
| 1 | 2 | 7.317 | 7.320 | 1.000 | 0 / 22,270,058 |
| 1 | 3 | 4.639 | 4.702 | 1.013 | 0 / 14,378,758 |
| 1 | 5 | 5.874 | 5.305 | 0.903 | 0 / 16,119,762 |
| 1 | 8 | 6.357 | 5.047 | 0.794 | 30,439 / 15,345,621 |
| 1 | 32 | 7.270 | 5.518 | 0.759 | 79,369 / 17,159,340 |
| 16 | 1 | 10.406 | 10.402 | 1.000 | 0 / 32,488,349 |
| 16 | 2 | 3.027 | 2.965 | 0.980 | 0 / 9,066,319 |
| 16 | 3 | 3.026 | 3.007 | 0.994 | 0 / 9,181,911 |
| 16 | 5 | 2.882 | 2.786 | 0.967 | 0 / 8,475,774 |
| 16 | 8 | 2.889 | 3.207 | 1.110 | 707,271 / 9,875,592 |
| 16 | 32 | 2.972 | 2.957 | 0.995 | 425,850 / 9,177,835 |

The 5-worker short-section cell loses 9.7% even though offered and delegated
counts are zero. That loss cannot be attributed to execution of proxy bodies.
At 8/32 workers the short section completes only about 0.20%/0.46% of KD
operations through delegation, whereas the sixteen-line section completes
about 7.16%/4.64%. These are completion shares, not measured physical batch
lengths. Queue admission and ordinary queue costs still need investigation.

## Correctness and cleanup

* API check: 65 checks, zero failures.
* All 176 recorded runs passed the benchmark oracle: 6 local checks,
  2 learning runs, 16 focused correctness runs, 8 phase-change runs,
  72 warmups and 72 timing runs. Every worker progressed, torn-read/error
  count was zero, and the shared sum matched completed writes times line count.
  This oracle is not a direct overlap instrumentation counter.
* Focused cases: spin, nested spin, raw spin and spin handback, Native/KD,
  2/8 workers. Nested delegation counters remained zero: these runs do not
  establish delegated nested-session coverage.
* Same loaded module, low/high/low sequence 1/2/3/8/32/3/2/1: offered and
  delegated counts were zero at every 1/2/3-worker point, both before and after
  the busy phase. The 8/32-worker points completed 6,847/13,362 delegated bodies.
* Final totals include all stages: 1,685,961 delegated completions, 87
  handbacks, 700 mode entries, 703 mode exits. Mode counters are observations,
  not an exact queue-state or physical-owner proof.
* Dry-run translations completed before enabling the daemon; they include
  unimplemented-path handback frontiers and missing diagnostic callees.
  They are not proof of unrestricted code support or a full stack-depth bound.
* No new BUG, WARNING, call trace, lockup or detected RCU-stall messages.
  The log retains an hrtimer latency notice and unrelated AppArmor messages.
  Taint was 8192 before the benchmark and 12288 after loading the out-of-tree
  module; this expected taint addition remains after unload.
* Daemon exited with status 0, `rmmod kd_bench` succeeded, and delegation is 0.
  VM remains running and idle on the candidate kernel. Default GRUB config
  hashes are unchanged; the one-time boot entry was consumed.

The controlled no-image depth-transition/address-reuse fixture and forced-mode
regression listed in the build guide were not run. Functional and timing
success here do not close those targeted proof obligations.

## Recovery and preserved evidence

Live QEMU reported `pre-kdclaude1-boot` and `pre-kdall1-boot` present on all
attached disks before this run. No snapshot was deleted or restored. Existing
kernels, build trees and reports were retained; only a new isolated build,
newly named installed kernel/modules, and test evidence were added.

`results.tar.gz` contains raw per-worker counts, all timing points, generated
code disassembly, daemon log/state, before/after kernel logs, cleanup records,
configuration and artifact hashes. The runner and preparation scripts are
retained beside it. The full build/install console logs were initially written
to guest `/tmp` and did not survive reboot; the completed artifact receipts and
reported diagnostics remain. Observed diagnostics included the upstream
AppArmor Kconfig/string and unused-variable warnings, a maple-tree frame warning,
and the benchmark's missing MODULE_DESCRIPTION warning. Do not interpret the
missing full console logs as a warning-free build.
