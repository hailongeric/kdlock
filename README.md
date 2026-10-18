# kdlock

kdlock is an experimental x86_64 Linux kernel lock library. A lock holder can
execute waiting callers' critical sections through a JIT compiler. The project
provides spinlocks, ordinary mutexes and spinning read-write locks, with matched
Linux Native and TCLock workloads. A separate [sleeping rwsem](docs/design/rwsem_implementation.md)
provides ordinary local readers/writers and explicit ABI2 writer delegation,
with Native/KD comparisons. Writer reservations drain readers before entering
the unchanged KD mutex protocol. There is no TCLock rwsem arm.

`master` is the maintained version. Its KD mutex uses **KD-owned physical
exclusion and the accepted legacy delegation protocol**, selected at `d2a2304`.
All callers of a KD mutex object must use KD APIs; ordinary mutex aliases execute
locally, while explicit clobber callers permit delegation. Loading the provider
does not replace locks throughout an existing kernel. See the
[mutex contract](docs/design/kd_only_mutex.md) for supported APIs and scope.

The accepted [504-session comparison](bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md)
covers c01/post64 and `api-pipebytes-query-n16` at 1–8 workers and 12–60 by four,
with three repetitions and Native/TCLock controls. The
[performance guide](docs/PERFORMANCE.md) retains variation and regression limits.

## Documentation

- [Documentation index](docs/README.md) and [project guide](docs/PROJECT_GUIDE.md)
- [Design](docs/DESIGN.md), [nine lock protocols](docs/design/lock_protocols.md)
  and [code map](docs/CODE_MAP.md)
- [Benchmark workloads](docs/BENCHMARK_WORKLOADS.md) and [benchmark commands](bench/README.md)
- [Tests](tests/README.md), [validation](docs/VALIDATION.md) and [known limitations](docs/TODO.md)
- [VM operations](docs/operations/VM.md) and [development rules](AGENTS.md)
- [Branch consolidation](docs/history/main-consolidation-20261018.md) and [historical evidence](docs/history/README.md)
- [Feature reintegration](docs/history/feature-reintegration-20261018.md): restored proc snapshots, benchmark safeguards and ordinary rwsem
- [Rwsem writer comparison](bench/results/10.176.26.71/bench/rwsem/20261018/README.md): 756 complete Native/KD sessions, execution evidence and performance limits

## Repository

| Directory | Responsibility |
| --- | --- |
| [kernel_module](kernel_module/README.md) | KD provider, ownership, queues and execution engine |
| [include](include/README.md) | Public APIs, shared ABI and wrapper assembly |
| [disassem](disassem/README.md), [daemon](daemon/README.md) | Translation, admission and immutable mutex image publication |
| [tclock_backend](tclock_backend/README.md) | Independent TCLock ports and upstream provenance |
| [workload_modules](workload_modules/README.md) | Kernel benchmark payloads |
| [bench](bench/README.md) | Maintained runners, archived analysis and results by machine |
| [tests](tests/README.md) | Basic, targeted and live checks |
| [kernel_baseline](kernel_baseline/README.md) | Captured kernel identity and historical experiments |
| [tools/vm](tools/vm/README.md) | Source synchronization |

Edit source on `380G10`; build and test only in the designated recovery VM on
`10.176.26.71`. KD's admission checks are not a security sandbox. See
[admission](docs/design/admission.md) and [lifetimes](docs/design/lifetimes.md).
