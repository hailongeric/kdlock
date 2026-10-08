# Performance plan

Goal: KD reaches at least **90% of TCLock's corresponding warmed peak**, while
protecting small-thread throughput. The broader user goal is parity across all
thread counts. The latest four-way matrix still fails that broader acceptance;
[results](../bench/tclock_compare/results/HISTORY.md) records the remaining gaps.
Current implementation contracts live in [spin](design/spin_implementation.md)
and [mutex](design/mutex_implementation.md); correctness work lives in [TODO](TODO.md).

## Current evidence

The VM now boots with [nopvspin](PROJECT_GUIDE.md#native-qspinlocks-in-the-vm).
The matrix below predates that change. Rerun all three arms under the new policy
before claiming current performance; no such rerun is recorded yet.

The [2026-10-08 rerun](../bench/tclock_compare/results/20261008-threeway-spin-mutex.md)
contains 540 valid samples at committed `009e8e3`, with four lock-outside arithmetic
rounds. Spin cacheline reaches 90% at 14/15 points and parity at 13/15; mutex
cacheline reaches 90% at 14/15 and parity at 12/15. Spin hash reaches 90% at 5/15
and parity at 3/15; mutex hash reaches 90% at 10/15 and parity at 5/15.

At 36 threads spin/hash peaks are KD 2.019 versus TCLock 2.789 Mops/s despite 99.9%
KD JIT execution. Mutex/hash peaks are 2.799 versus 2.222, but whole-run medians
are 2.143 versus 2.202: KD is 2.70% lower. Mutex/hash also misses 90% at 2/3/4/5/24.
KD mutex returns only 12.56–13.02% of 36-thread hash bodies through JIT, unlike
spin's nearly complete delegation. Separate native/admission and execution costs.

At 24 threads KD spin's four minority-node workers contribute only 0.5% of cacheline
and 2% of hash operations; TCLock spin is also strongly skewed. Every worker
progressed, but throughput and a bounded batch do not establish starvation freedom.
The [earlier spin investigation](../bench/tclock_compare/results/20260928-spin36-analysis.md)
records separate execution/NUMA diagnostics; flat cycles cannot measure remote latency.

## Retained optimizations

| Area | Current implementation |
| --- | --- |
| Spin terminal unlock | Fused completion proof; failure constructs the original CALL once and enters FULL |
| Wrapper inputs | Omit proven-unused GS/task imports; retain slots and the two-word ABI |
| Spin NUMA scan | Check exhausted budget before dependent successor reads; preserve deferred remote handoff |
| Spin layout | Identity/state and IP/SP/BP share one hot line; minimal frame/packet prefetch covers three lines |
| Mutex native entry | Caller-side owner CAS and exact outer cookie; no shadow/task/translation work on success |
| Mutex shadow reads | Exact published-key lookup without the insertion lock |
| Mutex observations | Separate approximate contention data and per-CPU observation/lifecycle totals |
| Mutex simple execution | Dedicated terminal waiter, batch transport and lazy cold routing fields; generic FULL recovery retained |

Mutex still uses serialized shadow insertion and dynamically allocated exact task
records with one registry writer lock. Its accepted queue is FIFO; bounded NUMA
grouping, stable-record/sharded-lock and packed-node candidates were reverted after
measured losses. Do not document those candidates as implemented.

## Next experiments

1. Separate native/low-delegation contention cost from JIT execution cost. Compare
   16 workers within one node versus 8+8, and 20 versus 10+10, retaining standard36.
   Check CPU/node shares and every worker's progress, especially the 24-thread
   minority node. Positive counts do not prove starvation freedom.
2. Collect separate supported PMU diagnostics for cycles, instructions and useful
   cache events. Verify availability and sample validity. Attribute queued-spin
   wait to a specific call path before claiming it is the task writer lock.
3. Revisit task/shadow coordination only with new evidence. Any bounded retained
   cache needs exact key publication, inactive zero-ref state, capacity/collision
   fallback, task refs until unload and acquisition refs through final owner ACK.
   Removing a lock alone did not produce an accepted end-to-end gain.
4. Optimize measured accesses and helper costs. Keep native-peer exclusion,
   blocking executor ownership, final ACK and source retirement. Rejected broad
   prefetch/register-residency and packed-mutex/NUMA experiments need new evidence
   before repetition. Generated hash has no per-body hardware fences to remove.

Pinned KD waiters and the two-word input ABI remain fixed scope. Protocol changes
may use useful TCLock/Linux logic, but must preserve the original Linux mutex owner
and distinct backend identity for generic recovery.

## Measurement and stopping rules

Use [the runner](../bench/tclock_compare/README.md) with fixed 2.5 GHz, NUMA on,
UBSAN-off KD benchmark provider and 48000 warmup operations per worker. Measure
three rounds at 1,2,3,4,5,6,7,8,12,16,20,24,28,32,36 threads for two seconds; select
the highest valid 300 ms window after settling. Retain whole throughput and
min/median/max/spread, full samples, failed candidates and frozen identity.

Screen at 16/36 before a broader run. Recheck an apparent regression once; reject
repeatable median losses above 3% at protected points. Require returned-body JIT
for contended KD positives and actual delegation evidence for TCLock mutex.
TCLock spin execution counts remain unmeasured; do not invent them.

Retain NUMA-on, exact 1,024 KD body cap, separate spin scan bound and current prefetch
defaults. Performance gains do not override correctness or retire already-published
requests. Commit independently validated changes with matching evidence. Cleanup
alone is neither a performance rerun nor a throughput improvement.
