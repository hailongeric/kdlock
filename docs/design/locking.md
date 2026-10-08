# KD spin and mutex ownership

This guide defines exact ownership and handoff. [Lock protocols](lock_protocols.md)
compares all six backends; [frames](frames.md) defines storage and continuation.
Admission counters are approximate and never substitute for these controls.

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

Fast owners and generation-checked tickets identify the exact acquisition, not
just its address. A physical request reserves once; retries and early-release
reacquisition keep its original identity. Ticket phase/borrow state controls native
handoff and final reclamation. Heat-table collisions or capacity do not erase owners.

Scheduling nodes are bounded and reusable. Their stable continuations survive
node reuse and C-stack return. A child has its own frame/ticket while sharing the
root register packet. Do not read a node after notification or outer release can
let it be reused; completion/ACK metadata needed later lives outside that node.

### 4.3 Combiner and native returns

The combiner holds the KD word, binds a logical waiter and executes its ready body.
Simple roots may use minimal completion; legacy/nested/complex exits require their
own checks. After final body completion, pop the frame before release-publishing
parent DONE and waiter completion. Queue handoff and physical unlock remain exact.

NATIVE_READY transfers permission to run a validated suffix with current logical
state; it is not final retirement. Every native executor, including a zero-lock
relay, borrows the root ticket before wakeup. The physical owner services unlock
requests and ACKs. After cleanup/pop, executors drop their borrows. The final native
unlock waits for all borrowers, releases root storage, then ends the original pin.
A continuation with no remaining native lock routes still waits for retirement
before final restore. The original thread cannot reclaim fields another executor
still needs.

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

### 5.1 Physical lock and scheduling gate

KD uses the original Linux `struct mutex`. Its owner word, wait list, sleeping
rules and native peers remain authoritative. A private `komb_mutex` shadow gate
serializes KD queue execution; gate ownership does not itself own Linux's mutex.
No global mutex interception is installed.

Exact shadow addresses select the gate. The current 1024-entry table has lock-free
published-key reads and serialized insertion; full capacity falls back natively.
Task/acquisition records route retained native unlocks and hold real task references
through final ACK. A profiling value cannot authorize release.

### 5.2 Entry, completion and task routing

<a id="mutex-outer-direct"></a>
#### Outer direct pair

`KD_MUTEX_OUTER_LOCK/UNLOCK` uses an opaque, same-task, nontransferable acquisition
cookie. Successful caller-side owner CAS records that native owner; matching unlock
calls original `(mutex_unlock)`. On failure, the provider counts the entry once and
continues without retrying that first CAS. Native fallback before KD reference/gate
returns the exact task owner; entry into the KD queue returns zero.

The physical return preserves its result. The separate JIT entry defines zero
before using the cookie, avoiding an incoming-RAX dependency under MINIMAL. Nested
JIT controls use `KD_MUTEX_DIRECT_LOCK/UNLOCK`, not the outer result-returning entry.
Existing void contended and kernel bridge aliases remain compatible; generic
bridge/control recovery uses FULL state.

#### Provider acquisition and completion

Before executing a delegated body the combiner must hold the original Linux mutex.
The frame ledger records that physical owner. A batch may retain its source lease
and physical ownership, but cannot bypass native-peer exclusion or owner checks.
Dedicated ABI2 preparation/completion/retirement avoids generic work for eligible
simple roots; FULL exits materialize cold routing fields before generic use.

A terminal COMPLETE returns only IP/SP/BP and can retire its queue node once no
executor needs it. FIFO tail retirement CASes the exact tail; when a successor is
not yet linked, wait for publication rather than dropping it. A completed waiter
never reexecutes its body or unlock. Current mutex batching is FIFO, bounded at
1024 bodies; the rejected NUMA grouping experiment is not current behavior.

#### Pinned waiting and blocking owners

Published KD waiters remain preemption-disabled and PAUSE-poll on reserved stacks.
Physical mutex owner/service paths may sleep while migration-pinned. A per-CPU
executor context is owned by one real task; a competing task on that CPU must be
refused before frame publication rather than overwrite its packet/continuation.
Pinned waiters can create oversubscribed scheduling dependencies; the known mode-4
failure remains in [TODO](../TODO.md#current-checkpoint).

### 5.3 Nested A/B and native continuation

Local B acquisition uses the original mutex and records the combiner as physical
owner. A validated PENDING capacity/control boundary resumes the original CALL;
a checked STACK_CHANGED boundary resumes after the already-completed CALL.
Previously acquired A/B remain on their real owners, serviced through native
unlock notifications and exact ACKs. Never roll back memory or replay acquisition.

An ordinary untranslated interruptible/killable CALL runs on the original waiter
with its source return token. The native callee supplies its real result; `-EINTR`
creates no B ownership. Uninterruptible `mutex_lock` completes its suffix and ACKs
before userspace signal/exit handling. Generic post-progress faults remain fail-stop.

Each acquisition holds its task-record reference through final owner ACK. Zero-ref
records leave the lookup table and are freed with the task reference after RCU
readers drain. Native frames for independent tasks/locks use independent ACK packets.

### 5.4 Differences from spin

| Boundary | Spin | Mutex |
| --- | --- | --- |
| Physical lock | KD word | Original Linux mutex |
| Queue | Tail in the same word | Separate shadow gate |
| Native route | Generation-checked ticket/borrow | Task acquisition reference and owner ACK |
| Sleeping | Ordinary path does not sleep | Physical owner/control may sleep |
| Restore | Stable continuation retained through packet reads | Node packet; FULL copy before node reuse |

### Spin diagnostic identity lifetime

Exact address/generation controls still own the request. The 32 aligned diagnostic
slots retain identity/disable state; per-CPU published/exited event totals are
observational. A live aggregate may be stale or temporarily negative. Check final
balance only after independent lock/frame/ticket drain; a nonzero final balance is
an invariant failure. Do not use the live balance as admission, ownership or
reclamation state. Mutex exact lifecycle balances remain separate.
