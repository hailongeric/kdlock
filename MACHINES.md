# kdlock machines and how to reach them (view from the cloud host)

This file describes only the machine topology and how to work across the
machines. The development rules are in [AGENTS.md](AGENTS.md), the build and
test procedure in [docs/BUILD_AND_TEST.md](docs/BUILD_AND_TEST.md), and the
state of the work in [docs/HANDOFF.md](docs/HANDOFF.md); they take precedence
and are not repeated here. (English version of the topology note the user put
in `/root/kdlock/AGENTS.md` on the cloud host on 2026-11-19; its original is
kept in `/root/kdlock-pre-migration-20261119/` there. Updated for the move of
the source to the cloud host the same day.)

## Machines

| Name | Where | Role | Reached from the cloud host |
| --- | --- | --- | --- |
| cloud host | public cloud machine 96.44.157.161, root, 6 cores / 5 GiB / 85 GiB free | where the agent runs; **source of truth since 2026-11-19: `/root/kdlock`** | - |
| B = `380G10` | internal 10.176.26.33, user `eric` | former source host; its repository `/home/eric/vm/vm-shared/kdlock` (branch `master`, remote `github.com/hailongeric/kdlock`) is frozen at the migration commit | `ssh kd-b` (reverse tunnel to 127.0.0.1:3333) |
| A = `Super-Server` | internal 10.176.26.71, user `eric` | test host: runs the QEMU VM `kdclaude` | `ssh kd-a` (reverse tunnel to 127.0.0.1:3334) |
| VM = `kdclaude` | QEMU guest on A, 64 vCPUs / 24 GiB, user `root` | every build, module, daemon, test and timing runs here | `ssh kd-vm` (through `kd-a` to A's 127.0.0.1:2223) |

* `kd-a`, `kd-b` and `kd-vm` are defined in `~/.ssh/config` on the cloud
  host; its `~/.ssh/id_ed25519` is accepted by both machines.
* The tunnels are opened by A and B towards the cloud host (`autossh -M 0 -N
  -R 3333:localhost:22 root@96.44.157.161` on B, `-R 3334` on A, both as
  `eric`); the cloud host cannot rebuild them. When `ssh` cannot connect,
  look at `ss -ltn | grep -E ':333[34]'` and `ss -tnp | grep ':333[34]'`: no
  listener means the tunnel is down; a listener whose connections sit in
  `CLOSE-WAIT` and whose outer connection has a stuck send queue means the
  tunnel session is dead but still holds the port. Both need the user (or an
  agent the user allows) to restart the tunnel ssh on the internal side (the
  `autossh` parent then reconnects); the stale `sshd` on the cloud host may
  have to be ended first so the port is free. Seen on 2026-11-19 right after
  the migration.
* A and B reach each other on the internal network (on B:
  `ssh eric@10.176.26.71`).
* The cloud host's public key was added to the VM's
  `/root/.ssh/authorized_keys` on 2026-11-19 (with the user's consent). If the
  VM disk is rolled back to an older snapshot the key is gone and `ssh kd-vm`
  is refused; add it again through A
  (`ssh kd-a 'ssh -p 2223 root@127.0.0.1 ...'`).

## Where the code is

| Where | What |
| --- | --- |
| cloud host `/root/kdlock` | **the only editable source**: full git repository (all branches, tags and `refs/archive/*`, copied from B with its `.git`) |
| B `/home/eric/vm/vm-shared/kdlock` | the repository as it was at the migration; do not edit it (two writable copies make uncommitted work diverge) |
| A `/home/eric/vm/vm-shared/kdlock` | rsync target the VM builds from; not a git repository |
| VM `/root/host_fs/kdlock` | 9p mount of A's `vm-shared`, the same files as the line above |

Data flow: edit and commit on the cloud host, rsync to A's
`vm-shared/kdlock`, build and run in the VM from `/root/host_fs/kdlock`.

```bash
# cloud host -> A (only while the VM is idle; look at the dry run first)
rsync -a --dry-run --itemize-changes --exclude=.git --exclude=.claude \
    /root/kdlock/ kd-a:vm/vm-shared/kdlock/
rsync -a --exclude=.git --exclude=.claude /root/kdlock/ kd-a:vm/vm-shared/kdlock/

# in the VM (bound every command)
ssh kd-vm 'timeout 60 sh -c "uname -r; uptime"'

# VM start, monitor, CPU pinning (on A)
ssh kd-a '~/vm/qemu-scripts/run_claude_vm.sh pin'
# serial log: /tmp/qemu-claude-serial.log on A
```

## Rules

1. **Make sure nobody else is using it.** Other agent sessions (claude, codex)
   may run on B, and a test may be running in the VM. Before acting, check
   `ssh kd-b 'pgrep -af "claude|codex"'` and
   `ssh kd-vm 'uptime; pgrep -af "run_|kd_daemon|will-it|make"'`. While
   something is active, do not synchronise, reboot the VM or change the
   inputs of a running test; ask the user first.
2. Builds, tests and timing never run on the cloud host, on A's host or on B,
   only in the VM.
3. A's `vm-shared` is the directory the VM has mounted: never empty it, and
   never `rsync --delete` into it without a dry run first.
4. The repository has many worktrees registered (paths on B, most of them
   gone): do not `git reset --hard`, `git clean` or `git worktree prune`.
   Roll back as AGENTS.md says.
5. The cloud host is on the public network: do not copy VM disks, kernel
   build output or large result sets to it; fetch only the log excerpts you
   need. Commit result data that belongs to the repository as usual.
6. Put `timeout` on every remote command; a timeout does not mean the remote
   process has ended, check again.
