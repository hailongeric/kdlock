# Performance status

The owned ABI4/reuse-32 profile passes the 97% Native target for c01/post64 at
1–8 workers. It extends the experimental `d8d14a1` provider with Linux-style
local acquisition before delegation. The benchmark still defaults to legacy
mutexes; `owned-v1` explicitly selects the independent 32-byte KD object.
Owned capture-first, admission ratio 256 and finite FIFO remain the general defaults.
This narrow result does not establish general Native parity. Implementation contracts live in
[the mutex guide](design/mutex_implementation.md); correctness receipts live in
[validation](VALIDATION.md).

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

## Latest owned-mutex entry and waiting study

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
governors and instrumented runs separate. The regular VM uses collector CPU 63
outside worker cohorts. The [complete comparison workflow](../tools/vm/README.md#complete-164-worker-comparison)
uses 66 vCPUs; at 64 workers, collector vCPU 65, the last worker and QEMU services
share physical host core 63. Historical cohorts are not interchangeable.

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
