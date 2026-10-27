# Nano selection, minimal-body results and locality refinement

The user-directed cleanup removed retired benchmark records and parts of mixed
source archives. Archival provenance is **REDACTED / INCOMPLETE**. Original
complete-archive hashes and full-source replay claims below describe the earlier
collection, not the current retained subset; retained measurements are unchanged.

The final **16-cacheline mutex nano with post64 beats both baselines at 32 and
60 workers**. At 60 workers KD reaches **4.025 Mops/s: 1.435× Native and
1.839× TCLock**, with 98.20% returned writers. It still loses to Native at eight,
16 and 36 workers. This is a measured favorable workload and contention range,
not a universal performance claim.

The two earlier post4 candidates remain negative controls: neither the
one-cacheline body nor its 16-cacheline refinement beats Native under contention,
although both beat TCLock there. The 1%-write rwsem nano beats Native at every
measured count while recording **NO_JIT throughout**, and loses to TCLock
throughout. Increasing rwsem writes to 20% produces more returned bodies but
lower total throughput. All **102 timed observations and 24 functional cases**
are retained; there is one timing round per point and no further parameter sweep.

## Selection and measurement scope

The [complete catalog analysis](../catalog-single-20261026/PERFORMANCE_ANALYSIS.md)
motivated this experiment. At 60 workers, public mutex seek-set achieved
3.117× Native / 1.689× TCLock and pipecap 2.728× / 2.193×, with returned-body
shares above 97%. Those results combine
different useful bodies and call shells; their speedups do not transfer directly
to a one-ioctl nano loop. The strongest rwsem ratio against Native was RCUHT at
1% writes and 36 workers: 7.907× Native, but 0.642× TCLock and NO_JIT. Within the 20%-write cases,
RCUHT at three workers had the strongest Native ratio, 3.821×, also NO_JIT.

All minimal measurements and local controls use source
`8c8f95461cc1bcc7a873f96bed51fc1ad93d7d23`. Each profile has its own frozen source,
ELF and publication identities. The guest is `6.1.159-kdclobber2`, build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot ID
`afe3a8d8-0c07-475b-89b4-163b822484b0`. Recovery snapshot:
`before-mutex-kdonly-20261017T140354Z`.

The locality comparisons use the separate source
`6ff80fadf368f9e261be24c2aa7800013a3d9f6d`, retaining the same lock implementation
and existing straight-line counter payload. The four changed frozen input files
are the launcher, runner, nano tests and workload Makefile. This identity extends
the mutex profile selection and records its geometry; it does not change the
mutex protocol. Post4 and post64 measurements remain separate workloads even
when the source and body match.

There is **one two-second observation per point**, after 48,000 warmup operations
per worker. The minimal body is two adjacent 64-bit fields in one 64-byte-aligned
record;
each writer increments the sequence and stores the same value into its copy.
Readers compare the pair. Every backend uses the same body, deterministic
per-worker operation mix, bulk-ioctl loop and four register-only post-work
rounds. Workers occupy CPUs `0..N-1`, with collector CPU 63; counts above 32 cross
the NUMA boundary. Rates below are **whole-run Mops/s**, including both reads and
writes for rwsem. Returned-body percentages use writes as the denominator.

All results remain **exploratory**. Strict host timing qualification remains
failed under the authorized auxiliary-QEMU-worker policy; endpoint pin captures
do not prove continuous isolation. There is no repeat variability estimate,
qualified parity result, or causal cache/scheduler profile. The older catalog's
exclusive synthetic post64 and real syscall shells are separate evidence.
TCLock worker registration occurs outside the operation loop but inside the
inherited whole-run interval.

## Minimal mutex: 100% writes

[Full table, chart and replay evidence](mutex-minimal/README.md).

| Workers | Native | KD | TCLock | KD/Native | KD/TCLock | KD execution; returned writers |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 35.496164 | 51.808970 | 57.752689 | 1.460× | 0.897× | NO_JIT; 0.0000% |
| 8 | 11.506015 | 6.676210 | 3.768737 | 0.580× | 1.771× | RETURNED_JIT; 93.0161% |
| 16 | 10.176723 | 6.652816 | 3.563940 | 0.654× | 1.867× | RETURNED_JIT; 96.0563% |
| 32 | 8.306746 | 5.832743 | 3.229438 | 0.702× | 1.806× | RETURNED_JIT; 98.7949% |
| 36 | 7.667508 | 4.973043 | 3.201337 | 0.649× | 1.553× | RETURNED_JIT; 98.7233% |
| 60 | 5.585783 | 5.002928 | 3.154607 | 0.896× | 1.586× | RETURNED_JIT; 97.3354% |

At eight workers KD is 42.0% below Native, and at 60 workers it remains 10.4%
below Native. High returned-body coverage establishes that delegation executes;
it does not establish a net saving. Reducing the body to one load and two stores
also removes most of the shared dirty working set whose ownership transfers
delegation might amortize. ABI capture/restore, queueing, physical exclusion and
exact frame/unlock retirement remain. This is a source-grounded explanation of
the negative result, not a measured decomposition of those costs. KD's one-worker
advantage over Native is local and cannot be attributed to returned JIT bodies.

## Minimal rwsem: 1% writes

[Full table, chart and replay evidence](rwsem-read-minimal/README.md).

| Workers | Native | KD | TCLock | KD/Native | KD/TCLock | KD execution; returned writers |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 33.056806 | 40.182735 | 43.494520 | 1.216× | 0.924× | NO_JIT; 0.0000% |
| 8 | 7.784266 | 17.774951 | 22.798755 | 2.283× | 0.780× | NO_JIT; 0.0000% |
| 16 | 7.455445 | 15.370549 | 19.130057 | 2.062× | 0.803× | NO_JIT; 0.0000% |
| 32 | 5.344148 | 10.415532 | 16.513255 | 1.949× | 0.631× | NO_JIT; 0.0000% |
| 36 | 3.019642 | 8.332762 | 14.019582 | 2.760× | 0.594× | NO_JIT; 0.0000% |
| 60 | 3.436297 | 7.088727 | 15.178210 | 2.063× | 0.467× | NO_JIT; 0.0000% |

This simpler body preserves the catalog's qualitative result: KD's local reader
and writer-admission path outperforms Native without executing generated bodies.
Bounded polling before sleeping and distinct reader/phase handling are plausible
contributors. No reader delegates. At 36 workers both KD and Native slow versus
32; the largest Native ratio is not KD's throughput maximum. TCLock remains
faster, particularly across NUMA nodes. The result supports a favorable local
rwsem control, not a delegation speedup or a win against both baselines.

## Minimal rwsem: 20% writes

[Full table, chart and replay evidence](rwsem-mixed-minimal/README.md).

| Workers | Native | KD | TCLock | KD/Native | KD/TCLock | KD execution; returned writers |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 33.940721 | 38.009085 | 46.091398 | 1.120× | 0.825× | NO_JIT; 0.0000% |
| 8 | 3.095698 | 5.909626 | 8.877550 | 1.909× | 0.666× | RETURNED_JIT; 0.0003% |
| 16 | 2.674631 | 4.313922 | 10.552680 | 1.613× | 0.409× | RETURNED_JIT; 0.0547% |
| 32 | 2.294880 | 3.157575 | 9.228315 | 1.376× | 0.342× | RETURNED_JIT; 0.2111% |
| 36 | 1.232962 | 2.509565 | 7.339103 | 2.035× | 0.342× | RETURNED_JIT; 4.9478% |
| 60 | 1.403183 | 2.204645 | 7.968835 | 1.571× | 0.277× | RETURNED_JIT; 15.9501% |

More writers require more admission closure, exclusive work and reader drainage.
Returned coverage reaches 15.95% of writers at 60 workers, yet KD delivers only
2.205 Mops/s, versus 7.089 Mops/s in its 1%-write profile. Those are different
operation mixes, not a controlled estimate of JIT's effect. KD still beats Native
at every count but falls to 27.7% of TCLock at 60. A `RETURNED_JIT` label at eight
workers represents only 0.0003% of writes; it must not be read as predominantly
delegated execution. This 20% profile retains substantial reader interference.

## Minimal-profile local controls

The separate `timed-local` stage uses KD only, at 1, 16 and 60 workers, with the
same minimal body and post4 setting. Mutex selects callable local acquisition
instead of public ABI2; rwsem selects ordinary local writer admission instead
of the delegated-writer reservation. All nine observations recorded zero JIT
entries and returns, exact data success and complete drain. The comparison is
therefore a **call-shell/admission control**, not an isolated JIT toggle.

Published evidence: [mutex](mutex-minimal-local/README.md),
[rwsem-read](rwsem-read-minimal-local/README.md),
[rwsem-mixed](rwsem-mixed-minimal-local/README.md).

| Profile | Workers | KD delegate-on Mops/s | KD explicit-local Mops/s | On/local |
| --- | ---: | ---: | ---: | ---: |
| mutex | 1 | 51.808970 | 29.369706 | 1.764× |
| mutex | 16 | 6.652816 | 4.198473 | 1.585× |
| mutex | 60 | 5.002928 | 0.559565 | 8.941× |
| rwsem-read | 1 | 40.182735 | 22.304690 | 1.802× |
| rwsem-read | 16 | 15.370549 | 9.384287 | 1.638× |
| rwsem-read | 60 | 7.088727 | 5.494776 | 1.290× |
| rwsem-mixed | 1 | 38.009085 | 21.540094 | 1.765× |
| rwsem-mixed | 16 | 4.313922 | 1.875079 | 2.301× |
| rwsem-mixed | 60 | 2.204645 | 1.235700 | 1.784× |

The read-mostly on/off paths both execute locally, yet differ by 1.638× at
16 workers and 1.290× at 60. All single-worker on/off comparisons also differ
without any JIT execution. These observations establish that shell/admission
differences matter independently of returned bodies. Mutex's large 60-worker
on/local ratio does not erase its loss against Native or quantify a pure JIT
benefit. Each local observation is a separate single round.

## Mutex locality: 16 cachelines, post4

The `mutex-locality` candidate reuses the existing straight-line
`cacheline` body at **16 separate 64-byte counters**, with 100% writes and post4.
One protected operation increments all 16 counters directly across a 1 KiB
dirty payload footprint. The existing 16-value oracle requires every counter
delta to equal the exact
sum of completed writes. No new payload implementation or lock protocol is
needed. Native, KD and TCLock were rebuilt and measured under the new frozen
identity. [Full table, chart and replay evidence](mutex-locality/README.md).

| Workers | Native | KD | TCLock | KD/Native | KD/TCLock | KD execution; returned writers |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 28.480687 | 43.602546 | 55.265757 | 1.531× | 0.789× | NO_JIT; 0.0000% |
| 8 | 7.892487 | 5.962314 | 2.294971 | 0.755× | 2.598× | RETURNED_JIT; 70.3002% |
| 16 | 7.863429 | 5.406432 | 2.394183 | 0.688× | 2.258× | RETURNED_JIT; 75.1228% |
| 32 | 6.350983 | 4.910756 | 2.166219 | 0.773× | 2.267× | RETURNED_JIT; 93.6356% |
| 36 | 6.589418 | 4.103647 | 2.234544 | 0.623× | 1.836× | RETURNED_JIT; 95.0617% |
| 60 | 4.393695 | 4.134295 | 2.194298 | 0.941× | 1.884× | RETURNED_JIT; 97.0243% |

Keeping multiple dirty lines near an executor
across requests could amortize more data ownership transfers for the same
delegation bookkeeping. Straight-line addressing can also help Native. At
60 workers KD is still 5.90% below Native, despite 97.02% returned coverage;
at 8–36 workers it is 22.7–37.7% below Native. KD beats TCLock by 1.836–2.598×
under contention. Preserving the dirty footprint alone therefore did not produce
a Native win in this post4 bulk-ioctl shell. This result does not isolate
ownership transfers and caller spacing as individual causes. Wider local reads could also change rwsem scaling,
so this refinement is scoped to mutex.

## Final mutex locality: 16 cachelines, post64

The final bounded comparison keeps the 16-cacheline body, source, worker grid,
interfaces and correctness checks fixed, and changes only the explicit outside-
lock post-work setting from four to 64 rounds for every backend. Post64 is the
known setting of the original exclusive synthetic catalog. It changes CPU work
and acquisition spacing, which can affect contention, scheduling and ownership
handoffs; it is not another payload simplification. Its result cannot be called
a pure delegation gain or pooled with post4. A separate KD callable-local
control was measured at one, 16 and 60 workers for this post64 workload. The
three locality stages have identical frozen source manifests; post64 was passed
explicitly as `--post-work-rounds 64` under source `6ff80fad`. A later launcher
default selecting this setting does not change these measurements' source identity.

[Full table, chart and replay evidence](mutex-locality-post64/README.md).

| Workers | Native | KD | TCLock | KD/Native | KD/TCLock | KD execution; returned writers |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 7.668639 | 13.723185 | 9.361566 | 1.790× | 1.466× | NO_JIT; 0.0000% |
| 8 | 7.360786 | 5.068131 | 2.418461 | 0.689× | 2.096× | RETURNED_JIT; 98.6360% |
| 16 | 6.373069 | 5.187927 | 2.440210 | 0.814× | 2.126× | RETURNED_JIT; 98.9759% |
| 32 | 4.208185 | 4.878723 | 2.193600 | 1.159× | 2.224× | RETURNED_JIT; 99.0399% |
| 36 | 4.371000 | 3.941281 | 2.154544 | 0.902× | 1.829× | RETURNED_JIT; 99.0788% |
| 60 | 2.806126 | 4.025490 | 2.189241 | 1.435× | 1.839× | RETURNED_JIT; 98.1982% |

At 32 workers KD is 15.9% above Native and 122.4% above TCLock; at 60 it is
43.5% above Native and 83.9% above TCLock. The loss at 36 workers, immediately
after the NUMA boundary, prevents an "all high counts win" conclusion.

Changing post4 to post64 at 60 workers reduces KD's absolute rate by 2.63%,
Native's by 36.13%, and TCLock's by 0.23%. At 32 workers the corresponding KD
and Native reductions are 0.65% and 33.74%. Thus the improved KD/Native ratio
reflects different sensitivity to added outside-lock work and acquisition
spacing; KD did not become faster in absolute operations per second. The
16-line resident footprint is designed to offer ownership locality, and a service
batch can potentially overlap other callers' outside-lock work. Neither mechanism
was profiled directly. Compiler/register allocation, call-shell costs, scheduling
and ownership policy remain possible contributors. The one-worker ratios already
differ substantially without JIT. These single-round comparisons do not isolate
those causes or establish a repeatable optimum.

The final callable-local controls use the same 16-line body and post64 setting.
[Full local-control table, chart and replay](mutex-locality-post64-local/README.md).

| Workers | KD delegate-on Mops/s | KD explicit-local Mops/s | On/local |
| ---: | ---: | ---: | ---: |
| 1 | 13.723185 | 7.686078 | 1.785× |
| 16 | 5.187927 | 2.651585 | 1.957× |
| 60 | 4.025490 | 0.518639 | 7.762× |

All three local observations have zero entries and completions. Both one-worker
paths are NO_JIT, yet differ by 1.785×. At 60 workers the 7.762× on/local ratio
therefore includes the public-versus-callable interface and physical acquisition
policy as well as delegated execution; it is not a standalone JIT speedup.

The selected nano now preserves a bounded, resident dirty working set and the
known post64 outside-lock setting. Its supported favorable scope is the measured
32- and 60-worker mutex cases. The minimal rwsem-read profile remains a separate
best-case local-reader/admission example against Native, with no JIT attribution.
Both post4 mutex negative results remain visible above and are not relabeled or
averaged into the selected post64 result.

## Evidence and validation limits

The minimal timed stages contain 54 successful, drained backend/count records;
their explicit local stages add nine. The two locality settings add 18 matched
observations each, and the final post64 local control adds three: **102 timings**.
The initial functional stage contains 18 successful fixed-iteration cases at one
and eight workers; the locality functional stage adds six: **24 functional cases**.
All 204 warmup/measurement phases in the timed stages and all 48 functional-stage
phases passed frozen-version data replay.
Independent warmup JIT entry/return deltas were not recorded; returned-body
classification applies to the measured phase.

Guest checks recorded 32 affected tests, then six nano tests after the launcher
check was added. The locality revision passed 34 affected tests. Its six live
functional cases preceded a final metadata-only runner/test change; seven nano
tests then passed for that change. The archived functional and timing manifests
retain that distinction; the C payload and lock implementation were unchanged.
These overlapping check runs are not summed into a unique test count and do not
supply repeated timing evidence. The final launcher-default selection passed
seven focused nano tests; that later source is separate from the measured
`6ff80fad` source and receives no additional timing claim.

The minimal invariant requires both word deltas to equal exact completed writes,
zero reader consistency errors, deterministic per-worker mixes/checksums and
unchanged unused snapshot fields. KD returned completions are distinct from
entry counts and publication; source/frame retirement remains exact. TCLock
mutex registration drain checks actual task exit and queue/stack quiescence.
Per-profile replay receipts and immutable archived inputs retain the evidence.
Compact public directories retain each table, chart and audit; the audit's
`receipts_root` identifies the full extracted JSON under
`raw/bench/nano-pair-20261026/receipts/<profile>/`.
Raw stage archives, commands and host receipts are under
`bench/results/10.176.26.71/raw/bench/nano-pair-20261026/`; their `.stdout` archive
files are gzip tar data, not text logs. No missing repeat is treated as a pass,
and correctness replay cannot qualify the host's timing environment.

The [compact final validation receipt](validation.json) retains aggregate offline
and environment audits. Final guest checks recorded the same boot and kernel,
the original 73-module set, idle state and no matched fault-pattern lines in the
final kernel log. External unsigned benchmark modules changed the recorded
taint from 0 to 12288; no reboot was used to clear that evidence. Host endpoint
checks remained within the exploratory policy, with strict qualification failed.
