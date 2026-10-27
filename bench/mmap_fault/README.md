# Separate mmap-only and page-fault workloads

These are supporting stage 2 controls in the [project roadmap](../../docs/ROADMAP.md).
The selectable KD/TCLock lock protects private backing state, while actual mmap
locks remain Native. The mmap-only loop never acquires that backing lock and has
only a Native arm. These results cannot close the actual-MM gain/parity gate or
replace the planned mmap1 comparison. "Private" describes driver ownership of
the backing state; the measured mappings use `MAP_SHARED`.

The single-round extension uses a separate explicit plan:
`timing.py measure --single-round-grid --workload mmap` or `--workload fault`.
It selects the standard 21 worker counts, one plain repetition and only the
supported arms below. `--exploratory-host` retains failed strict timing
qualification; source-host captures still verify the original tasks, placement,
frequency/NUMA policy and recovery snapshot. No historical result is relabelled.
Exact whole-operation accounting remains required. Only the final absence of a
positive full-cohort peak is optional in this new plan; malformed progress,
identity, callback, reader-release and teardown evidence still fail.

The current runners target `7.0.0-38-kdlock1` with the kernel MM adapter disabled.
Their Linux 7 port has not yet been executed. Follow the
[Linux 7 command and prerequisite plan](LINUX70_PLAN.md); old 6.1 receipts do not
authorize a new run. Required arguments bind the exact boot UUID, SHA256 of the
host reference, fresh host capture, and verified schema-2 kernel bundle. Fresh
`--split` correctness and timing-client preparation remain prerequisites;
`prepare --plain-only` checks the plain client without collecting latency
samples. The old 48-session plain/sampled plan remains the default.

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

Timing requires the permanent tasks from the selected Linux 7 host reference,
64 matching vCPU affinities, auxiliary CPU 63, two bound NUMA memory backends,
and all 64 configured CPU-frequency policies fixed at 2.0 GHz with turbo off.
Exploratory mode permits only literal `worker` creation/retirement on CPU 63,
records both full identities, and retains failed strict qualification even when
the endpoint task sets happen to match. Other task, affinity and start-time
changes fail. The pinned Python environment must include the
verified Python 3.14 Miasm patch. Correctness, timed-client preparation and
measurement must bind the same kernel image, configuration and runtime policy.
Capture the host immediately after measurement and retain frequency-monitor and
endpoint evidence. These runner preflights alone do not accept performance.
