# Performance plan

Goal: KD matches the **faster of TCLock and Linux Native** across the requested
thread counts, while protecting small-thread throughput. Reaching 90% of TCLock's
warmed peak remains an intermediate milestone. Track whole-run medians as well:
peak parity must not conceal sustained losses. Current evidence fails acceptance;
[results](../bench/tclock_compare/results/HISTORY.md) records the remaining gaps.
Current implementation contracts live in [spin](design/spin_implementation.md)
and [mutex](design/mutex_implementation.md); correctness work lives in [TODO](TODO.md).

## Current evidence

The [current hash diagnosis](../bench/tclock_compare/results/20261008-hash-diagnosis.md)
has 90 unprofiled samples under `nopvspin`: 2/16/24/36 threads plus a split-node
16-worker control,
all three arms, three rounds. It uses committed `11c8e72`, four lock-outside
arithmetic rounds and the default UBSAN-off provider. The earlier
[540-sample matrix](../bench/tclock_compare/results/20261008-threeway-spin-mutex.md)
predates this boot policy; the full 15-point matrix has not been rerun under it.

Spin/hash at 36 threads peaks at KD 2.017 versus TCLock 2.765 Mops/s, only 72.95%,
despite 99.9% JIT execution. Mutex/hash at 36 reaches 92.21% of the strongest peak
but only 64.27% of Native's whole-run median. At 24, KD mutex reaches 39.69% of Native's
whole median. Its JIT coverage varies; increasing delegation is not itself a gain.

Separate profiles and PMU runs identify generated traversal/request overhead
for spin and competing native/KD wait paths for mutex. Total L1-load misses per
operation are similar to TCLock; more prefetch is not supported by that count.
Fixed 16-worker placement controls show large NUMA effects while a local spin gap remains.
All workers progressed, but minority-node shares remain uneven. Flat cycles do
not identify remote latency or the individual lock behind a kernel spin wait.

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

1. Test local translator proofs independently: omit dead incoming packet reads
   before complete MOV overwrites, then redundant terminal metadata comparisons.
   Preserve partial writes, alternate entries and exact-once FULL construction.
   A later CFG-budget contraction needs finite-work, flags and exit-state proofs.
2. Optimize native caller cost separately from delegated service. For mutex,
   first measure route mix, batch exit reasons and stage-specific wait durations;
   shorten service before promoting more requests. Cache only immutable batch
   facts; retain per-request publication, identity, ownership and completion checks.
3. Revisit task/shadow coordination only with new evidence. Any bounded retained
   cache needs exact key publication, inactive zero-ref state, capacity/collision
   fallback, task refs until unload and acquisition refs through final owner ACK.
   Removing a lock alone did not produce an accepted end-to-end gain.
4. Optimize measured accesses and NUMA service. Keep native-peer exclusion,
   blocking executor ownership, final ACK and source retirement. Rejected broad
   prefetch/register-residency and packed-mutex/NUMA experiments need new evidence
   before repetition. The disabled-injection read guard also previously regressed.
   Generated hash has no per-body hardware fences to remove. Retain local 16 versus
   split 8+8 and add local 20 versus split 10+10 when a locality change warrants it.

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
