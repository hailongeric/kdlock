# Performance status

The archived 64-vCPU study accepted the owned ABI4/reuse-32 profile against the
97% Native target for c01/post64 at 1–8 workers. It extends the experimental
`d8d14a1` provider with Linux-style local acquisition before delegation at
implementation commit `585335b`.
The benchmark still defaults to legacy
mutexes; `owned-v1` explicitly selects the independent 32-byte KD object.
Owned ABI2 capture-first, admission ratio 256, reuse allowance 0 and finite FIFO
remain the general defaults. The measured profile explicitly selects ABI4 and 32.
This narrow result does not establish general Native parity. Implementation contracts live in
[the mutex guide](design/mutex_implementation.md); correctness receipts live in
[validation](VALIDATION.md).

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
98.15%/98.51%. The owned target uses only KD's protocol and retains the Linux
object layout. General defaults and acceptance above eight workers are unchanged.

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
| <a id="earlier-c01-protocol-study"></a>Legacy protocol trials, 2026-10-13 | [Report](../bench/results/10.176.26.71/bench/mutex_protocol/20261013/README.md): frame/layout/capture/epoch candidates rejected; raw failures and post-work variants retained. |
| <a id="earlier-c01-optimistic-spin-study"></a>Legacy optimistic retry, 2026-10-13 | [Report](../bench/results/10.176.26.71/bench/mutex_optimistic/20261013/README.md): six retry/OSQ candidates rejected; explicit native owner/list/OSQ drain check retained. |
| <a id="earlier-c01-cost-study"></a>Three-way cost study, 2026-10-13 | [Report](../bench/results/10.176.26.71/bench/mutex_c01_cost/20261013/README.md): waiter counters and successor prefetch retained as a bounded higher-thread gain; Native parity unmet. |
| <a id="earlier-c01-admission-study"></a>Admission study, 2026-10-13 | [Report](../bench/results/10.176.26.71/bench/mutex_admission/20261013/README.md): all eight thresholds rejected; default 256 retained with the pinned cold sampler. |

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
