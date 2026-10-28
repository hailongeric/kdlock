# Nano comparison after rwsem reader-cohort optimization: October 28, 2026

630/630 measurements and 630/630 warmups passed the retained data, progress, placement, frozen-oracle and drain audit. Each point has exactly one two-second measurement; no real-world API cases were run.

Source `edf1cc06d68d476b8d4382a9f24258471a76f8d3` on Linux `7.0.0-38-kdlock1`. All bodies use c01 or c16 and post256. KD mutex uses total cap 1024 and NUMA boundary 1024. This source includes the rwsem queued-reader preference from acc4dbc2. Rwsem/rwlock reads always execute locally; only writes may delegate.

Workers: `1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60`, on CPU prefixes 0..N-1 with collector CPU63. Counts above 32 cross NUMA nodes. Rates include post-lock work and compare complete implementations.

**Exploratory timing, n=1.** Strict timing qualification remains failed; there is no repeat variability estimate or significance claim. Returned-JIT and NO_JIT observations retain their execution classes. NO_JIT results cannot establish delegation gains.

Whole-run throughput at **60 workers**, Mops/s:

| Workload | Native | TCLock | KD | KD / Native | KD / TCLock | KD execution |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| [mutex c01, 100% writes](mutex-c01-w100/README.md) | 1.739 | 2.602 | 4.313 | 2.481× | 1.658× | RETURNED_JIT |
| [mutex c16, 100% writes](mutex-c16-w100/README.md) | 1.528 | 1.716 | 4.000 | 2.617× | 2.331× | RETURNED_JIT |
| [rwsem c01, 1% writes](rwsem-c01-w001/README.md) | 2.777 | 7.577 | 7.569 | 2.726× | 0.999× | NO_JIT |
| [rwsem c01, 20% writes](rwsem-c01-w020/README.md) | 1.170 | 4.740 | 3.772 | 3.224× | 0.796× | RETURNED_JIT |
| [rwsem c16, 1% writes](rwsem-c16-w001/README.md) | 2.348 | 10.230 | 10.064 | 4.286× | 0.984× | RETURNED_JIT |
| [rwsem c16, 20% writes](rwsem-c16-w020/README.md) | 1.076 | 3.740 | 3.608 | 3.352× | 0.965× | RETURNED_JIT |
| [rwlock c01, 1% writes](rwlock-c01-w001/README.md) | 7.002 | 7.787 | 7.510 | 1.072× | 0.964× | RETURNED_JIT |
| [rwlock c01, 20% writes](rwlock-c01-w020/README.md) | 3.200 | 4.309 | 3.591 | 1.122× | 0.833× | RETURNED_JIT |
| [rwlock c16, 1% writes](rwlock-c16-w001/README.md) | 9.199 | 10.928 | 8.442 | 0.918× | 0.772× | RETURNED_JIT |
| [rwlock c16, 20% writes](rwlock-c16-w020/README.md) | 2.291 | 3.931 | 2.468 | 1.078× | 0.628× | RETURNED_JIT |

Current rwsem c01, 20% writes, post256:

| Workers | Native | TCLock | KD | KD / Native | KD / TCLock | KD execution |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 8 | 1.889 | 4.546 | 6.049 | 3.203× | 1.331× | RETURNED_JIT |
| 16 | 1.870 | 5.497 | 5.336 | 2.854× | 0.971× | RETURNED_JIT |
| 32 | 1.813 | 5.948 | 5.052 | 2.787× | 0.849× | RETURNED_JIT |
| 60 | 1.170 | 4.740 | 3.772 | 3.224× | 0.796× | RETURNED_JIT |

[All 630 measurements](combined.csv) · [Audit and execution classes](audit.json)

Each workload link provides its complete worker grid and PNG/SVG chart. [Plot receipt](plot-receipt.json) records offline rendering completion, the matplotlib version and exact input/output hashes. The campaign source manifests and original session data remain in the separate raw evidence tree; this report does not modify them.

[Evidence](evidence.json) binds the source commit, launch receipt, host captures,
final guest health and archive hashes. [Archive verification](archive-verification.json)
checked all eleven archives and 27,203 inventory paths. Both host captures
verified fixed 2.0 GHz policies, CPU placement and the actual recovery snapshot.
All 630 retained session kernel logs were fault-free and the guest finished idle
on the same boot. The global dmesg ring no longer reaches the estimated campaign
start; its retained contents are not claimed as complete historical coverage.
