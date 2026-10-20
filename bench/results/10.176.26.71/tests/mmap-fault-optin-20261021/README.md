# Opt-in mmap/fault implementation stage

Status: implementation prepared; VM validation pending. No correctness or
performance pass is claimed yet.

This follows the retained 46-file mmap/fault review and `d7f7358`, on source
host `380G10` with the same recovery VM. The main agent remains the only writer
and serial test executor. No guest kernel changes or access-setting changes
are planned. The owner-interval diagnostic stays inconclusive; its unvalidated
estimator will not be extended to five workers. All seven mutex regressions and
performance acceptance remain open.

The implementation is a module-owned mapping with a private backing-state lock,
not substitution of selected native mmap-lock calls. Its supported cases,
pre-publication Native fallback, exact originating-task scope and retained
full-mm blockers are defined in the [design](../../../../../docs/design/mmap_fault.md).
Actual CPU faults use ordinary callbacks; controlled ioctls exercise RETRY,
NOWAIT and COMPLETED without attributing those branches to a hardware-fault run.

The fixed correctness order is Native and KD first, then a separate TCLock
validation if both pass. Each invocation runs basic plus directly affected
checks, preserves frozen inputs and retains every failed attempt. No parallel
test or comparison runs are authorized by this plan.
