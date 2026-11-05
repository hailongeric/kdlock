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
selected 128 override, including invalid bounds. Continue with new cold
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
