# Mutex optimization study

The strongest candidate is a longer NUMA locality cohort, not an unbounded
delegation chain or removing frame validation. With boundary 768, KD throughput
was 8.41–15.95% higher in the four 36/60-worker observations. These are
exploratory single-round results; same-node results varied substantially.
The maintained defaults remain **total cap 1024, locality boundary 256**.
The new runner options preserve 768 as an explicit experiment.

All 200 timed observations are retained: 150 ordinary measurements and 50
diagnostic measurements, each with its own warmup. Four additional fixed-work
functional sessions are separate and unscored. [The campaign index](README.md)
links every workload table, chart, source identity and replay audit. No source
versions, workloads or instrumentation modes are pooled into repeated means.

## What the profiles establish

The [baseline interpretation](BASELINE_INTERPRETATION.md) combines source review
with separate counter, flat-sample and batch observations. At 16/32 workers,
KD already services roughly 1,000 returned bodies per batch. Generally short
batches therefore do not explain the minimal-body gap against Native.

Precise instruction attribution places about 80–95% of settled KD worker
sampled cycle periods in result waiting and PAUSE. Many pinned requesters wait
while one owner services the lock; this fraction is not an estimate of removable
service overhead. Active-path samples identify frame initialization and exact
owner checks/retirement as candidates. The outlined
`kd_jit_minimal_complete_allowed.part.0` helper accounts for only about
0.006–0.030% of all worker sampled periods; inlined portions are outside that
symbol. An unapplied candidate would inline its call while preserving the
predicate. It was not timed, and has weak profiling evidence for a substantial
gain.

The current ABI2 fast path already avoids several generic frame transitions
and repeated ledger validation. The remaining checks bind source OPEN,
immutable image admission, packet/ABI state, physical ownership, the exact lock
ledger and retirement. They were retained. The 32-byte mutex also places its
owner, gate and delegation tail in one cacheline in these allocations. Producer
tail exchanges and owner reads can contend on that line, but these profiles do
not measure HITM traffic or establish a per-instruction latency breakdown.

[Instrumentation sensitivity](INSTRUMENTATION_EFFECTS.md) is material: perf
changes contention, throughput and completed-work fairness, especially for
Native. Candidate decisions use separate ordinary measurements. Neither the
diagnostic rates nor a high returned-JIT share prove a speedup.

## Frame and prefetch experiments

The frame experiment initialized the unused mutex root's tag byte directly,
while generic preparation preserved spin producer tags. It retained every
owner, ledger, admission and retirement check and preserved borrowed registers
and cold routing. Frozen ELF inspection confirmed removal of the old header
read/AND/OR sequence in the constructor and its inlined copy. Frame size stayed
656 bytes, with registers at offset 40. Normalized instruction sequences changed
in exactly those two functions; local register allocation and store scheduling
also changed.

The second experiment prefetched two published successors instead of one.
It acquire-loaded only the next link, before executing the current body, and
added no access after completion, native wake or handoff. Tests covered missing
links, zero stack pointers, ordering, prohibited notification hints and a
poisoned third link.

| Experiment | Source and comparator | Measured KD changes | Disposition |
|---|---|---|---|
| Fresh-frame byte initialization | `96fc5e89` versus `b0d12ba8` | Minimal −4.05% to +2.04%; locality −24.17% to +0.46% | No consistent gain; restored baseline |
| Two-successor prefetch | `9ec2be09` versus frame candidate | Minimal −2.21% to +4.57%; locality −0.20% to +6.37% | Mixed results; restored baseline |

[Frame comparison](frame-tags-vs-control-b0/README.md) and
[prefetch comparison](prefetch-two-vs-frame-tags/README.md) retain every point,
including Native changes, worker fairness and returned-body shares. For
example, Native locality/16 fell 29.37% during the frame comparison; the KD
change cannot be attributed entirely to the candidate.

Both experiments remain reachable through
`archive/mutex-frame-tags-20261026` and
`archive/mutex-prefetch-two-20261026`. Commit `d9d2b6fa` restored only their
reviewed paths. The [frame ELF proof](../../raw/bench/mutex-profile-20261026/analysis/frame-tags/proof.json)
and its reproduction script remain in the raw evidence.

## Independent batch and NUMA trials

Commit `f61ddc1a` adds independent, bounded mutex build controls and runner
options. All three policies below use that same source. Spin's cap remains
independent; the legacy mutex runner still forwards its existing cap option.
Plans, build commands, modinfo and diagnostic receipts record the actual policy.
Defaults preserve the original service loop. The
[default ELF comparison](../../raw/bench/mutex-profile-20261026/analysis/policy-defaults/proof.json)
found no added default-path operations: only two logging line-number immediate
bytes differ from the earlier control; full binary identity is not claimed.

Whole-run KD throughput in Mops/s, one observation per cell:

| Body | Workers | Default 1024/256 | Total cap 4096/256 | Locality 1024/768 | Locality change versus default |
|---|---:|---:|---:|---:|---:|
| Minimal pair, post4 | 16 | 6.560 | 4.808 | 5.979 | −8.86% |
| Minimal pair, post4 | 32 | 5.785 | 5.807 | 5.908 | +2.11% |
| Minimal pair, post4 | 36 | 4.929 | 4.696 | 5.343 | +8.41% |
| Minimal pair, post4 | 60 | 4.904 | 4.932 | 5.595 | +14.10% |
| 16 counters, post64 | 16 | 5.002 | 5.155 | 3.269 | −34.64% |
| 16 counters, post64 | 32 | 4.610 | 4.708 | 4.895 | +6.19% |
| 16 counters, post64 | 36 | 3.768 | 3.753 | 4.369 | +15.95% |
| 16 counters, post64 | 60 | 4.100 | 4.111 | 4.486 | +9.40% |

The [4096-cap comparison](policy-cap4096-vs-policy-control/README.md) and
[768-boundary comparison](policy-numa768-vs-policy-control/README.md) show
fresh Native rates and full precision separately. In the 768 trial at 60
workers, the minimal body achieved 5.595 versus Native's 5.623 Mops/s; locality
achieved 4.486 versus 2.717 Mops/s. TCLock was not rerun in this optimization
study; its earlier nano results remain a different campaign.

Separate compiled observations confirm that the policies changed queue
behavior. These batch statistics are diagnostic, not throughput scores:

| Policy | Body | Mean bodies/batch, 16 / 36 / 60 workers | Remote returned bodies at 36 workers |
|---|---|---:|---:|
| 1024/256 | Minimal | 1015.72 / 928.38 / 255.80 | 8.473% |
| 4096/256 | Minimal | 3994.89 / 3662.73 / 255.75 | 10.340% |
| 1024/768 | Minimal | 1018.01 / 842.18 / 762.49 | 2.969% |
| 1024/256 | Locality | 1013.23 / 978.35 / 255.59 | 8.551% |
| 4096/256 | Locality | 3948.96 / 3643.47 / 255.79 | 10.464% |
| 1024/768 | Locality | 1014.19 / 892.31 / 764.34 | 3.055% |

The 4096 cap produces much longer chains at 16/36 workers, without a consistent
throughput benefit. At 36 it also allows more mixed-node service after the
small-prefix FIFO transition. At 60 the separate 256 boundary still ends
almost every batch, explaining why the larger total cap does little there.

The 768 boundary addresses two different regimes. At 36 workers, remote service
falls from about 8.5% to 3%; mean batch length actually falls, so a longer
overall chain is not the explanation. More of the bounded service interval
uses NUMA selection before the FIFO remainder. At 60 workers, locality was
already about 99.98%; the main observed change is roughly tripling the batch
length, which can amortize owner transfer. These are source-supported
mechanism explanations, not an isolated causal cost decomposition.

The eight-request handoff threshold, scan budget 64, deferred-prefix rejoin,
bounded FIFO remainder, cancellation, exact ownership and ACK/retirement
obligations remain unchanged. Longer cohorts can delay remote service; body
counts and completed-work fairness do not measure tail latency or prove
scheduler-independent starvation freedom. The single-round evidence does not
justify changing the maintained 256 default.

## Critical-section size and request spacing

The [54-point factor grid](factor-grid/README.md) tests 1, 4 and 16 padded
counters with 4, 64 and 256 post-unlock arithmetic rounds, at 16/36/60 workers
against matched Native controls. Every combination has its own table and
chart. Changing the padded-counter count changes both work and footprint; it
does not isolate memory traffic from instruction cost. The one-counter body
also differs from the two-word minimal pair.

The highest observed KD/Native ratio is 3.328× for one counter/post256/60.
KD changes only from 4.923 Mops/s at post4 to 4.892 at post256, while Native
slows substantially. This identifies a favorable arrival pattern, not a code
optimization. KD can overlap producer-side post-work with the combiner's
service; tight Native reacquisition and service order are plausible contributors.
[Completed-work fairness](factor-grid/FAIRNESS.md) provides supporting
observations: Native wins eight of nine post4 points with less equal completed
work than KD. At post256, Native is more equal than KD in eight of nine points,
yet KD wins all nine. This is not a trace of lock acquisition order or latency.
Absolute-rate charts accompany ratio charts to expose the distinction.

## Validation and retained limitations

All builds, executable tests, modules and timing ran in the recovery VM.
Source/Git work and offline archive analysis ran on 380G10. The actual recovery
snapshot and host placement were rechecked at stage boundaries. The VM stayed
on `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot
`afe3a8d8-0c07-475b-89b4-163b822484b0`. Workers use CPUs 0..N−1, with node0
0–31, node1 32–63 and collector63. Native is this modified recovery kernel,
not a pristine upstream-kernel comparison.

Validation included basic checks plus directly affected frame/ABI, queue,
native continuation, spin/rwlock layout, diagnostics and runner checks.
The final policy checks passed seven repository drivers, ten nano unittest
cases and two legacy-provider cases. Private provider builds used W=1;
ordinary timing compiled batch diagnostics out. Fixed-work functional checks,
each measured session's exact payload/worker/completion oracle, frozen replay,
source/frame retirement and provider drain all passed. No full suite was run.

Preserved failures include the initial diagnostic fixture's missing extracted
type dependency, the diagnostic module's pre-init per-CPU allocation failure,
the initial counter-size Makefile rejection, and the nonexistent spin-restore
test selector. Each was corrected and its directly affected check rerun; none
is counted as a pass or a measured point. The two failed live/build stages
performed zero warmups and zero measurements. The selector correction uses
the real restore fixture through `test_spin_wait.py`.

The [final idle receipt](../../raw/bench/mutex-profile-20261026/final-idle.stdout)
confirms no remaining project activity, the same boot/kernel, 73 loaded system
modules and unchanged taint 12288. No kernel was modified, installed or rebooted,
and no module was forcibly unloaded. Strict host timing qualification remains
failed under the authorized exploratory policy. One observation per point
provides no variance or confidence interval. The retained changes are profiling,
workload factors and explicit bounded policy controls; the frame/prefetch
candidates were not promoted as performance improvements.
