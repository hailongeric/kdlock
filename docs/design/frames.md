# Shared frames and forward continuation

Current implementation contract; start with the [design overview](../DESIGN.md).
Validation belongs to its frozen inputs in [tests](../../tests/README.md).

## 9. Nested Ownership And Continuation

### 9.1 Frames And Lock Ledger

A frame tracks backend, logical task, GS, supported registers, explicit held
locks, parent/requester links and control-call phase. Physical ownership is
not inferred from logical depth. Cross-backend controls are rejected.
Pre-entry context/resource refusal leaves valid queue/native ownership intact;
it does not grant permission to replay an executed frame.

The per-CPU context's `top`/`parent` links and `depth` describe the physical
execution chain. Spin frames live in producer-owned continuation storage; mutex
frames retain the fixed per-CPU array. Bind changes the physical parent, depth
and batch association without copying the request frame. Pop is the common
unbind/retirement check: physical LIFO ownership, terminal state, remote
requests and native routing/ACKs must be clear. It does not reclaim a spin
continuation or copy its packet. Whole-context scans remain SELFTEST diagnostics.
`jit_lock_depth` bounds the live lock prefix; inactive arrays are not cleared.

A physical spin root with one lock starts with `spin_simple`. Its first wrapper
return completes directly only for CALL_MISS at the exact spin-unlock target
with the matching outer lock. Other dispatch exits capture the independent
combiner checkpoint before servicing controls/hostcalls or publishing native
work. Remote and physically nested frames capture that checkpoint at entry.
These are distinct physical executor states, not copies of logical registers.

### 9.1.1 Reuse-Before-Copy Contract

**2026-09-20: spin continuation storage and retirement handoff implemented; JIT remains the backend.**
Reusable register/frame state has one authoritative object shared by waiter and
combiner. Initial CPU capture and final CPU restoration are necessary boundaries;
node-to-frame, frame-to-node and final software restoration snapshots are absent
from this spin path. Mutex and the legacy frame-push API retain their own packet
handling. This is not a replacement of every state snapshot in the repository.

Each CPU preallocates one 20 KiB region. The low 12 KiB contains a
64-byte-aligned continuation stack (12 records, each 704 bytes); the high 8 KiB
is the physical waiter polling stack. These regions never overlap. The four
128-byte scheduling nodes still point directly to stable execution records.
Combiner C and JIT physical stacks remain on the executor's task stack; virtual
SP continues to address the logical waiter stack.

The continuation stack starts at a bounded, CPU-dependent offset inside that
low 12 KiB region. With the current 8512-byte layout, initialization selects
`((cpu * 13) % 60) * 64` bytes, preserving cache-line alignment and distributing
root packets across different page offsets. The number of choices is derived
from the remaining space, not a larger allocation. The highest offset is 3776
bytes, so all 12 records still end before the polling stack. This changes only
the initialized continuation pointer: requests add no offset calculation,
packet copy, or allocation. The polling stack retains its original base and
top; teardown and partial-initialization rollback recover the allocation base
from `wait_stack_top - KD_SPIN_STORAGE_BYTES`, never free the interior
continuation pointer. Reservation, completion publication and retirement keep
the protocol below. Performance evidence and its cache-causality limits are in
the [historical layout investigation](../../bench/tclock_compare/results/HISTORY.md#20260923-spin-single-hot-balance).

Reservation takes the next stack record. Release marks it retired and collapses
only the contiguous retired top; holes below a live top are neither scanned for
allocation nor moved. Only the allocating CPU changes top. A remote native child
may release-publish its retired marker after pop; its producer collapses it on
its next reservation/release. No request `users` or `packet_owner` remains.
The stack header plus records occupies 8512 bytes within the reserved 12 KiB.
Exact object sizes, allocation sites and cross-CPU data flow are maintained in
[execution paths](spin_implementation.md).
Exhaustion before publication uses native KD MCS with the existing ticket.
Pinned physical context is rejected before a delegation node is published.

The protocol is:

1. The producer prepares the continuation and register packet in place. `frame.spin_kind`
   distinguishes physical roots and virtual children; `result` distinguishes
   queued, unstarted retry and NATIVE_READY. Whole records are not cleared.
2. Release publication transfers execution to the combiner, which binds the
   same frame and packet. A virtual child has its own lock ledger and aliases
   the root packet through `regs_ref`; no packet retain/copy is needed.
3. Ordinary completion finishes child work, detaches the remote parent, pops
   the frame, then release-publishes remote DONE and node completion. DONE never
   means only “the remote lock was released”. No frame/packet access follows
   final completion publication; queue work and logs use independent data.
4. The physical waiter restores RIP/SP/BP or the full GPR packet. After every
   packet load, the final assembly marks the record retired and collapses the
   CPU's stack top, then consumes the retained completion pin through a GPR-preserving helper and returns. An unstarted head
   return releases its record on the intact C stack.
5. NATIVE_READY grants permission to execute the checked native suffix, not
   permission to free the record or end the root pin. Every executor, including
   a zero-lock relay, borrows the root ticket before the original thread wakes.
   Physical unlock ACKs remain independent messages. After cleanup/pop, each
   executor drops its borrow; the final native unlock waits for all borrows,
   releases root storage, then ends the original entry's preemption pin.
6. If NATIVE_READY has no remaining native lock routes, the original thread
   waits for retirement before restoring the checked IP. Its assembly releases
   the root after the last packet load. A virtual native record is marked
   retired after pop and before remote DONE; only its owner CPU reclaims top.

One source/provider lease spans each batch through all native/remote waits and
frame unbinds. Bind still checks admission. Ticket generation, physical owner,
lock ledger and ACK routing remain separate checks; early-release reacquisition
uses the original ticket and never repeats a completed physical release.

The 648-byte frame begins at the aligned continuation base. Its 40-byte core
header and private `kd_regs.ip/sp/bp` at offsets 40/48/56 fill one 64-byte line.
That line carries the entry RIP, lock identity, entry ABI, packet state, depth
and frame state. The five virtual GPR backing slots occupy offsets 64..96 in
the next line; regs_ref, GS, logical task and parent share offsets 208..232.
All FULL fields remain in the 168-byte packet. Linux pt_regs is unchanged and
must never be cast to this private type. Layout-2 image directories are required
before NORMAL publication, including legacy FULL entries.

Only two queue-private tags share a byte; their producer initializes them before
publication. Notification, exact owner/ACK state and the 32-bit result are not
packed into those bits. The 704-byte continuation and 8512-byte storage stack
retain their capacities and alignment. Result/retirement metadata follows the
frame, keeping the hot line separate from final storage retirement.

`complex_ready` still gates the preallocated eight-lock ledger, remote/native
discriminators and combiner snapshot from offset 240. A pristine single-lock
root does not initialize or inspect that cold storage. The first non-final
wrapper exit materializes a one-lock ledger in place before control/hostcall/
native handling. It never copies the spin register packet. The scheduling node
cannot share this storage lifetime: it may be reused before the final owner ACK.
The actual caller stack retains its addresses and aliases; only its authoritative
SP is colocated in the hot line, never a copied stack snapshot.

`kd_spin_batch_run` keeps one physical combiner C frame across the complete
batch, including mixed caller ABIs. Its inline assembly calls expose all GPR
clobbers except RSP/RBP to the compiler. The legacy KDWB002 adapter protects only
RBP, which that wrapper does not restore; KDWC002 restores RBP itself. There is
no outer assembly register group save or per-waiter callback return/reentry.
This follows TCLock's retained combiner continuation while keeping the JIT's
physical scratch frame separate from the logical waiter stack. Admission,
completion/unbind/publication and successor selection remain in the lock loop.
The provider compiles `kd_exec.c`, `exe.c`, `kd_spinlock.c` and `kd_mutex.c`
together through `kd_spin_runtime.c`. Readiness, batch preparation/completion
and frame bind/retire use GNU always-inline definitions: each combiner can see
the helper bodies, while other clients retain external entry points. This changes the compiler's
optimization scope, not the publication, physical-owner or packet contract.
Both seven-byte wrapper directory signatures use exact overlapping 32-bit
loads; admission no longer calls `memcmp` for the clobber directory.

Normal production batch roots combine terminal validation and physical unbind
in `kd_exec_frame_retire_single_spin`: exact physical owner/top/depth, batch
lease, non-complex state and the existing final-packet checks are mandatory.
SELFTEST observers retain the complete/observe/pop sequence; complex returns
retain generic retirement. Queue completion is still published afterward.
Batch limits, NUMA deferral rollback and outer release/reclaim remain lock-side
operations; generated code has no queue/scheduler callback.

In that legacy ABI, only the exact final spin-unlock CALL and matching L use reduced ABI writeback:
RBX/RBP/R12–R15, virtual RIP/SP and the RDI classification field. All other exits
write the full supported GPR packet. `kd_exe_spin_batch_resume` consumes an already
returned packet once, preserving the original entry SP for unstarted-refusal
validation; it must not invoke the JIT again before processing that exit. Legacy
uploads without the alternate-entry signature use the ordinary wrapper path.
Both legacy entries import CPU-resident logical GPRs; virtual R11-R15 backing
now stays directly in the shared packet instead of being copied into a second
wrapper frame. The physical waiter still restores 15 GPRs. Reduced final
writeback does not reduce final CPU-restore traffic; intermediate continuation
boundaries retain their full register requirements.

Caller-clobber v1 has a separate offset-32 wrapper and explicit `entry_abi`
identity from kernel entry through registry, translator and frame. The caller
compiler owns live-value spills. Its initial packet is MINIMAL (RIP/RSP/RBP),
and the normal root result is COMPLETE with an independently checked outer
unlock continuation. The wrapper imports no thread GPR bundle and protects only
physical RBP; the lock-side C step calls it through an inline asm clobber
boundary. Every intermediate exit materializes FULL before existing C handling.
The continuation-retirement/ticket/owner protocol above still applies; only valid
packet fields and the compiler call contract differ. Detailed states and mixed
ABI rules live in [the register ABI](../JIT_REGISTER_ABI.md#10-普通-spin-的-caller-clobber-v1).

Within that lease, a batch reuses its resolved executable slot for the same
entry and SPIN backend. Resolution alone grants no admission. Ordinary roots
check OPEN, acquired NORMAL publication, pid/entry and the current code pointer
once in batch prepare; generic dispatch keeps its readiness check. Backend,
scope, image ABI and bind-time OPEN checks remain.
The cache dies with the batch and is neither a code-pointer cache nor an
immutable-code version mechanism. Before executing the current request, the
combiner prefetches its queued successor's actual register packet and frame hot
fields, plus the virtual SP/push slot and caller stack lines inside the logical waiter's task
stack. This precedes any completion or outer-release publication; it grants no
ownership and never follows successors after early outer release.

Diagnostic identities are append-only for the module session. A batch resolves
one slot for disable checks and events; each queued request retains the slot
returned by waiter entry for its matching exit. Only the identity is cached:
disable loads remain acquire operations and waiter counts remain live atomics.
The 128-byte diagnostic slot separates the addr/disable cache line from its
waiter-count line. Full-table/null-slot behavior still refuses accounting;
slots are not reclaimed before all callers drain. Complex callers without a
retained identity may still resolve by lock address.

The read-only module parameter `spin_prefetch` selects successor warming:
0 disables it, 1 retains the consumer-side lookup, and 2 (default) uses producer
hints. Other existing queue-return stack hints are unchanged in every mode.
Mode 2 prepares the packet pointer, bounded logical-stack SP, upward hint count
and full/complex flags before queue publication. A physical producer passes its inline packet;
a virtual producer passes the retained parent packet and always marks it FULL.
Thus mode 2 MINIMAL packets are inline: the aligned continuation and its asserted
layout put IP/SP/BP in the core frame line. The MINIMAL consumer issues three
frame/packet hints: the core line, the virtual-GPR backing line, and the line
containing regs_ref/GS/task/parent. The five backing slots remain active during
JIT execution even though clobber imports no incoming GPRs. No consumer-side
alignment test or packet read is needed. FULL/borrowed packet
hints keep their existing range. For a valid logical SP, mode 2 hints `SP-8`
and up to four upward addresses: `SP`, `SP+64`, `SP+128`, `SP+192`. The producer
clamps the count to addresses below the retained task's stack end; the consumer
does not rediscover that bound through task/frame/packet loads. The
`u8 prefetch_stack_lines` occupies existing node padding, adding no allocation
or cache line. This warms caller spills and nearby stack locals; it is not a
claim that every caller fits within that footprint. Mode 1 retains its original
SP and SP-8 stack hints. The current 128-byte node keeps links,
execution and hints in its first line; completed/locked occupy offsets 64/65
on a separate polling line. Type alignment and stride isolate all four slots,
including nested nodes. The consumer can issue
frame/register/stack hints using only node fields, before running the current
body, without loading the successor's frame, task or packet to discover them.

These immutable queue-interval hints are not another register snapshot or an
executable SP. They neither pin objects nor replace admission: continuation retirement, task/stack lifetime, source lease and owner/ACK rules remain necessary.
The node still becomes reusable independently of the request. Prepared addresses
must be overwritten for each new queued request, and no old hint may be followed
after wake/outer release. A missing/out-of-stack SP suppresses only stack hints.
Modes 0/1 skip producer hint preparation; values outside 0..2 fail module init.
Current layout-aware warming covers both request header lines; packet and
logical-stack hints remain within their retained objects. Notification semantics and wrapper
ABI do not change. Compare modes within one image to isolate the hint policy; compare
the retained old image separately to include node layout and option overhead.

Spin diagnostic events, maximum depth and overflow/invariant counters are
CPU-local, allocated once at module initialization with `alloc_percpu()` to
stay outside the fixed module per-CPU reservation. x86 `this_cpu` RMWs avoid
shared LOCK-prefixed updates; the local maximum uses cmpxchg so an interrupted
shallower recorder cannot overwrite a
deeper IRQ observation. Simple root completion increments only JIT_SUCCESS:
the same pinned combiner already recorded depth 1 for that slot, so checking
the monotonic maximum again would read a second diagnostic cache line without
changing it. Generic/complex success retains its depth update.
Drained shutdown sums all possible CPUs, including
offline CPUs. The separate `kd_spin batch` report records alternate entries and
consecutive WWJUMPs; these counts are also per-CPU until shutdown. Slot identity, the live waiter
count and JIT-disable latch remain shared. Reporting is not a live snapshot.

Ticket pools maintain a task-owned live bitmap: allocation finds a free bit,
and duplicate/lookup scans visit only occupied slots. Generation, phase, kind and
native borrow count share one atomic64 control word; remote get/put use a full-word
CAS without accessing owner metadata. The pinned owner publishes new slots,
ends them only with zero borrows and waits with acquire reads, not a metadata
spinlock. Borrow counts remain exact and protect frame lifetime after physical
ACK. The transitions and finite generation/borrow limits are defined in
[the ticket protocol](locking.md#42-acquisition-tickets-and-node-lifetime).
Source/provider references remain once per batch.

Independent owner ledgers/checkpoints also remain. The virtual producer copies
the parent's live lock-ledger prefix directly into the child's stable request
and appends the delegated lock before publishing the node. `kd_spin_jit_context`
is embedded in the stable request and holds only the requester and prepared
depth; it no longer needs a separate per-CPU allocation or a node-indexed
lifetime. Cancellation may detach `resume_target`, so the immutable producer
context remains available for unstarted readmission. After binding, the executor validates
those same child columns and publishes their live depth/outer index without a
second copy. Parent and child ledgers must stay independent while both owners
are live; the shared logical register packet does not replace owner state.

A queued virtual waiter caches its requester and acquire-loads that owner's
remote mailbox each iteration. An empty mailbox skips `kd_exec_remote_poll()`;
a nonempty mailbox still enters the existing validation/unlock/ACK handler.
This keeps ancestor unlocks progressing while the child executes. It cannot be
replaced with a completion-only PAUSE loop like the physical waiter. Storage
retirement is implemented as described above; remaining measured-cost work is
tracked in [shared request storage](../TODO.md#shared-request-storage).

The physical CPU scheduler is `kd_spin_cpu_state`: its lock ledger, current
logical CPU, node reservation depth and polling-stack pointer belong to the CPU.
Optional NUMA queue head/tail remain CPU state. `node_count` is not queue-node
identity and is not restored with a frame checkpoint: node reuse and frame
retirement have different boundaries. Nodes retain links, execution reference,
CPU/NUMA identity, scheduler RSP and cache-line-separated notifications; the
unused encoded-tail copy was removed. The default CPU state is 80 bytes (96
with NUMA), while nodes retain their 128-byte stride and notification offsets.

Nondelegating physical callers use these same preallocated MCS nodes, with
`execution == NULL` and a non-combinable marker. They need no stable JIT record
or frame; node reservation ends at queue-head acquisition/handoff, while the
physical hold continues until unlock. See [the shared native queue](locking.md#41-native-lock-and-private-queue).

The 88-byte `kd_combiner_state` preserves the lock ledger/depth, current logical
CPU and NUMA queue pointers. Former constant `prev_cs_cpu`, wrapper-RSP scratch
and IRQ mirror fields were removed from both CPU state and checkpoints. Plain
spin now also removes the continuation's `irq_flags` and leaves IRQ state unchanged. `kd_spin_batch` uses
`outer.released` directly for outer-lock reclaim, without a second boolean.
The legacy frame-push APIs no longer accept unused waiter/outgoing-RSP arguments.

Mutex keeps a separate `kd_mutex_cpu_state` and its own ownership protocol.
Ordinary ABI2 mutex roots borrow a single enclosing batch source lease and the
waiter's packet, while retaining an explicit physical-owner ledger. Their first
COMPLETE return uses checked mutex retirement before queue publication.
`mutex_backend && !complex_ready` identifies a pristine ABI2 batch root with
that explicit slot-0 ledger, its exact shadow pointer, release hook, live depths
and release state already initialized. Only unrelated continuation-IP,
logical-PID and control/native/remote routing discriminators remain inactive.
Manually constructed generic mutex frames, including the owner/ACK probe,
must initialize their routing/list state and mark `complex_ready=true` before
calling ledger or native-protocol helpers; zero does not identify a generic frame.
Ordinary completion checks the exact ledger, context owner, physical shadow
owner and original Linux mutex owner without reading those inactive bytes.

The generic dispatcher materializes mutex routing before its first validation,
covering both a pending wrapper exit and failed fast preparation. This separate
mutex helper preserves the borrowed-register union and release hook; the spin
promotion helper cannot substitute for it. An explicit entry refusal retains
the MINIMAL borrowed packet, while an actual FULL exit detaches the packet
before any C service, early outer release, native publication or final owner ACK.
A materialized frame never returns to the pristine representation. FULL
returns retain backend identity and enter the existing native/ACK path once. The batch lease ends after every frame/ACK has retired;
source closure still rejects new roots within the batch.

For this pristine ABI2 mutex root, batch preparation fills the wrapper transport
from the packet selected before admission. The existing MINIMAL ledger predicate,
source/publication checks, image identity and direct endpoint checks must all pass
before it fixes `complete=true` and the mutex ABI/unlock fields. Generic clobber
preparation remains responsible for other dispatches. This specialization changes
neither the two-word wrapper input nor completion, physical-owner or final-ACK checks.

The mutex batch push, preparation, completion and retirement helpers now use
the same compilation unit as the mutex combiner. Its private queue helpers
have mutex-specific names; public entries and all packet/frame layouts stay
unchanged. Stack-switch and restore functions retain their `noipa`/`noinline`
boundaries. The generic frame constructor and FULL/native dispatcher remain
available, including physical-owner checks and final-ACK retirement. This
compiler scope change does not merge spin/mutex state or change source leases,
publication ordering, batch limits or waiter policy.

Mutex reservations and active waiter balances are exact per-CPU integers. Both
updates occur with preemption disabled on the migration-pinned origin CPU;
a remote combiner never releases that node. Controlled drain checks each CPU's
active balance, reservation balance and node bitmap separately, so opposite
imbalances cannot cancel. Owner/task acquisition references, nested waits and
final ACKs retain their separate synchronization. Only shutdown diagnostics sum
these balances; `max_waiters_per_cpu` names the local maximum explicitly.

Its scheduling object's tail is an encoded `u32`, not a pointer. The immutable
`origin_mutex_addr` also supplies the protected shadow-map key, removing a
second address column. These changes leave physical-owner checks, waiter
accounting and owner ACKs intact. Register-reference representation, ledger
counters and role transitions remain separate possible work; none is folded
into hotlock statistics entries or recyclable nodes.

### 9.1.2 TCLock Spin Reference And State Boundaries

The source comparison uses TCLock revision
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef`, specifically its kernel
`rcuht/locks/komb.c` and `rcuht/lib/combiner.c`. TCLock executes original
critical-section instructions after switching physical RSP to a waiter's stack.
Its switch saves/restores six callee-saved GPRs and RSP, with return addresses
on the stack; the local reference enables WWJUMP between eligible waiters.
kdlock keeps physical RSP on the combiner task stack and represents the waiter's
stack through virtual RSP. Its independent shadow stack isolates physical waiter
polling; it does not replace wrapper entry/exit or execute the JIT body.

Sharing the logical register packet now also removes the wrapper's GPR backing
copy. Necessary CPU register loads/spills and independently live executor
checkpoints remain. Reserving R11 for the packet moves the branch budget to a
private stack slot; less boundary copying does not guarantee lower total cost.
Caller-clobber v1 initializes only RIP/RSP/RBP for a normal request; legacy
entries retain their saved-register contract. Plain spin does not load IRQ flags;
this does not add restoration of JIT live condition codes.
The canonical path/state table and source scope are in the
[register ABI comparison](../JIT_REGISTER_ABI.md#11-与-tclock-spinlock-的执行路径和状态保存对比).
The independent [TCLock backend](../../tclock_backend/README.md) now runs the native
stack-delegation path through the same spin hook. Its scoped runtime acceptance
and three-way results are in the [benchmark report](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260918-native-stack.md);
they do not validate arbitrary task/per-CPU or nested native critical sections.

### 9.2 A/B Execution

Spin B may enqueue a virtual request and resume remotely; mutex B is acquired
by the same A combiner. Both record the actual acquisition before consuming
the lock CALL. Inner unlock normally continues A, while final completion uses
the last required unlock return, including A-before-B execution.

### 9.3 Capacity And Refusal

Frame, logical held-lock, CPU-local shadow-held-lock, ticket and node pools have
independent limits. Capacity checks precede acquiring/publishing a new B.
A valid pre-acquisition PENDING resource failure can hand the original lock
CALL to the waiter. Already entered/acquired operations cannot use that path.

Spin's 32-slot physical-CPU ticket pool can return E2BIG before publishing B
or retaining a temporary preemption pin. The KD gate map has been removed;
there is no current gate-capacity ENOMEM branch and no Linux-lock fallback for
KD objects. A supported PENDING failure preserves the control CALL target,
stack and return IP for checked continuation; it does not replay the root.
Historical gate-pressure evidence belongs to its old protocol and is not
current acceptance. Current production fixtures are listed in
[tests](../../tests/README.md).

A virtual pre-entry refusal preserves the caller's full register packet and
queue connection. Already-progressed work cannot be recast as fresh native
entry. Exact node reservation and stack lifetimes persist through readmission,
child completion and native ACK; selected bounded tests are not arbitrary-depth
or arbitrary-schedule guarantees.

### 9.4 Out-Of-Order And Remote Completion

A logical unlock of A while B remains held is performed by A's real owner.
It drops A/S once, detaches the old batch and lets saved A successors progress.
B ownership is unchanged. The old combiner must reacquire A before running
its own original CS, without rereading a possibly reused old node.
Spin waits for full S availability and reuses its released ticket without
adding a new pin or switching back to a stale stack.

Remote child state is published as WAITING/NATIVE/DONE. Clear the child's
resume_target before release-publishing final DONE; do not touch the parent
after final publication. A parent with no remaining local locks still waits
for its child while keeping its frame alive.

NUMA deferred-list publication and nested-list isolation must preserve the
same ownership and completion rules. Native-aware waits must continue servicing
owner-side unlock requests, including ancestor release.
A zero-local-lock COMPLETE relay also retains a root-ticket borrow until pop.
The last physical unlock ACK cannot end the original thread's pin or reclaim
its packet while any executor remains. The SELFTEST observer now checks that
the logical task is alive at pop, its packet/context are preserved, and frame
validation rejects it after retirement. The earlier “frame outlives waiter TID”
schedule is superseded; its archives are historical evidence only.

### 9.5 Forward Native Continuation

For an ordinary CALL miss, keep current GPRs, callee RIP and virtual CALL RSP.
The original waiter enters that callee, returns natively and finishes the suffix
without reentering this JIT invocation. Memory writes and completed B sections
remain committed; there is no transaction rollback.

The combiner retains its acquired physical locks and pauses its own batch;
independent combiners can keep their separate native registrations active.
The waiter borrows protection, not physical ownership. Unlock requests return to
the physical owner and wait for ACK. The ACK resides on the waiter's native
stack. Spin physical ACKs do not drop executor borrows: cleanup and frame pop
must precede that drop. The final spin unlock waits for all executor borrows
before ending its origin pin; a mutex waiter has
already restored migration/preemption state before entering its native suffix.
Borrowing several remote frames does not add lexical lock-depth pins on the
waiter: the existing root origin pin persists through final retirement. This is
not full preemption-count/context reconstruction; the concrete contract and
mixed B/native-successor test are in [历史：usage 6.14](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/spin_protocols.md#614-两个独立-root-共享-b-combiner).
The owner must not reread a queue node after publishing its native wakeup, or
a stack-local unlock request after publishing that request's ACK. The owner's
live frame remains until its own completion/pop. A completion log is not the
ACK's linearization point.

Every allocated frame initializes an empty native routing head. Physical-LIFO
pop refuses both an outstanding `native_request` and a still-linked native
registration, even in ERROR/COMPLETE state; refusal preserves the output packet,
context storage and source lease. The owner must still finish the native wait
protocol before popping. This final guard does not send an ACK, unlink routing,
release physical locks, or make an arbitrary failed frame recoverable. The
[历史：retirement checks](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/spin_protocols.md#frame-回收门禁) separate direct bad-state
unit inputs from real owner/ACK schedules; no live use-after-free is claimed.

Acquisition phases are NONE/PENDING/ENTERED/ACQUIRED/COMPLETE. Validated PENDING
-ENOMEM/-E2BIG before acquisition/publication can restore the original lock
callee RIP/CALL RSP while retaining current GPRs and effects. The mutex stack
precheck can also hand off an unstarted CALL when the bounded window is too
short, without inventing an allocation error. A changed post-control window
instead uses the distinct STACK_CHANGED phase and exact already-consumed packet.
For a local spin post-acquisition EIO, `finish_acquired_spin_call()` validates
the unreleased top local lock record, current physical KD-word owner, original
lock target/token in the waiter stack and exact post-CALL RIP/RSP. Only this
checked boundary receives SPIN_NATIVE: B stays acquired and the waiter resumes
after the CALL. Remote publication, missing records or a bad packet remain
errors. See [历史：flow and tests](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/spin_protocols.md#611-spin-获取后的受检续跑).
Native registration independently checks these states, ordinary NONE and
validated spin remote COMPLETE relay before borrowing/publishing/accounting.
A still-held A does not make arbitrary later-phase failures recoverable; the
checked local boundaries are not general ACQUIRED/COMPLETE recovery permission.

If pending B is first acquired by the native waiter, B really belongs to that
waiter; earlier combiner-owned locks still use notifications. After A release,
continuation requires a consistent remaining ledger. Unhandled IJ/budget/fault
and later-phase errors fail-stop, not entry retry.

The existing [历史：early-A dependency workload](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/spin_protocols.md#610-提前释放-a-的原生依赖)
checks a native C owner needing the released A while B remains borrowed, then
seven owner ACKs after real ledger exhaustion. It is selected separately from
ordinary held-B register continuation; neither contract subsumes the other.

Borrowed mutex execution does not satisfy mutex.owner == current on the waiter.
Recursive acquisition, owner-sensitive code, lockdep or task-local locking
effects remain outside the supported subset; no owner-bit assignment fixes
those requirements.

### 9.6 BCD Comparison And Continuation Scope

The local BCD source inspection used revision
`dbde52c57a961a5cdb87c0212f9b032947d2df13`, not a BCD runtime test.
Its active daemon/asm/wrapper.S preserves supported registers in the waiter's
syscall pt_regs. Ordinary CALL miss retains the pushed original return address
and callee RIP; the syscall-return path resumes the updated user context.
Learning a missing callee is for future work, not an entry restart.

kdlock adopts forward progress but cannot reuse syscall return as its kernel
lock-ownership protocol. It additionally needs frames, phase validation,
physical-owner retention and native-unlock rendezvous. The old entry-register
retry and popped CALL frame were incompatible with this purpose.

Neither inspected BCD code nor kdlock's current wrapper preserves arbitrary
live arithmetic flags. Saving GPRs alone is not proof of arbitrary-fault
recovery. Supported outcomes are: native entry for unstarted work, current
callee continuation for ordinary CALL miss, validated pending-lock acquisition,
successful post-unlock return, or fail-stop for unsupported progressed state.
