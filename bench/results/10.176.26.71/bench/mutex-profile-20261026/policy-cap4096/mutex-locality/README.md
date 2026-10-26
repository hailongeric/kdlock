# Nano resident counters: mutex, 100% writes (mutex-locality)

One timed repetition per point; no repeat variability estimate.
EXPLORATORY: strict timing qualification remains failed. Rates include post-lock work. Failed/unrun cases have no plotted rate.

| Workers | Native Mops/s | TCLock Mops/s | KD Mops/s | KD execution |
| ---: | ---: | ---: | ---: | --- |
| 16 | 4.021 | — | 5.155 | RETURNED_JIT |
| 32 | 4.443 | — | 4.708 | RETURNED_JIT |
| 36 | 4.180 | — | 3.753 | RETURNED_JIT |
| 60 | 2.630 | — | 4.111 | RETURNED_JIT |

[Full receipt table](table.csv)

![Throughput](throughput.png)

The shared payload is 16 independently cacheline-padded resident counters (1024 bytes); each operation uses 64 post-work rounds. The call shell is `bulk_ioctl`; these rates do not include a separate real API syscall per operation. Archive profile: `mutex-locality`.

[Exact offline replay and archive hashes](audit.json). Every warmup and measurement passed the frozen-version oracle and exact count checks. Measurements also passed exact completion classification and source/frame or TCLock worker drain checks. Warmup did not record independent JIT entry/return deltas. One round provides no variability estimate. Full byte-preserved JSON receipts remain under the raw path recorded in `audit.json`.
Recorded provider policy: total cap **4096**, NUMA boundary **256**, deferred handoff **8**, scan budget **64**. [Frozen ELF policy identity](policy-identity.json) checks the compiled tags against every KD row; Native rows have no KD policy.
