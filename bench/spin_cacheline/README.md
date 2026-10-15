# Shared benchmark components

The spin/mutex entry points are [run.py and run_mutex.py](../tclock_compare/README.md).
This directory supplies their common client and evidence helpers. The
[rwlock runner](../rwlock_compare/README.md) reuses peak selection, kernel identity
and private provider preparation with its own client and read/write oracle.
Payloads live in
[workload_modules](../../workload_modules/README.md).

| File | Responsibility |
| --- | --- |
| `client.c` | Pinned workers, unified start, fixed/timed measurement and final validation |
| `peak.py`, `test_peak.py` | Complete-cohort peak windows and worker progress checks |
| `bench_runtime.py` | CPU placement, counters, source/device lifetime and frozen inputs |
| `bench_session.py` | Preparation, publication, measurement and ordered cleanup |
| `provider/prepare.py` | Private observation-provider copy and patch; production source stays separate |
| `kernel_identity.py` | Captured source/config/build/live Build ID verification |
| `summarize.py`, `assembly.py`, `profile_summary.py` | Offline summary, assembly export and flat-IP attribution |
| `test_spin_cacheline.py`, `test_assembly.py` | Client/oracle/provider/export checks without live modules |

All-worker warmup and measurement share the same CPU geometry. Timed loops publish
progress every 256 operations; static final snapshots independently verify exact
cacheline/hash business results. Progress is used to select windows, not to replace
data correctness. Assembly export groups identical code by critical section and
retains all drained source sessions and hashes.

The spin/mutex client can label a timed 64-worker run sharing CPU 63 with its
collector. The runner requires `--cpus 0-63 --collector-cpu 63 --share-collector`;
client JSON and peak validation retain `collector_shared`. Smaller cohorts keep
the collector separate. Other runners have their own placement restrictions;
see the [support table](../../tools/vm/README.md#complete-164-worker-comparison).

`make -C bench/spin_cacheline test` runs only in the guest and loads no module.
The direct runner builds backend-specific workloads and symbol dependencies.
Its private KD provider defaults to `--kd-provider-ubsan off`; `kernel` explicitly
inherits the kernel's policy. See [runner settings](../tclock_compare/README.md).

Current heat rules, objects and prefetch are documented once in
[execution flow](../../docs/JIT_EXECUTION.md) and
[spin implementation](../../docs/design/spin_implementation.md).
[The evidence index](../results/380G10/bench/tclock_compare/HISTORY.md) preserves historical
measurements; old hook/dispatch-floor entry points are no longer live instructions.
