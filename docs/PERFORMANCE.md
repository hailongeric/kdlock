# Performance status

Current KD mutexes use bounded polling followed by uninterruptible sleep. Spinlocks
and rwlocks retain their separate protocols. The blocking-only change in `792db45`
passed [targeted verification](../bench/results/10.176.26.71/tests/mutex-blocking-only-20261012/validation.json),
including a drained 320,000-operation mutex JIT run. That functional check does
not provide a new performance matrix.

## Latest c01 admission study

The [2026-10-13 c01 study](../bench/results/10.176.26.71/bench/mutex_admission/20261013/README.md)
did **not** reach 97% of Native mutex on both median whole-run throughput and
best warmed peak through 28 workers. All eight entry-ratio thresholds (2–256)
failed screening; the default remains 256. The pinned sampler removes cold-path
work, but no low-thread throughput gain is established. Its full-grid run stays
within the specified 3% regression bound at 32, 36, 48 and 60 workers, with
returned JIT bodies in every round.

The report retains 543 correct, progressing, drained sessions, including 48
unscored diagnostics, source/ELF/JIT hashes, variation and CPU/worker-share data.
It uses the regular 64-vCPU VM, collector 63 and 64 post-work rounds. Adaptive
native acceptance is opt-in and visibly distinct from returned JIT execution.
No candidate qualified for confirmation; this is not a parity result or an
acceptance of other workloads and the 64-worker topology.

## Earlier full comparison

The [2026-10-12 full report](../bench/results/10.176.26.71/bench/mutex_wait/20261012-full/README.md)
was measured before removal of the polling-only mutex policy. It contains 31
configurations at 22 worker counts: 1–8 by one, then 12–64 by four. Native,
TCLock and the two historical KD policy settings ran three rounds; API cases
also include Stock Linux. All 8,910 sessions drained, 8,908 were accepted, and
two zero-JIT spin controls remain excluded.

Use the report's **KD blocking** series when assessing the retained mutex policy.
The historical KD policy labels select mutex waiting behavior; spinlock and
rwlock pairs are control runs of the same lock algorithms.

| Observation from the frozen report | Result |
| --- | --- |
| Blocking setting meets both Native and TCLock on median whole-run and best warmed peak throughput | 502 of 649 complete multithreaded points |
| Same comparison, mutex configurations only | 119 of 189 points |
| All nine mutex configurations at 60 and 64 workers | Meet both comparisons |
| Blocking/spin mutex whole-run ratio at 60 workers | 93.3–99.3% |
| Blocking/spin mutex whole-run ratio at 64 workers | 95.3–98.7% |

These values describe the captured implementation and environment. They do not
establish universal parity for the current checkout. The report retains source
hashes, round variation, all accepted and failed samples, JIT classifications,
CPU cost, plots and per-worker progress.

## Remaining gaps and comparison limits

Low-thread overhead remains. The frozen two-worker c01 blocking case was 30.1%
slower than the polling-only control, with variation and no recorded parking.
Several rwlock throughput gains had no returned JIT bodies. UTS uses more worker
CPU per operation than Native's sleeping rwsem, and its 64-worker hostname case
loses to TCLock. This bounded UTS experiment does not establish a general
rwsem or mmap implementation.

The full report uses a temporary 66-vCPU boot. At 64 workers, collector vCPU 65,
the last worker and QEMU services share physical host core 63. The regular VM has
64 vCPUs; the earlier six-count report uses collector 63 and at most 60 workers.
Keep source versions, topologies, workload/post-work settings, governors and
JIT/NO_JIT classes separate. Aggregate throughput and amortized ns/op do not
measure lock-acquisition latency.

## Reproduction and history

The [benchmark guide](../bench/README.md) identifies maintained runners and
measurement rules. The [results index](../bench/results/README.md) groups frozen
reports by physical machine; [validation](VALIDATION.md) indexes correctness
receipts. Older optimization trials, rejected candidates and original-host
profiles remain in those records instead of being repeated here.

Current implementation contracts live in the [spin](design/spin_implementation.md),
[mutex](design/mutex_implementation.md) and [rwlock](design/rwlock_implementation.md)
guides. [Known limitations](TODO.md) records unresolved correctness and lifetime
work. Documentation cleanup does not rerun measurements or schedule optimization.
