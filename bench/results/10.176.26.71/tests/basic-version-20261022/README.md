# Basic functional delivery

Status: spin/public-mutex smoke passed; rwlock/rwsem completion pending. The
user requested a basic version across all original tasks before more performance
analysis. This stage changes no production lock, admission, ownership, ACK,
cancellation or teardown protocol.

Source ownership at 2026-10-22 06:12:54 UTC: clean `9e9df64`, neither previous
coordinator present, no visible checkout writer or test runner; 551 processes
were inaccessible. The guest check at 06:13:23 UTC confirmed idle recovery boot
`97c45a77-3ce3-4d3f-87b4-4ef3e880af64`, the exact 73-module set, 64 CPUs and no
build/profile tasks. No in-flight run was stopped. The main agent is the sole
writer and executor; existing helpers remain finished and touched no files.

`bench/basic/run.py` runs both basic programs, focused runner guards and four
existing fixed-work list cases serially: KD spin, public mutex, rwlock and
rwsem, 16 nodes, 100,000 iterations per worker. Shared families keep
20% writes and local concurrent readers. Every case requires positive returned
JIT bodies and complete drain. Additional CPU-63 I/O workers are recorded in
this unscored functional mode; the original timing gates are unchanged.

Attempt `run-1`, frozen `6237f5e`, passed dependencies, both basic programs and
four runner tests. Spin and public mutex each completed 1,600,000 operations;
matching JIT entry/completion counts were 1,591,572 and 1,533,374. The 16-worker
mixed rwlock case completed and drained with zero returned JIT bodies. Its
strict `NO_JIT` failure stopped the runner before rwsem. This is retained as a
failed delegation check, not relabeled as delegated support. The separate
post-run guard confirms the same idle recovery boot and exact 73 modules.

The basic preset now uses the already exercised 60-worker mixed rwlock case;
spin, public mutex and rwsem retain 16 workers. The next run selects only rwlock
and rwsem, preserving passed cases and the failed original attempt. It retains
`--require-jit`, list/data/reader checks and full retirement. This geometry change
is a functional preset, not a comparable timing rerun or causal correction.

Existing evidence keeps its original identities:

- [Nine continuation/ownership probes and 16 resident-list cases](../native-continuation-20261020/README.md)
  cover reviewed markers, exact handback, sticky refusal and family functionality.
  Later shared type/initialization refactoring retains separate
  [kernel integration validation](../mmap-kd-kernel-20261021/README.md).
- [Actual-MM Native/KD correctness](../actual-mm-plain-20261021/README.md)
  separates untouched mapping from faults. MM readers and writers are local;
  no TCLock MM or arbitrary delegated MM support is claimed.
- [Deterministic observer controls](../mmap-phase-controls-20261022/README.md)
  are complete; further causal observer work is deferred.

The [quick start](../../../../../docs/PROJECT_GUIDE.md#basic-working-version)
provides commands and scope. Causal profiling, wake attribution, the seven
regressions, qualified variance and p95 remain unresolved/deferred. Earlier
failed receipts and rejected timings are preserved.
