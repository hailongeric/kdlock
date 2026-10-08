# JIT execution flow

This is the direct KD spin flow and shared execution engine. The mutex-specific
entry is in [mutex implementation](design/mutex_implementation.md).
Ordinary spin pairs preemption protection and leaves IRQ/BH state unchanged.
Explicit [IRQ/BH variants](../include/README.md#explicit-irqbh-spin-interfaces)
execute natively on the calling CPU.

## Preparation and entry

1. `kd_spin_prepare()` registers the post-lock continuation and entry ABI.
   The daemon reads leased source text, translates, assembles and publishes NORMAL.
   The benchmark completes this stage before all-worker warmup and stops the daemon
   before measurement. Publication does not prove execution.
2. `KD_SPIN_DIRECT_LOCK()` pins the caller and reads the one per-CPU hot value.
   Cold callers try the inline CAS; failure passes its observed value to the native
   pending/MCS helper without repeating the first CAS. Hot callers use the pinned
   clobber entry. The compiler owns live spills around that boundary.
3. A successful hot acquisition keeps the fast owner without allocating execution
   state. On contention, a small request, exact ticket and ready translation are
   considered. Context/readiness/resource refusal uses KD native pending/MCS;
   only actual node exhaustion falls back to polling the word.
4. An eligible waiter prepares its shared continuation/frame/packet, switches to
   the reserved wait stack, release-publishes its node and polls while pinned.
   The combiner takes the same storage; it does not copy a register snapshot.

Backend and emitted-scope checks remain independent of hotness. The
[admission guide](design/admission.md) defines GS/logical-task screening,
entry guards and the unresolved dynamic-address gap.

## Batch execution and return

Simple spin roots use one resident lock-side C loop. Preparation validates image
layout, ABI, packet state and pristine-root eligibility, then writes final wrapper
metadata once. One source lease spans the batch; each request still checks readiness.
The clobber and legacy entries use the same loop, with separate completion rights.

A terminal clobber unlock can fuse CALL and completion validation. On success it
returns the IP/SP/BP triple without writing a virtual return word. On any failed
proof it constructs the original CALL exactly once and follows FULL recovery.
Complex/nested exits use the generic dispatcher. Known controls and typed services
resume only at registered continuations; ordinary CALL miss resumes natively.

Completion pops the frame before publishing DONE. The waiter loads all return
state before retiring/reclaiming the continuation and releasing the entry pin.
NATIVE_READY permits a checked suffix, not reclamation: all native executors,
including zero-lock relays, borrow the root ticket and drop it after cleanup/pop.
The final native unlock waits for those borrows and exact owner ACKs.

See [ABI](JIT_REGISTER_ABI.md), [KD ownership](design/locking.md),
[frames](design/frames.md) and [spin layout](design/spin_implementation.md).

## Heat and roles

Hotness is approximate admission data; exact owner/ticket/frame state is separate.
Spin and mutex each have per-CPU 256-bucket/256-record exact-address tables.
Collisions use slot chains, never eviction; an unknown lock at full capacity stays
native. Queries do not insert, count or read time.

| Sampling point | Current rule |
| --- | --- |
| Spin physical acquisition | Count once, including fast/pending/native paths; retries are not new acquisitions |
| Spin MCS publication | Count only real publications; at `>=1024`, compare `(entries >> 10) < spin_entry_ratio_limit` |
| Spin CPU gate | Default ratio limit 2; after comparison clear both counters and sample time; interval must be `<40000000000` TSC ticks |
| Spin lock gate | At `>=512` records, interval must be `<1250000000` TSC ticks |
| Mutex CPU gate | Own entry/contention counters; at `>=1024` contentions compare `(entries >> 10) < 256`, reset both, then sample time |
| Mutex lock gate | The 1025th record checks an interval `<2500000000` TSC ticks |

At 1024 MCS publications, the default ratio accepts 1024..2047 acquisitions and
rejects 2048. The first window participates. Limit 0 disables only the ratio;
it does not bypass CPU/lock heat, queue eligibility, context or JIT validation.
Supported nonzero values are powers of two of at least 2.

Mutex uses its separate fixed ratio limit 256 and the same CPU time bound;
the initially proposed limit 2 is not its current setting. Native successful
acquisitions count entries without touching shadow/task/translation state.

At the approximate sampling boundary, a hot native MCS head also checks a captured
queue tail and up to six linked successors before waiting/acquiring the word.
Missing tail, zero locked byte, incomplete links or fewer than six successors
turn the CPU gate cold without waiting for links. It never scans beyond that tail,
reads successor frames or changes an already-published request. The queue head
prevents observed nodes from being reused while checking them.

IRQ/reentrant observations may be lost or mixed. A busy guard skips comparison
without clearing counts or sampling time; the next MCS publication retries.
A CPU sample preserves lock windows only if the CPU was and remains hot; otherwise
it clears their hot/count state but retains exact addresses. Cached heat can persist
when subsequent acquisitions never publish MCS. No cooldown or consecutive-low
window rule exists.

`spin_delegate=0` counts acquisitions but skips heat-table/MCS observation and
executes natively. `hotlock_stats=1` reports approximate accumulated observations;
the ratio log's `scope=unfinished_batch` is only the remaining uncompleted window.
Neither is a peak-window execution count or lifetime/ownership proof.

## Unlock and validation

`KD_SPIN_DIRECT_UNLOCK()` always calls the broad-clobber unlock entry. Native byte-5
ownership releases that byte while retaining pending/tail, decrements its exact
in-flight count and unpins. Other states use the owner/ticket/native-ACK protocol.
Unlock does not infer the acquisition route from current hotness or the heat cookie.

Actual JIT positives need returned-body counts, correct data, IRQ/preempt checks
and drain. Native controls, NO_JIT, refusals and synthetic fixtures are separate
results. [Tests](../tests/README.md) and [the runner](../bench/tclock_compare/README.md)
define acceptance and commands; [operations](AGENTS.md) defines environment/recovery.
