# kdlock

An incremental, independent rebuild for **Linux kernel 7.0, x86_64,
non-PREEMPT_RT**.

## Current state

This is the clean design baseline (P0). There is no lock implementation, build
system, benchmark payload or captured result in this branch. No build, runtime
correctness, kernel integration or performance result is claimed for the
rebuilt lock. Acceptance specifications T01-T56 remain unrun.

Read the design in order:

1. [Overview](docs/design/kdlock_redesign/00_overview.md)
2. [Lock protocol](docs/design/kdlock_redesign/01_lock_protocol.md)
3. [Original JIT contract](docs/design/kdlock_redesign/02_jit_contract.md)
4. [Implementation plan and open decisions](docs/design/kdlock_redesign/03_implementation_plan.md)
5. [Evidence and reconciliation](docs/design/kdlock_redesign/04_evidence_and_reconciliation.md)

The next step is to settle the integration/compatibility contract C12 and the
initial family/API/context lanes in C01, then choose the necessary C02-C11
mechanisms for that lane. The independent clean-baseline route is selected;
these remaining design choices are not decided by deleting the old code.

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
