# Evidence identity and preservation

Source edits, Git and read-only archive analysis ran on `380G10`. Builds, unit/kernel checks, profiles and timing ran only in the Linux 7 VM on `10.176.26.71`. Each command wrapper checked the exact tracked input hashes before/after, boot identity and project idle state. [Source identities](source-identities.json) retain core hashes and the complete-manifest hash; full manifests and commands are inside the controller/evidence archives.

The VM source checkout at completion is the isolated `4df80e5a14d0368b07c5c0a63b49f0b79b80ca4f` component snapshot. The final readback confirms no project workload/provider activity. The kernel and boot were not changed. Master and its unrelated local edits remain untouched.

## Archives

All six guest evidence bases were frozen, checked idle and archived with `bench/archive_run.py`; input inventories remained unchanged. Every downloaded archive, inventory and archiver script was checked against its receipt. No raw run was deleted. The source-host raw store is:

`/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/nano-four-lock-20261101/`

The guest archive roots are under `/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/bench/`, with `-archives` appended to each base below. Raw archives are intentionally outside Git; compact receipts, tables, profile summaries and figures are committed.

| Evidence base | Compressed bytes | Archive groups | Receipt SHA256 |
|---|---:|---:|---|
| nano-four-lock-20261101 | 799689692 | 3 | `90be11fcff25c75ffb7ec711d1a6e86d44b5337f525d745d975617daae38dccc` |
| nano-four-lock-candidate-20261101 | 283198596 | 3 | `6d752d45f315a7722b58fe83639161bd96a6070a1389ec30b0e3821021a89309` |
| nano-four-lock-reader-entry-20261101 | 305460 | 2 | `475087865d028e0d050306f755f3c1f1e53a40de538499a34b8d8920ac776365` |
| nano-four-lock-reader-entry-r2-20261101 | 188210927 | 3 | `78bde52fd1d9c3fe179788037a6305b28050c6cde385cad8e5301ee7abbd3364` |
| nano-four-lock-rwsem-reader-only-20261102 | 46474066 | 3 | `1c0c54c1d5c1cfa0c33eda4b4dec5f41fe651634e40c749371c27fd3e6dcad29` |
| nano-four-lock-osq-poll-only-20261102 | 46447891 | 3 | `708f06165617a6254367a2fc1da263609f5d37fdcb66f322b81d04e281aba705` |

The six guest bases total 1,364,326,632 compressed bytes. Group-file hashes and input-inventory hashes are in [the archive receipts](archives); the [download receipt](archives/download-receipt.json) binds the source-host copies.

Source-host orchestration, commands, captured host references, score inputs and intermediate/failed status records are retained in `source-controllers.tar.gz` (611 files). The separate `host-receipts/host-receipts.tar.gz` contains 119 QEMU-host files, including the recovery snapshot/placement captures, pool activation and restoration. [Controller receipt](archives/source-controllers.json), [host receipt](archives/host-receipts.json).

## Final runtime state

The QEMU main-loop pool settings were restored from minimum 64 / maximum 64 / batch 0 to the pre-campaign minimum 0 / maximum 64 / batch 0. Live readback confirms the settings; the retained restoration capture contains 76 tasks including nine retiring pool workers. The original 67-task map and original absence of the facade object are not claimed restored. No worker was forcibly removed. A future timing campaign needs a fresh task/placement capture.

The restoration itself completed successfully. A subsequent collection wrapper requested `after.host.json`, whereas restore mode writes `restored.host.json`; that read failed. The actual `before` and `restored` captures were then fetched and checked against their recorded hashes without issuing another mutation. The failed collection output remains in the source-controller archive. See [restore receipt](environment/result.json), [collection correction](environment/capture-collection.json), and [final guest idle check](environment/guest-idle.json).

## How to read the data

- [All follow-up points](reader-entry/ALL_POINTS.md) and [withdrawn points](grouping/ALL_POINTS.md) preserve the original Native/TCLock/KD baseline, candidate deltas and returned-body counts. CSVs contain unrounded rates.
- [Component table](COMPONENTS.md) retains all six separately measured points; none substitutes for a full-grid score.
- [Cycle/profile index](profile-index.csv), [retained profile summaries](profiles.json), and [PMU counters](pmu-counters.csv) remain unscored. Counter scope is the measured client tree; cycle summaries have their own explicit worker filtering. Spin flat summaries use the whole worker interval, unlike the settled cohort filter for the other families.
- [Worker CPU-time table](worker-utilization.csv) and [eight-worker completion table](rwsem-c01-w001-t08-workers.csv) qualify the parking discussion. They are not sleep/wakeup trace counts.
- [Negative observations](REGRESSIONS.md) enumerate all 136 negative comparisons across the specified axes and versions, with the unresolved cases marked. These comparisons reuse baseline observations as denominators; 136 is not a count of failed sessions.
- [Correctness receipts](correctness) preserve returned JIT checks, local API checks, the failed follow-up compilation and final per-session log/drain checks. Failed setup, missing instrumentation and unavailable event/batch diagnostics are not passes.

All aggregate changes are geometric means of matched ratios within one workload; no raw throughput is pooled across versions, placements, shells or instrumentation. A single round supplies no confidence interval. [The design](../../../../../docs/design/nano_four_lock_20261101.md) records the profile-first sequence and each rejected/retained choice. Component designs were committed first at `1055d8de` and `9cf4298e`, on their own branches.
