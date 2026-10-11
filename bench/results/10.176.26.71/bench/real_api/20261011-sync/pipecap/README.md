# Real syscall lock comparison

Rates include the syscall, VFS/security checks, metadata search, result copying and userspace validation. Native/TCLock/KD use matched scoped substitutions; stock uses the captured kernel helper without substitution. Private objects are initialized before binding. Xattr/OFD and pipe data remain immutable; setfd changes preallocated flags, seek changes the shared file position, and UTS mixes uname reads with fixed-length name updates in a private namespace. These are API microbenchmarks, not whole-application measurements.

Accepted and drained: 72/72 sessions. Failed: 0; not run: 0.

Whole-run columns are medians across rounds, in million operations/second. Peak ratios use the best valid 300 ms window from each backend. A speedup above 1 favors KD. Raw exports retain min/median/max/spread and NO_JIT runs. An operation is one xattr/OFD syscall or one F_SETFD plus a validating F_GETFD. Pipe and seek operations each use one syscall; UTS uses one uname or name-update syscall. Entries/stride means attributes/ranges for xattr/OFD, FD stride for setfd, occupied buffers for pipebytes, capacity in pages for pipecap, file pages for seek, or write percentage for UTS. Matched UTS arms use private locks: a Linux rwsem for Native, reader/writer spinlocks for KD/TCLock. They move proc notification after unlock; stock keeps the global rwsem and original placement.

| API/query | Entries/stride/write % | Threads | Stock | Native | TCLock | KD | KD/native | KD/TC | Peak KD/native | Peak KD/TC | KD JIT runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pipecap/query | 16 | 1 | 6.704 | 5.745 | 5.975 | 5.786 | 1.01× | 0.97× | 1.01× | 0.97× | 0/3 |
| pipecap/query | 16 | 8 | 4.757 | 4.213 | 2.814 | 6.778 | 1.61× | 2.41× | 1.54× | 2.40× | 3/3 |
| pipecap/query | 16 | 16 | 3.786 | 4.549 | 2.756 | 10.338 | 2.27× | 3.75× | 2.22× | 3.83× | 3/3 |
| pipecap/query | 16 | 32 | 3.860 | 4.489 | 2.600 | 9.542 | 2.13× | 3.67× | 2.06× | 3.57× | 3/3 |
| pipecap/query | 16 | 48 | 1.904 | 2.136 | 2.666 | 5.731 | 2.68× | 2.15× | 2.53× | 2.06× | 3/3 |
| pipecap/query | 16 | 60 | 1.753 | 1.914 | 2.721 | 5.639 | 2.95× | 2.07× | 2.81× | 2.02× | 3/3 |

TCLock spin/rwlock delegation is unmeasured; mutex counts are exported when available. KD JIT counts are returned-body observations over the measured phase; UTS shares use writes as the denominator. A published translation alone is not a JIT execution. Throughput is not acquisition latency. The CPU-time export helps distinguish throughput gains from processor cost.
