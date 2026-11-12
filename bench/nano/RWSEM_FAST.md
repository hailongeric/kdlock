# Rwsem reader candidate and comparison handoff

This candidate accelerates eligible original-task ordinary rwsem reads through
one preallocated exact credit on the existing gate. Writer acquisition,
cohort ordering, downgrade and cancellation keep the current path. See the
[protocol and focused checks](../../tests/rwsem_fast/README.md) for eligibility,
queued-writer refusal, repeated-read routing, source/storage lifetime and
controlled-check limits. Builds, tests, VM work and timings belong exclusively
to the existing bench session. No candidate runtime or performance result has
been obtained by the source session.

Preserve the parent source `a1ad50e5f218dbeb3dd4f7c77e0568271c3880ca` and measured
kernel `7.0.0-38-kdrebuild11`, plus kernel9/10 and all raw source/build/boot and
benchmark evidence. The durable kernel11 report is
`/home/eric/vm/vm-shared/kdlock-evidence/mutex-fast-a1ad50e5-20261112-01/README.md`,
SHA256 `0ee1df17a172e604a19b0d4c01b2f2ef7b8a2912deceba8bb0f5a7b51332174c`.
That receipt establishes the bounded mutex candidate and its affected rwsem
check results. It contains no fresh Native comparison. Preserve the bench
session's separate same-boot Native/current kernel11 receipt when available,
with its own identities; do not substitute an older Native number.

The private task-root layout changes again. A complete isolated kernel build,
distinct release/install/boot and rebuilt dependent modules are required.
Old-kernel modules cannot validate this candidate. Use the established
source/output separation and unchanged build headroom gate. Bench owns any
space remedy; do not delete preserved kernel9/10/11 inputs or recovery data.
Keep running/frozen source untouched and synchronize only while idle.

Bind the candidate to exact source/package hashes, kernel configuration,
compiler, ELF hash/Build ID, boot ID, signed module hashes and fresh GS proof.
Verify live and ELF `its_return_thunk` with its admitted two-byte `c3cc` span.
Preserve the existing recovery, idle, disk and placement checks. The task does
not request a GS optimization, new JIT lowering, full suite or mmap campaign.

Run only the five new reader C checks, seven affected fast-owner checks and
twelve recorder/ABI checks described in the protocol guide. Rebuild the existing
mutex, rwsem reader/mode and managed-killable fixtures and both KD nano modules.
Retain their existing generated-completion, native mode/cancellation, source
effect, exact physical release and final-retirement checks. The reader oracle
adds the exact task-root credit lifetime rather than weakening pool proofs.
Preserve every failed, skipped and unrun stage; timeout is not drain.

After correctness and both recorder functional lanes pass, use the established
small recorder-pair sequence for KD: one timed worker on CPU0, collector CPU63,
one cacheline, post256, mutex 100% writes, rwsem 20% writes, proxy limit 16,
unchanged eight-worker training and fixed-image/empty-claim checks. Keep three
two-second on/off pairs per family, ordered on/off, off/on, on/off: twelve
KD timings. Account fast reads separately from pooled writer/delegation work.
Recorded read count and exact fast lifetimes must agree; recorder-off evidence
remains unavailable, never zero or a generated-completion pass.

The user now requires Native comparison after each optimization. Reuse the
bench session's small same-boot Native/current procedure on the candidate
kernel with the same real workload body, postwork, write mix, worker/collector
placement, duration, repetition and peak criteria. Rebuild Native for that
kernel. Compare it primarily with KD recorder-off and show KD recorder-on
separately; Native has no KD recorder counts. Retain whole-workload and selected
peak results separately. The current `recorder-pair` runner accepts KD only;
do not pass Native through it or widen the default full comparison. The bench
session should use its bounded Native procedure with exact receipts.

Report candidate versus same-boot Native, candidate KD versus kernel11 KD in
each recorder mode, and the preserved kernel10/earlier KD series with source,
build and boot boundaries explicit. Do not pool versions or claim pure lock
latency, strict timing qualification, physical batch length or a generated
timed benefit from whole-workload throughput. A writer-path improvement remains
a separate later candidate, guided by the resulting measurements.
