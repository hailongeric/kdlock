# JIT execution flow

This guide follows an ordinary spin request from preparation to completion.
Mutexes and rwlock writers share the execution engine, but have different
acquisition steps; see [mutex](design/mutex_implementation.md) and
[rwlock](design/rwlock_implementation.md). The
[design glossary](DESIGN.md#terms-used-in-these-guides) explains the request terms.

An ordinary spin pair disables preemption until unlock and preserves IRQ/BH
state. Explicit [IRQ/BH variants](../include/README.md#explicit-irqbh-spin-interfaces)
run natively on the calling CPU.

## Preparation and entry

For ordinary spin:

1. **Prepare the code.** `kd_spin_prepare()` registers the continuation after the
   lock call and its ABI. The daemon keeps source modules pinned while reading and
   translating the machine code, then uploads it as NORMAL. Benchmarks finish
   preparation and stop the daemon before warming up all workers. NORMAL means
   the code is published, not that anyone has executed it.
2. **Try to acquire the lock.** `KD_SPIN_DIRECT_LOCK()` pins the caller and reads
   the per-CPU heat value. A cold caller tries the inline compare-and-swap (CAS).
   If it fails, the native pending/MCS helper uses that observed result rather
   than repeating the first CAS. A hot caller uses the pinned clobber entry;
   the compiler saves live values around that call.
3. **Decide whether to delegate.** Even a hot caller may acquire the lock directly,
   without allocating an execution frame. A contending caller needs a request,
   an exact acquisition ticket and a ready image. Failed context, readiness or
   resource checks use the native pending/MCS path. Only running out of queue
   nodes falls back to polling the lock word itself.
4. **Publish the request.** An eligible waiter prepares its shared frame and
   register packet, switches to the reserved wait stack, and makes its queue node
   visible with release ordering. It polls with preemption disabled. The combiner
   uses the same frame and packet, without copying the register state.

Heat controls whether KD considers delegation. It never bypasses backend or code
checks. [Admission](design/admission.md) explains those checks, including how GS
and the original task are represented and which dynamic addresses remain unchecked.

Rwlock preparation registers the embedded gate with ABI3. Readers run locally.
Writers first try a native count CAS without the gate; on failure they take the
native or hot gate path. Before the body starts, either the pinned native helper
or the combiner must acquire exclusive writer admission.

## Batch execution and return

A combiner can execute several simple root requests in one C loop. For each
request, preparation checks the image layout, ABI, packet state and whether the
request is eligible for this simple path. It then writes the wrapper metadata
once. One source lease covers the batch, but each request still needs a readiness
check. Legacy and clobber entries share the loop while keeping their different
completion checks.

For an ABI3 rwlock root, the combiner waits for readers and acquires the writer
byte in native code before entering JIT. A nested virtual spin request inherits
the ABI but does not acquire another rwlock count. If JIT refuses before the body
starts, KD cancels writer admission while retaining the gate. The physical native
retry must acquire admission again before resuming the body. If the body already
made progress, its native remainder keeps admission until write unlock.
`rwlock_admitted` records that obligation without enlarging the packet or wrapper
inputs.

The final clobber unlock can combine CALL handling and completion checks. When
those checks pass, the wrapper returns only IP/SP/BP and skips writing a virtual
return address. If the checks fail, it constructs the original CALL exactly once,
saves FULL state and uses the general recovery path. Nested and other complex
exits also use the general dispatcher. Known controls and approved services can
resume JIT at registered continuations; an ordinary untranslated call finishes
natively.

Completion removes the frame from the active stack before publishing DONE. The
waiter must read its return state before reusing the continuation or enabling
preemption. NATIVE_READY only grants permission to run a checked native remainder;
it does not permit the root request to be freed. Every native executor, including
a relay with no remaining held lock, retains a reference to the root ticket until
its cleanup and frame removal finish. Final native unlock waits for those
references and the required owner ACKs.

See [ABI](JIT_REGISTER_ABI.md), [KD ownership](design/locking.md),
[frames](design/frames.md) and [spin layout](design/spin_implementation.md) for the
exact state and storage rules.

## Heat and roles

A lock is called **hot** when sampled contention makes it eligible for delegation.
These measurements are approximate. They never decide who owns a lock or when a
request can be freed.

Spin and mutex each maintain a per-CPU table with 256 buckets and 256 records.
Records match the full lock address. Hash collisions form chains; they do not evict
existing records. If the table is full, an unknown lock stays native. A lookup does
not insert a record, increment a counter or read the clock.

Rwlocks use the existing spin table keyed by the embedded gate. Successful ungated
writers count an entry and retain an exact nondelegated reference; failed fast
attempts transfer to ordinary gate accounting. Fast readers do not touch heat
state, while slow readers acquire the native gate. There is no separate rwlock
heat policy or reader delegation.

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
acquisitions count entries without touching delegation/task/translation state.

When sampling, a hot native MCS queue head also saves the current tail and checks
up to six linked successors before waiting for or acquiring the word. A missing
tail, zero locked byte, incomplete link or fewer than six successors makes the
CPU cold. This check does not wait for missing links. It stops at the saved tail,
never reads successor frames and never changes a published request. The queue
head's position prevents those nodes from being reused during the check.

Interrupts or reentrant calls can lose or mix observations. If another comparison
is already running, a busy guard skips this one without clearing counters or
sampling time; the next MCS publication retries. A CPU sample keeps the lock
windows only if that CPU was hot and remains hot. Otherwise it clears their heat
and counts while retaining the recorded addresses. If later acquisitions never
publish an MCS node, cached heat may remain indefinitely. There is no cooldown
or rule requiring several low-contention windows.

`spin_delegate=0` counts acquisitions but skips heat-table/MCS observation and
executes natively. `hotlock_stats=1` reports approximate accumulated observations;
the ratio log's `scope=unfinished_batch` is only the remaining uncompleted window.
Neither is a peak-window execution count or lifetime/ownership proof.

## Unlock and validation

`KD_SPIN_DIRECT_UNLOCK()` always calls the broad-clobber unlock entry. For native
ownership marked by byte 5, it clears only that byte, keeps the pending/tail fields,
drops the exact in-flight count and unpins. Other ownership states use their
owner, ticket and native-ACK records. Unlock follows the recorded acquisition;
it does not choose a route from the current heat value or cookie.

Rwlock write unlock clears only the count's writer byte before releasing the gate
or entering spin completion. Ungated native writers instead drop their exact
reference and pin after that byte release. Completion clears frame bookkeeping;
it must not clear the count again after a successor can own it.

To report successful JIT execution, require a returned-body count, correct data,
restored IRQ/preemption state and complete drain. Report native controls, NO_JIT,
refusals and synthetic fixtures separately. For rwlocks, JIT share is the number
of returned JIT writer bodies divided by completed writes; reads are excluded.
[Tests](../tests/README.md), the
[spin/mutex runner](../bench/tclock_compare/README.md) and
[rwlock runner](../bench/rwlock_compare/README.md) define acceptance and commands;
[operations](operations/VM.md) defines environment/recovery.

## Legacy mutex image generations

In the current implementation, mutex registration precedes executable allocation.
The daemon publishes one complete, immutable generation; a frame binds its
image and keeps it through FULL continuations. Replacement never overwrites a
running mutex image, and old-generation misses cannot change the current image's
metadata. Source and ownership retirement still apply independently. Published
versions remain in the existing 64-block pool until session teardown. Spin/rwlock
image storage retains its existing in-place lifetime. See the
[compatibility comparison](history/legacy_mutex_compatibility.md).
