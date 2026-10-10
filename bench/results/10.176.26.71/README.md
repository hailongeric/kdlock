# Results from 10.176.26.71

This is the machine directory for tests and benchmarks in the VM on the Ubuntu
Xeon Gold 6438N host at `eric@10.176.26.71`. Source edits remain in the original
checkout on `380G10` and are synchronized to this VM before testing.

- [Current 64-vCPU performance comparison, 2026-10-10](bench/comparison/performance-20261010T081816Z/README.md):
  rwlock, spin and mutex tables, scaling charts and three-round statistics;
  all 144 sessions passed correctness and drained.
- [64-vCPU setup and affected checks, 2026-10-10](tests/20261010-topology64/README.md)
- [Initial 60-vCPU migration validation, 2026-10-10](bench/migration-20261010T070707Z/README.md)

The current performance report covers selected worker counts, not the full
benchmark matrix. It uses 32 CPUs per NUMA node, collector CPU 63 and the host's
`ondemand` governor. Its samples remain separate from the initial 60-vCPU
migration validation and the [original-host reports](../380G10/README.md).
Record each run's actual topology and frozen source. Current connection and
operational instructions are in [the project guide](../../../docs/PROJECT_GUIDE.md).
See [the common layout](../README.md) for guest output and host archive paths.
