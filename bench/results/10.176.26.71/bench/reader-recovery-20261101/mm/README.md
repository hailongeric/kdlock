# Fresh mmap1 comparison

The reader-restoration candidate remains **unaccepted** because the Nano point gate failed. This fresh MM pair compares provider `66c68c17457c0ae60d09ff1f3d89b5fff16a500c` with promoted provider `1b6f256b13e8743aa1fd7bdc958cc82ae7726463`, using unchanged upstream applications and one measurement round at each worker count. Native MM bodies execute on their original tasks; no MM body delegation is claimed.

Both arms completed all 42 points and passed the common actual-MM correctness prerequisites, including 218 API assertions per arm with cancellation, downgrade and ownership checks. The separate held-writer fixture checks syscall paths and exact ownership; it is not part of timed execution. The offline validator checked 84 original point records and 42 paired comparisons.

| Model | Geometric mean change | 20 workers | 32 workers | 60 workers | Observed losses |
| --- | ---: | ---: | ---: | ---: | ---: |
| threads | -0.780% | -5.156% | -1.972% | -1.119% | 12/21 |
| processes | -1.192% | +0.307% | +0.142% | -11.261% | 10/21 |

The [complete comparisons](comparisons.json), [thread grid](threads.csv), [process grid](processes.csv), and [validation record](validation.json) preserve all gains and losses. One round supplies no variance estimate or causal attribution.

This pair has no newly measured `f7a84065` MM arm. The historical -22.385920% result at 60 processes remains a separate cohort; multiplying that ratio by the current result would not establish recovery. The existing source-bound queue fixture would need an explicit phase-queue variant before a fresh f7 arm. No process-loss fix is claimed from this comparison alone.

The normal `7.0.0-38-kdlock1` boot was verified after both arms. QEMU pool settings were restored from their original activation receipt. Exact boot, kernel, source, pool and archive identities remain in the provenance records.

The [complete comparison figure](mmap1-comparison.png) shows every paired point.
The [60-process inspection](process60/README.md) separates the aggregate loss
from the changed distribution of progress across workers.

The restored pool settings are `thread-pool-min=0`, `thread-pool-max=64` and
`aio-max-batch=0`. The restoration receipt reports
`original_task_map_restored=false`; restoration of settings does not establish
that the earlier QEMU task map or QOM object absence was restored.

The successful [kernel preparation/build and boot records](../mm-kernel/preservation.json)
are retained separately from the failed preparation attempts. The provider is
archived at `codex/archive-reader-recovery-20261101`; the scope4 recipe is at
`codex/archive-reader-scope4-20261101`. Neither is promoted into master.
