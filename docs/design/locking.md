# KD spin, mutex and rwlock ownership

This guide explains who really holds a KD lock and how that responsibility moves
between callers and combiners. [Lock protocols](lock_protocols.md) compares all
backends; [frames](frames.md) explains how request state stays alive. The
[glossary](../DESIGN.md#terms-used-in-these-guides) defines the common terms.
Approximate heat counters help choose future requests; they cannot prove ownership
or authorize an unlock.

## 4. Spin delegation protocol

### 4.1 Native lock and private queue

An explicit `kd_spinlock_t` is one 32-bit KD word. Fast, pending, MCS, combiner and
native fallback all use that word; no second Linux lock is acquired. The native
pending/MCS path publishes a CPU/node tail, release-links successors and uses
acquire handoff. Only node exhaustion falls back to word polling.

Locked byte 5 denotes ordinary nondelegating ownership. Unlock releases only the
owned byte, preserves pending/tail, retires its exact in-flight count and unpins.
Other locked states use the stable owner/ticket protocol. Each physical lock must
have one protocol: Linux, TCLock and KD tail encodings cannot be mixed.

### 4.2 Acquisition tickets and node lifetime

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

### 4.3 Combiner and native returns

The combiner holds the KD word, binds a logical waiter and executes its ready body.
Simple roots may use minimal completion; ABI0, nested and complex exits require their
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

### 4.4 Nested contention and stack resources

For A→B, add only actually acquired B to the child ledger. A local successful
control advances its CALL once. Remote B uses a child frame and retained parent;
parent continuation resumes only after child pop and DONE. Native B keeps a
validated pending CALL or post-acquisition tag, according to the actual boundary.

Early release of A marks that ledger entry released while B remains owned. Later
cleanup cannot repeat A's physical release. If A must be reacquired, use its exact
original ticket and backend. Refusal before publication preserves CALL state;
resource failure after progress cannot be relabelled an unstarted retry.

## 5. Mutex delegation protocol

KD mutexes retain exact physical owners and acquisition references through
native continuation and ACK.

### KD-owned mutex ownership

`struct kd_mutex` owns its 32-byte owner/OSQ/wait-list object for its entire
lifetime. Only KD APIs may access it. SELF callers and delegated executors use
the same owner word; there is no second lock or address-indexed shadow gate.
The [implementation flowcharts](mutex_implementation.md#owned-abi4-acquisition-and-release-flow)
cover ABI4 local acquisition, late capture, guarded publication and unlock.

An explicit outer acquisition returns the exact physical-task cookie on SELF
or directed GRANTED pickup. A borrowed FULL continuation carries zero and routes
unlock to the retained owner, waiting for its exact ACK. COMPLETE means the body
already finished. The shared frame ledger must record nested acquisitions and
early releases exactly once on every path.

Ordinary/nested native acquisitions retain task-local held counts and never combine on
unlock. Only explicit outer unlock may detach and execute a leading DELEGATE
prefix. WAITERS/DELEGATION remain set while detached work still needs ownership.
An early outer release rejoins unstarted requests before releasing A; the batch
does not reacquire or access A while a still-held B finishes. No later heat or
admission change can cancel already published work or its cleanup obligations.

Result waits use bounded polling then sleeping with reserved stacks and migration
pins. This does not limit the separate Linux-style SELF optimistic spin phase.
Stop callers and drain the object, producer packets, executor, frames and ACKs
before reinitializing or freeing its storage.

### Nested controls and native continuation

A translated nested acquisition obtains another KD mutex on the physical executor
and records `KD_EXEC_LOCK_OWNED` in the frame ledger. A validated PENDING control
boundary resumes the original CALL; a checked STACK_CHANGED boundary resumes
after the completed CALL. Existing acquisitions retain their physical owners,
which service native unlock requests and exact ACKs. No path replays an acquisition
or rolls back body effects.

Task records remain live through the final owner ACK. Zero-reference identities
stop routing immediately; eviction unlinks them before RCU releases the record
and task reference. Independent requests retain independent ACK packets.

| Boundary | Spin | KD mutex |
| --- | --- | --- |
| Physical exclusion | KD word | KD owner word |
| Waiters | Tail in the spin word | Tagged SELF/DELEGATE FIFO |
| Native continuation | Generation-checked ticket/borrow | Task acquisition reference and owner ACK |
| Sleeping | Ordinary spin path does not sleep | SELF waiters, delegates and physical owner may sleep |
| Restore | Stable continuation retained through packet reads | Producer packet; FULL detaches state before packet reuse |

### Spin diagnostic identity lifetime

Exact address/generation controls still own the request. The 32 aligned diagnostic
slots retain identity/disable state; per-CPU published/exited event totals are
observational. A live aggregate may be stale or temporarily negative. Check final
balance only after independent lock/frame/ticket drain; a nonzero final balance is
an invariant failure. Do not use the live balance as admission, ownership or
reclamation state. Mutex exact lifecycle balances remain separate.

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
cannot participate in this object, and no sleeping rwsem contract is provided.
