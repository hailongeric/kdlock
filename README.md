# kdlock

An incremental, independent rebuild for **Linux kernel 7.0, x86_64,
non-PREEMPT_RT**.

## Current state

The first implementation slice is a private
[source-flow fragment planner](disassem/fragment.py), contributing only the
structural graph walk to P2. Given a finite, caller-classified intraprocedural
graph, it stops before lock/unlock/mode/special sites, retains safe alternatives
and shared joins, and reports missing targets and unresolved transfers
separately. Its records are provisional compiler data, not a public ABI.

There is no decoder, API recognition, instruction emission, CALL/RET handling,
lock implementation, build system or benchmark payload yet. Ten focused private
planner cases passed with Python 3.10.12; see the
[evidence limits](docs/design/kdlock_redesign/04_evidence_and_reconciliation.md#21-rebuild-status).
No build, JIT execution, kernel integration or performance result is claimed.
Acceptance specifications T01-T56 remain unrun.

Read the design in order:

1. [Overview](docs/design/kdlock_redesign/00_overview.md)
2. [Lock protocol](docs/design/kdlock_redesign/01_lock_protocol.md)
3. [Original JIT contract](docs/design/kdlock_redesign/02_jit_contract.md)
4. [Implementation plan and open decisions](docs/design/kdlock_redesign/03_implementation_plan.md)
5. [Evidence and reconciliation](docs/design/kdlock_redesign/04_evidence_and_reconciliation.md)

Before implementation of kernel or adapter contracts, settle the
integration/compatibility contract C12 and the initial family/API/context lanes
in C01, then choose the necessary C02-C11 mechanisms for that lane. The
independent clean-baseline route is selected; these remaining design choices
are not decided by deleting the old code.

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
