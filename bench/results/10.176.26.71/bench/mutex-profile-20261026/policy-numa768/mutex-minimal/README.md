# Nano shared record: mutex, 100% writes (mutex-minimal)

One timed repetition per point; no repeat variability estimate.
EXPLORATORY: strict timing qualification remains failed. Rates include post-lock work. Failed/unrun cases have no plotted rate.

| Workers | Native Mops/s | TCLock Mops/s | KD Mops/s | KD execution |
| ---: | ---: | ---: | ---: | --- |
| 16 | 6.518 | — | 5.979 | RETURNED_JIT |
| 32 | 7.627 | — | 5.908 | RETURNED_JIT |
| 36 | 7.777 | — | 5.343 | RETURNED_JIT |
| 60 | 5.623 | — | 5.595 | RETURNED_JIT |

[Full receipt table](table.csv)

![Throughput](throughput.png)

The shared payload is 64-byte resident record with 2 logical words; each operation uses 4 post-work rounds. The call shell is `bulk_ioctl`; these rates do not include a separate real API syscall per operation. Archive profile: `mutex`.

[Exact offline replay and archive hashes](audit.json). Every warmup and measurement passed the frozen-version oracle and exact count checks. Measurements also passed exact completion classification and source/frame or TCLock worker drain checks. Warmup did not record independent JIT entry/return deltas. One round provides no variability estimate. Full byte-preserved JSON receipts remain under the raw path recorded in `audit.json`.
Recorded provider policy: total cap **1024**, NUMA boundary **768**, deferred handoff **8**, scan budget **64**. [Frozen ELF policy identity](policy-identity.json) checks the compiled tags against every KD row; Native rows have no KD policy.
