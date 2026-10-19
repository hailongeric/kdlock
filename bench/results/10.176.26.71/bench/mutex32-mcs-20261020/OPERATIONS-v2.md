# Explicit locality256 trial and four-source analysis

This extends [OPERATIONS.md](OPERATIONS.md) after the original three source
blocks completed. The first candidate's observed regressions prompted a separate
bounded-locality trial. The original source blocks, collector bytes, check
collector, labels and results remain unchanged. This document specifies scope;
it does not select a retained implementation or claim a performance gain.

| Arm | Committed source | Original matrix role | Analysis role |
| --- | --- | --- | --- |
| `baseline` | `826faa6` | `comparison_arm=true` | Original comparison |
| `candidate` | `f4d359d` | `comparison_arm=true` | Original comparison, first MCS/FIFO candidate |
| `old256` | `0324e60d6791948e9762a9916a50e8e026f073b0` | `comparison_arm=true` | Fresh historical control |
| `locality256` | `752fec1` | `comparison_arm=false` | Explicit later trial |

The trial restores the NUMA deferred-count handoff at eight and uses a bounded
256-body local cohort. Its source and outcomes are separate from `f4d359d`.
The existing frozen matrix already accepts a separate label and preserves
`comparison_arm=false`; no collection helper is edited or role silently changed.
The same c01/seek/pipe workload, worker, repetition and measurement settings apply:

```sh
python3 "$RUN/run-checks.py" --commit 752fec1 --output "$RUN/checks-locality256"
python3 "$RUN/run-matrix.py" --version locality256 --commit 752fec1 --base "$RUN"
```

Root orchestration owns VM commands and source transitions. These commands
require the same confirmed recovery environment and idle-state checks as the
original collection. The separate new check directory retains its complete
source snapshot, builds, 17 basic/affected drivers, runner programs and three
live probes. The finalizer reads terminal control names from each check's
frozen source: eleven for `f4d359d`, thirteen for `752fec1`, excluding only the
passing `production` entry. It checks each named negative outcome separately.
OSQ retains ten named controls. No check outcome is borrowed across sources.

The extended inventory is **72 ordinary timings**, no profiles or placement
experiments, and two sets of three live probes: **78 expected kernel logs**.
`host-after-fifo.json` is an intermediate capture; final `host-after.json` must follow
the trial and the selected checked production's restoration. Archive any
intermediate captures and provisional summaries under their original identities.
Do not overwrite a previously used v1 analysis output without preserving it.

## New analysis files and commands

The original helpers remain byte-for-byte intact. The new `*-v2.py` helpers
explicitly accept only the original three arms plus `locality256`, preserve
original/trial roles in sessions and groups, and require both new-source check
sets. All four medians remain separate. `CURRENT_ARM` must be selected explicitly
after reviewing results and must identify the checked production currently
present in the maintained checkout. It is not inferred from an arm name or
the trial's collection order.

For a preliminary table without final host/check validation, use a new external
output directory; the unchanged formatter reads the resulting JSON:

```sh
python3 "$RUN/summarize-v2.py" --base "$RUN" \
  --arms baseline candidate old256 locality256 --output /tmp/kdlock-mcs-preliminary-v2
python3 "$RUN/print-summary.py" /tmp/kdlock-mcs-preliminary-v2/comparison.json
```

After restoring the selected checked source and capturing final host policy,
run finalization with stdout outside the evidence tree:

```sh
python3 "$RUN/run-finalize-v2.py" --base "$RUN" \
  --arms baseline candidate old256 locality256 \
  --check candidate=checks-candidate --check locality256=checks-locality256 \
  --current-arm CURRENT_ARM > /tmp/mutex32-mcs-finalize-v2.log 2>&1
python3 bench/archive_run.py --base "$RUN" --output "${RUN}-archives" \
  --health "$RUN/health.json" --group baseline=baseline --group candidate=candidate \
  --group old256=old256 --group locality256=locality256 \
  --group checks_candidate=checks-candidate --group checks_locality256=checks-locality256 \
  > /tmp/mutex32-mcs-archive.log 2>&1
python3 "$RUN/export-compact.py" --base "$RUN" --archives "${RUN}-archives" \
  --output "${RUN}-compact" > /tmp/mutex32-mcs-export.log 2>&1
```

The wrapper records `final-analysis-commands-v2.json` and bounds each analysis
subprocess to 240 seconds. The grouped archiver preserves the v1 and v2 helpers
alongside all source blocks. Source-host review uses the new explicit scope:

```sh
python3 "$REPORT/offline-archive-review-v2.py" --repo "$REPO" --raw "$RAW" --report "$REPORT" \
  --expect baseline=826faa6 --expect candidate=f4d359d \
  --expect old256=0324e60d6791948e9762a9916a50e8e026f073b0 --expect locality256=752fec1
python3 "$REPORT/offline-statistics-review-v2.py" --raw "$RAW" --report "$REPORT" \
  --arms baseline candidate old256 locality256
```

The arithmetic audit independently reconstructs all 72 windows and each
cohort's median, range, measured entry/returned share and whole-session batch
ratio. Source/archive review binds the v2 analysis helper hashes and original
matrix role flags. Synthetic entries remain distinct from explicit API returns;
batch ratios include warmup/checks. Sequential blocks, mixed execution classes
and overlapping ranges retain the same interpretation limits as the original
plan. Failed or excluded attempts require explicit preserved archive groups,
not deletion or a changed acceptance predicate.
