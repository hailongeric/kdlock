# Actual-MM plain workload validation, 2026-10-21

Status: implementation prepared; VM build and correctness validation pending.
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
