# 2026-10-08: mandatory-JIT mutex optimization trials

No runtime candidate was promoted. Bounded task retention repeatedly regressed;
the smaller changes did not establish a repeatable benefit against both opening
and closing baselines. Production code is restored. The retained change adds
checks for the existing combiner gate-return contract (`2a5ca3f`). Mutex JIT remains
mandatory; no disabled-JIT control or option was introduced.

These are **306 valid sessions**, comparing KD, TCLock and Linux Native at 16/36
threads with one-cacheline and hash payloads. Screens, rechecks and unchanged
baselines remain separate. Full distributions are in [statistics](20261008-mutex-priority-trials-statistics.csv);
[samples](20261008-mutex-priority-trials-samples.csv) retain individual results,
execution evidence and worker/node progress. Rejected patches and samples are preserved too.

## Decisions

Changes below compare peak medians with the opening baseline. Each candidate was
tested independently; the guard was absent from retention and execution trials.

| Candidate | Result | Decision |
| --- | --- | --- |
| Read the disabled fault flag before CAS | Hash36 changed −12.13%, then +11.13%; spreads were 58.12% and 61.44% | Inconclusive; restored |
| Retain at most 1,024 exact task identities | Cacheline16 lost 34.57% / 35.47%; cacheline36 47.59% / 49.78%; hash16 28.80% / 28.54%; hash36 16.73% / 36.47% | Rejected after recheck; restored |
| Reuse the mutex ledger predicate after root checks | Hash36 changed −9.20%, then +18.69% | Inconclusive; restored |
| Remove repeated caller-side gate restoration | Hash36 initially gained 9.60% / 12.52%, cacheline36 6.63% / 7.66% | Gains overlap unchanged-baseline variation; restored |

The unchanged closing baseline moved materially. Rates are Mops/s; “peak” here
means the median of each round's best valid window, not the best of three rounds.
Whole-run throughput includes settling and can exceed the selected settled peak.

| Payload / threads | Opening peak | Closing peak | Opening whole | Closing whole |
| --- | ---: | ---: | ---: | ---: |
| Cacheline / 16 | 7.582 | 7.480 | 7.328 | 7.249 |
| Cacheline / 36 | 5.343 | 5.733 | 5.150 | 5.631 |
| Hash / 16 | 3.552 | 3.534 | 3.621 | 3.604 |
| Hash / 36 | 2.395 | 2.650 | 1.635 | 1.709 |

Against closing, gate-store hash36 peak changes are only −0.93% / +1.71%.
Its whole-run gains remain +4.03% / +7.02%, but cacheline36 whole medians are
−1.62% / −4.07%. This does not establish an improvement across protected points.
Reference-arm results are retained without using them to “correct” KD scores.

## What this establishes

**More delegation is not itself a benefit.** Retention preserves the original
hash geometry, writer lock and unconditional fault CAS. It removes repeated
allocation/free work on cache hits while preserving inactive zero-ref records,
exact acquisition refs through final ACK, and task refs until drained unload.
At hash16, measured JIT share rises from a 20.24% median to 65.40% / 69.61%, and
lifetime bodies per combiner rise from 20.44 to 286.94 / 372.01. Peak throughput
still falls about 29%. Only 16 task identities are retained in these hash16 runs.
The data show a changed execution mix and queue behavior; they do not isolate
entry cost, quantify registry-lock waiting, or prove hash-chain scans caused loss.

**A source simplification need not shrink generated code.** The ledger trial
removes the outlined predicate call, but its executor grows by 101 bytes and
12 static instructions after compilation. The gate trial removes exactly two
instructions and 15 bytes from its caller; combiner and physical-lock helpers
remain byte-identical. Static size is not an executed-instruction count or a
causal explanation for throughput. These comparisons are retained in the archive.

**Peak and progress need separate scrutiny.** The valid retention cacheline36
outlier peaks at 7.388 Mops/s but delivers 3.346 Mops/s over the whole run; node1
contributes only 12.21% of that peak despite owning 16/36 workers. It remains in
the data. Every worker progressed in every whole run and selected window, which
does not establish starvation freedom. KD batch ratios include warmup; JIT shares
and TCLock batch ratios use measured counter deltas. Their scopes are different.

The closing baseline's hash16 best peak is 3.562 Mops/s versus TCLock 4.109 and
Native 4.713: 86.69% and 75.57%, respectively. Hash36 reaches a 2.801 Mops/s best
peak, yet its whole median is 1.709 versus TCLock 2.212 and Native 2.703.
The performance target remains unmet. The full 15-thread sweep was not repeated
because no runtime optimization passed this screen.

## Verification and reproduction

Frozen baseline: `c04b214fd6332f3d2864d7b2283b18748c3aee96`, committed four-round
outside-lock arithmetic; unrelated working-tree caller/payload changes were
excluded. Existing kernel `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, `nopvspin`, verified CPU pinning and
2.5 GHz policy. NUMA-on, KD UBSAN-off and configured batch 1024 remain unchanged.
Mutex admission keeps `mutex_contention1024_ratio256`, native-first acquisition
and the existing successor prefetch. Workers use CPUs 0–15 or 0–35, collector 38,
48,000 warmup operations each,
three rounds, 2 s measurement and a full-cohort 300 ms peak after 300 ms settling.

| Check | Fresh result |
| --- | --- |
| Fault guard | Basic/resource checks and real two-order/four-ACK task probe passed |
| Retention | Basic/resource/cache checks passed, including collisions/capacity/reactivation; real probe verified four ACKs, two reactivations and two unload frees |
| Ledger | Seven selected checks passed: admission, capacity, clobber ABI, terminal/FULL and outer progress |
| Gate contract | Five selected checks passed, including removal mutations for both gate producers; rerun against restored production before commit |
| Live performance | All 306 sessions correct and drained; all 102 KD sessions returned JIT and all 102 TCLock sessions demonstrated delegation |

The two task probes execute no JIT bodies and remain resource evidence only.
The [audit](20261008-mutex-priority-trials-audit.json) covers frozen source plus
each patch, provider overlays, caller/control ELF identity, JIT images, raw
warmup/measurement data, independently reconstructed peaks and retirement.
Exact archive hashes, commands, unit logs and patch identities are in
[evidence](20261008-mutex-priority-trials-evidence.json). Raw archives remain under
host `bench/.tmp/mutex-priorities-20261008/` and guest
`/root/kdlock-evidence/mutex-priorities-20261008/`.

Next work should measure admission routes, batch exit reasons and stage-specific
wait/service time before changing policy. Compare native/delegated crossover
separately for cacheline and hash. Preserve per-request readiness, ownership and
completion checks; the current results do not justify broader prefetch, packing,
larger batches or repeated cache/NUMA policy changes.
