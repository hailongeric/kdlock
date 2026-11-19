# lkp-tests workloads as kdlock macro benchmarks: analysis and plan

> **Baseline caveat (found 2026-11-19).** The native kernel of this round
> was built without `CONFIG_PARAVIRT_SPINLOCKS`. In a KVM guest such a
> kernel leaves `virt_spin_lock_key` on and every contended native spinlock
> (and with it the native rwlock's writer queue) is a test-and-set lock,
> not the queued one; `nopvspin` does not change that without the option.
> Every "native" figure here that depends on a contended spinlock or rwlock
> is therefore against a slower lock than bare-metal Linux runs: ratios of
> kd spinlock and rwlock cases, lock1, the FxMark directory cases and the
> like overstate kd. Cases whose contention is on a mutex or an rwsem (the
> mmap lock) are much less affected. The corrected twins are kdnat11 and
> later; see
> [../plain-20261119-64cpu/](../plain-20261119-64cpu/README.md) section 1.

Started 2026-11-18. The goal is a macro benchmark set for kdlock built from
workloads of the Linux kernel performance suite (lkp-tests,
`https://github.com/intel/lkp-tests`, commit `50c5f0e`): unchanged
applications whose throughput depends on kernel locks that kdlock replaces.

**The measure of success is kd with delegation against native Linux**
(the user's goal, 2026-11-18): a workload is worth keeping when kd "on"
(the daemon running with allow lists) runs faster than the native twin,
with the delegated sections and handbacks reported for every rate. Plain
mode ("off") is measured as well, as the reference that separates what
delegation adds from what node order and eras already give.

This document has three parts:

1. the analysis: which lkp workloads stress which kernel locks;
2. the plan: how candidates are screened and the set is chosen;
3. the results, added as the experiments run (section 6 onwards).

Target: the kdclaude VM (64 vCPUs as 2 nodes of 32, 24 GiB, host at
2.7 GHz), kernels `7.0.0-38-kdnat9` (native locks) and `7.0.0-38-kdall10`
(every lock a kdlock, `787264dc`), as in
`../kdall-native-20261117-64cpu/`, section 8.

## 1. What makes a workload useful here

A workload belongs in the set when all of the following hold:

1. **Kernel time is concentrated on locks kdlock replaces.** With
   `CONFIG_KDLOCK_ALL` that is every `spinlock_t`, `raw_spinlock_t`,
   `rwlock_t`, `struct mutex`, `ww_mutex` and `rw_semaphore`. Not replaced,
   and so not a target: `rt_mutex`, seqcounts, RCU, atomics and reference
   counts, bit locks (`folio_lock`, `bit_spin_lock`), and per-VMA locks
   (a reference count, not a kdlock). `percpu_rwsem`, `semaphore` and
   `local_lock` are built on replaced locks and inherit them. `lockref` (the
   dentry reference count) keeps its cmpxchg fast path
   (`arch_spin_value_unlocked` is provided) and falls back to the
   replaced `d_lock`.
2. **The lock is shared by the workers.** Many lkp tests run one private
   object per worker (a file, a pipe, a process); those measure the
   uncontended path only, which is useful as a cost check but cannot show
   what delegation or node order do.
3. **It runs here.** No real disks (the VM has none to spare: file systems
   go on tmpfs or a RAM block device), no remote hosts, no hardware
   features the VM lacks, at most about 20 GiB of memory.
4. **It is repeatable** within a few percent in one boot, with a run time
   of seconds to a minute per point.
5. **Its contended sections can be delegated.** Delegation runs a waiter's
   section on the combiner from a translated image, so the gain needs:
   - a lock family that delegates: spinlock, rwlock writers, mutex, rwsem
     writers (LOCKS.md). Raw spinlocks (run queues, `pi_lock`), readers
     and ww mutexes never delegate; workloads bound on them can only gain
     from plain mode;
   - short sections that stay on the combiner: a call that can sleep, a
     user copy that faults, a TLB shootdown, or code the translator has
     not learned ends the delegation there (a handback,
     TRANSLATOR.md). Sections that hand back often lose (pipe in
     `../kdall-native-20261117-64cpu/`, bad case 4);
   - lock users that can be put on an allow list (`bench/allow/`,
     AGENTS.md goal step 4), found with the daemon as `api.txt` was.

What kdlock can change once a lock is contended: plain mode (node order of
the sleepable queues, eras of the reader-writer families, the spin queue)
helps when native collapses across the two nodes; delegation helps when the
critical sections are short, do not sleep, and their lock users are
allow-listed. What delegation gained so far, against native at 64 threads
(same README, section 8.7): setfd (`files->file_lock`) 9.65x, ofd
(`flc_lock`) 8.04x, uts (`uts_sem` writers) 5.21x, mmap1 / mmap2 / brk1
(mmap lock writers) 2.06x / 1.83x / 2.12x.

## 2. lkp-tests at a glance

357 programs and 169 job files. By what they measure:

| group | programs | here |
|---|---|---|
| kernel scalability micro/macro benchmarks | will-it-scale, vm-scalability, stress-ng, aim7, aim9, reaim, unixbench, hackbench, perf-bench-* (futex, sched-messaging, sched-pipe, numa-mem, syscall), ebizzy, pft, tlbflush, schbench, lmbench3, exit-free, bust-shm-exit, sysbench-*, simoop | **candidates** (section 3) |
| file system benchmarks | fsmark, fxmark, dbench, filebench, postmark, iozone, fio, blogbench, sysbench-fileio | candidates on tmpfs or a RAM disk; fxmark is already in `../appgrid-20261118-64cpu/` |
| servers and databases | apachebench, httpd, siege, memcached/mutilate/memtier, redis, nginx/php (phpbench), pgbench, mysql/oltp, rocksdb, cassandra, mongodb, ycsb | later, after section 4: setup heavy; Apache and LevelDB are in the appgrid round |
| network | netperf, iperf, uperf, tbench, sockperf, netpipe, nuttcp, qperf, thrulay | loopback only (tbench, netperf, sockperf) |
| builds | kbuild, kernbench, makepkg | broad mixture, long; one point as a sanity check |
| compute, memory bandwidth, crypto, compression | coremark, linpack, stream, hpcc, openssl-speed, pigz, pixz, pbzip2, plzip, lz4, tinymembench, simd-stress, tcrypt | no: no kernel lock on the hot path |
| functional and stress testing | ltp, xfstests, kselftests, kunit, blktests, trinity, perf-fuzzer, locktorture, rcutorture, rcuscale | no as benchmarks (locktorture is already in the suite) |
| power, boot, hardware, monitors | suspend, idle, cpufreq, mce, nvdimm, pm-qa, turbostat, the monitors (vmstat, perf-profile, lock_stat, ...) | no |

## 3. Candidates by lock

For each kernel lock class, the lkp workloads that contend it, with the
job parameters lkp uses. "thread" and "process" are will-it-scale's two
models; in process mode each worker has its own mm and files, so only locks
on shared kernel objects (one directory, one file, global locks) are
contended.

### 3.1 `mm->mmap_lock` (rwsem; brk, mmap and munmap already delegated)

| workload | lkp job | what contends |
|---|---|---|
| will-it-scale mmap1, mmap2, brk1, brk2, malloc1 (thread) | `will-it-scale-part{1,2}` | writers: mmap/munmap/brk of one mm |
| will-it-scale page_fault1/2/3, tlb_flush1/2/3 (thread) | `will-it-scale-part3,4` | faults that fall back from per-VMA locks to the read side; madvise under the read side with TLB shootdowns |
| vm-scalability `*-mt` (anon-w-rand-mt, anon-cow-rand-mt, mmap-pread-*-mt, small-allocs-mt, msync-mt, mremap-xread-rand-mt) | `vm-scalability` | faults and VMA changes of one mm; also the page allocator and LRU (3.4) |
| ebizzy | `ebizzy` (200% threads, 10 s) | malloc/free of large chunks: mmap/munmap and faults, the classic mmap lock test |
| pft (threads) | `pft` | page faults of one mm |
| tlbflush (lkp's own) | `tlbflush` (200%, 512 entries) | madvise and TLB shootdowns |
| stress-ng mmap, mmapfork, mmaprandom, mmapmany, mmaptorture, munmap, mremap, mprotect, madvise, vma, brk, stackmmap, msync | `stress-ng-part1/2/5` | VMA changes of one mm (per stressor instance, one process each; contention only inside an instance with threads, e.g. vma, mmaptorture) |

Already measured in this repository: mmap1, mmap2, brk1, page_fault1-3.
New here: tlb_flush, malloc1, brk2, vm-scalability, ebizzy, pft.

### 3.2 VFS: directories, dentries, inodes, file tables

| lock | kd family | workloads |
|---|---|---|
| directory `i_rwsem` (create, unlink, rename in one directory) | rwsem | will-it-scale open1, unlink1 (thread and process: one directory); stress-ng dentry, dir, link, rename, unlink, getdent, filerace; fsmark, dbench, aim7 creat-clo, fxmark MWCM/MWUM |
| file `i_rwsem` (writers to one file) | rwsem | will-it-scale pwrite2/pwrite3, writeseek2/3 (same file); aim7 disk_* on one file system; fallocate |
| `d_lock` (lockref fallback), `inode->i_lock`, `sb->s_inode_list_lock`, `inode_hash_lock` | spinlock | will-it-scale open3 (one file), open1/unlink1 (inode lists); stress-ng dentry, inode churn |
| `files->file_lock` | spinlock (CONFIG_KDLOCK_API object, delegated in `api.txt`) | will-it-scale dup1, open1-3 (thread); stress-ng dup, close, fdfork |
| `file->f_pos_lock` | mutex (delegated in `api.txt`) | will-it-scale lseek2, readseek2/3, writeseek2/3 when the fd is shared (thread) |
| `file_lock_context.flc_lock` | spinlock (delegated in `api.txt`) | will-it-scale lock2 (same file), stress-ng flock, fcntl, lockf, lockofd |
| file system journal (`j_state_lock` rwlock, `j_list_lock`), allocator locks | rwlock, spinlock | aim7 disk_rw/disk_rr/sync_disk_rw on ext4/xfs on a RAM disk; fsmark; dbench |

### 3.3 Processes, signals, IPC

| lock | kd family | workloads |
|---|---|---|
| `sighand->siglock` | spinlock | will-it-scale signal1 (thread); stress-ng signal, sigq, kill, sigpending |
| `tasklist_lock` | rwlock | fork/exit/exec: stress-ng fork, vfork, clone, exit, spawn, zombie, wait; unixbench spawn, execl, shell; aim9 fork_test, exec_test; reaim high_systime; hackbench (process mode, setup) |
| pid allocation (`pidmap_lock`), `css_set_lock`, `mm->mmlist` | spinlock | the same fork/exit workloads |
| futex hash bucket `hb->lock` | spinlock | will-it-scale futex1-4, pthread_mutex1/3/4/5, posix_semaphore1 (thread: one futex word); perf-bench-futex hash, wake, wake-parallel, requeue, lock-pi (also `pi_lock`, raw); sysbench-mutex, sysbench-threads; stress-ng futex, mutex |
| SysV IPC (`sem_lock`, `ipc_ids.rwsem`, `shm`), POSIX mq | spinlock, rwsem | stress-ng sem, semsysv, msg, mq, shm, shmsysv; bust-shm-exit; reaim shared |

### 3.4 Memory management below the address space

| lock | kd family | workloads |
|---|---|---|
| `lruvec->lru_lock` | spinlock | vm-scalability lru-file-*, lru-shm, anon-*; will-it-scale page_fault2/3 |
| `zone->lock` (page allocator refills and frees) | spinlock | vm-scalability anon-w-*, exit-free (freeing tens of GiB), will-it-scale page_fault1, malloc1 |
| `mapping->i_mmap_rwsem`, `anon_vma` rwsem | rwsem | will-it-scale mmap2, page_fault3, tlb_flush3; vm-scalability mmap-*, truncate; fork-heavy tests (anon_vma) |
| `i_pages` xa_lock | spinlock | vm-scalability lru-file-*, truncate, shm-* |
| split PTE lock | spinlock | page faults on one page-table page (`../pfshared-20261116-64cpu/`, not lkp) |

### 3.5 Scheduler, wakeups, pipes and sockets

| lock | kd family | workloads |
|---|---|---|
| run queue `rq->__lock`, `p->pi_lock` | raw spinlock (never delegated) | hackbench (pipe and socket, process and thread, 100% and 1600% tasks); perf-bench-sched-messaging, -pipe; will-it-scale context_switch1, sched_yield; schbench; unixbench context1, pipe |
| wait queue heads (`wq_head->lock`) | spinlock | eventfd, pipes, sockets, epoll: will-it-scale eventfd1, pipe1, unix1, poll; stress-ng epoll, eventfd, pipe, pipeherd |
| `pipe->mutex` | mutex (delegated in `api.txt`) | hackbench pipe, stress-ng pipe, pipeherd, splice, tee, vmsplice |
| socket lock (`sk_lock`), unix socket `u->lock` | spinlock and its owned mode | hackbench socket, stress-ng sock, sockpair, unix; tbench and netperf on loopback |

### 3.6 Excluded within the scalability group

- Per-worker objects only (useful as uncontended cost checks, not as
  macro benchmarks): will-it-scale getppid1, read1, write1, pread1, pwrite1,
  lseek1, readseek1, writeseek1, open2/unlink2 in process mode, pipe1,
  unix1, eventfd1, poll1/2, fallocate1/2, futex1/3 in process mode.
- aim9 and unixbench arithmetic, string, sort and FPU tests.
- vm-scalability swap and hugetlb jobs (swap devices, 1 TiB sizes).
- `lock_stat`: needs `CONFIG_LOCK_STAT`, which `kernel/Kconfig` refuses.

### 3.7 Ranking for the goal: kd with delegation faster than native

Expected from the lock family and what runs inside the section; phases 1-3
check it.

**Tier A: a delegable lock, short sections without sleeping or user
access, lock users like those already allow-listed.**

| workload | lock | lock users (allow list) |
|---|---|---|
| will-it-scale dup1, open1, open3 (thread) | `files->file_lock` | `alloc_fd`, `file_close_fd` (`api.txt`) |
| will-it-scale lock2 (thread and process), stress-ng flock, fcntl, lockf, lockofd | `flc_lock` | `posix_lock_inode`, `posix_test_lock` (`api.txt`); flock and OFD users new |
| will-it-scale mmap1, mmap2, brk1, brk2, malloc1 (thread), ebizzy, vm-scalability small-allocs-mt | mmap lock writers | brk, mmap, munmap (`mm.txt`) |
| will-it-scale signal1 (thread), stress-ng signal, sigq, kill | `sighand->siglock` | new: signal send and dequeue paths |
| will-it-scale futex1/2, pthread_mutex1/3/4, posix_semaphore1 (thread); perf bench futex hash, wake, wake-parallel; stress-ng futex | futex `hb->lock` | new: futex wait queueing and wake |
| stress-ng sem, semsysv, msg, mq | SysV/POSIX IPC spinlocks | new |

**Tier B: delegable, but the sections may sleep or touch user memory, so
handbacks decide.**

| workload | lock | why uncertain |
|---|---|---|
| will-it-scale pwrite2/3, writeseek3, fallocate (one file) | file `i_rwsem` writers | page cache allocation and user copies inside |
| will-it-scale unlink1, open1 create path; stress-ng dentry, dir, link, rename; fsmark, dbench, aim7 creat-clo | directory `i_rwsem` writers | inode and dentry allocation, journal |
| will-it-scale tlb_flush1-3 (madvise) | mmap lock readers, TLB shootdowns | readers never delegate; shootdowns are frontiers |
| vm-scalability lru-*, truncate, exit-free | `lru_lock`, `zone->lock`, `i_pages` | short sections, but taken from many call sites inside larger operations |
| hackbench pipe, stress-ng pipe, pipeherd | `pipe->mutex` | the user copy hands back (bad case 4 of the native comparison) |

**Tier C: bound on locks that never delegate; plain mode only.**
hackbench socket, perf bench sched messaging and pipe, will-it-scale
context_switch1 and sched_yield, schbench (run queue locks, `pi_lock`);
page faults that fall back to the mmap lock read side; fork, exec and exit
(`tasklist_lock` is an rwlock: its writers delegate, its readers do not).

## 4. Plan

### 4.1 Build (no guest network)

Sources are fetched on 380G10 into `/home/eric/vm/vm-shared/lkpbench`
(lkp-tests itself for the job parameters, will-it-scale, vm-scalability,
stress-ng, rt-tests for hackbench, byte-unixbench, pft, schbench, fs_mark,
dbench, ebizzy 0.3, AIM7 s7110 and re-aim 7.0.1.13, lkp's tlbflush.c), and
built in the guest in `/root/lkpbench`. perf bench comes with the guest's
perf. Missing packages are installed from `.deb` files fetched on the host
(`apt-get install --print-uris` in the guest).

lkp's own harness (`lkp install`, `lkp run`) is not used: it installs
packages over the network and expects its own rootfs. The commands below
reproduce the job parameters directly.

### 4.2 Phase 1: screening on native (kdnat9)

For every candidate of section 3, at 16 workers (one node) and 64 (both
nodes), one run of 10 s each (`screen.sh`):

- the rate the benchmark reports;
- at 64 workers, a 5 s flat profile (`perf record -a`, no call graphs) and
  the context switches (`perf stat`);
- the **lock share**: the samples in native lock code
  (`native_queued_spin_lock_slowpath`, `queued_read/write_lock_slowpath`,
  `osq_lock`, `mutex_spin_on_owner`, `__mutex_lock*`,
  `rwsem_spin_on_owner`, `rwsem_down_*_slowpath`, `rwsem_optimistic_spin`,
  `_raw_spin_lock*`, `_raw_read_lock*`, `_raw_write_lock*`) over all
  samples, and the idle share (threads asleep in a lock wait show up as
  missing samples, `../kdall-native-20261117-64cpu/` section 8.5).

A candidate passes when its lock share at 64 workers is at least 10%, or
its rate at 64 workers is below its rate at 16 (native collapse across the
nodes), or it sleeps in locks for at least a quarter of the time. Tier A
and B candidates (3.7) that pass go on; tier C ones are kept only as plain
mode references.

### 4.3 Phase 2: kd without delegation (kdall10 off)

The candidates that pass, same points, plus the kd flat profile and kd
counters. Result: kd off against native per candidate, with the kd lock
functions' share. This separates what plain mode already gives.

### 4.4 Phase 3: delegation for the new lock users (the main phase)

1. **Find the lock users.** Each candidate once with the daemon and an
   empty allow list (`kd_daemon.py -v`, its own state file), as `api.txt`
   was made: the sites the kernel requests are the contended lock users.
2. **Keep the delegable ones** in `bench/allow/lkp.txt`: sections that the
   learning pass shows ending at their release, not at a frontier or a
   miss; one comment line per lock, as in `api.txt`.
3. **kd on against native and kd off** at 16, 32 and 64 workers, with the
   allow lists api, torture, mm and lkp, after a learning pass; delegated
   sections, sessions and handbacks (frontier and miss) per point.
4. **Where handbacks eat the gain** (tier B), find the frontier or the
   miss from the daemon log and decide: a missing translator capability
   is a change of its own with its tests (TRANSLATOR.md); a call that can
   sleep inside the section stays a handback, and that lock user leaves
   the allow list.

Result of the phase: per candidate, on/native and on/off, and for each
gain the lock users that produce it.

### 4.5 Phase 4: the macro benchmark set

The workloads where kd on beats native in phase 3, together with the tier
B and C cases that show the limits, about 10-15 in all, each with its lkp
parameters. Full worker grid (1-8, then every fourth to 64), native, kd
off and kd on, 3 boots each, in the format of
`../kdall-native-20261117-64cpu/suite.sh` so the existing tables apply.
Workloads where kd on loses stay in the set and are reported with their
cause, as the bad cases of the native comparison were.

### 4.6 Rules for the runs

- Kernels kdnat9 and kdall10 only, one-shot `grub-reboot`; the GRUB
  default stays kdlock1.
- The VM is shared with the session running `../appgrid-20261118-64cpu/`:
  no guest access until it reports the VM idle, and none of its files
  (`/root/appbench`, `/root/appgrid`, `/root/kds_cmp.json`, `/root/tc`,
  `/root/kdbt`) are touched. This round uses `/root/lkpbench`,
  `/root/lkpres` and its own daemon state `/root/kds_lkp.json`.
- One run per point in phases 1-3: they choose candidates, they are not
  results. Performance claims come from phase 4 (matched runs, 3 boots).
- `sync` before any run that may take the guest down.
- No core dumps (`ulimit -c 0`; a dump into apport hung a reboot in the
  appgrid round) and `kernel.print-fatal-signals=1`: every fatal signal of
  a benchmark process is in the kernel log and is reported with the run.
  The appgrid round saw a page_fault2 process die at exit on kdall10,
  under investigation there; a fatal signal on kdall10 that native does not
  show counts as a correctness failure, not as noise.

## 5. Status

| step | state |
|---|---|
| analysis (sections 1-3) | done |
| sources on the host, build in the guest | done (all but re-aim: its configure fails, AIM7 covers its file system tests) |
| phase 1 native, phase 2 kd off | done, one boot each (section 6) |
| phase 3 discover, allow list, kd on | done once; kd on is partly invalid, see section 7 |
| a per-CPU state bug found by phase 3 | located, not fixed (section 7) |
| phase 4 | waiting for the fix |

## 6. Screening results (s1, one run per point)

Kernels kdnat9 (native) and kdall10 (kd), 16 and 64 workers, 10 s per
point, one boot per mode (`screen.sh`, `data/screen.txt`, profiles in
`data/prof/`). No kernel complaint and no fatal signal of a benchmark
process in any of them.

- `data/s1-native-off.md`: native rates, native lock share at 64 workers,
  kd off / native (`screen_summary.py`).
- `data/s1-off.md`: the kd profiles.
- `data/s1-on.md`: native, kd off and kd on with delegated sections,
  sessions and handbacks per point (`on_summary.py`); kd on with
  `kd_vdown=0` (`data/s1-on.knobs`) and the allow lists api, torture, mm
  and `bench/allow/lkp.txt`, after a learning pass.
- `data/discover/`: the contended lock users per candidate, from the
  discover pass (empty allow list), which `bench/allow/lkp.txt` was made from.

"Busy" and the lock share are only meaningful where the benchmark ran
longer than the profile window; AIM7, fs_mark, hackbench and the
vm-scalability cases were over before it.

### 6.1 Where native is lock-bound

Native spends 86-97% of its time in `queued_spin_lock_slowpath` at 64
workers in will-it-scale signal1, dup1, lock2, open1, open3, readseek2,
pread2 and pthread_mutex1/3/4, and in stress-ng zombie and shm; 97-99% in
the rwsem/mutex spin (`osq_lock`) for brk1/2, mmap1/2, unlink1, pwrite2/3,
writeseek3 and vm-scalability small-allocs. Most of these run slower at 64
workers than at 16 (signal1 0.38, dup1 0.41, lock2 0.38, open1 0.36).

### 6.2 kd without delegation against native (64 workers)

| | kd off / native |
|---|---|
| far ahead | signal1 3.06, dup1 3.27, lock2 3.38, open1 2.87, open3 3.36; stress-ng zombie 3.59, mremap 3.52, shm 2.60, unlink 2.23 |
| ahead | brk1/2 1.88, mmap1/2 1.63-1.66, readseek2 1.60, pread2 1.48; stress-ng rename 1.68, open 1.67, vfork 1.67, dentry 1.51, shm-sysv 1.47; fs_mark 1.44 |
| behind | pthread_mutex1/3/4 0.55-0.57 (futex bucket); process-mode lock2 0.38; hackbench socket 0.44-0.46, stress-ng sock 0.52, perf sched messaging 0.61; pwrite3 0.76, writeseek3 0.84; stress-ng epoll 0.76 |

### 6.3 kd with delegation against native (64 workers)

Valid for the lock users that do not allocate memory (section 7):

| workload | native | kd on | on/native | delegated sections, handbacks |
|---|---|---|---|---|
| will-it-scale lock2 | 655 k | 4.87 M | **7.44** | 78.6 M, 121 |
| will-it-scale dup1 | 328 k | 2.42 M | **7.37** | 76.5 M, 214 |
| will-it-scale open3 | 336 k | 2.36 M | **7.02** | 74.7 M, 129 |
| will-it-scale open1 | 331 k | 2.32 M | **7.00** | 73.6 M, 84 |
| stress-ng zombie | 372 k | 2.24 M | **6.02** | 13.2 M, 115 |
| stress-ng shm | 1196 | 5144 | **4.30** | 25.9 M, 232 |
| will-it-scale signal1 | 182 k | 515 k | **2.83** | 20.4 M, 1987 |
| vm-scalability small-allocs | 19.8 M | 52.0 M | **2.62** | 13.9 M, 77 |
| unixbench execl | 29 k | 40 k | **1.38** | 27.9 M, 131 |

The first four are `files->file_lock` and `flc_lock` users already in
`api.txt`; zombie is `tasklist_lock` (`__do_sys_setpgid`), shm the tmpfs
quota lock (`dquot_add_space`), signal1 `siglock`, small-allocs and execl
`i_mmap_rwsem` writers. At 16 workers the same lock users give 2.3-3.3
(file locks, zombie) and 1.38 (signal1).

Where delegation does not help (yet):

- mmap1/2, brk1/2: on/native 0.87-1.04. With `kd_vdown=0` every munmap
  section is handed back at its downgrade (sessions = handbacks); with
  `kd_vdown=1` they were 2.06 in the native comparison, but that setting
  leaks the mmap lock (appgrid round, open).
- pread2, readseek2: 1.45 M handbacks at a frontier in `folio_wait_bit`
  (the section sleeps on a folio): on/off 0.33-0.38. Those two lock users
  leave the allow list.
- pthread_mutex1/3/4: on = off (0.57 of native): the futex bucket sections
  are delegated (5.6 M) but do not beat native's lock here.
- stress-ng shm-sysv: 475 k handbacks at misses.

## 7. A per-CPU state bug in delegation

The kd on pass ran slower than kd off on memcg-heavy stress-ng and
hackbench tests by 2-5x and on stress-ng dup by 240x, although they
delegated almost nothing. It was not the daemon: in the same boot, kd off
was as slow (`chk1`, `chk2` in `data/screen.txt`), and from a fresh cgroup
as well. In a fresh boot, kd off ran fast again, and after a delegated
pass the same boot stayed slow (`data/bisect/degrade.out`):

| stress-ng, 64 workers, kd off | fresh boot | after a delegated pass |
|---|---|---|
| dup | 3.61 M | 27.6 k |
| msg | 27.6 M | 9.2 M |
| epoll | 1.09 M | 0.51 M |
| eventfd | 5.05 M | 2.39 M |

The profile of the slow runs is memcg object accounting:
`refill_obj_stock` and `obj_cgroup_charge_account` take 50-54% (6-8% when
fast).

**Bisection by allow list** (`tools/bisect.sh`, a fresh boot per step,
`data/bisect/`): api, torture and mm alone are clean; of `lkp.txt`, the
half with the file system users triggers it; within it, the page wait
queue users, the quota user, `shmem_file_write_iter` and
`filename_unlinkat` are clean, and **`path_openat` alone triggers it**.

**The state left behind** (`tools/pcpu.py` reads per-CPU memory through
`/proc/kcore`): memcg's per-CPU object stock is guarded by a
`local_trylock_t`, whose `acquired` byte lives in per-CPU memory. A fresh
boot has it clear on every CPU. After one 10 s run of will-it-scale
unlink1 with only `path_openat` delegated (3856 handbacks, all at misses),
it was set on 14 of 64 CPUs, with no task inside (`data/bisect/stuck.out`);
after the full kd on pass, on 28. On those CPUs every later charge fails
the trylock and takes the slow path, for every task, for the rest of the
boot.

**Mechanism.** A delegated section runs on the combiner's CPU; per-CPU
accesses in it go to the combiner's CPU (ARCHITECTURE: only the three
task-identity symbols are the waiter's). `path_openat` creates an inode
under the directory lock, and the slab allocation's memcg hook takes the
combiner CPU's `obj_stock` lock (sets `acquired`). When the translator
meets unlearned code before the matching unlock, the section is handed
back, and the waiter continues on its own CPU: its `local_unlock`
re-derives the per-CPU address and clears its own CPU's byte. The
combiner's byte stays set. The preemption count is transferred at a
handback; per-CPU memory is not.

**Scope.** Any delegated section that takes a local lock (the per-CPU
`acquired` byte of `local_trylock_t`, re-derived at release) and is handed
back before the release leaves this behind; memcg object accounting is the
case seen. Lock users whose sections allocate accounted memory are exposed
while their code is still being learned (misses); once learned, the
section does not hand back inside the stock's few instructions, so steady
state is less exposed but not safe. This is the open AGENTS.md goal step 3
(classification of per-CPU `%gs` accesses) showing as a fault.

**Consequences for this round.** The kd on pass (section 6.3) ran after
its learning pass in a degraded boot: its rates for memcg-heavy workloads
are invalid, and the gains of 6.3 are, if anything, understated. The
earlier rounds' kd on runs used api, torture and mm only; the bisection's
first step (those three lists, `data/bisect/bisect-b1.out`) showed no
slowdown, but the per-CPU bytes were not read there. The appgrid session
then read them with `tools/pcpu.py` on a fresh kdall10 boot with api,
torture and mm (master `b6041b6f`): 0 of 64 CPUs after delegated mmap1 and
mmap2 (11-23 M sections, about 50 handbacks), **57 of 64 after delegated
will-it-scale brk1** (1.06 M handbacks, all misses). So the fault is not
specific to `lkp.txt`: any lock user with many misses inside accounted
allocations triggers it. In its data, the appgrid kd on pass ran with the
bytes set after brk1 (its on/off medians stay at 0.99-1.04, FxMark MRDM
0.95), and the native comparison's c4/a4 boots (on before off) have off
values within 0.94-1.06 of the clean boots. AGENTS.md on master now says to
measure kd off before kd on within a boot.

**Fix options** (not done here; a translator and kernel change for the
maintained branch):

1. A frontier before every local lock acquisition: the translator ends
   the delegation before a section takes a `local_trylock`/`local_lock`,
   so the waiter takes it on its own CPU. Needs the translator to
   recognise the acquisition (a `%gs`-relative access to a local lock
   object), which is the per-CPU classification of goal step 3.
2. As an interim policy: the memcg charge entry points
   (`__memcg_slab_post_alloc_hook`, `__memcg_slab_free_hook`,
   `obj_cgroup_charge*`, the page charge functions) as frontiers in the
   translator's policy lists, so no section reaches the stock locks.
3. A check at every handback that no local lock of the combiner's CPU was
   taken since the section began (the `acquired` bytes of the known
   local locks), with a kernel warning, as a guard while 1 is built.
