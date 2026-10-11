# Real syscall lock comparison

Rates include the syscall, VFS/security checks, metadata search, result copying and userspace validation. Native/TCLock/KD use matched scoped substitutions; stock uses the captured kernel helper without substitution. Private objects are initialized before binding. Xattr/OFD and pipe data remain immutable; setfd changes preallocated flags, seek changes the shared file position, and UTS mixes uname reads with fixed-length name updates in a private namespace. These are API microbenchmarks, not whole-application measurements.

Accepted and drained: 32/32 sessions. Failed: 0; not run: 0.

Whole-run columns are medians across rounds, in million operations/second. Peak ratios use the best valid 300 ms window from each backend. A speedup above 1 favors KD. Raw exports retain min/median/max/spread and NO_JIT runs. An operation is one xattr/OFD syscall or one F_SETFD plus a validating F_GETFD. Pipe and seek operations each use one syscall; UTS uses one uname or name-update syscall. Entries/stride means attributes/ranges for xattr/OFD, FD stride for setfd, occupied buffers for pipebytes, capacity in pages for pipecap, file pages for seek, or write percentage for UTS. Matched UTS arms use private locks: a Linux rwsem for Native, reader/writer spinlocks for KD/TCLock. They move proc notification after unlock; stock keeps the global rwsem and original placement.

| API/query | Entries/stride/write % | Threads | Stock | Native | TCLock | KD | KD/native | KD/TC | Peak KD/native | Peak KD/TC | KD JIT runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| utsname/domain | 20 | 1 | 3.822 | 3.471 | 3.525 | 3.528 | 1.02× | 1.00× | 1.02× | 1.00× | 0/1 |
| utsname/domain | 20 | 16 | 2.296 | 2.227 | 3.648 | 5.663 | 2.54× | 1.55× | 2.51× | 1.55× | 1/1 |
| utsname/domain | 20 | 48 | 0.589 | 0.548 | 1.707 | 3.364 | 6.14× | 1.97× | 6.11× | 1.99× | 1/1 |
| utsname/domain | 20 | 60 | 0.583 | 0.542 | 2.154 | 3.277 | 6.05× | 1.52× | 5.95× | 1.00× | 1/1 |
| utsname/host | 20 | 1 | 0.856 | 2.270 | 1.954 | 2.291 | 1.01× | 1.17× | 1.01× | 1.18× | 0/1 |
| utsname/host | 20 | 16 | 1.358 | 3.147 | 3.410 | 5.575 | 1.77× | 1.63× | 1.76× | 1.63× | 1/1 |
| utsname/host | 20 | 48 | 0.555 | 0.443 | 2.669 | 3.588 | 8.10× | 1.34× | 7.91× | 1.28× | 1/1 |
| utsname/host | 20 | 60 | 0.552 | 0.453 | 2.749 | 3.387 | 7.47× | 1.23× | 7.34× | 1.18× | 1/1 |

TCLock spin/rwlock delegation is unmeasured; mutex counts are exported when available. KD JIT counts are returned-body observations over the measured phase; UTS shares use writes as the denominator. A published translation alone is not a JIT execution. Throughput is not acquisition latency. The CPU-time export helps distinguish throughput gains from processor cost.
