# Current comparison: 2026-10-11

The requested rerun completed **1,584 sessions**, with **1,582 accepted** and **1,584 drained** on `10.176.26.71`. Linux Native, TCLock and KDLock each ran three rounds at 22 worker counts from 1 through 64. Only **c01 and hash** workloads ran; **c02, c04, c08 and c16 were excluded**.

Two KD spin c01 sessions at **20 workers**, rounds 0 and 1, executed no JIT bodies. Their business data and drain checks passed, and their peak windows were independently verified, but the contended-JIT acceptance rule rejected them. They remain archived and excluded from scores; that point has only one accepted KD round and is marked incomplete. [Rejection audit](excluded-samples-audit.json).

Source was `0e1112e2a55d02ee4e574d2cfa0223d4854c9dff` plus the nine existing working-tree edits, whose exact patch and hashes are archived. The NUMA handoff and mutex fixes from that commit are included. No implementation changes were made for this rerun.

At 36 workers, KD leads both alternatives on spin c01, spin hash and mutex hash whole-run throughput. Mutex c01 remains **18.7% below Native**; mutex hash is **7.8% above Native** at that count. At 60 workers, mutex c01 also trails TCLock by **8.3%**. These are workload/count-specific results.

The cross-NUMA spin cost remains visible: KD c01 whole-run throughput drops **35.6%** from 32 to 36 workers, even though it remains ahead of Native and TCLock at 36. The rerun therefore does not show that cross-node scaling costs or all mutex performance gaps have been eliminated.

Each table entry is **best warmed peak / median whole-run throughput**, in **Mops/s**, over three rounds. The complete report retains all 22 worker counts, min/median/max/spread, every sample and CPU/NUMA progress. Spin/mutex use 64 post-work rounds; rwlocks use four, so compare backends within each row.

| Workload | Workers | Linux Native | TCLock | KDLock | KD execution |
| --- | ---: | ---: | ---: | ---: | --- |
| Spin c01 | 16 | 7.716 / 7.182 | 5.789 / 5.404 | 11.169 / 9.909 | ACTUAL_JIT |
| Spin c01 | 32 | 6.422 / 6.213 | 5.290 / 5.097 | 10.237 / 9.578 | ACTUAL_JIT |
| Spin c01 | 36 | 5.682 / 4.956 | 4.961 / 4.850 | 6.399 / 6.164 | ACTUAL_JIT |
| Spin c01 | 60 | 4.710 / 4.173 | 4.779 / 4.678 | 7.081 / 6.988 | ACTUAL_JIT |
| Spin c01 | 64 | 4.860 / 4.304 | 4.852 / 4.750 | 6.973 / 6.915 | ACTUAL_JIT |
| Spin hash | 16 | 2.922 / 2.875 | 3.589 / 3.553 | 4.873 / 4.841 | ACTUAL_JIT |
| Spin hash | 32 | 2.594 / 2.570 | 3.271 / 3.228 | 4.371 / 4.347 | ACTUAL_JIT |
| Spin hash | 36 | 2.089 / 2.062 | 3.003 / 2.976 | 3.941 / 3.889 | ACTUAL_JIT |
| Spin hash | 60 | 1.690 / 1.629 | 2.190 / 2.176 | 2.662 / 2.648 | ACTUAL_JIT |
| Spin hash | 64 | 1.638 / 1.565 | 2.181 / 2.165 | 2.648 / 2.633 | ACTUAL_JIT |
| Mutex c01 | 16 | 9.470 / 9.140 | 3.646 / 3.599 | 6.998 / 6.742 | ACTUAL_JIT |
| Mutex c01 | 32 | 7.698 / 6.716 | 3.459 / 3.304 | 6.467 / 6.278 | ACTUAL_JIT |
| Mutex c01 | 36 | 6.662 / 5.691 | 3.494 / 3.373 | 4.719 / 4.624 | ACTUAL_JIT |
| Mutex c01 | 60 | 4.394 / 3.703 | 3.237 / 3.196 | 3.029 / 2.932 | ACTUAL_JIT |
| Mutex c01 | 64 | 3.582 / 3.444 | 3.534 / 3.387 | 2.972 / 2.913 | ACTUAL_JIT |
| Mutex hash | 16 | 4.273 / 4.224 | 2.779 / 2.648 | 4.037 / 3.920 | ACTUAL_JIT |
| Mutex hash | 32 | 3.428 / 3.265 | 2.375 / 2.320 | 3.656 / 3.637 | ACTUAL_JIT |
| Mutex hash | 36 | 2.534 / 2.466 | 2.150 / 2.124 | 2.771 / 2.659 | ACTUAL_JIT |
| Mutex hash | 60 | 1.818 / 1.693 | 1.710 / 1.693 | 1.816 / 1.791 | ACTUAL_JIT |
| Mutex hash | 64 | 1.615 / 1.562 | 1.730 / 1.703 | 1.852 / 1.825 | ACTUAL_JIT |
| Rwlock c01 (1% writes) | 16 | 18.787 / 18.491 | 17.374 / 16.477 | 23.899 / 23.623 | MIXED |
| Rwlock c01 (1% writes) | 32 | 15.248 / 14.965 | 15.405 / 14.743 | 18.433 / 18.189 | ACTUAL_JIT |
| Rwlock c01 (1% writes) | 36 | 14.692 / 14.246 | 15.911 / 15.236 | 17.725 / 17.464 | ACTUAL_JIT |
| Rwlock c01 (1% writes) | 60 | 14.147 / 13.909 | 15.362 / 15.136 | 17.341 / 16.843 | ACTUAL_JIT |
| Rwlock c01 (1% writes) | 64 | 15.876 / 14.213 | 15.696 / 15.434 | 25.909 / 17.192 | ACTUAL_JIT |
| Rwlock c01 (20% writes) | 16 | 9.776 / 9.225 | 8.225 / 7.538 | 18.629 / 18.304 | ACTUAL_JIT |
| Rwlock c01 (20% writes) | 32 | 8.040 / 7.824 | 6.704 / 6.506 | 15.587 / 14.907 | ACTUAL_JIT |
| Rwlock c01 (20% writes) | 36 | 7.661 / 7.414 | 8.060 / 7.824 | 15.332 / 14.522 | ACTUAL_JIT |
| Rwlock c01 (20% writes) | 60 | 6.623 / 6.277 | 7.393 / 7.238 | 13.332 / 13.067 | NO_JIT |
| Rwlock c01 (20% writes) | 64 | 8.362 / 7.672 | 7.456 / 7.235 | 15.129 / 14.425 | NO_JIT |
| Rwlock hash (1% writes) | 16 | 17.776 / 17.168 | 16.617 / 14.968 | 19.309 / 18.967 | MIXED |
| Rwlock hash (1% writes) | 32 | 15.212 / 14.844 | 15.012 / 14.769 | 16.579 / 16.202 | ACTUAL_JIT |
| Rwlock hash (1% writes) | 36 | 14.427 / 13.577 | 15.431 / 15.193 | 15.380 / 14.870 | ACTUAL_JIT |
| Rwlock hash (1% writes) | 60 | 13.302 / 13.085 | 15.189 / 14.885 | 14.575 / 14.358 | ACTUAL_JIT |
| Rwlock hash (1% writes) | 64 | 13.200 / 12.816 | 15.112 / 14.892 | 14.587 / 14.202 | ACTUAL_JIT |
| Rwlock hash (20% writes) | 16 | 8.570 / 8.246 | 6.438 / 6.354 | 11.579 / 11.279 | ACTUAL_JIT |
| Rwlock hash (20% writes) | 32 | 7.206 / 6.950 | 5.618 / 5.552 | 9.541 / 9.246 | ACTUAL_JIT |
| Rwlock hash (20% writes) | 36 | 6.138 / 5.764 | 5.483 / 5.358 | 7.839 / 7.692 | ACTUAL_JIT |
| Rwlock hash (20% writes) | 60 | 5.100 / 5.015 | 5.126 / 5.015 | 6.566 / 6.360 | ACTUAL_JIT |
| Rwlock hash (20% writes) | 64 | 5.364 / 5.120 | 5.032 / 4.887 | 7.222 / 6.340 | ACTUAL_JIT |

Across 176 workload/count points, descriptive best-peak and whole-run comparisons have **53 FAIL**, **1 INCOMPLETE**, **3 MIXED_EXECUTION**, **119 PASS**. PASS means KD matched or exceeded both comparators on both metrics. These descriptive counts include native-path controls and do not establish JIT gains or satisfy strict rwlock parity by combining execution types.

Accepted KD sessions contain **356 ACTUAL_JIT** and **170 NO_JIT** runs. Status-separated aggregates and original runner parity evidence remain available.

The temporary 66-vCPU layout maps 32 worker cores to each NUMA node; counts above 32 cross nodes. **At 64 workers, the collector and QEMU services share physical core 63 with the last worker.** The 60-worker point avoids that worker/collector sharing. The host remains on the captured `ondemand` policy, with kernel Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, `nopvspin` and voluntary preemption.

All accepted warmed peaks were independently recomputed from raw progress. Frozen source, binary and JIT-image hashes passed verification. The archived copy reproduced every exported CSV byte. The regular 64-vCPU VM was restored, all pins and kernel policy rechecked, and a fresh recovery snapshot confirmed after archiving.

- [Complete tables and scaling charts](README.md)
- [Three-round statistics](statistics.csv)
- [Execution-type statistics](statistics-by-execution.csv)
- [Comparison ratios](comparison.csv)
- [Independent verification](verification.json)
- [Archive and replay receipt](archive-validation.json)
- [VM restoration](vm-restoration.json)

Raw archive SHA256: `9f2dca9c58eec1e0a0b26f134d429a2c52d175347c9efc38d0946c84d4636f77`. Verified copies are retained on both physical hosts; [paths and size](archive.json).
