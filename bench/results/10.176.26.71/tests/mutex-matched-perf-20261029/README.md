The mutex performance gap remains unresolved. This matched profiling pair shows more retired instructions and aggregate kernel cycles per completed operation in the current candidate. The extra state and budget bookkeeping is visible in emitted code, but these measurements do not identify it as the cause. They also do not establish increased parking or a dominant cost from shared owner checks. These are diagnostic observations, kept separate from nano scores and later optimization candidates.

Candidate runtime: `99f383624faa872a76521d1b5be7faea586591c1`. Baseline runtime: `1c86d6d1a15d96d75c09504f1041772247707804`, profiled through the tools-only overlay `c8c98f1167ce6be2f5e992cabb4d822307d3b986`, following the documentation commit `2daafa039ed617df477d3743d7911ebf6d7ab939`. Each source has one `stat` and one `record` run of **c01 (one cacheline), post256, 20 workers**, public mutex ABI2, `bulk_ioctl`, CPUs 0–19/node0, collector CPU 63, two seconds, and 48,000 warmup iterations per worker. Provider diagnostics are off; total/local limits are 1024/1024. Both use boot `677b7afa-5358-4ece-a650-5f4a4adecd55`, kernel `7.0.0-38-kdlock1`, recorded build ID `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62` and `full (lazy)` preemption.

All four sessions exited successfully, validated data and reported drain. Returned JIT bodies equal completion deltas, with no address-guard exit. Every final retirement receipt has state 2 and zero frames, modules and writers. Image publication alone is not used as completion evidence.

| Source / mode | Completed operations | Returned JIT completions |
|---|---:|---:|
| Baseline / stat | 9,020,416 | 8,955,676 |
| Candidate / stat | 7,902,720 | 7,847,281 |
| Baseline / record | 8,498,944 | 8,433,067 |
| Candidate / record | 7,744,768 | 7,687,789 |

Whole-client `stat` includes inherited workers and client startup/collection, after preparation and warmup. All events report 100% runtime without multiplexing. Counts are divided by completed operations, not JIT completions or peak-window progress.

| Whole-client stat metric | Baseline | Candidate | Change |
|---|---:|---:|---:|
| Kernel cycles / op | 8,764.33 | 9,998.58 | +14.08% |
| Kernel instructions / op | 2,452.80 | 3,502.48 | +42.80% |
| Kernel cache misses / op | 0.037789 | 0.035823 | −5.20% |
| Context switches, total | 475 | 451 | — |
| CPU migrations, total | 20 | 20 | — |

Those software-event totals are not worker parking events, reasons or off-CPU durations. Fewer completed operations under almost equal aggregate CPU time increase per-operation counts; the totals do not locate the initiating bottleneck. Generic cache misses do not measure notification-line coherence latency.

The separate `record` runs sample `cycles:k` at 997 Hz without call graphs. The IP review uses only settled `rb_worker` samples and each run's own progress-aligned interval: 7,143,680 published operations over 1.680000421 seconds in the baseline, versus 6,505,216 over 1.679996782 seconds in the candidate. Published progress is batched by 256 per worker; snapshot skew and up to 5120 unpublished operations per endpoint make these ratios approximate aggregate sample periods per operation, not lock latency.

| Progress-aligned flat attribution | Baseline period/op | Candidate period/op |
|---|---:|---:|
| All sampled worker regions | 8,953.84 | 9,829.88 |
| `__kd_mutex_lock_slowpath` | 6,942.39 | 7,816.26 |
| `kd_mutex_execute_cs` | 245.66 | 237.09 |
| `kd_mutex_run_combiner` | 82.06 | 117.69 |

Waiting workers account for most net sampled growth; that can amplify slower execution elsewhere. Shared initial owner/gate and frame-retirement check regions do not increase in this pair. New READY load/test neighborhoods appear in samples, but sampled IP skid prevents interpreting them as load latency. No stat total is multiplied by a separately collected IP share to manufacture a function cost.

The two verified archive trees contain **four archives and 2789 inventoried paths**. The independent check matches compact receipts, all four binary manifests, and all four 293-file source snapshots. Some snapshots retain synchronization leaves: `include/kd_rwsem_direct.h` and `kernel_module/kd_rwlock.c` in both sources, plus `kernel_module/mutex/pin_diag.inc`, `pin_origin.inc` and `pin_window.inc` in the baseline. None appears in archived build `.cmd` dependencies; tracked source bytes match the declared Git blobs. Entire snapshot identity to Git is not claimed. Independently, both baseline providers' actual 133230-byte `.text` and full relocation tuples equal the original 1c mutex nano provider. `.text` SHA256 is `302213c976df9d26c1e4292f235daed4266fef5047bed1bcc2334be428665192`.

The retained `perf` binary is identical in all four runs, but recorded `perf_event_max_sample_rate` changes from 100000 in the candidate to 9000 in the later baseline. Both exceed 997 Hz; that does not establish equal sample delivery or rule out dynamic throttling. Both raw summaries conserve samples and periods with no reported lost samples; throttle records were not decoded. The record windows are about 15.8 minutes apart, with fixed order and one observation per source/mode. No performance gain, gap closure or no-regression acceptance follows from this evidence.

Detailed evidence is preserved unchanged:

- [Independent receipt, source and binary verification](kdlock-mutex-matched-perf-verification-20261029.md), with [JSON](kdlock-mutex-matched-perf-verification-20261029.json).
- [Matched IP mapping and denominator review](kdlock-matched-perf-ip-review-20261029.md), with [JSON](kdlock-matched-perf-ip-review-20261029.json), and [baseline executable identity](kdlock-baseline-perf-elf-identity-20261029.json).
- [Candidate results](kdlock-once-perf-results-20261029.json) and [archive verification](kdlock-once-perf-archive-verification-20261029.json); [baseline results](kdlock-baseline-perf-results-20261029.json) and [archive verification](kdlock-baseline-perf-archive-verification-20261029.json).
- [Copied artifact hashes](artifact-sha256.json), [candidate raw archives](../../raw/tests/mutex-admission-once-perf-20261029/bench/mutex-admission-once-perf-20261029-archives/) and [baseline raw archives](../../raw/tests/mutex-pinned-baseline-perf-20261029/bench/mutex-pinned-baseline-perf-20261029-archives/).

Verification was read-only offline Git/archive/ELF/JSON inspection. No archived code, host build/test or VM operation was executed during this review.
