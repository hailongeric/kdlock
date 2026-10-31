# Local writer queue and reader fast paths

This isolated candidate starts at `f7a84065e84474380faa37eeadfdf534abd72a68`.
The preceding `22d62d5c13cad3c61c97dd47524da908769f1a52` experiment and its
report `a435ab376ec59f54d0db88a993436a8f854400c2` remain rejected performance
evidence. This document precedes implementation. Nothing here establishes a
performance gain or authorizes promotion without the checks below.

## Objective and diagnosis

Keep runnable contending writers on the CPU through the existing owner-aware
mutex optimistic-spin queue. Currently a local rwsem writer reserves the phase
before taking the physical gate. Other writers compete on that phase and can
sleep before reaching the queue that already serializes optimistic mutex
acquisition. The earlier bounded phase poll improved some shared-mm points but
left low-thread and process losses, and did not pass the nano gate.

The retained nano evidence also has losses in paths that never call the changed
killable function. Inspected mutex and rwlock instructions were unchanged, and
selected losses retained almost full worker CPU utilization. A larger parking
cost is therefore not established as their cause. This candidate also removes
verified unnecessary work from the ordinary rwsem reader fast path; new timing
must determine whether that helps. Historical scores will not be pooled.

## Acquisition and progress

1. For an unprepared object, every blocking local writer takes the physical gate
   first, then makes its own `0 -> -1` phase reservation, then drains accepted
   readers. Ordinary, callable, interruptible and killable entry points must
   agree on this order. Preparation remains a quiescent object-wide decision.
2. Prepared objects keep phase-first acquisition and positive delegated
   reservations. A gate-first waiter could otherwise hold the gate while waiting
   for a producer that needs it. Enforce the existing prepared-object contract
   at internal delegated entry as well as the public macro boundary.
3. Use a scoped signal-aware version of gate spinning for signalable local
   rwsem writers. Reuse exact OSQ grant, unlink and retirement operations.
   This includes prepared local signalable writers after phase reservation.
   Ordinary mutex callers and delegated producers retain their existing path.
   A completed acquisition/grant is checked before cancellation. A pending
   nonfatal signal ends optimistic spinning but does not cancel a killable wait.
4. Phase transitions and reader drainage receive at most 16,384 success-first
   condition probes per unpublished interval, ending on `need_resched()` or,
   for signalable callers, `signal_pending(current)`. There is no unconditional
   scheduling in the successful path. Physical-gate spinning retains its
   existing owner-running/predecessor-running checks and scheduler exit.
5. Exhausted reader/phase probes use the existing state-specific wait. Reader
   ownership does not identify whether the remaining readers are runnable;
   retaining a finite fallback is necessary for sleeping or lower-priority
   same-CPU holders. Reader drainage retains its one-jiffy recheck because an
   atomic or IRQ-disabled final reader intentionally omits a wake. Removing
   that recheck could strand a writer. Never infer reader progress from the
   gate owner, which at this point is the waiting writer itself.

Track gate acquisition and phase reservation separately. Before reservation,
cancellation releases only the gate. After reservation, rollback retains the
existing gate-unlock then phase-release order exactly once. A successor can
acquire the gate before its predecessor releases the phase; it must perform its
own reservation CAS and must never infer phase ownership from gate ownership.
The nonblocking phase-first trylock can remain: failure to obtain the gate
immediately releases its reservation. Downgrade remains reader publication,
gate unlock, then phase reopen. Readers always execute locally.

## Nano work

Replace the unused return-value reader increment with a nonreturning increment
surrounded by explicit before/after atomic barriers. Preserve the full ordering
against the writer reservation and the acquire phase recheck and rollback.
Outline the ordinary read slow path so a first-probe success avoids its saved
registers and stack frame. Preserve exactly eight initial probes, including the
first failed probe's scheduler check and pause, followed by the same reader OSQ
and wait path. Inspect emitted code on the VM before attributing any improvement.
Other nano families remain comparison controls; do not claim that rwsem changes
repair their historical losses without fresh measurements.

## Execution and acceptance

Source edits, Git and static inspection run on 380G10. All compilation, fixtures,
live workloads and timing run on the designated VM. Preserve existing user work,
recovery snapshots and old results. Use a new frozen source identity and distinct
kernel recipe/profile for the MM build. Do not edit running inputs.

Run basic plus directly affected fixtures: gate/phase cancellation and rollback,
grant-versus-signal ordering, fatal/nonfatal signals, prepared/local ordering,
reader publication races, trylock overlap, downgrade, and atomic final-reader
release. Update the actual linked-image writer wait-chain mapping for gate
waiting without reducing its exact call/return or ownership requirements.

Then run fresh f7 and candidate arms, one round per point: the same ten nano
profiles over workers `1..8,12..60` in steps of four above eight, and unchanged
will-it-scale `mmap1_threads` and `mmap1_processes` over that grid. Keep workload,
topology, frequency, instrumentation and eligibility policy identical between
arms; report whole-window and qualified peak nano measurements separately.
Retain any failed attempt. Shared-mm threads and independent-mm processes are
separate results, not one average. MM bodies and syscall semantics stay native.

Promotion requires functional passes and the no-regression gate. Complete both
comparisons even if nano has a loss, keeping the candidate unaccepted. If any
required gate fails, retain the exact candidate and evidence, state the remaining
limits and use the measured cause to propose a next iteration. One round does
not establish repeat variance or prove that an unchanged path has regressed.
