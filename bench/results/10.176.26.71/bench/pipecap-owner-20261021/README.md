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
