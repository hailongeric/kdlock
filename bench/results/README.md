# Results by physical machine

`master` retains the accepted KD-only mutex protocol from `d2a2304` and the accepted
reader/writer semaphore (rwsem) waiting implementation from `c21345b`. See
[current performance](../../docs/PERFORMANCE.md) for results and retained
regressions, and [terminology](../../docs/TERMINOLOGY.md) for execution and
measurement definitions.
The [instruction-exit receipt](10.176.26.71/tests/native-instruction-exit-20261018/README.md)
records the later checked waiter-continuation feature and its failures/final
correctness checks separately from accepted throughput measurements.
The [2026-10-18 consolidation checks](10.176.26.71/tests/main-consolidation-20261018/README.md)
validate organization and tooling separately from the measured runtime.
The [feature reintegration checks](10.176.26.71/tests/feature-reintegration-20261018/README.md)
validate the earlier ordinary-only rwsem, restored snapshots and benchmark safeguards,
including retained delegation failures. Historical owned/adaptive mutex and
owned-gate rwsem reports remain separate evidence.

The [accepted rwsem comparison](10.176.26.71/bench/rwsem-optimization-20261018/README.md)
records the `c21345b` Native/KD c01/c08/RCUHT comparison at 1%/20% writes on the
standard 1–60-worker grid, preserving the selected KD mutex protocol. It retains
candidate screens, baseline controls, execution groups, diagnostic profiles and
source identities. Acceptance includes the substantial two-worker regressions;
the recorded report and raw measurements remain unchanged. Its separate Native/TCLock/KD spinning-rwlock reference uses
all three payloads and both mixes at 1/8/32/36/60 workers, 270 completed sessions;
those non-sleeping results are not pooled with rwsem. The
[focused validation receipt](10.176.26.71/tests/rwsem-optimization-20261018/README.md)
records the matching functional and execution checks.

The [initial rwsem writer-delegation comparison](10.176.26.71/bench/rwsem/20261018/README.md)
remains the historical shared-queue baseline. Its high-count regressions, split
execution statuses, returned-body counts and raw evidence are preserved.

The [KD-only mutex round](10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md) contains 504 fresh accepted/drained sessions
at 1–8 workers by one and 12–60 by four, three repetitions, with accepted KD,
Native and TCLock controls. It measures the removal of Linux mutex backing while
retaining legacy delegation. At 60 workers KD-only reaches
4.838/5.130 Mops/s for c01/post64 and
pipebytes n16. Full scaling, low-count variation, separate regression follow-ups,
intermediate trials and independently replayed evidence remain in the report.

The [2026-10-17 legacy compatibility comparison](10.176.26.71/bench/comparison/mutex-legacy-compat-20261017T122742Z/README.md)
contains 504 accepted/drained sessions and a verified 20,567-file archive,
including its failed first preparation. It compares independent instruction/image
backports against fresh legacy, with Native/TCLock controls. Raw evidence is in
`10.176.26.71/raw/bench/mutex-legacy-compat-20261017T122742Z/`; the report retains all results, regressions,
plots, source identities and replay receipts.

The [latest recovered-legacy mutex grid](10.176.26.71/bench/comparison/mutex-legacy-grid-20261016T125529Z/README.md)
contains all 378 requested c01/post64 and pipebytes n16 sessions, with separate
source-verified archives and fresh Native/TCLock controls. Its raw archive is
`10.176.26.71/raw/bench/mutex-legacy-grid-20261016T125529Z/`; all samples and
failed offline-analysis invocation logs remain preserved.

Use the physical benchmark host as the machine identifier, even when the run
executes inside its VM. Source edits remain on `380G10`; all new compilation,
tests and benchmarks run in the VM on `10.176.26.71`.

| Machine | Results |
| --- | --- |
| [`380G10`](380G10/README.md) | Historical 40-vCPU tests and comparisons; retained evidence and source-host scratch files |
| [`10.176.26.71`](10.176.26.71/README.md) | Migrated VM validation and all subsequent tests and benchmarks |

Each machine directory uses the same structure:

```text
bench/results/<machine>/
  bench/<runner>/<run>/       compact benchmark reports, tables and figures
  tests/<suite>/<run>/        compact test reports
  raw/bench/<run>/            original benchmark archives and extracted evidence
  raw/tests/<run>/            original test archives and extracted evidence
```

Compact reports are tracked in Git. `raw/` is ignored and is not included in source
synchronization. Keep full raw evidence, including failures, partial runs, commands,
source/binary hashes, CPU/NUMA topology, kernel identity and final drain checks.
Do not pool measurements from different machines or VM topologies.

Live guest output must remain outside `/root/host_fs/kdlock`, as required by the
runners' frozen-input checks. New output paths are:

```text
/root/kdlock-evidence/10.176.26.71/bench/<run>
/root/kdlock-evidence/10.176.26.71/tests/<run>
```

Copy or archive those runs to the corresponding host `bench/results/10.176.26.71/raw/`
directory. Assembly exports follow the source run's parent under `assembly/`;
retain them with the run's evidence. Use a fresh run name for every execution.
Publish only compact summaries under `bench/` or `tests/`.

Historical raw files moved from `bench/.tmp/` to
`bench/results/380G10/raw/legacy/`. This includes source-host scratch files whose
individual run provenance is not established; retain their existing manifests
rather than assuming they are benchmark samples. The proven new-host migration
archive is separated into `bench/results/10.176.26.71/raw/bench/`.
`bench/.tmp` is a local compatibility symlink to the legacy directory, and its
old migration-run path redirects to the new-host archive. These links preserve
old references without duplicating evidence. A fresh checkout contains the
compact reports, without raw archives or these local links.

The migrated guest also retains original-host archives under
`/root/kdlock-evidence/380G10/legacy/`, with compatibility links at their original
top-level paths. The Python environment remains reachable through its original
path. New-host guest runs are stored separately under `10.176.26.71/`.

Frozen JSON/CSV records, captured commands and fixed Git links keep their original
paths and bytes. For retained compact reports, the relocation mapping is:

| Original path | Current path |
| --- | --- |
| `results/<machine>/<category>/` | `bench/results/<machine>/<category>/` |
| `bench/rwlock_compare/results/<report>` | `bench/results/380G10/bench/rwlock_compare/<report>` |
| `bench/tclock_compare/results/<report>` | `bench/results/380G10/bench/tclock_compare/<report>` |
| `bench/.tmp/<entry>` | `bench/results/380G10/raw/legacy/<entry>` |
| `bench/.tmp/migration-20261010T070707Z` | `bench/results/10.176.26.71/raw/bench/migration-20261010T070707Z` |
