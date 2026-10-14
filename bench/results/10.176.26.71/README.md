# Results from 10.176.26.71

This index covers the VM on the Ubuntu Xeon Gold 6438N host at
`eric@10.176.26.71`. Source edits stay on `380G10` and are synchronized before
execution. Receipts retain their own source, kernel, boot policy and topology.

## Current source verification

The [2026-10-14 owned-protocol optimization](bench/mutex_owned/20261014-hybrid/README.md)
integrates grant/completion notification and avoids a second queue-lock
acquisition on delegated pickup, while retaining the Linux-sized 32-byte object
and excluding original Linux target-lock calls. It audits 708 scored sessions
and 72 separate diagnostics, with [affected correctness checks](bench/mutex_owned/20261014-hybrid/validation.json).
Final finite and refill policies pass the fresh same-policy higher-thread
regression gates; neither meets the 97% Native primary target. Pre-capture
admission and bounded OSQ polling remain opt-in, and the owned defaults remain
capture-first, ratio 256 and finite FIFO. This is experimental protocol progress,
not Native parity; all rejected screens and raw evidence are retained.

## Earlier verification

The [KD-owned mutex study](bench/mutex_owned/20261013/README.md) implements the
same 32-byte object geometry as Linux with private owner/OSQ/sleep code and a
typed FIFO. It retains 426 scored sessions, 114 diagnostics and the
[correctness receipt](bench/mutex_owned/20261013/validation.json). Target probes
observe no original Linux calls for owned objects. Bounded refill improves this
prototype's throughput but neither owned policy meets the 97% target or retains
legacy KD's higher-thread performance. The owned protocol stays explicit and
experimental; legacy remains the benchmark default.

The [c01 protocol study](bench/mutex_protocol/20261013/README.md) expands the
optimization space to frame reuse, node layout, caller capture, native preflight
and bounded execution epochs. Its [separate eight-round follow-up](bench/mutex_protocol/20261013-post8/README.md)
adds exact-address caching and cross-node epochs after the user changed the
outside work. Both retain fresh Native/TCLock/KD baselines and all rejected
screens; neither establishes the two-metric 97% target. The accepted provider
remains `9b76719`. The linked receipts distinguish correctness, returned JIT,
performance acceptance and diagnostic evidence.

The [optimistic-spin study](bench/mutex_optimistic/20261013/README.md) measures
owner-aware retries and Linux OSQ across six candidates. All fail primary parity;
the accepted provider stays at `9b76719` and the rejected implementation is
preserved at `260d330`. Its [receipt](bench/mutex_optimistic/20261013/validation.json)
records 369 audited performance sessions, affected/protocol checks and restored
provider verification. The benchmark now checks original owner, wait-list and
OSQ drain explicitly.

The [c01 cost study](bench/mutex_c01_cost/20261013/README.md) compares fresh
Native, TCLock and KD mutex runs, profiles separate diagnostics and evaluates
successor-prefetch changes. Its [receipt](bench/mutex_c01_cost/20261013/validation.json)
retains affected checks, live owner/ACK and parking/cooling evidence, rejected
variants and all raw source identities. The 97% Native target is still unmet.

The [c01 admission receipt](bench/mutex_admission/20261013/validation.json)
records 14 basic/affected groups, 54 runner tests, six acceptance-auditor tests,
normal/SELFTEST builds and live cooling, parking and owner/ACK checks. All 543
benchmark/diagnostic sessions progressed and drained. The
[study](bench/mutex_admission/20261013/README.md) rejects all eight thresholds;
default 256 remains and the 97% Native target is unmet. The retained sampler
passes the specified higher-thread regression gates.

The [blocking-only mutex receipt](tests/mutex-blocking-only-20261012/validation.json)
records the `792db45` policy change: seven basic/affected groups, 87 runner/report
tests, normal/SELFTEST builds, sleeping-waiter and cross-NUMA owner/ACK probes,
and a fully drained 320,000-operation JIT run. It records all validation limits
and raw archive hashes. It is functional evidence, not a new performance matrix.

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
