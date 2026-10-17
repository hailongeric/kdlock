# Results by physical machine

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

Current KD mutexes always support blocking. Older reports retain the policies,
commands and source hashes captured when they ran; reproduce them with their
frozen source versions. The [performance guide](../../docs/PERFORMANCE.md) and
[validation index](../../docs/VALIDATION.md) describe the applicable limits.
The recorded owned ABI4/reuse-32 profile has a separate
[1–8-worker acceptance study](10.176.26.71/bench/mutex_owned/20261014-linux-local/README.md)
and [1–64-worker comparison](10.176.26.71/bench/mutex_owned/20261014-full-grid/README.md).
They use different VM topologies; the latter's three-worker peak misses its
Native target. Neither changes historical report verdicts or general defaults.

The [adaptive c01/pipebytes comparison](10.176.26.71/bench/comparison/mutex-adaptive-20261016T075356Z/README.md)
adds 504 fresh sessions with exact pre-change KD, adaptive KD, Native and TCLock.
The new 128-byte layout and optional contention policy have separate identities;
performance regressions keep adaptation off by default. Its historical legacy
reference and rejected pilots are not pooled with the final comparison.

The [2026-10-16 expanded mutex comparison](10.176.26.71/bench/comparison/mutex-expanded-20261016T040928Z/README.md)
adds 2,079 fresh accepted and drained sessions across all five cacheline payloads,
RCUHT and five private pipe/file API variants. It compares KD, TCLock and Native
at 21 worker counts through 60, with three repetitions and explicit ABI4/reuse-32.
The [2026-10-15 all-lock round](10.176.26.71/bench/comparison/workloads-20261015T180603Z/README.md)
remains the separate 7,749-session spin/mutex/rwlock and API report; its missing
KD mutex variants describe the support at that frozen source version. The new
matrix supplies complete mutex coverage without pooling the rounds or broadening
the earlier c01 performance acceptance.

Compact reports are tracked in Git. `raw/` is ignored and is not included in source
synchronization. Keep full raw evidence, including failures, partial runs, commands,
source/binary hashes, CPU/NUMA topology, kernel identity and final drain checks.
Do not pool measurements from different machines or VM topologies.
Extracted working copies may be removed after regular-file bytes and logical
symlink destinations match a retained canonical archive. Cleanup receipts for
[2026-10-12](380G10/tests/documentation-cleanup-20261012.json) and
[2026-10-15](380G10/tests/documentation-cleanup-20261015.json) record the pruned
copies, archive hashes and recovery paths. The later check also compares file
permissions and retains copies with unique files or differing permissions.
Raw archives and unique failure records remain available. Restore an extraction
only when needed for an offline audit, using the receipt's archive and member
prefix; retain any recorded guest-to-local symlink mapping.

Dated measurements, kernel captures, upstream provenance and branch inventories
are historical records, not files that expire by age. Update maintained guides
and indexes when behavior changes; preserve frozen commands, verdicts and source
identities. Generated Python bytecode outside raw evidence can be removed and
regenerated from its source. The `bench/.tmp` compatibility link below is retained.

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
