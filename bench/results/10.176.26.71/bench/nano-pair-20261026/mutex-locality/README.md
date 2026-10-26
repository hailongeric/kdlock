# Nano resident counters: mutex, 100% writes (mutex-locality)

One timed repetition per point; no repeat variability estimate.
EXPLORATORY: strict timing qualification remains failed. Rates include post-lock work. Failed/unrun cases have no plotted rate.

| Workers | Native Mops/s | TCLock Mops/s | KD Mops/s | KD execution |
| ---: | ---: | ---: | ---: | --- |
| 1 | 28.481 | 55.266 | 43.603 | NO_JIT |
| 8 | 7.892 | 2.295 | 5.962 | RETURNED_JIT |
| 16 | 7.863 | 2.394 | 5.406 | RETURNED_JIT |
| 32 | 6.351 | 2.166 | 4.911 | RETURNED_JIT |
| 36 | 6.589 | 2.235 | 4.104 | RETURNED_JIT |
| 60 | 4.394 | 2.194 | 4.134 | RETURNED_JIT |

[Full receipt table](table.csv)

![Throughput](throughput.png)

The shared payload is 16 independently cacheline-padded resident counters (1024 bytes); each operation uses 4 post-work rounds. The call shell is `bulk_ioctl`; these rates do not include a separate real API syscall per operation. Archive profile: `mutex-locality`.

[Exact offline replay and archive hashes](audit.json). Every warmup and measurement passed the frozen-version oracle and exact count checks. Measurements also passed exact completion classification and source/frame or TCLock worker drain checks. Warmup did not record independent JIT entry/return deltas. One round provides no variability estimate.

Full byte-preserved JSON receipts remain under the raw path recorded in `audit.json`.
