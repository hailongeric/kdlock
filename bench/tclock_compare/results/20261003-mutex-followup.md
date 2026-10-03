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
