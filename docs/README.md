# Documentation index

These guides describe `master`, whose mutex implementation is the accepted
KD-only version from `d2a2304`. Historical experiments do not define current APIs.

| Guide | Responsibility |
| --- | --- |
| [Project guide](PROJECT_GUIDE.md) | Reading order, source ownership and quick setup |
| [VM operations](operations/VM.md) | Environment, identity, builds, recovery and drain |
| [Development rules](../AGENTS.md) | Repository-wide contribution constraints |
| [Design](DESIGN.md), [code map](CODE_MAP.md) | Architecture, terms and file responsibilities |
| [Lock protocols](design/lock_protocols.md) | KD/TCLock/Native spin, mutex and rwlock behavior |
| [Spin](design/spin_implementation.md), [mutex](design/mutex_implementation.md), [rwlock](design/rwlock_implementation.md) | Implementation and storage details |
| [Sleeping rwsem](design/rwsem_implementation.md) | Ordinary sleeping readers/writers on KD physical locking; delegation and real mmap replacement remain separate |
| [KD-only mutex](design/kd_only_mutex.md) | Object replacement, ordinary aliases and delegation |
| [Locking](design/locking.md), [frames](design/frames.md), [lifetimes](design/lifetimes.md) | Ownership and retirement |
| [JIT execution](JIT_EXECUTION.md), [register ABI](JIT_REGISTER_ABI.md), [admission](design/admission.md) | Translation and execution contracts |
| [Workload catalog](BENCHMARK_WORKLOADS.md), [benchmarks](../bench/README.md) | Protected work and reproducible runner commands |
| [Performance](PERFORMANCE.md), [results](../bench/results/README.md) | Measured outcomes and retained evidence |
| [Tests](../tests/README.md), [validation](VALIDATION.md) | Check selection and receipts |
| [Limitations](TODO.md) | Known failures and deferred work |
| [History](history/README.md), [branch consolidation](history/main-consolidation-20261018.md) | Superseded designs and exact branch dispositions |
| [Feature reintegration](history/feature-reintegration-20261018.md) | Branch content audit, restored independent features and rwsem port boundary |
