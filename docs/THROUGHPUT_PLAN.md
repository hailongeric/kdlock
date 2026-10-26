# Native/KD throughput campaign plan

The [project roadmap](ROADMAP.md) owns the three-stage goal and completion gates:
micro/nano gains, scoped MM improvement or parity, then relevant kernel lock
replacement and application evaluation. This document owns concrete throughput
campaigns and their retained status. Their outcomes test the project's hypotheses;
a completed campaign is not automatically a completed development stage.

Current measurement objective: quantify KD against Native across documented lock
workloads and actual mmap/page-fault use. Report losses, local execution, class
gaps and variance with gains. **This phase measures throughput only**; new tail-latency
collection and sampled workload variants are deferred. Preserve historical
latency evidence. Environment diagnosis is a separate activity.

The explicitly requested October 26 one-round exploratory screen has completed:
[51 runnable lock/API configurations](../bench/results/10.176.26.71/bench/catalog-single-20261026/README.md)
and [three implemented mmap/fault workloads](../bench/results/10.176.26.71/bench/catalog-mmap-single-20261026/README.md).
It retains 3,292 timed observations and 47 drained xattr preparation failures,
with strict timing qualification failed and no repeat variability estimate.
The private-backing fault experiment remains separate from the generic
actual-mmap-backend page-fault throughput driver proposed below.

No campaign below is authorized to run by this roadmap. The separately authorized
[`plain-v1` attempt](../bench/results/10.176.26.71/bench/mmap-plain-v1-20261025/README.md)
stopped at 68 QEMU tasks versus 67: one full capture, no boot or payload load,
all twelve measurements and six unscored checks unrun. The earlier
[73-versus-67 admission stop](../bench/results/10.176.26.71/bench/mmap-kdmm31-paired-20261025/README.md)
remains separate preserved evidence. The [60-second diagnostic](../bench/mmap_lock/DIAGNOSTIC.md)
first stopped during initial observation; its guide tracks the separately
reviewed timing correction and execution status. No quiet observation, weaker
gate or repeated provider diagnostic can qualify the campaign.

## Workload and interface boundaries

The next application-matching target is upstream `mmap1_threads`: 128 MiB
anonymous private read/write mappings, immediately unmapped without access, with
all pthreads sharing one actual mmap lock. `mmap1_processes` is a separate
independent-mm control. Both need a separately prepared actual-backend comparison;
neither is implemented by relabelling the existing 4 KiB device mapping or the
private-backing fault loop. The [stage 2 contract](ROADMAP.md#stage-2-prove-scoped-mm-improvement-or-parity)
defines the work, semantic checks and gain/parity criterion. Historical plans
below retain their workload identities and do not become mmap1 plans.

| Scenario | Existing implementation/evidence | Comparison contract and next gap |
| --- | --- | --- |
| Mutex c01/c08, exclusive-update RCUHT | [Mutex runner](../bench/tclock_compare/README.md), `run_mutex.py`; public and OUTER are separate compiled shells | Same preallocated work and post-work, Native versus current public KD. Preserve entry-only/returned-body/NO_JIT classes. OUTER is a separate regression control. |
| Pipe byte count/capacity, seek and other documented APIs | [Workload catalog](BENCHMARK_WORKLOADS.md#real-world-api-critical-sections), [public mutex collector](../bench/mutex_api_compare/run.py) | Same objects, query parameters and syscall shell; copy-to-user and post-work remain in their native positions. Freeze a bounded point list; the historical replay is not a new Native/KD plan. |
| Rwlock c01/c08/RCUHT and resident lists | [Reader/writer runner](../bench/rwlock_compare/README.md), `--lock-kind rwlock` | Local concurrent readers, bounded non-sleeping writers; keep 1% and 20% writes separate. Preserve strict delegation failures and exact drain. |
| Rwsem c01/c08/RCUHT and resident lists | Same runner, `--lock-kind rwsem`; [unified API](../include/kd_rwsem.h) | Ordinary local readers/writers and explicit OUTER writer delegation are separate controls. Internal local mutex calls cannot replace reader admission. Compare the selected interface consistently. |
| Actual shared-mm mmap/munmap | [Prepared mmap workload](../bench/mmap_lock/README.md), unchanged `kdmm31`, Native/KD boot modes | Same pthread cohort, exact mm/lock, CPUs and untouched mappings. No delegated MM body. The new `plain-scaling-v1` runner/report is mock-tested; all 126 sessions are unrun. The older `plain-v1` admission failed. |
| Actual kernel page faults | [Fault correctness cases](../tests/kernel/mmap_lock/fault_cases.c), [completed-fault client](../tests/kernel/mmap_lock/page_fault_completed/client.c) | Actual native fault bodies remain on the faulting task behind the selected mmap backend. Correctness drivers exist; a generic throughput driver has not been established. Prepare that driver separately before any timed fault campaign. |
| Module-owned backing-page faults | [Private mapping runner](../bench/mmap_fault/README.md), `timing.py` / `timed_client.c` | Real CPU faults through a private backing lock, with separate native mms and native mmap locks unchanged. Preserve this evidence separately; it cannot stand in for actual mmap-backend fault throughput. |

TCLock is optional only for supported equivalent interfaces and matched work.
Its original rwsem port exports ordinary registered-worker pairs, without
equivalent cancellation, downgrade or actual-mmap APIs. There is no TCLock arm
in the current local harness for actual mmap/fault comparisons. TCLock's paper
instead used a modified kernel; a future comparable full integration belongs to
stage 3 and requires its own evidence. Do not substitute the local port's rwlock
for a sleeping rwsem. Explicit delegation is not evidence of generic MM support.

## Prospective 21-count mmap comparison

The implemented `plain-scaling-v1` plan uses exactly
`1,2,3,4,5,6,7,8,12,16,20,24,28,32,36,40,44,48,52,56,60` writers, Native/KD and
three paired repetitions: **126 measured sessions per workload**, with no
64-worker point. Only the existing shared-mm writer workload is implemented.
Its [41 focused mocked tests](../bench/results/10.176.26.71/tests/mmap-scaling-plan-20261026/README.md)
passed; independent source/receipt review found no material matrix defect. No
measurement in that three-repeat matrix has run; its live attempt stopped during
KD validation. The completed October 26 single-round screen is a separate plan.
The original `paired-v1` (24 sessions, also the
missing-plan default) and stopped `plain-v1` (12 sessions) remain separate.

Reuse the same `kdmm31` image/configuration, build-3 payload/clients and scoped
API evidence. Plain runs retain exact totals, joins, callback oracles, mm/lock
identity, retirement and progress accounting, with zero latency samples.
Workers use CPUs 0..N−1; collector 63 is separate. Counts above 32 span both guest
NUMA nodes. Collector-first-touch buffers remain unchanged; this is not an
isolated NUMA experiment or a reader/delegation/TCLock comparison.

Order is initial Native validation; KD repeat 0; Native repeats 0/1; KD repeats
1/2; Native repeat 2; recovery. Adjacent repetitions share boots. Each backend
runs one observed 16-worker fixed proof and all 21 unobserved timed controls.
The current window-policy maxima are **44 unscored checks, 170 payload cycles,
385 full host captures, 126 observers (at most 12,222 scans) and six boots**,
with no retries or dedicated warmups. Fixed writer-chain
proofs are not extended to every worker count by those timed controls.

The [runner guide](../bench/mmap_lock/README.md#plain-throughput-plan) gives
commands, placement, replay/log accounting and the pure `describe` interface.
The older `describe` output estimates legacy transport: 259 captures,
44 min 36.8 s and 2 GiB per retention filesystem. For `mmap-window-v2` with
`qemu-workers-v1`, the additional endpoints, guards and 168 required 90-second
post-setup waits revise the estimate to **5 h 5 min 0.8 s** and **3 GiB per
retention filesystem**. The runner guide gives the arithmetic and assumptions;
neither estimate is measured cost, a completion guarantee or permission.
Recheck actual space, log sizes and frozen source identity before execution.
Any required synchronization must happen only while idle, after review.

The original 67-QEMU-task policy remains unchanged for historical transport.
The explicit worker policy permits verified auxiliary lifetimes and activity;
the completed [small pair](../bench/results/10.176.26.71/bench/mmap-worker-screen-20261026/README.md)
qualified under that policy and is not repeated as part of the sweep.
Stop on the first failed
identity, correctness, admission, endpoint or drain check; retain every failure.
No later quiet observation can replace a failed admission or rejected endpoint.
Return to the preserved recovery entry only after proven drain; uncertainty
requires review. No automatic campaign follows a diagnostic.

The [October 26 sweep](../bench/results/10.176.26.71/bench/mmap-worker-scaling-20261026/README.md)
used this revised budget and stopped at the KD fixed-writer observation after
Native validation passed. It consumed three boots, four full captures and
23 payload cycles, with zero measured cases. Recovery is restored. Review
whether the sleeping-writer observation belongs in throughput eligibility or
in a separate integration claim before proposing another bounded cycle.
Keep the failed observation and completed controls; do not repeat the small
screen to substitute for this missing proof.

The [explicit eligibility policy](../bench/mmap_lock/THROUGHPUT_POLICY.md)
implements the reviewed separation of functional completion from an inconclusive
sleeping-writer observation, while retaining strict mode and verification of
every positive proof. Its 99 focused offline tests and saved Native-control
replay passed. The separately reviewed continuation would reuse those controls:
one new KD fixed check, 21 KD controls and 126 measurements, bounded by 148
payload cycles, five boots and 384 full captures. Estimated time is 4 h 28 min
19.7 s, with 3 GiB reserved per retention filesystem under the documented
assumptions. The separately authorized
[continuation](../bench/results/10.176.26.71/bench/mmap-functional-scaling-20261026/README.md)
ran at `30af034`: KD completed its functional check with an inconclusive writer
observation and passed 15 controls, then failed the 40-worker positive
full-cohort peak-window check. It consumed 17 payload cycles, two boots and
three full captures, with zero measured cases, and restored recovery. That
failed result retains its verdict. A separately requested
[five-case aggregate run](../bench/results/10.176.26.71/bench/mmap-aggregate-tail-20261026/README.md)
subsequently completed the missing 44/48/52/56/60-worker KD counts, with peaks
unavailable and aggregate/drain checks passed. It used five payload cases, two
boots and three captures, then verified recovery before its deadline. These
single controls do not complete the 126-session paired matrix. No further live
cycle is authorized by this roadmap.

## Expansion after the first qualified baseline

The prospective mmap matrix is separate from later workload expansion. Optional
screens must not become prerequisites: public-mutex c08, rwlock c08/20% writes
and rwsem c08/20% writes at 16 workers would each take six Native/KD sessions
(three pairs), 18 total. The write mix is per worker; mutex c08's retained
`LEGACY_ENTRY_OBSERVATION` is not returned-body proof. Use the
[documented catalog](BENCHMARK_WORKLOADS.md), keeping each interface's source and
execution class separate. For each additional workload, specify the same 21-count grid separately and
retain the 32/36-worker NUMA boundary and interface-specific limitations. Set CPU lists explicitly; the normal collector is CPU 63.

Retain all seven unresolved mutex regression points: c08 at **3/4/5** workers,
pipebytes at **3/5**, pipecap at **5**, and RCUHT at **2**. A fresh Native/public-KD
three-pair comparison of those points is 42 sessions; a contemporaneous OUTER
control would add 21 separately labelled sessions. These counts describe later
scope, not a launched collector or a claim that the original public/OUTER
regressions are already resolved.

Actual page-fault throughput needs a small userspace driver with explicit fault
classes, setup/reset boundaries, shared-versus-independent mm identity and data
oracles. Start with one reproducible anonymous minor-fault case and an explicit
residency/reset contract; resident-file and independent-mm controls follow
separately. Keep read/write faults distinct. Pin workers and memory placement, fix
page size/THP and cache-state policy, and retain observed minor/major fault counts.
Report completed page touches per timed interval; call them faults per second
only when fault accounting supports that denominator. Do not relabel a
`MADV_DONTNEED`-plus-touch cycle as fault-only throughput. COW, dirty shared-file
`page_mkwrite`/`VM_FAULT_COMPLETED`, major faults and retry/contention variants
are later separate cases. Existing correctness evidence does not time them.
No global cache dropping, memory-policy change, kernel probe or extra boot is
implicitly authorized. Keep native MM algorithms/bodies unchanged.

## Report and optimize from evidence

For every fixed workload/interface/count, retain three paired repetitions,
raw counts and durations, each rate, paired KD/Native ratios, median, minimum,
maximum and sample coefficient of variation. Preserve rejected/unrun cases and
their reasons; report qualified sample size separately. Do not pool source
versions, boot identities, CPU/NUMA layouts, caller shells, fault classes or
instrumentation. Three pairs do not provide precise confidence intervals.

Once a qualified baseline exists, choose the largest measured lock-related
loss or scaling bottleneck. Use a bounded CPU/wait profile only if attribution
needs it. Explain the mechanism, make one lock/API-only change on a separate
commit, and rerun the same affected correctness checks and paired throughput
cases against the clean baseline. Report regressions as well as gains. The
validated one-jiffy atomic-reader-release recheck remains unchanged until that
evidence justifies a lifetime-safe alternative. No Native equivalence,
performance neutrality or optimization gain is assumed.
