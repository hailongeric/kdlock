# Historical designs and evidence

Current APIs and instructions are in the [documentation index](../README.md).
These records preserve decisions, failed experiments and measured source identities.
Historical throughput does not describe `master` unless the report says so.

| Record | Status |
| --- | --- |
| [VM storage and Ubuntu 26.04 migration, 2026-10-27](vm-ubuntu2604-migration-20261027.md) | Approved 43-snapshot purge and 132 GiB expansion completed; Ubuntu 26.04.1 / Linux 7.0.0-38 boot verified; KD port and compatibility remain unvalidated |
| [Linux 6.1 retirement, 2026-10-27](kernel-retirement-20261027.md) | One legacy recovery version, preserved results, exact cleanup receipts and the planned Ubuntu 26.04 / Linux 7.0 transition |
| [Main consolidation, 2026-10-18](main-consolidation-20261018.md) | Accepted baseline, branch dispositions, moves and removals |
| [Feature reintegration, 2026-10-18](feature-reintegration-20261018.md) | Restore independent branch features and port ordinary sleeping rwsem without changing the selected mutex protocol |
| [Legacy compatibility backport](legacy_mutex_compatibility.md) | Instruction/image changes retained in the current KD-only mutex |
| [Protocol simplification](protocol_simplification.md) | Closed historical study; rejected candidates are not a current plan |
| [KD-only acceptance report](../../bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md) | Measured current lock implementation |
| [All-workload comparison](../../bench/results/10.176.26.71/bench/comparison/workloads-20261015T180603Z/README.md) | Earlier spin/rwlock/API coverage and superseded owned mutex |
| [Expanded owned mutex](../../bench/results/10.176.26.71/bench/comparison/mutex-expanded-20261016T040928Z/README.md) | Historical compatibility/performance study, not selected |
| [Old master rwsem validation](../../bench/results/10.176.26.71/tests/rwsem-snapshots-20261015/README.md) | Historical owned-gate and delegated-writer results; distinct from the current phase-admitted rwsem port |

The [machine result index](../../bench/results/README.md) retains other reports and
raw archive locations. The old large status narratives remain in
[the selected checkpoint's documentation](https://github.com/hailongeric/kdlock/tree/d2a23049a4b6e3c65cf0ff21bbfd3e21cd975761/docs).
