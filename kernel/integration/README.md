# Direct task anchors for the source-rebuilt lane

C02 selects two direct `task_struct` pointers: `kd_own_state` to that task's one
canonical core and `kd_active_state` to an active borrowed origin. The latter is
NULL for the ordinary own/native path, which uses `kd_own_state`. Both fields
are pointers only; no packet, duplicate source state, registry, allocator,
capacity or control-stack placement is introduced.

The repository does not contain the exact selected Linux 7.0 source tree.
[task_struct.patch](task_struct.patch) is a context-anchored integration template,
with nominal hunk positions, not an applied or source-revision-verified patch.
It has not been applied, built or executed. Rebase its anchors against the exact
source/configuration before any implementation validation. Keep architecture
first-member requirements intact: the fields follow
`randomized_struct_fields_start`, not the beginning of `task_struct`.

The task copy path must clear both copied pointers immediately after successful
`dup_task_struct`, before publishing the child or any child cleanup that reads
the fields. A shallow task copy did not acquire a reference to the parent's
core; reset never modifies or frees that core. The static initial task's omitted
pointer fields are zero initialized. Do not reset either field on a live task.

[kernel/task_state.c](../task_state.c) implements the current-task anchor layer.
The caller supplies a fresh canonical core and initialized native binding;
attach initializes that same core and publishes its pointer. It captures no
registers, chooses no allocator and clears no packet. An unattached task has no
core: lookup returns NULL rather than allocate or substitute another task's
state.

Borrowed entry validates the retained current JIT binding for a foreign origin,
saves only the prior active pointer in caller-owned small scope control, and
publishes the borrowed pointer. Leave restores that pointer after the bridge has
materialized/stopped or transferred the entered source. It neither restores an
old packet nor grants execution authority. Serial scopes are strict LIFO;
same-state nesting cannot detect every out-of-order close with only these two
fields. Scope storage/lifetime remains caller supplied and selects no C05
control-stack policy. Callback/entry integration must retain each old binding
and MCS result user through its actual last binding access.

Before task exit releases the original stack, or before own-core storage is
reused, source admission must close and every queued/executing/bound source,
grant, code, return, notification and borrowed-pointer user must drain. The
source integration must then call `kd_task_state_detach` on the origin task with
its retained exact current native binding. Detach rejects an active borrowed
anchor, another origin, any grant or pending image exit, or any operation
other than IDLE/RESUMABLE.
Its acquire-before-read binding check and pointer removal do not infer all
escaped last users; the caller provides that complete proof. -EBUSY is not
permission to continue exit or free the core/stack.

Detach does not free storage or release providers. Actual allocation/free,
source-admission closure, exit drain scheduling, build wiring and any exact
kernel exit hook remain integration work; no generic module callback or default
waiting policy is selected here. The original task, its stack, owner/control
containing allocations and callback code keep their separate actual last-user
contracts. Stable mutex-object lifetime through physical release does not end
those longer obligations.
