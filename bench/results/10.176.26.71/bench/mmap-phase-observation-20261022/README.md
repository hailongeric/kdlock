# Actual mmap writer phase observation, 2026-10-22

Status: preparing a bounded observation experiment; no protocol change or new
live run yet. Main agent is the sole writer and serial VM executor. Helpers
review source and retained evidence only. Start from clean `cace439` on 380G10;
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
