# KD spin, mutex, rwlock and rwsem ownership

This guide explains who really holds a KD lock and how that responsibility moves
between callers and combiners. [Lock protocols](lock_protocols.md) compares all
maintained backends; [frames](frames.md) explains how request state stays alive. The
[glossary](../DESIGN.md#terms-used-in-these-guides) defines the common terms.
Approximate heat counters help choose future requests; they cannot prove ownership
or authorize an unlock.

<a id="4-spin-delegation-protocol"></a>

## Spin delegation protocol

<a id="41-native-lock-and-private-queue"></a>

### Native lock and private queue

An explicit `kd_spinlock_t` is one 32-bit KD word. Fast, pending, MCS, combiner and
native fallback all use that word; no second Linux lock is acquired. The native
pending/MCS path publishes a CPU/node tail, release-links successors and uses
acquire handoff. Only node exhaustion falls back to word polling.

Locked byte 5 denotes ordinary nondelegating ownership. Unlock releases only the
owned byte, preserves pending/tail, retires its exact in-flight count and unpins.
Other locked states use the stable owner/ticket protocol. Each physical lock must
have one protocol: Linux, TCLock and KD tail encodings cannot be mixed.

<a id="42-acquisition-tickets-and-node-lifetime"></a>

### Acquisition tickets and node lifetime

A lock address is not enough to identify one acquisition. KD uses a fast-owner
record or a ticket with a checked generation. A physical request reserves its
identity once and keeps it through retries, including reacquisition after an early
release. Ticket state tracks native handoff and references held by other executors.
Storage cannot be reclaimed until those references are gone. Heat-table collisions
or a full heat table do not remove ownership records.

Scheduling nodes are bounded and reusable. Their stable continuations survive
node reuse and C-stack return. A child has its own frame/ticket while sharing the
root register packet. Do not read a node after notification or outer release can
let it be reused; completion/ACK metadata needed later lives outside that node.

<a id="43-combiner-and-native-returns"></a>

### Combiner and native returns

The combiner holds the KD word, binds a logical waiter and executes its ready body.
Simple roots may use minimal completion; legacy/nested/complex exits require their
own checks. After final body completion, pop the frame before release-publishing
parent DONE and waiter completion. Queue handoff and physical unlock remain exact.

NATIVE_READY means that the waiter may run a checked remainder of the body using
its current logical state. It does not mean the root request can be freed. Each
native executor takes a reference to the root ticket before wakeup, even if it is
only relaying a continuation and holds no lock. The physical owner processes unlock
requests and returns ACKs. Executors release their references after cleanup and
frame removal.

Final native unlock waits for all those references, releases the root storage,
and only then ends the original preemption pin. A caller with no native unlock
left still waits for retirement before its final restore. It must never reclaim
fields another executor still uses.

<a id="44-nested-contention-and-stack-resources"></a>

### Nested contention and stack resources

For A→B, add only actually acquired B to the child ledger. A local successful
control advances its CALL once. Remote B uses a child frame and retained parent;
parent continuation resumes only after child pop and DONE. Native B keeps a
validated pending CALL or post-acquisition tag, according to the actual boundary.

Early release of A marks that ledger entry released while B remains owned. Later
cleanup cannot repeat A's physical release. If A must be reacquired, use its exact
original ticket and backend. Refusal before publication preserves CALL state;
resource failure after progress cannot be relabelled an unstarted retry.

### Spin diagnostic identity lifetime

Exact address/generation controls still own the request. The 32 aligned diagnostic
slots retain identity/disable state; per-CPU published/exited event totals are
observational. A live aggregate may be stale or temporarily negative. Check final
balance only after independent lock/frame/ticket drain; a nonzero final balance is
an invariant failure. Do not use the live balance as admission, ownership or
reclamation state. Mutex exact lifecycle balances remain separate.

<a id="5-mutex-delegation-protocol"></a>

## Mutex delegation protocol

<a id="51-physical-lock-and-scheduling-gate"></a>

### Physical lock and scheduling gate

KD owns a 256-byte `struct kd_mutex`, with its physical owner, sleeping wait list,
private OSQ and legacy delegation gate. Every delegation executor acquires physical
exclusion as well as the gate; ordinary local callers acquire physical exclusion
without joining that gate. There is no Linux mutex object or shadow lookup.
Every caller must obey the [KD-only object/API contract](kd_only_mutex.md); loading the module
does not replace objects in the running kernel.

Task/acquisition records retain real task references and exact unlock routing
through final ACK. A profiling value cannot authorize release.

<a id="52-entry-completion-and-task-routing"></a>

### Entry, completion and task routing

<a id="mutex-outer-direct"></a>

#### Outer direct pair

`KD_MUTEX_OUTER_LOCK/UNLOCK` keeps a cookie for one acquisition. The same task must
use it for the matching unlock; callers must not copy, modify or transfer it.
The caller makes up to eight read-guarded owner probes, with a pause after each
failure. If its zero-owner CAS succeeds, the cookie records the native owner and
unlock calls `kd_mutex_local_unlock`. If the bounded window is exhausted, the
provider counts that contention once and enters legacy admission without
repeating the probe window. The existing active-combiner gate state (3) also ends retries, so new work
joins a batch promptly. A lone gate owner (state 1) may finish its local body
during the bounded retry window. The observed state is only a hint;
it never authorizes ownership or retirement. There is no worker-count threshold.

A native fallback may return the exact task owner only before it takes a KD
reference or gate. Once the request enters the KD queue, it returns zero instead.
Zero tells the matching unlock to use KD's ownership routing.

The physical return preserves its result. The separate JIT entry defines zero
before using the cookie, avoiding an incoming-RAX dependency under MINIMAL. Nested
JIT controls use `KD_MUTEX_DIRECT_LOCK/UNLOCK`, not the outer result-returning entry.
The void direct interfaces retain ABI2; generic control recovery uses FULL state.
Linux mutex bridge symbols are refused by the KD-only translator.

#### Provider acquisition and completion

Before executing a delegated body the combiner must hold KD physical exclusion.
The frame ledger records that physical owner. A batch may retain its source lease
and physical ownership, but cannot bypass physical exclusion or owner checks.
Dedicated ABI2 preparation/completion/retirement avoids generic work for eligible
simple roots; FULL exits materialize cold routing fields before generic use.

A terminal COMPLETE returns only IP/SP/BP and can retire its queue node once no
executor needs it. Queue tail retirement CASes the exact tail; when a successor is
not yet linked, wait for publication rather than dropping it. A completed waiter
never reexecutes its body or unlock. Current mutex batching has a default
1024-body cap and bounded NUMA selection. Only fully linked remote nodes can be
deferred; every exit rejoins them before handoff. The
[implementation guide](mutex_implementation.md#queue-batch-execution-and-recovery)
defines the scan/cohort limits and small-remote-cohort service rule.

#### Pinned waiting and blocking owners

After publishing a request, a KD waiter stays preemption-disabled and polls with
PAUSE on a reserved stack. The physical mutex owner or a service path may sleep,
but remains pinned against migration. One real task owns each per-CPU executor
context. A competing task on that CPU must be refused before publishing a frame;
it cannot overwrite the current packet or continuation.

With more runnable tasks than CPUs, a pinned waiter can prevent a task it depends
on from running. The reproduced mode-4 failure remains in
[TODO](../TODO.md#current-checkpoint).

<a id="53-nested-ab-and-native-continuation"></a>

### Nested A/B and native continuation

Local B acquisition uses the KD physical primitive and records the combiner as physical
owner. A validated PENDING capacity/control boundary resumes the original CALL;
a checked STACK_CHANGED boundary resumes after the already-completed CALL.
Previously acquired A/B remain on their real owners, serviced through native
unlock notifications and exact ACKs. Never roll back memory or replay acquisition.

An ordinary untranslated interruptible/killable CALL runs on the original waiter
with its source return token. The native callee supplies its real result; `-EINTR`
creates no B ownership. Uninterruptible `mutex_lock` completes its suffix and ACKs
before userspace signal/exit handling. Generic post-progress faults remain fail-stop.

Each acquisition holds its task-record reference through final owner ACK. Zero-ref
records immediately stop routing and may remain in the bounded inactive cache.
Eviction unlinks the identity; the record and task reference are released after RCU
readers drain. Native frames for independent tasks/locks use independent ACK packets.

<a id="54-differences-from-spin"></a>

### Differences from spin

| Boundary | Spin | Mutex |
| --- | --- | --- |
| Physical lock | KD word | KD-owned owner word and sleeping wait list |
| Queue | Tail in the same word | Legacy scheduling fields in the same object |
| Native route | Generation-checked ticket/borrow | Task acquisition reference and owner ACK |
| Sleeping | Ordinary path does not sleep | Physical owner/control may sleep |
| Restore | Stable continuation retained through packet reads | Node packet; FULL copy before node reuse |

## Rwlock ownership over the spin gate

The [rwlock protocol](rwlock_implementation.md) adds a count to the KD spin gate.
Readers execute locally and retain their count through read unlock. An ungated
native writer owns a distinct count byte and an exact nondelegated reference;
gate ownership is not required on that route. Gated writers must own both the
gate and writer admission before the application body, including ABI3 JIT entry.

Only unstarted refusal can cancel admission and later reacquire it on native
retry. A progressed suffix keeps exclusion and the spin ticket/ACK protocol.
The body releases the writer byte before spin unlock/completion; final frame
cleanup cannot release that byte again. Readers, native writers and delegated
writers must all drain before lock storage is reused. Linux and TCLock rwlocks
cannot participate in this object. Sleeping read/write operations use the
separate [KD rwsem](rwsem_implementation.md).

## Rwsem ownership around the mutex gate

A rwsem has three independent obligations: admitted readers retain their read
count, every writer retains an admission reservation, and an executing writer
owns the KD physical mutex. A positive reservation permits joining an outer
writer phase; it does not identify the physical executor or replace the mutex
owner, task reference, frame or acknowledgement.

| Boundary | Required ownership and release order |
| --- | --- |
| Reader enters | Publish a reader count and recheck open admission before accessing data; roll back a failed speculation |
| Ordinary writer enters | Reserve admission `-1`, acquire the mutex locally, then drain readers |
| Outer writer enters | Acquire one positive reservation and drain readers while schedulable, then enter the unchanged mutex outer interface |
| Delegated writer completes | Finish the matching mutex unlock and its required acknowledgement before the origin drops its reservation |
| Ordinary writer unlocks | Release physical mutex ownership before reopening admission |
| Ordinary writer downgrades | Publish a reader count while still exclusive, release the mutex, then reopen admission |
| Final outer reservation leaves | Reopen admission and wake phase waiters only when the exact reservation count reaches zero |

The reservation surrounds the whole outer pair even if an invocation executes
locally. A delayed origin can conservatively keep admission closed after its
body has finished. No executor may decrement that origin's reservation merely
because its JIT body returned. Outer writers cannot cancel after publication or
downgrade: creating a reader behind published pinned writers would violate the
reader-free phase.

After joining all users, `kd_rwsem_is_idle` checks reader/admission counts, both
sleeping waitqueues and embedded mutex state. Provider frames, source leases and
native acknowledgements must also be drained. The [rwsem implementation](rwsem_implementation.md)
owns the waiting algorithm, cancellation details and integration limits.
