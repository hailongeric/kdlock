# lkp-tests workloads as kdlock macro benchmarks: analysis and plan

Started 2026-11-18. The goal is a macro benchmark set for kdlock built from
workloads of the Linux kernel performance suite (lkp-tests,
`https://github.com/intel/lkp-tests`, commit `50c5f0e`): unchanged
applications whose throughput depends on kernel locks that kdlock replaces.
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

What kdlock can change once a lock is contended: plain mode (node order of
the sleepable queues, eras of the reader-writer families, the spin queue)
helps when native collapses across the two nodes; delegation helps when the
critical sections are short, do not sleep, and their lock users are
allow-listed (`bench/allow/`, AGENTS.md goal step 4).

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
nodes), or it sleeps in locks for at least a quarter of the time.

### 4.3 Phase 2: kd without delegation (kdall10 off)

The candidates that pass, same points, plus the kd flat profile and kd
counters. Result: kd off against native per candidate, with the kd lock
functions' share.

### 4.4 Phase 3: delegation for the new lock users

For candidates whose contended lock users are not in `bench/allow/` yet:
run them once with the daemon and an empty allow list
(`kd_daemon.py -v`, as `api.txt` was made) to list the requested sites,
keep the ones whose sections are short and do not sleep, and write
`bench/allow/lkp.txt`. Then kd on (allow lists api, torture, mm and lkp)
against kd off, with delegated sections and handbacks reported for every
rate (AGENTS.md).

### 4.5 Phase 4: the macro benchmark set

From phases 1-3, about 10-15 workloads that cover the lock classes of
section 3 (mmap lock, directory and file `i_rwsem`, file table and file
locks, signals and fork, futex buckets, LRU and zone locks, run queues and
pipes), each with its lkp parameters. Full worker grid (1-8, then every
fourth to 64), native, kd off and kd on, 3 boots each, in the format of
`../kdall-native-20261117-64cpu/suite.sh` so the existing tables apply.

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

## 5. Status

| step | state |
|---|---|
| analysis (sections 1-3) | done |
| sources on the host | done (section 4.1) |
| build in the guest | waiting for the VM |
| phases 1-4 | waiting for the VM |
