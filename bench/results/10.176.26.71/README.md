# Results from 10.176.26.71

`master` selects KD-only `d2a2304`; see [current performance](../../../docs/PERFORMANCE.md).
The [2026-10-18 consolidation checks](tests/main-consolidation-20261018/README.md)
validate organization and tooling separately from the measured runtime.
Historical owned/adaptive mutex and sleeping-rwsem reports below are preserved
evidence, not current implementation selections.

The [KD-only mutex round](bench/comparison/mutex-kdonly-20261017T140354Z/README.md) contains 504 fresh accepted/drained sessions
at 1–8 workers by one and 12–60 by four, three repetitions, with accepted KD,
Native and TCLock controls. It measures the removal of Linux mutex backing while
retaining legacy delegation. At 60 workers KD-only reaches
4.838/5.130 Mops/s for c01/post64 and
pipebytes n16. Full scaling, low-count variation, separate regression follow-ups,
intermediate trials and independently replayed evidence remain in the report.

The [legacy compatibility comparison, 2026-10-17](bench/comparison/mutex-legacy-compat-20261017T122742Z/README.md)
contains 504 accepted/drained sessions for c01/post64 and pipebytes n16, with
fresh legacy, backported legacy, Native and TCLock at all 21 worker counts.
At 60 workers, the backport reaches 4.914/5.375 Mops/s versus legacy's
4.820/5.370. The 44-worker pipebytes regression and low-count variability remain
in the report. Both KD versions retain the legacy lock protocol. This run uses
64 vCPUs and collector CPU 63.

The [fresh legacy mutex grid](bench/comparison/mutex-legacy-grid-20261016T125529Z/README.md)
compares c01/post64 and pipebytes n16 over all 21 requested worker counts,
with 378 accepted/drained sessions. At 60 workers, legacy KD reaches
4.931/5.379 Mops/s respectively. The report includes every count, all three
repetitions, peak/whole statistics, plots and the independently replayed archive.

This is the machine directory for tests and benchmarks in the VM on the Ubuntu
Xeon Gold 6438N host at `eric@10.176.26.71`. Source edits remain in the original
checkout on `380G10` and are synchronized to this VM before testing.

- [All-workload/API comparison, 2026-10-15](bench/comparison/workloads-20261015T180603Z/README.md): 21-count grid; historical owned mutex scope and omissions remain explicit.
- [Expanded owned mutex, 2026-10-16](bench/comparison/mutex-expanded-20261016T040928Z/README.md): expanded synthetic/API coverage for the superseded protocol.
- [Rwlock c01, 2026-10-15](bench/rwlock/20261015-c01/README.md): 378 sessions, 1%/20% writes, 39/42 strict parity points.
- [Mutex and read/write API results, 2026-10-11](bench/real_api/20261011-sync/RESULTS.md):
  pipe-buffer/capacity queries, shared-file seeks and bounded UTS namespace
  reads/writes; 504 accepted sessions, three-round comparisons, JIT evidence and retained
  exploratory failures. The UTS experiment distinguishes private Native rwsem
  from KD/TCLock reader/writer spinlocks and the original global Stock path.
- [Spinlock API results, 2026-10-11](bench/real_api/20261011/RESULTS.md):
  OFD conflict queries and file-table bitmap updates, their kernel locks and
  TCLocks paper context; stock helper plus matched Native/TCLock/KD, three rounds
  at six worker counts, 288 accepted sessions. The [run record](bench/real_api/20261011/README.md)
  retains validation, xattr refusal and exploratory failures; slower cases remain
  in the results.
- [Historical mutex optimization, 2026-10-11](bench/comparison/mutex-opt-20261011T045425Z/README.md):
  c01/hash, all three backends, 22 worker counts, three rounds;
  396 accepted, drained sessions. Causes, selected changes, rejected candidates
  and unresolved regressions are retained. Strict multithreaded parity holds at
  14 of 42 points; c02/c08/c16 excluded.
- [Earlier all-lock c01/hash rerun, 2026-10-11](bench/comparison/full-matrix-20261011T025525Z/overview.md):
  all three backends and lock families, 22 worker counts, three rounds;
  1,584 drained sessions after the NUMA/mutex fixes; 1,582 accepted.
  c02/c04/c08/c16 excluded; complete charts, statistics and archive replay.
- [NUMA spin and mutex investigation, 2026-10-10](bench/comparison/numa-mutex-20261010/README.md):
  root causes, accepted fixes and remaining Native gaps; 354 accepted timed
  sessions, six diagnostics, placement/progress controls and rejected candidates.
  The final three-round comparison contains 72 c01/hash sessions.
- [Complete 22-point comparison, 2026-10-10](bench/comparison/full-matrix-20261010T094831Z/README.md):
  spin, rwlock and mutex under KDLock/TCLock/Linux Native at 1–8 and 12–64
  workers; all maintained performance payloads, three rounds, 3,960 accepted and
  drained timed sessions. The report includes all charts, CSVs and archive receipts.
- [Earlier bounded 64-vCPU performance comparison, 2026-10-10](bench/comparison/performance-20261010T081816Z/README.md):
  rwlock, spin and mutex tables, scaling charts and three-round statistics;
  all 144 sessions passed correctness and drained.
- [64-vCPU setup and affected checks, 2026-10-10](tests/20261010-topology64/README.md)
- [Initial 60-vCPU migration validation, 2026-10-10](bench/migration-20261010T070707Z/README.md)

The historical complete comparisons through 2026-10-11 use a temporary
66-vCPU boot, 32 worker CPUs per NUMA node and collector vCPU 65. At 64 workers,
the collector and QEMU services share
physical host core 63 with the last worker. The earlier bounded report uses a
64-vCPU boot and collector 63. All record the host's `ondemand` governor;
keep their samples separate from the initial 60-vCPU migration validation and
the [original-host reports](../380G10/README.md).
Record each run's actual topology and frozen source. Current connection and
operational instructions are in [the project guide](../../../docs/PROJECT_GUIDE.md).
See [the common layout](../README.md) for guest output and host archive paths.
