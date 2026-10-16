# Results from 10.176.26.71

This index covers the VM on the Ubuntu Xeon Gold 6438N host at
`eric@10.176.26.71`. Source edits stay on `380G10`. Each report retains its own
source, kernel, boot policy, topology, measurements and failed attempts.
Current commands and accepted-provider status live in the
[project guide](../../../docs/PROJECT_GUIDE.md) and
[performance status](../../../docs/PERFORMANCE.md).

New runs use exactly CPUs 0–63: node 0 has CPUs 0–31 and node 1 has CPUs 32–63,
with no extra vCPUs or unused spare CPU. Earlier 66-vCPU reports below are
historical evidence, not instructions for new runs; retain their recorded
topology rather than relabeling them as 64-vCPU results.

## Current workload comparison

The [expanded mutex round](bench/comparison/mutex-expanded-20261016T040928Z/README.md)
contains 2,079 accepted, drained measurements across all eleven mutex variants,
with three repetitions at 1–8 workers by one and 12–60 by four. KD now covers
c01/c02/c04/c08/c16, RCUHT, pipebytes n16/n128, pipecap n16 and seek set/end.
Its 693 measurements include all 630 previously omitted KD samples and fresh
c01 controls; Native and TCLock each have 693 fresh samples. The report retains
the 93 basic/affected checks, 29 live validation sessions, full curves and archive.
All 660 multithreaded KD sessions returned JIT bodies; 33 single-worker sessions
ran locally. This round explicitly selects ABI4/reuse-32 with origin and NUMA
policies off. Pipe/file KD uses the controlled private-object adapter; Native
retains its embedded kernel mutex, so lock placement differs.

The earlier [synthetic and syscall/API round](bench/comparison/workloads-20261015T180603Z/README.md)
contains 7,749 accepted, drained measurements across 41 workload groups, with
three repetitions at every worker count from 1–8 by one and 12–60 by four.
It compares the captured current workspace with TCLock and Linux Native on
the regular 64-vCPU guest, using collector CPU 63. The report includes complete
curves, whole-run and warmed-peak statistics, raw samples, source identity and
a checksummed archive.

KD's local executions and returned JIT bodies are distinguished throughout.
In that earlier round, KD owned mutex coverage was c01 only; pipe/seek mutexes
and xattr API cases compared Native with TCLock. UTS retains its scoped rwsem/rwlock distinction.
The report includes lower-worker regressions as well as high-worker gains;
this comparison does not change provider defaults or performance acceptance.
The earlier report supplies the spin/rwlock and other-API results; its mutex
omissions describe that captured source. The expanded round has fresh controls
and is not pooled with it. Xattr remains outside KD's admitted API scope.

## Owned-only mutex verification

The [removal receipt](tests/remove-mutex-legacy-20261015/validation.json) records
builds, basic/affected tests, live task/scheduler probes and ABI2/ABI4 JIT checks
with FULL continuations, owner ACKs and complete drain. It contains no new
performance comparison.

The [commit check](tests/remove-mutex-legacy-20261015/commit-check-20261016.json)
records fresh basic/affected checks and builds against the isolated staged
source, plus the documentation audit. The earlier live evidence remains separate.

## Current owned-protocol optimization

The [origin claims and bounded NUMA study](bench/mutex_owned/20261015-origin/README.md)
implements immutable image binding and the audited GS subset, with basic,
affected and live JIT verification. Its regular-64 c01 screen and separate
confirmations miss the regression gates; both new policies remain opt-in.
The shared-collector 64-worker point and GS diagnostics have separate evidence.

The [fresh c01 1–60-worker rerun](bench/mutex_owned/20261015-numa-rerun/README.md)
contains 189 audited Native/TCLock/KD sessions on the regular 64-vCPU guest,
with origin claims and NUMA selection enabled for KD and a separate collector.
At 60 workers, KD median throughput is 7.106 Mops/s, 1.79× Native and 2.28×
TCLock. This three-round comparison leaves the opt-in defaults unchanged.

The [fresh c01 1–64-worker comparison](bench/mutex_owned/20261014-full-grid/README.md)
contains 198 correct, drained Native/TCLock/KD samples at the full 22-point grid.
KD reaches at least 97% of Native median throughput at every count, but misses
the warmed-peak threshold at three workers (93.86%). At 60 workers its median
is 1.92× Native. The temporary 66-vCPU topology and its 64-worker physical
collector contention remain separate from the accepted narrow study below.

The [Linux-local ABI4/reuse-32 profile](bench/mutex_owned/20261014-linux-local/README.md)
passes the 97% Native target for both throughput measures at all counts 1–8,
in the screen and both fresh confirmations. It extends the experimental owned
provider while preserving the 32-byte object and KD-only ownership. Its c01/post64
scope remains separate from the older through-28/higher-thread studies below.

## Latest archived mutex experiment

The native-first implementation at `9a5305e` failed its full performance gates
and is preserved under `archive/perf/mutex-native-first-20261014`. Its report is
integrated separately; the accepted provider was restored. Correctness evidence,
KD_SELF throughput and returned-JIT requirements remain distinct.

## Earlier verification

| Study | Captured scope and disposition | Correctness receipt |
| --- | --- | --- |
| [Native-first entry/waiting, 2026-10-14](bench/mutex_owned/20261014-native-first/README.md) | ABI4, OSQ, leaf unlock and guarded release; implementation rejected, report retained. | [Receipt](bench/mutex_owned/20261014-native-first/validation.json) |
| [Owned outcome/grant protocol, 2026-10-14](bench/mutex_owned/20261014-hybrid/README.md) | Structural changes retained experimentally; same-policy higher-thread gates pass, Native parity fails. | [Receipt](bench/mutex_owned/20261014-hybrid/validation.json) |
| [Owned redesign, 2026-10-13](bench/mutex_owned/20261013/README.md) | Independent 32-byte object and finite/refill protocol retained explicitly; performance target fails. | [Receipt](bench/mutex_owned/20261013/validation.json) |
| [Legacy protocol trials, 2026-10-13](bench/mutex_protocol/20261013/README.md) | Frame/layout/capture/epoch candidates rejected; post-work variants kept separate. | [Receipt](bench/mutex_protocol/20261013/validation.json) |
| [Legacy optimistic retry, 2026-10-13](bench/mutex_optimistic/20261013/README.md) | Six candidates rejected; native owner/list/OSQ drain check retained. | [Receipt](bench/mutex_optimistic/20261013/validation.json) |
| [Three-way cost study, 2026-10-13](bench/mutex_c01_cost/20261013/README.md) | Native/TCLock/KD diagnostics and bounded counter/prefetch improvement; parity unmet. | [Receipt](bench/mutex_c01_cost/20261013/validation.json) |
| [Admission study, 2026-10-13](bench/mutex_admission/20261013/README.md) | Eight thresholds rejected; pinned cold sampler and default 256 retained. | [Receipt](bench/mutex_admission/20261013/validation.json) |
| Blocking policy, 2026-10-12 | Sleeping/task/ACK probes and contended JIT; functional evidence, not a new matrix. | [Receipt](tests/mutex-blocking-only-20261012/validation.json) |

## Frozen benchmark reports

| Earlier report | Captured scope |
| --- | --- |
| [Mutex and read/write APIs, 2026-10-11](bench/real_api/20261011-sync/RESULTS.md) | 504 accepted sessions; pipes, seeks and bounded UTS metadata |
| [Spinlock APIs, 2026-10-11](bench/real_api/20261011/RESULTS.md) | 288 accepted sessions; OFD queries and descriptor flags; [run record](bench/real_api/20261011/README.md) retains failed pilots |
| [Mutex optimization, 2026-10-11](bench/comparison/mutex-opt-20261011T045425Z/README.md) | 396 accepted/drained c01/hash sessions at 22 worker counts |
| [All-lock c01/hash rerun, 2026-10-11](bench/comparison/full-matrix-20261011T025525Z/overview.md) | 1,584 drained sessions, 1,582 accepted, after NUMA/mutex fixes |
| [NUMA investigation, 2026-10-10](bench/comparison/numa-mutex-20261010/README.md) | Accepted fixes, rejected candidates, placement/progress controls and parity gaps |
| [Complete baseline, 2026-10-10](bench/comparison/full-matrix-20261010T094831Z/README.md) | 3,960 accepted/drained sessions, including larger cacheline payloads |
| [Bounded 64-vCPU comparison, 2026-10-10](bench/comparison/performance-20261010T081816Z/README.md) | 144 accepted/drained sessions at selected counts |
| [64-vCPU setup](tests/20261010-topology64/README.md) | Topology and affected-check receipts |
| [Initial migration](bench/migration-20261010T070707Z/README.md) | 60-vCPU setup and validation |

The full 22-point comparisons used temporary 66-vCPU boots with collector 65.
At 64 workers, the collector, last worker and QEMU services share physical host
core 63. The bounded reports used 64 vCPUs and collector 63.
The migration used 60 vCPUs. Keep these measurements separate from the
[original-host reports](../380G10/README.md).

Current connection and execution instructions live in the
[project guide](../../../docs/PROJECT_GUIDE.md). The [common layout](../README.md)
defines guest output, host archives and historical relocation mappings.
