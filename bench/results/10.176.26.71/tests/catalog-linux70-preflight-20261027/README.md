# Linux 7 catalog preflight

The affected runner checks passed after one retained fixture failure. Seven old reporting fixtures lacked completion counters; their corrected local-execution inputs now provide explicit zero counters, and a missing-counter negative check remains. No production admission or completion requirement was relaxed.

The later [trusted-source basic controller](../ordinary-string-translation-20261027/README.md#complete-four-family-basic-controller)
passed all four families in one completed run, with correct data, returned JIT
bodies and final idle. Its distinct source identity, complete archive and exact
counts are bound in that report. It supplies no performance score.

The earlier constituent functional checks below passed across three isolated
runs. Each completed 1,600,000 operations with correct data, returned JIT bodies
and normal drain. Their two parent controllers that stopped on later presets
retain their original failed state; the newer pass does not change those
historical outcomes.

| KD family | Preset | Workers | Returned bodies |
| --- | --- | ---: | ---: |
| spin | c01 | 16 | 1,596,969 |
| mutex | public c01 | 16 | 1,588,598 |
| rwlock | c01, 20% writes | 16 | 32,874 |
| rwsem | c16, 100% writes | 16 | 1,571,790 |

Retained `NO_JIT` attempts completed correct data and drained: rwlock c01/20% writes at 60 workers (6,000,000 operations), and rwsem c01/20% writes at 16 workers (1,600,000 operations). Neither is relabelled as a returned-body pass. The timed catalog retains its complete requested grid and mixes.

The first campaign launch was rejected by the caller-affinity guard before source freezing, builds, module loads or timing. Its 63 coordinates remain `NOT_RUN` in the preserved attempt. Removing the controller-wide CPU restriction allowed the runners to validate the worker mask before their clients pin each worker and collector. No timed coordinate was repeated.

[Evidence index](evidence.json) · [Timed catalog](../../bench/catalog-linux70-20261027/README.md)

Compact receipts are copied and hash-bound. The complete five-attempt frozen trees were also preserved at the drained boundary in `raw/tests/catalog-linux70-preflight-20261027/full-frozen-evidence.tar.gz` (SHA256 `0d16eedd635c0fe4bf8b97ee0a0252df1c6a691d83efb56c127ae1f6903d2263`, 26,895,886 bytes). Original VM copies remain unchanged. Later MM runner fixture checks are recorded with the trusted-source checks; actual shared-MM runtime remains a separate scope.
