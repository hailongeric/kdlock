# Bounded killable writer admission candidate

This isolated candidate starts from
`f7a84065e84474380faa37eeadfdf534abd72a68`. The prepared implementation at
`9ce007498d7d4ed48f85b89353726d28656a3933` is unbuilt, untested, unmeasured
and unaccepted. The completed f7 comparisons retain their frozen source,
binaries and losses in `2a0bbfad348950a519b8cf017dc0a6f3583d14ee`.
No change here is a performance claim or a promotion to `master`.

The October 31 implementation follows the user's admission-only request.
Retain the 16,384-attempt budget, but stop optimistic polling for any pending
signal, including a nonfatal one. The prepared implementation's fatal-only
polling stop does not satisfy that new constraint and must be corrected before
testing. This section records the correction before code.

The original-task mmap/munmap paths acquire the killable writer interface.
Unlike ordinary uninterruptible writers, `kd_down_write_killable()` currently
goes directly to `wait_event_killable` for phase admission. That macro tries its
condition immediately; not every acquisition sleeps. Native Linux 7 can attempt
owner-aware optimistic rwsem spinning before publication. A short unpublished
KD admission poll is a bounded scheduling-cost hypothesis, not an implementation
of Native's owner-aware queue algorithm.

Add one private Boolean helper used only by killable writer admission. Each
iteration first calls the unchanged `kd_rwsem_reserve_local(sem)` predicate.
Success returns immediately and must not evaluate that side-effecting predicate
again. Only after failure, check `need_resched()` and
`signal_pending(current)`, then `cpu_relax()` while the
16,384-attempt budget remains. Polling stays preemptible and unpublished: no
waiter, OSQ/delegation membership, owner-pointer access, task-state change or
queue-lock acquisition is added.

A false helper result always enters the existing
`wait_event_killable(sem->phase_wait, kd_rwsem_reserve_local(sem))` fallback.
The helper never returns `-EINTR` itself. This preserves the Native-style rule
that a successful condition wins a concurrent pending signal. Nonfatal
signals stop optimistic polling but do not cancel a killable acquisition;
the unchanged wait macro still checks the fatal-only killable condition.
The wait macro retains its
condition check before signal failure and enqueue/recheck ordering, including
a release between the final poll and waiter publication.

Keep the physical gate, killable reader-drain timer, rollback, exact owner,
phase release and downgrade unchanged. Reader OSQ tail remains the existing
admission hint; all writers still win the actual 0-to--1 phase CAS. Winning admission
does not authorize entry while readers remain. Gate or reader-drain cancellation
releases the exact phase once, after any acquired physical gate is unlocked.
Do not add polling to reader drainage, interruptible acquisition, ordinary or
prepared writers. Fairness, batching, wake policy and oversubscription remain
outside this candidate. More retries can still consume CPU or change barging
opportunities; those costs must be measured rather than assumed absent.

The Linux 7 generator reuses the local source before removing delegated phase
helpers. It must retain this helper automatically without changing the generator
or native MM bodies. The scope kernel currently uses HZ=1000: the unchanged
one-jiffy reader-drain recheck parameter is nominally 1 ms, not a mandatory sleep
or an elapsed-time bound.

## Focused validation contract

Prepare a guest-only fixture extracting the actual reservation, new helper,
killable acquisition, reader drain, release and downgrade functions. Explicitly
label deterministic atomic/wait/scheduler doubles: they can check control flow,
exact predicate effects, condition-before-signal ordering, fallback rechecks and
phase release ordering. Their synthetic wait-boundary counters include attempts
that Native `prepare_to_wait_event` may refuse without adding membership. They
do not prove exact queue membership, weak-memory behavior or real scheduling.

Required cases include first/final-probe success, exact exhaustion, reschedule,
fatal/nonfatal signals stopping the poll, condition winning a pending/racing signal,
release before fallback and after modeled wait preparation, reader-tail refusal/exit, lost CAS
to another writer, gate cancellation, reader-drain cancellation, and downgrade
followed by another killable writer. Check that success is consumed once and
that no body is entered before all readers drain. Negative mutations must
actually execute and fail; compile errors, timeouts or skips are not passes.
Include a mutation restoring the rejected fatal-only polling stop, and a
nonfatal case that reaches the wait fallback and subsequently acquires without
cancellation. Retain the exact exhaustion and cancellation/rollback checks.

The later VM selection is basic plus
`tests/unit/mutex/test_rwsem_killable_poll.py`, existing
`tests/unit/mutex/test_rwsem_api.py`, `test_rwsem_read_admission.py` and
`tests/unit/infrastructure/test_mmap_rwsem_generation.py`. Inspect generated
local source and enabled-object compilation separately. Existing live rwsem
cancellation tests do not prove a signal during this new unpublished poll;
that boundary needs a focused actual-helper case before promotion.

After correctness, compare compiled ordinary/prepared paths with the exact
baseline, allowing addresses/relocations explicitly. A matching instruction
sequence is not a throughput result. Any performance experiment needs its own
source/kernel identity and one-round results after preserving the original f7
MM/mmap1 comparison. No current result may be relabeled as testing this change.

## October 31 execution plan

1. Commit this design update, then change only the private admission helper's
   stop condition and its directly affected fixtures. Keep physical gate,
   reader-drain, downgrade and rollback code byte-identical to f7.
2. Synchronize the isolated candidate only after the VM is confirmed idle.
   Run the two basic unit checks, the four focused drivers above, the existing
   live rwsem cancellation/rollback probe and the four basic lock checks in the
   VM. Report initial implementation and actual correctness outcomes before
   proceeding to performance work. Preserve failed attempts separately.
3. Run one round per point for fresh f7 and candidate nano arms under one
   declared kernel/topology/host policy. Preserve the earlier f7 nano data as
   a separate historical cohort rather than transferring its qualification.
4. Regenerate the namespaced local MM source and build a separate kernel
   identity for the candidate. Keep native MM bodies unchanged. Run one round
   per point for f7 and candidate `mmap1_threads` and `mmap1_processes`, reusing
   the same unchanged upstream binaries and recording both kernel identities.
5. Report every negative point, exact commits, budget and correctness limits.
   Both functional checks and the no-regression criterion must pass before
   any promotion; otherwise retain the isolated candidate and its results.
