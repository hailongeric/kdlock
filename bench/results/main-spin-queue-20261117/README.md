# Main live queue phase candidate on local 380G10

**Candidate comparison complete.** The main 741 points and a separate ten-point
rwlock supplement completed with zero failed points and normal cleanup on one
boot. Enabling the live queue phase raises the matched 32-worker short-cell
median from 3.1626 to 6.2110 Mops/s, while the five-worker short control remains
4.4018 versus 4.3993 Mops/s. The ordinary five-worker short grid still trails
Native by 2.9%, and TCLock remains faster for the 16-worker short cell.

This report validates runtime policy settings in the kernel5 candidate from
`02e604d3`; its compiled queue-phase default is false. The default-enabled
kernel6 verification has completed and is recorded in the
[separate final report](../main-spin-final-20261117/README.md), with its own
source/image/boot identity. This report retains only the kernel5 policy-candidate
measurements; results from the two boots are not pooled.

## Frozen inputs

Candidate main commit `02e604d32fd0dfa1c563ec6d6e6c6138d3f4be19` follows
`5cd2e62bfdd015584e3ffbd7e81038ac90da92f0`. The exact 131-file identity is in
[main-queue-identity.json](main-queue-identity.json). The overlay contains
`include/kdlock/kd_types.h`, `kernel/kd_core.c` and `kernel/kd_internal.h`.
Its [archive identity](source-overlay.json) has SHA256
`c541ed856bf44fbdf0daf0734cac7e4f41000e2f31d8c89a421122e87d298045`.
The [guest preparation receipt](prepare-receipt.json) records 131 matching
input hashes, an independent `main-queue-source` copy, fresh `main-queue-out`,
and 36,433,739,776 available bytes after preparation. That receipt records
preparation; the separate build receipts below establish the build result.

Only main source/documents and the identity-verified local 380G10 VM are in
scope. No other branch or remote VM supplies code or validation for this work.
The built kernel release is `7.0.0-38-kdlocalspin5`. Its actual image/config
hashes are recorded below. The candidate boot is
`50ac3f08-891c-4800-ba2c-4ce5580d256b`.

## Completed build stage

The [build result](build/main-queue-status-6.json) reports rc=0 after
255.536 seconds for this candidate's independent source and fresh output.
The log tail includes the completed image and modules_prepare step before
`LOCAL_BUILD_COMPLETE`. This build succeeded; the previous phase-wait
experiment's failed module attempt remains only in that experiment's report.

* Image SHA256: `0c3b78cd1d58a00ddfcb897fe368fafe5d7573982fed37f3f24e8fa2e7f8f6b8`.
* Config SHA256: `1395ae1ff15c215ab680dbb5a4a8af074044cc7de35be82004ddf2647f01ca64`,
  exactly matching the phase-wait candidate's recorded config.
* [Build review](build/main-queue-build-review.json) verified all 131 main
  inputs. Benchmark `.text` is `b2ef8124a52507b3f99e72136acffead24e85d4893841ad1763471b391a41eec`;
  TCLock spin `.text` is `55d113c7c1680a3d89430ebd88508f005d552cf5b42e6eb060288f77c145317f`.
  Both pairs match the previous main comparison modules byte-for-byte.
* [Finalization](build/main-queue-finalize.json) records seven signed modules,
  the actual kernel/config hashes and empty depmod diagnostics. No signing
  keys are copied into this report.
* [Ready receipt](build/main-queue-ready.json) records normal build drain,
  only NLS loaded and no recorded kernel warnings before the clean poweroff.
  Its boot UUID `7e85181e-c95d-43fa-82e6-611304550383` identifies the builder's
  preceding boot, **not a boot of this new candidate**.

The local VM was cleanly powered off after build drain for read-only image
extraction. The extracted [full build log](build/build.log), [raw result](build/result.json),
[raw review](build/review.json), [signed artifact identities](build/signed-artifacts.json),
[exact config](build/config), [queue slow-path assembly](build/asm/kd_q_lock_slow.asm)
and [spin entry assembly](build/asm/kd_spin_lock.asm) are retained. These build
receipts do not establish complete mitigation or runtime coverage. The full
logs retain non-fatal kernel configuration/locale and compiler warnings,
maple-tree 1,080-byte frame warnings, benchmark MODULE_DESCRIPTION warnings,
and TCLock compiler/objtool warnings including naked returns and BP scratch
use. A successful build is not a warning-free mitigation review.

## Candidate boot, entry checks and host preflight

The [boot receipt](boot/main-queue-boot-check.json) identifies
`7.0.0-38-kdlocalspin5 #1`, boot `50ac3f08-891c-4800-ba2c-4ce5580d256b`,
40 online CPUs, `full (lazy)` preemption, tracer `nop`, initial taint 4096 and
only the existing NLS module loaded. It repeats the exact config SHA256 above.
This early receipt still had eight startup jobs, so it is not an idle receipt.
The later entry checker waited for startup jobs before its checks; all six
cases in the [entry result](checks/main-queue-entry-check.json) passed and the
module unloaded normally on the same candidate boot.

| Entry case | Total | Worker 0 | Worker 1 | Errors | Contended | Inside at end |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| plain | 60,000 | 30,000 | 30,000 | 0 | 7,560 | 0 |
| irq | 60,000 | 30,000 | 30,000 | 0 | 6,501 | 0 |
| irqsave | 60,000 | 30,000 | 30,000 | 0 | 3,760 | 0 |
| irqsave-disabled | 60,000 | 30,000 | 30,000 | 0 | 3,944 | 0 |
| bh | 60,000 | 30,000 | 30,000 | 0 | 5,023 | 0 |
| clobber | 60,000 | 30,000 | 30,000 | 0 | 5,935 | 0 |

The [pinning and disk receipt](host/queue-pinning.json) records local QEMU
PID 3890629, vCPU i pinned to host CPU i for i=0..39, and the exact attached
root/build image paths. The [recovery receipt](host/recovery-before-queue-run.json)
confirms `kdlock-kernel16-two-disk-smoke-20261116-01` is present on both disks.
The [host preflight](host/queue-host-preflight.json) identifies host `380G10`
and 96,448,790,528 available host bytes before this run.

At this preflight, worker CPUs 0..35 have frequency policy minimum=maximum
2,500,000 kHz. CPUs 36, 37 and 39 instead have a 1,000,000–3,000,000 kHz
policy; CPU 38 has minimum=maximum 2,500,000 kHz. The instantaneous frequency
samples are retained in the receipt and are not a measurement of every timed
interval. No host frequency settings were changed by this work. These details
supersede assumptions based on earlier receipts: this report does not claim
CPUs 0..37 all have fixed policy or that host configuration stayed unchanged
across boots. Controller/emulator CPUs 38–39 therefore have different policies.

The [comparison start](runtime/queue-comparison-start.json) records campaign
PID 946 and runner SHA256
`970b4b9f7aa3582fd5df5e6334757b19ffccae34ca1ee59b4909b60db8e54b6a`.
The separate [main result](runtime/result.json), [completion marker](evidence/measurements-complete.json)
and [cleanup](evidence/cleanup.json) now record successful completion. This
one candidate boot contains all Native/KD/TCLock comparisons and the separate
rwlock supplement. Measurements are not pooled with the preceding phase-wait
boot or the completed default-enabled kernel6 boot.

## Candidate mechanism and review

The spin-class word uses a phase hint while its queue remains live. Ownership
still comes from the holder/pending protocol and exact queue head, not the hint.
The hint is removed with final tail retirement; pending undo preserves it.
This avoids per-address history, arbitrary tail-node lookup and polling in
the admission window. In this frozen kernel5 binary, `kd_spin_queue_phase` defaults to false and
`kd_spin_phase_wait` defaults to zero. The runner explicitly enables queue
phase for the ordinary grid and checks both phase values; polling stays zero.

The [static review](review.md) was written before the candidate commit was
created. Its header records that stage; it is static reasoning, not a build
or test receipt. It identifies last-head/pending, last-tail/new-enqueue and
option-disable races, and the shared raw/rwlock queue scope that require checks.
Do not interpret approximate counters as ownership or physical-chain proofs.

## Executed comparison

[run-queue.py](run-queue.py) and [summarize-queue.py](summarize-queue.py) are
the frozen scripts for this completed campaign. The runner requires the exact source
identity file, expected release, disk serials, unloaded comparison modules,
normal initial taint and inactive tracing. It keeps phase_wait=0 and records
both initial and effective parameters. Queue phase is enabled for the default
grids; the 0/1 controls alternate order and preserve Native/KD/TCLock alongside
each KD setting. All parameter values are restored in cleanup.

The main run completed 741 checked points in 483.366 seconds including setup:

* Three-way standard grid: 1/5/8/16/32 workers, lines 1/16, post=64.
* Three measured backend-order rotations for the standard, policy and NUMA
  grids, each with 250 ms warmup and 1,000 ms timing. The post=0 control has
  two repetitions. The five-worker cell checks the polling candidate's regression.
* Balanced 32-worker CPUs 4–35 across two 20-CPU NUMA nodes; packed CPUs 0–31
  and post=0 controls remain separate. Controller/emulator use CPUs 38–39.
* Queue-phase 0/1 checks for the actual spin/clobber/nested/raw/handback families.
* Shared-helper checks for actual `rwlock`, `rwlock_cl` and `rwlock_hb` families,
  plus rwlock with 20% writes. No nonexistent `rwlock_raw` family is invoked.
* The actual API check is invoked initially and under each queue-phase value;
  its IRQ/BH checks are not presented as contended IRQ coverage.
* A bounded NUMA-order 0/1 control at 32 balanced workers, lines 1/16 and three
  rotated three-way repetitions, with queue phase enabled and phase_wait=0.
* Exact operation/write sums and shared-data deltas, zero reported reader
  mismatches, and progress by every worker passed. Main and supplement daemons
  exited normally and comparison modules unloaded normally.

Every rate retains KD offered/delegated/handback/session/plain-stop/NUMA
counters and raw deltas. TCLock spin execution counters are unavailable, so KD
zero counters in TCLock points cannot describe TCLock delegation. Functional
handback counts remain separate from ordinary spin timing. Serial progress
markers are emitted outside measured points and before warmups; the host must
not issue serial requests during timing.

## Same-boot throughput and remaining regressions

The ordinary grid below uses queue phase=1, phase_wait=0, kd_numa=1 and post=64.
All rates are Mops/s medians of three repetitions; complete minimum/maximum
ranges, every repetition and all event counts appear in
[measured-cells.md](measured-cells.md), [summary.json](evidence/summary.json) and
[rates-and-counts.csv](evidence/rates-and-counts.csv). D/H/plain-stop/NUMA columns
sum the three KD measurements of that cell, not warmups. Native KD deltas are
zero; TCLock proxy and handback counts are unavailable, because sampled KD
counters do not measure TCLock execution.

| Workers | Lines | Native | KD | TCLock | KD vs Native | KD delegated | KD handback | KD plain stops | KD NUMA deferred |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 9.4494 | 9.4517 | 9.4515 | +0.02% | 0 | 0 | 0 | 0 |
| 1 | 16 | 8.9583 | 9.0754 | 8.9003 | +1.31% | 0 | 0 | 0 | 0 |
| 5 | 1 | 4.5321 | 4.4022 | 3.2685 | -2.87% | 0 | 0 | 0 | 0 |
| 5 | 16 | 2.3446 | 2.3595 | 2.5325 | +0.64% | 0 | 0 | 0 | 0 |
| 8 | 1 | 4.5070 | 5.3976 | 5.1467 | +19.76% | 16,859,043 | 0 | 52 | 0 |
| 8 | 16 | 2.3487 | 4.1848 | 3.2045 | +78.17% | 13,138,994 | 0 | 5 | 0 |
| 16 | 1 | 4.5305 | 5.7276 | 5.8153 | +26.42% | 17,761,178 | 0 | 0 | 0 |
| 16 | 16 | 2.3129 | 4.1750 | 3.2290 | +80.51% | 12,902,286 | 0 | 0 | 0 |
| 32 | 1 | 3.3772 | 6.1762 | 5.6282 | +82.88% | 19,393,238 | 0 | 0 | 77,056 |
| 32 | 16 | 1.8260 | 4.4388 | 3.1370 | +143.08% | 13,719,357 | 0 | 0 | 54,720 |

There is no measured one-worker regression in this grid, but it does not prove
identical instruction cost. Five-worker short KD is 4.4022 [4.4020, 4.4090]
versus Native 4.5321 [4.5298, 4.5384], a 2.87% gap with zero delegation and
handback. Five-worker long KD also trails TCLock by 6.83%. At 16 workers,
short KD is 5.7276 [5.6673, 5.7366] versus TCLock 5.8153 [5.8150, 5.8193],
a 1.51% gap. These regressions remain open; no profile was collected to
attribute their remaining cycle cost.

At 32 balanced workers, ordinary short KD is 1.829x Native and 1.097x TCLock;
long KD is 2.431x Native and 1.415x TCLock. These ratios compare the matched
three-repetition medians in this grid. They are not qualified peak claims,
confidence intervals or unchanged-application results.

## Queue-phase on/off control

The same boot alternates policy order and rotates Native/KD/TCLock backends.
Both policies keep phase_wait=0; these rows isolate the queue-phase option
within this candidate. All cells have three measured repetitions. Event counts
below again sum only those three KD repetitions; all session and offered
counts, ranges and individual repetitions are in [measured-cells.md](measured-cells.md).

| Queue phase | Workers | Lines | Native | KD | TCLock | KD vs Native | KD delegated | KD handback | KD plain stops | KD NUMA deferred |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| kd_spin_queue_phase=0 | 5 | 1 | 4.5329 | 4.4018 | 3.2591 | -2.89% | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=0 | 5 | 16 | 2.3405 | 2.3591 | 2.5346 | +0.79% | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=0 | 8 | 1 | 4.5054 | 4.4529 | 5.1375 | -1.16% | 14 | 0 | 2,274 | 0 |
| kd_spin_queue_phase=0 | 8 | 16 | 2.3432 | 2.3789 | 3.1933 | +1.52% | 24,168 | 0 | 359,275 | 0 |
| kd_spin_queue_phase=0 | 32 | 1 | 3.3778 | 3.1626 | 5.6030 | -6.37% | 57 | 0 | 1,792 | 21 |
| kd_spin_queue_phase=0 | 32 | 16 | 1.8129 | 1.8171 | 3.1238 | +0.23% | 10,279 | 0 | 465,942 | 18,809 |
| kd_spin_queue_phase=1 | 5 | 1 | 4.5314 | 4.3993 | 3.2624 | -2.92% | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=1 | 5 | 16 | 2.3409 | 2.3592 | 2.5359 | +0.78% | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=1 | 8 | 1 | 4.5057 | 5.4063 | 5.1328 | +19.99% | 16,805,256 | 0 | 47 | 0 |
| kd_spin_queue_phase=1 | 8 | 16 | 2.3403 | 4.1872 | 3.1802 | +78.92% | 13,008,553 | 0 | 5 | 0 |
| kd_spin_queue_phase=1 | 32 | 1 | 3.3550 | 6.2110 | 5.6047 | +85.13% | 19,096,518 | 0 | 0 | 75,648 |
| kd_spin_queue_phase=1 | 32 | 16 | 1.8015 | 4.4644 | 3.1155 | +147.81% | 13,814,993 | 0 | 0 | 54,832 |

The five-worker short median changes by -0.06%, from 4.4018
[4.3966, 4.4073] to 4.3993 [4.3986, 4.3994], with offered/delegated/handback
all zero under both settings. This avoids the large five-worker regression
of the earlier polling experiment; that cross-boot experiment is motivation,
not a pooled baseline.

At eight workers, short medians rise 4.4529 to 5.4063 and long medians rise
2.3789 to 4.1872. At 32 workers, short medians rise 3.1626 [3.1598, 3.3602]
to 6.2110 [5.8703, 6.3717]; plain stops fall 1,792 to zero, delegated events
rise 57 to 19,096,518 and session events rise 54 to 4,730. Long medians rise
1.8171 to 4.4644, with plain stops 465,942 to zero. This matched intervention
is consistent with live queue phase preventing ordinary admissions from
repeatedly interrupting delegation. Approximate events do not measure actual
physical chain lengths or establish exclusive causation of the rate change.

## NUMA, placement and outside-work controls

The locality control holds queue phase=1, phase_wait=0 and CPUs 4..35 fixed,
then alternates kd_numa=0/1. Each row has three measured repetitions, with
Native and TCLock repeated alongside KD. The complete count columns and
per-repetition ranges remain in [measured-cells.md](measured-cells.md).

| NUMA policy | Workers | Lines | Native | KD | TCLock | KD vs Native | KD delegated | KD handback | KD plain stops | KD NUMA deferred |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| kd_numa=0 | 32 | 1 | 3.3812 | 3.0469 | 5.6185 | -9.89% | 9,532,439 | 0 | 0 | 0 |
| kd_numa=0 | 32 | 16 | 1.7841 | 2.2891 | 3.1078 | +28.31% | 7,058,256 | 0 | 0 | 0 |
| kd_numa=1 | 32 | 1 | 3.4250 | 6.3363 | 5.6185 | +85.00% | 19,448,187 | 0 | 0 | 77,168 |
| kd_numa=1 | 32 | 16 | 1.7997 | 4.4573 | 3.1017 | +147.67% | 13,996,065 | 0 | 0 | 55,792 |

NUMA ordering matters even after plain stops reach zero: short KD changes from
3.0469 [3.0413, 3.0474] to 6.3363 [6.1276, 6.3788], and long KD from 2.2891
to 4.4573. Short sessions are 2,331 versus 4,826 and long sessions 1,728 versus
3,490. Deferral events identify exercised ordering but do not directly measure
cache transfers. The kd_numa=0 short/long rows trail TCLock; they are retained.

The packed CPUs 0..31 control is separate from balanced CPUs 4..35: short
Native/KD/TCLock medians are 3.3425/6.3501/5.6097 and long medians
1.7953/4.6297/3.1224. Both arrangements still span the two NUMA nodes. They
are not pooled. The post=0 control has only two repetitions: its eight-worker
short KD median 5.2919 trails TCLock 5.4203 by 2.37%, and five-worker long KD
2.2823 trails Native 2.2915 by 0.40% and TCLock 2.5913 by 11.93%. Those
regressions are retained alongside the higher-load gains.

The translator-off short control has zero delegation/handback and KD versus
Native medians 4.4213/4.5320 at five workers, 4.4913/4.5108 at eight, and
3.1866/3.3840 at 32. The fast/plain path still has costs relative to Native;
this work improves contended delegation without claiming that all gaps closed.

## Functional coverage, counts and cleanup

The [main raw points](evidence/points.jsonl) contain 741 successes and zero
failed points. [Count accounting](count-accounting.md) lists every phase and
family separately, including warmups, learning, forced delegation, nested,
raw, handback, clobber and shared rwlock checks. The main all-phase totals are:

| Offered | Delegated | Handback | Sessions | Plain stops | NUMA deferred |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 432,608,549 | 429,700,828 | 991,781 | 1,475,152 | 1,773,616 | 7,060,079 |

These totals include functional and warmup points and cannot explain one
measured rate. All 991,781 handbacks are frontier events: spin_hb 335,826,
spin_hb_cl 226,347 and rwlock_hb 429,608. Ordinary spin timing has zero
handbacks. Raw spin has zero offered/delegated events, so it establishes local
execution coverage, not exercised delegation.

The original lines=1 mixed rwlock rows check progress/write totals but have no
multi-value reader comparison. A separately drained [supplement](supplement/result.json)
therefore ran two all-write learning points plus eight lines=16, write_pct=20
Native/KD checks, at 8/32 workers and queue phase 0/1. All ten passed; each
mixed row has positive reads and writes from every worker, exact totals and
zero reader mismatches. [Supplement points](supplement/evidence/points.jsonl),
[its runner](supplement/run.py) and the detailed [accounting table](count-accounting.md)
retain their independent records. Its duration was 7.579 seconds, on the same
boot as the main campaign. This is functional evidence, not a repeated
throughput comparison. Learning delegated 3,588,068 sections; the eight mixed
checks delegated 617,952, with handback zero in both groups.

The main API routine ran three times with 65 assertions each; the supplement
ran twice with the same 65 assertions each. Every call returned zero failed
checks. This is repeated coverage of 65 single-task local-object assertions,
not 325 distinct APIs or contended/delegated IRQ validation. The earlier
six-case, two-worker entry fixture provides the explicit overlap detector and
preemption/IRQ/BH checks. It ran with delegation off and does not establish
actual interrupt-handler entry or delegated IRQ/BH behavior.

Both [main cleanup](evidence/cleanup.json) and
[supplement cleanup](supplement/evidence/cleanup.json) record daemon rc=0,
normal removal of all five comparison modules, and restoration of every saved
parameter: adapt=Y, enter/exit=5/2, batch=4096, numa=Y, numa_after=32,
phase_wait=0, queue_phase=N. Only the pre-existing NLS module remains.
Both after-dmesg files have no BUG, WARNING, soft-lockup, hard-LOCKUP or Oops
markers, and both final boot UUIDs equal the initial candidate UUID.

## Interpretation limits and evidence map

The [independent runner review](runner-review.md) distinguishes exact sums and
protected-data checks from an explicit inside detector. It was written before
the supplement executed; its preparation-only wording is historical, while
the separate result/cleanup above establish execution. Nano all-write rows do
not exercise reader consistency. Entry checks, nano accounting and the mixed
supplement are complementary observations rather than a universal exclusion,
ownership, full-stack, arbitrary-nesting or whole-kernel proof.

The stopwatch stops before worker drain, while returned counts include
in-flight operations completed during that drain. All three backends use the
same convention; these are aggregate nano rates, not strict peak throughput.
Count sums across repetitions are not the counts of a hypothetical median
run. No profile was collected. KD event deltas cannot supply TCLock proxy or
handback counts, and delegated/sessions is not physical chain length.

All inputs, logs, failures and settings remain preserved. The earlier
[phase-wait report](../main-spin-phase-20261117/README.md) retains its failed
initial module build and successful retry and its five-worker regression.
This kernel5 build succeeded on its first recorded attempt. No result is
pooled across those kernels, configurations, boot identities or placements.

* [Archive receipt](archive.json): 505,747 bytes, SHA256
  `0e5e6386b91236022a8aa145358f8744b79950de8131cb44df6193b7cb152da6`;
  85 archive members accepted only as safe relative regular files/directories.
* [Main run log](runtime/run.log), [result](runtime/result.json),
  [identity](evidence/identity.json), [summary](evidence/summary.json),
  [all points](evidence/points.jsonl), [rates/counts](evidence/rates-and-counts.csv).
* [Supplement log](supplement/run.log), [result](supplement/result.json),
  [identity](supplement/evidence/identity.json), [all points](supplement/evidence/points.jsonl).
* [Complete measured cells](measured-cells.md), [phase/family and supplemental accounting](count-accounting.md),
  [runner review](runner-review.md), [source review](review.md).
* [Build log](build/build.log), [module logs](build/module-logs),
  [signed artifacts](build/signed-artifacts.json), [exact config](build/config),
  [source identity](main-queue-identity.json), and [file hashes](SHA256.json).
