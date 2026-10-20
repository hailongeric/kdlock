# Rwlock execution admission and QEMU thread diagnosis

Status: active, continuing from clean source `d58f7cf`. The previous collection
and archives did not complete the unresolved engineering goals. The source host
reports hostname `380G10`; the same recovery VM and boot remain in use. Extended
module/task/evidence-writer checks on 2026-10-21 confirmed no active run before
this stage began. The main agent remains the sole writer and VM test executor.

The first targets are the strict `list-n16-kdlock-w020-t08-r00` failure and
the original 83/86-versus-67 host endpoint failures. Their data, images,
retirements, receipts and complete archives remain unchanged in the
[prior report](../nano-list-followup-20261020/README.md).
The remaining 69 rwlock cases, seven mutex regressions, p95 measurement and
overhead, shared-family acceptance and real mmap/fault integration remain
required work. Diagnostic instrumentation and its overhead will be identified
separately from acceptance results.

The initial host hypothesis comes from the
[QEMU 8.2.2 thread-pool source](https://raw.githubusercontent.com/qemu/qemu/v8.2.2/util/thread-pool.c):
its disk-I/O pool creates threads named `worker`, inherits main-loop affinity,
and allows idle workers above the minimum to exit after ten seconds.
This matches properties of the retained observations but does not yet bind
those workers to the running binary or establish their effect during timing.
A read-only process/I/O capture will identify the installed executable and
configuration before a bounded, separately labelled causal diagnostic.

For rwlock, publication success is already established. The next provider
diagnostic must distinguish CPU ratio/time gates, native queue-prefix vetoes
and per-lock heat during warmup and the measured phase. It must preserve the
existing branches, ownership and strict returned-JIT requirement. No failed
case will be repeated merely to obtain a favorable execution class.

## Host I/O diagnostics

`host-inventory-1` binds the running PID 257489 to installed
`qemu-system-x86` package `1:8.2.2+ds-0ubuntu1.18` and executable SHA-256
`8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854`.
Its raw command-line hash is
`08a7ad4ddad7da7d6437c5ebcc2987894c2e69b1cd8abd31db0bd491f30ce917`.
Both existing qcow2 drives use writeback cache; no named IOThreads or explicit
aio/pool override were reported. The first snapshot has 68 threads, including
one `worker` pinned to CPU 63, with recent system-disk I/O while KD is idle.

Two serial diagnostic arms, `ram-1` and `disk-1`, each created and verified
33,554,432 bytes with eight CPU-pinned workers, fsync, and a 12-second setup
settle interval. All files remain in their new VM directories. No KD module or
lock workload ran concurrently. These are I/O stimuli, not throughput samples.
The [summary](io-summary.json) retains per-worker host I/O and block counters.
RAM endpoints had 67/68/68 QEMU threads; ext4 endpoints had 71/72/72.
Extra workers had positive write-byte counters. System-disk writes increased
even during the RAM control and both subsequent 12-second observation intervals.
The ext4 arm added 34,648,064 block-layer bytes between its before/after receipts.
Thus ordinary root-disk activity is a demonstrated source of worker I/O, but
these observations do not identify the exact producers or activity in historical
timing intervals. The background writes confound a simple RAM-versus-disk
attribution. The earlier strict 83/86-thread failures remain unchanged.
The [raw index](raw-index.json) binds every full host capture and stderr file
to its retained local path and the 268,489-byte archive, SHA-256
`0ad70baada318e865e8d84d0457c65db318f76d030f92ca893530cedda460e23`.

## Planned rwlock diagnostic and coverage

The provider-only observation patch adds 35 preallocated per-CPU fields, read
at drained phase boundaries. It retains every threshold, native queue-prefix
branch, ownership record, image, ACK and retirement check. The production
provider and workload binaries remain frozen. Its additional instructions and
changed layout are diagnostic overhead, not an accepted optimization.

The fixed diagnostic plan contains three original/observed pairs at eight
workers and three at sixty, alternating arm order. Every arm reuses the
original caller, daemon, translator, guard and collector. The original provider
is reused byte-for-byte; only the observed provider is rebuilt in a new tree.
All cases retain the two-second duration, original warmup, mix, sampling,
CPU placement and strict returned-JIT requirement. Separate phase counters
must classify all root entries, lock records and queue checks completely.

The subsequent coverage plan contains exactly the original 69 unstarted
rwlock cases, with unchanged binaries and arguments. The runner retains a
strict `NO_JIT` failure and may proceed only after verified complete drain and
exact source retirement. Every other error stops the sequence. Completing
coverage does not convert a failed case into a pass; overall success still
requires every planned case to pass. Both plans retain the strict 67-thread
host admission check and require fresh recovery-snapshot confirmation.
Preparation, basic/affected checks and live runs are not yet complete.
