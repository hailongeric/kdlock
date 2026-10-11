# Real syscall lock comparison

Rates include the syscall, VFS/security checks, metadata search, result copying and userspace validation. Native/TCLock/KD use matched scoped substitutions; stock uses the captured kernel helper without substitution. The private file is populated before binding. Xattr/OFD metadata remains immutable; setfd changes only the preallocated descriptor flags. These are API microbenchmarks, not whole-application measurements.

Accepted and drained: 144/144 sessions. Failed: 0; not run: 0.

Whole-run columns are medians across rounds, in million operations/second. Peak ratios use the best valid 300 ms window from each backend. A speedup above 1 favors KD. Raw exports retain min/median/max/spread and NO_JIT runs. An operation is one xattr/OFD syscall or one F_SETFD plus a validating F_GETFD. For setfd, the count is the descriptor-number stride between workers.

| API/query | Entries/stride | Threads | Stock | Native | TCLock | KD | KD/native | KD/TC | Peak KD/native | Peak KD/TC | KD JIT runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| setfd/toggle | 16 | 1 | 3.556 | 3.291 | 3.254 | 3.238 | 0.98× | 1.00× | 0.99× | 1.00× | 0/3 |
| setfd/toggle | 16 | 8 | 4.332 | 4.804 | 4.634 | 3.889 | 0.81× | 0.84× | 0.78× | 0.82× | 3/3 |
| setfd/toggle | 16 | 16 | 4.627 | 5.156 | 5.805 | 5.749 | 1.11× | 0.99× | 1.09× | 0.94× | 3/3 |
| setfd/toggle | 16 | 32 | 4.112 | 4.496 | 5.176 | 5.808 | 1.29× | 1.12× | 1.29× | 1.09× | 3/3 |
| setfd/toggle | 16 | 48 | 2.505 | 2.769 | 5.125 | 5.565 | 2.01× | 1.09× | 1.94× | 1.08× | 3/3 |
| setfd/toggle | 16 | 60 | 2.294 | 2.382 | 4.819 | 5.415 | 2.27× | 1.12× | 2.21× | 1.10× | 3/3 |
| setfd/toggle | 512 | 1 | 3.580 | 3.288 | 3.253 | 3.252 | 0.99× | 1.00× | 0.99× | 1.00× | 0/3 |
| setfd/toggle | 512 | 8 | 6.256 | 6.356 | 4.353 | 3.570 | 0.56× | 0.82× | 0.57× | 0.84× | 3/3 |
| setfd/toggle | 512 | 16 | 6.155 | 6.841 | 5.675 | 6.989 | 1.02× | 1.23× | 1.07× | 1.22× | 3/3 |
| setfd/toggle | 512 | 32 | 5.593 | 5.221 | 5.001 | 8.026 | 1.54× | 1.60× | 1.55× | 1.56× | 3/3 |
| setfd/toggle | 512 | 48 | 3.031 | 3.106 | 4.938 | 7.163 | 2.31× | 1.45× | 2.16× | 1.45× | 3/3 |
| setfd/toggle | 512 | 60 | 2.546 | 2.965 | 4.724 | 7.549 | 2.55× | 1.60× | 2.48× | 1.57× | 3/3 |

TCLock spin delegation is unmeasured. KD JIT counts are returned-body observations over the measured phase. A published translation alone is not a JIT execution. Throughput is not acquisition latency. The CPU-time export helps distinguish throughput gains from processor cost.
