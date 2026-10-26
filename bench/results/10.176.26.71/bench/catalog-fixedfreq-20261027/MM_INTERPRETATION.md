# MM results and interpretation

The three MM suites completed **126 valid, drained, archive-audited measurements**. They exercise different mechanisms from nano delegation. At 60
workers, the independent-address-space Native mmap/munmap control measures
0.439 million complete pairs/s. Each process has its own mmap lock, but the
workers share the file/mapping object, VMA counters and file-mapping metadata.
Native throughput peaks at three workers (0.851 million pairs/s), then declines;
32 to 36 workers drops from 0.618 to 0.511 million pairs/s. Shared metadata and
cross-NUMA coherence are plausible contributors, not measured attribution to
the per-address-space mmap lock.

The private-backing fault control measures `MADV_DONTNEED` followed by a checked
CPU read, including PTE reset and fault handling. At 60 workers, Native/TCLock/KD
measure 4.807/5.608/5.636 million complete cycles/s: KD is 1.173× Native and
1.005× TCLock in this single observation, while KD trails Native at the sampled
counts from 2 to 16 workers.
The selected lock protects a shared backing object; actual mmap locks remain
Native. Readers execute locally, and the preallocated pages and shared
fault/read counters are part of this workload. These rates do not demonstrate
JIT delegation or a shared-mm writer improvement.

The actual shared-mm suite uses the historical installed `6.1.159-kdmm31`
kernel, with Native/KD boot modes and unchanged MM bodies on their original
tasks. It performs untouched 4 KiB device mmap/munmap pairs, without faults.
Its kernel Build ID is `ef5179e8def44f0255adcd62585f62f118fee30f`, with audited
source commit `e6fc371b032cc0444dba34ee9025e7d939811125`; the current `a9aeb280`
controller identity does not turn that kernel into the current external module.
At one worker, Native/KD measure 0.358803/0.357066 million pairs/s. At 60,
Native measures 132,873.54 complete pairs/s and KD 6,441.88: KD is 0.048481×
Native, or 95.15% lower in this observation (Native/KD 20.63×). KD is below
Native at every measured count; the one-worker difference is only 0.48%, while
the throughput gap generally grows as workers are added. This does not establish statistical
superiority from one round. Eight optional KD peak windows at 32–60 workers
are unavailable; exact whole-run accounting and drain still pass, and only
whole-run rates are used here.

The exact installed KD source provides a hypothesis for additional contended
writer work: an ordinary writer first competes for a `0 → -1` phase reservation;
others wait before reaching the physical mutex. Reopening admission calls
`wake_up_all` on nonexclusive waiters, allowing multiple contenders to wake and
retry while only one reserves the phase. A munmap downgrade can also reopen
admission while its read-side teardown remains, so a newly admitted writer may
then wait for readers to drain. Native rwsem has different optimistic-spin,
head-writer wake and handoff rules. The aggregate timings do not measure phase
queue lengths, wakes, failed reservations or reader-drain time, so they cannot
establish which mechanism dominates, a `1/N` scaling law or starvation. The
reader-drain timeout is a progress fallback, not a mandatory 4 ms delay.
Current nano JIT batching and its 768-body locality boundary do not participate
in this historical local-writer path.

All comparisons remain separate by workload, kernel and backend. There is one
plain round per point, no repeat-variability estimate or latency distribution,
and strict host timing qualification remains failed despite a fixed 2.0 GHz policy,
exact output checks and drain.

[Independent-mm table](mm-mmap/README.md) · [Private-backing fault table](mm-fault/README.md) · [Actual shared-mm table](mm-shared/README.md)

[Exact installed-kernel source evidence](../../raw/bench/catalog-fixedfreq-20261027/mm/analysis/KDMM31_CONTENTION.md) binds the historical source hashes and identifies relevant lines. [Rate arithmetic and evidence bindings](../../raw/bench/catalog-fixedfreq-20261027/MM_INTERPRETATION-evidence.json) retain all 126 rates and archive/table/source hashes. The source analysis identifies plausible mechanisms; it supplies no profiling attribution. Final environment and recovery verification are reported separately in the [campaign report](README.md).
