# Final MM archive review

This is a review plan for existing results, not an additional test or measurement
campaign. It changes no source, runner, controller or archive. The full analyzer
must remain unexecuted until all four completed archives and transfers exist.

## Fixed inputs

- Source: `f7a84065e84474380faa37eeadfdf534abd72a68`.
- Kernel recipe: `8446f4ecb08816380a4c233197a8ce5e4d333aac`.
- Kernel: `7.0.0-38-kdscope1`, Build ID
  `a17d565ee157601e030d1b3c77c13e63fa62c994`.
- Analyzer: `/tmp/kdlock-scope-f7-mm-offline-analysis-r2-20261030.py`, SHA256
  `da6ce611cf61b75b5c0fa3ce11c7d6a9c094b0b88d9664e92d094af308b2a145`.
- Incomplete input draft:
  `/tmp/kdlock-scope-f7-mm-offline-inputs-draft-20261030.json`, SHA256
  `a0e80a46554473df34588aa26fad855462236b2d4ffee3c1346434270c428035`.
- Root reports KD-B boot `8c5259e3-0f93-493d-afa9-bd93d5358683`, completed
  postboot receipt `4cdd61dac5ae60398fcd52653e2ec874e3eed0fef643c155976eb8b98480e68f`
  and sites receipt `360ec8fdae0c178691ebba7e5a1cc47942288d833977eb94b5a06e3a97839b6b`.
  These are checkpoints, not evidence that the pending KD-B grid or archive passed.

The raw base is
`bench/results/10.176.26.71/raw/tests/kdscope1-mm-f7a84065-20261030/`
in `/home/eric/vm/vm-shared/kdlock`. Reuse its existing receipt caches; do not
create duplicate full caches or change captured bytes.

## Review against the actual archive members

| Review | Existing evidence and exact expected result |
| --- | --- |
| Transfer completion | Each label's `transfer.json`, `<label>-archive-control/owner.json`, `<label>-archives/archives.json`, `input-inventory.json` and `member-sha256.json` agree. Native-A transfer is `ed2d1820426c2ee32619aa07417dea4f0366244ed2115e2cc07203335f2c7dc8`; KD is `7227b2a63bf1d26a51ececdf7a17ce46cd4689f874cc1d9849fdaafbcb0728a2`; Native-B is `c5aaf779a13c1c36208a929b5eb5d3d5def8e12c41623814a47a79197db619da`. Record the actual fourth transfer instead of inferring it from a successful workload. |
| Measurement inventory | KD and Native-B each supply 21 `shared-measure` sessions. Native-B and KD-B each supply 42 `mmap1-measure` sessions: 21 threads, then 21 processes. Workers are exactly `1,2,3,4,5,6,7,8,12,16,20,24,28,32,36,40,44,48,52,56,60`; every coordinate is round zero. The full result has 126 points and 63 pairs, with no missing, duplicated or silently omitted point. |
| Completion | For every timed grid, its `*-controller.json`, aggregate `result.json`, individual point `result.json` and archive preservation map bind the same bytes and boot. Require the existing completed/passed/drained/final-idle, return-code and explicit retirement fields; a finished transport alone is insufficient. |
| Reuse and mode | Native-A's `shared-prepare/inputs.json` and `mmap1-prepare/inputs.json` are the exact inputs reused later. Native/KD bundles retain identical compiled source/build maps, with only the declared mode/runtime identity different. Original project generation and 8446 kernel recipe remain separately named. |
| Same-boot prerequisites | Read each measured boot's `api`, `mapping`, `faults` and `completed` result plus owners, and the mmap1 grids' `mmap1-identity` result. Report their actual case/error/retirement totals, not a success extrapolated from another boot. Check all dependency hashes resolve to the retained original receipts. |
| Timed placement | Grid `topology.json` and `environment.json` retain 64 online CPUs, worker CPUs 0 through N-1, collector CPU 63, and the same source/build/dependency/preemption settings. Mmap1's retained worker records distinguish thread TGIDs from process TGIDs and bind the prepared executable. Live affinity checks are runner-verified evidence, not newly performed by the offline reviewer. |
| Immediate endpoints | Read `endpoints/<step>/endpoint-receipt.json` and its before/after/reference/policy/transport copies. Bind exact grid owner/result/controller hashes, boot and the original 0–300 second capture delay. Native-B's localized endpoint precedes its later identity/mmap1 work. Localized remains exploratory with `strict_host_gate=FAILED`; mmap1 requires strict PASS and unchanged 131-task identity. Do not overwrite the original runner's generic `host_endpoint=PENDING` field. |
| Diagnostic correction | Both mmap1 identity results name the external runner SHA `5c23db457fc9cfc91ff68c7f392e5c003812cb54a66fe082a0e73a0b459b6120`, separate diagnostic commit `d22a36567de28c024ebb8d1c79997c0d39541bd2`, and retained runner copy. The exact unused generated `.mod.c` snapshot is labeled untracked/not-built; it does not alter the frozen f7 source or scored executables. |

## Independent score reconstruction

Review raw scores separately from the analyzer's CSV, using the archived logs
and point receipts. This is arithmetic over existing results, not a rerun.

For every localized point, read the two original `client.jsonl` records. Sum
workers' completed pairs and CPU times, check all N joined with no errors, and
verify `finished_ns=max(worker.finished_ns)` and
`wall_ns=finished_ns-started_ns`. Recompute
`whole_ops_s=sum(worker.completed)*1e9/wall_ns`. Preserve exact shared mm/lock
identity, maps/closes conservation and final health
`files=0 mm_refs=0 destroyed=1 release_errors=0`. Compare the reconstructed
value with the point's `measurement.whole_ops_s` and final CSV. Do not substitute
the two-second nominal duration, peak window, CPU time or the preparation runs.
One operation is an mmap/munmap pair, not a processor cycle.

For every mmap1 point, read `mmap1-measure/<model>-nNN-r00/upstream.log`.
Keep the six pre-marker warmup samples separate from the two post-marker
measurement samples. Let T be the sum of the two post-marker totals: the score
is `T/2` pairs per nominal second, while upstream's printed integer average must
be `T//2`. A possible half-pair difference is therefore expected; do not replace
the score with the rounded average. Compare all parsed min/max/total samples
and T with `result.json` and the final CSV. The roughly eight-second whole
process lifetime and whole-lifetime CPU times include warmup and are not score
denominators or isolated lock-cost measurements.

For each of the 63 pairs, recompute `KD/Native` and
`100*(KD/Native-1)` from the unrounded underlying score. Keep three distinct
groups: localized shared-mm (21), mmap1 threads (21), mmap1 processes (21).
Count gains/losses/ties per group and retain every negative. Cross-check the
published n1/n20/n32/n36/n60 rows and each group's extrema against raw values;
all other coordinates remain in the complete CSV. The localized final values
must reconcile with the retained preliminary 21-pair CSV, or any difference
must be explained from exact raw evidence before publication.

## Reporting and retained failures

The final independent review should state the actual validation result and
hashes of both CSVs, `points.json`, final input manifest and `validation.json`.
The latter must say `completed=true`, `validated=true`, 126 points, 63 pairs
and `performance_accepted=false`. Preserve any failed offline analysis attempt
and diagnose it without repeating measurements or relabeling source bytes.

Keep Native-A's self-open log refusal and missing-hwloc preparation attempt,
KD's API snapshot mismatch and failed stable-writer observation, and Native-B's
generated-input identity failure. Their original failed/undrained fields remain;
separate later idle/preservation receipts establish cleanup without rewriting
those failures. Distinguish unscored corrective attempts from the single scored
round. Retain transport failures separately from successful guest completion.

Report original-task unchanged MM bodies and local reads/writers explicitly.
The separate two-worker identity observation does not observe the timed
application's exact mm address. There are no scored JIT, parking, per-lock
contention, PFN/NUMA placement or isolated scheduling-cost counters. Preserve
those limits and the one-round lack of variability estimates. Do not infer
causation or claim whole-kernel replacement from throughput alone. Keep the
existing nano and syscall results separate, with no retrospective acceptance.

The final report stays in one MM result directory and one later reviewed
commit. Raw archives remain external; copy only the exact necessary small
receipts, complete CSVs and analysis provenance. No TODO/ROADMAP status change
or performance acceptance precedes the final paired evidence and root review.
