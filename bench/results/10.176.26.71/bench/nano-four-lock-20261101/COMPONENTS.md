# Three-point component comparisons

These are separate source versions, each with one round per selected point. The retained baseline is `87a3a41f1ba3746b7716e611541068bd3ab6e975`; it was not rerun to replace a score. The combined candidate is `1ba4cc6e59f5451eaecafcf1c3a36861d026e5d9`.

- Reader-entry only: `252825407cd40d91a32010e82c8c111a768e7fcf`; exact baseline OSQ restored.
- OSQ64 only: `4df80e5a14d0368b07c5c0a63b49f0b79b80ca4f`; exact baseline rwsem entry/release restored.

Both passed the five affected unit groups, basic returned-JIT mutex/rwsem checks and live local mutex/rwsem API checks before profiling and timing. All six scored sessions returned correct data and drained. This narrow comparison cannot establish a full-grid regression pass.

| Workload/placement/workers | Component | Baseline Mops/s | Both Mops/s | Component Mops/s | Component/baseline | Returned JIT |
|---|---|---:|---:|---:|---:|---:|
| c01 w001 contiguous/1 | osq-poll-only | 1.7889 | 1.9174 | 1.7858 | -0.17% | 0 |
| c01 w001 contiguous/1 | rwsem-reader-only | 1.7889 | 1.9174 | 1.9171 | +7.17% | 0 |
| c01 w001 contiguous/8 | osq-poll-only | 11.3437 | 8.8599 | 7.9820 | -29.63% | 0 |
| c01 w001 contiguous/8 | rwsem-reader-only | 11.3437 | 8.8599 | 7.8539 | -30.76% | 0 |
| c16 w020 split20/20 | osq-poll-only | 3.3145 | 3.3972 | 3.5161 | +6.08% | 813407 |
| c16 w020 split20/20 | rwsem-reader-only | 3.3145 | 3.3972 | 3.0500 | -7.98% | 658031 |

## Eight-worker unscored cycle profiles

Flat sampled worker-cycle shares; these percentages are neither score ratios nor inclusive elapsed times. No baseline c01/w1 eight-worker cycle profile was captured, so per-instruction cost changes cannot be assigned from this table alone.

| Version | Read entry | Read release | OSQ lock | Outlined read slowpath | Common rb_run |
|---|---:|---:|---:|---:|---:|
| both | 25.31% | 19.46% | 6.30% | 4.25% | 41.03% |
| rwsem-reader-only | 19.94% | 14.29% | 12.22% | 5.09% | 41.72% |
| osq-poll-only | 17.56% | 5.43% | 3.62% | 0.00% | 69.44% |

[Exact scores and worker CPU-time data](components.csv), [profile summaries](component-profiles.json), [correctness receipts](correctness/components.json). Each observed negative remains in the table; no value is substituted into a full-grid candidate result.


## Interpretation

The single-worker improvement follows the reader-entry component: +7.17%
alone, versus -0.17% for OSQ64 alone and +7.18% for both. That agrees with
the smaller fast-success frame and reduced release work. OSQ waiting cannot
explain the single-worker gain.

The eight-worker loss persists with either component alone: -30.76% for
reader-entry only and -29.63% for OSQ64 only, versus -21.90% for both. Each
records zero returned JIT bodies, about 16 summed CPU-seconds and balanced
worker completion. This excludes a unique explanation requiring both edits,
and does not support parking or delegated-body execution as the dominant cost.
It does not prove that either edit independently causes the entire baseline
gap: a single original baseline score and no matching baseline c01/w1 cycle
profile leave timing variability and instruction/arrival-pattern effects
unseparated. Neither component is accepted on these data.

At split-node c16/w20, OSQ64 alone improves 6.08%; reader-entry alone loses
7.98%; together they improve 2.49%. These are separate observed results, not
additive contributions. The scoped polling change is worth retaining as an
isolated experiment, but its eight-worker loss prevents a general performance
claim. The full-grid candidate's favorable c16 averages do not replace any of
these component scores.
