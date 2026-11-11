# Build and test

All builds and runs happen in the `kdclaude` VM, never on the source host.
Source edits are made on the host and reach the VM through the 9p share.

## 1. The VM

| Item | Value |
| --- | --- |
| Start / stop / monitor / pin | `/home/eric/vm/qemu-scripts/run_claude_vm.sh [start\|stop\|monitor\|pin]` |
| SSH | `ssh -p 2223 root@127.0.0.1` |
| OS / kernel | Ubuntu 26.04.1 LTS; default boot `7.0.0-38-kdlock1`; the kdlock kernel `7.0.0-38-kdclaude1` is installed next to it and booted once with `grub-reboot` |
| Size | 32 vCPUs (2 nodes x 16), 16 GiB, pinned to host CPUs 0-15 and 20-35 |
| Disks | `/home/eric/vm/qemu-disks/kdclaude-root.qcow2`, `kdclaude-builds.qcow2` (mounted at `/mnt/kdlock-builds`) |
| Source in the VM | `/root/host_fs/kdlock/kdlock_claude_version` (9p share of the host's `vm-shared`) |
| Serial log | `/tmp/qemu-claude-serial.log` (on the host) |
| Snapshot | `pre-kdclaude1-boot` (internal, both disks), taken before the first boot of the kdlock kernel |

The VM was created from the original build VM's root filesystem with the same
Ubuntu and kernel version. It is independent of that VM.

`savevm` refuses while the 9p share is mounted. Take a snapshot with
`umount /root/host_fs` in the guest, `savevm <tag>` on the monitor, then
`mount /root/host_fs`.

## 2. Build checks

| Check | How | Result |
| --- | --- | --- |
| kdlock directory, built in | `bash /root/kdc/builtin.sh` then `make O=/mnt/kdlock-builds/kdc/out -j32 kernel/locking/kdlock/` in `/mnt/kdlock-builds/kdc/src` | 8 objects compile/assemble, objtool clean, no warnings |
| Full kernel | `make O=../out -j32 KERNELRELEASE=7.0.0-38-kdclaude1` (debug info off, `XEN_PV`/`PARAVIRT_XXL` off, `KDLOCK=y`) | links; bzImage 15 MB |
| Benchmark module | `bash /root/benchcheck.sh` (copies `bench/` and `include/` to `/root/kdb`, builds against the kdclaude tree) | `kd_bench.ko` links, all `kd_*` symbols resolved |
| Translator | capstone 5.0.7 in a venv: `/root/kdvenv` (`/root/kdvenv/bin/pip install capstone`) | imports and runs |

## 3. Building, installing and booting the kdlock kernel

```
cd /mnt/kdlock-builds/kdc/src
bash /root/kdc/builtin.sh                      # re-applies kdlock sources, olddefconfig, prepare
make O=../out -j32 KERNELRELEASE=7.0.0-38-kdclaude1
make O=../out KERNELRELEASE=7.0.0-38-kdclaude1 INSTALL_MOD_STRIP=1 modules_install   # only when modules changed
make O=../out KERNELRELEASE=7.0.0-38-kdclaude1 install
grub-reboot "gnulinux-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961>gnulinux-7.0.0-38-kdclaude1-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961"
systemctl reboot
```

`GRUB_DEFAULT` is pinned to the `kdlock1` entry by id
(`/etc/default/grub.d/99-kdlock-nopvspin.cfg`), so installing does not change
the default and a failed boot comes back on `kdlock1`.

## 4. Running the tests

```
insmod /root/kdb/bench/kd_bench.ko
cd /root/host_fs/kdlock/kdlock_claude_version/jit
setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kdstate.json -v \
    > /root/kdd.log 2>&1 < /dev/null & echo $! > /root/kdd.pid    # turns delegation on
python3 ../bench/run_nano.py --family mix --backend kd --workers 8 32 --ms 1000
kill -INT $(cat /root/kdd.pid)                                     # turns delegation off
```

Stop the daemon by its pid: `pkill -f kd_daemon.py` also matches the remote
shell whose command line names it. Without the daemon, `delegation` is 0 and
every kd lock is a plain queued lock (the "local" runs below).

`jit/kd_dryrun.py FUNC... [--disasm]` builds the images for the lock calls in
the named functions without loading anything and prints the generated code;
use it before letting new code run.

## 5. Runtime results (2026-11-11)

Kernel `7.0.0-38-kdclaude1 #2` (built 13:25 UTC), bench module and translator
from the working tree whose source files hash to `d523a3ec8c052d00`
(`sha256sum` over `kernel include jit bench integration` sources, then of that
list). Not committed. All points are single 0.5–5 s rounds; the rates are not
performance results (no repeats, no frequency control) and are not quoted
here.

| Check | Result |
| --- | --- |
| Boot (twice, builds #1 and #2) | clean; `kdlock: core ready, batch 1024, numa order 1`; `/dev/kdlock`, debugfs `kdlock_stats` present |
| Local correctness (no daemon): spin/mutex/rwlock/rwsem, c01/c16, writes 100/20%, 1/8/32 workers, kd and native | 72/72 points exact (data oracle, no torn reads, every worker progressed) |
| Delegated (daemon on), same 36 kd points | 36/36 exact; spin and rwlock writers delegate almost every contended section; mutex and rwsem part of them; 0 handbacks (the nano bodies only leave through their unlock) |
| Module unload/reload with daemon on | kernel drops all images, daemon purges the range, requests return, sites rebuilt, delegation resumes |
| Stress, 32 workers x 5 s per family with JIT, then `rmmod` | exact; 50.8 M delegated sections; no warning, no preempt-count report after unload |
| Nesting (`nest_spin`, `nest_mutex`, 8/32 workers) | exact; outer exclusion held across the inner section; nested acquires both inline (`nested_local`) and as nested sessions (`nested_delegated`) |
| Handback (`mix`: indirect call, `yield()` frontier, nested sleeping acquire, `current` checks) | exact; ~6.5% handed back; every `current` read in delegated code returned the origin task (31 `current_task` loads in the image redirected to `kd_cpu.task`) |
| Final pass, 9 profiles x kd/native x 8/32 workers | 36/36 exact; totals since boot: 107.5 M delegated, 135 k handed back, `handback_pinned` 0 |
| Shutdown and reboot after unload | clean (serial log: no BUG/WARNING/hang) |

Bugs found by these runs and fixed:

* `kd_bench`: counters were not reset between runs (later c16 readers saw
  lines left behind by a c01 run), and a finished worker rewrote `cnt[15]`
  outside the lock while others still incremented it.
* Images were never dropped when module text went away, so a later module at
  the same address could run a stale copy; module exception tables were not
  read. Fixed with the text generation interface (`KD_IOC_TEXT`,
  `KD_EV_TEXT_GONE`, ABI 2; [INTERFACES.md](INTERFACES.md)).
* A site request was sent once per address, ever; a lost one (or one sent
  while no daemon ran) left the site without an image for good. Requests now
  repeat every 4096 contended waits, and the daemon rebuilds on every request.
* Module ITS indirect-branch thunks have no symbol; calls to them were treated
  as frontiers, so any section with an indirect call was handed back. They are
  now recognized as `jmp *%reg` and handled as indirect branches.

## 6. Not tested yet

* Nesting deeper than two levels, and the `KD_MAX_DEPTH` / `KD_MAX_ROOTS`
  limits.
* Forced `MISS_CODE` / `MISS_RET` handback (seen only as learning events),
  `UNLOCK_ANC`, `irq`/`irqsave`/`bh` variants, and an interrupt handler
  taking a lock that a delegated section holds (DIFFERENCES D4).
* Signals during queued spinning for `killable`/`interruptible` (D8).
* CPU hotplug, text patching after publication.
* Kernel lock API switch (`kd_linux_map.h`) and real system-call workloads.
* Any performance measurement with repeats and matched Native controls
  ([PERF_PLAN.md](PERF_PLAN.md) task C).

## 7. Rules

* No performance claim without a matched native run on the same kernel, VM and
  call shell; no pooling across kernels, source versions or call shells.
* Report the execution class (delegated / handed back / local) with every
  rate.
* One round gives no variance claim.
* Do not touch the original VM on `10.176.26.71` while another agent works
  there.
