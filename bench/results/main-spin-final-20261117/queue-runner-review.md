# Static review of the main queue-phase comparison

This review read only the main checkout and its prepared host runner. No VM
access, builds, tests or timing were performed by the reviewer.

## Input and result layout

`run-queue.py` packs ten little-endian u32 inputs, followed by five u64 result
fields and two arrays of 64 u64 worker counters. This matches
`bench/kd_bench_uapi.h:82` and `bench/run_nano.py:25`. The five result fields
start at tuple index 10; worker operations start at 15 and worker writes at
79. The ioctl request size is 1104 bytes. Passing cpus=0 gives one CPU per
worker. The result check additionally verifies both worker sums, positive
elapsed time, progress by every worker, zero mismatches and the expected
protected-data sum. Mops/s is correctly computed as ops/elapsed_ns*1000.

The source loops schedule 741 points, including warmups, learning and
functional points. API checks are separate ioctl calls, not timed points.

## Comparison scope

Native, KD and TCLock base spin bodies are generated from the same
`DEFINE_OPS` source body and increment the same padded counter array. Only
the lock entry/release expressions differ. Each lock occupies a separate
128-byte-aligned block; this is equal alignment, not the same lock address
or identical machine-code instruction stream. The worker loop, register-only
post work, periodic cond_resched, CPU assignment and stop convention are shared.
32-worker default rows use CPUs 4..35; the packed control explicitly uses
0..31. The runner cannot by itself establish host NUMA binding or Native
kernel configuration; those require the captured build and pinning receipts.

Timed comparisons use a 250 ms warmup and a nominal 1000 ms interval, with
actual elapsed_ns returned by the kernel. Backend order rotates over three
repetitions; policy order reverses in the middle repetition. The module stops
the elapsed-time clock when it publishes stop, then drains workers before
returning. Completed in-flight operations are included in final counts;
drain time is not in the denominator. All backends use this convention.

## Correctness evidence and its limits

The main spin nano result is an accounting and protected-data consistency
oracle. It has no atomic inside-the-critical-section overlap detector.
For all-write spin rows, torn_reads=0 does not establish a reader-consistency
test because no reader body runs. Exact sums detect lost or extra updates,
but are not a universal proof of exclusion or ownership.

The separate entry fixture does have an atomic inside detector, exact
30,000 operations per worker, and preempt/IRQ/BH state checks. It covers
plain, irq, irqsave, initially-disabled irqsave, bh and clobber entries with
two task-context workers. Its delegation-off execution does not validate
delegated IRQ/BH paths, actual interrupt-handler entry, or arbitrary nesting.

The API routine has exactly 65 CK invocations: 16 spin, seven raw/arch spin,
14 rwlock, eight mutex, eight ww_mutex and 12 rwsem. Each invocation of the
API ioctl runs those single-task assertions on local lock objects. The main
runner invokes it three times, so report three executions of 65 assertions,
not 195 distinct APIs or contended/delegated IRQ validation.

The original rwlock-mixed-check rows use lines=1. Their reader comparison
loop is empty (`bench/kd_bench.c:78`), so they test progress and write totals
but not multi-value reader consistency. The separately prepared
`run-queue-rwcheck.py` retains that evidence and adds eight mixed rows with
lines=16, write_pct=20, Native/KD, workers 8/32 and queue phase 0/1, plus two
learning rows. It records positive reads and writes for every worker and
requires exact totals and zero reader mismatches. Preparation is not execution.

## Counter interpretation

`delegated` counts generated-code section completions and `handback` counts
sections returned unfinished to the origin (`kernel/kd_core.c:641`).
`sessions` counts session invocations that served at least one waiter;
`stop_plain` records a next waiter without generated code and `numa_deferred`
counts waiters moved to the deferred list. The per-CPU statistics are read
and summed without an ownership snapshot. They are approximate event deltas,
not ownership records, unique-request counts or measured physical batch
length. In particular delegated/sessions is not a measured physical chain.

KD statistics sampled around a TCLock point are not TCLock proxy or handback
counts. A zero KD delta for TCLock must not be described as zero TCLock
delegation. Per-cell count sums over three repetitions must be labelled as
such; the median rate can come from just one of those repetitions. Do not
pool functional, warmup and measured counts to explain a single rate.

No profile was collected by the runner, and these are kernel-thread nano
bodies rather than unchanged-application syscall-path evidence.
