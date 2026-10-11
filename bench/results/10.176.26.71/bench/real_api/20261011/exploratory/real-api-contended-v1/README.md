# Real syscall lock comparison

Rates include the syscall, VFS/security checks, metadata search, result copying and userspace validation. Native/TCLock/KD use matched scoped substitutions; stock uses the captured kernel helper without substitution. The private file is populated before binding. Xattr/OFD metadata remains immutable; setfd changes only the preallocated descriptor flags. These are API microbenchmarks, not whole-application measurements.

Accepted and drained: 32/32 sessions. Failed: 0; not run: 0.

Whole-run columns are medians across rounds, in million operations/second. Peak ratios use the best valid 300 ms window from each backend. A speedup above 1 favors KD. Raw exports retain min/median/max/spread and NO_JIT runs. An operation is one xattr/OFD syscall or one F_SETFD plus a validating F_GETFD. For setfd, the count is the descriptor-number stride between workers.

| API/query | Entries/stride | Threads | Stock | Native | TCLock | KD | KD/native | KD/TC | Peak KD/native | Peak KD/TC | KD JIT runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ofd/tail | 16 | 16 | 5.298 | 4.908 | 5.094 | 5.166 | 1.05× | 1.01× | 1.06× | 1.01× | 1/1 |
| ofd/tail | 16 | 48 | 3.094 | 3.080 | 3.901 | 4.270 | 1.39× | 1.09× | 1.44× | 1.13× | 1/1 |
| ofd/tail | 128 | 16 | 2.277 | 2.232 | 2.612 | 2.737 | 1.23× | 1.05× | 1.22× | 1.05× | 1/1 |
| ofd/tail | 128 | 48 | 1.668 | 1.683 | 2.335 | 2.282 | 1.36× | 0.98× | 1.33× | 0.98× | 1/1 |
| xattr/tail | 16 | 16 | 2.368 | 2.904 | 3.025 | 2.220 | 0.76× | 0.73× | 0.77× | 0.74× | 0/1 |
| xattr/tail | 16 | 48 | 1.975 | 2.079 | 2.565 | 1.535 | 0.74× | 0.60× | 0.75× | 0.62× | 0/1 |
| xattr/tail | 128 | 16 | 0.783 | 0.763 | 0.748 | 0.709 | 0.93× | 0.95× | 0.93× | 0.96× | 0/1 |
| xattr/tail | 128 | 48 | 0.568 | 0.612 | 0.650 | 0.541 | 0.88× | 0.83× | 0.88× | 0.86× | 0/1 |

TCLock spin delegation is unmeasured. KD JIT counts are returned-body observations over the measured phase. A published translation alone is not a JIT execution. Throughput is not acquisition latency. The CPU-time export helps distinguish throughput gains from processor cost.
