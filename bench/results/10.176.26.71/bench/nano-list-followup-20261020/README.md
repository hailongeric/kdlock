# Resident-list measurements after correctness validation

Status: planned, not run. Shared-lock collection and the mmap/fault source
review precede this stage. The current recovery VM remains the only test
environment; every task will run serially after an idle/environment preflight.

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
