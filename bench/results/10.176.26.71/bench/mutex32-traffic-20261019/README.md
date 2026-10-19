# Compact mutex reference traffic and pipe delegation

The maintained `ba98937` keeps **32 bytes and native 8-byte alignment**, the KD
physical protocol and automatic auxiliary retirement. Counted fetch-add pins
remove the reference-acquisition CAS retry loop; inlined helpers and simpler
common guards reduce instruction work. Auxiliary lookup still uses one fixed
hash-indexed slot, with no registry locks or RCU. The provider preallocates
65,536 slots (16 MiB); no allocation or caller cleanup is added per acquisition.

Pipe median throughput improves **3.2% / 1.9%** at eight / 60 workers versus
the previous compact version, but remains **21.6% / 31.0% below** the old
256-byte object. Other workload changes are mixed. This round does not close
the remaining performance gaps or establish a general speedup.

## Sources and decision

| Arm | Runtime revision | Change |
| --- | --- | --- |
| `baseline` | `e999008cf7035c03271f8622afa3a9ef88cb197c` | Previous direct-index, reference-transfer implementation |
| `fetchadd` | `113b317acab178212aa80c671afcf67a26a85beb` | One counted fetch-add per pin, additive lifecycle transitions |
| `old256` | `0324e60d6791948e9762a9916a50e8e026f073b0` | Old 256-byte, 128-byte-aligned inline state |
| `hint` | `cd49d65` | Cached slot address across bounded outer retries; rejected |
| `inline` | `ba98937db35f47aa2c0f066019019b0e5db94bf1` | Fetch-add plus explicitly inlined pin helpers and common guards |

These are five fresh, separate source blocks in the listed order. Earlier
rounds are retained unchanged and never pooled. The cached-slot experiment
showed no useful pipe improvement over fetch-add and a 5.5% lower c08 median
at 60 workers. It was reverted by `cf024da`; branch
`archive/mutex32-traffic-hint-20261019` preserves it. Final source does not
contain that retry-loop change.

The final candidate prioritizes the modest pipe improvement while retaining
mixed c01/c08/seek outcomes. Against fetch-add alone, inline changes pipe by
+6.3% / −0.7%; fetch-add alone changes pipe by −3.0% / +2.6% against the prior
compact version. There is no claim that inline wins every cohort. Three
repetitions in sequential blocks cannot distinguish all scheduling variation
from small implementation effects.

## Measured results

All **120 plain sessions** passed result, progress, source and drain checks.
Each source runs c01, c08, SEEK_SET n16 and pipebytes/query n16 at eight and 60
workers, three repetitions each. All 40 groups are complete. The primary metric
is median whole-run Mops/s; each cell below is eight / 60 workers.

| Workload | Previous 32 B | Fetch-add | Cached slot, rejected | Final 32 B | Old 256 B |
| --- | ---: | ---: | ---: | ---: | ---: |
| c01, post64 | 5.520 / 4.332 | 5.556 / 4.417 | 5.776 / 4.381 | 5.405 / 4.378 | 7.055 / 4.972 |
| c08, post64 | 4.899 / 4.054 | 4.985 / 4.057 | 4.874 / 3.834 | 5.070 / 3.964 | 4.792 / 3.649 |
| SEEK_SET, n16 | 4.261 / 3.871 | 4.247 / 3.845 | 4.136 / 3.857 | 4.115 / 3.814 | 4.968 / 3.995 |
| Pipe FIONREAD, n16 | 5.276 / 3.666 | 5.119 / 3.763 | 5.198 / 3.716 | 5.442 / 3.735 | 6.943 / 5.411 |

The [complete table](comparison-table.md) retains min/max ranges for every group;
[comparison.json](comparison.json) retains individual sessions, source hashes,
execution classes and measured counters. Raw measurements and
[statistics-review.json](statistics-review.json) retain the separate 300 ms peak
reconstruction. For pipe, final
ranges are 5.412–5.463 / 3.727–3.743, previous compact 4.854–5.641 /
3.617–3.696, and old inline 6.446–7.094 / 5.279–5.417 Mops/s. Ranges are observed
variation, not confidence intervals; ratios of medians are not paired estimates.

Against the previous compact version, final c01 changes −2.1% / +1.1%, seek
−3.4% / −1.5%, and c08 +3.5% / −2.2%. Against old inline, c01 remains
23.4% / 11.9% slower and seek 17.2% / 4.5% slower; c08 is 5.8% / 8.6% faster.
No fresh Linux Native or TCLock controls were added in this bounded KD comparison.

Every real API session counted matching JIT returns (`RETURNED_JIT`). Synthetic
sessions have entry witnesses (`WITNESSED_JIT`), with the completion probe
disabled; their entered-body counts do not prove a returned body. A NORMAL
image alone is publication evidence. All profiles are unscored.

## Reference lifetime and delegation findings

The [source review](reference-review.md) traces invocation, physical-owner and
frame/ACK lifetimes. A single fetch-add pins LIVE, including zero before a
retiring put reserves it. Post-pin address validation remains mandatory.
BUSY/FREE lookup results grant no protocol-field access and stay counted until
their ordinary put; publication may make that put the final LIVE release.
Additive publication, failure rollback and retirement preserve those
pins. Only a successful zero-to-BUSY CAS authorizes retirement field access;
a losing final put returns without touching those fields. Exact FREE is required
for reuse. This preserves automatic retirement without per-object destruction.

The [fetch-add ELF inspection](fetchadd-reference-code.json) found an outlined
pin helper with repeated call/return and state-decoding work. The
[final ELF inspection](inline-reference-code.json) confirms no standalone
`try_ref`/`find_ref` symbols: `get` contains the pin RMW and a single unsigned
common bound comparison, and nonfinal `put` takes its short guard. The actual
tested provider ELF and instruction bytes are archived. This proves a code
change, not a dynamic count of cache-line transfers or isolated coherence cost.

References cannot simply be bulk-released when a combiner finishes a batch:
awakened origins may still access auxiliary state in waiter exit or packet
restoration. A persistent per-CPU pin would prevent automatic retirement until
an additional eviction protocol released it. Exact waiter counts have different
boundaries from invocation references and cannot replace them. No reference,
source lease, physical owner, unlock ACK or frame obligation was removed; queue,
batch limits, heat/admission policy, pinned waiting and immutable images remain.

Measured pipe return shares rise from **74.63% / 85.87%** in the previous compact
version to **87.88% / 87.33%** in the final version. Old inline still returns
**96.83% / 94.98%**. Equal `RETURNED_JIT` labels therefore do not imply equal
delegation rates. See the independently reconstructed
[pipe phase analysis](pipe-phase-analysis.md) for whole-session batch and
admission counts, separated from measured-phase return shares.

The whole-session median ratio of JIT successes to combiner starts changes
from **37.31 / 66.25** to **48.11 / 67.34** bodies per combiner; old inline
reaches **311.28 / 127.57**. This is an aggregate ratio, not a batch-size
distribution. Native fast acquisitions reconstructed from approximate admission
diagnostics still represent
**13.44% / 11.66%** of whole-session operations in the final version, compared
with **2.66% / 4.92%** for old inline. Whole-session operations include warmup
and two redirected checks, so these fractions are not measured-phase fallback
shares. All worker ratio rows are present in this fresh round.

At 60 workers, all 15 plain pipe runs reconcile the remaining contended
entries exactly to `60*2047` plus recorded BUSY refusals. At eight workers,
subtracting `8*2047`, BUSY and generation-race refusals leaves zero in 13 of
15 runs; the first baseline and fetch-add repeats retain unexplained residuals
of **28,672** and **16,384**. These whole-session diagnostics cannot locate the
residual in warmup or measurement. All 30 plain pipe logs end with hot CPU/lock
states and zero handoff, JIT-not-ready, JIT-failure, context-busy, node-overflow
and frame-failure counters; indexed arms record no collision, exhaustion or
injected failures. The remaining gap is associated with shorter service
batches and more native acquisition, without evidence here of failed JIT
execution or sustained admission refusals at 60 workers. Reference/producer
latency can affect those batch arrivals, but this does not isolate its cost.

Ten flat `cycles:k` profiles at 199 Hz retain **136,990 parsed samples**, with
zero reported loss. The [profile table](profile-table.md) compares every
profile's execution mix with its own plain cohort. At 60 workers, the final
reference-acquire and put symbol groups account for 2.18% and 1.44% of
`sc_worker` sampled period, versus 2.25% and 1.51% in the baseline. This small
difference does not establish a large reduction in dynamic reference traffic.
About 90% remains attributed to the polling slowpath in both compact versions.
These percentages are neither RMW counts nor an
upper bound on reference-related cost: coherence can change waiting and batch
timing elsewhere. Inlining changes symbol attribution.

Sampling itself changes behavior: the eight-worker baseline profile returned
only 0.81% of measured operations through JIT, versus 74.63% in plain runs.
Its small reference-symbol percentage is therefore not representative of plain
contention. No profile throughput enters the comparison score. The profiler
uses acknowledged enable/disable controls, an owned recorder PID, flat sampling
and saved symbol/module identities; it avoids unwinding borrowed stacks.

## Configuration and checks

The recovery VM remained on boot `b65f0205-c8f9-4385-8b13-039cbce243a6`, kernel
`6.1.159-kdclobber2`, Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`.
It has 64 vCPUs, 24 GiB and two NUMA nodes (0–31 / 32–63); workers use the
0-based eight/60 CPU prefix and collector CPU 63. Matching host pinning and
frequency policy are captured before/after. The actual snapshot
`before-mutex-kdonly-20261017T140354Z` was confirmed. The guest kernel was not
modified or rebooted. Source edits/static inspection ran on 380G10; all builds,
tests, live probes, workloads and timing ran in the VM.

Each timing uses 2 seconds, 300 ms peak window, 300 ms peak settling and 10 ms
samples. API workloads use n16, 64-byte values, 48,000 warmup operations per
worker and a 1-second warmup. The configured four waves of eight helpers apply
to xattr learning; seek/pipe execute no helper learning waves. NUMA is on,
batch size 1024, entry ratio 2, prefetch 2, delegation on and provider UBSAN off.
Exact commands/environment/source inputs remain in each arm's receipts/archive.
The public layout is checked as 32-byte size/8-byte type alignment; address
divisibility in timing logs alone is not a type-alignment proof.

Each of `checks-fetchadd`, `checks-hint` and `checks-inline` passed dependencies,
provider `W=1` and daemon warning-as-error builds, two basic programs plus 12
directly affected drivers (**14 passed, zero failed**), and ordinary-mutex,
rwsem and instruction-exit live probes. All nine live probes drained. The final
auxiliary fixture includes 20 negative controls, LIVE-zero revival, delayed
final-CAS generation reuse, rejected-pin transitions, state/count guards,
2,048-object admission with collision refusal, 131,072 sequential keys, eight creators and
8×4,000 concurrent operations. Each provider log retains 51 warning lines;
successful builds are not warning-free builds. [validation.json](validation.json)
binds checks to the measured production bytes and preserves exact scope.

[health.json](health.json) records final idle, unchanged topology/snapshot and
**139 kernel logs with no matched faults**. This is basic plus affected checking,
not a full suite or validation of whole-kernel replacement, RT/ww_mutex or lockdep.

## Retained evidence and analysis correction

The first summary attempt rejected synthetic rows because the runner adds five
derived fields after saving `session.json`. The corrected helper validates the
saved fields exactly and independently recomputes those additions. The original
helper, incomplete output and receipt remain in `analysis-first-attempt/`.
[analysis-correction.md](analysis-correction.md) distinguishes inferred initial
statuses from the actual final statuses in
[final-analysis-commands.json](final-analysis-commands.json). No workload result
was rerun or relabeled to repair the analysis. Switching to old256 required
removal of exactly two stale auxiliary source paths absent from that Git tree;
[old256-source-cleanup.json](old256-source-cleanup.json) preserves checked hashes.

The VM evidence tree is
`/root/kdlock-evidence/10.176.26.71/bench/mutex32-traffic-20261019`; its frozen
archives are in the `-archives` sibling. The source-host copy is under ignored
`bench/results/10.176.26.71/raw/bench/mutex32-traffic-20261019`.
[archives.json](archives.json) indexes nine archives totaling 134,759,679 bytes.
Their complete inventory, private includes, binaries, generated images, raw
samples and failures remain in those archives. The tracked report keeps compact
summaries, command receipts, source reviews and check logs.

Independent read-only archive/source and statistics audit receipts are
[archive-review.json](archive-review.json), [source-review.json](source-review.json)
and [statistics-review.json](statistics-review.json). Both audits passed on their
first runs with no issues. The archive/source audit checked 21,196 inventory
members, 35 source manifests, 184 binary bindings and 203 JIT binaries, with
zero ancillary exceptions to Git identities. The statistics audit made 152,227
checks, reconstructed all 130 timing windows and reconciled all ten weighted
profiles. Neither audit executes archived code. These evidence checks are
separate from live workload validation.
