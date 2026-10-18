# Independent offline replay

Replayed all 756 sessions, 253 execution-status summary groups and 126 comparison points from the saved archive. All arithmetic and identity checks passed: True. No repository runner or test program was executed.

Parity counts: {'PASS': 26, 'FAIL': 99, 'INCOMPLETE': 1}. The incomplete point has six valid sessions; it is split by KD JIT status, not skipped.

## Timed returned-JIT sessions

| Case | Completed / writes | Final CPU-hot / reported | Final lock-hot / reported | CPU checks | Lock residual samples |
| --- | ---: | ---: | ---: | --- | --- |
| rwsem-cacheline-c08-kdlock-w020-t16-r01 | 3 / 356556 | 16 / 16 | 5 / 16 | [1, 2] | [50, 1009] |
| rwsem-cacheline-c08-kdlock-w020-t36-r00 | 172 / 217344 | 36 / 36 | 4 / 36 | [2, 5] | [6, 1023] |
| rwsem-cacheline-c08-kdlock-w020-t36-r01 | 30 / 220261 | 36 / 36 | 4 / 36 | [2, 5] | [123, 1024] |
| rwsem-cacheline-c08-kdlock-w020-t36-r02 | 63 / 216064 | 36 / 36 | 4 / 36 | [2, 4] | [280, 526] |
| rwsem-cacheline-c08-kdlock-w020-t40-r00 | 489 / 190313 | 40 / 40 | 8 / 40 | [2, 4] | [31, 1004] |
| rwsem-cacheline-c08-kdlock-w020-t40-r01 | 726 / 191127 | 40 / 40 | 6 / 40 | [3, 5] | [7, 952] |
| rwsem-cacheline-c08-kdlock-w020-t40-r02 | 269 / 191488 | 40 / 40 | 3 / 40 | [3, 4] | [255, 916] |

These are measured entry/completion deltas, not warmup totals. Final heat records support the presence of admitted hot locks but do not identify when each CPU became hot or bound how much delegation occurred in a selected peak window.

## Sixty-worker outcomes

| Case | Native median Mops/s | KD median Mops/s | KD/Native whole | KD/Native best peak | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| cacheline-c01, writes 1% | 3.576498 | 1.065278 | 0.297855 | 0.295578 | NO_JIT; FAIL |
| cacheline-c01, writes 20% | 1.424055 | 0.402515 | 0.282654 | 0.282858 | NO_JIT; FAIL |
| cacheline-c08, writes 1% | 3.259181 | 1.069965 | 0.328293 | 0.330755 | NO_JIT; FAIL |
| cacheline-c08, writes 20% | 1.414840 | 0.397254 | 0.280776 | 0.273869 | NO_JIT; FAIL |
| rcuht-c00, writes 1% | 3.269816 | 1.055699 | 0.322862 | 0.321385 | NO_JIT; FAIL |
| rcuht-c00, writes 20% | 0.867688 | 0.401365 | 0.462569 | 0.466009 | NO_JIT; FAIL |

| KD 60-worker session | CPU-hot / reported | CPU checks | Lock-hot / reported | Lock residual samples |
| --- | ---: | --- | ---: | --- |
| rwsem-cacheline-c01-kdlock-w001-t60-r00 | 0 / 60 | [0, 0] | 0 / 0 | None |
| rwsem-cacheline-c01-kdlock-w001-t60-r01 | 0 / 60 | [0, 0] | 0 / 0 | None |
| rwsem-cacheline-c01-kdlock-w001-t60-r02 | 0 / 60 | [0, 0] | 0 / 0 | None |
| rwsem-cacheline-c01-kdlock-w020-t60-r00 | 60 / 60 | [1, 2] | 0 / 60 | [1, 1017] |
| rwsem-cacheline-c01-kdlock-w020-t60-r01 | 60 / 60 | [1, 2] | 0 / 60 | [37, 1018] |
| rwsem-cacheline-c01-kdlock-w020-t60-r02 | 60 / 60 | [1, 2] | 0 / 60 | [1, 1022] |
| rwsem-cacheline-c08-kdlock-w001-t60-r00 | 0 / 60 | [0, 0] | 0 / 0 | None |
| rwsem-cacheline-c08-kdlock-w001-t60-r01 | 0 / 60 | [0, 0] | 0 / 0 | None |
| rwsem-cacheline-c08-kdlock-w001-t60-r02 | 0 / 60 | [0, 0] | 0 / 0 | None |
| rwsem-cacheline-c08-kdlock-w020-t60-r00 | 60 / 60 | [4, 4] | 0 / 60 | [150, 562] |
| rwsem-cacheline-c08-kdlock-w020-t60-r01 | 60 / 60 | [3, 4] | 0 / 60 | [10, 1020] |
| rwsem-cacheline-c08-kdlock-w020-t60-r02 | 60 / 60 | [3, 4] | 0 / 60 | [4, 1012] |
| rwsem-rcuht-c00-kdlock-w001-t60-r00 | 0 / 60 | [0, 0] | 0 / 0 | None |
| rwsem-rcuht-c00-kdlock-w001-t60-r01 | 0 / 60 | [0, 0] | 0 / 0 | None |
| rwsem-rcuht-c00-kdlock-w001-t60-r02 | 0 / 60 | [0, 0] | 0 / 0 | None |
| rwsem-rcuht-c00-kdlock-w020-t60-r00 | 60 / 60 | [1, 2] | 0 / 60 | [19, 980] |
| rwsem-rcuht-c00-kdlock-w020-t60-r01 | 60 / 60 | [1, 2] | 0 / 60 | [40, 1021] |
| rwsem-rcuht-c00-kdlock-w020-t60-r02 | 60 / 60 | [1, 2] | 0 / 60 | [5, 1020] |

For all nine 60-worker sessions at 1% writes, every CPU reports zero CPU heat checks and remains cold; their per-CPU contention residuals range from 1 to 80 across these sessions, below the initial 1,024-sample threshold. No per-lock heat entry was created. This directly supports CPU heat admission as the reason these runs never entered delegation.

For all nine 60-worker sessions at 20% writes, all 60 CPUs are hot at shutdown but every reported lock remains cold. The saved delegation-queue slowpath, combiner and JIT-success counters are all zero in all 18 sixty-worker KD sessions. These are delegation counters, not proof of zero ordinary mutex waiting. The 20% logs do not retain each per-lock timing interval, so they cannot establish whether every cold lock lacked samples or missed a rate window. Do not explain all 20% cases merely by residual counts being below 1,025.

The unchanged mutex policy first evaluates CPU heat after 1,024 contention samples and uses `(entries >> 10) < 256` plus its existing CPU time bound. Once a CPU is hot, a lock needs 1,025 records within its existing lock time bound. Promotion/reset can restart per-lock samples. Final `contentions` and lock `count` fields are residual sampling windows, not lifetime contention totals. Low end-of-run residuals alone cannot prove that a lock was never hot; interpret them together with check counts, hot flags and actual measured JIT completions.

The rwsem admission layer can block writers before the mutex acquisition; those waits do not themselves count as mutex contention samples. This is a source-level explanation of why overall rwsem contention need not imply mutex heat, not a measured attribution of every slow operation.

No policy change or performance claim is inferred from the diagnostics. The acceptance runs at 80%/100% writes remain separate from this 1%/20% timed matrix.
