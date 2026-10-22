# Actual mmap writer phase observation, 2026-10-22

Status: `stage-1` completed serial correctness and one metadata diagnostic on
unchanged `kdmm1`, then restored recovery. Repeated phase-admission failures
after blocking are observed; the host endpoint failed, so timing is rejected.
No protocol change or performance acceptance follows. Main agent is the sole
writer and serial VM executor; helpers review read-only. Preparation began
from clean `cace439` on 380G10;
the same VM was freshly idle on recovery boot
`9545bcf9-e8ae-4515-be1b-0a5309afc18f` at 04:00:37.247866 UTC, with exactly 73
modules and no project worker/profiler. Known coordinator/child PIDs were absent.
The source descriptor scan observed no writer but could not inspect 530 other
processes; the task inventory independently reported no competing kdlock task.
Fresh ownership/drain and the real recovery snapshot remain prerequisites.

## Evidence and predeclared discriminator

The unchanged candidate is `6.1.159-kdmm1`, Build ID
`687ff5a29315d732f93a618e50ac407c794bbf9b`, ELF SHA-256
`7c7305c78f5466276a79e3cde4d2809dce67a9677896b30e268d8f4e3d08f236`.
The [completed pair](../mmap-contention-followup-20261022/README.md) selected
570/571 Native and 1,148/1,148 KD samples by exact worker, CPU and active interval.
Each period is 10,101,010. KD phase admission accounts for 1,000 samples: 653
prepare-to-wait, 294 schedule and 53 finish-wait contexts. Native has 266 samples
in optimistic-spin/OSQ context. Reader-drain admission contributes eight KD
samples; no selected KD sample identifies the physical gate. Native/KD common
MM contexts contain 150/27 samples. These are sampled contexts, not cost or
ownership measurements. IRQ reenabling concentrates 704 KD phase samples at
spin-unlock restoration; intermediate frames are demonstrably missing, and
22 Native/three KD stacks contain profiler execution. Both endpoints failed.

**Hypothesis:** repeated unsuccessful phase predicates after actual blocked
resumptions amplify writer-admission work under contention. The current samples
cannot distinguish that from initial enqueue/recheck, a single blocking wait,
or schedule calls that never switch out. The killable path has no ordinary
writer's bounded pre-publication polling. All phase waiters are non-exclusive;
merely replacing wake_up_all with wake_up would still wake every such waiter.

Choose one metadata-only observer on the existing candidate and frozen
16-worker mmap client, with no simultaneous perf sampler and no wake/ownership
change. Bind exact emitted probe sites, task identity, semaphore and acquisition
sequence. Count initial/queued predicate failures, successful reservations,
phase and reader-drain schedule calls, actual scheduler departures/resumptions,
post-resumption predicate outcomes, gate transitions and final success/EINTR.
Keep no-switch scheduling and runnable preemption distinct from blocked waits.
No counter authorizes an acquisition, release or cleanup.

Many blocked resumptions followed by failed predicates support retry amplification
under this observer. Few such retries weaken that explanation. Reader-drain or
gate blocking instead identifies a different target. These counts alone do not
identify wake-all fanout or phase-wake losers: that requires an exact queue/wait
entry/wake callback correlation, beyond this first discriminator. Observer
perturbation prevents inferring uninstrumented rates or literal instruction cost.

Before the single KD diagnostic, require meaningful deterministic observer
controls: uncontended success, queued progress, phase and reader-drain killable
cancellation with rollback, concurrent readers, a killable downgrade transition,
nested distinct objects, and full task/module teardown. Require exact source and
instruction-byte binding, balanced records, zero missed probes/overflow/identity
errors, and intact existing business oracles. All builds/tests run serially in
the same VM. Baseline sources/images/binaries stay frozen; new observers and
failed attempts have separate identities.

Use 60 seconds settling after guest idle checks, unchanged full admission and
immediate command endpoint. Export and normal unload follow that original
endpoint. A timeout is not drain and must not signal workers or justify a new
run. Restore and verify recovery at the end. Concurrent readers remain local;
page faults are a separate workload and unsupported TCLock bodies are excluded.
New p95 is deferred. All seven original mutex causes, qualified performance and
variance remain unresolved; no acceptance follows from this experiment.

## Prepared implementation and review

The new observer is in `workload_modules/mmap_phase_observer/`; the external
serial driver is `bench/mmap_lock/phase_observation.py`. The original API fixture
remains byte-identical (SHA-256
`33de9a40c4d95f6c2da759db362e60a9e14860a75a607de44efb221968e39c97`).
The separate `tests/kernel/mmap_lock/phase/payload/` derivative adds killable
nested acquisitions, phase/drain cancellation controls and a killable downgrade
waiter. It retains all original ownership, rollback, concurrent-reader,
IRQ-transfer, reference-count and destruction checks. The original fixture also
runs observer-off before these controls. No production lock source is changed.

Fourteen instruction probes bind exact bytes in the unchanged image. Entry is
at `+0x9`, after fentry and before argument modification; `+0xd7` records the
epilogue status, not an independently proven function return. Only the outgoing
scheduler callback updates its current task's preallocated record. A blocked
departure requires non-preemption, a sleeping saved state and `on_rq == 0` under
the scheduler's runqueue lock: a pending signal can otherwise leave the saved
state sleeping while the task actually remains runnable. A paired schedule
return is classified as no-switch, runnable-only or blocked. No switch-in
timestamp, wake source, fanout or off-CPU duration is claimed.

Exact retained task/TGID identities and descriptor references survive the host
endpoint. STOP requires independently exited workload tasks (or the joined
fixture contract), unregisters and synchronizes callbacks, then releases mm
references. Module pinning survives control-fd close and timeout. Invalid
counts reject observations; they neither authorize cleanup nor obstruct cleanup
after independently proven task exit. Descriptor retention changes destruction
timing and is part of this intrusive diagnostic.

Each of the 16 exact worker records must have `entries == epilogues == success ==
2 * completed`, balanced wait/reservation counters, zero missing/error/active
events, and its entire first-entry to last-epilogue envelope inside that worker's
validated active interval. Any boundary contamination rejects the whole
aggregate; counts are never silently subtracted. The prior frozen 683 bindings
remain prerequisites. The new source, binaries, correctness results and endpoint
are separately recorded. Five focused receipt tests include negative identity,
window, missing-event, schedule and business-denominator controls.

Fresh preflight rechecked the real recovery snapshot, original QEMU PID 257489
and 67 pinned threads, and rehashed the preserved recovery/candidate files and
recovery boot default. Live validation has not started at this preparation
checkpoint. All reviewers were read-only and reported no files touched.

## Completed serial stage

Frozen observer/control source: `d9210e13d6d2feb2ee92b86720675c0f678ac1db`.
Synchronization copied 16 changed files, verified 4,072 tracked hashes and
deleted nothing. The original 683 workload bindings remain unchanged. New
preparation retains 427 source/binary path bindings separately; no kernel or
original workload binary was rebuilt. All builds and tests ran only in the original VM.

| Stage / run ID | Result |
| --- | --- |
| `kd-1/prepare-1` on recovery | Two basic C programs and five focused receipt tests passed; dependency check and all three module builds passed |
| `kd-1/controls-1`, observer off | Original API fixture: 139 checks, zero errors, idle and destruction checks passed |
| `kd-1/controls-1`, observer on | Separate fixture: 198 checks, zero errors; six calls, four successes, two expected EINTR; zero missed/error/active observations |
| `kd-1/diagnostic-1` | One original 16-worker mmap client; 64,576 completed cycles, zero business errors/faults/live VMAs; exact file/mm drain |
| `recovery-1` | Preserved recovery restored, idle with exactly 73 modules and all 5,686 recovery module files verified |

The build logs retain Perl locale fallback warnings; there were no compiler
errors. No full suite, page-fault workload, TCLock MM body or p95 measurement ran.
The control fixture covers nested distinct objects, cancellation before phase
reservation and during reader drain, rollback, concurrent sleeping readers,
downgrade, exact physical ownership, IRQ reference transfer and destruction.
Observer-held descriptor references are explicit and ordinary counts are checked
again after STOP. Baseline and instrumented fixture records remain separate.

KD boot: `d9ca7103-c978-4ee1-a109-463633ba5011`. Both controls and diagnostic
first observed 68 QEMU threads and refused admission; each later observed the
original 67 after recorded post-idle 60-second settling. The full original
guest gate passed before each execution. The diagnostic was attempted exactly
once at 04:41:24 UTC. Its immediate command endpoint captured **72 threads versus
67** and remains **FAIL**. Capture dispatch followed source-observed SSH exit by
1,452 ns; this is not a simultaneous observation of the last mmap call.
Cleanup/export happened afterward. No later capture replaced this endpoint.

Recovery boot: `4b9775c4-ac74-4db8-85c7-491f6b81f212`, release
`6.1.159-kdclobber2`, original default and Build ID preserved. The recovery log
retains the six known fd0 I/O messages; no fault-pattern matches were reported.
The coordinator exited normally with code zero. All 47 source child-command
receipts are EXITED: 46 zero, one SSH 255 during the requested reboot followed
by verified reachability. A fresh source check found no listed coordinator,
retained child PID or writable checkout descriptor; 541 other processes were
inaccessible to descriptor inspection. The guest was verified idle before
sealing recovery evidence.
The 54 legacy guest command receipts retain arguments/PIDs/start/timeout but
not individual exit-code fields. Successful enclosing commands and checked
driver progression support their normal completion; they are not reported as
54 independently exit-coded receipts.

## Observed admission behavior

All 16 exact task records reconcile to the workload's mm/semaphore identities
and active intervals. Every worker has exactly two successful writer calls per
completed mmap/munmap cycle. Aggregate counts equal the per-worker sums; missed
probes, errors, active records, unexpected EINTR and gate errors are all zero.

| Metadata | Count |
| --- | ---: |
| Successful writer acquisitions / epilogues | 129,152 |
| Initial reservation failures; eventual queued reservations | 120,625 |
| Initial reservations without phase waiting | 8,527 |
| Phase prepare-to-wait returns | 1,891,495 |
| Phase scheduling calls / returns | 1,770,870 |
| Phase blocked scheduling returns | 1,683,343 |
| Their next predicate fails, without cancellation | 1,583,015 |
| Their next predicate reserves admission | 100,328 |
| Phase schedules with no switch / runnable-only departure | 87,525 / 2 |
| Reader-drain blocked returns / no-switch schedules | 5,581 / 45 |
| Physical-gate blocked / runnable departures | 0 / 3 |

**94.03996%** of blocked phase-schedule returns are followed by another failed
predicate. There are **13.03381 blocked phase returns per successful acquisition**
and 13.71152 queued predicate failures per acquisition. The driver's
`failed_predicates_per_reservation` field specifically counts queued failures.
Every worker exhibits failed retries: blocked returns/acquisition have
min/median/max **8.093 / 13.115 / 15.124**, and next-predicate failure percentages
have **90.340% / 94.112% / 94.860%**. Workers complete 3,584–5,248 cycles.
These are within-run differences, not repetition variance.

This supports retry amplification under this observer and distinguishes it
from predominantly initial queue checks, no-switch schedules or physical-gate
blocking. It does not establish wake-all causality: exact wait-entry/wake-callback
correlation was not collected. Breakpoints, scheduler callbacks, timestamps and
descriptor retention perturb the workload. Aggregates do not retain individual
acquisition retry distributions or prove starvation freedom. The controlled
fixture did not independently force failed-after-block, no-switch or runnable-only
episodes; these remain explicit control-coverage gaps despite their observation
and balanced accounting in the live diagnostic. Selective-wake changes still
require multi-writer/reader fairness, cancellation-around-selection, rollback
successor and downgrade/cohort controls before implementation acceptance.

The rejected instrumented whole/peak rates are **32,188.884 / 40,101.742 cycles/s**.
They are retained evidence, not comparable to earlier perf profiles or plain
repetitions. There was one metadata run, no matched Native metadata run and no
repetition variance estimate. Qualified repetitions remain zero.

## Evidence and unresolved scope

Source evidence is under
[`raw/bench/mmap-phase-observation-20261022/`](../../raw/bench/mmap-phase-observation-20261022/);
guest evidence is under the corresponding
`/root/kdlock-evidence/10.176.26.71/bench/mmap-phase-observation-20261022/`.
The [`stage-1/result.json`](../../raw/bench/mmap-phase-observation-20261022/stage-1/result.json)
binds preparation, controls, one diagnostic, admissions, endpoint and recovery.
The independent inert arithmetic reconciliation passed **267 checks**, zero
mismatches, and retains
[`analysis.json`](../../raw/bench/mmap-phase-observation-20261022/offline-1/analysis.json)
and [`workers.csv`](../../raw/bench/mmap-phase-observation-20261022/offline-1/workers.csv).
Analysis SHA-256:
`410558f23e9ab528973e86aa829f5e21801d406f73bc49c2ff999c1310e94021`.

| Receipt / archive | SHA-256 |
| --- | --- |
| Controls result | `9c86270a9e87839171980beaccb4c8cd19f234dc34878a8acc82745172c9b394` |
| Diagnostic result | `f8fb33bc81ccd7cf94132ca09cf9ee60ea21dfa69ec2dafb66878713b6530b1a` |
| KD archive manifest | `5f31b48921d5cfa5a4177fbb5b909a4e46bc0a997de26883b3150493ff007838` |
| KD transition archive | `aa76054882c7e49df349ffaab7ab60559b8a5c3f71dcfcd3eead58b2ec233ca8` |
| KD metadata archive | `267111e56ec5df1f4d09f5e7510547a1d0f4c047cb051599ee8aaf8766395c0d` |
| Recovery archive manifest | `c0aee93f632353b9d399e3180605070d3e764c8aa80df4d1feb5023cd57180aa` |
| Recovery transition archive | `e90494657061ab7ae26db72c6742800ef8f65a0e3f2e4b777e9a184611010b8c` |
| Recovery metadata archive | `0b3e8c71a5fa575d47db1ed3e9bc687ba24ce6ea601037c2c7a263dec4373df1` |

The four guest archives total 2,666,091 bytes and include frozen sources/modules,
basic/receipt/build logs, original and instrumented business assertions, every
fault scan, observer records, command and unload receipts, and recovery proof.
Earlier baselines and pair-2 profiles remain separate and unchanged.

Independent archive/content review passed **5,174 checks**, zero mismatches:
5,145 current-stage checks and 29 preservation checks. It verified 427 regular
files, 32 directories and no links in the four guest archives, all 427 new
preparation bindings and all 683 original frozen-input bindings. The ten prior
follow-up archives and six manifests remain unchanged at 22,083,777 bytes.

Local preflight, all source command receipts, frozen coordinator sources,
offline exports, arithmetic script/CSV and read-only review findings are sealed
separately in
[`completed-local-archives-1/control-and-offline.tar.gz`](../../raw/bench/mmap-phase-observation-20261022/completed-local-archives-1/control-and-offline.tar.gz):
208 files, 353,760 compressed bytes, SHA-256
`a1edfdf4bb3a7caa4e0dbaa501419e2d41074079b1316d6ba7a7d7b5791132f8`.
Its manifest SHA-256 is
`b31eef299ec5f14400ac89a7442e9672b782c67884e6d28685cc9aaba848b3f4`;
the final `stage-1/result.json` SHA-256 is
`3a514eb0cc51e77fcbb4a2fe2dd6afb811c5e9c2d1562fb217017969f6ce06f6`.
Final local packaging review passed **2,134 checks**, zero mismatches, including
all 208 members, all 12 extracted guest files and all six frozen control sources.
The four separate guest archives remain unchanged. Both archive reviews and
the metadata review were read-only; no helper edited a file or contacted the VM.

All seven original public-mutex causes remain **UNRESOLVED**: c08 at 3/4/5
workers, pipe bytes at 3/5, pipe capacity at 5, and RCUHT at 2. The repeated host
endpoint failure, qualified throughput repetitions/variance, observer control
gaps and wake-source attribution remain open. Readers remain local/concurrent;
mmap and page faults remain separate workloads. No lock-policy change, broader
kernel replacement or performance acceptance is claimed.
