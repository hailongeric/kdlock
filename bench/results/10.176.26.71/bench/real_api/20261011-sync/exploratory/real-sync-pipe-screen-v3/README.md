# Real syscall lock comparison

Rates include the syscall, VFS/security checks, metadata search, result copying and userspace validation. Native/TCLock/KD use matched scoped substitutions; stock uses the captured kernel helper without substitution. The private file is populated before binding. Xattr/OFD metadata remains immutable; setfd changes only the preallocated descriptor flags. These are API microbenchmarks, not whole-application measurements.

Accepted and drained: 10/64 sessions. Failed: 1; not run: 53.

Whole-run columns are medians across rounds, in million operations/second. Peak ratios use the best valid 300 ms window from each backend. A speedup above 1 favors KD. Raw exports retain min/median/max/spread and NO_JIT runs. An operation is one xattr/OFD syscall or one F_SETFD plus a validating F_GETFD. For setfd, the count is the descriptor-number stride between workers.

| API/query | Entries/stride | Threads | Stock | Native | TCLock | KD | KD/native | KD/TC | Peak KD/native | Peak KD/TC | KD JIT runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pipebytes/query | 16 | 1 | 3.957 | 5.114 | 5.407 | 5.162 | 1.01× | 0.95× | 1.01× | 0.95× | 0/1 |
| pipebytes/query | 16 | 16 | 3.750 | 5.458 | 2.544 | 9.694 | 1.78× | 3.81× | 1.77× | 3.81× | 1/1 |
| pipebytes/query | 16 | 48 | 1.918 | 2.066 | — | — | — | — | — | — | 0/0 |
| pipebytes/query | 16 | 60 | — | — | — | — | — | — | — | — | 0/0 |
| pipebytes/query | 128 | 1 | — | — | — | — | — | — | — | — | 0/0 |
| pipebytes/query | 128 | 16 | — | — | — | — | — | — | — | — | 0/0 |
| pipebytes/query | 128 | 48 | — | — | — | — | — | — | — | — | 0/0 |
| pipebytes/query | 128 | 60 | — | — | — | — | — | — | — | — | 0/0 |
| pipecap/query | 16 | 1 | — | — | — | — | — | — | — | — | 0/0 |
| pipecap/query | 16 | 16 | — | — | — | — | — | — | — | — | 0/0 |
| pipecap/query | 16 | 48 | — | — | — | — | — | — | — | — | 0/0 |
| pipecap/query | 16 | 60 | — | — | — | — | — | — | — | — | 0/0 |
| pipecap/query | 128 | 1 | — | — | — | — | — | — | — | — | 0/0 |
| pipecap/query | 128 | 16 | — | — | — | — | — | — | — | — | 0/0 |
| pipecap/query | 128 | 48 | — | — | — | — | — | — | — | — | 0/0 |
| pipecap/query | 128 | 60 | — | — | — | — | — | — | — | — | 0/0 |

TCLock spin delegation is unmeasured. KD JIT counts are returned-body observations over the measured phase. A published translation alone is not a JIT execution. Throughput is not acquisition latency. The CPU-time export helps distinguish throughput gains from processor cost.
