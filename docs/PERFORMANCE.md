# Performance status

Current KD mutexes use bounded polling followed by uninterruptible sleep. Spinlocks
and rwlocks retain their separate protocols. The blocking-only change in `792db45`
passed [targeted verification](../bench/results/10.176.26.71/tests/mutex-blocking-only-20261012/validation.json),
including a drained 320,000-operation mutex JIT run. That functional check does
not provide a new performance matrix.

## Latest owned-mutex entry and waiting study

The [native-first study](../bench/results/10.176.26.71/bench/mutex_owned/20261014-native-first/README.md)
tests an ordinary C caller ABI, late continuation capture, an exact-owner
leaf unlock and guarded release before the queue lock for SELF-only contention.
Its Linux-derived optimistic path retries acquisition across owner transitions
and directed handoffs; only sustained contention after the polling budget can
request delegation. The public object still matches Linux mutex's 32-byte size,
alignment and field offsets. Owned target operations remain inside KD.

Neither full optimistic-policy screen meets all primary throughput and
higher-thread JIT requirements. The final ABI2 compatibility screen also fails
the 32-worker regression floor. The implementation is preserved separately as
`archive/perf/mutex-native-first-20261014`; it is not integrated into the current
provider. Current owned source and defaults remain the preceding `d8d14a1`
implementation. The report separates all policy/source versions, returned JIT
bodies and unscored diagnostics. Fast KD_SELF execution does not satisfy a gate
requiring delegation.

## Earlier c01 owned-mutex optimization

The [2026-10-14 protocol study](../bench/results/10.176.26.71/bench/mutex_owned/20261014-hybrid/README.md)
retains 708 scored sessions and 72 separate diagnostics. The owned protocol now
uses one notification word for directed grants and COMPLETE/FULL results. A
delegated waiter consumes its exact PICKUP grant without reacquiring the queue
lock. The public object remains 32 bytes with Linux mutex's alignment and field
offsets, and owned target operations never call the original Linux mutex API.

The final capture-first finite policy reaches 3.227, 2.325, 2.070 and 1.647 Mops/s
at 4, 16, 28 and 60 workers, respectively. Against the fresh owned finite baseline,
those median changes are +96.7%, +22.6%, -3.3% and +74.0%. Both final finite and
opt-in refill pass the same-policy 32/36/48/60-worker regression gates with
returned JIT bodies in every round. These are improvements to the experimental
owned protocol; they do not restore legacy KD's performance or establish Native
parity. At sixteen workers, the final finite result remains well below its paired
Native's 8.734 Mops/s. The 97% primary target fails, so confirmation blocks were
not run.

Optional pre-capture admission and bounded private OSQ polling can reach Native
at four workers, predominantly through SELF execution, but fail the broader
grid. They remain explicit compile-time/runtime opt-ins. Capture-first, ratio
256 and refill off remain the owned defaults. Separate PMU diagnostics show
substantial extra instructions and cycles per operation at 16–32 workers;
frequency differences alone do not explain the gap. The report retains worker
shares, CPU cost, all candidate sources and failed attempts, including variation
in Native's sixty-worker execution regime.

## Earlier c01 owned-mutex redesign

The [owned-mutex study](../bench/results/10.176.26.71/bench/mutex_owned/20261013/README.md)
implements a separate 32-byte KD object with private Linux-derived owner/OSQ/sleep
code and typed SELF/DELEGATE waiters. Target-address probes observe no original
Linux mutex calls. It audits 426 scored sessions and 114 diagnostics.
The requested two-metric 97% target remains unmet.

At sixteen workers the fresh Native/TCLock/legacy-KD medians are
8.694/3.525/7.315 Mops/s. Owned finite FIFO reaches 1.766. Opt-in bounded refill
reaches 2.614, versus 2.152 for a separate refill-off group on identical source;
its larger batches improve amortization but leave a substantial gap. Neither
owned policy preserves the earlier higher-thread gains. All threshold screens
fail, so ratio 256, refill off and the benchmark's legacy default remain.
The owned backend is retained as an explicit experimental protocol, with its
correctness evidence, variation and remaining causal uncertainty visible.

## Earlier c01 protocol study

The [protocol study](../bench/results/10.176.26.71/bench/mutex_protocol/20261013/README.md)
tests frame retirement reuse, queue-node layout, caller capture, native preflight
and bounded native/delegation epochs. None of the candidates meets the
two-metric 97% target. Native epochs improve the 28-worker result, but their
2/4/16-worker gaps remain; favorable isolated counts do not justify a new default.

The report retains all samples, worker progress, CPU cost, JIT shares, raw
sources and rejected implementations; the accepted provider remains `9b76719`.

## Earlier c01 optimistic-spin study

The [owner-aware retry study](../bench/results/10.176.26.71/bench/mutex_optimistic/20261013/README.md)
adds 369 audited sessions: a fresh three-way baseline and six retry/OSQ screens.
Linux OSQ plus 1,024 retries improves the observed four-worker KD median from
5.063 to 8.445 Mops/s, but its paired Native control reaches 9.463. Medium-thread
gaps remain and all six candidates fail the two-metric 97% target. The provider
and ratio default 256 remain at `9b76719`; the rejected implementation is archived
at `260d330`. Only an explicit owner/wait-list/OSQ drain check is retained in the
benchmark. Low-thread variation and the untested candidate grid points remain
visible; no new default or stable throughput gain is claimed.

## Earlier c01 cost study

The [three-way cost study](../bench/results/10.176.26.71/bench/mutex_c01_cost/20261013/README.md)
adds a fresh Native/TCLock/KD baseline, separate CPU/PMU diagnostics and measured
successor-prefetch experiments. At sixteen workers, baseline Native/TCLock/KD
reach 9.064/3.559/7.230 Mops/s; almost complete delegation does not eliminate
per-body coordination costs. The report separates whole-run and warmed-peak
results, variation, worker shares, CPU cost and the limits of intrusive profiles.
The 97% Native target through 28 remains unmet and ratio default 256 remains.
The retained counter/prefetch changes gain 7.16% median and 7.58% peak at sixty
workers and pass the four higher-thread regression gates. Low-thread results
remain variable, including a lower four-worker median; this is a bounded
higher-thread improvement, not a parity claim. Removing the counter component
fails the thirty-two-worker regression gate and remains archived as rejected.

## Earlier c01 admission study

The [2026-10-13 c01 study](../bench/results/10.176.26.71/bench/mutex_admission/20261013/README.md)
did **not** reach 97% of Native mutex on both median whole-run throughput and
best warmed peak through 28 workers. All eight entry-ratio thresholds (2–256)
failed screening; the default remains 256. The pinned sampler removes cold-path
work, but no low-thread throughput gain is established. Its full-grid run stays
within the specified 3% regression bound at 32, 36, 48 and 60 workers, with
returned JIT bodies in every round.

The report retains 543 correct, progressing, drained sessions, including 48
unscored diagnostics, source/ELF/JIT hashes, variation and CPU/worker-share data.
It uses the regular 64-vCPU VM and collector 63. Adaptive
native acceptance is opt-in and visibly distinct from returned JIT execution.
No candidate qualified for confirmation; this is not a parity result or an
acceptance of other workloads and the 64-worker topology.

## Remaining gaps and comparison limits

Low-thread overhead and Native parity remain unresolved in the c01 studies
above. Their measurements cover specific source versions, workloads and worker
counts; they do not establish universal parity for the current checkout.

The [complete comparison workflow](../tools/vm/README.md#complete-164-worker-comparison)
uses a temporary 66-vCPU boot. At 64 workers, collector vCPU 65, the last worker
and QEMU services share physical host core 63. The regular VM has 64 vCPUs;
collector 63 is excluded from worker cohorts. Keep source versions, topologies,
workload settings, governors and JIT/NO_JIT classes separate.
Aggregate throughput and amortized ns/op do not measure lock-acquisition latency.

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
