# Development and operations

The current compatibility experiment is `/tmp/kdlock-mutex-legacy-compat`, branch
`task/legacy-mutex-compat`, based on `74676c3`. Its
[implementation comparison](design/legacy_mutex_compatibility.md) separates the
backported instruction/publication changes from the unchanged legacy protocol.
The exact recovery and baseline benchmark worktrees remain unchanged. The current
verified snapshot is `before-mutex-legacy-compat-20261017T122742Z`; recheck live state
and snapshot availability before further module/JIT work.

Follow these rules when developing or running the x86_64 KD spin/mutex/rwlock
provider. Start with the [project guide](PROJECT_GUIDE.md). Use
[tests](../tests/README.md) and [benchmarks](../bench/README.md) for commands and
results, and the [design glossary](DESIGN.md#terms-used-in-these-guides) for the
ownership and lifetime terms used below.

## Development rules

1. Read the source and `git status --short` before editing. Preserve unrelated
   changes; do not reset unknown files. Maintained prose and comments use English.
2. Explain the purpose and ordering constraints of protocol changes. Keep common
   supported paths working and select basic plus directly affected checks.
   Full suites require an explicit request. Rare resource, cancellation and alias
   combinations are optional coverage, not automatic delivery gates.
3. Track the real lock owner and each acquisition exactly. Keep source leases
   and acquisition references until the required unlock ACKs and frame retirement
   have finished. Approximate profiling counters cannot replace these records.
   Do not weaken admission checks or remove probes to make a failing case pass.
4. Share an existing request packet/frame through pointers and explicit ownership
   transfer. Prefer preallocated storage. Do not copy whole packets, clear whole
   records or add a global lock just to make lifetime handling easier. Keep the
   required initial capture, final restore and owner state that has a separate
   lifetime.
5. Keep the two-word wrapper input ABI. Userspace/futex, other architectures and
   general oversubscription redesign are outside this phase. Published KD waiters
   remain pinned and poll; native mutex owners/services may sleep.
6. Ordinary KD spin and rwlock pairs protect preemption and preserve IRQ/BH state.
   Spin IRQ/irqsave/BH variants use their explicit native interfaces. Rwlocks
   support ordinary task context only; no rwlock IRQ/BH variants are provided.
7. Do not modify, build or install the guest kernel by default. The separately
   authorized static/spin-clobber/mutex-clobber experiments keep independent
   source trees, releases and captured baselines. Current code requires both
   clobber-v1 interfaces; old kernels are only for matching historical checkouts.
8. This isolated compatibility experiment backports fail-closed processor-state
   admission and immutable mutex images at the user's 2026-10-17 request. It retains
   the recovered legacy lock protocol. Access-time guards, general instruction/flags
   repair, ordinary-C ABI4 and owned-origin claims are outside this experiment.
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

## Recovered legacy baseline

This branch restores the captured KD mutex implementation associated with the
2026-10-11 pipebytes n16 result of 5.330 Mops/s at 60 workers. It uses the original
Linux mutex, shadow MCS queue and pinned polling producers. The user's explicit
2026-10-16 recovery instruction selects this historical policy; do not add the
later owned mutex, adaptive policy or sleeping producer path to this baseline.
See the [recovery receipt](../bench/results/10.176.26.71/bench/comparison/mutex-legacy-recovery-20261016T113518Z/README.md)
for source identities, validation and fresh measurements.

The original source is `/tmp/kdlock-mutex-legacy-5m330` on `380G10`, branch
`recovery/mutex-legacy-5m330`. The compatibility source is the worktree named
above; use the maintained helper with `--source /tmp/kdlock-mutex-legacy-compat`.
The primary worktree retains its 35 pre-existing edits and archived adaptive
experiment. Freeze manifest-listed inputs and keep all builds and tests guest-only.

## Environment

| Action | Location |
| --- | --- |
| Primary benchmark host | Ubuntu host: `eric@10.176.26.71` |
| Source edits, Git and static checks | Current host `380G10`: `/home/eric/vm/vm-shared/kdlock` |
| Destination source mirror and VM control | `10.176.26.71`: `/home/eric/vm/vm-shared/kdlock` and `/home/eric/vm/qemu-scripts` |
| All subsequent compilation, unit tests, modules, daemon and benchmarks | VM on `10.176.26.71`: `/root/host_fs/kdlock` |
| Guest SSH from another machine | `root@10.176.26.71:2222` |
| Guest SSH from the benchmark host | `ssh kdlock-vm`, or `/home/eric/vm/qemu-scripts/vm_ssh.sh` |
| Current kernel source/build | `/root/linux-6.1.159-kdclobber2` |
| Captured kernel bundle | `/root/kdlock-kernel-baselines/mutex-clobber2-20260919` |
| QEMU launcher | Host: `/home/eric/vm/qemu-scripts/run_vm.sh` |

The destination launcher defaults to `recovery`: 64 vCPUs, two sockets with
32 cores each, and 24 GiB of RAM. Guest NUMA node 0 has CPUs 0–31 and 12 GiB,
bound to host CPUs 0–31 and memory node 0. Guest node 1 has CPUs 32–63 and
12 GiB, bound to host CPUs 32–63 and memory node 1. Every guest vCPU is pinned
to the same-numbered physical host core. QEMU service threads share host CPU 63;
the VM retains all 64 cores. `pin_cpu.sh` runs automatically and verifies every
vCPU affinity. Use collector CPU 63 and worker cohorts that exclude it.
Use exactly 64 vCPUs for new runs. This recovered API runner requires a separate
collector and supports at most 63 workers. Do not use the historical temporary
66-vCPU recipe for new measurements or load snapshots from another topology.

Launcher modes are `recovery`, `shared`, `status`, `monitor [COMMAND]` and
`stop`; `stop` requests guest shutdown and never force-kills QEMU. Guest SSH
and service forwards are host ports 2222, 9090 and 9091; debugger port 1234 is
host-loopback only. `vm_ssh.sh` uses `/home/eric/.ssh/kdlock_vm_ed25519`.
Edit kdlock only in the current host's Git checkout, then run
`python3 tools/vm/sync_to_vm.py` there. It snapshots current tracked source bytes,
updates the destination mirror and hash manifest, and invokes `sync_source.py`
to copy changed files into an idle ext4 guest. Do not edit the destination mirror
or guest as a second source checkout. The synchronization helper excludes Git
metadata and ignored raw results; tracked deletions are reported without deleting
guest files. See [the synchronization guide](../tools/vm/README.md).
`bench.sh` saves and verifies a fresh snapshot, runs the migration checks, and
archives results on the physical host; see [the benchmark guide](../bench/README.md#vm-migration-validation).

Do not build or execute tests on the host. Read-only offline archive checks are
allowed there. Recovery mode uses an ext4 copy; `shared` mode uses shared 9p
with the `hostshare` mount tag and does not attach VFIO devices.
While idle, compare SHA256 and copy only changed files, creating subdirectories
as needed. Delete only identified obsolete project files. Never move, recursively
replace or clear `/root/host_fs`, and do not edit frozen running inputs.

The 64-vCPU boot, exact kernel identity, all 64 CPU pins and guest health were
verified again on 2026-10-16, with recovery snapshot
`before-mutex-legacy-recovery-20261016T113518Z`. The earlier 73-session migration benchmark used 60 vCPUs
and remains evidence for that topology. The migration copy contains current disk
contents without historical VM snapshots; the original disks on `380G10` remain
untouched for rollback. Saved VM state from the old CPU/topology is not portable
to the destination. Create and verify a new snapshot there before live module/JIT
runs, then verify kernel identity, boot policy, placement and benchmark drain.

Verify the captured source, config, build files and live Build ID with
[the guide](PROJECT_GUIDE.md#kernel-identity); `uname -r` alone is insufficient.
Keep `nokaslr`, voluntary preemption, frame pointers and mitigations unchanged.
Benchmark boot policy requires `nopvspin` and native qspinlocks. Verify the
argument and boot confirmation independently of Build ID; snapshot restoration
can restore the earlier policy. Follow [the boot policy](PROJECT_GUIDE.md#native-qspinlocks-in-the-vm)
before live runs and keep benchmark samples from different policies separate.
Check actual CPU/NUMA placement against the destination mapping above after
every restart. Historical 40-vCPU measurements retain their original placement.
Saved VM states captured with 40 or 60 vCPUs must not be loaded into the current
64-vCPU configuration; use a verified snapshot from the current boot.

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

Store results by the physical machine that executed them. Published reports use
`bench/results/<machine>/{bench,tests}/`; ignored host archives use
`bench/results/<machine>/raw/{bench,tests}/`. Current guest runs write outside the
source tree to `/root/kdlock-evidence/10.176.26.71/{bench,tests}/<run>` before
archiving to the matching host directory. Original-host reports remain under
`bench/results/380G10/`. Preserve historical source hashes, commands and paths as
captured; relocation mappings and legacy compatibility paths are in
[the results index](../bench/results/README.md). Never pool different machines or CPU
topologies into one benchmark result.

NORMAL means a JIT image was published; it does not show that the body ran. Report
observed JIT execution, NO_JIT/native controls, refusals, synthetic fixtures and
kernel protocol probes separately. Save commands, source/ELF hashes, environment,
exit status, kernel identity and shutdown checks. An old pass is neither a new run
nor proof that the whole current project passes.

For shutdown, stop new calls and wait for workers and translators to finish.
Then retire sources. If retirement returns EBUSY, retain pins and diagnose the
remaining users; never force unload or reopen admission. After retirement succeeds,
unload workloads before providers.

When replacing code, replace the workload, provider and JIT session together.
Mutex frames bind immutable generations retained until session teardown.
Spin/rwlock artifacts remain keyed by RIP with in-place replacement. Source pins, device references, physical owners, ACKs and
frames each have their own lifetime. Reusing a queue node or waking a waiter does
not mean its frame has retired.

Before changing inputs, stop the experiment through its mechanism for stopping
between cases. Keep partial results, and do not combine runs from different frozen
versions into one complete matrix. Matching archived files can establish internal
consistency; it does not prove a new execution or authenticate where the source
originally came from.

## VM recovery

Check the actual host process view and a bounded SSH connection before restarting.
If SSH fails or times out, save `/tmp/qemu-serial.log`, stop the confirmed old VM,
and verify it has exited before launching another instance. Do not restart a
healthy guest because monitor access failed or a test has not produced output.

Run `./run_vm.sh recovery` on `10.176.26.71` from `/home/eric/vm/qemu-scripts`.
Recovery supports snapshots; shared/VirtFS mode must not be assumed to.
The monitor socket is
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
[the spin/mutex runner](../bench/tclock_compare/README.md),
[the rwlock runner](../bench/rwlock_compare/README.md) and
[performance status](PERFORMANCE.md).
