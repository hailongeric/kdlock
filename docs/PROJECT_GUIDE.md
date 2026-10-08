# Project guide

KD spin uses an explicit four-byte lock; KD mutex retains the original Linux
mutex and its physical owner. Both use caller-clobber entries and shared JIT
execution. Providers do not install global interception hooks.

## Reading order

| Need | Document |
| --- | --- |
| Understand all six locks | [Lock protocols](design/lock_protocols.md) |
| Find the KD execution components | [Design](DESIGN.md), [code map](CODE_MAP.md) |
| Follow spin or mutex operations | [Spin implementation](design/spin_implementation.md), [mutex implementation](design/mutex_implementation.md) |
| Change generated code or state layout | [Execution flow](JIT_EXECUTION.md), [register ABI](JIT_REGISTER_ABI.md) |
| Change ownership or recovery | [KD locking](design/locking.md), [frames](design/frames.md), [lifetimes](design/lifetimes.md) |
| Build and verify | [Provider](../kernel_module/README.md), [tests](../tests/README.md), [benchmarks](../bench/README.md) |
| Review limits and remaining work | [TODO](TODO.md), [performance plan](PERFORMANCE_PLAN.md) |

## Guest workflow

The host checkout is `/home/eric/vm/vm-shared/kdlock`. SSH connects to
`root@127.0.0.1:2222`; the guest checkout is `/root/host_fs/kdlock`.
Recovery uses a separate ext4 copy, so synchronize changed files by SHA256 while
idle. Normal mode shares source through 9p. Do not replace `/root/host_fs` or
modify frozen inputs. Full operational rules are in [AGENTS](AGENTS.md).

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

Since 2026-10-08, the guest boots with `nopvspin`. Linux uses native qspinlocks;
PV lock stealing and PV waiter parking are disabled. Kernel source, image and
Build ID are unchanged. KD/TCLock keep their own target-lock protocols.

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
establish the boot policy. The activation check passed with all 40 CPUs online,
node0 CPUs0–19, node1 CPUs20–39, voluntary preemption, unchanged host CPU pinning
and the 2.5 GHz frequency policy. Earlier snapshots can restore the old policy;
confirm a snapshot of the current boot before new live verification.

Backups and verification are in guest
`/root/kdlock-evidence/pvspin-nopvspin-20261008/`. Its adjacent `.tar.gz` archive
has SHA256 `287447eabe43596b7494f5caa9d0c2fa39cf58ed918d703d66570ffc2cc37418`.
To roll back while idle, remove the override, run `update-grub`, select the intended
kernel and reboot. This also restores the prior GRUB default.

The [540-sample comparison](../bench/tclock_compare/results/20261008-threeway-spin-mutex.md)
finished before activation. The subsequent
[hash diagnosis](../bench/tclock_compare/results/20261008-hash-diagnosis.md)
has 90 unprofiled and 72 separate diagnostic samples under `nopvspin`, covering
selected thread counts and placement controls. It does not replace the full
15-point matrix. Keep the two boot policies separate.

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
module lifecycle check; [the direct runner](../bench/tclock_compare/README.md)
documents performance and plain/nested/early JIT checks.

### Drain and evidence

Stop new calls, join workers and translators, then retire sources. After success,
unload workloads before providers. EBUSY retains pins; do not force unload.
Keep frozen source/ELF hashes, kernel identity, business results, returned-body
counts and drain. NORMAL only proves publication. Historical results and failed
candidates remain in [the evidence index](VALIDATION.md), separately from fresh checks.
