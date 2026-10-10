# Complete spin, mutex and rwlock reports

The [full benchmark driver](../../tools/vm/README.md#complete-164-worker-comparison)
runs one-cacheline and RCUHT payloads under KDLock, TCLock and Linux Native
at 22 worker counts: 1–8 in steps of one, then 12–64 in steps of four.
Three rounds produce 1,584 timed sessions by default. Explicitly opting into
multi-cacheline payloads restores the historical 3,960-session matrix.
The driver owns execution and drain;
[`export.py`](export.py) reads saved evidence without executing benchmark code.

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

The complete 64-worker run uses the documented temporary 66-vCPU layout.
Collector vCPU 65 is distinct from every worker, but it shares physical host
core 63 with the last worker and QEMU services at 64 workers. Preserve that
limitation and the frozen source, topology and governor when publishing results.
