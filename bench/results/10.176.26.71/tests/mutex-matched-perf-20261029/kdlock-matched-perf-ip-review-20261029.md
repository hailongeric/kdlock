Independent matched perf review, 2026-10-29

The matched profiles confirm extra aggregate work per operation in candidate `99f383624faa872a76521d1b5be7faea586591c1`, but do not establish shared owner/gate checks as the cause. `kd_mutex_execute_cs` has slightly lower normalized sampled periods; `kd_mutex_run_combiner` has higher periods, while waiting workers account for most of the aggregate increase. These are single instrumented observations, not performance acceptance.

Both arms ran c01 (one cacheline), post-work 256, 20 workers on CPUs 0–19, with collector CPU 63. The baseline tools overlay is `c8c98f1167ce6be2f5e992cabb4d822307d3b986`, retaining runtime `1c86d6d1a15d96d75c09504f1041772247707804`. Recorded boot ID is `677b7afa-5358-4ece-a650-5f4a4adecd55`; the record windows are about 15.8 minutes apart. Recorded topology, kernel identity and preemption policy match. All four sessions report valid data, successful execution, joined workers, drain and exact retirement.

Actual ELF identity is verified, separately from Git identity: both baseline stat and record providers have the same 133230-byte `.text` and relocation tuples as the original 1c mutex nano provider. `.text` SHA256 is `302213c976df9d26c1e4292f235daed4266fef5047bed1bcc2334be428665192`; whole ELF hashes differ. The profile overlay changes optional diagnostics/schema support, while the stat parser, sample filter, perf command, measured-client wrapper and symbol capture are AST-identical. No archived code was executed.

Whole-client stat includes inherited workers plus client startup/collection. Stat and record are separate invocations. Each stat event reports 100% runtime without multiplexing.

| Whole-client stat metric | Baseline | Candidate | Change |
|---|---:|---:|---:|
| Mops/s | 4.486588 | 3.930638 | -12.39% |
| cycles:k per completed op | 8764.330953 | 9998.578597 | +14.08% |
| instructions:k per completed op | 2452.801586 | 3502.479943 | +42.80% |
| cache-misses:k per completed op | 0.037789 | 0.035823 | -5.20% |

The flat record uses `cycles:k` at 997 Hz, only `rb_worker` samples in the settled full cohort. The normalization below further restricts each arm to the first and last complete progress snapshots inside that interval. The published-operation denominators are 7,143,680 and 6,505,216 over 1.680000 s and 1.679997 s. Progress publishes in batches of 256 per worker, allowing up to 5120 unpublished operations at each endpoint, and snapshots are sequential. These ratios are approximate aggregate sampled periods per published operation; they are not acquisition or service latency.

| Progress-aligned sampled region | Baseline period/op | Candidate period/op | Difference |
|---|---:|---:|---:|
| `ALL` | 8953.84 | 9829.88 | +876.04 |
| `__kd_mutex_lock_slowpath` | 6942.39 | 7816.26 | +873.87 |
| `kd_mutex_execute_cs` | 245.66 | 237.09 | -8.57 |
| `kd_mutex_run_combiner` | 82.06 | 117.69 | +35.62 |
| `rb_run` | 1084.95 | 1044.63 | -40.32 |
| `GENERATED_IMAGE` | 99.70 | 94.48 | -5.22 |

The origin initial-spin region rises from 6632.32 to 7517.27 sampled periods/op. Almost all net flat-symbol growth is in the slowpath (+873.87 of the aggregate +876.04). This is waiting amplification, which may follow a slower executor or other serialization; it does not locate the initiating bottleneck. The baseline spin loop is PAUSE/load/test/branch, whereas the candidate also validates state and maintains its initial spin budget. That emitted difference is consistent with extra instructions, but no per-function instruction measurement attributes the stat increase to it.

The common initial owner/gate region falls from 63.36 to 50.19 sampled periods/op; frame-retirement owner checks fall from 75.12 to 73.34. New candidate READY admission/test and completion/test neighborhoods contribute 17.90 and 18.20 periods/op, and the new completion private-epoch/owner/gate region contributes 19.66. Absent baseline labels mean those exact new code blocks do not exist, not that related baseline work is free.

Exact candidate hot IPs include `kd_mutex_execute_cs+0x9cb` (ELF `0x14acb`, READY compare after the byte load at `0x14ac4`) and `kd_mutex_run_combiner+0x3b0` (ELF `0x19340`, READY compare after `0x19339`). Shared owner-region samples land primarily on adjacent register instructions in both arms. Ordinary frequency sampling can skid; these are instruction-neighborhood observations, not remote-load latency or cache-line misses. A read-only successor notification-line prefetch remains a bounded hypothesis requiring measurement.

The raw samples reproduce both recorded summary totals with no reported lost-event lines. However, recorded `perf_event_max_sample_rate` changed from 100000 in the candidate to 9000 in the later baseline. Requested 997 Hz is below both, but this remains an environment difference. Generic cache-miss counts cannot isolate the notification line. Whole-client context switches (475 baseline, 451 candidate) are not parking counts. No randomized repeats, parking attribution or no-regression claim is supported.

Artifacts: `/tmp/kdlock-matched-perf-ip-review-20261029.json` preserves selected ELF/IP mappings, source identities, both denominators, symbol/region tables and limitations; `/tmp/kdlock-baseline-perf-elf-identity-20261029.json` preserves the actual code/relocation comparison. Candidate-only `/tmp/kdlock-once-perf-ip-review-20261029.json` remains unchanged.
