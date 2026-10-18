# Capture and reproduction

Capture is complete: the final 756-session rwsem grid, 270-session spinning-rwlock
reference, both diagnostic profiles, focused validation and guest-health checks
completed successfully. All six archives passed transfer/hash verification.
The independent arithmetic replay passed for all 2,118 timed sessions across
the two full grids, seven screens and spinning reference. These outcomes do not
turn every measured performance comparison into a pass; regressions and split
execution groups remain in the [report](README.md).

The source checkout was on `380G10`, branch `master`, with parent
`485729fa6cfd9d5c116f7234e9d3114928d5d764`. Compilation, unit programs,
modules, daemons, live probes, timing and profiling ran only in the recovery VM
at `10.176.26.71:2222`. Host-side work consisted of source editing/Git inspection,
documentation, archive verification and arithmetic/figure generation. No guest
kernel source, installation or boot configuration was changed.

## Identity and placement

The guest used Linux `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, and boot ID
`b65f0205-c8f9-4385-8b13-039cbce243a6`. Its 64 vCPUs and 24 GiB RAM were split
between two NUMA nodes: CPUs 0–31 and 32–63, with 12 GiB each. Each vCPU was
pinned to the identically numbered host CPU; QEMU service threads and the
benchmark collector used CPU 63. Workers used CPUs 0 through N−1. The host
topology capture reports 64 physical cores across two sockets without SMT
siblings. The benchmark runner checks boot policy and kernel identity; the
scheduler/API probe also checks kernel identity.

The recoverable snapshot `before-mutex-kdonly-20261017T140354Z` was confirmed
through the actual QEMU monitor before live work and was
[rechecked after completion](recovery-snapshot-after-verified.json).
[Before/after host checks](host-comparison.json) confirm unchanged QEMU identity,
arguments, CPU pins and frequency policies. These receipts are separate from
the runners' kernel/environment receipts. Final guest health confirmed idle,
the same boot ID, no Linux mutex imports and no detected kernel faults in
1,423 retained session logs. Tracing ended at `nop`, function profiling disabled
and no enabled functions. The host used `ondemand`, with
800 MHz–3.6 GHz policy limits. Equal policy settings do not establish equal
effective frequency or load during every measurement.

## Source versions

| Run family | Source evidence |
| --- | --- |
| Initial full grid | Historical `485729f` report and immutable archive |
| `baseline-screen`, `baseline-repeat-screen`, `baseline-profile` | Original rwsem provider/header, with their own frozen manifests |
| `poll-screen` | `archive/rwsem-opt-poll-20261018`, `6480326b314db2ff95508c22787075f58a899e1c` |
| `split-screen` | `archive/rwsem-opt-split-20261018`, `1a53a0f3ac75d44bb6e3c9d069ee7865f3f9379c` |
| `long-screen` | `archive/rwsem-opt-long-20261018`, `72a0a0e3a7a4a228e367830f7cb7293669df5858` |
| `grant-screen` | `archive/rwsem-opt-grant-20261018`, `c5aa264cac7ade5e3eb40dab2b080c9b568fdf07` |
| Selected `xlong-screen` and final checks/comparisons | Runtime files from `archive/rwsem-opt-xlong-20261018`, `768fc20cd981bfe28cc223825d25b5c9c2552757` |

The archive refs retain rejected experiments. Frozen source manifests, rather
than run names or commit messages, establish which bytes each measurement used.
The selected runtime changes are confined to `include/kd_rwsem.h`,
`kernel_module/kd_rwsem.c` and the affected probe in
`tests/kernel/rwsem/module.c`. Source-equivalence receipts compare 112 preserved
runtime inputs with `d2a2304`, including all 16 selected mutex files. A separate
comparison checks 115 unchanged provider/header/translator/daemon inputs against
`485729f`, excluding the two changed rwsem runtime files. These scopes overlap.
Both final-grid and final-reference manifests match all 233 reviewed source
inputs; the [source-equivalence receipt](final-source-equivalence.json) records
each comparison. The receipts do not claim binary identity between different
builds or replace runtime validation.

Each screen contains 48 sessions: c01, Native/KD, 1%/20% writes,
1/8/32/60 workers, three repetitions. The historical full grid and both fresh
baseline screens remain separate controls. The selected screen is not pooled
with the final grid. The reader-grant candidate passed its own focused
correctness probe but regressed badly in its screen; it is not present in the
selected implementation. Smaller polling budgets also remain separate,
rejected measurements.

## Run controls

The guest orchestration script `run.py` delegates each benchmark to the
maintained `bench/rwlock_compare/run.py`, which freezes its inputs. The
orchestrator checks idle before
and after each stage, retains the exact command and exit status, and gives the
full grid a 7,200-second subprocess bound and other stages a 2,400-second bound.
The profile helper has its own alarm deadline; both captured invocations use
`--timeout-seconds 900`. A timeout is not accepted as
drain. No module was force-unloaded, and no running source snapshot was edited.

The timed matrix uses two seconds per session, three repetitions, 48,000 warmup
iterations per worker, post4 work, evenly spaced writes with worker phase 17,
collector CPU 63, default unchanged heat/admission rules, KD/TCLock provider NUMA
support enabled, applicable delegation batch limit 1,024, and provider UBSAN
disabled. The frozen plan retains sampling
and warmed-peak window settings. Native/KD rwsem uses the standard 21 worker
counts; the separate spinning-rwlock reference uses Native/TCLock/KD at
1/8/32/36/60 workers. The runner README gives both exact command lines.

The focused validation uses different plans and is not throughput evidence:
the selected scheduler/API probe; two basic C programs; 36 Native/KD functional
sessions at 0%/1%/20% writes and 1/8 workers; four ordinary local KD controls;
and four strict c08/RCUHT checks at 80%/100% writes and 16 workers. The basic
program capture includes source and logs but has no separate executable-hash
manifest. Other retained build manifests identify modules and daemon binaries.

## Evidence import

The guest evidence base is `/mnt/kdlock-builds/rwsem-opt-20261018`. After all
runs and final health capture completed, the archive helper partitioned
every top-level path into six groups: `screens`, `profiles`,
`tests`, `main`, `reference` and `metadata`. It preserves private `.inc` files,
source/build inputs, binaries, all session records, publication/translation
evidence, logs, rejected candidates, command receipts and profiling controls.
It confirmed guest idle and unchanged input inventory before accepting capture.
The guest archives remain in `/mnt/kdlock-builds/rwsem-opt-20261018-archives`.

Raw archives and exported receipt JSON files belong under the ignored
`../../raw/bench/rwsem-optimization-20261018/` directory relative to this report.
The tracked [archive receipt](archives.json) records compressed SHA256 values;
the six [verification receipts](verification/main.json) record successful
source/binary-manifest checks. They verified 4,185 source-file instances and
95 binary-file instances across independent frozen run copies. Those are
instances, not unique files. Analysis inputs and independent replay are retained
alongside them. The [import guide](IMPORT.md) explains
group-specific receipt roots and commands. Archive readers do not execute
captured project code or extract arbitrary links.

`analysis.json` and the replay retain the hash of [captured-runs.json](captured-runs.json),
whose relative paths resolve from the raw evidence directory. The report's
relocated [runs.json](runs.json) resolves from this directory instead. Their
[path comparison](run-map-relocation.json) confirms that all 12 run roots are
identical; the map-file hashes differ because the relative prefixes differ.

`report.py` recomputes rates, peaks and groups from captured records.
`independent-replay.py` imports neither that analyzer nor repository programs;
it separately checks progress, protected effects, deterministic read/write
mixes, raw-sample peaks, JIT completion deltas and comparison arithmetic.
`validation-report.py` reads captured test/profile/health evidence rather than
inferring a pass from a planned command. Diagnostic profiles never enter scored
throughput. Native control variation, mixed JIT statuses and every lower
observed rate remain visible.

[Independent replay](final-independent-replay.json) passed 816,639 recorded
arithmetic/data/identity checks with zero failures, covering all 2,118 timed
sessions. The [targeted final review](final-evidence-review.md) independently
checked every regression, every 60-worker case, all spinning references and
diagnostic aggregation. Neither offline reader ran a fresh kernel test. The
[validation report](../../tests/rwsem-optimization-20261018/README.md) records
the actual focused VM checks and the basic-program executable-manifest limit;
the full unit suite was not run.

An initial offline verification attempt used the new archive's default prefix
against the older full-grid tar and failed. The corrected explicit-prefix
invocation verified that historical archive; the
[initial failure](verification/verify-old-grid.json) and
[corrected result](verification/verify-old-grid-v2.json) are retained. This
was an import-path error, not a skipped benchmark or a runtime test pass.

The post-run snapshot helper initially assumed numeric snapshot IDs and
misclassified QEMU's all-disk listing, whose IDs are `--`. Its first receipt
retains the real listed snapshot despite a false parsed flag. The parser was
corrected to accept either numeric IDs or `--`; a second read-only monitor
query verified the snapshot. The original/corrected helpers and receipts are
preserved in the metadata archive. This parser correction did not alter VM
state or replace the successful pre-run recovery check.
