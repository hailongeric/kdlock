# Shared frames and forward continuation

A delegated request can outlive its queue node and the C call that created it.
Its frame keeps the state needed to finish the work and resume the caller.
This guide explains when that storage can be reused. [Ownership](locking.md)
covers locks and unlock acknowledgements; [register ABI](../JIT_REGISTER_ABI.md)
covers saved registers and wrapper exits. Start with the
[glossary](../DESIGN.md#terms-used-in-these-guides) if these terms are new.

## 9. Nested ownership and continuation

### 9.1 Frames and lock ledger

A frame identifies one request: its entry address, backend, ABI, original task,
parent, saved registers and resume point. Its **lock ledger** records which locks
are held, which have been released and how native code must unlock them. The
ledger records real effects; it does not perform them. Once a release has happened,
recovery must not describe the operation as an unstarted CALL and retry it.

`kd_exec_current_frame()` belongs to the thread physically executing the code.
The original waiter may be a different task. Binding a frame tracks both identities,
but does not switch hardware current/GS/IRQ/RCU context. One executor must own the
shared per-CPU storage before publishing a frame. A mutex owner that sleeps must
retain that exclusive use of the storage.

### 9.1.1 Reuse-before-copy contract

The spin waiter creates a continuation containing its frame and register packet.
The combiner uses that same storage. A virtual child has its own frame and lock
ledger, but `regs_ref` points to the root's register packet. This path does not
copy snapshots between node and frame or clear whole records. It still needs the
initial register capture, final restore and any owner/control state with a separate
lifetime.

Each CPU reserves 20 KiB: low 12 KiB for twelve 704-byte continuations and high 8 KiB
for the wait stack. The 8512-byte continuation-stack layout is aligned and offset
inside the low region. Allocation/partial rollback retain the original base.
Only the CPU that allocated a record may move the stack top. Remote cleanup marks
the record `retired` after removing its frame; it cannot move that top. Reclaim
records from the top only while each successive record is retired. Never reclaim
past a record that is still live.

The compact 648-byte frame places its header and IP/SP/BP in one cacheline; the next
line backs five virtual GPRs. Source/provenance pointers share another line.
[Spin implementation](spin_implementation.md) gives offsets and prefetch coverage.

For ABI3 rwlock roots, `rwlock_admitted` shares one byte with `spin_kind` and
`spin_regs_decoded`; the header and IP/SP/BP offsets stay unchanged. It records
native writer admission before body execution, not a second register snapshot.
Virtual spin children inherit the entry ABI but do not acquire a rwlock count.

Mutex requests use the packet in their queue node while MINIMAL or COMPLETE;
owned ABI4 uses CALLEE_ENTRY and CALLEE_COMPLETE for its nonvolatile-register
contract. The initial eight-word capture is allocated only after local acquisition
fails, and completion restores the updated values. On a FULL exit, KD copies
the current logical state into independent frame storage
before general owner/ACK recovery, because that recovery may outlive the node.
Final restoration also keeps a copy before releasing a reusable node. Spin
continuations have a longer lifetime than these mutex nodes; they cannot use the
same reuse rule.

### 9.1.2 TCLock reference and state boundaries

TCLock saves six callee-saved registers and switches onto the waiter's real stack.
KD keeps the executor on its wrapper stack and represents the waiter's registers,
SP and BP in software. Both can access values the compiler saved on the waiter's
original stack. Neither approach proves that other code left those values unchanged.
These different execution models need different storage and restore rules.

### 9.2 A/B execution

Suppose a body holds lock A and then acquires lock B:

1. Record A's actual physical owner in the frame's ledger.
2. For a recognized B lock call, save the original CALL and return token, then
   check that the required resources are available.
3. If B is acquired locally, record it and advance past the CALL once. If B needs
   remote execution, publish a child frame with its own ownership state and keep
   the root register packet alive.
4. Remove the completed child before publishing the parent's DONE notification.
   Resume the parent with the current packet and the effects already performed.
   Do not replay earlier instructions or restore the initial register values.
5. If A is released before B, keep tracking B. Cleanup releases only locks still
   held. If the protocol later requires reacquiring A, use A's original identity.

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

An unstarted ABI3 refusal cancels writer admission while the gate is held.
Its physical native retry reacquires admission before restoring the prepared
body, because the old acquisition helper's C frame is discarded. A progressed
suffix retains admission through normal write unlock and native ACK handling.
Completion clears only the frame's admission bookkeeping; the body has already
released the count byte. See [the rwlock protocol](rwlock_implementation.md).

### 9.4 Out-of-order and remote completion

Releasing outer lock A does not release a still-held B. Keep separate ledger
entries. Likewise, an ACK for a remote unlock does not say that the child frame
has finished. After the child finishes, remove it before publishing DONE with
release ordering.

After the final handoff, another thread may reuse the frame, packet or node. Do
not read it again, even for logging or queue decisions. Save any later-needed
information in storage that remains yours.

A native executor takes a reference to the root ticket before it is woken. It
keeps the original task, backend and lock identity needed for ACKs, and releases
that reference only after cleanup and frame removal. Even relay frames with no
held locks follow this rule. The physical root stays reserved until every such
reference is released. An original thread that has no native unlock left to do
still waits for final retirement before restoring its continuation.

The batch source/provider lease stays live through every wrapper, complex or
native path, remote wait and frame unbind. A reusable queue node does not by itself
allow that lease to be released.

### 9.5 Forward native continuation

Ordinary CALL miss preserves the virtual CALL word and enters the original callee
on the waiter. The remainder of that invocation stays native. Known controls and
typed services can resume JIT at validated registered continuations instead.

Native registration accepts only supported NONE/PENDING and distinct validated
post-acquisition/STACK_CHANGED/remote COMPLETE tags. It verifies callee, token,
IP/SP and phase before borrowing references or publishing a native frame. A held A
does not make every progressed error recoverable.

Before a supported local mutex control, KD snapshots 256 bytes within the
waiter's live stack. After the call, it compares those bytes and checks the exact
CALL, return token, IP and SP. If they still match, JIT may continue. If the bytes
changed, STACK_CHANGED resumes the waiter after the completed call, preserving
the new memory contents and real lock owners.

If KD cannot cover the required stack bytes before the call, it uses PENDING
without executing that control. A bad read or token after progress is still a
fail-stop error. This checkpoint covers one control call; it does not protect
against every concurrent stack write or prove all stack objects remain alive.

Spin post-acquisition native continuation has its own completed control tag. It
must not reexecute B, release A twice or assume a physical unlock ACK also popped
the frame. [ABI](../JIT_REGISTER_ABI.md#native-continuation-and-final-restore) defines
packet restoration; [locking](locking.md) defines the owner obligations.

### 9.6 Comparison and remaining scope

Synthetic production-code fixtures check modeled transitions and exactly-once
behavior; they do not establish every live remote/native schedule. Ordinary native
controls, actual JIT, context refusals and returned-body evidence remain separate.
Known pinned-waiter dependencies, dynamic-address guards, general flags repair
and immutable versions for legacy image families remain open or deferred in
[TODO](../TODO.md). Owned frames retain an immutable descriptor for their entire
execution and continuation.
