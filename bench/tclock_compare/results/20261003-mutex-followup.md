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
