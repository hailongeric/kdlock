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
