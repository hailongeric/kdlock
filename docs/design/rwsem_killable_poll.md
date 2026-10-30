# Bounded killable writer admission candidate

This isolated candidate starts from
`f7a84065e84474380faa37eeadfdf534abd72a68`. It is unbuilt, untested, unmeasured
and unaccepted. The ongoing f7 syscall and MM comparisons retain their frozen
source, binaries and results. No change here is a performance claim.

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
`signal_pending_state(TASK_KILLABLE, current)`, then `cpu_relax()` while the
16,384-attempt budget remains. Polling stays preemptible and unpublished: no
waiter, OSQ/delegation membership, owner-pointer access, task-state change or
queue-lock acquisition is added.

A false helper result always enters the existing
`wait_event_killable(sem->phase_wait, kd_rwsem_reserve_local(sem))` fallback.
The helper never returns `-EINTR` itself. This preserves the Native-style rule
that a successful condition wins a concurrent pending fatal signal. Nonfatal
signals do not cancel a killable acquisition. The wait macro retains its
condition check before signal failure and enqueue/recheck ordering, including
a release between the final poll and waiter publication.

Keep the physical gate, killable reader-drain timer, rollback, exact owner,
phase release and downgrade unchanged. Reader OSQ tail remains an admission
barrier; all writers still win the actual 0-to--1 phase CAS. Winning admission
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
exact predicate effects, signal ordering, queue rechecks and release ordering;
they do not prove weak-memory behavior or real kernel scheduling.

Required cases include first/final-probe success, exact exhaustion, reschedule,
fatal/nonfatal signals, condition winning a pending/racing fatal signal,
release before fallback and after enqueue, reader-tail refusal/exit, lost CAS
to another writer, gate cancellation, reader-drain cancellation, and downgrade
followed by another killable writer. Check that success is consumed once and
that no body is entered before all readers drain. Negative mutations must
actually execute and fail; compile errors, timeouts or skips are not passes.

The later VM selection is basic plus this fixture, existing
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
