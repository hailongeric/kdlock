# Resident-list measurements after correctness validation

Status: `timing-1` is running serially after `preflight-2` passed. Shared-lock
collection and the mmap/fault source review are complete, with their documented
limits. The original recovery VM remains the only test environment.

The [task plan](task-plan.json) preserves all ten timing argument lists from
the previously retained resident-list plan. That plan selected eight and 60
workers, three repetitions, two-second measurements, collector CPU 63 and CPU
prefixes. This is a focused 264-session comparison, not the full 21-count grid.
Its geometry is unchanged; source identity is now validated `f48b90e`, whose
497 manifest files equal restored `a768361`. The original plan and all earlier
functional failures remain separate evidence.
The prepared [preflight](preflight.py) requires the original host configuration,
actual recovery snapshot, unchanged manifest and exact historical arguments,
then checks all ten dry-run plans before allowing the serial supervisor.
The prepared [post-run verifier](verify.py) checks all 264 results, frozen
sources/binaries, 44 compiled-function audits, 96 KD loaded-image receipts and
exact retirements. It retains both strict environment endpoints; a failed
post-run check remains a failure. It has not yet run against timing evidence.
The prepared [independent archive review](offline-review.py) recomputes worker
effects, timing windows, execution classes and three-round ranges from raw
records. It reconstructs provider sources and checks compiled/generated ELF
extents, loaded bytes and every retained prefetch instruction. It imports only
hash-pinned inert readers and will run on `380G10` after archival. It has not
yet run against this timing stage.

| Family | Variants | Controls | Mix | Sessions |
| --- | --- | --- | --- | ---: |
| Spin | plain/prefetch × 16/128 nodes | Native, TCLock, KD | exclusive | 72 |
| Public mutex | same | Native, TCLock, KD | exclusive | 72 |
| Rwlock | same | Native, TCLock, KD | 20% writes | 72 |
| Sleeping rwsem | same | Native, KD | 20% writes | 48 |

These are the bounded, resident-memory
[list payloads](../../../../../docs/BENCHMARK_WORKLOADS.md#resident-linked-list-traversal).
They perform no allocation or page-fault workload inside the critical section.
Exclusive post-work remains 64 rounds; shared-family post-work remains four.
NUMA, batch 1024, queue prefetch 2, entry ratio 2 and UBSAN-off settings remain
explicit. Payload prefetch is a separate variant from queue prefetch.

The [16 functional cases](../../tests/native-continuation-20261020/README.md)
already passed with returned JIT bodies, list integrity, loaded-image checks and
exact retirement. Timing retains the original JIT requirements and stops on a
failure. It will keep every repetition, worker result, source/binary identity,
prefetch audit and retirement record. Three-round groups require a single
execution class; missing or partial JIT evidence cannot be scored as a returned
body. Any within-backend hint comparison also requires matching family, size,
worker count, mix, source and instrumentation. Ranges and spreads will be
reported; p95 latency remains unmeasured.

## Admission and active collection

The first strict admission, `preflight-1`, **failed before any timing session**.
Its host capture at 2026-10-20 17:02:04.263592 UTC had 70 QEMU threads against
the required original 67. The additional TIDs 421142, 421144 and 421145 were
named `worker`, each pinned to CPU 63; every original thread identity and
affinity remained unchanged. No host setting or admission check was changed.
[Failed health](preflight-1/health.json) confirms an idle guest, all 497 source
hashes unchanged, zero measured sessions and no timing output directory.

The [independent preservation review](preflight-1/offline-review.json) passed
633 checks; the preflight itself remains failed. The
[archive manifest](preflight-1/archives.json) SHA-256 is
`130790ae1ce9092a103e764906049608b8738e6d936b8fbae01034cda18e06a7`.
Raw archives are under
`bench/results/10.176.26.71/raw/bench/nano-list-followup-20261020/preflight-1/archives/`.
The first later [thread inspection](preflight-1/thread-review-1.json) saw those
three TIDs absent but 68 total threads; a separately retained
[full receipt](preflight-1/later-host-receipt.json) at 17:04:49 still had 70,
with different worker TIDs. The [17:05:44 inspection](preflight-1/thread-review-2.json)
observed 67 and no worker-named threads. These are observations of natural
thread turnover; the source of that work and within-run interference are
unmeasured. Later receipts do not repair the failed admission.

The new full host receipt at **17:06:19.825167 UTC** matched the original
67-thread configuration, pins, frequency and memory policies, boot, dependencies
and actual recovery snapshot. `preflight-2` passed all 497 source hashes and
the exact ten dry-run plans, totaling 264 sessions. The unchanged supervisor
started the first task at **17:07:03.292316 UTC** under:

`/root/kdlock-evidence/10.176.26.71/bench/nano-list-followup-20261020/timing-1/`

The source snapshot at collection admission is `6c124de`; measured inputs remain
the fixed `f48b90e` manifest. Only documentation and evidence helpers changed
during the preceding idle synchronization. A source-host launcher invokes the
same VM supervisor once and captures the host endpoint after its SSH command
returns. It adds no observer during timing; SHA-256 is
`215d64e540040a69bb647e2f2afc446be5a4ee30937a8b8b2f27a14215ce1213`.
Its exit code does not establish drain; the supervisor and per-session exact
retirement checks still do that. No result or acceptance is claimed while
collection is active.
