# Results from 10.176.26.71

This index covers the VM on the Ubuntu Xeon Gold 6438N host at
`eric@10.176.26.71`. Source edits stay on `380G10`. Each report retains its own
source, kernel, boot policy, topology, measurements and failed attempts.
Current commands and accepted-provider status live in the
[project guide](../../../docs/PROJECT_GUIDE.md) and
[performance status](../../../docs/PERFORMANCE.md).

## Current owned-protocol optimization

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
