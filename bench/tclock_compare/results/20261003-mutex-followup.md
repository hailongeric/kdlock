# Mutex follow-up: full thread set and execution costs (2026-10-03)

The acceptance set is 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 28, 32 and 36 workers. The goal is to avoid falling below TCLock across this set; a successful 16/36 screen is not full acceptance. This follow-up starts at `51493f2`, with the native-first pin and published-shadow read changes retained from the [earlier run](20261003-mutex-optimization.md).

All new builds and execution use the existing recovery guest, kernel `6.1.159-kdclobber2`, Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. The private KD benchmark provider defaults to UBSAN off. NUMA stays on. Each scored group has three rounds, 48,000 warmup operations per worker, two seconds of measurement, and the highest valid 300 ms full-cohort window after 300 ms settling. Worker CPUs and collector CPU38 remain pinned at 2.5 GHz; unused guest CPUs are not claimed frequency-fixed. Linux Native and the actual TCLock mutex port accompany every performance screen.

## Shared compilation, independently screened

The mutex combiner now compiles alongside the existing execution/spin runtime. Four mutex batch helpers use GNU always-inline definitions while retaining public external entries. Private queue helper names are distinct. This changes compiler visibility without changing queue order, source leases, ownership predicates, final ACK handling, wrapper ABI, packet layout or stack-switch boundaries.

The frozen ELF confirms all four public helpers remain global `T` symbols. Their calls disappear from the mutex body, along with out-of-line readiness/context/timing calls. The generic frame constructor, clobber preparation, minimal-completion predicate, physical-owner checks and FULL dispatcher remain. Function text grows from 2,102 to 4,406 bytes; local stack reservation decreases from 352 to 336 bytes. This is a code-size tradeoff, not removal of lifetime checks.

Cacheline1, Mops/s, each triplet is peak min / median / max:

| Workers | KD | TCLock | Linux Native | KD max / TC max |
|---:|---:|---:|---:|---:|
| 1 | 16.890 / 16.895 / 16.907 | 36.126 / 36.133 / 36.144 | 27.980 / 27.988 / 27.989 | 46.78% |
| 2 | 5.500 / 5.962 / 6.376 | 9.327 / 9.640 / 10.143 | 6.826 / 7.602 / 7.635 | 62.86% |
| 16 | 5.747 / 5.772 / 5.867 | 4.403 / 4.543 / 4.613 | 6.884 / 7.127 / 7.540 | 127.18% |
| 36 | 4.654 / 4.664 / 4.797 | 4.236 / 4.376 / 4.504 | 4.761 / 5.076 / 5.674 | 106.51% |

All 36 scored sessions pass data/context/drain checks; every contended KD positive has returned-body JIT evidence. Relative to the immediately preceding full cacheline matrix, KD median changes at 1/2/16/36 are approximately -0.05%/+2.74%/+8.00%/+14.17%. The prior identical-source 36-thread recheck was lower (3.828), so that alternative comparison is +21.84%; both old groups remain preserved. This screen does not establish parity at unmeasured thread counts.

KD JIT shares at 16/36 are still only 5.14%–6.42% / 4.43%–5.79%. The measured improvement therefore cannot be assigned entirely to saved wrapper calls. Shared compilation also changes surrounding queue code generation, and the screen does not isolate a per-component nanosecond cost.

The shared-runtime change is retained after the checks below. Later candidates remain independent experiments. Raw phases use guest `/root/kdlock-evidence/mutex-20261003b-*`; original logs and failed candidates are retained, never pooled into accepted scores.

Whole-run throughput and peak spread are retained separately (Mops/s):

| Workers | KD whole min / median / max | TC whole min / median / max | Native whole min / median / max | Peak spread KD / TC / Native |
|---:|---:|---:|---:|---:|
| 1 | 16.885 / 16.887 / 16.900 | 36.111 / 36.120 / 36.125 | 27.956 / 27.961 / 27.973 | 0.10% / 0.05% / 0.04% |
| 2 | 5.492 / 5.941 / 6.376 | 9.298 / 9.600 / 10.102 | 6.788 / 7.585 / 7.619 | 14.69% / 8.46% / 10.63% |
| 16 | 5.604 / 5.713 / 5.806 | 4.377 / 4.524 / 4.585 | 6.767 / 7.076 / 7.498 | 2.07% / 4.62% / 9.22% |
| 36 | 4.331 / 4.451 / 4.536 | 4.202 / 4.353 / 4.481 | 4.411 / 4.941 / 5.381 | 3.07% / 6.13% / 18.00% |

Targeted guest validation:

- Two basic programs plus `mutex/test_mutex_resources.py`, `mutex/test_mutex_outer_progress.py`, `execution/test_jit_entry_scope.py` and `execution/test_exec_capacity.py`: six drivers pass. Covers COMPLETE refusal/FULL single consumption, source closure, capacity, retirement and owner/ACK blockers. Unit command/log/status are retained; this initial unit phase did not freeze a separate source manifest.
- Spin plain/nested/early actual JIT, 20 workers, two million operations each: returned bodies 1,996,446 / 1,997,857 / 637,860; data, context, source retirement and drain pass. These functional sessions explicitly bypass only the spin entry-ratio filter; they are not performance scores. Mutex runner still supports ordinary operations only; these are not mutex nested tests.
- Real mutex task/owner test: two unlock orders, four final ACKs, two deferred frees, no failures, normal retirement/unload. This probe is explicitly JIT=0; timed mutex sessions supply the independent real JIT evidence.
- Offline frozen ELF audit: `bench/.tmp/mutex-20261003b/shared-runtime-elf-audit.json`; candidate provider SHA256 `0caaa79c8a1649c2bc08eeb9682f3f0b0296dc7c1f56e47edb9ada2c5b6af383`. Spin's execution function retains the same normalized instructions and ordered calls. No UBSAN symbols.

Phase suffixes: `shared-runtime-unit`, `mutex-shared-runtime-c1`, `mutex-shared-small-c1`, `shared-spin-plain`, `shared-spin-nested`, `shared-spin-early`, `shared-runtime-ack`. No full unit suite or full spin performance matrix was run.

## Exact pinned lifecycle balances

On top of shared runtime (`5111cbc`), active-waiter and reserved-node gauges move from shared atomics to exact per-CPU balances. Reserve/enter/release/exit stay on the pinned origin CPU with preemption disabled. The drain predicate checks every CPU and its node bitmap individually. Per-lock waiter count, original owner, task references, source lifecycle and final ACK handling are unchanged. Approximate observations never authorize retirement.

The five targeted guest drivers pass: two basics, mutex resources, new two-CPU balance fixture and source lifetime. They exercise sleeping reservations, opposite imbalances, slot lifetime, nested slots, underflow, source closure and capacity; mutations that hide a busy CPU or reservation are rejected. Sources are frozen for this unit phase. The timed screen has 18/18 valid sessions and real contended JIT evidence.

| Workers | KD peak min / median / max | TC peak min / median / max | Native peak min / median / max | KD max / TC max |
|---:|---:|---:|---:|---:|
| 16 | 5.829 / 5.934 / 5.955 | 4.604 / 4.633 / 4.687 | 6.657 / 6.716 / 7.460 | 127.05% |
| 36 | 4.337 / 4.701 / 4.821 | 4.291 / 4.339 / 4.758 | 5.178 / 5.529 / 5.709 | 101.33% |

Relative to the shared-runtime screen, KD peak medians increase 2.81% at 16 and 0.79% at 36. The latter is small relative to the 10.30% sample spread; no large repeatable gain is claimed. Neither protected screen regresses. The per-CPU implementation remains exact, and avoids four shared atomic updates per queued request.

| Workers | KD whole min / median / max | TC whole min / median / max | Native whole min / median / max | Peak spread KD / TC / Native |
|---:|---:|---:|---:|---:|
| 16 | 5.714 / 5.859 / 5.915 | 4.591 / 4.612 / 4.678 | 6.553 / 6.615 / 7.414 | 2.13% / 1.81% / 11.96% |
| 36 | 4.303 / 4.480 / 4.675 | 4.285 / 4.299 / 4.645 | 4.927 / 5.196 / 5.603 | 10.30% / 10.78% / 9.60% |

The matching real mutex owner probe passes both unlock orders, four final ACKs and two deferred frees, with normal source retirement/unload (JIT=0). This exact-balance change is retained for full-matrix verification.

Phase suffixes: `balances-unit`, `mutex-balances-c1`, `balances-ack`. Small-thread and full-matrix acceptance remain separate.

## Rejected bounded NUMA grouping

The independently tested grouping candidate (`87888c9`, branch `perf/mutex-numa-rejected-20261003b`) preserves a deferred remote prefix, independent 1,024-body/scan limits, legacy/FULL boundaries, refusal rollback and priority remote handoff. It adds no broad prefetch hints. The two basics plus actual selection/combiner and outer-progress fixtures pass with NUMA both on and off, including protected reads after scan exhaustion. All 27 timed samples pass data, JIT and drain checks.

It is nevertheless rejected: 36-thread KD medians fall from 4.701 to 4.445 (-5.44%) and 4.336 (-7.76%) Mops/s on the required recheck. The implementation was reverted in `7c74d3e`; accepted mutex queue order remains FIFO. Correct bounded grouping alone is not a throughput improvement when most requests still take native routes. That is a workload/protocol interpretation, not a measured remote-latency attribution.

| Phase / workers | KD peak min / median / max | TC peak min / median / max | Native peak min / median / max | KD max / TC max |
|---|---:|---:|---:|---:|
| mutex-numa-c1 / 16 | 5.719 / 6.026 / 6.054 | 4.367 / 4.710 / 4.869 | 6.833 / 6.940 / 7.343 | 124.34% |
| mutex-numa-c1 / 36 | 4.409 / 4.445 / 4.530 | 4.286 / 4.576 / 4.993 | 4.884 / 5.023 / 5.597 | 90.74% |
| mutex-numa-recheck-c1 / 36 | 4.161 / 4.336 / 4.404 | 4.410 / 4.429 / 4.429 | 5.612 / 5.667 / 5.883 | 99.44% |

| Phase / workers | KD whole min / median / max | TC whole min / median / max | Native whole min / median / max | Peak spread KD / TC / Native |
|---|---:|---:|---:|---:|
| mutex-numa-c1 / 16 | 5.652 / 5.947 / 5.959 | 4.341 / 4.687 / 4.858 | 6.768 / 6.873 / 7.284 | 5.56% / 10.66% / 7.36% |
| mutex-numa-c1 / 36 | 4.191 / 4.301 / 4.387 | 4.263 / 4.529 / 4.542 | 4.716 / 4.838 / 5.496 | 2.73% / 15.44% / 14.20% |
| mutex-numa-recheck-c1 / 36 | 4.121 / 4.281 / 4.368 | 4.395 / 4.405 / 4.411 | 5.272 / 5.363 / 5.513 | 5.60% / 0.42% / 4.77% |

Frozen phases: `numa-unit`, `mutex-numa-c1`, `mutex-numa-recheck-c1`. No hash or full-matrix acceptance is attributed to this rejected candidate.

## Native outer acquisition and explicit unlock routing

The retained `KD_MUTEX_OUTER_LOCK/UNLOCK` pair performs the original Linux owner CAS in the caller. Success records one approximate entry and its opaque acquisition-local cookie; unlock calls the original Linux function directly. Failed CAS enters the new contended-only ABI2 endpoint, counts exactly once and writes zero to the cookie immediately after the registered continuation. This includes native fallbacks. Zero routes unlock through the existing provider, preserving queue gate/task-reference release and borrowed owner ACKs. Existing DIRECT APIs remain for nested operations; neither global interception nor the two-word wrapper ABI changes.

The cookie chooses routing only: it does not replace the Linux owner word or any exact KD lifetime state. Five callee-saved caller spills remain. The performance gain therefore does not demonstrate their removal. Both unlock branches end at recognized calls; the native branch's empty compiler barrier prevents tail-call conversion without adding a hardware fence.

All 36 cacheline screen sessions pass. Each contended KD positive has actual returned-body JIT. Relative to shared-runtime small-thread results and the immediately preceding accepted balances screen, KD medians improve about 94.31% / 38.86% / 51.70% / 73.87% at 1/2/16/36. All four peak ratios exceed the original 90% screen threshold; strict parity with TCLock remains unmet at 1 and 2. Full 15-point acceptance is still pending.

| Workers | KD peak min / median / max | TC peak min / median / max | Native peak min / median / max | KD max / TC max |
|---:|---:|---:|---:|---:|
| 1 | 32.824 / 32.828 / 32.835 | 36.110 / 36.145 / 36.153 | 27.991 / 27.991 / 27.994 | 90.82% |
| 2 | 8.084 / 8.279 / 9.691 | 10.228 / 10.381 / 10.505 | 6.575 / 7.005 / 7.006 | 92.25% |
| 16 | 8.899 / 9.002 / 9.064 | 4.421 / 4.546 / 4.671 | 6.563 / 7.178 / 7.379 | 194.04% |
| 36 | 8.093 / 8.174 / 8.356 | 4.372 / 4.399 / 4.480 | 5.577 / 5.584 / 5.664 | 186.51% |

| Workers | KD whole min / median / max | TC whole min / median / max | Native whole min / median / max | Peak spread KD / TC / Native |
|---:|---:|---:|---:|---:|
| 1 | 32.812 / 32.818 / 32.819 | 36.099 / 36.134 / 36.138 | 27.965 / 27.979 / 27.980 | 0.03% / 0.12% / 0.01% |
| 2 | 7.729 / 8.127 / 9.457 | 10.207 / 10.357 / 10.478 | 6.563 / 6.966 / 6.983 | 19.42% / 2.67% / 6.15% |
| 16 | 8.632 / 8.851 / 8.977 | 4.391 / 4.529 / 4.655 | 6.444 / 7.092 / 7.175 | 1.83% / 5.50% / 11.37% |
| 36 | 7.855 / 7.921 / 8.286 | 4.291 / 4.369 / 4.452 | 5.206 / 5.485 / 5.521 | 3.21% / 2.46% / 1.56% |

KD JIT share is 2.44%–2.83% at 16 and 1.14%–1.40% at 36. The faster native path is therefore central to the gain; this is not evidence of TCLock-like delegation frequency. At 36, node1 contributes 44.08%–44.58% of whole-run work (16/36 workers), and 42.57%–44.67% in selected peaks. The smallest individual worker completes 308,992 whole-run and 46,080 peak operations. Observed progress is substantially more balanced than the earlier hash minority-node result; cacheline evidence is not a hash fairness guarantee.

Validation and preserved failures:

- The actual compiled header preserves live registers and flags fallback. Its translated ABI2 continuation runs with poisoned uncaptured registers and verifies zero-cookie routing, unchanged Linux ownership, COMPLETE and exact terminal FULL. Separate generated tests cover 16 completion/refusal and native-CALL continuation cases, including cookie read after native replay.
- Resources: 12,940 checks with once-only contention observation and native-CAS retry mutation; endpoint registry: 29,659 checks; native-after-outer owner recovery: 3,414 checks plus four Python tests. Basic programs pass with these targeted drivers.
- The clobber guard driver passes all 27 tests after correcting three stale layout-1 fixture indices to current RBP/RSP slots. Expected success/refusal assertions are unchanged; production admission was not relaxed.
- Initial `outer-api-unit` failed on a genuine inline-native-release CFG reaching an FS canary epilogue, and on those three stale fixture indices. Inline release was replaced by original Linux unlock. `outer-api-unit-fixed` then passed admission but caught changed source addresses after relinking the fixture. `outer-protocol-unit` caught its unexported weak wrapper, preventing an unexecuted generated image from passing. Fixing a stable text base, wrapper export and explicit entry-SP metadata yields `outer-compiled-unit` pass. All failed logs, statuses and frozen inputs remain retained.
- The changed benchmark runner passes 44 tests (`outer-runner-unit`). Actual mutex/hash functional sessions at 16/36 complete 1.6/3.6 million operations with 47,732/861,778 returned JIT bodies, valid data and clean drain (`mutex-outer-hash-functional`). This verifies real hash cookie admission; it is not a timed hash score.
- The real owner/RCU test passes two unlock orders, four final ACKs and two deferred frees, with normal retirement/unload (`outer-ack`, explicitly JIT=0).

The cacheline score phase is `mutex-outer-c1`. The original screen records literally use `mutex_outer_cookie` / `outer_acquisition_stack`. ELF inspection found that c1 keeps the cookie in RBX (the entry defines zero with `xor %ebx,%ebx`), so subsequent records correct the storage label to `outer_acquisition_local`: the compiler chooses register or spill. Raw screen metadata is preserved. Its scores are compared with earlier caller shells as successive implementations, not pooled across shells. No full unit suite or mutex nested benchmark is claimed.

## Complete cacheline matrix after native outer routing

Phase `mutex-final-c1`, source `60879dd`: all 135 sessions pass, with three valid rounds per arm at every requested thread count. Every KD point from 4 through 36 has returned-body JIT evidence; TCLock delegation is independently observed. KD best peaks exceed TCLock at all 12 points from 4 through 36, while 1/2/3 remain below it. The original 90% peak threshold is met at 14/15 points; 3 threads reaches only 78.57%. Full parity is not achieved.

Relative to the prior full cacheline matrix, every KD peak median improves: +94.01% at 1, +61.26% at 2, +1.91% at 3, +73.06% at 16 and +98.29% at 36. Thus no protected median regression requires a recheck in this matrix. Relative to the immediately preceding outer screen, the 36-thread median changes by -0.90%, within the 3% acceptance bound. Samples are not pooled across phases.

All rates below are Mops/s. Spread is `(max-min)/median`.

| Threads | KD peak min / median / max | TC peak min / median / max | Native peak min / median / max | KD / TC max | Valid KD rounds |
|---:|---:|---:|---:|---:|---:|
| 1 | 31.931 / 32.794 / 32.825 | 36.133 / 36.141 / 36.142 | 27.906 / 27.985 / 28.014 | 90.82% | 3/3 |
| 2 | 8.471 / 9.358 / 9.648 | 10.061 / 10.234 / 10.486 | 6.407 / 6.639 / 7.576 | 92.01% | 3/3 |
| 3 | 5.716 / 5.883 / 6.767 | 7.755 / 8.096 / 8.612 | 7.389 / 7.467 / 7.711 | 78.57% | 3/3 |
| 4 | 7.339 / 7.798 / 8.034 | 5.955 / 6.070 / 6.343 | 6.911 / 7.133 / 7.256 | 126.66% | 3/3 |
| 5 | 8.515 / 8.630 / 8.797 | 5.796 / 5.799 / 5.841 | 6.507 / 7.119 / 7.213 | 150.62% | 3/3 |
| 6 | 8.578 / 8.956 / 9.187 | 4.997 / 5.173 / 5.222 | 6.553 / 7.276 / 7.452 | 175.91% | 3/3 |
| 7 | 8.473 / 8.554 / 9.377 | 4.177 / 4.189 / 4.267 | 7.234 / 7.293 / 7.864 | 219.75% | 3/3 |
| 8 | 8.665 / 8.989 / 9.196 | 4.150 / 4.230 / 4.441 | 6.799 / 7.399 / 7.414 | 207.09% | 3/3 |
| 12 | 9.055 / 9.096 / 9.172 | 4.256 / 4.367 / 4.617 | 6.916 / 7.053 / 7.117 | 198.63% | 3/3 |
| 16 | 9.055 / 9.249 / 9.306 | 4.487 / 4.648 / 4.853 | 7.159 / 7.367 / 7.472 | 191.77% | 3/3 |
| 20 | 8.904 / 9.073 / 9.104 | 4.549 / 4.589 / 4.596 | 6.907 / 7.123 / 7.336 | 198.08% | 3/3 |
| 24 | 8.017 / 8.170 / 8.486 | 4.468 / 4.469 / 4.525 | 6.199 / 6.331 / 6.342 | 187.55% | 3/3 |
| 28 | 7.924 / 7.938 / 8.209 | 4.394 / 4.549 / 4.576 | 5.974 / 6.108 / 6.353 | 179.42% | 3/3 |
| 32 | 7.751 / 8.055 / 8.314 | 4.349 / 4.442 / 4.549 | 5.488 / 5.635 / 5.798 | 182.76% | 3/3 |
| 36 | 7.703 / 8.100 / 8.324 | 4.421 / 4.623 / 4.640 | 5.092 / 5.749 / 5.779 | 179.41% | 3/3 |

| Threads | KD whole min / median / max | TC whole min / median / max | Native whole min / median / max | Peak spread KD / TC / Native |
|---:|---:|---:|---:|---:|
| 1 | 31.906 / 32.785 / 32.799 | 36.122 / 36.126 / 36.127 | 27.892 / 27.977 / 27.987 | 2.73% / 0.02% / 0.38% |
| 2 | 8.264 / 9.195 / 9.466 | 10.026 / 10.201 / 10.475 | 6.375 / 6.621 / 7.562 | 12.58% / 4.15% / 17.61% |
| 3 | 5.322 / 5.651 / 6.361 | 7.661 / 8.060 / 8.541 | 7.358 / 7.444 / 7.686 | 17.86% / 10.58% / 4.30% |
| 4 | 7.137 / 7.411 / 7.810 | 5.897 / 6.037 / 6.290 | 6.888 / 7.095 / 7.235 | 8.91% / 6.39% / 4.83% |
| 5 | 8.351 / 8.404 / 8.444 | 5.750 / 5.764 / 5.803 | 6.410 / 7.078 / 7.172 | 3.27% / 0.77% / 9.92% |
| 6 | 8.317 / 8.756 / 9.032 | 4.952 / 5.128 / 5.173 | 6.436 / 7.247 / 7.426 | 6.79% / 4.35% / 12.36% |
| 7 | 8.262 / 8.368 / 9.135 | 4.148 / 4.177 / 4.258 | 7.185 / 7.250 / 7.829 | 10.57% / 2.15% / 8.65% |
| 8 | 8.469 / 8.851 / 9.037 | 4.101 / 4.173 / 4.419 | 6.739 / 7.351 / 7.389 | 5.91% / 6.88% / 8.31% |
| 12 | 8.911 / 8.938 / 9.040 | 4.243 / 4.344 / 4.572 | 6.798 / 6.982 / 6.987 | 1.28% / 8.27% / 2.85% |
| 16 | 8.958 / 9.074 / 9.082 | 4.458 / 4.619 / 4.667 | 7.063 / 7.333 / 7.416 | 2.72% / 7.88% / 4.24% |
| 20 | 8.772 / 8.876 / 8.913 | 4.536 / 4.573 / 4.576 | 6.668 / 6.949 / 7.221 | 2.21% / 1.02% / 6.03% |
| 24 | 7.891 / 7.913 / 8.330 | 4.439 / 4.448 / 4.493 | 6.080 / 6.118 / 6.252 | 5.74% / 1.26% / 2.26% |
| 28 | 7.652 / 7.699 / 8.095 | 4.386 / 4.524 / 4.561 | 5.834 / 5.914 / 6.135 | 3.59% / 3.99% / 6.21% |
| 32 | 7.354 / 7.764 / 8.242 | 4.328 / 4.330 / 4.430 | 5.281 / 5.355 / 5.636 | 6.98% / 4.51% / 5.50% |
| 36 | 7.314 / 7.693 / 7.862 | 4.367 / 4.584 / 4.604 | 4.900 / 5.338 / 5.556 | 7.67% / 4.72% / 11.95% |

| Threads | KD JIT share | TC delegation share | KD min worker whole / peak ops | KD node1 whole share | KD node1 peak share |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.000%–0.000% | 0.000%–0.000% | 63814400 / 9579264 | 0.000%–0.000% | 0.000%–0.000% |
| 2 | 0.000%–0.000% | 0.000%–0.000% | 7931904 / 1223936 | 0.000%–0.000% | 0.000%–0.000% |
| 3 | 0.000%–0.001% | 0.088%–0.561% | 3107328 / 502272 | 0.000%–0.000% | 0.000%–0.000% |
| 4 | 1.797%–2.798% | 14.520%–15.339% | 3012096 / 484864 | 0.000%–0.000% | 0.000%–0.000% |
| 5 | 2.721%–2.928% | 21.328%–22.182% | 2780160 / 463104 | 0.000%–0.000% | 0.000%–0.000% |
| 6 | 2.539%–2.635% | 35.099%–39.215% | 2482176 / 381440 | 0.000%–0.000% | 0.000%–0.000% |
| 7 | 2.487%–3.080% | 82.339%–89.920% | 1983232 / 312064 | 0.000%–0.000% | 0.000%–0.000% |
| 8 | 2.850%–3.242% | 96.163%–96.469% | 1677056 / 256512 | 0.000%–0.000% | 0.000%–0.000% |
| 12 | 2.768%–2.945% | 98.492%–98.757% | 1207552 / 183808 | 0.000%–0.000% | 0.000%–0.000% |
| 16 | 2.557%–2.832% | 97.839%–98.887% | 963072 / 133632 | 0.000%–0.000% | 0.000%–0.000% |
| 20 | 2.508%–2.681% | 98.753%–98.936% | 547328 / 81664 | 0.000%–0.000% | 0.000%–0.000% |
| 24 | 1.853%–2.041% | 94.364%–95.832% | 428544 / 65536 | 16.705%–17.390% | 16.325%–17.515% |
| 28 | 1.566%–1.672% | 95.464%–97.150% | 376064 / 58880 | 28.084%–30.457% | 27.793%–29.603% |
| 32 | 1.340%–1.787% | 97.408%–98.859% | 388864 / 58112 | 37.197%–40.274% | 37.380%–40.522% |
| 36 | 1.419%–1.744% | 97.927%–98.617% | 297216 / 43008 | 44.699%–46.183% | 43.354%–52.644% |

At 24 threads, node1 completes 16.705%–17.390% of whole-run KD work, close to its 4/24 worker share; every worker advances in whole-run and selected peak windows. At 36, the minimum is 297,216 whole-run and 43,008 peak operations. This finite observation does not establish a starvation bound. KD JIT is 1.419%–1.744% at 36 versus TCLock delegation 97.927%–98.617%; the throughput lead does not mean the KD delegation mechanism is faster. Timed hash verification remains separate.

## Flat-cycle diagnosis of the remaining low-thread gap

`mutex-20261003b-outer-route-profile` 独立采集 1/2/3/36 threads × 三臂 × 一轮，共 12 个 diagnostic，全部 `OK`、drained、lost samples=0。`perf record -e cycles -F 499` 不采 callchain；逐项核对 `sample_type=IP|TID|TIME|PERIOD`。采集范围是测量 client 及其继承 workers；离线只统计 `sc_worker`：119,298 个 samples，另有 169 个 client samples 不进入下表。百分比是该臂该配置的 sampled event-period 权重，不是独立函数耗时；这批 throughput 不参与成绩。

| threads | KD 主要 worker cycle 权重 | 测量期 returned JIT |
| --- | --- | --- |
| 1 | caller `mc_body_1` 50.41%；原始 `mutex_unlock` 41.03% | 0 |
| 2 | caller 21.66%；原始 unlock 14.75%；task get/put 3.88%/1.15%；PV queued-spin slowpath 5.50%；irqsave spin-lock entry 5.99% | 0 |
| 3 | private gate wait/acquire 14.23%；PV queued-spin slowpath 13.30%；KD queue slowpath 11.50%；task get/put 3.77%/1.34% | 154，0.001132% |
| 36 | PV queued-spin slowpath 83.48%；KD queue slowpath 4.45%；generated image 0.03426% | 236,119，1.51263% |

1T 没有进入 KD registry/queue：卸载统计的 origin acquisitions、task reroutes、slowpath 都为 0。剩余差异落在 native caller 和 Linux unlock。冻结 ELF 中 KD caller 仍有 RBX、R12–R15 五组额外 push/pop、current-task load、owner CAS 和 per-CPU entry 计数；TCLock 的冻结 `source/tclock_backend/komb_mutex.c:675` / `:729` 使用自己的 lock-state CAS 与普通 release store。KD 保留原始 Linux owner/flags 及 unlock 语义，不能把这部分直接等价成 TCLock 的状态字释放。这里的 ELF 和 flat samples 能证明工作内容与热点所在，不能分离每组 spill/CAS 的纳秒代价。

2T 的整个模块生命周期（**包含 warmup**）有 2,143,698 次 KD origin acquisitions/task reroutes，618 次 queue slowpath，combiner/JIT 均为 0。3T 有 1,106,704 次 queue slowpath、588,920 次 combiner entry、588,765 次 handoff，JIT success 仅 155；99.97368% 的 combiner entry 走 handoff。`jit_not_ready`、`jit_failure`、`frame_failure` 都为 0。冻结 `source/kernel_module/mutex/combiner.inc:338` 要求当前 waiter 已有 successor 才开始代理，并把最后一个 waiter 留给 native handoff；短队列因此反复承担 registry、gate waiting 和原始 mutex 获取，却几乎没有 batching 收益。卸载 JIT=155 与测量期 returned JIT=154 的统计范围不同。对应三轮 c1 成绩在 3T 只有 37/42/62 个 returned bodies、0.000327–0.000582%；最佳峰值 KD/TC=78.57325%，不能宣布全部 15 点达标。

36T 的 remaining cost 仍指向协调路径；但通用 PV queued-spin slowpath 的 flat samples **不能确定是哪一个 lock 实例，也不能证明 remote-memory latency**。全局 task-registry lock 是源码支持的候选解释，不能把 83.48% 全部归给它。36T unresolved 权重保留为 2.01%，未按最近符号猜测。generated-image 权重低还与 returned JIT 比例低有关，不能据此推导单个代理 body 很便宜。

离线证据保存在 `bench/.tmp/mutex-20261003b/outer-route-hotspots.json`、`outer-route-lifecycle.json` 与 `outer-route-profile-summary.py`；归因使用该 phase 的冻结 ELF/JIT 和相同 kernel Build ID 的 symbol-size capture，不使用正在修改的候选源码，也不执行归档代码。

## Exact native fallback result

The next independently screened change extends OUTER routing to native fallbacks before any KD reference or gate is acquired. A new return-valued endpoint returns the exact native owner for those acquisitions, and zero after every KD queue entry. The old void endpoint stays compatible. Normal C return retains the result; a distinct named JIT entry defines zero itself. This preserves ABI2 and the two-word wrapper input. Nested translated calls to the new outer-only endpoint are refused by admission and runtime recovery, since the existing nested service does not supply this return value.

The initial 16/36 screen has 18 valid samples. Relative to `mutex-final-c1`, medians change -1.57% / -3.44%; the apparent 36-thread regression triggered the required separate recheck. That recheck has 36 valid samples at 1/2/3/36: median changes +0.39% / +5.60% / +13.87% / +0.79%. The 36-thread regression does not repeat. The 2/3-thread gains are observed in this screen, with prior three-thread spread retained; no isolated nanosecond saving or final full-matrix result is claimed. Strict parity remains unmet at 1/2/3.

First screen (`mutex-outer-result-c1`):

| Threads | KD peak min / median / max | TC peak min / median / max | Native peak min / median / max | KD / TC max | Valid KD rounds |
|---:|---:|---:|---:|---:|---:|
| 16 | 9.053 / 9.104 / 9.219 | 4.390 / 4.459 / 4.686 | 6.516 / 6.974 / 7.154 | 196.73% | 3/3 |
| 36 | 7.396 / 7.821 / 8.065 | 4.446 / 5.261 / 5.350 | 5.416 / 5.421 / 5.582 | 150.77% | 3/3 |

| Threads | KD whole min / median / max | TC whole min / median / max | Native whole min / median / max | Peak spread KD / TC / Native |
|---:|---:|---:|---:|---:|
| 16 | 8.823 / 8.860 / 9.078 | 4.356 / 4.445 / 4.656 | 6.456 / 6.827 / 7.101 | 1.82% / 6.65% / 9.15% |
| 36 | 7.088 / 7.519 / 7.600 | 4.420 / 4.515 / 4.638 | 5.254 / 5.326 / 5.333 | 8.55% / 17.17% / 3.06% |

| Threads | KD JIT share | TC delegation share | KD min worker whole / peak ops | KD node1 whole share | KD node1 peak share |
|---:|---:|---:|---:|---:|---:|
| 16 | 2.681%–2.738% | 98.647%–98.855% | 896768 / 140288 | 0.000%–0.000% | 0.000%–0.000% |
| 36 | 1.441%–1.811% | 93.567%–98.366% | 304384 / 49664 | 41.770%–44.743% | 42.356%–43.869% |

Small-thread screen and 36-thread recheck (`mutex-outer-result-recheck-c1`), kept separate rather than pooled:

| Threads | KD peak min / median / max | TC peak min / median / max | Native peak min / median / max | KD / TC max | Valid KD rounds |
|---:|---:|---:|---:|---:|---:|
| 1 | 32.921 / 32.922 / 32.923 | 36.130 / 36.133 / 36.134 | 27.673 / 27.982 / 27.990 | 91.11% | 3/3 |
| 2 | 9.789 / 9.883 / 9.957 | 9.388 / 9.850 / 10.205 | 6.408 / 6.561 / 7.092 | 97.57% | 3/3 |
| 3 | 6.089 / 6.699 / 6.743 | 8.020 / 8.369 / 8.801 | 7.376 / 7.397 / 7.447 | 76.62% | 3/3 |
| 36 | 7.684 / 8.164 / 8.309 | 4.419 / 4.520 / 4.720 | 5.002 / 5.107 / 5.690 | 176.02% | 3/3 |

| Threads | KD whole min / median / max | TC whole min / median / max | Native whole min / median / max | Peak spread KD / TC / Native |
|---:|---:|---:|---:|---:|
| 1 | 32.876 / 32.908 / 32.910 | 36.100 / 36.117 / 36.120 | 27.659 / 27.963 / 27.972 | 0.01% / 0.01% / 1.13% |
| 2 | 9.388 / 9.401 / 9.649 | 9.365 / 9.813 / 10.181 | 6.368 / 6.547 / 6.946 | 1.70% / 8.30% / 10.42% |
| 3 | 5.695 / 6.243 / 6.481 | 7.953 / 8.313 / 8.764 | 7.363 / 7.381 / 7.423 | 9.77% / 9.34% / 0.96% |
| 36 | 7.483 / 8.034 / 8.151 | 4.401 / 4.495 / 4.687 | 4.802 / 4.902 / 5.582 | 7.65% / 6.66% / 13.47% |

| Threads | KD JIT share | TC delegation share | KD min worker whole / peak ops | KD node1 whole share | KD node1 peak share |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.000%–0.000% | 0.000%–0.000% | 65754368 / 9876992 | 0.000%–0.000% | 0.000%–0.000% |
| 2 | 0.000%–0.000% | 0.000%–0.000% | 9200896 / 1452800 | 0.000%–0.000% | 0.000%–0.000% |
| 3 | 0.000%–0.001% | 0.072%–0.750% | 3470592 / 518144 | 0.000%–0.000% | 0.000%–0.000% |
| 36 | 1.324%–1.670% | 97.914%–98.559% | 352768 / 54016 | 43.900%–44.852% | 43.541%–44.953% |

Targeted validation covers the actual compiled synthetic entry with poisoned GPRs, physical/native return routing, COMPLETE and forced FULL, task/shadow resources, once-only sampling, registry endpoints and existing native-after-outer owner recovery. The first `outer-result-unit` phase has six passing drivers and one failed diagnostic assertion: the new rejection test muted the log whose text it then checked. Removing that test-only muting preserves its refusal assertion; `outer-result-admission` passes the basics and all 28 admission tests. The failed phase remains frozen. `outer-result-runner` passes all 44 tests. `outer-result-ack` passes the real owner/RCU probe with two orders, four final ACKs and two deferred frees, explicitly JIT=0. Timed contended sessions independently provide returned-body JIT and clean source/module drain.

This result-routing change is retained as a separate validated checkpoint. Its full 15-point/hash verification remains pending until the next candidate screens finish; neither the earlier full matrix nor its profile is relabeled as this implementation.

## Hash screen and required recheck: regression remains

The `ec45ca2` exact-native-result checkpoint was measured at 16/36 workers in `mutex-outer-result-hash` and `mutex-outer-result-recheck-hash`. Both phases contain 18/18 valid, drained samples. Every contended KD sample returns JIT bodies and every TCLock sample reports delegation. Offline record validation reproduces selected peaks, correct payload/hash state, exact worker CPUs, positive progress for every worker in both the whole run and selected peak, and consistent totals. Functional correctness passes; performance acceptance does not.

The matching historical reference is the full hash matrix at `51493f2`: its 16/36 KD peak medians were 4.249548/2.509651 Mops/s and whole medians 4.118330/2.044662. All six KD reference samples at these two points are valid; the five NO_JIT failures elsewhere in that historical matrix remain excluded. This is a comparison across the cumulative shared-runtime/balance/outer-routing changes, not an isolated causal experiment on the exact-native-result endpoint alone.

| Workers | First peak median change | Recheck peak median change | First whole median change | Recheck whole median change |
|---:|---:|---:|---:|---:|
|16|−9.44%|−10.16%|−5.11%|−5.32%|
|36|−25.81%|−23.33%|−14.36%|−10.51%|

Both protected medians regress by more than 3%, and the loss repeats. At 16 the best KD/TC ratios are 98.97% and 100.57%; at 36 they are 87.99% and 104.45%. The recheck's high 36-thread best window is retained, but its KD peak range is 1.608236–2.846716 Mops/s and its median is 1.924143; it does not cancel the repeated median regression. A single best-window pass is not repeatable target acceptance, and no full hash matrix or all-thread parity is claimed for this checkpoint.

All throughput values are Mops/s; spreads are `(max-min)/median`. Each row contains three valid rounds.

| Phase / threads | Arm | Peak min / median / max | Peak spread | Whole min / median / max | Whole spread |
|---|---|---:|---:|---:|---:|
| first / 16 | kdlock | 3.814 / 3.848 / 4.025 | 5.47% | 3.889 / 3.908 / 4.062 | 4.43% |
| first / 16 | tclock | 4.049 / 4.063 / 4.067 | 0.44% | 4.030 / 4.049 / 4.053 | 0.56% |
| first / 16 | native | 4.614 / 4.721 / 4.744 | 2.75% | 4.594 / 4.675 / 4.695 | 2.15% |
| first / 36 | kdlock | 1.749 / 1.862 / 1.940 | 10.25% | 1.650 / 1.751 / 1.801 | 8.59% |
| first / 36 | tclock | 2.198 / 2.199 / 2.205 | 0.32% | 2.187 / 2.188 / 2.194 | 0.32% |
| first / 36 | native | 2.682 / 2.688 / 2.697 | 0.55% | 2.633 / 2.645 / 2.655 | 0.83% |
| recheck / 16 | kdlock | 3.763 / 3.818 / 4.114 | 9.19% | 3.839 / 3.899 / 4.067 | 5.86% |
| recheck / 16 | tclock | 4.063 / 4.066 / 4.091 | 0.69% | 4.050 / 4.052 / 4.077 | 0.67% |
| recheck / 16 | native | 4.692 / 4.705 / 4.723 | 0.66% | 4.650 / 4.685 / 4.698 | 1.02% |
| recheck / 36 | kdlock | 1.608 / 1.924 / 2.847 | 64.37% | 1.725 / 1.830 / 2.331 | 33.10% |
| recheck / 36 | tclock | 2.202 / 2.209 / 2.726 | 23.69% | 2.191 / 2.199 / 2.281 | 4.07% |
| recheck / 36 | native | 2.597 / 2.721 / 2.734 | 5.06% | 2.445 / 2.664 / 2.692 | 9.27% |

| Phase / threads | KD max / TC max | KD JIT share | TC delegation share | KD min worker whole / peak ops | KD node1 whole share | KD node1 peak share |
|---|---:|---:|---:|---:|---:|---:|
| first / 16 | 98.97% | 8.987%–11.491% | 97.484%–97.548% | 435200 / 60416 | 0.000%–0.000% | 0.000%–0.000% |
| first / 36 | 87.99% | 20.182%–24.849% | 97.705%–97.781% | 67584 / 10496 | 36.595%–37.735% | 39.073%–43.096% |
| recheck / 16 | 100.57% | 9.073%–11.825% | 97.476%–97.581% | 433152 / 61440 | 0.000%–0.000% | 0.000%–0.000% |
| recheck / 36 | 104.45% | 7.656%–22.673% | 93.149%–98.022% | 62464 / 768 | 35.228%–40.773% | 34.854%–43.004% |

At 36, the 20+16 worker distribution gives node1 a 44.44% worker share, but KD whole-run node1 shares are 36.60%–37.73% in the first phase and 35.23%–40.77% in the recheck. All workers advance, yet one recheck peak worker completes only 768 operations. The node shares and minima should accompany the high peak, rather than treating positive progress as a fairness or starvation guarantee. There is no 24-thread observation in these screens.

Delegation frequency rises substantially from the historical reference: at 16 KD JIT share was 0.067%–1.342%, versus 8.987%–11.491% and 9.073%–11.825% now; at 36 it was 0.405%–9.057%, versus 20.182%–24.849% and 7.656%–22.673%. More returned JIT bodies coexist with lower aggregate throughput. That motivates investigating coordination and per-request costs, but does not isolate their causal contribution or prove remote-cache latency. The retained cacheline gain must not be extrapolated to hash.


## Rejected post-admission native retry

This independent candidate permits one later native-owner CAS after the failed outer entry has already recorded contention, and after admission/shadow lookup, only when observations of the original owner, private gate and tail are empty. The real owner CAS still decides acquisition; observations grant no ownership, entry counting is not repeated, and successful retry occurs before task-reference/queue publication. The candidate is rejected for performance, not relabeled a correctness failure. Commit `ae7a26b` preserves it; `6ab4f10` reverts it.

`mutex-retry-c1` has 18/18 valid samples at 16/36; `mutex-retry-recheck-c1` has 36/36 at 1/2/3/36. At 16/36, every KD sample has returned-body JIT. The 1/2-worker recheck samples report zero JIT; the 3-worker samples return 51–58 JIT bodies. Data, worker progress and recorded drain pass. Compared with the ec45 c1 first screen, KD peak medians fall 10.02% at 16 and 7.98% at 36. The 36-thread ec45 recheck is the latest same-source reference (8.163526 Mops/s); against that fixed reference, the retry's first/recheck medians 7.196961/7.358964 fall 11.84%/9.86%. Even against the lower original ec45 screen 7.821451, both retry 36 medians remain more than 3% lower. The repeatable 36 regression is sufficient to reject the candidate; 16 was not repeated, so its loss is reported only as a first-screen result.

The retry recheck also fails to repair small-thread behavior. Compared with matching ec45 recheck medians, changes at 1/2/3/36 are −0.03%/−6.88%/−10.21%/−9.86%; whole-run median changes are −0.05%/−4.50%/−10.07%/−10.42%. At 3 the best KD/TC ratio is 60.69%, with only 51–58 returned JIT bodies. No hash score or full-matrix acceptance is attributed to this rejected candidate. Original valid observations are retained, not removed because the candidate loses.

All throughput values are Mops/s; spreads are `(max-min)/median`. Each row contains three valid rounds.

| Phase / threads | Arm | Peak min / median / max | Peak spread | Whole min / median / max | Whole spread |
|---|---|---:|---:|---:|---:|
| first / 16 | kdlock | 8.029 / 8.192 / 8.399 | 4.52% | 7.906 / 8.029 / 8.164 | 3.21% |
| first / 16 | tclock | 4.390 / 4.628 / 4.750 | 7.78% | 4.369 / 4.602 / 4.725 | 7.73% |
| first / 16 | native | 6.490 / 6.766 / 7.014 | 7.75% | 6.215 / 6.622 / 6.893 | 10.24% |
| first / 36 | kdlock | 6.906 / 7.197 / 7.296 | 5.43% | 6.565 / 7.048 / 7.193 | 8.91% |
| first / 36 | tclock | 4.401 / 4.539 / 4.612 | 4.67% | 4.371 / 4.516 / 4.581 | 4.65% |
| first / 36 | native | 5.243 / 5.587 / 5.687 | 7.96% | 5.089 / 5.494 / 5.502 | 7.51% |
| recheck / 1 | kdlock | 32.909 / 32.912 / 32.916 | 0.02% | 32.875 / 32.890 / 32.896 | 0.06% |
| recheck / 1 | tclock | 36.143 / 36.146 / 36.146 | 0.01% | 36.100 / 36.116 / 36.126 | 0.07% |
| recheck / 1 | native | 27.930 / 27.987 / 27.990 | 0.21% | 27.915 / 27.966 / 27.972 | 0.20% |
| recheck / 2 | kdlock | 8.375 / 9.203 / 9.444 | 11.61% | 8.110 / 8.978 / 9.050 | 10.48% |
| recheck / 2 | tclock | 10.147 / 10.372 / 10.445 | 2.87% | 10.111 / 10.346 / 10.415 | 2.95% |
| recheck / 2 | native | 5.735 / 6.936 / 7.298 | 22.53% | 5.720 / 6.886 / 7.272 | 22.55% |
| recheck / 3 | kdlock | 6.013 / 6.015 / 6.608 | 9.90% | 5.582 / 5.614 / 6.271 | 12.26% |
| recheck / 3 | tclock | 8.605 / 9.058 / 10.889 | 25.22% | 8.540 / 8.928 / 10.773 | 25.01% |
| recheck / 3 | native | 7.027 / 7.274 / 7.559 | 7.31% | 6.983 / 7.244 / 7.544 | 7.75% |
| recheck / 36 | kdlock | 7.307 / 7.359 / 7.430 | 1.67% | 7.072 / 7.197 / 7.212 | 1.94% |
| recheck / 36 | tclock | 4.537 / 4.560 / 4.849 | 6.83% | 4.481 / 4.501 / 4.560 | 1.75% |
| recheck / 36 | native | 5.401 / 5.604 / 5.639 | 4.25% | 5.324 / 5.434 / 5.479 | 2.85% |

| Phase / threads | KD max / TC max | KD JIT share | TC delegation share | KD min worker whole / peak ops | KD node1 whole share | KD node1 peak share |
|---|---:|---:|---:|---:|---:|---:|
| first / 16 | 176.81% | 2.928%–3.163% | 98.591%–98.916% | 766720 / 113664 | 0.000%–0.000% | 0.000%–0.000% |
| first / 36 | 158.19% | 1.508%–2.059% | 97.800%–98.350% | 271360 / 38656 | 44.574%–46.341% | 43.012%–47.232% |
| recheck / 1 | 91.06% | 0.000%–0.000% | 0.000%–0.000% | 65752832 / 9873920 | 0.000%–0.000% | 0.000%–0.000% |
| recheck / 2 | 90.42% | 0.000%–0.000% | 0.000%–0.000% | 7497728 / 1164032 | 0.000%–0.000% | 0.000%–0.000% |
| recheck / 3 | 60.69% | 0.000454%–0.000466% | 0.020%–0.199% | 3389952 / 482816 | 0.000%–0.000% | 0.000%–0.000% |
| recheck / 36 | 153.24% | 1.490%–1.547% | 96.587%–98.147% | 268544 / 39168 | 44.778%–46.414% | 44.040%–45.937% |

All measured retry workers make progress. At 36, KD node1 whole shares remain 44.57%–46.34% first and 44.78%–46.41% recheck; selected-peak shares are 43.01%–47.23% and 44.04%–45.94%. These are near the 16/36 worker fraction, so the observed throughput loss is not explained by a stopped minority node. Finite progress does not establish a starvation bound. The added retry changes admission timing and races; throughput measurements alone do not identify which altered interleaving causes the loss.

Both comparisons preserve min/median/max, whole-run throughput and spreads. Offline audit inputs and per-arm progress/node statistics are recorded in `/tmp/kd-mutex-regression-audit-1003b.json`, with reproducible record-only checks in `/tmp/kd-mutex-regression-audit-1003b.py`. Exact frozen source/binary/session retirement checks remain the archive collector's separate responsibility.

## Rejected mutex node packing

The isolated packing experiment is preserved as `ad59ff3` on `perf/mutex-pack-rejected-20261003b`; `5b75d60` reverts it. The node remains 256 bytes, aligned to 64 bytes. Request identity/state and logical RIP/RSP/RBP move into line 0, the five virtual GPR backings into line 1, and the queue link remains separate from polling in line 3. The two-word wrapper ABI, `kd_regs` layout, original Linux `pt_regs`, physical return-stack semantics, and independent node/frame lifetimes remain unchanged. Prefetching changes from five hints to four: core and queue-link lines plus the existing two caller-stack hints. This is one object-layout/prefetch candidate, so its two parts were not measured independently.

The c1 screen has 18/18 valid samples at 16/36 workers, the first hash screen 18/18 at 16/36, and the hash recheck 9/9 at 36. All 45 records are `OK` and drained; all KD samples have returned JIT bodies, all TCLock samples report delegation, and every worker advances in both whole-run and selected-peak counts. The offline audit reproduces peak selection, business-data validation, CPU bindings and count sums. The candidate passes these functional and measurement checks but fails the protected performance criterion.

For hash, the latest ec45 recheck is the fixed reference for both packing rounds. Its KD peak medians at 16/36 are 3.817764/1.924143 Mops/s, and whole medians are 3.899225/1.829779. The comparisons below use unrounded data.

| Hash phase / workers | KD peak median | Change from fixed ec45 reference | KD whole median | Change from fixed ec45 reference |
|---|---:|---:|---:|---:|
| First / 16 | 3.768320 | −1.30% | 3.829705 | −1.78% |
| First / 36 | 1.815027 | −5.67% | 1.701618 | −7.00% |
| Recheck / 36 | 1.845459 | −4.09% | 1.821289 | −0.46% |

The 36-worker peak-median loss exceeds 3% in both trials, so packing is rejected. Its recheck still includes a valid 2.674327 Mops/s maximum, yielding 119.41% of that phase's TCLock maximum; the first phase reaches only 85.04%. The recheck KD range is 1.831836–2.674327 Mops/s, a 45.65% peak spread. The high best window does not erase the repeated protected median loss. Both the reference and candidate have substantial 36-worker variability, so this is a failed acceptance screen, not a precise estimate of the layout's isolated cost.

For c1, packing yields peak medians 9.054707/8.276468 and whole medians 8.923697/7.951708 at 16/36. Against the latest available matching ec45 points (16 from the first screen; 36 from the recheck), peak changes are −0.54%/+1.38% and whole changes +0.72%/−1.03%. These do not establish a repeatable c1 improvement. Using the older 36-worker first-screen reference would show +5.82% peak, but that should not replace the later same-source reference.

All throughput values are Mops/s; spreads are `(max-min)/median`. Each row contains three valid rounds.

| Phase / threads | Arm | Peak min / median / max | Peak spread | Whole min / median / max | Whole spread |
|---|---|---:|---:|---:|---:|
| c1 first / 16 | kdlock | 8.965 / 9.055 / 9.154 | 2.09% | 8.732 / 8.924 / 8.935 | 2.27% |
| c1 first / 16 | tclock | 4.610 / 4.618 / 4.762 | 3.30% | 4.595 / 4.601 / 4.747 | 3.30% |
| c1 first / 16 | native | 6.616 / 6.883 / 7.388 | 11.21% | 6.453 / 6.828 / 7.337 | 12.93% |
| c1 first / 36 | kdlock | 7.765 / 8.276 / 8.481 | 8.65% | 7.328 / 7.952 / 8.396 | 13.44% |
| c1 first / 36 | tclock | 4.519 / 4.554 / 4.577 | 1.27% | 4.514 / 4.549 / 4.564 | 1.09% |
| c1 first / 36 | native | 4.879 / 5.380 / 5.479 | 11.16% | 4.644 / 4.996 / 5.135 | 9.84% |
| hash first / 16 | kdlock | 3.730 / 3.768 / 3.805 | 2.00% | 3.808 / 3.830 / 3.921 | 2.96% |
| hash first / 16 | tclock | 3.999 / 4.083 / 4.085 | 2.12% | 3.982 / 4.066 / 4.070 | 2.16% |
| hash first / 16 | native | 4.645 / 4.699 / 4.708 | 1.34% | 4.619 / 4.684 / 4.687 | 1.46% |
| hash first / 36 | kdlock | 1.630 / 1.815 / 1.869 | 13.17% | 1.670 / 1.702 / 1.736 | 3.87% |
| hash first / 36 | tclock | 2.185 / 2.193 / 2.198 | 0.58% | 2.167 / 2.182 / 2.182 | 0.70% |
| hash first / 36 | native | 2.575 / 2.659 / 2.667 | 3.46% | 2.449 / 2.490 / 2.580 | 5.26% |
| hash recheck / 36 | kdlock | 1.832 / 1.845 / 2.674 | 45.65% | 1.677 / 1.821 / 2.056 | 20.85% |
| hash recheck / 36 | tclock | 2.208 / 2.209 / 2.240 | 1.41% | 2.193 / 2.198 / 2.211 | 0.80% |
| hash recheck / 36 | native | 2.713 / 2.743 / 2.752 | 1.39% | 2.549 / 2.684 / 2.701 | 5.65% |

| Phase / threads | KD max / TC max | KD JIT share | TC delegation share | KD min worker whole / peak ops | KD node1 whole share | KD node1 peak share |
|---|---:|---:|---:|---:|---:|---:|
| c1 first / 16 | 192.22% | 2.448%–3.079% | 98.835%–98.912% | 916480 / 134400 | 0.000%–0.000% | 0.000%–0.000% |
| c1 first / 36 | 185.30% | 1.146%–1.719% | 98.113%–98.575% | 290560 / 49152 | 41.935%–45.873% | 43.637%–47.634% |
| hash first / 16 | 93.15% | 11.111%–12.571% | 97.413%–97.581% | 436736 / 64768 | 0.000%–0.000% | 0.000%–0.000% |
| hash first / 36 | 85.04% | 22.336%–25.140% | 97.626%–97.986% | 60160 / 8704 | 34.075%–36.347% | 33.435%–40.575% |
| hash recheck / 36 | 119.41% | 13.242%–24.184% | 95.518%–97.891% | 61440 / 1792 | 45.312%–47.885% | 43.545%–47.368% |

At 36 hash workers, node1 has 16/36 (44.44%) of workers. KD whole-run node1 shares are 34.07%–36.35% in the first trial and 45.31%–47.89% in the recheck; selected-peak shares are 33.43%–40.58% and 43.55%–47.37%. The recheck improves node balance but still has the protected median loss, and its least-progressing peak worker completes only 1,792 operations. Positive progress is not a starvation guarantee. No 24-worker result or full matrix was measured for this candidate.

The generated hash evidence also limits the proposed explanation. Both the historical image and frozen ec45 image contain two textual `Stack_R11` loads and one store, with no `Stack_R12`–`Stack_R15` references. R11 is at node offset 136 before packing and 96 after packing; it shares the waiter-polling line under neither layout. Therefore these images do not support repeated GPR-backing writes contending with waiter polling as the explanation for the observed hash gap. Packing reduces the request core's footprint, but also puts logical IP/SP/BP completion writes into the polling line. That is a possible tradeoff, not a measured cache-causality result. The existing hash images do not justify another broad GPR-prefetch experiment.

The generated-code review is `/tmp/kd-mutex-node-pack-hash-audit-1003b.json`; the record audit and all-arm progress/node statistics are `/tmp/kd-mutex-regression-audit-1003b.{json,py}`. Exact frozen input/ELF identities and full lifecycle logs remain separate archive checks. All valid measurements, including the high recheck maximum and rejected candidate, are retained.

The native-retry experiment is preserved by `ae7a26b` / `perf/mutex-retry-rejected-20261003b`, reverted by `6ab4f10`. Packing unit verification (`node-pack-unit`) passed the two basics, actual stack-return fixture, resources and outer-progress driver (five drivers total). Its CLI typo `--workloads` was rejected before output creation/session execution; the corrected `--workload` run is the scored phase.
