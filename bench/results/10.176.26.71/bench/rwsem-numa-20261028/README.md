# Cross-NUMA rwsem admission analysis and optimization

Commit `acc4dbc2e28394522992469250a31da536c39fa7` makes a new KD writer phase
yield to queued readers. In this one-round comparison, it improves the
60-worker c01/20% workload by **17.8%** and c16/20% by **50.6%**. The remaining
gaps to the fresh TCLock measurements are 17.9% and 3.0%, respectively.
Reads always execute on their acquiring task; only writes may delegate.

The old **768 local delegation cutoff was already removed** before this
campaign. Both baseline and candidate use total cap 1024 and NUMA boundary
1024. This change addresses admission policy, not a further batch-limit increase.

## Workloads and results

`c01` and `c16` mean one and sixteen cachelines in the protected body.
All timed cases use post256 and one two-second measurement per point, with a
separate warmup. The normal grid here is 16, 32, 36 and 60 workers, CPU prefixes
0..N-1, collector CPU63. CPUs 0..31 belong to NUMA node 0 and 32..63 to node 1.
The split-32 control uses CPUs 0..15 and 32..47. No real-world API workload ran.

Throughput at 60 workers, in Mops/s:

| Workload | Baseline KD | Optimized KD | KD change | Fresh TCLock | KD / TCLock |
| --- | ---: | ---: | ---: | ---: | ---: |
| c01, 1% writes | 6.707 | 7.491 | +11.7% | 7.438 | 1.007 |
| c01, 20% writes | 3.164 | 3.729 | +17.8% | 4.542 | 0.821 |
| c16, 1% writes | 7.590 | 9.888 | +30.3% | 10.339 | 0.956 |
| c16, 20% writes | 2.390 | 3.600 | +50.6% | 3.713 | 0.970 |

The c01/20% results retain the smaller regressions as well as improvements:

| Placement / workers | Baseline KD | Optimized KD | KD change | Fresh TCLock |
| --- | ---: | ---: | ---: | ---: |
| Compact 16 | 5.028 | 5.222 | +3.9% | 5.437 |
| Compact 32 | 5.182 | 5.084 | -1.9% | 5.957 |
| Prefix 36, crossing NUMA | 4.038 | 4.018 | -0.5% | 4.683 |
| Prefix 60, crossing NUMA | 3.164 | 3.729 | +17.8% | 4.542 |
| Split 32, crossing NUMA | 3.162 | 3.573 | +13.0% | 4.413 |

The baseline placement control isolates worker count: moving half of the same
32 workers to node 1 reduces KD from 5.182 to 3.162 Mops/s (-39.0%), and TCLock
from 6.026 to 4.210 (-30.1%). This supports a NUMA placement effect beyond merely
adding workers. Whole implementations are compared: their naturally observed
writer execution mixes can change with placement.

**Exploratory timing, n=1.** Strict timing qualification remains failed. There
is no estimate of repeat variability or significance. Fresh TCLock rates at
60 workers differ from its baseline-phase rates by -4.0% to +1.4%; its split-32
rate rises 4.8%. Do not pool the different source versions, placements or
instrumented profile rates. [All 136 uninstrumented points](measurements.csv)
include the rejected candidates and every small regression.

## Why the baseline loses

The old KD policy admitted a new writer phase whenever the exact phase word
was zero, even with readers waiting in the optimistic spin queue (OSQ).
Queued readers then competed with another newly closed writer phase before
they could publish a successful reader count. The queue serialized admission,
but gave its queued readers no preference against a fresh writer phase.
Cross-node ownership and queue handoffs add coherence costs to this global
admission path. The placement experiment demonstrates the sensitivity; flat
CPU samples do not measure individual cache misses or assign all lost time to
cacheline transfers.

TCLock uses a combined reader/writer count and an AQS reader queue with NUMA
shuffling. Its slow reader publishes a reader bias once after queue admission
and then waits for writer bits to clear. KD uses a separate exact reader count,
phase word and physical writer gate; accepted outer reservations last through
the origin's unlock ACK. These mechanisms have different coordination costs.
They are source-level explanations, not individually measured cost shares.
Moving KD's two counters onto one cacheline actually regressed this workload.

Parking does not explain the large gap in the retained nano examples. The
previous full-grid worker receipts show c01/20% KD worker CPU time at roughly
99.95% of their active kernel intervals at 60 workers; TCLock is also near 100%.
See [CPU evidence](cpu-evidence.json). This is active waiting evidence, not an
exact park count: the CPU clock brackets the ioctl and includes small wrapper
overheads. No assertion of zero parking is made.

Flat `cpu-clock` samples provide a stronger view of the active cost. Below are
period-weighted settled `rb_worker` shares at 60 workers, excluding startup and
the first 300 ms:

| Sampled function | Baseline KD | Optimized KD |
| --- | ---: | ---: |
| `kd_mutex_osq_lock` | 79.787% | 25.571% |
| vCPU-preemption query | 11.672% | 3.910% |
| `kd_rwsem_delegate_enter` | 0.299% | 43.817% |
| `kd_down_read` | 2.736% | 11.147% |

The OSQ function serves both reader admission and the mutex gate. These are
flat instruction-pointer samples without callchains, so they cannot attribute
all OSQ time to readers. TCLock's baseline settled shares are 48.2% in AQS and
43.9% in its writer slowpath. The candidate moves much of KD's waiting out of
OSQ, but writer phase admission remains the largest sampled function. The
c01 gap is reduced, not eliminated.

## Change and execution evidence

When admission is zero, ordinary writers and new outer-writer cohorts defer
while `reader_osq` is nonempty. Positive outer cohorts still accept exact
reservations. The queue hint is rechecked after failed reservation CAS attempts;
it never authorizes access to protected data. Exact count/barrier checks,
reader drain, physical owners, ABI2, source leases, ACKs and retirement remain
unchanged. The object remains 320 bytes, with the original field offsets.

After OSQ unlink and slot release, the caller enables preemption. If the queue
is now empty, it executes a full barrier before testing and waking phase
waiters. That wake is necessary because a writer can now wait for queue
emptiness even when no writer phase changes. Failure and abort paths perform
the same empty-queue notification. Reads remain local, including the slowpath.
This preference supplies neither global starvation freedom nor bounded waiting.

The change also allows more writers to reach the gate together, increasing
actual completed delegation. At 60 workers, returned-body shares of writes
change from 0 to 58.40% for c01/20%, 0 to 21.06% for c16/1%, and 2.63% to
71.14% for c16/20%. c01/1% remains NO_JIT in both. These are measured gains
of the whole implementation with a changed writer execution mix, not an
isolated reduction of reader queue overhead.

The [limit audit](limit-evidence.json) checks the previous full-grid rwsem
archives, captured build flags, load commands, provider hashes and embedded
module information. All four rwsem profiles bind `mutex_batch=1024` and
`mutex_numa_boundary=1024`; spin also retains 1024. Rwsem uses the embedded KD
mutex policy. Thus no count-triggered handoff occurs at 768. The total 1024
cap and other terminal/deferred handoff conditions remain; delegation is not
unlimited. TCLock's own policy was not changed. The baseline c01/20% 60-worker
point had zero returned JIT writes, so increasing an already inactive batch
length could not address that example's dominant cost.

## Rejected candidates and identities

| Candidate | Source identity | Outcome |
| --- | --- | --- |
| Baseline | `35735c0d51faeafe31ca9d71049b86efadcf182e` | Includes the preceding local reader-OSQ fix and 1024/1024 defaults |
| Colocated reader/admission counters | `archive/rwsem-numa-colocated-20261028`, `61da3706e664c2dacf5d0f660897534518b4905a` | c01/20% at 60 falls to 2.969; rejected |
| Two NUMA reader OSQs | `archive/rwsem-numa-striped-20261028`, `ffda1f53b7d6682e5aec0b51286a4d565b8fe88f` | c01/20% at 60 stays 3.154; split-32 stays 3.156; rejected |
| Queued-reader preference | `acc4dbc2e28394522992469250a31da536c39fa7` | Retained; only `kernel_module/kd_rwsem.c` differs in the benchmark's frozen source set |

The [phase summary](phase-summary.json) retains every point, exact source
manifests, returned-body counts and eight separate diagnostic profiles. Its
[extractor](extract-results.py) records the calculation and verification scope;
the source-host [augmentation script](augment-results.py) verifies the Git
binding and derives the before/after comparisons.
The baseline profile's CLI commit label was transcribed incorrectly. Its
original records remain unchanged; a retained correction and exact manifest
comparison establish equality with the baseline source. The candidate profile
omits a CLI commit label; all 282 frozen files independently match `acc4dbc2`.
Neither correction is inferred from a NORMAL image or publication alone.

## Validation and retained evidence

The focused production-extraction unit fixture passed and detected all sixteen
negative mutations. Basic C checks and the existing OSQ lifetime fixture passed.
The live rwsem probe passed sleeping readers/writers, same-CPU progress,
trylocks, downgrade before publication, ten cancellation cases and final drain.
These local outer paths do not count as JIT execution; the nano measurements
retain separate entry/completion witnesses.

The four-family basic runner passed with 1,600,000 operations per family,
positive returned-JIT witnesses and final drain. Two read-only controls
(c01/c16, 60 workers) and four ordinary-writer mixed controls (c01/c16,
20% writes, 32/60 workers) passed with 10,000 operations per worker, correct
data, zero JIT entries and final drain. These fixed-iteration checks are not
performance scores.

The first final-check launcher was rejected before module activity because its
parent log was open under `/root`, which the maintained basic runner forbids.
The second attempt moved launcher logs to `/tmp` but was rejected because the
selected host reference included an auxiliary QEMU worker that had since exited
(TID 666401, CPU63). QEMU process identity, vCPU identities, placement, NUMA and
frequency settings were unchanged. Both attempts are retained. A fresh selected
reference and current capture passed the unchanged admission checks, followed
by the completed functional run.

[Evidence and validation](evidence.json) retain the exact commands, identities,
functional results and final idle health. All seven
[benchmark archives](../../raw/bench/rwsem-numa-20261028/archives.json) and four
[validation archives](../../raw/tests/rwsem-numa-20261028/archives.json) were
copied to the source host. Offline verification checked compressed hashes and
the complete inventory of 18,217 paths and 15,852 regular files:
[benchmark audit](benchmark-archive-verification.json) and
[validation audit](validation-archive-verification.json). Rejected candidates,
failed launches and two evidence-helper schema-check failures are preserved.
The final guest is idle. Retained per-session kernel logs contain no detected
faults. The global dmesg ring no longer reaches the campaign's estimated start,
so it is not claimed as complete historical coverage.

The guest is Linux `7.0.0-38-kdlock1`, boot
`15dc5977-59d3-4471-a196-d71f03f450ed`, with the verified recovery snapshot
`linux70-kdlock1-clean-20261027`. Host policy remains fixed 2 GHz with matched
vCPU pins and collector CPU63. No kernel build, installation, reboot or
real-world API workload is part of this campaign. Trusted-source translation
remains selected; this evidence does not qualify arbitrary source, mmap
execution, whole-kernel replacement, RT or lockdep integration.
