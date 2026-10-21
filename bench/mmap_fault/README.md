# Separate mmap-only and page-fault workloads

`split_client.c` provides fixed-work correctness cases through the maintained
[mapping payload](../../docs/design/mmap_fault.md). Readers remain concurrent,
local readers. `timed_client.c` supplies two independent operation definitions:

| Task | Setup outside timing | One completed operation | Eligible arms |
| --- | --- | --- | --- |
| mmap-only | backing object and pages | `mmap` then `munmap`, without accessing the range | Native control |
| page-fault cycle | backing object, pages and one untouched VMA per worker | `MADV_DONTNEED` then checked CPU read | Native, KD local reader, TCLock local reader |

Every worker has a separate native mm and a fixed CPU in the 0..N-1 prefix.
Fault workers share one backing object. The mmap control measures independent-mm
creation/removal; it does not test contended same-mm mmap locking. Native mmap
locking is unchanged. There is no supported KD/TCLock mmap-lock replacement in
this payload, and those labels must not be attached to the mmap control.
TCLock work requiring task/GS state, user access, sleep or unsupported ownership
transitions inside the combined body is excluded. The existing Native fallback
correctness checks are not TCLock measurements.

The timed client uses a common two-second interval, collector CPU 63, 10 ms
progress samples, 256-operation progress publication, a 300 ms settling period
and a 300 ms full-cohort peak window. Exact totals come from joined workers and
callback/reader counters, not sampled progress. The stop clock is checked every
32 complete operations in both observation modes; overshoot is retained. Whole
throughput uses actual start through the last worker's completed teardown,
which includes the final unmap/close. Peak uses the existing conservative
bracketed window analysis and retains checkpoint quantization limits.

Plain and sampled modes use the same binary and prefaulted result storage.
Sampled mode records every 64th completed operation, with each worker's offset
staggered by its index. The nearest-rank p95 uses all retained samples within
one session. A fixed capacity is checked; overflow fails instead of truncating.
This p95 measures the entire operation defined above, including PTE reset in the
fault task, and is not acquisition-only or pure hardware-fault latency. Paired
sampled/plain throughput ratios describe observed instrumentation effects;
they do not isolate causation from scheduling variance.

`timing.py prepare` first requires both successful `--split` correctness runs
from the same payload revision. It freezes new timing sources, reuses and hashes
the previously validated provider/payload binaries, runs both basic C checks,
and validates the timed client on all eight workload/arm/count combinations.
`timing.py measure` requires that preparation to pass and drain. It runs 48
serial sessions: two counts (1/16), three rotated repetitions, and two observation
modes for mmap Native plus the three fault-reader arms. It preserves every run,
source/binary identity, completed operation, raw latency and progress sample,
retirement, failure and variance. Both phases require the original recovery VM.

Timing also requires the exact original 67-thread QEMU identity, frequencies,
NUMA placement, boot policy and dependencies. Capture the host immediately after
measurement and retain the strict endpoint comparison. No setting is changed
to make a check pass. No performance acceptance or resolution of the seven
mutex regressions follows from this separate reader workload.
