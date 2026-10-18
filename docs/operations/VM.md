# VM operations

All builds, unit tests, live modules, daemons and benchmarks run in the recovery
VM on `10.176.26.71`. The source host performs edits, Git, static inspection and
read-only offline evidence checks. See [development rules](../../AGENTS.md).

## Environment

| Purpose | Location |
| --- | --- |
| Source checkout on `380G10` | `/home/eric/vm/vm-shared/kdlock`, branch `master` |
| Benchmark host | `eric@10.176.26.71` |
| Host source mirror | `/home/eric/vm/vm-shared/kdlock` on the benchmark host |
| Guest source | `/root/host_fs/kdlock` |
| VM scripts | Host `/home/eric/vm/qemu-scripts` |
| Guest connection | `root@10.176.26.71:2222`, or host `./vm_ssh.sh` / `ssh kdlock-vm` |
| Kernel source/build | `/root/linux-6.1.159-kdclobber2` |
| Captured kernel bundle | `/root/kdlock-kernel-baselines/mutex-clobber2-20260919` |
| Pinned Python environment | `/root/kdlock-evidence/clobber-20260918/venv` |
| Guest data disk | `/mnt/kdlock-builds`; use for frozen build copies when root space is low |
| Live evidence | `/root/kdlock-evidence/10.176.26.71/{bench,tests}/<new-run>` |

The recovery VM has exactly 64 vCPUs and 24 GiB RAM. Node 0 uses CPUs 0–31
and 12 GiB; node 1 uses CPUs 32–63 and 12 GiB. Each vCPU is pinned to the same
host CPU, with memory on the corresponding host NUMA node. QEMU service threads
share host CPU 63. Verify actual placement and host frequency policy before timing.

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

## Kernel identity

Run in the guest:

```sh
cd /root/host_fs/kdlock
python3 bench/spin_cacheline/kernel_identity.py \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919
```

Expected release: `6.1.159-kdclobber2`. Expected Build ID:
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. The verifier checks captured source,
configuration, build files and live identity. A mismatch requires investigation,
not an automatic kernel update. Spin requires spin-clobber-v1; KD mutex uses its
own object and clobber entry rather than the kernel mutex-clobber API.

## Boot policy

Verify `nokaslr`, `nopvspin`, voluntary preemption, frame pointers, unchanged
mitigations and actual CPU/NUMA placement. In the guest:

```sh
cat /proc/cmdline
dmesg | rg -F 'PV spinlocks disabled, forced by "nopvspin" parameter'
cat /sys/devices/system/cpu/online
cat /sys/kernel/debug/sched/preempt
```

The captured [GRUB override](../../kernel_baseline/nopvspin-grub.cfg) records the
installed policy. Matching Build ID does not prove boot arguments: a snapshot
can restore older policy. Kernel rebuilds, boot changes and restarts are outside
ordinary development work.

## Dependencies and checks

Confirm no benchmark, daemon, project module or in-flight request before sync or
build. Use the pinned environment and [requirements](../../disassem/requirements.txt):

```sh
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH
export LC_ALL=C
python3 -m pip check
make -C kernel_module KDIR=/root/linux-6.1.159-kdclobber2 W=1 UBSAN_SANITIZE=n
make -C daemon CFLAGS='-O2 -Wall -Wextra -Werror'
make -C tests/unit run
```

The default unit target runs two basic C programs. Add directly affected Python
drivers through `PY_TESTS`; full suites require explicit selection. Missing
dependencies and skipped checks are not passes. Benchmark builds use private
provider copies with UBSAN off by default; ordinary builds inherit kernel policy.

## Snapshots and recovery

Before live module/JIT work, confirm an actual recoverable snapshot through
`/tmp/qemu-monitor.sock` on the benchmark host. `savevm` must succeed and
`info snapshots` must list the tag. Only then set `KDLOCK_RECOVERY_CONFIRMED=1`
and the recorded `KDLOCK_SNAPSHOT_TAG`. Environment variables alone are not proof.
The accepted round used `before-mutex-kdonly-20261017T140354Z`; recheck availability
and current boot identity before relying on it.

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
loads or either bounded string service (`strcmp` or `strscpy_pad`) transitions to
immutable images for that and every later generation. Earlier frames keep their
original descriptor and code. This does not permit
editing frozen inputs or replacing source while work is active. Owners, ACKs,
source leases and generated images have distinct [lifetimes](../design/lifetimes.md#executable-images-and-guarded-spin-transition).

The provider currently advertises capability version 9. Runners must check the
specific feature bit they require, including the separate writing-service bit;
provider version alone does not prove that an image can use a feature. See the
[service admission contracts](../design/admission.md#bounded-original-strcmp-service).

Save commands, exit statuses, source/ELF hashes, kernel identity, topology,
business results, every worker's progress, returned JIT counts and final drain.
NORMAL means publication, not execution. Preserve failures and interrupted runs;
do not pool different frozen inputs. Published reports belong in
`bench/results/<machine>/{bench,tests}/`; raw archives belong in ignored
`bench/results/<machine>/raw/`. See [result storage](../../bench/results/README.md).
