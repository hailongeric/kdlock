# Real syscall lock comparison

Rates include the syscall, VFS/security checks, metadata search, result copying and userspace validation. Native/TCLock/KD use matched scoped substitutions; stock uses the captured kernel helper without substitution. Private objects are initialized before binding. Xattr/OFD and pipe data remain immutable; setfd changes preallocated flags, seek changes the shared file position, and UTS mixes uname reads with fixed-length name updates in a private namespace. These are API microbenchmarks, not whole-application measurements.

Accepted and drained: 144/144 sessions. Failed: 0; not run: 0.

Whole-run columns are medians across rounds, in million operations/second. Peak ratios use the best valid 300 ms window from each backend. A speedup above 1 favors KD. Raw exports retain min/median/max/spread and NO_JIT runs. An operation is one xattr/OFD syscall or one F_SETFD plus a validating F_GETFD. Pipe and seek operations each use one syscall; UTS uses one uname or name-update syscall. Entries/stride means attributes/ranges for xattr/OFD, FD stride for setfd, occupied buffers for pipebytes, capacity in pages for pipecap, file pages for seek, or write percentage for UTS. Matched UTS arms use private locks: a Linux rwsem for Native, reader/writer spinlocks for KD/TCLock. They move proc notification after unlock; stock keeps the global rwsem and original placement.

| API/query | Entries/stride/write % | Threads | Stock | Native | TCLock | KD | KD/native | KD/TC | Peak KD/native | Peak KD/TC | KD JIT runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| utsname/domain | 20 | 1 | 3.822 | 3.471 | 3.512 | 3.528 | 1.02× | 1.00× | 1.02× | 1.00× | 0/3 |
| utsname/domain | 20 | 8 | 2.406 | 2.283 | 3.829 | 6.409 | 2.81× | 1.67× | 2.66× | 1.67× | 0/3 |
| utsname/domain | 20 | 16 | 2.306 | 2.237 | 3.755 | 5.992 | 2.68× | 1.60× | 2.65× | 1.57× | 3/3 |
| utsname/domain | 20 | 32 | 1.778 | 1.772 | 3.350 | 5.215 | 2.94× | 1.56× | 2.89× | 1.58× | 3/3 |
| utsname/domain | 20 | 48 | 0.591 | 0.555 | 1.676 | 3.439 | 6.19× | 2.05× | 6.28× | 2.07× | 3/3 |
| utsname/domain | 20 | 60 | 0.589 | 0.553 | 2.136 | 3.290 | 5.95× | 1.54× | 5.88× | 1.00× | 3/3 |
| utsname/host | 20 | 1 | 1.425 | 2.251 | 1.915 | 2.295 | 1.02× | 1.20× | 1.00× | 1.18× | 0/3 |
| utsname/host | 20 | 8 | 1.387 | 3.434 | 3.459 | 5.965 | 1.74× | 1.72× | 1.61× | 1.70× | 0/3 |
| utsname/host | 20 | 16 | 1.412 | 3.427 | 3.474 | 5.561 | 1.62× | 1.60× | 1.65× | 1.66× | 3/3 |
| utsname/host | 20 | 32 | 1.407 | 2.664 | 3.041 | 5.312 | 1.99× | 1.75× | 1.82× | 1.74× | 3/3 |
| utsname/host | 20 | 48 | 0.546 | 0.442 | 2.597 | 3.504 | 7.92× | 1.35× | 7.82× | 1.30× | 3/3 |
| utsname/host | 20 | 60 | 0.557 | 0.457 | 2.735 | 3.288 | 7.20× | 1.20× | 7.21× | 1.12× | 3/3 |

TCLock spin/rwlock delegation is unmeasured; mutex counts are exported when available. KD JIT counts are returned-body observations over the measured phase; UTS shares use writes as the denominator. A published translation alone is not a JIT execution. Throughput is not acquisition latency. The CPU-time export helps distinguish throughput gains from processor cost.
