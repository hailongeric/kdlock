# c01 mutex protocol study with eight post-work rounds

The user requested this independent study after changing `SC_POST_WORK_ROUNDS`
from 64 to 8. The accepted provider is `9b76719` (baseline checkout `096f1d4`),
with the user's workload edit preserved separately. Candidate source freezes
`475e1d62b05c167881c64f8993e4b1e4cd137eb1` plus that same eight-round edit.
The final caller experiment uses `722ea98`. All provider experiments are rejected
and preserved by `archive/perf/mutex-protocol-c01-20261013`; their switches are
available in that archived source, not the retained runner. The accepted provider
remains `9b76719`. No 64-round sample is pooled into this study.

The shorter outside work changes which strategy pays. Native now exceeds
baseline KD on both throughput measures at every tested higher-thread count,
including 36/48/60. A cross-NUMA observation therefore does not establish that
delegation is profitable. The experiments test bounded native epochs, exact-address
policy caching and caller capture independently before combining them.

## Fresh baseline

Recovery VM, physical CPU placement, kernel, governor and measurement rules match
the [64-round study](../20261013/README.md): host `10.176.26.71`, 64 vCPUs,
workers `0..N-1`, collector 63, host governor `ondemand`, voluntary preemption,
`nokaslr nopvspin`, kernel `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. The verified separate snapshot is
`mutex-protocol-c01-post8-20261013`. Source synchronization follows guest drain;
all builds and execution occur in the recovery VM.

Each c01 sample performs one protected increment followed by eight dependent
multiply/add rounds. Warmup remains 48,000 operations per worker, measurement
two seconds, and warmed peak uses the existing 300 ms settling exclusion and
300 ms full-cohort progress windows. Three rounds alternate backend order. KD
retains blocking waits after 4,096 polls, batch cap 1,024, NUMA selection,
admission threshold 256 and provider UBSAN disabled.

Median whole-run Mops/s, with best valid warmed peak in parentheses:

| Workers | Linux mutex | TCLock mutex | KD mutex | KD / Native, median / peak |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 64.078 (64.275) | 83.558 (84.008) | 60.109 (60.292) | 93.81% / 93.80% |
| 2 | 11.895 (12.176) | 11.612 (12.161) | 15.452 (16.454) | 129.90% / 135.14% |
| 4 | 12.512 (12.697) | 5.369 (5.559) | 6.605 (9.376) | 52.79% / 73.85% |
| 8 | 12.139 (12.815) | 3.670 (3.733) | 7.522 (7.652) | 61.97% / 59.71% |
| 16 | 10.961 (11.501) | 3.584 (3.697) | 7.374 (7.434) | 67.27% / 64.64% |
| 28 | 8.328 (8.951) | 3.184 (3.257) | 6.611 (6.827) | 79.37% / 76.27% |
| 32 | 8.691 (9.013) | 3.190 (3.362) | 6.665 (6.706) | 76.69% / 74.40% |
| 36 | 8.008 (8.628) | 3.166 (3.346) | 5.989 (6.063) | 74.79% / 70.27% |
| 48 | 6.820 (7.725) | 3.381 (3.481) | 5.926 (6.030) | 86.89% / 78.06% |
| 60 | 5.850 (6.790) | 3.198 (3.297) | 5.584 (5.686) | 95.45% / 83.75% |

[Statistics](statistics.csv) cover all 17 baseline counts; [samples](samples.csv)
retain each run, variation, worker shares, CPU cost and execution classification.
All 153 baseline samples pass source/binary/raw-peak checks, correct results,
worker progress and final drain. This baseline alone establishes no candidate
gain. Acceptance requires at least 97% on median and peak separately through 28,
and no greater than 3% loss against fresh KD at 32/36/48/60 with returned JIT
bodies. A candidate must pass the full grid and two independent fresh three-round
blocks before parity is claimed.

## What the changed workload reveals

Linux mutex combines a short owner-word acquisition with owner-aware optimistic
spinning, OSQ for ordinary spinners and sleeping as fallback. It may reacquire
before explicit handoff, which can preserve local ownership of the lock and
protected data. KD's native fallback already uses Linux optimistic spinning.
[Linux design](https://docs.kernel.org/6.1/locking/mutex-design.html),
[version-matched source](https://raw.githubusercontent.com/gregkh/linux/v6.1.159/kernel/locking/mutex.c).

Compared with the separate 64-round baseline, Native median throughput rises
23.4% at 16, 26.0% at 32, 34.6% at 36 and 52.8% at 60. KD changes by only +6.0%,
+0.3%, -0.1% and +6.3%; TCLock remains near its previous sustained-delegation
rates too. This is consistent with per-request queue/dispatch/completion work
limiting delegation while producer post-work overlaps service. These studies
were not alternated as a controlled 8-versus-64 experiment: frequency, scheduling
and acquisition phases remain confounders. No single cache event or code path
is assigned the full difference.

The one-worker result exposes a separate caller cost. Native and TCLock workload
callers have the same 61-byte, 13-instruction shape, differing only in call
targets. KD's compiled caller saves and restores five extra callee-preserved
registers even on its native fast path because its cold branch can enter a
clobber continuation. It also reads the owner before CAS, performs an inline
per-CPU entry increment and branches on the acquisition cookie. Linux itself
also checks sleep context; seeing KD's `might_resched` call does not alone explain
the gap. Altering only contended admission cannot fix a no-delegation shortfall.

KD and TCLock pay for different delegation mechanisms. KD retains task/source
lifetime, publishes queue nodes, binds and retires frames, calls translated bodies
and notifies completion while preserving original Linux owners and native peers.
The selected TCLock port switches native stack/register contexts and chains
successor execution, with pre-registered fixed-affinity participants and its own
mutex API. Producer work may overlap combiner execution, so adding every observed
instruction into a serialized latency estimate would be incorrect.

At 16 workers KD returns 99.20% JIT bodies and TCLock delegates 99.49%, yet their
rates are 7.37 and 3.58 Mops/s against Native's 10.96. Lifetime KD counters already
show roughly 836–990 successful bodies per combiner at 16 and 996–1,020 at 28–32,
including warmup. At 48/60, means are approximately 128, matching the existing
cross-node service boundary rather than the global 1,024 cap. Increasing that
global cap does not address this boundary or eliminate per-request coordination.

| Workers | Native worker CPU ns/op | TCLock worker CPU ns/op | KD worker CPU ns/op |
| ---: | ---: | ---: | ---: |
| 1 | 15.61 | 11.95 | 16.64 |
| 16 | 1,450 | 4,464 | 2,170 |
| 60 | 9,692 | 18,753 | 10,739 |

These are summed worker CPU costs per operation, including polling, not pure
lock acquisition or combiner latency. Both delegating backends record zero
parking at two workers; KD's median returned JIT share there is only 0.095%,
so its favorable result is predominantly adaptive native execution. At four,
KD's 51.9% whole-run spread and result-scheduling counts `[3, 810, 1]` show
distinct execution phases. At 60, KD records only `[357, 500, 254]` result
scheduling calls; it does not sleep on every request.

Native's median largest worker share rises from 8.04% to 11.83% at 16 between
the two studies, but falls from 5.47% to 3.11% at 60. Whole-run shares cannot
measure short ownership-reuse streaks or coherence traffic. Every worker's
progress and the full-cohort peak rule remain required. Native and TCLock each
have a slow valid one-worker round, producing 44.6% and 25.4% whole-run spread;
all rounds are retained.

## Candidate design

Every option defaults off. The 64-round report documents the frame-lifetime,
node-layout and original capture implementations; this study adds:

* An exact-address per-CPU epoch cache. A hit may select Linux native before
  source/name/task checks and shadow lookup, using the existing once-only
  admission pin. A KD decision still runs every eligibility and exact-shadow
  check. Cached identity never grants ownership, references or queue admission.
  After migration it is only a prior observation; resident shadow lifetime
  lasts until provider unload.
* Preflight independent of lazy capture. All four combinations preserve either
  the original compiler clobbers or explicit lock/unlock saves. This separates
  producer-side routing work from the additional translated stack instructions.
* Bounded cross-node native epochs. This opt-in setting removes only the remote
  locality veto. Periodic delegation probes and epoch expiry remain intact,
  and previously queued work keeps all owner, ACK and retirement obligations.

The policies never read benchmark worker count. Read-only parameters, compiled
caller policy and actual execution classification are recorded in each sample.
The runner records actual post-work source and keeps eight/64-round summaries
and Native denominators separate. Offline auditing verifies the hashed frozen
header even for older records that predate that metadata.

[Validation](validation.json) records basic and affected guest checks, four
actual compiled/JIT caller modes, cache/migration/source-closure/queue-state
fixtures, cross-node expiry tests, runner isolation tests and normal provider
builds. These checks establish their tested correctness scope; they do not
establish performance acceptance or replace live returned-body and drain checks.

## Completed screening

All ten candidate/control screens completed three alternating-order rounds at
1/2/4/16/28/32/36/48/60 workers, with fresh Native controls in each screen.
The 540 screen samples plus 153 baseline samples pass the offline source,
binary, business-result, full-cohort peak, worker-progress and drain audits.
[Coverage and frozen identities](coverage.json), [all samples](samples.csv),
[statistics](statistics.csv) and [acceptance checks](acceptance.json) retain
every round, including slow valid runs. No candidate passes the 97% requirement.
The current provider remains the baseline; these experiments do not establish
an accepted protocol optimization.

Each cell below is KD / that screen's Native, **median whole-run / best warmed
peak**, in percent. The final column lists counts failing either 97% of fresh
baseline KD or the returned-JIT requirement at 32/36/48/60. Every higher-thread
KD sample did return JIT bodies; the listed failures are throughput failures.
All epoch variants use requested native/probe periods of 128/1 ms. `cached`
adds the exact-address CPU cache; `cross` includes that cache and permits
native epochs across NUMA nodes. `lazy` and `preflight` refer to the independent
caller controls described above.

| Screen | 4 workers | 16 workers | 28 workers | Higher-thread failures |
| --- | ---: | ---: | ---: | --- |
| All options off (`control`) | 55.45 / 51.99 | 69.39 / 62.56 | 76.65 / 72.96 | None |
| Retired frame reuse, width fix (`frame-width`) | 50.67 / 49.61 | 66.55 / 63.79 | 83.45 / 73.99 | None |
| `epoch` | 72.94 / 67.02 | 91.86 / 86.28 | 91.25 / 97.86 | None |
| `epoch-cached` | 84.39 / 80.39 | 89.53 / 90.44 | 93.90 / 95.82 | None |
| `epoch-cached-preflight` | 85.84 / 92.68 | 89.53 / 89.42 | 99.25 / 96.59 | None |
| `epoch-cached-lazy` | 103.22 / 86.46 | 91.42 / 90.09 | 87.11 / 85.30 | 36 |
| `epoch-cached-preflight-lazy` | 96.51 / 90.06 | 94.12 / 89.19 | 84.09 / 82.37 | 36, 48, 60 |
| `epoch-cross` | 81.92 / 87.90 | 91.23 / 91.20 | 100.40 / 99.15 | 60 |
| `epoch-cross-lazy` | 95.39 / 88.48 | 87.47 / 86.70 | 86.00 / 83.07 | 48, 60 |
| `epoch-cross-preflight-lazy` | 96.36 / 91.01 | 99.60 / 94.75 | 86.53 / 88.37 | 48, 60 |

The candidate screens omit primary counts **3/5/6/7/8/12/20/24**, and no fresh
confirmation blocks were run. The complete baseline at these counts does not
fill candidate coverage. Each candidate already fails measured required counts,
so it is rejected rather than merely awaiting an unmeasured-count pass.
[Throughput plot](throughput.svg) provides the absolute rates; unlike the
table's paired Native denominator, higher-thread acceptance always uses the
fresh baseline KD denominator.

The strongest broad improvement comes from reducing delegation frequency.
At 16 workers, `epoch` raises KD from the baseline's 7.374 to 9.684 Mops/s
and reduces median worker CPU cost from 2,170 to 1,642 ns/op. Its median
returned-JIT share falls from 99.20% to 2.23%. The predominantly native result
supports avoiding per-request delegation overhead for this tiny body; it is
not evidence that translated execution itself became faster. It still reaches
only 91.86% of paired Native whole-run throughput and 86.28% of peak. The
all-options-off experiment stays within the higher-thread regression bounds,
so shared experimental code alone does not explain the larger losses in the
enabled variants.

Cross-node native epochs expose a workload-dependent tradeoff. `epoch-cross`
reaches 8.312 Mops/s at 28, passing both paired Native thresholds there. At 36,
it improves baseline KD by 25.20% whole-run and 35.84% peak, while reducing
worker CPU cost from 6,008 to 4,662 ns/op. At 60, however, 5.283 Mops/s is
only 94.61% of baseline KD despite a peak ratio of 108.91%. Removing the
locality veto therefore helps some cross-node cohorts without establishing a
safe default for all of them. Its median JIT share is only 2.35% at 36 and
2.70% at 60, visibly different from sustained delegation.

Two independent problems remain. Every candidate's one-worker best peak is
below 94% of Native, so the caller/fast-acquisition cost persists. Every epoch
variant also loses at two workers, reaching only 61.53–86.33% of paired Native
median throughput, whereas the all-options-off screen reaches 124.26%.
Sparse returned bodies do not imply cheap routing: admission and policy work
can still run on failed native acquisitions. The exact contribution of these
instructions, altered ownership reuse and frequency remains unmeasured by
the performance screens.

Frame reuse gives approximately 1.4–2.4% median gains over baseline KD at the
four higher counts, but no primary parity and a lower median at 16. Lazy
capture and preflight do not compose into a consistent gain: the cross-node
combination reaches 99.60% median at 16 yet only 94.75% peak and regresses at
48/60. These small or uneven effects do not justify adding their complexity
to the default protocol.

Variation and progress remain part of the result. The cached-epoch one-worker
median ratio is 57.46%, while cached/preflight/lazy reports 168.73%; their best
peak ratios are only 93.77% and 93.60%, respectively. Slow valid rounds in
different arms explain why the medians alone would mislead. They remain in
the data. Native epochs also change work distribution: at 16, individual
worker shares across `epoch` samples range from 4.34% to 15.66%, compared with
5.93–6.30% for the all-options-off screen. At 28 the cross-node epoch range is
0.52–5.10%. Every worker progresses, but aggregate gains do not establish equal
service or bounded per-worker latency.

## Limits of the epoch mechanism and next design work

The nominal 1 ms delegation probe is quantized by the frozen kernel's
`CONFIG_HZ=250`: `msecs_to_jiffies(1)` is one 4 ms tick. Phase transitions occur
when a subsequent acquisition observes expiry; they are not a timer-driven
promise of exact phase residence. The measurements typically record 15–16
native/probe transitions in two seconds, not a measured count of policy reads
or native acquisitions. The non-cross-node epoch screen records zero native
epochs and 16 remote vetoes/probes at 36/48/60, consistent with its continuing
high JIT participation there.
[Frozen policy implementation](../../../raw/bench/mutex-protocol-c01-post8-20261013/epoch-cross/source/kernel_module/lock/mutex_policy.inc),
[frozen kernel configuration](../../../raw/bench/mutex-protocol-c01-post8-20261013/epoch-cross/source/kernel_baseline/guest.config).

The exact-address cache saves lookup and eligibility work on native decisions,
but it does not cache a complete time-bounded native decision. Every admitted
contended cache hit still reads time and validates shared policy word/deadline/
word metadata; a racing transition may cause up to four attempts. These are
static control-flow observations, not measured read, cache-miss or cycle
counts. Policy metadata is separate from owner/queue state, yet can still add
coordination traffic. Cached identity never grants ownership, and a routing
change neither cancels queued work nor bypasses owner ACK or frame retirement.
[Frozen admission path](../../../raw/bench/mutex-protocol-c01-post8-20261013/epoch-cross/source/kernel_module/lock/mutex_calls.inc).

Further optimization should first make the native route cheaper, including
the one-worker caller ABI, and measure the actual policy-read cost before
adding more routing state. A CPU-local decision cached until a bounded expiry
is a separate design requiring explicit rules for migration, address identity,
source closure and renewed delegation probes. A larger delegation redesign,
such as persistent per-worker mailboxes and reusable execution context, would
need to reduce request publication, completion and frame work together while
retaining one acquisition's owner/ACK/lifetime obligations. Neither proposal
has demonstrated acceptance here; any implementation needs fresh independent
screens, the complete primary grid and two confirmation blocks.

## Separate causal diagnostics

The completed diagnostic controls comprise 12 lock-profile sessions
(Native/KD at 2/4/16/28/32/60) and 21 PMU sessions
(Native/TCLock/KD at 1/2/4/16/28/32/60), one sample per combination. They use
the frozen experimental provider with every option off and the same eight-round
workload. All 33 pass [the offline diagnostic audit](diagnostics.json): frozen
source/binary identity, explicit workload and policy metadata, raw progress and
peak reconstruction, every worker's progress, returned-body evidence, balanced
owners and final drain. All profile `missed` counters are zero; all six PMU
events report 100% running time. KD epoch/probe/veto deltas are `[0,0,0]`.
Every record is explicitly **diagnostic, not score eligible**.
An independent [archive check](diagnostics-archive.json) also matches all 2,078
regular files and 26 symlink targets in the retained `diagnostics.tar.gz` to
the extracted evidence, without following archived symlinks.

The initial profile launcher was restricted to collector CPU 63, causing
`CPU outside caller affinity` before any sample. The initial PMU launch lacked
`perf` in `PATH` and also produced no sample. Both failed preflights, commands
and logs are retained. Fresh `stage2-profile-control-retry` and
`stage2-pmu-control-retry` directories hold the successful sessions; no measured
sample was discarded. The PMU retry uses the archived verified `perf` with
SHA-256 `be41fc3678db80aa92593a72034ebd6ec4c574c2dca2523f294dff5a0667aca3`.
[Initial commands](../../../raw/bench/mutex-protocol-c01-post8-20261013/diagnostic-commands.json),
[profile preflight log](../../../raw/bench/mutex-protocol-c01-post8-20261013/stage2-profile-control.log),
[PMU preflight log](../../../raw/bench/mutex-protocol-c01-post8-20261013/stage2-pmu-control.log).

Lock probes change the balance they observe. Native's counted fast acquisitions
are about 50–61% of calls across these instrumented cohorts; its slow path can
still use optimistic spinning before sleeping. At 16 workers the KD profiler
observes 21.81% returned JIT bodies and a mean batch of 7.94, compared with
99.20% JIT and lifetime batch means of hundreds in the uninstrumented baseline.
At 60 the instrumented JIT share is 8.18% and the mean batch 6.91. These
measurements establish substantial probe perturbation, not small production
batches or a faster revised protocol. `admitted` is an admission-path result,
not a returned-body count. The 100 us owner samples do not resolve exact
acquisition streaks, ownership transfers or cacheline movements.
[Profile counts](diagnostics-profiles.csv), [batch histograms](diagnostics-histograms.csv).

The independent PMU controls retain much higher delegation at 16: 99.03% for
KD and 99.31% for TCLock. Their aggregate effective frequencies are similar,
yet TCLock spends substantially more worker CPU and cycles per completion:

| 16-worker PMU control | Worker CPU ns/op | Cycles/op | Instructions/op | Effective GHz |
| --- | ---: | ---: | ---: | ---: |
| Linux mutex | 1,929 | 5,064 | 1,094 | 2.626 |
| TCLock mutex | 4,399 | 14,351 | 1,478 | 3.259 |
| KD mutex | 2,378 | 7,785 | 2,244 | 3.270 |

This supports a difference in coordination and waiting cost between the two
delegation protocols. TCLock's smaller instruction count does not translate
into fewer cycles; these aggregate events do not distinguish serialized
handoff, dependency stalls, polling and context-switch machinery. KD also
uses more instructions and cycles than Native in this sample. At two workers,
however, KD uses more instructions than Native (230 versus 141 per completion)
but fewer cycles (522 versus 651). Instruction count alone is not an adequate
performance model. Counters include the measured client and inherited workers;
they do not isolate a combiner or individual lock acquisition.
[PMU event values and running times](diagnostics-pmu.csv),
[per-session CPU cost and execution](diagnostics-samples.csv),
[individual worker counts](diagnostics-workers.csv).

Frequency and scheduling differences limit stronger attribution. In the
one-worker PMU controls, effective GHz is 1.964 for Native, 2.102 for TCLock
and 3.543 for KD, reversing the throughput order of the uninstrumented best
peaks. At 60, the Native PMU run falls to 1.140 Mops/s and 1.866 GHz, against
5.850 Mops/s in its uninstrumented baseline median. Its summed worker CPU time
corresponds to about 21 active CPUs over the measurement wall time, versus
about 60 for both delegating controls; it records 14,959 context switches,
versus 407 for TCLock and 786 for KD. Native also reports 12.88 generic cache
misses per completion in that sample. This is a markedly different execution
regime, retained as evidence rather than used as a favorable KD denominator.
Aggregate cycles/task-clock is not a direct combiner frequency measurement,
and generic cache misses do not prove coherence transfers. No epoch-enabled
PMU comparison or direct cacheline-transfer measurement was performed.

## Final caller experiment and disposition

Checkpoint `722ea98` moves the native owner read after `might_sleep()` and
reloads it after an ordinary-ABI native preflight. All four compiled/JIT ABI
modes pass the affected fixture. Inspection of the frozen production c01 ELFs
confirms that both lazy modes remove the unconditional RBX spill and its
epilogue reloads. The compiler emits the intended current-task loads; this is
an observed code-generation change, not an assumed compiler effect.
[Disassembly and ELF hashes](../../../raw/bench/mutex-protocol-c01-post8-20261013/late-owner-codegen.txt).

Four new screens retain three paired Native/KD rounds at one and four workers,
adding 48 samples to the 693 above. KD Mops/s are median whole-run / best peak:

| Late-owner mode | 1 worker | 1-worker peak / Native | 4 workers |
| --- | ---: | ---: | ---: |
| Original capture | 60.046 / 60.270 | 93.76% | 6.807 / 6.846 |
| Lazy capture | 59.468 / 59.699 | 92.92% | 9.207 / 9.335 |
| Preflight | 59.613 / 59.789 | 93.03% | 6.131 / 6.488 |
| Preflight and lazy capture | 60.131 / 60.299 | 93.79% | 6.286 / 7.652 |

All four fail the measured primary gates. Removing the spill does not remove
the native-path gap; code shape, owner/cookie handling and admission work remain.
The four-worker improvement in the lazy screen is insufficient for acceptance,
and differing admission phases prevent assigning that entire gain to the spill.
No higher-thread confirmation is justified by these failed primary screens.

The final independent audit covers **741 scored samples** in this eight-round
study, separate from 537 scored samples in the 64-round study. All 33 diagnostic
samples remain unscored. Every scored sample has correct results, worker progress,
validated warmed peaks and complete drain. The requested full parity is **not
achieved**. All rejected protocol source is retained at `722ea98`; the accepted
provider stays at `9b76719`, with ratio default 256.

The retained code change records the actual post-work source in benchmark plans
and samples, rejects mismatched frozen headers, and separates Native references
and acceptance studies by round count. It does not change lock execution policy.
The user's eight-round header edit remains uncommitted and unchanged. Raw sources,
ELFs, generated JIT images, failures and command records remain under the matching
`raw/bench` and `raw/tests` directories; [validation](validation.json) and
[artifact hashes](artifacts.json) identify their checked scope.

After restoration, both basic unit groups and all 67 focused runner/auditor tests
pass in the recovery VM. A separate single-round 16-worker Native/TCLock/KD check
has correct results and complete drain; KD returns 14,646,557 JIT bodies. It
verifies the restored runner and provider together and is not another performance
confirmation block. Source identity, build warnings and its three raw samples
are retained in the validation receipt. All 64 vCPU pins and host governors are
rechecked; the provider, lock ABI, sleep support and owner/ACK rules are unchanged.
