# VM operations

The development VM runs Ubuntu 26.04.1 LTS with kernel `7.0.0-38-generic`.
Ubuntu 26.04 / Linux 7.0 is the active adaptation platform; KD porting and
validation remain pending. The [migration record](../history/vm-ubuntu2604-migration-20261027.md)
binds OS, package, boot and storage identities. Linux 6.1 adaptation is retired.
Its single recovery version and historical inputs remain under the
[retirement record](../history/kernel-retirement-20261027.md).

All builds, unit tests, live modules, daemons and benchmarks run in the development
VM on `10.176.26.71`. The source host performs edits, Git, static inspection and
read-only offline evidence checks. See [development rules](../../AGENTS.md).

These operations rules apply to all three [project stages](../ROADMAP.md).
Stage 3's kernel replacement goal is a future integration task, not permission
to modify, install or boot a kernel during documentation or microbenchmark work.
Honor the concrete session authorization; do not ask again for authorized steps.

## Environment

| Purpose | Location |
| --- | --- |
| Source checkout on `380G10` | `/home/eric/vm/vm-shared/kdlock`, branch `master` |
| Benchmark host | `eric@10.176.26.71` |
| Host source mirror | `/home/eric/vm/vm-shared/kdlock` on the benchmark host |
| Guest source | `/root/host_fs/kdlock` |
| VM scripts | Host `/home/eric/vm/qemu-scripts` |
| Guest connection | `root@10.176.26.71:2222`, or host `./vm_ssh.sh` / `ssh kdlock-vm` |
| Active OS/kernel | Ubuntu 26.04.1 LTS; `7.0.0-38-generic` |
| Kernel image/header package version | `7.0.0-38.38` |
| Installed kernel headers | `/usr/src/linux-headers-7.0.0-38-generic` |
| Legacy recovery source/build | `/root/linux-6.1.159-kdclobber2` |
| Legacy captured bundle | `/root/kdlock-kernel-baselines/mutex-clobber2-20260919` |
| Translation/plotting environments | Earlier Python environments are historical; new dependencies remain unvalidated |
| Guest data disk | `/mnt/kdlock-builds`; 132 GiB virtual capacity after the October 27 expansion |
| Live evidence | `/root/kdlock-evidence/10.176.26.71/{bench,tests}/<new-run>` |

The development VM has exactly 64 vCPUs and 24 GiB RAM. Node 0 uses CPUs 0–31
and 12 GiB; node 1 uses CPUs 32–63 and 12 GiB. Each vCPU is pinned to the same
host CPU, with memory on the corresponding host NUMA node. QEMU service threads
share host CPU 63. Verify actual placement and host frequency policy before timing.

On October 27, 2026, the user explicitly requested a fixed **2.0 GHz** host
frequency. All 64 host CPU policies now use the `performance` governor with
`scaling_min_freq = scaling_max_freq = 2000000` kHz and `intel_pstate/no_turbo = 1`.
The passive `intel_cpufreq` driver is unchanged. This is a runtime setting;
recheck it after a reboot or any host configuration change. The
[fixed-frequency nano campaign](../../bench/results/10.176.26.71/bench/nano-mutex-fixedfreq-20261027/README.md)
retains the original settings, readbacks and APERF/MPERF observations. Preserve
this requested setting after the campaign. A configured limit alone is not
proof of effective frequency, and earlier ondemand results remain separate.

Use collector CPU 63 and workers 0 through N−1 for the standard 1–60-worker grid.
Only the spin/mutex synthetic runner supports explicit `--share-collector` for
the optional 64-worker point; this labels CPU 63 contention in the evidence.
Real API and rwlock runs require a separate collector. Keep old 40-, 60- and
66-vCPU measurements separate; never restore snapshots across CPU topologies.

## Source synchronization

On the source host, inspect Git status, stage intended new files, then run:

```sh
python3 tools/vm/sync_to_vm.py --dry-run
python3 tools/vm/sync_to_vm.py
```

The helper freezes tracked bytes, verifies hashes and updates an idle ext4 guest.
It does not delete old files. Review identified obsolete paths separately while
idle; never clear or recursively replace `/root/host_fs`. Do not edit the mirror,
guest source or frozen running inputs as another source of truth. See
[synchronization details](../../tools/vm/README.md).

## Disk housekeeping

Inspect the root and data filesystems separately. Before removing old build
outputs, confirm the VM is idle and exclude captured source/configuration/build
files, recovery inputs and frozen run evidence. An old date alone does not make
an artifact disposable. Use an exact deletion inventory and verify retained
copies before removing duplicates; do not run a blanket kernel-tree clean.
The [October 22 cleanup receipt](../../bench/results/10.176.26.71/tests/vm-disk-cleanup-20261022/README.md)
records the 10.01 GiB reclaimed from four historical build trees and the
preserved kernel identities. That receipt describes the state before the
October 27 retirement; its MM and ancestor build-tree retention is superseded
by the retirement inventory.
The later [October 25 exact-file cleanup](../../bench/results/10.176.26.71/tests/approved-archive-cleanup-20261025/README.md)
removed only three separately approved duplicate guest archives, retaining
hash-matched source-host copies. It freed 552,722,432 bytes on root and
684,572,672 bytes on the data disk. This did not authorize further cleanup or
resume the benchmark stopped by host admission.

The [October 27 retirement](../history/kernel-retirement-20261027.md) removed
the obsolete project kernel installations, ancestor/MM build copies and stale
boot-menu files after preserving their source changes and records. That checkpoint
retained the `kdclobber2` project kernel, source/build tree and captured bundle.
Benchmark evidence and distro-managed packages were outside that deletion scope. The user subsequently approved the exact
43 old and temporary snapshot removals. The
[migration and storage record](../history/vm-ubuntu2604-migration-20261027.md)
records their completed deletion, leaving only `legacy-kdclobber2-20261027`, and
the data disk's expansion from 32 to 132 GiB. The earlier approval rejection
remains part of the recorded history.

## Kernel identity

The verified active release is `7.0.0-38-generic`, with GNU Build ID
`338e542e384c46228f7a378babc0f9bb2b6a5997`. The installed image and matching
header packages have version `7.0.0-38.38`; `/lib/modules/7.0.0-38-generic/build`
resolves to `/usr/src/linux-headers-7.0.0-38-generic`, whose recorded kernel
release matches. The [migration receipt](../../bench/results/10.176.26.71/tests/vm-ubuntu2604-migration-20261027/README.md)
binds the boot, package and configuration hashes.

Read-only checks in the guest:

```sh
cat /etc/os-release
uname -r
dpkg-query -W linux-image-7.0.0-38-generic linux-headers-7.0.0-38-generic
readlink -f /lib/modules/7.0.0-38-generic/build
cat /lib/modules/7.0.0-38-generic/build/include/config/kernel.release
```

Installed headers establish a matching package interface, not a full kernel
source/build tree or a KD port. KD source/configuration selection, clobber and
hook contracts, JIT admission and live compatibility remain unvalidated. The
[legacy identity procedure](https://github.com/hailongeric/kdlock/blob/cd6f1061ea1b3686dd6d43a7a180ab1942ea4e57/docs/operations/VM.md#kernel-identity)
applies only to the retained Linux 6.1 recovery environment; it is not the
identity gate for this boot.

## Boot policy

The verified Linux 7.0 boot retained `nokaslr nopvspin console=tty1 console=ttyS0`.
The preemption selector reported `full (lazy)`, whereas the legacy measurements
used voluntary preemption. This upgrade does not establish equivalent kernel
configuration, instrumentation or timing qualification. Taint was zero, no
project modules were loaded, and no failed services were reported.

Read the actual command line, selector and topology before new live work:

```sh
cat /proc/cmdline
cat /sys/kernel/debug/sched/preempt
cat /sys/devices/system/cpu/online
```

GRUB now selects its first normal kernel entry instead of an explicit Linux 6.1
entry. The captured [legacy GRUB override](../../kernel_baseline/nopvspin-grub.cfg)
is provenance and must not be installed as the current boot configuration.
Kernel rebuilds, boot changes and restarts remain outside ordinary development
work unless the session authorizes them.

## Dependencies and checks

The active system reports Python 3.14.4 and GCC 15.2.0. Earlier translation and
plotting virtual environments are historical artifacts; their old dependency
passes do not establish compatibility with this interpreter. Establish isolated
environments for the [translator requirements](../../disassem/requirements.txt)
and [plotting requirements](../../bench/archive/requirements.txt), and verify
them before future KD builds or measurements.

The [legacy build and dependency recipe](https://github.com/hailongeric/kdlock/blob/cd6f1061ea1b3686dd6d43a7a180ab1942ea4e57/docs/operations/VM.md#dependencies-and-checks)
retains the old KDIR and Python environment for historical reconstruction only.
No KD module build, unit-test pass or live validation on Linux 7.0 is claimed by
the OS upgrade. Confirm idle state and use basic plus directly affected checks
when adapting KD. Full suites still require explicit selection; missing
dependencies, skipped checks and compilation failures are not passes.

## Snapshots and recovery

Before live module/JIT work, confirm an actual recoverable snapshot through
`/tmp/qemu-monitor.sock` on the benchmark host. `savevm` must succeed and
`info snapshots` must list the tag. Only then set `KDLOCK_RECOVERY_CONFIRMED=1`
and the recorded `KDLOCK_SNAPSHOT_TAG`. Environment variables alone are not proof.
The only retained snapshot is `legacy-kdclobber2-20261027`. The user explicitly
approved deleting the 42 earlier snapshots and the temporary pre-cleanup
snapshot; the [migration record](../history/vm-ubuntu2604-migration-20261027.md)
records all 43 completed removals. The retained snapshot captures Ubuntu 22.04
and the former 32 GiB data disk. Restoring it also restores that disk size and
rolls back subsequent active contents, including the Ubuntu 26.04 migration.
Recovery of the new platform has not been validated; this legacy snapshot is
not a capture of its current state. Establish the recovery boundary before
future live module/JIT work, and recheck the actual snapshot list, topology and
boot identity before recovery.

Use bounded SSH and monitor commands. Root-owned sockets may need sudo. Disconnect
without sending `quit`; close only monitor clients created for the operation.
If SSH fails, save `/tmp/qemu-serial.log` and inspect the actual host process view.
Never restart a healthy guest merely because a monitor client failed. Verify the
old VM exited before starting another. The launcher at
`/home/eric/vm/qemu-scripts/run_vm.sh` supports `recovery`, `shared`, `status`,
`monitor [COMMAND]` and `stop`; shared mode does not establish snapshot support.
Archive evidence before recovery, then recheck source, modules, policy and pins.

## Drain and evidence

Stop new calls and wait for workers and translators. Retire sources before
unloading workloads, then unload providers. If retirement returns EBUSY, retain
pins and diagnose remaining users. Never force unload or reopen admission.
A timeout or signal does not prove a blocked ioctl drained.

Replace workload, provider and JIT session together. Mutex frames bind immutable
generations until session teardown. Ordinary spin/rwlock images remain keyed by
RIP with in-place replacement; an ABI1 spin entry that publishes checked pointer
loads or either original string API service (`strcmp` or `strscpy_pad`) transitions to
immutable images for that and every later generation. ABI1/3 root instruction
markers (requirements exactly 33) make the same transition. Earlier frames keep their
original descriptor and code. This does not permit
editing frozen inputs or replacing source while work is active. Owners, ACKs,
source leases and generated images have distinct [lifetimes](../design/lifetimes.md#executable-images-and-guarded-spin-transition).

The provider currently advertises capability version 12. String-service
runners must require bit 9 plus bit 7 for `strcmp` or bit 8 for `strscpy_pad`.
Bit 9 means that the original caller guarantees valid memory and lifetime;
KD performs no helper instruction checks, string scans or destination-bound
rechecks. Common lock ownership, frame and pending CALL continuation checks
remain. Optional bit 10 allows direct calls inside one generated invocation;
the direct-string probe requires it. Images using it add requirement value 16.
Its separate near-text pool may be unavailable, in which case translation keeps
the existing dispatcher route. Version alone does not prove a feature is available. See the
[API admission contracts](../design/admission.md#original-strcmp-service).
Bit 11 plus bit 5 separately enables ordinary task-context ABI1/3 root
instruction exits; their positive probes must require both and an immutable
requirement-33 image.

Direct CALL operands are filled before publication. The uploaded `jit.bin` has
placeholder operands and therefore differs from the executable image. Current
benchmark sessions capture actual loaded bytes from `/proc/kcore` under a
readonly provider reference, outside worker timing, and retain both hashes.
Replay compares every byte against the uploaded image with only the recorded
relative CALL operands changed. Capture the exact original helper symbol
addresses and kernel identity separately for independent reconstruction.

The final direct-helper implementation `05876a4` passed its
[focused wrapper and live checks](../../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md#candidate-3-checks)
and completed all 18 [diagnostic profiles](../../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md#final-diagnostic-profiles)
with drain and tracing restored. Profiles and the separate KD-only screen do not
establish performance against fresh controls. The separate
[standard-grid comparison](../../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
completed 567 validated, drained sessions for read-only taskname and xattr tail
with 16 and 128 entries. Main-round and development archives passed independent
preservation checks. The separate n129 quota control and its archive check also
passed; its generated prefixes and native completion are unscored. Retain the
failed early profile and its missing pre-refusal tracing snapshot as documented
in the [development record](../../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md#development-and-quota-archive-preservation).

The historical v10 dispatcher passed
[focused correctness checks](../../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/DEVELOPMENT.md#final-live-acceptance)
through candidate 6. Its
[`88bb5a4` standard-grid comparison](../../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/README.md)
completed all 567 sessions with validation and drain, and its per-session kernel
logs contained no recorded fault matches. This does not establish taskname
mutation delegation or performance parity with Linux Native or TCLock.
Preserve the frozen `c79d84f`
checked implementation's logs and measurements under their existing source
identity. Its preliminary string-length check and native-fallback probe are
historical behavior. New probes must validate original API results, returned
JIT bodies and complete drain; do not reuse those earlier pass labels for the
changed implementation.

Save commands, exit statuses, source/ELF hashes, kernel identity, topology,
business results, every worker's progress, returned JIT counts and final drain.
NORMAL means publication, not execution. Preserve failures and interrupted runs;
do not pool different frozen inputs. Published reports belong in
`bench/results/<machine>/{bench,tests}/`; raw archives belong in ignored
`bench/results/<machine>/raw/`. See [result storage](../../bench/results/README.md).
