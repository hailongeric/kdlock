# Benchmark evidence index

Reports describe their own frozen source and environment. They are historical
measurements, not performance reruns of a later cleanup commit. Raw archives stay
under ignored `bench/.tmp/` and guest `/root/kdlock-evidence/`; they are not deleted
by source cleanup and are not shipped in a new checkout.

## Retained reports

| Report | Purpose |
| --- | --- |
| [Final mutex matrix](20261003-mutex-followup.md) | All 15 thread points; acceptance still fails across all workloads |
| [Mutex statistics](20261003-mutex-followup-statistics.md), [JSON](20261003-mutex-followup.json) | Full valid distributions and targeted rechecks |
| [Spin36 investigation](20260928-spin36-analysis.md) | Hash/cacheline, NUMA, PMU and UBSAN attribution limits |
| [Packed continuation check](20260928-packed-continuation.md) | Current spin packet geometry, ACK and regression evidence |

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
