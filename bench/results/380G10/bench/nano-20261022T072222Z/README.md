# Current nano benchmarks in a temporary source-host VM

All 3,600 sessions were collected on 2026-10-22, from 07:34:54 to 11:53:24 UTC.
Every session passed data checks and drained safely. **35 KD mutex linked-list
sessions failed the required JIT check** and remain excluded from scores.
There are 3,565 eligible sessions and 1,179 complete three-repeat comparison
points. See the [collection summary](report/collection.json),
[execution verdicts](matrix-status.json), and [final health](final-health.json).

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
use UBSAN off. All 3,600 planned sessions were collected.

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

The report independently reconstructs the maintained private-provider preparation
from the frozen production sources and observation patch. The
[reconstruction manifest](report/provider-reconstruction.json) matches the
prepared copies retained by the runners. Plotting used a separate environment;
its [pinned package versions](plotting-env.json) were verified and `pip check`
passed.

### Plots and tables

Each plot contains c01, c08, list16, list128 and RCUHT panels for the full worker
grid. PNG and matching SVG files are retained. Bars show the observed min/max
across three repeats; hollow points have fewer than three eligible repeats in
one execution class. Missing or rejected cohorts break the curves.

| Lock / write mix | Whole-run throughput | Warmed peak throughput |
| --- | --- | --- |
| Spinlock, exclusive | [PNG](report/spin-whole.png) | [PNG](report/spin-peak.png) |
| Mutex, exclusive | [PNG](report/mutex-whole.png) | [PNG](report/mutex-peak.png) |
| Rwlock, 1% writes | [PNG](report/rwlock-w01-whole.png) | [PNG](report/rwlock-w01-peak.png) |
| Rwlock, 20% writes | [PNG](report/rwlock-w20-whole.png) | [PNG](report/rwlock-w20-peak.png) |
| Rwsem, 1% writes | [PNG](report/rwsem-w01-whole.png) | [PNG](report/rwsem-w01-peak.png) |
| Rwsem, 20% writes | [PNG](report/rwsem-w20-whole.png) | [PNG](report/rwsem-w20-peak.png) |

- [Individual sessions](report/samples.csv), including status, execution class,
  JIT entry/return shares and receipt hashes.
- [Grouped medians, min/max and spread](report/summary.csv).
- [Matched KD/control ratios](report/comparisons.csv).
- [Input-manifest hashes](report/input-manifests.json).

The 1,200 planned provider/workload/mix/worker points yield 1,179 complete
three-repeat groups. Incomplete groups are retained without a comparison ratio.
A positive entry or return witness does not mean every operation was delegated;
the per-session shares record that distinction.

| KD lock | Eligible local / no JIT | Entry-only witness | Returned-body witness | Failed JIT requirement |
| --- | ---: | ---: | ---: | ---: |
| Spinlock | 105 | 72 | 48 | 0 |
| Mutex | 28 | 117 | 45 | 35 |
| Rwlock | 278 | 0 | 172 | 0 |
| Rwsem | 281 | 0 | 169 | 0 |

The 35 failures comprise 20 list16 and 15 list128 mutex sessions. Their exact
names are retained in [matrix-status.json](matrix-status.json). Local sessions
whose runner verdict is `OK` are scored separately from JIT sessions; failed
`NO_JIT` verdicts are not scored. All 2,250 Native/TCLock control sessions passed.

### Results at 36 workers

Values below are whole-run median Mops/s from three eligible repetitions in the
same execution class. Ratios use those matched medians. `Entry only` means the
runner recorded entry witnesses without a completion probe. `Local` means zero
JIT entries. The complete curves above include every requested worker count.

| Lock | Writes (%) | Payload | Native | TCLock | KD | KD evidence | KD/Native | KD/TCLock |
| --- | ---: | --- | ---: | ---: | ---: | --- | ---: | ---: |
| spin | 100 | c01 | 3.399 | 5.815 | 6.045 | entry only | 1.78 | 1.04 |
| spin | 100 | c08 | 3.373 | 4.420 | 5.833 | entry only | 1.73 | 1.32 |
| spin | 100 | list16 | 1.168 | 4.504 | 3.766 | returned | 3.22 | 0.84 |
| spin | 100 | list128 | 0.301 | 2.781 | 2.023 | returned | 6.72 | 0.73 |
| spin | 100 | rcuht | 1.599 | 2.612 | 1.820 | entry only | 1.14 | 0.70 |
| mutex | 100 | c01 | 3.711 | 4.381 | 4.118 | entry only | 1.11 | 0.94 |
| mutex | 100 | c08 | 4.016 | 3.411 | 3.988 | entry only | 0.99 | 1.17 |
| mutex | 100 | list16 | 4.215 | 2.831 | 4.037 | returned | 0.96 | 1.43 |
| mutex | 100 | list128 | 2.543 | 2.236 | — | incomplete | — | — |
| mutex | 100 | rcuht | 1.861 | 2.200 | 1.538 | entry only | 0.83 | 0.70 |
| rwlock | 1 | c01 | 12.112 | 14.356 | 14.745 | returned | 1.22 | 1.03 |
| rwlock | 1 | c08 | 10.091 | 12.682 | 9.918 | returned | 0.98 | 0.78 |
| rwlock | 1 | list16 | 5.009 | 5.461 | 6.047 | returned | 1.21 | 1.11 |
| rwlock | 1 | list128 | 1.951 | 2.284 | 1.999 | local | 1.02 | 0.87 |
| rwlock | 1 | rcuht | 11.550 | 13.436 | 13.195 | returned | 1.14 | 0.98 |
| rwlock | 20 | c01 | 5.588 | 6.297 | 10.681 | returned | 1.91 | 1.70 |
| rwlock | 20 | c08 | 4.731 | 5.961 | 8.101 | returned | 1.71 | 1.36 |
| rwlock | 20 | list16 | 2.204 | 4.099 | 4.426 | returned | 2.01 | 1.08 |
| rwlock | 20 | list128 | 0.567 | 1.290 | 0.565 | returned | 1.00 | 0.44 |
| rwlock | 20 | rcuht | 4.149 | 4.917 | 4.876 | returned | 1.18 | 0.99 |
| rwsem | 1 | c01 | 1.614 | — | 4.027 | local | 2.50 | — |
| rwsem | 1 | c08 | 1.612 | — | 3.919 | local | 2.43 | — |
| rwsem | 1 | list16 | 1.626 | — | 3.635 | local | 2.24 | — |
| rwsem | 1 | list128 | 1.178 | — | 1.850 | local | 1.57 | — |
| rwsem | 1 | rcuht | 1.449 | — | 3.949 | local | 2.73 | — |
| rwsem | 20 | c01 | 2.213 | — | 1.439 | returned | 0.65 | — |
| rwsem | 20 | c08 | 2.260 | — | 1.387 | returned | 0.61 | — |
| rwsem | 20 | list16 | 3.102 | — | 1.564 | returned | 0.50 | — |
| rwsem | 20 | list128 | 1.399 | — | 1.145 | returned | 0.82 | — |
| rwsem | 20 | rcuht | 1.032 | — | 1.368 | returned | 1.33 | — |

At this endpoint, KD spinlock exceeds Native in each payload, while TCLock leads
KD on both lists and RCUHT. Mutex results are mixed, and list128 lacks a complete
KD point. Rwlock's 20%-write c01 case favors KD, but its list128 case trails
TCLock. Rwsem's 1%-write gains are local-execution results; at 20% writes KD trails
Native on four payloads and leads on RCUHT. These are separate comparisons, not
a pooled ranking of lock types with different operation mixes and post-work.

The 36-worker, 20%-write rwlock c08 KD point has unusually wide variation:
7.933 / 8.101 / 19.311 Mops/s for min / median / max, a 140.45% range relative to
the median. The outlier is retained in the data and plot; this point does not
establish a stable gain. All other per-point spreads are available in the CSV.

### Preservation and shutdown

The [final health audit](capture-health.py) checked all 3,600 session/kernel-log
pairs, worker and collector placement, 1,350 exact KD retirements, unchanged
publication records and all 664 frozen source files. It found no per-session
kernel faults or faults in retained final dmesg. The [host comparison](host-comparison.json)
confirms matching QEMU arguments, CPU topology, vCPU identities, pins and governors.

The complete evidence is stored under
`bench/results/380G10/raw/bench/nano-20261022T072222Z/`, excluded from Git.
The [archive receipt](archives.json) records two archives:
225,184,874 bytes for `matrix.tar.gz` and 5,764,681 bytes for `metadata.tar.gz`.
The latter retains the original frozen source tarball, reporting environment,
scripts, source identities, preflight failure and final health evidence.

The [read-only archive verifier](verify_archive.py) passed; see
[verification receipt](archive-check.json). It checked 131,011 paths,
114,617 file hashes, 4,712 source-file instances (including 768 generated-provider
instances), 117 binaries and all 3,600 session receipts. It also verified the
original source-tar hash, health/report script identities and all 16 source and
binary manifests. The guest archiver confirmed an unchanged inventory and final
idle state. A separate [compact-copy check](compact-check.json) verified all 54
downloaded report/metadata files against that archive, including all 32 files in
`report/`; the checked serial-log copy is retained in the ignored raw directory.

The first report attempt failed because it treated generated provider paths as
original checkout paths. Its [error log](report.log), original script and empty
output directory are retained. The corrected report reconstructs the provider
from the frozen inputs and compares exact prepared hashes; its
[successful receipt](report-retry.command.json) is separate. Benchmark inputs
and measurements were not changed by this reporting correction.

After verified export, the temporary guest powered off gracefully, QEMU PID
901846 exited, and port 2223 closed. Its two new overlays and their temporary
recovery snapshot were retired; the existing base disks were retained. See the
[shutdown receipt](shutdown.json). The occupied `10.176.26.71` host was not used.
