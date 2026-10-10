# Project guide

KD spin uses an explicit four-byte lock; KD mutex retains the original Linux
mutex and its physical owner. KD rwlock uses a 128-byte object with concurrent
local readers and JIT writers over a KD spin gate. The three APIs use
caller-clobber entries and shared JIT execution; rwlock ABI3 acquires writer
admission before entering its translated body. Providers do not install global
interception hooks.

The spin/mutex optimization phase closed on 2026-10-09. Its
[final benchmark report](../bench/tclock_compare/results/20261008-protocol-simplification/README.md)
contains the completed comparison and remaining gaps. The subsequent
[RCUHT rwlock report](../bench/rwlock_compare/results/20261010-rcuht/README.md)
records 270 valid sessions at 1%/20% writes and strict parity at 21 of 30
configurations. Use [performance status](PERFORMANCE.md) for measured outcomes and
[benchmark history](../bench/tclock_compare/results/HISTORY.md) for older evidence.

## Reading order

| Need | Document |
| --- | --- |
| Understand all nine lock backends | [Lock protocols](design/lock_protocols.md) |
| Find the KD execution components | [Design](DESIGN.md), [code map](CODE_MAP.md) |
| Follow each lock's operations | [Spin](design/spin_implementation.md), [mutex](design/mutex_implementation.md), [rwlock](design/rwlock_implementation.md) |
| Change generated code or state layout | [Execution flow](JIT_EXECUTION.md), [register ABI](JIT_REGISTER_ABI.md) |
| Change ownership or recovery | [KD locking](design/locking.md), [frames](design/frames.md), [lifetimes](design/lifetimes.md) |
| Build and verify | [Provider](../kernel_module/README.md), [tests](../tests/README.md), [benchmarks](../bench/README.md) |
| Review status and limits | [Known limitations](TODO.md), [performance status](PERFORMANCE.md) |
| Evaluate simpler execution contracts | [Protocol simplification](design/protocol_simplification.md) |

## Guest workflow

The primary benchmark host is Ubuntu at `eric@10.176.26.71`, with source workspace
`/home/eric/vm/vm-shared/kdlock`. Guest SSH connects to
`root@10.176.26.71:2222` from another machine, or `root@127.0.0.1:2222` from
that host; the guest checkout remains `/root/host_fs/kdlock`.
The original Git checkout remains on `380G10`; the destination source mirror
contains the approved tracked files and their current edits.
Recovery uses a separate ext4 copy, so synchronize changed files by SHA256 while
idle. The optional `shared` mode shares source through 9p with mount tag
`hostshare`, without VFIO. Do not replace `/root/host_fs` or
modify frozen inputs. Full operational rules are in [AGENTS](AGENTS.md).

Run the host helpers from `/home/eric/vm/qemu-scripts`. `run_vm.sh` defaults to
`recovery` and also accepts `shared`, `status`, `monitor [COMMAND]` and graceful
`stop`. It starts 60 vCPUs across two 30-core sockets with 24 GiB of RAM:
guest node 0 CPUs 0–29 map to host CPUs 0–29, and guest node 1 CPUs 30–59 map
to host CPUs 32–61, with 12 GiB bound to each matching host memory node.
`pin_cpu.sh` runs automatically; host CPUs 30, 31, 62 and 63 are reserved for
QEMU services and the host. Use collector CPU 58 for cohorts of up to 56 workers.
The spin/mutex runner's existing maximum remains 36 workers.

`vm_ssh.sh` uses `/home/eric/.ssh/kdlock_vm_ed25519` to reach the guest locally.
The host also provides the `ssh kdlock-vm` alias. `sync_source.py` copies only
changed files from the reviewed hash manifest while the recovery guest is idle.
Refresh manifest entries after reviewed source edits. `bench.sh` creates and
verifies a fresh snapshot, runs the migration checks, and archives evidence on
the physical host; see [commands and validation](../bench/README.md#vm-migration-validation).
Host ports 2222, 9090 and 9091 retain their guest mappings; debugger port 1234
is available only on host loopback. The monitor and serial log remain
`/tmp/qemu-monitor.sock` and `/tmp/qemu-serial.log`.

Migration boot, exact kernel identity, source synchronization, CPU placement and
guest health were verified on 2026-10-10. The recorded 73-session validation is
separate from historical measurements on the original host.
The migration copy retains current disk contents without historical VM snapshots.
Original disks on `380G10` remain untouched for rollback. Saved VM state from the
old CPU/topology is not portable: create and verify a new destination snapshot
before live module/JIT tests, then check the kernel, boot policy and CPU placement.

### Kernel identity

Run in the guest:

```sh
cd /root/host_fs/kdlock
python3 bench/spin_cacheline/kernel_identity.py \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919
```

Expected release: `6.1.159-kdclobber2`; captured Build ID:
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. The verifier checks source,
config, build and live identity. Keep `nokaslr`, voluntary preemption and the
recorded CPU/NUMA placement. A mismatch requires investigation, not a kernel update.

### Native qspinlocks in the VM

The benchmark boot policy has required `nopvspin` since 2026-10-08. Linux then
uses native qspinlocks; PV lock stealing and PV waiter parking are disabled.
Kernel source, image and Build ID are unchanged. KD/TCLock keep their own
target-lock protocols. Verify this policy on the destination before new runs.

The installed override is `/etc/default/grub.d/99-kdlock-nopvspin.cfg`; its exact
contents are recorded in [nopvspin-grub.cfg](../kernel_baseline/nopvspin-grub.cfg).
It appends the argument and selects `6.1.159-kdclobber2` as the persistent GRUB
default. Its menu IDs contain this VM's root filesystem UUID.

Verify in the guest after boot or snapshot restoration:

```sh
grep -w nopvspin /proc/cmdline
dmesg | grep -F 'PV spinlocks disabled, forced by "nopvspin" parameter'
```

Run the kernel identity check above too: a matching Build ID alone does not
establish the boot policy. The 2026-10-08 activation check on `380G10` passed
with all 40 CPUs online, node0 CPUs0–19, node1 CPUs20–39, voluntary preemption,
unchanged host CPU pinning and the 2.5 GHz frequency policy. This is historical
evidence for the original host. Earlier snapshots can restore the old policy;
confirm a snapshot of the current boot before new live verification.

Backups and verification are in guest
`/root/kdlock-evidence/pvspin-nopvspin-20261008/`. Its adjacent `.tar.gz` archive
has SHA256 `287447eabe43596b7494f5caa9d0c2fa39cf58ed918d703d66570ffc2cc37418`.
To roll back while idle, remove the override, run `update-grub`, select the intended
kernel and reboot. This also restores the prior GRUB default.

The [protocol simplification trials](../bench/tclock_compare/results/20261008-protocol-simplification/README.md)
use `nopvspin`. Both combined translator/memory and memory-only candidates were
rejected after repeated regressions; no runtime change was promoted. Their full
matrices remain separate from the fresh 540-session comparison of the restored
runtime at all 15 thread counts. The earlier
[hash diagnosis](../bench/tclock_compare/results/HISTORY.md#hash-diagnosis)
uses the same boot policy but covers selected counts and placements. The
[previous 540-sample comparison](../bench/tclock_compare/results/HISTORY.md#pre-nopvspin-matrix)
predates activation. Keep samples from the two boot policies separate.

### Dependencies and idle state

Use guest CPython 3.10 and the [pinned requirements](../disassem/requirements.txt).
An existing environment is available outside the checkout:

```sh
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH
export LC_ALL=C
python3 -m pip check
python3 - <<'CHECK'
import sys
sys.path.insert(0, 'bench/spin_cacheline')
import bench_runtime
bench_runtime.idle()
CHECK
```

For a new environment, create a venv outside the repository and install the
pinned requirements there. GCC, make, binutils and Python development headers
are required. Do not upgrade system Python or global packages.

### Build and check

```sh
make -C kernel_module KDIR=/root/linux-6.1.159-kdclobber2 W=1 UBSAN_SANITIZE=n
make -C daemon CFLAGS='-O2 -Wall -Wextra -Werror'
make -C tests/unit run
```

The default unit target runs two basic C programs. Add only directly affected
Python drivers through `PY_TESTS`; see [test selection](../tests/README.md#unit-checks).
The benchmark runner builds isolated modules and defaults its KD provider to
UBSAN off. Standalone builds inherit kernel policy unless explicitly overridden.

Before any live module/JIT run, confirm a real recovery snapshot through the
monitor and use an outer timeout. [Tests](../tests/README.md) documents the
module lifecycle check; [the spin/mutex runner](../bench/tclock_compare/README.md)
documents performance and plain/nested/early JIT checks. Use the separate
[rwlock correctness guide](../tests/kernel/rwlock/README.md) for overlap/exclusion
checks and [rwlock runner](../bench/rwlock_compare/README.md) for mixed RCUHT
performance and writer JIT acceptance.

### Drain and evidence

Stop new calls, join workers and translators, then retire sources. After success,
unload workloads before providers. EBUSY retains pins; do not force unload.
Keep frozen source/ELF hashes, kernel identity, business results, returned-body
counts and drain. NORMAL only proves publication. Historical results and failed
candidates remain in [the evidence index](VALIDATION.md), separately from fresh checks.
