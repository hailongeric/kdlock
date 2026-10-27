# Documentation index

Start with the [three-stage project roadmap](ROADMAP.md) for the ultimate kernel
replacement goal, scoped MM milestone and current evidence gaps. This index
assigns one responsibility to each maintained guide.

Ubuntu 26.04 / Linux 7.0 is the active adaptation platform. The
[VM migration record](history/vm-ubuntu2604-migration-20261027.md) records
Ubuntu 26.04.1 LTS, kernel `7.0.0-38-generic`, matching headers, the approved
snapshot purge and expansion to 132 GiB. The separate
[Linux 7 port receipt](../bench/results/10.176.26.71/tests/linux70-port-20261027/README.md)
records the custom `7.0.0-38-kdlock1` build, Native/TCLock functional controls,
KD native-continuation probes and remaining validation limits. Current basic
cacheline presets require fresh validation. The
[kernel retirement record](history/kernel-retirement-20261027.md) preserves
the legacy recovery version and earlier results.

These guides describe `master`, whose mutex retains the accepted
KD-only lock protocol from `d2a2304` and whose reader/writer semaphore (rwsem) waiting
implementation is accepted at `c21345b`. The rwsem acceptance includes its
documented two-worker performance regressions. Historical experiments do not
define current APIs (application programming interfaces).
The [checked instruction-exit contract](JIT_REGISTER_ABI.md#checked-instruction-exit)
adds validated original-waiter continuation without changing that lock protocol.

| Guide | Responsibility |
| --- | --- |
| [Project roadmap](ROADMAP.md) | Ultimate kernel replacement goal, three development stages, milestones and completion criteria |
| [Project guide](PROJECT_GUIDE.md) | Reading order, source ownership and quick setup |
| [Current lock catalog](LOCKS.md) | All four KD lock families, public interfaces, shared engines and compatibility limits |
| [Terminology](TERMINOLOGY.md) | Plain-language definitions of lock, execution and benchmark terms |
| [VM operations](operations/VM.md) | Environment, identity, builds, recovery and drain |
| [Linux 7 integration](../kernel_integration/linux70/README.md) | Exact Ubuntu source, core kernel patch, separate mmap overlay and schema-2 kernel identity |
| [Development rules](../AGENTS.md) | Repository-wide contribution constraints |
| [Design](DESIGN.md), [code map](CODE_MAP.md) | Architecture, terms and file responsibilities |
| [Lock protocols](design/lock_protocols.md) | KD/TCLock/Native comparisons for spin, mutex and rwlock, plus Native/KD/original-TCLock rwsem with documented API limits |
| [Spin](design/spin_implementation.md), [mutex](design/mutex_implementation.md), [rwlock](design/rwlock_implementation.md), [rwsem](design/rwsem_implementation.md) | Canonical implementation guides: API, source paths, state, ordering, storage and limits |
| [KD-only mutex](design/kd_only_mutex.md) | Object replacement, ordinary aliases and delegation |
| [Locking](design/locking.md), [frames](design/frames.md), [lifetimes](design/lifetimes.md) | Ownership and retirement |
| [JIT execution](JIT_EXECUTION.md), [register ABI](JIT_REGISTER_ABI.md), [admission](design/admission.md) | Translation and execution contracts |
| [Workload catalog](BENCHMARK_WORKLOADS.md), [benchmarks](../bench/README.md) | Protected work and reproducible runner commands |
| [Throughput campaign plan](THROUGHPUT_PLAN.md) | Bounded Native/KD measurement plans, actual mmap/fault boundaries and retained campaign status |
| [Performance](PERFORMANCE.md), [results](../bench/results/README.md) | Measured outcomes and retained evidence |
| [Tests](../tests/README.md), [validation](VALIDATION.md) | Check selection and receipts |
| [Limitations](TODO.md) | Known failures and deferred work |
| [History](history/README.md), [branch consolidation](history/main-consolidation-20261018.md) | Superseded designs and exact branch dispositions |
| [Feature reintegration](history/feature-reintegration-20261018.md) | Branch content audit, restored independent features and rwsem port boundary |

For a lock implementation review, start with the catalog, choose its canonical
implementation guide, then follow the ownership and execution references as
needed. Benchmark numbers belong in performance/result records; they do not
define API guarantees. The current direct string-helper optimization is a spin
ABI1 execution feature and preserves the selected mutex and rwsem protocols.
