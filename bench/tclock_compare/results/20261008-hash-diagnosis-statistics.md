# Targeted hash comparison

Frozen source: `11c8e72`. Targeted current-nopvspin hash investigation; historical results not pooled.

Record/timing/data audit: **PASS**; 90/90 accepted exported samples.

Three rounds per point. Rates are Mops/s. Triplets are min / median / max; spread is 100 × (max − min) / median. Best peaks and whole-run medians use their own strongest reference backend. Incomplete groups cannot establish parity.

## spin-local

Recorded nopvspin: True; complete expected grid: True.

| Threads | KD peak | TC peak | Native peak | KD / best peak | KD / best whole median |
|---:|---:|---:|---:|---:|---:|
| 2 | 2.5412 | 5.1061 | 5.6729 | 44.80% | 44.12% |
| 16 | 3.9084 | 5.0986 | 3.7410 | 76.66% | 77.06% |
| 24 | 3.3762 | 4.7575 | 2.0239 | 70.96% | 72.54% |
| 36 | 2.0173 | 2.7653 | 1.6938 | 72.95% | 73.27% |

| Threads | Arm | Valid rounds | Peak min / median / max | Peak spread | Whole min / median / max | Whole spread |
|---:|---|---:|---:|---:|---:|---:|
| 2 | kdlock | 3/3 | 2.3731 / 2.4823 / 2.5412 | 6.77% | 2.3680 / 2.4750 / 2.5359 | 6.78% |
| 2 | tclock | 3/3 | 4.9301 / 5.0909 / 5.1061 | 3.46% | 4.9170 / 5.0772 / 5.0917 | 3.44% |
| 2 | native | 3/3 | 5.5636 / 5.6337 / 5.6729 | 1.94% | 5.5542 / 5.6098 / 5.6565 | 1.82% |
| 16 | kdlock | 3/3 | 3.9014 / 3.9056 / 3.9084 | 0.18% | 3.8910 / 3.8980 / 3.8980 | 0.18% |
| 16 | tclock | 3/3 | 5.0738 / 5.0782 / 5.0986 | 0.49% | 5.0578 / 5.0584 / 5.0754 | 0.35% |
| 16 | native | 3/3 | 3.7137 / 3.7274 / 3.7410 | 0.73% | 3.6184 / 3.7133 / 3.7199 | 2.73% |
| 24 | kdlock | 3/3 | 3.3485 / 3.3681 / 3.3762 | 0.82% | 3.3312 / 3.3332 / 3.3393 | 0.24% |
| 24 | tclock | 3/3 | 4.6182 / 4.6211 / 4.7575 | 3.01% | 4.5852 / 4.5952 / 4.7291 | 3.13% |
| 24 | native | 3/3 | 2.0141 / 2.0183 / 2.0239 | 0.48% | 1.9913 / 1.9924 / 1.9985 | 0.36% |
| 36 | kdlock | 3/3 | 2.0156 / 2.0166 / 2.0173 | 0.08% | 2.0047 / 2.0065 / 2.0072 | 0.12% |
| 36 | tclock | 3/3 | 2.7636 / 2.7648 / 2.7653 | 0.06% | 2.7375 / 2.7386 / 2.7521 | 0.53% |
| 36 | native | 3/3 | 1.6813 / 1.6894 / 1.6938 | 0.74% | 1.6162 / 1.6460 / 1.6670 | 3.08% |

| Threads | Arm | JIT / delegation share | Minimum worker operations whole / peak | Node1 whole share | Node1 peak share |
|---:|---|---:|---:|---:|---:|
| 2 | kdlock | 0.000–0.000% | 2366720 / 355584 | n/a | n/a |
| 2 | tclock | UNMEASURED | 4891904 / 756224 | n/a | n/a |
| 2 | native | 0.000–0.000% | 5483264 / 822784 | n/a | n/a |
| 16 | kdlock | 99.900–99.901% | 484864 / 72448 | n/a | n/a |
| 16 | tclock | UNMEASURED | 628992 / 93952 | n/a | n/a |
| 16 | native | 0.000–0.000% | 452352 / 69632 | n/a | n/a |
| 24 | kdlock | 99.712–99.805% | 30976 / 4608 | 1.888–1.973% | 1.845–1.911% |
| 24 | tclock | UNMEASURED | 15872 / 2304 | 0.684–1.055% | 0.660–1.035% |
| 24 | native | 0.000–0.000% | 165376 / 25088 | 16.602–16.603% | 16.400–16.530% |
| 36 | kdlock | 99.897–99.899% | 99072 / 14592 | 49.987–49.990% | 50.000–50.082% |
| 36 | tclock | UNMEASURED | 134400 / 19968 | 49.977–50.035% | 49.938–50.090% |
| 36 | native | 0.000–0.000% | 89856 / 14080 | 44.374–44.444% | 44.008–44.444% |

## mutex-local

Recorded nopvspin: True; complete expected grid: True.

| Threads | KD peak | TC peak | Native peak | KD / best peak | KD / best whole median |
|---:|---:|---:|---:|---:|---:|
| 2 | 5.2665 | 7.1361 | 5.3111 | 73.80% | 71.75% |
| 16 | 3.6863 | 4.0730 | 4.7032 | 78.38% | 79.10% |
| 24 | 2.7997 | 3.7120 | 4.1949 | 66.74% | 39.69% |
| 36 | 2.6781 | 2.9043 | 2.7562 | 92.21% | 64.27% |

| Threads | Arm | Valid rounds | Peak min / median / max | Peak spread | Whole min / median / max | Whole spread |
|---:|---|---:|---:|---:|---:|---:|
| 2 | kdlock | 3/3 | 4.8459 / 5.0457 / 5.2665 | 8.34% | 4.8369 / 5.0389 / 5.2630 | 8.46% |
| 2 | tclock | 3/3 | 6.9526 / 7.0536 / 7.1361 | 2.60% | 6.9352 / 7.0231 / 7.1218 | 2.66% |
| 2 | native | 3/3 | 4.8651 / 5.0176 / 5.3111 | 8.89% | 4.8507 / 5.0082 / 5.2939 | 8.85% |
| 16 | kdlock | 3/3 | 3.6112 / 3.6265 / 3.6863 | 2.07% | 3.6914 / 3.7015 / 3.8121 | 3.26% |
| 16 | tclock | 3/3 | 4.0482 / 4.0490 / 4.0730 | 0.61% | 4.0342 / 4.0368 / 4.0556 | 0.53% |
| 16 | native | 3/3 | 4.6524 / 4.6984 / 4.7032 | 1.08% | 4.6306 / 4.6795 / 4.6808 | 1.07% |
| 24 | kdlock | 3/3 | 1.4466 / 2.3612 / 2.7997 | 57.31% | 1.4633 / 1.5566 / 1.8032 | 21.83% |
| 24 | tclock | 3/3 | 3.6468 / 3.6996 / 3.7120 | 1.76% | 3.6313 / 3.6712 / 3.6928 | 1.68% |
| 24 | native | 3/3 | 4.1412 / 4.1804 / 4.1949 | 1.29% | 3.8503 / 3.9224 / 3.9601 | 2.80% |
| 36 | kdlock | 3/3 | 1.8666 / 2.4209 / 2.6781 | 33.52% | 1.4347 / 1.7461 / 1.9319 | 28.47% |
| 36 | tclock | 3/3 | 2.2101 / 2.2277 / 2.9043 | 31.16% | 2.1978 / 2.2187 / 2.3264 | 5.79% |
| 36 | native | 3/3 | 2.7330 / 2.7486 / 2.7562 | 0.84% | 2.7056 / 2.7169 / 2.7240 | 0.67% |

| Threads | Arm | JIT / delegation share | Minimum worker operations whole / peak | Node1 whole share | Node1 peak share |
|---:|---|---:|---:|---:|---:|
| 2 | kdlock | 0.000–0.000% | 3883776 / 597760 | n/a | n/a |
| 2 | tclock | 0.000–0.000% | 6841856 / 1037824 | n/a | n/a |
| 2 | native | 0.000–0.000% | 3432192 / 489216 | n/a | n/a |
| 16 | kdlock | 16.356–19.330% | 396288 / 57856 | n/a | n/a |
| 16 | tclock | 97.405–97.499% | 499968 / 74496 | n/a | n/a |
| 16 | native | 0.000–0.000% | 454912 / 48384 | n/a | n/a |
| 24 | kdlock | 36.056–52.842% | 66304 / 9728 | 7.945–10.300% | 7.011–8.847% |
| 24 | tclock | 96.447–96.941% | 35072 / 5120 | 1.957–2.135% | 1.931–2.083% |
| 24 | native | 0.000–0.000% | 49152 / 2304 | 3.669–5.209% | 1.607–2.453% |
| 36 | kdlock | 21.988–49.784% | 50176 / 5120 | 40.282–42.918% | 41.860–45.475% |
| 36 | tclock | 92.021–97.757% | 104704 / 14080 | 50.259–53.302% | 50.211–64.777% |
| 36 | native | 0.000–0.000% | 75520 / 6400 | 42.336–43.325% | 43.372–43.584% |

## spin-split16

Recorded nopvspin: True; complete expected grid: True.

| Threads | KD peak | TC peak | Native peak | KD / best peak | KD / best whole median |
|---:|---:|---:|---:|---:|---:|
| 16 | 2.0386 | 2.7648 | 1.7067 | 73.74% | 74.05% |

| Threads | Arm | Valid rounds | Peak min / median / max | Peak spread | Whole min / median / max | Whole spread |
|---:|---|---:|---:|---:|---:|---:|
| 16 | kdlock | 3/3 | 2.0373 / 2.0386 / 2.0386 | 0.06% | 2.0311 / 2.0317 / 2.0326 | 0.07% |
| 16 | tclock | 3/3 | 2.7537 / 2.7542 / 2.7648 | 0.40% | 2.7406 / 2.7436 / 2.7563 | 0.57% |
| 16 | native | 3/3 | 1.6930 / 1.7022 / 1.7067 | 0.80% | 1.6801 / 1.6943 / 1.6971 | 1.00% |

| Threads | Arm | JIT / delegation share | Minimum worker operations whole / peak | Node1 whole share | Node1 peak share |
|---:|---|---:|---:|---:|---:|
| 16 | kdlock | 99.895–99.896% | 249856 / 37120 | 50.025–50.170% | 50.021–50.182% |
| 16 | tclock | UNMEASURED | 324864 / 47872 | 47.769–47.986% | 47.598–48.203% |
| 16 | native | 0.000–0.000% | 209920 / 31744 | 49.939–49.940% | 50.000–50.125% |

## mutex-split16

Recorded nopvspin: True; complete expected grid: True.

| Threads | KD peak | TC peak | Native peak | KD / best peak | KD / best whole median |
|---:|---:|---:|---:|---:|---:|
| 16 | 2.0932 | 2.2374 | 2.8269 | 74.04% | 55.38% |

| Threads | Arm | Valid rounds | Peak min / median / max | Peak spread | Whole min / median / max | Whole spread |
|---:|---|---:|---:|---:|---:|---:|
| 16 | kdlock | 3/3 | 1.4208 / 1.6546 / 2.0932 | 40.64% | 1.4517 / 1.5149 / 1.5856 | 8.84% |
| 16 | tclock | 3/3 | 2.2187 / 2.2340 / 2.2374 | 0.84% | 2.2112 / 2.2281 / 2.2281 | 0.76% |
| 16 | native | 3/3 | 2.6995 / 2.7850 / 2.8269 | 4.57% | 2.6780 / 2.7355 / 2.7653 | 3.19% |

| Threads | Arm | JIT / delegation share | Minimum worker operations whole / peak | Node1 whole share | Node1 peak share |
|---:|---|---:|---:|---:|---:|
| 16 | kdlock | 40.928–49.437% | 128768 / 16640 | 42.720–47.387% | 36.817–48.253% |
| 16 | tclock | 97.700–97.872% | 271360 / 40192 | 50.373–50.416% | 50.269–50.534% |
| 16 | native | 0.000–0.000% | 153088 / 2560 | 48.070–50.178% | 48.546–50.490% |

## Fixed 16-worker placement comparison

Values are split 8+8 divided by local16. Both builds retain NUMA-on; this is worker placement, not a remote-latency measurement.

| Lock | Arm | Best peak ratio | Peak median ratio | Whole median ratio |
|---|---|---:|---:|---:|
| spin | kdlock | 52.16% | 52.20% | 52.12% |
| spin | tclock | 54.23% | 54.24% | 54.24% |
| spin | native | 45.62% | 45.67% | 45.63% |
| mutex | kdlock | 56.78% | 45.63% | 40.93% |
| mutex | tclock | 54.93% | 55.17% | 55.19% |
| mutex | native | 60.11% | 59.28% | 58.46% |

## Scope

- JIT/delegation counts cover whole runs, not selected peaks.
- Finite worker progress does not establish a starvation bound.
- This audit checks exported records and raw timing/data/drain files; source-to-binary identity, live kernel identity, host frequency/affinity, full teardown logs and recovery remain separately verified.
