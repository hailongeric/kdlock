# Task-owned root, request storage and auxiliary entry

The [current evidence checkpoint](../../docs/design/kdlock_redesign/04_evidence_and_reconciliation.md#current-evidenced-checkpoint)
records exact build/boot and scoped execution results, retained failures and
current validation limits. This guide states integration duties; its source
instructions do not establish support or performance evidence.

Every active borrowed or nested request uses its explicit MCS call/node's
`node->state` pointer to original W's one canonical S_W. A nested request keeps
that same pointer. The dispatcher passes its current call and parent role;
changing physical executor never substitutes that task's own core. No external
registry or active-borrowed-state task field participates. The fixed-image
fixture now observes this same-state relationship across actual CA → CB → CA
execution and positive protected returns; its exact release/retirement evidence
remains narrower than a complete auxiliary/lifecycle or public API proof.

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
static initial task's omitted pointer is zero initialized. The template now
contains managed fork/failure/exit hooks implemented by
[lifecycle.c](../lifecycle.c). Exact target application has its own receipt under
[the build guide](BUILDING.md); the template itself remains unapplied evidence.

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
helper allocates or supplies a global fork/exit policy by itself. Concrete
[task storage](../task_storage.c) and [managed lifecycle](../lifecycle.c) wrappers
compose those duties as described below.

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

The immutable episode configuration also supplies an initialized feedback pool
and an explicit pure target-classification callback. The pool and its actual
record-array extent are checked outside both task stacks and disjoint from known
setup/control records. Its backing can be shared across admitted tasks and must
outlive every fact/claim observer independently of task teardown. The callback
must distinguish ordinary source, source APIs and unclassified targets; a mutex
operation resolver returning NONE is insufficient. See [image and feedback
ownership](IMAGES.md) for finite capacity and exact publication/ACK ordering.

## Managed allocation, fork and exit

[task_storage.h](../task_storage.h) allocates cold header/pool/resources,
explicit slot/frame arrays and page-multiple vmalloc auxiliary backing before
source admission, without clearing the source packet. Error with non-NULL
storage retains attached state and the native-provider lease for explicit cleanup;
clean NULL failure leaves that lease with the caller. [source_stack.h](../source_stack.h)
retains the actual original task stack for bounded synchronous single-word
accesses through the last borrower; a task reference alone retains no stack.

[lifecycle.h](../lifecycle.h) defines an immutable typed managed-task context with
episode configuration, explicit capacities/control requirement and native
begin/release callbacks. The initial parent enters before its first declared
source call. After successful dup_task_struct, private child preparation clears
the copied root alias and creates a fresh single core/pool/auxiliary stack plus
independent task/stack/native holds. It copies no parent grant or continuation.
Only a managed parent supplies this context; unmanaged tasks stay outside the
lane. Child GS begins explicitly uncaptured and is refreshed before first source
publication. Clone may fail before publication; failure cleanup discharges the
child holds before the kernel drops its stack.

The current-native exit hook closes per-task admission, rejects borrowed/auxiliary
execution, pending operations and logical-open grants, then pumps exact owner/
grant/pool metadata with conditional rescheduling until atomic detach succeeds.
It neither executes source nor fabricates unlocks, and never waits solely for
pending==false. Invariant refusal cannot authorize freeing live state. Managed
callers permit no untracked raw root/storage/config observer across exit;
callback/module/caller-return backing survives its own final return. Actual
auxiliary scheduler/IRQ/unwinder compatibility remains unproved.

The [control workflow](CONTROL.md) connects runtime-native retention, compiler
transport and shutdown; [IMAGES.md](IMAGES.md) owns source/code/feedback lifetimes.
These source implementations select no deployment count or control-stack budget.

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
or freeing. The managed lifecycle wrapper supplies per-task admission closure and metadata
drain. Installing the exact hooks and proving full observer/context lifetimes
remain separate target integration duties.

These components had source/static review at `c6becf81`; its 12 focused host
pipeline checks, including GNU construction, executed no kernel path. Later
exact target build/boot, native-local and managed fork/exit observations have
their own receipts in the current checkpoint. They do not establish full
lifecycle/context proof or complete any T01-T56 acceptance item.
The older external registry, two-task-pointer variant and removed temporary
local fallback remain historical Git evidence, not the active integration.

## Plain spin runtime

Set `kd_jit_runtime_config.atomic_spin` for a runtime whose source uses the
plain `kd_spin_lock` and `kd_spin_unlock` macros in
[kd_spin_api.h](../../include/kd_spin_api.h). Initialize each object with
`kd_spin_init` or `KD_SPINLOCK_INITIALIZER`. Attach each caller in ordinary
task context before using the pair. All users of each object follow this pair
and keep its storage valid through its last actual queue and physical access.
The source provider supplies the exact spin entry addresses as LOCK and UNLOCK
boundaries. The wire directions and the original UB and GS lowering stay shared
with mutex. The kernel resolver distinguishes the exact spin entry targets.

The source enters with IRQs enabled and no unrelated preemption, IRQ or BH
obligation. Native nested calls can carry existing grants from this spin
runtime. Source and callbacks while a spin grant is open require a valid
atomic execution context, with no sleeping or explicit context changes.
Delegated source may not rely on the executor's numerical preemption depth
or physical CPU. IRQ, BH, signalable, trylock, callable and mixed-family entry
variants need their own integration. The spin runtime requires
`CONFIG_PREEMPT_COUNT` and uses the same non-PREEMPT_RT target.

The acquisition takes a preemption reference before queue publication and
moves wait control to the original task's auxiliary stack before lending its
source stack. A physical head with no open source grant can serve its immediate
eligible successor once. It withdraws its still ungranted request for that
turn and serves the waiter under the waiter's sole physical grant. It publishes
the waiter's result and pumps any remaining foreign physical release before
rejoining the queue for its own acquisition. The physical owner must keep
running its atomic control while another task needs its release. An atomic
wait polls the same exact owner and result records without scheduling.

A typed spin unlock completes after the responsible physical task performs
the queue release and acknowledges it. A child that unlocks an outer spin
grant can continue while its own grant remains held. The parent's control
polls and releases that exact outer grant during the child wait. Logical
completion, physical release and final request retirement have separate
conditions. The mutex policy for deferred outer release still carries its
same-object reacquisition limitation.

When a continuation returns to W, its open spin grants determine the native
preemption references. A control reference stays in place while W is on its
auxiliary stack. After a final generated unlock, the ordinary preemption check
runs on W's source stack with its native frame chain active. Admission requires
the original stack to fit the ordinary unlock and scheduling path at that
continuation. Complete auxiliary and unwind coverage remains a caller context
obligation. Request and fact availability use the same finite provisioning
contract as the mutex runtime.
