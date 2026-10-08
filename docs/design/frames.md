# Shared frames and forward continuation

[Ownership](locking.md) defines physical locks and ACKs; this guide defines the
request storage that survives queue and C-stack handoff. The
[register ABI](../JIT_REGISTER_ABI.md) defines captured state and wrapper exits.

## 9. Nested ownership and continuation

### 9.1 Frames and lock ledger

A stable frame identifies entry/backend/ABI, logical task, parent/resume target,
packet state, role and continuation. Its lock ledger records exact held/released
locks and their native routes. It does not acquire locks. State transitions must
match actual effects: a completed release cannot become an unstarted CALL retry.

`kd_exec_current_frame()` is physical executor state. The logical waiter can be a
different task. Binding keeps both identities; hardware current/GS/IRQ/RCU context
is not replaced. Shared per-CPU executor storage must be exclusively owned before
publication, including a mutex owner that sleeps.

### 9.1.1 Reuse-before-copy contract

Spin producer and combiner share one continuation/frame/packet. A virtual child has
its own frame and ledger but aliases the root packet through `regs_ref`. There are
no node-to-frame/frame-to-node snapshots or whole-record clears on this path.
Independent owner/control state, initial capture and final restoration remain necessary.

Each CPU reserves 20 KiB: low 12 KiB for twelve 704-byte continuations and high 8 KiB
for the wait stack. The 8512-byte continuation-stack layout is aligned and offset
inside the low region. Allocation/partial rollback retain the original base.
Only the producer changes top; remote cleanup publishes `retired` after pop and
cannot move that top. Reclaim only a contiguous retired suffix.

The compact 648-byte frame places its header and IP/SP/BP in one cacheline; the next
line backs five virtual GPRs. Source/provenance pointers share another line.
[Spin implementation](spin_implementation.md) gives offsets and prefetch coverage.

Mutex MINIMAL/COMPLETE borrows its node packet. FULL detaches current logical state
before generic owner/ACK recovery, whose lifetime can exceed node use. Final mutex
restoration retains a copy before releasing a reusable node. Do not generalize the
spin record's stable lifetime to that mutex node.

### 9.1.2 TCLock reference and state boundaries

TCLock switches real native stacks and preserves six callee-saved registers.
KD executes translated code with a software packet and logical SP/BP on a physical
wrapper stack. Compiler-owned caller spills are shared source stack data in either
case, not evidence that arbitrary memory remained unchanged. Cross-backend structures
cannot be merged solely because both carry a continuation.

### 9.2 A/B execution

1. A is acquired on its physical backend; frame ledger records its exact owner.
2. A known B control captures its original CALL/token and validates resources.
3. Successful local B updates the ledger and advances once. Remote B publishes a
   child with independent ownership and a retained root packet.
4. Child completion detaches/pops before parent DONE. Parent resumes with the current
   packet and real effects; no prefix replay or recapture of initial GPRs.
5. Early A release leaves B live. Later cleanup releases only remaining owned locks;
   reacquisition uses A's original identity if its protocol requires it.

Lock depth is bounded at eight. Scope/ledger checks reject repeat identities,
backend mismatches and invalid outer membership before treating a request as simple.
Minimal mutex roots defer cold routing fields; generic recovery materializes them
before any handler reads them.

### 9.3 Capacity and refusal

Unstarted entry refusal may return to intact native execution. Published or
progressed requests keep their exact effects and lifetime. Supported PENDING
`-ENOMEM`/`-E2BIG` control failures preserve the original callee, return token and
current state for native continuation; no acquired B or consumed CALL is replayed.

Spin native fallback retains its ticket and original physical protocol. Node
exhaustion, continuation exhaustion, ledger fullness and source admission failure
are distinct boundaries. A source lease is not a guarantee that any resource is
available or any executable generation is immutable.

### 9.4 Out-of-order and remote completion

A released outer A and a still-live B require separate ledger entries. Remote lock
release ACK and child-frame completion are different messages. After child work,
pop/detach precedes release-publishing DONE. No frame/packet/node access follows
its final handoff; any later logs or queue decisions use independently retained data.

A physical root remains reserved until every native borrower retires. Native
executors borrow the root ticket before wakeup, keep logical task/backend/lock ACK
identity, then drop the borrow after cleanup/pop. Zero-lock relay frames participate
too. An original thread with no native unlock route still waits for final retirement
before restoring the checked continuation.

One batch source/provider lease spans wrappers, complex/native/remote waits and
all frame unbinds. It is not released merely because the queue node can be reused.

### 9.5 Forward native continuation

Ordinary CALL miss preserves the virtual CALL word and enters the original callee
on the waiter. The remainder of that invocation stays native. Known controls and
typed services can resume JIT at validated registered continuations instead.

Native registration accepts only supported NONE/PENDING and distinct validated
post-acquisition/STACK_CHANGED/remote COMPLETE tags. It verifies callee, token,
IP/SP and phase before borrowing references or publishing a native frame. A held A
does not make every progressed error recoverable.

A local mutex control snapshots and compares 256 bounded live stack bytes plus
exact CALL/token/IP/SP. Equal bytes allow JIT continuation. Changed bytes produce
STACK_CHANGED, retaining current memory and physical owners while the waiter resumes
after the completed control. Insufficient pre-control coverage uses PENDING;
an invalid read/token after progress remains fail-stop. This checkpoint protects
one control interval, not arbitrary concurrent writes or all stack lifetimes.

Spin post-acquisition native continuation has its own completed control tag. It
must not reexecute B, release A twice or assume a physical unlock ACK also popped
the frame. [ABI](../JIT_REGISTER_ABI.md#native-continuation-and-final-restore) defines
packet restoration; [locking](locking.md) defines the owner obligations.

### 9.6 Comparison and remaining scope

Synthetic production-code fixtures check modeled transitions and exactly-once
behavior; they do not establish every live remote/native schedule. Ordinary native
controls, actual JIT, context refusals and returned-body evidence remain separate.
Known pinned-waiter dependencies, dynamic-address guards, general flags repair
and immutable code versions remain open or deferred in [TODO](../TODO.md).
