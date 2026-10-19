Fresh traffic-round pipe evidence. Plain timing and measured return counters are separate from whole-session diagnostics and instrumented profiles.

| Arm | Workers | Plain Mops/s median [min, max] | Change vs baseline | Change vs old256 | Measured returned JIT | Whole-session bodies/combiner median | Whole-session native-fast median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 8 | 5.276 [4.854, 5.641] | +0.00% | -24.02% | 74.63% | 37.31 | 17.44% |
| baseline | 60 | 3.666 [3.617, 3.696] | +0.00% | -32.24% | 85.87% | 66.25 | 13.22% |
| fetchadd | 8 | 5.119 [5.117, 5.451] | -2.98% | -26.28% | 84.54% | 42.37 | 16.97% |
| fetchadd | 60 | 3.763 [3.758, 3.764] | +2.62% | -30.46% | 86.72% | 67.88 | 12.19% |
| old256 | 8 | 6.943 [6.446, 7.094] | +31.61% | +0.00% | 96.83% | 311.28 | 2.66% |
| old256 | 60 | 5.411 [5.279, 5.417] | +47.58% | +0.00% | 94.98% | 127.57 | 4.92% |
| hint | 8 | 5.198 [5.025, 5.258] | -1.47% | -25.14% | 83.98% | 35.14 | 14.47% |
| hint | 60 | 3.716 [3.698, 3.776] | +1.35% | -31.32% | 86.73% | 67.44 | 11.99% |
| inline | 8 | 5.442 [5.412, 5.463] | +3.16% | -21.62% | 87.88% | 48.11 | 13.44% |
| inline | 60 | 3.735 [3.727, 3.743] | +1.88% | -30.97% | 87.33% | 67.34 | 11.66% |

The profile fractions and symbol costs describe the instrumented sessions below; they do not replace the plain results.

| Arm | Workers | Profile returned JIT | Plain returned JIT | Ref acquire % | Ref put % | Hint/retry family % | Worker samples |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 8 | 0.81% | 74.63% | 0.43 | 0.09 | 0.23 | 3223 |
| baseline | 60 | 84.89% | 85.87% | 2.25 | 1.51 | 0.55 | 24146 |
| fetchadd | 8 | 86.40% | 84.54% | 6.60 | 4.69 | 1.24 | 3218 |
| fetchadd | 60 | 83.43% | 86.72% | 2.05 | 1.65 | 0.52 | 24163 |
| old256 | 8 | 91.62% | 96.83% | 0.00 | 0.00 | 0.00 | 3221 |
| old256 | 60 | 94.51% | 94.98% | 0.00 | 0.00 | 0.00 | 24173 |
| hint | 8 | 83.16% | 83.98% | 6.19 | 4.02 | 4.94 | 3221 |
| hint | 60 | 85.18% | 86.73% | 1.80 | 1.49 | 1.29 | 24180 |
| inline | 8 | 79.59% | 87.88% | 6.29 | 4.46 | 2.70 | 3230 |
| inline | 60 | 85.30% | 87.33% | 2.18 | 1.44 | 0.45 | 24175 |

Limits:

- This is the fresh traffic round only; no prior-round measurements are pooled.
- Three sequential plain repeats provide observed medians/ranges, not confidence intervals or isolated hardware effects.
- Measured returned JIT shares pool only measured operations within one plain cohort; whole-session counters additionally contain warmup and checks.
- Bodies per combiner is an aggregate ratio, not a batch-size distribution. Native-fast counts use approximate admission diagnostics, not ownership records.
- Missing suppressed CPU ratio rows leave full-cohort native-fast and admission residuals unknown. Known-only rows are separately labelled.
- Profiles have one repeat per configuration and are unscored. Their execution mix can differ substantially from the corresponding plain cohort.
- Flat weighted samples cannot count CAS retries or memory coherence transactions. Inlining and code-scope changes affect symbol attribution.
- No claim of universal improvement or complete recovery of the old256 performance gap follows from this table.
