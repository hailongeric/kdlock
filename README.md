# kdlock

An incremental, independent rebuild for **Linux kernel 7.0, x86_64,
non-PREEMPT_RT**.

## Current state

The first implementation slice is a private
[source-flow fragment planner](disassem/fragment.py), contributing only the
structural source-flow analysis to P2. Given a finite, caller-classified graph,
it stops before lock/unlock/mode/special sites, retains safe alternatives and
shared joins, and reports missing targets and unresolved transfers separately.
Explicit direct CALL/RET records keep each call's target and continuation
separate; a continuation is retained only when its callee has a modeled
boundary-free route to a RET. Its records are provisional compiler data, not a
public ABI or a runtime-return proof.

A private [decoder adapter](disassem/source_decode.py) now converts only supplied
stable source bytes and exact boundary metadata through the original Miasm
x86_64 decoder into planner records. It retains source bytes/length and separates
decode failures and unmodeled transfers from missing ordinary coverage. It does
not read source, discover successors or select a register/packet mapping.

The private [mutex release protocol](kernel/mutex_release.c) and its
[header](kernel/mutex_release.h) retain physical-owner context and exact
per-acquisition controls. They distinguish source request, deferred marker,
unwind readiness, owner handling, physical release and retirement; exact
source-request, return and notifier users gate retirement. The request publishes
its exact OWNER or DEFERRED_OUTER route; same-task identity alone cannot classify
an outer unlock. No default source resumption is selected. Initialization binds
the already-acquired backend's exact ordinary unlock callback/object. An
owner-only finish validates handled obligations, closes the batch/binding and
takes/clears that binding under its guard, invokes the bound synchronous complete
unlock once outside the guard, then records physical release. Owner operations
check the current task. Correct callback binding and code/object lifetime remain
caller obligations; no callback has executed. This is protocol code with static
review only, not a physical mutex backend, queue, JIT adapter or source-cursor
advancement implementation.

There is no API recognition, instruction emission, runtime CALL/RET effect
handling, complete lock implementation, build system or benchmark payload yet.
Ten focused private cases passed on the earlier intraprocedural planner in
`13f2630f` with Python 3.10.12. The CALL/RET, decoder and C protocol extensions
have static review only; decoder dependencies have not been installed or
imported. Further behavioral tests are deferred until overall functionality is
complete. See the [evidence limits](docs/design/kdlock_redesign/04_evidence_and_reconciliation.md#21-rebuild-status).
No build, JIT execution, kernel integration or performance result is claimed.
Acceptance specifications T01-T56 remain unrun.

Read the design in order:

1. [Overview](docs/design/kdlock_redesign/00_overview.md)
2. [Lock protocol](docs/design/kdlock_redesign/01_lock_protocol.md)
3. [Original JIT contract](docs/design/kdlock_redesign/02_jit_contract.md)
4. [Implementation plan and open decisions](docs/design/kdlock_redesign/03_implementation_plan.md)
5. [Evidence and reconciliation](docs/design/kdlock_redesign/04_evidence_and_reconciliation.md)

C12 is selected: source-rebuilt integration with fresh private layouts and no
compatibility promise for old binary lock/object layouts. C01 starts with
ordinary mutex lock/unlock in sleepable task context on Linux 7.0 x86_64 without
PREEMPT_RT; other lock families follow later. These are implementation scope
approvals, not support evidence. C03 now selects TCLock-style out-of-order outer
mutex unlock deferral: retain the responsible outer combiner, notify/unwind to
it, continue its normal batch protocol and physically release through that
protocol. Extra waiting is accepted; this is not a generic native release-timing
or progress-parity claim. The earlier transferable-grant proposal is superseded.
C11 queue/arbitration, the original-backend adapter and remaining mechanisms
stay open.

The lock-object lifetime choice is still pending: require stable lock objects
through physical release, or hold post-unlock source continuation until physical
release. Neither is selected here. Early reacquisition and source handshakes
that depend on outer-lock availability remain unresolved scope issues; a
deferred marker is not physical release or permission to reclaim the object.

## Git history

`archive/before-main-20261109` at
`7ce7db54334960fe0d9db2c425c5c581cdedf4b0` preserves the complete tracked tree
plus the eight pre-rebuild modified/untracked files, including the original five
redesign documents and comparison audit. Its parent is the untouched `master`
revision `2e9016915632ab4a488f444d06fe881ffcca0616`.

Legacy implementation, guides, results and deployment-specific content have
been removed from the `main` tree through a normal descendant commit. History
has not been rewritten. The original checkout, its untracked/ignored evidence
and other linked worktrees remain unchanged. The preserved material is not a
current implementation or support promise. No changes have been pushed.
