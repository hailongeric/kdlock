# Development and operations

These rules cover the x86_64 KD spin/mutex provider. Start with the
[project guide](PROJECT_GUIDE.md); use [tests](../tests/README.md) and
[benchmarks](../bench/README.md) for commands and evidence.

## Development rules

1. Read the source and `git status --short` before editing. Preserve unrelated
   changes; do not reset unknown files. Maintained prose and comments use English.
2. Explain the purpose and ordering constraints of protocol changes. Keep common
   supported paths working and select basic plus directly affected checks.
   Full suites require an explicit request. Rare resource, cancellation and alias
   combinations are optional coverage, not automatic delivery gates.
3. Preserve exact physical ownership, source leases, acquisition references,
   final ACKs and frame retirement. Approximate profiling counters cannot replace
   these controls. Do not relax admission or remove probes to manufacture a pass.
4. Reuse a request's shared packet/frame through pointers and ownership transfer.
   Prefer preallocation. Do not copy whole packets, clear whole records or add a
   global lock merely to simplify lifetime management. Initial capture, final
   restoration and independently live owner state remain necessary.
5. Keep the two-word wrapper input ABI. Userspace/futex, other architectures and
   general oversubscription redesign are outside this phase. Published KD waiters
   remain pinned and poll; native mutex owners/services may sleep.
6. Ordinary KD spin pairs preemption protection and preserves IRQ/BH state.
   IRQ/irqsave/BH variants use their explicit native interfaces.
7. Do not modify, build or install the guest kernel by default. The separately
   authorized static/spin-clobber/mutex-clobber experiments keep independent
   source trees, releases and captured baselines. Current code requires both
   clobber-v1 interfaces; old kernels are only for matching historical checkouts.
8. Access-time guards and pre-instruction native exits, general instruction/flags
   repair and immutable JIT versions remain explicitly deferred. Cleanup does
   not reopen them. Known supported-path failures remain documented in [TODO](TODO.md).
9. Keep kernel payload demos under `workload_modules/`, runners under `bench/`
   or `tests/`, and provider probes under `tests/kernel/`. Private `.inc` files
   belong to their translation unit and must be included in frozen inputs.
10. Maintain one document per responsibility. Root README contains introduction
    and navigation; test/benchmark commands and results belong in their guides.
    Replace stale narrative with a fixed Git evidence link rather than repeating it.

## Git and rollback

The user authorized ongoing local Git management on 2026-09-22. Commit useful
or substantial independently validated changes with matching documentation;
no per-commit confirmation is needed. Check the staged diff and include only
reviewed task files. Report the commit and validation limits.

Keep experiments independently reversible. Mark an unverified checkpoint as
such; do not claim a gain without measurement. Preserve failed candidates and
raw samples in their evidence archives. Roll back committed work with `git revert`
or a reviewed path-specific restore followed by a new commit, never a whole-tree
reset. Git rollback does not synchronize the guest or drain loaded modules.

## Environment

| Action | Location |
| --- | --- |
| Source edits, static checks, Git, archives and VM control | Host: `/home/eric/vm/vm-shared/kdlock` |
| Compilation, unit tests, modules, daemon and benchmarks | Guest: `/root/host_fs/kdlock` |
| SSH | `root@127.0.0.1:2222` |
| Current kernel source/build | `/root/linux-6.1.159-kdclobber2` |
| Captured kernel bundle | `/root/kdlock-kernel-baselines/mutex-clobber2-20260919` |
| QEMU launcher | Host: `/home/eric/vm/qemu-scripts/run_vm.sh` |

Do not build or execute tests on the host. Read-only offline archive checks are
allowed there. Recovery mode uses an ext4 copy; normal mode uses shared 9p.
While idle, compare SHA256 and copy only changed files, creating subdirectories
as needed. Delete only identified obsolete project files. Never move, recursively
replace or clear `/root/host_fs`, and do not edit frozen running inputs.

Verify the captured source, config, build files and live Build ID with
[the guide](PROJECT_GUIDE.md#kernel-identity); `uname -r` alone is insufficient.
Keep `nokaslr`, voluntary preemption, frame pointers and mitigations unchanged.
The current VM boots with `nopvspin` and uses native qspinlocks. Verify the
argument and boot confirmation independently of Build ID; snapshot restoration
can restore the earlier policy. Follow [the boot policy](PROJECT_GUIDE.md#native-qspinlocks-in-the-vm)
before live runs and keep benchmark samples from different policies separate.
Check actual CPU/NUMA placement. Host vCPUs were pinned to CPUs 0..39, with the
first 20 on NUMA node 0; recheck that mapping after a restart.

The 2026-09-21 cleanup removed only rebuildable intermediates from old kernel
builds. Their source, config, boot images and recovery baselines remain preserved;
see the [fixed maintenance record](https://github.com/hailongeric/kdlock/blob/e533214/docs/PROJECT_GUIDE.md).

## Verification and drain

1. Check host Git and guest health. Confirm no benchmark, daemon, old project
   module or in-flight request before synchronizing source.
2. Use the pinned guest Python environment and [requirements](../disassem/requirements.txt).
   Put its `bin` first in PATH; do not upgrade global packages.
3. Run basic plus affected checks. Performance runners may be used directly:
   standalone SELFTEST, functional runs and a full matrix are not prerequisites.
   Missing dependencies, skipped checks and compile failures are not passes.
4. Before live module/JIT tests, confirm an actual recoverable snapshot through
   the QEMU monitor, then set `KDLOCK_RECOVERY_CONFIRMED=1`. The variable itself
   does not prove a snapshot exists. Mutex JIT is always enabled; the provider
   has no `mutex_jit` parameter. Resource probes that execute no JIT bodies do
   not replace actual JIT acceptance.
5. Give SSH and test commands an outer timeout. A timeout or signal does not
   prove a blocked ioctl or worker drained. Save failure evidence and stop.
6. Check business results, returned-body JIT evidence where required, kernel
   errors, every worker's progress and final ownership/frame/queue drain.

### Acceptance and cleanup

NORMAL publication is not execution. Separate actual JIT, NO_JIT/native controls,
refusals, synthetic fixtures and kernel protocol probes in reports. Record commands,
source/ELF hashes, environment, exit status, kernel identity and drain. Historical
passes never count as a fresh run or a whole-project pass.

Stop new calls, wait for workers and translators, then retire sources. On EBUSY,
retain pins and diagnose; never force unload or reopen admission. After successful
retirement unload workloads before providers. Replace a workload/provider/JIT
session together: RIP-keyed artifacts have no immutable code generation.
Source pins, device references, physical owners, ACKs and frame retirement are
separate lifetimes. Node reuse or waiter wakeup does not retire a frame.

Stop a running experiment through its existing case-boundary mechanism before
changing inputs. Retain partial results; do not combine different frozen versions
into a purported complete matrix. Offline archive consistency does not prove
fresh execution or authentic source provenance.

## VM recovery

Check the actual host process view and a bounded SSH connection before restarting.
If SSH fails or times out, save `/tmp/qemu-serial.log`, stop the confirmed old VM,
and verify it has exited before launching another instance. Do not restart a
healthy guest because monitor access failed or a test has not produced output.

Run `./run_vm.sh recovery` from `/home/eric/vm/qemu-scripts`. Recovery supports
snapshots; normal/VirtFS/VFIO mode must not be assumed to. The monitor socket is
`/tmp/qemu-monitor.sock`. Confirm `savevm` succeeded and `info snapshots` lists
the chosen tag. Disconnect the monitor client without sending `quit`.
Root-owned sockets may require sudo; bound `nc` with a timeout at the same
privilege. Close only clients created by this operation, not unknown user sessions.
Archive evidence before `loadvm`; guest `/tmp` may be lost. Recheck module and
source state after recovery and start with the affected low-risk checks.

## Performance reporting

Compare current KD, TCLock and Linux Native, using three rounds per configuration.
Report the highest valid warmed peak plus min/median/max/spread and whole-run
throughput. Keep all valid and failed samples; do not pool different workloads,
ABIs, call shells or instrumentation settings. Functional runs explicitly use
one round. Benchmark settings and acceptance criteria live in
[the runner guide](../bench/tclock_compare/README.md) and
[performance plan](PERFORMANCE_PLAN.md).
