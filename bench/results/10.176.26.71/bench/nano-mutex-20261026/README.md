# Fresh mutex nano comparisons — October 26, 2026

The fresh 16-cacheline/post64 mutex comparison beats both baselines at 32 and
60 workers. At 60 workers KD reaches **4.045 Mops/s: 1.526× Native and
1.849× TCLock**, with 98.21% returned writers. It remains below Native at eight,
16 and 36 workers. The one-worker gains are **NO_JIT** local execution.

The minimal one-cacheline/post4 comparison loses to Native at every contended
count despite 95–99% returned coverage, while beating TCLock at those counts.
Both tables contain only this fresh campaign's **36 timed observations**, one
round per backend/count/profile. No earlier result is pooled into a mean, median,
or a supposed second repetition.

The [Native-gap analysis](NATIVE_GAP_ANALYSIS.md) traces the per-request KD path
and derives worker CPU cost, work distribution and NUMA observations from these
same receipts. Its [24-row Native/KD table](worker-comparison.csv) adds no timing
samples.

## Workloads and measurement scope

Source: `444f68577ed56a10aa8b69da82d97de8f2081497`. Native, KD and TCLock each
receive one two-second measurement at `1 8 16 32 36 60` workers, after 48,000
warmup operations per worker. Both profiles use 100% exclusive writes, a
bulk-ioctl operation loop and public ABI2 KD mutex acquisition. Workers occupy
CPUs `0..N-1`, with collector CPU 63; the 36- and 60-worker cohorts cross the
32-CPU NUMA boundary.

| Profile | Protected operation | Outside-lock post-work |
| --- | --- | ---: |
| `mutex-locality` | Increment all 16 separately padded 64-byte counters, a 1 KiB resident payload | 64 register-only rounds |
| `mutex` | Increment a sequence and store its matching copy; two adjacent 64-bit fields in one 64-byte record | 4 register-only rounds |

Every backend within a profile executes the same protected body and post-work.
These profiles differ in both body and post-work, so their rate difference does
not isolate payload size or acquisition spacing. The existing
[selection experiment](../nano-pair-20261026/README.md) retains its separate
source identities, post4/post64 controls and negative results; it contributes
no samples to the tables here.

The guest runs `6.1.159-kdclobber2`, build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot ID
`afe3a8d8-0c07-475b-89b4-163b822484b0`. Timing remains **exploratory** under the
authorized auxiliary-QEMU-worker policy: strict qualification is failed,
endpoint checks do not establish continuous isolation, and one observation
provides no repeat-variability estimate. Rates are **whole-run Mops/s**, including
outside-lock work. Returned shares use measured completed writes as denominator.

## Resident 16-cacheline mutex, post64

[Full table, chart and exact replay audit](mutex-locality/README.md).

| Workers | Native | KD | TCLock | KD/Native | KD/TCLock | KD execution; returned writers |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 7.666410 | 13.732246 | 9.205672 | 1.791× | 1.492× | NO_JIT; 0.0000% |
| 8 | 6.493582 | 4.897096 | 2.463705 | 0.754× | 1.988× | RETURNED_JIT; 96.2069% |
| 16 | 5.937709 | 5.263772 | 2.373876 | 0.886× | 2.217× | RETURNED_JIT; 98.8611% |
| 32 | 4.333622 | 4.605936 | 2.166345 | 1.063× | 2.126× | RETURNED_JIT; 99.0497% |
| 36 | 4.412872 | 3.948346 | 2.255142 | 0.895× | 1.751× | RETURNED_JIT; 99.0683% |
| 60 | 2.650753 | 4.044701 | 2.187617 | 1.526× | 1.849× | RETURNED_JIT; 98.2075% |

KD is 6.28% above Native at 32 workers and 52.59% above Native at 60. It is
24.6%, 11.4% and 10.5% below Native at eight, 16 and 36 workers, respectively.
The 36-worker loss prevents an "all high counts win" conclusion. KD beats
TCLock at every measured count, but its one-worker gains over both baselines
have zero generated-body execution and cannot be attributed to delegation.

Repeated updates to a resident dirty working set offer an opportunity to
amortize ownership transfers under a service batch. Outside-lock work changes
arrival spacing, while compiler/register allocation and call-shell costs remain
in the measured path. High returned coverage establishes that delegated bodies
completed; it does not prove which mechanism explains the throughput ratios.
No cache, scheduler or handoff profile was captured to separate those causes.

## Minimal one-cacheline mutex, post4

[Full table, chart and exact replay audit](mutex-minimal/README.md).

| Workers | Native | KD | TCLock | KD/Native | KD/TCLock | KD execution; returned writers |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 35.466437 | 52.066191 | 57.136157 | 1.468× | 0.911× | NO_JIT; 0.0000% |
| 8 | 11.176651 | 6.233104 | 3.797674 | 0.558× | 1.641× | RETURNED_JIT; 97.6292% |
| 16 | 10.471687 | 6.356407 | 3.630754 | 0.607× | 1.751× | RETURNED_JIT; 95.2385% |
| 32 | 8.256046 | 5.888515 | 3.218492 | 0.713× | 1.830× | RETURNED_JIT; 98.8990% |
| 36 | 7.367363 | 4.852627 | 3.222843 | 0.659× | 1.506× | RETURNED_JIT; 98.1420% |
| 60 | 5.703869 | 5.011395 | 3.164498 | 0.879× | 1.584× | RETURNED_JIT; 97.3343% |

At eight workers KD is 44.2% below Native; at 60 it is still 12.1% below Native.
The one-worker 1.468× Native ratio is local NO_JIT execution, and TCLock is faster
at that count. Once contended, KD exceeds TCLock by 1.506–1.830× but remains
slower than Native, even though nearly all writes return through generated bodies.

One load and two stores provide little shared dirty data whose ownership
transfers might be amortized. Queueing, continuation capture/resumption and exact
frame/completion retirement remain part of KD's operation. That is a plausible
explanation for the minimal body's unfavorable Native comparison, not a causal
cost breakdown. The comparison reinforces that a smaller protected body and a
high returned-JIT share are insufficient to establish a favorable KD workload.
The locality profile's 32- and 60-worker wins retain their own body and post64
scope; they do not override these negative results.

## Validation and evidence

Each profile has 18 successful, drained observations: **36 measurements and
36 warmups** in total. All 72 phases passed frozen-source oracle replay and exact
accounting. Each measurement passed completion classification, and every session
passed final retirement and drain checks. Both profiles
retain the same 276-file frozen source manifest, byte-matched to commit
`444f6857`, with separate binaries and workload specifications.

No new unit suite or separate functional suite was run in this timing campaign.
The prior validation is reused through the checked source/provenance identity;
its original functional-stage and later metadata/default-check identities remain
in the [prior report](../nano-pair-20261026/README.md). Those earlier tests are
not counted as new checks or new timing observations here.

The locality oracle checks all 16 counter deltas against exact completed writes;
the minimal oracle checks both fields and unused snapshot slots. Worker affinity,
operation counts and post-work checksums are validated independently. Published
images, entry counts and returned completions remain distinct evidence. Native
must have no JIT activity; TCLock delegation is not independently classified by
KD's counters. Warmup did not record separate JIT entry/return deltas.

TCLock registration occurs outside the operation loop but inside the inherited
whole-run interval. Exact task/queue/stack drain precedes its teardown; KD keeps
exact source/frame retirement. Per-profile public directories contain tables,
charts and compact audits. Each audit's `receipts_root` points to the extracted
JSON under `raw/bench/nano-mutex-20261026/receipts/<profile>/`; raw command, host
and gzip-tar archive evidence remains under the same campaign directory.

The [final validation receipt](validation.json) combines offline and environment
audits. Final checks recorded idle state, unchanged boot/kernel and the original
73-module set, unchanged taint 12288, unchanged 276 source hashes, and no matched
fault-pattern lines in the final kernel log. These checks preserve correctness
and environment provenance; strict host timing qualification remains failed.
