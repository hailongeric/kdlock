# Offline evidence import

Collection is coordinated by the root agent. This guide does not authorize a
second VM run, synchronization during a run, or changes to frozen inputs.

`archive-guest.py` runs only in the idle guest after the final retained
`health.json` confirms idle. It creates a new sibling archive directory and
assigns every top-level evidence path, including logs and command receipts, to
`screens`, `profiles`, `tests`, `main`, `reference` or `metadata`. Unknown names
are retained as metadata. Copy orchestration scripts into the completed base
before this capture if they otherwise exist only in `/tmp`.

```sh
python3 /tmp/kd-rwsem-opt-20261018/archive-guest.py \
  --base /mnt/kdlock-builds/rwsem-opt-20261018
```

The default output is `/mnt/kdlock-builds/rwsem-opt-20261018-archives`. Its
`archives.json` records the guest base, archive prefix, health hash, every
compressed hash, input inventory and final idle confirmation. `completed:false`
or a timeout is not a successful archive capture. Keep partial files and the
failure receipt for diagnosis; never delete evidence to retry.

Host commands below run from this report directory; `captures` is an example
archive directory. The actual imported archives and exported receipts are under
`../../raw/bench/rwsem-optimization-20261018/`. The supplied `runs.json` already
points to those inputs.

After transfer, run `verify-archive.py` on `380G10` for each archive, using a new
receipt-export directory per group. For example:

```sh
python3 verify-archive.py \
  captures/screens.tar.gz verification/screens.json \
  --archives-json captures/archives.json --extract-receipts receipts/screens
```

The verifier checks the transferred archive's guest hash and every entry in
every source/binary manifest. It reads the tar stream without executing source
or extracting links, modules or source files. It exports only the seven runner
JSON receipts and additional profile JSON receipts. Variable archive prefixes
come from `archives.json`; legacy single-run captures can instead provide
explicit `--guest-base` and `--archive-prefix`. A successful `status:PASS`
receipt is required; failures produce `status:FAIL` and exit nonzero.

1. Wait for the runner's normal exit and confirmed worker/provider/source drain.
   A timeout is not drain. Preserve failures and rejected candidates alongside
   successful runs. Copy each completed run's receipts to its own host directory:
   `plan.json`, `records.json`, `summary.json`, `parity.json`,
   `source-sha256.json`, `binary-sha256.json`, and `environment.json`.
2. Keep the original immutable evidence archive, its SHA256, command receipt,
   stdout/build logs, session records, publication images, source snapshot and
   module hashes. The compact receipts support analysis; they do not replace
   the full archive. Verify transferred file hashes against the captured guest
   hashes. Do not synthesize records from `summary.json` alone.
3. Map each run name to its receipt directory. A single-run `.tar.gz` archive is
   also accepted: the analyzer reads JSON members without extracting files.
   Multi-run archives with ambiguous top-level receipts must first be imported
   into separate receipt directories. Relative paths resolve against the map.
   Keep candidate names attached to their actual frozen source manifests; do
   not relabel a source version because a different candidate was selected.

Example `runs.json` (include optional candidate keys only when available):

```json
{
  "baseline-grid": "/path/to/rwsem-delegation-20261018/guest-evidence.tar.gz",
  "baseline-screen": "receipts/screens/baseline-screen",
  "poll-screen": "receipts/screens/poll-screen",
  "split-screen": "receipts/screens/split-screen",
  "long-screen": "receipts/screens/long-screen",
  "grant-screen": "receipts/screens/grant-screen",
  "grants128-screen": "receipts/screens/grants128-screen",
  "xlong-screen": "receipts/screens/xlong-screen",
  "baseline-repeat-screen": "receipts/screens/baseline-repeat-screen",
  "final-grid": "receipts/main/final-grid",
  "final-reference": "receipts/reference/final-reference",
  "baseline-profile": "receipts/profiles/baseline-profile",
  "final-profile": "receipts/profiles/final-profile"
}
```

These paths assume each archive was verified with
`--extract-receipts receipts/GROUP`, where `GROUP` is `screens`, `main`,
`reference` or `profiles`. The verifier removes the common archive prefix
`rwsem-opt-20261018` and retains the run directory. Point profile entries at
their profile root, not its nested `rwsem` directory. Do not point the analyzer
at a multi-run `screens.tar.gz` or `profiles.tar.gz`: their receipt names are
ambiguous until the verifier exports separate run roots. The accompanying
`final-runs.template.json` uses this layout and the existing historical baseline
archive. Remove optional screen keys only if those runs were never attempted;
retain attempted partial/failed runs so missing evidence stays explicit.

The optional profile directories contain `function-count-summary.json` and,
when captured, `diagnostic.json` and `result.json`. Retain their raw per-CPU
profiles and tracing restoration receipts in the original profile archive.
These diagnostics never supply scored throughput.

Run only the offline analyzer on `380G10`, with a new output directory outside
all evidence directories:

```sh
python3 report.py runs.json analysis-NEW
```

The full rwsem grids expect 756 sessions each. Each c01 screen expects 48
sessions: Native/KD, 1%/20% writes, 1/8/32/60 workers, three repetitions. The
separate spinning-rwlock reference expects 270 sessions: Native/TCLock/KD,
c01/c08/RCUHT, both mixes, 1/8/32/36/60 workers, three repetitions. Missing runs
or receipts remain explicit. Optional `long-screen`, `grant-screen`,
`grants128-screen`, `xlong-screen` and `baseline-repeat-screen` are absent from
the report when omitted from the map. The archiver automatically captures all
these `*-screen` directories and their `*-probe`, log and command sidecars.

Review `analysis.json` coverage and input hashes before citing results.
`groups.csv` preserves source/run/variant/JIT strata, including partial groups;
`screen-points.csv` includes every candidate and both baseline comparisons.
Historical full-grid and fresh-screen baselines remain separate even when their
source hashes match. Whole-run ranges and separate Native controls expose run
variability. A mixed-status point has no pooled three-repetition score; a lower
observed median or peak is retained, without a significance claim. Source
differences against both baselines are in `source-differences.json`. When a
`baseline-repeat-screen` is supplied, it stays a distinct later control: every
screen also receives a comparison with it, and source differences against it
are captured. Confirm its source manifest before interpreting it as baseline
bracketing; the name alone does not establish source equivalence. No candidate
is designated selected by the analyzer, and rejected candidates remain evidence.

For a second arithmetic path after the final receipts arrive, run:

```sh
python3 independent-replay.py runs.json replay-NEW.json \
  --compare analysis-NEW/analysis.json --require-final
```

This helper imports no repository or analyzer programs and generates no figures.
It reconstructs rates and warmed peaks from raw records/samples, checks worker
progress, deterministic mixes, checksums, recorded protected effects, drain and
JIT counter deltas, and compares separate groups and point ratios with the main
analysis. Its output retains total returned-JIT completions, every JIT split and
the six 60-worker before/after rows. `--require-final` requires both full grids
and the separate rwlock reference; omit it only for an explicitly partial screen
replay. A successful offline replay does not constitute a new lock-correctness
test or a performance significance claim.

For the final validation summary, after all archives are captured and transferred:

```sh
python3 ../../tests/rwsem-optimization-20261018/validation-report.py \
  captures/archives.json captures validation-NEW
```

The helper reads only the `tests`, `metadata` and `profiles` tar groups. It
checks their compressed hashes and captured source/binary manifests, then emits
`validation.json` and a README draft. The selected xlong probe, two basic C
programs, 36 functional sessions, four ordinary-shell controls and four strict
JIT sessions remain separate. Earlier poll/split/long/grant probes remain
experimental evidence; grant's 13-field payload is not confused with the
selected probe's 12 fields. Profiles include exact tracing restoration and raw
per-CPU hash checks and never supply performance scores. Missing or failed final
evidence produces a nonzero exit and an explicit report, not a pass inferred
from a planned command or published image.

The tracked `README.md`, `diagnosis.md` and `provenance.md` add reviewed narrative
to the analyzer output. Regeneration into a new directory reproduces numerical
tables and figures, not those editorial additions. The archived commands and
targeted-review helper retain their original capture paths; adjust its `ROOT`,
`WORK`, `ANALYSIS`, `RAW` and `OLD` constants only when reproducing that extra
review in another directory, keeping the retained inputs unchanged.
