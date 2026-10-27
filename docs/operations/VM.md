# VM operations

The development VM runs Ubuntu 26.04.1 LTS. The reviewed Linux 7 development
kernel, `7.0.0-38-kdlock1`, has been built, installed and booted. Its first boot
had unsigned-module taint 8192 before project loads. Signing repair, the
subsequent clean boot and the four-family KD basic functional run passed.
The separate enabled-MM `7.0.0-38-kdmm1` image has also built, installed and
booted cleanly in Native/KD modes. Its
[checkpoint](../../bench/results/10.176.26.71/tests/linux70-kdmm1-20261027/README.md)
records fresh API, mapping, fault and completed-fault passes in both modes,
followed by all 42 shared-MM timing points with normal drain. Together with the
84 private-MM points in their separate campaign, all 126 selected MM points are
complete. Measurements remain exploratory, one round per point. The original
`contention_ok` failure, later cleanup and separate diagnostic pass remain
intact. `kdlock1` remains the normal boot default. The
[post-MM normal-boot checkpoint](../../bench/results/10.176.26.71/tests/linux70-normal-basic-20261028/README.md)
records boot `15dc5977-59d3-4471-a196-d71f03f450ed` and a fresh passing
four-family functional run; subsequent catalog endpoints remained on that boot.
The
[port record](../../bench/results/10.176.26.71/tests/linux70-port-20261027/README.md)
owns the new source, build and validation evidence. The
[migration record](../history/vm-ubuntu2604-migration-20261027.md)
binds the preceding OS, package, boot and storage identities. Linux 6.1 adaptation is retired.
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
| OS/normal development release | Ubuntu 26.04.1 LTS; `7.0.0-38-kdlock1` |
| Separate enabled-MM release | `7.0.0-38-kdmm1`; verify the actual `kd_mmap=off/on` boot mode |
| Boot and basic validation | Post-MM normal boot `15dc5977-59d3-4471-a196-d71f03f450ed`; all four basic cases passed with returned JIT bodies and final idle |
| Authenticated Ubuntu source package | `linux=7.0.0-38.38`, containing upstream 7.0.14 |
| Pristine guest source | `/mnt/kdlock-builds/ubuntu-7.0.0-38-source/linux-7.0.0` |
| Development source | `/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/source` |
| Development output / external-module KDIR | `/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build` |
| Verified schema-2 identity | `/root/kdlock-kernel-baselines/linux70-kdlock1-20261027` |
| Enabled-MM source/build | `/mnt/kdlock-builds/linux-7.0.0-38-kdmm1/{source,build}` |
| Enabled-MM preparation | `/mnt/kdlock-builds/linux70-mmap-prepared-kdmm1/prepare.json` |
| Enabled-MM mode bundles | `/root/kdlock-kernel-baselines/linux70-kdmm1-{native,kd}-20261027` |
| Stock recovery headers | `/usr/src/linux-headers-7.0.0-38-generic` |
| Legacy recovery source/build | `/root/linux-6.1.159-kdclobber2` |
| Legacy captured bundle | `/root/kdlock-kernel-baselines/mutex-clobber2-20260919` |
| Translation Python | `/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3` |
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

The installed development release is `7.0.0-38-kdlock1`, GNU Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`. Its final revision-2 build preserved
the complete configuration and source during compilation. The source package
contains 7.0.14, so the generated Linux version code remains `458766` despite
the Ubuntu ABI release name. The full kernel build/install commands must pass
`KERNELRELEASE=7.0.0-38-kdlock1`; never change `SUBLEVEL` to manufacture the
release string. Ordinary external-module wrapper Makefiles instead receive the
canonical build directory as KDIR. Do not export `KERNELRELEASE` into those
wrappers: many use its presence to select their inner Kbuild branch.

The custom image, config and System.map match their build hashes. All 6,901
installed module copies were inventoried; debug stripping reduced their total
size to 668,795,275 bytes after signing repair while the original build modules and vmlinux remained
unchanged. `/lib/modules/7.0.0-38-kdlock1/{build,source}` points to the separate
canonical directories above. Installation preserved GRUB, the stock Linux 7
boot files and the legacy recovery kernel. Its initial signing failure and
subsequent mode-only repair are documented in the
[kernel installation guidance](../../kernel_integration/linux70/README.md#configuration-and-validation-boundary).
All 6,827 policy-selected signatures were checked against the built certificate;
74 Ubuntu staging exclusions remain unsigned. Installation alone did not
validate KD or clear the first boot's unsigned-module taint.

The canonical schema-2 bundle was captured after the clean custom boot and
passed running verification with `runtime_policy_verified: true`. Its manifest
SHA256 is `1d65f61df1be4ab03e358b456d67165d5c9bdc3edd50cf8f15ad651281feca17`.
The manifest and all 23 named bundle files were independently copied and
hash-verified on the source host. Recheck the existing identity from the idle,
synchronized guest checkout:

```sh
python3 kernel_integration/linux70/verify.py --running
```

The [schema-2 capture procedure](../../kernel_integration/linux70/IDENTITY.md)
requires a new bundle directory; do not recapture over the current identity.
It binds source/configuration, release/version headers,
exports, ELF/build ID, installed boot files and exact runtime policy. The mmap
preparation receipt remains required even with `CONFIG_KDLOCK_MMAP` disabled;
the current capture uses `/mnt/kdlock-builds/linux70-mmap-prepared-r2/prepare.json`.
Only successful running verification returns `runtime_policy_verified: true`.
Shared runners use `--kernel-source` for the **build directory** and
`--kernel-baseline` for the captured bundle; their schema dispatch preserves the
unchanged legacy verifier for historical identities.

The stock recovery release `7.0.0-38-generic`, package `7.0.0-38.38`, retains
Build ID `338e542e384c46228f7a378babc0f9bb2b6a5997`. Its migration receipt and the
Linux 6.1 [legacy identity procedure](https://github.com/hailongeric/kdlock/blob/cd6f1061ea1b3686dd6d43a7a180ab1942ea4e57/docs/operations/VM.md#kernel-identity)
remain separate evidence. None substitutes for the new running identity,
recovery snapshot, returned-JIT or performance gates.

The enabled-MM image has Build ID `ac9ea2ec7f24be8b910547bdfdbfb071176677e6`.
Its two schema-2 bundles bind exactly the same source, build, installed files
and configuration, with distinct runtime modes. Both clean boots had taint 0
before probes. The first installer retained a failed initramfs filename guard;
the separate validation-only continuation passed actual module-path, signature
and byte checks without changing the original failure. Use
`verify.py --variant kdmm1-native --running` or `--variant kdmm1-kd --running`
only for the current mode, as described in the
[MM identity procedure](../../kernel_integration/linux70/IDENTITY.md#separate-enabled-mm-identities).
Do not recapture over either existing bundle or reuse normal-kernel validation
as enabled-MM evidence.

## Boot policy

The Linux 7.0 boots retain `nokaslr nopvspin console=tty1 console=ttyS0`.
The preemption selector reported `full (lazy)`, whereas the legacy measurements
used voluntary preemption. This upgrade does not establish equivalent kernel
configuration, instrumentation or timing qualification. The first custom boot
selected the ITS return thunk and reported no failed services, but had taint
8192 from unsigned modules before project loads. After signing repair, boot
`59172bf2-ccd2-49bd-bc1b-fea1d12056a7` verified the same custom Build ID, ITS
thunk and lazy preemption with taint 0, no recorded kernel errors and no failed
services. Preserve the failed first boot separately; a clean boot still does
not establish KD correctness or timing qualification.

Read the actual command line, selector and topology before new live work:

```sh
cat /proc/cmdline
cat /sys/kernel/debug/sched/preempt
cat /sys/devices/system/cpu/online
```

Installing custom artifacts did not update GRUB. After the clean boot, the
separately authorized boot procedure selected the normal custom-kernel entry
as the default, retaining stock Linux 7 and legacy Linux 6 recovery entries.
The current GRUB override SHA256 is
`dcfb2c3feacfe8eddfc4e8a57b315a42113d91d03861da0a2e9bba347a865c2a`;
the port's compact boot receipt binds its generated menu too. The captured
[legacy GRUB override](../../kernel_baseline/nopvspin-grub.cfg)
is provenance and must not be installed as the current boot configuration.
Kernel rebuilds, boot changes and restarts remain outside ordinary development
work unless the session authorizes them.

## Dependencies and checks

The system reports Python 3.14.4 and GCC 15.2.0. Use the translation virtual
environment listed above, with [pinned requirements](../../disassem/requirements.txt)
and the exact [Miasm Python 3.14 compatibility patch](../../disassem/compat/README.md).
The translator checks those dependency bytes before semantic analysis. Import
success alone is insufficient: the initial semantic checks failed and their
subsequent corrected checks have separate receipts. Earlier translation and
plotting environments remain historical; follow the
[plotting requirements](../../bench/archive/requirements.txt) when preparing new
analysis rather than borrowing an old dependency-pass label.

The kernel build retains Rust, BTF, frame-pointer unwinding and the stock
Canonical certificate paths. Its tools include GCC 15.2.0, Rust 1.93.1,
bindgen 0.72.1, Clang 21.1.8 and pahole 1.31. The initial missing `dwarf.h`
failure was resolved with `libdw-dev`; no required feature was disabled.

The [legacy build and dependency recipe](https://github.com/hailongeric/kdlock/blob/cd6f1061ea1b3686dd6d43a7a180ab1942ea4e57/docs/operations/VM.md#dependencies-and-checks)
retains the old KDIR and Python environment for historical reconstruction only.
The port record distinguishes source/fixture checks, compilation, installation,
boot and live validation. The normal kernel keeps the mmap overlay disabled;
the separate enabled image has its own Native/KD boot and correctness receipts.
Confirm
idle state and use basic plus directly affected checks. Full suites still require explicit selection; missing
dependencies, skipped checks and compilation failures are not passes.

The Linux 7 basic runner is functional-only. It requires the pinned interpreter
on PATH, a schema-2 running identity, a real recovery tag and explicit
`--host-reference`, `--host-reference-sha256` and fresh `--host-state` files.
Run [capture_host.py](../../bench/basic/capture_host.py) as root on the QEMU host
with the actual `--snapshot` tag to obtain those host captures. It verifies the
monitor snapshot listing, 64 matched vCPU pins, auxiliary threads on CPU 63,
NUMA memory bindings and all 64 fixed 2 GHz policies. The runner compares QEMU
process/task identities and placement with the selected reference; only the
documented extra CPU-63 worker case is admitted. An old host capture is not
automatically waived. Every successful family needs correct data, returned JIT
bodies and complete retirement; these checks produce no performance score.

The [post-MM normal-boot basic controller](../../bench/results/10.176.26.71/tests/linux70-normal-basic-20261028/README.md)
passed spin c01, public mutex c01, rwlock c01/20% writes and rwsem c16/100%
writes in one run, each with 1,600,000 correct operations, matched returned-JIT
counters and final idle. Treat those exact presets and frozen source as its
validation boundary. See the
[current functional workflow](../PROJECT_GUIDE.md#current-development-workflow)
for worker presets and remaining gates. No basic run supplies throughput
acceptance or enabled-MM correctness.

The separate OUTER-mutex and spin native-escape checks passed original-task,
effects, flags, terminal-ban and drain assertions across four phases each.
The hot phases returned through native escape rather than completing a JIT
body; their receipts keep those outcomes distinct. See the
[port evidence](../../bench/results/10.176.26.71/tests/linux70-port-20261027/README.md).
Final post-validation health recorded no project modules, kernel errors or
failed services. Taint remained 12288 from unsigned out-of-tree project modules;
the clean pre-live boot's taint 0 remains a separate checkpoint. No throughput
or broader MM support is inferred from these checks.

The clean Linux 7 checkpoint's host reference is preserved at
`bench/results/10.176.26.71/raw/tests/linux70-port-20261027/boot/host-functional-reference.json`,
SHA256 `3474d973eda9b7871624cd41a1fb1c37442bff07e2ce4481b0818570df60281a`.
It records 69 QEMU tasks, verified vCPU identities/pins, fixed 2 GHz policies
and auxiliary placement on CPU 63. That functional reference is distinct from
strict timing qualification. Supply its exact copied bytes and a fresh current
capture; do not silently reuse it after QEMU process/task identities change.

## Snapshots and recovery

Before live module/JIT work, confirm an actual recoverable snapshot through
`/tmp/qemu-monitor.sock` on the benchmark host. `savevm` must succeed and
`info snapshots` must list the tag. Only then set `KDLOCK_RECOVERY_CONFIRMED=1`
and the recorded `KDLOCK_SNAPSHOT_TAG`. Environment variables alone are not proof.
The normal-kernel clean snapshot is `linux70-kdlock1-clean-20261027`.
Its `savevm` returned successfully, and the monitor listed it on all disks at
`2026-10-27 14:12:19`, with 23.6 GiB of VM state. It captures the signed custom
kernel after the clean second boot, schema-2 identity capture and custom normal
GRUB default selection. The legacy snapshot remains separately retained.
This recovery boundary does not itself validate KD execution or performance.

The separate enabled-MM recovery tag is
`linux70-kdmm1-native-clean-20261027`. Its HMP save returned in 41.64 seconds,
then the monitor listed it on all disks at `2026-10-28 00:01:50`, with 23.6 GiB
of state. It captures the clean Native-mode boot
`a84cb9f5-bbab-457e-83ca-dcfc3bffed09`, before correctness probes. The campaign
tag retains October 27 even though creation occurred October 28. Creation and
listing were verified; no restore drill is claimed. Use the correct
mode/kernel snapshot and recheck the actual listing before any recovery.

The migration checkpoint retained `legacy-kdclobber2-20261027`. The user explicitly
approved deleting the 42 earlier snapshots and the temporary pre-cleanup
snapshot; the [migration record](../history/vm-ubuntu2604-migration-20261027.md)
records all 43 completed removals. The retained snapshot captures Ubuntu 22.04
and the former 32 GiB data disk. Restoring it also restores that disk size and
rolls back subsequent active contents, including the Ubuntu 26.04 migration.
The legacy snapshot does not capture the new platform. Use the verified current
boundary for Linux 7 work, and recheck the actual snapshot list, topology and
boot identity before any recovery. Do not infer that the legacy and current
snapshots have interchangeable OS, disk-size or source identities.

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
