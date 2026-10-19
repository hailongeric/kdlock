# Owner, gate and tail contention comparison

Root orchestration owns all VM commands. Source-host work is limited to source,
Git, static review and inert archive inspection. Follow
[VM operations](../../../../../docs/operations/VM.md), including actual recovery
snapshot, idle-state and host pinning checks before live work. This document
defines collection; it does not claim a completed result.

The new external guest evidence path is
`/root/kdlock-evidence/10.176.26.71/bench/mutex32-cacheline-20261019` (`RUN` below).
Keep every earlier report and frozen source unchanged. The final comparison
has three fresh source arms:

| Arm | Source identity | Meaning |
| --- | --- | --- |
| `packed32` | `0987358` | Current versioned-node accounting, production `c2f0d9c` |
| `candidate` | `76af844` | Queue-head retirement, inline gate hint and exact ownership predicate |
| `old256` | `0324e60d6791948e9762a9916a50e8e026f073b0` | Historical 256-byte object |

Actual command receipts establish collection order. Labels are not an order
or permission to pool source versions. A failed check, timeout, no-gain
candidate or incomplete collection remains under its original source identity
and a separate archive group. Never rerun into an existing output directory.

## Fixed comparison scope

Each arm runs six plain `pipebytes/query` timings: 16 entries, value size 64,
outer clobber caller, 8 and 60 workers, three repeats, 2000 ms measurement,
48000 operations per worker and 1000 ms minimum warmup. Workers use CPUs
0 through N−1 and collector CPU 63. NUMA, batch limit 1024, entry-ratio limit 2,
prefetch 2 and UBSAN-off provider settings remain those of the ordinary runner.
The configured helper waves/workers are unused by pipe.

Two unscored diagnostic profiles follow each arm's plain timings. The copied
profile driver uses flat `cycles:k` at 199 Hz, attaches to the idle client,
inherits workers and requires FIFO start/stop acknowledgements. It retains
the exact perf binary and resolves symbols before teardown. Never treat a
NORMAL image as a returned JIT body. Preserve every worker's results/progress,
measured body entries and returned completions, source retirement and drain.

Copy the reviewed helper bytes into `RUN` while idle before the first arm.
Keep the matrix/profile driver bytes unchanged across the three arms:

```sh
python3 "$RUN/run-matrix.py" --version packed32 --commit 0987358 --base "$RUN"
python3 "$RUN/run-matrix.py" --version old256 --commit 0324e60d6791948e9762a9916a50e8e026f073b0 --base "$RUN"
python3 "$RUN/run-checks.py" --commit CANDIDATE_REV --output "$RUN/checks-candidate"
python3 "$RUN/run-matrix.py" --version candidate --commit CANDIDATE_REV --base "$RUN"
```

Use the pinned translation environment and recorded recovery environment only
after verifying the real monitor snapshot. Commands above are sequential;
each source transition requires idle verification and reviewed synchronization.
The matrix bounds each plain/profile subprocess at 900 seconds. The affected
check driver preserves individual command bounds. A timeout does not prove
drain and does not authorize force unloading or editing active inputs.

`run-matrix.py` also accepts a safe preliminary arm label, such as
`candidate-preliminary-1`; it still uses six plain timings and two profiles,
and records `comparison_arm=false`. Final analysis accepts the three named
main arms and the explicitly selected `prefetch` trial described below.
Candidate checks can use a new output directory per attempt;
the final wrapper's `--check candidate=DIRECTORY` selects the successful
checked source. Keep failed and earlier attempts as separate archive groups.

The later `prefetch` trial is source `de30588`, preserved by
`archive/mutex32-prefetch-20261020`. It uses the same frozen matrix driver and
standard six plain timings plus two profiles. Its source/checks remain separate
from `76af844`, and the original `comparison_arm=false` receipt is preserved.
Summary tables label it `cohort_role=trial`; it is never silently substituted
for the original candidate or pooled with that candidate's repetitions:

```sh
python3 "$RUN/run-checks.py" --commit de30588 --output "$RUN/checks-prefetch"
python3 "$RUN/run-matrix.py" --version prefetch --commit de30588 --base "$RUN"
```

To analyze all four completed source blocks, use repeated explicit check
mappings. `CURRENT_ARM` is `prefetch` only if that checked production is retained;
otherwise restore the checked `candidate` production while idle and select it:

```sh
python3 "$RUN/run-finalize.py" --base "$RUN" --arms packed32 candidate old256 prefetch \
  --check candidate=checks-candidate --check prefetch=checks-prefetch \
  --current-arm CURRENT_ARM > /tmp/mutex32-cacheline-finalize.log 2>&1
```

Archive both trial subtrees with `--group prefetch=prefetch` and
`--group prefetch_checks=checks-prefetch`. Add `--expect prefetch=de30588` to the
source audit and `prefetch` to the arithmetic audit's explicit `--arms` list.
The completed four-source scope is 24 plain sessions, eight profiles, twelve
placement sessions and two sets of three live probes. The arithmetic audit
reconstructs 44 windows. A failed/incomplete trial cannot enter this completed
scope; preserve it separately and keep its failure explicit.

The copied `remove-obsolete.py` permits only the exact reviewed `0987358`
additions absent from old256, including `include/kd_mutex_state.h`,
`kernel_module/mutex/count.inc` and five added test files. Its hashes must be
reviewed again if a candidate changes those paths before switching to old256.
The helper refuses changed files before deleting anything and writes a receipt.
This is not permission to delete unknown files. Sync does not delete obsolete
inputs automatically; stale files would invalidate source identity.

## Checks and diagnostics

The selected checks are the two basic tests and fourteen affected mutex,
execution and provider-lifetime drivers, including `test_mutex_head.py`, then
the two separate API runner planning/report programs and ordinary mutex local,
rwsem and instruction-exit live probes. The expected unit total is 16/16;
the runner programs currently contain 11 and 13 unittest cases. Their passing
totals and absence of skips are checked separately. Private `.inc` files and
`bench/real_api` plus its `bench/tclock_compare` imports are frozen inputs.
Any newly affected invariant must be covered without dropping existing probes.
If the selected driver inventory changes, update both the check driver and
finalization's exact expected scope before freezing them. Missing dependencies,
compile failures and skips are not passes.

Record lock addresses from every session and calculate actual field lines;
native 8-byte alignment alone does not establish their placement. Separate
placement-only diagnostics are described in [PLACEMENT.md](PLACEMENT.md).
Their modified workload source and timing results must remain distinct from
the standard three-arm comparison.

The reviewed `09ebd8f` diagnostic source has exactly the same provider bytes as
baseline `0987358`. Once synchronized and idle, run:

```sh
python3 "$RUN/run-placement.py" --commit 09ebd8f --base "$RUN"
```

This requires a completed baseline matrix and verifies its retained production
hashes against the diagnostic checkout. It runs the planning/report checks,
then offsets 32 and 40, each with six plain diagnostic sessions and no profiles.
It retains source/binary manifests, commands and statuses, checks actual lock
addresses and returned-body equality, and requires drain before continuing.
The two offsets share a source identity and differ in the compile option and
resulting workload ELF. Keep the diagnostic subtree under `placement`, add
`--group placement=placement` when archiving, and map it with
`--extra-source placement=09ebd8f` during source audit. No placement result
enters the three main medians.

Flat cycle samples predominantly show waiting at high worker counts. They do
not measure HITM, cache transfers, gate-CAS retries or the cost of a specific
atomic instruction. Inspect the guest's actual PMU before considering precise
events; unavailable or unsupported events remain unavailable, not zero cost.
Compare every profile's returned-JIT fraction with its own plain cohort before
attributing sampled work. Performance claims use only fresh plain timings.

## Finalization, preservation and review

After all arms and final candidate checks are complete, restore the checked
candidate in the idle maintained guest checkout. Capture host-after policy
and pins, preserving the same boot identity and actual snapshot evidence.
Run finalization with logs outside the evidence tree:

```sh
python3 "$RUN/run-finalize.py" --base "$RUN" --check candidate=checks-candidate > /tmp/mutex32-cacheline-finalize.log 2>&1
python3 bench/archive_run.py --base "$RUN" --output "${RUN}-archives" \
  --health "$RUN/health.json" --group packed32=packed32 \
  --group old256=old256 --group candidate=candidate --group checks=checks-candidate \
  --group placement=placement \
  > /tmp/mutex32-cacheline-archive.log 2>&1
python3 "$RUN/export-compact.py" --base "$RUN" --archives "${RUN}-archives" \
  --output "${RUN}-compact" > /tmp/mutex32-cacheline-export.log 2>&1
```

Add explicit groups for every preliminary/failed/placement attempt. Top-level
metadata and unused reviewed helper sources are preserved in the metadata
archive. Finalization scans all retained kernel logs; it does not hide a fault
in an excluded timing cohort. If a retained failure needs separate treatment,
report it explicitly instead of weakening the health predicate.

The final wrapper first runs `placement-analysis.py`, then the separate main
summary/profile analysis and finalization. Health inventories 18 main timings,
six profiles and twelve placement sessions individually, plus the three live
probe logs. Placement diagnostics are never part of the main timing totals.

After copying the grouped archives and compact metadata to the source host,
the following helpers inspect archives as inert data and do not execute them:

```sh
python3 "$REPORT/offline-archive-review.py" --repo "$REPO" --raw "$RAW" --report "$REPORT" \
  --expect packed32=0987358 --expect candidate=CANDIDATE_REV \
  --expect old256=0324e60d6791948e9762a9916a50e8e026f073b0 \
  --extra-source placement=09ebd8f
python3 "$REPORT/offline-statistics-review.py" --raw "$RAW" --report "$REPORT" \
  --arms packed32 candidate old256
```

Use `--extra-source DIRECTORY=REVISION` for separately retained check or
preliminary source snapshots. Production differences receive no ancillary
exception. Retain archive hashes, exact source manifests, loaded JIT evidence,
measured entry/return equality, whole/peak arithmetic and profile denominators.
The three-source arithmetic audit independently reconstructs 36 measured windows,
including the twelve separate placement diagnostics, and their group medians.
The optional static offset helper binds samples to the exact retained ELF;
it does not convert sampling skid into a measured cache-transfer cost.
