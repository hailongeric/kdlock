# Documentation index

kdlock targets relevant in-kernel lock replacement and evaluation of unchanged
applications such as will-it-scale `mmap1`. The [roadmap](ROADMAP.md) defines the
three stages and their completion criteria. Current work uses Ubuntu 26.04.1
and Linux `7.0.0-38-kdlock1`; Linux 6.1 is retained for recovery and historical
evidence only.

This index describes maintained implementation and source-specific evidence.
Use [execution](JIT_EXECUTION.md) for present source/continuation behavior and
[validation](VALIDATION.md#retained-original-jit-and-proxy-read) for the latest
retained-MM result. Historical candidate notebooks preserve decisions and
receipts; their old work orders do not define a new redesign or schedule runs.
The [documentation archive](history/documentation-20261109/README.md) records
superseded guides and the full pre-cleanup design/TODO snapshots.

Production trusts kernel and module source. Semantic safety, context/loop-value
and entry-input proofs are bypassed; ordinary string callees use the normal
backend. Source leases, faithful lowering, CALL/RET routing and exact runtime
ownership remain required. See [translation policy](design/admission.md).

| Responsibility | Maintained guide |
| --- | --- |
| Goals, stages and next deliverables | [Roadmap](ROADMAP.md) |
| Environment, synchronization, dependencies and recovery | [VM operations](operations/VM.md) |
| Public APIs and supported execution modes | [Lock catalog](LOCKS.md), [public headers](../include/README.md) |
| Architecture and source ownership | [Design](DESIGN.md), [code map](CODE_MAP.md) |
| KD, TCLock and Native algorithms | [Protocol comparison](design/lock_protocols.md) |
| Per-family implementation | [Spin](design/spin_implementation.md), [mutex](design/mutex_implementation.md), [rwlock](design/rwlock_implementation.md), [rwsem](design/rwsem_implementation.md) |
| Mutex object replacement and aliases | [KD-only mutex contract](design/kd_only_mutex.md) |
| Ownership, acknowledgements and retirement | [Locking](design/locking.md), [frames](design/frames.md), [lifetimes](design/lifetimes.md) |
| Translation and execution | [Translation policy](design/admission.md), [execution flow](JIT_EXECUTION.md), [register ABI](JIT_REGISTER_ABI.md) |
| Linux 7 source/build identity and MM adapter | [Kernel integration](../kernel_integration/linux70/README.md), [MM integration](../kernel_integration/linux70/MMAP.md) |
| Module-owned mappings and backing faults | [Mapping/fault contract](design/mmap_fault.md) |
| Workload definitions and commands | [Workloads](BENCHMARK_WORKLOADS.md), [benchmark runners](../bench/README.md) |
| Measurements and validation | [Performance](PERFORMANCE.md), [validation](VALIDATION.md), [test selection](../tests/README.md) |
| Known limits and vocabulary | [Open work](TODO.md), [terminology](TERMINOLOGY.md) |
| Superseded designs, plans and result narratives | [History](history/README.md) |

The [complete Linux 7 catalog](../bench/results/10.176.26.71/bench/catalog-linux70-complete-20261028/README.md)
contains 3,402 selected timing observations across separately frozen generations.
All are exploratory single rounds. Fresh four-family functional checks passed;
the actual shared-MM performance objective remains unmet. Publication, returned
JIT execution, functional correctness and performance qualification are separate
verdicts.

Follow [development rules](../AGENTS.md). Source edits, Git and static review run
on `380G10`; builds, tests and timing run only in the designated VM. The old
project quick-start and throughput-plan documents are superseded by this index,
VM operations and the roadmap; their fixed versions remain in history.
