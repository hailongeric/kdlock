# Prior pipe delegation investigation

The retained `0324e60` and `e999008` pipe results point to shorter batches and
more physical fast acquisitions. They do not show a translation-readiness or
instruction-admission failure. This is a read-only investigation of the preceding
comparison, not new timing evidence or a causal attribution of the remaining gap.

[`prior-pipe-analysis.py`](prior-pipe-analysis.py) reads original Git sources,
checks the two compressed archive hashes, and reconciles retained kernel counters,
warmup/measurement replies and session summaries. It does not build, test, import
or execute archived code. [`prior-pipe-analysis.json`](prior-pipe-analysis.json)
retains every derived value, source/input hash and missing counter row.

| Version | Workers | Bodies per combiner, whole-session range | Physical fast share, whole-session range | Returned JIT share, measured phase |
| --- | ---: | ---: | ---: | ---: |
| 256 B, `0324e60` | 8 | 164.96–344.52 | 2.36–21.16% | 96.77% |
| 32 B, `e999008` | 8 | 35.79–69.69 | 11.48–32.47% | 87.79% |
| 256 B, `0324e60` | 60 | 127.34–127.73 | 4.87–4.88% (two complete records) | 94.98% |
| 32 B, `e999008` | 60 | 66.61–67.06 | 12.13–12.78% | 86.54% |

Whole-session columns include warmup and two redirected checks. The measured JIT
column is the sum of returned bodies divided by the sum of measured operations
within the preceding three-repeat group. These scopes must remain separate.
Repeat zero has a substantial warmup transient at eight workers in both versions;
the later repeats' physical fast shares are 2.36% for inline and 11.48% / 12.81%
for compact. These are diagnostic reconstructions, not ownership records or new
performance samples.

The reconstruction sums each printed CPU's completed heat checks times 1,024 and
its unfinished contention count. Subtracting that result from warmup operations,
measured operations and the two checks gives physical fast acquisitions for this
private workload. One inline 60-worker session omits CPU 59's ratio line because
its unfinished entry count is zero; that session's total contentions and physical
fast share remain null. No missing row is silently treated as a zero lifetime
count. The general heat counters are approximate admission state, and this
diagnostic reconstruction must never replace exact runtime lifetime accounting.

For each compact 60-worker session, reconstructed contentions minus JIT successes
and delegation-owner acquisitions is exactly `60 * 2047` plus its 4 / 1 / 4 BUSY
refusals. Complete inline records give exactly `60 * 2047`. With an initially
successful CPU heat check at contention 1,024 and 1,025 per-lock records, the first
admitted contention is 2,048: 2,047 initial refusals per worker. Compact eight-worker
repeats one and two similarly give `8 * 2047` plus their BUSY counts. Repeat zero
has an additional 16,384 residual; the receipt preserves it without assigning it
to a particular phase. All printed final mutex heat states are hot.

All twelve pipe sessions have zero JIT-not-ready, JIT-failure, frame-failure,
context-busy, node-overflow and handoff counters. The evidence therefore does not
support changing the admission thresholds to fix this regression. At 60 workers,
seek and c08 retain approximately 128 bodies per combiner in both versions, while
the compact c01 and pipe batches are shorter. Slower producer circulation is a
plausible explanation for exhausting these shorter-body batches before another
local request arrives. The counters do not identify each batch's stopping reason.

Two implementation changes are worth measuring independently. Every compact
delegation invocation adds a shared auxiliary-reference acquisition and release;
the acquisition currently uses a retrying compare/exchange loop. Also, the outer
physical fast path still allows eight probes, but its former inline gate load is
now an out-of-line hash/sequence/key/gate query on each busy probe. The eight-probe
window can therefore take longer, permitting more native successes before queue
admission, while also delaying arriving producers. These are concrete mechanisms,
not established per-operation costs. Any optimization must retain the physical
owner CAS, exact lifetime protections, instruction admission and existing batch
fairness boundaries.
