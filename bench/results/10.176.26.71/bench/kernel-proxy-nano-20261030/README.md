# Kernel proxy nano comparison: retained baseline

This is the baseline milestone of the October 30 kernel-proxy campaign, recorded
while the candidate campaign was still running. All **210 baseline points**
completed, drained and passed offline replay of the raw data, operation mix,
sampled peak, JIT accounting, source retirement and ordinary unload receipts.
There is **no candidate comparison or performance acceptance yet**. Strict host
timing qualification remains failed; these measurements are exploratory and
cannot establish the required no-regression result or `mmap1` acceptance.

Baseline source is `acfa33a5adbc1ec6a8aa3bb02f0107052b32a20f`. The separate
candidate is `8446f4ecb08816380a4c233197a8ce5e4d333aac`; no candidate result is
included in this milestone. No measured baseline point was retried. Preparation,
capture and archival failures below are retained separately.

## Workload and platform

`c01` means one padded cacheline counter; `c16` means sixteen. `w1`, `w20` and
`w100` mean 1%, 20% and 100% writes. Every point has 256 register-only post-work
rounds, 48,000 preparation operations per worker and one 2-second measurement.
The existing peak observation uses a 300-ms window after a 300-ms settling
interval, sampled every 10 ms. Warmup operations are not pooled with measurement.

Each row below covers workers `1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52
56 60`, exactly once. Readers in rwsem and rwlock execute locally; JIT counts
refer to writers. A positive returned-body count does not imply that every
operation delegated.

| Lock | Workload | Returned JIT points | No JIT points |
| --- | --- | ---: | ---: |
| Mutex | c01, w100 | 18 | 3 |
| Mutex | c16, w100 | 19 | 2 |
| Rwsem | c01, w1 | 2 | 19 |
| Rwsem | c01, w20 | 17 | 4 |
| Rwsem | c16, w1 | 11 | 10 |
| Rwsem | c16, w20 | 18 | 3 |
| Rwlock | c01, w1 | 10 | 11 |
| Rwlock | c01, w20 | 13 | 8 |
| Rwlock | c16, w1 | 10 | 11 |
| Rwlock | c16, w20 | 13 | 8 |

All 131 `RETURNED_JIT` and 79 `NO_JIT` points remain in
[`baseline-points.json`](baseline-points.json) and
[`baseline-points.csv`](baseline-points.csv). No point is `PARTIAL_JIT`.
The captured identifiers in these files and the raw archives are unchanged.
This is a coverage classification, not an aggregate throughput score.

The VM was `10.176.26.71`, release `7.0.0-38-kdlock1`, boot
`677b7afa-5358-4ece-a650-5f4a4adecd55`, running Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`. It had 64 vCPUs: node 0 CPUs 0–31,
node 1 CPUs 32–63. Workers use the CPU prefix beginning at 0; collector CPU 63
is separate. Host frequency was fixed at 2 GHz with turbo disabled; guest
preemption was lazy. The actual recovery snapshot
`linux70-kdlock1-clean-20261027` was listed and the exact kernel bundle verified.
Mutex total/locality limits and the spin batch limit were 1024; optional mutex
diagnostics were off. Existing completion and heat observations were enabled
and remain part of this measurement identity.

The campaign ran from `2026-10-29T20:07:49.943267+00:00` through
`2026-10-29T20:33:50.100970+00:00`. Host endpoint captures were 42.674 seconds
before launch and 194.531 seconds after completion, within the 300-second
freshness bound. Fixed host/QEMU placement and frequency matched. Two auxiliary
host `worker` threads appeared at the ending endpoint, both confined to CPU 63,
as allowed by the recorded exploratory policy. These endpoint checks do not
prove uninterrupted conditions during the campaign or repair strict timing
qualification. `performance_accepted` remains false.

## Evidence and provenance

The completed guest evidence root is
`/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/bench/kernel-proxy-nano-baseline-acfa-20261030`.
Its sibling `-control` directory records controller, synchronization, plan and
completion identities; the sibling `-archives` directory contains the maintained
archiver's eleven groups. The copied raw evidence is retained under
`bench/results/10.176.26.71/raw/bench/kernel-proxy-nano-20261030/` in the main
checkout. [`baseline-validation.json`](baseline-validation.json) records archive,
inventory, controller, source, ELF, image, host and oracle hashes.

Offline verification authenticated all 15,650 inventory paths and 12,840 regular
files. All 287 selected tracked source blobs match the baseline Git commit in
every profile. Synchronization also left 15 extra leaves; their exact hashes,
review and retained dependency/import proofs are in
[`baseline-extra-source-review.json`](baseline-extra-source-review.json).
The baseline's explicit object list and include/import paths do not use them;
none occurs in the 350 retained compiler dependency receipts. This is tracked
Git authentication plus an explicit stale-file review, not a claim that the
whole guest directory was a pristine checkout.

Each of the ten providers was prepared from 111 captured production leaves plus
the recorded benchmark observation inputs. The verifier reconstructs all 26
patch hunks from baseline Git bytes using exact, unique full-context matches,
including recorded line offsets. All 113 resulting prepared leaves per profile
match both the preparation manifest and actual archived bytes. The preparation
step adds observation code; the exact binary manifest and `insmod` receipts bind
the built provider to each measured session. Provider filenames and whole-ELF
hashes differ between profile build directories; they are retained individually.

The verifier reads archived code only as data. It imports only this report's
reviewed analyzer and the explicitly selected checkout's `oracle.py` and
`peak.py`, after verifying that both oracle files equal both named Git commits.
It executes no archived source, build, module, daemon, test or timing program.
All live work ran in the VM; edits and this read-only archive replay ran on
`380G10`.

## Retained preparation and capture failures

These are not failed or repeated measurement points. Their bytes and SHA256
values are preserved in [`baseline-preparation.json`](baseline-preparation.json)
and `preparation/`:

- The first synchronization failed on source-host disk space before guest
  mutation. A subsequent bounded synchronization completed and was bound to
  the controller's exact tracked-source manifest.
- The first host-before capture rejected a changed QEMU task list during its
  snapshot. A fresh capture succeeded before the first measurement; the failed
  receipt remains retained.
- The first archival command supplied newer kernel-profile arguments to the
  baseline archiver, which does not accept them. Argument parsing failed before
  capture. Invoking that same baseline archiver with its supported arguments
  then completed all groups, verified unchanged inputs and confirmed guest idle.

The daemon/server interruption occurred after baseline launch. On recovery,
the controller had already completed all ten blocks with return code 0 and an
idle health receipt. Work resumed with the ending host capture and archival;
no measured point was repeated.

## Reproduce the offline baseline audit

Use the completed raw archive and copied control directories. The output must
be a new directory outside the input archives and source checkout. This is an
offline receipt replay, not permission to run builds or tests on the source host.

```sh
python3 bench/results/10.176.26.71/bench/kernel-proxy-nano-20261030/verify_baseline.py \
  --baseline-archives /ABS/kernel-proxy-nano-baseline-acfa-20261030-archives \
  --baseline-control /ABS/kernel-proxy-nano-baseline-acfa-20261030-control \
  --baseline-host-after /ABS/baseline-host-after.json \
  --trusted-checkout /ABS/kdlock \
  --output /ABS/new-baseline-audit
```

[`verify_baseline.py`](verify_baseline.py) binds the prepared provider and exact
reviewed extra-source set, then invokes the baseline checks in
[`analyze.py`](analyze.py). The latter also contains the final two-campaign
comparison, which has not been run at this milestone. It requires all 630
candidate points, candidate source preparation review and fresh endpoints;
every observed KD loss against its matched baseline is retained. Versions,
topologies, call shells, preparation intervals and observation settings are
never pooled. Candidate API, localized mmap and final unchanged will-it-scale
`mmap1` acceptance remain separate unfinished work.
