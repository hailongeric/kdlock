# JIT execution flow

This guide follows ordinary requests. Family-specific acquisition belongs in
[spin](design/spin_implementation.md), [mutex](design/mutex_implementation.md),
[rwlock](design/rwlock_implementation.md) and [rwsem](design/rwsem_implementation.md).
[Translation policy](design/admission.md) defines trusted source; the
[register ABI](JIT_REGISTER_ABI.md) defines machine-state capture and exits.

## Preparation and entry

1. Register the continuation and matching backend/ABI after its source is live.
   Unified direct mutex calls may register their internal numeric continuation.
2. Decode leased text and publish a complete image. Kernel/module source is
   trusted; semantic context, loop/value and entry-input proofs are not run.
   Ordinary string callees use generated CALL/RET without named helper routes.
3. Attempt the family-specific physical acquisition. A hot caller may still
   acquire locally without a frame. Delegation also requires a ready image,
   correct runtime context and available request/ticket resources.
4. A published waiter release-orders its shared frame/packet and queue membership.
   It polls pinned on its reserved stack. The executor uses that existing packet;
   it does not copy a second request to simplify lifetime accounting.

Ordinary spin/rwlock pairs protect preemption and IRQ/BH state. Explicit spin
IRQ/BH variants are local. Published mutex waiters are pinned even though physical
owners and supported service paths may sleep. Heat never authorizes ownership.

## Batch execution and return

A combiner holds physical exclusion while selecting requests. Each request keeps
its exact ticket/acquisition, frame and image binding. Batch preparation checks
layout, ABI, packet and supported simple-path conditions. A refused preparation
leaves the prior binding unchanged. An existing source lease may cover the batch,
but each request still needs readiness and exact owner checks.

Rwlock ABI3 acquires exclusive writer admission before the first body. An unstarted
refusal cancels it while retaining the gate; a native retry must reacquire it.
A progressed native remainder keeps admission until its matching writer unlock.
Rwsem outer writers reserve/drain before entering the mutex queue.

The terminal clobber unlock can complete with IP/SP/BP only. If its exact fast
completion conditions do not hold, the wrapper constructs the original CALL once,
materializes FULL and uses the dispatcher. Supported controls/scalar services may
resume at validated continuations. An ordinary untranslated callee finishes the
remaining invocation on the origin; it does not resume JIT after arbitrary native
work or reset the body.

Supported instruction markers resume the origin before the selected instruction
with the declared arithmetic flags. Prior stores and locks remain owned; the entry
retains its existing eligibility for later invocations. The optional ABI2
original-task instruction service instead retains node/frame/owner through an
intermediate ACK and resumes the same image after exact RDTSC/RDTSCP/CPUID.
Its source, flags and remaining-budget contract is separate from a native suffix.
Generic faults, missing targets and budget
errors are not arbitrary recovery boundaries. Optional address guards and old
string-service/direct-call routes belong to checked/historical compatibility,
not current trusted-source emission.

## Unlock and validation

Unlock follows the exact acquisition, not current heat or an approximate counter.
Public mutex unlock routes local owners, delegation owners and borrowed native
continuations through their retained provider records and ACKs. Rwlock writer
unlock releases the writer byte before gate/spin completion, and completion must
not clear it again after a successor can own it.

A frame leaves the active stack before DONE publication. The waiter reads return
state before reusing storage or releasing its pin. NATIVE_READY permits a checked
native remainder, not root retirement. Native executors, including relays with no
remaining held lock, retain their root/ticket references until cleanup and frame
removal finish. Final native unlock waits for required owner ACKs.

To claim returned JIT execution, require actual completion evidence, correct data,
state restoration and drain. Reader/writer delegated share uses completed writes
as its denominator. `NORMAL`, an entry witness and successful local `NO_JIT` are
different evidence classes. See [validation](VALIDATION.md), [frames](design/frames.md)
and [ownership](design/locking.md).

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

## Executable image generations

Mutex frames bind immutable generations through FULL/native continuations.
Replacement does not overwrite their code or allow an old-generation miss to
modify new metadata. Versions remain allocated until terminal session teardown.

Ordinary spin/rwlock descriptors initially refer to in-place code. Supported root
instruction-marker images make an immutable transition. Retained checked address
and historical string images have their own compatible transition too; production
does not select their analyses or named string routes. Once transitioned, later
generations remain immutable even if their requirements shrink.

Source pins, bound image descriptors, physical ownership and frame retirement
remain distinct. [Lifetimes](design/lifetimes.md) defines their limits. Synchronize
only while idle and never replace frozen inputs under live work.
