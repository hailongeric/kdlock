# Actual-MM plain workload validation, 2026-10-21

Status: preparation passed; both-mode live correctness validation pending.
No timing acceptance. New p95 collection remains deferred. All seven mutex
regression causes remain unresolved.

The main agent is the sole writer and VM executor. Three helpers reviewed
source read-only and reported no files touched. The source checkout began clean
at `e4d7bfa`. Fresh ownership checks found no competing source writer and no
active guest workload. The same VM remains on `6.1.159-kdclobber2`, boot
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
eligible for acceptance. Its focused tests and execution are pending.

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
will use the identical preparation-1 binaries.
