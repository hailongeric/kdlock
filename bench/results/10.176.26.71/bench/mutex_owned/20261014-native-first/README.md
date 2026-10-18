# Owned mutex native-first c01 study

No candidate meets all performance gates. The implementation is archived and
the previous provider is retained.

The complete-group audit has passed 894 samples: 264 baseline/control samples, eight 30-sample
candidate screens, two 102-sample C8 full-grid blocks, a 48-sample ABI2 default
control, two 24-sample C9/C10 default-path screens and 90 unscored PMU/lock-profile diagnostics. A separate partial lock-profile attempt
retains one completed Native sample, one owned preparation failure and 34
unattempted samples. No full performance candidate is
accepted. C8-4096 recovers high throughput but fails primary gates at 2/3/4/8
workers and returns no JIT at any count. The ABI2 default control also fails
the median-throughput regression floor at 32/60. C8-1024 fails primary gates at
3/4 and every higher-thread JIT gate in its full grid. Its earlier 1/1/18 JIT
bodies at 60 do not repeat. There are no confirmation blocks.
The final C10 default screen also fails at 32/60. The implementation is rejected for
promotion and preserved at [9a5305e](https://github.com/hailongeric/kdlock/commit/9a5305e7631247136ea89f1c8ac771afd7da3d8c),
tag `archive/perf/mutex-native-first-20261014`. The accepted tree retains its
prior implementation and concurrent cleanup; no experimental default is promoted.
Fresh finite/refill references use `d8d14a1`; candidates keep
the same 32-byte object, c01 payload, 64 post-work rounds, kernel and placement.
The [preceding study](../20261014-hybrid/README.md) remains unchanged.

## Fresh baselines and controls

Each finite/refill baseline contains three alternating-order rounds at all 17
counts. The old queued-preflight control and fresh Native/TCLock comparison each
contain 30 samples at 1/4/16/28/60. All 264 completed correctly, gave every worker
progress and drained. Source, binary, JIT and raw measurement checks passed.
The four groups share frozen source-manifest SHA256
`a8b168717df03ddb89a2bc693ff9968db3f7b91eea0d858e26e6a777273ab2d4`.

The table gives **median whole-run / best valid warmed-peak Mops/s**. Each Native
column belongs to its own alternating group; controls are never pooled.

| Workers | Native, finite group | Owned finite | Native, refill group | Owned refill |
| ---: | ---: | ---: | ---: | ---: |
| 4 | 7.973 / 8.630 | 3.158 / 3.297 | 7.940 / 8.814 | 2.909 / 2.987 |
| 16 | 8.709 / 9.384 | 2.131 / 2.908 | 8.817 / 9.249 | 3.074 / 3.393 |
| 28 | 7.154 / 7.724 | 2.000 / 2.097 | 7.358 / 7.898 | 2.631 / 2.925 |
| 60 | 3.951 / 5.196 | 1.424 / 1.641 | 3.824 / 4.620 | 1.672 / 1.737 |

At 16 workers, finite/refill median returned-JIT shares are 93.32%/99.88%, with
7,508/5,205 aggregate worker CPU ns per operation; paired Native costs are
1,827/1,803 ns. More delegation is therefore not itself evidence of lower total
cost. Minimum whole-run worker shares across those rounds are 0.012% finite and
3.994% refill. Every worker progressed, but this does not establish a general
fairness or starvation bound. All 17 counts, sample ranges, CPU costs and worker
shares are retained in [statistics.csv](statistics.csv), [samples.csv](samples.csv),
[workers.csv](workers.csv) and lossless [progress.csv.gz](progress.csv.gz).
The [throughput figure](throughput.svg) and [execution/CPU figure](execution.svg)
show the fresh finite baseline and both complete C8 budget grids with their
own Native controls. Earlier screens remain in the tables and CSV exports.
The C6 head-budget comparison has
[separate paired-control figures](budget/throughput.svg).
The C6/C7 release comparison has its own [paired-control figure](release/throughput.svg).
The C7/C8 transition comparison has [separate paired-control figures](transition/throughput.svg).
The [full-grid figures](full-grid/throughput.svg) show C8-4096 and the ABI2
default control alongside the fresh finite reference, with each Native control.

The old `c_abi_v1` queued-preflight control uses the finite queue and 4,096 shared
poll iterations. Its 4/16/28/60 whole-run medians are 7.627/2.052/1.986/1.607
Mops/s, with median JIT shares 0.020%/88.76%/88.07%/1.66%. It is a stage control,
not a new candidate or a same-policy higher-thread reference.

Native at 60 workers in that control enters a distinct valid slow regime:

| Round | Backend order | Native whole / peak Mops/s | Worker CPU equivalents | Largest worker share |
| ---: | --- | ---: | ---: | ---: |
| 0 | Native, KD | 3.875 / 4.964 | 56.28 | 4.08% |
| 1 | KD, Native | 0.509 / 0.518 | 22.15 | 1.92% |
| 2 | Native, KD | 0.497 / 0.506 | 23.70 | 1.92% |

The low rate persists into a round where Native runs first. The slow samples have
less aggregate worker CPU activity and a more even operation distribution, while
all workers progress. These observations distinguish the regime from a simple
fixed throughput penalty; they do not identify whether scheduling, owner reuse,
sleeping or frequency caused it. No PMU or scheduler probe was active. The low
samples remain in every statistic: Native's median is 0.509 Mops/s but its best
valid warmed peak remains 4.964 Mops/s. A whole-run ratio alone would therefore
give a misleading account of this comparison.

Fresh TCLock context is audited separately and never enters owned acceptance:

| Workers | Native, TCLock group | TCLock | TCLock median delegated share |
| ---: | ---: | ---: | ---: |
| 4 | 10.360 / 10.561 | 3.446 / 3.808 | 37.54% |
| 16 | 8.692 / 9.320 | 3.616 / 3.718 | 99.63% |
| 28 | 7.475 / 7.884 | 3.157 / 3.265 | 97.57% |
| 60 | 3.864 / 4.591 | 3.166 / 3.229 | 98.88% |

TCLock's measured bodies per batch are about two at four workers and
1,016–1,023 at 16/28/60; median worker CPU costs at those latter counts are
4,425/8,867/18,938 ns per operation. These show substantial amortization once its
batch stays populated, with remaining costs above Native. Its layout differs
from the 32-byte Native/owned object; the audit checks matching lock/data
cacheline alignment and protected-data placement, not equal private structure
geometry. Native's four-worker median rises to 10.360 Mops/s in this group, so
cross-group Native drift must accompany any KD/TCLock interpretation. See
[TCLock statistics](tclock-statistics.csv), [samples](tclock-samples.csv),
[workers](tclock-workers.csv), [batches](tclock-batches.csv) and
[progress](tclock-progress.csv.gz).

The [reference receipt](references.json) independently verifies archive SHA256
`4c0e97e71cbcd6286278fd424a1438e9bf41cb5c0dc46d97af15d3b372835550`, all 10,158
regular extracted files (108,047,342 bytes), 1,100 directories and 234 archived
symlink target strings. Workspace symlinks are deliberately not materialized;
audited JIT and frozen source files are regular files. [Coverage](coverage.json)
and [acceptance](acceptance.json) retain explicit roles: 204 baseline samples,
30 old-preflight control samples, 540 candidate/compatibility-screen samples
and zero confirmations. The separate
TCLock audit contributes another 30 context samples.

## WAITERS-only screen

This screen changes the old queued-preflight flag veto to permit WAITERS-only
spinning, retaining HANDOFF/PICKUP refusal and the 4,096 shared polling budget.
The measured source manifests differ only in `owned_mutex/core.c`, its frozen
provider-build copy and the associated provider manifest. Planned controls are
identical. The checkpoint is `5dd159ded2d5765d1a4250e13f2df41a2e7c0ca3`
(`archive/perf/mutex-waiters-only-20261014`); the captured manifests independently
establish which bytes were measured.

| Workers | Mask whole / peak Mops/s | Whole change vs old preflight | Peak change vs old preflight | Paired Native whole change | Mask median JIT share |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 11.091 / 13.908 | −19.92% | +0.03% | +0.04% | 0% |
| 4 | 8.045 / 8.278 | +5.47% | +4.34% | −0.01% | 0.011% |
| 16 | 6.398 / 8.358 | +211.80% | +212.45% | −3.78% | 1.83% |
| 28 | 1.618 / 3.488 | −18.52% | +39.96% | +5.51% | 17.21% |
| 60 | 0.380 / 0.382 | −76.34% | −79.68% | −7.74% | 1.58% |

At 16 workers, the lower JIT share accompanies a large improvement and a fall in
aggregate worker CPU cost from 7,402 to 2,279 ns per operation. This supports
investigating how the entry protocol chooses SELF versus delegation; it does not
prove a particular cache-transfer or owner-reuse mechanism. The mask's result is
still only 76.28% of paired Native whole-run throughput and 91.18% of its peak.
At four workers the whole-run ratio reaches 98.37%, while the peak ratio is only
83.79%. Each metric remains an independent gate.

The 28-worker result worsens in the whole-run measure while improving its best
window, and 60 workers fails the higher-thread floor: whole/peak ratios are
26.72%/23.30% of the fresh finite baseline, despite returned JIT bodies in all
three rounds. Mask KD uses only 4.80–5.00 worker CPU equivalents at 60 workers;
its own Native control again changes from a fast first round to two slow rounds.
The observations are consistent with materially different execution/scheduling
regimes, but the screen contains no probes that establish their cause.

One-worker mask rounds also vary: KD whole rates are 9.00/11.09/13.85 Mops/s and
Native rates are 7.67/13.85/13.88, with about one worker CPU equivalent throughout.
Their best peaks both approach 13.9 Mops/s. These valid samples remain included;
no frequency, ordering or policy explanation is asserted from rates alone.

All 30 samples passed raw correctness, progress and drain checks. The screen
fails at every measured count when both applicable gates are required; it also
lacks primary counts 2/3/5/6/7/8/12/20/24 and regression counts 32/36/48. No
confirmation block or default promotion follows. Exact stage ratios and Native
drift are in [comparisons.csv](comparisons.csv), while [stage1-archive.json](stage1-archive.json)
verifies the complete archive (1,659 regular files, 20,491,873 bytes and 30
symlink target strings), SHA256
`627db381deb8a93c8e9166ffc848da6f0c65a8fa400a8381782fb14e92536201`.

## ABI4, native-first and guarded-release screens

These three 30-sample finite-queue screens freeze the same C6 source manifest,
SHA256 `4c8f1335ee600f633f488c2bb8563c3e5985f62ef8ce60e79ee95a13d17aced7`.
`nf4096` changes only `owned_mutex_native_first` from `cabi`;
`guard4096` additionally changes only `owned_mutex_early_release`. ABI4 alone is
compared with the fresh finite baseline, which is an earlier source version;
that contrast does not isolate caller ABI from every common source change.
All samples are correct, progressed and drained. Values below are **median
whole-run / best valid warmed-peak Mops/s**.

| Workers | ABI4 only | ABI4 + native-first 4096 | Plus guarded release |
| ---: | ---: | ---: | ---: |
| 1 | 13.873 / 13.913 | 12.860 / 13.911 | 13.866 / 13.913 |
| 4 | 3.476 / 3.699 | 8.114 / 10.187 | 8.469 / 8.652 |
| 16 | 2.755 / 2.789 | 0.612 / 0.673 | 1.002 / 1.042 |
| 28 | 2.393 / 2.582 | 0.625 / 0.661 | 1.056 / 1.084 |
| 60 | 1.715 / 1.742 | 0.447 / 0.463 | 0.664 / 0.701 |

ABI4-only whole-run rates exceed the fresh finite baseline by 10.09%, 29.31%,
19.69% and 20.47% at 4/16/28/60. Peaks change by +12.17%, −4.11%, +23.08% and
+6.19%, so this is not an improvement in both measures everywhere. Median JIT
shares are 43.78%, 93.75%, 96.37% and 98.33%. Its 16-worker CPU cost is 5,807
ns/op versus the baseline's 7,508, with worker shares tightly grouped around
6.25%. It passes only the measured primary one-worker gate and the measured
60-worker regression gate; primary 4/16/28 remain far below Native.

Both native-first variants return **exactly zero JIT bodies in all 15 KD samples
per variant**, including 60 workers. Their classification is `KD_SELF`; publishing
a translation does not change that result. Zero returned bodies does not prove
that no DELEGATE request was published: a promoted request can receive a directed
physical GRANT or be refused before JIT execution. These scores do not count
publication or native-first PROMOTE outcomes; even a measured PROMOTE only
permits capture and is not by itself proof of publication. Native-first improves four-worker
throughput, but its 16/28/60 whole-run rates are only 22.22%/26.12%/26.06% of the
ABI4-only screen. At those counts its workers consume roughly 2.3–2.4 aggregate
CPU equivalents, compared with almost the entire cohort in ABI4-only.

Guarded release is associated with whole-run increases of 4.38%/63.75%/68.93%/
48.54% over native-first at 4/16/28/60. Peak changes are −15.06%/+54.80%/+63.98%/
+51.39%; at four workers Native's best peak also falls 16.55% between blocks.
Guarded KD costs 3,120/3,444/5,248 worker CPU ns/op at 16/28/60 and uses about
3.1–3.7 CPU equivalents. Every worker progresses; at 16 workers the observed
minimum/maximum operation shares are 5.14%/8.11%. Lower aggregate CPU cost here
does not compensate for the large whole-run throughput gap.

Native itself changes regimes between these groups. Paired median whole-run
rates must accompany the candidate comparison:

| Workers | Native with ABI4 only | Native with native-first | Native with guarded release |
| ---: | ---: | ---: | ---: |
| 4 | 7.808 | 7.867 | 7.766 |
| 16 | 8.996 | 2.608 | 3.078 |
| 28 | 7.165 | 0.933 | 0.907 |
| 60 | 4.169 | 0.517 | 0.511 |

At 16 workers, Native's native-first rounds run at 8.773/2.608/2.568 Mops/s;
guarded-release rounds run at 8.304/2.949/3.078. The order is Native→KD, KD→Native,
Native→KD, so the low rate again persists into a Native-first round. At 60 all
Native rounds in both latter blocks are slow, with roughly 21–23 worker CPU
equivalents and largest worker shares below 2%. Native's ABI4-only rounds use
roughly 54–57 CPU equivalents. The evidence establishes changed execution regimes,
not whether scheduling, parking, frequency or ownership behavior caused them.
No diagnostic probes were active in these scores.

Native-first passes both measured primary metrics only at four workers. Guarded
release passes at 1/4/28, but its 28-worker ratios of 116.38% whole and 105.03%
peak apply to the slow Native regime, not the earlier 7-Mops/s control. Guarded
release fails 16 workers at 32.56% whole and 11.07% peak, and fails 60 workers at
46.64% whole and 42.75% peak relative to fresh finite KD, with no returned JIT.
All three screens are incomplete: primary 2/3/5/6/7/8/12/20/24 and regression
32/36/48 are unmeasured. Neither confirmation nor default promotion is justified.

[stages234-archive.json](stages234-archive.json) verifies the archive's 4,230
regular files (54,473,442 bytes), 504 directories and 90 symlink target strings,
SHA256 `4e71a655c96474ebd75af68e59b9a382b6bdba21dde4f9cf6c6a3f5d8962c0d7`.
Correctness/build/JIT/FULL evidence and retained failures are separate in
[validation.json](validation.json); those results do not substitute for these
performance and higher-thread JIT gates.

## Guarded 1,024-poll screen

`guard1024` uses the same C6 source as `guard4096` and changes only the owner-head
budget from 4,096 to 1,024. All 30 samples are valid. All 15 KD samples again have
zero returned JIT bodies; possible publication followed by GRANT/refusal remains
unresolved. The lower budget does not materially change the observed 16/28/60
throughput, which limits what can be achieved by this budget adjustment alone.

| Workers | KD whole / peak Mops/s | Whole change vs guard4096 | Peak change vs guard4096 | Paired Native whole / peak Mops/s |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 13.862 / 13.915 | −0.03% | +0.01% | 13.845 / 13.900 |
| 4 | 7.864 / 10.690 | −7.15% | +23.55% | 8.404 / 9.385 |
| 16 | 1.002 / 1.012 | −0.04% | −2.88% | 3.263 / 8.553 |
| 28 | 1.059 / 1.083 | +0.30% | −0.15% | 0.926 / 1.212 |
| 60 | 0.671 / 0.701 | +1.12% | +0.01% | 0.522 / 0.538 |

At four workers KD's whole-run rates vary from 7.750 to 10.627 Mops/s across
three rounds (36.60% spread relative to the median). Its whole-run Native ratio
is 93.57%, while its best-peak ratio is 113.91%; the whole-run gate fails.
At 28 workers the opposite metric fails: whole reaches 114.33% of the slow
paired Native control, but peak reaches only 89.38%. Native's 16-worker rounds
again shift from 7.758 to 3.205/3.263 Mops/s. KD CPU costs at 16/28/60 are
3,160/3,402/4,981 ns/op, with approximately 3.1–3.6 worker CPU equivalents.
These are observations without a diagnosed transition mechanism.

Only the one-worker gate passes both measures. At 60, whole/peak are 47.16%/
42.75% of fresh finite KD and the returned-JIT requirement fails. Coverage is
the same incomplete five-count screen as the other candidates; no confirmation
or default promotion follows. [Budget throughput](budget/throughput.svg) and
[execution/CPU cost](budget/execution.svg) plot both budgets alongside their own
Native controls. [guard1024-archive.json](guard1024-archive.json) verifies 1,410
regular files (18,103,044 bytes), 168 directories and 30 symlink targets, archive
SHA256 `20d0d73e643f0b6ad42339a84db75cd17c51bb457c4c2b88bd2a6bbc19dc7625`.

## C7 leaf-unlock screen

This 30-sample screen keeps C6's ABI4, native-first 4,096, guarded-release and
finite-queue policy. Its source manifest is
`f84508d444cd49a189177840ef2d1f4661efa8c1ca472524fc52565ebfa778ef`.
The production delta is confined to the ABI4 header, entry assembly and
delegation implementation: an assembly leaf attempts the exact uncontended
owner CAS and tail-calls the existing slow release contract when needed. The
separate correctness receipt records those three files plus two affected test
files; frozen measurement manifests also include provider-build copies.

| Workers | C7 whole / peak Mops/s | Whole change vs C6 guard4096 | Peak change vs C6 guard4096 | Paired Native whole / peak Mops/s |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 13.857 / 13.910 | −0.07% | −0.02% | 13.847 / 13.902 |
| 4 | 8.637 / 9.006 | +1.98% | +4.09% | 9.453 / 9.839 |
| 16 | 1.044 / 1.058 | +4.14% | +1.54% | 3.661 / 8.441 |
| 28 | 1.063 / 1.100 | +0.65% | +1.42% | 0.954 / 1.027 |
| 60 | 0.730 / 0.761 | +9.90% | +8.46% | 0.494 / 0.527 |

These are modest observed changes between blocks, with substantial Native drift:
paired Native whole-run medians change by +21.72%/+18.92%/+5.12%/−3.34% at
4/16/28/60. No PMU or lock probes were active in this screen, and the separate
C6 SELF diagnostic cannot assign these changes to leaf-unlock instruction cost.
Native-16 again shifts from 7.723 to 3.266/3.661 Mops/s in alternating rounds.
At 60, all Native rounds remain slow at 0.491–0.515 Mops/s with 21.76–22.47
worker CPU equivalents. All valid samples remain included.

C7 returns zero JIT bodies in all 15 owned samples. Worker CPU costs at
16/28/60 are 2,731/2,881/3,801 ns/op, with approximately 2.7–3.1 active CPU
equivalents. All workers progress; the smallest/largest shares at 16 are
5.09%/8.81%. This remains `KD_SELF` execution, without proving that no DELEGATE
request was published. The entry-path regime seen in C6 persists.

Only measured primary counts 1 and 28 pass both gates; the 28-worker comparison
uses the slow Native control. At four workers C7 reaches 91.37% whole and
91.54% peak of Native; at 16 it reaches 28.51% and 12.53%. At 60, whole/peak
reach only 51.26%/46.36% of the fresh finite baseline and the returned-JIT
requirement fails. Missing counts and confirmation requirements are unchanged.
There is no policy promotion. [Release throughput](release/throughput.svg) and
[execution/CPU cost](release/execution.svg) preserve each stage's own Native
control. [validation.json](validation.json) separately audits the C7 archive,
SHA256 `2a5522e97647a09933dd00a7714255bb3c4177ac44de1c45eb5652fe24510bcf`,
its 3,012 regular files and affected correctness/JIT/FULL receipts.

## C8 optimistic-transition screens

Both C8 budgets freeze source manifest
`2790d9a2eef2fb4c49cdb74042944289842443e3eea3504c4a23e702879b3818`.
Compared with C7, the sole production change is in `owned_mutex/core.c`; two
preflight fixtures change alongside it. Native-first now uses the Linux-style
initial running-owner check and retries exact acquisition when the owner changes.
The previous version could commit to SELF on a changed snapshot or directed
flag observation before retrying acquisition. The strict stable/running-owner
predicate remains a condition for promotion after the spin budget expires;
the exact owner CAS and PICKUP checks still control acquisition. These are
source-established changes, not measured counts of which branch caused a delay.

The two 30-sample screens differ only in the owner-head budget. All 60 samples
passed source/raw correctness, worker-progress and final-drain checks.

| Workers | C8-4096 whole / peak Mops/s | Its Native control | C8-1024 whole / peak Mops/s | Its Native control |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 13.879 / 13.908 | 13.860 / 13.905 | 13.855 / 13.910 | 13.861 / 13.905 |
| 4 | 8.959 / 9.026 | 8.417 / 8.666 | 8.770 / 8.855 | 8.448 / 8.671 |
| 16 | 9.063 / 9.312 | 9.072 / 9.290 | 9.032 / 9.362 | 8.791 / 9.565 |
| 28 | 7.757 / 8.407 | 7.275 / 7.728 | 7.808 / 8.118 | 7.028 / 7.760 |
| 60 | 3.945 / 4.623 | 3.811 / 4.930 | 3.629 / 4.615 | 4.110 / 5.154 |

C8-4096 whole-run throughput at 16/28/60 is 8.68/7.30/5.41 times C7, while
its paired Native medians are also 2.48/7.63/7.71 times the C7 controls. C8 KD
uses approximately 15.9/27.2–27.6/55.6–56.1 worker CPU equivalents at these
counts, versus roughly three in C7. The earlier low-activity regime is absent
from these C8 samples. This is a substantial observed recovery following a
narrow protocol correction, but the uninstrumented screens do not separate
its direct instruction/branch cost from changes in scheduling, frequency or
ownership behavior. The valid first one-worker rounds remain slow in both
C8 blocks, and are retained.

Reducing the budget to 1,024 changes KD whole-run throughput at 4/16/28/60 by
−2.11%/−0.35%/+0.65%/−8.03%, and best peak by −1.90%/+0.53%/−3.44%/−0.17%.
Its Native whole-run controls change by +0.37%/−3.10%/−3.39%/+7.82%. Thus the
lower budget is not uniformly better. The 4,096 budget was selected for the
separate full-grid characterization reported below on its primary-screen
performance; this choice preceded the complete 1,024-budget audit. The separate
full-grid 1,024-budget qualifying screen is also reported below. Neither
full-grid block is a confirmation, and no default is promoted.

Both budgets pass whole and peak gates at measured primary counts 1/4/16/28.
At 16, C8-4096 reaches 99.90%/100.24% of Native, while C8-1024 reaches
102.74%/97.88%; the latter peak margin is small. At 60, C8-4096 reaches
277.14%/281.78% of the fresh finite baseline but returns zero JIT bodies in
all three rounds, so its higher-thread gate fails. C8-1024 reaches
254.90%/281.29% and returns 1, 1 and 18 JIT bodies (20 total) out of about 7.1–8.1 million
operations per round. Its measured 60-worker gate passes, although delegation
accounts for only 0.000012%–0.000255% of operations. The `JIT` classification
records real returned bodies; it does not imply that delegation is responsible
for the throughput. All other C8 KD samples are `KD_SELF`.

Neither screen covers primary 2/3/5/6/7/8/12/20/24 or higher-thread 32/36/48.
There are no confirmation blocks. The separate [transition throughput](transition/throughput.svg)
and [execution/CPU figures](transition/execution.svg) retain both C8 budgets,
C7 and each group's own Native controls. [validation.json](validation.json)
audits the C8 archive's 4,428 regular files, SHA256
`4375584ecf55e46eeab5763c5229390fcd3cedd9e6f59573a5279b1749478486`,
and the affected correctness and functional JIT/FULL checks. Those functional
checks use a separately declared policy and do not replace scored high-thread
returned-body evidence.

## Full C8-4096 characterization and ABI2 default control

These blocks use the same C8 source manifest as the preceding budget screens.
The 102-sample `c8_full4096` group is a separate three-round characterization
at all 17 counts, not a confirmation block and not pooled with the earlier
five-count screen. Every sample is correct, every worker progresses and all
sessions drain. All 51 owned samples return zero JIT bodies.

The complete primary grid exposes failures that the five-count screen missed.
Both metrics must reach 97% of the Native control in this same full-grid block:

| Workers | C8-4096 whole / peak Mops/s | Paired Native whole / peak Mops/s | Whole / peak ratio | Both gates |
| ---: | ---: | ---: | ---: | --- |
| 1 | 13.859 / 13.907 | 13.855 / 13.905 | 100.03% / 100.01% | Pass |
| 2 | 9.514 / 9.802 | 10.061 / 10.896 | 94.57% / 89.95% | Fail |
| 3 | 7.503 / 8.128 | 7.555 / 8.485 | 99.31% / 95.79% | Fail |
| 4 | 9.018 / 9.104 | 9.759 / 10.507 | 92.41% / 86.64% | Fail |
| 5 | 9.082 / 10.230 | 8.356 / 9.861 | 108.69% / 103.74% | Pass |
| 6 | 9.510 / 9.587 | 8.585 / 9.537 | 110.77% / 100.53% | Pass |
| 7 | 9.006 / 9.274 | 8.942 / 9.289 | 100.72% / 99.84% | Pass |
| 8 | 9.201 / 9.310 | 9.053 / 9.849 | 101.64% / 94.53% | Fail |
| 12 | 9.604 / 9.761 | 8.858 / 9.034 | 108.42% / 108.05% | Pass |
| 16 | 9.115 / 9.385 | 8.847 / 9.338 | 103.02% / 100.51% | Pass |
| 20 | 8.875 / 9.131 | 8.807 / 9.167 | 100.77% / 99.60% | Pass |
| 24 | 8.253 / 8.662 | 8.385 / 8.600 | 98.43% / 100.73% | Pass |
| 28 | 7.871 / 8.284 | 7.239 / 7.510 | 108.74% / 110.31% | Pass |

At four workers, C8's whole/peak rates are similar to the preceding screen,
but paired Native rises to 9.759/10.507 Mops/s from 8.417/8.666. The resulting
gate failure must be retained. At two workers, observed Native worker shares
range from 18.85% to 81.15%, while C8's are 49.00%–51.00%; at four they are
5.77%–49.50% Native versus 22.04%–26.32% C8. These distribution differences
are consistent with different acquisition behavior, but do not measure owner
streaks or prove that reacquisition locality causes the remaining gap.

Higher-thread throughput improves substantially over the fresh finite owned
reference, but every returned-JIT gate fails:

| Workers | C8-4096 whole / peak Mops/s | C8 / fresh finite whole / peak ratio | Returned JIT bodies per round | Regression gate |
| ---: | ---: | ---: | --- | --- |
| 32 | 7.678 / 8.087 | 298.76% / 294.60% | 0 / 0 / 0 | Fail |
| 36 | 6.309 / 7.062 | 369.19% / 407.42% | 0 / 0 / 0 | Fail |
| 48 | 4.641 / 5.653 | 348.53% / 414.58% | 0 / 0 / 0 | Fail |
| 60 | 4.153 / 4.849 | 291.75% / 295.50% | 0 / 0 / 0 | Fail |

The separate 48-sample `c8_default` block uses ABI2 capture-first, finite queue,
with native-first, guarded early release and old preflight all disabled. It
checks whether the new source preserves the existing default path. Values and
changes below compare its owned rates with the fresh finite `d8d14a1` reference;
the Native column records control drift between those two blocks.

| Workers | C8 default whole / peak Mops/s | Whole change | Peak change | Native whole change |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 13.862 / 13.900 | −0.09% | −0.16% | −0.09% |
| 4 | 3.119 / 3.282 | −1.22% | −0.47% | +5.51% |
| 16 | 2.567 / 2.934 | +20.46% | +0.87% | +1.82% |
| 28 | 2.088 / 2.581 | +4.43% | +23.07% | +2.18% |
| 32 | 2.119 / 2.703 | −17.53% | −1.52% | −0.40% |
| 36 | 1.948 / 2.265 | +13.97% | +30.65% | +1.73% |
| 48 | 1.355 / 1.399 | +1.80% | +2.56% | +2.12% |
| 60 | 1.219 / 1.741 | −14.35% | +6.09% | +0.78% |

At 32 and 60 the median whole-run gate fails while the best-peak floor passes.
All higher-thread samples return JIT bodies. The round-level evidence shows
why those two measures cannot be substituted for one another:

| Workers | Block | Round | Whole / peak Mops/s | Worker CPU equivalents | Measured JIT share | Lifetime bodies/batch |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 32 | Fresh finite | 0 | 2.594 / 2.671 | 31.91 | 96.693% | 26.69 |
| 32 | Fresh finite | 1 | 2.570 / 2.745 | 31.98 | 96.773% | 27.80 |
| 32 | Fresh finite | 2 | 2.534 / 2.720 | 31.94 | 96.734% | 25.34 |
| 32 | C8 default | 0 | 2.444 / 2.703 | 31.97 | 96.817% | 27.48 |
| 32 | C8 default | 1 | 2.099 / 2.125 | 31.96 | 96.746% | 26.77 |
| 32 | C8 default | 2 | 2.119 / 2.151 | 31.95 | 96.716% | 26.59 |
| 60 | Fresh finite | 0 | 1.607 / 1.638 | 59.87 | 98.301% | 54.94 |
| 60 | Fresh finite | 1 | 1.424 / 1.641 | 59.85 | 98.250% | 53.29 |
| 60 | Fresh finite | 2 | 1.183 / 1.207 | 59.82 | 98.274% | 52.42 |
| 60 | C8 default | 0 | 1.705 / 1.741 | 59.96 | 98.331% | 54.01 |
| 60 | C8 default | 1 | 1.211 / 1.222 | 59.88 | 98.232% | 52.62 |
| 60 | C8 default | 2 | 1.219 / 1.220 | 59.82 | 98.275% | 51.06 |

Batch observations include warmup/provider lifetime, whereas JIT shares and CPU
equivalents cover the measurement interval. CPU activity and JIT fractions stay
high in the slow rounds; batch means are broadly similar. This does not isolate
the cost of the source change. Waiting, frequency and other execution-state
differences could affect work per completed operation without reducing summed
active CPU time. Native's nearly stable median controls strengthen the need to
investigate the owned path, but do not establish a causal mechanism. No PMU or
lock probes were active. All failures and valid ranges remain in the exports;
neither the ABI4 option nor the unchanged default policy is declared accepted.

The archive is `candidate8-full-default.tar.gz`, SHA256
`642843eae5ce3f711d3e3b5614702033d5f8b938537a2d991b29859a7197c88d`.
[Full-grid throughput](full-grid/throughput.svg) and
[execution/CPU cost](full-grid/execution.svg) keep these blocks separate from
the earlier screens. The following section records the separate C8-1024 full grid.

At its recorded audit time, [c8-source-equivalence.json](c8-source-equivalence.json)
found 369 active non-document/provenance files identical to frozen C8, including
the lock/JIT runtime, active runners, workloads and current tests. Other changes
were documentation/provenance plus concurrent cleanup `fe8d758`: removal of a
retired exporter and unrelated real-API error-message text. This carries source
identity forward only for the listed matching files; it does not claim that the
entire newer commit or the unrelated report edit was compiled or tested.

## Full C8-1024 qualifying screen

This additional 102-sample block uses the same frozen C8 source and differs from
`c8_full4096` only in the owner-head budget. It is a qualifying screen, not a
confirmation or a pooled repeat of the earlier five-count screen. All source,
raw correctness, worker-progress and final-drain audits pass.

| Workers | C8-1024 whole / peak Mops/s | Paired Native whole / peak Mops/s | Whole / peak ratio | Both primary gates |
| ---: | ---: | ---: | ---: | --- |
| 1 | 13.859 / 13.908 | 13.845 / 13.902 | 100.10% / 100.05% | Pass |
| 2 | 9.733 / 10.148 | 8.890 / 8.934 | 109.48% / 113.59% | Pass |
| 3 | 7.331 / 7.644 | 8.094 / 10.912 | 90.57% / 70.05% | Fail |
| 4 | 8.451 / 9.008 | 8.478 / 10.242 | 99.68% / 87.95% | Fail |
| 5 | 9.301 / 10.886 | 8.432 / 9.581 | 110.32% / 113.61% | Pass |
| 6 | 9.469 / 9.503 | 8.851 / 9.166 | 106.98% / 103.67% | Pass |
| 7 | 9.282 / 9.646 | 8.860 / 9.150 | 104.76% / 105.42% | Pass |
| 8 | 9.291 / 9.653 | 8.939 / 9.345 | 103.94% / 103.30% | Pass |
| 12 | 9.434 / 9.692 | 8.887 / 9.166 | 106.16% / 105.73% | Pass |
| 16 | 8.970 / 9.275 | 8.897 / 9.406 | 100.81% / 98.60% | Pass |
| 20 | 8.906 / 9.287 | 8.463 / 9.169 | 105.23% / 101.29% | Pass |
| 24 | 8.445 / 8.927 | 8.259 / 8.623 | 102.26% / 103.52% | Pass |
| 28 | 7.717 / 8.158 | 7.317 / 7.954 | 105.47% / 102.56% | Pass |

At 3/4 workers, Native's round-one whole-run rates rise to 10.830/10.170
Mops/s, with best peaks of 10.912/10.242. Its other whole-run rounds are
7.539/8.094 at three workers and 7.733/8.478 at four. KD's corresponding
whole-run ranges are 7.181–7.599 and 8.282–8.980 Mops/s, with nearly the whole
cohort active in all samples. Those fast Native rounds are valid and retained;
their cause is not established by this uninstrumented block.

Relative to the complete 4,096-budget block, C8-1024 whole rates at 4/16/28/60
change by −6.29%/−1.59%/−1.96%/−1.64%; best peaks change by
−1.05%/−1.18%/−1.53%/−4.28%. Paired Native medians change by
−13.13%/+0.56%/+1.08%/+2.12%. Improved ratios at some counts therefore do not
establish a uniformly better budget. Both measures remain independently gated.

Higher-thread throughput again exceeds the fresh finite owned reference, but
every count fails the requirement for returned JIT bodies in each round:

| Workers | C8-1024 whole / peak Mops/s | C8 / fresh finite whole / peak ratio | Returned JIT bodies per round | Regression gate |
| ---: | ---: | ---: | --- | --- |
| 32 | 7.894 / 8.241 | 307.19% / 300.21% | 0 / 0 / 0 | Fail |
| 36 | 6.210 / 6.943 | 363.38% / 400.55% | 0 / 3 / 1 | Fail |
| 48 | 4.978 / 5.776 | 373.91% / 423.58% | 0 / 0 / 0 | Fail |
| 60 | 4.085 / 4.641 | 286.96% / 282.84% | 0 / 0 / 0 | Fail |

Only four JIT bodies return across the entire block, in two of 51 owned samples.
The earlier five-count screen's 20 bodies at 60 workers did not repeat here.
Thus occasional delegation proves that the path can execute, but does not
establish its repeatability, a substantial delegated fraction or a causal
throughput benefit. Zero-body samples also do not prove absence of request
publication. This full screen fails acceptance; no confirmation or default
promotion is justified.

The physical archive is `candidate8-full1024.tar.gz`, SHA256
`f327059c6444cdb554b255a25c841073ac9f3c94b6e8cb9684b1669ff436e7e9`,
containing 3,750 regular files. Both complete budget blocks appear in the main
[throughput](throughput.svg) and [execution/CPU](execution.svg) figures, and all
rounds remain separate in the CSV/progress exports.

## C9 ABI2 wrapper isolation

The completed `c9_default` group is the separately named retry
`mutex-native-first-c9-default64-retry-20261014`: 24 samples at 32/36/48/60,
with C8's ABI2 default policy unchanged. Its source manifest is
`72451d4561ea9b31707ffc7d700400599aac31064e8a16b89848f8129e73d431`.
C9 conditionally emits the ABI4-only terminal completion block only for ABI4,
keeping that code out of older generated wrapper images. This isolates an
unneeded ABI4 code-layout change from ABI2 execution; it does not itself prove
a throughput benefit. The affected generated-image checks are recorded in
[validation.json](validation.json).

| Workers | C9 whole / peak Mops/s | Whole change vs C8 default | Peak change vs C8 default | Whole / peak ratio vs fresh finite | Higher-thread gate |
| ---: | ---: | ---: | ---: | ---: | --- |
| 32 | 2.128 / 2.165 | +0.41% | −19.92% | 82.81% / 78.86% | Fail |
| 36 | 1.758 / 2.179 | −9.72% | −3.80% | 102.89% / 125.68% | Pass |
| 48 | 1.338 / 1.363 | −1.26% | −2.53% | 100.52% / 99.97% | Pass |
| 60 | 1.634 / 1.684 | +34.00% | −3.24% | 114.77% / 102.66% | Pass |

All samples pass source/raw, progress and drain checks and all owned rounds
return JIT bodies. Native whole-run controls change by +2.72%/−1.02%/+6.20%/
−3.68% versus C8 default. The 32-worker regression persists in both metrics;
the narrower wrapper alone does not restore that measured rate. At 60, median
whole-run improves while the best peak declines, so the result is not a
uniform throughput gain or an isolated instruction-cost measurement.

C9's 32-worker whole rates are 1.297/2.128/2.141 Mops/s, with 31.94–31.99
worker CPU equivalents, about 96.7%–96.9% JIT share and lifetime batch means
30.90/27.58/27.00. At 60, rates are 1.634/1.639/1.153, CPU equivalents
59.78–59.96, JIT share about 98.2%–98.3%, and batch means
54.76/54.87/49.97. The valid whole-run spreads are 39.64% and 29.75%.
These rounds stay in the report; similar activity and delegation do not isolate
frequency, waiting or code-layout effects. No primary counts or confirmation
blocks were collected in this compatibility screen.

The original output directory
[c9-default64](../../../raw/bench/mutex-native-first-20261014/extracted/bench/mutex-native-first-c9-default64-20261014)
contains only preflight artifacts: the launcher was confined to CPU 63 and
failed the worker-affinity check before loading the benchmark. A subsequent
attempt using that existing directory was rejected by the runner's fresh-output
requirement. The [affinity failure](../../../raw/bench/mutex-native-first-20261014/candidate9-console.log)
and [existing-output rejection](../../../raw/bench/mutex-native-first-20261014/candidate9-screen-console.log)
are retained; neither produced a scored
measurement. Only the fresh `-retry` directory enters the audit. The archive is
`candidate9-validation.tar.gz`, SHA256
`816ee94cf1ab0255bb00d24ad10f50e18d47f954ac0580c782fc0cf714da3a40`.
C9 does not establish default preservation or performance acceptance; C10 is
measured separately below.

## C10 final default-path cleanup

C10 constructs each execution frame with its actual entry ABI/state before
publishing frame depth, avoiding the former post-publication overwrite pair.
It also inlines the private waiter publication helper. The guarded and ordinary
publication orders remain distinct. Saved disassembly establishes these static
changes; the combined screen does not isolate either one's cycle cost.
The score and profile groups share source-manifest SHA256
`c87cef3d03a60cd40288fea2fcf337b7c7151849549850624baa840d5d143713`.

| Workers | C10 whole / peak Mops/s | Whole change vs C9 | Peak change vs C9 | Whole / peak ratio vs fresh finite | Higher-thread gate |
| ---: | ---: | ---: | ---: | ---: | --- |
| 32 | 2.009 / 2.176 | −5.58% | +0.52% | 78.19% / 79.27% | Fail |
| 36 | 2.119 / 2.209 | +20.52% | +1.41% | 124.00% / 127.45% | Pass |
| 48 | 1.344 / 1.389 | +0.41% | +1.90% | 100.93% / 101.87% | Pass |
| 60 | 1.251 / 1.741 | −23.45% | +3.35% | 87.86% / 106.09% | Fail |

All 24 scored samples are correct and drained, with returned JIT bodies in all
12 owned samples. Median JIT shares are 96.76%/97.16%/97.85%/98.27% at the four
counts. The paired Native medians change by −10.46%/+2.71%/−10.81%/+1.82%
versus C9. These controls and the valid round ranges prevent assigning the
whole-run changes solely to the source edits. C10's owned rates at 32 are
1.259/2.097/2.009 Mops/s with 31.94–31.99 worker CPU equivalents; at 60 they are
1.251/1.726/1.227 with 59.85–59.94 equivalents. Their whole-run spreads are
41.73% and 39.91%. The first Native-32 sample is also in a distinct slow regime:
0.826 Mops/s and 20.39 CPU equivalents, versus 6.441/6.547 Mops/s and about
30.46–30.48 equivalents in the other rounds. All remain included.

The 32-worker median and peak, and the 60-worker median, miss the fresh finite
floor. No primary grid or confirmations were run for this compatibility screen.
C10 therefore does not repair the default-path regression sufficiently to
promote the implementation. [Default-path figures](defaults/throughput.svg)
compare the fresh finite reference, C9 and C10 with each block's own Native.
The archive `candidate10-validation.tar.gz` has SHA256
`e3395748f6ccd0f79fefb191c1aae7abe6eff65fca491cfaf28a0f77cb3d65e2`.

[validation.json](validation.json) records the actual unit, codegen, JIT/FULL,
ACK and drain coverage separately from these failed performance gates.
[source-equivalence.json](source-equivalence.json) scopes the comparison of the
final experimental source to its frozen C10 inputs. It does not claim the whole
concurrent cleanup commit was tested: the active post-work header, study CLI and
runner inventory have separately identified differences. The retained final
checkout receipt covers the explicitly rerun checks and post64 codegen comparison.

## C10 native-first lock profiles

The completed 36-session profile replaces the failed C8 attempt with a distinct
C10 source identity; it is not a C8 rerun. It uses ABI4, native-first budget 1,024,
guarded release, finite queues and three alternating rounds at 2/4/16/28/32/60.
The diagnostic module allocates its counters dynamically, removing the reserved
per-CPU section that prevented the C8 owned profile from loading. The failed
attempt remains in [partial-profile.json](partial-profile.json).

The table aggregates counters over each count's three diagnostic rounds, from
after warmup until profile drain; returned JIT uses the timed measurement window.
`Native fast` is calls minus entries into the native slow helper; that slow helper
can spin and must not be equated to sleeping. Owned acquired/SELF/PROMOTE are
returns from the exact-target native-first helper, not all lock acquisitions.

| Workers | Native fast share | Owned helper acquired share | PROMOTE returns | SELF returns | Sampled owner-change fraction, Native / owned |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 80.15% | 99.9930% | 0 | 372 | 24.58% / 17.13% |
| 4 | 47.65% | 99.9743% | 0 | 2,797 | 51.32% / 65.08% |
| 16 | 51.34% | 99.6071% | 0 | 32,802 | 61.32% / 83.44% |
| 28 | 57.29% | 98.4029% | 0 | 74,475 | 58.80% / 84.27% |
| 32 | 54.68% | 98.0454% | 0 | 83,133 | 60.94% / 83.73% |
| 60 | 38.80% | 97.0288% | 1 | 151,754 | 72.70% / 85.08% |

Across all 18 owned sessions, the helper returns 38,231,814 ACQUIRED,
345,333 SELF and one PROMOTE, with zero missed or unknown returns. The
wait-only SELF helper count matches those SELF returns. Owned-target original
Linux lock and unlock calls are zero in every session; zero is independently
checked rather than inferred from symbols. All returned-body JIT and profiled
batch counters are zero except one body/batch in the 60-worker first round,
which also contains the single PROMOTE. PROMOTE allows capture and is not, in
general, proof of publication. The legacy `admitted` field is the contention
heat sampler's result; it is not a count of accepted delegated requests.

These observations support the hypothesis that Linux-style owner-transition
retry can satisfy this tiny critical section before delegation becomes useful.
They also explain why throughput near Native is insufficient for the required
higher-thread JIT gate. They do not establish ownership streak lengths, cacheline
transfers or fairness: owner changes are sampled at fixed time intervals,
including zero-owner observations, and probe overhead changes the execution mix.

The profiling runs' Native/owned median whole rates are 9.280/11.825,
4.348/5.631, 4.809/5.201, 3.860/5.688, 3.718/5.648 and 1.943/1.584 Mops/s.
At 60 their CPU equivalents are 56.62/55.47, differing sharply from C8 PMU's
slow, low-activity regime. Neither profiler's rates enter performance scores,
and C10's intrusive profile does not isolate the cause of C8's uninstrumented
or PMU regimes. [Lock profiles](lock-profiles.csv),
[native-first outcomes](owned-native-first-profiles.csv), [samples](samples.csv)
and [workers](workers.csv) retain all individual observations.

## SELF-routing PMU and physical-host observations

This separate 18-session diagnostic uses the same C6 source, three alternating
rounds at 4/16/60, ABI4 and guarded release, with explicit `mutex_routing=self`
and **native-first disabled**. It is not the scored native-first policy.
All sessions are correct and drained; all six perf events have 100% running time.
Owned lifetime body/batch/refusal observations and returned JIT bodies are zero.
The routing flag declares the control; zero returned JIT alone would not prove
that a different policy never published a delegation request.

Medians below are unscored. CPU equivalents use summed worker CPU time divided
by measurement wall time. Effective GHz separately uses inherited perf cycles
divided by task-clock; neither is a direct instantaneous physical clock reading.

| Workers | Backend | Whole Mops/s | Worker CPU equivalents | Effective GHz | Instructions/op | Context switches / 1,000 ops |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 4 | Native | 7.937 | 3.99 | 3.540 | 398 | 0.096 |
| 4 | Owned SELF | 7.693 | 3.98 | 3.172 | 405 | 0.117 |
| 16 | Native | 8.023 | 15.63 | 3.208 | 1,422 | 0.492 |
| 16 | Owned SELF | 8.027 | 15.71 | 3.216 | 1,432 | 0.453 |
| 60 | Native | 0.550 | 22.40 | 1.795 | 12,091 | 7.592 |
| 60 | Owned SELF | 0.649 | 19.98 | 1.774 | 10,215 | 7.150 |

The 16-worker SELF control runs at 7.806–8.563 Mops/s with about 5,905–6,460
cycles/op, close to Native in this diagnostic block. It shows that the owned
SELF core can operate in a very different regime from scored native-first's
roughly 0.6–1.0 Mops/s and 2–3 active CPU equivalents. Routing and instrumentation
both differ, so this observation motivates the entry-path investigation without
establishing scored parity or isolating one code change.

Within the Native-60 diagnostic, rates fall from 1.047 to 0.550/0.492 Mops/s while
effective GHz is 1.752/1.802/1.795. Instructions/op rise from 6,824 to
12,091/13,536 and cycles/op from 34,986 to 76,185/84,142. Thus a drop in clock
rate alone cannot explain this within-block decline. Context switches rise from
7.01 to 7.59/8.37 per 1,000 operations; generic cache misses are 13.36–16.13 per
operation. More instructions and misses per completed operation can include
waiting and scheduler work, and do not identify exact cacheline transfers or
false sharing. This block does not capture the earlier roughly 4-Mops/s Native-60
regime, so the full fast/slow distinction remains unresolved.

A separate physical-host observer ran on CPU 63 at about 1 Hz, recording all 64
CPUs' `scaling_cur_freq` and `/proc/stat`. It observed the `ondemand` governor,
800–3,600 MHz policy bounds, up-threshold 95 and 2,000 µs sampling rate. In the
conservatively aligned interior samples, median frequency across the worker
prefix is generally 3.6 GHz at four workers, 3.3 GHz at 16 and 2.0 GHz at 60.
The first four-worker Native sample is instead near 2.0 GHz and has lower perf
GHz as well. Frequency variation is therefore observed, but its throughput
contribution is not isolated. At 60, physical host CPU activity in complete
nominal measurement intervals is approximately 21–24 CPU equivalents, broadly
consistent with the reduced worker activity. Host activity also includes work
outside the guest workload.

Clock alignment is explicit rather than assumed precise. Guest realtime versus
monotonic offset changes by 1,055 ns between before/after anchors; host observer
offset spread is 3,574 ns. Causal bounds from the SSH command permit guest-to-host
realtime offset from −673.210 to +63.266 ms. Each two-second measurement contains
two nominal frequency points and one or two points inside the common interior
for every permitted offset, assuming no intervening clock jump. Sequential
per-CPU frequency reads have no individual timestamp and are not weighted by
executed operations. The exports retain nominal and conservative interior
summaries; missing complete host-CPU intervals stay blank.

[self-pmu-analysis.csv](self-pmu-analysis.csv) preserves all 18 PMU/CPU/frequency
rows, and [self-frequency-samples.csv](self-frequency-samples.csv) retains matched
per-CPU frequency observations. [self-observer.json](self-observer.json) records
input hashes, the observer command, clock bounds, limitations and the complete
archive audit: 1,044 regular files (37,626,571 bytes), 127 directories and 18
symlink targets, SHA256
`d52d501663ea7fd7b031a54a5674d26708617c30697b55e7c877e76cb943023b`.
No diagnostic rate enters candidate acceptance.

## C8 native-first PMU and retained profile failure

The completed `c8_pmu` diagnostic contains 36 sessions: three alternating rounds
at 2/4/16/28/32/60, Native versus ABI4/native-first 1,024 with guarded release
and the finite queue. It uses the same C8 source as the scored full grids.
Every session passes source/raw, progress and drain checks; all six PMU events
report 100% running time. These instrumented rates never enter acceptance.
Counters cover the measure client and inherited workers, excluding setup and
warmup. Each quantity below is computed per session and then summarized by its
median, so ratios of table medians need not reproduce per-session quantities.

| Workers | Backend | Whole Mops/s | Worker CPU equivalents | Effective GHz | Cycles/op | Instructions/op | Context switches / 1,000 ops |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | Native | 8.052 | 2.00 | 3.555 | 776 | 264 | 0.023 |
| 2 | C8 native-first | 9.597 | 2.00 | 3.556 | 745 | 266 | 0.020 |
| 4 | Native | 7.800 | 3.99 | 3.538 | 1,673 | 399 | 0.102 |
| 4 | C8 native-first | 8.687 | 3.99 | 3.549 | 1,636 | 361 | 0.086 |
| 16 | Native | 7.898 | 15.68 | 3.220 | 6,386 | 1,456 | 0.489 |
| 16 | C8 native-first | 8.314 | 15.64 | 3.225 | 6,080 | 1,377 | 0.519 |
| 28 | Native | 5.440 | 26.56 | 2.619 | 12,755 | 2,803 | 1.357 |
| 28 | C8 native-first | 5.950 | 26.49 | 2.615 | 11,637 | 2,595 | 1.389 |
| 32 | Native | 4.934 | 30.15 | 2.610 | 15,948 | 3,490 | 1.698 |
| 32 | C8 native-first | 5.441 | 30.10 | 2.606 | 14,357 | 3,182 | 1.722 |
| 60 | Native | 0.548 | 20.57 | 1.789 | 61,841 | 9,602 | 7.457 |
| 60 | C8 native-first | 0.534 | 11.09 | 1.747 | 36,544 | 6,283 | 7.582 |

At 2–32 workers, paired effective clock estimates are close, with owned cycles
and instructions per operation generally comparable to or below Native in this
diagnostic block. That observation does not isolate the ABI, OSQ transition or
release contribution; both production versions and instrumentation differ from
earlier controls. It also does not override the scored 3/4-worker failures: the
profiled/PMU execution mix and Native variation are different, and three workers
are not in this diagnostic grid.

At 60, both locks re-enter a slow regime. Native's round whole rates are
1.102/0.542/0.548 Mops/s and owned rates are 0.775/0.534/0.521, far below the
roughly 4-Mops/s scored full-grid values. Native effective GHz is
1.878/1.766/1.789, whereas instructions/op rise from 7,074 to 9,602/10,520 and
cycles/op from 36,315 to 61,841/67,134. Owned worker CPU equivalents vary from
10.11 to 17.02 and 11.09, versus roughly 56 in its scored full grid. Median
generic cache misses are 15.26/op Native and 10.94/op owned. More waiting,
scheduler work or different operation/ownership behavior can contribute to
these counters; they neither count exact cacheline transfers nor establish
frequency as the sole cause. This PMU block does not capture the fast Native-60
regime, and therefore does not resolve the full transition mechanism.

Measured owned JIT bodies are one at two workers and 6/1/2 at 60 (ten total).
Those rare executions remain distinct from a substantial delegation fraction
and from the uninstrumented acceptance evidence. [pmu.csv](pmu.csv) retains
all six events, raw values, running percentages and per-operation quantities;
[samples.csv](samples.csv) retains the per-session CPU and effective-GHz fields.

The separate C8 lock-profile attempt is incomplete. One Native two-worker
sample completed. The next owned sample completed its 96,000-operation warmup
and lifetime counters recorded 19 delegated bodies, but loading
`kd_mutex_profile.ko` failed when the reserved per-CPU arena could not allocate
264 bytes. The kernel allocation warning and stack trace are retained. No owned
timed measurement or native-first outcome profile was collected; 34 planned
samples did not run. The failed preparation subsequently drained to zero active
workers and retired its source with zero modules/frames/writers. This is an
instrumentation setup failure, not a clean completed diagnostic or evidence of
a measured mutex failure. Warmup counters are not returned-JIT evidence for a
measurement that never started.

[partial-profile.json](partial-profile.json) verifies the frozen sources and
binaries, the completed Native raw measurement/profile, the exact failed command,
the allocation receipt, cleanup and all 34 `NOT_RUN` records.
[The raw partial run](../../../raw/bench/mutex-native-first-20261014/extracted/bench/mutex-native-first-c8-profile-lock64-20261014)
remains intact and is excluded from complete-group performance assertions.
The containing archive is `candidate8-diagnostics-validation.tar.gz`, SHA256
`c6941a4b3ed438f41ee3f5928fed70d6e4ad5636ae8a52b27c010c442a531af4`.
The fixed profiler completed all 36 sessions on separately frozen C10 source;
its results above retain that distinct identity. Independent resource-probe
results and clean logs remain in [validation.json](validation.json).

## Independent stages

These controls describe the archived rejected implementation. The accepted tree
does not expose ABI4, native-first or the new early-release option.

- **WAITERS-only optimistic retry:** a separate frozen source changes the old
  queued-preflight veto while preserving HANDOFF/PICKUP exclusion. Its 4,096
  polling budget retains the old shared queue/head interpretation.
- **ABI4 caller only:** `--owned-mutex-cabi` selects `c_abi_v2`, preserving normal
  callee-saved registers through explicit capture/restore instead of broad
  caller clobbers. ABI2 remains the default and is recorded as `clobber_v1`.
- **ABI4 plus native-first:** `--owned-mutex-native-first` uses full cancelable
  OSQ entry and a separately bounded owner-head budget. The default budget is
  4,096; a 1,024-budget screen is separate. This is not the old preflight budget.
- **Guarded early release:** `--owned-mutex-early-release` independently enables
  the proposed release ordering. Existing logical early-release/FULL counters
  retain their meaning; this flag does not fabricate a physical-release count.
- **SELF diagnostics:** explicit SELF routing is unscored. Returned JIT bodies,
  physical SELF and Linux Native remain distinct execution classifications.

The runner rejects ABI4 combined with the old preflight, and native-first without
ABI4. Compiled imports, module caller/ABI metadata, live registry ABI and provider
parameter readback must agree. All source versions, flags and rejected runs remain
separate. Candidate stage names do not substitute for frozen source identity.

## Audit and acceptance

The report-only accepted tree can reproduce the audits below without restoring
experimental runtime files. To inspect or separately reproduce the rejected
implementation, use an isolated checkout of its immutable archive:

```sh
git worktree add --detach /tmp/kdlock-native-first-archive 9a5305e7631247136ea89f1c8ac771afd7da3d8c
```

Follow that checkout's VM/recovery instructions before any live execution; an
archive checkout is not a fresh performance validation. After the physical
archives are copied and extracted, run the offline audit from the repository root:

```sh
python3 bench/results/10.176.26.71/bench/mutex_owned/20261014-native-first/analyze.py \
  --raw bench/results/10.176.26.71/raw/bench/mutex-native-first-20261014/extracted \
  --baselines finite=bench/mutex-native-first-baseline-finite64-20261014 \
              refill=bench/mutex-native-first-baseline-refill64-20261014 \
  --controls preflight_control=bench/mutex-native-first-baseline-pref4096q64-20261014 \
  --runs mask=bench/mutex-native-first-mask-pref4096q64-20261014 \
         cabi=bench/mutex-native-first-cabi64-20261014 \
         nf4096=bench/mutex-native-first-nf4096-64-20261014 \
         guard4096=bench/mutex-native-first-guard4096-64-20261014 \
         guard1024=bench/mutex-native-first-guard1024-64-20261014 \
         c7_guard4096=bench/mutex-native-first-c7-guard4096-64-20261014 \
         c8_guard4096=bench/mutex-native-first-c8-guard4096-64-20261014 \
         c8_guard1024=bench/mutex-native-first-c8-guard1024-64-20261014 \
         c8_full4096=bench/mutex-native-first-c8-full4096-64-20261014 \
         c8_default=bench/mutex-native-first-c8-default64-20261014 \
         c8_full1024=bench/mutex-native-first-c8-full1024-64-20261014 \
         c9_default=bench/mutex-native-first-c9-default64-retry-20261014 \
         c10_default=bench/mutex-native-first-c10-default64-20261014 \
  --compare mask=preflight_control nf4096=cabi guard4096=nf4096 \
            guard1024=guard4096 c7_guard4096=guard4096 \
            c8_guard4096=c7_guard4096 c8_guard1024=c8_guard4096 \
            c8_full4096=c8_guard4096 c8_default=finite c8_full1024=c8_full4096 \
            c9_default=c8_default c10_default=c9_default \
  --diagnostics self_pmu=bench/mutex-native-first-self-pmu64-20261014 \
                c8_pmu=bench/mutex-native-first-c8-pmu64-20261014 \
                c10_profile=bench/mutex-native-first-c10-profile-lock64-20261014
```

Reproduce the observer/PMU correlation separately:

```sh
python3 bench/results/10.176.26.71/bench/mutex_owned/20261014-native-first/self_diagnostics.py \
  --raw bench/results/10.176.26.71/raw/bench/mutex-native-first-20261014
python3 bench/results/10.176.26.71/bench/mutex_owned/20261014-native-first/partial_diagnostic.py
```

Add scored stages with `--runs LABEL=PATH` and diagnostic stages with
`--diagnostics LABEL=PATH`. `--controls` keeps a paired stage control separate
from candidate acceptance. `--compare CHILD=PARENT` records an explicit stage
contrast; by default candidates are contrasted with their same-policy baseline.
`comparisons.csv` includes both owned ratios and the paired Native change, source
identities and every differing planned field. The optional `--baseline-source-manifest-sha256`
checks the expected frozen reference manifest. The baseline commit label is a
study declaration; hashes independently establish captured-byte consistency.
Group plans define expected counts and rounds, rather than hardcoded group sizes.

The audit requires every declared sample and checks frozen sources, binaries,
JIT artifacts, raw measurement/peak data, worker progress, parameters, kernel logs
and final drain. Historical records lacking newer flags remain visibly distinct.
The local [evidence helper](evidence.py), [policy validators](experiment_policy.py)
and [study validators](study_audit.py) retain the strict pure experimental checks
without importing a live or archived experimental runner. They use unchanged
accepted generic raw/peak validators. [Extraction provenance](audit-helper-provenance.json)
records member hashes and AST equivalence; [portability evidence](audit-portability.json)
records a successful isolated accepted-`ab2c3f4` audit with no `run`, `session` or
`mutex_study` module available. Before C10 was added, all 13 main score/progress/gate
exports regenerated byte-for-byte; the auxiliary TCLock, SELF and partial-failure
audits also passed in that isolated tree. This is an offline evidence check,
not a workload or test execution. [references.py](references.py) audits fresh
TCLock using the same raw checks plus its delegation/drain checks; its invocation
is saved in [references.json](references.json).

Primary counts are 1–8, 12, 16, 20, 24 and 28. Median whole-run throughput and
best valid warmed peak must each reach 97% of the candidate's paired Native
control. At 32, 36, 48 and 60, both must reach 97% of the fresh `d8d14a1` owned
reference with the same finite/refill policy, with returned JIT bodies in every
sample. Every worker must progress and drain. Three alternating-order rounds
form a screen; two additional fresh, source-identical full-grid blocks must each
pass independently. Declare those using `--confirmations SCREEN BLOCK1 BLOCK2`.
Incomplete screens never establish acceptance or a production default.

Warmup is 48,000 operations per worker; measurement is two seconds with the
existing 300 ms settle and full-cohort warmed-peak rules. Collector CPU 63 is
outside the worker prefix. All valid variation is retained. The exports include
per-run rates, median/min/max/spread, best observed peak, worker shares, summed
worker CPU cost, batches and separate diagnostic tables. Sampled progress is
retained losslessly in deterministic `progress.csv.gz` (mtime zero); zero sampled
deltas alone do not establish starvation. CPU cost excludes collector overhead.
[plot.py](plot.py) plots only audited, explicitly selected groups with gaps for
unmeasured counts and no interpolation.

ABI4 native-first lock profiles use the independent
`owned_native_first_profile` receipt: `acquired`, `promote`, `self`, `other` and
`missed`. The helper is probed only for the exact target object and enum results
use EAX. Unknown outcomes and missed returns must both be zero. PROMOTE permits
capture; it does not prove that a request was published or a JIT body returned.
The profiler registers the new helper instead of the old preflight probes and
still requires zero original Linux mutex calls on the owned object. These
intrusive results are exported separately and never enter performance scores.
The owned receipt separately counts calls to the original SELF entry
(`self_calls`), its slow helper (`self_slow`), and the wait-only continuation
(`self_wait`) also used by ABI4. These count helper invocations, not all physical
SELF acquisitions; fast acquisitions can bypass them. Historical receipts lack
the wait-only field. Owner sampling masks all four owned flag bits, including the
delegate flag, while Native sampling retains its original three-bit mask.

## Causal context

**Linux's advantage is a cheap local execution path plus selective waiting.**
The uncontended path uses an acquire CAS on the owner word, with a release CAS
on unlock. Contention does not immediately imply sleeping: optimistic spinning
checks that the owner is running and that rescheduling is unnecessary. Cancelable
OSQ limits competition among new spinners; the first sleeping waiter has a
separate opportunity to spin. Sleeping is the fallback. A slow-path entry
therefore cannot be counted as a park. These are source-established mechanisms. The profiles above count fast/slow
entries but do not separately measure every spinning or sleeping transition.
[Linux mutex design](https://docs.kernel.org/6.1/locking/mutex-design.html)

Without HANDOFF, Linux's contended unlock releases ownership before taking
`wait_lock`, then queues a waiter wake. A contender can acquire an ownerless
WAITERS word before that waiter obtains ownership. HANDOFF instead directs
ownership to the first waiter with PICKUP, preventing arbitrary theft. Thus
queued waiters do not imply strict acquisition alternation; wakeup and ownership
transfer are distinct. Repeated local reacquisition could preserve hot lock/data
lines and avoid some scheduling work, but that causal benefit has not been
measured here. The relevant routines are `__mutex_trylock_common`,
`mutex_optimistic_spin` and `__mutex_unlock_slowpath` in
[Linux 6.1.159 mutex.c](https://raw.githubusercontent.com/gregkh/linux/v6.1.159/kernel/locking/mutex.c).
The guest's patched source hashes and owned-port differences are recorded in
[linux-source.json](https://github.com/hailongeric/kdlock/blob/9a5305e7631247136ea89f1c8ac771afd7da3d8c/kernel_module/owned_mutex/linux-source.json);
the upstream explanation does not replace the captured kernel identity audit.

**KD-owned adds work around executing the same tiny body.** Its SELF core already
ports Linux's owner, OSQ and sleep mechanisms. Successful delegation additionally
captures a continuation, obtains a task-routing reference, reserves a preallocated
request/stack slot, publishes through the common FIFO and waits for an outcome.
The combiner validates the translation entry, creates a checked execution frame,
runs the body and retires its frame before publishing completion. Executor and
source-lifetime setup can be shared across a batch; request/frame/completion
work still occurs for each body. These operations are visible in
[delegation.c](https://github.com/hailongeric/kdlock/blob/9a5305e7631247136ea89f1c8ac771afd7da3d8c/kernel_module/owned_mutex/delegation.c),
[task-reference handling](https://github.com/hailongeric/kdlock/blob/9a5305e7631247136ea89f1c8ac771afd7da3d8c/kernel_module/kd_mutex_tasks.c) and
[frame lifecycle](https://github.com/hailongeric/kdlock/blob/9a5305e7631247136ea89f1c8ac771afd7da3d8c/kernel_module/execution/frame_lifecycle.inc).
Their presence is proven by code; their individual cycle costs are not isolated
by the throughput measurements.

Two distinctions matter when attributing that cost. Translation is prepared
before measurement; these results do not charge compilation to every operation.
A normal reduced COMPLETE result also avoids the FULL native-continuation ACK
path. FULL requires exact owner acknowledgments and later frame retirement, but
that correctness requirement must not be described as an ACK paid by every c01
operation. Likewise, preallocated slots avoid per-request heap allocation;
reservation and publication still cost work. The 32-byte public object matches
Native geometry, while the delegate packet is 320 bytes and the owned SELF waiter
is 40 bytes. Equal public geometry does not imply equal traffic: queue mutation,
register state and completion touch additional storage. Exact cacheline transfers
and false-sharing costs remain hypotheses, not results from these counters.

**TCLock amortizes a different protocol over long batches.** This selected port
switches to waiter-native stacks and can transfer directly from one waiter's
unlock to the next continuation, delaying prior-waiter completion until its stack
is safe to release. It does not use KD's translated-entry/frame protocol.
It still has queue, stack-switch, completion and parking/wakeup work; its wake
path takes a task reference when waking a parked waiter. See the local
[combiner](https://github.com/hailongeric/kdlock/blob/9a5305e7631247136ea89f1c8ac771afd7da3d8c/tclock_backend/mutex/combiner.inc),
[unlock](https://github.com/hailongeric/kdlock/blob/9a5305e7631247136ea89f1c8ac771afd7da3d8c/tclock_backend/mutex/unlock.inc),
[trampoline](https://github.com/hailongeric/kdlock/blob/9a5305e7631247136ea89f1c8ac771afd7da3d8c/tclock_backend/mutex/trampoline.inc) and
[waiter](https://github.com/hailongeric/kdlock/blob/9a5305e7631247136ea89f1c8ac771afd7da3d8c/tclock_backend/mutex/waiter.inc) implementations.
Fresh measured batches average roughly 1,016–1,023 bodies at 16/28/60, which is
direct evidence of amortization across many requests. It does not remove all
per-body coordination: TCLock remains below its own Native controls in both
throughput measures. Its 16-worker whole rate is 3.616 Mops/s versus 8.692 Native,
with 4,425 versus 1,834 worker CPU ns/op. The older comparison remains in the
[prior report](../20261013/README.md); neither TCLock data set is an owned
higher-thread acceptance reference.

**The measurements favor reducing unnecessary delegation, with limits.** At 16
workers the mask screen's JIT share falls from 88.76% to 1.83%, while whole-run
throughput rises from 2.052 to 6.398 Mops/s and worker CPU cost falls sharply.
At 28 and 60 it does not deliver a comparable benefit. High contention or a high
JIT fraction is therefore insufficient evidence that delegation is worthwhile.
The Native-60 changes in CPU activity and worker shares also show that the
comparison can enter distinct regimes. Current evidence cannot separate
owner-reuse locality, scheduler/parking behavior, frequency and protocol costs
into exact contributions. Every worker's progress is checked, but operation
shares do not establish fairness bounds, and generic cache misses would not
establish ownership-transfer counts. Intrusive probes previously changed JIT
participation, so their execution mix must stay separate from scored runs.

The opt-in implementation responds to three specific costs. The screens above
measure its tradeoffs; they do not establish the overall target:

- **Opt-in ABI4:** an ordinary C caller preserves callee-saved registers and
  captures the continuation only when the gate requests it, targeting ABI2's
  broad caller-clobber burden. See the [entry assembly](https://github.com/hailongeric/kdlock/blob/9a5305e7631247136ea89f1c8ac771afd7da3d8c/kernel_module/owned_mutex/entry.S)
  and [capture contract](https://github.com/hailongeric/kdlock/blob/9a5305e7631247136ea89f1c8ac771afd7da3d8c/include/kd_owned_mutex_cabi.h).
- **Native-first:** full cancelable OSQ precedes a separately bounded owner-head
  spin attempt. C8 retries exact acquisition on an owner transition; scheduler
  pressure or a nonrunning owner commits to SELF. Stable viable-owner budget
  exhaustion can permit delegation, subject to admission and eligibility.
  This targets premature publication and avoids a
  second initial optimistic pass on the committed SELF continuation.
- **Delegation guard and early release:** a sticky owned-only D flag protects
  delegated publication and private batches. An unguarded SELF-only release can
  clear ownership before taking `wait_lock`, while guarded work keeps exact
  directed-owner rules. This targets the release-order gap without exposing
  outstanding delegation to an ordinary wake-only release. Both mechanisms are
  in the [owned core](https://github.com/hailongeric/kdlock/blob/9a5305e7631247136ea89f1c8ac771afd7da3d8c/kernel_module/owned_mutex/core.c).

These controls were independent and opt-in within the archived experiment;
ABI2 capture-first was its default. The accepted tree retains the prior provider
and does not expose these rejected additions.
ABI4-only, native-first and guarded-release screens remain separate, including
their changed Native regimes, before any attribution or selection. A later benefit-sensitive admission policy could
compare sampled total SELF/delegation cost, including batching and CPU/scheduler
cost, instead of dispatching by thread count or contention alone. That policy is
a future design, not an implemented or measured result of this phase.
