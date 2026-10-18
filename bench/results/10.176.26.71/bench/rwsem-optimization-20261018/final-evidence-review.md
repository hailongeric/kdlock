# Targeted final evidence review

PASS: 11988 offline checks. Final rwsem: 756/756 valid sessions, 126 points; reference: 270/270, 30 points. Raw rates, the CSVs and analysis JSON agree for all 60-worker cases, all regression cases and all spinning-rwlock references. All measured sessions drained and passed data checks. No benchmark was rerun.

Baseline/final environments match except command-line ordering/output. The 233-entry source manifests differ only in `include/kd_rwsem.h` and `kernel_module/kd_rwsem.c`; the KD mutex and runner hashes match. Final KD rwsem has 155 PASS and 223 NO_JIT sessions, with 7,275,620 completed JIT bodies. Mixed final statuses at c01 write20 workers 5/6/7 and old c08 write20 workers16 are excluded from the affected homogeneous comparisons.

## Sixty-worker sleeping rwsem

Mops/s; whole is the three-run median, peak is the maximum observed warmed window.

| Case | Writes | Before KD whole / peak | Final KD whole / peak | Final Native whole / peak | KD before ratio whole / peak | KD Native ratio whole / peak |
| --- | --- | --- | --- | --- | --- | --- |
| c01 | 1% | 1.065278 / 1.090203 | 7.899619 / 8.140396 | 3.560574 / 3.668790 | 7.4155 / 7.4669 | 2.2186 / 2.2188 |
| c01 | 20% | 0.402515 / 0.421199 | 2.196955 / 2.270568 | 1.421012 / 1.485283 | 5.4581 / 5.3907 | 1.5460 / 1.5287 |
| c08 | 1% | 1.069965 / 1.104762 | 7.757555 / 7.912945 | 3.298830 / 3.378941 | 7.2503 / 7.1626 | 2.3516 / 2.3418 |
| c08 | 20% | 0.397254 / 0.408739 | 2.182789 / 2.305521 | 1.411500 / 1.553197 | 5.4947 / 5.6406 | 1.5464 / 1.4844 |
| RCUHT | 1% | 1.055699 / 1.090516 | 7.312333 / 7.548959 | 3.261718 / 3.363302 | 6.9265 / 6.9224 | 2.2419 / 2.2445 |
| RCUHT | 20% | 0.401365 / 0.418718 | 2.046790 / 2.119650 | 0.873375 / 0.901090 | 5.0996 / 5.0622 | 2.3435 / 2.3523 |

## Low-count regression detail

All 12 before/after comparison failures occur at 1–5 workers. Ten are at least 5% worse on one metric; the single-worker c01 differences are −1.79% whole/−0.10% peak (1% writes) and +0.13% whole/−0.03% peak (20% writes). The worst case is c08, 20% writes, two workers: −72.45% whole and −72.96% peak. These are descriptive differences, not significance tests.

| Case | Workers | Before KD whole [min,max] | Final KD whole [min,max] | CPU ns/op before → final | Native whole before → final |
| --- | --- | --- | --- | --- | --- |
| c01 w20 | 2 | 35.137 [34.558,35.579] | 10.065 [9.293,10.328] | 40.6 → 198.6 | 7.442 → 6.690 |
| c01 w20 | 3 | 18.822 [18.165,19.595] | 7.982 [7.875,9.088] | 104.0 → 375.6 | 3.946 → 3.695 |
| c01 w20 | 4 | 10.596 [10.212,11.506] | 7.619 [7.143,7.687] | 231.5 → 522.2 | 3.302 → 3.224 |
| c08 w20 | 2 | 32.149 [31.716,32.351] | 8.859 [8.482,8.875] | 42.8 → 225.6 | 3.842 → 2.469 |
| c08 w20 | 3 | 18.794 [17.353,19.143] | 8.035 [7.409,8.089] | 98.5 → 371.4 | 3.016 → 2.963 |
| c08 w20 | 4 | 11.480 [10.249,11.898] | 6.458 [6.140,7.732] | 205.0 → 616.1 | 2.951 → 3.338 |

At two/three workers, every KD repetition is NO_JIT before and after. All new warmed peaks are below all old warmed peaks. Old workers consume roughly 1.2–1.5 CPU-seconds each per two-second session; final workers consume nearly 2.0 each. The old samples are somewhat less balanced, but every worker progresses in every eligible 10ms interval. Median per-interval Jain fairness is 0.958–0.999 before and 0.998–1.000 after. A stalled worker does not explain the old score at that resolution.

The source change replaces immediate wait-event fallback with up to 16,384 predicate probes before sleeping, alongside split queues and cacheline separation. The timing/CPU evidence is consistent with more simultaneous busy contention at low counts. Baseline blocking may reduce simultaneous contention and permit inexpensive bursts, but no low-count scheduler trace was captured: sleeping versus other scheduling effects and sub-10ms burst patterns cannot be isolated. The 60-worker function profiles cannot establish a low-count cause.

The six final/Native comparison failures are c01 w20 t1/t36, c08 w1 t2, c08 w20 t1/t36, and RCUHT w20 t1. Exact ratios and both metrics are retained in JSON.

## Separate spinning-rwlock reference

KD/TCLock wins both metrics at 28/30 points; exceptions: c08 w20 t1 (0.99147 whole, 0.99181 peak) and RCUHT w1 t60 (0.95930 whole, 0.95804 peak). KD/Native wins both at 29/30, with c08 w20 t1 at 0.95317 whole/0.93843 peak. TCLock/Native wins both at 15/30. All reference groups have three homogeneous repetitions. TCLock delegation remains UNMEASURED; its NATIVE JIT label is not proof of local execution. These are rwlock references, not rwsem parity.

| Case | Writes | Native whole / peak | TCLock whole / peak | KD whole / peak | KD/TCLock whole / peak | KD/Native whole / peak |
| --- | --- | --- | --- | --- | --- | --- |
| c01 | 1% | 13.635906 / 14.139888 | 15.394243 / 15.842158 | 16.532801 / 17.358086 | 1.0740 / 1.0957 | 1.2124 / 1.2276 |
| c01 | 20% | 5.991749 / 6.265772 | 7.402139 / 7.588328 | 13.300282 / 13.536389 | 1.7968 / 1.7838 | 2.2198 / 2.1604 |
| c08 | 1% | 13.115564 / 13.644888 | 14.957070 / 15.229154 | 15.859972 / 16.108628 | 1.0604 / 1.0577 | 1.2092 / 1.1806 |
| c08 | 20% | 5.089363 / 5.347175 | 7.098703 / 7.281177 | 10.997403 / 11.305963 | 1.5492 / 1.5528 | 2.1609 / 2.1144 |
| RCUHT | 1% | 12.775740 / 13.224646 | 14.933495 / 15.213359 | 14.325776 / 14.574940 | 0.9593 / 0.9580 | 1.1213 / 1.1021 |
| RCUHT | 20% | 4.957095 / 5.166006 | 4.954788 / 5.053015 | 6.397125 / 6.912230 | 1.2911 / 1.3679 | 1.2905 / 1.3380 |

## Diagnostic scope and counts

Each profile runs c01/write20/60 workers, Native and KD, three repetitions, with the same profiler-script SHA256 and kernel config. Source manifest hashes match the before/final performance sources respectively. Tracing restoration and guest idle are recorded. Baseline KD profiles are NO_JIT3; final KD profiles are PASS3, so this compares changed source plus observed execution behavior, not an isolated queue-only effect. Instrumentation covers all CPUs/tasks during measure, including client startup and publication/counter reads, while excluding preparation/warmup/cleanup. It includes background work and changes execution cost; rates and inclusive nested function times are not scored.

| Function | KD calls/op before → final | Native calls/op before → final |
| --- | --- | --- |
| schedule | 1.160244 → 0.001123 | 0.137182 → 0.128964 |
| try_to_wake_up | 2.035045 → 0.001140 | 1.007869 → 1.008216 |
| _raw_spin_lock_irqsave | 9.684372 → 0.014329 | 2.444546 → 2.420616 |
| native_queued_spin_lock_slowpath | 2.971247 → 0.000222 | 0.131083 → 0.129444 |
| prepare_to_wait_event | 2.046040 → 0.000819 | 0.000057 → 0.000029 |
| autoremove_wake_function | 2.031441 → 0.000810 | 0.000000 → 0.000000 |
| kd_up_read | 0.804220 → 2.226582 | — |

KD `kd_up_read` rises from 0.804 to 2.227 calls/op despite ~0.8 reads/op. The function is also called to roll back a raced reader admission; these counts must not be interpreted as completed read unlocks alone. The reduction in waitqueue/scheduler calls supports avoiding frequent sleeps at high contention, without establishing exclusive CPU costs or ownership.

Full exact worker counts, CPU times, status groups, reference ratios, source IDs, profile counts and input hashes are in `final-evidence-review.json`.
