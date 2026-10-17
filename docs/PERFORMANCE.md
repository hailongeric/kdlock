# Performance status

The [2026-10-17 compatibility backport comparison](../bench/results/10.176.26.71/bench/comparison/mutex-legacy-compat-20261017T122742Z/README.md)
contains 504 accepted/drained sessions: fresh legacy and backported legacy,
Native and TCLock, c01/post64 and pipebytes n16, all 21 worker counts through 60,
three repetitions. At 60 workers, backport versus legacy median throughput is
**4.914 versus 4.820 Mops/s** for c01 (+1.94%) and **5.375 versus 5.370 Mops/s**
for pipebytes (+0.11%). Pipebytes at 44 workers regresses 9.47%; low-count
variation and all individual results remain in the report. The selected
instruction/publication changes retain the legacy lock protocol; see
[the implementation comparison](design/legacy_mutex_compatibility.md).
This evidence applies to `task/legacy-mutex-compat`, not the retained owned code.

The [fresh recovered-legacy comparison](../bench/results/10.176.26.71/bench/comparison/mutex-legacy-grid-20261016T125529Z/README.md)
accepted all 378 sessions across c01/post64 and pipebytes n16 at 1–8 workers by
one and 12–60 by four. At 60 workers, KD median throughput is **4.931 Mops/s**
for c01 (**1.19× Native, 1.60× TCLock**) and **5.379 Mops/s** for pipebytes
(**2.87× Native, 2.17× TCLock**). The pipebytes result reproduces the historical
5.330 Mops/s. C01 remains below Native median throughput at tested counts 2–40,
and below Native best peak at every multithreaded count. See the report for
all three repetitions, low-count variability and JIT/NO_JIT classifications.
This result does not include the rejected owned/adaptive implementation.

The adaptive mutex experiment is rejected. The source-verified
[legacy recovery](../bench/results/10.176.26.71/bench/comparison/mutex-legacy-recovery-20261016T113518Z/README.md) reaches **5.367 Mops/s** at 60 workers
on `api-pipebytes-query-n16`, compared with the historical **5.330 Mops/s**.
All 18 fresh Native/TCLock/KD sessions at 1 and 60 workers passed and drained.
The recovered source is on `recovery/mutex-legacy-5m330` (`6ecdd0a`); this
checkout retains the rejected experiment and its measurements below.

The archived 64-vCPU study accepted the owned ABI4/reuse-32 profile against the
97% Native target for c01/post64 at 1–8 workers. It extends the experimental
`d8d14a1` provider with Linux-style local acquisition before delegation at
implementation commit `585335b`.
That archived benchmark used `owned-v1` with the then-current independent
32-byte KD mutex object. The current 128-byte adaptive experiment has a separate
comparison below; the earlier acceptance does not transfer to its layout/policy.
Owned ABI2 capture-first, admission ratio 256, reuse allowance 0 and finite FIFO
remain the general defaults. The measured profile explicitly selects ABI4 and 32.
This narrow result does not establish general Native parity. Implementation contracts live in
[the mutex guide](design/mutex_implementation.md); correctness receipts live in
[validation](VALIDATION.md).

## Adaptive mutex comparison

The [fresh c01/pipebytes comparison](../bench/results/10.176.26.71/bench/comparison/mutex-adaptive-20261016T075356Z/README.md) contains
504 accepted and drained measurements: both workloads, four arms, three rounds
and 1–8 workers by one plus 12–60 by four. The candidate keeps ABI4 local
acquisition at low queue pressure and offers earlier delegation, successor
prefetch and bounded refill/cohorts at high pressure. It uses the new 128-byte
object; the separately frozen pre-change KD arm retains its exact 32-byte object.
Native and TCLock controls are fresh. Historical legacy results remain separate.

At 60 workers, adaptive/before median whole-run throughput is
2.972/6.894 Mops/s for c01/post64 (-56.9%) and
2.944/2.961 Mops/s for pipebytes n16 (-0.6%).
Low-count behavior is also mixed: c01 loses 17.8% at three workers and pipebytes
loses 35.7% at seven, despite remaining almost entirely local. The four-worker
pipebytes gain likewise executes more than 99.99% of operations locally.
The policy changes delegation frequency but does not establish a general gain;
`owned_mutex_adaptive` remains off by default. The report retains all worker
counts, warmed peaks, spread, CPU cost, worker/node shares and rejected pilots.
This is one descriptive block, without fresh confirmation blocks or a separate
128-byte adaptive-off performance arm. The old 32-byte acceptance below does
not cover the new layout, even with adaptation disabled. Callers and provider
must be rebuilt together.

## Expanded mutex workloads

The [2026-10-16 comparison](../bench/results/10.176.26.71/bench/comparison/mutex-expanded-20261016T040928Z/README.md)
contains 2,079 accepted, drained sessions across c01/c02/c04/c08/c16, RCUHT and
five pipe/file API variants, with three repetitions at 1–8 workers by one and
12–60 by four. It selects ABI4/reuse-32 with owned origin and NUMA policies off.
At 60 workers, KD median whole-run throughput is 1.20–2.26× Native across the
eleven variants. Both seek variants remain slower than TCLock, at 0.65–0.66×.
KD is below Native at 29 of 231 workload/worker-count points, including larger
low-worker API regressions. The report retains all samples, warmed peaks and
variation. API KD/TCLock use private objects while Native retains its embedded
kernel mutex. This descriptive comparison leaves the narrow acceptance below
and general provider defaults unchanged.

Spin, rwlock and the other API cases remain in the separate
[7,749-session all-lock round](../bench/results/10.176.26.71/bench/comparison/workloads-20261015T180603Z/README.md).
Its c01-only KD mutex coverage describes the source captured before this
expansion. The new mutex round supplies fresh controls for every variant;
samples from the two rounds are not pooled. KD xattr admission remains unsupported.

<a id="fresh-c01-164-worker-comparison"></a>

## Recorded c01 1–64-worker comparison

The [full-grid report](../bench/results/10.176.26.71/bench/mutex_owned/20261014-full-grid/README.md)
compares the unchanged ABI4/reuse-32 profile, Linux Native and TCLock at 1–8
workers in steps of one and 12–64 in steps of four. All 198 samples are correct
and drained. KD reaches 97% of Native median throughput at every count; the
three-worker warmed peak reaches only 93.86%, so this block does not establish
full-grid parity. At 60 workers, KD/Native medians are 6.913/3.599 Mops/s.
At least 99.5% of each KD sample executes through SELF, although all 63 contended
KD sessions return some JIT bodies. This historical 2026-10-14 three-round block
used the temporary 66-vCPU topology, with physical collector contention at
64 workers. It remains separate from the accepted 64-vCPU study below and supplies
no fresh confirmation blocks for full-grid acceptance.

At three workers, Native's whole-run spread is 35.88% versus KD's 5.67%; the
fastest Native sample gives one worker 85.11% of operations. Those shares are
consistent with ownership reuse helping the tiny workload, but do not measure
ownership streaks or coherence traffic. The report retains CPU cost, all worker
shares and all samples, including the slow first one-worker Native round.

<a id="active-c01-18-worker-study"></a>

## Accepted c01 1–8-worker profile

The [Linux-local study](../bench/results/10.176.26.71/bench/mutex_owned/20261014-linux-local/README.md)
accepts `--mutex-implementation owned-v1 --owned-mutex-cabi
--owned-mutex-reuse-spins 32 --mutex-acceptance adaptive-performance`.
The scope is c01 with
64 post-work rounds and 1–8 workers only. At every count, median whole-run
throughput and best valid warmed peak must each reach 97% of the paired Native
control. A three-round screen and two fresh three-round confirmation blocks must
each pass independently. Correctness, every worker's progress and complete drain
remain required; this scope has no higher-thread or minimum-JIT gate.
The [scoped auditor](../bench/tclock_compare/mutex_local_study.py) verifies that
the screen and both confirmations pass. Their lowest whole/peak ratios are
98.15%/98.51%. The independently owned 32-byte target uses only KD's protocol
and matches the captured Linux mutex layout; it never calls Linux mutex
operations on that object. General defaults and acceptance above eight workers
are unchanged.

<a id="latest-owned-mutex-entry-and-waiting-study"></a>

## Archived native-first entry and waiting study

The preceding [native-first study](../bench/results/10.176.26.71/bench/mutex_owned/20261014-native-first/README.md)
failed its broader primary-through-28, higher-thread JIT and compatibility gates.
Its implementation is preserved at `9a5305e`, tag
`archive/perf/mutex-native-first-20261014`; its report was integrated separately.
The new 1–8 scope does not change that historical verdict. Returned JIT,
KD_SELF execution and original Linux Native remain distinct classifications.

## Earlier studies

Each report owns its numerical results, candidate identities, variation and
causal limits. These dispositions apply to the recorded version and scope.

| Study | Disposition and evidence |
| --- | --- |
| <a id="earlier-c01-owned-mutex-optimization"></a>Owned protocol, 2026-10-14 | [Report](../bench/results/10.176.26.71/bench/mutex_owned/20261014-hybrid/README.md): outcome/grant changes retained in the experimental provider; higher-thread same-policy gates pass, Native parity fails. |
| <a id="earlier-c01-owned-mutex-redesign"></a>Owned redesign, 2026-10-13 | [Report](../bench/results/10.176.26.71/bench/mutex_owned/20261013/README.md): independent object/protocol retained explicitly; finite/refill performance target fails. |
| <a id="earlier-c01-cost-study"></a>Three-way cost study, 2026-10-13 | [Report](../bench/results/10.176.26.71/bench/mutex_c01_cost/20261013/README.md): waiter counters and successor prefetch retained as a bounded higher-thread gain; Native parity unmet. |
| <a id="earlier-c01-admission-study"></a>Admission study, 2026-10-13 | [Report](../bench/results/10.176.26.71/bench/mutex_admission/20261013/README.md): all eight thresholds rejected; default 256 retained with the pinned cold sampler. |

## Origin claims and bounded NUMA selection

The [2026-10-15 origin/NUMA report](../bench/results/10.176.26.71/bench/mutex_owned/20261015-origin/README.md)
compares immutable owned images with fresh Native, TCLock and pre-change KD
controls across the full 22-count c01/post64 grid. The screen and separate
confirmation blocks do not meet the 97%-of-current-KD regression requirement;
origin claims and NUMA selection remain independently selectable and off by
default. The Native target at 1–8 workers is assessed separately. All scored
blocks use the regular 64-vCPU topology, with explicit collector contention at
64 workers. The report separates functional GS results from performance scores
and identifies the exact frozen implementation tested.

## Remaining gaps and comparison limits

Keep source versions, policies, object/caller ABIs, workloads, topologies,
governors and instrumented runs separate. All new runs use exactly CPUs 0–63,
with node 0 on 0–31 and node 1 on 32–63; no extra vCPUs or unused spare CPU.
Use collector CPU 63 outside cohorts of up to 63 workers. At 64 workers the
collector must share CPU 63 with the final worker and QEMU services, and that
contention must be reported separately. The [complete comparison workflow](../tools/vm/README.md#complete-164-worker-comparison)
records support by runner. Spin/mutex timed runs now accept explicit
`--share-collector`; rwlock, real-API and the all-lock driver still require a
separate collector. Historical 66-vCPU results remain evidence only for their
recorded placement and cannot replace the shared 64-worker point.

Immutable owned-image publication and opt-in origin-readiness/NUMA policies
were added after the accepted `585335b` implementation. The
[origin comparison](../bench/tclock_compare/README.md#owned-origin-and-numa-comparison)
uses fresh Native, TCLock and frozen KD controls. Its screen and confirmations
must stand on their own; this index does not promote the optional policies or
transfer an older performance verdict to the new source.

All valid variation belongs in the result. Operation shares do not measure
ownership streaks or establish starvation bounds. Aggregate throughput and
amortized CPU ns/op do not measure acquisition latency. Published JIT code is
not proof of a returned delegated body, and functional checks are not a new
performance matrix.

## Reproduction and history

The [benchmark guide](../bench/README.md) owns commands and measurement rules;
[workload definitions](BENCHMARK_WORKLOADS.md) explain the protected work.
The [machine index](../bench/results/10.176.26.71/README.md) catalogs reports,
and [known limitations](TODO.md) records unresolved correctness/lifetime work.
Documentation cleanup does not rerun measurements.
