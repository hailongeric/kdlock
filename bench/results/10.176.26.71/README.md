# Results from 10.176.26.71

This is the machine directory for tests and benchmarks in the VM on the Ubuntu
Xeon Gold 6438N host at `eric@10.176.26.71`. Source edits remain in the original
checkout on `380G10` and are synchronized to this VM before testing.

- [Current c01/hash rerun, 2026-10-11](bench/comparison/full-matrix-20261011T025525Z/overview.md):
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

The complete comparison uses a temporary 66-vCPU boot, 32 worker CPUs per NUMA
node and collector vCPU 65. At 64 workers, the collector and QEMU services share
physical host core 63 with the last worker. The earlier bounded report uses a
64-vCPU boot and collector 63. Both record the host's `ondemand` governor;
keep their samples separate from the initial 60-vCPU migration validation and
the [original-host reports](../380G10/README.md).
Record each run's actual topology and frozen source. Current connection and
operational instructions are in [the project guide](../../../docs/PROJECT_GUIDE.md).
See [the common layout](../README.md) for guest output and host archive paths.
