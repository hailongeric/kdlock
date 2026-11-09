# V3 independent measurement audit

**The archived fixed point passes: 25,670.9 mmap/munmap pairs per nominal second over ten samples, with no compiler interval overlapping the entire fixed application or its delivered sample window.** This is counter-enabled, unscored throughput evidence. It is not a quiet measurement, strict peak qualification or a Native performance comparison.

Analysis was offline only. No target PCs, per-record reasons or lock states were decoded; no VM action, workload, build, test or candidate edit was performed.

Archive: retained raw root `collection/evidence.tar`; 897218560 bytes; SHA256 `3f58be968edf403e45bfbc793a4b3f1a87915b9d2a074c22b0f2a6e3785c53e6`. Exact timing is in [phase-timing.json](phase-timing.json), with verdicts in [validation.json](validation.json) and [measurement-audit.json](measurement-audit.json). The complete original `measurement-review.json` is retained under the raw root's `controls/` directory. The archive is unchanged.

## Fixed application and compiler exclusion

- All 19 compiler children succeeded. Their complete `evidence/run/daemon.log` metric sequence equals the 19 records before and after the fixed point.
- No logged compiler interval overlaps either fixed-application interval below. The final compiler finished **16.768834281 seconds before** the fixed application started.
- The fixed point is COMPLETE/stable/conservation_passed, with application return code 0, passed=true and drained=true. Registry generations remain mmap 7 and munmap 12 before the app, at both sample callbacks and after it. The superseded-report counter remains 2 throughout.

| Recorded interval | CLOCK_MONOTONIC start (s) | End (s) | Duration (s) | Compiler overlap (s) |
| --- | ---: | ---: | ---: | ---: |
| Whole fixed application | 2447.077521715 | 2463.138030688 | 16.060508973 | 0 |
| Delivered ten-sample window | 2453.110374583 | 2463.111654129 | 10.001279546 | 0 |

The first interval is the recorded upstream process lifetime including setup, six warmup samples, ten final samples and normal worker reaping. The second is PTY line delivery from the last warmup boundary through the final measured boundary. It is not an exact execution-time clock for the application counter updates. Callback completion lags its begin/end line by 0.000438396/0.000494894 seconds; callback-finish timestamps span 10.001336044 seconds.

Rate calculation is the unchanged upstream convention: 256,709 pairs summed over ten nominal one-second samples, divided by ten = **25,670.9**. The observed delivery interval does not replace that nominal denominator.

## Warmup, compilation and phase gaps

The campaign origin derived from its recorded deadline minus 3600 is 88.240025544 monotonic seconds. First upstream application start is 94.015679632, a **5.775654088-second** construction/preparation/check interval. This excludes earlier host/boot/source/artifact preparation and is not a separately instrumented setup routine.

| Application phase | Recorded process duration (s) | Overlapping compiler intervals (s) | App verdict |
| --- | ---: | ---: | --- |
| Preparation application | 730.152563558 | 728.801989212 | rc0 / passed / drained |
| Continuation 01 | 8.038198684 | 7.918610117 | rc0 / passed / drained |
| Continuation 02 | 8.038291753 | 7.916888188 | rc0 / passed / drained |
| Continuation 03 | 8.038693234 | 7.907949276 | rc0 / passed / drained |
| Continuation 04 | 8.085142872 | 7.956682344 | rc0 / passed / drained |
| Continuation 05 | 8.039106301 | 7.903054236 | rc0 / passed / drained |
| Continuation 06 | 8.040048935 | 0.000000000 | rc0 / passed / drained |
| Fixed application | 16.060508973 | 0.000000000 | rc0 / passed / drained |

The long preparation contains 730 delivered samples. Six continuations completed, and only continuation 06 has an unchanged generation history. Compiler work overlaps training applications as intended; it does not overlap the separate fixed application.

| Gap after application → next application | Total gap (s) | Logged compiler portion (s) | Outside logged compiler intervals (s) |
| --- | ---: | ---: | ---: |
| Preparation application → Continuation 01 | 98.730451577 | 94.072389549 | 4.658062028 |
| Continuation 01 → Continuation 02 | 308.010800480 | 303.048502893 | 4.962297587 |
| Continuation 02 → Continuation 03 | 399.497770737 | 394.287848932 | 5.209921805 |
| Continuation 03 → Continuation 04 | 262.498322643 | 257.114087221 | 5.384235422 |
| Continuation 04 → Continuation 05 | 263.204308663 | 257.659900478 | 5.544408185 |
| Continuation 05 → Continuation 06 | 239.726985363 | 233.959357300 | 5.767628063 |
| Continuation 06 → Fixed application | 2.961157283 | 0.000000000 | 2.961157283 |

**These gaps are not pure settlement time.** They combine post-body compiler completion, export/upload, quiescent checks, artifact copying, receipt/kernel/source verification and next-start work. Those components have no separate direct timestamps here. The last 2.961157283-second gap follows the already stable continuation 06 and precedes the fixed application.

Learning application process intervals sum to 778.432045337 seconds; compiler intervals overlap 768.405173373 seconds of them. Between-application gaps total 1574.629796746 seconds, including 1540.142086373 seconds covered by logged compiler intervals and 34.487710373 seconds outside them.

All serial compiler child wall intervals total 2308.547259746 seconds. Campaign origin to fixed-application start is 2358.837496171 seconds. Application and compiler times overlap and must not be added as independent costs.

## Generation and learned-history stability

| Phase | Before mmap/munmap generations | After mmap/munmap generations | Stable |
| --- | --- | --- | --- |
| preparation | empty | 5/7 | false |
| continuation-01 | 5/7 | 6/8 | false |
| continuation-02 | 6/8 | 7/9 | false |
| continuation-03 | 7/9 | 7/10 | false |
| continuation-04 | 7/10 | 7/11 | false |
| continuation-05 | 7/11 | 7/12 | false |
| continuation-06 | 7/12 | 7/12 | true |

Aggregate retained batches comprise two empty seeds and 17 strict history additions. No update repeats its preceding same-root opaque learned input, and no cumulative history entry is removed. mmap ends with four CALL plus two IJ entries (sequences 1–6); munmap ends with ten CALL plus three IJ entries (sequences 1–13). Frozen snapshot overflow counters/flags remain zero. These normal history comparisons decode no individual targets.

The sixth continuation validates the final generation pair through a complete unchanged application. The fixed point then preserves the same registry, report counters and compiler metrics. These are scoped stability and returned-body observations for this workload/run, not whole-kernel equivalence or proof that every possible path has been learned.

## Counter interpretation

Whole-application snapshots are taken outside the drained upstream lifetime and conserve exactly:

| Root | Selected/submitted/bound/JIT entered/returned | Handback | Local or canceled |
| --- | ---: | ---: | ---: |
| mmap | 398610 | 0 | 0 |
| munmap | 398608 | 0 | 0 |

The active measured-window callbacks are not atomic/drained boundaries:

| Root | Selected/submitted | Bound/JIT entered | Returned |
| --- | ---: | ---: | ---: |
| mmap | 256698 | 256701 | 256703 |
| munmap | 256701 | 256701 | 256704 |

The small differences must be preserved; do not force conservation or use these callback deltas as an exact join to the 256,709 application pairs. The archive explicitly states that transport/callback counters are not sampled atomically with application counters. The conservation verdict applies to whole_application_delta.

The nested generic application record contains scored=true/instrumentation=none. It does not model the provider observation overlay. The point and campaign correctly retain selected-service-counters, scored=false, quiet_performance_accepted=false and performance_accepted=false. Report the counter-enabled classification.

## Retirement and evidence boundaries

`evidence/run/result.json` remains MEASURED_RETIREMENT_PENDING with its original pre-finalization generic booleans. The separate `evidence/run/finalization.json` and `evidence/normal-result.json` both pass: campaign_complete, exact retirement, drain and final idle are true; controller/finalizer return codes are 0. This audit does not rewrite those original receipts.

No Native reference point is present in this audit; no gain or strict performance acceptance follows. The fixed point reports zero whole-application handbacks and complete returned JIT bodies for both selected roots, without introducing targeted instruction/ownership tracing.

## Human wall-time markers

These are retained file modification times, explicitly America/Los_Angeles (PST, UTC-08:00); they are not substitutes for the monotonic phase boundaries above. Raw epochs remain unchanged in JSON.

| File marker | America/Los_Angeles time |
| --- | --- |
| `evidence/controller-command.json` | 2026-11-09 08:52:53.287811 PST |
| `evidence/finalizer-command.json` | 2026-11-09 09:32:29.061697 PST |
| `evidence/run/processes/application/command.json` | 2026-11-09 09:32:12.430215 PST |
| `evidence/run/processes/learning/learning-00/command.json` | 2026-11-09 08:52:59.368165 PST |

Independent source/archive review found no material mismatch in the stable point, rate, compiler exclusion, generations, whole-application counters or retirement.
