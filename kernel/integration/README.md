# Task-owned root, request storage and auxiliary entry

Every active borrowed or nested request uses its explicit MCS call/node's
`node->state` pointer to original W's one canonical S_W. A nested request keeps
that same pointer. The dispatcher passes its current call and parent role;
changing physical executor never substitutes that task's own core. No external
registry or active-borrowed-state task field participates.

Before the first node exists, native entry needs stable own-core and control
backing. [task_state.h](../task_state.h) defines one caller-owned
`kd_task_root_context` header. The source-rebuilt task stores one pointer,
`kd_root_context`, to it. The header contains the sole own core, its initial
native endpoint, task reference, auxiliary bounds/cursor and exact prepared-entry
reservation. Its owner-progress controller records the physical task's retained
batch duties. `mutex_resources` and `mutex_control_bytes` configure that task's
own native entry; they do not identify an active borrowed S_W.

[task_struct.patch](task_struct.patch) is an unapplied context template. The exact
selected Linux 7.0 source is absent here, so it supplies no exact-tree application,
build or runtime evidence. It clears the copied child's pointer after successful
`dup_task_struct`, before publication or cleanup can use it. That copied alias
owns no parent-context reference. It must never clear a live task's header. A
static initial task's omitted pointer is zero initialized. Actual task allocation,
constructor/exit hooks and source-built kernel integration remain work.

## Private setup before ordinary source admission

The caller provisions the header, one request pool and its slot array, an equally
sized episode-frame array, writable auxiliary stack, immutable episode
configuration and all source/code/object backing. Storage extents are explicit,
valid and disjoint as required; none is allocated at each lock call. Close source
admission until every private setup step succeeds:

1. Initialize the private header with `kd_task_root_context_init`.
2. Call `kd_task_root_attach` with the original GS input, auxiliary low/high/current
   values, pool, slots and explicit nonzero capacity. It initializes the sole core,
   pool and initial native endpoint, retains current and publishes the task anchor.
3. Initialize episode resources with `kd_episode_resources_init`, supplying the
   same pool and capacity, frame array, image slot, source-stack word operations,
   exact operation resolver, explicit proxy limit and synchronous reached-result
   reporter. The configuration and callback code survive every actual user.
4. Bind the resources and explicit complete control-stack requirement through
   `kd_mutex_bind_current` before using the ordinary source pair.

[task_setup.h](../task_setup.h) composes those private steps through
`kd_task_setup_current`. It copies the small call-only inputs before output
initialization, validates known retained object/array extents, alignment,
overflow and source/auxiliary disjointness, then performs attach/resources/bind.
An already attached current task is refused before initialization. Later failure
attempts exact unused initial-native detach; an unwind error keeps all attached
backing retained for explicit resolution. Backing stays caller-owned.
Opaque context/code extents and actual auxiliary context compatibility remain
caller proofs. `kd_task_teardown_current` composes one native progress pass with
exact detach, including when the current endpoint keeps pending true. Neither
helper allocates or supplies a global fork/exit policy.

The supported workload guarantees that a persistent record is available whenever
it needs one. The pool is finite: `pool->capacity` and `resources->capacity` are
the actual supplied count, and must cover simultaneously nested requests plus
all still-retained physical-owner/release, grant, control, return, notification,
image/binding and current-native-endpoint records. Depth alone is insufficient.
No deployment count is configured in this source tree. This assumption is not
proof that any particular count suffices or that the pool is unbounded. Node
exhaustion is a documentation-only support limitation; it selects no handler,
recovery path, temporary waiter or separate local MCS implementation.

Normal local and proxy winners use the same persistent MCS request protocol.
Every nested physical executor reserves from original W's pool through the
explicit frame/node relationship. A record is reused only after actual request
retirement and all independent observers finish. The pool's exact user/parent
memberships and final current-endpoint comparison retain those duties; queue
removal, a result, an idle auxiliary cursor or a raw claim identity alone does
not permit reuse. A current native endpoint can legitimately keep an otherwise
finished slot occupied until the next exact transfer or final detach.

## Native entry and borrowed execution

[The ordinary source macros](../../include/kd_mutex_api.h) emit distinct lock and
unlock operation CALL targets. Their compiler clobber contract supplies object
DI, pre-CALL source SP, post-CALL IP and BP; other source GPRs are not guessed.
[The native bootstrap](../../include/mutex_api.S) preserves those four scalars,
aligns its C preparation call independently of source stack alignment, and fully
unwinds that transient frame before the auxiliary switch. No source is published
while the original task's wait/control frames still occupy its source stack.

For acquisition, preparation reserves persistent referring control. The existing
[auxiliary entry](../../include/mutex_entry.S) marks the exact entry ENTERED,
loads the task-owned admitted control top, and calls the serial episode driver.
That cursor has TCLock's `current->komb_stack_curr_ptr` role from pinned commit
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef`. The original UB-derived JIT and KD GS
lowering remain the body engine; TCLock's native borrowed-stack execution engine
is not imported. W's pre-CALL SP and post-CALL IP form a captured continuation,
without a fabricated source CALL word or a second source pop.

A reached nested operation uses the same serial request path and original S_W.
An ordinary local winner remains a persistent request. If a new root cannot admit
a JIT image because its slot is empty or closing, optional proxy eligibility may
be declined while the same persistent local protocol handles acquisition. This
image admission decision is distinct from the documented node-availability
assumption. Generated execution requires a distinct physical task with admitted
nonoverlapping source/control stacks. The original task receives its current
native continuation directly, without running JIT on its own source stack.

Native unlock can operate synchronously on its exact existing grant/control;
it needs no new request allocation or source-stack lending. Its actual hardware
CALL/RET completes that native operation. It never imports a stale canonical
native SP/IP or repeats an earlier virtual CALL/RET. A source unlock marker,
owner handling, actual physical release and retirement remain distinct. Only
the responsible physical owner performs its complete backend release.

Numerical auxiliary ranges do not prove scheduler, IRQ, stack-overflow or
unwinder compatibility. The caller admits the full recursive C/control path and
its actual stack requirement before enabling source. The entry/header/endpoints
and all escaped control remain outside both stacks and survive their final
users. A live `aux_entry` forbids a second native prefix from reusing the cursor.
The final native-resume helper completes every entry/binding read, marks COMPLETE,
clears that reservation, closes its final exact actor and reads only stable core
regs for the native jump. No old entry snapshot or abandoned C frame is restored.

## Progress, detach and final storage use

The actual physical task's owner-progress controller handles retained release
metadata during existing MCS waits. It never reads a borrowed packet or executes
source. Stopped-control state gates physical finish and reap. Terminal foreign
physical duties can keep that task's own source pending; later result/grant/image
metadata retirement alone is not the same physical wait. Head storage can become
reusable at the final retirable publication, so owner-progress membership ends
before a possibly successful reap and no later head/item access follows success.

`kd_task_progress_native` makes one explicit original-W native progress pass:
owner control, completed-grant/episode actor collection, owner reap and finished
pool collection. It does not restore source registers or mutate the binding.
Existing physical MCS release can poll/yield for an in-flight producer's final
link store. Its returned pending flag describes remaining metadata; the current
native endpoint may keep it true. Never wait for that flag alone to become false,
and never treat false as a complete task-exit or reclamation proof.

Before detach, close source admission and drain all escaped source, queue, owner,
grant, code, return, notification, binding, lookup and auxiliary actors. A task
reference retains task identity, not an exiting stack or arbitrary caller
allocation. The caller must prove those last users before freeing stacks or
backing, including frames abandoned by a native jump.

`kd_task_root_detach` requires the same original current task and retained native
endpoint, no auxiliary entry or retained owned batch, no grants/pending exit and
an IDLE/RESUMABLE operation. It collects clean noncurrent slots, then the pool
validates otherwise-finished storage and revokes the exact native binding under
its metadata guard. Only infallible slot cleanup follows that revocation. The
helper clears task lookup, completes its final header access and drops the task
reference without later header/core use. A failed detach does not authorize exit
or freeing. Full admission closure, drain scheduling and actual lifecycle hooks
remain separate integration duties.

All components here have source/static review only. No new compilation,
assembly, behavioral check, kernel execution or whole-lane support is established.
The older external registry, two-task-pointer variant and removed temporary
local fallback remain historical Git evidence, not the active integration.
