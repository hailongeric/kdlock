# Why the mutex nano loses to Native

KD's most likely disadvantage in the minimal mutex nano is the work needed to
publish, execute and retire each delegated request relative to a body containing
only a load, an increment and two stores. Batching amortizes physical ownership;
it does not eliminate that per-request work. Source inspection establishes the
mechanisms, and the recorded CPU and throughput measurements support this
explanation. They do not isolate the cycle cost of each mechanism.

This analysis uses the [fresh mutex campaign](README.md), source
`444f68577ed56a10aa8b69da82d97de8f2081497`. All points remain exploratory, with
one two-second observation per backend/count/profile and failed strict host
timing qualification. There are no new timing samples here. The separately
identified post-work control below uses an earlier source and is not pooled
with the fresh campaign.

## Measured gap

Rates include outside-lock work. `RETURNED_JIT` means generated bodies actually
returned successfully; the percentage is returned writes divided by completed
writes. It establishes execution coverage, not a speedup.

| Profile | Workers | Native Mops/s | KD Mops/s | KD versus Native | KD returned writes |
| --- | ---: | ---: | ---: | ---: | ---: |
| One cacheline, post4 | 8 | 11.177 | 6.233 | −44.2% | 97.63% |
| One cacheline, post4 | 16 | 10.472 | 6.356 | −39.3% | 95.24% |
| One cacheline, post4 | 32 | 8.256 | 5.889 | −28.7% | 98.90% |
| One cacheline, post4 | 36 | 7.367 | 4.853 | −34.1% | 98.14% |
| One cacheline, post4 | 60 | 5.704 | 5.011 | −12.1% | 97.33% |
| 16 cachelines, post64 | 8 | 6.494 | 4.897 | −24.6% | 96.21% |
| 16 cachelines, post64 | 16 | 5.938 | 5.264 | −11.4% | 98.86% |
| 16 cachelines, post64 | 32 | 4.334 | 4.606 | +6.3% | 99.05% |
| 16 cachelines, post64 | 36 | 4.413 | 3.948 | −10.5% | 99.07% |
| 16 cachelines, post64 | 60 | 2.651 | 4.045 | +52.6% | 98.21% |

The contended losses therefore cannot be explained by KD simply failing to
execute JIT bodies. The one-worker points have zero returned bodies and are
local fast-path comparisons; their KD gains do not demonstrate delegation.

## Per-request coordination outweighs the tiny body

The successful uncontended KD path returns before task admission, queueing or
frame setup. Under contention, the common delegated path has more work:

| Stage | Work retained for a delegated request | Source at the measured revision |
| --- | --- | --- |
| Admission | Contention/source/process checks, cached task identity/reference and entry lookup | [`mutex_calls.inc`](../../../../../kernel_module/lock/mutex_calls.inc), `kd_mutex_contended_acquire`; [`kd_mutex_tasks.c`](../../../../../kernel_module/kd_mutex_tasks.c), `kd_mutex_task_get/put` |
| Publication | Pinning, preallocated slot reservation, IP/SP/BP capture, shadow-stack entry, shared tail exchange and predecessor-link publication | [`kd_mutex.c`](../../../../../kernel_module/kd_mutex.c), `_kd_mutex_lock_abi`; [`waiter.inc`](../../../../../kernel_module/mutex/waiter.inc); [`queue.inc`](../../../../../kernel_module/mutex/queue.inc) |
| Execution | Bind an exact ownership frame, check source/image/ABI readiness and enter the generated body | [`frame_lifecycle.inc`](../../../../../kernel_module/execution/frame_lifecycle.inc), `kd_exec_frame_push_mutex_batch`; [`wrapper_entry.inc`](../../../../../kernel_module/execution/wrapper_entry.inc), `kd_exe_mutex_batch_prepare` |
| Completion | Check terminal unlock identity/state, retire the frame and queue links, publish completion, release the origin's node/task reference and resume after unlock | [`combiner.inc`](../../../../../kernel_module/mutex/combiner.inc); [`clobber.inc`](../../../../../kernel_module/mutex/clobber.inc) |

The [captured generated body](../../raw/bench/nano-mutex-20261026/analysis/minimal-t16-jit.S)
contains four useful data instructions. Its completion path additionally checks
metadata, the lock, unlock target and continuation state. The source also shows
wrapper/frame work outside that listing. Request packets, metadata and
completion notifications are still shared between producer and executor even
when the protected payload stays resident on the executor. A single cacheline offers
little payload movement to amortize against those costs.

These are not claims of allocation, translation or full register snapshots on
every operation. Nodes and shadow stacks are preallocated, task identities are
cached, and translation stops before warmup/timing. ABI2 initially captures
IP/SP/BP; the compiler supplies the clobber contract. The tiny fixed-address body
does not dynamically bounds-check each payload access. Source residency is held
once per combiner batch, and a successful COMPLETE body does not require the
extra unlock-ACK round trip used by a borrowed native continuation. Exact frame,
queue and lifetime retirement remain required.

## CPU use and Native's acquisition behavior

The [worker comparison](worker-comparison.csv) derives CPU cost from the saved
per-worker records. CPU cost is the sum of worker CPU time divided by completed
operations, including on-CPU spinning/polling and ioctl/post-work but excluding
time descheduled. It is not lock latency or an isolated JIT cost.

| Profile | Workers | Native aggregate worker CPU µs/op | KD aggregate worker CPU µs/op | Native / KD work-distribution fairness |
| --- | ---: | ---: | ---: | ---: |
| One cacheline, post4 | 8 | 0.710 | 1.282 | 0.996 / 1.000 |
| One cacheline, post4 | 16 | 1.509 | 2.501 | 0.739 / 0.998 |
| One cacheline, post4 | 32 | 3.756 | 5.403 | 0.823 / 1.000 |
| One cacheline, post4 | 60 | 9.839 | 11.885 | 0.911 / 0.996 |
| 16 cachelines, post64 | 32 | 7.110 | 6.907 | 0.427 / 1.000 |
| 16 cachelines, post64 | 36 | 7.838 | 9.066 | 0.338 / 0.993 |
| 16 cachelines, post64 | 60 | 20.824 | 14.738 | 0.797 / 0.996 |

Fairness is Jain's index over completed operations per worker; 1 means equal
work distribution. It is not a latency guarantee. At 16 workers in the minimal
case, Native and KD consumed approximately 15.80 and 15.90 scheduled worker cores
respectively, yet Native completed 65% more operations. Most workers remained
busy with either implementation. Native's advantage here is not evidence that
it puts most contenders to sleep.

The captured Native mutex uses owner-word CAS, optimistic owner spinning and an
OSQ queue before entering its blocking slow path. Fast/optimistic acquisition
and conditional handoff allow a different service order from KD's delegation
queue. Unequal service can permit repeated acquisition while data remains
nearby. The worker records are consistent with that explanation: at 16 workers
in the minimal case, Native's busiest worker completed 4.43 times the least busy
worker's count; KD's ratio was 1.18. At 32 workers in the locality case, a busiest
worker accounted for a median 24.8% of Native completions in settled approximately
100-ms windows, versus 3.2% for KD.

There is no owner-sequence trace proving consecutive reacquisition. Moreover,
Native is quite evenly distributed at eight workers in the minimal case and
still wins by a large margin. Fairness cannot explain the entire gap. KD's
minimal throughput also stays near 6 Mops/s from 8 through 32 workers while its
aggregate CPU/op increases: adding polling producers does not increase useful
service proportionally.

## NUMA and outside-lock work change the crossover

Counts up to 32 use one node. Increasing to 36 introduces four remote callers.
KD throughput drops 17.6% for the minimal body and 14.3% for the locality body;
Native changes by −10.8% and +1.8%, respectively. The KD source has a bounded
locality scan and a 256-body boundary: eight or more deferred requests receive
handoff, while a smaller deferred prefix is serviced before a FIFO remainder.
For a combiner on the first node, the four other-node callers cannot supply
eight simultaneous deferred requests; the larger 60-worker cohort may. A
combiner on the second node instead sees 32 other-node callers. The threshold
counts actual deferred requests, not configured workers. Request/notification
traffic across nodes and this policy are plausible contributors to the dip.
No executor, batch-length or handoff trace establishes when this branch ran or
its cost. Requester-node completion shares in the CSV do not identify the
executor node or physical owner.

The fresh profiles change both body size and post-work, so their difference is
not a controlled payload-size experiment. A separate earlier
[selection study](../nano-pair-20261026/README.md), source
`6ff80fadf368f9e261be24c2aa7800013a3d9f6d`, holds the 16-cacheline body and source
fixed while changing post-work from 4 to 64 rounds. At 60 workers:

| Backend | Post4 Mops/s | Post64 Mops/s | Change |
| --- | ---: | ---: | ---: |
| Native | 4.394 | 2.806 | −36.1% |
| KD | 4.134 | 4.025 | −2.6% |

KD's relative crossover arises primarily because Native slows more under that
outside-work setting. KD does not become faster in absolute throughput. Arrival
spacing, reacquisition opportunity and resident-data ownership are plausible
mechanisms, but this factor experiment does not separate them. The fresh
60-worker locality win likewise does not override its 8-, 16- and 36-worker
losses or the minimal body's losses at every contended count.

This also explains why deleting application logic from favorable API workloads
does not necessarily preserve their speedups. Those APIs include one syscall
and surrounding application/kernel work per operation. The nano uses one bulk
ioctl per worker, changes request spacing and removes much of the protected
work. A favorable nano needs enough avoidable ownership/data movement to pay for
delegation; the fewest possible body instructions are not sufficient.

## Evidence limits and optimization direction

The Native comparator is the captured `6.1.159-kdclobber2` recovery kernel, not
an unmodified upstream build. Its internal legacy hooks also save RBX/R12–R15.
KD's extra saves visible at the caller alone therefore cannot establish a net
whole-operation register-save disadvantage. KD's measured provider additionally
records CPU-local body/completion observations. Instrumentation and call-shell
differences remain part of this comparison; their individual costs were not
measured.

Across the 24 fresh Native/KD points examined here, all workers entered within
8.9 ms of the start; whole-run end overrun was at most 10.8 ms. Every examined
Native/KD worker made positive published progress in every examined settled
approximately 100-ms window. Startup skew or absent workers does not explain
these large differences. Shorter windows have 256-operation publication
granularity; a zero sampled delta does not prove sleeping or starvation.

The useful next optimization target is per-request admission/publication,
frame/dispatch and completion cost. A focused profile should distinguish those
costs from payload work and measure batch lengths, physical-owner transitions
and cache transfers before changing the algorithm. Exact owners, source leases,
unlock routing, admission and retirement must remain intact. The current data
does not justify attributing a numerical fraction of the loss to any one stage,
changing the NUMA thresholds, or weakening those checks.

## Reproduction and provenance

The [offline calculator](../../raw/bench/nano-mutex-20261026/analysis/calculate_worker_metrics.py)
reads immutable receipts and checks raw measurements against their aggregate
records. Its [JSON output](../../raw/bench/nano-mutex-20261026/analysis/worker-metrics.json)
records formulas, 56 input hashes, full-precision metrics and sampling rules.
The CSV contains 24 fresh Native/KD rows; the 24 earlier factor rows remain
separate in the JSON. Settled windows start after the full cohort plus 300 ms;
approximately 100-ms windows overlap and are not independent repetitions.

Existing guest Native source/build inputs were fetched read-only for offline
inspection on `380G10`; no build, test, module change or new timing was run.
The captured `mutex.c` SHA-256 is
`9398306fa9f63327ca4fcdacc70acb6b83e29591f81e79f3e52f4e3193131368`;
`osq_lock.c` is
`daab1575a9464194d5ad399a4168bd20718e81db806a2f9b896da7f00367a7dc`.
Both match [`linux-source.json`](../../../../../kernel_module/mutex/linux-source.json).
The [capture audit](../../raw/bench/nano-mutex-20261026/analysis/native-source-audit.json)
also records the archive hash. Native source and existing-object disassembly
reside alongside it; the object inspection is not a new live kernel byte audit.
