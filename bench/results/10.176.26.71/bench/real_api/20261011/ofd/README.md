# Real syscall lock comparison

Rates include the syscall, VFS/security checks, metadata search, result copying and userspace validation. Native/TCLock/KD use matched scoped substitutions; stock uses the captured kernel helper without substitution. The private file is populated before binding. Xattr/OFD metadata remains immutable; setfd changes only the preallocated descriptor flags. These are API microbenchmarks, not whole-application measurements.

Accepted and drained: 144/144 sessions. Failed: 0; not run: 0.

Whole-run columns are medians across rounds, in million operations/second. Peak ratios use the best valid 300 ms window from each backend. A speedup above 1 favors KD. Raw exports retain min/median/max/spread and NO_JIT runs. An operation is one xattr/OFD syscall or one F_SETFD plus a validating F_GETFD. For setfd, the count is the descriptor-number stride between workers.

| API/query | Entries/stride | Threads | Stock | Native | TCLock | KD | KD/native | KD/TC | Peak KD/native | Peak KD/TC | KD JIT runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ofd/tail | 16 | 1 | 3.998 | 3.714 | 3.721 | 3.697 | 1.00× | 0.99× | 0.99× | 0.99× | 0/3 |
| ofd/tail | 16 | 8 | 5.036 | 4.531 | 3.867 | 4.874 | 1.08× | 1.26× | 0.96× | 1.32× | 2/3 |
| ofd/tail | 16 | 16 | 4.522 | 4.806 | 4.672 | 5.154 | 1.07× | 1.10× | 1.07× | 1.02× | 3/3 |
| ofd/tail | 16 | 32 | 4.460 | 4.549 | 4.002 | 5.019 | 1.10× | 1.25× | 1.12× | 1.11× | 3/3 |
| ofd/tail | 16 | 48 | 3.234 | 3.084 | 4.104 | 4.333 | 1.41× | 1.06× | 1.42× | 1.11× | 3/3 |
| ofd/tail | 16 | 60 | 2.733 | 2.815 | 3.988 | 4.345 | 1.54× | 1.09× | 1.56× | 1.04× | 3/3 |
| ofd/tail | 128 | 1 | 2.224 | 2.229 | 2.145 | 2.185 | 0.98× | 1.02× | 0.97× | 1.00× | 0/3 |
| ofd/tail | 128 | 8 | 2.636 | 2.905 | 2.628 | 1.818 | 0.63× | 0.69× | 0.97× | 1.06× | 3/3 |
| ofd/tail | 128 | 16 | 2.059 | 2.373 | 2.609 | 2.618 | 1.10× | 1.00× | 1.08× | 1.02× | 3/3 |
| ofd/tail | 128 | 32 | 1.848 | 1.893 | 2.217 | 2.204 | 1.16× | 0.99× | 1.08× | 1.02× | 3/3 |
| ofd/tail | 128 | 48 | 1.756 | 1.727 | 2.276 | 2.363 | 1.37× | 1.04× | 1.24× | 1.07× | 3/3 |
| ofd/tail | 128 | 60 | 1.795 | 1.588 | 2.186 | 2.172 | 1.37× | 0.99× | 1.22× | 1.03× | 3/3 |

TCLock spin delegation is unmeasured. KD JIT counts are returned-body observations over the measured phase. A published translation alone is not a JIT execution. Throughput is not acquisition latency. The CPU-time export helps distinguish throughput gains from processor cost.
