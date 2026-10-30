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


## October 31 recorded implementation and validation

The preceding proposal is retained as the historical preparation record. The
implemented candidate is `22d62d5c13cad3c61c97dd47524da908769f1a52`, isolated from
`master`. Its only production extension relative to
`f7a84065e84474380faa37eeadfdf534abd72a68` is the bounded phase-admission poll in
`kd_down_write_killable()`, with the required pending-signal include. The stop
condition is now `need_resched() || signal_pending(current)`. Every probe first
tries the unchanged reservation predicate; success is consumed once before
checking scheduling or signals. A false result enters the unchanged killable
wait, so nonfatal signals stop spinning without canceling acquisition. Fatal
cancellation, physical-gate acquisition, reader drainage, rollback, downgrade,
phase release and exact ownership retain their existing paths.

The 16,384 limit counts reservation probes, not unconditional atomic exchanges:
`kd_rwsem_reserve_local()` first reads phase admission and the existing reader
OSQ-tail hint, and attempts the phase CAS only when both permit it. This poll
remains preemptible and unpublished. It is not Native's owner-aware optimistic
spinning queue. All eligible entering killable writers can poll; no proof of
owner progress, fairness improvement or reduced parking follows from the new
loop. Ordinary and prepared writers, readers and delegated bodies do not gain
this helper.

The [isolated validation report](../../bench/results/10.176.26.71/bench/rwsem-killable-poll-20261031/README.md)
retains the initial functional receipts separately from the fresh timing
cohort. These are recorded VM results, not host-side test executions:

| Evidence | Recorded result | Receipt SHA256 |
| --- | --- | --- |
| Basic plus directly affected unit selection | Six checks passed; the extracted-helper fixture ran 25 scenarios and rejected 10 executable mutations | `11980b5b69ce1decc445c79cafa65e1345bbb9379d658818d893b646e4f9accc` |
| Existing live rwsem API/cancellation probe | 17 API checks and 10 cancellation checks, zero errors, drained | `eb465041f72403b3a5dd4f6585254ab85b04a5b3365a96a1851beb644e20ce8b` |
| Initial four-family basic probe | Spin, mutex, rwlock and rwsem passed, with final idle recorded | `99c68b5b072f1b13f867bfe84d26b8a0b7710c63623c485a430a264335b273a3` |
| Source-extracted actual-kernel signal probe | Four cases passed, zero errors or inconclusive cases, drained | `f78d8bac48ca6f37118dccabf4ee46949ee72c3a5d22ce78f2499af854d6fb1b` |

The last probe, at diagnostic commit
`43dd256e7e0eba7639d4db87c0eaa450f6d86d41`, uses actual kernel tasks, signals and
atomic operations with the extracted helper. It proves the bounded helper's
observed signal/condition order in those cases. It does not instrument the
uninstrumented provider binary, prove arbitrary scheduler interleavings or
replace queued cancellation coverage.

The separate kernel recipe is
`f4ae82cfdf053c679c5d09ee8e503a7919764c9b`, based on
`8446f4ecb08816380a4c233197a8ce5e4d333aac`. The recorded preparation comparison
found only `kernel/locking/kd_mmap/kd_mmap_rwsem.c` changed in the generated
kernel source; the configuration difference is `CONFIG_VERSION_SIGNATURE`.
Native MM bodies, source generators and original headers are retained. MM
critical sections execute on their original task; this change does not add MM
delegation, generic Native CALL interval reentry or queued combiner/waiter role
exchange.

The fresh nano comparison completed 420 points: 210 matching KD pairs across
ten workload profiles and 21 worker counts, one round per point. The strict
host checks passed and zero points were unscored. The candidate lost 120 whole
rates and 120 peak rates; 123 pairs lost at least one metric. The no-regression
gate therefore failed, and the candidate remains unaccepted. Identical emitted
JIT bytes at the paired points establish byte identity, not a causal explanation
or grounds to omit negative results.

The original candidate mapping correctness attempt remains failed: its
16-worker cycle completed 80,000 operations with no worker errors, but did not
capture the required strict sleeping/stack bracket. This does not prove an
absence of parking. A separately identified prospective functional mapping run
completed all six cases with its ordinary writer observation still
`inconclusive`; it does not relabel the earlier strict failure.

A separate same-mm held-writer diagnostic at
`3b34414a259d6061a4b566ac33579f9547df080e` subsequently passed actual `mmap` and
`munmap` syscall cases and rejected nine proof mutations per case. Its receipt
is `1f38b8da4af61e36278fb0a5db701f2c92565331699f38437a77b81c80cc1cda`;
normal unload, drain and final idle were recorded. It uses the unchanged stack
classifier, an exact held writer on the target mm and a separate-mm observer.
This proves those deliberately blocked syscall cases, not a sleeping witness
in the original free-running case. Its post-acquisition release deadline does
not bound native lock acquisition or joining after a kernel malfunction.

Both mmap1 arms are now archived and fetched. The
[completed comparison](../../bench/results/10.176.26.71/bench/rwsem-killable-poll-20261031/mm-comparison/README.md)
validated all 84 raw points and 42 matched pairs, one round per point. Its score
is completed mmap/munmap pairs per nominal second: the sum of the two
post-marker integer samples divided by two. Threads gained at 16 worker counts
and lost at five; processes gained at two and lost at 19. All 24 negative pairs
remain in the report. Selected changes relative to the fresh f7 arm are:

| Workers | mmap1_threads | mmap1_processes |
| ---: | ---: | ---: |
| 20 | +135.394558% | -0.706155% |
| 32 | +68.495828% | -1.634649% |
| 60 | +88.465320% | -10.997268% |

The strict host comparisons passed, but the prospective `mmap-functional-v1`
policy leaves `performance_qualified=false` and `strict_qualified=false`.
Validation receipt
`c9577f24ee5a2655ba9c51e7e3354e6eee25f8c9d4e78901b5ab11ffa6a0241f`
records `performance_accepted=false`. The supplemental functional run and
held-writer proof do not relabel the original strict mapping failure. The
subsequent ordinary writer observation remains inconclusive. These are fresh KD-versus-KD
comparisons, not a fresh Linux Native parity result. Earlier Native rates are
not pooled into them. The thread gains do not establish reduced parking as
their cause, and they do not reverse the failed nano gate. The candidate remains
isolated and unaccepted.

Restoration completed separately after evidence preservation. The source view
was unbound and the original ordinary kernel `7.0.0-38-kdlock1` was verified on
new boot `fa97b9f8-fefc-49b9-abc1-636861e64fc0`; postboot receipt
`ec53bffef6230be06cafb6351dbb828767750c4516e3d1902722a7cc0596b536`
records `NORMAL_BOOT_VERIFIED`. Pool receipt
`6bbf13bbb1d3ff5ec11a0cc3da96cae27f2ace1e9055d95bd98cb52af4bbd421`
records restored minimum 0, maximum 64 and `aio-max-batch=0`. Its original QOM
object-absence and task-map restoration flags remain false. Those limits and
the request transport whose result fetch did not complete remain preserved.
Settings restoration is not proof of exact original host-state restoration or
performance acceptance.
