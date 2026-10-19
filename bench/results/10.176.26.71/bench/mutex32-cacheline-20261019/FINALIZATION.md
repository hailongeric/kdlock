# Four-source finalization and preservation

These commands run only after the active `prefetch` matrix exits successfully
and its own result confirms drain. A timeout or missing SSH response is not
drain. Root orchestration owns all remote operations. Use asynchronous bounded
SSH and poll for progress; no command here changes the guest kernel or unloads
a module.

## Preconditions and metadata freeze

1. Require complete/idle `matrix.json` for `packed32`, `candidate`, `old256`
   and `prefetch`; complete/idle `placement/result.json`; and successful,
   unchanged-source `checks-candidate/result.json` and
   `checks-prefetch/result.json`. The two checked revisions are `76af844` and
   `de30588`. The original three arm roles and `prefetch`'s trial role remain
   distinct.
2. Keep the production chosen for maintenance in the idle guest checkout.
   Select `--current-arm prefetch` only if that checked production is retained;
   otherwise use the reviewed path-specific restore to the checked `candidate`
   production, synchronize only while idle, and select `candidate`.
3. Capture actual host-after pins, frequency policy, QEMU identity and recovery
   snapshot with the existing `capture-host.py`, then retain `host-after.json`
   in the guest run tree. Preserve the existing host-before and guest boot
   evidence. A changed snapshot/topology/boot requires investigation.
4. Copy the final reviewed metadata helpers while idle: `run-finalize.py`,
   `placement-analysis.py`, `summarize.py`, `profile-analysis.py`, `finalize.py`,
   `export-compact.py`, both offline audits and the static code/offset receipts.
   Keep the used `run-matrix.py`, `mutex_profile.py`, `run-checks.py` and
   `run-placement.py` bytes unchanged. `REPORT-DRAFT.md` is a pending source-host
   narrative, not collected evidence; do not copy it as a completed report.
5. Require new sibling archive and compact-output directories. Preserve any
   failed attempt under a new name rather than retrying into its output.

The invariant collector SHA-256 values are:

| File | SHA-256 |
| --- | --- |
| `run-matrix.py` | `05b62f452941ff11ad5315ea4d5793faa14bb018e0b1b51346b07f184faea482` |
| `mutex_profile.py` | `cdcc07193b412e846502ffba58a4641365f17429031a476b8951e385b8031bce` |
| `run-checks.py` | `3ffa7d44a1fda78fcbbe9f0cf9fd50933129f85f8ffa04aebdc1e9e0bb3d516d` |
| `run-placement.py` | `c32fc18e60d40db814cfc98f350fc151e1fc2ac3ad961bb8ca761b16e0c268cc` |

## Guest commands

Run from `/root/host_fs/kdlock` with the pinned translation environment,
`LC_ALL=C` and `PYTHONDONTWRITEBYTECODE=1`. `RUN` below is the unchanged external
evidence directory; `CURRENT_ARM` is the explicit selection from step 2.
Redirect stdout/stderr outside `RUN`, because final idle/archive checks reject
every writable descriptor into that tree.

```sh
RUN=/root/kdlock-evidence/10.176.26.71/bench/mutex32-cacheline-20261019
timeout 1200s python3 "$RUN/run-finalize.py" --base "$RUN" \
  --arms packed32 candidate old256 prefetch \
  --check candidate=checks-candidate --check prefetch=checks-prefetch \
  --current-arm "$CURRENT_ARM" > /tmp/mutex32-cacheline-finalize.log 2>&1
```

Require exit zero and `validation.json.passed=true`, `health.json.idle=true`,
24 valid plain sessions, eight profiles and twelve placement sessions. With
both sets of live probes, expect 50 inventoried kernel logs. The wrapper retains
every analysis subprocess argv, status and output in
`final-analysis-commands.json`. Its child bound is 240 seconds; the outer bound
allows all four analyses. Preserve a failed wrapper receipt before retrying.

```sh
timeout 960s python3 bench/archive_run.py --base "$RUN" \
  --output "${RUN}-archives" --health "$RUN/health.json" --timeout-seconds 900 \
  --group packed32=packed32 --group candidate=candidate --group old256=old256 \
  --group prefetch=prefetch --group placement=placement \
  --group checks_candidate=checks-candidate --group checks_prefetch=checks-prefetch \
  > /tmp/mutex32-cacheline-archive.log 2>&1
```

Require exit zero, `archives.json.completed=true` and `guest_idle=true`.
There are seven selected groups plus automatic metadata. The archive helper
checks all paths and metadata before/after, preserves hashes and symlinks,
requires same boot and refuses active writers. It does not remove anything.

```sh
timeout 120s python3 "$RUN/export-compact.py" --base "$RUN" \
  --archives "${RUN}-archives" --output "${RUN}-compact" \
  > /tmp/mutex32-cacheline-export.log 2>&1
```

Require exit zero and `compact-export.json.passed=true`. Export checks the
completed archive/boot and copies only compact metadata and immediate command
receipts; raw source, samples, generated code and binaries remain in archives.
Transfer every tar group plus `archives.json`, `input-inventory.json` and the
retained archiver to the ignored raw directory. Transfer compact metadata to
the new report directory, preserving exact bytes. Do not trim logs.

## Source-host inert archive checks

On `380G10`, set `REPO` to the maintained checkout, `REPORT` to this report
directory and `RAW` to its ignored raw archive directory. These bounded commands
read archive members/Git objects as data; they do not execute retained source,
binaries, modules, tests or timings:

```sh
timeout 600s python3 "$REPORT/offline-archive-review.py" --repo "$REPO" \
  --raw "$RAW" --report "$REPORT" \
  --expect packed32=0987358 --expect candidate=76af844 \
  --expect old256=0324e60d6791948e9762a9916a50e8e026f073b0 \
  --expect prefetch=de30588 --extra-source placement=09ebd8f \
  > /tmp/mutex32-cacheline-archive-review.log 2>&1
timeout 600s python3 "$REPORT/offline-statistics-review.py" --raw "$RAW" \
  --report "$REPORT" --arms packed32 candidate old256 prefetch \
  > /tmp/mutex32-cacheline-statistics-review.log 2>&1
```

Require both exits zero, all audit JSON `passed=true` and zero issues. No
ancillary exception is expected. The arithmetic audit reconstructs all 44
windows and keeps the later trial and placement diagnostics separate. The
source audit binds both check snapshots through validation and placement via
its explicit source mapping. Archive receipts, audit counts and any failures
belong in the final narrative.

Only after those checks should the pending draft become the final README and
diagnostic interpretation. Report the retained production, measured limits and
remaining old256 gap. Do not turn a small three-repeat median difference into
a confidence interval, a universal gain or a causal cache-transfer estimate.
