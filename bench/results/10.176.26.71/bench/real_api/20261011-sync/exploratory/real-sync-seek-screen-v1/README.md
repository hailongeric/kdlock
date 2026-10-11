# Real syscall lock comparison

Rates include the syscall, VFS/security checks, metadata search, result copying and userspace validation. Native/TCLock/KD use matched scoped substitutions; stock uses the captured kernel helper without substitution. Private objects are initialized before binding. Xattr/OFD and pipe data remain immutable; setfd changes preallocated flags, seek changes the shared file position, and UTS mixes uname reads with fixed-length name updates in a private namespace. These are API microbenchmarks, not whole-application measurements.

Accepted and drained: 32/32 sessions. Failed: 0; not run: 0.

Whole-run columns are medians across rounds, in million operations/second. Peak ratios use the best valid 300 ms window from each backend. A speedup above 1 favors KD. Raw exports retain min/median/max/spread and NO_JIT runs. An operation is one xattr/OFD syscall or one F_SETFD plus a validating F_GETFD. Pipe and seek operations each use one syscall; UTS uses one uname or name-update syscall. Entries/stride means attributes/ranges for xattr/OFD, FD stride for setfd, occupied buffers for pipebytes, capacity in pages for pipecap, file pages for seek, or write percentage for UTS. Matched UTS arms use private locks: a Linux rwsem for Native, reader/writer spinlocks for KD/TCLock. They move proc notification after unlock; stock keeps the global rwsem and original placement.

| API/query | Entries/stride/write % | Threads | Stock | Native | TCLock | KD | KD/native | KD/TC | Peak KD/native | Peak KD/TC | KD JIT runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| seek/end | 16 | 1 | 6.406 | 5.647 | 5.831 | 5.645 | 1.00× | 0.97× | 1.00× | 0.97× | 0/1 |
| seek/end | 16 | 16 | 2.519 | 3.196 | 2.638 | 5.535 | 1.73× | 2.10× | 1.73× | 2.09× | 1/1 |
| seek/end | 16 | 48 | 1.009 | 1.133 | 2.075 | 4.147 | 3.66× | 2.00× | 3.05× | 1.84× | 1/1 |
| seek/end | 16 | 60 | 1.133 | 1.339 | 2.584 | 3.846 | 2.87× | 1.49× | 2.79× | 1.49× | 1/1 |
| seek/set | 16 | 1 | 4.231 | 5.656 | 5.825 | 5.645 | 1.00× | 0.97× | 1.00× | 0.97× | 0/1 |
| seek/set | 16 | 16 | 2.843 | 3.222 | 2.576 | 4.997 | 1.55× | 1.94× | 1.55× | 1.94× | 1/1 |
| seek/set | 16 | 48 | 0.953 | 1.104 | 2.139 | 4.110 | 3.72× | 1.92× | 3.17× | 1.83× | 1/1 |
| seek/set | 16 | 60 | 1.173 | 1.255 | 2.512 | 3.884 | 3.09× | 1.55× | 3.03× | 1.55× | 1/1 |

TCLock spin/rwlock delegation is unmeasured; mutex counts are exported when available. KD JIT counts are returned-body observations over the measured phase; UTS shares use writes as the denominator. A published translation alone is not a JIT execution. Throughput is not acquisition latency. The CPU-time export helps distinguish throughput gains from processor cost.
