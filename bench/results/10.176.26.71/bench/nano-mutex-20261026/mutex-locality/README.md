# Nano resident counters: mutex, 100% writes (mutex-locality)

One timed repetition per point; no repeat variability estimate.
EXPLORATORY: strict timing qualification remains failed. Rates include post-lock work. Failed/unrun cases have no plotted rate.

| Workers | Native Mops/s | TCLock Mops/s | KD Mops/s | KD execution |
| ---: | ---: | ---: | ---: | --- |
| 1 | 7.666 | 9.206 | 13.732 | NO_JIT |
| 8 | 6.494 | 2.464 | 4.897 | RETURNED_JIT |
| 16 | 5.938 | 2.374 | 5.264 | RETURNED_JIT |
| 32 | 4.334 | 2.166 | 4.606 | RETURNED_JIT |
| 36 | 4.413 | 2.255 | 3.948 | RETURNED_JIT |
| 60 | 2.651 | 2.188 | 4.045 | RETURNED_JIT |

[Full receipt table](table.csv)

![Throughput](throughput.png)

The shared payload is 16 independently cacheline-padded resident counters (1024 bytes); each operation uses 64 post-work rounds. The call shell is `bulk_ioctl`; these rates do not include a separate real API syscall per operation. Archive profile: `mutex-locality`.

[Exact offline replay and archive hashes](audit.json). Every warmup and measurement passed the frozen-version oracle and exact count checks. Measurements also passed exact completion classification and source/frame or TCLock worker drain checks. Warmup did not record independent JIT entry/return deltas. One round provides no variability estimate. Full byte-preserved JSON receipts remain under the raw path recorded in `audit.json`.
