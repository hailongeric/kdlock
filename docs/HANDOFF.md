# Handoff: state of the work and what comes next (2026-11-19)

Written when the work moved from 380G10 to the cloud host (96.44.157.161,
`/root/kdlock`) so that a new session can continue without the previous
one's context. Machines and access: [../MACHINES.md](../MACHINES.md). Rules:
[../AGENTS.md](../AGENTS.md). This file is a snapshot; the guides and the
result READMEs it points to are the maintained record.

## 1. Where things are

* **Source of truth:** `/root/kdlock` on the cloud host, a copy of 380G10's
  repository including `.git` (every branch, tag and `refs/archive/*`).
  `master` = this commit (it follows `a61af664`). The copy on 380G10 is
  frozen; do not edit it.
* **Remote:** `origin` is `github.com/hailongeric/kdlock`; nothing was
  pushed there by these sessions. Pushing needs the user's word.
* **Worktrees:** `git worktree list` shows about 117 entries with paths on
  380G10 (`/tmp/...`, `kdlock-main`, `.claude/worktrees/lkp-macro`). They do
  not exist on the cloud host; their branches are all in the refs. Leave the
  entries (AGENTS.md forbids pruning without the user).
* **Other branches worth knowing:**
  * `lkp-macro` (`338989d9`, 10 commits on top of an older master): a
    second session's study of lkp-tests workloads as kdlock macro
    benchmarks (`bench/results/kdclaude/lkp-macro-20261118-64cpu/` on that
    branch: analysis, plan, screening on kdall10/kdnat9, an allow list from
    the discover pass). Not merged. That session found the per-CPU lock
    byte failure independently. It planned to redo its delegated lkp runs,
    with a native baseline in the same boot, on a kernel carrying both
    fixes of section 3: that is `kdall13`.
  * `main` (`8309b0a0`) has diverged from `master` (an older line of work,
    "original main"); `master` is the maintained branch.
* **VM state at the handoff:** booted into `7.0.0-38-kdall13` (one-shot);
  GRUB's default stays `kdlock1`. The guest has kdall1-7, kdall9-13 (with
  kdall11d/11e) and kdnat1-6, kdnat8-9 installed (BUILD_AND_TEST.md table). Nothing is running there.

## 2. How work is done (from the cloud host)

1. Edit and commit in `/root/kdlock`.
2. Sync to A while the VM is idle (MACHINES.md has the rsync lines).
3. In the VM (`ssh kd-vm`, guest shell is **zsh**: run anything with word
   splitting as a bash script):
   * kernel: `bash /root/host_fs/kdlock/bench/vm/buildk.sh kdallNN out3`
     (about 10-20 min; output ends with `BUILDK_DONE`), then
     `grub-reboot 'gnulinux-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961>gnulinux-7.0.0-38-kdallNN-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961' && sync && reboot`.
     `grub-reboot` must come before `sync`, or a forced restart boots
     kdlock1.
   * bench module for the booted kernel: copy `bench` and `include` to
     `/root/kdb` and `make -C /mnt/kdlock-builds/kda/out3 M=/root/kdb/bench
     modules`, `insmod kd_bench.ko` (`/dev/kdbench`).
   * daemon: `cd /root/host_fs/kdlock/jit && setsid nohup
     /root/kdvenv/bin/python -u kd_daemon.py --state FILE --allow LIST -v >
     LOG 2>&1 < /dev/null &`, stop with `kill -INT`. Allow lists:
     `bench/allow/{api,torture,mm,kd_bench}.txt`. **A daemon that exits
     leaves its images loaded**: to compare translators in one boot drop
     the previous daemon's sites first
     (`bench/results/kdclaude/appgrid-20261118-64cpu/drop_sites.py STATE`).
     A fresh state file needs warm-up passes until misses stop
     (`fix_ab.sh` does it); a reused one converges at once.
   * helpers: `bench/vm/dis.sh SYM START END` (disassembly of the kdall
     vmlinux), `bench/vm/kdsym.py ADDR...` (addresses to symbol+offset),
     `jit/kd_dryrun.py FUNC...` (build images without loading; prints the
     per-CPU frontiers and region counts).
4. A hung guest: on A, set `grub-reboot` first if the guest still answers,
   then `echo quit | nc -U -N /tmp/qemu-claude-monitor.sock`,
   `~/vm/qemu-scripts/run_claude_vm.sh start`, then `pin`.
   `bench/results/kdclaude/appgrid-20261118-64cpu/drivers/repro_drive.sh`
   does all of it for a reproduction (`KERNEL=`, `CYCLES=`).
5. Before measuring: the host CPU frequency on A is fixed at 2.7 GHz with
   turbo on (`/sys/devices/system/cpu/intel_pstate/no_turbo` = 0,
   `scaling_min_freq` = `scaling_max_freq` = 2700000); it does not survive a
   host reboot, so check it. `sync` in the guest before anything that may
   take it down (a panic once left freshly built `.ko` files empty).
   TCLock's spinlock with more than one worker per CPU panics the guest;
   `run_oversub.py` skips it.

## 3. What was done in the last sessions (2026-11-17 to 2026-11-19)

* **Whole kernel against native** (`kdall-native-20261117-64cpu`,
  `787264dc`): mmap1 at 64 threads 2.06x native with delegation; plain-mode
  analysis; mutex plain-mode rules (`f9d7c9fe`), rwsem era bound
  (`2cf73c74`), `KD_QF_WOKEN` (`0eb98634`).
* **Full grid on kdall10/kdnat9** (`appgrid-20261118-64cpu`, `5baeb07f`,
  `8564d29d`): nano c01/c08 of every family at 1-8 and 12-64 workers with
  TCLock; will-it-scale (without the project's own variants); FxMark,
  Psearchy, Metis, LevelDB as TCLock runs them; Apache in the process
  mode of the interval-skiplist paper. Across nodes kd is ahead of native in
  every nano profile (1.14-5.53 delegated); mmap1 1.61-2.18 and brk1
  1.88-2.85 at 36-64 with delegation, Apache single process 1.28-1.41;
  losses in page_fault1/3 at 1-32 threads, page_fault2, LevelDB readrandom
  at 64 (README sections 3-4).
* **Two failures found in that grid and fixed** (README section 8):
  1. `a26a8578`: a delegated munmap with the kept downgrade left the mmap
     lock write-held, and Apache's exiting workers hung. Cause: after a
     resumed nested acquisition `kd_exec_one()` kept the other combiner's
     verdict, so a later miss looked like a completion. Release assertions
     added in `kd_rwsem.c`. Fixed: 20/20 Apache cycles clean.
  2. `3a909d50`: a handback inside a per-CPU local trylock region left the
     executor's lock byte set (memcg `obj_stock`, 57 of 64 CPUs after brk1).
     The translator now walks per-CPU regions (TRANSLATOR.md section 3a):
     own-function exits make the identity read a frontier, deeper exits stay
     flagged (`KD_X_REGION`) and are counted when taken with the region open
     (`hb_region`); region code is decoded fully so regions do not miss;
     `max_insns` default 250000. Fixed: 0 of 64 bytes after every delegated
     workload; in one boot the previous translator set 46 of 64.
  * `a61af664`: verification data and scripts; an in-boot A/B on kdall13 of
    kd off, the new translator and the previous one (both converged): new/old
    mmap1 1.03, brk1 1.14-1.24, mmap2 0.91-1.01, page_fault1 0.99-1.04 (the
    old column includes its own per-CPU damage). Correctness on kdall13:
    locktorture 6/6, run_corr plain and delegated 442 points 0 failed,
    test-ww_mutex, mm_stress 16/32/64, 0 kernel complaints.

## 4. What is next, in order

1. **Rerun the measurement grid on kdall13: done 2026-11-19**
   (`bench/results/kdclaude/appgrid-20261119-64cpu/`, round g2: kdall13
   and its native twin `kdnat10`, 14 worker counts and one round at the
   user's request). No kernel complaint, no fatal signal, the per-CPU lock
   bytes at 0 of 64 after every benchmark of kd on, Apache's default
   configuration measurable with `kd_vdown=1`. Its open points: brk1 at 2
   workers (1.6 M in both kd modes, 1.0 M native), FxMark MRDM on below
   off at 48-56 workers with nothing delegated.
2. **`hb_region` precision.** It is an upper bound (684 in the A/B's new
   mode with no damage): an inner lock held at a flagged exit counts too.
   Separating the two (for example the translator also recording the region
   level expected at each flagged exit) would let a run state "0 region
   exits" instead of "no visible damage".
3. **Per-CPU limits** (TRANSLATOR.md 3a): far exits are not proven
   unreachable; reporting paths are stepped over by name (`_REPORT`); the
   balanced-callee and helper rules are structural, not value-based.
   Options: let the daemon turn a region start into a frontier when the
   kernel reports a `KD_X_REGION` handback (adaptive), or a narrow return
   value correlation for trylock helpers. Images grew (mm sites 45-65 k
   instructions); measure build time and whether `pcpu_walk_depth` 3 keeps
   the bytes clean.
4. **lkp-macro**: the branch is merged into `master` (2026-11-19). Its
   second round, `bench/results/kdclaude/lkp-macro-20261119-64cpu/`, adds
   the applications and file systems the first one left out and repeats
   the measurements on kdnat10 and kdall13; its README section 5 has the
   state.
5. **Open losses** from the grid: page_fault1/3 at 1-32 threads,
   page_fault2, LevelDB readrandom at 64, Apache single process without
   delegation at 36-64. Not profiled yet.
6. **Whole-kernel steps** (AGENTS.md goal): images that follow runtime text
   patching (step 2), then delegation lock user by lock user from allow
   lists (step 4). Step 3 (per-CPU classification) now has the region
   analysis above.

## 5. Things that cost time before

* zsh in the guest: `echo ====` fails, unmatched globs abort, `$var` does
  not split.
* `pgrep`/`ps` can block on a process whose mmap lock is stuck (they read
  `/proc/PID/cmdline`); use `/proc/*/comm` and `/proc/*/stat`.
  `pkill -f` matches the ssh command line that runs it.
* Long waits: poll with a loop in the background, never a long foreground
  sleep; a remote timeout does not prove the remote command ended.
* tracefs kprobes refuse kd functions (notrace); a small module counting
  calls was used instead.
* The guest's apt goes through a proxy that blocks it; fetch `.deb` files
  elsewhere with URLs from `apt-get --print-uris`.
* capstone decodes the kernel's WARN `ud1` (`67 48 0f b9 3a`) one byte
  short; the translator's region walk accounts for it (`_ud1_end`).
