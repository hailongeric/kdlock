# Current nano benchmarks in a temporary source-host VM

Collection is running. This report does not yet establish a complete comparison.

The user requested a temporary VM because the regular `10.176.26.71` benchmark
host was occupied. The requested name `380G10-1` did not resolve; the user then
confirmed use of the current source host and its existing `/home/eric/vm`
scripts and images. The measured physical host identifies itself as `380G10`,
address `10.176.26.33`. No connection or change to `10.176.26.71` was needed.

## Frozen implementation and VM

- Source: `050c1aad72b7de45c6dd3d19b8299314f7471faf`, clean at capture.
  [Source identity](source-state.json) and [file hashes](source-sha256.json)
  bind 664 files, including private `.inc` files. Historical result directories
  are excluded from deployment.
- Kernel: unchanged `6.1.159-kdclobber2`, Build ID
  `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`; the exact source/config/build/live
  identity check passed. See [kernel identity](kernel-identity.log).
- Temporary VM: 40 vCPUs, two sockets with 20 cores each, no SMT; 28 GiB RAM,
  with 14 GiB bound to each corresponding host NUMA node. Each vCPU is pinned
  to the same numbered host CPU. QEMU userspace service threads use host CPU 39;
  its captured `kvm-nx-lpage-re` helper uses CPU 37. Both are outside the workers
  and collector.
- Workers use CPUs 0 through N−1; collector CPU 38 is dedicated. NUMA node 0
  contains CPUs 0–19 and node 1 contains CPUs 20–39. The first requested cohort
  crossing nodes is 24 workers.
- Boot policy: `nokaslr`, `nopvspin`, voluntary preemption. Host CPU governors
  remain `powersave`; the capture records the actual setting on every CPU.
- The existing `ubuntu22.04.img` and `sda.qcow2` are read-only backing files for
  new writable overlays under `/run/qemu/kdlock-nano-20261022T072222Z/`.
  The separately mounted `ubuntu22.04_mal.qcow2` is untouched. The old guest
  source was preserved by rename inside the overlay before fresh deployment.
- Recovery snapshot `before-nano-20261022T072222Z` was successfully saved and
  listed on both disks before live module/JIT work. The [host receipt](host-before-matrix.json)
  records the snapshot, QEMU arguments, CPU pins and memory bindings.
- Guest SSH is on `127.0.0.1:2223`. Evidence is under
  `/root/kdlock-evidence/380G10/bench/nano-20261022T072222Z`.

These results are a separate topology and collection identity from the regular
64-vCPU guest and from earlier 40-vCPU measurements.

## Requested matrix

Workers: `1 2 3 4 5 6 7 8 12 16 20 24 28 32 36`.

| Family | Providers | Payloads | Operation mix | Sessions |
| --- | --- | --- | --- | ---: |
| Spinlock | Linux Native, TCLock, KD | c01, c08, list16, list128, RCUHT | Exclusive updates | 675 |
| Mutex | Linux Native, TCLock, KD | Same five payloads | Exclusive updates | 675 |
| Rwlock | Linux Native, TCLock, KD | Same five payloads | 1% and 20% writes | 1,350 |
| Rwsem | Linux Native, KD | Same five payloads | 1% and 20% writes | 900 |

The current implementation has no TCLock sleeping-rwsem backend. That cell is
unavailable; the spinning TCLock rwlock is measured only in the rwlock family.
The user explicitly selected all three workload families. Linked-list cases use
ordinary resident traversal at 16 and 128 nodes; prefetch variants are outside
this selection. Mutex uses literal public `kd_mutex_lock/unlock` calls.

Each point has three repetitions with rotated backend order, 48,000 warmup
operations per worker, two-second timing, 10 ms samples, and the highest valid
300 ms full-cohort window after 300 ms settling. Spin/mutex uses post64;
rwlock/rwsem uses post4. NUMA selection is on and private benchmark providers
use UBSAN off. There are 3,600 planned sessions.

The [controller](run-matrix.py) runs maintained per-family runners serially and
checks all session receipts, source hashes, boot identity and drain. Its
[concrete plan](matrix-plan.json) preserves the exact commands. Drained NO_JIT
failures may be collected without becoming passes or eligible timing scores;
other failures stop collection. A deadline leaves a child for inspection and
never establishes drain or forces unload.

## Preflight evidence

[Preflight checks](preflight-checks.json) retain both passes and the failed check.
The two basic C programs, 58 spin/mutex runner checks, 26 reader/writer runner
checks, pinned dependency check and kernel identity check passed.

The existing peak test ran ten cases and failed its shared-collector parser
expectation: it assumes exactly 64 online CPUs and expects that option to reach
the device-open step. The unchanged client correctly rejects it on 40 CPUs.
The other nine cases passed; the full test is **not** recorded as a pass. The
[original failure](peak-checks.log) is preserved.

The separate [topology check](tests/collector_topology.py) builds the unchanged
client with the same device-open interception. It verifies that all 15 requested
cohorts accept dedicated collector 38, all 15 overlapping collector choices are
rejected, and both shared-collector cases are rejected on this topology.
All 32 checks passed; see [receipt](collector-topology.json). No admission check,
probe, benchmark source or lock implementation was changed.

## Reporting

The [report generator](report.py) retains each session and groups repetitions by
lock, payload, write mix, worker count, provider and execution class. It separates
returned JIT bodies, entry-only witnesses, partial JIT and local execution.
Only three eligible repetitions in one group yield a complete comparison point.
Failed sessions and incomplete groups remain visible. Throughput comparisons
use matched complete groups and do not pool workloads, call shells or topology.

Final collection status, archive checks and plots will be added after collection.
