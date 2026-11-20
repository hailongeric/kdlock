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
| sources, `build_lkp2.sh`, `screen.sh` | done; validated in the guest (pass val3) |
| phase 1, native screening | done, reduced: section 6 |
| phases 2-3, kd off, discover, learn, on | done for the candidates at 64 workers: section 6 |
| phase 4, macro set | section 7 |

## 6. The reduced round (2026-11-20)

At the user's request the round was shortened: screening at 64 workers
only, 6 s per point (the shortest that holds the profile window), kd passes
only for the candidates, five worker counts in the macro set. Kernels:
**kdnat18** (native twin with `CONFIG_PARAVIRT_SPINLOCKS`, the real queued
spinlocks; the first round's native kernel ran test-and-set spinlocks) and
**kdall21** (`d72a6b5d`). One run per point: a screening.

### 6.1 Native screening

| tag | what | state |
|---|---|---|
| `s3` | the application groups at 16 and 64 workers, 10 s (`p1_native.sh` up to its file system group) | used; that pass was stopped in AIM7 on btrfs (disk_rr with 64 tasks did not end in 900 s on the native kernel; AIM7 on btrfs is left out) |
| `s4-w64` | the rest at 64 workers (`p1_native_reduced.sh`), same boot | **not used**: run right after the stuck pass was killed, its rates are a fifth below the first round's in the median and some are off by orders of magnitude (sched_yield 2.3e4 against 1.97e8) |
| `s4r-w64` | the 44 points of that pass that had no value | not used |
| `s5-w64` | the rest at 64 workers again in a fresh boot | used; median 0.99 of the first round's native values where both exist |

`pass.py data s3 s5-w64` -> `data/s5-native-pass.md`: 256 of 451 points
pass a rule; **143 candidates** by the rule of this round (lock share at 64
workers at least 30%, or at least 10% for the application groups):
`data/s5-candidates.txt`. The kd passes ran for the 113 the disturbed pass
gave (`data/s4-candidates.txt`, 13 of them not candidates in the clean
pass) and then for the 43 the clean pass added
(`data/s5-candidates-added.txt`, `p23b_kd.sh`).

11 points have no value on any kernel (malloc1, malloc2, stress-ng cap,
mlockmany, mmaprandom, acl, aiol, fiemap, fanotify, vm-scalability
small-allocs-mt) and both AIM7 btrfs points.

### 6.2 kd off and kd on at 64 workers

`p23_kd.sh`, `p23b_kd.sh`; `s4_summary.py data` -> `data/s4-kd-summary.md`
(all 156), `data/s4-kd-summary-sorted.md`. Allow lists api, torture, mm,
lkp as the first round left them; `kd_vdown` 1.

No kernel complaint in any pass; per-CPU lock bytes 0 of 64 after every
group; `hb_region` (upper bound) 5.5 M in the first boot, nearly all of it
in wisp-pread2, wisp-readseek2 and stress-ng fcntl. One fatal signal in
the delegated pass: section 6.4.

Over the 156: kd off / native has a median of 1.00, 12 below 0.90; kd on /
native 29 at 1.10 or above, 22 below 0.90.

**Applications** (lock share from the native profile):

| candidate | native lock share | native | off/native | on/native | delegated | handbacks | hb_region |
|---|---|---|---|---|---|---|---|
| pbe-wait | 83% | 8374 | 1.01 | 0.91 | 21 | 0 | 0 |
| pbe-ctl | 85% | 3.927e+04 | 0.85 | 0.77 | 423148 | 601 | 0 |
| sysbench-threads | 90% | 5304 | 0.99 | 0.80 | 545334 | 836 | 0 |
| filebench-fileserver | 77% | 3.47e+05 | 1.05 | 1.00 | 540888 | 2075 | 0 |
| filebench-varmail | 87% | 6.259e+05 | 0.98 | 0.94 | 656681 | 1565 | 0 |
| filebench-webserver | 89% | 6.734e+05 | 0.98 | 0.97 | 935843 | 1308 | 0 |
| filebench-webproxy | 88% | 5.119e+05 | 0.95 | 0.97 | 728432 | 1561 | 0 |
| fio-randwrite-shared | 84% | 7.341e+05 | 0.97 | 0.94 | 112 | 596 | 0 |
| vms-lru-file-mmap-read | 35% | 6.625e+07 | 1.50 | 1.46 | 11 | 0 | 0 |
| vms-lru-file-mmap-read-rand | 66% | 1.076e+07 | 0.99 | 0.98 | 16 | 0 | 0 |
| vms-mmap-pread-rand-mt | 90% | 3.295e+06 | 1.02 | 1.00 | 0 | 38 | 0 |
| vms-mmap-xread-rand-mt | 14% | 4.128e+06 | 0.94 | 0.88 | 0 | 0 | 0 |
| vms-mremap-xread-rand-mt | 22% | 8.61e+06 | 0.93 | 1.40 | 0 | 0 | 0 |
| fsmark-ext4-fsync | 46% | 5.963e+04 | 1.03 | 1.00 | 0 | 0 | 0 |
| dbench-ext4 | 25% | 1.16e+04 | 0.99 | 0.92 | 0 | 0 | 0 |
| fsmark-xfs-fsync | 13% | 4.893e+04 | 1.05 | 1.05 | 0 | 0 | 0 |
| fsmark-btrfs-nosync | 41% | 3.441e+04 | 1.13 | 1.10 | 0 | 0 | 0 |
| vms-small-allocs | 72% | 1.869e+07 | 1.06 | 2.55 | 8113846 | 0 | 0 |
| fsmark-btrfs-fsync | 46% | 2.819e+04 | 0.97 | 0.94 | 0 | 0 | 0 |
| dbench-btrfs | 44% | 1265 | 1.40 | 1.37 | 0 | 0 | 0 |
| ub-execl | 67% | 2.615e+04 | 1.00 | 1.68 | 32800393 | 27 | 27 |

**Ahead with kd** (off or on at 1.2 or more):

| candidate | native lock share | native | off/native | on/native | delegated | handbacks | hb_region |
|---|---|---|---|---|---|---|---|
| wis-fallocate1 | 98% | 1.028e+06 | 1.29 | 1.93 | 46613415 | 116 | 0 |
| wis-fallocate2 | 97% | 1.068e+06 | 1.24 | 1.84 | 46156468 | 118 | 0 |
| wisp-fallocate1 | 97% | 1.024e+06 | 1.29 | 1.93 | 46747389 | 126 | 0 |
| wisp-fallocate2 | 97% | 1.088e+06 | 1.24 | 1.80 | 46200342 | 126 | 0 |
| sng-fd-abuse | 80% | 4.651e+07 | 0.99 | 1.63 | 14115061 | 34 | 28 |
| sng-munmap | 82% | 3.762e+05 | 1.00 | 1.21 | 4032354 | 767 | 0 |
| sng-netlink-task | 85% | 5.479e+05 | 1.56 | 1.56 | 145 | 0 | 0 |
| sng-schedpolicy | 81% | 5.125e+05 | 1.49 | 1.49 | 162 | 0 | 0 |
| sng-seal | 88% | 8.046e+05 | 1.00 | 1.43 | 13117876 | 0 | 0 |
| sng-dirmany | 92% | 8.167e+05 | 1.01 | 1.19 | 6642238 | 0 | 0 |
| sng-dnotify | 79% | 5.037e+04 | 1.41 | 1.41 | 447 | 0 | 0 |
| sng-chattr | 71% | 6184 | 1.96 | 1.67 | 1008314 | 399706 | 0 |
| sng-pty | 83% | 474.4 | 1.31 | 1.29 | 4675 | 0 | 0 |
| wis-brk1 | 84% | 3.897e+05 | 0.86 | 1.97 | 0 | 0 | 0 |
| wis-brk2 | 84% | 3.723e+05 | 2.03 | 2.06 | 0 | 0 | 0 |
| wis-mmap1 | 83% | 1.26e+05 | 1.63 | 1.62 | 0 | 0 | 0 |
| wis-mmap2 | 84% | 1.823e+05 | 1.87 | 1.82 | 0 | 0 | 0 |
| sng-zombie | 95% | 1.555e+06 | 0.96 | 1.50 | 8245143 | 0 | 0 |
| sng-shm | 91% | 3364 | 1.20 | 1.57 | 15981579 | 862 | 0 |
| wis-open2 | 98% | 1.204e+06 | 1.03 | 1.98 | 56700682 | 0 | 0 |
| wisp-mmap1 | 93% | 2.338e+06 | 2.37 | 2.11 | 9 | 0 | 0 |
| wisp-mmap2 | 91% | 2.464e+06 | 2.19 | 1.82 | 71 | 70 | 0 |

**Behind** (a selection; the full list is the last line of the summary):

| candidate | native lock share | native | off/native | on/native | delegated | handbacks | hb_region |
|---|---|---|---|---|---|---|---|
| sng-clone | 15% | 1301 | 1.05 | 0.76 | 0 | 0 | 0 |
| wisp-pread2 | 96% | 1.554e+06 | 1.03 | 0.33 | 4032428 | 1140248 | 1140248 |
| wisp-readseek2 | 96% | 1.55e+06 | 1.03 | 0.36 | 3966670 | 1049155 | 1049155 |
| sng-full | 90% | 2.202e+06 | 0.94 | 0.82 | 173 | 0 | 0 |
| sng-forkheavy | 26% | 218.8 | 1.39 | 0.76 | 20020 | 518 | 0 |
| sng-sigstop | 84% | 2.605e+06 | 0.87 | 0.83 | 396 | 0 | 0 |
| sng-handle | 98% | 1.655e+05 | 0.90 | 0.85 | 310 | 0 | 0 |
| sng-procfs | 64% | 3055 | 0.70 | 0.65 | 1 | 327 | 0 |
| sng-epollmany | 85% | 1.378e+04 | 1.11 | 0.60 | 237421 | 3 | 3 |
| sng-pidfd | 32% | 6.649e+04 | 0.97 | 0.85 | 6434810 | 0 | 0 |
| sng-ptrace | 96% | 1.312e+06 | 0.85 | 0.81 | 215 | 0 | 0 |
| sng-io-uring | 30% | 8.054e+06 | 0.50 | 0.97 | 293 | 0 | 0 |

- filebench, fio on one file, fs_mark and dbench on ext4 have 25-89% of
  their samples in lock code on native and are at 0.92-1.05 with kd either
  way.
- kd on is ahead where the lock is a tmpfs or mm lock whose sections
  complete: vm-scalability small-allocs 2.55, will-it-scale open2 1.98,
  fallocate 1.80-1.93, unixbench execl 1.68.
- sysbench threads (0.80) and epoll ctl (0.77) lose with delegation;
  will-it-scale pread2 and readseek2 in processes are at a third (the page
  wait queue lock: 21% of the sections handed back, all inside a per-CPU
  region). `folio_wake_bit` and `folio_wait_bit_common` should leave
  `bench/allow/lkp.txt`.
- kd off below 0.90: stress-ng io-uring 0.50, procfs 0.70, and ten more at
  0.85-0.90; single 6 s points, not rerun.
- **The mmap lock sites were not delegated in the pass of the added
  candidates** (will-it-scale mmap1, mmap2, brk1, brk2: 0 sections): their
  "on" column is kd off again. See 6.5; the delegated rates of these tests
  with a learned daemon are in
  `../plain-20261119-64cpu/README.md` section 11 (mmap1 1.31-1.90, brk1
  1.59-2.17 of native).

### 6.3 Which locks (discover pass)

`screen.sh discover` runs every candidate with an empty allow list, so
every contended delegable lock call asks for an image and is refused;
`discover_summary.py data s4-w64` -> `data/s4-discover.md` (per candidate,
and per lock user as below; the counts are rate-limited request events).

| lock user | candidates | requests | which |
|---|---|---|---|
| __remove_mapping | 8 | 55236 | vms-mmap-pread-rand-mt, vms-mmap-xread-rand-mt, vms-mremap-xread-rand-mt, vms-lru-file-mmap-read-rand, sng-mmapcow, sng-mmapmany ... |
| dquot_add_space | 6 | 33263 | wisp-fallocate2, wisp-fallocate1, wis-fallocate1, wis-fallocate2, sng-shm, sng-dev-shm |
| shmem_file_write_iter | 14 | 24009 | wis-writeseek3, wisp-writeseek3, wisp-pwrite3, wis-pwrite3, sng-fpunch, wis-writeseek2 ... |
| futex_wake | 9 | 18214 | wis-pthread_mutex3, wis-pthread_mutex5, wis-pthread_mutex4, wis-pthread_mutex1, sysbench-threads, filebench-webserver ... |
| futex_q_lock | 9 | 14565 | wis-pthread_mutex3, wis-pthread_mutex5, wis-pthread_mutex4, wis-pthread_mutex1, sysbench-threads, filebench-webproxy ... |
| alloc_fd | 5 | 14265 | wis-open1, wis-open3, wis-dup1, wis-open2, wis-unlink2 |
| file_close_fd | 5 | 14243 | wis-open1, wis-dup1, wis-open3, wis-open2, wis-unlink2 |
| folio_wake_bit | 7 | 9628 | wis-readseek2, wis-pread2, wisp-pread2, wisp-readseek2, sng-dynlib, wisp-mmap2 ... |
| __iterate_supers | 6 | 8842 | sng-mknod, sng-io, sng-dirdeep, sng-touch, sng-dentry, sng-open |
| posix_lock_inode | 3 | 8746 | wis-lock2, sng-fcntl, wisp-lock2 |
| folio_wait_bit_common | 5 | 7940 | wisp-pread2, wis-pread2, wis-readseek2, wisp-readseek2, sng-dynlib |
| inode_sb_list_add | 13 | 7661 | sng-open, sng-fd-abuse, sng-seal, sng-memfd, sng-filename, sng-filerace ... |
| fcntl_setlk | 2 | 7551 | wis-lock1, wis-lock2 |
| evict | 14 | 6806 | sng-fd-abuse, sng-seal, sng-memfd, sng-filename, sng-dirmany, sng-filerace ... |
| __filemap_add_folio | 5 | 6133 | vms-mmap-pread-rand-mt, vms-mremap-xread-rand-mt, vms-mmap-xread-rand-mt, sng-mmapcow, sng-mmapmany |
| chrdev_open | 4 | 5491 | sng-full, sng-rlimit, sng-sockfd, sng-open |
| shmem_fallocate | 3 | 5463 | sng-chattr, sng-fpunch, sng-filerace |
| folio_lruvec_lock_irq | 5 | 5277 | sng-mlock, sng-msync, sng-mmapmany, sng-forkheavy, sng-env |
| cpuset_cpus_allowed | 2 | 4964 | sng-affinity, sng-cpu-sched |
| cgroup_leave_frozen | 5 | 4603 | sng-ptrace, sng-sigstop, sng-wait, sng-vfork, sng-vforkmany |
| cgroup_enter_frozen | 5 | 4582 | sng-ptrace, sng-sigstop, sng-wait, sng-vforkmany, sng-vfork |
| dput.part.0 | 10 | 4364 | sng-fstat, sng-handle, sng-landlock, sng-forkheavy, sng-sysinfo, sng-open ... |
| __do_sys_brk | 2 | 4339 | wis-brk1, wis-brk2 |
| lockref_get_not_dead | 7 | 3542 | sng-fstat, sng-handle, sng-landlock, sng-open, sng-dir, sng-clock ... |
| vma_prepare | 8 | 3509 | ub-execl, sng-dynlib, sng-munmap, sng-mmapmany, sng-fd-abuse, wis-page_fault1 ... |
| dquot_free_inode | 4 | 3310 | wisp-unlink2, wis-unlink2, sng-shm, sng-forkheavy |
| __slab_free | 18 | 3194 | sng-rawpkt, sng-rawsock, sng-rawudp, sng-msg, wisp-mmap2, sng-msync ... |
| anon_vma_fork | 18 | 3065 | sng-sigchld, sng-pidfd, sng-session, sng-landlock, sng-seccomp, sng-exit-group ... |
| unlink_file_vma_batch_final | 16 | 3026 | sng-dynlib, ub-execl, sng-munmap, sng-sigchld, sng-pidfd, sng-session ... |
| cgroup_file_notify | 1 | 2981 | sng-mremap |

- filebench and sysbench threads contend on the **futex hash bucket lock**:
  the contention is their own pthread mutexes. Delegating that lock gains
  nothing (filebench 0.96-1.02 of kd off) or loses (sysbench 0.81).
- Not in the allow lists and contended by applications: the page cache
  xarray lock (`__remove_mapping`, `__filemap_add_folio`: the
  vm-scalability file mmap cases), the LRU lock, jbd2 (dbench on ext4,
  about 40 sites). (`do_epoll_ctl` is in `lkp.txt`; every site shows as
  refused in this pass because its list is empty.)
- `shmem_file_write_iter` (fio on one file, pwrite, writeseek) is in the
  list, but its sections copy user memory and are handed back there
  (`copy_folio_from_iter_atomic`); the site account switches it off.

### 6.4 Open: SIGSYS in stress-ng seccomp with the daemon

The delegated pass logged one "potentially unexpected fatal signal 31" of a
stress-ng seccomp child, at `getpid` (`data/seccomp-on-sigsys.txt`).
Repeated, 64 instances for 6 s per run:

| setup | runs | runs with a SIGSYS kill logged |
|---|---|---|
| kdall21, daemon, lists api torture mm lkp (the passes; `secc_check.sh`) | 27 | 3 |
| kdall21, daemon, the same lists without the four `sighand->siglock` users (`secc_bisect.sh` A) | 24 | 1 |
| kdall21, daemon, only those four (`secc_bisect.sh` B) | 24 | 2 |
| kdall21, daemon, only those four, with `perf record` on failed system calls (`secc_trace.sh`) | 40 | 0 |
| kdall21, no daemon (`secc_off.sh` and the off passes) | 30 | 0 |
| kdnat18, 6 s (the passes and `secc_native.sh`) | 5 | 0 |
| kdnat18, 12 s and 20 s (two and three times the iterations) | 6 | 0 |

Six in 75 untraced runs with the daemon against none in 41 without. It is
treated as a possible correctness failure of delegation until understood.
What is known:

- The stressor's child installs a SIGSYS handler and then a filter that
  traps what it does not allow; a trapped call ends in the handler and
  `_exit`, which is not logged. A logged kill needs SIGSYS blocked or at
  its default action, or a filter that kills. The stressor calls `getpid`
  after the filter only in its message functions, i.e. on an error path.
- It is not a matter of more iterations in the same time (the random
  sequence is fixed by `--no-rand-seed`): native runs of twice and three
  times the length show none.
- It does not follow one half of the allow list.
- With every failed system call recorded it did not occur in 40 runs, so
  the failing call is not known.

### 6.5 Open: learning and short points

`data/mm-site-check.txt`. In the boot of the added candidates the mmap lock
sites handed back every section for a translation miss (`hb_miss`): 2700
handbacks and about 10 completed sections per 6 s run of mmap1, for the
upstream and the TCLocks copy alike, the sites switched off and retried
6-8 times per run. Two things:

- Learning is slow by construction: a miss hands the section back, 256
  such sections switch the site off, and it is tried again after 1-4 s.
  With a new state file mmap1 at 16 threads needed six runs of 6 s (72 s
  of wall time) before sections completed (115 k in the sixth run). The
  screening gives a candidate 6 s per pass. The application grid's two
  learning passes (12 s per point, three worker counts, seven tests on the
  mm sites) were enough.
- With the state file of the lkp passes (`/root/kds_lkp.json`, several
  daemon sessions, module loads and unloads in between) the misses went on
  and the daemon's log shows no miss report for them. Not looked into.

So a candidate whose lock users are in the allow lists and that shows few
delegated sections in 6.2 may simply not have been learned. The macro set
(section 7) gets two learning passes of 30 s per point with a new state.

## 7. The macro set (phase 4)

`p4_macro.sh kd` on kdall21 (fresh boot: kd off; two learning passes at 32
workers with 30 s per point and a new daemon state; kd on) and
`p4_macro.sh native` on kdnat18 (fresh boot), 6 s per point, one run;
`m1_summary.py data/m1-screen.txt` -> `data/m1-summary.md`. Sixteen
workloads: what the screening had ahead with kd on, applications at parity,
and cases where delegation lost.

| workload | | 4 | 16 | 32 | 48 | 64 | delegated, handbacks, hb_region |
|---|---|---|---|---|---|---|---|
| pbe-ctl | native, ops/s | 7.651e+05 | 1.586e+05 | 7.449e+04 | 3.169e+04 | 2.28e+04 | |
| | off/native | 1.16 | 1.13 | 1.10 | 1.39 | 1.59 | |
| | on/native | 1.11 | 1.61 | 1.62 | 2.44 | 2.36 | 45346691, 11, 11 |
| sysbench-threads | native, events/s | 7913 | 6288 | 5919 | 5737 | 5252 | |
| | off/native | 1.06 | 1.10 | 1.04 | 1.04 | 1.00 | |
| | on/native | 1.05 | 1.01 | 0.98 | 1.02 | 0.97 | 1951291, 2154, 0 |
| filebench-varmail | native, ops/s | 5.775e+05 | 6.879e+05 | 6.772e+05 | 6.517e+05 | 6.049e+05 | |
| | off/native | 1.01 | 0.99 | 1.03 | 1.03 | 0.99 | |
| | on/native | 0.93 | 0.95 | 0.98 | 0.99 | 0.98 | 2384951, 6959, 381 |
| filebench-webserver | native, ops/s | 6.823e+05 | 7.095e+05 | 7.443e+05 | 7.181e+05 | 6.591e+05 | |
| | off/native | 0.96 | 1.00 | 0.99 | 1.01 | 0.99 | |
| | on/native | 1.00 | 1.04 | 1.10 | 0.98 | 0.99 | 3925032, 4679, 0 |
| fio-randwrite-shared | native, iops | 8.797e+05 | 9.441e+05 | 9.97e+05 | 8.425e+05 | 8.025e+05 | |
| | off/native | 0.82 | 0.86 | 0.90 | 0.89 | 0.87 | |
| | on/native | 0.78 | 0.81 | 0.79 | 0.85 | 0.86 | 170, 2264, 0 |
| vms-lru-file-mmap-read | native, KB/s | 9.126e+07 | 9.602e+07 | 1.063e+08 | 1.075e+08 | 1.005e+08 | |
| | off/native | 0.92 | 1.02 | 1.00 | 1.00 | 0.98 | |
| | on/native | 1.01 | 1.02 | 0.97 | 0.96 | 0.98 | 48, 0, 0 |
| dbench-ext4 | native, MB/s | 3623 | 8794 | 1.104e+04 | 1.232e+04 | 1.186e+04 | |
| | off/native | 0.98 | 0.95 | 1.01 | 0.97 | 0.98 | |
| | on/native | 0.99 | 0.90 | 0.93 | 0.92 | 0.93 | 0, 0, 0 |
| wis-brk1 | native, ops/s | 7.579e+05 | 6.792e+05 | 6.788e+05 | 4.576e+05 | 3.596e+05 | |
| | off/native | 1.11 | 1.07 | 1.06 | 1.65 | 2.19 | |
| | on/native | 1.08 | 1.07 | 1.06 | 1.09 | 1.72 | 3022374, 1389463, 242 |
| wis-mmap1 | native, ops/s | 2.774e+05 | 2.786e+05 | 2.366e+05 | 1.447e+05 | 1.226e+05 | |
| | off/native | 1.01 | 1.04 | 1.27 | 1.51 | 1.70 | |
| | on/native | 0.99 | 0.98 | 1.05 | 1.53 | 1.56 | 54, 12078, 0 |
| wisp-pread2 | native, ops/s | 3.206e+06 | 2.312e+06 | 2.247e+06 | 1.571e+06 | 1.55e+06 | |
| | off/native | 0.88 | 1.00 | 1.02 | 1.05 | 1.03 | |
| | on/native | 0.94 | 0.98 | 1.02 | 0.41 | 0.51 | 8909268, 1987378, 1766245 |
| sng-shm | native, bogo/s | 1240 | 3795 | 3848 | 3818 | 3486 | |
| | off/native | 0.99 | 1.21 | 1.22 | 1.23 | 1.14 | |
| | on/native | 0.99 | 0.97 | 1.28 | 1.33 | 1.52 | 53741863, 1265, 0 |
| vms-small-allocs | native, KB/s | 8.299e+06 | 2.46e+07 | 2.464e+07 | 2.071e+07 | 1.9e+07 | |
| | off/native | 1.00 | 0.99 | 1.01 | 1.05 | 1.06 | |
| | on/native | 1.00 | 1.06 | 1.37 | 1.91 | 2.61 | 23172619, 11, 11 |
| ub-execl | native, lps | 8603 | 2.902e+04 | 3.098e+04 | 2.811e+04 | 2.63e+04 | |
| | off/native | 1.00 | 0.98 | 0.99 | 1.03 | 0.98 | |
| | on/native | 0.97 | 0.88 | 1.13 | 1.46 | 1.66 | 92274381, 30, 30 |
| wis-fallocate1 | native, ops/s | 1.925e+06 | 2.171e+06 | 1.988e+06 | 1.201e+06 | 1.07e+06 | |
| | off/native | 0.99 | 1.10 | 1.12 | 1.22 | 1.24 | |
| | on/native | 0.99 | 1.08 | 1.12 | 1.64 | 1.81 | 92776835, 161, 0 |
| wis-open2 | native, ops/s | 2.09e+06 | 2.295e+06 | 2.143e+06 | 1.37e+06 | 1.282e+06 | |
| | off/native | 1.02 | 0.91 | 1.01 | 1.02 | 1.02 | |
| | on/native | 0.98 | 0.96 | 1.01 | 1.71 | 1.77 | 94900763, 0, 0 |
| sng-fd-abuse | native, bogo/s | 1.354e+07 | 5.387e+07 | 5.288e+07 | 5.308e+07 | 4.839e+07 | |
| | off/native | 1.10 | 1.00 | 1.06 | 1.05 | 1.05 | |
| | on/native | 1.15 | 0.97 | 1.51 | 1.50 | 1.61 | 47158817, 56, 0 |

below the bounds (off 0.93, on 0.90): fio-randwrite-shared off 4 0.82; fio-randwrite-shared on 4 0.78; fio-randwrite-shared off 16 0.86; fio-randwrite-shared on 16 0.81; fio-randwrite-shared off 32 0.90; fio-randwrite-shared on 32 0.79; fio-randwrite-shared off 48 0.89; fio-randwrite-shared on 48 0.85; fio-randwrite-shared off 64 0.87; fio-randwrite-shared on 64 0.86; vms-lru-file-mmap-read off 4 0.92; dbench-ext4 on 16 0.90; wisp-pread2 off 4 0.88; wisp-pread2 on 48 0.41; wisp-pread2 on 64 0.51; ub-execl on 16 0.88; wis-open2 off 16 0.91

No kernel complaint and no fatal signal in the four passes; per-CPU lock
bytes 0 of 64 at the end. Counters of the boot (`data/m1-on-stats.txt`):
931 M sections delegated, 3.59 M handed back (3.06 M for misses, 0.53 M at
frontiers), `vdown` 1.41 M, all of them handed back (brk1), `hb_region`
(upper bound) 1.77 M, nearly all in wisp-pread2, **`done_in_region` 5860**
(stress-ng shm 5832, will-it-scale fallocate1 28: sections that completed
with the preempt count raised by their own code; the lock bytes are clean,
the cases are not looked at).

- **Learning changes the picture.** epoll ctl was at 0.77 of native with
  the daemon in the screening and is at 1.6-2.4 here; sysbench threads
  0.80 there, 0.97-1.05 here. The screening's 6 s per point after one
  learning pass understates kd on (section 6.5).
- **Macro benchmark material**: epoll ctl (2.4 at 48-64 workers),
  vm-scalability small-allocs (1.4-2.6 from 32 workers), will-it-scale
  fallocate1 (1.6-1.8) and open2 (1.7-1.8), unixbench execl (1.1-1.7),
  stress-ng fd-abuse and shm (1.3-1.6), all with next to no handbacks;
  the gains are at 48 and 64 workers, across the nodes, and from 32 for
  small-allocs, execl, fd-abuse and shm. With these: mmap1, brk1 and
  Apache of `../plain-20261119-64cpu/` section 11.
- **At parity**: filebench (futex hash bucket lock, i.e. the application's
  own mutexes), sysbench threads (the same), dbench on ext4 (jbd2, not in
  the allow lists; 0.90-0.93 with the daemon at 16-64 workers with nothing
  delegated), vm-scalability lru-file-mmap-read.
- **fio, random writes of N jobs to one file: kd off at 0.82-0.90 of
  native** at every worker count (0.78-0.86 with the daemon; the sections
  of `shmem_file_write_iter` are handed back at the user copy and the site
  is off). The lock is the inode rwsem, writers only; native has 82% of
  its samples in `osq_lock`. A plain-path loss of the kd rwsem that the
  plain-path round did not have a workload for. Open.
- **will-it-scale mmap1 was not delegated** here either (54 sections; the
  munmap and mmap sites still handing back for misses after 60 s of
  learning load), and **brk1 loses with the daemon** at 48 and 64 workers
  (1.09 and 1.72 against 1.65 and 2.19 without): this copy of brk1 has its
  shrinking half handed back at the TLB flush after the kept downgrade
  (1.39 M of 3.0 M sections), which is under half of the site's sections,
  so the site account leaves it on. The TCLocks copy of both tests
  delegates and gains in the application grid.
- **wisp-pread2**: 0.41 and 0.51 at 48 and 64 workers with the daemon,
  1.05 and 1.03 without; `folio_wake_bit` and `folio_wait_bit_common` are
  taken out of `bench/allow/lkp.txt` with this round.

## 8. Open after this round

1. SIGSYS in stress-ng seccomp with the daemon (6.4).
2. Learning: a miss counts against its site like any handback, so a site
   that is still being learned is switched off after 256 sections and
   tried again after 1-4 s; mmap1 needs more than a minute of contended
   load, and with a reused state the misses were no longer reported (6.5).
   Candidate change: do not count a miss whose report the daemon will act
   on.
3. fio on one file: the kd rwsem's writers at 0.82-0.90 of native without
   delegation (7).
4. brk1 (upstream copy): half of a site's sections handed back after a
   kept downgrade is not "mostly" for the site account, and delegation
   loses a fifth (7).
5. `done_in_region` in stress-ng shm and fallocate1 (7).
6. Lock users the applications contend on that no allow list has: page
   cache xarray lock, LRU lock, jbd2; each needs the first round's
   one-by-one check before it is added (6.3).
7. kd off below 0.90 in the screening and not rerun: stress-ng io-uring
   0.50, procfs 0.70 (6.2).

