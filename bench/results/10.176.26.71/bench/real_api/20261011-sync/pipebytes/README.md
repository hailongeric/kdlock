# Real syscall lock comparison

Rates include the syscall, VFS/security checks, metadata search, result copying and userspace validation. Native/TCLock/KD use matched scoped substitutions; stock uses the captured kernel helper without substitution. Private objects are initialized before binding. Xattr/OFD and pipe data remain immutable; setfd changes preallocated flags, seek changes the shared file position, and UTS mixes uname reads with fixed-length name updates in a private namespace. These are API microbenchmarks, not whole-application measurements.

Accepted and drained: 144/144 sessions. Failed: 0; not run: 0.

Whole-run columns are medians across rounds, in million operations/second. Peak ratios use the best valid 300 ms window from each backend. A speedup above 1 favors KD. Raw exports retain min/median/max/spread and NO_JIT runs. An operation is one xattr/OFD syscall or one F_SETFD plus a validating F_GETFD. Pipe and seek operations each use one syscall; UTS uses one uname or name-update syscall. Entries/stride means attributes/ranges for xattr/OFD, FD stride for setfd, occupied buffers for pipebytes, capacity in pages for pipecap, file pages for seek, or write percentage for UTS. Matched UTS arms use private locks: a Linux rwsem for Native, reader/writer spinlocks for KD/TCLock. They move proc notification after unlock; stock keeps the global rwsem and original placement.

| API/query | Entries/stride/write % | Threads | Stock | Native | TCLock | KD | KD/native | KD/TC | Peak KD/native | Peak KD/TC | KD JIT runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pipebytes/query | 16 | 1 | 5.945 | 5.137 | 5.407 | 5.163 | 1.00× | 0.95× | 1.01× | 0.96× | 0/3 |
| pipebytes/query | 16 | 8 | 4.111 | 4.524 | 2.684 | 7.042 | 1.56× | 2.62× | 1.47× | 2.61× | 3/3 |
| pipebytes/query | 16 | 16 | 4.127 | 4.757 | 2.563 | 9.556 | 2.01× | 3.73× | 2.07× | 3.85× | 3/3 |
| pipebytes/query | 16 | 32 | 3.937 | 4.439 | 2.367 | 9.324 | 2.10× | 3.94× | 2.05× | 3.54× | 3/3 |
| pipebytes/query | 16 | 48 | 1.904 | 2.127 | 2.415 | 5.541 | 2.60× | 2.29× | 2.50× | 2.26× | 3/3 |
| pipebytes/query | 16 | 60 | 1.682 | 1.823 | 2.418 | 5.330 | 2.92× | 2.20× | 2.71× | 2.20× | 3/3 |
| pipebytes/query | 128 | 1 | 4.551 | 4.124 | 4.318 | 4.088 | 0.99× | 0.95× | 0.99× | 0.95× | 0/3 |
| pipebytes/query | 128 | 8 | 5.254 | 4.366 | 2.337 | 3.954 | 0.91× | 1.69× | 0.86× | 1.64× | 3/3 |
| pipebytes/query | 128 | 16 | 4.805 | 4.478 | 2.303 | 3.793 | 0.85× | 1.65× | 0.86× | 1.62× | 3/3 |
| pipebytes/query | 128 | 32 | 3.819 | 3.628 | 2.185 | 3.165 | 0.87× | 1.45× | 0.84× | 1.43× | 3/3 |
| pipebytes/query | 128 | 48 | 2.528 | 2.497 | 2.136 | 3.005 | 1.20× | 1.41× | 1.12× | 1.41× | 3/3 |
| pipebytes/query | 128 | 60 | 1.990 | 2.106 | 2.171 | 2.746 | 1.30× | 1.26× | 1.23× | 1.25× | 3/3 |

TCLock spin/rwlock delegation is unmeasured; mutex counts are exported when available. KD JIT counts are returned-body observations over the measured phase; UTS shares use writes as the denominator. A published translation alone is not a JIT execution. Throughput is not acquisition latency. The CPU-time export helps distinguish throughput gains from processor cost.
