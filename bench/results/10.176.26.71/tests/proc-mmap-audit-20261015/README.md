# Process/mmap source audit, 2026-10-15

This is retained source and syscall-path evidence, with an offline recheck on
2026-10-18. It is not a contention measurement, container scalability benchmark
or current KD performance result. The maintained interpretation and proposed
workloads are in the [workload catalog](../../../../../docs/BENCHMARK_WORKLOADS.md#process-inspection-and-mmap-candidates).

## Original evidence

[audit.json](audit.json) is byte-identical to
`9a4bf2af9a52a92e147b439393f21343b7fc99af:docs/proc_mmap_source_audit.json`.
Its dates, source identities and observations are preserved unchanged. The
original audit inspected `/root/linux-6.1.159-kdclobber2` in the recovery guest
on `10.176.26.71`. It recorded matching live/source Build IDs
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960` and the captured configuration.
This did not authenticate every source file or establish a reproducible build.

The local ignored raw archive is
`bench/results/10.176.26.71/raw/tests/proc-mmap-audit-20261015/`:

- `kernel-inputs/`: 25 captured source/configuration files.
- `ps-comm.strace`, `ps-args.strace`, `ps-threads.strace`: procps-ng 3.3.17
  `openat`, `getdents64` and raw-address `read` traces. Command output was
  discarded; the traces identify paths rather than saving read buffers.
- `captured-kernel-manifest.json`, `guest-identity.raw` and `audit.json`:
  original identity/provenance material.

The three commands were `ps -e -o pid=,comm=`, `ps -e -o pid=,args=` and
`ps -eL -o pid=,tid=,comm=`. All exited successfully. They opened process
`stat`/`status`; the arguments command additionally opened `cmdline`, and the
thread command enumerated `task` and opened per-thread files. None opened
`maps` or `smaps`. Their process populations differed slightly, so syscall
counts must not be compared as performance samples.

## Offline recheck, 2026-10-18

[offline-recheck-20261018.json](offline-recheck-20261018.json) records exact
paths and hashes. All 25 kernel/configuration files, all three traces and the
captured baseline manifest matched the original audit. It also identifies the
current source revision and the four provider/interface files reviewed for
delegation feasibility. This recheck did not connect to or change the guest,
retrace `ps`, verify today's live kernel, build code or run tests/benchmarks.

The source review confirmed the separation between per-task `alloc_lock`,
per-MM `arg_lock`/mmap rwsem, per-group signal/accounting locks, and the global
task-list lock in lifecycle paths. It also confirmed the lockless-first
statistics traversal, maps-open `exec_update_lock`, mmap downgrade behavior and
the tracepoint boundaries described in the catalog.

The separate [historical snapshot experiment](../../bench/proc_snapshots/20261015/README.md)
establishes complete delegation for an extracted four-word argument-boundary
payload and a refusal for the exact task-name helper. Its implementation and
measurements do not establish current runnable support or delegation of full
procfs/mmap operations.
