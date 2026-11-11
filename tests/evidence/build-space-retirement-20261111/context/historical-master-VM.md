# VM operations

Use this guide for the active Ubuntu 26.04.1 / Linux 7 environment. Source edits,
Git, static inspection and read-only offline evidence checks run on `380G10`.
All builds, unit tests, modules, daemons and timing run only in the designated
VM on `10.176.26.71`. Follow [development rules](../../AGENTS.md).

## Environment

| Purpose | Location |
| --- | --- |
| Source of truth | `380G10:/home/eric/vm/vm-shared/kdlock`, branch `master` |
| QEMU host | `eric@10.176.26.71` |
| Host mirror | `/home/eric/vm/vm-shared/kdlock` on the QEMU host |
| Guest connection | `root@10.176.26.71:2222` |
| Guest source | `/root/host_fs/kdlock` |
| VM scripts / monitor | Host `/home/eric/vm/qemu-scripts`; `/tmp/qemu-monitor.sock` |
| Normal release | `7.0.0-38-kdlock1`; mmap backend disabled |
| Authenticated source package | `linux=7.0.0-38.38`, containing upstream 7.0.14 |
| Normal source / build | `/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/{source,build}` |
| Normal schema-2 bundle | `/root/kdlock-kernel-baselines/linux70-kdlock1-20261027` |
| Separate enabled-MM source / build | `/mnt/kdlock-builds/linux-7.0.0-38-kdmm1/{source,build}` |
| Enabled-MM mode bundles | `/root/kdlock-kernel-baselines/linux70-kdmm1-{native,kd}-20261027` |
| Enabled-MM preparation | `/mnt/kdlock-builds/linux70-mmap-prepared-kdmm1/prepare.json` |
| Translation Python | `/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3` |
| Stock Linux 7 recovery headers | `/usr/src/linux-headers-7.0.0-38-generic` |
| Legacy recovery tree / bundle | `/root/linux-6.1.159-kdclobber2`; `/root/kdlock-kernel-baselines/mutex-clobber2-20260919` |
| Data disk | `/mnt/kdlock-builds`, 132 GiB virtual capacity |
| Second build disk | `/mnt/kdlock-builds2`, 168 GiB virtual capacity |
| Live evidence | `/root/kdlock-evidence/10.176.26.71/{bench,tests}/<new-run>` |

The VM has 64 vCPUs and 24 GiB RAM: node 0 uses CPUs 0–31 and 12 GiB; node 1
uses CPUs 32–63 and 12 GiB. Each vCPU is pinned to the corresponding host CPU;
QEMU service/auxiliary workers use CPU 63. Standard workload workers use `0..N-1`
and collector 63, for `1..8,12..60` workers in steps of four above eight.

## Source synchronization

Inspect Git status and stage intended new paths before using the source-host
synchronizer:

```sh
python3 tools/vm/sync_to_vm.py --dry-run
python3 tools/vm/sync_to_vm.py
```

It freezes tracked bytes, verifies hashes and updates an idle ext4 guest. It
does not delete stale leaves. Never synchronize or edit frozen inputs while a
build, translator or workload is active. Do not edit either mirror as another
source of truth. Follow [synchronization details](../../tools/vm/README.md).

The shared MM benchmark guest gate also admits an immutable private snapshot
at exactly one directory below `/root/kdlock-inputs`, alongside the unchanged
canonical source route. This lets a newer module/runner revision coexist with
the frozen kernel-component inputs required by schema-2 capture. A private
snapshot must be a local ext4 copy, with no symlink component, leaf mount or
nested mount. Its two root-local receipts are `source-state.json` and
`source-sha256.json`. The parent controller supplies their exact hashes through
`KDLOCK_PRIVATE_SOURCE_STATE_SHA256` and
`KDLOCK_PRIVATE_SOURCE_MANIFEST_SHA256`; the guest does not invent expected
hashes from the same files it is admitting.

The state binds a 40-character `git_head`, empty `git_status`, empty
`omitted_missing_tracked_paths`, and exact `files`/`transfer_bytes` totals from
the committed source snapshot. Every other regular file in the private tree
must occur exactly once in the manifest and match its SHA256; extra files,
links, nonregular entries, omitted paths and count/byte mismatches refuse the
snapshot. Keep Python bytecode output disabled and build outside that tree.
The existing guest UID, release, boot UUID, pinned interpreter, recovery,
kernel identity, mode, filesystem and host/topology gates still apply. The
recorded environment includes this source provenance separately from the
kernel-component identity; admitting the copy is not a runtime test pass.

## Kernel identity

Normal `kdlock1` has Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`; its schema-2 manifest SHA256 is
`1d65f61df1be4ab03e358b456d67165d5c9bdc3edd50cf8f15ad651281feca17`.
The separate enabled `kdmm1` image has Build ID
`ac9ea2ec7f24be8b910547bdfdbfb071176677e6`. Its Native/KD bundles bind the same
source, image and configuration with different explicit runtime modes.

From the idle synchronized guest, verify the selected installed/running identity:

```sh
python3 kernel_integration/linux70/verify.py --running
```

Enabled-MM verification additionally selects `--variant kdmm1-native` or
`--variant kdmm1-kd` for the actual boot. Successful live verification must return
`runtime_policy_verified: true`. A normal-kernel pass cannot validate enabled MM.
Do not recapture over an existing bundle. The
[identity guide](../../kernel_integration/linux70/IDENTITY.md) owns capture,
source/configuration/build/installed-file checks and mode binding.

The Ubuntu ABI release and upstream version are different identities: generated
Linux version code remains `458766` (7.0.14). Full-kernel build/install commands
must pass the intended custom `KERNELRELEASE`; do not manufacture it by changing
`SUBLEVEL`. External-module wrappers receive the canonical output directory as
KDIR/`--kernel-source`; do not export `KERNELRELEASE` into those wrappers, where
it may select the inner Kbuild branch. The source directory is separate.

Kernel changes, installation, boot selection and reboot are outside ordinary
module/documentation work. The [Linux 7 port guide](../../kernel_integration/linux70/README.md)
owns the current patch, signing, return-thunk and build boundaries. Captured
experiments and Linux 6.1 commands remain historical inputs only.

## Boot policy

The Linux 7 boots retain `nokaslr nopvspin console=tty1 console=ttyS0`, with
lazy preemption (`full (lazy)` in the selector). Record actual command line,
preemption, topology and mitigation policy before live work. The old voluntary
preemption policy and legacy GRUB override are not current configuration.

Normal `kdlock1` is the default. Enabled `kdmm1` requires its explicit Native/KD
mode and separate prerequisites. Both clean-platform boots were checked with
taint 0 before probes; unsigned/out-of-tree project loads produce expected taint
12288 in the retained live receipts. Those checkpoints are not interchangeable.

Active call-depth tracking is refused by provider initialization because its
return thunk changes arithmetic flags after native-escape restore. Compiled
support alone is not active use. Complete mitigation coverage of handwritten
and generated returns remains separately unvalidated.

## Dependencies and checks

Use the pinned Python above on PATH, [translation requirements](../../disassem/requirements.txt)
and exact [Miasm compatibility patch](../../disassem/compat/README.md). Dependency
bytes are checked before translation. Import success, a skip, missing dependency
or compilation failure is not a pass. Plotting has separate
[requirements](../../bench/archive/requirements.txt).

The [basic runner](../../bench/basic/run.py) is functional-only. It requires a
verified schema-2 running identity, the pinned interpreter, actual recovery tag,
new external output and exact host reference/current captures:
`--host-reference`, `--host-reference-sha256` and `--host-state`.
[Host capture](../../bench/basic/capture_host.py) runs as root on the QEMU host
with the actual `--snapshot` tag. It binds QEMU identity, pins, NUMA mappings,
frequency policies and the monitor snapshot listing. Supply matching selected
reference bytes and a fresh capture; an old reference is not automatically waived
after QEMU/task identities change.

All four current basic presets use sixteen workers and 100,000 iterations per
worker: spin c01, public mutex c01, rwlock c01/20% writes/post4, and rwsem
c16/100% writes/post4. Each requires correct data, positive returned-JIT evidence
and final retirement. The [post-MM normal-boot checkpoint](../../bench/results/10.176.26.71/tests/linux70-normal-basic-20261028/README.md)
passed all four. Its recorded boot is `15dc5977-59d3-4471-a196-d71f03f450ed`;
subsequent catalog endpoints retained that identity. This is historical endpoint
evidence, not a substitute for fresh checks before new live work.

Use basic plus [directly affected checks](../../tests/README.md). Full suites
require explicit scope. Select benchmark commands from the
[runner guide](../../bench/README.md) and [current catalog](../BENCHMARK_WORKLOADS.md),
not a dated Linux 6.1 launch script. No basic check produces a performance score.

## Frequency and timing policy

The requested runtime host policy is fixed **2.0 GHz** on all 64 CPUs:
`performance`, `scaling_min_freq = scaling_max_freq = 2000000` kHz and
`intel_pstate/no_turbo = 1`, with the existing passive `intel_cpufreq` driver.
Preserve this setting; recheck it after a reboot or configuration change.
Configured limits and sampled APERF/MPERF do not prove an exact effective
frequency at every instruction.

The completed Linux 7 catalog permits recorded auxiliary workers on CPU 63 and
labels all timing exploratory. Strict timing qualification remains failed.
Functional placement/data/drain checks have separate verdicts. Freeze the policy
for a new campaign and retain every failed/partial attempt; do not retrospectively
change gates or pool source generations. One round has no repeat variance.

## Snapshots and recovery

Before live module/JIT work, verify an actual recoverable snapshot through the
host monitor. Environment variables are not proof: only after verifying the
listing use `KDLOCK_RECOVERY_CONFIRMED=1` and the matching `KDLOCK_SNAPSHOT_TAG`.
The recorded recovery boundaries are:

| Tag | Scope |
| --- | --- |
| `linux70-kdlock1-clean-20261027` | Signed clean normal Linux 7 kernel and schema-2 identity |
| `linux70-kdmm1-native-clean-20261027` | Clean enabled-MM Native mode before correctness probes |
| `legacy-kdclobber2-20261027` | Historical Ubuntu 22.04 / Linux 6.1 / former 32 GiB data disk |

Creation/listing receipts are in the [port](../../bench/results/10.176.26.71/tests/linux70-port-20261027/README.md)
and [enabled-MM checkpoint](../../bench/results/10.176.26.71/tests/linux70-kdmm1-20261027/README.md).
No restore drill is inferred. Restoring the legacy snapshot rolls back the OS,
disk size and later contents; it is not recovery for a Linux 7 experiment.
The approved 43 old/temporary snapshot removals remain in the
[migration record](../history/vm-ubuntu2604-migration-20261027.md).

Bound SSH and monitor commands. Close only clients created for the operation;
do not send QEMU `quit` or restart a healthy guest because a connection failed.
Archive evidence before recovery and recheck boot, source, modules, policy and
pins afterward. A lost connection or timeout does not establish workload drain.

## Disk housekeeping

The [November 1 expansion](../../bench/results/10.176.26.71/tests/build-disk-growth-20261101/README.md)
grew the second build disk to 160 GiB while preserving existing builds and
results. It had about 86.5 GiB free immediately afterward. Recheck actual
capacity before each build; the MM preparation reserve remains 50 GiB.

Inspect root and data filesystems separately. Use exact deletion inventories and
verify retained source/configuration, identity, recovery and result copies before
removing duplicates. A date alone does not establish obsolescence. Do not run a
blanket kernel clean, force unload, or recursively clear `/root/host_fs`.
[Kernel retirement](../history/kernel-retirement-20261027.md),
[OS/storage migration](../history/vm-ubuntu2604-migration-20261027.md) and
[workload cleanup](../../bench/results/10.176.26.71/tests/workload-retirement-20261027/cleanup.json)
retain the exact completed phases; they are not an open deletion list.

## Drain and evidence

Stop new calls and wait for workers/translators. Retire sources before workload
unload, then unload providers in dependency order. If retirement is busy, keep
pins and diagnose. Never force unload, reopen a retired session or treat a signal
as proof that a blocked ioctl completed.

Replace source/provider/JIT sessions together while idle. Preserve physical
owners, acquisitions, source leases, unlock ACKs, frame retirement and exact image
identity. Mutex images are immutable; ordinary spin/rwlock in-place generations
have the limits in [lifetimes](../design/lifetimes.md).

Save commands/statuses, source/ELF hashes, kernel/boot identity, topology, every
worker's progress, data, JIT entries/returns and final drain. `NORMAL` is publication
only. Public reports belong in `bench/results/<machine>/{bench,tests}/`; raw
archives in ignored `bench/results/<machine>/raw/`. Follow
[result storage](../../bench/results/README.md). Historical string-service and
near-text relocation recipes are archived, not current translation instructions.
