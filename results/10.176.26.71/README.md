# Results from 10.176.26.71

This is the machine directory for tests and benchmarks in the VM on the Ubuntu
Xeon Gold 6438N host at `eric@10.176.26.71`. Source edits remain in the original
checkout on `380G10` and are synchronized to this VM before testing.

- [Migration validation, 2026-10-10](bench/migration-20261010T070707Z/README.md)
- [64-vCPU setup and affected checks, 2026-10-10](tests/20261010-topology64/README.md)

The migration validation used the initial 60-vCPU topology. Subsequent runs use
the revised 64-vCPU topology with 32 CPUs per NUMA node; record each run's actual
topology and keep these samples separate. Current connection and operational
instructions are in [the project guide](../../docs/PROJECT_GUIDE.md).
See [the common layout](../README.md) for guest output and host archive paths.
