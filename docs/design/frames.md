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
execution chain. Spin frames live in producer-owned request storage; mutex
frames retain the fixed per-CPU array. Bind changes the physical parent, depth
and batch association without copying the request frame. Pop is the common
unbind/retirement check: physical LIFO ownership, terminal state, remote
requests and native routing/ACKs must be clear. It does not reclaim a spin
request or copy its packet. Whole-context scans remain SELFTEST diagnostics.
`jit_lock_depth` bounds the live lock prefix; inactive arrays are not cleared.

A physical spin root with one lock starts with `spin_simple`. Its first wrapper
return completes directly only for CALL_MISS at the exact spin-unlock target
with the matching outer lock. Other dispatch exits capture the independent
combiner checkpoint before servicing controls/hostcalls or publishing native
work. Remote and physically nested frames capture that checkpoint at entry.
These are distinct physical executor states, not copies of logical registers.

### 9.1.1 Reuse-Before-Copy Contract

**2026-09-17: implemented for the spin request path; JIT remains the backend.**
Reusable register/frame state has one authoritative object shared by waiter and
combiner. Initial CPU capture and final CPU restoration are necessary boundaries;
node-to-frame, frame-to-node and final software restoration snapshots are absent
from this spin path. Mutex and the legacy frame-push API retain their own packet
handling. This is not a replacement of every state snapshot in the repository.

Each CPU preallocates `KD_EXEC_MAX_NESTING + MAX_NODES` (12) execution records.
A record contains a 648-byte frame, optional logical-packet owner, user count and
request-owned return/routing metadata (768 bytes, aligned to 64). The 5208-byte execution context retains its legacy array
and adds one stack-top pointer. This pool is independent of the four recyclable
queue nodes and costs 9216 bytes per possible CPU, allocated at module init.
There is no allocation or global lock in request reservation. Only pinned task
producers allocate on their own CPU; other CPUs can release users. An acquire
read of users==0 precedes reuse. Exhaustion refuses delegation and preserves the
existing native/queue fallback; it never overwrites a live request.

The implemented protocol is:

1. The producer reserves a record with one queue/waiter user, decodes the hook
   registers directly into `request.frame.regs`, and initializes readable frame
   state. The 128-byte, 64-byte-aligned node carries one execution reference plus queue linkage/notification
   and scheduler stack metadata. Registers, task/GS, origin and native/retry
   state belong to the request. No whole-frame memset runs.
2. Release queue publication transfers access to the combiner. It binds that
   frame by pointer into its physical chain and supplies actual lock-owner and
   batch metadata. The JIT wrapper reads/writes the same packet throughout
   simple, control and native execution; no complex-path register copy is needed.
3. The combiner holds L across the bounded batch. One source/provider lease is
   acquired before the batch and released after its final handoff or outer-lock
   reclaim. Individual spin binds borrow that lease and still check admission
   is open. Native/remote waits and frame retirement finish before batch release.
   The status ABI field named `frames` now counts these leases plus legacy frame
   leases, not every spin frame inside a batch.
4. Normal completion unbinds the frame before release-publishing completed/locked.
   The physical waiter restores the record's valid state: RIP/RSP/RBP for a
   caller-clobber MINIMAL/COMPLETE packet, or GPRs for FULL/legacy. Its final release follows every packet load, then flags and the return are
   restored. A pristine single-lock root has one user and uses a release store;
   native/remote lifetimes retain the atomic decrement.
   No node/request access occurs after the corresponding lifetime ends. IRQ-off
   entry stays IRQ-off; IRQ-on entry is restored only at the final boundary.
5. Native handoff first adds an owner user, then publishes continuation/wake.
   The queue/waiter user and owner user may retire independently. The owner
   releases its user only after native ACK, cleanup and frame pop, so a waiter
   can finish or exit before the owner without invalidating its frame.
6. A virtual child has distinct owner/control state but aliases the same logical
   root packet through `regs_ref`. It holds one root-record reference until its
   own final user ends. Ancestors use saved scalar CALL return/stack and
   `delegated_lock_addr` facts, never changing packet fields as frozen scope.
   Suspended owners only service their own lock mailboxes until handoff returns.

The native owner's extra user and remote packet dependency are branch-specific;
ordinary wrapper entry/exit adds no request reference. A queue wake or node reuse
is not permission to recycle execution storage. The record's users count, source
lease, ticket/native references and physical lock ownership serve different lifetimes.

The ordinary frame state is a 72-byte header followed by the shared packet and
preallocated cold storage. `complex_ready` gates the eight-lock ledger, remote/
native discriminators and combiner snapshot. Prepare/bind/validate/complete/pop
of a pristine single-lock root do not initialize or inspect that cold storage.
Request flags and users now precede the frame; entry ABI and packet state
precede its register packet. These ordinary admission fields fit in the first
two aligned request cache lines. Each pool record has its own cache-line
boundaries; no second mutable state cache is introduced. The packet starts at
request offset 96; restore/wait assembly uses compiler-derived offsets.
The first non-final wrapper exit materializes a one-lock ledger in place before
control/hostcall/native handling. It never copies the register packet.

`kd_spin_batch_run` keeps one physical combiner C frame across the complete
batch, including mixed caller ABIs. Its inline assembly calls expose all GPR
clobbers except RSP/RBP to the compiler. The legacy KDWB001 adapter protects only
RBP, which that wrapper does not restore; KDWC001 restores RBP itself. There is
no outer assembly register group save or per-waiter callback return/reentry.
This follows TCLock's retained combiner continuation while keeping the JIT's
physical scratch frame separate from the logical waiter stack. Admission,
completion/unbind/publication and successor selection remain in the lock loop.
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
The ordinary request/reference/owner protocol above is unchanged; only valid
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
fields, plus the virtual SP/push slot only inside the logical waiter's task
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
Mode 2 prepares the packet pointer, bounded logical-stack SP and full/complex
flags before queue publication. A physical producer passes its inline packet;
a virtual producer passes the retained parent packet. The current 128-byte node keeps links,
execution and hints in its first line; completed/locked occupy offsets 64/65
on a separate polling line. Type alignment and stride isolate all four slots,
including nested nodes. The consumer can issue
frame/register/stack hints using only node fields, before running the current
body, without loading the successor's frame, task or packet to discover them.

These immutable queue-interval hints are not another register snapshot or an
executable SP. They neither pin objects nor replace admission: existing request
users, task/stack lifetime, source lease and owner/ACK rules remain necessary.
The node still becomes reusable independently of the request. Prepared addresses
must be overwritten for each new queued request, and no old hint may be followed
after wake/outer release. A missing/out-of-stack SP suppresses only stack hints.
Modes 0/1 skip producer hint preparation; values outside 0..2 fail module init.
Current layout-aware warming covers both request header lines; packet and
logical-stack hints still use the same bounds. Notification semantics and wrapper
ABI do not change. Compare modes within one image to isolate the hint policy; compare
the retained old image separately to include node layout and option overhead.

Spin diagnostic events, maximum depth and overflow/invariant counters are
CPU-local, allocated once at module initialization with `alloc_percpu()` to
stay outside the fixed module per-CPU reservation. x86 `this_cpu` RMWs avoid
shared LOCK-prefixed updates; the local maximum uses cmpxchg so an interrupted
shallower recorder cannot overwrite a
deeper IRQ observation. Drained shutdown sums all possible CPUs, including
offline CPUs. The separate `kd_spin batch` report records alternate entries and
consecutive WWJUMPs; these counts are also per-CPU until shutdown. Slot identity, the live waiter
count and JIT-disable latch remain shared. Reporting is not a live snapshot.

Ticket pools maintain a task-owned live bitmap: allocation finds a free bit,
and duplicate/lookup scans visit only occupied slots. Generation/native-reference
state mutations retain `entry.guard`; remote readers can race retirement, so
this guard is not interchangeable with a diagnostic counter. Source/provider
references remain once per batch, and genuinely shared request users retain RMW.

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
replaced with a completion-only PAUSE loop like the physical waiter. Remaining
work is tracked in [shared request storage](../TODO.md#shared-request-storage).

The physical CPU scheduler is `kd_spin_cpu_state`: its lock ledger, current
logical CPU, node reservation depth and polling-stack pointer belong to the CPU.
Optional NUMA queue head/tail remain CPU state. `node_count` is not queue-node
identity and is not restored with a frame checkpoint: node reuse and frame
retirement have different boundaries. Nodes retain links, execution reference,
CPU/NUMA identity, scheduler RSP and cache-line-separated notifications; the
unused encoded-tail copy was removed. The default CPU state is 80 bytes (96
with NUMA), while nodes retain their 128-byte stride and notification offsets.

The 88-byte `kd_combiner_state` preserves the lock ledger/depth, current logical
CPU and NUMA queue pointers. Former constant `prev_cs_cpu`, wrapper-RSP scratch
and IRQ mirror fields were removed from both CPU state and checkpoints. Actual
IRQ restoration still uses the request's `irq_flags`. `kd_spin_batch` uses
`outer.released` directly for outer-lock reclaim, without a second boolean.
The legacy frame-push APIs no longer accept unused waiter/outgoing-RSP arguments.

Mutex keeps a separate `kd_mutex_cpu_state` and its own ownership protocol.
Its scheduling object's tail is an encoded `u32`, not a pointer. The immutable
`origin_mutex_addr` also supplies the protected shadow-map key, removing a
second address column. These changes leave physical-owner checks, waiter
accounting and owner ACKs intact. Register-reference representation, ledger
counters and role transitions remain separate possible work; none is folded
into hotlock candidates or recyclable nodes.

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
entries retain their saved-register contract. Restoring the physical waiter's
saved IRQ flags does not restore JIT live condition codes.
The canonical path/state table and source scope are in the
[register ABI comparison](../JIT_REGISTER_ABI.md#11-与-tclock-spinlock-的执行路径和状态保存对比).
The independent [TCLock backend](../../tclock_backend/README.md) now runs the native
stack-delegation path through the same spin hook. Its scoped runtime acceptance
and three-way results are in the [benchmark report](../../bench/tclock_compare/results/20260918-native-stack.md);
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
A zero-local-lock COMPLETE relay propagates the register packet only: no
extra ACK, borrowed reference or unpin. The last real lock ACK ends the origin
waiter's obligation. Deferred observation must not itself change queue state.

A no-lock ancestor may finish after the waiter's final ACK and normal task
exit. Its completion/pop must not dereference the old logical task, queue slot
or waiter stack; diagnostics use the PID cached while the waiter was blocked.
The bounded live schedule is maintained in
[历史：usage 6.9](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/spin_protocols.md#69-无锁祖先与-waiter-退出). It observes TID detachment,
not completed task-memory reclamation or arbitrary request cancellation.

The same terminal rule applies to an owned remote B after its native ACK.
Mode 8's mixed phase pauses at B's validated pop, while A0 finishes its own
ACK and the original waiter exits; only then may that same B combiner execute
the next independent root. This is a SELFTEST schedule, not a production
all-owner/exit barrier. It holds a PID identity, not a task ref, and keeps the
real source-frame lease through pop. Waiting before B publishes its ACK would
block the very exit being observed. The [历史：shared-B flow](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/spin_protocols.md#614-两个独立-root-共享-b-combiner)
distinguishes the full software-frame comparison from live register/flags or
completed task-memory reclamation evidence.

### 9.5 Forward Native Continuation

For an ordinary CALL miss, keep current GPRs, callee RIP and virtual CALL RSP.
The original waiter enters that callee, returns natively and finishes the suffix
without reentering this JIT invocation. Memory writes and completed B sections
remain committed; there is no transaction rollback.

The combiner retains its acquired physical locks and pauses its own batch;
independent combiners can keep their separate native registrations active.
The waiter borrows protection, not physical ownership. Unlock requests return to
the physical owner and wait for ACK. The ACK resides on the waiter's native
stack; the executor drops borrow references before release-publishing done.
The spin waiter ends its origin pin only on the last ACK; a mutex waiter has
already restored migration/preemption state before entering its native suffix.
Borrowing several remote frames does not add lexical lock-depth pins on the
waiter: the existing root origin pin persists through the final ACK. This is
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
