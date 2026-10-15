# Project guide

KD lets a lock holder execute a waiting caller's critical section through JIT.
Spinlocks use KD's own four-byte object. The experimental owned mutex uses a
32-byte `struct kd_mutex` with its own owner, OSQ and tagged waiter list; it
never passes that object to Linux mutex operations. The retained legacy mutex
backend keeps the original Linux object and its real owner. Read-write locks use a 128-byte object: readers run locally,
while writers may delegate through the spin engine. Rwlock ABI3 acquires exclusive
write access before the translated body starts. Callers select these APIs
explicitly; loading the provider does not redirect global Linux lock calls.

For an introduction to the execution model and its terms, start with
[Design](DESIGN.md). The table below points to implementation and operations guides.

Mutex delegation-result waits use bounded polling then sleep on reserved stacks;
owned SELF acquisition separately uses Linux-style optimistic spinning and
sleeping. Legacy mutexes refuse delegated origin-CPU GS access; owned mutexes
can opt into the audited bounded subset with an exclusive spinning claim. The
[validation index](VALIDATION.md#current-owned-protocol-verification) separates
current-source protocol/JIT/FULL/ACK checks from older receipts and performance runs.
[Performance status](PERFORMANCE.md) summarizes the latest frozen measurements;
[the results index](../bench/results/README.md) owns historical reports and provenance.

The owned ABI4/reuse-32 profile is accepted for c01/post64 at 1–8 workers on the
regular boot. The later 22-count, 1–64-worker comparison uses the same implementation
on a temporary 66-vCPU boot; its three-worker peak misses the 97% Native gate.
The [current flowcharts](design/mutex_implementation.md#owned-abi4-acquisition-and-release-flow)
show the protocol, and the [owned benchmark command](../bench/tclock_compare/README.md#owned-c01-full-grid)
selects the measured profile explicitly. The runner's legacy default and the
owned caller's ABI2/reuse-0 defaults remain unchanged.

## Reading order

| Need | Document |
| --- | --- |
| Understand the lock backends | [Lock protocols](design/lock_protocols.md) |
| Find the KD execution components | [Design](DESIGN.md), [code map](CODE_MAP.md) |
| Follow each lock's operations | [Spin](design/spin_implementation.md), [mutex](design/mutex_implementation.md), [rwlock](design/rwlock_implementation.md) |
| Change generated code or state layout | [Execution flow](JIT_EXECUTION.md), [register ABI](JIT_REGISTER_ABI.md) |
| Change ownership or recovery | [KD locking](design/locking.md), [frames](design/frames.md), [lifetimes](design/lifetimes.md) |
| Build and verify | [Provider](../kernel_module/README.md), [tests](../tests/README.md), [benchmarks](../bench/README.md) |
| Review status and limits | [Known limitations](TODO.md), [performance status](PERFORMANCE.md) |
| Understand benchmark labels and protected work | [Workloads and critical sections](BENCHMARK_WORKLOADS.md) |
| Compare real syscall critical sections | [Runner and contract](../bench/real_api/README.md), [API reports](../bench/results/10.176.26.71/README.md#frozen-benchmark-reports) |

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
The [full-grid closeout](../bench/results/10.176.26.71/bench/mutex_owned/20261014-full-grid/README.md#verification-and-closeout)
records the 2026-10-14 restoration, kernel/boot-policy and idle checks, and confirmed
`normal64-after-mutex-owned-full-20261014` snapshot. Reverify the live state and
snapshot before any new run; the receipt is a historical observation.

`vm_ssh.sh` uses `/home/eric/.ssh/kdlock_vm_ed25519` to reach the guest locally.
The host also provides the `ssh kdlock-vm` alias. The source-host synchronization
command updates the mirror, manifest and idle guest in sequence. `bench.sh` creates and
verifies a fresh snapshot, runs the migration checks, and archives evidence on
the physical host; see [commands and validation](../bench/README.md#vm-migration-validation).
Host ports 2222, 9090 and 9091 retain their guest mappings; debugger port 1234
is available only on host loopback. The monitor and serial log remain
`/tmp/qemu-monitor.sock` and `/tmp/qemu-serial.log`.

The [blocking-mutex validation](../bench/results/10.176.26.71/tests/mutex-blocking-only-20261012/validation.json)
verified the captured kernel, native qspinlocks, all 64 CPU pins and a fresh
recovery snapshot on 2026-10-12. Recheck those properties before live runs.
Snapshots belong to their exact CPU topology; archive evidence before restoration.

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
establish the boot policy. Earlier snapshots can restore an earlier policy.
If the boot printk has rotated out, the maintained benchmark preflight verifies
native lock/unlock pointers through `/proc/kcore` using the captured vmlinux.
The [kernel baseline](../kernel_baseline/README.md) and
[validation index](VALIDATION.md) retain the original boot-policy evidence.

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

## Git branches

`master` holds accepted work. The owned local-acquisition extension is
`585335b`, with an explicit ABI4/reuse-32 profile accepted under the
[c01/post64 1–8-worker scope](PERFORMANCE.md#active-c01-18-worker-study).
Its measured source snapshots remain independent of the later report/index edits.
The unchanged implementation's full-grid report is committed at `5d09eef`,
archived exactly as `archive/perf/mutex-c01-full-grid-20261014`, and integrated
into local `master`. Its completed local topic branch is closed.
The rejected native-first provider is a separate historical experiment.

Use short-lived task branches. Archive finished or rejected tips under
`archive/<original-branch>` tags and verify the exact object before deleting a
branch. Never merge a rejected implementation merely to close its branch.
The native-first implementation is preserved at `9a5305e`, tag
`archive/perf/mutex-native-first-20261014`; its
[report](../bench/results/10.176.26.71/bench/mutex_owned/20261014-native-first/README.md)
was integrated separately. [The machine index](../bench/results/10.176.26.71/README.md)
records earlier study dispositions without duplicating their narratives here.

The [2026-10-15 inventory](git-branches-20261015.json) records refs and retained
worktrees during this documentation refresh, after full-grid integration. It
predates the documentation commit and includes its temporary task branch.
The [2026-10-14 inventory](git-branches-20261014.json) preserves the prior cleanup.
Accepted topic tip `c768c23` was fast-forwarded into `master`, preserved as
`archive/perf/mutex-linux-local-c01-20261014`, then its local branch was closed.
Earlier cleanup also preserves the following tips:
merged WIP `09bfffe` is preserved exactly by
`archive/wip/worktree-20261012` and its local branch is closed. The cached remote
protocol tip `475e1d6` has a separate exact-tip archive tag; no remote refs changed.
The [2026-10-12 inventory](git-branches-20261012.json) retains earlier dispositions. Detached worktrees may contain dirty frozen experiment inputs. Their
canonical source evidence must be preserved before removing a checkout.

Remote-tracking refs are cached observations. Publishing tags, advancing remote
`master` and deleting remote branches are separate operations; verify actual
remote tips and archive targets first. Local cleanup does not publish anything
or synchronize the guest. [Operations](AGENTS.md#git-and-rollback) defines the
Git and recovery workflow.
