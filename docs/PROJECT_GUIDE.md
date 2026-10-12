# Project guide

KD lets a lock holder execute a waiting caller's critical section through JIT.
Spinlocks use KD's own four-byte object. Mutexes keep the original Linux mutex
and its real owner. Read-write locks use a 128-byte object: readers run locally,
while writers may delegate through the spin engine. Rwlock ABI3 acquires exclusive
write access before the translated body starts. Callers select these APIs
explicitly; loading the provider does not redirect global Linux lock calls.

For an introduction to the execution model and its terms, start with
[Design](DESIGN.md). The table below points to implementation and operations guides.

The latest [full 1–64-worker report](../bench/results/10.176.26.71/bench/mutex_wait/20261012-full/README.md)
compares Native, TCLock and both KD mutex policies across all 31 selected
configurations: 8,910 drained sessions, 8,908 accepted and two retained zero-JIT
spin controls. It includes c01/hash, larger payloads and real APIs at 1–8 in
steps of one and 12–64 in steps of four. The report separates JIT evidence,
CPU cost and low-thread gaps from high-contention gains. Its temporary 66-vCPU
boot was restored to the regular 64-vCPU layout after archiving.

The earlier [mutex waiting-policy report](../bench/results/10.176.26.71/bench/mutex_wait/20261012/README.md)
compares KD's former spin mode and retained blocking implementation, scheduler/JIT
validation, and their Native/TCLock comparison across kernel payloads and real
APIs on the regular 64-vCPU VM. It uses six worker counts up to 60, with a
separate collector. Current KD mutexes always support blocking and retain the
original Linux owner; the wait-mode selector has been removed.

The earlier [complete performance report](../bench/results/10.176.26.71/bench/comparison/full-matrix-20261011T025525Z/overview.md)
compares rwlock, spin and mutex on the new host at 22 worker counts: 1–8 in
steps of one and 12–64 in steps of four. One-cacheline and hash payloads have
three rounds under each backend, for 1,584 timed sessions with tables, charts
and exported statistics; c02, c04, c08 and c16 are excluded. Its temporary
66-vCPU layout records physical collector contention at 64 workers.
The subsequent [mutex optimization report](../bench/results/10.176.26.71/bench/comparison/mutex-opt-20261011T045425Z/README.md)
isolates task caching, polling layout, field-width retirement reads and bounded
NUMA selection, with a fresh mutex c01/hash comparison at the same worker counts.
It preserves rejected candidates and identifies remaining Native/TCLock gaps.
The [earlier full baseline](../bench/results/10.176.26.71/bench/comparison/full-matrix-20261010T094831Z/README.md)
retains the wider payload matrix before the NUMA/mutex fixes.

On the original 40-vCPU host, the [spin/mutex phase](../bench/results/380G10/bench/tclock_compare/20261008-protocol-simplification/README.md)
ended on 2026-10-09 with performance gaps remaining. The later
[RCUHT rwlock comparison](../bench/results/380G10/bench/rwlock_compare/20261010-rcuht/README.md)
completed 270 valid runs at 1%/20% writes. KD matched both alternatives on both
throughput measures at 21 of the 30 combinations of write percentage and thread
count. [Benchmark history](../bench/results/380G10/bench/tclock_compare/HISTORY.md) links older evidence.

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
| Compare real syscall critical sections | [Complete rerun and analysis](../bench/results/10.176.26.71/bench/mutex_wait/20261012-full/README.md), [runner and contract](../bench/real_api/README.md) |
| Evaluate simpler execution contracts | [Protocol simplification](design/protocol_simplification.md) |

## Guest workflow

Keep source edits and Git work on the current host `380G10` in
`/home/eric/vm/vm-shared/kdlock`. All subsequent builds, tests and benchmarks run
inside the VM on Ubuntu host `eric@10.176.26.71`. Guest SSH connects to
`root@10.176.26.71:2222` from another machine, or `root@127.0.0.1:2222` from
that host; the guest checkout remains `/root/host_fs/kdlock`.
The destination has a source mirror at `/home/eric/vm/vm-shared/kdlock`;
it receives current tracked files and edits from the original Git checkout.
Synchronize from the current host before testing:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 tools/vm/sync_to_vm.py --dry-run
python3 tools/vm/sync_to_vm.py
ssh -p 2222 root@10.176.26.71
```

The helper snapshots tracked bytes, verifies hashes and updates only changed
files while the guest is idle. Git metadata and ignored raw evidence stay on the
source host. See [sync options](../tools/vm/README.md) for newly added or removed
files and troubleshooting.
Recovery uses a separate ext4 copy, so synchronize changed files by SHA256 while
idle. The optional `shared` mode shares source through 9p with mount tag
`hostshare`, without VFIO. Do not replace `/root/host_fs` or
modify frozen inputs. Full operational rules are in [AGENTS](AGENTS.md).

Run the host helpers from `/home/eric/vm/qemu-scripts`. `run_vm.sh` defaults to
`recovery` and also accepts `shared`, `status`, `monitor [COMMAND]` and graceful
`stop`. It starts 64 vCPUs across two 32-core sockets with 24 GiB of RAM:
guest node 0 CPUs 0–31 map to host CPUs 0–31, and guest node 1 CPUs 32–63 map
to host CPUs 32–63, with 12 GiB bound to each matching host memory node.
`pin_cpu.sh` verifies one-to-one pinning automatically. QEMU service threads share
host CPU 63 with guest CPU 63. Use collector CPU 63 and exclude it from workers.
Both comparison runners accept up to 64 workers. The [complete 22-point matrix](../tools/vm/README.md#complete-164-worker-comparison)
uses a temporary 66-vCPU boot for 64 workers and a separate guest collector;
at 64 workers they share the last physical host core. Archive that topology's
evidence before restoring the regular boot, and keep its snapshots separate.

`vm_ssh.sh` uses `/home/eric/.ssh/kdlock_vm_ed25519` to reach the guest locally.
The host also provides the `ssh kdlock-vm` alias. The source-host synchronization
command updates the mirror, manifest and idle guest in sequence. `bench.sh` creates and
verifies a fresh snapshot, runs the migration checks, and archives evidence on
the physical host; see [commands and validation](../bench/README.md#vm-migration-validation).
Host ports 2222, 9090 and 9091 retain their guest mappings; debugger port 1234
is available only on host loopback. The monitor and serial log remain
`/tmp/qemu-monitor.sock` and `/tmp/qemu-serial.log`.

The 64-vCPU boot, exact kernel identity, CPU placement and guest health were
verified on 2026-10-10, followed by the
[144-session performance comparison](../bench/results/10.176.26.71/bench/comparison/performance-20261010T081816Z/README.md)
at the current topology. The recorded 73-session migration validation used the
earlier 60-vCPU layout; it remains separate from the current topology and
historical 40-vCPU measurements on the original host.
The migration copy retains current disk contents without historical VM snapshots.
Original disks on `380G10` remain untouched for rollback. Saved VM state from the
old CPU/topology is not portable: create and verify a new destination snapshot
before live module/JIT tests, then check the kernel, boot policy and CPU placement.
Do not load a saved state captured under the old 40- or 60-vCPU layout into this
64-vCPU VM.

### Results by machine

Published reports live in `bench/results/<machine>/{bench,tests}/`; raw archives copied
to either physical host live in ignored `bench/results/<machine>/raw/{bench,tests}/`.
Use `380G10` for original-host runs and `10.176.26.71` for destination-host runs.
Inside the VM, write live output outside the checkout to
`/root/kdlock-evidence/10.176.26.71/{bench,tests}/<run>`; runners protect frozen
inputs by rejecting output beneath the checkout. Archive each run to the matching
machine directory before snapshot restoration. The [results index](../bench/results/README.md)
records relocated history and compatibility paths. Keep each run's CPU topology,
boot policy and frozen source identity with its evidence.

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

The [protocol simplification trials](../bench/results/380G10/bench/tclock_compare/20261008-protocol-simplification/README.md)
use `nopvspin`. Both combined translator/memory and memory-only candidates were
rejected after repeated regressions; no runtime change was promoted. Their full
matrices remain separate from the fresh 540-session comparison of the restored
runtime at all 15 thread counts. The earlier
[hash diagnosis](../bench/results/380G10/bench/tclock_compare/HISTORY.md#hash-diagnosis)
uses the same boot policy but covers selected counts and placements. The
[previous 540-sample comparison](../bench/results/380G10/bench/tclock_compare/HISTORY.md#pre-nopvspin-matrix)
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

Stop new calls and wait for workers and translators to finish. Then retire sources
so the provider can invalidate entries and release module pins. Once retirement
succeeds, unload workloads before providers. If it returns EBUSY, keep the modules
loaded and diagnose the remaining users; do not force unload.

Save source and ELF hashes, kernel identity, data checks, returned JIT body counts
and shutdown results. NORMAL means an image was published, not that it ran.
[The evidence index](VALIDATION.md) keeps older results and failed candidates
separate from new validation.
