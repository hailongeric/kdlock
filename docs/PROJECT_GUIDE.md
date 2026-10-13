# Project guide

KD lets a lock holder execute a waiting caller's critical section through JIT.
Spinlocks use KD's own four-byte object. Mutexes keep the original Linux mutex
and its real owner. Read-write locks use a 128-byte object: readers run locally,
while writers may delegate through the spin engine. Rwlock ABI3 acquires exclusive
write access before the translated body starts. Callers select these APIs
explicitly; loading the provider does not redirect global Linux lock calls.

For an introduction to the execution model and its terms, start with
[Design](DESIGN.md). The table below points to implementation and operations guides.

Current mutexes always support blocking after bounded polling and reject delegated
origin-CPU GS access. The [2026-10-12 verification](../bench/results/10.176.26.71/tests/mutex-blocking-only-20261012/validation.json)
checks sleeping waiters, physical-owner ACKs and actual JIT execution.
[Performance status](PERFORMANCE.md) summarizes the latest frozen measurements;
[the results index](../bench/results/README.md) owns historical reports and provenance.

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

The repository's default branch is named `master`. It holds the accepted
experimental baseline. Use short-lived branches for subsequent tasks; archive
finished or rejected experiments under `archive/<original-branch>` tags.
The [2026-10-12 branch inventory](git-branches-20261012.json) records original tips,
unique commits, rejection/revert evidence, completed local cleanup and the remote
publication plan.

The former `perf/hash-payload-20260927` branch grew into an integration branch for
spin/mutex optimization, rwlock ABI3, real APIs, NUMA changes, blocking-only mutexes
and their evidence. At review it was 91 commits ahead of the old `master`, which
had no unique commits. Local `master` was fast-forwarded without conflicts to
`fa48b7d89265befced26925ce7c0b73fd5a44f97`: the 91 accepted commits plus the branch
documentation commit. The former integration branch is complete as an experimental
checkpoint and closed locally. General performance parity and the limitations in
[TODO](TODO.md) remain unresolved.

| Archived experiment (names below use `perf/`) | Purpose and outcome |
| --- | --- |
| `mutex-empty-bucket-rejected-20261003` | Empty task-bucket shortcut; rejected and reverted |
| `mutex-fail-read-rejected-20261003` | Avoid unconditional fault-injection atomic reads; rejected and reverted |
| `mutex-hash-admission-20260928` | Ratio512 admission; rejected repeated regressions |
| `mutex-numa-candidate-20260928` | Original bounded NUMA scan/handoff candidate; performance rejected |
| `mutex-numa-rejected-20261003b` | Later NUMA grouping candidate; rejected and reverted |
| `mutex-pack-rejected-20261003b` | Metadata packing and prefetch/layout changes; rejected and reverted |
| `mutex-retry-rejected-20261003b` | Extra native acquisition retry after admission; rejected and reverted |
| `mutex-task-buckets-rejected-20261003` | Sharded task-registry locks; rejected and reverted |
| `mutex-task-cache-batch-candidate-20260928` | High-JIT cache plus batch/NUMA changes; rejected combined candidate |
| `mutex-task-cache-candidate-20260928` | Original task retention cache; correctness passed, performance rejected |

Six experiment tips are already in the accepted history followed by explicit
reverts. Four have seven separate commits in total; archive tags preserve them
without promoting the rejected implementations. Later accepted cache/NUMA work
is a separate implementation with its own measurements.

The nine pre-existing edits were committed as `09bfffe` on
`wip/worktree-20261012`. That checkout, including the outer acquisition cookie
and configurable 64-round post-work default, is the starting baseline for the
[2026-10-13 admission study](../bench/results/10.176.26.71/bench/mutex_admission/20261013/README.md).
Its implementation and evidence are integrated into local `master`; the task
tip is preserved as `archive/perf/mutex-admission-c01-20261013`. All threshold
candidates were rejected and default 256 remains. The user's original WIP
branch is retained unchanged at `09bfffe`. [Validation](VALIDATION.md) gives
the tested scope and remaining limits.

The subsequent [c01 cost study](../bench/results/10.176.26.71/bench/mutex_c01_cost/20261013/README.md)
retains exact per-CPU waiter counters and staged successor prefetch as a bounded
higher-thread improvement. It does not reach the through-28 Native target.
Its local task tip is archived as `archive/perf/mutex-c01-cost-20261013` after
fast-forward integration; failed variants and raw evidence remain separate.

The [optimistic-spin study](../bench/results/10.176.26.71/bench/mutex_optimistic/20261013/README.md)
rejects all six owner-aware retry/OSQ candidates. Its exact experimental tip
`260d330` is preserved as `archive/perf/mutex-optimistic-c01-20261013` without
merging the rejected provider. The report and retained workload drain check are
integrated separately, with their tip archived as
`archive/perf/mutex-optimistic-report-20261013`. The provider remains `9b76719`.

All twelve original tips are preserved by verified archive tags, including
`archive/master-before-integration-20261012`. The eleven local `perf/` branches
were removed. The remaining local branches are `master` and
`wip/worktree-20261012`; the original patch remains preserved with the inventory.

Remote publication remains pending; this operation did not push commits or tags,
or delete remote branches. Publish and verify the archive tags before
fast-forwarding `origin/master`, then remove the eleven old remote topic branches.
[Operations](AGENTS.md#git-and-rollback) defines the local Git workflow.
