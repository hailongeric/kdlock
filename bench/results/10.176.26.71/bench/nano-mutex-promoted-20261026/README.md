# Promoted mutex nano comparison

Two public-ABI2 mutex workloads, 21 worker counts, Native/TCLock/KD, one two-second round per point. The complete campaign has 126 planned measurements. Strict host timing qualification remains failed; these are exploratory results with no repeat-variability estimate.

Both workloads perform 256 dependent post-unlock arithmetic rounds. KD uses total cap 1024 and NUMA boundary 768, with diagnostics compiled out. The optional two-word/post4 control is outside this campaign. Historical studies retain their original source, workload and policy identities.

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
| `mutex-throughput` | 1.461 | 3.111 | 5.567 | 3.811× | 1.790× |
| `mutex-locality` | 1.284 | 2.116 | 4.400 | 3.426× | 2.080× |

`mutex-throughput`: KD has higher/lower observed rates than Native **21/0** and TCLock **21/0** across the 21 counts.
`mutex-locality`: KD has higher/lower observed rates than Native **20/1** and TCLock **21/0** across the 21 counts.
KD was **3.76% below Native at four workers** in `mutex-locality`.

For `mutex-throughput`, the two-worker KD rate is only **0.089%** above TCLock: treat that point as essentially tied. These observed higher/lower counts are not statistically established wins; one round provides no repeat-variability estimate.

`mutex-throughput` records **NO_JIT** at workers 1, 2.
`mutex-locality` records **NO_JIT** at workers 1, 2.
Low-count gains without returned JIT bodies are not delegation gains. Ratios compare the complete implementations and include post-unlock arithmetic.

[Focused validation and retained setup failure](validation.json): the first orchestration attempt stopped before any test because the campaign directory did not exist. Creating its parent fixed setup; the subsequent basic and affected checks passed. The original failed attempt is preserved.

Final VM state: **idle**, kernel `6.1.159-kdclobber2`, boot ID `afe3a8d8-0c07-475b-89b4-163b822484b0`, **73 modules**, taint **12288**. Boot, kernel, module count and taint match the initial idle receipt.

Host endpoint captures recorded 70, 75, 75, 77 QEMU tasks versus the preserved 67-task qualification anchor. Strict qualification remains **failed**. All four endpoint checks passed the authorized exploratory policy: original task identities and placement were preserved, and added auxiliary workers were pinned to CPU 63. Full endpoint and final-idle hashes are retained in the validation receipt.
