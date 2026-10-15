# Sleeping rwsem validation, 2026-10-15

The ordinary sleeping API passed its scheduler probe. All 21 fixed-iteration
Native/KD benchmark sessions passed their business-result, worker-progress and
final-drain checks. They returned **86,927 complete delegated writers**.
[Validation data](validation.json) preserves per-case counts and raw-record hashes.
These functional sessions establish correctness and execution evidence, not a
performance advantage.

The probe checks two concurrent readers sleeping inside their critical sections,
a writer sleeping until both readers release, and a later reader sleeping behind
that writer. It also checks ordinary writer sleep, read/write trylocks, downgrade
and idle state. Each worker records a voluntary context switch. This probe does
not execute JIT bodies.

| Writer shell | Workers | Write percentages | Complete delegated writers |
| --- | --- | --- | ---: |
| ABI4 | 1, 8 | 0, 20, 100 | 326 |
| ABI4 | 32, 60 | 20, 100 | 21,567 |
| ABI2, delegated-result spin budget 0 | 8 | 100 | 65,034 |

Readers validate eight cachelines for consistent versions; writers increment all
eight, and the final values must equal the exact writer count. The benchmark's
private completion observer counts only pristine wrappers reaching their matching
outer unlock. It supplements the entry witness and does not change admission.
Every contended writer case returned complete bodies; single-worker and read-only
controls returned none. ABI2 and ABI4 results remain separate.

Runs used the 64-vCPU recovery guest on physical host `10.176.26.71`, workers on
CPU prefixes and collector CPU 63. The captured kernel Build ID is
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, with `nokaslr`, `nopvspin` and voluntary
preemption. Source files, build logs, ELF hashes, kernel identity and source/frame
retirement receipts are retained under the external guest root recorded in
`validation.json` and its corresponding host raw archive.

The first ordinary probe (`api-v1`) reported a bookkeeping failure because it
tested a completion already consumed by a staged assertion. Workers had exited
and the semaphore was idle. The corrected probe joins each referenced kthread
and checks its return; `api-v3` passed. The blocked `api-v2` attempt stopped at
the idle preflight without running a test. All failed-attempt logs are retained.

The API is documented in the [design guide](../../../../../docs/design/rwsem_implementation.md).
It does not include killable waits or replace the real mmap lock. The checked-in
TCLock port supplies no sleeping rwsem arm; TCLock comparison belongs to the
separate exclusive-spin snapshot workloads.
