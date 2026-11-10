# Task-owned root and auxiliary context

Every active borrowed or nested request uses its current MCS call/node's direct
`node->state` pointer to the original canonical S_W. A nested request retains
that same pointer. The dispatcher passes its current call and parent role
explicitly; changing the physical executor never replaces S_W with that task's
own core. No external registry, borrowed-state task pointer or borrowed-pointer
scope is part of this design.

Native root entry precedes the first MCS node, so it still needs stable own-core
and auxiliary-control backing. [task_state.h](../task_state.h) defines one
caller-supplied `kd_task_root_context` header containing exactly one own
`kd_thread_state`, its initial native endpoint, retained owner task and explicit
auxiliary low/high/current values and one exact prepared-entry reservation. The source-rebuilt task stores one pointer,
`kd_root_context`, to this stable header. That root/auxiliary lookup does not
select the state used for borrowed execution. [task_struct.patch](task_struct.patch)
is an unapplied context template because the exact selected Linux 7.0 tree is
absent here. It makes no application/build or revision-match claim.

The task-owned auxiliary cursor has the role of TCLock's
`current->komb_stack_curr_ptr`: retain the physical task's waiting and control
frames on its own stack, with serial caller-managed reservation/restoration.
Here the cursor and bounds live in the one root header. The original UB-derived
JIT keeps its physical wrapper/control stack separate from the original W's
virtual source SP; no TCLock native waiter-stack body execution or context-switch
engine is imported. The archived source patterns are design inputs, not current
execution evidence. Restoring a saved cursor cannot reclaim an escaped owner,
request, binding or return control before its actual last user.

The caller initializes private header storage with `kd_task_root_context_init`
and provides the writable auxiliary range `[aux_low, aux_high)` and initial
cursor to `kd_task_root_attach`. The range must be disjoint from the stable
header/core; attach checks those intervals and cursor containment. The caller
also proves disjointness from each lent source stack, usable stack alignment,
room for actual control frames, sleepable context and all required source/native
entry resources. No allocator, byte capacity, recursion limit or default stack
size is selected here, and interval checks do not prove available execution
space. The aux_entry field names the single prepared native wait/control entry
occupying this cursor; it is not an active borrowed-state pointer. Native
preflight reserves it before the prefix, and only the exact entry may release
it after its final auxiliary-frame/descriptor access, immediately before the
exact native jump without source reentry in between. Nested JIT control uses
that same physical auxiliary C stack and explicit node->state. A second native
prefix cannot reuse the cursor while this reservation remains live. Actual
reserve/switch/restore integration remains separate.

Attach initializes the sole own core and its initial native endpoint, takes
`get_task_struct(current)` and release-publishes the single task pointer. It
captures no source registers and clears no packet. Later handbacks use fresh
caller-reserved exact native bindings, not a reinitialized initial endpoint
while old observers remain. Header/core/auxiliary storage must not be shared
with a second task or reused while any retained user survives. Metadata writes
are serial current-task operations in ordinary task context, without IRQ/NMI
or concurrent reentry.

`kd_task_root_context_current` is explicit root/auxiliary lookup before the first
request and during native preflight. `kd_task_state_own` only derives that
header's embedded core address for capture/original-W checks; it reads no own
packet during borrowed work and grants no execution permission. Lookup creates
no new storage reference. The current-task lifecycle and caller-owned backing
retain its result through the caller's last use; any escaped pointer needs its
own retained user and must drain before detach. Generated source-operation
handling instead receives the current MCS node explicitly. Its origin GS/task
inputs still come from the same node's S_W, independent of the physical task's
own root context.

The copied task field owns no parent-context reference. Clear the child's one
alias immediately after successful `dup_task_struct`, before child publication
or cleanup can consume it; never modify the parent's header/core. A static
initial task's omitted pointer field is zero initialized. Constructor reset is
not permission to clear a live task. The template preserves architecture first
member requirements by placing the field after `randomized_struct_fields_start`.

Before task exit or header/core/auxiliary reuse, close source admission and drain
all source, queue, owner, grant, code, notification, lookup and binding users,
including suspended or abandoned auxiliary frames and their exact return users.
Do not call detach during borrowed execution or from a retained auxiliary frame.
A restored/idle cursor cannot prove that drain. `kd_task_root_detach` requires
the same current origin and exact retained native endpoint, acquired before
binding-field reads, no grants or pending image exit and an IDLE/RESUMABLE
operation, and rejects a live aux_entry before reading the own state. It then revokes the binding and task pointer, completes its final
header access and drops the task reference without later header/core reads.
The structural checks do not establish all escaped last users; the caller must
provide the complete proof before this function reads the own state.

A task reference retains task identity, not an exiting kernel stack or arbitrary
caller allocation. Stack release and storage reuse therefore wait for successful
detach AND the full last-user proof. -EBUSY is not permission to exit/free.
Allocation/free, admission closure, drain scheduling, exact lifecycle/build
hooks and actual auxiliary admission/reservation remain integration work.
Stable mutex-object lifetime through physical release does not end the longer
owner/control, stack, source/code and callback obligations.

This layer has source review only. No compile, assembly, behavioral test, kernel
execution or whole-lane acceptance is claimed. The superseded two-field source
and rejected external-registry implementation remain separate Git archives;
neither is selected by this template.
