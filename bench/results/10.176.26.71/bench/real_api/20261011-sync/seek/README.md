# Real syscall lock comparison

Rates include the syscall, VFS/security checks, metadata search, result copying and userspace validation. Native/TCLock/KD use matched scoped substitutions; stock uses the captured kernel helper without substitution. Private objects are initialized before binding. Xattr/OFD and pipe data remain immutable; setfd changes preallocated flags, seek changes the shared file position, and UTS mixes uname reads with fixed-length name updates in a private namespace. These are API microbenchmarks, not whole-application measurements.

Accepted and drained: 144/144 sessions. Failed: 0; not run: 0.

Whole-run columns are medians across rounds, in million operations/second. Peak ratios use the best valid 300 ms window from each backend. A speedup above 1 favors KD. Raw exports retain min/median/max/spread and NO_JIT runs. An operation is one xattr/OFD syscall or one F_SETFD plus a validating F_GETFD. Pipe and seek operations each use one syscall; UTS uses one uname or name-update syscall. Entries/stride means attributes/ranges for xattr/OFD, FD stride for setfd, occupied buffers for pipebytes, capacity in pages for pipecap, file pages for seek, or write percentage for UTS. Matched UTS arms use private locks: a Linux rwsem for Native, reader/writer spinlocks for KD/TCLock. They move proc notification after unlock; stock keeps the global rwsem and original placement.

| API/query | Entries/stride/write % | Threads | Stock | Native | TCLock | KD | KD/native | KD/TC | Peak KD/native | Peak KD/TC | KD JIT runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| seek/end | 16 | 1 | 6.430 | 5.647 | 5.821 | 5.643 | 1.00× | 0.97× | 1.00× | 0.97× | 0/3 |
| seek/end | 16 | 8 | 2.899 | 3.265 | 2.655 | 4.965 | 1.52× | 1.87× | 1.55× | 1.89× | 3/3 |
| seek/end | 16 | 16 | 2.602 | 3.064 | 2.509 | 5.151 | 1.68× | 2.05× | 1.69× | 2.12× | 3/3 |
| seek/end | 16 | 32 | 2.429 | 2.798 | 2.552 | 4.821 | 1.72× | 1.89× | 1.70× | 1.89× | 3/3 |
| seek/end | 16 | 48 | 1.269 | 1.485 | 2.452 | 4.138 | 2.79× | 1.69× | 2.62× | 1.64× | 3/3 |
| seek/end | 16 | 60 | 1.172 | 1.315 | 2.443 | 3.839 | 2.92× | 1.57× | 2.86× | 1.54× | 3/3 |
| seek/set | 16 | 1 | 6.419 | 5.625 | 5.801 | 5.634 | 1.00× | 0.97× | 1.00× | 0.97× | 0/3 |
| seek/set | 16 | 8 | 2.705 | 2.835 | 2.596 | 4.718 | 1.66× | 1.82× | 1.72× | 1.93× | 3/3 |
| seek/set | 16 | 16 | 2.786 | 3.253 | 2.604 | 5.421 | 1.67× | 2.08× | 1.67× | 2.05× | 3/3 |
| seek/set | 16 | 32 | 2.404 | 2.805 | 2.568 | 4.835 | 1.72× | 1.88× | 1.74× | 1.90× | 3/3 |
| seek/set | 16 | 48 | 1.271 | 1.533 | 2.524 | 4.132 | 2.70× | 1.64× | 2.59× | 1.63× | 3/3 |
| seek/set | 16 | 60 | 1.182 | 1.385 | 2.623 | 3.839 | 2.77× | 1.46× | 2.70× | 1.43× | 3/3 |

TCLock spin/rwlock delegation is unmeasured; mutex counts are exported when available. KD JIT counts are returned-body observations over the measured phase; UTS shares use writes as the denominator. A published translation alone is not a JIT execution. Throughput is not acquisition latency. The CPU-time export helps distinguish throughput gains from processor cost.
