# Pending-admission mmap diagnostic continuation, 2026-10-22

Status: `pair-2` completed both profiles serially and restored recovery. Both
workloads validated and drained; both fixed endpoints failed. Diagnostic stacks
are available, but no timing is accepted and all seven mutex causes remain unresolved.
Main agent only writes and executes VM work; helpers remain read-only. Start
from clean `a03204f`. The same VM was freshly verified idle on recovery
`6.1.159-kdclobber2`, boot `68924d08-9913-4e43-91f8-3643e3331c09`, with exactly
73 modules and all 5,686 recovery module files preserved. The real recovery
snapshot and original pins were verified. Source process checks found no
observed competing writable checkout descriptors; inaccessible processes and
the absence of an application task registry are recorded limits.

All eight prior contention-stage archives and all 31 earlier archives remain
unchanged. The original `pair-1` refusal at 72 versus 67 and both unrun profiles
stay fixed in the [preceding report](../mmap-contention-20261022/README.md).

## Continuation contract

Only repository-side coordination changes. Keep the guest profiler, candidate
image, validated workload/payload, original full admission and fixed endpoint
checks unchanged. Run one Native then one KD profile, serially. Concurrent
readers stay local; mmap stays separate from fault cycles. TCLock actual-MM
workloads remain excluded. New p95 is deferred and earlier latency evidence
remains fixed.

After each candidate boot, a refused capture with only extra worker threads
is pending admission. Preserve every capture and remain on that same boot.
Observe at least 60 seconds apart, with fresh source ownership and guest drain
checks before each observation. Original task identities, affinity, all host
controls and the complete guest gate must pass before a profile starts. A
count alone never grants admission. No observation count grants acceptance or
declares a persistent blocker. Other changes require diagnosis; no host
settings, services, networking, credentials or access controls may change.

The original guest driver performs the complete admission immediately before
loading. The source controller preserves the immediate endpoint after recorder
exit including flush, before validation and normal unload. Later captures can
admit a distinct unrun mode; they never replace an endpoint or rerun a completed
profile. Record observation, profile-command attempt, actual completion, mode,
boot and endpoint separately. A timeout retains uncertain state and prevents
another run or automatic reboot.

Once both profiles complete and drain, seal/review their evidence and restore
recovery. If a specifically established persistent condition prevents progress,
retain its duration/evidence and exact missing condition, verify drain before
restoring recovery, and report it. A first transient refusal is not completion.

The predeclared source hypothesis and stack interpretation from the preceding
stage still apply. Filter exact worker TIDs/CPUs and active intervals; separate
leaf symbols from supported caller ancestry, account globally for loss/throttle
and unresolved frames, and retain profiler configuration and overhead limits.
One sampled pair supplies intrusive diagnostic evidence, not accepted plain
throughput, repetition variance or an isolated protocol-cost proof. All 24 prior
timings remain rejected and all seven original causes remain unresolved unless
new demonstrated evidence resolves a specific claim.

## Focused checks before transition

Synchronization of `601541e` copied 18 changed files, verified all 4,060 tracked
hashes and deleted no project files. The frozen `checks-1` contains 198 source
files, including private daemon `.inc` files and both admission helper/test
files. In the same recovery boot, both basic C programs and all five directly
affected pending-admission tests passed; dependency validation passed. The
daemon-policy test's deliberately failed children are expected negative cases.
No full suite ran. The unchanged guest profiler's four and serial driver's ten
focused tests remain the separately recorded preceding-stage evidence.

The new checks result SHA-256 is
`fbcf9f3b7ba530280781f3616925bca49c830e3ae03cc74b657f812daff82836`.
Exact baseline modules, idle state, recovery preservation and no fault-pattern
matches were rechecked before archiving. Local evidence is under
`bench/results/10.176.26.71/raw/bench/mmap-contention-followup-20261022/`;
guest evidence is under the corresponding
`/root/kdlock-evidence/10.176.26.71/bench/mmap-contention-followup-20261022/`.
The `pretransition/archives/archives.json` SHA-256 is
`827bba69b1d461e1e086e596039820942a38364d9fa3e32c4c99ae1e76219cd0`;
its two archives total 519,757 bytes. All 39 earlier archives remain separate.

Read-only protocol review found no blocker to the first attempt. On a guest
refusal, `ADMISSION` alone does not prove no payload loaded: retain the exact
trace and verify launch state plus fresh drain. Resume a returned recorder only
through its existing finish step and original endpoint; never repeat a
completed profile. All source files stay frozen while the pair controller runs.

## Approved retirement and settling continuation

The original follow-up `pair-1` retained 434 pending observations over roughly
7 hours 27 minutes. Neither profile was attempted. The user explicitly approved
retiring only the waiting coordinator and resuming on the same Native boot with
60 seconds settling after every guest idle check. No admission criterion changes.

At `2026-10-22T02:57:30.280546Z`, a parent-only pidfd SIGINT retired coordinator
PID 792734 (start ticks 970588747). The traceback locates interruption in
`admission_wait.wait` at `sleep(interval)`; its tool session returned 130. The
process and its command chain exited. All 880 original command receipts report
EXITED/0, and the final state records zero profile attempts and completions.
The old `KeyboardInterrupt()` and `drain_requires_review` state remain fixed;
subsequent drain proof is separate. The signal was observed about 0.216 seconds
after the latest pending branch, not claimed to have an atomic timing guarantee.
No workload, recorder, process group or VM worker received a signal.

Fresh guest idle and preservation checks then passed on unchanged Native boot
`89400671-89e1-4797-b703-70cb4ac71c67`, release `6.1.159-kdmm1`, `kd_mmap=off`,
with exactly 73 baseline modules and no profiler or mmap/fault workers. The
candidate, recovery/default boot configuration and all 5,686 recovery module
files remain preserved. `control-stop-1.json` binds the retirement, final pair
state, command receipts and fresh checks; SHA-256:
`e66d9493141afff777563b65ce2e84abd9711128858b302be80c686c7a781dd1`.
The original final `pair-1/result.json` SHA-256 remains
`4a6aa252b8ad9f8344230cc8fc5f8d45d3aa7575585136bdab1bd9aa67fb8e39`.

`run_pair_resume.py` creates separate `pair-2` source evidence and `native-2`,
`kd-2`, `recovery-2` guest blocks. It requires the stopped coordinator's exact
receipt, absent old process, zero prior attempts, fresh idle and unchanged
Native boot. The copied original transition/request/host-capture hash chain
retains that boot's provenance. Every new observation follows a guest idle
check, a recorded 60-second settling interval, a source ownership check and the
unchanged complete host capture. Extra-thread refusals remain pending; the
original complete guest gate still runs before loading. The guest profiler,
frozen inputs, candidate image, recording settings and immediate endpoint are
unchanged. Only the source coordinator and this report change; no guest source
synchronization or new workload build is needed.

The source coordinator is reviewed statically. Existing focused VM checks cover
the unchanged admission helper and recording/endpoint drivers; they do not claim
to test the new same-boot orchestration. The new run must retain its actual
admission, command, endpoint, completion, drain and recovery receipts. This
continuation is not performance acceptance; all seven original causes remain
unresolved.

## Completed pair-2

Clean source commit `889a840ee3fc85fd8a4b589bb5e3f055413e54df` ran the source
coordinator; the guest driver, validated frozen binaries and candidate kernel
were unchanged. Native reused its original boot. Native observations were
68 then 67 tasks; KD observations were 69 then 67. All four observations follow
recorded settling: guest command return to capture dispatch was
60.102760–60.103726 seconds. Both complete guest admission comparisons passed
before loading. Both admissions passed after the recorded settling intervals;
this does not establish why the earlier checks saw extra workers.

| Mode / guest block | Boot UUID | Completed mmap/munmap cycles | Business errors | Fixed endpoint | Drain |
| --- | --- | ---: | ---: | --- | --- |
| Native / `native-2/profile` | `89400671-89e1-4797-b703-70cb4ac71c67` | 198,464 | 0 | FAIL, 85 vs 67 tasks | Passed |
| KD / `kd-2/profile` | `7ae32334-7d07-4849-84dd-f11adf89609b` | 50,048 | 0 | FAIL, 74 vs 67 tasks | Passed |

Exactly one profile ran per mode. Each original endpoint starts immediately
after the controller observes recorder-command exit, including flush: recorded
capture-dispatch gaps are 744 ns for Native and 711 ns for KD. These are dispatch
gaps, not claims that the remote capture completed in that time. No later
capture replaces either failed endpoint. Both modes retain zero fault callbacks,
exact maps/closes/completed counts, zero live VMAs and final
`files=0 mm_refs=0 destroyed=1 release_errors=0`. No reader delegation or
page-fault workload ran in this diagnostic.

Both recordings use the retained perf tool, `cpu-clock:k`, 99 Hz, inherited
kernel frame-pointer chains, the monotonic clock and collector CPU 63. Work is
the same untouched mmap/munmap loop on workers 0–15. The recorded whole rates
are 99,006.432 and 24,969.222 cycles/s; worker CPU is 30.784 and 262.080
microseconds/cycle. These are **single intrusive, rejected observations**, not
plain timing replacements or an accepted ratio. Repetition variance is
unavailable for this pair (one per mode); qualified n=0. The earlier 24 rates,
ratios and variance remain separate and rejected.

The coordinator exited 0. All 55 source command receipts reached EXITED: 53
returned zero; the first KD and recovery reachability probes returned SSH 255
during reboot, followed by successful boot verification. Recovery is restored
on boot `9545bcf9-e8ae-4515-be1b-0a5309afc18f`, release `6.1.159-kdclobber2`,
Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, exact 73-module set and
5,686 preserved recovery module files. Recovery default and candidate image
bindings remain unchanged. Each transition retains its six known `fd0` I/O
error lines; no configured kernel-fault pattern matched. This is not an
error-free-boot claim.

## Offline integrity and stack attribution

The archived perf data was exported on the source host with the exact candidate
ELF and captured runtime symbols. Before worker filtering, a separate binary
parser reconciled every sample's PID/TID, CPU, monotonic timestamp, period and
entire address chain with both the raw and symbolized exports. Caller addresses
are unchanged return addresses, not return-minus-one; sampled leaf addresses
are never adjusted. All exported symbol bases match captured kallsyms.

| Global recording check | Native | KD |
| --- | ---: | ---: |
| Raw/exported samples | 571 | 1,148 |
| Selected worker/CPU/active-interval samples | 570 | 1,148 |
| Excluded non-worker samples | 1 | 0 |
| LOST / LOST_SAMPLES / THROTTLE / UNTHROTTLE records | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| Raw chain entries, including kernel context marker | 3–19 | 5–16 |
| Unresolved exported symbol frames | 0 | 0 |
| Misordered timestamps | 0 | 0 |

No chain hits the recorded maximum 127, and no export truncates a raw chain.
Intermediate frame omission is demonstrated: 13 Native spin samples omit the
explicit slowpath frame while retaining `rwsem_spin_on_owner` and the matching
`down_write_killable` caller. Other writer context means not identified as spin,
not proof that no spinning occurred. Each raw
numeric export retains a warning about the absent default vmlinux; the separate
symbolized export explicitly uses the verified ELF and has empty stderr. The
binary reconciliation does not depend on the default-symbol lookup. All five
export commands per mode returned zero. No loss/throttle check is performed
only on the filtered worker subset.

Classification uses the predeclared order: physical KD gate or Native optimistic
spin/OSQ first, then writer acquire/release, reader release/downgrade, common
MM/VMA/file work, and unknown/interrupt work. Generic scheduler/wakeup/spin
symbols need surviving caller evidence. IRQ/softirq boundaries prevent using
interrupted lock ancestry. Operation and queue subtype remain separate.

| Selected sample context | Native count (%) | KD count (%) |
| --- | ---: | ---: |
| Physical KD gate / Native optimistic spin or OSQ | 266 (46.67%) | 0 (0%) |
| Writer acquire/release excluding above | 101 (17.72%) | 1,057 (92.07%) |
| Reader release/downgrade excluding above | 37 (6.49%) | 61 (5.31%) |
| Common MM/VMA/file/payload work | 150 (26.32%) | 27 (2.35%) |
| Other/unknown | 14 (2.46%) | 3 (0.26%) |
| Interrupt work | 2 (0.35%) | 0 (0%) |

Every selected period is 10,101,010, so sample and period shares agree. These
shares describe sampled on-CPU contexts, not fractions of elapsed waiting time.
Profiler execution is explicitly flagged within the retained categories: 22
Native and three KD stacks contain `perf_*` or `__perf_*` frames. Common MM
includes profiler-related mmap notification work; recording overhead is not
isolated.

KD has 1,000 phase-admission samples (87.11% of selected): 653 through
`prepare_to_wait_event`, 294 through `schedule`, and 53 through `finish_wait`.
Another eight belong to reader-drain admission. Proven phase-wake contexts
contribute 48 writer-release and 57 downgrade samples; two read-release samples
belong to reader-drain wake. Three other KD lock-context samples retain unknown
queue subtype. No selected sample is attributed to the physical KD gate;
zero samples do not prove absence of execution or cost.

The sampled leaf remains distinct from the caller context: KD's leading leaves
are `_raw_spin_unlock_irqrestore` (812) and `finish_task_switch.isra.0` (299).
Sampling after IRQ restoration can concentrate events at the restore boundary,
so these counts cannot identify the literal cost of the unlock instruction.
Native's leading leaves include `osq_lock` (143) and `rwsem_spin_on_owner` (92).

This pair supports the narrower observation that KD's sampled CPU execution
concentrates in writer phase waiting and related scheduler work. It is consistent
with the source hypothesis and gives a concrete next investigation target.
It does **not** establish a wake-all causal regression, queue length, wake count,
successful reservation count, off-CPU delay, ownership history or accepted
protocol-cost difference. These actual-MM writers execute in their original
tasks; the result does not measure DIRECT delegation or unlock ACK overhead.

## Evidence and remaining gaps

Local root: `bench/results/10.176.26.71/raw/bench/mmap-contention-followup-20261022/`.
`pair-2/result.json` SHA-256:
`58d11fe0f4679256ccefc1f5926fdb7ac8e4f8f0bd46b1ee56da3c53181f4cd3`.
Its Native/KD result hashes are respectively
`ee0d59b89e0ba850d38532b39ee6b9da220c3c981edf8006b675b4c5150a8341` and
`7d4321b8cfe084bfef1704e0c5397555d4f9ee0ad9ec63aa4f691b3fc6a0c53c`.

| Archive manifest relative to local root | SHA-256 |
| --- | --- |
| `pair-2/native/archives/archives.json` | `720519a04afe04afc9af523b440c8ad8da78305f69b8b34287dc41d3fe43e472` |
| `pair-2/kd/archives/archives.json` | `05504d7f7f319acd18cf63a9c92d73fa4398ca0955b8045838f246f6d54d158a` |
| `pair-2/recovery/archives/archives.json` | `ae59db55a6ad0532e5a1ecb849a236b9e1e91d7fb916d43d28ba6a700b1cfb38` |
| `retired-control-archives-1/archives.json` | `6d9597011f66d65496fabb8f848ef6aa4a64cb2eb5a06a98ae3f1d749fafbc7f` |

The six pair archives total 3,491,115 compressed bytes, with 168 files,
13 directories and zero links. Independent decompression, inventory and binding
review passed 1,648 checks. The stopped-control archive has 3,090 files and
12,537,456 bytes; its SHA-256 is
`8328ffa33d0546610496339e5f42514516e54deefbd779604a6f670abce6fba3`.
The separate stopped-observation/archive review passed 30,016 inert checks.
All 42 prior archives (39 earlier, two pretransition, one stopped-control)
remain unchanged at 32,866,084 bytes. Offline exports, reconciler, per-sample
classification and summary are retained under `offline-1/`.

The final local control/offline archive is
`completed-local-archives-2/control-and-offline.tar.gz`: 392 files,
5,535,449 compressed bytes, SHA-256
`6b1cb1816ec0531d36d2dd8ea647fd18cb99f2e30ca98604f74691b2f44ad1a2`.
Its `archives.json` SHA-256 is
`f7f7381bdbde0f3848fd6db6ab5de086a1bd3e102643cd6cf762a48136d3e4d7`.
It includes source control receipts, console, read-only review summary, exact
export commands, binary reconciler and all classified samples; the six guest
archives remain separate. Independent packaging review passed 2,688 checks
with zero mismatches, including all 142 extracted Native/KD guest files against
their separate sealed archives. The final `offline-1/analysis.json` SHA-256 is
`4dce581f04fa4f88ed5389c09875edeb5e37947b6e104b1d5f869835cfb101bb`,
and its `analysis.py` SHA-256 is
`f8e536c1f776293cff493deeada6f10cfd4cbabb53eefc857a463be953dc3a7a`.

All seven original public-mutex causes remain **UNRESOLVED**: c08 at 3/4/5
workers, pipe bytes at 3/5, pipe capacity at 5, and RCUHT at 2. Their original
baselines and follow-up source identities remain distinct. Qualified throughput
repetitions/variance and the repeated host-endpoint failure remain open. New p95
stays deferred. No protocol fix, broader kernel replacement, unsupported TCLock
MM compatibility or performance acceptance is claimed. Future phase-admission
work must preserve killable cancellation, reader concurrency, exact ownership,
downgrade ordering and wake/retirement obligations.
