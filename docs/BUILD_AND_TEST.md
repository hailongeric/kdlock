# Build and test

All builds and runs happen in the `kdclaude` VM, never on the source host.
Source edits are made on 380G10. Since 2026-11-14 the VM runs on
10.176.26.71, and its 9p share is that host's `vm-shared`, so edited files
are copied there (rsync) before a build or run. Do not run it at the same
time as the other VM on that host (`ubuntu-build`): memory and CPUs are
not enough for both, and timings would interfere.

## 1. The VM

| Item | Value |
| --- | --- |
| Start / stop / monitor / pin | on 10.176.26.71: `/home/eric/vm/qemu-scripts/run_claude_vm.sh [start\|stop\|monitor\|pin]` (pin after every start) |
| SSH | `ssh -p 2223 root@127.0.0.1` on 10.176.26.71; from 380G10 first `ssh -f -N -L 2223:127.0.0.1:2223 eric@10.176.26.71` |
| OS / kernel | Ubuntu 26.04.1 LTS; default boot `7.0.0-38-kdlock1`; the kdlock kernels are installed next to it and booted once with `grub-reboot` |
| kdlock kernels | `7.0.0-38-kdclaude1` (mmap lock and syscall-path objects switchable, `CONFIG_KDLOCK_MM`/`_API`); every lock a kdlock (`CONFIG_KDLOCK_ALL`, tree `/mnt/kdlock-builds/kda/src`): `kdall1` #3 (`3ff2d94e`), `kdall2` #4 (ww spin, `48f57b3b`), `kdall3` #5 (plus plain-mode node order, `130cc457`, output `out3`); the same tree with `CONFIG_KDLOCK_ALL` off, native locks with kdlock built in, for comparisons against native: `kdnat1` (as kdall1, output `outnat`), `kdnat2` (as kdall3). kdnat3/4 and kdall4/5 carry rejected changes (`bench/results/kdclaude/kdall-native-20261117-64cpu/rejected/`). Second round (section 8 of that README): `kdall6`-`kdall9` and `kdnat5`-`kdnat8` are intermediate steps; **`kdall10` (output `out3`) and its twin `kdnat9` (output `outnat2`)** carry the committed state (rwsem era bound, queue rule, ww spin rule, `KD_QF_WOKEN`). Fixes of 2026-11-19 (`bench/results/kdclaude/appgrid-20261118-64cpu/` section 8), all output `out3`: `kdall11` rwsem release assertions; `kdall11d`/`kdall11e` diagnostic builds (a temporary decision ring, not committed; 11e with the nested-verdict fix); `kdall12` an intermediate per-CPU attempt; **`kdall13` #18 = `3a909d50`** (both fixes, `hb_region`/`done_in_region`) and its native twin **`kdnat10` #10** (the same source, output `outnat2`; `bench/results/kdclaude/appgrid-20261119-64cpu/`). **Native twins up to `kdnat10` lack `CONFIG_PARAVIRT_SPINLOCKS`: in the guest their contended spinlocks are test-and-set locks, not the queued ones (`virt_spin_lock_key`); do not use them as a baseline.** Plain-path round of 2026-11-19/20 (`bench/results/kdclaude/plain-20261119-64cpu/`), kd output `out3`, native output `outnat3` (with `CONFIG_PARAVIRT_SPINLOCKS=y`; with `nopvspin` on the command line the key is off, check `python3 /root/skey.py virt_spin_lock_key`): `kdnat11`-`kdnat17` and `kdall14`-`kdall20` are its steps (README there); **`kdall21` and its twin `kdnat18`** carry the committed state. Built with `bench/vm/buildk.sh NAME out3` (kdnat: `outnat2`) |
| Size | 64 vCPUs (2 sockets x 32, guest node 0 = CPUs 0-31 on host node 0, node 1 = 32-63 on host node 1), 24 GiB (12 per node); one vCPU pinned per host CPU. Until 2026-11-13: 380G10, 32 vCPUs (2 x 16), 16 GiB |
| Disks | `/home/eric/vm/qemu-disks/kdclaude-root.qcow2`, `kdclaude-builds.qcow2` (mounted at `/mnt/kdlock-builds`) |
| Source in the VM | `/root/host_fs/kdlock` (9p share of the host's `vm-shared`; the repository root) |
| Serial log | `/tmp/qemu-claude-serial.log` (on 10.176.26.71) |
| Host frequency | from 2026-11-15: turbo on, every CPU fixed at 2.7 GHz, the all-core turbo limit (`intel_pstate/no_turbo` = 0, `scaling_min_freq` = `scaling_max_freq` = 2700000, governor `performance`); 2699 MHz measured with 64 busy CPUs. Before: turbo off, 2.0 GHz fixed. Results at the two frequencies are not comparable. To go back: `no_turbo` = 1 and both limits 2000000 |
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
cd /root/host_fs/kdlock/jit
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

## 5a. Nano grid and the TCLock backend

`bench/run_grid.py` runs the profiles of [PERF_PLAN.md](PERF_PLAN.md) task C,
alternating the backends at every point; `bench/grid_summary.py` prints the
medians with the execution-class shares, and `bench/grid_table.py` exports one
row per (profile, workers) with every backend's rate and the ratios, as CSV for
plotting or as a markdown table. `bench/wis_table.py` does the same for the
will-it-scale runs of `bench/run_mmap1.py`, adding the delegation counters so
that "kdlock is not helping" stays distinguishable from "kdlock is not even
running here". Results and the map from build number to source are in
`bench/results/kdclaude/`.

`bench/run_place.py` runs one point at several CPU placements (worker *i*
runs on CPU *first + i*, so the first CPU decides how many workers each NUMA
node gets) and, with `--configs`, under several sets of core parameters in
one boot, rotating their order per round. The grid cannot separate "more
workers" from "across nodes", because from 36 workers on both change
together; a fixed count at two placements can. `bench/place_summary.py`
prints the rates, the ratios to the first column or to the one-node placement
(`--cross`), the least over the most operations per worker (`--fair`) and
chosen counters. Two things this tool taught that apply to any A/B here: a
comparison of a feature switched off and on does not show what the feature's
always-on code costs, so the switch must remove that code's work as well
(`kd_rw_era_ns=0` does since build #81); and equal total rates can hide a
node that gets a fraction of its share, which is why `--fair` exists.

`bench/run_oversub.py` runs a point with more threads than CPUs: `--cpus`
CPUs, `--factors` workers per CPU (worker *i* on CPU *first + i mod cpus*,
`run_nano.py --cpus`). It records the least and most operations per worker
and per CPU and the workers that completed nothing. TCLock runs only with one
worker per CPU (its spinlock crashed the guest with two, its sleepable
adapters refuse more than one task per CPU).

Before any run that may take the guest down, `sync`: a panic loses what the
page cache had not written, built modules included (build #82: the bench and
TCLock modules were empty files after the reboot).

The original TCLock locks are a third backend when the bench is built with
them (`/root/tcbuild.sh` in the VM):

```
/root/tcbuild.sh          # builds tclock_backend x4 (TCLOCK_NUMA=1) and kd_bench with KDB_TCLOCK=1
rmmod kd_bench
for f in spin/tclock_backend_km mutex/tclock_mutex_backend_km \
         rwlock/tclock_rwlock_backend_km rwsem/tclock_rwsem_backend_km; do
    insmod /root/tc/$f.ko; done
insmod /root/kdbt/bench/kd_bench.ko
python3 run_grid.py --backends native kd tclock --out grid.jsonl
```

The four TCLock modules build with objtool warnings from upstream's
hand-written stack switch (`naked return`, `BP used as a scratch
register`); they are unchanged upstream code. Correctness pass with all three
backends (spin/mutex/rwlock/rwsem, c01/c16, 1%/20% writes, 1–32 workers): 288
points exact.

## 5b. Adaptive delegation, role exchange, API coverage (2026-11-12/13)

Builds #25 to #39 of `7.0.0-38-kdclaude1`; the last one is the committed
state. `bench/run_corr.py` is the correctness pass used from here on:

```
python3 run_corr.py --out corr.jsonl          # Native and kd, about 2 minutes
python3 run_nano.py --api-test                # the single-task API check alone
```

It runs 240 points (every family and test body of `kd_bench`, 1 to 32
workers, 300 ms each), the single-task check of every kd API variant (65
checks of lock state, interrupt flag and preempt count), and fails on a
broken data oracle or on anything the kernel log complained about meanwhile.

| Check (build #39 unless noted) | Result |
| --- | --- |
| Correctness pass, defaults | 240 points exact, API 65/65, no kernel complaints |
| The same with `kd_xchg=2` (every family offers), build #38 | 240 points exact |
| Role exchange exercised (`spin_hb`, `rwlock_hb`, `rwsem_hb`, `mix`: a sixteenth of the sections handed back) | exact; of 643 768 offers in one pass 640 586 taken over, 3 177 declined, 5 withdrawn (build #36) |
| ww mutexes (`ww` body: two of four locks in random order per operation, back-off on `-EDEADLK`), 2/8/32 workers | exact |
| Sections with `rcu_read_lock(); rcu_read_unlock()` delegated (`spin_curw`, `mutex_curw`) | exact, 12.5 M delegated sections at 16 workers without an RCU complaint; build #38 did complain, see below |
| Nano grid, three backends, 2 rounds (round 5) | 1008 points, no failed point; `bench/results/kdclaude/grid-20261113-r5/` |

Bugs found by these runs and fixed:

* **Delegated `rcu_read_lock()` sections unbalanced the RCU depth** (kernel
  warnings on build #38). The origin's `rcu_read_lock_nesting` was changed
  from the executor's CPU while interrupt handlers on the origin's CPU
  changed it too. The RCU calls now count for the executor and the depth is
  carried over (ARCHITECTURE 6).
* **No section with `rcu_read_unlock()` could be translated**: an
  instruction with an operand-size prefix and a rip-relative operand, deep
  in its call graph, made the whole site fail (TRANSLATOR 2).
* A release that looked at the lock word before releasing (for the exchange
  mark, or for the handoff flag) was replaced before it was measured as
  final: the look can cost a cache transfer on the handover path. The
  sampling counter written in the queue node's line did cost 5 to 15% of
  the plain rate and was moved (`bench/results/kdclaude/README.md`).

## 5c. The mmap lock on kdlock (2026-11-13)

Builds #40-#43 with `CONFIG_KDLOCK_MM`. The kernel's `mm_struct` changes
size, so `kbuild.sh` now also runs `modules_install`; build #40 booted
without it and stopped in emergency mode (`/boot/efi` not mountable,
`module_layout` mismatch).

```
echo 1 > /sys/module/kernel/parameters/kd_mm      # new mms get the kdlock mmap lock
gcc -O2 -pthread -o mm_stress bench/mm_stress.c && ./mm_stress 16 30
python3 bench/run_mmap1.py --out mmap1.jsonl --rounds 2
```

| Check (build #43) | Result |
| --- | --- |
| `mm_stress` (data-checked mmap, munmap, mprotect, mremap, MADV_DONTNEED, malloc, fork; one shared mm), kdlock mms, 4/16/31 threads x 30 s | all checks passed; Native control passed |
| Kernel subtree and module builds run with `kd_mm=1` | built; modules load and pass the API check |
| will-it-scale mmap1, threads and processes, 1-32 workers, 2 rounds | no failed point, no kernel warning; delegated mmap sections 2-3.6 M per point from 4 threads |
| Nano correctness pass | 240 points exact |

`mm_stress` itself had a defect that only showed under load: a thread
refilled a hole with `MAP_FIXED` after another thread could have mapped it.
It failed with Native too and was fixed in the test.

## 5d. Syscall-path lock objects on kdlock (2026-11-13)

Build #45 with `CONFIG_KDLOCK_MM` and `CONFIG_KDLOCK_API` (the VM's
`builtin.sh` enables both). Struct layouts change (`files_struct`, `file`,
pipes, ...), so the TCLock modules and `kd_bench` must be rebuilt
(`tcbuild.sh`) after the kernel.

```
gcc -O2 -pthread -o /root/api_stress bench/api_stress.c
echo 7 > /sys/module/kernel/parameters/kd_api   # new spinlock_t/rwlock_t/mutex objects on kdlock
/root/api_stress setfd 16 20                    # also ofd, pipe, seek, xattr
python3 bench/run_api.py --out api.jsonl --rounds 2
# uts_sem: boot once with kd_uts=1 (grub entry id kdclaude1-uts in /boot/grub/custom.cfg)
grub-reboot kdclaude1-uts && reboot
```

| Check (build #45) | Result |
| --- | --- |
| Whole Ubuntu-config kernel and all modules build with the dispatch | no error, no call site needed a change; only new warnings are stack-frame sizes |
| `api_stress` kd, setfd/ofd/pipe/seek/xattr at 4/16/31 threads x 20 s; uts at 4/16/31 on the `kd_uts=1` boot | all checks passed; setfd/ofd 40-66 M delegated sections per point; no kernel log entries |
| `run_api.py` 1-32 workers, 2 rounds, plus uts on two boots | 120 points, all checks passed (`bench/results/kdclaude/api-20261113/`) |
| `defconfig` subtree build (kernel/ fs/ mm/ lib/) with `kd_api=0` and `kd_api=7` | 808 object files byte-identical; no kernel warning |

## 6. Not tested yet

* Nesting deeper than two levels, and the `KD_MAX_DEPTH` / `KD_MAX_ROOTS`
  limits.
* Forced `MISS_CODE` / `MISS_RET` handback (seen only as learning events),
  `UNLOCK_ANC`, `irq`/`irqsave`/`bh` variants, and an interrupt handler
  taking a lock that a delegated section holds (DIFFERENCES D4).
* Signals during queued spinning for `killable`/`interruptible` (D8).
* CPU hotplug, text patching after publication.
* Whole-kernel lock API switch (`kd_linux_map.h`). Only the mmap lock and
  the six syscall-path objects of KERNEL_INTEGRATION 4b are switchable.
* Switchable objects under NFS/ceph/SMB lock and lease traffic, and the
  `_irq`/`_bh`/`_irqsave` forms on them (built, not exercised by the
  workloads).
* Role exchange when the new holder really sleeps for long (the test bodies
  `yield()` with nothing else runnable), under oversubscription, and for a
  holder that migrates before it releases (the path through the lock word's
  mark instead of the per-CPU hint ran 3 177 + 5 times, as declines and
  withdrawals).
* ww mutexes against a second user in the same class holding locks for long,
  and `kd_mutex_lock_io` accounting.
* Sections that update other task fields non-atomically
  (`pagefault_disable()`, `migrate_disable()`); only the RCU depth is
  carried over.

## 7. Rules

* No performance claim without a matched native run on the same kernel, VM and
  call shell; no pooling across kernels, source versions or call shells.
* Report the execution class (delegated / handed back / local) with every
  rate.
* One round gives no variance claim.
* Do not touch the original VM on `10.176.26.71` while another agent works
  there.
