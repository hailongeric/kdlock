# Nano resident counters: mutex, 100% writes (mutex-locality-post64-local)

One timed repetition per point; no repeat variability estimate.
EXPLORATORY: strict timing qualification remains failed. Rates include post-lock work. Failed/unrun cases have no plotted rate.

| Workers | Native Mops/s | TCLock Mops/s | KD Mops/s | KD execution |
| ---: | ---: | ---: | ---: | --- |
| 1 | — | — | 7.686 | NO_JIT |
| 16 | — | — | 2.652 | NO_JIT |
| 60 | — | — | 0.519 | NO_JIT |

[Full receipt table](table.csv)

![Throughput](throughput.png)

The shared payload is 16 independently cacheline-padded resident counters (1024 bytes); each operation uses 64 post-work rounds. The call shell is `bulk_ioctl`; these rates do not include a separate real API syscall per operation. Archive profile: `mutex-locality-local`.

[Exact offline replay and archive hashes](audit.json). Every warmup and measurement passed the frozen-version oracle and exact count checks. Measurements also passed exact completion classification and source/frame or TCLock worker drain checks. Warmup did not record independent JIT entry/return deltas. One round provides no variability estimate. Full byte-preserved JSON receipts remain under the raw path recorded in `audit.json`.

This is the separately compiled KD local control. Mutex writers use callable lock/unlock symbols; rwsem writers use the local admission path instead of the outer writer phase. This is not an isolated switch for JIT execution alone.
