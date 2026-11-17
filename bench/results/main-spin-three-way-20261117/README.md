# Main spin: Native, KD and TCLock, 2026-11-17

**Location correction and cleanup.** The user clarified that this work must use
only the VM on 380G10. The tests below used the wrong host. At the user's explicit
request, both newly installed kdmainspin kernels, their modules and both isolated
build trees were deleted, and nine hash-matched host transfer files were removed.
The original kdall1 image is running again; default GRUB configuration hashes
match the saved pre-install values. Boot symlinks were reconstructed to kdall1
and the preceding kdclaude1 installation; the pre-install symlink targets were
not separately captured, so byte-for-byte restoration of all prior state is not
claimed. Boot history and system audit logs are retained. No VM disk, snapshot,
other build tree or existing host SSH tunnel was removed. Final verification is
in `final-remote-cleanup.log`. No further access to the remote VM is authorized.
The local source/module/report copies have been migrated into the existing
380G10 VM: [416 entries verified](migration-380g10/README.md). Complete deleted
kernel build outputs are not among those copies.


The trial `1d29a9a1` passed the exercised correctness checks but did not deliver
consistent performance gains. It is rejected, remains reachable at
`archive/spin-handoff-trial-1d29a9a1`, and its five changed paths are restored to
`ebd43023`. The resulting lock implementation is the previously tested
`20e9db0c`. No new speedup is claimed. All changes in this session belong to
`main`; the separate `master` worktree was not edited by this work.

## Changes examined and decision

1. **Plain queue handoff:** retain the successor pointer already read and
   prefetched while waiting, instead of reloading it after acquiring the lock.
   This removes a dependent read in the serialized handoff path. The emitted
   code retains the pointer in a register without increasing the function's
   frame or per-CPU structure size. Nevertheless, the combined trial regressed
   at 32 workers, including with its new policy disabled. A static reduction
   in loads is not a demonstrated throughput improvement. This change is
   withdrawn together with the trial; its independent effect is unresolved.
2. **Adaptive delegation:** leave delegation mode when a plain successor ends
   a spin session before two foreign bodies are served. Ownership, publication,
   completion and handback rules are unchanged. The new switch
   `kd_spin_min_batch=0/2` provided a same-boot policy control. The rule reduced
   offers but caused repeated mode entry/exit and lost useful batching on
   longer sections. It is withdrawn, including its parameter and appended
   diagnostic statistic.
3. **Entry path and polling:** compared Native and KD assembly, pending/tail
   handling, sampled queue-depth checks, node layout, and callable wrappers.
   The no-contention path was not enlarged. Remaining differences include KD's
   slow-function frame, lock-word reload and bookkeeping/probing; their separate
   costs have not been measured. No ownership or lifetime instrumentation was
   removed to improve timing.
4. **Benchmark and platform:** added the existing original TCLock port, repeated
   the old kernel with the same three-way benchmark, varied section size and
   outside work, included cross-NUMA workers, separate daemon-off points,
   same-boot policy controls, and separate sampling. Also examined module layout,
   host topology, pinning, frequency and load. These dimensions matter: TCLock
   loses the single-node cases here but wins the cross-NUMA cases.

## Identity and method

* Baseline kernel `7.0.0-38-kdmainspin1`, core `20e9db0c`; candidate kernel
  `7.0.0-38-kdmainspin2`, core `1d29a9a196a1db2f6b278f27111d8bdeca1a13e2`.
  Each Native/KD/TCLock grid is within one boot. **The two kernels necessarily
  use different boots**; their absolute throughputs are not pooled.
* Frozen guest tree `/mnt/kdlock-builds/main-spin-handoff-1d29a9a1-20261117`.
  Baseline kernel inputs remain in
  `/mnt/kdlock-builds/main-spin-20e9db0c-20261117`.
  Existing compiler and `/root/kdvenv` only. Builds, modules and tests ran in
  the VM; source review and result processing ran on 380G10.
* Config SHA-256 for both:
  `6e79093df66cd0f150c81b7e46b1fdf0b5ce083a4aa55765daef663de70832d9`.
  `full (lazy)` preemption; no whole-kernel replacement. `nopvspin` is active:
  the exact Linux KVM initialization skips enabling `virt_spin_lock_key`.
  Native's virtualized TAS fallback is therefore not an explanation for the
  observed queue-path difference.
* Baseline installed kernel SHA-256
  `ba3f919b4f651d855fc1e2e79338027b1742a828848b85b45552ecf058f715ec`;
  candidate `82bf0480161c69c51f2eb7471558474a3a86351b4305e112636b101992361762`.
  Candidate vmlinux/config/install hashes and persistent build/install logs are
  archived. Baseline kernel build provenance is in the preceding report.
* The three-way benchmark and all four TCLock providers were built against
  each matching kernel output. Their respective `.text` hashes are identical
  across the two builds; complete module hashes differ and are preserved.
  TCLock uses the repository's unchanged original port with `TCLOCK_NUMA=1`;
  see [port provenance](../../../tclock_backend/README.md). No TCLock tuning or
  protocol substitution was made. All provider modules were required to link
  the combined benchmark; timing here exercises spin only.
* Inspected TCLock spin slow-entry and context-switch assembly: six callee-saved
  register pushes/pops and its explicit stack switch, with no extra C frame.
  Existing objtool naked-return/RETHUNK and BP-scratch warnings remain in the
  module build logs. This is not a claim of complete return mitigation coverage.
* VM: 64 vCPUs, two nodes of 32, 24 GiB. Every vCPU i is pinned to host CPU i;
  host CPUs 0–31 are socket/node 0, 32–63 socket/node 1. Ordinary points start
  at CPU 0; cross-NUMA points use 32 workers on CPUs 16–47. Host memory is bound
  to the corresponding nodes. All host CPU policies recorded min=max=2.7 GHz,
  performance governor; instantaneous readings vary. No constant achieved
  frequency or continuous exclusive host control is claimed. The host process
  sample found no competing high-CPU workload other than this QEMU.
* Each timing has 250 ms warmup then 1000 ms measurement. Three rotated backend
  rounds per standard/policy/NUMA cell; outside-work controls have two rounds.
  100% writes, one or sixteen 128-byte-aligned data lines, `post=64` normally,
  `post=0` for outside-work controls. These are whole-loop Mops/s, not isolated
  acquisition latency. Both KD and Native use callable lock/unlock wrappers.
* Adaptive entry/exit depths remain 5/2. Candidate default short-batch threshold
  is 2. All temporary parameters were restored by each runner.
* Both two-disk recovery snapshots were verified with live QEMU `info snapshots`
  before module work. Idle checks and space checks preceded builds/runs.
  No other files, snapshots, modules or kernel images were deleted.

## Three-way timing

Medians in Mops/s, `post=64`, one guest/host NUMA node. All samples, ranges,
counts and warmups are in `summary.json`, `summary.csv` and the archives.
Three samples do not establish a confidence interval or universal parity.

### Retained baseline

| Lines | Workers | Native | KD | TCLock | KD/Native |
| --- | --- | --- | --- | --- | --- |
| 1 | 1 | 10.409 | 10.410 | 10.406 | 1.000 |
| 1 | 2 | 8.490 | 8.048 | 6.192 | 0.948 |
| 1 | 3 | 4.687 | 4.809 | 2.834 | 1.026 |
| 1 | 5 | 6.679 | 6.516 | 3.226 | 0.976 |
| 1 | 8 | 6.954 | 6.620 | 4.465 | 0.952 |
| 1 | 32 | 7.054 | 6.486 | 4.889 | 0.919 |
| 16 | 1 | 10.406 | 10.404 | 10.408 | 1.000 |
| 16 | 2 | 2.964 | 3.020 | 2.842 | 1.019 |
| 16 | 3 | 3.099 | 3.120 | 2.267 | 1.007 |
| 16 | 5 | 2.967 | 2.869 | 2.499 | 0.967 |
| 16 | 8 | 2.918 | 3.053 | 2.521 | 1.046 |
| 16 | 32 | 2.979 | 3.021 | 2.556 | 1.014 |

### Rejected candidate

| Lines | Workers | Native | KD | TCLock | KD/Native |
| --- | --- | --- | --- | --- | --- |
| 1 | 1 | 10.407 | 10.409 | 10.405 | 1.000 |
| 1 | 2 | 8.766 | 8.798 | 6.427 | 1.004 |
| 1 | 3 | 4.727 | 4.841 | 2.865 | 1.024 |
| 1 | 5 | 6.862 | 6.733 | 3.253 | 0.981 |
| 1 | 8 | 7.082 | 6.721 | 4.540 | 0.949 |
| 1 | 32 | 7.066 | 5.890 | 4.942 | 0.834 |
| 16 | 1 | 10.407 | 10.405 | 10.410 | 1.000 |
| 16 | 2 | 3.120 | 3.187 | 2.851 | 1.022 |
| 16 | 3 | 3.192 | 3.150 | 2.299 | 0.987 |
| 16 | 5 | 3.050 | 3.018 | 2.596 | 0.989 |
| 16 | 8 | 3.004 | 3.031 | 2.572 | 1.009 |
| 16 | 32 | 2.987 | 2.950 | 2.575 | 0.988 |

### Cross-NUMA, 32 workers

| Version | Lines | Native | KD | TCLock |
| --- | --- | --- | --- | --- |
| baseline | 1 | 3.994 | 3.875 | 4.809 |
| baseline | 16 | 2.279 | 2.251 | 2.489 |
| candidate | 1 | 4.120 | 3.753 | 4.785 |
| candidate | 16 | 2.292 | 2.359 | 2.530 |

### Candidate policy control in the same boot

| Lines | Workers | Threshold 0 | Threshold 2 | 2/0 |
| --- | --- | --- | --- | --- |
| 1 | 5 | 6.731 | 6.731 | 1.000 |
| 1 | 8 | 6.741 | 6.726 | 0.998 |
| 1 | 32 | 5.880 | 5.872 | 0.999 |
| 16 | 5 | 3.014 | 3.017 | 1.001 |
| 16 | 8 | 3.052 | 3.028 | 0.992 |
| 16 | 32 | 2.963 | 2.951 | 0.996 |

The new rule changes throughput by at most about 0.8% in these same-boot
median comparisons, and does not remove the 32-worker short-section loss.
Therefore the large cross-boot regression cannot be assigned entirely to this
policy. In the candidate default three-way grid at 8 workers/16 lines,
64,587 mode entries and 64,574 short-batch exits accompany only 57,576 delegated
operations. The baseline grid has 88 entries and 493,850 delegated operations.
These counts show mode churn and reduced batching; they are not a measurement
of the latency of an individual transition or physical batch-length distribution.

## Why five workers can still be slower without delegation

For every five-worker standard timing cell, offered and delegated counts are
zero in both kernels. With five total workers, a holder plus the queue head
leaves too few successors to satisfy the entry-depth threshold of five.
No continuation capture or foreign body execution explains those cells.

Separate 199 Hz software `cpu-clock` sampling on CPUs 0–4 attributes 88.20% of
baseline Native samples to `native_queued_spin_lock_slowpath`, and 88.77% of KD
samples to `kd_q_lock_slow`. Candidate KD is 89.01%. The dominant work is queue
waiting/handoff. Sampling identifies the relevant path but does not distinguish
spinning from a particular load's latency; it is not cycles/op or a causal
instruction-cost measurement. Profiling was outside the main timing grid.

The first historical two-way run showed a 9.7% loss at five workers. This new
matched three-way baseline shows 2.4%, and the trial 1.9%. This is **not proof of
a patch-induced 7.8-point gain**: repeating the original module and three-way
module in the same baseline boot gave the following control results:

| Sequential session | Artifact | Native | KD | KD/Native |
| --- | --- | --- | --- | --- |
| 0 | original two-way | 5.606 | 4.664 | 0.832 |
| 1 | three-way | 5.280 | 5.634 | 1.067 |
| 2 | three-way | 6.843 | 6.578 | 0.961 |
| 3 | original two-way | 6.867 | 6.703 | 0.976 |

Each session has three alternating pairs, five workers, one line, `post=64`.
All counts and progress checks passed. Variation occurs even when reusing the
same artifact; the experiment does not isolate module layout as the cause.
A small baseline evidence download also overlapped the first control session,
so that session is not treated as isolated timing. The original and three-way
artifacts keep `nspin_w`/`kspin_w` text offsets at 0x10/0xa00, but differ in BSS
positions. Absolute module addresses are recorded per session. Host CPU/core
placement was verified, but unmeasured transient environment/cache effects
remain possible. All samples are retained, not just the favorable sessions.

## Eight and 32 workers: capture is not useful combining

On the baseline short-section three-way grid, eight workers offer 94,799
continuations and complete 44,468 elsewhere; 32 workers offer 177,821 and
complete 88,483 elsewhere. Many offers return locally. These counts establish
that capture/publication work is paid without foreign completion for a large
fraction of offers. They do not identify the exact fraction of elapsed time
spent on that work.

Baseline daemon-off Native/KD medians for 5/8/32 workers are respectively
6.683/6.495, 6.952/6.842, and 7.064/7.124 Mops/s; all offered/delegated counts
are zero. The standard daemon-on KD rates are 6.516, 6.620 and 6.486.
This supports investigating capture/combining overhead at 8/32, while the
sequential daemon-off/on phases do not isolate every environmental factor.
The candidate's daemon-off 32-worker rate already falls to 6.680 versus Native
7.073; removing short-batch exits cannot repair a regression already present
without offers. This is why both candidate changes were withdrawn.

The `post=0` controls also show that one-worker throughput, normally capped by
outside work near 10.4 Mops/s, differs when the outside work is removed. On the
baseline at one line, Native/KD/TCLock reach 78.658/81.058/60.459 Mops/s. This is
whole-loop throughput with different lock implementations, not a universal
fast-path equality proof. Full post=0 results, including losses, are in the
summary and raw records.

## Correctness and coverage

* Baseline: 65 API checks, zero failed; 429 point records, all passed.
* Candidate: 65 API checks, zero failed; 501 point records, all passed.
* Each point checks exact aggregate writes versus observed data sum, all workers
  progressing, and zero torn reads. These are exclusion-sensitive data checks,
  not a separate direct overlap monitor or an exhaustive concurrency proof.
* Native/KD/TCLock spin checks ran at 1/2/5/8/32 workers. Native/KD nested,
  raw and handback fixtures ran at 2/8; daemon-on KD fixtures also ran.
  Low/high/low worker phases and forced-delegation checks ran. The final
  `nested_delegated` count is zero: nested local execution passed, but nested
  foreign execution was **not covered**.
* Baseline/candidate final handback counts are 192/17, with matching frontier
  counts. Published images alone are not completion evidence; the per-point
  returned operations and delegated counters are separately retained.
* Dry-run output and daemon translation diagnostics are retained. This is not
  a whole-kernel stack bound, real-world MM validation, exhaustive IRQ nesting
  proof, or a dedicated no-image/address-reuse campaign.
* All TCLock providers reported quiescent between relevant calls and at cleanup.
  Both daemons exited 0; all five test/provider modules unloaded normally,
  parameters restored, and no new BUG/WARNING/fault/error appeared in the
  retained dmesg deltas. No forced unload or timeout-as-drain assumption.
* The layout control completed and cleaned up. The initial end state was `kdmainspin1`; the subsequent user-requested
  cleanup returned to `kdall1` and removed both test installations/build trees.
  Local evidence remains. See the cleanup notice at the top.

## Evidence and remaining work

`baseline-results.tar.gz`, `candidate-results-complete.tar.gz` and
`layout-results.tar.gz` preserve raw per-worker records, counters, logs,
identities, completion/cleanup records and perf reports/data. `modules.tar`
retains both three-way module sets, their build warnings and exact hashes;
`queue-objects.tar` and `native-source.tar` retain inspected objects and exact
Native implementation inputs. `run.py`, `layout.py`, `build.sh`, `install.sh`
and `summarize.py` capture the procedures. The rejected source is immutable in
Git at `1d29a9a1`; no frozen guest source was edited during a run.

The five-worker historical deficit and the candidate's extra 32-worker loss
are not fully explained. A next experiment should isolate one queue change
with repeated return-to-baseline runs and tighter time-local environment
records, then measure capture cost versus actual served work before selecting
another adaptive policy. Cross-NUMA locality deserves separate treatment;
it cannot be evaluated by single-node results. Raising entry thresholds or
removing probes merely to produce a better number is not a demonstrated
solution. The current result is a measured rejected optimization, not completion
of all possible performance work or achievement of Native parity.
