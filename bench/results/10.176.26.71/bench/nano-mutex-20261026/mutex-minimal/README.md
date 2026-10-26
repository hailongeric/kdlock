# Nano shared record: mutex, 100% writes (mutex-minimal)

One timed repetition per point; no repeat variability estimate.
EXPLORATORY: strict timing qualification remains failed. Rates include post-lock work. Failed/unrun cases have no plotted rate.

| Workers | Native Mops/s | TCLock Mops/s | KD Mops/s | KD execution |
| ---: | ---: | ---: | ---: | --- |
| 1 | 35.466 | 57.136 | 52.066 | NO_JIT |
| 8 | 11.177 | 3.798 | 6.233 | RETURNED_JIT |
| 16 | 10.472 | 3.631 | 6.356 | RETURNED_JIT |
| 32 | 8.256 | 3.218 | 5.889 | RETURNED_JIT |
| 36 | 7.367 | 3.223 | 4.853 | RETURNED_JIT |
| 60 | 5.704 | 3.164 | 5.011 | RETURNED_JIT |

[Full receipt table](table.csv)

![Throughput](throughput.png)

The shared payload is 64-byte resident record with 2 logical words; each operation uses 4 post-work rounds. The call shell is `bulk_ioctl`; these rates do not include a separate real API syscall per operation. Archive profile: `mutex`.

[Exact offline replay and archive hashes](audit.json). Every warmup and measurement passed the frozen-version oracle and exact count checks. Measurements also passed exact completion classification and source/frame or TCLock worker drain checks. Warmup did not record independent JIT entry/return deltas. One round provides no variability estimate. Full byte-preserved JSON receipts remain under the raw path recorded in `audit.json`.
