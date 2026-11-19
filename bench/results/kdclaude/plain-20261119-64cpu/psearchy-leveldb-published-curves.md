# Psearchy and LevelDB readrandom: workload characteristics, and why published "stock Linux" curves collapse when ours do not

Date: 2026-11-19. Desk research only (papers, artifacts, library and kernel sources); nothing in this file was measured here. The measurements in the VM that test its conclusions are in [README.md](README.md) section 8 (the IntervalVM configurations reproduced on the native kernel: LevelDB peaks at 4-8 threads with the thrashing table cache and not with `--open_files=50000`; Psearchy shows no peak up to 60 threads with the per-thread tables that fit into 24 GiB).

Conventions used below:
- **[S]** = stated by the source (paper text, artifact script, or source code I read).
- **[F]** = read off a figure by eye, so approximate.
- **[I]** = my inference, not stated by any source.

## 0. Short answers

**(a) Psearchy.**
The classic collapse of threaded Psearchy is an address-space-lock collapse, from two sources:
- mmap/munmap calls taking the lock for write. Up to glibc 2.22, stdio allocated every FILE buffer with an anonymous mmap, so there was one mmap/munmap pair per input file.
- Millions of anonymous page faults taking the same lock for read (every thread zeroes and fills its private hash-table memory).

Neither source exists in our setup [I]:
- glibc 2.23 and later malloc the stdio buffer.
- Linux 6.4 and later handle anonymous faults under per-VMA locks without touching mmap_lock.

Our own observation of only 700-1200 contended mmap-lock sections per run is what the pedsort source predicts: roughly 10-20 mmap/munmap calls per thread [I].

Two further points:
- The TCLocks stock curve does not collapse at 40 cores. It peaks at 56-84 threads at about 510 jobs/hour [F], which is our number at 60 threads (521). Its decline lies beyond the size of our 64-vCPU VM.
- The curve that does peak at 32-40 threads is IntervalVM's Fig. 15d. That run uses `-m 2048`, glibc malloc, and a 48-core machine whose points above 48 are hyperthreads.

**(b) LevelDB readrandom.**
In TCLocks, ShflLocks and CNA this is a user-space lock benchmark. The kernel is stock, and "Stock"/"Pthread" is the glibc mutex.
- Every `Get()` takes the global `DBImpl::mutex_` twice, plus sharded LRU-cache mutexes.
- Once that mutex is contended, glibc parks waiters with futex, and throughput is set by lock hand-off and wake-up latency.

Our curve is essentially the TCLocks 2-socket stock curve (Fig. 6b), so there is no discrepancy to explain there.

The sharp published drops come from three different situations:
1. An empty or near-empty database, where a Get is almost only the global lock: 1 thread is very fast and 2 threads fall to about a third (CNA Fig. 11b; TCLocks Fig. 6a has the same shape [I]).
2. A glibc mutex on an 8-socket machine (ShflLocks Fig. 12).
3. IntervalVM's different workload: an 8 GB database with 4 KiB values whose table cache thrashes, so every table open/evict is an mmap/munmap and the bottleneck is mmap_lock writers (peak at 4 threads).

## 1. Sources read

| Source | Where | How read |
|---|---|---|
| TCLocks, OSDI 2023 | https://www.usenix.org/system/files/osdi23-gupta.pdf | full text, Fig. 4 and 6 rendered |
| TCLocks artifact | https://github.com/rs3lab/TCLocks | scripts and benchmark sources read |
| TCLocks artifact guide | https://rs3lab.github.io/TCLocks/docs/artifact.html | read |
| ShflLocks, SOSP 2019 | https://gts3.org/assets/papers/2019/kashyap:shfllock.pdf | sections 6.2 and 6.4, Fig. 10 and 12 |
| ShflLocks artifact | https://github.com/sslab-gatech/shfllock | file list only; it contains no LevelDB run script |
| CNA, EuroSys 2019 (arXiv version) | https://arxiv.org/abs/1810.05600 | section 7, Fig. 11 |
| CST locks, USENIX ATC 2017 | https://www.usenix.org/system/files/conference/atc17/atc17-kashyap.pdf | section 7.1, Fig. 5 |
| MOSBENCH, OSDI 2010 | https://pdos.csail.mit.edu/papers/linux:osdi10.pdf | sections 3.6 and 5.7 |
| Bonsai, ASPLOS 2012 | https://people.csail.mit.edu/nickolai/papers/clements-bonsai.pdf | Psearchy passages |
| IntervalVM, SOSP 2025 (author copy; DOI 10.1145/3731569.3764807) | https://travis1829.github.io/assets/pdf/interval-vm.pdf | sections 1, 7, 7.3, Fig. 1 and 15 |
| IntervalVM artifact | https://github.com/kaist-cp/interval-vm | psearchy/, leveldb/, metis/, lockstat/ scripts read |
| LevelDB v1.20 | https://github.com/google/leveldb/tree/v1.20 | Get path read; diffed against the TCLocks copy |
| glibc `libio/filedoalloc.c` at tags 2.11, 2.21, 2.22, 2.23, 2.31, 2.39, 2.42 | https://github.com/bminor/glibc | read |
| glibc `stdlib/msort.c` (2.31), `stdlib/qsort.c` (2.39, 2.42) | same | read |

Local copies are under `/root/kdwork/research-src/` (papers in `pdf/`, rendered figures in `pdf/img/`, clones in `tclocks/`, `intervalvm/`, `leveldb/`).

Not accessed or not verified:
- The kernel git history. Kernel version numbers below come from LWN, man-pages and mailing-list pages, not from `git log`.
- Any Linux 7.0-specific changelog.
- The identity of the "2-socket machine" in TCLocks Fig. 6b. The paper does not give it.
- How ShflLocks populated its LevelDB database. Neither paper nor artifact says.
- The RadixVM paper was downloaded, but it does not mention Psearchy.

## 2. Psearchy

### 2.1 What pedsort does [S: source code]

The TCLocks copy (`src/benchmarks/vbench/psearchy/mkdb/pedsort.C`) and the IntervalVM copy (`psearchy/mkdb/pedsort.C`) are identical apart from one cosmetic line.

1. **Serial start.** `main()` reads the file list from stdin and inserts every name into a Berkeley DB (`n2f`). This is single-threaded and is inside the measured time.
2. **Workers.** One worker per core: threads by default, processes with `-p`. Each pins itself to its CPU.
3. **Per-worker memory.** Each worker mallocs four buffers of `maxmem/4` bytes (`-m` is in MB) and memsets two of them (hash table and block array). With `-m 128` that is 4 x 32 MB with 64 MB zeroed at once; the rest is touched as it fills.
4. **Phase 1.** Workers take file numbers from a shared atomic counter. For each file: `fopen(name,"r")`, a `getc()` loop to split words, insert into the private hash table, `fclose`. Files are not mmapped by pedsort itself.
5. **Flush.** When a buffer fills, `flushwords()` runs `qsort()` over the whole table and writes an intermediate file with `putc()`. glibc's qsort is a merge sort that mallocs a temporary buffer as large as the array (`msort_with_tmp`).
6. **Phase 2.** Each worker merges its intermediate files (up to 800 open at once), writes the final index and Berkeley DB files (`-l 200000` starts a new DB every 200,000 words), then frees its buffers.

Kernel-visible activity is therefore:
- anonymous page faults (hash-table memory and the sort temporary);
- mmap/munmap from malloc/free of large blocks;
- open/read/close of about 93k cached files;
- a few tmpfs file creations and writes per worker.

### 2.2 What the sources say the bottleneck is

**MOSBENCH (OSDI 2010), section 5.7** [S]. Linux 2.6.35-rc5, 48 cores (8 x 6-core Opteron 8431), 368 MB in 33,312 files, 48 MB hash table per core, output on tmpfs.
- "Threaded pedsort scales poorly because a per-process kernel mutex serializes calls to mmap and munmap for a process' virtual address space. pedsort reads input files using libc file streams, which access file contents via mmap, resulting in contention over the shared address space".
- System time went from 2.3 s at 1 core to 41 s at 48 cores.
- Their fix was one process per core. After it, "system time remains small, so the kernel is not a limiting factor"; the remaining decline is `msort_with_tmp` missing in the L3 cache ("pedsort is bottlenecked by cache capacity").
- They also note that the threaded version is slower even on one core, because threads force glibc into its thread-safe stdio variants.

**Bonsai (ASPLOS 2012)** [S]. Linux 2.6.37, 80 cores, same input, 128 MB table.
- Threads "use libc's stdio library to read files, which internally calls mmap and munmap to manage memory for stream buffers, resulting in ~30,000 small anonymous mmap/munmap pairs".
- "With read/write locking, this base lock contention is further aggravated by page faults acquiring the mmap_sem in read mode; indeed, performance decays beyond the peak at 32 cores owing to the non-scalability of Linux's read/write lock implementation."
- Psearchy "is ultimately limited both by lock contention between mapping operations and by lock contention within glibc itself".

**glibc source** [S].
- Tags 2.11, 2.21 and 2.22: `_IO_file_doallocate` uses `ALLOC_BUF`, which is `mmap(0, ROUND_TO_PAGE(size), PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS, -1, 0)`.
- Tags 2.23, 2.31, 2.39 and 2.42: `p = malloc (size);`.
- The change is the fix for glibc BZ #16374, "don't use mmap for FILE buffers" (https://patchwork.sourceware.org/comment/13711/).
- So one mmap/munmap pair per fopen/fclose exists only up to glibc 2.22.

**CST locks (ATC 2017), section 7.1 and Fig. 5c** [S]. Linux 4.6/4.7, 8 sockets, 120 cores.
- Psearchy "does around 96,000 small and large mmap/munmap operations from 96,000 files with multiple threads, which taxes the writer side of the rwsem in the memory subsystem as well as the allocation of the inodes".
- "the native lock suffers from the scheduler intervention after 45 cores, as it spends up 54.4% being idle, whereas the CST-rwsem is only idle for 11.4% of the time."
- [F] Vanilla flattens at about 150 jobs/hour from roughly 60 threads; CST reaches about 200 at 120.

**TCLocks (OSDI 2023), section 6.2 and Fig. 4a** [S].
- Paper: 8 sockets, 224 cores, hyper-threading off, tmpfs. It says Linux v5.14.19; the artifact ships 5.14.16.
- The Psearchy description is the CST sentence almost word for word: "around 96,000 small and large mmap/munmap operations from 96,000 files", "stresses the writer side of the rwsem in the memory subsystem and inode allocation in the file system layer".
- "TCLock outperforms existing locks up to 2.2x."
- "ShflLock and Stock have similar performance."
- "we observe that psearchy's performance drops with increasing core count, which happens due to the contention in the file stream glibc library."

[F] Fig. 4a, jobs/hour:

| Threads | 28 | 56 | 84 | 112 | 140 | 168 | 196 | 224 |
|---|---|---|---|---|---|---|---|---|
| Stock | 340 | 510 | 505 | 440 | 400 | 370 | 340 | 290 |
| TCLocks | 460 | 750 | 830 | 760 | 670 | 680 | 600 | 510 |

ShflLock is slightly below Stock. CNA is flat at about 40, which looks broken.

**TCLocks artifact** [S].
- The guide says the paper's machine has Xeon Platinum 8276L CPUs and runs Ubuntu 20.04 with Linux 5.4.0 as host.
- The benchmarks run inside a QEMU/KVM guest: `-smp cores=28,threads=1,sockets=8`, 8 NUMA nodes of 16 GB, vCPUs pinned, guest kernel 5.14.16 with `CONFIG_PARAVIRT_SPINLOCKS` off.
- Psearchy runs through vbench: `mode=thread`, `order=seq`, `mem=128`, `dblim=200000`, `taskset -c 0-(N-1)`.
- Input is the Linux 5.14.16 source tree, prefetched and sorted largest file first.
- Output goes to `tmpfs-separate`, which is one tmpfs mount per CPU.
- `run.sh` exports `LD_PRELOAD=/usr/local/lib/libjemalloc.so.2` before starting vbench.
- The paper does not say whether its published numbers came from this guest or from bare metal.

**IntervalVM (SOSP 2025), section 7.3, Fig. 1 and Fig. 15d** [S].
- Linux 6.8.0, Ubuntu 24.04 default configuration, 2 x Xeon Gold 6248R (48 cores, 96 threads). Thread counts go up to 96, and the paper marks everything above 48 as the hyper-threading range.
- Psearchy "intensively uses both anonymous memory and file-backed memory, by allocating per-thread hash tables using malloc() and reading files using a few ten thousands of mmap()s and munmap()s in glibc's stdio library".
- "IntervalVM outperforms Linux by 1.27x. Notably, in both IntervalVM and Linux, throughput declines after reaching its peak - an expected behavior in Psearchy due to high cache miss rates at higher thread counts [MOSBENCH]."
- Fig. 1 (lock_stat on a 6.8.0 debug kernel): Psearchy wastes up to 41% of its time waiting for mmap_lock. [F] About 3% at 12 threads, 15% at 30, 30% at 50-60, 41% at 96.
- [F] Fig. 15d: Linux peaks at about 305 jobs/hour at 32-36 threads and falls to about 175 at 96. IntervalVM peaks at about 385 at 40-48 and falls to about 275 at 96.
- Artifact `psearchy/run.sh`: `./mkdb/pedsort -t /tmp/db/db -c $CPUS -m 2048 < linux-6.8-files.txt`. That is threads, 2048 MB per thread, no `-l`, one shared tmpfs, no taskset, glibc malloc, Linux 6.8 tree.

ShflLocks and CNA do not use Psearchy. ShflLocks' kernel applications are AFL, Exim and Metis (Fig. 10). It describes Metis as stressing "the reader side of the mmap_sem", with stock rwsem having "33% more idle time due to its naive parking strategy" (v4.19-rc4, 8 sockets, 192 cores).

### 2.3 Why the published curves collapse and ours does not, ranked [I]

**1. Kernel generation: page faults no longer take mmap_lock.**
- In 2.6.37, 4.7 and 5.14, every anonymous fault takes the address-space rwsem for read. Psearchy does N x (64 MB of zeroing, plus buffer fill, plus sort temporaries) of such faults, mixed with mmap/munmap writers.
- Bonsai and CST both describe this reader/writer mix on one rwsem as the collapse, and CST measures the idle time.
- Since 6.4, anonymous faults run under per-VMA locks, so only the mmap/munmap calls still serialize.
- This is the only explanation that also accounts for TCLocks gaining 1.35-1.5x at 28-56 threads on 5.14 [F] while our lock gains nothing on 7.0 at the same thread counts.

**2. glibc generation: no mmap per input file.**
- The MOSBENCH and Bonsai collapse (peak at about 32 cores) is driven by the roughly 30,000 stdio-buffer mmap/munmap pairs. This cannot happen with glibc 2.23 or later.
- The "96,000 mmap/munmap" sentence in CST/TCLocks and the "few ten thousands of mmap()s ... in glibc's stdio library" sentence in IntervalVM repeat that description. On their distributions (Ubuntu 20.04 has glibc 2.31; 24.04 has 2.39) the stdio buffer is malloc'd, so these counts are probably not what those runs did. I could not verify this.
- With modern glibc and `-m 128`, the source predicts only about 10-20 mmap/munmap/mprotect calls per thread: four 32 MB buffers, the qsort temporary per flush, the thread stack and malloc arena, and Berkeley DB caches. That is the order of our 700-1200 contended sections.

**3. Machine size and topology.**
- TCLocks stock keeps scaling to 56 threads and matches our throughput there (about 510 vs our 521 at 60). Its decline starts beyond 84 threads, at three or more 28-core sockets.
- A 64-vCPU, 2-node VM never reaches that regime.
- In IntervalVM, everything past 48 threads is SMT siblings.

**4. Parameters.**
- IntervalVM's `-m 2048` gives every thread four 512 MB buffers (1 GB zeroed up front), a qsort over a 512 MB table with a 512 MB temporary, and munmap of all of it at the end.
- That is a fixed per-thread cost that grows with N and passes through mmap_lock: munmap of populated 512 MB regions, and mmap/munmap writers queueing behind each other.
- With `-m 128` this cost is 16x smaller. I expect this to be why Linux 6.8 still shows 41% mmap_lock wait in their run while we see almost none.

**5. Limits unrelated to kernel locks.** These cap every curve:
- cache and memory-bandwidth misses in `msort_with_tmp` (MOSBENCH);
- per-character FILE locking in multi-threaded glibc;
- the serial file-list load.

They make curves bend, but they do not respond to a kernel lock change.

**6. Allocator.** TCLocks preloads jemalloc, which retains and reuses large extents, giving fewer munmaps and more madvise. glibc munmaps every large free immediately. This changes the writer rate by a small factor only.

**7. tmpfs vs disk, input set.** All setups use page-cached input and tmpfs output. One tmpfs versus one per CPU matters little, because only a handful of files are created per thread. This is not a differentiator.

### 2.4 Experiments to confirm (in our VM)

- **A1, syscall census.** `strace -f -c -e trace=mmap,munmap,mprotect,madvise,brk pedsort ...` or `perf trace -s`. Expect tens of mmap/munmap calls per thread, not about 2 x 93k. This confirms cause 2.
- **A2, lock mode of faults.** `perf stat -e page-faults`, and a bpftrace count on `tracepoint:mmap_lock:mmap_lock_start_locking` split by `args->write`. On 7.0, read acquisitions should be thousands against millions of faults. If the kernel has `CONFIG_PER_VMA_LOCK_STATS`, compare `vma_lock_success` with `vma_lock_abort`/`vma_lock_miss` in `/proc/vmstat`.
- **A3, recreate old glibc.** In a scratch copy of pedsort.C, after the `fopen(files[d],"r")` call, mmap one anonymous page and pass it to `setvbuf(input, buf, _IOFBF, 4096)`; munmap it after `fclose`. This reproduces `ALLOC_BUF` exactly. If native 7.0 now bends and our lock separates from native, the writer side is confirmed as the lever.
- **A4, recreate the old fault path.** Run the same binary on the TCLocks 5.14.16 stock kernel in the VM, or on a 7.0 build with per-VMA locking forced off (this needs a Kconfig edit, since it is not a user-visible option). Look for `rwsem_down_read_slowpath`, `rwsem_down_write_slowpath`, `rwsem_optimistic_spin`, `osq_lock` and idle time in `perf top`. On 7.0, expect `lock_vma_under_rcu`, `do_anonymous_page`, `clear_page_erms`, `get_page_from_freelist` and user-side `msort_with_tmp`, `lookup`, `strcmp`, `getc`.
- **A5, IntervalVM parameters.** `-m 2048`, no `-l`, single tmpfs, no taskset. Check whether a peak appears, and whether `perf lock contention -ab` shows mmap_lock with `unmap_vmas`/`zap_pte_range` under it.
- **A6, process-mode control.** Add `-p`. If thread and process mode scale alike on 7.0, the shared address space is no longer a factor.
- **A7, THP setting.** Record `/sys/kernel/mm/transparent_hugepage/enabled`. With `always`, the 32 MB buffers fault 512x less often, which alone would hide a fault-path bottleneck. Rerun with `never`.
- **A8, serial fraction.** Time until pedsort prints "Building index", and its `u/s/r` line. MOSBENCH saw kernel time grow from 1.9% to 23% of the run.
- **A9, allocator.** Repeat with `LD_PRELOAD=libjemalloc.so.2`, as the TCLocks `run.sh` does.

## 3. LevelDB readrandom

### 3.1 What a Get() does in 1.20 [S: source code]

`DBImpl::Get` (`db/db_impl.cc` lines 1109-1154):
- `MutexLock l(&mutex_)` on entry. Under it: read the last sequence number and Ref the memtable(s) and the current Version.
- `mutex_.Unlock()`, then the search runs without the lock.
- `mutex_.Lock()` again for `UpdateStats`, and Unref of the same objects.

So there are two acquisitions of one global pthread mutex per Get, each with a very short critical section.

The search itself takes more mutexes:
- `TableCache::Get` does a `Lookup` and a `Release` on the table cache.
- `Table::BlockReader` does a `Lookup`, an `Insert` on a miss, and a `Release` on the block cache.

Both caches are `ShardedLRUCache` with 16 shards, each with its own mutex (`util/cache.cc`). That is about 4-5 more lock/unlock pairs per Get.

Other facts:
- `port::Mutex` is a default `pthread_mutex_t` (`pthread_mutex_init(&mu_, NULL)`).
- Table files are read through mmap (up to 1000 mappings on 64-bit), not pread.
- db_bench defaults: 1,000,000 keys, 100-byte values, 8 MB block cache.
- With those defaults the database is about 110 MB in a few dozen files, so every table stays open and mapped. In steady state there are no mmap/munmap calls and no file I/O.

Kernel time therefore comes only from the contended mutex path [I]:
- `futex(FUTEX_WAIT)` and `futex(FUTEX_WAKE)`;
- the futex hash-bucket spinlock;
- `try_to_wake_up` and run-queue locks;
- idle entry/exit and wake-up IPIs, which are costly in a guest.

**TCLocks copy of db_bench** [S: diff against upstream v1.20].
- Adds `--time_ms` (SIGALRM stops the read loop) and `--pin_threads`.
- `--pin_threads=1` makes benchmark thread i call `pthread_setaffinity_np` to CPU i, via a new `PosixEnv::PinThread`.
- Also adds `--writers`, `--writes` and CDF output.
- `DBImpl`, the cache and the table code are unchanged.
- `run_db_bench.sh` builds a bundled jemalloc, but the Makefile does not link it.

### 3.2 What the sources say

**CNA, section 7.1.2 and Fig. 11** [S]. User space, LiTL interposition, LevelDB 1.20, 2 x Xeon E5-2699 v3 (72 logical CPUs).
- "Each Get operation acquires a global database lock in order to take a consistent snapshot of pointers to internal database structures ... The search operation itself, however, executes without holding the database lock, but acquires locks protecting (sharded) LRU cache".
- They modified readrandom to run for a fixed 30 s.
- [F] Fig. 11a, pre-filled 1M-key database: all locks scale to about 1.2 ops/us at 8 threads. MCS then flattens at 1.45 and declines to 1.3 at 70; CNA reaches 1.85.
- [S] Fig. 11b, empty database: "the work outside of the critical sections ... is minimal and does not involve acquiring any LRU cache lock". [F] 2.8 ops/us at 1 thread, about 1.1 at 2 threads, plateau at 1.4-2.0.

**ShflLocks, section 6.4 and Fig. 12** [S]. User space, LiTL, 8 sockets, 192 cores.
- "We use the readrandom benchmark that contends on the global database lock."
- "Pthread only scales up to eight threads because it starts parking threads."
- [F] Pthread is about 2.0 ops/us at 1 thread, about 1.1 at 2, and flat at 0.8 from 8 threads on.

**TCLocks, section 6.4 and Fig. 6** [S]. User space, LiTL.
- "readrandom benchmark with 1M key-value pairs, that contends on the global database lock".
- `scripts/run-userspace-benchmark.sh` boots only the stock kernel.
- `run_db_bench.sh` loops over `litl_lock=("" libaqswonode_spinlock.sh libkomb_spinlock.sh)`, named `(stock shfllock komb)`. So "Stock" is the un-interposed glibc mutex. The kernel lock implementation is not varied in this figure.

[F] Fig. 6, Stock, ops/us:

| Threads | 1 | 2 | 4 | 8 | 28-32 | 56-64 | 128-224 |
|---|---|---|---|---|---|---|---|
| (a) 8-socket | 3.2 | 1.1 | 1.1 | 1.0 | 1.0 | 0.6 | 0.5 |
| (b) 2-socket | 0.7 | 1.1 | 1.5 | 1.55 | 1.4 | 0.8 | - |
| Ours, native 7.0 | 0.705 | 1.08 | 1.24 | 1.15 | 1.0-1.2 | 0.7 | - |

In (b), TCLock reaches 2.9.

**IntervalVM, section 7.3, Fig. 1 and Fig. 15b** [S]. Linux 6.8.0, LevelDB 1.23.
- Artifact: `fillrandom --num=2000000 --value_size=4096` into a database on the SSD, then `--benchmarks=readrandomsmall --use_existing_db=1 --threads=N`. No pinning.
- "Each thread reads a database file using mmap(), performs key-value lookups, and later invokes munmap() once the file is no longer needed. ... On Linux, threads contend for the mmap_lock ... under IntervalVM, contention on the mmap_lock is eliminated; instead, threads contend on LevelDB's global database lock."
- [F] Fig. 15b: Linux peaks at about 120 K ops/s at 4 threads, is about 70 K at 16, and about 50 K at 96. IntervalVM reaches about 530 K.
- Fig. 1: up to 40% of time waiting on mmap_lock, peaking at 12-16 threads. A footnote says the ratio then falls because the global database lock takes over.
- [I] Mechanism: 8 GB of data in 2 MB table files is several thousand files, but the table cache holds 990 (`max_open_files=1000` minus 10). Random reads keep evicting and reopening tables, and each open/evict is an mmap/munmap.

### 3.3 Why other curves drop sharply and ours looks the way it does, ranked [I]

**1. Different benchmark regime.** This is not a kernel difference.
- 3.2 -> 1.1 ops/us from 1 to 2 threads (TCLocks Fig. 6a) is the empty-database shape of CNA Fig. 11b.
- A pre-filled 1M-key database gives 0.25-0.7 ops/us at one thread and scales to 4-8 threads (CNA Fig. 11a, TCLocks Fig. 6b, ours).
- A 3.2 M ops/s single-thread rate is not plausible for a filled database on a machine whose 2-socket sibling gets 0.7.
- The older `leveldb-1.20/run.sh` in the artifact runs `readrandom --num=20` with no fill, which is effectively an empty database.
- I therefore think Fig. 6a (and probably ShflLocks Fig. 12) measured a mostly-miss or empty-database Get. The papers do not say so.

**2. The user-space mutex is the bottleneck.**
- Two acquisitions of `DBImpl::mutex_` per Get, with a parking lock.
- Past about 4-8 threads, each hand-off costs a futex wake plus a scheduler wake-up, so throughput is flat or falling regardless of core count.
- ShflLocks states this for Pthread directly.
- Our 1.26 M peak at 6 threads and 1.0-1.2 M plateau is this regime.
- Kernel lock replacements can only touch the futex bucket lock and run-queue locks inside that path.

**3. NUMA and socket count.**
- Our fall to 0.7 M at 40-60 threads matches TCLocks 2-socket stock (0.8 at 56). The lock and the hot LevelDB structures bounce between nodes.
- On 8 sockets the plateau is lower (0.5-1.0) for the same reason.

**4. IntervalVM's collapse at 4 threads is an mmap_lock writer collapse.** It comes from table-cache thrashing. It is absent in the TCLocks configuration, where all tables stay mapped.

**5. Kernel version.**
- Small effect expected for the TCLocks configuration: it has no page faults or mmap calls in steady state.
- The futex and scheduler path existed in 5.14 and exists in 7.0.
- The per-process futex hash does not help when all waiters sit on one futex. Its history: merged for 6.16, disabled before the 6.16 release after a regression report, listed by man-pages as 6.17.

**6. Guest effects.** Parking and waking vCPUs costs more than on bare metal (halt exits, IPIs). This could lower our plateau relative to bare metal, but does not change the shape.

**7. Allocator and compression.**
- glibc malloc arenas see cross-thread frees of cached blocks.
- Whether Snappy was linked decides whether blocks go through the block cache at all. In 1.20, uncompressed mmapped blocks are never inserted.
- These shift the plateau height by tens of percent.

### 3.4 Experiments to confirm (in our VM)

- **B1, empty-database run.** Fresh directory, no fillseq, no `--use_existing_db`: `db_bench --db=/tmp/empty --benchmarks=readrandom --threads=N --pin_threads=1 --time_ms=30000`. Expect about 3 M ops/s at 1 thread and about 1 M at 2. That reproduces TCLocks Fig. 6a and CNA Fig. 11b, and confirms cause 1.
- **B2, futex census.** `perf stat -e syscalls:sys_enter_futex,context-switches,cpu-migrations` at 1, 2, 4, 8 and 32 threads. Futex calls per operation should go from about 0 to order 1 exactly where scaling stops.
- **B3, profile.** `perf record -g`.
  - User side: `pthread_mutex_lock`, `__lll_lock_wait`, `__lll_lock_wake`, `leveldb::DBImpl::Get`, `LRUCache::Lookup`, `LRUCache::Release`.
  - Kernel side: `futex_wait`, `futex_wake`, `futex_q_lock`, `native_queued_spin_lock_slowpath` (check callers: futex bucket vs `try_to_wake_up`), `select_idle_sibling`, `schedule`, and the idle routine.
- **B4, kernel lock share.** `perf lock contention -a -b -- sleep 10` during a 32-thread run. If total kernel spinlock wait is a few percent of CPU time, no kernel lock can move this benchmark. That would explain a ratio near 1.0.
- **B5, swap the user-space lock.** Run under LiTL (`libmcs_spinlock.sh`, `libaqswonode_spinlock.sh`, `libkomb_spinlock.sh` from the TCLocks tree). The plateau should move as in Fig. 6b (about 1.3 for ShflLock, about 2.9 for TCLock). That proves the limiter is the user-level lock.
- **B6, IntervalVM regime.** `fillrandom --num=2000000 --value_size=4096`, then `readrandom --use_existing_db=1 --threads=N`.
  - Count mmap/munmap calls.
  - Look for `rwsem_down_write_slowpath`, `unmap_region` and TLB-shootdown IPIs.
  - Repeat with `--open_files=50000`. With no table eviction, the collapse at 4 threads should disappear.
  - This is the LevelDB variant in which a kernel mmap_lock replacement could matter.
- **B7, NUMA.** 32 threads on one node versus 16+16, and `--pin_threads=0`, to size the cross-node drop.
- **B8, wake-up cost in the guest.** Compare the guest's default idle with `idle=poll` or the haltpoll cpuidle governor at 8-32 threads. A large change means wake-up latency sets the plateau.
- **B9, build check.** `ldd db_bench` and the build log for `-DSNAPPY`, tcmalloc or jemalloc.

## 4. Kernel changes between 5.14 and 7.0: do they explain "no collapse on 7.0"?

| Change | Version (source) | Psearchy / Metis-type collapse | LevelDB |
|---|---|---|---|
| Per-VMA locks for page faults | 6.4 (LWN 937943); file-backed and swap faults later, planned for 6.6 per Wilcox's slides, not verified in git | Yes, the main reason: faults stop taking mmap_lock for read | TCLocks config: irrelevant. IntervalVM config: no, writers still serialize (its collapse is measured on 6.8) |
| Maple tree for VMAs | 6.1 | Only as the prerequisite for lockless VMA lookup | No |
| rwsem rework (owner tracking, handoff); reader optimistic spinning added then removed | 5.3; removal is commit 617f3ef95177 (LKML), 5.11 by my recollection | Explains differences against 2.6.37 and 4.7 results. Already present in TCLocks' 5.14, so it does not explain 5.14 vs 7.0 | No |
| munmap downgrades to read lock while zapping | 4.20 by my recollection, not verified | Already in 5.14 | Minor |
| MADV_DONTNEED under per-VMA lock | patches June 2025 (patchew); merge release not verified | Minor: allocator trimming | No |
| Per-process private futex hash | merged 6.16, disabled in 6.16, man-pages lists 6.17 | No | Unlikely: one hot futex is one bucket either way |
| Fault-path costs (allocator per-cpu lists, LRU batching, large folios) | various, not verified | Raise the ceiling, but do not remove a lock collapse | No |
| glibc stdio buffers malloc'd instead of mmap'd (user space, not kernel) | glibc 2.23 (source tags) | Yes for MOSBENCH/Bonsai-era curves | No |

## 5. Two corrections to the question's premises

- **TCLocks does not show stock Psearchy collapsing at 40 cores.** It shows a peak at 56-84 threads, where the absolute stock numbers are close to ours. The curves that turn over at 32-45 are Bonsai (2.6.37), CST (4.7, "after 45 cores") and IntervalVM (6.8, `-m 2048`, 48 physical cores).
- **TCLocks' LevelDB figure does not evaluate kernel locks.** It evaluates user-space locks under a stock kernel. Running `run_db_bench.sh` with a modified kernel exercises only the futex and scheduler path behind a glibc mutex, so a ratio near 1.0 is the expected outcome there [I].
