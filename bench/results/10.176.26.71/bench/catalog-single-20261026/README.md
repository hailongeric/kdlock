# Single-round catalog campaign, October 26, 2026

The user requested all workloads from `docs/BENCHMARK_WORKLOADS.md`, one timed
repetition per point and immediate per-workload tables/charts. The runnable
standard catalog plan contains 51 workload configurations, each with 21 worker
counts and Native/TCLock/KD: 3,213 planned sessions. See [plan.json](plan.json).
All 51 configurations and 3,213 points were attempted: **3,166 valid timed
measurements and 47 KD helper-preparation failures**, all drained. Each measured
point has exactly one timed repetition. The [result index](progress.md) links
every table, CSV and chart. Failed points have no rate and break the chart line.
The [offline audit](audit.json) matched every published value, all 51 archive
hashes and 13,994 frozen source-file hashes. Recorded final health retained the
same recovery boot and original 73-module inventory.
The [corrected API command plan](plan-v2.json) restricts `--mutex-api public`
to pipe and seek mutex cases. The original OFD startup attempt rejected this
option before output creation or module loading; it measured no points. All
23 corrected API plans passed the guest runner's argument and plan checks.
The initial check harness had a missing Python import path; that failed check
is preserved separately from the successful check. Existing measurements and
their inputs remain unchanged.
The first xattr front/n16 attempt measured Native and TCLock at one worker,
then KD exhausted four eight-worker helper-learning waves without a returned
body. It drained and remains a preparation failure, with no KD timed rate.
The explicit xattr continuation retains the same sources, binaries, plan,
helper settings and probes. It skips previously attempted points and continues
only after that exact pre-measurement helper failure when cleanup succeeds and
the guest is idle. Other failures stop the campaign. Failed preparations remain
gaps; they are neither local throughput measurements nor delegation passes.
Ten focused continuation-boundary checks passed in the VM.
The lock/API portion and the explicitly requested separate
[mmap/fault extension](../catalog-mmap-single-20261026/README.md) are complete.
After the initial spin c01 stop, the user
explicitly authorized continuation as exploratory measurements. The
[result index](progress.md) records each completed workload.
Strict timing qualification remains failed throughout this continuation.

| Workload | Measurements | Correct and drained | Timing qualification | Results |
| --- | ---: | ---: | --- | --- |
| Spin c01/post64 | 63/63 | 63/63 | Failed host endpoint: 67 to 74 QEMU tasks | [Table](spin-c01/README.md), [CSV](spin-c01/table.csv), [PNG](spin-c01/throughput.png), [SVG](spin-c01/throughput.svg) |
| All 51 lock/API configurations, including c01 | 3,166/3,213 timed; 47 preparation failures | All 3,213 attempts drained | Strict qualification remains failed | [Tables/charts](progress.md); corrected API commands in plan-v2.json |
| Selected 64-node lists | Unrun | Not implemented by current payload/runners | Requires implementation and validation | Not substituted with 128 nodes |
| Private-backing mmap/fault timing and actual shared-mm mmap | 126/126 timed | All passed and drained | Exploratory; separate runner and kernel scopes | [Three tables/charts](../catalog-mmap-single-20261026/README.md) |
| Generic actual-page-fault throughput and full proc/application proposals | Unrun | No generic maintained throughput driver | Requires implementation | Not represented by synthetic or extracted snapshots |

Spin c01 used source base `90fd62f` and the current provider, with one round at
`1,2,3,4,5,6,7,8,12,16,20,24,28,32,36,40,44,48,52,56,60` workers. Each backend
used matched c01/post64 work, a two-second interval, 48,000 warmup operations
per worker and dedicated collector CPU 63. Tables show whole-run throughput;
CSV also retains peak rates and execution evidence. There is no variability
estimate or accepted performance claim. KD recorded zero JIT at 1–7 workers
and matching entries/completions at all remaining worker counts.

The initial host capture recorded the original 67 tasks, verified pins and the
existing `before-mutex-kdonly-20261017T140354Z` recovery snapshot. The workload
endpoint recorded seven additional QEMU `worker` tasks, all pinned to CPU 63.
Their names and placement do not establish harmlessness or causality. The
strict host endpoint failed; all rates retain that failure. No later quiet
capture replaces it. Further measurements began only after the user's explicit
exploratory-continuation instruction. That mode records auxiliary-worker
identities, placement and endpoint CPU/I/O counters, without declaring their
activity harmless. Original QEMU tasks, CPU placement, frequency policy,
memory bindings, recovery snapshot, workload correctness and drain remain checked.
Endpoint inventories do not provide continuous worker-lifetime observation.

Guest health confirmed idle, no project modules, 73 total modules and unchanged
recovery boot `8caa1264-4d93-4448-a6d8-6d8393d364ee`, kernel
`6.1.159-kdclobber2`. Post-run taint was 12288. No kernel build, installation or
reboot ran. Guest evidence remains at
`/root/kdlock-evidence/10.176.26.71/bench/catalog-single-20261026/`;
source-host raw receipts are under
`bench/results/10.176.26.71/raw/bench/catalog-single-20261026/`.
The `spin-c01-evidence.tar.gz` archive contains 2,802 members and 5,746,092
compressed bytes; SHA-256:
`e1495578117abf0944e79e8bafb34b0878c39009feccf5b833c7ce005a65d62b`.
Read-only archive review matched all 63 published rates to their original
receipts and verified the retained idle-health record.

Preparation synchronized 4,323 tracked source hashes to the idle guest. Both
basic C programs and all 27 affected reader/writer runner tests passed there.
The runner change accepts one timed round while retaining three-round parity
requirements. The single-round campaign does not claim a full test-suite pass.
