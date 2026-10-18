# Main consolidation, 2026-10-18

The user selected KD-only `d2a23049a4b6e3c65cf0ff21bbfd3e21cd975761` as the main
implementation. `master` merges the previous master history while retaining that
runtime. Compatible tooling and missing reports from the owned-mutex branch are
selected explicitly; rejected protocol changes are excluded.

## Branch dispositions

| Previous ref / tip | Disposition |
| --- | --- |
| `task/kd-only-mutex`, `current/kd-mutex`: `d2a2304` | Selected runtime; immutable tag `accepted/kd-only-mutex-20261018`; `master` and `current/kd-mutex` select the consolidated version |
| Previous `master`: `2c88895` | Merged history and missing evidence; preserved by `archive/master-before-kdonly-20261018` |
| `task/legacy-mutex-compat`: `555b8b7` | Already an ancestor of selected version; retained by `accepted/kd-mutex-compat-20261017` |
| `bench/legacy-mutex-c01-pipebytes`: `74676c3` | Already an ancestor; retained by `archive/legacy-mutex-grid-20261018` |
| `recovery/mutex-legacy-5m330`: `6ecdd0a` | Already an ancestor; retained by `archive/mutex-legacy-recovery-20261018` |
| `task/owned-mutex-origin-numa`: `9a4bf2a` | Compatible tooling/catalog and missing evidence imported; full implementation archived at `archive/owned-mutex-before-main-20261018` |
| Original 35 dirty files | Preserved exactly in `bc7efcf` on `wip/pre-main-20261018`; token audit found formatting/comment changes only; not mixed into the measured runtime |
| Other `origin/perf/*` and `origin/wip/*` | Historical candidates/checkpoints; existing remote refs retained, no speculative runtime merge |

Completed local topic branches are replaced by the immutable refs above. Their
frozen worktrees remain available at detached commits. Detached experiment
worktrees containing edits remain untouched. No remote branch deletion, force
push or remote default-branch change is performed by this consolidation.

## Integrated updates

- c02/c04 CLI selection for the existing synthetic payloads.
- Explicit synthetic spin/mutex collector sharing at 64 workers, checked in the
  client and peak reader and separated in report identity. The 1–60 grid continues
  to use a dedicated collector. The current 256-byte mutex layout checks remain.
- Missing historical reports from old master and the owned-mutex branch. Numeric
  evidence is copied unchanged; source identities remain historical.
- A current workload catalog, one operations guide, a documentation index and
  scoped current validation/performance status.

## Excluded implementation changes

Owned/adaptive mutex, CABI4, parked producers, owned-specific benchmark parameters
and origin-context experiments conflict with the user's selected legacy protocol.
Fail-closed instruction admission and immutable image publication were already
backported into `555b8b7`, so those fixes are retained without the owned protocol.

Old master's sleeping rwsem uses the owned-mutex gate and combines writers at
unlock. It drains readers only after acquisition returns. Current legacy mutex
combines during acquisition: renaming APIs would permit delegated writers before
reader drain. That feature needs a separately designed port and live validation.
Its proc-snapshot integration and validation stay in history, outside the build.

## File organization

Development rules move to root `AGENTS.md`; VM procedures live in
`docs/operations/VM.md`. Historical design studies move to `docs/history/`.
Captured kernel experiments move under `kernel_baseline/experiments/`, with source
snapshot and clobber-test paths updated. The historical full-matrix exporter
moves under `bench/archive/`; the 66-vCPU launcher and its one-off resume helper
are removed from maintained tools.

Obsolete mutex shadow/signal/parallel trace fixtures are removed because they
expect deleted provider hooks and address-to-shadow interfaces. Their exact files
remain in Git history. Current local mutex, resource, task/ACK, image, terminal
and outer-progress checks remain. This removal does not resolve historical pinned
waiter failures, which remain in [limitations](../TODO.md).

The [machine-readable change inventory](main-consolidation-20261018.json) lists
every move, removal, imported evidence path and captured branch identity. The
[validation receipt](../../bench/results/10.176.26.71/tests/main-consolidation-20261018/README.md)
records runtime equivalence, static/link checks and guest tests. No new benchmark
timing is claimed for this consolidation, which leaves the lock runtime unchanged.
