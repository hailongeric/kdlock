# External task registry for the source-rebuilt lane

C02 selects an external per-task registry with explicit lookup and lifetime
management. [task_state.h](../task_state.h) defines caller-supplied persistent
`kd_task_anchor` storage: one hash link, retained task key, own-core pointer and
active borrowed-core pointer. It contains no packet. `task_struct` is unchanged;
there is no task-copy reset hook or direct-field integration patch. A new child
has no registered entry and cannot acquire its parent's core by shallow copy.
The rejected direct-field source remains in Git history.

[task_state.c](../task_state.c) implements a private task-pointer hash index with
short independently locked buckets. Its 64 buckets are an internal mapping
choice, not an anchor capacity or a scaling result. Bucket guards protect only
registry/anchor metadata, bucket-list traversal and fixed-size attach/detach
checks; no source body, wait, allocation, provider callback or physical unlock
runs under them. Bucket traversal is linear in that bucket's retained entries;
no lookup-latency bound is claimed. Calls
are current-task-only in ordinary task context, without IRQ/NMI or concurrent
reentry. No arbitrary-task lookup, global family lock, allocator, default
capacity or C05 control-stack placement is introduced.

The caller initializes a private anchor with `kd_task_anchor_init`, supplies a
fresh own core and initialized native binding, then calls
`kd_task_state_attach(anchor, core, origin_gs, native_binding)` on that task.
Attach initializes that same canonical core, takes `get_task_struct(current)`
and publishes the exact anchor under its bucket guard. It captures no source
registers and clears no packet. An unattached task gets NULL from lookup rather
than allocation or substitution of another task's state. A registered anchor
must not be copied, reinitialized, concurrently reused or shared with a second
task; anchor/core backing remains caller owned and retained.

`kd_task_state_own` and `kd_task_state_active` perform explicit current-task
lookup under the bucket guard. Active returns the borrowed pointer when one is
present and own otherwise. These functions read anchor pointers, never the own
packet while borrowed execution is active. Bucket locking orders publication;
lookup does not acquire another core/storage reference or execution right.
The returned own pointer stays valid because this task's registration and
caller-owned backing remain live through its last use. The same current task
cannot detach itself concurrently under the task-only contract. Any pointer
that escapes that serial scope requires its caller's existing retained user,
and every such user must drain before detach. A borrowed core additionally
stays valid through the enclosing scope and its exact runtime users.

Borrow entry validates the retained current JIT binding for a foreign origin,
looks up the current registered anchor, and saves its exact anchor and previous
borrowed pointer in small caller-owned scope storage. Leave verifies that same
registered anchor, restores only its previous pointer after source has stopped
or transferred, and closes the scope. It does not restore an old packet or
binding authority. Serial scopes are strict LIFO; same-state nesting cannot
detect every out-of-order close from pointer identity alone. The scope and both
cores remain retained through leave. No registry reference replaces existing
MCS result/binding/grant users, and the last old binding access still precedes
its exact user drop.

Before task exit releases its stack, or before anchor/core reuse, close source
admission and drain every queued/executing/bound source, grant, code, return,
notification, lookup, binding and borrowed-scope user. Then call
`kd_task_state_detach` on the origin task with the retained exact current native
binding. Detach first rejects an active borrowed pointer without inspecting the
own mutable source packet. It then checks exact origin/native ownership,
acquires before reading binding fields, and rejects any grant, pending image
exit or operation other than IDLE/RESUMABLE. It revokes the canonical binding,
removes the exact anchor, completes its final anchor access and drops the
registry's retained task reference outside the guard. It never dereferences the
anchor or state after that drop.

Those checks do not infer all escaped last users; the caller supplies the full
drain proof before detach. A held task reference retains task identity, not an
exiting task's kernel stack or all caller-owned allocations. Task exit/stack
release therefore waits for successful detach AND the complete last-user proof.
-EBUSY is not permission to continue exit or free storage. Detach does not free
storage, release providers or choose a drain-wait policy. Allocation/free,
source-admission closure, exit drain scheduling, exact kernel lifecycle hooks
and build wiring remain integration work. Owner/control-containing allocations,
callback code and source stacks keep their separate actual last-user duties;
stable mutex-object lifetime through physical release does not end them.

This layer has source review only. No import, compile, build, behavioral test or
kernel execution is claimed.
