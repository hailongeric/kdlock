# 16 resident cache lines, post256

One unprofiled observation per point. Strict host timing qualification remains failed. The shared write body and post-lock work run through the existing bulk ioctl shell.

| Workers | Native Mops/s | KD Mops/s | KD / Native | KD returned share |
|---:|---:|---:|---:|---:|
| 16 | 3.107 | 4.783 | 1.540 | 99.52% |
| 36 | 1.913 | 3.796 | 1.985 | 99.48% |
| 60 | 1.320 | 4.033 | 3.056 | 98.02% |

[Full-precision table](table.csv) · [Stage exact replay/hash audit](../audit.json)

![Throughput](throughput.png)

Frozen source: `b0d12ba86ca33dd71aaf5bc12b932f21c0b89525`. Each write updates 16 padded counters (1024 shared bytes); post-work rounds: 256. The table includes all completed operations. Returned-share classification uses exact returned-body counter deltas; publication alone is insufficient.

Both warmup and measurement passed the frozen oracle, exact payload/count checks and source/frame drain. Worker CPU/op is aggregate worker CPU time, including scheduled waiting; fairness is completed-work distribution. No repeat uncertainty or acquisition latency is measured. Changes across body size or spacing are separate factor settings and are never averaged together.
