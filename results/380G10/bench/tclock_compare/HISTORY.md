# Spin/mutex benchmark evidence index

The spin/mutex optimization phase closed on 2026-10-09. Reports apply to their frozen source
and environment; cleanup does not rerun their measurements. Raw evidence archives
remain under ignored `results/380G10/raw/legacy/` and historical guest
`/root/kdlock-evidence/`. See [the machine layout](../../../README.md) for
relocated paths and compatibility links.
A fresh checkout includes compact results, not those original run directories.
The separate [rwlock benchmark guide](../../../../bench/rwlock_compare/README.md) indexes the
ABI1 cacheline and ABI3 RCUHT results; [all benchmarks](../../../../bench/README.md) links both
families.

## Final report

| Report | Scope |
| --- | --- |
| [Protocol simplification and final baseline](20261008-protocol-simplification/README.md) | 2,286 trial sessions; final 540-session spin/mutex comparison at all 15 counts under `nopvspin`; rejected candidates, complete statistics, audits and archive identities |

The performance target remains unmet. [Performance status](../../../../docs/PERFORMANCE.md)
records the closed scope and deferred designs.

## Earlier retained report

| Report | Scope |
| --- | --- |
| <a id="mutex-priority-trials"></a>[Mandatory-JIT mutex trials](20261008-mutex-priority-trials.md), [statistics](20261008-mutex-priority-trials-statistics.csv), [samples](20261008-mutex-priority-trials-samples.csv) | 306 sessions at 16/36 threads; rejected retention/entry/service candidates. This report family is retained alongside existing local edits. |

## Superseded reports in Git

The 32 report, chart and data artifacts below were removed from the working tree
at closeout. Their exact bytes remain in commit
`cb1629a3788f5c0b75383b9761a8b1838c784581`. Each report links its associated
statistics, audits and evidence manifests in that same Git snapshot. For local
retrieval, use:

```sh
git show cb1629a:bench/tclock_compare/results/20261008-hash-diagnosis.md
```

| Record | Purpose |
| --- | --- |
| <a id="hash-diagnosis"></a>[2026-10-08 hash diagnosis](https://github.com/hailongeric/kdlock/blob/cb1629a3788f5c0b75383b9761a8b1838c784581/bench/tclock_compare/results/20261008-hash-diagnosis.md) | 90 unprofiled and 72 diagnostic sessions under `nopvspin`; NUMA controls, profiles and attribution limits |
| <a id="pre-nopvspin-matrix"></a>[2026-10-08 spin/mutex matrix](https://github.com/hailongeric/kdlock/blob/cb1629a3788f5c0b75383b9761a8b1838c784581/bench/tclock_compare/results/20261008-threeway-spin-mutex.md) | 540 samples at `009e8e3` before `nopvspin`; keep its boot policy separate |
| <a id="mutex-followup"></a>[2026-10-03 mutex follow-up](https://github.com/hailongeric/kdlock/blob/cb1629a3788f5c0b75383b9761a8b1838c784581/bench/tclock_compare/results/20261003-mutex-followup.md) | Earlier full matrix, distributions and protected rechecks |
| <a id="spin36-analysis"></a>[2026-09-28 spin36 investigation](https://github.com/hailongeric/kdlock/blob/cb1629a3788f5c0b75383b9761a8b1838c784581/bench/tclock_compare/results/20260928-spin36-analysis.md) | Hash/cacheline, NUMA, PMU and UBSAN controls |
| <a id="packed-continuation"></a>[2026-09-28 packed continuation](https://github.com/hailongeric/kdlock/blob/cb1629a3788f5c0b75383b9761a8b1838c784581/bench/tclock_compare/results/20260928-packed-continuation.md) | Spin packet geometry, ACK and regression evidence |

## Earlier reports in Git

Superseded narrative and duplicate charts have been removed from the working tree.
Every report below is preserved at fixed commit `e533214`, including failed
candidates, source identities, archive hashes and original statistical policies.
To read locally, use `git show e533214:<path>`.

| Date | Fixed report |
| --- | --- |
| 2026-09-24 | [Warmed cacheline peaks and retained observation policy](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260924-warmed-peak.md) |
| 2026-09-25 | [One/eight-cacheline comparison](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260925-c1-c8-warmed-peak.md) |
| 2026-09-26 | [Cacheline matrix through 36 threads](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260926-c1-through36.md) |
| 2026-09-26 | [Targeted spin cleanup checks](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260926-cleanup.md) |
| 2026-09-26 | [Cross-node bounded batching](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260926-cross-node.md) |
| 2026-09-26 | [NUMA follow-up and short-batch regression](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260926-numa-followup.md) |
| 2026-09-26 | [Initial NUMA batching](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260926-numa.md) |
| 2026-09-26 | [Prefetch, diagnostics and heat checks](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260926-prefetch-unlock.md) |
| 2026-09-27 | [End-to-end memory and generated-code review](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260927-flow.md) |
| 2026-09-27 | [Repeated-operation cleanup](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260927-followup.md) |
| 2026-09-27 | [Hash translation and provider optimization](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260927-hash-optimization.md) |
| 2026-09-27 | [Timed hash comparison](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260927-hash-peak.md) |
| 2026-09-27 | [Hash helper inlining and unlock](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260927-hash-runtime.md) |
| 2026-09-27 | [Hash36 profiles and batch tuning](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260927-hash36-profile.md) |
| 2026-09-27 | [Rejected heat-only admission candidates](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260927-heat-thresholds.md) |
| 2026-09-27 | [MCS 1024 ratio tuning](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260927-ratio-window.md) |
| 2026-09-27 | [Full spin cacheline checkpoint](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260927-spin-checkpoint.md) |
| 2026-09-27 | [Bounded refill and regression recheck](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260927-spin-refill.md) |
| 2026-09-28 | [NUMA investigation and initial three-arm mutex work](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260928-numa-mutex.md) |
| 2026-10-03 | [Earlier mutex optimization and remaining regressions](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20261003-mutex-optimization.md) |

Older removed reports are indexed in the fixed
[direct-runner history](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/HISTORY.md)
and [early spin history](https://github.com/hailongeric/kdlock/blob/e533214/bench/spin_cacheline/results/HISTORY.md).
Use those checkouts only for historical reproduction; their commands are not
current operating instructions.
