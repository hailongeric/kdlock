# lkp-tests workloads as kdlock macro benchmarks, second round

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

Started 2026-11-19 on the cloud host. The first round
([../lkp-macro-20261118-64cpu/](../lkp-macro-20261118-64cpu/README.md),
merged into `master` with this round) holds the analysis of lkp-tests by
kernel lock, the plan and one screening pass. This round

1. reviews what that round covered and what it left out (sections 1-2);
2. adds the applications and workloads of lkp-tests it did not screen
   (section 3);
3. repeats the measurements on the kernels that carry the two fixes its
   delegated pass was missing (section 4 onwards).

The measure stays the first round's: **kd with delegation ("on") against
native Linux**, with the delegated sections and handbacks of every rate,
and kd without delegation ("off") as the reference that separates what
delegation adds.

Target: the kdclaude VM (64 vCPUs as 2 nodes of 32, 24 GiB, host fixed at
2.7 GHz), kernels `7.0.0-38-kdall13` (every lock a kdlock, `3a909d50`) and
its native twin `7.0.0-38-kdnat10` (the same source with `CONFIG_KDLOCK_ALL`
off, built for this round and for `../appgrid-20261119-64cpu/`).

## 1. What the first round established

lkp-tests (`https://github.com/intel/lkp-tests`, commit `50c5f0e`) has 357
programs; its job files (169 at the top of `jobs/`, 216 more in
subdirectories) name the workloads and their parameters. The first round's
README sorts them by the kernel lock they contend (its section 3) and ranks
them by what delegation can do (its 3.7). Its screening `s1` ran 121
candidates at 16 and 64 workers on kdnat9 (native) and kdall10 (kd off, a
discover pass with an empty allow list, kd on):

- **Native is lock-bound** (86-99% of the samples in lock slow paths at 64
  workers) in will-it-scale signal1, dup1, lock2, open1, open3, readseek2,
  pread2, pthread_mutex1/3/4, brk1/2, mmap1/2, unlink1, pwrite2/3,
  writeseek3, in stress-ng zombie and shm, and in vm-scalability
  small-allocs.
- **kd off against native at 64 workers:** 2.2-3.6 for the spinlock-bound
  ones (signal1, dup1, lock2, open1, open3, stress-ng zombie, mremap, shm,
  unlink), 1.4-1.9 for the mmap lock writers and several stress-ng file
  tests; behind in pthread_mutex1/3/4 (0.55-0.57), hackbench socket
  (0.44-0.46), stress-ng sock (0.52), perf sched messaging (0.61).
- **kd on against native at 64 workers**, for lock users that do not
  allocate memory: lock2 7.44, dup1 7.37, open3 7.02, open1 7.00, stress-ng
  zombie 6.02, shm 4.30, signal1 2.83, small-allocs 2.62, unixbench execl
  1.38.
- **Allow list** `bench/allow/lkp.txt` from the discover pass (33 lock
  users: siglock, futex bucket, shmem and directory `i_rwsem` writers, page
  wait queue, tmpfs quota, `i_mmap_rwsem` and anon_vma writers,
  `tasklist_lock` writers, `s_inode_list_lock`, SysV IPC, epoll).

What was not valid in it:

1. Its kd-on pass ran in a boot where handbacks had left memcg's per-CPU
   lock bytes set (its section 7; it found that failure). Rates of
   memcg-heavy workloads in "on" are too low there. Fixed in the translator
   (`3a909d50`, TRANSLATOR.md 3a).
2. It ran with `kd_vdown=0` because the kept downgrade left the mmap lock
   write-held (`a26a8578` fixes it), so every delegated munmap was handed
   back: mmap1/2 and brk1/2 show on/native 0.87-1.04 there, against 1.6-2.9
   in `../appgrid-20261118-64cpu/`.
3. One run per point and two worker counts: it selects candidates, it is
   not a result (its 4.6).

Its phase 4 (the macro set over a worker grid) did not start.

## 2. What the first round left out

Checked against the job files of the same lkp-tests commit:

| lkp-tests | in its jobs | screened in s1 | left out |
|---|---|---|---|
| will-it-scale | 60 tests, thread and process mode | 33 thread, 8 process | 27 thread tests (lock1, malloc1/2, eventfd1, pipe1, unix1, poll1/2, fallocate1/2, futex3/4, pthread_mutex2/5, the `*1` read/write/seek tests, read3/4, pread3, readseek3, writeseek2, open2, unlink2); 52 process-mode tests |
| stress-ng | 386 stressors in 11 jobs | 47 (and pipeherd, which lkp does not run) | 339; 186 of them exercise the kernel and can run here (the rest are compute, sort, math and cache stressors, or need hardware, a device or a changed machine) |
| vm-scalability | 27 cases without swap or hugetlb | 7 (anon and small-allocs) | the file, shm, mmap and truncate cases (they need its sparse files) |
| aim7, fsmark, dbench | on a 48 G RAM block device with btrfs, ext4, xfs | on tmpfs | every disk file system: the journal and allocator locks of 3.2 of the first round were never reached |
| perf bench | futex (5), sched messaging, sched pipe, syscall, numa mem, mem | futex hash, lock-pi, wake-parallel; sched messaging | futex requeue and wake; `perf bench epoll` is not an lkp job but belongs with stress-ng epoll |
| pft, schbench | yes | built, not run | both |
| applications: netperf, tbench, sockperf, redis, memcached (mutilate, memtier), sysbench, apachebench, siege, nginx/phpbench, pgbench, mysql (oltp, linkbench), rocksdb, cassandra, mongodb (ycsb), kbuild, kernbench, filebench, blogbench, postmark, fio, iozone | yes | none ("later, setup heavy") | all |

So the first round is a micro-level screen: will-it-scale and stress-ng
operations, mostly one system call in a loop. The applications of lkp-tests,
which are the point of a macro benchmark set, and the disk file systems
were not measured.

## 3. Candidates added in this round

### 3.1 Applications

What each application does in the kernel, which locks that contends, and
what delegation can be expected to do (tiers as in 3.7 of the first round:
A delegable and short, B delegable but the section may sleep or copy, C
bound on locks that never delegate or on no shared lock). The screening
decides; this table is the expectation it is checked against.

| application | lkp job, as run here | kernel work | shared locks expected | tier |
|---|---|---|---|---|
| filebench fileserver, varmail, webserver, webproxy | `filebench` (personalities with their own thread counts, on a disk); here N threads of one process, tmpfs, 10 s | open, create, append, read, delete, fsync on one file set | `files->file_lock` (one file table for all threads, as dup1 and open1), directory `i_rwsem` writers, file `i_rwsem`, `d_lock`, `s_inode_list_lock` | A (file table), B (directories) |
| blogbench | `blogbench` on a disk; here tmpfs, N readers and N/8 writers, rewriters and commenters | concurrent create, rename, append and read in shared directories | directory and file `i_rwsem`, dentry locks | B |
| fio, buffered 4 KiB psync | `fio-basic` (rw modes, sync engine); here N jobs on one file and on a file each, tmpfs | `pwrite`/`pread` | one file: `i_rwsem` writers (as pwrite2/3); own files and reads: none shared (reference) | B / none |
| kbuild | `kbuild` (defconfig, vmlinux, 50% and 200% tasks); here `make -jN vmlinux`, objects on tmpfs | fork, exec, exit, page faults, path lookups, small file I/O | `i_mmap_rwsem` writers of the compiler's and libc's mappings (as unixbench execl, 1.38 in s1), `tasklist_lock` writers, anon_vma, dentry and inode list locks | B, a broad mixture |
| pgbench | `pgbench` (scale 1000, 50% clients); here PostgreSQL 17 on tmpfs, scale 100, select-only and simple-update, N clients | one process per client: shared memory, futex-backed semaphores, file reads, WAL appends | futex hash bucket, WAL file `i_rwsem`, run queue locks; no shared mm or file table | B / C |
| memcached with memtier_benchmark | `memtier` (redis) and `mutilate` (memcached); here memcached with N/2 threads, memtier with N/2 threads | epoll, socket reads and writes, futex for its item locks | futex hash bucket, wait queues; socket locks are per connection | C, A where the futex bucket contends |
| redis | `redis` (4 servers, redis-benchmark set/get, 5 clients, pipeline 3); here N/2 servers | loopback TCP between one benchmark and one single-threaded server each | none shared across the pairs but the scheduler's | C (reference) |
| netperf TCP_RR, UDP_RR, TCP_CRR, TCP_STREAM | `netperf` on localhost, 50% and 200% instances; here N instances | request/response and connection setup on loopback | per-socket locks (private), hash bucket locks for ports and connections in TCP_CRR, run queue locks | C; TCP_CRR to be seen |
| tbench | `tbench` on localhost, 100% clients | the dbench file server load over loopback TCP | as netperf TCP_RR | C |
| sysbench mutex, threads | `sysbench-mutex`, `sysbench-threads` (4096 mutexes; 8 locks and 1000 yields) | contended pthread mutexes, `sched_yield` | futex hash bucket, run queue locks | A (futex bucket) / C |
| AIM7, fs_mark, dbench on ext4, xfs, btrfs | `aim7-fs-1brd`, `fsmark-1brd`, `dbench` on a RAM block device (48 G; here 8 G) | file creation, writes, sync, deletion through a journalled file system | ext4: `j_state_lock` (rwlock), `j_list_lock`, `s_orphan_lock`, `i_data_sem`; xfs: inode locks (rwsem), CIL context rwsem and push lock, AIL lock, `l_icloglock`; btrfs: extent buffer locks (rwsem), delayed-ref and transaction spinlocks; all: directory `i_rwsem`, `i_pages` lock, writeback list locks | B (sections start journal handles and allocate) |

Already measured elsewhere: Apache httpd (lkp's `apachebench` and `siege`
drive it with one client process, which then is the limit; with `wrk` it is
in the appgrid rounds), LevelDB `readrandom` (lkp's `rocksdb` job runs the
same benchmark of its successor), FxMark.

Not built here, with the reason:

- mysql (`oltp`, `linkbench`), rocksdb, cassandra, mongodb (`ycsb`),
  nginx with PHP (`phpbench`): large builds that need packages the guest
  cannot fetch (it has no network; sources come through the cloud host),
  a JVM or an hour of compilation. pgbench stands for the databases.
- mutilate: needs scons and ZeroMQ; memtier drives memcached instead.
- lmbench3 (needs libtirpc headers) and lib-micro: latencies of single
  system calls with one task, the uncontended path.
- iozone, postmark, sysbench-fileio, stutter, simoop, pmbench: one stream,
  or bound on a disk or on swap.
- exit-free (frees 80 G), bust-shm-exit (reports pass or fail, no rate),
  autonuma-benchmark (compute loops under NUMA balancing), reaim (did not
  build in the first round; AIM7 has its file tests), kernbench (kbuild).

### 3.2 The rest of will-it-scale, stress-ng, vm-scalability, perf bench

- **will-it-scale:** the 27 thread tests and 52 process-mode tests of
  section 2. Expected: `malloc1` (mmap lock writers, tier A); most others
  work on per-thread objects and are cost checks of the uncontended path;
  process mode can only contend global locks.
- **stress-ng:** 186 more stressors (`SNG2` in `screen.sh`), first at 64
  workers only with a profile, then the ones that pass at 16 as well.
- **vm-scalability:** lru-file-readonce/readtwice, lru-file-mmap-read(-rand),
  mmap-pread-*-mt, mmap-xread-*-mt, mremap-xread-rand-mt, shm-pread-rand-mt,
  shm-xread-rand-mt, lru-shm-rand, truncate, msync-mt, anon-r-seq-mt,
  anon-rx-rand-mt with 4 G instead of lkp's 16-256 G (`lru_lock`,
  `i_pages`, `i_mmap_rwsem`, the mmap lock read side).
- **perf bench:** epoll wait and ctl on one shared epoll instance
  (`ep->lock`, `ep->mtx`), futex requeue and wake.
- **pft, schbench.**

## 4. Plan

### 4.1 Sources and build

The guest has no network. The first round's sources are in
`/home/eric/vm/vm-shared/lkpbench` on 10.176.26.71 (built in the guest in
`/root/lkpbench`, `../lkp-macro-20261118-64cpu/build_lkp.sh`). The
additional ones are fetched on the cloud host from the URLs of lkp's
`PKGBUILD` files (`/root/lkpsrc/fetch.sh` there: netperf, redis 7.2,
memcached 1.6.39 with libevent 2.1.12, memtier_benchmark, sysbench,
blogbench 1.2, filebench, fio, PostgreSQL 17.6, adrestia, sockperf), copied
to `lkpbench/src2` and built by `build_lkp2.sh`. A component that does not
build is reported and left out; it is not a pass.

### 4.2 Phases

All with `screen.sh` of this directory (the first round's, with the groups
of section 3, the region counters and the per-CPU lock bytes). 10 s per
point, 16 and 64 workers, a flat profile at 64, as in s1, so the two rounds
compare.

| phase | kernel | what | tag |
|---|---|---|---|
| 0 | any | build; a validation pass of the new groups (3 s points) | `val3` |
| 1 | kdnat10 | native: the new groups (stress-ng remainder at 64 workers first); the first round's candidates again on this kernel | `s2` |
| 2 | kdall13, fresh boot | kd off: the candidates that pass (first round's rule: lock share at 64 workers at least 10%, or the rate at 64 below the rate at 16, or a quarter of the time asleep in locks) | `s2` |
| 3 | same boot, after off | discover pass for the new candidates (empty allow list); additions to `bench/allow/lkp.txt`; a learning pass; kd on with `kd_vdown=1` (the default) and the lists api, torture, mm, lkp | `s2` |
| 4 | kdnat10, kdall13 | the macro set: the workloads where kd on is ahead of native in phase 3, and the tier B and C cases that show the limits; workers 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 40, 48, 56, 60, one round (the user's grid of 2026-11-19); native, kd off, kd on | `m1` |

With every kd-on rate: delegated sections, handbacks by kind, `hb_region`,
`done_in_region`, and the memcg per-CPU lock bytes after each group
(`/root/lkpres/pcpu.txt`).

### 4.3 Rules

- The VM is shared with `../appgrid-20261119-64cpu/` (the same session
  drives both): lkp runs start only when that grid's pass in the boot is
  over, and never during one.
- kd off before kd on within a boot; a fresh boot before a measured pass.
- One-shot `grub-reboot`; the GRUB default stays kdlock1.
- This round uses `/root/lkpbench`, `/root/lkpres` and its own daemon state
  `/root/kds_lkp.json`; nothing of `/root/appbench`, `/root/appgrid` or
  `/root/kds_cmp.json` is written (the kernel source copy under
  `/root/appbench/text` is read by the kbuild candidate).
- No core dumps, `kernel.print-fatal-signals=1`; a fatal signal on kdall13
  that native does not show counts as a correctness failure.
- Phases 1-3 select candidates (one run per point); phase 4 is one round
  as well at the user's request, so its ratios within about 5% of 1 are
  not results.

## 5. Status

| step | state |
|---|---|
| review of the first round, added candidates (sections 1-3) | done |
| sources on the cloud host | done (16 of 16 fetched) |
| `build_lkp2.sh`, `screen.sh` | written; not yet validated in the guest |
| phases 0-4 | waiting for the VM (the appgrid rerun on kdall13 runs first) |
