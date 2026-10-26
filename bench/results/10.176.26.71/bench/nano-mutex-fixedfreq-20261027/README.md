# Fixed-frequency mutex nano comparison: 2.0GHz target

Two public-ABI2 mutex workloads, 21 worker counts, Native/TCLock/KD, one two-second round per point. The complete campaign has 126 planned measurements. Strict host timing qualification remains failed; these are exploratory results with no repeat-variability estimate.

Both workloads perform 256 dependent post-unlock arithmetic rounds. KD uses total cap 1024 and NUMA boundary 768, with diagnostics compiled out. The optional two-word/post4 control is outside this campaign. Historical studies retain their original source, workload and policy identities.

The requested host control is **2.0GHz minimum = maximum**, **performance** governor, with **turbo disabled** on all 64 host CPU policies. Each published workload binds successful pin and before/after readback receipts. Effective frequency is checked separately using APERF/MPERF.

This is a separate rerun after the requested host frequency control. The [previous campaign](../nano-mutex-promoted-20261026/README.md) used an ondemand policy and showed a one-worker TCLock rate transition. Source and workload geometry are checked against that archive; rates are never pooled across the two frequency settings.

| Workload | Shared payload | Published measurements | Table and chart |
|---|---|---:|---|
| `mutex-throughput` | One padded counter, 64 bytes | 63 | [Results](mutex-throughput/README.md) |
| `mutex-locality` | 16 padded counters, 1024 bytes | 63 | [Results](mutex-locality/README.md) |

Published: **126/126 measurements** and **126 warmups**. Published phases passed frozen-source oracle replay, exact counts and final drain.

Worker counts: `1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60`.

Frozen source: `e5b7f84c41f33f3b15c4f3be0c87fcb943c54212`. Each workload audit records its provider ELF and archive hashes; no earlier campaign rates are pooled.

Observed whole-run throughput at **60 workers**, in Mops/s:

| Workload | Native | TCLock | KD | KD / Native | KD / TCLock |
|---|---:|---:|---:|---:|---:|
| `mutex-throughput` | 1.597 | 2.632 | 4.895 | 3.065× | 1.860× |
| `mutex-locality` | 1.450 | 1.793 | 3.831 | 2.643× | 2.136× |

`mutex-throughput`: KD has higher/lower observed rates than Native **18/3** and TCLock **19/2** across the 21 counts.
`mutex-throughput` observed losses: 1 worker versus Native (-0.11%); 1 worker versus TCLock (-0.29%); 2 workers versus Native (-0.30%); 2 workers versus TCLock (-0.43%); 6 workers versus Native (-7.44%).
`mutex-locality`: KD has higher/lower observed rates than Native **17/4** and TCLock **20/1** across the 21 counts.
`mutex-locality` observed losses: 1 worker versus Native (-0.39%); 1 worker versus TCLock (-0.33%); 3 workers versus Native (-11.69%); 4 workers versus Native (-10.14%); 5 workers versus Native (-5.06%).

These observed higher/lower counts are not statistically established wins; one round provides no repeat-variability estimate.

`mutex-throughput` records **NO_JIT** at workers 1, 2, 3.
`mutex-locality` records **NO_JIT** at workers 1, 2.
Low-count gains without returned JIT bodies are not delegation gains. Ratios compare the complete implementations and include post-unlock arithmetic.

One-worker observations from the two separate frequency-policy campaigns (Mops/s):

| Workload | Prior Native | Prior TCLock | Prior KD | Fixed-target Native | Fixed-target TCLock | Fixed-target KD |
|:---|---:|---:|---:|---:|---:|---:|
| `mutex-throughput` | 1.921 | 2.502 | 3.459 | 1.925 | 1.929 | 1.923 |
| `mutex-locality` | 1.919 | 2.513 | 3.454 | 1.927 | 1.926 | 1.919 |

The former one-worker gap is absent at comparable magnitude in the new observations. The early/late progress windows ([mutex-throughput](mutex-throughput/single-worker-windows.csv), [mutex-locality](mutex-locality/single-worker-windows.csv)) retain within-run variation, including the approximately 1% late dip in the locality KD one-worker run. These are separate runs, with no pooled means or statistical equivalence claim. Fixed frequency removes one known uncontrolled setting; it does not isolate every source of run variation.

[Frequency, environment and validation receipts](validation.json) retain the configured frequency policy and its measurement limits, focused validation provenance and final state. A fixed frequency request does not erase the separate failed strict task-membership gate.

The final readback confirms that the host remains at the requested **2.0GHz target**, **performance** governor and **turbo disabled** after the campaign. The previous ondemand settings were retained as evidence and were not restored.
