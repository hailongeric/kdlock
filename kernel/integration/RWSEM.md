# Generic Linux rwsem binding

This source lane extends the source-rebuilt Linux 7.0 x86_64, non-PREEMPT_RT
primitive. It has no build or execution receipt yet. The earlier private reader
fixtures remain mechanism evidence; they do not validate these new Linux APIs
or a real userspace workload.

## One selected object and one gate

The exact target installer adds an optional `kd_binding` pointer to Linux's
`struct rw_semaphore`, initialized to NULL in static and dynamic initializers.
An unselected object follows its original Linux implementation. A selected
object routes every ordinary, callable, constructor, signalable, try, query and
nonowner API to the same `kd_rw` reader gate and MCS writer queue. Native count,
owner and wait-list fields never provide parallel exclusion for that object.
MM bodies, mmap trace calls, sequence counters and surrounding data structures
retain their native ordering and behavior.

The caller cold-initializes a `kd_rwsem`, a `kd_rw_native_pool` and an explicit
array of native records, then calls `kd_linux_rwsem_bind`. The binding, lock,
pool, records and callback code survive all API, queue, grant and final object
accesses. Binding is immutable while the object is reachable. Bind and unbind
require caller-established exclusion of **all** entry, waiters, held grants,
observers and final accesses across the transition. Merely seeing an unlocked
count, no contention or an idle pool cannot establish this exclusion. Busy
checks supplement that proof; they do not supply it. No automatic allocation,
selection, global task registry or mmap-specific lock protocol is introduced.
The actual Linux owner-query symbols also have GPL exports in the rebuilt
configuration, so module callers observe the same generic dispatch.
Selected bindings currently refuse lockdep, DEBUG_LOCK_ALLOC and DEBUG_RWSEMS;
these configurations have no supported bound-object lane.

Native records contain physical control and exact credits, without an S_W or
register packet. The user-provided finite capacity guarantees an available
record for every supported need, including held credits, waiting calls and
canceled writers whose MCS membership still lives after `-EINTR`. Capacity is
not a nesting-depth bound or a deployment default. Exhaustion remains a
support limitation; there is no storage wait, recovery/fallback or new special
assertion. Owned native grants on an already attached task also link into its
exact `native_grants` list; attach precedes its first selected owned grant.
This list retains the root through release and blocks detach/exit while live.
Nonowner credits remain object-owned and can outlive their acquiring task.

## API and continuation behavior

Ordinary prepared source macros can use the existing private clobber entries
when `source_calls` is explicitly selected and the original task is eligible.
Active nested requests still obtain W's canonical state from their direct
`node->state`. The existing task-owned auxiliary stack, original UB-derived JIT,
GS lowering, recursive delegation and exact current-state handback are retained.
The entry helpers require original-task context; reached helper calls and
normal Linux callable symbols are permanent SPECIAL frontiers. They return to
W before the operation, with its exact CALL/RET state and no replay. They are
never reclassified as ordinary code by learning or mistaken for private typed
clobber entries simply because their names or DI argument look similar.

Signalable read/write and try APIs initially use their normal C result ABI and
execute locally on the same KD gate. Successful signalable acquisition returns
0; interrupted acquisition returns `-EINTR` without a grant. Actual readiness
wins before pending signal cancellation. Try returns 1 or 0 and publishes no
queue membership on failure. An interrupted queued writer can return before
its predecessor releases; its persistent queue user remains until exact turn
selection or predecessor removal finishes. No source packet is allocated for
these calls and no unused typed result-return extension is added.

A shared active-reader ledger orders actual managed and native credits. Owned
`up_read` chooses the most recent exact credit for that original task across
both routes. Nonowner acquisition/release uses separate real credits, choosing
an actual eligible credit under the same guard, with no source-task dependency.
Queries report physical gate state and speculative owner identity; they never
create a hold or authorize release. A physical-task native grant also prevents
starting unrelated inner source batching before that task's new local grant,
preserving the existing extra-cycle restriction.

Native downgrade installs a real read credit before ending writer admission;
matching read release consumes that credit once. The private JIT-consumed
selected downgrade is unchanged: it retains the exact physical WRITE grant
through its logical read tail and matching typed UP_READ, including exact
native suffix handback. A native syscall downgrade observation alone cannot
prove that the JIT-consumed retained-write path executed.

## Directly affected validation

The compatibility fixture uses real Linux lock APIs on a private selected
object. The separate [userspace mmap/munmap workload](../../tests/kernel/mmap_api/README.md)
executes actual system calls, mapping effects, unmapping and fresh exact-address
reuse. Its control interface performs binding/routing/lifetime operations only;
it calls no MM test body. Initial real-MM selection uses `source_calls=false`,
so it needs no dummy source provider or task state and makes no MM JIT claim.
All compilation, project parsing and execution run only in the VM after source
review, fresh idle/space and exact recovery/identity checks. Skips, timeouts,
compile failures and unrun stages are not passes. Real syscall completion, KD
physical grants, native downgrade, JIT entry, returned generated body and
performance remain separate evidence.
