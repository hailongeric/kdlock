# Native C context custody and exact W handback

Source-only refinement after the boot8 archive closed. This note uses current
main and the saved kernel8 source/disassembly export. It changes no source or
test input and requests no interruption of the independent tests.

## The concrete seam

Retaining physical C custody is compatible in principle with keeping W as the
sole canonical source owner after an ordinary miss. The existing retained KD
owner pattern already separates source ownership from a physical release
duty. It does not implement the native RCU/PTL context pairing required here.

`kernel/episode.c:670–704` consumes/stages the exact pending CALL and transfers
S_W directly to the native endpoint through `kd_jit_transfer_origin`.
`kernel/jit.c:322–340` checks packet/operation phase and native endpoint identity,
not an open native-context record. There is currently no handback step that
converts or retains native C RCU/PTL duties for an unmodified W suffix.

The actual linked kernel8 `_raw_spin_lock` increments physical preemption
depth at `ffffffff8276ccf5` before its lock attempt. `_raw_spin_unlock` performs
the corresponding decrement at `ffffffff8276ceaf` and can schedule at
`ffffffff8276cec8`. Therefore simply retaining the PTL lock word on C and
letting W call ordinary unlock is insufficient: the native decrement acts on
W's executing CPU/context, not C's retained obligation. Likewise, the saved
RCU pair updates the executing task's nesting and special-unlock state.

The current KD atomic handback has an explicit W-local reconciliation step
(`kernel/native_entry.c:138–162,199–203`) based on exact logical atomic grants.
That mechanism is selected by the root's atomic family. It is not invoked for
an inner native PTL beneath a sleepable RWSEM root. Runtime family/atomic
selection remains fixed (`runtime.c:370–412`), owner tracking rejects another
atomic mode (`owner_progress.c:34–50`), and the sleepable pump may call
`schedule()` (`episode.c:178–196`). Removing a family check would not supply
context custody or legal control progress.

## The irreducible obligation

Before admitting a native context acquire on C, every allowed first-unexecuted
escape must have a route on which **W can actually execute its exact suffix
through the matching release while C retains the physical duty legally**.
That is the narrow missing escape/progress obligation. It is independent of
source-register authority, object exclusion and source-code coverage.

For the actual PTL, C cannot schedule while its native preemption pin is open.
If W can run only on C's occupied CPU, immediate handback plus a waiting C
cannot reach W's eventual release. A busy C loop is not a proof that W can
run. Conversely, running W elsewhere still requires an exact native release
route to C, W-local context admission, and actual C release/ACK before the
native unlock return. No existing queue or numerical depth record supplies
these by itself. The RCU duty must remain live through every use of the
derived PTE pointer and its matching native release, including failed-map and
retry branches. Same mm or same CPU proves neither pairing.

Keeping the selected immediate handback rule does not itself require choosing
a new source-authority policy. It requires implementing and proving that
escape route, or declining context entry before its first effect when the
route is unavailable. Delaying the already-required handback until an inner
scope ends, or releasing/reacquiring PTL/RCU around W, would instead change a
selected contract and cannot be inferred as an implementation detail.

## What can proceed without that choice

The four generic SPECIAL entry records plus exact shared-scanner pre-CALL
propagation supply the safe current prefix lane. The first demonstrated RCU
CALL is `ffffffff81841237`, preceding PTL CALL `ffffffff8184159c`; a PTL-only
cut is late. These records can be built and tested independently. They admit
no live C native-context duty, so the existing handback remains applicable.

Full protected munmap completion still needs a generic per-scope custody and
matching native service/ACK mechanism, W-local suffix context admission, and
the concrete progress proof above. The existing sleepable outer-rwsem owner,
selected retained-write downgrade, root-only killable cancellation and exact
S_W/CALL/RET rules stay separate and unchanged. No new progress policy or
mixed-context execution claim is selected by this audit.
