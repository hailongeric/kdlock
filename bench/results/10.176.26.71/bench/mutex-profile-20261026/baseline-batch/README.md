# Batch diagnostic preparation failure

The first case failed while loading the diagnostic provider. **No warmup or timed measurement ran; no throughput is available.**

| Body | Workers | Backend | Result | Measurements |
|:---|---:|:---|:---|---:|
| Minimal pair, post4 | 16 | KD | Provider load failed | 0 |

The kernel rejected the module’s 8,360-byte reserved per-CPU allocation with `ENOMEM`, before module initialization. The post-failure receipt records an idle guest with neither the provider nor workload module loaded; the session reports drained. The allocator failure and its diagnostic stack trace remain preserved.

Failed source: `8b31c980192bd69daf5abedf989a8dacb445ee5f`. The campaign stopped at this case. Any reduced-histogram retry is a distinct source and stage, with its own validation and measurements.

[Failure scope and receipt hashes](failure.json) · [Case table](table.csv). Raw evidence is retained under `raw/bench/mutex-profile-20261026/` as `baseline-batch-command.json` and `batch-load-failure-state.stdout`; this report does not reinterpret the failed load as a benchmark result.
