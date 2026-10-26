# 16 resident cache lines, post64: stat diagnostics

These are instrumented, exploratory observations, one per point. Every generated record has `score_eligible=false`; throughput here is diagnostic and is not a replacement for the unprofiled benchmark.

[Full-precision table](table.csv) · [Archive/hash and exact replay audit](audit.json)

| Workers | Backend | Diagnostic Mops/s | Worker CPU µs/op | Jain fairness | Max/min completed | Returned write share |
|---:|:---|---:|---:|---:|---:|---:|
| 16 | native | 1.441 | 8.629 | 0.9671 | 1.886 | 0.00% |
| 16 | kdlock | 2.370 | 6.710 | 0.9994 | 1.072 | 97.65% |
| 36 | native | 1.259 | 17.076 | 0.9984 | 1.194 | 0.00% |
| 36 | kdlock | 3.665 | 9.752 | 0.9933 | 1.357 | 99.14% |
| 60 | native | 1.036 | 12.469 | 0.9952 | 1.361 | 0.00% |
| 60 | kdlock | 3.786 | 15.657 | 0.9958 | 1.159 | 97.99% |

| Workers | Backend | Kernel cycles/op | Kernel instructions/op | Cycles/instruction | Cache misses/op | Cache miss fraction | Branch miss fraction |
|---:|:---|---:|---:|---:|---:|---:|---:|
| 16 | native | 15182.20 | 2974.73 | 5.104 | 0.0746 | 0.24% | 0.33% |
| 16 | kdlock | 13663.77 | 2263.71 | 6.036 | 0.0375 | 0.17% | 0.60% |
| 36 | native | 29788.34 | 6294.49 | 4.732 | 8.4656 | 18.80% | 0.18% |
| 36 | kdlock | 21846.11 | 2789.17 | 7.832 | 2.1030 | 8.25% | 0.49% |
| 60 | native | 22200.83 | 4353.56 | 5.099 | 20.3659 | 41.09% | 0.33% |
| 60 | kdlock | 37497.31 | 3686.98 | 10.170 | 1.1896 | 3.97% | 0.37% |

![Diagnostic counters](counters.png)

Perf stat covers the measured client and inherited threads, including client startup and collection. Preparation and warmup are excluded. Hardware events use `:k`; software events retain their requested scope. Dividing these all-client counts by completed operations does not isolate the protected body. All reported events must have valid runtime metadata; multiplexing is retained explicitly in the CSV.

Worker CPU/op is the sum of each worker’s recorded CPU time divided by completed operations; it includes scheduled waiting and operation/post-work. Jain fairness describes completed work distribution, not acquisition order or latency. Requester NUMA nodes do not identify the JIT executor. Reciprocal throughput is an aggregate completion interval, not operation latency.

Virtual PMU behavior, sampling skid and instrumentation can change contention and observed costs. The VM smoke probe included unknown user IPs even for `cycles:k`; those are retained. Flat symbols containing several code paths cannot by themselves separate polling from service. One observation gives no variability estimate; strict host timing qualification remains failed.

Frozen source: `c438bb2566245993e274ffb9c1f1e30196b426cb`. Exact replay validated 6 measurements and 6 warmups, with ordinary final count, source/frame retirement and provider drain checks. Full receipts and reproducible analysis remain at `bench/results/10.176.26.71/raw/bench/mutex-profile-20261026/receipts/baseline-stat/mutex-locality` and `bench/results/10.176.26.71/raw/bench/mutex-profile-20261026/analysis/scripts/e259ea85d9af4c720a72c0a2c555ea5f9d8f5c07cf6064d3c8dcfd4babf413fd.py`.
