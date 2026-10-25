# Native/KD throughput roadmap

Current objective: test whether KD improves throughput substantially across
documented lock workloads and actual mmap/page-fault use. A large gain is a
hypothesis, not a required result. Report losses, local execution, class gaps and
variance with the gains. **This phase measures throughput only**; new tail-latency
collection and sampled workload variants are deferred. Preserve historical
latency evidence. Environment diagnosis is a separate activity.

No campaign below is authorized to run by this roadmap. The October 25
[73-versus-67 admission stop](../bench/results/10.176.26.71/bench/mmap-kdmm31-paired-20261025/README.md)
remains in force. The [60-second diagnostic](../bench/mmap_lock/DIAGNOSTIC.md)
has 43 mocked test passes and still needs exact live approval. No quiet retry,
weaker gate or repeated provider diagnostic is scheduled.

## Workload and interface boundaries

| Scenario | Existing implementation/evidence | Comparison contract and next gap |
| --- | --- | --- |
| Mutex c01/c08, exclusive-update RCUHT | [Mutex runner](../bench/tclock_compare/README.md), `run_mutex.py`; public and OUTER are separate compiled shells | Same preallocated work and post-work, Native versus current public KD. Preserve entry-only/returned-body/NO_JIT classes. OUTER is a separate regression control. |
| Pipe byte count/capacity, seek and other documented APIs | [Workload catalog](BENCHMARK_WORKLOADS.md#real-world-api-critical-sections), [public mutex collector](../bench/mutex_api_compare/run.py) | Same objects, query parameters and syscall shell; copy-to-user and post-work remain in their native positions. Freeze a bounded point list; the historical replay is not a new Native/KD plan. |
| Rwlock c01/c08/RCUHT and resident lists | [Reader/writer runner](../bench/rwlock_compare/README.md), `--lock-kind rwlock` | Local concurrent readers, bounded non-sleeping writers; keep 1% and 20% writes separate. Preserve strict delegation failures and exact drain. |
| Rwsem c01/c08/RCUHT and resident lists | Same runner, `--lock-kind rwsem`; [unified API](../include/kd_rwsem.h) | Ordinary local readers/writers and explicit OUTER writer delegation are separate controls. Internal local mutex calls cannot replace reader admission. Compare the selected interface consistently. |
| Actual shared-mm mmap/munmap | [Prepared mmap workload](../bench/mmap_lock/README.md), unchanged `kdmm31`, Native/KD boot modes | Same pthread cohort, exact mm/lock, CPUs and untouched mappings. No delegated MM body. The explicit `plain-v1` runner/report is mock-tested; live approval remains required. |
| Actual kernel page faults | [Fault correctness cases](../tests/kernel/mmap_lock/fault_cases.c), [completed-fault client](../tests/kernel/mmap_lock/page_fault_completed/client.c) | Actual native fault bodies remain on the faulting task behind the selected mmap backend. Correctness drivers exist; a generic throughput driver has not been established. Prepare that driver separately before any timed fault campaign. |
| Module-owned backing-page faults | [Private mapping runner](../bench/mmap_fault/README.md), `timing.py` / `timed_client.c` | Real CPU faults through a private backing lock, with separate native mms and native mmap locks unchanged. Preserve this evidence separately; it cannot stand in for actual mmap-backend fault throughput. |

TCLock is optional only for supported equivalent interfaces and matched work.
Its original rwsem port exports ordinary registered-worker pairs, without
equivalent cancellation, downgrade or actual-mmap APIs. There is no TCLock arm
for the proposed actual mmap/fault comparisons. Do not substitute its rwlock
for a sleeping rwsem. Explicit delegation is not evidence of generic MM support.

## First small mmap comparison

The proposed replacement is **12 plain sessions**: 1 and 16 shared-mm writers,
Native and KD, three paired repetitions, two seconds per session. Reuse build-3
payload/client binaries, the same image/configuration and prior scoped API
evidence. No latency sampling is requested. Whole-run completed mmap/munmap
cycles per second is the primary measure; retain exact totals, joins, callback
oracles, identity, retirement and existing progress checks.

The explicit `plain-v1` selection is implemented at `7e6641e` in `paired.py` and
`report.py`. Its [25 focused mocked checks](../bench/results/10.176.26.71/tests/mmap-plain-plan-20261025/README.md)
passed in recovery: 11 new plan fixtures and 14 directly affected historical
tests. Case order, plain specifications, validation receipts, report cardinality
and chronological predecessors are bound to the plan. The original 24-case
plain/sampled schema remains `paired-v1`, also used when old receipts omit a
plan field. Skipping or relabelling its rows is invalid.

Preserve the existing alternating order: initial Native validation; KD repeat 0;
Native repeats 0/1; KD repeats 1/2; Native repeat 2; recovery. This is at most
five candidate boots plus one recovery boot, not six independent paired boots.
Adjacent repeats share a boot; report that dependence. A proposed reduced
validation set is one fixed-work check plus both plain worker counts in each
mode: six unscored checks plus twelve measured sessions, or **18 payload
load/check/unload cycles**. Keeping the same capture boundaries gives at most
**31 full captures**: one initial, five boot-readiness, 24 measurement boundaries
and one recovery check. These bounds are derived and covered by the focused
fixtures. They remain maxima for exact cycle review, not live permission.

Before any live cycle, synchronize only the reviewed runner inputs while idle
and bind current source, prepared binaries, image/configuration, module set,
CPU/NUMA placement and instrumentation. Present exact commands,
counts, storage allowance and recovery entry. Stop at the first failed gate;
no measurement or endpoint is replaced after waiting. Return to the preserved
recovery entry only after proven drain; uncertainty requires review.

## Expansion after the first qualified baseline

The first baseline contains only the twelve actual mmap cases. Optional later
screens must not become prerequisites: public-mutex c08, rwlock c08/20% writes
and rwsem c08/20% writes at 16 workers would each take six Native/KD sessions
(three pairs), 18 total. The write mix is per worker; mutex c08's retained
`LEGACY_ENTRY_OBSERVATION` is not returned-body proof. Use the
[documented catalog](BENCHMARK_WORKLOADS.md), keeping each interface's source and
execution class separate. Extend worker counts from local
overhead to contention, then to the 32/36-worker NUMA boundary and 60 workers
only when justified. Set CPU lists explicitly; the normal collector is CPU 63.

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
