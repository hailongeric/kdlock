# kdlock

The project's goal is to replace relevant Linux kernel locks with KD and measure
unchanged applications such as will-it-scale's `mmap1`. Work proceeds in three
stages: demonstrate gains on lock micro/nano benchmarks; establish improvement
or parity in scoped mmap/page-fault integration; then complete the declared
kernel lock replacements and evaluate application performance. The
[project roadmap](docs/ROADMAP.md) defines goals, milestones and completion
criteria. Current measurements support favorable nano cases but have not met the
scoped MM performance objective; broad kernel replacement remains planned.

Start with the [basic working version](docs/PROJECT_GUIDE.md#basic-working-version)
for focused functional commands across all four lock families and the separate
real mmap/page-fault examples. Current work prioritizes qualified Native/KD
throughput across lock workloads, actual mmap and actual page faults; see the
[throughput campaign plan](docs/THROUGHPUT_PLAN.md). New tail-latency work is deferred.

The October 26 exploratory screen attempted all 51 runnable lock/API
configurations and completed the three separate implemented mmap/fault workloads,
with one timed round per point. The [lock/API tables](bench/results/10.176.26.71/bench/catalog-single-20261026/progress.md)
retain 3,166 measurements and 47 drained KD xattr preparation failures; the
[MM tables](bench/results/10.176.26.71/bench/catalog-mmap-single-20261026/README.md)
retain another 126 measurements. Strict host timing qualification remains failed;
these observations do not replace repeated accepted baselines.

kdlock is an experimental x86_64 Linux kernel lock library. A lock holder can
execute waiting callers' critical sections through a just-in-time (JIT) compiler,
which translates their protected work into code for delegated execution. The project
provides spinlocks, ordinary mutexes and spinning read-write locks, with matched
Linux Native (unmodified Linux locks) and TCLock (the separate stack-switching
delegation implementation) workloads. A separate
[sleeping reader/writer semaphore, or rwsem](docs/design/rwsem_implementation.md),
allows concurrent readers or one exclusive writer, and lets blocked callers
sleep. Its ordinary readers/writers execute locally; explicit outer writers can
delegate their work through the unchanged KD mutex protocol.

The public rwsem interface is [`include/kd_rwsem.h`](include/kd_rwsem.h) and
`struct kd_rwsem`. The experimental [mmap adapter](kernel_integration/mmap_lock/README.md)
uses that local reader/writer protocol behind Linux's mmap wrappers. Native MM
bodies stay on their original task, and readers remain concurrent. Explicit
rwsem delegation is a separate interface; operation-specific MM-body delegation
and prepared teardown are retired.

The `e6fc371` correction passed 137 Native and 161 KD assertions on actual mmap
objects, plus a separate 352-assertion standalone probe and two basic programs.
These focused checks do not establish full Linux semantic equivalence. Benchmark
payload/client preparation has passed. The authorized October 25 `plain-v1`
attempt [stopped before boot](bench/results/10.176.26.71/bench/mmap-plain-v1-20261025/README.md)
at 68 QEMU tasks versus the required 67; all 12 measured sessions remain unrun.
The separate prospective `plain-scaling-v1` matrix has 21 worker counts and
126 Native/KD sessions per workload; its 41 focused mocked tests passed. Its
[live sweep](bench/results/10.176.26.71/bench/mmap-worker-scaling-20261026/README.md)
passed all Native controls, then stopped on the KD fixed-writer observation;
all 126 measurements remain unrun and recovery is restored. A separate qualified
[16-worker validation pair](bench/results/10.176.26.71/bench/mmap-worker-screen-20261026/README.md)
measured 108,246 Native versus 35,406 KD mmap/munmap cycles/s (KD 0.3271×).
One pair provides no variability estimate or optimization conclusion. See the
[validation scopes](docs/VALIDATION.md#native-shared-mm-mmap-writers).

The rwsem waiting policy selected in **`c21345b`** remains the baseline. Writers
first block new readers and wait for existing readers to finish. Separate queues
serve different waiting conditions. Ordinary uninterruptible acquisition polls
for a bounded number of attempts before sleeping; killable mmap writers use
their separate wait path. The
[756-session comparison](bench/results/10.176.26.71/bench/rwsem-optimization-20261018/README.md)
records large 60-worker gains and retained two-worker regressions. Acceptance
includes this measured tradeoff. Those measurements predate the current object
layout and IRQ-safe reader-release correction; they do not establish current
performance. The [TCLock rwsem port](tclock_backend/README.md#original-rwsem-comparator)
supports restricted ordinary pairs, without compatible cancellation, downgrade
or actual mmap integration.

`master` is the maintained version. Its KD mutex uses **KD-owned physical
exclusion and the accepted legacy delegation protocol**, selected at `d2a2304`.
All callers of a KD mutex object must use KD APIs. Direct calls to the unified
`kd_mutex_lock/unlock` interface and ordinary blocking aliases permit delegation;
signal/try/I/O acquisitions and function-pointer lock calls execute locally.
Loading the provider does not replace locks throughout an existing kernel. See the
[mutex contract](docs/design/kd_only_mutex.md) for supported APIs and scope.

Mutex translation now supports [checked instruction exits](docs/design/admission.md#checked-instruction-exits).
A reviewed special instruction on an untaken branch can remain in an eligible
critical section. If that branch is taken, generated code stops before the
instruction; the original waiter resumes there, and delegation of that entry is
disabled for the source session. Earlier updates are retained. The
[validation record](bench/results/10.176.26.71/tests/native-instruction-exit-20261018/README.md)
separates correctness checks from the accepted performance measurements below.

The current mutex is 32 bytes with native 8-byte alignment. Its delegation phase
and tail are embedded in the object; preallocated CPU/slot nodes share storage
between independent OSQ and delegation memberships. There is no auxiliary
address-indexed table. The user-selected defaults are a 1024-body total cap and
768-body NUMA locality boundary; the
[optimization study](bench/results/10.176.26.71/bench/mutex-profile-20261026/OPTIMIZATION.md)
retains the exploratory cross-NUMA gains and same-node regressions motivating
that choice. The earlier
[shared-node comparison](bench/results/10.176.26.71/bench/mutex32-mcs-20261020/README.md)
records the 256-body NUMA locality policy and remaining performance gaps against
the old 256-byte object. Earlier compact-table measurements remain historical.

The historical accepted [504-session comparison](bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md)
covers c01/post64 and `api-pipebytes-query-n16` at 1–8 workers and 12–60 by four,
with three repetitions and Native/TCLock controls. The
[performance guide](docs/PERFORMANCE.md) retains variation and regression limits.

Eligible spin-delegated bodies now call the original `strcmp` and `strscpy_pad`
inside the same generated invocation, removing repeated dispatcher transitions.
No helper-code checks, string pre-scans or runtime destination checks are added;
exact ownership, source lifetime and return bookkeeping remain. The KD mutex
protocol is unchanged.

The [`05876a4` taskname/xattr comparison](bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
contains 567 validated, drained sessions. At 60 workers, KD reaches
4.521/2.368/0.573 Mops/s for taskname/xattr n16/xattr n128: 1.838×/4.901×/6.528×
the preceding dispatcher implementation. All three exceed fresh Native there
and remain below TCLock. The report retains low-count regressions, complete
scaling results and the still-unaccepted taskname mutation delegation case.

## Documentation

- [Project goal and three-stage roadmap](docs/ROADMAP.md)
- [Documentation index](docs/README.md) and [project guide](docs/PROJECT_GUIDE.md)
- [Terminology](docs/TERMINOLOGY.md): lock, execution and measurement terms used in these guides
- [Current lock catalog](docs/LOCKS.md): spinlock, mutex, rwlock and rwsem APIs and implementation guides
- [Design](docs/DESIGN.md), [lock protocol comparisons](docs/design/lock_protocols.md)
  and [code map](docs/CODE_MAP.md)
- [Benchmark workloads](docs/BENCHMARK_WORKLOADS.md) and [benchmark commands](bench/README.md)
- [Tests](tests/README.md), [validation](docs/VALIDATION.md) and [known limitations](docs/TODO.md)
- [VM operations](docs/operations/VM.md) and [development rules](AGENTS.md)
- [Branch consolidation](docs/history/main-consolidation-20261018.md) and [historical evidence](docs/history/README.md)
- [Feature reintegration](docs/history/feature-reintegration-20261018.md): restored proc snapshots, benchmark safeguards and ordinary rwsem
- [Accepted rwsem comparison](bench/results/10.176.26.71/bench/rwsem-optimization-20261018/README.md): `c21345b` Native/KD results, separate Native/TCLock/KD spinning-rwlock reference, candidate history and validation limits
- [Initial rwsem writer comparison](bench/results/10.176.26.71/bench/rwsem/20261018/README.md): historical shared-queue baseline, execution evidence and regressions

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

The [folder ownership guide](docs/PROJECT_GUIDE.md#folder-ownership) explains
where new source, runners, probes and records belong. Historical analysis tools
are kept together in [bench/archive](bench/archive/README.md); measured outputs
remain under machine-specific result directories.

Edit source on `380G10`; build and test only in the designated recovery VM on
`10.176.26.71`. KD's admission checks are not a security sandbox. See
[admission](docs/design/admission.md) and [lifetimes](docs/design/lifetimes.md).
