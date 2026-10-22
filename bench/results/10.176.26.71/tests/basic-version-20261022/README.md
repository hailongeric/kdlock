# Basic functional delivery

Status: new runner and documentation prepared; focused VM smoke pending. The
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
rwsem, 16 nodes, 16 workers, 100,000 iterations per worker. Shared families keep
20% writes and local concurrent readers. Every case requires positive returned
JIT bodies and complete drain. Additional CPU-63 I/O workers are recorded in
this unscored functional mode; the original timing gates are unchanged.

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
