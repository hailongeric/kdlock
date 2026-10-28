# Current nano comparison: October 28, 2026

630/630 measurements and 630/630 warmups passed the retained data, progress, placement, frozen-oracle and drain audit. Each point has exactly one two-second measurement; no real-world API cases were run.

Source `6d8c8be736ecfc23e1470e3256ee51d6e16e666e` on Linux `7.0.0-38-kdlock1`. All bodies use c01 or c16 and post256. KD mutex uses total cap 1024 and NUMA boundary 1024. This source includes the current rwsem reader-admission change. Rwsem/rwlock reads always execute locally; only writes may delegate.

Workers: `1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60`, on CPU prefixes 0..N-1 with collector CPU63. Counts above 32 cross NUMA nodes. Rates include post-lock work and compare complete implementations.

**Exploratory timing, n=1.** Strict timing qualification remains failed; there is no repeat variability estimate or significance claim. Returned-JIT and NO_JIT observations retain their execution classes. NO_JIT results cannot establish delegation gains.

Whole-run throughput at **60 workers**, Mops/s:

| Workload | Native | TCLock | KD | KD / Native | KD / TCLock | KD execution |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| [mutex c01, 100% writes](mutex-c01-w100/README.md) | 1.804 | 2.588 | 4.279 | 2.372× | 1.653× | RETURNED_JIT |
| [mutex c16, 100% writes](mutex-c16-w100/README.md) | 1.454 | 1.665 | 3.946 | 2.714× | 2.369× | RETURNED_JIT |
| [rwsem c01, 1% writes](rwsem-c01-w001/README.md) | 2.753 | 7.561 | 6.519 | 2.368× | 0.862× | NO_JIT |
| [rwsem c01, 20% writes](rwsem-c01-w020/README.md) | 1.175 | 4.682 | 3.146 | 2.678× | 0.672× | NO_JIT |
| [rwsem c16, 1% writes](rwsem-c16-w001/README.md) | 2.342 | 10.298 | 7.619 | 3.253× | 0.740× | NO_JIT |
| [rwsem c16, 20% writes](rwsem-c16-w020/README.md) | 1.084 | 3.781 | 2.441 | 2.251× | 0.645× | RETURNED_JIT |
| [rwlock c01, 1% writes](rwlock-c01-w001/README.md) | 6.761 | 7.780 | 7.704 | 1.140× | 0.990× | RETURNED_JIT |
| [rwlock c01, 20% writes](rwlock-c01-w020/README.md) | 3.125 | 4.235 | 3.544 | 1.134× | 0.837× | RETURNED_JIT |
| [rwlock c16, 1% writes](rwlock-c16-w001/README.md) | 9.089 | 11.217 | 7.959 | 0.876× | 0.710× | RETURNED_JIT |
| [rwlock c16, 20% writes](rwlock-c16-w020/README.md) | 2.317 | 4.007 | 2.435 | 1.051× | 0.608× | RETURNED_JIT |

Current rwsem c01, 20% writes, post256:

| Workers | Native | TCLock | KD | KD / Native | KD / TCLock | KD execution |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 8 | 1.862 | 4.551 | 4.931 | 2.648× | 1.084× | NO_JIT |
| 16 | 1.875 | 5.550 | 4.932 | 2.631× | 0.889× | NO_JIT |
| 32 | 1.818 | 5.920 | 5.126 | 2.819× | 0.866× | NO_JIT |
| 60 | 1.175 | 4.682 | 3.146 | 2.678× | 0.672× | NO_JIT |

[All 630 measurements](combined.csv) · [Audit and execution classes](audit.json)

Each workload link provides its complete worker grid and PNG/SVG chart. [Plot receipt](plot-receipt.json) records offline rendering completion, the matplotlib version and exact input/output hashes. The campaign source manifests and original session data remain in the separate raw evidence tree; this report does not modify them. [Evidence](evidence.json) binds the source, command, host captures, final guest health and archive hashes. [Archive verification](archive-verification.json) checked all 11 archives and 27,204 inventory paths. Both host captures verified the fixed 2.0 GHz policy, CPU placement and actual recovery snapshot; the guest remained on the same boot and drained with no new retained kernel faults.
