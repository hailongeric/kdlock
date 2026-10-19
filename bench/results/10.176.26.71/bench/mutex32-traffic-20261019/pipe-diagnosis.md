The final 32-byte implementation improves this round's pipe median by 3.16%
at eight workers and 1.88% at 60 workers against the previous compact version.
It remains 21.62% and 30.97% below the fresh old256 comparison. These are
observed changes in three sequential repetitions, with overlapping ranges at
eight workers; they do not establish a general speedup.

The independent [arithmetic audit](statistics-review.json) passed 152,227
checks with zero issues. It reconstructed all 130 whole/peak measurements,
checked measured return counts and whole-session diagnostics, and independently
parsed all 136,990 samples in ten profiles. No retained code or binaries were
executed. The [fresh phase tables](pipe-phase-analysis.md) and their
[numeric receipt](pipe-phase-analysis.json) contain only this traffic round.

The plain results identify a continuing batching and execution-mix difference:

| Metric, eight / 60 workers | Previous compact | Final compact | Old256 |
| --- | ---: | ---: | ---: |
| Whole-run median Mops/s | 5.276 / 3.666 | 5.442 / 3.735 | 6.943 / 5.411 |
| Measured returned-JIT share | 74.63% / 85.87% | 87.88% / 87.33% | 96.83% / 94.98% |
| Whole-session median bodies per combiner | 37.31 / 66.25 | 48.11 / 67.34 | 311.28 / 127.57 |
| Whole-session median native-fast share | 17.44% / 13.22% | 13.44% / 11.66% | 2.66% / 4.92% |
| Whole-session median physical origin acquisitions per 1,000 JIT successes | 32.01 / 25.57 | 23.27 / 24.16 | 3.80 / 9.46 |

The first two rows describe measured operations. The remaining rows use
whole-session counters, including warmup and two redirected checks. Bodies per
combiner is an aggregate ratio, not a batch-size distribution. Heat-based
native-fast reconstruction is diagnostic and never substitutes for exact
ownership records. All worker ratio rows happen to be present in this round;
the audit continues to leave totals unknown when a row is suppressed.

For every 60-worker plain pipe run, reconstructed contended entries outside
JIT successes and physical origin acquisitions equal `60*2047` plus recorded
BUSY refusals. The final three runs have only 6, 9 and 6 BUSY refusals over
their whole sessions. There are no collisions, exhaustion, injected failures
or generation-race refusals in those final 60-worker runs. The data gives no
evidence that repeated cold admission or refusal is the continuing bottleneck
there. It instead records shorter batches and a larger native-fast share than
old256. Source-level reasoning makes slower producer circulation and shared
reference traffic plausible contributors; these measurements do not isolate
their individual causal costs.

At eight workers, subtracting the diagnostic `8*2047` startup term, BUSY and
generation-race refusals leaves zero in 13 of the 15 plain runs. The first
baseline and first fetch-add repeats retain unexplained residuals of 28,672
and 16,384. The report preserves them without assigning them to warmup or the
measurement interval. All 30 plain pipe logs end with hot CPU/lock states and
zero handoff, JIT-not-ready, JIT-failure, context-busy, node-overflow and
frame-failure counters. All indexed plain pipe runs have zero collision,
exhausted and injected-failure counters. Thus lower returned-JIT percentages
are not evidence of observed JIT body failures in this round.

The reference changes remove the CAS retry loop and reduce common-path
instruction work, as shown by the separately retained ELF inspections. They
do not eliminate the exact lifetime pins. At 60 workers, reference-acquire
and put account for 2.25% + 1.51% of baseline worker sampled period and
2.18% + 1.44% in the final profile. This is not evidence of a large measured
drop in coherence traffic. Flat samples do not count atomic retries or cache
line transfers, and inlining moves `try_ref` attribution into `get`. About
90% of worker sampled period remains in the polling slowpath; a serialized
delay can increase waiting elsewhere, so reference-symbol percentages do not
bound the throughput effect of reference traffic.

The baseline eight-worker profile is unsuitable for comparing reference cost
with the later profiles: it returned only 0.81% of operations through JIT,
against 74.63% in its plain cohort. The final eight-worker profile returns
79.59%, against 87.88% plain. All profile/plain pairs remain separate and
unscored. At 60 workers the mix is closer, but there is still only one profile
per version. No direct transaction count or dynamic CAS retry count was
collected.

The ablations also limit causal claims. Fetch-add alone improves the
60-worker pipe median 2.62% but lowers the eight-worker median 2.98%.
The cached-slot hint experiment does not improve both pipe cohorts and was
reverted. The final inline candidate improves eight-worker pipe 6.32% over
fetch-add while its 60-worker median is 0.73% lower. This supports retaining
the modest pipe-focused result with explicit mixed outcomes; it does not show
that the remaining old256 gap has been solved.
