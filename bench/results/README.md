# Results by physical machine

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

Compact reports are tracked in Git. `raw/` is ignored and is not included in source
synchronization. Keep full raw evidence, including failures, partial runs, commands,
source/binary hashes, CPU/NUMA topology, kernel identity and final drain checks.
Do not pool measurements from different machines or VM topologies.
Extracted working copies may be removed after regular-file bytes and logical
symlink destinations match a retained canonical archive. The
[documentation cleanup receipt](380G10/tests/documentation-cleanup-20261012.json)
records the four pruned copies and recovery archive paths; raw archives and
unique failure records remain available.

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
