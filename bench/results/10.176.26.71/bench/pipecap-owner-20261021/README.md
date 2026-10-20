# Pipecap physical-ownership investigation

This continues `cdd0ef4` with the same sole writer and serial VM executor.
The actual source hostname remains `380G10`; no environment is substituted.
The original VM, boot, kernel, snapshot, 64-vCPU topology, pinning, translation
Python and workload settings remain the required identities in
[VM operations](../../../../../docs/operations/VM.md).

The prior 0.30325 plain DIRECT/OUTER throughput ratio and entry/polling profile
weights were measured under a failed 95-versus-67-thread endpoint. They remain
descriptive and are not accepted causal evidence.

## Retained source and emitted paths

The source and ELF inputs are read from the original immutable `d21a1e3`
collection (OUTER `752fec1`), with hashes checked against its source manifests
and the previous stage's verified original-file map. See
[identities](retained-identities.json) and [binding checks](static-binding-checks.json).
The exact workload and ten provider function disassemblies per arm are retained.
Patchable fentry sites in relocatable ELFs are not assumed to execute as calls;
instruction counts are not cycle estimates.

For a successful local fast acquisition, OUTER's workload performs the owner CAS
inside `rb_body` and continues directly into the capacity read. Its nonzero exact
acquisition cookie selects `kd_mutex_local_unlock`, whose owner CAS physically
releases the mutex. DIRECT performs the same bounded acquisition algorithm in
`kd_mutex_lock_entry`; after acquisition it returns through that function and
`kd_mutex_direct_lock_clobber_v1` before the workload reads capacity. Its unlock
passes through `__kd_mutex_unlock`, `kd_mutex_task_reroute` and the RCU-protected
exact task-identity lookup before `kd_mutex_local_unlock`. The local branch has
additional work while physical ownership remains held. Its duration and causal
contribution to the five-worker regression are not established by this static fact.

The routed branches must remain intact: a gate owner releases physical exclusion
before opening the gate; a completed delegated body resumes at its saved
post-unlock continuation and retires its exact node/task reference; a native
continuation issues an unlock request and waits for the real owner's ACK.
Neither a cold task lookup nor a free gate is a replacement for those records.
The prior observed intervals exercised no native continuation ACKs.

## Discriminating diagnostic design

First compare the original arms at **one worker**, with native and TCLock
controls. Require measured zero JIT completions, zero delegation queue entries,
zero gate-owned acquisitions and zero native continuations before interpreting
the result as local-only. Do not force locality by changing admission settings.
This isolates the local path from the changing delegation mix at five workers.

Use a separate read-only sampler on guest CPU 62. It reads one byte, the most
significant byte of the exact KD owner word, through unbuffered `pread` on
`/proc/kcore`. On this captured x86-64 kernel, canonical task pointers have high
byte `0xff`; an absent owner with only low mutex flags has high byte zero.
Reading one byte avoids torn multiword observations. Only `0` and `255` are
valid. The original workload ELF, live symbol, section base, exported lock
address, active paging mode and unique kcore extent must bind the address.
Open read-only device references keep both the provider and workload modules
pinned until the sampler finishes. No lock word, owner record or code is written.

A fixed random schedule with a 1-ms mean interval avoids a fixed-phase sampling
relationship to the short body. Save clock brackets around every byte read,
intended deadlines, actual gaps, CPU time, all samples and the seed. Buffer
samples in preallocated memory and write them only after the workers join.
Reject overflow, invalid bytes, missing coverage and overlapping boundary data.
No sampled state grants acquisition, release, teardown or admission permission.
Skipped schedule deadlines are retained, with no catch-up burst. The process
has a fixed 15-second safety duration and reports failure if it expires; this
never stops a worker or proves drain. Parent deadlines never kill a child.

Keep three diagnostic modes separate: the original plain caller; a reference
sampler reading the provider's immutable disabled timing flag; and an owner-byte
sampler. The reference follows the same scheduling and read protocol without
reading the ownership cacheline. Counter snapshots occur only at joined
boundaries. Compare throughput and sampling behavior to quantify observer effects.

When the entire phase is proven local-only, estimate mean physical ownership as
`sampled occupied fraction × measured wall time / completed acquisitions`.
This is an occupancy-based estimate, not a timestamp of each lock operation or
an acquisition-latency measurement. Report finite-sample uncertainty, temporal
variation, read/gap distributions and possible cacheline-probe perturbation.
Do not infer identical execution mixtures from a common JIT/no-JIT label.

The initial fixed plan is three repeats of both KD arms in all three modes,
plus Native and TCLock plain controls: **24 serial one-worker sessions**.
Only after validating this estimator should a separately identified five-worker
follow-up assess owner occupancy together with exact returned-JIT counts.
Every live stage retains the strict original thread-set preflight and immediate
endpoint. No production fix is justified yet. All existing unresolved broader
work remains tracked in the [previous stage](../pipecap-causal-20261021/final-status.json).

The new VM checks select the two basic C programs plus the existing comparison
and counter-boundary checks and eight owner-sampler checks. No full suite or
kernel build is requested. The original provider, workload and client are
reused without rebuilding. The plain mode retains original observation only;
the stronger local-only counter qualification applies to reference and sampled
modes, which capture counters outside the joined worker interval.

## Checks and preflight

`checks-1`, source `62046e8`, passed both basic C programs and 30 focused Python
checks (13 comparison, nine counter/boundary, eight owner-sampler). Dependency
checks, frozen/current source hashes and final idle also passed. The manifest
binds 519 committed inputs; private implementation includes are retained.
See the [check receipt](checks-1/result.json).

The recovery snapshot was actually listed before checking. The initial host
capture had 68 QEMU threads; the first timing preflight at
`2026-10-20T22:38:12.848246+00:00` had 75, so no timing run was started from that
receipt. The original 67-thread requirement remains unchanged.

## Completed diagnostic and limits

`pipecap-owner-20261021/run-1`, diagnostic source `62046e8`, completed **24/24
sessions**, **272,865,280 operations**, and **18 exact KD retirements**. All
original result, worker, image, redirection and drain checks passed. All 24
measurements returned zero JIT bodies. The 12 observed phases additionally
had zero queue entries, gate-owned acquisitions/releases, nested entries,
handoffs and native continuation starts/completions/unlock ACKs. These phases
qualify as local-only; they do not exercise or replace the earlier ACK tests.

The strict preflight passed at `2026-10-20T22:39:11.227853+00:00` with the exact
original 67-thread set. The immediate endpoint at
`2026-10-20T22:41:55.860557+00:00` had **101 threads and failed**. The kernel,
boot, QEMU command, topology, frequency policy, snapshot and recorded affinities
matched. Host interference remains unresolved; no setting was changed to obtain
a passing preflight or endpoint.

Plain one-worker results, in million operations/second:

| Arm | Median | Minimum–maximum | CV |
| --- | ---: | ---: | ---: |
| Native | 5.71919 | 4.64996–5.76021 | 11.71% |
| TCLock | 5.96461 | 5.91388–5.97566 | 0.55% |
| OUTER | 5.77985 | 5.73130–5.79608 | 0.58% |
| DIRECT | 5.61385 | 5.60820–5.62205 | 0.12% |

The descriptive DIRECT/OUTER median ratio is **0.97128**; paired ratios are
0.97951, 0.97030 and 0.96998. This one-worker comparison is a different point
from the five-worker regression. It is not evidence that the latter is fixed.

Owner sampling produced the following **unaccepted occupancy estimates**:

| Arm | Repeat 0 | Repeat 1 | Repeat 2 | Median | CV |
| --- | ---: | ---: | ---: | ---: | ---: |
| OUTER, ns/acquisition | 6.556 | 8.311 | 6.964 | 6.964 | 12.62% |
| DIRECT, ns/acquisition | 8.503 | 8.616 | 10.201 | 8.616 | 10.42% |

Paired estimated differences are +1.947, +0.305 and +3.237 ns. Per-arm Wilson
intervals conditional on independent observations are retained in the
[session arithmetic](review-1/sessions.json), along with ten temporal blocks
per session. They do not include correlation or measurement bias. The sampler
is not calibrated against a known physical-owner duty cycle: cacheline reads
can affect, or observe at a time related to, ownership transitions. These
estimates therefore do not establish physical durations or explain the
five-worker loss.

Across reference and owner modes, **24,018 in-phase observations** were kept;
the six owner phases observed 560 occupied bytes. The reference byte was always
zero. No overflow, invalid byte, lifecycle failure or missing-coverage refusal
occurred. One reference session skipped one scheduled deadline; all other
sessions skipped none. Median read brackets were 4.02–4.68 microseconds and
p95 brackets 21.92–23.05 microseconds. These bracket durations are observer
costs, not lock latency. All samples, schedule seeds, skipped deadlines and
process CPU time are retained.
The sampler consumed 6.99–7.41% of one guest CPU on CPU 62 during its active
window (`process_cpu_ns / (stopped_ns - started_ns)`). This resource cost is
separate from the throughput associations below.

Relative to each plain repeat, owner-mode throughput ratios ranged
0.99830–1.00875 for OUTER and 0.99872–1.00132 for DIRECT. Reference-mode ratios
ranged 0.99776–1.00829 and 0.98585–1.00032 respectively. These associations
include time drift and host activity; they do not isolate a subtractable
instrumentation cost. See [observer comparisons](review-1/observer-effects.json).

**Disposition: inconclusive.** Static extra work inside DIRECT ownership is
established, but its duration under contention and contribution to the original
regression are unresolved. The estimator has not met the design's validation
condition for a five-worker follow-up, so no larger matrix or production change
was made. No new acquisition-latency or p95 result is claimed. All seven
regressions and the previously listed integration/performance gaps remain open
in [the current status](final-status.json).

## Preservation

The independent VM health check reverified **4,088 original file hashes** and
**336 retained harness hashes**, all sampler exits, all exact retirements and
actual idle. No per-session kernel fault matches were found. Its full receipt
is in `metadata.tar.gz`; [the compact receipt](health-summary.json) identifies it.

Four archives preserve checks, sessions (including raw binary samples), host
receipts and metadata. Their manifest SHA-256 is
`d4d8a49a4c409970defbc502b76ec3e2071cce530e0fb272649a92aebf601b1b`.
[Artifact locations and hashes](artifact-set.json) distinguish this diagnostic
from the original OUTER/DIRECT inputs and all earlier stages.

The source-host-only [independent review](review-1/review.json) passed
**109,948 consistency checks** over 1,714 archive members, 1,398 regular files
and 70 preserved symlinks. It reconstructs the original settings and rotations,
worker/progress arithmetic, counter deltas, each random sampling deadline and
skip, phase membership, occupancy estimates and host endpoint failure. It
executes no retained benchmark code. Archive consistency is separate from
performance acceptance, which remains **OPEN**.
