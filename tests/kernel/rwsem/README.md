# Sleeping rwsem public API and prepared-writer admission checks

The reader/writer semaphore (rwsem) waiting implementation in `c21345b` remains
the foundation for exact phases and sleeping waits. Ordinary read contention
now queues optimistic admission attempts, and new writer phases yield while
those readers remain queued. Admission means permission for a reader or writer
to enter. A prepared ordinary writer may delegate its work
to another lock holder. JIT means just-in-time compiled code for that delegated
execution; a returned body must reach its matching unlock and finish the return
protocol. See the [terminology guide](../../../docs/TERMINOLOGY.md) for other
implementation and result labels.

Run only in the verified recovery guest, following
[VM operations](../../../docs/operations/VM.md). This probe exercises the
[current KD rwsem](../../../docs/design/rwsem_implementation.md), including the
ordinary prepared wrapper's local return path. It registers a source entry but
does not start a translator or register an image. These scheduling assertions do not count as returned JIT
bodies; the mixed c08 benchmark checks reader consistency alongside actual
entry and matching-unlock completion witnesses.

```sh
timeout 600s python3 tests/kernel/rwsem/run.py \
  --output /root/kdlock-evidence/10.176.26.71/tests/rwsem-admission-<new-run>
```

Set the verified snapshot environment and pinned Python environment first. The
runner freezes source (including `.inc` files), verifies kernel identity, builds
provider/probe, saves commands and kernel logs, checks results, then retires the
source session before unloading the probe and provider normally. The source
entry holds the probe module until that retirement. A timeout or kernel fault retains modules
for diagnosis; it does not prove worker or source drain.

The probe checks:

- Static initialization, read/write trylocks, writer-to-reader downgrade and
  quiescent inspection.
- Unified ordinary calls, ignored non-lockdep nested annotations, named init,
  rejection of preparation on a live object, prepared flag retention, default
  ordinary and prepared-object callable downgrade, local cleanup guards,
  coordinated cross-task non-owner read release, and exact routed public unlock.
  A separate translation unit uses Native aliases, callable query types,
  guard/scoped/conditional guard helpers and `ACQUIRE_ERR` on KD objects.
- Two readers that sleep concurrently while retaining their read counts; a
  writer that sleeps waiting for both; a late reader blocked behind that writer;
  and a writer that sleeps inside its body. All four workers share CPU 0, so
  correctness depends on blocked participants allowing their holders to resume.
- The same four-worker scenario using an outer writer: the writer reserves its
  phase but sleeps before entering the pinned mutex protocol. Exact queue tail
  and waiter counts stay zero while the two sleeping readers still hold their
  counts; both readers can resume and release on CPU 0. The late reader stays
  blocked until the outer writer returns and releases its reservation.
- An ordinary writer with a waiting outer caller, then writer-to-reader
  downgrade. The caller remains unpublished both before the downgrade and while
  the downgraded reader remains live. It enters only after that reader releases.
- Ten cancellation cases: interruptible and killable read/write acquisition
  waiting for an ordinary writer phase; ordinary write acquisition waiting for
  admitted readers after acquiring its phase and gate; and ordinary read/write
  acquisition waiting for an outer writer reservation. Killable
  waits first receive a nonfatal signal and must remain blocked, then cancel on
  `SIGKILL`. A cancelled drain waiter must reopen reader admission immediately.
  Unprepared writers behind another writer inspect the physical gate wait list;
  prepared writers and readers inspect `phase_wait`. Writers that already own
  their reservation and wait for readers inspect `reader_drain`. Unrelated
  queues remain empty at each controlled cancellation point.
- Three additional unprepared gate-signal cases use a runnable writer holder,
  a contender and the controller on three distinct online CPUs. The controller
  observes a real gate OSQ tail before sending a signal. Interruptible nonfatal
  and killable fatal cancellation must retire the OSQ and wait list while the
  holder still owns the lock. A nonfatal killable signal must instead leave the
  contender asleep on the gate wait list until a subsequent fatal signal. A
  missing queue observation fails this check. A rescheduling request may race
  the signal, so these live observations do not isolate which stop predicate
  retired the queue; the deterministic OSQ fixture checks that distinction.
  The holder has a two-second busy interval after acquisition. Release precedes
  every join; a failed or stuck join retains the module and task state.
- Exact zero error result, expected sleeping transitions, all worker joins, zero
  readers and writer reservations, no phase or drain waiters and an idle
  physical gate. Quiescent inspection also requires an empty read-admission OSQ.

Ordinary read acquisition first tries its exact reader count/phase protocol up
to eight times, stopping early for rescheduling. After failure, it uses an
abortable OSQ backed by an existing preallocated mutex
CPU/slot reservation. Only the queue head polls shared admission, for at most
16,384 condition checks and with an earlier exit when rescheduling is needed.
The OSQ membership and slot retire before preemption is enabled, a reader body
executes or the caller enters its sleeping fallback. Slot exhaustion and OSQ
abort also fall back to the existing waitqueue path. The queue does not publish
a delegation request or acquire the writer gate.

An ordinary writer or new outer-writer cohort defers when admission is zero and
the reader OSQ is nonempty. Existing positive outer cohorts still accept exact
reservations. A failed reservation CAS rechecks the queue if the phase becomes
zero. Queue presence is only a waiting-policy hint; the count/phase barriers,
reader drain, mutex ownership and origin ACK/release remain authoritative.

After OSQ retirement, slot release and preemption enable, an empty tail triggers
a full barrier before the `phase_wait` check and wake. This pairs the release-only
tail update with sleeping writers' enrolment/recheck, including unsuccessful
reader acquisition paths. New writer phases can therefore resume when the queue
empties without waiting for another phase change. This preference does not
guarantee starvation freedom or bounded waiting.

Writer polling remains before publication with preemption enabled. The sleeping
and same-CPU cases exercise scheduling fallback. Interruptible and killable
acquisitions retain their original cancellation paths, and atomic read trylock
does not enter OSQ. Every reader acquires and executes on its own task; only
eligible writes may delegate.

The guest-only [read-admission unit fixture](../../unit/mutex/test_rwsem_read_admission.py)
extracts the production slowpath and checks fast success, bounded head polling,
slot/OSQ abort, release before reader return or sleeping fallback, ordered
empty-queue wakeups, and exact writer reservation decisions across CAS races. Its
deterministic substitutes do not prove concurrent unlink or scheduling progress;
the existing mutex OSQ fixtures and this live probe cover those separately.

Expected result: `api_checks=17`, `cancellation_checks=10`, `readers_slept=2`,
`writer_slept=1`, `late_reader_slept=1`, `outer_readers_slept=2`,
`outer_writer_slept=1`, `downgrade_checks=1`, `publication_checks=3`,
`colocated=1`, `errors=0`, `idle=1`. Prepared ordinary macro acquisition has no cancellation or
downgrade contract; these cases exercise the supported ordinary operations mixed
with outer callers. Returned JIT bodies are explicitly zero. See the
[optimization validation receipt](../../../bench/results/10.176.26.71/tests/rwsem-optimization-20261018/README.md)
for recorded outcomes and source identities, and the separate
[benchmark report](../../../bench/results/10.176.26.71/bench/rwsem-optimization-20261018/README.md)
for performance measurements. The
[initial writer-delegation receipt](../../../bench/results/10.176.26.71/tests/rwsem-delegation-20261018/README.md)
uses the same twelve-field result layout with the earlier shared-queue provider.
The [previous local-only receipt](../../../bench/results/10.176.26.71/tests/feature-reintegration-20261018/README.md)
records the earlier eight-field probe and separate workload checks. The historical
[2026-10-15 receipt](../../../bench/results/10.176.26.71/tests/rwsem-snapshots-20261015/README.md)
belongs to the archived owned-mutex implementation and is not current evidence.

The guest-only [public facade fixture](../../unit/mutex/test_rwsem_api.py) compiles
the production headers and phase-retirement helpers. It checks single evaluation,
local/prepared routing, preparation failures, exact unlock-before-phase order,
downgrade and the emitted ABI2 terminal boundary. Deterministic mutex/ACK stubs
do not establish live scheduling or delegation. The Native header identity in
[native-source.json](native-source.json) records the source used to compare API
coverage. RT/debug/lockdep configurations are explicitly refused; fairness and
arbitrary kernel replacement remain unvalidated.

The additional `gate_signal` result preserves the original twelve-field ioctl
record and uses a separate eight-field record: `cases=3`, `osq_observed=3`,
`scoped_retired=3`, `nonfatal_wait=1`, `fatal_cancel=2`,
`interruptible_cancel=1`, `errors=0`, `idle=1`. These are functional
observations, not throughput or delegation measurements. The focused
[writer queue fixture](../../unit/mutex/test_rwsem_writer_queue.py) extracts the
production phase/gate/poll/drain functions and checks exact local reservation
and rollback effects with deterministic primitives.

The first writer-queue candidate `7fa989c1` passed its focused unit checks and
the original live API record (`api_checks=17`, `cancellation_checks=10`), but its
new gate-signal record failed with `errors=2`, `cases=1`, `osq_observed=1`,
`scoped_retired=0`, `idle=1`. This failed attempt remains evidence. The first
completion wait consumed the waiter's single `complete()` notification. The
subsequent `completion_done()` therefore suppressed the retirement counter, and
the join-path wait timed out; the final three-case check then also failed. The
actual cancellation, holder ownership, queue-retirement and worker joins passed
in that attempted case. The fixture now uses `complete_all()` for this one
completion, which deliberately has multiple observers. This is a diagnostic
notification correction; no lock implementation changes accompany it. The
corrected live result requires a new VM run and does not replace the failed one.
