# Real syscall lock comparison

Rates include the syscall, VFS/security checks, metadata search, result copying and userspace validation. Native/TCLock/KD use matched scoped substitutions; stock uses the captured kernel helper without substitution. Private objects are initialized before binding. Xattr/OFD and pipe data remain immutable; setfd changes preallocated flags, seek changes the shared file position, and UTS mixes uname reads with fixed-length name updates in a private namespace. These are API microbenchmarks, not whole-application measurements.

Accepted and drained: 8/8 sessions. Failed: 0; not run: 0.

Whole-run columns are medians across rounds, in million operations/second. Peak ratios use the best valid 300 ms window from each backend. A speedup above 1 favors KD. Raw exports retain min/median/max/spread and NO_JIT runs. An operation is one xattr/OFD syscall or one F_SETFD plus a validating F_GETFD. Pipe and seek operations each use one syscall; UTS uses one uname or name-update syscall. Entries/stride means attributes/ranges for xattr/OFD, FD stride for setfd, occupied buffers for pipebytes, capacity in pages for pipecap, file pages for seek, or write percentage for UTS. Matched UTS arms use private locks: a Linux rwsem for Native, reader/writer spinlocks for KD/TCLock. They move proc notification after unlock; stock keeps the global rwsem and original placement.

| API/query | Entries/stride/write % | Threads | Stock | Native | TCLock | KD | KD/native | KD/TC | Peak KD/native | Peak KD/TC | KD JIT runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| setfd/toggle | 16 | 1 | 2.377 | 3.287 | 3.257 | 3.268 | 0.99× | 1.00× | 0.99× | 1.00× | 0/1 |
| setfd/toggle | 16 | 16 | 3.967 | 5.233 | 5.387 | 5.436 | 1.04× | 1.01× | 1.03× | 0.98× | 1/1 |

TCLock spin/rwlock delegation is unmeasured; mutex counts are exported when available. KD JIT counts are returned-body observations over the measured phase; UTS shares use writes as the denominator. A published translation alone is not a JIT execution. Throughput is not acquisition latency. The CPU-time export helps distinguish throughput gains from processor cost.
