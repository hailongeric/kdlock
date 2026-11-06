# Original compiled images for kdlock lock replacement

The sole implementation writer is this session on `codex/mmap-reached-jit`,
starting at `fe06f8add830110e0dbd44bb63c8248257b3f57c`. Master and unrelated
work remain unchanged. This design precedes implementation.

## Correction and reuse

Use the original `disassem/disassem.py`, `translation_scope.py`, `normal.py`,
`special_inst.py`, `translation_image.py`, `include/wrapper.S` and daemon
workspace/compiler/publication pipeline. The original backend bounds selected
CFG exploration and follows learned CALL/IJ history. It does not require a
complete kernel CFG. Remove the candidate's eager ordinary-callee closure;
do not prewarm all MM paths or replace it with another instruction backend.

Preserve saved-origin GS (`normal.py` RGS; wrapper `PT_GS`), logical current_task
(RCT), virtual source SP/BP and actual source CALL/RET words. Stable GS reads,
including the stack guard, use ordinary generated lowering. GS mutations and
precisely identified task/CPU-context accesses retain declared services. A GS
prefix alone is not a reason to execute an instruction on O.

The general queue, acquisition readiness, killable/interruptible predicates,
ready-success priority, nested owners, downgrade/read credit, source/task/stack
leases, physical owner transfer, ACK and exact retirement remain unchanged.

## Learning and current-invocation joins

Legacy learning updates later immutable images. The original validated
indirect CALL path may run a suffix on O; generic IJ/RET/JMP misses are errors.
Neither policy completes the selected retained-lock requirement.

For current-position compiled execution, generated misses export a typed FULL
event before wrapper cleanup. Existing optional arithmetic-flags handling is
kept where available; general flags/SIMD restoration is deferred. The packet names the
actual target and post-transfer source SP. An ordinary CALL already pushed its
return word; RET already popped its word. Never repeat those effects.

Report direct missing callees through CALL_MISS and actual indirect edges
through IJ_MISS, including the real source continuation/site convention.
Never report an indirect CALL as CALL_MISS(target,0). Preserve generation-scoped
reports and stale-report rejection. Keep the existing capture image fixed;
only an explicit execution-artifact join may select another immutable image.
Ordinary frames continue to execute their original bound generation.

The updated user direction supersedes same-invocation image waiting/joining.
A retained miss exports the exact current source position and hands execution
to O without replay. The existing capture image remains fixed; learned edges
are used for later invocations and replacement images only. The old flags-less
generic IJ error is not a valid handback packet.

The independent E service worker has no caller acquisition of its own. Transfer
all live KD owners through exact owner transfer/pickup, route O's ordinary
release/downgrade/read release to those retained records, and retain frame,
source, task, stack and module lifetimes until final handback acknowledgment.
E then returns to its service loop; do not invent a public writer acquisition.
Native-context owner records require explicit custody transfer or an encountered
unsupported boundary. Do not relabel them released while they remain held.

The origin read-release route must be allocation/scheduling/guard-free and must
not touch the object after its final decrement. Internal speculative rollback
must remain separate from the public read-tail release. Existing legacy Native
routing cannot substitute its one-entry vector for the full retained owner list.

Returning Native helper/instruction services remain bounded intervals followed
by E resumption before any untranslated-code handback. A handled declared
service is not automatically a suffix handback.

## Boundaries requiring explicit evidence

A handback with live Native spin/preempt/RCU owners requires exact transfer of
those records and matching origin context. Existing returning-service records
cannot simply be dropped when O executes ordinary Native unlocks. Enumerate any
unsupported encountered combination without weakening its ownership checks.

Compiler/daemon progress also requires attention: their own MM operations must
not recursively depend on the image being compiled. Provider activation and
source/worker lifetime must permit independent compiler progress. No mmap1-only
branch or helper will be introduced to avoid this dependency.

The existing image pool has session-wide immutable allocations. New joins must
retain that capacity/lifetime limit explicitly; successful publication does not
establish unbounded active-path supplementation. Exhaustion is a candidate
validation boundary, not permission for origin completion.

## Delivery and focused checks

1. Commit this correction and dependency map.
2. Add exact original-backend current-position miss contracts and distinct
   CALL/IJ learning, preserving ordinary immutable bindings.
3. Connect current-position owner/lifetime handback and general API routing;
   replace the selected per-instruction emitter/cache path.
4. Move unnecessary interpreter execution to fixtures only after checking
   `kd_reached_decode`, `kd_reached_begin`, `kd_exe_reached_run` and the existing
   generated-code comparison fixture. Do not delete `kd_reached.c` wholesale or
   revert `1340d0e1`, which would restore interpretation.
5. Run focused original-codegen, entry/miss, immutable-publication, retained
   service and directly affected build checks only on the VM. Inspect actual
   idle/run state before synchronization; old SSH monitor processes alone prove
   neither activity nor drain. Do not reboot/install, force unload or disturb
   another run as part of these non-disruptive checks.

Build/test results and unresolved contexts will be reported separately from
this design. No old per-instruction JIT score proves the corrected backend.

## Explicit cold-image contract

ABI2 compiled images select the FULL current-position miss contract independently
of whether a recognized service was discovered in their bounded graph. A cold
ordinary CALL can therefore hand back with flags even before a service target
is reached. The requirement is valid for ordinary ABI2 mutex frames too; those
use the original owner/ACK handback chain. Retained roots use their exact owner
list instead. Neither path is a new instruction backend.

## Phase scope and original design

The first unexecuted source instruction is the handback boundary. Completed
CALL pushes and RET pops stay committed. Original design intent and later
implementation limitations are distinct: complete caller tracing at `20fde062`
finds progressed generic errors stopped by executed-body guards, while the
RUN_NATIVE path restores the current packet. The correction wires the intended
current-position behavior; it does not use later fail-stop code to justify a
second JIT. UserspaceBypass provides a matching current-target/later-learning
reference, not a kernel ownership implementation.

General flags and SIMD restoration, and IRQ/NMI conflicts, are deferred for this
phase. Existing supported arithmetic-flags packet handling may remain, but it
is not a claim of general architectural equivalence or a reason to delay lock
custody work. Exact IP/GPR/SP, source CALL/RET effects and owner/ACK lifetime
remain required.

## One backend and reference dependencies

Remove the per-instruction emitter, CPU code cache, module selector and runtime
entry points. Preserve its fixed historical evidence at `fe06f8ad`; it is not an
alternative execution mode. Move the C decoder/effect engine and adapter into
standalone fixtures, and remove their objects from the provider link. Keep
those fixture checks labeled as references, not original-JIT runtime validation.
The original image backend is the only production JIT.

An untranslated initial entry has executed no source body and has not published
a delegated request. It records that boundary and takes ordinary C admission
before continuing locally at that entry, preserving cancellation. A progressed
miss must instead use exact current-position owner handback and final ACK; it
must not return through the completed-body cleanup path.

## Original-backend fixture follow-up

The frozen `336009d3d76b946976382b610752d23e43d516e8` VM check built the
provider and passed GS, entry-scope, immutable-image publication and the moved
reference adapter/fetch checks. Two code-generation fixtures failed. The cold
ABI2 fixture omitted the provider's clobber control symbols. The conditional
callee fixture omitted its learned callee entry after bounded exploration was
restored, so the service inside that callee was correctly absent from its image.
Supply those fixture inputs explicitly; do not expand production exploration or
change emitted requirements to make either fixture pass. Rerun only those two
affected programs after the overall functionality is complete, following the
later testing-order instruction. No intermediate rerun has been launched.
These checks do not establish retained-owner handback or an
executed mmap1 result for the corrected backend.

## Retained handback joins

Status: the user selected option 2, explicit Native read custody. The approved
sequence below supersedes the historical cohort proposal in this section.
Commit `6648a732` records that unimplemented proposal. Do not add its reader
layout, paired-atomic operation, CPU requirement or cohort-drain wait.

Reuse the existing native-frame registry for permanent current-position
handoff. Suspend before registration. Its typed service callbacks resolve the
full retained owner list; ordinary mutex unlock and rwsem write release or
downgrade route before local-only ownership checks. A stack request pins the
frame across each callback outside the registry guard. Registry removal and
the callback's final acknowledgment precede frame retirement. Initial restore
does not call the completed-body helper or drop the capture callback reference.

E transfers every live KD gate with the existing transfer/pickup operations.
O picks up those gates on its independent waiting stack, copies the current
packet onto its source stack, and publishes its final restore acknowledgment
before continuing. Native locks already physically held by O transfer ledger
custody, not physical exclusion: record this explicitly without claiming an
unlock. E never resumes that source packet or acquires an invented writer.

Anonymous read release needs an object-level join rather than a task lookup.
Place a retained cohort pointer beside the real reader count in its existing
cacheline padding. Attach a cohort only for a permanently handed-back read
tail, while its actual read credit is still held. Extra local readers and
non-owner releases remain anonymous Native-compatible credits. Cohort drainage
is a conservative proof that every attached credit has gone; an unrelated
first read release is not such a proof.

For prepared objects every possibly final decrement, including speculative
rollback, uses one x86 paired compare/exchange to change count one and its
cohort pointer to zero and NULL together. A nonfinal count greater than one can
use a count-only compare/exchange. Do not use a NULL-pointer check followed by
an unconditional decrement: a delayed speculative rollback can overlap cohort
publication. A removed pointer is not dereferenced until its successful paired
operation. Its final acknowledgment touches retained metadata only, never the
semaphore. The target Linux 7 header exposes `try_cmpxchg128`; provider setup
must check the corresponding CPU capability before preparing objects. The
ordinary unprepared local backend keeps its existing count operation.

O continues directly after its own source release; it never waits for unrelated
readers to drain. E retains the old cohort and owner anchors until drainage and
all callback accesses finish, removes routing, then uses suspended completion
and exact retirement. This can retain a worker longer than the source read
tail; worker availability under long overlapping readers remains an explicit
progress validation item, separate from read exclusion. Ordinary fully
translated tails do not attach a cohort and retain their existing completion.
The capture callback reference is dropped only after E's final retirement;
module exit still stops service workers before freeing their storage.

### Review before implementation

The cohort-zero proposal above is not acceptable merely with a progress caveat.
The service pool is finite and each worker executes a root synchronously. If
every worker retains a handed-back cohort, an unrelated reader can wait for an
independent prepared acquisition before dropping its read share. That new
request needs a worker, but the workers wait for those shares. This adds a
worker-pool cycle without an application lock cycle. This is a source-derived
counterexample, not an observed VM result. Storage spill does not add workers.

| Choice | Existing state reused | Additional state or operations | Retirement and limits |
| --- | --- | --- | --- |
| Retain writer records and reuse ordinary Native routing | Executor stack-local owner/request anchors, native-frame registry, existing transfer/pickup and suspended continuation | Typed callbacks over the full owner list; no separate task registry | Keep owner anchors through actual release callbacks and final packet/access ACK. Read release cannot use the guarded Native registry. |
| Explicit Native read custody | Existing read credit, object/provider binding, original task/source stack, packet and final acknowledgment | A distinct custody state; no reader decrement, new reader identity or object-layout change | Retire translated custody only after E has no further packet/route access. O and non-owner callers retain the ordinary object lifetime. Bound objects retain provider/source; unbound users require their existing Native source-lifetime contract. This is a proposal, not a proof of universal replacement. |
| Cohort zero from `6648a732` | Retained owner metadata and reader count | Adjacent pointer, 128-bit operation, CPU capability and passive-record/progress machinery | Waiting in E is insufficient because of the cycle above. Additional detachment would be a larger redesign and is not authorized by this document. |

The minimal recommended direction is stack-local writer/request state with
existing Native routing, plus explicit Native read-custody transfer where its
lifetime contract is established. A read-custody transfer is not `up_read`, a
returned JIT body, or an outer-unlock event. Its exact packet/access ACK must be
distinct from full-body completion. The builtin completion trampoline cannot
drop the capture module reference while E still depends on it. The ordering of
frame/route retirement, final stack-local ACK and builtin restoration remains
part of the decision to review before implementation.

Relevant source evidence is `kd_service.c`'s stack-local child owner records and
synchronous worker loop; `execution/native.inc`'s guarded frame registry and
last-access stack acknowledgment; builtin `provider.c` binding get/put; adapter
object initialization/destruction; and `kd_source_begin_retire`'s refusal while
bound objects remain. None proves that a translated frame can simply disappear
while another actor still has one of its pointers.

## Independent reuse inventory

This inventory was checked against `bfcb0852`. It does not select or implement
the pending read-credit alternative. O denotes the original task, E the service
worker, and ACK an acknowledgment of the specified actor's final access.

| Existing storage | Location and owner | Lifetime that must be preserved |
| --- | --- | --- |
| Root continuation, outer admission and packet | `kd_service_root`, preallocated service record and `node->regs`; a capacity spill is allocated only after real acquisition commits | Keep the UID/generation and source/task/stack lease until the exact retirement boundary. Storage allocation must not conceal killable cancellation. |
| Nested KD owner and request | `kd_service_nested`'s E-stack `child`; linked through `scope.owners` | `kd_service_run_scope` retains its C activation. Do not unwind while any actor or route can still refer to the child. Non-LIFO release does not change storage lifetime. |
| Additional Native owner | `kd_service_native_spill`'s E-stack `owner`, beyond the root's eight preallocated records | Keep the activation while its Native ownership record is live. A future custody transition must be explicit; it cannot merely clear `held`. |
| Native release request | `kd_exec_native_unlock`'s O-stack `kd_native_request` | E clears its frame request and removes completed routing before its final store to `request.done`. O then reads only its own request, not a potentially retired frame. |
| Current source packet | Original generated FULL export in the existing packet | A missing CALL has already pushed its source return word; a missing RET has already popped it. Restore the first unexecuted IP without rebuilding or replaying the entry packet. |
| Final restore copy | Existing `kd_service_resume_packet`'s O-stack local packet | This is a completion helper, not an initial-handback helper. It frees the root and may drop the callback module reference; live owner records cannot be left behind. |

### Function-level reuse and ordering

| Function | Reusable behavior | Required boundary or adaptation |
| --- | --- | --- |
| `kd_jit_retained_miss` | Checks and exports exact current packet; reports the actual CALL/IJ edge for later generation | No pending source service or remote/Native request. It does not transfer ownership or retire a frame. |
| `kd_exec_cont_suspend` / `kd_service_unpin` | Remove E's CPU activation and retain its continuation and task reference | Suspend before publishing a Native route. `kd_exec_cont_no_stack_service` refuses a live `native_link` or `native_request`. |
| `kd_admission_owner_transfer_locked` | The real physical owner designates the next owner under the object's gate guard | Sets pickup pending; it does not release the lock or finish pickup. |
| `kd_admission_owner_pickup_locked` | The designated task consumes the exact pickup and updates the rwsem phase owner | The selected phase remains ADMISSION; ordinary LOCAL-only release is not automatically valid afterward. |
| `kd_service_origin_command` | Existing transfer/pickup/release command and ACK | Currently addresses only the outer admission before body execution. A retained multi-owner handback needs the complete owner list, not just this outer field. |
| `kd_exec_native_begin` / `kd_exec_native_unlock` / `kd_exec_native_wait` | Existing frame registry, O-stack request publication and final-access ACK | Service scopes are intentionally refused by the old begin path: the compatibility vector is not their linked owner set. Any extension must use explicit typed operations over that set and invoke callbacks outside the registry guard. |
| `kd_admission_release` / `kd_admission_downgrade` | Actual physical release and ordered downgrade credit | Keep their real release ordering; do not substitute a custody-state update or decrement the same read credit twice. |
| `kd_admission_detach_local_locked` | Ordinary C admission transfers into object-local custody | Also retires its stack request immediately. It is not an unchanged retained-frame handback helper. |
| `kd_exec_cont_return` | Already supports exact completed-body return from a suspended frame on its original E | Requires literal release/completion facts. A Native read-custody decision cannot be represented by manufacturing `outer_unlock_seen`. |
| `kd_exec_cont_retire` | Drops stack/task/source references only after memberships, routes and dependent records finish | No E, resume task, service, child, selection or retained storage reference may remain. |
| `kd_rwsem_provider_resume` | Builtin final module-reference drop and restoration from O-owned packet storage | Enter only after module-owned accesses retire; do not reuse its reference drop at an earlier handback stage without a separate proved reference. |

The root's existing request, packet, linked owner records and native-frame
registry are sufficient storage for preparing the writer-routing extension.
This inventory adds no allocation, global registry, reader field, CPU
requirement or protocol state. The earlier question about retiring translated
read custody is resolved by the approved Native read-custody sequence below;
the read credit itself remains live until its ordinary Native release.

### Bound-object references and limits

Builtin `provider.c`'s `kd_rwsem_bind_provider` takes both a module reference and
the provider's binding reference. `adapter.c` retains them until object
destruction; `kd_source_begin_retire` refuses closure while bindings remain.
Individual API callbacks also hold a separate invocation reference. The
clobber capture reference instead survives until completed restoration or a
properly specified handback. These are different references, not substitutes
for one another. The retained packet/route pointers still require their own
last-access proof even while an object keeps source text resident.

The in-tree non-owner path separately retains its mm/object reference. Generic
unbound callers have their ordinary Native source/object-lifetime contract;
the bound-object observation alone does not establish universal replacement.

### Independent runner and fixture preparation

The mmap1 diagnostic controller still exposed the removed execution mode even
though its default image path already uses the original daemon and immutable
registry. Restrict new controller construction and its CLI to `image`; retain
historical trace validators for offline evidence rather than relabeling them
as a current backend. The old one-point runner and schema-2 image-free receipts
still require migration before they can measure this candidate; removing a
module option alone would omit the required daemon/image lifecycle.

The moved adapter/fetch fixtures exercise a standalone reference component.
Their result labels must say reference, not production. Their existing checks
remain intact. Prepare the controller-boundary fixture now, but do not run it
or any intermediate checks until the overall functionality is complete.

## Approved Native read-custody sequence

Option 2 transfers the existing downgraded read obligation to ordinary Native
execution without changing the reader count. The normal `up_read` or
`up_read_non_owner` consumes it. This transfer is neither a physical unlock nor
a returned JIT body. Other live mutex/writer gates remain physically owned by E
and use exact existing Native release routing. No additional queue, reader
metadata, task registry or allocation is needed for this join.

1. A validated original-JIT miss exports the first unexecuted source position.
   E suspends its CPU activation before publishing a Native frame route.
2. Preserve E-stack nested records. Mark already downgraded read obligations as
   Native custody without touching the semaphore. Native locks actually held by
   O likewise transfer ledger custody; their physical state is unchanged.
3. Register the retained frame in the existing Native registry, resolving typed
   operations against the complete owner list instead of its compatibility
   vector. The writer ownership query uses that exact route, not an aggregate
   `is_locked` observation.
4. O moves back to its source stack and copies the current packet and completion
   fields into local storage. An existing-style O-stack Native request records
   acceptance; its done ACK is E's final access to that request. O accesses no
   root/frame field after acknowledgment and resumes the saved packet once.
5. Retain the original capture callback reference for E's outstanding frame.
   Bound restoration takes a separate temporary module reference and consumes
   it only through the existing builtin restoration callback. This prevents
   the initial restore from dropping E's reference. Keep the frame source lease
   until all E-owned releases and packet/access acknowledgments finish.
6. Subsequent O write-release or downgrade calls submit typed stack requests.
   E checks the exact owner UID/generation, performs the real release, and
   acknowledges it. A downgrade then transfers its new read credit to Native
   custody without a second decrement. Ordinary read release and speculative
   rollback remain unchanged.
7. Remove routing before its final ACK. After every E-owned gate is actually
   released and packet acceptance is acknowledged, unwind stack anchors and
   retire the handed-back continuation through a distinct terminal state.
   Do not manufacture `outer_unlock_seen` or increment full-JIT completion.

Bound MM objects retain provider/source independently through object destruction
and transferred non-owner references. Generic unbound callers retain their
ordinary Native source/object-lifetime obligation; the source/module references
for E's retained records must still be explicit. Unbound Native-only lifetime
coverage must be reported separately from the bound mmap1 evidence, not assumed
from an object of equal layout. Broader source-lifetime machinery, if needed,
requires review before adding it.

The writer route, packet acceptance and distinct terminal state are required
implementation details of this selected option. Full flags/SIMD and IRQ/NMI
conflict handling remain deferred. Tests follow the completed implementation;
no intermediate VM run is part of this sequence.

## Selected synchronous pooled-storage retirement

The existing pooled release updates this CPU's slot mask and reserved-node
count. E deliberately executes away from O's reservation CPU. After permanent
Native restoration O may migrate, and its final write-release ACK also precedes
recursive E-stack unwind. Neither E freeing the slot directly nor O freeing it
at that early ACK is valid. No remote release helper currently exists.

The user authorized the smaller synchronous E-side path. No additional cleanup
workqueue or change to O's handback/ACK timing is required. The earlier deferred
work proposal remains historical at `f7d97c55`; it is not selected. This design
precedes the synchronous cleanup implementation.

1. E first finishes every retained writer release, O packet acceptance and
   recursive stack anchor. E performs the distinct handed-back terminal
   transition itself because `resume_executor` names the actual E task.
2. Snapshot the capture callback module reference, pooled/storage identity and
   original CPU before dispatching cleanup. Mark the root FINISHED under the
   existing dispatch guard. It remains observable with source/task references
   retained, but no longer excludes its origin CPU as a pending proxy origin.
3. For pooled storage, hold `cpus_read_lock` from the online check through the
   complete synchronous `work_on_cpu(home_cpu, cleanup, root)` call. A queued
   callback without hotplug exclusion through execution is insufficient. The
   target Linux 7 source does not supply an SMP `work_on_cpu_safe` interface.
4. The callback validates exact encoded CPU, slot, node pointer and service-root
   identity. Remove active-list observation under the dispatch guard before
   retiring the continuation's source/task/stack references. Drop that guard
   before continuation callbacks, source retirement or any sleeping operation.
   Retire the request after its continuation and before publishing slot reuse.
5. An online home-CPU callback disables preemption and uses ordinary local node
   release. Keep all OSQ, queue-membership, selection and count assertions.
   A service root uses its own request, so the slot's legacy request_live must
   be false. Slot reuse is the callback's final access to root-associated data.
6. If the home CPU is already offline, run a service-only explicit CPU-indexed
   release. Retain hotplug exclusion and serialize bitmap/count updates under
   the dispatch guard: the hotplug read lock is shared and does not serialize
   two offline cleanups. Validate the same exact identity and request_live
   conditions. Factor shared node validation and field retirement rather than
   omitting the local path's checks. Do not wait for that CPU to return online.
7. Spill roots have no CPU-local slot and can retire synchronously on E in
   ordinary sleepable context. No dispatch guard spans vfree or kfree.
8. E never dereferences the root after the callback returns. Release only the
   previously saved module references. Existing worker-stop ordering includes
   synchronous cleanup completion before pool/code destruction.

`kd_service_idle` can become true after active-list removal while the callback
still has its final retirement work. It is not a standalone callback-completion
barrier. Exact reservation bitmap/count state, frame/module references and
synchronous worker joining retain the composite drain/teardown contract.

O continues independently after its existing final packet or release ACK. E
can wait for the home CPU's task-context callback, so this selection is not a
claim of bounded cleanup latency or universal progress. The reviewed simple
free-worker/preemption cycle was not demonstrated by the actual capture path;
do not report it as an observed deadlock. A later waiter-side final-use ACK
simplification is separate work, not a prerequisite imposed by this design.

## Selected state queries use the original JIT

The user selected ordinary original-JIT execution for
`kd_mmap_assert_held_write`, `kd_mmap_assert_held` and `kd_mmap_is_locked`.
This is a targeted classification correction, not permission to expand an
entire helper call chain before execution. The existing bounded CFG policy,
actual CALL/IJ reports and later immutable-image learning remain unchanged.
This section precedes the corresponding code changes.

The exported facade-control rows use synthetic labels. Identify the three
queries by `KD_RWSEM_OP_ASSERT_HELD` (14),
`KD_RWSEM_OP_ASSERT_HELD_WRITE` (15) and `KD_RWSEM_OP_IS_LOCKED` (16), not by
their display names. Keep their immutable control-table records for exact
discovery, but exclude these records from the translator's runtime-control,
lock-control and callee-exclusion sets. Do not register their targets as
returning Native services. Consequently their reached CALLs use ordinary miss
reporting, and their learned direct or indirect targets become decoded roots
through the existing history mechanism. An inconsistent snapshot that still
declares one of these targets as a Native service must fail translation rather
than silently selecting that service. The other query operations,
`KD_RWSEM_OP_IS_CONTENDED` (17) and `KD_RWSEM_OP_IS_WRITE_OWNER` (18), retain
their current Native services. Acquisition, release and downgrade controls
retain their current classifications.

Keep the actual assertion bodies and provider callbacks unchanged. In
particular, `kd_provider_write_owned` first checks the exact LOCAL phase and
physical owner, then calls `kd_service_write_owned` for retained ownership.
That inner runtime query depends on `kd_exec_current_frame` and the exact
origin-service transaction. Its physical CPU/task interpretation cannot be
replaced by an ordinary translated `current_task` read. Declare this existing
two-argument Boolean function as a returning Native service using the existing
atomic-compatible context and module-reference contract. O executes only that
runtime query while E is suspended, then E resumes the same immutable JIT
image. Preserve its request generation, physical gate owner, selected phase
identity/generation and pending-pickup checks. A positive reader count or a
generic locked observation cannot replace those checks. This uses the existing
service protocol and adds no query-specific queue or new public API.

Other downstream operations retain their individually declared Native services
or ordinary bounded learning. Merely being called by one of the three queries
does not force a helper into translation or turn it into a Native service.
A cold downstream target still uses the documented first-unexecuted-position
handback; it does not wait for a new image or replay completed instructions.
The original JIT remains the sole production backend.

Focused fixture preparation covers operation-based partitioning, inconsistent
service declarations, cold and learned query CALLs, exact ownership predicates
with different O/E tasks and stale identity/generation observations, and Native
read custody retiring while its ordinary read credit remains live. These are
prepared checks until executed on the VM after the overall functionality is
complete. They do not establish an mmap1 result. The separately selected
synchronous pooled-storage retirement above retains its own implementation
and validation obligations.

## First focused candidate evidence

Candidate `a6fe0bb269642cf2dd6f07c3430b6933f9c0557a` built with `W=1` against
the separate Linux 7 `kdscope5` output tree. The VM remained on
`7.0.0-38-kdlock1`; no module was loaded and no reboot or timing point ran.
The build retained its compiler-name notice and objtool return/frame warnings.
Frozen input hashes were unchanged and the VM was idle after the checks.

Seven fixture drivers passed: the production writer-query/descriptor consumer,
canonical admission (15 cases and four mutation checks), Native writer custody
(81 checks and seven mutation checks), original generated misses (four cases),
returning CALLs (21 cases), the production entry/hostcall consumer and mutation
checks, and generated MM/provider binding. Their exact source remains the
candidate above; later fixture reruns do not relabel those receipts.

Two prepared fixtures failed. The query-image fixture incorrectly treated a
legal caller continuation label as evidence of a Native outer helper. Original
image generation supplies those labels for ordinary CALL successors too.
Replace that assertion with execution of the actual inner Native target,
both source CALL words, one substituted Boolean result and JIT execution of
the surrounding helper/caller continuation. The retirement fixture did not
compile under `-Werror` because its supplied unsigned CPU ID was compared with
an int. Compare against an unsigned CPU value after the existing range checks.
Also reject a missing pooled reservation before retiring its source/task
references; a later diagnostic return is not successful slot reclamation.

Prepare the directly affected resource/OSQ and saved-GS checks, the existing
final-reader-access fixture, and a small production-extraction Native-service
join. The latter must execute registry acceptance, typed owner match/release,
the final O-stack ACK, stack-anchor removal and handed-back continuation
retirement. Physical admission/release, task/CPU context and source-reference
primitives remain supplied observations. Neither these fixtures nor a provider
build establishes live kernel handback or mmap1 execution. Retain that boundary
until separate focused kernel and unchanged application runs prove it.

## Canonical-queue fixture adaptation

The `da55414f` build and seven directly affected fixture drivers passed. The
resource and OSQ drivers stopped during extraction because they still named
helpers removed by the earlier canonical-queue migration. Preserve those
failures and adapt the drivers to the current producers; do not restore the
removed production functions or omit node-retirement checks.

The OSQ-only fixture uses the real cold-record layout and common-spin helper.
It never publishes a captured request, so any request-state retirement remains
a failing supplied boundary. The resource fixture extracts the real request
initializers, slot lookup, state transitions and release. Its substituted
physical/assembly boundary supplies an acquired request with the exact record
and generation; queue election itself remains covered by the admission fixture.
Model physical acquisition before scheduling-gate pickup, retain all mutation
checks, and require the Native unlock lookup even without a legacy task record.
Only these repaired drivers need a new VM run; unchanged passing drivers keep
their original source-specific receipts. This remains component evidence,
separate from matching-kernel live continuation and mmap1 checks.

The frozen `615cdb0b` rerun passed all 26 OSQ scenarios and detected all 14
mutations. Its resource driver compiled, then rejected the supplied ordinary
peer case because the old assembly substitute had no outcome for that case.
Route it through the extracted physical-wait helper without pretending that
the ordinary peer owns a delegation gate. Preserve a noncalling function
reference in the omitted-physical-acquisition mutation so its result remains
a runtime assertion, not an unused-function compile failure. Rerun only the
resource driver; the OSQ receipt remains attached to its existing version.

## Completed fixture repair and next live boundary

The frozen `2bfbb8dc992ce9cb8ef38521cbc2ca43c35e6f48` resource-only rerun passed
19,164 checks with zero failures and detected all 27 mutations. OSQ remains
26 scenarios and 14 detected mutations at `615cdb0b`. Their production
`kernel_module`, `include` and `disassem` trees are byte-identical to
`da55414fa576a6e683f98364523cf9353b598c0e`; no new provider build was needed
for these fixture-only changes. The [fixed result record](../../bench/results/10.176.26.71/tests/compiled-mm-handback-components-da55414f/README.md)
retains every earlier failure, exact freeze/check reply and evidence limit.

Fresh metadata verification passed the installed scope5 KD bundle, but the VM
still runs normal `kdlock1` and the candidate provider is unloaded. The shared
facade/layout/adapter match; provider-header/restoration differences are only
comments. The exact kernel/provider identities and source comparison are in
the same result record. This is preparation, not a running-MM pass.

The next minimal live validator must distinguish cold permanent handback from
returned JIT work, preserve prefix effects and actual IP/SP/CALL words, exercise
nested release/downgrade/read custody and a subsequent writer, and observe a
later learned immutable image. Use the existing generic continuation probes;
do not add mmap1-specific API behavior. The actual three public query bodies
also need live evidence beyond their synthetic code-generation fixture. Bind
all runs to matching kernel, provider, daemon and translator identities, and
refresh the real recovery-snapshot inventory before module execution. Only
then run the two focused real-syscall mmap1 models; no performance claim follows
from the component results.

## Opt-in cold and learned continuation probe

Use the existing helper-mode kernel fixture and controller with a separate
`--check-set handback` selection. Preserve old modes' exact full-return and
unchanged-publication assertions. Add one unregistered ordinary register-JMP
wrapper and three small source leaf entries for root, nested-owner and read-tail
cases. The leaf captures source-entry SP and the real return word before its C
body, then publishes a bounded scalar checkpoint. It is not a registered
runtime service or an application adapter. The nested call occurs after child
acquisition and before release; the read-tail call occurs after real downgrade.

Pause/resume the same daemon between drained learning waves. Archive each
immutable registry row, generated source/binary and learned CALL/IJ tables.
Determine expected cold/warm behavior from that actual image's decoded-source
coverage rather than assuming a fixed wave number. A cold ordinary CALL and
actual indirect edge must each hand back once; a later image must execute the
same useful body and return on E. Keep the source effect count one per request,
check actual O/E identities, compare the handback IP/SP with the source entry,
and validate the return word against the loaded module's actual CALL relocation.

Append IP, SP and image generation to the existing opt-in service event record
so a read-only handback can be observed even after E has retired its frame.
These fields are diagnostic and do not authorize ownership or restoration;
disabled tracing retains the same execution path. Native read custody does
not emit an E-side read release. Observe its real credit and queued successor,
release the O-side read tail, then require a fresh writer and complete source,
service, reservation and module drain. A terminal handback event alone is not
storage-retirement evidence.

The first `5ff1f232` live launch stopped before module loading because its
controller-only CPU mask excluded the requested worker CPUs. The corrected
launcher reached the fixture but its CALL oracle rejected an ordinary function
address stored by the snapshot code. Actual ELF records show one absolute
`R_X86_64_32S` reference and three `R_X86_64_PLT32` references with an `E8`
opcode and addend -4. Only the latter are source CALL return words. Keep strict
checks on those actual CALLs and omit the absolute address reference from that
set. The second attempt retired all frames, modules and writers, unregistered
the helper pin, unloaded normally and left the VM idle. No body result is
claimed from either stopped attempt.

The third attempt passed cold CALL and indirect-target handback. Its later
compiled callee reached an unlearned RET continuation: IP equals the audited
source return word, SP equals leaf-entry SP plus eight, and all useful effects
occurred once. The archived decoded return-thunk block contains one bare RET;
its next-PC is the actual IJ history source. Accept only that exact post-pop
case and learn it for a later image within the same bounded wave count. Entry
coverage alone does not prove a complete translated return path.

Failure cleanup also resumed the paused daemon too early, allowing a compiler
child to start before the existing no-child stop check. Preserve that guard;
at the actual stop boundary send termination before continuation. The exact
retained daemon was later stopped after its child completed, source retirement
reported modules/frames/writers zero, helper registration was released, and
both modules unloaded normally. The VM is idle; no force unload occurred.
# Demand image preparation for the throughput pilot

This design starts at `805e29f3d4c11f602740c066a7ac26c5689d2ef3` on
`codex/mmap-reached-jit`. The VM has returned to the verified ordinary kernel
before implementation. The earlier pilot attempts and Native rates remain
separate evidence; none established current KD mmap1 throughput.

The 55 audited entries are static MM writer sites. They are not 55 observed
mmap1 paths. `kd_rwsem_provider_prepare_entries()` registers the full table,
activation requires an image for every entry, and the daemon synchronously
waits for each compiler child. These preparation policies are independent of
the original JIT's bounded translation and later miss learning.

Add the explicit, general provider option `rwsem_provider_demand=1`, keeping
the existing default unchanged. In demand mode preparation validates the
builtin site descriptors without registering every image. Activation retains
initialization, open-source, CPU, provider registration and source-binding
requirements; image availability is decided at each capture. No MM body,
caller-specific branch, lock API, queue, cancellation or downgrade changes.

The existing `kd_service_capture_internal()` already registers an encountered
entry. When no image is available, it releases the pending capture lease and
uses ordinary local KD acquisition before reserving/publishing a request or
executing a source instruction. Killable success/cancellation ordering is
therefore preserved by the existing local admission. This is distinct from a
miss after JIT progress: that path retains current IP/SP/GPRs, actual CALL/RET
effects, physical lock custody, source/frame references and exact final ACKs.
It must neither restart the body nor report a handed-back prefix as a returned
JIT body. The original immutable-image backend remains the only JIT backend.

The benchmark separates learning from a stable timing epoch. Learning uses
unchanged application lifetimes and records image additions/updates as normal
progress. It waits outside the application interval for compiler, request and
source drainage before taking a new receipt. A bounded learning deadline is
not proof of drain. Stable timing retains exact provider/daemon/controller,
source, inputs and image-generation checks; a new entry or generation during
that interval leaves it unaccepted and records learning rather than claiming
corruption or silently repeating the score.

At each learning boundary, stop new object bindings while the daemon catches
up, then reactivate before taking the next receipt and starting fresh workload
tasks. Existing objects keep their immutable provider binding until destruction;
source admission stays open. Compiler children started during this wait use the
existing local backend, avoiding continued demand creation by the compiler's
own new MM objects. A child that was already bound still completes through its
original provider. This is experiment sequencing, not a caller-specific kernel
rule, and scored timing never toggles object binding.

Demand registry identity is `(pid, entry)`, with kernel `pid == 0`, valid
audited entry/ABI/lock kind and publication generation. First-registrar TGID
is metadata: the provider binds new MM objects globally, so unrelated MM tasks
can legitimately register an entry. It is not execution or ownership proof.
The receipt must bind the reviewed static site table and actual provider/source
identities independently. Workload delegation claims require worker/root/
backing joins; global JIT counters alone do not establish them. Native-only
and mixed local/JIT observations must be labelled accordingly.

Use the existing private benchmark provider, whose declared parameters include
`bench_quiet` and `bench_complete_probe`; a production module is not that
variant. Check those parameters before preparation. Preserve source module
pins until `RETIRE`, exact zero state afterward, fresh-process finalization
and normal unload. Focus validation on demand/default activation, cold local
admission, receipt provenance and valid learning transitions, followed by the
one-round thread/process pilot and verified normal-kernel recovery. The
separate retained-continuation fixture is not rerun by this task.

## Empty scratch mapping correction before the next pilot

Baseline `8a7b8e73535b7dcfea326ff56f24422b5ad5ac73` on
`codex/mmap-reached-jit` completed one unscored thread learning lifetime, then
failed before a scored KD point. Preserve that result and the unrun process
point. The failed boot was `ca0f4f0e-2309-438c-bef1-cf85fbebd27e` with kernel
Build ID `5f2fce72a33480f6e79a79b374b21a0db377ecd1`.

The retained `map_vdso` image at entry `0xffffffff81344abb`, generation 2,
was published at `0xffa0000014bfa000`. Its instruction at offset `0xe9f` is
`MOV Stack_R, R13`; the fault IP is exactly base plus that offset, and the
destination is zero. The saved object SHA256 is
`c68c91e6e3a00b1b5d8b6470597fc2f86fd205a0cb3d0b785332af0b7c9fff2c`.
Its `.rela.text` contains `R_X86_64_32S` at `0xea3` referencing undefined
`Stack_R`. This establishes the emitted-byte failure independently of earlier
blocked-worker reports.

Fix the general register mapper: `release_IP()` has already emptied a borrowed
physical register when `recover_stable()` restores SP, so `spill_register()`
must emit nothing for that empty mapping. Keep the saved SP and dirty-GPR
protocol unchanged. Add the object completeness check described in
[JIT execution](../JIT_EXECUTION.md#executable-image-generations) before raw
extraction, including allocated data sections rather than only executable code.

Validate GS/RIP loads that borrow the SP register through the real generated
wrapper against owned guest userspace storage. Cover low and kernel-range
source IPs, SP restoration and logical reserved-GPR results. Separately verify
that incomplete emitted code/data is refused, resolved local expressions pass,
debug-only relocations are ignored, and a failed rebuild leaves no stale raw
image. Build the matching benchmark provider, then retry the focused two-worker
thread/process pilot with the existing Native controls retained. Keep learning
lifetimes unscored, record any failure and verify normal-kernel recovery. This
compiler correction does not implement the separate permanent ownership transfer
and immediate requeue protocol.

The first focused VM run at `87430984` passed the six object-image cases, then
stopped because the new GS/RIP fixture supplied no ABI2 lock symbol bindings.
Keep that failed run; correct its fixture to use the existing synthetic symbol
table before rerunning the focused checks. No module was loaded by this attempt.

At `b9b4e83f`, the GS/RIP wrapper corpus and reached ordinary-read reproducer
pass. The read-directory fixture still expects requirements `3968`, omitting
the existing retained-miss bit 13 selected by ABI2; its actual value is `12160`.
Update that fixture expectation using the named requirement constant. The
other seven read-codegen cases passed; retain the failed metadata check.

The corrected checkpoint `15f1c08a3a52ed271fcf3fd81f5da68f1f524878` passes
the four focused codegen drivers and provider build on the VM. All three
learning lifetimes in each mmap1 model complete and drain. Both comparison
attempts stop at `LEARNING_ADVANCED`; every pass still replaces image
generations, so no scored KD point starts. Both sessions retire exactly and
unload normally, followed by verified normal-kernel recovery. The
[complete record](../../bench/results/10.176.26.71/tests/jit-scratch-recovery-15f1c08a-20261105/README.md)
retains fixture failures, all six unscored rates and the open delegation and
performance criteria. No promotion or performance gain is claimed.

## Bounded cold convergence follow-up

The retained histories account for all completed jobs: threads have 12 initial
compilations, 35 distinct per-root CALL records and one IJ edge; processes have
13 initial compilations, 37 CALL records and one IJ edge. No root contains a
duplicate learned record. The common roots learn the same sequences in both
models. Assembly/binary hashes and decoded coverage grow across generations.
The pre-application receipt agrees with each saved `registry_before`; the
observed changes are not caused solely by comparing an earlier preparer state.
These observations do not demonstrate a history, compiler or receipt defect.

Use the unchanged tested runtime `15f1c08a3a52ed271fcf3fd81f5da68f1f524878`
for a separately identified cold session. Daemon startup clears its workspace,
so this does not resume the previous images or import old histories. Keep the
existing Native controls, source/provider hashes, topology, original JIT,
demand admission and syscall bodies unchanged. No new build is needed for this
configuration-only continuation.

Select the existing maximum of eight learning lifetimes with a 1,800-second
learning deadline per model. The runner already stops at the first stable
lifetime, so eight is a ceiling rather than a request to run eight regardless.
The measured 13.2-second median compiler jobs and 12/13 active roots make the
earlier three-wave ceiling inadequate to test deeper convergence. Roughly nine
images per 13 roots at the observed job cost fit this finite deadline, including
the initial image; it is a planning estimate, not a completeness guarantee.
Bound the parent measurement command at 2,100 seconds and transport at 2,220,
preserving the existing 300-second and 120-second outer margins.
Do not increase these limits during a running session.

Preserve the exact stable-lifetime check, fresh immutable execution receipt and
unchanged-before/after check for the single scored application point. A further
miss leaves that point unaccepted; no score retry, whole-CFG preparation or
relaxed acceptance is added. Keep thread/process evidence separate and retain
every unscored lifetime. After each session require exact retirement and normal
unload, or preserve an unresolved state for ordinary recovery. Verify the normal
`kdlock1` kernel afterward. Broader ownership transfer and pure-query changes
remain separate from this convergence test.

## Bounded image-capacity correction

The eight-lifetime cold attempt at runtime `15f1c08a` reached the existing
capacity limit. Its captured registry has 12 roots and a sum of 64 successful
published generations; 72 compiler jobs returned zero, leaving eight compiled
replacements unpublished. The daemon repeatedly reports `ENOSPC` from
`/dev/kd_dev`. `sys.c` returns it when `kd_image_alloc()` cannot obtain a slot;
`exe.c` fixes the shared descriptor count at 64. A replaced immutable image
remains occupied by design. This is a publication resource limit, not evidence
of duplicate history or failed source decoding.

The controller exited on its own learning deadline before the separate stop
attempt reached it; no signal was sent by that attempt. Exact subsequent
retirement records zero bindings/frames, normal daemon close and zero writers,
then terminal source retirement and normal unload. Normal kernel Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62` is verified idle at boot
`f15229a2-222b-494a-93e7-6216cbecfc94`. No online image reclamation is allowed:
zero frames and an inactive provider are not a general code-lifetime barrier.

The user authorized more image capacity. Select an explicit candidate build
with 128 descriptors, retaining the ordinary default of 64 and bounding the
build option to 1–256. Keep the 4 MiB slot size and all existing allocation,
publication, immutable generation and terminal retirement rules. There is no
growth or reclamation during a running session and no new allocation in a lock
hook. This is a general image-pool option, with no caller-specific behavior.

The observed 12/13 roots with an initial image plus up to eight learning
generations require at most 108/117 slots at that root count; 128 leaves some
headroom without the 2 GiB upper reservation of a 256-slot build. Capacity 128
uses up to 512 MiB ordinary and 512 MiB optional near storage, sharing 128
descriptors. Its descriptor/pointer arrays are 10 KiB on x86-64. The recovered
VM reported `MemAvailable=24265138176` bytes before this change. Record actual
allocations through read-only `jit_image_usage` under the existing publication
gate; do not treat this observation as owner or lifetime accounting.

Document the count option in a shared header and Kbuild, add the resource
observation, then run the existing image-capacity and immutable-image fixtures
plus a matching W=1 private-provider build on the VM. Check default 64 and the
selected 128 override, including invalid bounds. The registry-extraction fixture
must include the shared count header and run its production case at 128 as well
as the default; extracting only defines from `exe.c` would omit the new count.
The first VM preflight at `31710a60` passes the shared-capacity cases, then its
default registry fixture stops at the stale zero-gate assertion. Initialization
now takes the existing gate to enable resource observations; lookup remains
gate/pin-free. Keep that failed attempt and compare lookup counters with their
post-initialization baseline. No module build or live run began in that attempt.
Continue with new cold
thread/process sessions under the same eight-lifetime/1,800-second limits and
unchanged acceptance. Resource observations occur outside application timing.
Keep the failed 64-slot campaign separate and verify normal-kernel recovery
after the new candidate. No broader ownership-transfer change is included.

The captured current published mmap image at `0xffffffff817b6f68`, generation
6, has 1,100 decoded source bytes, 295 static instructions and 62 blocks; its
generated image is 11,352 bytes. The munmap image at `0xffffffff8181c73b`,
generation 5, has 2,405 bytes, 604 instructions and 147 blocks, generating
23,272 bytes. These complete selected graphs include learned callees but still
cover only part of the logical critical section. Generated sizes include the
wrapper, dispatch and metadata. They measure neither executed instruction count
nor critical-section duration or time ratio.

## Approved follow-on: permanent takeover and executor-local pure queries

The user selected immediate physical ownership transfer to O and immediate
requeue of a combiner's own pending request, with pure ownership/state queries
remaining on E through exact retained records. This replaces the earlier
one-operation O service followed by E resumption as the target for operations
that actually require O. It is a general protocol design, not an MM caller
adapter, and is not implemented by `15f1c08a`.

1. Classify the encountered operation before publishing a returning service.
   Preserve the first unexecuted source IP, current GPR/SP/BP, the existing
   arithmetic-flag contract, actual CALL/RET word effects, image and source
   references. General architectural flags/SIMD restoration remains deferred;
   these records do not establish that broader equivalence. The current
   `kd_exec_cont_native_prepare()` and `kd_exec_cont_memory_prepare()` create
   PREPARED state; `kd_exec_cont_handoff()` refuses those outstanding records.
   Transfer must precede preparation, or retire only an unissued preparation
   exactly. Completion helpers cannot clear it: they advance source execution.
2. Retain the full owner list, phase identities, nested parent/child records,
   source task/stack and final release obligations in shared request storage.
   Existing `kd_service_handoff()` retains E-owned gates and E-stack anchors;
   it cannot make E available immediately. In particular, a live
   `kd_service_native_spill()` record on E's stack blocks detachment until its
   storage/lifetime is redesigned. Never mark a retained physical owner released
   to make handback pass.
3. Transfer physical gates and selected writer/read custody with their exact
   owner and generation records before making O runnable. Publish a combiner's
   actual pending acquisition back into the common queue without replaying its
   body. An independent service worker has no own pending acquisition: it returns
   to dispatch, with no fabricated writer request. Detachable final ACK handling
   must retain old request storage until O's actual releases and retirement.
4. Preserve committed-acquisition priority over signals. Internal requeue cannot
   turn an already successful killable acquisition into `-EINTR`; an uncommitted
   request still arbitrates its origin's signals against actual readiness under
   the queue protocol, with exact cancellation/slot retirement. Nesting and
   out-of-order child completion retain their existing identity obligations.
5. A downgraded read tail may stay on E under the approved general protocol.
   Release its read credit before E acquires any pending writer phase, which
   freshly drains readers. If takeover transfers that read custody to O, E's
   subsequent writer waits for O's actual read release. Keep atomic-compatible
   `up_read` and positive reservation cohorts distinct from the selected phase.
6. Keep pure queries on E using the bound continuation's logical O, committed
   admission, exact physical owner and selected phase. The current
   `kd_service_write_owned()` initially requires `task == current`; directly
   calling it on E with logical O would falsely return false. Add the explicit
   executor query route while preserving ordinary caller behavior. Keep the
   three selected public query bodies in the original JIT and preserve their
   existing operation identities. Neither counters nor a generic locked bit
   replace the exact ownership proof.

Focused follow-on checks must distinguish a true combiner's requeued request
from an independent worker, cover committed/uncommitted killable and nested
ownership, and establish physical transfer plus final ACK/slot reuse. Pure
query checks need different O/E tasks and stale identity/phase observations.
Mmap1 application completion remains separate from proof that E executes the
read tail and subsequently acquires a fresh writer phase. Keep the separately
blocked retained-continuation fixture out of this validation step.
# Focused writer-entry selection

The next isolated candidate starts from
`4eb5a2f5a017686a1edeaef66503c4f6ac7d06cf` on
`codex/mmap-reached-jit`. The completed 128-slot experiment returned to the
ordinary development kernel. Its eight thread applications passed and drained,
but image changes prevented a scored point: 108 serial compilation jobs took
1453.958 seconds, while application lifetimes totalled 64.297 seconds.

Add the optional, load-time-only `rwsem_provider_entries` array. An empty array
preserves unrestricted entry selection. Every supplied entry must be unique,
nonzero, and present as a supported writer in the running kernel's builtin site
table. Validate this before registering the provider's instruction services.
The benchmark records the complete selected list and exact module parameter in
its execution receipts; its registry checks admit only entries in that list.

For this bounded comparison, select `0xffffffff817b6f68`
(`vm_mmap_pgoff+0x118`) and `0xffffffff8181c73b` (`__vm_munmap+0xbb`) from the
matched scope5 kernel. These code sites also serve activity outside the timed
loop, so selection is not worker-only attribution. Default behavior remains
unrestricted. No application or MM body is changed.

Apply selection in `kd_provider_capture`, before `kd_service_capture_bound`
can capture, register, or publish a request. An excluded entry must execute the
callable local KD acquisition matching its wait state: ordinary,
interruptible, or killable. Return zero only after acquisition, or the actual
acquisition error. There is no Boolean decline and no alternate Native lock on
the same object. Provider binding, prepared capability, local/delegated phase
selection, unlock, downgrade, cancellation, and retirement remain unchanged.
Preparation and non-demand readiness checks operate on selected entries while
retaining validation of the builtin table.

Nested locks are not assumed absent. The existing service path retains nested
owners and resumes the same frame/image; this candidate does not add a child
image switch. Allocator, page-table, anon-vma, and per-VMA protocols retain their
existing handling. Each image ending at its own matching release, child-image
return routing, image storage reuse, and CFG limits remain separate designs.

Focused validation first covers default and selected preparation/activation,
invalid entry sets, excluded local success/cancellation, and selected capture
routing using production functions. Run the directly affected receipt checks
and a W=1 provider build in the VM. Live checks must retain Native API ordering
and exact source/frame/binding retirement. A later fresh comparison retains its
one scored round per point and existing learning bounds; selecting two entries
does not guarantee stability or performance acceptance.

The first scope preflight at `c66af150a83f8dd324003ef699dd03fc389846c3`
passed the four affected benchmark/provider receipt groups, then stopped before
the module build: the standalone rwsem API fixture lacked declarations for
the existing `kd_exec_native_service_unlock` route and its operation enum.
Update the fixture to import the production enum and explicitly model its
local-only, unregistered route. Keep its ownership, release, downgrade, error,
and emitted-ABI assertions; the failed attempt remains retained evidence.

Cold learning may have no selected images yet, a partial registry, or an entry
that remains local. These states are not a two-entry JIT timing point. Before
a scoped scored application starts, require exactly the selected entries and
NORMAL images with nonzero code addresses and generations for both. This is
image readiness only; it does not replace worker-attributed execution proof.

The `19e591aa90f08da08be2162009db720ec2112f6c` repeat passed the public rwsem
facade runtime assertions. Its emitted-control expectation then found the
existing `PUSHFQ` / flags-bank store before the three control-transfer
instructions. Require that complete five-instruction sequence instead of
omitting the flag-save contract. This changes only the fixture expectation;
no lock or code-generation implementation is changed.

The completed scope experiment and all preliminary rates are recorded in
[the fixed scope report](../../bench/results/10.176.26.71/tests/mmap1-entry-scope-130b6593/README.md).
Runtime source `130b65939053026339014833774e5fb11b234972` passed focused
component checks and both unscored local application checks. Each JIT comparison
then completed eight learning lifetimes and stopped with `LEARNING_ADVANCED`:
18 successful compilations and two generation-9 roots per model, zero scored
points. Both sessions retired normally and the ordinary kernel was verified
idle. A smaller preparation scope does not establish throughput acceptance.

# Per-acquisition image regions: design review

This follow-on uses the same branch and the original JIT backend, starting
from the scoped runtime above. The user approved bounded segments within one
acquisition region. Segments remain inside that region and end at its matching
release; an image must not contain its own post-release continuation. This
does not select a numeric CFG cap. The user selected separate child images for
selected KD acquisitions initially; allocator and other Native locks retain
their existing instruction-service handling. Code for these transitions has
not been implemented.

The boundary applies to translated source instructions. Generated entry/exit
controls and metadata remain necessary, but cannot execute another source
instruction beyond that region's release. Each child entry and parent join
must retain compatible IRQ/BH/preemption and CPU-local state. An image boundary
does not permit a sleeping acquisition inside an existing atomic interval.

An outer region A can suspend at a reached acquisition of B. A retains its
exact owner, source/stack lifetime and immutable image version. B has its own
request identity/generation and image family, while the root keeps one shared
canonical register/stack packet. Only the current packet owner may change it.
B's resulting registers and memory effects continue into A; restoring A's
pre-child packet would discard real execution. Internal child-image entries
must have a distinct family identity so the two-entry public root scope still
rejects unrelated startup captures.

The integer clobber ABI has two different PCs. The actual CALL word is the
literal return PC used for cancellation. A capture-capable API also supplies
the success entry separately in RDX; its success label can clear EAX. Preserve
both values and validate the supplied entry against the declared ABI/site.
Never derive it by adding a constant to the literal return PC, and never use
the success label on cancellation. INTEGER-only callable APIs do not acquire
a capture label merely because they return an integer.

On failed B admission, observe the original task's signal under the existing
grant-first queue arbitration, finish exact cancellation retirement, consume
only the pending acquisition CALL word, and continue A at the literal return
PC with the error. B's body and success label must not execute. On success,
consume that acquisition word exactly once, preserve successful-acquisition
priority, and enter B through its validated success entry when its ABI has one.
`kd_exec_cont_child_acquired()` currently selects the literal return PC, so it
needs an explicit capture-aware adapter before it can select B's image.

At B's matching release, a child-scoped service completion validates the
terminal CALL and physical release without popping that CALL word. Child
return then consumes the release word once, transfers packet custody, and
resumes A at the first unexecuted source instruction after B's release. That
join is inside A and outside B. It is not B's acquisition-return PC. Retain
separate acquisition and terminal-release transactions; a COMPLETE phase alone
does not establish the correct join. A's continuation must be admitted by its
pinned image family, with reached learning supplying a bounded segment later
when that join has not been compiled.

The existing `kd_exec_cont_child_begin/acquired/return` helpers provide useful
packet and state operations, but the live `kd_service_nested()` still acquires
into the root scope and resumes the same root image. A new adapter must give
each child its own service scope. Current callbacks recover a root structure
from root-only identity, and retained entry currently requires an independent
`source_lease` even though generic children borrow their root's lease. Replace
these assumptions with exact root/parent/generation validation, preserving
the root lease until every child, Native service and final ACK has retired.
Do not compose the current acquisition service completion and child-acquired
helper blindly: both paths can consume the acquisition CALL word.

Downgrade changes the held phase of the same region. Its delegated read tail
can continue in bounded segments on the executor and ends at that acquisition's
matching read unlock. The read credit remains live until then. A subsequent
writer takes fresh admission and drains readers normally; it must not reuse
the former writer phase or overwrite an outstanding positive cohort.

If B's image or A's post-child join is unavailable, hand the entire active
region stack permanently to the origin for this invocation at the first
unexecuted point. Preserve all parent/child/image/source references and publish
one Native acceptance. A pending acquisition, a committed success entry, and
an already completed child unlock require different packet/CALL-word states.
Do not replay a committed operation or return from a missing child interval
to A on the executor. The legacy missing-continuation status currently reaches
an unsupported path; a valid completed-control handback must be added explicitly
instead of globally reinterpreting that status.

The user selected continued B delegation for an API-valid non-LIFO release.
Releasing ancestor A while B remains held must mark A's region closed without
allowing A's image to execute after its release. A's storage remains retained
for B's references and outstanding ACKs. Keep region liveness separate from
owner-storage retirement and skip closed ancestors on return. B continues on
the executor while its own region remains live; this case is not a reason to
hand the invocation back. Existing root-wide all-released tests cannot be used
as each image's release boundary. This selected transition is still design,
not an implemented or validated feature.

Typed release controls are segment frontiers. Runtime exact owner matching
distinguishes the current region's release, an ancestor's release and another
nonterminal operation. After an ancestor release, B's next segment starts at
the actual post-release source PC with B still live. After B's own release,
select the nearest open ancestor, skipping closed A. Retain the canonical
packet instead of restoring an old ancestor snapshot. Separate image-region
closure from final frame/storage retirement and physical release ACKs.

# Bounded learning allowance after the two-entry audit

The retained histories show six distinct mmap CALL additions and two distinct
IJ edges, plus eight distinct munmap CALL additions. All 18 jobs per model
succeeded. Eight changed learning lifetimes publish generation 9 only after
the eighth application ends; the old eight-round cap cannot even test that
generation. This is evidence of continuing incremental coverage, not duplicate
target churn. The scalar miss report may be overwritten by already admitted
frames, so it is not a record of the first miss or every dynamic miss.

Raise the optional learning-round maximum to 32, preserving the existing
default of three and the independently bounded learning deadline. The focused
configuration retains 1800 seconds. Keep the same provider, daemon, source
leases, immutable images and history from learning through timing; do not
restart them at an intermediate generation. Require exact selected entry
identity, source quiescence, usable NORMAL images and an unchanged registry
across a complete application lifetime before the single scored application.

With the observed one update per selected root per lifetime, 32 lifetimes
would occupy 66 images, within the existing 128-slot pool. That observation is
not a universal allocation bound. Keep actual capacity, deadline and lifetime
failures explicit; do not reclaim published images, suppress a failure or
weaken the stable-epoch gate to obtain a score.

Do not copy unversioned IJ addresses from the retired runs into a new session:
the callback target `0xffffffffc0e31d50` belongs to a loaded module instance.
Fresh sessions must obtain current targets and source residency. A longer
bounded live learning phase avoids that stale-instance issue without changing
the lock implementation. Quiet timing and a separate worker-attributed proof
remain distinct evidence. The current false proof field is not itself the
learning failure, and it does not establish that no delegation occurred.

# Persistent scaling and separate execution proof

Use the representative initial grid `1,2,4,8,16,32,36,60`, one scored round per
point, for threads and processes separately. This is a subset of the standard
21-count grid. Workers retain CPUs `0..N-1`, collector 63 and the declared
executor pool `0-61`. Count 36 is the first selected cross-node point. Native
uses the same scope5 kernel Build ID with `kd_mmap=off`; the ordinary development
kernel is a different build and is not its matched control.

Keep one provider/daemon/source session across both KD models and all counts.
Learning snapshots and quiet timing receipts are per count, while workspace,
current images and append histories remain live. Track the actual 128-slot
pool across the entire campaign and bound total learning wall time; a per-count
round allowance must not imply unlimited cumulative generations. Keep every
partial valid point and every stopped/unrun count explicit if capacity or the
deadline prevents completion.

Before quiet timing, compose the existing worker-identity diagnostic on two
workers in the same image session. While the factory is inactive, load the
existing `kd_mmap1_identity` observer and continuous bounded log collector.
Enable `service_trace`, activate, take a new exact receipt, and run unchanged
mmap1 with `diagnostic=True`. Preserve stable STOP snapshots and apply the
existing delegated-root, instruction-service and syscall-pair validators,
including the downgraded read tail and later same-executor writer evidence.
Then deactivate, remove the observer in its documented order, disable trace,
prove quiescence, and take a new quiet receipt. Do not reload the provider,
restart the daemon, reuse stale image addresses or count diagnostic rates as
timing data. A proof with different image generations needs revalidation.

Record requester CPU time with its existing whole-lifetime scope. Optional
exact executor task/start-time CPU snapshots and guest CPU counters can add a
whole-lifetime view including executor work; they are not measurements of the
two-second scored interval or critical-section ratio. Idle executors sleep on
work-sequence changes, so their count alone does not establish spinning cost.
The quiet observation build suppresses routine diagnostics; its parameter
values do not establish that every instrumentation write is absent.

The scaling controller uses an explicit translation phase barrier. At verified
quiescence, stop the exact idle daemon and verify its stopped state before
activating the factory and starting an application. After that application
drains, deactivate the factory before continuing the daemon and settling image
updates. This keeps compiler CPU outside application lifetimes and prevents
compiler children from receiving new provider-bound MMs while learning.
Keep the same daemon PID, device description and workspace throughout. Quiet
timing also keeps translation stopped and still rejects every registry change.
For cleanup, send termination before continuation so a stopped daemon cannot
start another compiler child between resume and the existing stop check.

Before each new application, require the declared 128-slot capacity, no private
images and at least one free descriptor per selected root. Translation remains
stopped throughout that application, so its reached-path reports cannot cause
publication until all application frames have drained. Every quiet application
still requires an unchanged exact registry. The learning deadline bounds entry
to learning and proof attempts; ordinary bounded application and cleanup waits
may finish after that deadline. This is not an asynchronous termination timer.

Accept execution proof only after its application drains, the idempotent STOP
snapshot and lifecycle STOP summary agree, all existing worker and continuation
validators pass, and the complete collector reports no fault or collection
loss. Preparation failures and unknown application lifetimes retain their exact
stage and live state. A fresh process verifies the recorded registry and source
ledger before ordinary retirement; partial results remain distinct from passed
and drained campaign completion.

If a pause attempt observes a child after the daemon stops, keep the observed
stopped state. With the factory inactive, application drain known and no live
frames, resume that exact daemon to reap its child before ordinary shutdown.
A stopped parent cannot retire an unreaped child merely by waiting in the
controller. Unknown application or frame lifetimes still retain live state.

# Reached warning-path frontier after the bounded scaling run

The `f9fdaa2aa6a71ca0b03dd3a859d63bf746c0983a` campaign completed 32 drained
learning lifetimes but produced no quiet point or worker proof. Its mmap root
reached generation 33. Munmap stopped at generation 19 and became Native-only
when an expanded graph could not decode `0xffffffff81817f57` in `__split_vma`.
There were 76 free image descriptors; neither the image pool nor the text-byte
budget caused that refusal. The complete outcome is retained in
`bench/results/10.176.26.71/bench/mmap1-scaling-f9fdaa2a/README.md`.

The disk ELF has a CALL to `__SCT__WARN_trap` at that site; the live instruction
bytes were not retained. Capture the exact bounded bytes through the existing
source lease on the matched Build ID before choosing a decoder correction.
A subsequent boot's capture is a reproduction, not proof of the old boot's
bytes. No further cold benchmark or larger cap is justified by this result.

If the exact form requires original-site execution, represent it as an
explicit reached source frontier in the retained ABI2 backend. Decode its exact
length and terminate only that generated branch. Reaching the frontier exports
the first unexecuted original IP, unchanged source SP and current flags/GPRs;
it must neither push nor consume a CALL/RET word. The existing owner handoff,
source/frame retention and unlock ACK protocol then completes this invocation
on the original task. Other branches remain eligible for JIT execution. Do not
copy a warning instruction to another address: the original site identifies
its kernel record.

Keep this frontier separate from the legacy instruction-marker image class,
which rejects retained-service combinations. Negotiate the added control in
the existing image requirements/capabilities so an older runtime refuses an
unsupported image before execution. Reuse the original JIT and retained
handoff machinery; no instruction interpreter or caller-specific MM path is
introduced. Killable admission, nested owner records, downgraded read credit
and exact retirement remain unchanged. Validate branch-not-taken completion,
branch-taken packet state and original-site identity before another focused
mmap1 attempt. At the end of that scaling run this was a design only. The
implementation and its validation scope are recorded under
[Authorized original-instruction frontier](#authorized-original-instruction-frontier)
below; the earlier run remains unscored.

The bounded reproduction on matched Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, boot
`c301906d-c322-47a2-9e9e-a0840f4401d6`, captured `67 48 0f b9 3a` at that
site and reproduced the pinned decoder's failure at offset 2. The exact source
path is the file-reference diagnostic in `file_ref_inc()` through `get_file()`
inside `__split_vma()`. Its increment has already occurred before the diagnostic
branch. A reached frontier must preserve that effect and resume at the original
UD1 site without replay. This new boot is a reproduction; the earlier boot's
bytes remain unavailable. Capture, source evidence and normal restoration are
retained in
`bench/results/10.176.26.71/tests/mmap1-warning-form-f9fdaa2a/README.md`.

The mmap root's 28 distinct CALL targets and four distinct IJ edges are not
evidence of duplicate learning. Both `master` at
`20fde062729703208ac54445f51fc0f21f24e0e8` and this candidate keep
`mdis.follow_call = False`; this candidate also has `direct_call_closure = False`.
Do not restore the intermediate eager closure experiment as a latency fix.
The shared entry can encounter startup/file-backed mappings as well as worker
anonymous mappings. Once a callee is learned, its decoded conditional paths
can expose more source even when a particular branch was not taken.

Retained `critical_section_blocks(..., runtime_delimited=True)` uses unknown
lexical depth and keeps a finite graph beyond possible releases; exact runtime
owner matching ends actual execution. Post-release code in an emitted image
is therefore a real boundary-design limitation, but it does not prove that
those instructions caused an observed miss. Direct CALL history records only
the target, with no exact caller PC/task lifetime, so the current artifacts
cannot assign every addition to an acquisition-to-release interval or worker.
The latest `can_vma_merge_right` addition is also a normal MM merge helper;
long learning alone does not show irrelevant work.

For the next scoped diagnostic, retain the already checked literal CALL return
word together with the current source image, logical origin lifetime, target,
owner region and operation kind. Record it at the reached miss before any
handoff, without inventing an IJ edge or changing normal CALL stack effects.
Only that joined evidence can attribute a direct frontier to a specific region.
Per-lock segments and child-region transitions remain the separately reviewed
design above; neither a root-wide arbitrary cutoff nor pruning a cold branch
implements them.

# Opt-in syscall-argument selection for the bounded benchmark

Keep the warning-frontier proposal above on hold. Independently narrow public
capture with a default-off, immutable `rwsem_provider_syscall_shape` benchmark
parameter. This is eligibility selection before capture/registration, not an
MM backend switch or a change to the general lock protocol. It composes with
`rwsem_provider_entries` and requires explicit entries plus demand preparation.
The default remains unchanged. Publish a getter-only contract version `1` and
bind the enabled policy, version and exact provider binary in execution receipts.

At the original-task public `kd_provider_capture()` boundary, read the current
task's saved userspace syscall frame. Refuse benchmark eligibility for kernel
threads, missing user MM, non-user frames, compatibility syscalls and syscall
numbers outside native64 mmap/munmap. Do not read the KD virtual packet or apply
the predicate to internal nested-service admission. Rejected captures call the
same local KD writer API already used for excluded entries; do not modify
`use_kd`, provider binding, `prepared_writes`, queue ownership or read drainage.

The version-1 argument envelope is:

- mmap: native64 syscall, address hint zero, length 128 MiB, protection exactly
  read/write, flags exactly private/anonymous, low 32 bits of fd equal to -1,
  and zero offset. Both sign-extended and zero-extended fd representations
  retain the Native argument interpretation.
- munmap: native64 syscall, nonzero page-aligned address and length exactly
  128 MiB. This is deliberately only an address/length test.

The retained unchanged `tests/mmap1.c` uses this mmap tuple and unmaps its exact
returned address. The stateless munmap predicate cannot prove that pairing,
mapping type or file provenance; an unrelated file-backed 128 MiB munmap can
still pass. Do not name or report this as exclusive worker/pair admission.
Existing worker/MM identity and syscall-pair validation remain mandatory for
delegation proof. No VMA walk, per-task pair tracker or new lock is introduced.
This filter does not resolve the cold warning decode or implement per-lock
image boundaries, and it does not justify another cold 32-run campaign.

Delivery order is documentation, predicate/receipt implementation, production
component checks and module build in the VM, then short actual-syscall checks.
The focused matrix covers default-off behavior, exact and near-miss tuples,
both fd representations, native64/compatibility/kernel contexts, local
killable/interruptible returns and unchanged successful-acquisition priority.
Live checks must show excluded startup/file-backed mmap cannot register a new
root, matching anonymous mmap/munmap remain eligible, local API results remain
correct, and exact retirement/normal restoration complete. These are selection
and API checks, not returned-JIT, throughput or full delegated-mmap acceptance.

Implemented at `4506f6e46394133e439f68a04d6fde38aea0885f`. The VM build,
55 Python cases, compiled rwsem API/ABI checks, six actual-syscall checkpoints
and one unscored two-worker lifetime for each mmap1 model passed. The existing
identity observer confirmed route 2, shared thread MM and distinct process
MMs. No translator ran and both entries stayed UNINIT, so no delegated body or
performance result is claimed. Exact retirement and normal restoration passed.
The file-backed 128 MiB munmap was eligible, confirming the stated limit.
Evidence is retained in
`bench/results/10.176.26.71/tests/mmap1-syscall-shape-4506f6e4/README.md`.

# Resolver preparation cost, measured separately

The normal-kernel resolver reproduction under
`bench/results/10.176.26.71/tests/symbol-lookup-normal-a46ff2ec/README.md`
measured 138 ordered symbol requests with the unchanged resolver and a
helper-only first-match snapshot. All results matched. One original-first
pair took 14.588 seconds versus 0.256 seconds, including snapshot construction;
symbol-file opens fell from 138 to one. This is metadata lookup cost, not a
complete compiler or mmap1 throughput measurement. Missing KD symbols on the
normal unloaded kernel make retrospective attribution to the earlier enabled
campaign invalid. That measurement made no production resolver or JIT change.
At that point the warning frontier awaited review; its later implementation is
recorded below. Child images remain initially scoped to selected KD
acquisitions as specified above, and their transitions remain unimplemented.

# Per-translation core symbol reuse: candidate design

Baseline `be0fd17bd7f10b49ae2776a9b7ccc37a797bdd45` still performs a live
symbol-file scan for each request. The proposed optimization belongs only to
translation preparation. It must not change decoded scope, generated code,
runtime ownership, admission, publication, or validation. The full-table helper
prototype above is not suitable as production behavior: a new module can
change the first matching dynamic symbol or make a previously absent name
available. Source pins retain accepted ranges, not the entire name space.

Use a fresh cache context for each `dis_assem()` invocation, after the CLI has
entered its validated device session. Fill lazily at the first real lookup;
direct calls without a validated lease retain the old live resolver. Clear the
cache on every return or exception. Nested invocations get independent caches
and restore the outer context on return. Never reuse entries between images,
translations, provider sessions, or processes. Existing callers that replace
`get_kernel_symbol` for a fixture continue to intercept every request.

Cache only positively resolved entries in the fixed core prefix through its
first `_etext` row. The matched Linux 7 `kernel/kallsyms.c` emits its fixed
`kallsyms_num_syms` core section first (`update_iter`, lines 725–738), then
module and additional dynamic sections (`update_iter_mod`, lines 705–722).
`scripts/kallsyms.c` retains `_etext` even without all-symbol enumeration, and
provider initialization already requires coherent positive `_stext`/`_etext`
values. Require those markers in the collected prefix, with
`0 < _stext < _etext`, and commit the prefix only after successful close.
An owner field before the marker, absent/zero/malformed markers or any observed
read/close error discards the tentative prefix and keeps live lookup.

Do not infer core provenance merely from a missing owner field. A module that
has reached COMING can briefly emit rows with an empty name before later
validation. It still follows the entire fixed core section, including the
built-in `_etext` marker, so stopping there excludes those transient ownerless
rows as well as ordinary module and generated rows. Later core data and any
other rows after the marker remain live. Keep the first raw token for each
name; only the fixed markers are parsed during fill. Other hexadecimal
conversion remains request-local, preserving duplicate priority and malformed
matching-token errors.

Module/dynamic names, missing names and zero-address names always use the
unchanged live scan. Never store a negative result, a module result or a
caller's default in the reusable lookup result. A new module can therefore
turn a miss into a hit, replace the first dynamic match, or remove a previous
hit during the same translation. A later module cannot precede the fixed core
section. Existing source pinning before text reads and service-owner retention
remain mandatory; a symbol address alone never establishes residency.

On an observed cache-fill open, iteration or close error, discard the partial
cache and use the original live resolver for the current and subsequent
requests. The fill is a preparation probe, not a cached API result; the current
request's fresh live scan retains its own first-match, default and error
behavior. Do not eagerly convert unrelated malformed tokens. Failure must not
cache a default or persist into the next translation.

Value equivalence assumes the same boot and unchanged translator credentials
and symbol visibility. A reused positive core entry does not observe a later
file-read error or visibility change because it does not repeat that read.
Literal equivalence to arbitrary future I/O failures cannot be promised by
such a cache without repeating the original reads. An unsuccessful preparation
probe followed by a fresh live scan is also an extra I/O attempt compared with
the original resolver. These are explicit environment/measurement limits,
not reasons to cache dynamic or missing names. Do not describe the candidate
as freezing the live symbol table.

The focused checks cover dynamic insertion, replacement and removal, a new
module shadowing a dynamic name, transient ownerless rows after `_etext`,
absent/zero/malformed/misordered markers, core priority, zero versus missing,
distinct defaults, malformed raw tokens, partial reads, open/close failures,
cleanup on all exits, nested scopes, and the existing mocked translator lookup
boundary.
Then compare one full compilation per arm on identical live leased text and
identical retained histories, with no publication or application execution.
Include dependency startup, decoding, lowering and assembly in that comparison;
require matching return status, selected text coverage and generated artifacts.
Retain all failures. The warning frontier remains unchanged and on hold.

Implemented at `26337db1d722e3f7a239d703496197658bee05e8`. The VM passed
26 resolver cases and 13 JIT diagnostics cases. The context-policy driver
retains four identical baseline/candidate failures involving the existing
8192 requirement bit; they remain unresolved. One complete baseline-first
compiler pair per selected MM root, using fresh empty histories, produced
identical lookup results, coverage and all four generated artifacts. mmap
compilation took 13.375 to 7.765 seconds and munmap 13.323 to 7.715 seconds,
with 137 lookups but 49 rather than 137 opens. Per-child peak RSS increased
about 23.4 MiB. No publication or workload ran, so this is cold-history
compilation evidence, not mmap1 runtime acceptance. Exact retirement and
normal restoration passed. Full results and retained failures are in
`bench/results/10.176.26.71/tests/core-symbols-26337db1/README.md`.

# Authorized original-instruction frontier

The user authorized the pending warning-path handback and mmap1 validation.
Start from `c919bd81871d77c7f37a2f8a06fc1e2aa9f5e164` on
`codex/mmap-reached-jit`; retain the core symbol optimization. This is a general
retained ABI2 instruction frontier, with no MM caller special case.

At an instruction actually requested by the existing decoder, recognize only
the complete `67 48 0f b9 3a` form. Represent its five source bytes as a terminal
instruction in that branch. Do not scan source windows for byte patterns or
expand call closure. Other branches keep their ordinary JIT execution. The
frontier has no generated successor, source CALL word, instruction service or
learning report. It never executes or emulates the original instruction.

Negotiate provider capability version 18, feature `KD_JIT_CAP_SOURCE_FRONTIER`,
and image requirement `KD_IMAGE_REQUIRE_SOURCE_FRONTIER` under the existing
extended header. A frontier image requires ABI2 mutex continuation and the
retained service queue. Earlier providers cannot accept that image. Give its
generated FULL return a distinct `KD_EXE_SOURCE_FRONTIER` outcome; it is not
`KD_EXE_RETAINED_MISS` because that outcome necessarily requests learning.

Generated code spills logical GPRs, retains virtual SP/BP and exports the exact
unexecuted source IP. Preserve the existing arithmetic-flags export without
claiming new flags, SIMD or IRQ/NMI support. Runtime checks the executed FULL
packet, matching immutable image/entry/ABI, logical origin, idle typed-call
state, no pending remote/native operation, original stack bounds and the exact
five-byte leased source range. Refuse any mismatch before changing the packet
or ownership. Do not replay the preceding `file_ref_inc()` increment.

On success, set the existing `KD_REG_ORIGIN_SUFFIX_TAG`, save continuation and
return `KD_EXE_RUN_HANDOFF`. Reuse the established retained handoff with its
exact owner records, suspension, Native ACCEPT, source/frame retention and
final owner/unlock ACK. A typed service scope with `api == KD_SERVICE_NONE` is
valid. Do not route through the legacy borrowing check, which intentionally
rejects these linked service-owned records. No registry state or image
generation changes merely because this permanent frontier was reached.

Complete the implementation before focused VM checks. Verify exact IP/SP/GPR
and preceding once-only effects, branch-not-taken JIT completion, no false
learning, unsupported-provider refusal and retained-owner lifetime. Then
resume the benchmark-filtered two-root mmap1 campaign using fresh module
identities, separate learning/proof/quiet intervals and the preserved matched
Native measurements. Require real worker-attributed delegation evidence;
compilation/publication alone is not proof. Retain every failure and restore
the verified normal kernel after validation. Do not merge.

Implemented at `d57f7523f4d6438e4c31a840524f48bc7413fb56`, with terminal
metadata and fixture corrections through
`99958c7d4d79bc9ddcdac290b51ed0bd40328487`. The generated-state driver passed
five cases in the VM; the retained join passed write, downgrade and read
completion with supplied physical/task primitives. The provider, daemon and
observer built. These establish the focused component behavior, while actual
MM execution and throughput require the separate worker-attributed campaign.
The text-region driver retains seven failures and one error reproduced on its
baseline. Exact scope, identities and earlier failed attempts are recorded in
[the focused frontier report](../../bench/results/10.176.26.71/tests/source-frontier-99958c7d/README.md).

# Bounded application learning after the frontier correction

The `99958c7d4d79bc9ddcdac290b51ed0bd40328487` campaign completed 32 passed,
drained applications and 57 successful compilations. Both roots remained
NORMAL at generations 32/25. Distinct CALL/IJ additions account for every
generation, with 71 image descriptors still free. Munmap stopped advancing
within that run; mmap still added VMA merge helpers. The harness reached its
32-application allowance before its separate execution proof or quiet scoring.
Exact retirement and normal-kernel restoration passed. Preserve the failure
and all unscored rates in
[the campaign report](../../bench/results/10.176.26.71/bench/mmap1-frontier-99958c7d/README.md).

For the next isolated benchmark candidate, accept an explicit learning
allowance of at most 64 application lifetimes, with the default still three.
Keep the campaign's 1800-second global learning deadline and its independent
controller/launcher time bounds. Keep the 128-slot capacity/headroom guard,
original decoder/CFG bounds, miss semantics, per-lock scope, exact registry
checks, worker-attributed proof, and one scored round per point unchanged.
This adjusts preparation, not the lock protocol or proof requirement. Start
with fresh module/source identities and empty CALL/IJ histories; never rebase
old module addresses into a new session.

Emit concise learning start/completion records through the existing controller
output, after each drained application, so the source-host log exposes registry
generations and remaining advancement without a guest inspection process.
Printing these preparation records does not enter a quiet scoring interval.
Append tables lack per-edge task/lock-phase provenance; this change does not
prove region leakage absent or live diagnostic handback complete. Another
actual defect must be diagnosed rather than hidden by extending these bounds.

The `cfdb52a83e98eed140062bc83c51207579242392` follow-on passed 20 affected
benchmark checks and rebuilt its provider, daemon and observer. Its 50 passed,
drained learning applications reached mmap generation 48 and munmap generation
25. The next mmap compilation planned 270,336 cached bytes against the
unchanged 262,144-byte limit, although decoded instruction bytes totaled
28,327. It became Native-only before proof or scoring. There were 55 free
image descriptors. Exact retirement and normal recovery passed; the negative
outcome and all unscored rates remain in
[the follow-on report](../../bench/results/10.176.26.71/bench/mmap1-frontier-cfdb52a8/README.md).

# Bounded original-JIT prefix at the source-cache boundary

This alternative was documented but not implemented. The user's later
direction selects the active aggregate-limit correction below for the next
test, without adding an image-retention command or learning latch.

Continue on `codex/mmap-reached-jit` from
`cfdb52a83e98eed140062bc83c51207579242392`. The user selected reached execution
over auditing unexecuted branches. A source-cache budget decision is distinct
from an unsupported source/ABI or ownership decision. Preserve complete valid
JIT work and use the existing retained waiter continuation when actual
execution reaches an uncompiled target. Keep source/stack ownership and prior
effects, including an already pushed CALL word or popped RET word. Do not
replay the acquisition region or earlier stores.

First, allow an explicit ordinary bounded-window policy to reduce only new
optional lookahead when a plan exceeds 256 KiB. Keep the preferred 8 KiB,
page-aligned read unchanged when it fits. Plan shorter tails before requesting
a lease or reading text; retain every existing byte/root and at least the full
15-byte instruction prefix at each new target. Keep pin-before-read, the
256 KiB aggregate/per-request bounds, 32 combined CFG transitions, 33 decode
passes, return-flow work and `follow_call = False`. The existing 1 MiB retained
policy and retired eager profile are not selected.

If even mandatory data cannot fit, return a distinct translator budget outcome
and clear partial output artifacts. The daemon must retain only the currently
published complete immutable ABI2 image with the retained-miss contract, matched
by entry/ABI and exact base generation under the existing publication gate.
Source closure, a terminal Native-only decision, a missing/mutable image or a
changed generation must refuse retention. A budget result never validates a
new incomplete image. An initial failure without any complete image remains an
explicit preparation limit, not claimed delegation.

Mark learning closed for that exact retained image and restore its NORMAL
readiness without changing code, generation or source ownership. Suppress only
future CALL/IJ learning reports from that limited image, with a recheck under
the publication gate, so a racing miss cannot reopen compilation. Terminal
semantic/source refusal continues to win. A stale executor cannot change a
new image. Expose the bounded state separately from the NORMAL publication
state, and negotiate the added header-only budget operation. Keep the existing
miss packet validation and Native ACCEPT/final ACK unchanged. Uncompiled paths
permanently continue on their origin at their exact current target; compiled
paths keep using the original JIT.

Focused checks cover the actual oversized-window arithmetic, largest fitting
optional tail, complete instruction prefixes, preservation of old bytes/roots,
mandatory-over-budget refusal before reads, exact-generation image retention,
Native-only/source-close/stale-image refusal and repeated-miss suppression.
Reuse unchanged continuation checks by hashes. Then build and run fresh-identity
mmap1 checks. Report worker-attributed prefix execution and original-task
continuation separately from a fully delegated read tail; compilation alone
does not establish either. Keep every incomplete/negative result and restore
the normal kernel. No caller-specific adapter or second execution backend is
introduced.

# Active aggregate text budget: selected 1 MiB correction

The user authorized a reasonable increase for this test. At
`cfdb52a83e98eed140062bc83c51207579242392`, `disassem/memread.py:13` sets the
active `MAX_TEXT_BYTES` to 262,144, while line 14 independently defines
`RETAINED_MAX_TEXT_BYTES` as 1,048,576. `disassem/disassem.py:349` keeps
`direct_call_closure = False`, so lines 352-353 select
`DEFAULT_WINDOW_POLICY`, and `extend_regions()` uses `MAX_TEXT_BYTES`. The
existing 1 MiB retained constant is not the active original-JIT budget.

Raise only `MAX_TEXT_BYTES` to `1024 * 1024`. Keep the active policy's
8 KiB lookahead and 4 KiB alignment, without compact-policy selection, eager
CALL closure or a different backend. Keep 32 combined CFG transitions, 33
decode passes, return-flow work and lock-region scope. This directly admits
the observed 270,336-byte plan under a bounded 1,048,576-byte aggregate.

`MAX_SOURCE_READ` and `KD_SOURCE_MAX_READ` remain 262,144. A merged cached
region larger than that must be read in consecutive pieces, each pinned
before its read, with complete concatenation or an error. `KD_CODE_BLOCK_SIZE`
remains 4 MiB per image; the selected pool remains 128 descriptors. Neither is
the aggregate source-cache limit. Existing CALL/IJ/RET miss handback, source
validation, current-state retention, owners and final ACK remain unchanged.

Focused VM checks must show that the reported 241,664-to-270,336-byte plan now
fits, that exact 1 MiB fits but one more mandatory byte refuses before reads,
and that requests remain at most 256 KiB with unchanged complete-source
behavior. Preserve the previous result and known unrelated driver failures;
reuse unchanged runtime checks by hashes. Then use fresh identities/histories
for mmap1, with progress, worker proof, partial/native-continuation coverage and
scoring reported accurately. Restore the normal kernel afterwards. No merge.

# Short preliminary mmap1 pilot

The user prioritized quick performance observations over full preparation and
matrix coverage. The long `f2d9caf3fca0cd69b38b8b2ea5d18422cbf16e22` run was
ended through the owned daemon's ordinary termination/continuation sequence
with zero frames and no compiler child. No workload received a signal. Its 33
completed learning applications remain separate from the final stop-affected
application. The last completed one-worker thread rate was 195,366 pairs per
nominal second, with roots advancing 32-to-33 and staying at 25. All completed
applications passed and drained; none has worker-attributed delegation proof
or a quiet score. Exact retirement and idle passed.

Add a diagnostic pilot around the existing campaign preparation, one-application
learning function and exact finalizer. Select counts 1, 8 and 32 for threads
and processes, one standard upstream lifetime per point: six warmup samples
and two nominal measured seconds. Keep identity, source/packet/data/placement,
image headroom and drain checks. Use fresh histories and matching provider
identities; reuse unchanged build/component evidence by hashes. This is not a
second lock or execution protocol.

Report each passed/drained application immediately, including raw throughput,
before/after image availability and generations, and whether the history
changed. Keep `scored=false`, `accepted=false` and worker proof absent unless
actually observed. A one-application learning allowance normally ends with
`LEARNING_ADVANCED`; accept only its saved single passed/drained application,
not another error or an incomplete lifetime. Preserve the strict campaign's
proof and quiet scoring path unchanged. Diagnostic completion and successful
retirement must not be presented as strict performance acceptance. Preserve
all preliminary positive/negative rates and the comparable Native controls.
Verify normal-kernel recovery at the end.

Implemented by `090ec98c9abc1963690ebfef75f1861876038795`, using runtime
`f2d9caf3fca0cd69b38b8b2ea5d18422cbf16e22`. All six short applications passed
and drained, with changing generations and no worker-attributed proof. Thread
rates at 1/8/32 workers were 201283.0/49296.5/18189.5 pairs per nominal second;
process rates were 234467.5/381426.0/400205.5. All are preliminary/unscored and
below matched Native controls. Exact retirement and normal restoration passed.
The 1 MiB change passed 36 focused cases; it is not a measured steady-JIT gain.
Full results and scope are in
[the short pilot report](../../bench/results/10.176.26.71/bench/mmap1-pilot-090ec98c/README.md).

# Actual mmap1 path and size: evidence boundary

The selected roots remain `0xffffffff817b6f68` (`vm_mmap_pgoff+0x118`) and
`0xffffffff8181c73b` (`__vm_munmap+0xbb`). Their matched Native intervals end
at write release for mmap and, on successful userspace munmap, downgrade plus
the later read release in `vms_complete_munmap_vmas()`. Post-release userfault
completion, population and detached-tree destruction are outside those holds.

At short-pilot generation 6 the decoded graphs contain 1100 source bytes / 295
instructions for mmap and 2676 / 687 for munmap, against fetched windows of
57344 / 49152 bytes. Those graphs include static alternatives and cover only
translated prefixes. The 1 MiB cache limit, 4 MiB image slot, decoded graph and
actual dynamic critical section are different quantities. No lock-held timing,
dynamic instruction count or runtime ratio was collected.

Reached CALL/IJ tables are execution-frontier evidence but lack per-edge task
and branch attribution. Current capture uses entry plus syscall shape, not a
mmap1 task/PID allowlist. Existing bound objects survive factory deactivation,
and bound capture bypasses the ordinary unbound task-name matcher. Excluded
acquisitions already stay local on the same KD object. A general requester
predicate could narrow that existing capture decision without a caller-specific
MM adapter; this analysis adds no filter or backend. Exact endpoints, targets,
coverage snapshots and the scope gap are recorded in
[the path/size evidence](../../bench/results/10.176.26.71/bench/mmap1-pilot-090ec98c/README.md#actual-paths-and-critical-section-size).

# Small executed-path diagnostic

Continue on `codex/mmap-reached-jit` from
`090ec98c9abc1963690ebfef75f1861876038795`. Separate child images initially
apply to selected KD acquisitions; allocator and other Native locks retain
their existing instruction-service treatment. This observation change does
not implement a different image, lock or handoff protocol.

Add an optional, load-time selected per-CPU observation of two configured
entry addresses and an exact origin task name. Count selected calls, local
admissions (including missing-image admissions), published requests, actual
JIT entry, permanent handback, delegated return, handback completion and
cancellation. Distinguish a cancellation before publication from a canceled
published request. Nonselected calls and disabled observations take no clock
samples or counter updates. These totals never participate in admission,
ownership, execution selection or retirement.

Retain only an observation index and shadow-wait start in private root
storage. Keep packets, frames, the wrapper ABI, lock layout and all protocol
decisions unchanged. Per-CPU totals are read before and after an application
by the existing controller, outside its lifetime; no concurrent observer or
per-request logging is added. Check local/published/prepublication-cancel
conservation, published terminal outcomes, and disabled/enabled behavior.

Elapsed nanoseconds delimit the existing local admission helper, the first
retained dispatcher call, and shadow-stack wait through normal resume or
Native acceptance. The dispatcher interval includes its C machinery and may
overlap shadow wait. Shadow wait includes services and scheduling; it is not
pure spinning. Neither interval is full critical-section held time or CPU
time. Existing `jit_timing` remains disabled because the strict image-session
identity requires that setting. Static decoded instruction counts are not
dynamic instruction counts, and these measurements do not determine a full
critical-section runtime ratio.

Use fresh histories, one one-worker priming application and one eight-thread
application, with the daemon paused throughout each standard six-warmup plus
two-measured-second lifetime. The eight-thread application uses the published
priming images, without compilation during execution. Keep source/image
headroom, identity, placement, data, drain, exact retirement and recovery
checks. Build and run focused off/on/conservation and directly affected
continuation checks on the VM, then the diagnostic and normal-kernel recovery.
Retain observations separately from the uninstrumented pilot and Native rates;
no acceptance or performance improvement follows from this diagnostic.

The first observation candidate, `328817076bbac8e17bfe2125609a450f63716a6d`,
passed its focused helper/controller checks and module build. Live loading
refused before any application: the extra static per-CPU totals raised the
module's reserved per-CPU allocation to 7984 bytes, which did not fit the
available reserved chunk. The VM remained idle; this is not workload or JIT
execution evidence. Keep that failed launch. Allocate the optional totals
once with `alloc_percpu()` during service initialization instead, before any
request is admitted, and free them after service workers and retained roots
have drained. Disabled observation allocates nothing. This retains CPU-local
updates while leaving the module's static per-CPU reservation unchanged.

Implemented by `e0a21c4a1c043fbb7d77ca9a679f47e5cf7a6c90`. Focused VM
checks/build and both applications passed; exact retirement and normal-kernel
restoration passed. At eight threads each root submitted/entered JIT/handed
back eight requests, returned zero wholly delegated requests, and handled over
408,000 acquisitions locally (99.99804%). Summed local admission was
57.624006611 task-seconds; initial dispatcher time totaled 90.049 microseconds.
The diagnostic rate was 51,042 pairs/s versus preserved Native 225,144.5.
No steady-JIT, complete MM read-tail or performance acceptance is claimed.
Counter/timer definitions, source references, failures and limits are in
[the selected-path report](../../bench/results/10.176.26.71/bench/mmap1-service-observe-e0a21c4a/README.md).

# Five direct-call levels and publication during learning

Continue the existing branch from `1d5017f1`, retaining the original backend,
GS lowering, wrapper ABI, source trust policy, cancellation, owners and exact
first-unexecuted continuation. The user authorized bounded direct-call
lookahead and image publication during the learning application's lifetime.

Count a source acquisition entry as depth zero and each ordinary direct CALL
edge as one additional level: follow callee entries at depths one through five.
Depth is lookahead, not a maximum permitted stack or API nesting depth. A target
already learned from actual execution is an additional depth-zero decoder seed
in the same acquisition region; it can extend that region in a later image.
Branches and tail jumps retain depth, cycles use minimum reached depth, and
lock controls / declared instruction services remain boundaries. Unknown or
deeper callees retain the existing exact CALL-miss continuation when reached.
Apply the default to trusted ABI2 images, with an explicit zero-depth setting
for fixtures and historical comparisons. Keep ordinary source windows, the
1-MiB aggregate, 256-KiB reads, 33 decode passes, 32 combined transitions and
ordinary return-flow budget. Do not select the older compact/closure profile.

Select lookahead only from the existing critical-section scope. A statically
identified outer release ends that caller path before callee discovery. Do not
mistake a nested release for the root release. Retained execution uses exact
object/identity/generation records: closing A does not close still-held B, and
the accepted non-LIFO case preserves B while marking A closed. Downgrade is not
a release; its read share and delegated tail continue until the matching read
release. Where decoded control flow alone cannot identify the release object,
runtime ownership delimits execution; no new value/CFG admission is introduced.
Separate images for selected KD child acquisitions remain their own delivery
item; this bounded discovery change must not claim to implement that machinery.

The capture/publication review found no need for a new admission guard. Capture
already owns a source/task-stack lease before lookup. Publication initializes
the immutable image before release-publishing its pointer and then NORMAL
status under the existing generation gate. Capture's acquire reads can choose
an old or new complete image, or return no eligible image after a miss; they do
not modify that image. Retained entry/resume uses its frame-bound image, and
all published images survive through session retirement. Reports change the
entry only when the reporting image is still current, under that same gate.
An old report after replacement cannot mark the new generation missed. Keep
all old images resident and do not merge, reclaim or swap active frames.

One existing capture filter omits `KD_IMAGE_REQUIRE_SOURCE_FRONTIER` although
the header and retained runtime support it. Include that declared requirement
in the retained capture mask and directly check valid/invalid image cases;
otherwise a deeper image containing the previously fixed reached marker would
publish successfully yet never be captured. Keep its exact instruction,
packet, source-lease and Native continuation checks.

Permit `pause_translation=false` in an explicitly unscored learning campaign.
The existing learning controller already deactivates new bindings and renews
source, registry, artifact and daemon receipts at drained boundaries. Leave
its daemon running during each application and wait for its ordinary compiler
child after drain. Preserve the strict quiet scoring path. Record changing
generations and actual compilation/application overlap, never pool them into
a fixed-image score. Keep the small counters and read them outside application
execution. Run focused depth/release/frontier/publication checks and short
mmap1 threads/processes observations on the VM, retain all outcomes and restore
the normal kernel. No merge or claimed gain without a comparable measurement.

The first live-learning candidate (`d5ec4eee`, fixture-only corrections through
`1f847d5b`) completed/drained threads at one and eight workers, at 190216.5 and
50785.5 pairs/s. Both roots were generation zero / NativeOnly; there were no
JIT submissions. Readiness correctly refused acceptance. The compiler found
undecodable blocks at `0xffffffff813b1b67` and `0xffffffff81dbceb2`. A maintained
leased source read identified `0f 01 ee` (RDPKRU) and `0f 01 ca` (CLAC),
respectively. The latter differs from the static ELF through kernel text
alternatives. Neither instruction is proved reached by the applications.
Exact retirement passed, including the separate two-site source read.

Extend the existing terminal source-frontier marker only for these two observed
three-byte encodings. Do not execute or emulate either on the executor. If
reached, export the full packet and preceding effects, retain the exact source
IP/SP and real CALL words, validate leased bytes at runtime, and use the
existing first-unexecuted original-task continuation with ACCEPT/final ACK.
Other branches continue through JIT. The matching full MM critical section is
not rejected merely because this instruction occurs on an alternative.

Advertise the extended encoding set with capability revision 19. Keep revision
18's original five-byte marker working; new decoder forms require explicit
revision-19 negotiation. Keep the same marker/image requirement and retained
lifetime protocol. Validate the two new generated exits and runtime source
checks, build on the VM, then resume the short threads/processes run without
another broad suite. Preserve all local-only observations as such.

The revision-19 candidate `bee6e2b22c6b08ea7e55cc281ca197aa1c7ee3be`
passed its necessary generated/runtime cases and provider build. Short threads
rates at one/eight workers were 187061/50447 pairs/s; processes were
221110/397627. All four applications passed and drained, with exact retirement
and normal-kernel restoration. Mmap remained generation-zero NativeOnly.
Munmap entered JIT eight times in each eight-worker application, handed back
eight times and returned zero requests without permanent handback. These are
partial-image observations, not steady delegation or an accepted optimization.

The recorded munmap IJ edge is `0xffffffff814f4a38` → `0xffffffffc0e32bf0`.
Saved generation-1 code shows indirect CALL at `0xffffffff814f4a33` inside
`kd_mmap_assert_held_write`, with return word `0xffffffff814f4a38` already
pushed before exit 11. The original task starts at the unexecuted callee;
this edge is not a completed RET pop. Individual handback reasons and actual
RDPKRU/CLAC marker hits remain unmeasured.

Mmap's remaining aggregate guard rejects the combination of retained services
and the older instruction-service markers (`disassem/disassem.py:845`). Its
last coverage RIP does not identify the offending instruction. Do not add a
broader returning instruction-service join for unproved branches, or relax
that guard. A minimal existing terminal CALL boundary may suffice where the
exact reached helper unconditionally requires the original task; it must not
exclude an ordinary helper merely for containing another conditional branch.
The current receipt lacks the selected legacy-site details needed to choose
that boundary. Preserve those details at the existing refusal before deciding
between the existing terminal CALL and exact terminal instruction paths.
The [fixed report](../../bench/results/10.176.26.71/bench/mmap1-depth5-bee6e2b2/README.md)
retains identities, counts, rates, source evidence and the unresolved scope.

## Exact interrupt-state boundaries before the next mmap1 run

The diagnostic at `9d144a95730a80063fc8570f81440f738442176a` identifies
three remaining legacy sites: CLI at `0xffffffff815e8cc9` in `vkdb_printf`,
and CLI/STI at `0xffffffff8178f532` / `0xffffffff8178f555` in
`lru_add_drain_cpu`. These are decoded alternatives, not proved application
hits. The matched ELF contains paravirtual CALL slots at those addresses;
the leased running-text decoder sees their patched CLI/STI instructions.
Do not exclude either complete helper or relax the retained-service guard.

Extend the existing terminal source frontier for precisely the one-byte
encodings `fa` and `fb`, negotiated only with capability revision 20. If a
path reaches either, export its preceding effects and exact first-unexecuted
IP, preserve the real source stack and flags, and complete the existing
permanent original-task continuation with ownership and final ACK retained.
Do not execute CLI/STI on the executor or create a returning service join.
Other paths remain JIT paths. The source reader must validate one byte first
and the exact selected length, including an instruction at a text boundary;
it must not require a second byte for a one-byte instruction. Revisions 18
and 19 retain their respective earlier encoding sets.

Generation 2 already contains the munmap callback edge learned from
`0xffffffff814f4a38` to the recorded module target `0xffffffffc0e32bf0`.
Its generated target dispatch needs execution evidence, not a new callback
protocol. A new-boot leased read at `0xffffffff814f4a33` is
`2e 2e 2e ff d2`, a five-byte CALL RDX; this is not a retrospective snapshot
of the old module instance. Keep the missing old module symbol map explicit.

Build on the VM and run only the new generated frontier cases, capability
negotiation, retained continuation check, and short mmap1 threads/processes
observations. Keep every result and restore the normal kernel after drain.
Separate child images initially apply only to selected KD acquisitions;
allocator and other Native locks retain their existing instruction-service
handling. This boundary correction does not implement separate child images
or establish complete delegated MM execution.

The CLI/STI candidate `eabe454b4ee51ea6962a73525372b4b09679c737` passed
the focused generated/negotiation/continuation checks and provider build.
Threads completed at one/eight workers with both roots publishing generation
one, then eight JIT submissions and eight permanent handbacks per root. The
eight-worker rate was 46445.5 pairs/s; generation two was published after
that application, so learned-dispatch execution remains unproved there.

For the following processes session, permit `[1,2,8]` alongside `[1,8]` in
the existing observation runner. Its inherited loop already runs each point
once and retains all observations. The two-worker point is one bounded extra
learning application before the final eight-worker observation, not another
scored repeat or an indefinite stabilization loop. Keep the tested provider
and its source identity; only the runner count check changes. Freeze the new
runner while idle, retain distinct runner/provider identities, and do not pool
the threads and processes observations as one source/configuration score.

The short run completed with exact retirement and normal-kernel recovery.
Threads were 188263 / 46445.5 pairs/s at one/eight workers; processes were
220110.5 / 329826 / 389100 at one/two/eight. The eight-worker values remain
79.37% / 77.02% below preserved Native. Both roots now publish images, but
each eight-worker point still has eight JIT handbacks per root and zero
ordinary delegated returns; most requests remain local. No performance
acceptance follows. Processes exercised generation two and learned the
callback return edge `0xffffffffc0e32bec` → `0xffffffff814f4a38` (exit 15),
confirming progress beyond the prior CALL miss. Generation three was published
afterward and remains unrun. Actual CLI/STI hits are not counted separately.
See the [scoped report](../../bench/results/10.176.26.71/bench/mmap1-frontier-eabe454b/README.md)
for source identities, all rates, regressions, focused checks and proof limits.

## One bounded generation-three follow-up

From report commit `aebd299e176fbee204b174df6f0e945b154335ec`, inspect the
retained generation-three sources before changing the protocol. Both MM roots
already resolve `0xffffffffc0e32bec` → `0xffffffff814f4a38`. The generated
return reads `[R13]`, increments R13 by eight, moves the target to R14 and
dispatches to the learned label; that label restores dispatch flags and jumps
to the actual target body without another pop. On a miss, exit 15 preserves
the already-advanced SP and the first-unexecuted target. The target body is
present in each selected image. This is static image coverage, not evidence
that generation three has executed. No new return/callback protocol is needed.

Permit `[1,2,4,8]` in the existing observation loop for one processes session.
The first three applications relearn within a fresh source/module epoch;
the final eight-worker application should use generation three if learning
follows the observed sequence. Do not import old module addresses or histories.
Run each point once, retain every outcome, stop after this bounded sequence,
and report the actual generation and any further executed miss. No indefinite
stabilization or full matrix is requested. Reuse the validated provider from
`eabe454b4ee51ea6962a73525372b4b09679c737` after verifying runtime and
translator source bytes are unchanged; only the observation count check and
documentation change. Preserve all established ownership, read-credit,
continuation and retirement checks, then restore the normal kernel.

Runner `816e9ce3430cebdd2c186f6a8d2baca16d75e66f` completed that bounded
processes sequence at 220830.5 / 322072 / 372330.5 / 369782.5 pairs/s.
Generation three was selected before the final point; its source hashes match
the reviewed return images. Each entry recorded eight JIT handbacks and zero
ordinary delegated returns. The new recorded CALL targets are
`unmapped_area_topdown` (`0xffffffff8181c0e0`) for mmap and `mas_mab_cp`
(`0xffffffff826b2f60`) for munmap. Generation three has CALL-miss stubs there;
the handback retains the already-pushed return word and begins at the callee.
This establishes further reached coverage limits, not non-delegability of the
helpers. Generation four was published afterward and remains unrun. All four
applications drained, exact retirement passed and normal-kernel recovery was
verified. Full delegated MM completion and performance acceptance remain open.
See the [generation-three report](../../bench/results/10.176.26.71/bench/mmap1-generation3-816e9ce3/README.md).

## Bounded generation-four execution, then diagnose recurrence

The retained generation-four sources contain actual bodies for both reached
targets, `unmapped_area_topdown` at `0xffffffff8181c0e0` and `mas_mab_cp` at
`0xffffffff826b2f60`. Their recorded hashes are respectively
`d4e19779467a04124b4fff43104c62bee10af4e896ec0c01d37e3e4d8dea107d` and
`d09cbc1e5ed1f34cf771377715b684367b6bb24a89a99f56282a9c721b49ed8c`.
This establishes static callee coverage; the previous run did not execute
these images. Existing direct CALL lowering retains its real return-word
push and jumps to the callee label. There is no second CALL at that label.

Use one fresh processes session with `[1,2,4,6,8]`: four bounded priming
applications, followed by one representative eight-process observation.
Relearn every edge within the new source/module epoch. Allow at most 900
seconds for this finite learning sequence; the previous four-point run
approached the 600-second limit. Keep the existing per-application timeout
and all identity/drain checks. Runtime and translator bytes remain those of
validated provider `eabe454b4ee51ea6962a73525372b4b09679c737`; only the
existing count choice and documentation change, so reuse its build/checks.
If another actual miss occurs, stop the run series after this observation
and trace the executed chain to distinguish the five-edge discovery limit,
scope clipping, seed propagation and ordinary later learning. Do not extend
the sequence indefinitely or investigate unrelated branches. Keep the
original backend, immutable images and all continuation/ownership/ACK rules,
retain every result, then restore and verify the normal kernel.

Runner `00413a9ae078234b14933f4ed9a385f48d26e05c` completed all five
applications, each once, at 220615 / 327626.5 / 380204 / 389485.5 /
391778.5 pairs/s. All drained and exact retirement passed. Generation four
was selected for the final eight-process application; each root recorded
eight JIT entries, eight completed handbacks and zero wholly delegated
returns. The final rate remains 76.86% below the preserved Native control;
this is an instrumented learning observation, not a steady-image comparison
or acceptance. Generation five was published afterward and is unrun. The
normal kernel was restored and verified idle with an empty one-shot entry.

Both new reached targets match the configured discovery boundary. The saved
generation-four source-comment graphs place `mas_wr_node_store`
(`0xffffffff826b4a80`, mmap) and `mas_leaf_max_gap`
(`0xffffffff826b2720`, munmap) at minimum direct-CALL depth six from that
generation's entry/history seeds; their callers are at depth five. Each
caller pushes its real return word before reaching an exit-1 callee stub.
Previous learned seeds have decoded bodies. These observations support
ordinary bounded coverage growth, with no evidence here of lost seeds,
incorrect release clipping or source-capacity refusal. All ten compiler jobs
completed successfully.

The new target visits are observed in the histories; the six-edge chains are
inferred structural paths, not dynamic branch traces or attribution of every
handback. Fresh munmap priming learned `__memcpy`, not the prior session's
`mas_mab_cp`, so its generation-four image differs. Do not equate generation
numbers across those sessions. Fixed `call_roots` come from the initial
entry/history seeds; a discovered descendant does not reset its callers' or
unrelated later work's depth. The five-edge setting bounds new discovery,
not all already decoded paths or the permitted runtime stack depth.

Stop this bounded live series here. The
[generation-four report](../../bench/results/10.176.26.71/bench/mmap1-generation4-00413a9a/README.md)
retains the selected images, source paths, all rates and counts, compiler
outcomes, and recovery evidence. This diagnosis changes no runtime protocol
and does not implement the separately selected child-image design.

## Retained capture while a recoverable miss is pending

Continue `codex/mmap-reached-jit` from
`79c2a752a547cecedf41948f3b0549c5ae2c990b`. A valid immutable ABI2 image
with the retained terminal-miss contract remains usable by retained service
captures while a CALL/IJ report requests its next generation. Ordinary mutex
batch and spin readiness keep their current contract. Both demand capture
and prepared rwsem registration use the same image validator; neither may
discard an otherwise eligible image through a preceding NORMAL-only lookup.
Source-open, exact entry/ABI/header/requirements and permanent exclusions
remain mandatory. Bound frames retain their selected image across replacement;
no new readiness check is inserted after an instruction has executed.

Keep the existing one-record learning representation, with a per-entry revision
under the publication gate. Exact duplicate tuples coalesce without changing
revision. A distinct report replaces the pending tuple as today, increments the
revision and an explicit superseded-report counter; this remains latest-report
learning, not a lossless event queue. Bind acknowledgment to the writable device
description's registry-read snapshot and base generation, frozen at the first
upload chunk. Publication clears only its matching observed revision. A newer
pending tuple survives and requests another generation; late reports from an old
bound image remain ignored. An upload without a matching read receipt consumes
no pending report. No new wire field or lock/wrapper API is introduced.

Generation-qualified daemon command deduplication must not reuse an earlier
generation's compiler outcome as a new translation. Source closure and permanent
entry exclusion still deny fresh capture. No pending array, new backend,
returning service, or general lock queue is introduced. This narrow change
preserves existing last-report behavior while closing publication's deletion
of a newer report; broad branch coverage still requires subsequent occurrences
of any superseded target.

Finish implementation before focused VM checks. Exercise pending-miss capture,
duplicate and distinct concurrent reports, exact acknowledgment, replacement
with an old frame retained, and closed/permanent/invalid cases. Reuse generated
branch/terminal-continuation checks for bypass completion and reached handback.
Build the provider and changed daemon on the VM only.

Use one unchanged eight-process application per Native/KD arm with `-s 724`:
six upstream warmup samples plus 714 additional preparation samples, followed
by the final ten measured samples. The 720-sample warmup exceeds the prior
608.812 seconds of serial compiler work, including the latest 201.756-second
pair; it does not guarantee convergence. Bound each application at 800 seconds
and preparation/drain separately. Preserve all samples and the upstream average
over its full 724 post-marker samples; report the selected final-ten average
separately. Use the same PTY stdout transport for both arms so complete sample lines arrive
promptly without changing the executable. Sample JIT/local/handback/completion
counters and registry generations after the final warmup line and final measured
line, retaining callback timestamps and transport-delay limits. Keep full-lifetime
counts separately. These callbacks delimit an observed window, not an atomic
snapshot at the application's counter instruction. Do not claim steady delegated
performance when coverage advances or completion remains unproved. Keep matched identities and
placement, immutable running inputs, exact retirement, and normal-kernel recovery.
