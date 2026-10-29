# Kernel proxy nano comparison, October 30

All **210 baseline KD points and 630 candidate Native/TCLock/KD points** passed
offline validation on their first complete replay. Of the 210 matched KD
coordinates, **108 have lower whole-run throughput, sampled peak throughput,
or both**. This round does **not** establish the required no-regression result.
Strict host timing qualification remains failed; `performance_accepted` is false.
No positive point is treated as an accepted gain, and no loss is discarded as
noise. One observation per point cannot determine variance or causality.

Measured sources are baseline `acfa33a5adbc1ec6a8aa3bb02f0107052b32a20f` and
candidate `8446f4ecb08816380a4c233197a8ce5e4d333aac`. The later original-task
instruction service at `ace6eaf882c54bc822b8fe4f4eea4d85fc605473` is a different
generation; its VM checks are not included. Real API, localized mmap, kernel
replacement and unchanged will-it-scale `mmap1` acceptance remain separate.
The earlier milestone is preserved verbatim in [baseline-report.md](baseline-report.md),
with all baseline artifacts unchanged. No measured point was repeated or replaced.

## Matched observations

`c01` is one padded cacheline counter; `c16` is sixteen. `w1`, `w20`, `w100` mean
1%, 20%, 100% writes. Each point has 256 register-only post-work rounds, 48,000
preparation operations per worker and one 2-second measurement. Peak throughput
uses the existing 300-ms window after 300-ms settling, sampled every 10 ms.
Warmup and measurement are separate. Rwsem/rwlock reads always run locally.

Workers are `1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60`. The VM
has 64 vCPUs: node 0 CPUs 0–31, node 1 CPUs 32–63. Workers use a prefix from
CPU 0; collector CPU 63 is separate. Thus 20 and 32 workers stay on node 0;
60 workers span both nodes. Versions, topologies and API shells are not pooled.

| Lock | Points | Whole losses | Peak losses | Either metric |
| --- | ---: | ---: | ---: | ---: |
| Mutex | 42 | 14 | 13 | 14 |
| Rwsem | 84 | 43 | 39 | 44 |
| Rwlock | 84 | 44 | 47 | 50 |
| Total | 210 | 101 | 99 | 108 |

Individual candidate KD whole-throughput changes against fresh baseline KD:

| Workload | 20 workers | 32 workers | 60 workers |
| --- | ---: | ---: | ---: |
| Mutex c01 w100 | +2.55% | −0.13% | +0.49% |
| Mutex c16 w100 | +1.50% | +2.65% | +2.16% |
| Rwsem c01 w1 | +0.71% | +1.45% | −1.58% |
| Rwsem c01 w20 | −0.60% | −1.33% | +3.44% |
| Rwsem c16 w1 | +6.93% | +2.50% | −0.08% |
| Rwsem c16 w20 | −2.34% | −0.88% | −0.05% |
| Rwlock c01 w1 | +2.00% | −2.87% | +1.65% |
| Rwlock c01 w20 | +0.04% | −5.36% | −1.49% |
| Rwlock c16 w1 | +1.74% | +0.57% | −1.35% |
| Rwlock c16 w20 | −3.05% | −1.72% | +0.06% |

These are observations, not significance tests. Full rates, peak changes and
same-candidate Native/TCLock ratios are in [selected-20-32-60.csv](selected-20-32-60.csv).
At 60 workers, KD/TCLock whole-throughput ratios remain 0.79 for rwsem c01 w20,
0.96 for rwsem c16 w20, 0.79 for rwlock c01 w20 and 0.64 for rwlock c16 w20.
The cross-node gap is still observed; its mechanism is not established here.

The largest whole losses include rwsem c01 w1 at 8 workers (−30.58%), rwlock c01
w1 at 6 (−18.08%) and at 16 (−11.50%). All three are **NO_JIT in both versions**.
Mutex c01 w100 at 5 loses 11.26% with returned JIT in both. Missing returned
JIT cannot explain every loss; added JIT fallback cannot by itself explain the
largest rwsem observation.

Baseline KD has 131 `RETURNED_JIT` and 79 `NO_JIT` points; candidate KD has 130
and 80. There are 129 returned/returned pairs, 78 no-JIT/no-JIT pairs and three
changed classifications, all retained. There are no partial JIT or unscored
matched points. NORMAL publication alone is not a returned-body receipt;
TCLock delegation remains `UNMEASURED`.

## Measured binary evidence and attribution limits

Static inspection uses actual archived measured ELFs authenticated against
their binary maps. No module or generated image executes on the source host.

| Evidence | Baseline | Candidate |
| --- | ---: | ---: |
| Provider `.text` bytes | 128,380 | 130,009 |
| `kd_exe_dispatch` bytes | 11,040 | 12,229 |
| DWARF `kd_spin_batch` bytes | 200 | 208 |
| Spin `run_combiner` stack reservation | 0x110 | 0x120 |
| Spin batch prefix initialization | 24 qwords | 25 qwords |

All ten KD workload executable text-section maps are byte-identical before
relocation. This does not prove identical runtime addresses or placement.
Measured `kd_spin_node` stays 128 bytes, `kd_mutex_node` 320, `kd_mutex` 32 and
`kd_exec_frame` 656. The spin combiner contains new preemption/context checks;
they preserve required semantics and cannot simply be removed for performance.

Address-normalized disassembly for `kd_mutex_execute_cs`, `_kd_mutex_lock_abi`,
`kd_mutex_run_combiner`, `__kd_mutex_lock_slowpath` and `kd_down_read` is unchanged.
Several rwsem read/write functions also retain identical raw bytes. This does
not prove identical relocation targets or cache placement: for example,
`kd_mutex_run_combiner` moves from text offset 0x14e00 to 0x154b0.

The spin changes provide a concrete overhead hypothesis for rwlock writer
paths, not a measured causal contribution. They do not explain all NO_JIT losses.
Code placement, interleaving and the unqualified timing environment remain
possible contributors. Further changes need their own identified measurements.
Function/section hashes, type sizes, disassembly and provenance are retained in
[binary-inspection/](binary-inspection/).

## Identity and validation

Both runs use `7.0.0-38-kdlock1`, boot `677b7afa-5358-4ece-a650-5f4a4adecd55`,
Build ID `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`. Actual mutex total/locality
limits and spin batch limit are all 1024: the former 768 cutoff is absent from
both versions. Optional mutex diagnostics are off; completion/heat observations
remain enabled. The recovery snapshot and kernel bundle were verified.

Candidate ran `2026-10-29T20:40:32.471188+00:00`–`2026-10-29T21:57:49.433861+00:00`.
Host endpoint ages are 21.220 seconds before and 2.746 after; baseline ages are
42.674 and 194.531 seconds. All meet the 300-second freshness bound and fixed
host/QEMU configuration matches. This does not establish continuous isolation
or repair strict qualification. Ordering was sequential, without randomized A/B.

Candidate replay authenticates 27,458 inventory paths, 23,958 regular files,
305 selected Git blobs and 624 compiler dependency receipts. Six stale leaves
are explicitly shown unused by selected source and build receipts. Every provider
reconstructs exactly from 111 captured production leaves plus 26 observation
hunks into 113 prepared leaves. Sixty actual measured module ELFs were retained,
including ten KD providers. This is tracked-Git plus explicit stale-file review,
not a pristine-whole-directory claim.

Raw archives remain in the ignored main-checkout
`bench/results/10.176.26.71/raw/bench/kernel-proxy-nano-20261030/` directory.
Captured identifiers remain unchanged. Retained report artifacts include:

- `candidate-validation.json`, `candidate-points.json`, `candidate-points.csv`:
  complete candidate replay.
- `comparison-validation.json`, `comparison-points.json`, `comparison-points.csv`:
  all matched observations; `observed-losses.json` retains all 108 either-metric
  losses using integer cross-products before rounding.
- `extra-source-review.json`, `candidate-host-after.json`,
  `candidate-retirement-proposal.json`: exact provenance. The proposal performs
  no retirement and later provenance/retirement operations do not alter this run.

The optional baseline workload-ELF extraction copied ten files, then rejected
the final non-profile `metadata` archive group before saving provenance. Its
failure note and subsequent byte-for-byte verification are retained under
`binary-inspection/`. Neither complete campaign audit required an adjustment or
rerun. This extraction issue did not change any archive or measurement.

## Offline reproduction

The baseline command remains in [baseline-report.md](baseline-report.md).
Run [verify_candidate.py](verify_candidate.py) with arguments retained in
`candidate-validation.json`, changing only outputs to new directories and
resolving local paths. It accepts explicit analyzer, archive/control, endpoints,
baseline extra review and trusted checkout. It emits the comparison invocation
after validation. The exact performed argv is in `final-analysis-argv.json`.
For replay use the exact executed [analyze_executed.py](analyze_executed.py), combined extras proof,
the same raw inputs/commits and a new output. `oracle.py`/`peak.py` run only after
their trusted-checkout bytes equal both measured commits. Archived code remains
data. No source-host build, test, module, daemon or timing run is involved.
