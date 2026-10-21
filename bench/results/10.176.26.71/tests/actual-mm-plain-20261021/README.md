# Actual-MM plain workload validation, 2026-10-21

Status: preparation and both-mode live correctness passed with identical frozen
binaries. The unchanged throughput gate refused 68 QEMU threads versus the
original 67; zero timing sessions started. Recovery was restored and both
default payload builds passed. No timing acceptance or new repetition variance
is available. New p95 collection remains deferred. All seven mutex regression
causes remain unresolved.

The main agent is the sole writer and VM executor. Three helpers reviewed
source read-only and reported no files touched. The source checkout began clean
at `e4d7bfa`. Fresh ownership checks found no competing source writer and no
active guest workload. The same VM started on `6.1.159-kdclobber2`, boot
`88449cfc-cea9-4647-a294-bc601e372146`, with the exact 73 runtime modules.
The approved synchronization retry copied five changed documentation files and
verified all 3,993 tracked hashes without deleting files. Its log is retained in
`raw/tests/actual-mm-plain-20261021/preflight/approved-sync.log`.

## Implementation and scope

The explicit `MF_NATIVE_ONLY=1` fault-payload build removes external provider
types and calls. Native backing lock operations, callback counters, ownership
and file/VMA release invariants remain intact. Backend KD/TCLock requests are
rejected before fallback/allocation, including unsupported features with
fallback requested. Existing default profiles remain selectable.

The separate `bench/mmap_lock/plain.py` driver freezes candidate-built payloads
and clients once. It binds executed source hashes, exact kernel/boot/mode/module
identity, selected prior correctness receipts and both-mode new validation.
Shared-mm untouched mmap/munmap and independent-mm fault cycles are distinct
tasks. Readers execute locally. Fixed-work, API, lifetime and plain-client
checks precede timing; corrupt receipts are rejected. Exact original host
controls and immediate endpoint admission remain required. Six boot blocks
and plain-only summaries preserve per-run values and population CV; missing
p95 is recorded as deferred. No TCLock actual-MM workload is included.

The existing candidate image and one-shot entries can be reused; no recovery
image/default needs replacement. Recovery diagnostics must drain before a
recorded candidate transition. New binaries must pass in both modes before any
timing. A later recovery boot receives a new identity and cannot reuse an old
same-boot receipt.

## Preparation 1

Committed source `7c517e1` passed the serial guest preparation. Dependency check,
two basic C programs and six focused Python tests passed. The writer, Native-only
fault and actual-mm API payloads built against the captured candidate kernel;
six clients built with warnings as errors. The Native-only fault module has no
external provider dependency; its only KD imports are the builtin actual-mm
read-lock adapter. No module was loaded and the recovery boot remained idle
with the exact 73 modules. [Preparation receipt](prepare-1.json).

The new `rcuht_boundary.py` diagnostic keeps the retained original synthetic
runner/provider/payload and adds four read-only snapshots around original
warmup and measurement. Two-worker OUTER and DIRECT sessions are serial; the
intervening gap is retained separately. Execution classes remain unchanged,
entry witnesses do not become returned-body counts, and no diagnostic rate is
eligible for acceptance. Its five focused tests passed; live admission refused
before any workload ran, as recorded below.

## Recovery diagnostic and preservation

Five focused RCUHT boundary tests passed, including four distinct captures and
partial-failure retention. Attempt 1 stopped before workload loading because
the retained collector refused a helper import from the current checkout.
The helper is now copied and loaded outside that checkout; the guard remains
unchanged. Attempt 2 reached the original environment comparison and refused
**71 QEMU threads versus the required original 67**. No workload started. The
first capture had 74 threads; it is retained separately, not replaced by the
second. [Failed admission receipt](rcuht-boundary-2.json). The invocation-label
correction for attempt 1 is explicit in its [record](rcuht-boundary-1-attempt.json).

The recovery VM drained with all 73 expected modules. Three pre-transition
archives were sealed, copied back, and checked for exact hashes/sizes and full
regular-member decompression (453 files). The manifest SHA-256 is
`9269260b6a89ca356794e71bae5f86f8eafdc900709d91771b436ecf9c582fcb`;
[archive review](pre-transition-archive-review.json). No RCUHT phase-counter
measurements or accepted throughput result exist.

The reviewed transition script verifies all preserved recovery artifacts and
installed candidate hashes, retains the recovery default, and selects only a
one-shot existing entry. It records new boot identity, exact module restoration
and full boot logs before readiness. Native-control and KD-local correctness
used the identical preparation-1 binaries.

## Native-control validation 1

The one-shot boot reached `6.1.159-kdmm1`, Build ID
`687ff5a29315d732f93a618e50ac407c794bbf9b`, boot
`e512cc18-96de-4f27-9fbd-37d6908d388a`, with `kd_mmap=off`. All recovery
files and 5,686 recovery module files remained unchanged. Five previously
recorded runtime modules were restored; the exact 73-module set matched. Full
boot logs contained no fault-pattern matches; six known fd0 I/O lines remain
retained. [Transition receipt](native-transition-1.json).

The frozen input manifest
`69271dff3cbb70e098a0b7157125b32a97ee7499b5903a539d0259bc5dff9b6f`
passed the actual-mm API (121 checks, zero errors), six untouched mapping
cases, backend rejection, four fixed fault/lifetime/concurrency cases, and the
Native full fault API. Four plain-client validations at 1/16 workers passed
with 36 corrupted receipt rejections, zero retained VMA/file references, and
normal unload. The 16-worker fixed mapping case also rejected all nine corrupt
writer-chain receipts. [Validation receipt](native-validation-1.json).

Plain-client completion counts were 717,280 / 219,712 untouched mapping cycles
and 519,424 / 5,155,008 fault cycles. These are correctness observations, not
accepted timing comparisons. The source/binary hashes were unchanged. Five
archives, including all 565 regular members, passed an independent offline
review. [Native archive review](native-archive-review.json).

## KD-local validation 1

The same candidate image booted with `kd_mmap=on`, boot
`28c4bb9c-bf14-49aa-9adb-34c6d60d7fa5`. Recovery artifacts remained unchanged,
the exact 73-module set was restored, and full boot logs had no fault-pattern
matches. Six known fd0 I/O lines remain retained. The first request invocation
used a nonexistent Python path and exited 127 before executing the transition
script; the successful request is `kd-request-2`. Both console records remain.
[Transition receipt](kd-transition-1.json).

The identical input manifest and nine binaries passed 139 actual-mm API checks
with zero errors, the same twelve fixed/API cases, four plain validations,
36 corrupt plain-receipt rejections and nine corrupt writer-chain rejections.
Readers remained local; writers stayed on their original task. Final VMA/file
references were zero, modules unloaded normally, and final idle passed.
[Validation receipt](kd-validation-1.json).

The plain validations completed 1,286,816 / 78,720 untouched mapping cycles
with zero faults and 950,304 / 11,355,296 fault cycles with exact callback/read
release counts. These are correctness observations only. Independent archive
review verified all 683 input bindings, nine binaries and the raw business
oracles. Seven archives contain 709 regular files and 55 directory entries;
the manifest SHA-256 is
`543944c7ff87323d2227e7814c2752d2aa3dcbf1a6950fc3120e5ce9dd9baedd`.
[Correctness archive review](correctness-archive-review.json).

## Throughput admission and unresolved work

`throughput-readiness-1` bound both successful correctness receipts and then
refused the unchanged original QEMU task-set gate: **68 threads versus 67**.
It started no workload or timing session and left the guest idle. The separate
RCUHT diagnostic had already refused at 71 threads. Failed receipts and host
captures remain fixed; later captures do not replace them.
[Readiness receipt](throughput-readiness-1.json).

The planned six boot blocks and 24 plain throughput sessions did not run.
There are no qualified repetitions from this stage, so rates, paired ratios
and repetition variance are unavailable. Missing p95 is deferred and did not
cause the refusal. Existing measurements and their variance remain in the
separate [seven-point recovery report](../../bench/mutex-recovery-followup-20261021/README.md).

| Regression | Current causal status |
| --- | --- |
| c08 / 3 workers | Unresolved; no new qualified timing |
| c08 / 4 workers | Unresolved; no new qualified timing |
| c08 / 5 workers | Unresolved; no new qualified timing |
| pipebytes / 3 workers | Unresolved; no new qualified timing |
| pipebytes / 5 workers | Unresolved; no new qualified timing |
| pipecap / 5 workers | Unresolved; prior execution-class mismatch remains |
| RCUHT / 2 workers | Unresolved; phase diagnostic refused before execution |

The next live timing attempt must qualify the original complete host controls
and immediate endpoint, retain a separately recorded boot identity, and use the
same frozen work. The added host thread's initiating activity is not established
by this refusal. No environment requirement, instruction admission or probe was
weakened. Selected actual-MM correctness does not validate arbitrary delegated
MM bodies, all filesystem/device callbacks, lockdep/RT or whole-kernel replacement.

## Recovery and default-build compatibility

The final one-shot transition restored `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot
`ad05e2e3-1f03-40db-9486-b49166f946ae`. The recovery image/default and all 5,686
recovery module files remain preserved. Exact 73-module restoration and full
boot-log checks passed; six known fd0 I/O lines remain recorded. This new boot
cannot reuse an older same-boot mutex receipt. [Recovery receipt](recovery-transition-1.json).

`compatibility-1` compiled isolated copies of both default fault-payload
profiles against the recovery kernel, leaving `MF_NATIVE_ONLY` at its default.
KD and TCLock builds passed and retained their expected provider metadata;
no module was loaded. These build checks do not exercise unsupported TCLock MM
critical sections. [Compatibility receipt](compatibility-1.json).

Final health rechecked preserved recovery artifacts, the exact 73 modules,
both frozen-input manifests, full boot logs and absence of project work.
All checks passed. [Final health](final-health.json).

Eight final archives were sealed in the idle guest and copied back. Offline
review checked all 902 regular members and 80 directory entries against the
inventory, archive hashes/sizes, default-build artifacts and final receipts.
All 709 regular files from the earlier correctness seal are byte-identical.
The final manifest SHA-256 is
`cedb89ef8a426a8fa339c5ddaad5dd2cc78633d6453e48ec3e26eaab004d2aba`.
[Final archive review](final-archive-review.json) and
[archive manifest](../../raw/tests/actual-mm-plain-20261021/final-archives-1/archives.json)
identify the eight groups: preparation, Native, KD, transitions, RCUHT, control,
compatibility and metadata. Raw consoles and host captures remain in
`raw/tests/actual-mm-plain-20261021/preflight/` and the archived control groups.

Implementation `7c517e1`, the RCUHT diagnostic revisions `559fb78`/`0d38c06`,
and transition preparation `7bff37e` remain separate from earlier baseline
versions. All helpers performed read-only review and reported no files touched.
The single writer ran every build and live check serially in the original VM;
no timing or unsupported TCLock MM workload was started.
