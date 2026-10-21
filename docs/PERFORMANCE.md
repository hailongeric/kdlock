# Performance status

The reader/writer semaphore (rwsem) implementation measured in `c21345b` is
**accepted as the current version**, including the two-worker regressions below.
Acceptance identifies the maintained implementation; it does not turn every
measured configuration into a performance pass.

Throughput is reported in **Mops/s**, millions of completed operations per second.
The **whole-run median** is the middle of three repetition rates, each measured
over its full timed interval. A ratio of 2× means twice the reference rate;
0.286× means 28.6% of that rate, or 71.4% slower. A **JIT** (just-in-time compiled)
body counts as returned only after delegated execution reaches its matching
unlock and completes the return protocol. `NO_JIT` means no generated body was
entered during measurement; `PARTIAL_JIT` means bodies were entered but none
completed the return protocol. **Drained** means all requests and their required
references and acknowledgements finished. The
[terminology guide](TERMINOLOGY.md) defines the remaining lock and evidence terms.

The later [instruction-exit change](design/admission.md#checked-instruction-exits)
has focused correctness validation, including ordinary rwsem delegation controls.
The fresh shared-lock comparison below measures ordinary payloads on the restored
source; it does not isolate additional flag-preservation cost in images containing
instruction markers. Every throughput result retains its recorded source version.

The retained mutex performance baseline is `752fec1`, preserving KD-only physical
ownership and the 32-byte object with native 8-byte alignment. Independent OSQ
and delegation memberships share the existing preallocated node pool. A
256-body locality boundary retains physical handoff for larger deferred NUMA
cohorts; smaller prefixes continue FIFO within the total 1024-body limit.
Fresh sixty-worker medians improve over the preceding compact implementation
by 14.3% for c01, 13.6% for seek and 16.5% for pipe. Pipe remains 9.2% behind
the fresh old-256-byte control. Earlier compact rounds below retain their own
source identities and measurements.
The
[2026-10-17 paired report](../bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md)
contains 504 complete, drained sessions: two workloads, 21 worker counts, three
repetitions and four arms (accepted compatibility baseline, KD-only, Native,
TCLock). It uses the regular 64-vCPU VM and collector 63, and measures the former
256-byte object. Those results do not measure the compact layout.

## Separate mmap and page-fault measurements

The [split-workload report](../bench/results/10.176.26.71/tests/mmap-fault-split-20261021/README.md)
records 48 serial sessions at timing source `77cadf5`, reusing the validated
`9291000` provider/payload binaries in the original VM. Mmap-only is a Native
map/unmap control with zero fault callbacks. Fault cycles use concurrent local
readers and include PTE discard plus a checked CPU read; there is no reader
delegation or KD/TCLock replacement of the native mmap lock.

All sessions drained, but the strict immediate host endpoint failed (73 versus
67 QEMU threads). The report retains all three repetitions, plain/sampled
controls and complete-operation p95, including 24.45% whole-rate CV for
one-worker mmap and 9.78% for sixteen-worker Native faults. These measurements
do not establish accepted gains, isolate sampling cost or resolve the seven
mutex regressions. Full-mm conversion remains open.

The subsequent [shared-mm Native writer baseline](../bench/results/10.176.26.71/tests/mmap-writer-native-20261021/README.md)
completed twelve serial sessions at `b043da5` after focused correctness and
four client validations. All pthreads share the exact actual mmap lock and the
mapped ranges are never touched. Plain whole-run median cycle throughput was
658,172/s with one worker and 108,217/s with sixteen. Three-repeat CV was 17.96%
and 9.85%, respectively; sampled p95 medians were 1.585 us and 69.515 us.

This Native instrumented baseline has a failed immediate host endpoint (76
versus the original 67 threads). Repetition and sampling effects remain
unseparated, and no gain or KD/TCLock mmap replacement is established. The seven
mutex causes remain unresolved; the earlier independent-mm results stay fixed.

## Unified public mutex: acceptance remains open

The [focused pipecap investigation](../bench/results/10.176.26.71/bench/pipecap-causal-20261021/README.md)
now examines five-worker path counts and waiting with unchanged original
binaries. Its initial 74-versus-67 host check failed before any new execution;
the separate diagnostic plan is awaiting basic/affected validation and a fresh
strict gate. No cause or production optimization is established.

A separate [operation-latency diagnostic](../bench/results/10.176.26.71/bench/mutex-latency-20261021/README.md)
completed all 252 serial sessions with frozen original providers and plain,
sampling-disabled and sampling-enabled callers. It retains 126 exact KD
retirements and 4,073,421 observations; all sampled workers meet the predeclared
minimum. Basic/affected VM checks passed, and the 5,218,772-check independent
audit verifies evidence integrity, including eight compiled body comparisons.
The immediate host endpoint fails at 125 versus 67 threads. The earlier capacity
failure, missing rejected samples and three failed preflights remain recorded.
Plain DIRECT/OUTER median ratios range from 0.3219 to 1.0593 across six comparable
points; plain RCUHT has split classes. Sampled p95 ratios range from 1.0733 to
3.2231, with substantial observer effects and variation. The report retains all
repetitions, range/CV and control comparisons. Sampled complete-operation p95 is
now available; causal fixes, acquisition latency and host interference remain
unresolved. All seven points remain unaccepted.

The [public DIRECT comparison](../bench/results/10.176.26.71/bench/mutex-public-20261020/README.md)
measured collection `d21a1e3` against frozen OUTER, Native and TCLock in 1,764
valid, drained sessions. Seven public/OUTER losses were separated across the
three-repeat ranges at the provisional 5% screen. This threshold was not
user-approved, and p95 latency was not measured.

After the selected [continuation correctness checks](../bench/results/10.176.26.71/tests/native-continuation-20261020/README.md)
completed, the [controlled original-input replay](../bench/results/10.176.26.71/bench/mutex-public-regressions-20261020/README.md)
completed 120 valid, drained sessions on the same VM. Four losses remained
separated; two had overlapping ranges; one fell below the provisional screen.
All seven causal resolutions remain unresolved. Two class comparisons remain
gaps; p95 was unmeasured in that replay. An additional QEMU worker on collector CPU 63 in the
post-run receipt is retained as an unresolved timing confounder; its later
retirement does not prove absence during measurement. No checks were weakened.

The original matrix and replay have separate records and archives. Neither
measures the later continuation/prefetch corrections, and neither establishes
whole-kernel replacement or performance acceptance for the unified API.

## Current shared-lock follow-up

The separate [current-source comparison](../bench/results/10.176.26.71/bench/shared-lock-followup-20261020/README.md)
completed 756 rwsem and 270 rwlock sessions on the original recovery VM.
All passed functional checks and drained, with 378 and 90 exact KD retirements.
The measured `f48b90e` inputs equal restored, validated `a768361`; historical
results below remain separate.

Rwsem meets observed whole-median and best-peak parity at 118/126 Native
comparisons, with six misses and two split execution-class points. Its immediate
post-run host-thread check failed (115 versus 67). Rwlock meets parity at 27/30
Native and 28/30 TCLock comparisons, with no class splits. Its host receipts
match, but the after receipt was captured 117.556 seconds after completion;
the intervening interval remains unobserved. Largest three-round whole-rate
spreads are rwsem KD/Native 89.10%/227.88%, and rwlock KD/Native/TCLock
10.72%/83.70%/43.63%. Full ranges, all misses and artifact hashes are in the
stage report. Shared-lock latency, runtime interference and the seven separate mutex
regressions remain unresolved; these results do not establish blanket acceptance.

## Resident-list follow-up: coverage completed with strict refusals

The [same-VM resident-list report](../bench/results/10.176.26.71/bench/nano-list-followup-20261020/README.md)
retains two separate runs on validated `f48b90e` inputs. `timing-1` completed
144 spin/mutex sessions and two shared controls, then stopped at the first KD
rwlock case because its required complete JIT body did not execute. Its data,
published/loaded image and exact retirement checks pass; the strict failure is
preserved and excluded from scoring. Its remaining 69 rwlock cases subsequently
completed in the separate diagnostic continuation described below.
The untouched rwsem task subsequently completed all 48 sessions in `rwsem-1`,
with 24 returned-JIT KD sessions and exact retirements.

Independent reviews verify evidence integrity with 250,374 and 71,582 checks.
Both immediate host endpoints fail the original thread-set check, at 83 and
86 threads versus 67. Descriptive parity counts are spin 8/8 against each
control, mutex 4/8 Native and 7/8 TCLock, and rwsem 4/8 Native. Maximum
three-run whole-rate spreads are KD/Native/TCLock spin 5.56%/12.86%/4.09%,
mutex 4.79%/1326.48%/35.90%, and KD/Native rwsem 165.98%/22.91%.
All misses, ranges, sample CVs and separate plain/prefetch comparisons remain
in the report. No blanket prefetch benefit or performance acceptance follows.
The seven earlier mutex regressions, strict rwlock execution failures and
family-specific latency/runtime-interference gaps remain unresolved.

The [separate 2026-10-21 diagnostic stage](../bench/results/10.176.26.71/bench/nano-rwlock-diagnosis-20261021/README.md)
binds the running QEMU executable and records extra workers with positive
disk-write counters. Background writes also occur in its RAM control; the
historical timing effect is still unmeasured. Provider gate counters and their
matched overhead measurements remain separate from unchanged-binary coverage
and performance acceptance.
The first fixed 12-case diagnosis preserves six eight-worker NO_JIT failures
and six sixty-worker successes. Measured diagnostic/original whole-run medians
are 1.1010/1.00055 at eight/sixty workers, with overlapping three-run ranges;
these are instrumentation observations, not an optimization claim.
All 12 exact retirements and 59,561 inert evidence checks pass, while the
72-versus-67 host endpoint fails. The separate remaining-coverage run has now
completed all 69 cases: 59 strict successes, ten strict NO_JIT failures and a
76-versus-67 host mismatch. Its 12,155 evidence checks pass, including 23 exact
retirements. Eight-worker KD results lack three successful same-class repeats.
At sixty workers, both n16 variants meet observed two-rate parity against
both controls; both n128 variants miss it. Maximum three-repeat spreads are
7.25% KD, 9.49% Native and 7.42% TCLock. These remain descriptive results under
the failed endpoint. The seven mutex causal regressions remain unresolved;
their later sampled operation-latency evidence is recorded above.
The second admission diagnostic classifies all 10,441 ready eight-worker
combiner attempts as first-follower non-combinable refusals. All six low-count
sessions still fail NO_JIT; all six sixty-worker sessions pass. Its 83,603
integrity checks and 12 exact retirements pass, with a failed 74-thread endpoint.
Matched observed/original median ratios are 1.0591/1.0269; counter, layout,
admission and noise effects are inseparable, so no optimization is claimed.

## Fresh 32-byte mutex comparison with Native and TCLock

The [2026-10-20 comparison](../bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/README.md)
measures the retained `752fec1` runtime from collection source `bd9d4ce` against
fresh Linux Native and TCLock controls. All 567 sessions passed their result and
drain checks: seven workloads, workers 1/2/4/8/16/32/36/48/60, three backends and
three 2000 ms repetitions. This is a focused nine-point grid in the same
64-vCPU VM with collector 63. Whole-run median Mops/s at sixty workers is:

| Workload, 60 workers | Linux Native | TCLock | KD | KD / Native | KD / TCLock |
| --- | ---: | ---: | ---: | ---: | ---: |
| c01/post64 | 3.974 | 3.145 | 4.952 | 1.246× | 1.575× |
| c08/post64 | 3.067 | 2.744 | 3.671 | 1.197× | 1.338× |
| RCUHT | 1.740 | 1.752 | 2.077 | 1.194× | 1.186× |
| SEEK_SET n16 | 1.369 | 2.448 | 4.185 | 3.057× | 1.709× |
| SEEK_END n16 | 1.310 | 2.525 | 4.185 | 3.196× | 1.658× |
| Pipe bytes n16 | 1.919 | 2.442 | 4.904 | 2.555× | 2.008× |
| Pipe capacity n16 | 1.907 | 2.491 | 4.345 | 2.279× | 1.744× |

At sixty workers KD's median exceeds both controls for every tested workload;
its minimum also exceeds their maxima in these three repetitions. At eight
workers KD trails Native for c01/c08/RCUHT at 0.834×/0.582×/0.852×, while the four
API medians exceed both controls. The complete curves preserve low-count
regressions, repetition ranges and separately measured peak rates. These are
descriptive results, not confidence intervals or full-grid parity.

Of 189 KD sessions, 68 witness synthetic generated-body entry, 78 count matching
returned API bodies and 43 have no generated entry. There are no PARTIAL_JIT
sessions or rejected timings. The c08/two-worker point splits into two
entry-positive repetitions and one NO_JIT repetition; those classes are not
pooled. Pipe-byte/capacity points at one/two/four workers remain local and are
not JIT results. At sixty workers API returned-body shares are 97.31–97.62%.
TCLock's measured returned delegation counts remain a separate counter class.

The two basic programs and 86 cases in four benchmark test programs passed.
All 567 retained kernel logs have no matched runtime faults; the VM is idle.
The independent archive/source/arithmetic review passed 668,688 checks and
reconstructed every timing window. Production and admission are unchanged;
no full suite or separate live protocol probe was rerun for this documentation
and benchmark change. Host pinning and frequency policy remained unchanged,
with ondemand frequency and imperfect NUMA page residency explicitly retained
as measurement conditions. Earlier compact/old256 comparisons below keep their
own source identities and are not pooled with this round.

## Mutex shared-node and locality comparison

The [shared-node investigation](../bench/results/10.176.26.71/bench/mutex32-mcs-20261020/README.md)
retains four separate source blocks: preceding compact `826faa6` (production
`76af844`), rejected FIFO trial `f4d359d`, old256 `0324e60`, and retained
`752fec1`. Each workload/worker/source point has three 2000 ms plain repetitions
in the same 64-vCPU VM with collector 63. Whole-run median Mops/s for the retained
comparison is:

| Workload | Workers | Previous 32-byte | Retained 32-byte | Old 256-byte | Retained / previous | Retained / old |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| c01/post64 | 8 | 6.134 | 6.005 | 7.494 | 0.979× | 0.801× |
| c01/post64 | 60 | 4.251 | 4.857 | 4.959 | 1.143× | 0.979× |
| SEEK_SET n16 | 8 | 4.290 | 4.668 | 4.875 | 1.088× | 0.957× |
| SEEK_SET n16 | 60 | 3.708 | 4.211 | 4.011 | 1.136× | 1.050× |
| Pipebytes/query n16 | 8 | 5.376 | 5.602 | 6.856 | 1.042× | 0.817× |
| Pipebytes/query n16 | 60 | 4.199 | 4.890 | 5.385 | 1.165× | 0.908× |

The shared OSQ subrecord occupies existing node padding: nodes remain 320 bytes,
aligned to 64 bytes. The two queues retain separate links, cancellation and
retirement. No auxiliary hash, shared lock reference count, registry lock or
new RCU mechanism is added. At the locality boundary, eight or more deferred
requests receive handoff; a smaller prefix is serviced before FIFO continuation.
Exact ownership, admission, frames, source leases and unlock ACKs remain.

The earlier `f4d359d` trial instead kept every deferred cohort on the current
owner after 128 bodies. Its sixty-worker c01/seek/pipe medians fell
28.8%/30.9%/13.3% versus the preceding compact arm, despite longer batches.
That rejected policy remains reachable as `archive/mutex32-fifo-20261020`;
its timings are not pooled with `752fec1`. These experiments do not isolate
the shared-node storage contribution or establish a cache-transfer cause.

All eight-worker retained/baseline repetition ranges overlap, including the
2.1% lower c01 median. At sixty workers, c01 remains 2.1% below old256 with
overlapping ranges, seek is descriptively 5.0% above it, and pipe retains a
9.2% gap. Three sequential repetitions are not confidence intervals or a
uniform speedup claim; this focused comparison does not establish full-grid
parity. No profiles or hardware cache-transfer counts were collected.

All 72 timings passed and drained. The 48 real-API sessions counted returned
JIT bodies; the 24 synthetic c01 sessions witnessed generated-body entry only.
At sixty workers, retained seek/pipe returned-body shares are 97.30%/97.44%.
Whole-session batch ratios include warmup and are not measured-phase batch
distributions. Both new sources passed their own 17 basic/affected checks,
11/13-case runner programs and three live probes. All 78 retained kernel logs
have no matched runtime faults; detailed receipts remain with the report.

## Earlier mutex owner, gate and tail comparison

The [cache-line investigation](../bench/results/10.176.26.71/bench/mutex32-cacheline-20261019/README.md)
compares fresh `0987358` (production `c2f0d9c`), retained `76af844`, old256
`0324e60` and a separate later prefetch trial `de30588`. Each source/worker
point has three 2000 ms plain repetitions in the same 64-vCPU VM with collector
63. Whole-run median Mops/s for the retained comparison is:

| Workers | Old 256-byte | Previous 32-byte | Retained 32-byte | Retained / previous | Retained / old |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 6.862 | 5.310 | 5.574 | 1.050× | 0.812× |
| 60 | 5.387 | 4.144 | 4.181 | 1.009× | 0.776× |

The candidate avoids a necessarily failing shared-tail CAS when the reserved
head already has a successor, and retains the exact CAS and delayed-link wait
for racing publication. The inlined gate hint and ownership predicate keep
their owner/phase reads, full acquisition CAS and independent physical-owner
probes. Layout remains 32 bytes with native 8-byte alignment; no auxiliary hash,
shared lock refcount, registry lock or auxiliary RCU mechanism is introduced.

Separate placement diagnostics use unchanged baseline provider bytes. Moving
the owner to a different cache line from gate/tail changes observed medians by
+13.4% at eight workers and +0.7% at sixty. Gate readers and tail writers still
share a line, and dedicated padding changes the object's neighbors. These
results do not establish owner sharing alone as the major sixty-worker cause.
The ordinary compact arms all actually place owner/gate/tail on one line;
native alignment by itself does not guarantee that placement. No validated
HITM/cache-transfer count was collected.

Returned-JIT share at sixty workers is 95.463% for retained compact and 94.924%
for old256, with whole-session batch ratios near 128. Lower delegation cannot
explain that remaining gap uniformly. The later prefetch trial's +1.53%/+1.36%
median changes versus `76af844` are inconclusive with overlapping ranges;
`044e351` reverts its hints while its archive branch and results remain intact.
No performance regression is claimed for the rejected trial.

All 24 ordinary timings, eight unscored profiles and twelve separate placement
sessions passed and drained. Each new source passed 16 basic/affected drivers,
11/13-case runner programs and three live probes. Independent source/archive
and arithmetic/profile audits passed. Sequential source blocks and three
repetitions support descriptive comparisons, not a uniform speedup or statistical
significance. The pipe gap remains; this round does not cover the full workload
grid. The report retains exact ranges, execution mixes and profile limitations.

## Earlier mutex waiter-record pipe comparison

The [packed-state investigation](../bench/results/10.176.26.71/bench/mutex32-packed-20261019/README.md)
compares fresh baseline `cb0e8e6` (runtime `372be89`), candidate `35718f5`
(runtime `c2f0d9c`) and old-256-byte `0324e60` source blocks in the same 64-vCPU
VM. Each point has three 2000 ms plain repetitions with collector 63. All 18
timings returned JIT bodies and drained; six separate profiles are unscored.
Whole-run median Mops/s is:

| Workers | Old 256-byte | Previous 32-byte | Then-current 32-byte | Then-current / previous | Then-current / old |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 6.922 | 4.498 | 5.370 | 1.194× | 0.776× |
| 60 | 5.387 | 3.456 | 4.171 | 1.207× | 0.774× |

The candidate removes two shared count RMWs per published request and replaces
owner-only phase CAS loops with release stores. Exact waiter records use existing
node padding; ownership, admission, queue, frame and ACK rules remain. This is a
combined change, so the timings do not isolate the two mechanisms' contributions.
Measured returned-JIT shares are slightly lower than the previous 32-byte arm,
while throughput rises. At sixty workers all three arms have median whole-session
ratios near 128 bodies per combiner. Neither higher delegation nor larger batches
explains the improvement there.

Polling dominates the flat profiles. They do not measure CAS retries or cache-line
transfer costs, and the old256 eight-worker profile changes the execution mix.
The remaining gap is explicit; no parity or full-grid claim is made. The report
retains ranges, exact placement evidence and phase-accounting limitations.
Independent archive/source and arithmetic/profile audits passed.

## Earlier embedded 32-byte mutex pipe comparison

The [embedded-state report](../bench/results/10.176.26.71/bench/mutex32-embedded-20261019/README.md)
compares fresh `372be89` and old-256-byte `0324e60` source blocks in the same
64-vCPU recovery VM, collector 63, with three 2000 ms repetitions per point.
All twelve sessions returned JIT bodies, passed the oracles and drained.
Whole-run median Mops/s is:

| Workers | Old 256-byte | Embedded 32-byte | New / old |
| ---: | ---: | ---: | ---: |
| 8 | 6.994 | 4.147 | 0.593× |
| 60 | 5.409 | 3.408 | 0.630× |

At sixty workers measured returned-JIT share increases from 94.899% to 96.187%,
while whole-session bodies per combiner remain about 127.5–127.9. Lower delegation
therefore cannot explain that throughput deficit. Packed gate/count/tail traffic
is a source-backed hypothesis; this round contains no profiling or isolated
ablation to attribute the cost. The report retains ranges and phase-accounting
limits. Source/archive and independent arithmetic audits passed. Prior rounds
are not pooled; no fresh pre-change 32-byte arm or full grid was run.

## Taskname and xattr comparison

Revision `05876a4` keeps original `strcmp` and `strscpy_pad` calls inside one
generated invocation. The selected KD mutex protocol is unchanged; these two
workloads use spin delegation. Neither this revision nor its `88bb5a4` baseline
performs helper-code checks, string scans or runtime destination checks.

The [completed comparison](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
contains **567 correct, drained sessions**: read-only taskname and xattr tail
queries with 16/128 attributes and 64-byte values, all three backends, the
standard 21 worker counts and three repetitions. Of 189 KD sessions, 168 returned
generated bodies and 21 had no generated entry; none entered without completing
a body. Mixed repetitions at three workers for taskname and xattr n16 remain
separate, leaving 61 complete comparable points.

At 60 workers, median whole-run throughput in Mops/s is:

| Workload | Fresh Linux Native | Fresh TCLock | Current KD | KD / Native | KD / TCLock |
| --- | ---: | ---: | ---: | ---: | ---: |
| Taskname, read-only | 3.860 | 5.008 | 4.521 | 1.171× | 0.903× |
| Xattr tail, 16 attributes, 64-byte values | 2.182 | 2.412 | 2.368 | 1.085× | 0.982× |
| Xattr tail, 128 attributes, 64-byte values | 0.562 | 0.600 | 0.573 | 1.020× | 0.956× |

These KD rates are **1.838×, 4.901× and 6.528×** the corresponding
[`88bb5a4` rates](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/README.md)
of 2.460, 0.483 and 0.088 Mops/s. At 60 workers, returned-body shares are
99.89%, 99.90% and 99.89%. KD exceeds fresh Native there but remains below
TCLock by approximately 9.7%, 1.8% and 4.4%.

The improvement is not uniform. Across 61 compatible points, 55 meet or exceed
both the old KD whole-run and 300 ms peak medians. Six have a lower whole-run
rate: taskname at four/five workers, xattr n16 at one/two, and xattr n128 at
one/three. The largest is taskname at five workers, 3.529 versus 3.662 Mops/s,
about 3.65% lower. Fresh-control gaps remain larger: taskname at six workers
reaches only 0.433× Native and 0.704× TCLock. Across the same 61 current points,
KD meets both observed throughput criteria at 16 versus Native and one versus
TCLock. These are descriptive comparisons, not statistical significance tests.
The [full-grid tables](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/tables.md),
[current CSV](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/current-full-grid.csv)
and [historical KD CSV](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/historical-kd-full-grid.csv)
retain status groups, repetition ranges, peak rates and exclusions.

Separate function profiles identified repeated dispatcher work in the old path:
1/16/128 source-pin lookups and 7/37/261 frame validations per returned
taskname/xattr-n16/xattr-n128 body. All six new KD diagnostic cases returned
bodies with zero measured calls to those routines. The original helper now runs
directly; its source references are retained when immutable code is published.
Register saves, actual source CALL return words, quotas, exact ownership and
completion checks remain. TCLock runs native instructions on the waiter's stack
and avoids this translated helper bridge. The profiles explain removed work;
their instrumented timings are not benchmark scores or an isolated cost estimate.

[Focused checks](VALIDATION.md#taskname-and-xattr-helper-validation), loaded-image
verification and a separate 129-comparison quota control passed. The latter
correctly returns the unfinished suffix to the original waiter and is unscored.
The earlier 20% taskname mutation control was correct but returned no delegated
bodies; mutation delegation and full live-task/procfs integration remain
unaccepted. The checked-helper `c79d84f` round, prior dispatcher round, screens
and profiles retain separate source identities and are never pooled.

## Compact mutex reference traffic, ba98937

The [reference-traffic investigation](../bench/results/10.176.26.71/bench/mutex32-traffic-20261019/README.md)
compares fresh `e999008` and old 256-byte `0324e60` controls with fetch-add
`113b317`, rejected cached-index `cd49d65`, and final inline-pin `ba98937`.
All 120 plain timings and ten separate pipe profiles passed and drained.
Median whole-run Mops/s; each pair is eight / 60 workers:

| Workload | Previous 32 B | Final 32 B | Old 256 B |
| --- | ---: | ---: | ---: |
| c01, post64 | 5.520 / 4.332 | 5.405 / 4.378 | 7.055 / 4.972 |
| c08, post64 | 4.899 / 4.054 | 5.070 / 3.964 | 4.792 / 3.649 |
| SEEK_SET, n16 | 4.261 / 3.871 | 4.115 / 3.814 | 4.968 / 3.995 |
| Pipebytes, n16 | 5.276 / 3.666 | 5.442 / 3.735 | 6.943 / 5.411 |

Pipe improves by 3.2%/1.9% against the previous compact implementation, while
remaining 21.6%/31.0% below the old inline object. Other changes are mixed:
c01 −2.1%/+1.1%, seek −3.4%/−1.5%, and c08 +3.5%/−2.2%. Three repetitions
in sequential source blocks support descriptive comparisons, not significance
or a general speedup. All API sessions returned generated bodies; synthetic
counters witness entry only. Exact ranges and peak windows remain in the report.

The new pin performs one fetch-add instead of a CAS retry loop; inlined helpers
and common guards reduce instruction work without dropping exact references.
The fixed direct-index table, 32-byte/8-byte public geometry and queue/frame/ACK
protocol remain intact, with no registry locks or RCU. Rejected pins remain
counted across publication and retirement. The cached-index experiment was
reverted after mixed results and a c08 regression.

Pipe's measured returned-body share rises from 74.63%/85.87% to 87.88%/87.33%,
but the old object's shares are still 96.83%/94.98%. Flat profiles locate
reference-path work but do not count coherence traffic or isolate its total
cost. Sampling substantially changes execution mix in some runs, especially
the eight-worker baseline; profile timings remain unscored. The report separates
code evidence, admission counters and timing inferences.

## Compact mutex direct index and reference transfer, e999008

The [matched comparison](../bench/results/10.176.26.71/bench/mutex32-index-20261019/README.md)
keeps four source versions separate: the 256-byte inline baseline `0324e60`,
RCU baseline `f0bd68d`, first direct-index candidate `44f8eb6`, and reference
transfer candidate `e999008`. The recorded RCU baseline has the same production
source as `fcbacbe`; its fresh measurements retain the actual `f0bd68d` label.
All 96 plain timings and eight unscored c01 profiles passed and drained, with
c01/c08/SEEK_SET n16/pipebytes n16 at eight and 60 workers and three repetitions.
Both candidates passed basic plus affected VM checks. Independent archive,
source and statistics audits passed, including all 104 reconstructed peak windows.

Median whole-run Mops/s; each pair is eight / 60 workers:

| Workload | 256 B inline | 32 B RCU | 32 B direct index | 32 B index + transfer |
| --- | ---: | ---: | ---: | ---: |
| c01, post64 | 6.987 / 4.998 | 5.321 / 4.141 | 5.760 / 4.238 | 5.685 / 4.234 |
| c08, post64 | 4.762 / 3.591 | 5.002 / 3.870 | 4.914 / 3.985 | 4.926 / 3.984 |
| SEEK_SET, n16 | 4.816 / 3.987 | 4.022 / 3.774 | 4.069 / 3.792 | 4.148 / 3.760 |
| Pipebytes, n16 | 7.020 / 5.394 | 4.993 / 3.470 | 4.977 / 3.631 | 5.361 / 3.716 |

Relative to RCU, the final version changes c01 by +6.8%/+2.2%, seek by
+3.1%/−0.4%, pipe by +7.4%/+7.1%, and c08 by −1.5%/+2.9%. Relative to
the old inline object, c01 remains 18.6%/15.3% slower, seek 13.9%/5.7%
slower, and pipe 23.6%/31.1% slower; c08 is 3.4%/11.0% faster. Transfer
versus the first index candidate changes pipe by +7.7%/+2.4%, with c01
−1.3%/−0.1%, seek +1.9%/−0.8%, and c08 +0.2%/−0.02%. All API sessions
returned JIT bodies, so these four fresh arms have no JIT/NO_JIT category change.
Whole-run medians are primary; observed repetition ranges and 300 ms peaks remain
separate in the report. Synthetic counters witness JIT entry with completion
instrumentation disabled. API sessions count
matching returns separately; a NORMAL image is only publication evidence.

The direct-index provider preallocates 65,536 slots (16 MiB), with no auxiliary
registry lock or RCU. Collisions and reserved slots use local KD exclusion
before queue publication. `e999008` transfers the immediate gate acquisition's
invocation reference to ownership and borrows that existing owner reference
during synchronous unlock. Queued/frame/ACK lifetimes, task-routing RCU,
physical exclusion, admission and the native 32-byte/8-byte object geometry
remain intact. The storage cost and fallback cases remain part of the tradeoff.

The four versions ran in sequential blocks. Three repetitions and observed
ranges do not eliminate drift or establish statistical significance, and ratios
of medians are not paired estimates. This is a bounded KD comparison without
fresh Native/TCLock controls; historical full-grid results are not pooled.

## Compact mutex registry optimization, fcbacbe

The [matched investigation](../bench/results/10.176.26.71/bench/mutex32-opt-20261019/README.md)
compares the initial compact implementation, its immediate 256-byte parent and
the optimized compact version on the same VM boot. All 63 plain timing sessions
and six separate profiles completed and drained. Registry spinlock serialization
in contention hints, reference updates and frame retirement explains much of
the regression: queued-spinlock samples fall from 44.616%/19.255% at 8/60 workers
to zero samples/0.0055% after RCU lookup and atomic references. Flat samples are
supporting evidence, not exact wall-time attribution.

Median whole-run Mops/s from three repeats:

| Workload | Workers | Initial 32 B | Old 256 B | Optimized 32 B |
| --- | ---: | ---: | ---: | ---: |
| c01, post64 | 8 / 60 | 1.991 / 2.997 | 7.206 / 4.970 | 5.610 / 4.085 |
| c08, post64 | 8 / 60 | 1.317 / 1.521 | 4.495 / 3.639 | 4.863 / 3.843 |
| SEEK_SET, n16 | 8 / 60 | 1.111 / 1.106 | 4.636 / 4.004 | 3.990 / 3.808 |

The optimized rates are 1.36–3.69× the initial compact rates for those cases.
c01 still trails the old object by 22.15%/17.81%, and seek by 13.92%/4.89%.
Pipebytes n16 at eight workers is a material tradeoff: initial compact stays
local at 18.138 Mops/s; old and optimized versions return JIT bodies at 6.843
and 4.986. Removing probe serialization changes admission observations under
the unchanged policy. Those different execution classes are not like-for-like
registry speed comparisons; optimized pipe also remains 27.14% below old JIT.

Synthetic c01/c08 measure entry witnesses, with completion instrumentation off;
API workloads separately measure returned bodies. Delegated shares also change
within those categories, so remaining gaps do not isolate reference overhead.
Exact counts, classes,
ranges, profiles, functional checks and retained failures are in the report.
This is a bounded comparison of three sequential source blocks with no fresh
Native/TCLock controls; it does not replace historical full-grid measurements.
The public mutex remains 32 bytes aligned to 8, with automatic auxiliary
retirement and the same physical/delegation protocol.

## Compact mutex screen, 7713897

The [focused comparison](../bench/results/10.176.26.71/bench/mutex32-screen-20261019/README.md)
completed 108 valid, drained sessions for c01, c08 and write-only RCUHT, using
fresh Native/TCLock/KD controls at 1/8/32/60 workers and three repetitions.
KD's whole-run median is roughly level with Native at one worker, but below
both controls at every tested contended point. At 60 workers:

| Workload | Native | TCLock | Compact KD | KD / Native | KD / TCLock |
| --- | ---: | ---: | ---: | ---: | ---: |
| c01, post64 | 3.983 | 3.128 | 2.674 | 0.671× | 0.855× |
| c08, post64 | 2.921 | 2.730 | 1.423 | 0.487× | 0.521× |
| RCUHT | 1.695 | 1.746 | 0.986 | 0.582× | 0.565× |

These are median whole-run Mops/s. The c01 best warmed KD peak is 4.956 Mops/s,
above Native's 4.747, despite the lower whole-run median. The report retains
both metrics and all observed ranges, including substantial variation. CPU pins
and the host's `ondemand` policy stayed unchanged, while actual VM memory had
some pages on the opposite NUMA node despite binding. No matched old-layout
KD arm was run; this screen cannot isolate the cost of shrinking the object.

The [additional API screen](../bench/results/10.176.26.71/bench/mutex32-api-screen-20261019/README.md)
completed 144 valid, drained sessions at the same four worker counts and three
repetitions, using fresh controls. At 60 workers, median whole-run Mops/s is:

| Workload | Native | TCLock | Compact KD | KD execution |
| --- | ---: | ---: | ---: | --- |
| pipebytes n16 | 1.844 | 2.423 | 4.735 | NO_JIT, local KD |
| pipecap n16 | 1.824 | 2.559 | 5.686 | NO_JIT, local KD |
| seek SET | 1.382 | 2.464 | 1.095 | Returned JIT |
| seek END | 1.335 | 2.520 | 1.157 | Returned JIT |

Pipe KD medians exceed both controls at every tested contended point, while
seek KD medians trail both. All 30 KD NO_JIT sessions have complete evidence
that CPU admission never reached its first contention heat check; all 18
contended seek sessions returned JIT bodies. One returned-JIT seek session
lacks a final per-CPU diagnostic row, retained as incomplete diagnostic evidence
without affecting its checked measurement and drain. Native's 60-worker
repeat spreads reach 72.7%; all ranges and separate peaks are retained.
These API results are not pooled with synthetic or historical measurements,
and do not isolate the cost of the compact layout.

## Historical 256-byte mutex result, d2a2304

At 60 workers, median whole-run throughput in Mops/s is:

| Workload | Linux Native | TCLock | Compatibility baseline | KD-only d2a2304 | Change vs baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| c01, post64 | 4.276 | 3.107 | 4.856 | 4.838 | −0.39% |
| api-pipebytes-query-n16 | 1.821 | 2.447 | 5.371 | 5.130 | −4.48% |

The main matrix has 41 of 42 points within 5% of baseline or faster. Pipebytes
at 44 workers was 7% slower. Nine additional fresh pairs at that point have
medians 5.175/5.193 Mops/s (baseline/current, +0.35%), but the median paired change
is −2.50% and six of nine pairs are slower. Keep this follow-up separate from
the original matrix; it does not erase the original regression or its variability.

The 252 KD measurements comprise 225 JIT-positive sessions and 27 NO_JIT controls.
The report retains every sample, whole-run and warmed-peak statistics, spread,
source identities, failed intermediate trials and independent archive replay.
The initial consolidation preserved the accepted runtime bytes. The subsequent
[feature reintegration](history/feature-reintegration-20261018.md) adds ordinary
rwsem and restores snapshots/tooling while retaining the accepted mutex source.
Its focused validation is recorded separately in [VALIDATION](VALIDATION.md).
The later rwsem comparison below measures the new writer interface separately;
it does not rerun or replace the accepted mutex comparison.

## Accepted rwsem implementation, c21345b

The [optimization report](../bench/results/10.176.26.71/bench/rwsem-optimization-20261018/README.md)
records all **756 correct, drained Native/KD sessions**: c01/c08/RCUHT, 1%/20%
writes, the standard 21 worker counts through 60, three repetitions and post4
work (four dependent arithmetic rounds after each unlock). At 60 workers,
accepted KD median whole-run throughput is **5.10–7.42×**
the initial KD rwsem and **1.546–2.352×** contemporary Native. Low-count
regressions remain; this is not an improvement at every configuration.

Separate waiting queues now serve callers waiting for permission to enter and
writers waiting for existing readers to finish. Frequently written fields occupy
different cachelines, reducing interference between CPU caches. Before sleeping,
callers poll: they repeatedly check whether they can proceed, for up to 16,384
checks, stopping earlier if the scheduler needs the CPU. Ordinary writers also
read the admission state before the authoritative atomic compare-and-exchange
that reserves it. The budget is accepted tuning for this captured platform, not
a universal optimum or a fixed time bound. Existing readers still finish before
a writer publishes a pinned delegation request. The
[design](design/rwsem_implementation.md) explains
the ordering and the object-size tradeoff (384 to 512 bytes). The accepted KD
mutex protocol, heat policy and wrapper ABI remain unchanged.

The before/final full grids have source-content IDs `03e379fc02be5ab7` and
`96940efc0a925d7f` respectively (canonical manifest hash prefixes, not Git IDs).
They share the captured `6.1.159-kdclobber2` kernel, 64-vCPU topology, worker
placement and collector 63. The initial `485729f` grid, fresh baseline screen,
later baseline-repeat screen and candidate screens remain separate runs.

At 60 workers, median whole-run throughput in Mops/s is:

| Workload | Writes | Linux Native | Accepted KD rwsem | KD / Native | KD / initial KD |
| --- | ---: | ---: | ---: | ---: | ---: |
| c01 | 1% | 3.561 | 7.900 | 2.219× | 7.416× |
| c01 | 20% | 1.421 | 2.197 | 1.546× | 5.458× |
| c08 | 1% | 3.299 | 7.758 | 2.352× | 7.250× |
| c08 | 20% | 1.412 | 2.183 | 1.546× | 5.495× |
| RCUHT | 1% | 3.262 | 7.312 | 2.242× | 6.927× |
| RCUHT | 20% | 0.873 | 2.047 | 2.344× | 5.100× |

For each comparison, both the median whole-run rate and the best eligible
post-warmup window must be at least the reference rates to count as a pass.
Across 126 points, KD meets both observed median-whole and best-peak criteria
at **110 points versus the initial KD**, with 12 failures and four split-status
comparisons. Against contemporary Native there are **117 passes, six failures
and three split-status comparisons**. At 20% writes/two workers, c01 and c08
retain substantial whole-run regressions versus the initial KD: **0.286× and
0.276×** respectively, approximately **71–72% slower**. These regressions remain
part of the accepted implementation's documented performance. The six Native
misses are all three 20%/one-worker points, c08/1%/two workers, and c01/c08 at
20%/36 workers. The report retains
all remaining differences and repetition ranges; these descriptive thresholds
are not significance tests.

The 378 KD timed sessions include **155 with returned JIT bodies and 223
NO_JIT controls**, with **7,275,620 matching entries and completions**. Final
c01/20% at five, six and seven workers splits execution statuses; the initial
c08/20%/16-worker point also splits. All planned sessions completed correctly.
A split point lacks one homogeneous three-repetition group; it was not skipped.
All six 60-worker points are homogeneous: 1% writes has zero JIT, while 20%
writes has returned JIT in every repetition. The high-count improvement therefore
cannot be attributed solely to delegation.

The separate **270-session spinning-rwlock reference** completed correctly and
drained: Native/TCLock/KD, the same three payloads and two mixes, and
1/8/32/36/60 workers with three repetitions. KD meets both observed criteria at
29/30 points against Native and 28/30 against TCLock. Its misses are c08/20%/one
worker against both and RCUHT/1%/60 workers against TCLock. TCLock's stack-based
delegation share is unmeasured. This port has no sleeping TCLock rwsem; these
spinning measurements are not rwsem parity or evidence of sleeping/cancellation/
downgrade support. The KD rwlock algorithm was not changed.

Focused screens preserve an unresolved first-repetition Native reduction in
both baseline and selected runs. Governor-policy equality, sampled frequencies
and inactive tracing do not isolate its cause; no samples were normalized away.
Separate baseline/final diagnostic profiles each completed six sessions with
tracing restored. For c01/20%/60 workers, KD median hits/op changed from
2.0460 to 0.000819 for `prepare_to_wait_event`, 2.0314 to 0.000810 for
`autoremove_wake_function`, 1.1602 to 0.001123 for `schedule`, and 9.6844 to
0.014329 for `_raw_spin_lock_irqsave`. Baseline profile sessions had no returned
JIT and final sessions did, so these observations do not isolate each change.
Profiles include background activity, are excluded from throughput scoring, and
overlapping function counts/times are not exclusive CPU costs.

Independent offline arithmetic replay passed for all **2,118 timed sessions**:
the initial/final grids (756 each), seven separate 48-session screens (336)
and the 270-session spinning reference. It recomputed protected effects, JIT
deltas, whole-run rates, eligible peaks and comparison groups from retained
plans, records and samples. This was an evidence check, not a new kernel test.
Six captured archives passed integrity verification. Both final-grid and
final-reference manifests match all 233 reviewed runtime inputs. The
[validation receipt](../bench/results/10.176.26.71/tests/rwsem-optimization-20261018/README.md)
records focused API/JIT checks and byte-equivalence scopes: 16 selected mutex
files within 112 preserved runtime files against `d2a2304`, and 115 unchanged
provider/header/translator/daemon files against `485729f`. These scopes overlap.

## Historical rwsem writer-delegation baseline, 2026-10-18

The [initial rwsem report](../bench/results/10.176.26.71/bench/rwsem/20261018/README.md)
contains all 756 correct, drained Native/KD sessions: c01/c08/RCUHT, 1%/20% writes,
the standard 21 worker counts through 60, three repetitions and post4 work.
This is the `485729f` shared-queue implementation before bounded polling and
queue separation. Its admission phase preserves the accepted mutex protocol.
All 233 frozen runtime inputs matched its recorded checkout when measured.
The 64-vCPU VM used collector 63, recorded CPU/NUMA placement and the host's
`ondemand` governor; those receipts do not describe the later provider bytes.

At 60 workers, median whole-run throughput in Mops/s is:

| Workload | Writes | Linux Native | KD rwsem | KD / Native |
| --- | ---: | ---: | ---: | ---: |
| c01 | 1% | 3.576 | 1.065 | 0.298× |
| c01 | 20% | 1.424 | 0.403 | 0.283× |
| c08 | 1% | 3.259 | 1.070 | 0.328× |
| c08 | 20% | 1.415 | 0.397 | 0.281× |
| RCUHT | 1% | 3.270 | 1.056 | 0.323× |
| RCUHT | 20% | 0.868 | 0.401 | 0.463× |

KD meets both observed peak and median-whole criteria at 26 of 126 points and
is slower on at least one metric at 99. The remaining c08/20%/16-worker point
has all six valid measurements but split KD execution statuses, so its groups
are reported separately. No benchmark was skipped. At 60 workers KD is 54–72%
slower on median whole throughput; that captured implementation was not a high-count
performance improvement over Native for these mixes.

Only seven of 378 KD timed sessions completed JIT bodies, all c08/20% writes:
one repetition at 16 workers and all three at 36 and 40. They completed 1,752
delegated writes in total. The other 371 sessions, including all 60-worker cases,
were `NO_JIT`. The unchanged heat policy was retained; publication was not
counted as execution. Four separate writer-heavy functional checks establish
substantial returned delegation, as recorded in the
[initial validation receipt](../bench/results/10.176.26.71/tests/rwsem-delegation-20261018/README.md).
Those different mixes are not pooled into this historical performance matrix.

The report retains every repetition, spread, peak and whole-run statistics,
JIT groups, all regressions, plots, verified raw archives and source identities.
Real mmap integration and Linux rwsem fairness remain outside this comparison.

## Other lock families and earlier versions

The [2026-10-15 c01 rwlock report](../bench/results/10.176.26.71/bench/rwlock/20261015-c01/README.md)
contains 378 accepted sessions at 1%/20% writes and the same 21-count grid.
It meets its strict best-peak and median-whole criterion at 39/42 points, with
mixed JIT statuses kept separate. These are measurements of its captured source,
not a rerun of the consolidated provider.

The [all-workload report](../bench/results/10.176.26.71/bench/comparison/workloads-20261015T180603Z/README.md)
and [expanded mutex report](../bench/results/10.176.26.71/bench/comparison/mutex-expanded-20261016T040928Z/README.md)
preserve spin/rwlock/API coverage and the superseded owned-mutex implementation.
Their KD mutex numbers do not describe the selected main version. The
[legacy compatibility report](../bench/results/10.176.26.71/bench/comparison/mutex-legacy-compat-20261017T122742Z/README.md)
and [recovery report](../bench/results/10.176.26.71/bench/comparison/mutex-legacy-recovery-20261016T113518Z/README.md)
explain the path to the accepted implementation.

Use the [workload catalog](BENCHMARK_WORKLOADS.md) and [runner guide](../bench/README.md)
for future comparisons. Keep machines, topologies, post-work, source versions,
instrumentation and JIT/NO_JIT groups distinct. No lock wins every supported
configuration. Historical matrices and rejected candidates remain in the
[results index](../bench/results/README.md) and [history](history/README.md).
