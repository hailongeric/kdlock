# Pipe phase and admission diagnostics

The independent [arithmetic review](statistics-review.json) passed 17,613 checks
over all twelve fresh sessions, including every whole/peak window. No archived
code or binaries were executed. The [audit log](offline-statistics-review.log)
records the result. These observations describe this sequential comparison;
the three-repeat ranges are not confidence intervals.

| Workers | Embedded / old median Mops/s | Embedded / old measured returned JIT | Embedded / old median whole-session bodies per combiner |
| ---: | ---: | ---: | ---: |
| 8 | 4.147 / 6.994 | 93.011% / 96.593% | 99.481 / 320.344 |
| 60 | 3.408 / 5.409 | 96.187% / 94.899% | 127.914 / 127.495 |

Returned fractions above divide summed measured returned completions by summed
measured operations within each arm/worker cohort. Body-entry and returned
counts match in every measured session. The batch figures use final provider
counters, including warmup and both oracle checks; they are aggregate ratios,
not distributions or measured-phase batch sizes. The 60-worker deficit occurs
despite higher measured returned-JIT fraction and similar whole-session batch
ratios, so a universal reduction in delegation is not supported by this run.

## Reconstruction and its limits

The exact JSON field is
`pipe_phase_diagnostics[].residual_after_2047_per_worker`. For each session:

```text
T = warmup.json.completed + measure.json.completed + 2 oracle calls
Ĉ = Σ over reported CPUs (1024 × ratio.checks + ratio.contentions)
F̂ = T − Ĉ
Ô = Ĉ − final_mutex_stats.jit_success − final_mutex_stats.origin_acquires
residual = Ô − 2047 × workers
```

`F̂` estimates outer native-fast calls. `Ô` is the remaining reconstructed
contended-call count, not an instrumented cold-admission counter. `origin_acquires`
counts the delegation path's physical acquisitions, not every local physical
acquisition. No auxiliary-state busy term exists in either arm.

These formulas perform exact arithmetic on retained diagnostics, but the
heat counters are approximate admission observations. Their source clears
the contention counter at a check after reaching **at least** 1024; a busy
table can delay that check. Thus `1024 × checks` is not a general lossless
lifetime counter. Every expected worker CPU row is present in this run. When
rows are suppressed, the helper leaves total estimates unknown and retains
only the observed partial sum. None of these estimates authorize ownership or
replace the separate exact drain/acquisition checks.

The conditional 2047 reference comes from the unchanged mutex heat code:
the initial CPU promotion can occur at failed attempt 1024, which also records
the first per-lock observation; the per-lock threshold is 1025 observations,
so the first admitted attempt is 2048. This assumes successful initial heat
promotion, one relevant lock identity and no subsequent cooling or other
admission refusal. The code checks failed-attempt counts in-band and reads
the TSC; there is no separate periodic warmup-monitor tick.

## Preserved exceptional residual

For `embedded32/pipe/pipebytes-query-n16-t08-r0-kdlock`:

```text
T = 6,053,888 + 8,294,656 + 2 = 14,348,546
Ĉ = 9,151,331
jit_success = 9,007,987; origin_acquires = 110,584
Ô = 32,760
residual = 32,760 − 2047 × 8 = 16,384
```

The remaining eleven sessions have zero residual under this reference. The
exception equals `2047 × 8 + 2 × 1024 × 8` before subtraction; it does **not**
equal `2 × 2047 × 8`, which is eight smaller. Additional cold/reheat windows
are compatible with increments of this size, but final snapshots do not
record the necessary CPU transition history or refusal reasons to establish
that explanation or its phase. All final reported CPU/lock heat gates are hot.

This same exceptional session has a reconstructed **whole-session** native-fast
fraction of 36.221%, while **measured** returned JIT is 93.727%. The counters
span different intervals; the former cannot be reported as measured fallback.
The residual remains an unexplained admission-accounting diagnostic, not
evidence of a runtime ownership failure. All sessions retain balanced reported
physical acquisition/release counts, drained waiter/node/task counts, and zero
reported handoff, JIT-not-ready, JIT-failure, context-busy, node-overflow and
frame-failure counters.
