# Sleeping rwsem and outer-writer admission checks

The reader/writer semaphore (rwsem) waiting implementation in `c21345b` remains
the foundation for exact phases and sleeping waits. Ordinary read contention
now queues optimistic admission attempts. Admission means permission for a reader or writer to
enter. An outer writer uses the explicit interface that may delegate its work
to another lock holder. JIT means just-in-time compiled code for that delegated
execution; a returned body must reach its matching unlock and finish the return
protocol. See the [terminology guide](../../../docs/TERMINOLOGY.md) for other
implementation and result labels.

Run only in the verified recovery guest, following
[VM operations](../../../docs/operations/VM.md). This probe exercises the
[current KD rwsem](../../../docs/design/rwsem_implementation.md), including the
outer-writer wrapper's local return path. It does not start a translator or
register an image. These scheduling assertions do not count as returned JIT
bodies; the mixed c08 benchmark checks reader consistency alongside actual
entry and matching-unlock completion witnesses.

```sh
timeout 600s python3 tests/kernel/rwsem/run.py \
  --output /root/kdlock-evidence/10.176.26.71/tests/rwsem-admission-<new-run>
```

Set the verified snapshot environment and pinned Python environment first. The
runner freezes source (including `.inc` files), verifies kernel identity, builds
provider/probe, saves commands and kernel logs, checks results, then retires the
source session and unloads normally. A timeout or kernel fault retains modules
for diagnosis; it does not prove worker or source drain.

The probe checks:

- Static initialization, read/write trylocks, writer-to-reader downgrade and
  quiescent inspection.
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
  Phase-admission cases inspect `phase_wait`; writers that already own their
  reservation and wait for readers inspect `reader_drain`. The other queue must
  remain empty at each controlled cancellation point.
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

Writer polling remains before publication with preemption enabled. The sleeping
and same-CPU cases exercise scheduling fallback. Interruptible and killable
acquisitions retain their original cancellation paths, and atomic read trylock
does not enter OSQ. Every reader acquires and executes on its own task; only
eligible writes may delegate.

The guest-only [read-admission unit fixture](../../unit/mutex/test_rwsem_read_admission.py)
extracts the production slowpath and checks fast success, bounded head polling,
slot/OSQ abort, and release before reader return or sleeping fallback. Its
deterministic substitutes do not prove concurrent unlink or scheduling progress;
the existing mutex OSQ fixtures and this live probe cover those separately.

Expected result: `api_checks=8`, `cancellation_checks=10`, `readers_slept=2`,
`writer_slept=1`, `late_reader_slept=1`, `outer_readers_slept=2`,
`outer_writer_slept=1`, `downgrade_checks=1`, `publication_checks=3`,
`colocated=1`, `errors=0`, `idle=1`. Outer acquisition has no cancellation or
downgrade API; these cases exercise the supported ordinary operations mixed
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
