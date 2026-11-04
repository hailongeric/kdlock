# Original compiled images for retained MM continuations

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
Neither policy completes the selected retained-MM requirement.

For retained compiled execution, generated misses export source arithmetic
flags before wrapper cleanup and a typed FULL event. The packet names the
actual target and post-transfer source SP. An ordinary CALL already pushed its
return word; RET already popped its word. Never repeat those effects.

Report direct missing callees through CALL_MISS and actual indirect edges
through IJ_MISS, including the real source continuation/site convention.
Never report an indirect CALL as CALL_MISS(target,0). Preserve generation-scoped
reports and stale-report rejection. Keep the existing capture image fixed;
only an explicit execution-artifact join may select another immutable image.
Ordinary frames continue to execute their original bound generation.

A retained miss suspends the exact execution activation, not the public
acquisition or logical request. When a compatible compiled artifact is ready,
validate source/entry/ABI, FULL PC/SP, request generation, services and owners;
then use an explicit flags-preserving reentry at that target. The old image is
not edited or republished in place. No whole-body origin suffix, entry replay,
implicit success or new public acquisition error is permitted.

Returning Native helper/instruction services remain bounded intervals followed
by E resumption. Resumption must use the artifact that owns that exact service,
not whichever image was most recently published in the registry.

## Boundaries requiring explicit evidence

A userspace compilation wait with live Native spin/preempt/RCU owners is not a
sleepable wait. Existing runtime checks refuse sleeping nested acquisition in
those intervals. Such a miss remains an explicit unsupported encountered point
until a nonblocking progress contract is implemented and validated; do not drop
its owners or silently run the protected remainder on O.

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
2. Add flags-preserving original-backend miss/reentry contracts and distinct
   CALL/IJ learning, preserving ordinary immutable bindings.
3. Connect retained execution-artifact selection and general service joins;
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
