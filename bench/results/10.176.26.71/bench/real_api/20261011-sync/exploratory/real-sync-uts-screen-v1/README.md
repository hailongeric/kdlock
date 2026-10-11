> **Exploratory, unequal lock scope.** This pilot uses global `uts_sem` for Native and private locks for KD/TCLock. It is excluded from the final matched comparison. All 100%-writer KD sessions have zero measured JIT bodies.

# Real syscall lock comparison

Rates include the syscall, VFS/security checks, metadata search, result copying and userspace validation. Native/TCLock/KD use matched scoped substitutions; stock uses the captured kernel helper without substitution. Private objects are initialized before binding. Xattr/OFD and pipe data remain immutable; setfd changes preallocated flags, seek changes the shared file position, and UTS mixes uname reads with fixed-length name updates in a private namespace. These are API microbenchmarks, not whole-application measurements.

Accepted and drained: 64/64 sessions. Failed: 0; not run: 0.

Whole-run columns are medians across rounds, in million operations/second. Peak ratios use the best valid 300 ms window from each backend. A speedup above 1 favors KD. Raw exports retain min/median/max/spread and NO_JIT runs. An operation is one xattr/OFD syscall or one F_SETFD plus a validating F_GETFD. Pipe and seek operations each use one syscall; UTS uses one uname or name-update syscall. Entries/stride means attributes/ranges for xattr/OFD, FD stride for setfd, occupied buffers for pipebytes, capacity in pages for pipecap, file pages for seek, or write percentage for UTS. UTS Native uses the original rwsem; KD and TCLock use reader/writer spinlocks for the bounded body. Matched UTS arms move proc notification after unlock; stock keeps the original placement.

| API/query | Entries/stride/write % | Threads | Stock | Native | TCLock | KD | KD/native | KD/TC | Peak KD/native | Peak KD/TC | KD JIT runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| utsname/domain | 20 | 1 | 3.820 | 3.474 | 3.517 | 3.518 | 1.01× | 1.00× | 1.01× | 1.00× | 0/1 |
| utsname/domain | 20 | 16 | 2.280 | 2.222 | 3.820 | 6.125 | 2.76× | 1.60× | 2.72× | 1.60× | 1/1 |
| utsname/domain | 20 | 48 | 0.584 | 0.547 | 1.691 | 3.404 | 6.22× | 2.01× | 6.16× | 2.02× | 1/1 |
| utsname/domain | 20 | 60 | 0.589 | 0.553 | 2.163 | 3.228 | 5.84× | 1.49× | 5.72× | 1.01× | 1/1 |
| utsname/domain | 100 | 1 | 2.411 | 2.247 | 2.287 | 2.284 | 1.02× | 1.00× | 1.02× | 1.00× | 0/1 |
| utsname/domain | 100 | 16 | 1.842 | 1.940 | 2.012 | 1.905 | 0.98× | 0.95× | 0.98× | 0.94× | 0/1 |
| utsname/domain | 100 | 48 | 1.141 | 1.114 | 1.142 | 1.133 | 1.02× | 0.99× | 1.03× | 1.00× | 0/1 |
| utsname/domain | 100 | 60 | 1.053 | 1.057 | 1.103 | 1.092 | 1.03× | 0.99× | 1.03× | 1.03× | 0/1 |
| utsname/host | 20 | 1 | 0.898 | 2.050 | 2.297 | 2.292 | 1.12× | 1.00× | 1.10× | 1.00× | 0/1 |
| utsname/host | 20 | 16 | 1.388 | 2.769 | 3.686 | 5.843 | 2.11× | 1.59× | 2.08× | 1.59× | 1/1 |
| utsname/host | 20 | 48 | 0.546 | 0.522 | 1.923 | 3.569 | 6.84× | 1.86× | 6.65× | 1.32× | 1/1 |
| utsname/host | 20 | 60 | 0.563 | 0.519 | 2.163 | 3.406 | 6.56× | 1.57× | 6.42× | 1.06× | 1/1 |
| utsname/host | 100 | 1 | 0.430 | 0.787 | 0.898 | 0.899 | 1.14× | 1.00× | 1.15× | 1.01× | 0/1 |
| utsname/host | 100 | 16 | 0.966 | 0.759 | 1.245 | 1.345 | 1.77× | 1.08× | 1.89× | 1.15× | 0/1 |
| utsname/host | 100 | 48 | 0.469 | 0.472 | 1.048 | 1.094 | 2.32× | 1.04× | 2.38× | 1.01× | 0/1 |
| utsname/host | 100 | 60 | 0.752 | 0.766 | 0.923 | 0.986 | 1.29× | 1.07× | 1.30× | 1.00× | 0/1 |

TCLock spin/rwlock delegation is unmeasured; mutex counts are exported when available. KD JIT counts are returned-body observations over the measured phase; UTS shares use writes as the denominator. A published translation alone is not a JIT execution. Throughput is not acquisition latency. The CPU-time export helps distinguish throughput gains from processor cost.
