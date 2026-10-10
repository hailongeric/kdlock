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
