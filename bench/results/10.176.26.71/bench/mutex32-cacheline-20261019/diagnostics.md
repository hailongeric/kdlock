# Owner, gate and tail diagnosis

The fresh ordinary comparison retains `76af844`, with small observed median
changes of +5.0%/+0.9% at eight/sixty workers and remaining old256 gaps of
18.8%/22.4%. The following diagnostic evidence explains the changes and limits
the contention claim. None of these profiles or controlled placements is pooled
with the ordinary timings in [comparison.json](comparison.json).

## Actual ordinary placement

The archived `pipe/records.json` and `profile/pipe/records.json` contain the
actual loaded `lock_addr` for all six ordinary and both profiled sessions in
each source arm. All eight records within each arm agree:

| Arm | Actual lock address | Address modulo 64 | Owner line:byte | Gate line:byte | Tail line:byte |
| --- | --- | ---: | --- | --- | --- |
| `packed32` | `0xffffffffc07984e0` | 32 | 0:32 | 0:56 | 0:60 |
| `candidate` | `0xffffffffc07984e0` | 32 | 0:32 | 0:56 | 0:60 |
| `old256` | `0xffffffffc0798580` | 0 | 0:0 | 1:8 | 2:0 |
| `prefetch` trial | `0xffffffffc07984e0` | 32 | 0:32 | 0:56 | 0:60 |

Line zero is the line containing the object's beginning. Current owner, gate
and tail offsets are 0, 24 and 28. Old256's owner, phase and tail offsets are
0, 72 and 128; its separate physical-owner witness and exact waiter counter
are at offsets 64 and 192. Those source offsets, applied to the observed
addresses, establish the field placement above. The benchmark's `gate_addr`
record denotes the lock argument, not a separately measured phase-field address.
The original records and source bytes are bound by [archive review](archive-review.json).

The ordinary compact object's owner, gate and tail therefore share a line in
this collection. Native 8-byte alignment alone does not imply this arrangement:
a caller can place a 32-byte object across a cache-line boundary. No universal
placement guarantee or caller-layout requirement is inferred from this module's
observed addresses. The old256 comparison also changes storage and runtime
details, so it is not a placement-only experiment.

## Controlled owner separation

Diagnostic source `09ebd8f` retains provider bytes identical to `0987358` and
adds only a benchmark compile option. Each offset uses a dedicated 128-byte
storage region aligned to 64 bytes. Offset 32 puts owner/gate/tail at line
0 bytes 32/56/60. Offset 40 puts owner at line 0 byte 40 and gate/tail at line
1 bytes 0/4. Compiled module metadata, actual lock addresses and unchanged
provider hashes are checked. See [PLACEMENT.md](PLACEMENT.md) for the method.

Each group has three 2000 ms diagnostic repetitions; entries are median
[minimum–maximum] Mops/s. The offset-32 block precedes the offset-40 block.

| Workers | Offset 32 | Offset 40 | Median change |
| ---: | ---: | ---: | ---: |
| 8 | 4.983 [4.927–5.527] | 5.649 [5.182–5.804] | +13.375% |
| 60 | 4.125 [3.996–4.223] | 4.156 [4.104–4.185] | +0.743% |

Operation-weighted returned-JIT shares are 92.882% versus 94.328% at eight
workers and 95.378% versus 94.995% at sixty. The changed execution mix is part
of the observed result, not a controlled constant. All twelve sessions pass
and drain; full precision and provenance are in
[placement-analysis.json](placement-analysis.json).

The eight-worker observation supports sensitivity to this owner separation.
The small sixty-worker difference does not establish owner sharing alone as
a substantial cause of the remaining gap there. Both placements still put
gate readers and tail writers on the same line, and both use dedicated padding
that changes the object's neighbors relative to the ordinary benchmark.
This pair cannot isolate all owner/gate/tail interactions or quantify a
cache-transfer cost. Sequential blocks and overlapping ranges further limit
causal and statistical claims.

## Avoided work and preserved checks

`76af844` avoids touching the tail when a successor is already linked, retaining
the exact retirement CAS and delayed-link handshake for races. It also inlines
the unchanged bounded-probe hint and exact ownership predicate. The full
zero-owner acquisition CAS, fresh owner/PICKUP/phase checks, and independent
physical-owner probes remain. [Source review](source-review.md),
[machine-code review](code-review-manual.md) and
[independent review](independent-review.md) cover lifetime, ordering and the
actual ELF branches. No separate arm measures each individual optimization,
so the total median change cannot be apportioned.

The separate [prefetch trial](prefetch-source-review.md) retained every
validation while adding read hints. Its +1.53%/+1.36% median changes versus
`76af844` have overlapping repetition ranges. The trial was rejected as
inconclusive and reverted by `044e351`; its source, checks and all six timings
plus two profiles remain preserved under their own identity. This is not a
claim that prefetch regressed performance.

## Delegation and batching

Returned-body shares below sum measured completions and measured operations
across each three-repetition ordinary cohort. They are not unweighted means
of per-repetition percentages. Body-entry shares equal return shares in these
groups. The final columns are medians of whole-session bodies/combiner ratios,
which include warmup and checks; they are not measured-phase batch distributions.

| Arm | Returned JIT, 8 workers | Returned JIT, 60 workers | Bodies/combiner, 8 | Bodies/combiner, 60 |
| --- | ---: | ---: | ---: | ---: |
| `packed32` | 92.811% | 95.361% | 125.902 | 128.043 |
| `candidate` | 92.732% | 95.463% | 125.781 | 127.945 |
| `old256` | 95.998% | 94.924% | 189.071 | 127.558 |
| `prefetch` trial | 93.389% | 95.510% | 130.392 | 127.948 |

Old256 has more delegation and a larger whole-session batch ratio at eight
workers. These differences may contribute to its advantage but are not isolated
cost estimates. At sixty workers the retained compact implementation delegates
slightly more than old256 and all batch ratios are near 128. Lower delegation
and smaller batches therefore cannot explain the remaining gap uniformly.
The candidate's eight-worker returned share is slightly below its compact
baseline despite its higher observed median throughput.

## Separate flat profiles

Each source has one unscored `cycles:k` profile per worker count at 199 Hz.
The driver attaches to the idle client, inherits its workers, and requires
start/stop FIFO acknowledgements. The exact retained perf executable SHA-256 is
`be41fc3678db80aa92593a72034ebd6ec4c574c2dca2523f294dff5a0667aca3`.
All eight reports have zero reported lost samples and zero parse errors;
the independent audit reparses 109590 samples.

Sample weights below are each symbol scope's fraction of observed cycle periods
for `sc_worker` threads. They are flat attribution, not call-graph totals or
elapsed-time fractions. Profile throughput is shown only to make perturbation
visible and never enters a benchmark median. JIT change is in percentage points
against that source/worker count's ordinary cohort.

| Arm | Workers | Profile Mops/s, unscored | Returned JIT | JIT change | Slowpath scope | Combiner/body scope |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `packed32` | 8 | 4.694 | 93.333% | +0.523 | 60.920% | 5.942% |
| `candidate` | 8 | 4.807 | 92.716% | −0.016 | 57.082% | 7.192% |
| `old256` | 8 | 5.635 | 92.494% | −3.504 | 54.806% | 7.560% |
| `prefetch` | 8 | 5.131 | 92.355% | −1.034 | 59.311% | 8.560% |
| `packed32` | 60 | 3.790 | 95.222% | −0.139 | 94.091% | 1.157% |
| `candidate` | 60 | 3.936 | 94.872% | −0.591 | 94.059% | 1.366% |
| `old256` | 60 | 5.075 | 94.653% | −0.272 | 93.426% | 1.332% |
| `prefetch` | 60 | 4.108 | 95.087% | −0.422 | 93.781% | 1.442% |

Slowpath means `__kd_mutex_lock_slowpath`; combiner/body means
`kd_mutex_run_combiner` plus `kd_mutex_execute_cs`. These broad scopes contain
multiple activities. In particular, slowpath attribution cannot be presented
as gate or tail contention cost. The old256 eight-worker profile changes the
returned-JIT share by −3.504 percentage points, so its sampled execution mix
does not match its ordinary cohort. Even profiles with closer mixes are single
instrumented observations. [profile-analysis.json](profile-analysis.json)
retains all-kernel and worker denominators, scope definitions, sampled offsets
and plain-context comparisons. The all-kernel denominator covers the attached
client's inherited process tree, not every task in the VM. Scopes may overlap
and must not be added indiscriminately.

The [PMU capture](pmu-capabilities.log) records available generic and memory
events; this round did not collect a validated HITM or cache-transfer count.
Sampled instruction addresses can skid, and no failed-CAS count was collected.
Inlining also changes symbol attribution. These profiles can locate sampled
work but cannot price a CAS, prove that a particular line transfer dominates,
or justify dropping exact ownership and lifetime checks. The sixty-worker
pipe deficit remains unresolved by this focused optimization.
