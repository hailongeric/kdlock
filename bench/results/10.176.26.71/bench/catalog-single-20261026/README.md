# Single-round catalog campaign, October 26, 2026

The user requested all workloads from `docs/BENCHMARK_WORKLOADS.md`, one timed
repetition per point and immediate per-workload tables/charts. The runnable
standard catalog plan contains 51 workload configurations, each with 21 worker
counts and Native/TCLock/KD: 3,213 planned sessions. See [plan.json](plan.json).
The full request is **incomplete**. Only spin c01 has run.

| Workload | Measurements | Correct and drained | Timing qualification | Results |
| --- | ---: | ---: | --- | --- |
| Spin c01/post64 | 63/63 | 63/63 | Failed host endpoint: 67 to 74 QEMU tasks | [Table](spin-c01/README.md), [CSV](spin-c01/table.csv), [PNG](spin-c01/throughput.png), [SVG](spin-c01/throughput.svg) |
| Remaining 50 runnable catalog configurations | 0/3,150 | Unrun | Awaiting admission-policy decision | Exact commands in plan.json |
| Selected 64-node lists | Unrun | Not implemented by current payload/runners | Requires implementation and validation | Not substituted with 128 nodes |
| Private-backing mmap/fault timing and actual shared-mm mmap | Unrun | Separate runner and kernel scopes | Not covered by the standard-lock plan | No reused historical measurements |
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
capture replaces it, and no further measurement started after this rejection.

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
