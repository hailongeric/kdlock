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
