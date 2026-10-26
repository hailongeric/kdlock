# Per-workload performance analysis and nano selection

The strongest high-contention **mutex** examples are the short public-ABI2 seek
and pipe operations. At 60 workers, seek-set is **3.117× Native / 1.689× TCLock**,
pipecap **2.728× / 2.193×**, and pipebytes16 **2.663× / 2.039×**. Their returned
JIT completion shares exceed 97%. The strongest synthetic mutex locality example
is list16 at 60 workers: **1.728× / 1.662×**, with 98.20% returned completion.

The strongest **rwsem** ratios have a different explanation. RCUHT at 1% writes
reaches **7.907× Native at 36 workers**, but only **0.642× TCLock**, and has
**zero JIT executions**. All 84 KD points in the four 1%-write rwsem configurations
are `NO_JIT`. The data supports selecting a separate local reader/phase-policy
control; it does not support claiming that those gains come from delegation.

## Scope, evidence and interpretation

This analysis uses all 51 lock/API tables and all three MM tables from the
October 26 single-round screen: 3,292 measured points and 47 drained preparation
failures. It uses whole-run completed-operation rates, not selected peak windows.
[The comparison CSV](workload-comparisons.csv) contains one row per workload,
Native/KD/TCLock rates at 1, 32 and 60 workers, both comparator ratios, each
comparator's best observed ratio and worker count, execution classes, returned
shares and source-table hashes. Best means the maximum *observed* ratio among
valid points; it is not a confidence bound, a repeated result, or a guaranteed
optimum. Failed preparations are absent rates, never zero-throughput samples.

All observations are **exploratory**: strict host timing qualification failed
when QEMU acquired auxiliary workers. Original CPU placement, correctness and
drain were checked, but endpoint captures do not establish continuous isolation.
There is one timed observation per point and no variation estimate. The CPU
prefix crosses from NUMA node 0 to node 1 above 32 workers. Consequently a kink
near 36 workers is compatible with topology effects, but also with scheduling or
host variation; the run contains no causal cache-miss, migration, context-switch
or lock-handoff profile to distinguish them.

Comparisons stay inside each workload's captured source/binaries, call shell,
operation definition and instrumentation. Public mutex APIs, rwsem outer writers,
synthetic one-ioctl loops, per-operation syscall clients, private backing faults
and the separate installed MM kernel are not pooled. The spin/mutex synthetic
suite has 64 register-only post-work rounds; the reader/writer suite has four.
Mixed reader/writer Mops/s includes both reads and writes. Its JIT completion
share is a fraction of **writes**, whereas mutex completion share uses all
eligible lock operations. `RETURNED_JIT` alone says at least one body returned;
it does not imply that most operations delegated. Low-count wins with `NO_JIT`
are evidence of local paths, call-shell/layout costs and/or measurement variation,
not evidence of delegation. The KD provider's UBSAN-off policy is retained in
its run manifests; this screen is not a matched compiler/instrumentation ablation.

## Complete workload comparison

The following ratios include every configuration. `L` = `NO_JIT`, `J` = returned
JIT bodies, `P` = preparation failure, `R` = local private-backing readers,
`M` = local mmap-lock execution. The class in the best-point cell belongs to that
point; the CSV retains anchor-point classes separately. A dash means no valid KD
rate or no supported comparator. Full curves and raw table values are linked.

### Spin and ordinary mutex synthetic bodies

| Workload | KD/Native 1w | 32w | 60w | KD/TCLock 60w | Best KD/Native: ratio @ workers, class | KD prep gaps |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| [spin-c01](spin-c01/README.md) | 1.807× | 1.296× | 2.204× | 1.884× | 2.361× @ 52, J | 0 |
| [spin-c08](spin-c08/README.md) | 1.808× | 1.909× | 2.919× | 2.524× | 2.919× @ 60, J | 0 |
| [spin-rcuht](spin-rcuht/README.md) | 1.776× | 1.573× | 1.573× | 1.167× | 1.848× @ 36, J | 0 |
| [spin-list16](spin-list16/README.md) | 1.807× | 7.213× | 9.503× | 2.142× | 10.488× @ 56, J | 0 |
| [mutex-c01](mutex-c01/README.md) | 1.788× | 0.906× | 1.227× | 1.591× | 1.788× @ 1, L | 0 |
| [mutex-c08](mutex-c08/README.md) | 1.780× | 0.899× | 1.468× | 1.561× | 1.780× @ 1, L | 0 |
| [mutex-rcuht](mutex-rcuht/README.md) | 1.739× | 1.085× | 1.203× | 1.162× | 1.739× @ 1, L | 0 |
| [mutex-list16](mutex-list16/README.md) | 1.781× | 1.276× | 1.728× | 1.662× | 1.781× @ 1, L | 0 |

**c01/c08.** Each operation increments one or eight separately aligned shared
cache lines under one exclusive lock. At 60 workers spin c08 improves more than
c01 versus Native (2.919× versus 2.204×), consistent with preserving more dirty
payload locally across delegated requests. The gain is smaller for the mutex
shell (1.468× versus 1.227×); its physical mutex/OSQ, exact lifetime and ACK work,
and its different caller path remain part of measured cost. At 32 workers both
mutex c01 and c08 are below Native despite returned JIT, so a tiny write body is
not universally a win. Their one-worker maxima are local executions.

**list16.** Sixteen resident 64-byte nodes have immutable stride-five links;
every writer traverses and increments all 16 values. This combines repeated
exclusive use of the same dirty working set with stable lifetime and bounded
control flow. Spin achieves 9.503× Native at 60 workers, while mutex achieves
1.728×. That contrast points to lock-shell sensitivity, not a general property
of every list traversal. Cache residency and fewer ownership transfers are
plausible benefits; this run did not measure their individual contributions.

**RCUHT.** The body searches buckets and moves a preallocated node, with random
source/destination keys chosen outside the lock. It has branches, pointer chains
and multiple outcomes, with no allocator or actual RCU service in the body.
Useful serial work and a wider mutable working set plausibly reduce the amount
of lock-transfer overhead delegation can amortize. At 60 workers KD is only
1.573× Native for spin and 1.203× for mutex, and close to TCLock (1.167×/1.162×).

Source: [payload](../../../../../workload_modules/spin_cacheline/payload.h),
[list](../../../../../workload_modules/spin_cacheline/list_payload.h),
[hash](../../../../../workload_modules/spin_cacheline/hash_payload.h),
[mutex shell](../../../../../workload_modules/mutex_cacheline/module.c).

### Reader/writer spinlocks and sleeping rwsems

| Workload | KD/Native 1w | 32w | 60w | KD/TCLock 60w | Best KD/Native: ratio @ workers, class | KD prep gaps |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| [rwlock-c01-w01](rwlock-c01-w01/README.md) | 2.319× | 1.136× | 1.264× | 1.228× | 2.319× @ 1, L | 0 |
| [rwlock-c01-w20](rwlock-c01-w20/README.md) | 2.024× | 2.053× | 2.181× | 1.980× | 2.259× @ 3, L | 0 |
| [rwlock-c08-w01](rwlock-c08-w01/README.md) | 1.806× | 1.210× | 1.204× | 1.061× | 1.806× @ 1, L | 0 |
| [rwlock-c08-w20](rwlock-c08-w20/README.md) | 1.712× | 1.931× | 2.066× | 1.606× | 2.400× @ 3, L | 0 |
| [rwlock-rcuht-w01](rwlock-rcuht-w01/README.md) | 1.916× | 1.072× | 1.066× | 0.979× | 1.916× @ 1, L | 0 |
| [rwlock-rcuht-w20](rwlock-rcuht-w20/README.md) | 1.883× | 1.379× | 1.330× | 1.328× | 1.883× @ 1, L | 0 |
| [rwlock-list16-w01](rwlock-list16-w01/README.md) | 1.858× | 1.203× | 1.154× | 1.010× | 1.858× @ 1, L | 0 |
| [rwlock-list16-w20](rwlock-list16-w20/README.md) | 1.790× | 1.796× | 2.176× | 1.255× | 2.591× @ 6, L | 0 |
| [rwsem-c01-w01](rwsem-c01-w01/README.md) | 1.159× | 1.824× | 1.948× | 0.449× | 3.308× @ 36, L | 0 |
| [rwsem-c01-w20](rwsem-c01-w20/README.md) | 1.103× | 1.358× | 1.523× | 0.383× | 2.977× @ 4, L | 0 |
| [rwsem-c08-w01](rwsem-c08-w01/README.md) | 1.160× | 2.297× | 2.223× | 0.476× | 2.744× @ 36, L | 0 |
| [rwsem-c08-w20](rwsem-c08-w20/README.md) | 1.115× | 1.314× | 1.511× | 0.450× | 3.395× @ 2, L | 0 |
| [rwsem-rcuht-w01](rwsem-rcuht-w01/README.md) | 1.304× | 2.177× | 2.280× | 0.512× | 7.907× @ 36, L | 0 |
| [rwsem-rcuht-w20](rwsem-rcuht-w20/README.md) | 1.339× | 1.451× | 2.255× | 0.674× | 3.821× @ 3, L | 0 |
| [rwsem-list16-w01](rwsem-list16-w01/README.md) | 0.893× | 2.091× | 2.192× | 0.515× | 4.902× @ 36, L | 0 |
| [rwsem-list16-w20](rwsem-list16-w20/README.md) | 0.942× | 0.882× | 0.968× | 0.658× | 2.612× @ 4, J | 0 |

**Rwlock, 1% writes.** Readers execute locally and write only caller-private
results. At 60 workers KD is close to the controls: 1.066–1.264× Native and
0.979–1.228× TCLock. Readers dominate total operations; only the rare writer can
benefit from JIT, so a large writer-specific improvement need not noticeably
change total throughput. c08/list/hash add read-side work that also stays local.

**Rwlock, 20% writes.** Writer contention is more frequent and KD/Native improves
to 1.330–2.181× at 60 workers. Yet c01 and c08 are `NO_JIT` at that point while
list16 and RCUHT have returned bodies. Ordinary reader/writer admission and local
lock paths therefore matter independently of delegation. The list's full traversal
and the hash's data-dependent paths lower absolute rates relative to c01/c08.

**Rwsem, 1% writes.** All KD measurements are local. KD's uninterruptible wait
path polls for at most 16,384 condition probes before sleeping, closes reader
admission on writer reservation, and keeps phase and reader-drain queues separate.
Readers use a counted reservation/recheck and ordered release; no reader body is
delegated. Avoiding sleep/wakeup transitions for short reader/writer epochs is a
source-grounded explanation for Native differences, but the campaign did not
count those transitions. The TCLock comparator uses a distinct reader gate and
counter protocol and is substantially faster at high counts: KD reaches only
0.449–0.515× TCLock at 60 workers. A winner against Native is not a winner against
both baselines.

The largest RCUHT ratio at 36 workers is amplified by a Native trough. At
32/36/40 workers, Native rates are 5.024788/0.821573/4.141666 Mops/s and KD rates
10.937521/6.496501/9.346471. KD also slows at 36; the 7.907× ratio is not a KD
throughput peak. The list16 36-worker result shows the same pattern. Do not pick
36 workers as a guaranteed sweet spot from one round.

**Rwsem, 20% writes.** More frequent admission closure and reader drainage reduce
absolute throughput versus the 1% case. Delegated writers can queue only after
reader drainage; they release their reader-free reservation on the original
caller after matching unlock. At 60 workers returned writer shares are 11.96%
for RCUHT and 44.33% for list16, yet KD remains below TCLock. list16 is even
0.968× Native there. Its best four-worker result has only 0.2796% returned writer
completion, so attributing its 2.612× Native gain primarily to JIT would be wrong.
These observations favor distinguishing reader/phase-policy gains from
high-density writer delegation when defining a nano case.

Source: [operation loop](../../../../../workload_modules/rwlock_bench/module.c),
[reader/writer payload](../../../../../workload_modules/rwlock_bench/payload.h),
[rwsem shell](../../../../../workload_modules/rwlock_bench/direct_rwsem.h),
[KD rwsem implementation](../../../../../kernel_module/kd_rwsem.c),
[TCLock rwsem](../../../../../tclock_backend/komb_rwsem.c).

### Snapshot and real API workloads

| Workload | KD/Native 1w | 32w | 60w | KD/TCLock 60w | Best KD/Native: ratio @ workers, class | KD prep gaps |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| [argbounds-w00](argbounds-w00/README.md) | 1.316× | 1.048× | 1.386× | 1.078× | 1.992× @ 16, J | 0 |
| [argbounds-w20](argbounds-w20/README.md) | 1.391× | 0.717× | 0.797× | 0.620× | 1.391× @ 1, L | 0 |
| [taskname-w00](taskname-w00/README.md) | 1.431× | 0.779× | 1.093× | 0.896× | 2.084× @ 2, L | 0 |
| [taskname-w20](taskname-w20/README.md) | 1.767× | 0.896× | 0.820× | 0.633× | 1.767× @ 1, L | 0 |
| [ofd-front-n16](ofd-front-n16/README.md) | 1.595× | 1.046× | 1.230× | 0.858× | 1.595× @ 1, L | 0 |
| [ofd-front-n128](ofd-front-n128/README.md) | 1.590× | 1.037× | 1.544× | 0.958× | 1.590× @ 1, L | 0 |
| [ofd-tail-n16](ofd-tail-n16/README.md) | 1.597× | 1.156× | 1.822× | 1.046× | 1.822× @ 60, J | 0 |
| [ofd-tail-n128](ofd-tail-n128/README.md) | 1.595× | 1.294× | 1.322× | 1.066× | 1.595× @ 1, L | 0 |
| [ofd-miss-n16](ofd-miss-n16/README.md) | 1.628× | 1.040× | 1.469× | 1.146× | 1.628× @ 1, L | 0 |
| [ofd-miss-n128](ofd-miss-n128/README.md) | 1.491× | 1.183× | 1.329× | 1.087× | 1.499× @ 52, J | 0 |
| [setfd-toggle-n16](setfd-toggle-n16/README.md) | 1.607× | 1.354× | 2.434× | 1.096× | 2.434× @ 60, J | 0 |
| [setfd-toggle-n512](setfd-toggle-n512/README.md) | 1.582× | 1.553× | 2.295× | 1.498× | 2.645× @ 56, J | 0 |
| [pipebytes-query-n16](pipebytes-query-n16/README.md) | 1.534× | 1.320× | 2.663× | 2.039× | 2.663× @ 60, J | 0 |
| [pipebytes-query-n128](pipebytes-query-n128/README.md) | 1.694× | 0.991× | 1.570× | 1.554× | 1.694× @ 1, L | 0 |
| [pipecap-query-n16](pipecap-query-n16/README.md) | 1.635× | 1.326× | 2.728× | 2.193× | 2.728× @ 60, J | 0 |
| [seek-set-n16](seek-set-n16/README.md) | 1.674× | 1.713× | 3.117× | 1.689× | 3.117× @ 60, J | 0 |
| [seek-end-n16](seek-end-n16/README.md) | 1.503× | 1.743× | 3.058× | 1.661× | 3.094× @ 48, J | 0 |
| [utsname-host-n20](utsname-host-n20/README.md) | 1.651× | 2.381× | 7.215× | 1.218× | 8.772× @ 40, J | 0 |
| [utsname-domain-n20](utsname-domain-n20/README.md) | 1.659× | 2.934× | 6.020× | 1.524× | 7.278× @ 36, J | 0 |
| [xattr-front-n16](xattr-front-n16/README.md) | — | — | — | — | 1.533× @ 56, J | 12 |
| [xattr-front-n128](xattr-front-n128/README.md) | — | 0.730× | 1.393× | 1.016× | 1.393× @ 60, J | 15 |
| [xattr-tail-n16](xattr-tail-n16/README.md) | 1.489× | 0.851× | 1.101× | 0.992× | 1.489× @ 1, L | 1 |
| [xattr-tail-n128](xattr-tail-n128/README.md) | 1.546× | — | — | — | 1.546× @ 1, L | 16 |
| [xattr-miss-n16](xattr-miss-n16/README.md) | 1.723× | 0.917× | 1.095× | 0.950× | 1.723× @ 1, L | 0 |
| [xattr-miss-n128](xattr-miss-n128/README.md) | 1.629× | 0.922× | — | — | 1.629× @ 1, L | 3 |
| [xattr-size-n16](xattr-size-n16/README.md) | 1.713× | 0.806× | 1.023× | 0.908× | 1.713× @ 1, L | 0 |
| [xattr-size-n128](xattr-size-n128/README.md) | 1.606× | 0.906× | 0.992× | 0.928× | 1.606× @ 1, L | 0 |

**Argument bounds and task names.** Argument bounds copies four words; taskname
calls the original `strscpy_pad` into a 64-byte caller-local destination and
validates the padded result after unlock. Both snapshot readers take an exclusive
spinlock. Read-only argbounds is 1.386× Native at 60 workers, while the longer
helper/copy/validation taskname is 1.093× and loses to TCLock. At 20% mutations,
writers always execute locally; returned JIT bodies are delegated snapshot reads,
not delegated mutations. Both mutation variants regress against both baselines
at 60 workers. Local writers changing shared data and fewer eligible operations
plausibly reduce amortization and locality.

**OFD front/tail/miss, 16/128.** Front hits terminate at the first conflict, so
increasing the total list length does not imply proportionally more protected
work. Tail and miss scan the list. At 60 workers KD tail/miss128 manages about
2.34–2.36 Mops/s versus 4.56–4.65 at 16 entries. Stable resident metadata can
benefit from repeated execution on one owner, but serial pointer traversal
remains real work. Front16/front128 lose to TCLock at 60 workers; tail/miss show
only small TCLock advantages. List size and query position must stay separate.

**Setfd stride 16/512.** The number in this workload is the descriptor stride,
not a list length. Workers use descriptors starting at `64 + worker * stride`;
one measured operation sets and then validates a close-on-exec flag. The protected
bitmap update is tiny, but spreading bits changes sharing of bitmap cache lines.
KD reaches 5.422/7.229 Mops/s at 60 workers, respectively, versus 2.434×/2.295×
Native. The different strides cannot be interpreted as a 512-entry traversal.

**Pipe capacity, pipe bytes and seek.** These are public-ABI2 mutex calls, the
best high-contention mutex examples in this screen. Capacity reads one field;
pipebytes walks the live ring and sums buffer lengths; seek checks bounds and
conditionally updates `f_pos`/`f_version`, with SEEK_END adding a size read.
There is no allocation, sleeping body or helper-call chain. File references,
syscall work and user copies remain outside the protected body. Repeated access
to a small shared state, high returned-body coverage and batching under one
physical owner form the strongest evidence for a favorable nano mechanism.
The larger pipebytes128 traversal reduces the 60-worker Native advantage from
2.663× to 1.570×. These comparisons still use actual Native object placement and
private KD/TCLock objects; layout and syscall envelopes were not independently
ablated.

**UTS host/domain, 20% writes.** The fixed-size writer copy may delegate and readers
remain local. Native uses Linux rwsem, whereas KD and TCLock use spinning rwlocks.
The 60-worker 7.215×/6.020× Native gains therefore include a lock-family change;
they are not examples of KD rwsem outperforming Native rwsem. Gains against
TCLock are much smaller (1.218×/1.524×). Keep these outside the rwsem nano ranking.

**Xattr front/tail/miss/size, 16/128.** Front searches one candidate, tail traverses
the list then copies, miss traverses without a copy, and size traverses to the
entry with a null destination buffer. Original `strcmp` calls remain, with actual
`memcpy` where required. At 60 workers the complete n16 tail/miss/size observations
are only 1.023–1.100× Native and below TCLock; size128 is 0.992× Native/0.928× TCLock.
Long helper/control and pointer paths limit the benefit of moving execution.
The 47 missing KD points exhausted the configured helper-learning waves and
drained before measurement: front16=12, front128=15, tail16=1, tail128=16,
miss128=3. They establish preparation reliability limits, not a slow timed rate.
Their missing anchors and curves remain gaps. Xattr is a poor choice for a tiny
helper-free best-case benchmark.

Source: [snapshot bodies](../../../../../workload_modules/rwlock_bench/snapshot_payload.h),
[local snapshot writers](../../../../../workload_modules/rwlock_bench/direct_spin.h),
[OFD/setfd/xattr](../../../../../workload_modules/real_api/module.c),
[pipe/seek](../../../../../workload_modules/real_api/mutex.c),
[UTS](../../../../../workload_modules/real_api/uts.c),
[API client](../../../../../bench/real_api/client.c).

### Separate MM suites

| Workload | KD/Native 1w | 32w | 60w | KD/TCLock 60w | Best KD/Native: ratio @ workers, class | KD prep gaps |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| [mm-mmap](../catalog-mmap-single-20261026/mmap/README.md) | — | — | — | — | — | 0 |
| [mm-fault](../catalog-mmap-single-20261026/fault/README.md) | 1.017× | 1.392× | 1.418× | 1.131× | 1.428× @ 52, R | 0 |
| [mm-shared-mm](../catalog-mmap-single-20261026/shared-mm/README.md) | 0.974× | 0.180× | 0.096× | — | 0.995× @ 2, M | 0 |

**Independent-mm mmap/munmap.** Only Native is implemented in this scope; it
performs no backing-lock access or page touch. Throughput rises from 0.387208
Mcycles/s at one worker to 1.069449 at four, then falls to 0.213577 at 60. That
curve does not measure KD or prove that any particular allocator, TLB or scheduler
mechanism is responsible.

**Private-backing CPU faults.** Each cycle is `MADV_DONTNEED` plus a checked CPU
read. All backends keep native mmap locks and execute local backing readers;
there is no generated-body delegation. At 60 workers Native/KD/TCLock reach
5.772332/8.184430/7.233381 Mcycles/s. The 1.418× Native and 1.131× TCLock KD result
is consistent with local reader-backend overhead differences, not delegated
page-fault bodies. The 32-to-36 transition changes topology and all arms slow.

**Actual shared-mm mmap/munmap.** This separate installed `kdmm31` image compares
`kd_mmap=off/on`, keeping native MM bodies on their original tasks. At 60 workers
Native is 70,350.82 cycles/s and KD 6,752.42: KD is 0.096× Native. KD is lower at
every measured count. Shared-mm writer admission, reader drainage, the local
mutex route and native MM serial work all remain in the path. The uninterruptible
microbenchmark's polling result cannot be transferred to killable mmap writer
semantics. Six high-count KD observations lack a positive full-cohort peak window;
exact aggregate accounting and drain passed, but the optional peak remains
unavailable. No run measured causal scheduler/VM-internal costs, so the precise
regression breakdown is unresolved.

Sources and exact kernel identities: [MM report](../catalog-mmap-single-20261026/README.md),
[private timing](../../../../../bench/mmap_fault/timing.py),
[MM adapter](../../../../../kernel_integration/mmap_lock/README.md).

## Selected favorable examples

Rates below are Mops/s within each workload. The completion percentage is over
all mutex operations, but over **writers only** for rwsem. Every row is one
observation. The local pipecap row is included to distinguish the largest
TCLock ratio from a JIT-heavy win.

| Workload | Workers | Native | KD | TCLock | KD/Native | KD/TCLock | KD class; returned share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| seek-set-n16 | 60 | 1.335730 | 4.163092 | 2.464838 | 3.117× | 1.689× | RETURNED_JIT; 97.2969% |
| seek-end-n16 | 48 | 1.450615 | 4.488347 | 2.467012 | 3.094× | 1.819× | RETURNED_JIT; 97.6146% |
| pipecap-query-n16 | 60 | 1.903198 | 5.192804 | 2.368322 | 2.728× | 2.193× | RETURNED_JIT; 97.4686% |
| pipebytes-query-n16 | 60 | 1.828942 | 4.869609 | 2.387763 | 2.663× | 2.039× | RETURNED_JIT; 97.3640% |
| mutex-list16 | 60 | 2.455822 | 4.242759 | 2.553286 | 1.728× | 1.662× | RETURNED_JIT; 98.2021% |
| mutex-list16 | 20 | 5.189264 | 5.481742 | 2.518496 | 1.056× | 2.177× | RETURNED_JIT; 98.8295% |
| pipecap-query-n16 | 4 | 13.342398 | 16.243509 | 2.722419 | 1.217× | 5.967× | NO_JIT; 0.0000% |
| rwsem-rcuht-w01 | 36 | 0.821573 | 6.496501 | 10.120494 | 7.907× | 0.642× | NO_JIT; 0.0000% |
| rwsem-rcuht-w01 | 60 | 3.289808 | 7.500175 | 14.655516 | 2.280× | 0.512× | NO_JIT; 0.0000% |
| rwsem-list16-w01 | 36 | 1.330796 | 6.523674 | 9.517633 | 4.902× | 0.685× | NO_JIT; 0.0000% |
| rwsem-list16-w01 | 8 | 7.701607 | 16.597154 | 14.946496 | 2.155× | 1.110× | NO_JIT; 0.0000% |
| rwsem-list16-w20 | 4 | 1.633089 | 4.265740 | 3.425752 | 2.612× | 1.245× | RETURNED_JIT; 0.2796% |

The largest mutex KD/TCLock ratio is pipecap at four workers (5.967×), but it is
`NO_JIT` and only 1.217× Native. For a delegation-oriented nano, the stronger
selection evidence is the sustained returned-body coverage of pipe/seek at
12–60 workers and list16 at 20–60. For rwsem, RCUHT's 36-worker Native ratio is
the largest, while list16 at four workers and 20% writes is the largest observed
TCLock ratio (1.245×); the latter's 0.2796% writer completion share also rules out
a strong causal claim for JIT. At 60 workers every rwsem case loses to TCLock.

## Mechanism to preserve in a new nano workload

The supported mutex design target is a **small, bounded, repeatedly shared body
under sustained contention**. Reduce real object lookup, file/syscall envelope,
helper calls, list links and random outcome branches to a preallocated resident
state with one short load/check/update critical section. Keep identical business
work across Native, KD and TCLock, public ABI2 mutex calls, returned values and
an exact quiescent invariant. Batching should keep the shared state near its
executor while amortizing physical ownership changes; the current KD combiner
has a bounded 256-body NUMA-local cohort and retains explicit handoff/retirement
obligations. Those mechanisms must remain untouched by workload simplification.

A rwsem nano needs two clearly named questions. A 1%-write local-reader variant
captures the measured rare-writer advantage over Native and must report zero
JIT honestly if that persists. A writer-dense variant can deliberately remove
reader-phase interference to test the mutex-like delegation hypothesis, but it
is a **new workload hypothesis**, not a demonstrated explanation of the 1% wins.
Do not silently turn the 1% measurement into an all-writer result or claim to beat
TCLock because KD beats Native.

Retain the original catalog and these rankings as the selection evidence.
Validate the simplified workload's result, admission, exact returned completions,
source leases and drain, then measure it with fresh controls. Until that new
measurement exists, “best case” describes the chosen favorable conditions, not
a proven universal maximum. A focused comparison of short versus longer body,
low versus sustained contention, and rare versus dense writers would distinguish
body simplification, local-path savings and actual delegation more directly than
selecting the single largest ratio from this exploratory screen.

Combiner source: [NUMA locality and bounded handoff](../../../../../kernel_module/mutex/combiner.inc).
