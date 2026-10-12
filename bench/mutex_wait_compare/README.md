# Historical mutex wait-policy comparison

KD mutexes now always support blocking. The spin-only implementation,
`mutex_blocking` module parameter, `--mutex-wait-mode` runner option and
spin-versus-blocking matrix launcher have been removed. The bounded polling
optimization remains: `mutex_spin_limit` defaults to 4096 PAUSE iterations
before sleeping, with zero requesting immediate parking.

Use the current [mutex runner](../tclock_compare/README.md),
[real API runner](../real_api/README.md) and
[complete-matrix driver](../../tools/vm/README.md#complete-164-worker-comparison)
for new measurements. The [implementation guide](../../docs/design/mutex_implementation.md#blocking-waits)
explains result/gate waits, migration pinning, wake ordering and GS admission.
The [scheduler probe](../../tests/kernel/mutex/run_wait_selftest.py) checks real
sleep, withheld-wake progress and exact drain separately from JIT evidence.

This directory retains the offline exporter and its tests for archived
spin/blocking comparisons. Historical source hashes, policy labels and results
remain unchanged. Reproduction requires the
[frozen implementation and launcher](https://github.com/hailongeric/kdlock/tree/742c81ebfa4ce8532d2c179ac28aa3ef9aba0f98/bench/mutex_wait_compare),
not the current blocking-only provider.

```sh
python3 bench/mutex_wait_compare/export.py --input RAW_RUN --output NEW_REPORT --plots
python3 bench/mutex_wait_compare/test_export.py
```

The exporter verifies saved source/binary/JIT hashes and recorded module policy,
recomputes peaks from raw per-worker progress, and retains all rounds, CPU costs,
wait observations and execution classifications. Optional `--pilots`, `--paired`
and `--superseded` inputs remain separate from final samples. Matplotlib is
needed only for plots. The archived default and full grids require all 2,430 or
8,910 planned records, respectively, with exact coverage and drain; required-JIT
exclusions remain unscored.

The [complete 1–64-worker report](../results/10.176.26.71/bench/mutex_wait/20261012-full/README.md)
records all 8,910 sessions, full tables/plots, retained exclusions and CPU/JIT
analysis. The [earlier six-count report](../results/10.176.26.71/bench/mutex_wait/20261012/README.md)
retains the implementation, scheduler validation and tuning history. Both
reports belong to their captured source versions and environments.
