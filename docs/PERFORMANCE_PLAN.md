# Performance plan

Goal: KD matches the **faster of TCLock and Linux Native** across all requested
thread counts while protecting small-thread throughput. Reaching 90% of TCLock's
warmed peak is an intermediate milestone. Whole-run medians must improve too;
peak parity cannot conceal sustained losses. The goal remains unmet.
Implementation contracts live in [spin](design/spin_implementation.md) and
[mutex](design/mutex_implementation.md); correctness work lives in [TODO](TODO.md).

## Current evidence

The [protocol simplification trials](../bench/tclock_compare/results/20261008-protocol-simplification/README.md)
promote no runtime changes. Dead packet-read removal and paired traversal budgets
brought no consistent benefit. The combined terminal-proof/lazy-backing candidate
repeatedly lost mutex/hash-36 whole-run throughput against the closing baseline.
Memory-only backing then repeated a mutex/cacheline-16 median peak loss above 3%
against the opening baseline; the corresponding closing-baseline peak losses
stayed below 3%.
Both candidates were reverted. Their complete matrices and rechecks remain
separate evidence. A fresh 540-session matrix of the restored runtime covers all
15 thread counts, both payloads and all three backends for spin and mutex.

The [hash diagnosis](../bench/tclock_compare/results/20261008-hash-diagnosis.md)
identifies generated traversal/request overhead for spin and competing native/KD
wait paths for mutex. A spin gap remains within one NUMA node and with nearly all
returned bodies executed by JIT. Aggregate L1 misses do not justify broad prefetch;
cycle samples do not establish remote-memory latency. Hash still writes shared
links and values, so delegation can amortize lock handoff and retain useful data.

The [earlier mutex trials](../bench/tclock_compare/results/20261008-mutex-priority-trials.md)
show why more delegation is not itself an optimization: retained task records
increased JIT share and batch length but lost throughput. Fault-guard, ledger and
gate-store trials did not establish a repeatable overall gain. Preserve their
evidence and the opening/closing baseline variation before revisiting these ideas.

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
records with one registry writer lock. Its accepted queue is FIFO. Bounded NUMA
grouping, stable-record/sharded-lock and packed-node candidates were reverted after
measured losses; they are not current implementation features.

## Next experiments

1. Measure mutex native/delegated routes, batch exits and stage costs before
   changing admission. Optimize native caller and delegated service independently.
   Hoist only proved immutable batch facts; retain per-request publication,
   identity, ownership and completion checks.
2. Prototype an explicit outlined body/context API, as proposed in
   [protocol simplification](design/protocol_simplification.md). Using today's
   translator still pays packet, virtual-stack and traversal-budget costs.
   Removing these needs a separate JIT tier for bounded, nonblocking,
   task-independent leaf bodies with compiler-managed registers and stack.
   Establish matched callers and exact completion before measuring it.
3. Revisit task storage, layout and locality only with new evidence. Cached records
   need exact publication, inactive zero-reference state, capacity/collision
   fallback and acquisition references through final owner ACK. Do not repeat
   broad prefetch, cross-block register residency or NUMA grouping merely because
   they remove instructions or increase JIT coverage. Keep local 16 versus split
   8+8 controls; add local 20 versus split 10+10 for locality changes. Measure
   deferred-waiter residence and node shares alongside throughput.

Pinned KD waiters, mandatory mutex JIT and the two-word input ABI remain fixed
scope. Preserve original Linux mutex ownership, backend identity for recovery,
source leases, final ACK and frame retirement. Refuse unsupported code before
execution; never replay completed side effects. Generated hash has no per-body
hardware fences to remove.

## Measurement and stopping rules

Use [the runner](../bench/tclock_compare/README.md) with fixed 2.5 GHz, NUMA on,
UBSAN-off KD provider and 48,000 warmup operations per worker. Measure three
rounds at 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 28, 32 and 36 threads for two
seconds; select the highest valid 300 ms window after settling. Retain whole-run
throughput, min/median/max/spread, failed candidates, all samples and frozen identity.

Screen at 16/36 before broader runs, adding 2 threads for caller changes and 24
for fairness. Recheck an apparent regression once; reject repeatable median losses
above 3% at protected points. Require exact business results, every worker's
progress, node shares and complete drain. Returned-body JIT is required for
contended KD positives; allowed native-route controls are not JIT passes. TCLock
mutex must demonstrate delegation; TCLock spin execution counts remain unmeasured.

Retain NUMA-on, KD's exact 1,024-body cap, separate spin scan bound and current
prefetch defaults. Positive observed progress is not a starvation guarantee.
Commit independently validated changes with matching evidence. Cleanup alone is
neither a performance rerun nor a throughput improvement.
