# Synchronizing source to the benchmark VM

Edit the Git checkout on `380G10` at `/home/eric/vm/vm-shared/kdlock`.
All compilation, tests, modules, daemons and benchmarks run in the VM on
`eric@10.176.26.71`, under `/root/host_fs/kdlock`. The physical benchmark host's
`/home/eric/vm/vm-shared/kdlock` directory is a source mirror.

From the source checkout, inspect or synchronize current tracked files,
including uncommitted edits:

```sh
python3 tools/vm/sync_to_vm.py --dry-run
python3 tools/vm/sync_to_vm.py
ssh -p 2222 root@10.176.26.71
```

The command copies regular tracked files into a private local snapshot and
hashes those bytes before transfer. It checks that the guest is idle and its
source directory resides on ext4, updates the physical host mirror, deploys
the current manifest and maintained guest sync helper, then copies only changed
files into the guest. Incoming bytes and every final guest source hash are
verified. SSH and rsync operations have bounded timeouts.

The dry run compares proposed mirror changes and guest hashes without writing
remote project files or manifests. The command never builds or runs tests on a
physical host. It never deletes files, transfers Git metadata, or transfers
untracked/ignored files. Raw evidence under `bench/results/<machine>/raw/` is excluded
even if accidentally tracked. Missing tracked paths are reported and retained
remotely; review and remove an identified obsolete guest file separately while
idle. Add intended new source files to Git before synchronizing them.

Stop and drain benchmark workers, daemons and project modules before replacing
source. If a command fails or times out, inspect the guest and rerun this command
to complete hash verification before starting a build or benchmark. A timeout
does not establish drain. The guest helper `sync_source.py` additionally refuses
symlink/non-file destinations and staged-source races; it never recursively
replaces the source root or clears evidence.

Keep tracked receipts under `bench/results/<machine>/tests/` or
`bench/results/<machine>/bench/` and ignored raw evidence under
`bench/results/<machine>/raw/`. Preserve the machine identity and CPU topology recorded
when each run executed; historical measurements do not become new-host runs
when their files move. See the [benchmark guide](../../bench/README.md) and
[test guide](../../tests/README.md) for result placement and execution commands.

The target's existing `/home/eric/vm/qemu-scripts/vm_ssh.sh` provides guest SSH
using its dedicated key. Alternate physical host and mirror/script paths can be
selected with `--host`, `--mirror` and `--scripts`; inspect `--help` for options.

## Complete 1–64-worker comparison

[`run_full_bench.py`](run_full_bench.py) runs Native, TCLock and KD with three
rounds at `1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60 64`.
By default it includes one-cacheline and RCUHT payloads for spin, mutex and
rwlock, with rwlock at 1%/20% writes: **1,584 sessions** in six groups.
This driver's default excludes multi-cacheline scenarios, including c02, c08
and c16. `--include-multicacheline` selects its wider 3,960-session matrix.
Current runners always use blocking mutexes. The
[real API runner](../../bench/real_api/README.md) covers syscall workloads and
Stock controls separately; [the results index](../../bench/results/README.md)
retains benchmark reports and their frozen source versions.
Each session has 48,000 warmup operations per worker, a two-second measurement,
and a 300 ms peak window after 300 ms of settling.
The all-lock driver retains legacy mutexes. Use the
[owned c01 full-grid command](../../bench/tclock_compare/README.md#owned-c01-full-grid)
for the ABI4/reuse-32 comparison alone: 22 counts, three arms, three rounds and
198 sessions. It uses the same temporary placement below. Its
[2026-10-14 closeout](../../bench/results/10.176.26.71/bench/mutex_owned/20261014-full-grid/README.md#verification-and-closeout)
records restoration of the regular 64-vCPU boot afterward; it is not a current
health or snapshot check for a future run.

The standard 64-vCPU VM cannot supply 64 distinct worker CPUs and a separate
collector CPU. A temporary two-node, 66-vCPU boot can use worker CPUs
`0–31,33–64` and collector 65, with CPU 32 unused. Pin workers 0–31 to host 0–31
and workers 33–64 to host 32–63, preserving 32 worker cores on each NUMA node.
Pin the extra vCPUs 32/65 to host 31/63 respectively. This host has only 64
physical cores: collector 65 and QEMU service threads share host core 63 with
the last worker at **64 workers**. Record this contention explicitly; a separate
guest CPU does not establish a separate physical collector core. Keep this
topology's evidence separate from earlier 64-vCPU measurements.

After synchronizing source, verifying pins/kernel/boot policy, and creating and
confirming a fresh snapshot of the temporary boot, run inside the guest:

```sh
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH
export LC_ALL=C
export KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_66_VCPU_SNAPSHOT
python3 tools/vm/run_full_bench.py \
  --cpus $(seq 0 31) $(seq 33 64) --collector-cpu 65 \
  --output /root/kdlock-evidence/10.176.26.71/bench/full-matrix-NEW
```

Use `--dry-run` to inspect the selected groups. Each group has an outer two-hour
timeout and retained runner logs. `matrix-status.json` records progress. Creating
`<output>/STOP` stops at the next drained group boundary; for a shorter boundary,
use the active runner's `<group>/STOP`. Incomplete or undrained groups stop the
driver. Completed, drained NO_JIT rejections remain excluded from performance
scores and do not prevent collecting other payloads. Archive all evidence before
restoring the regular 64-vCPU boot; saved states from different topologies must
never be loaded interchangeably.

If a full matrix stops only because `/proc/<pid>/task` disappeared during an
idle scan, [`resume_full_bench.py`](resume_full_bench.py) can continue after
verifying the guest is drained, kernel health is clean and all original approved
source hashes still match. Save the helper outside the guest checkout and invoke
it with `--output` pointing to the stopped matrix, using the same confirmed
snapshot and pinned benchmark environment. It preserves the interrupted group,
failure, driver log and status under `attempts/`, then reruns that entire group
and finishes the remaining groups. Three bounded retries handle an exited task;
an entire original idle scan must succeed. Live workers, missing payloads,
unsafe failures and repeated scan failures still stop execution. The
[retry checks](test_resume_full_bench.py) exercise those distinctions in the guest.
The [offline exporter](../../bench/full_compare/README.md) audits retained attempts
and excludes their samples from the final three-round statistics.
