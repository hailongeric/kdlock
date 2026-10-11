# Real syscall lock comparison

Rates include the syscall, VFS/security checks, metadata search, result copying and userspace validation. Native/TCLock/KD use matched scoped substitutions; stock uses the captured kernel helper without substitution. The private file is populated before binding. Xattr/OFD metadata remains immutable; setfd changes only the preallocated descriptor flags. These are API microbenchmarks, not whole-application measurements.

Accepted and drained: 24/24 sessions. Failed: 0; not run: 0.

Whole-run columns are medians across rounds, in million operations/second. Peak ratios use the best valid 300 ms window from each backend. A speedup above 1 favors KD. Raw exports retain min/median/max/spread and NO_JIT runs. An operation is one xattr/OFD syscall or one F_SETFD plus a validating F_GETFD. For setfd, the count is the descriptor-number stride between workers.

| API/query | Entries/stride | Threads | Stock | Native | TCLock | KD | KD/native | KD/TC | Peak KD/native | Peak KD/TC | KD JIT runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| setfd/toggle | 16 | 1 | 1.988 | 2.399 | 3.259 | 3.266 | 1.36× | 1.00× | 1.00× | 1.00× | 0/1 |
| setfd/toggle | 16 | 16 | 3.666 | 4.808 | 4.899 | 5.015 | 1.04× | 1.02× | 1.04× | 1.02× | 1/1 |
| setfd/toggle | 16 | 48 | 2.490 | 2.958 | 4.769 | 4.594 | 1.55× | 0.96× | 1.60× | 0.99× | 1/1 |
| setfd/toggle | 128 | 1 | 3.596 | 3.288 | 3.264 | 3.257 | 0.99× | 1.00× | 0.99× | 1.00× | 0/1 |
| setfd/toggle | 128 | 16 | 4.136 | 5.245 | 5.514 | 5.568 | 1.06× | 1.01× | 1.07× | 1.00× | 1/1 |
| setfd/toggle | 128 | 48 | 2.658 | 3.185 | 4.934 | 4.291 | 1.35× | 0.87× | 1.40× | 0.90× | 1/1 |

TCLock spin delegation is unmeasured. KD JIT counts are returned-body observations over the measured phase. A published translation alone is not a JIT execution. Throughput is not acquisition latency. The CPU-time export helps distinguish throughput gains from processor cost.
