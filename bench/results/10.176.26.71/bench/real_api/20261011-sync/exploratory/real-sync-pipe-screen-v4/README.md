# Real syscall lock comparison

Rates include the syscall, VFS/security checks, metadata search, result copying and userspace validation. Native/TCLock/KD use matched scoped substitutions; stock uses the captured kernel helper without substitution. The private file is populated before binding. Xattr/OFD metadata remains immutable; setfd changes only the preallocated descriptor flags. These are API microbenchmarks, not whole-application measurements.

Accepted and drained: 64/64 sessions. Failed: 0; not run: 0.

Whole-run columns are medians across rounds, in million operations/second. Peak ratios use the best valid 300 ms window from each backend. A speedup above 1 favors KD. Raw exports retain min/median/max/spread and NO_JIT runs. An operation is one xattr/OFD syscall or one F_SETFD plus a validating F_GETFD. For setfd, the count is the descriptor-number stride between workers.

| API/query | Entries/stride | Threads | Stock | Native | TCLock | KD | KD/native | KD/TC | Peak KD/native | Peak KD/TC | KD JIT runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pipebytes/query | 16 | 1 | 3.295 | 5.138 | 5.422 | 5.182 | 1.01× | 0.96× | 1.01× | 0.95× | 0/1 |
| pipebytes/query | 16 | 16 | 3.824 | 4.937 | 2.597 | 9.910 | 2.01× | 3.82× | 2.01× | 3.82× | 1/1 |
| pipebytes/query | 16 | 48 | 1.941 | 2.153 | 2.372 | 5.810 | 2.70× | 2.45× | 2.60× | 2.44× | 1/1 |
| pipebytes/query | 16 | 60 | 1.643 | 1.726 | 2.511 | 5.321 | 3.08× | 2.12× | 3.02× | 2.12× | 1/1 |
| pipebytes/query | 128 | 1 | 4.553 | 4.118 | 4.326 | 4.085 | 0.99× | 0.94× | 0.99× | 0.94× | 0/1 |
| pipebytes/query | 128 | 16 | 4.999 | 4.386 | 2.228 | 3.789 | 0.86× | 1.70× | 0.87× | 1.71× | 1/1 |
| pipebytes/query | 128 | 48 | 2.423 | 2.429 | 2.141 | 3.003 | 1.24× | 1.40× | 1.25× | 1.41× | 1/1 |
| pipebytes/query | 128 | 60 | 1.896 | 2.015 | 2.226 | 2.750 | 1.36× | 1.24× | 1.35× | 1.24× | 1/1 |
| pipecap/query | 16 | 1 | 6.704 | 5.719 | 5.960 | 5.785 | 1.01× | 0.97× | 1.01× | 0.97× | 0/1 |
| pipecap/query | 16 | 16 | 4.009 | 4.867 | 2.539 | 10.380 | 2.13× | 4.09× | 2.13× | 4.09× | 1/1 |
| pipecap/query | 16 | 48 | 1.935 | 2.195 | 2.521 | 5.268 | 2.40× | 2.09× | 2.30× | 2.08× | 1/1 |
| pipecap/query | 16 | 60 | 1.660 | 1.845 | 2.459 | 5.530 | 3.00× | 2.25× | 2.87× | 2.24× | 1/1 |
| pipecap/query | 128 | 1 | 6.721 | 5.725 | 5.972 | 5.756 | 1.01× | 0.96× | 1.01× | 0.97× | 0/1 |
| pipecap/query | 128 | 16 | 3.803 | 4.503 | 2.545 | 9.300 | 2.07× | 3.65× | 2.06× | 3.66× | 1/1 |
| pipecap/query | 128 | 48 | 1.431 | 1.541 | 2.313 | 5.186 | 3.37× | 2.24× | 2.74× | 2.03× | 1/1 |
| pipecap/query | 128 | 60 | 1.739 | 1.820 | 2.704 | 5.694 | 3.13× | 2.11× | 2.98× | 2.10× | 1/1 |

TCLock spin delegation is unmeasured. KD JIT counts are returned-body observations over the measured phase. A published translation alone is not a JIT execution. Throughput is not acquisition latency. The CPU-time export helps distinguish throughput gains from processor cost.
