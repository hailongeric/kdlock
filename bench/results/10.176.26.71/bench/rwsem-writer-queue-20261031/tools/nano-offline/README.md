# Fresh writer queue nano archive comparison

This unexecuted source-only revision compares fresh f7a84065 and 1b6f256b KD
arms from controller 1857baca and cohort 58c40508. It retains every one of the
210 coordinates per arm. Old f7/22d results remain historical and are not pooled.
The file hashes are in manifest.json. Independent source review passed at
manifest c69d6cf957f36a7a26ab0a793e93aab93d07511564cbca71f999858041431465
and fetch f7377f4216ed2d1a07d2371379acdf6ba261f254187b7e8733729bb9029a02cf.
Preparation has not fetched archives, imported archived code or run a workload.

The retained Archive/Git readers, point validator, source/provider checks and
integer loss comparison are unchanged. New control parsing binds the finalized
cohort, the fresh pool and the actual standalone four-family basic results.
The candidate's original 7fa overall failure remains failed. Only its successful
unit/classifier blocks are retained, with their exact logs and the full two-file
source-equivalence proof; corrected 1b live checks and basic are separate.

After each arm is complete, root archives it using the existing controller.
Fetch uses `/tmp/kdlock-writer-queue-nano-fetch-20261031.py`; it does not archive,
recapture an endpoint, retry or start a next phase. All five hashes below must
come from the actual completed receipts. Do not invoke it during timing.

```sh
python3 /tmp/kdlock-writer-queue-nano-fetch-20261031.py \
  --arm baseline \
  --destination /dev/shm/kdlock-writer-queue-nano-f7a84065-20261031 \
  --archive-sha256 ACTUAL_ARCHIVES_JSON_SHA \
  --owner-sha256 ACTUAL_RUN_CONTROL_OWNER_SHA \
  --archive-owner-sha256 ACTUAL_ARCHIVE_CONTROL_OWNER_SHA \
  --endpoint-receipt-sha256 ACTUAL_ENDPOINT_RECEIPT_SHA \
  --host-after-sha256 ACTUAL_HOST_AFTER_SHA
```

For the candidate, use `--arm candidate` and a new destination
`/dev/shm/kdlock-writer-queue-nano-1b6f256b-20261031`. These paths mean the actual
380G10 tmpfs mount namespace; use the approved elevated source-host executor
when necessary. The guest originals remain unchanged.

Before transport, read actual completed archive group sizes from archives.json
and obtain closed-tree apparent byte counts for the arm's archives/control plus
its standalone basic directory while idle. Compare them with actual destination
space. Do not infer a current size from an older campaign. Budget for the tar,
its extracted copies and the later temporary Archive cache concurrently. The
helper checks at least 2 GiB free initially and, after transfer, at least the tar
size plus 1 GiB before extraction; root should plan additional analysis cache
headroom from the actual inventory. Source root currently has limited capacity;
keep raw/control/analysis data in tmpfs and retain only compact final outputs in
the report. No unrelated cleanup is part of this workflow.

Fetch copies only the compressed archive directory, its complete control
directory and the original standalone basic directory. The eight known basic
workspace links retain their original target metadata and become confined
relative links to the same copied family source. All regular source/session
bytes and group hashes are checked. A failure retains the transport and partial
outputs. A timeout may terminate only its local SSH process; it never implies
guest drain. Only a completely verified task-created transport.tar is removed.
The fetch writes `analysis-arm.json` and `transfer.json` with actual hashes.

When both fetches succeed, create one new JSON input containing exactly:

```json
{"schema":1,"arms":{"baseline":{ "...": "actual baseline analysis-arm.json object" },
                     "candidate":{ "...": "actual candidate analysis-arm.json object" }}}
```

The placeholder objects must be replaced by parsed actual files, without
changing their paths or hashes. Retain both original arm files and record the
combined file's SHA-256. Then run only the offline maintained-source reader:

```sh
python3 /tmp/kdlock-writer-queue-nano-offline-20261031/nano_compare.py \
  --inputs ACTUAL_COMBINED_INPUT_JSON --inputs-sha256 ACTUAL_INPUT_SHA \
  --trusted-checkout /home/eric/vm/vm-shared/kdlock \
  --cache-root /dev/shm \
  --output /dev/shm/kdlock-writer-queue-nano-comparison-20261031
```

The trusted checkout supplies only the unchanged maintained peak/oracle source,
verified against both Git commits. Archived source is data, never imported or
executed. The reader verifies compressed groups, every member and source map,
actual provider overlays/ELFs, same kernel/topology/pool, exact settings and
both endpoint qualifications before publishing a completed result. Any failed
analysis remains separate; do not overwrite it.

Outputs include all 210 pointwise whole/peak ratios in comparison/points.json
and points.csv; every negative in observed-losses.json; exact integer loss
counts; unscored counts; and execution classifications including NO_JIT.
comparison/profiles.json and profiles.csv add per-profile geometric means over
all 21 measured ratios, explicitly including NO_JIT and retaining any unscored
classification. key-workers.json contains all 30 points at 20/32/60 workers.
Geometric means do not cancel individual regressions. One round supplies no
variance or significance estimate. performance_accepted remains false; the
no-regression evidence gate is false for any negative, unscored coordinate or
failed strict qualification.

Correctness provenance is retained in each campaign.json's offline_prerequisites
and the authenticated control files. Existing local originals are under
`/tmp/kdlock-writer-queue-controls-20261031/`: baseline-checks/result.json,
candidate-checks/result.json (the failed 7fa overall attempt),
corrected-checks/result.json, prerequisites/bindings.json, and
baseline-basic/result.json plus candidate-basic/result.json. Successful retained
unit blocks are not described as fresh 1b unit runs. The new control copies
retain prior-unit-config/sync and retained-check-0-result/sync/selected logs.

For bounded progress observation, the outer stdout remains empty until its
completion marker. The baseline launcher's actual profile progress is instead
in `/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/bench/writer-queue-nano-f7a84065-20261031-control/run.log`:
START and FINISH lines identify profile boundaries. The c01 mutex profile log is
`/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/bench/writer-queue-nano-f7a84065-20261031/mutex-throughput.log`.
Each profile log flushes `[n/21]` before a point and a reads/writes/JIT_complete/
drained=True line after it. A bounded tail of these small logs is preferable to
recursive scans. The arm owner.json contains profile/PID state but is rewritten
non-atomically; a partial read is not a failure or proof of drain. records.json
is written only after the profile's 21 sessions finish. Session files/logs prove
only their recorded state; no progress read itself authorizes another VM action.
No remote observation is performed by this preparation.
