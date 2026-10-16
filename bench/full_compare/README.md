# Complete spin, mutex and rwlock reports

The [full benchmark driver](../../tools/vm/README.md#complete-164-worker-comparison)
plans one-cacheline and RCUHT payloads under TCLock, Linux Native and KD for
spin, mutex and rwlock, at 22 worker counts: 1–8 in steps of one,
then 12–64 in steps of four. Three rounds select 1,584 timed sessions by default.
Explicitly opting into multi-cacheline payloads selects 3,960 sessions. Execution
at 64 workers still requires the collector-sharing support described below.
The driver owns execution and drain;
[`export.py`](export.py) reads saved evidence without executing benchmark code.
The all-lock driver uses owned ABI2 for KD mutex payloads. The current owned ABI4
c01 profile uses the [dedicated command](../tclock_compare/README.md#owned-c01-full-grid)
and its [198-sample report/auditor](../results/10.176.26.71/bench/mutex_owned/20261014-full-grid/README.md),
separately from the all-lock c01/hash matrix.

After the complete matrix has drained, use the plotting environment in the guest:

```sh
/root/kdlock-evidence/10.176.26.71/reports/performance-20261010T081816Z/venv/bin/python3 \
  bench/full_compare/export.py \
  --input /root/kdlock-evidence/10.176.26.71/bench/full-matrix-RUN \
  --output /root/kdlock-evidence/10.176.26.71/reports/full-matrix-RUN/report
```

[`requirements.txt`](requirements.txt) records that environment's plotting
packages. Keep it separate from the pinned CPython 3.10 translator environment.

The exporter checks all requested configurations, three rounds, worker and
collector placement, retained source/binary/JIT image hashes and complete KD
retirement. It independently recomputes accepted warmed peak windows from raw
progress samples. Original runner acceptance and rwlock parity evidence remain
in the report; failed sessions remain in the archive and are excluded from scores.
JIT and NO_JIT samples also have separate aggregates. Descriptive pooled totals
do not satisfy the rwlock runner's strict parity criterion when execution types differ.
Interrupted attempts remain archived, receive independent hash/peak checks and
have separate CSV/JSON; their sessions are excluded from final three-round scores.

CSV and JSON retain every session, best warmed peaks, whole-run medians,
min/max/spread, CPU/NUMA progress and comparison ratios. PNG/SVG scaling plots
show all 22 counts and round variation. `--no-plots` permits read-only auditing
of an extracted archive without a guest or plotting dependencies.
For Git publication, trim Matplotlib's trailing SVG whitespace in the guest
and check that SVG elements and path tokens match. Preserve the original
generated SVGs in the raw archive and retain a normalization receipt.

All new runs use exactly CPUs 0–63: NUMA node 0 has CPUs 0–31 and node 1 has
CPUs 32–63, pinned to the matching host cores. Do not add extra vCPUs or an
unused spare CPU. At 64 workers, the collector must share CPU 63 with the last
worker and QEMU services; the current driver needs collector-sharing support
before that point can run. See the [placement and runner limitation](../../tools/vm/README.md#complete-164-worker-comparison).
Historical 66-vCPU reports retain their original topology and physical
collector contention. Preserve frozen source, topology and governor when
publishing results; those reports do not describe the new required placement.
