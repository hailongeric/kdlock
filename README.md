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

There is no decoder, API recognition, instruction emission, runtime CALL/RET
effects, lock implementation, build system or benchmark payload yet. Ten focused
private cases passed on the earlier intraprocedural planner in `13f2630f` with
Python 3.10.12. The CALL/RET planning extension has static review only; further
behavioral tests are deferred until overall functionality is complete. See the
[evidence limits](docs/design/kdlock_redesign/04_evidence_and_reconciliation.md#21-rebuild-status).
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
approvals, not support evidence. Grant/release authority, arbitration, the
original-backend adapter and the other C02-C11 choices remain explicit work.

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
