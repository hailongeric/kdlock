# Work spacing, throughput and completed-work fairness

Native's tight-loop advantage coincides with less equal completed-work distribution, but fairness alone does not explain the throughput differences. At post4 Native wins eight of nine matched coordinates; its Jain index is 0.787–0.950, against KD's 0.991–0.9996. At post256 Native is near equal in eight of nine cases (Jain at least 0.999659), and is more equal than KD in eight cases, while KD wins all nine throughput comparisons. The remaining Native case, one cache line at 16 workers, has Jain 0.9543.

Each triplet below is post-work **4 / 64 / 256**. Rates are Mops/s; Jain uses whole-run worker completion counts.

| Lines | Workers | Native Mops/s | KD Mops/s | Native Jain | KD Jain |
|---:|---:|:---|:---|:---|:---|
| 1 | 16 | 7.526 / 2.425 / 3.118 | 6.428 / 4.395 / 5.987 | 0.9130 / 0.9979 / 0.9543 | 0.9993 / 0.9999 / 0.9997 |
| 1 | 36 | 6.928 / 4.810 / 2.117 | 4.878 / 4.855 / 4.927 | 0.8384 / 0.7766 / 0.9997 | 0.9944 / 0.9932 / 0.9934 |
| 1 | 60 | 5.086 / 3.177 / 1.470 | 4.923 / 4.915 / 4.892 | 0.9137 / 0.8126 / 0.9999 | 0.9958 / 0.9957 / 0.9959 |
| 4 | 16 | 10.607 / 8.572 / 3.205 | 6.199 / 6.209 / 5.989 | 0.8210 / 0.9748 / 1.0000 | 0.9996 / 1.0000 / 1.0000 |
| 4 | 36 | 7.764 / 5.691 / 2.094 | 4.650 / 4.682 / 4.422 | 0.8144 / 0.7155 / 0.9999 | 0.9910 / 0.9933 / 0.9934 |
| 4 | 60 | 4.902 / 3.479 / 1.416 | 4.680 / 4.785 / 4.680 | 0.8575 / 0.8320 / 0.9999 | 0.9962 / 0.9958 / 0.9960 |
| 16 | 16 | 9.616 / 7.504 / 3.107 | 5.148 / 5.393 / 4.783 | 0.9497 / 0.9839 / 1.0000 | 0.9991 / 1.0000 / 1.0000 |
| 16 | 36 | 6.513 / 3.885 / 1.913 | 3.940 / 4.001 / 3.796 | 0.7870 / 0.2941 / 1.0000 | 0.9966 / 0.9933 / 0.9936 |
| 16 | 60 | 4.148 / 2.651 / 1.320 | 4.169 / 4.104 / 4.033 | 0.8793 / 0.7551 / 0.9999 | 0.9958 / 0.9958 / 0.9960 |

Moving from post4 to post256 lowers Native throughput by 58.57–73.03% across all nine matches, while KD changes by −7.10% to +0.99%. For example, one cache line at 60 workers changes from Native/KD **5.086/4.923** to **1.470/4.892 Mops/s**. The KD/Native ratio rises from 0.968 to 3.328 because Native falls much more; KD does not become faster in that comparison.

The intermediate spacing is not a monotonic fairness improvement. All six Native 36/60-worker cases have lower Jain at post64 than post4. For 16 cache lines at 36 workers, Jain is 0.7870 → 0.2941 → 0.999966 and maximum/minimum completed work is 13.58× → 21.07× → 1.034×. Whole-run totals show uneven completion, but do not reveal whether workers acquired in bursts, their individual wait latency, or starvation bounds.

Rapid reacquisition by a recent Native owner is a plausible explanation for some high-throughput, uneven tight-loop results. KD can serve another producer while the previous producer executes its post-unlock work; that overlap could preserve combined throughput as spacing grows. The source permits this overlap, but these measurements contain no acquisition-order or execution-overlap trace that proves either mechanism. The post-work factor executes dependent multiply/add instructions on the original worker after unlock, and completion includes that work. Changing its assembly repetition count also changes code footprint, so it is not a pure elapsed-delay intervention.

Increasing the critical footprint is not an unlimited advantage for KD. At post256/60, changing from one to sixteen resident cache lines reduces KD from 4.892 to 4.033 Mops/s and Native from 1.470 to 1.320; the ratio falls from 3.328 to 3.056. At post4/16, KD falls from 6.428 to 5.148 Mops/s over the same size change. These bodies update only 1/4/16 padded resident counters (64/256/1024 bytes); they do not establish behavior for larger cache misses, dependent pointer chains, sleeping bodies or real API call shells. A favorable nano setting must state both protected work and producer spacing.

[Full-precision fairness and rates](fairness.csv) · [Replay/input audit](fairness-audit.json) · [Factor matrix and charts](README.md).

All 54 archived measurements were independently recomputed and matched to the public matrix. Each setting is a single unprofiled exploratory observation from the same frozen source; no settings are pooled as repeated trials. Strict host timing qualification remains failed. Jain is sum(completed)² / (worker count × sum(completed²)); it describes completed-work distribution only.
