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
affected programs. These checks do not establish retained-owner handback or an
executed mmap1 result for the corrected backend.

## Retained handback joins

Status: proposal only, awaiting the user's decision before dependent code
changes. Commit `6648a732` records a design, not approved implementation. No
reader-layout, paired-atomic, routing or retained-handoff production changes
have been made under this proposal.

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
