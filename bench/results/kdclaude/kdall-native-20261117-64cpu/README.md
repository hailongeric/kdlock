# kdlock with delegation against native Linux, whole kernel

Done on 2026-11-17 in the kdclaude VM: 64 vCPUs as 2 nodes, 24 GiB, host
fixed at 2.7 GHz, `nokaslr nopvspin`.

## 1. Kernels and method

| kernel | what it is |
|---|---|
| `7.0.0-38-kdnat1` #1 | **native**: the kdall1 tree (`/mnt/kdlock-builds/kda/src`) and configuration with only `CONFIG_KDLOCK_ALL` off. `apply_all.py` puts every edit inside `#ifdef CONFIG_KDLOCK_ALL`, so this is the unmodified kernel with native locks (the kdlock code is built but unused). `diff` of the two `.config` files: that one line. |
| `7.0.0-38-kdall1` #3 | **kd**: every spinlock, raw spinlock, rwlock, mutex, ww_mutex and rwsem is a kdlock (KERNEL_INTEGRATION 4d); `3ff2d94e` |
| `7.0.0-38-kdall2` #4 | kdall1 plus the ww_mutex spin phase (4.1, `48f57b3b`) |
| `7.0.0-38-kdall3` #5 | kdall2 plus the node order in plain mode (4.2, `130cc457`): the final kernel of section 5 |
| `7.0.0-38-kdnat2`, `-kdnat3`, `-kdnat4` | native locks, kdlock built in, with the kdall3 sources and with the two rejected era changes (4.3); for nano measurements of native against kd in one boot |

- **Modes.** Each workload runs in three modes:
  - **native** on kdnat1;
  - **kd off** on kdall1 without the daemon: every lock is a kd lock, no
    delegation;
  - **kd on** on kdall1 with `jit/kd_daemon.py` and the allow lists
    `api.txt`, `torture.txt` and `mm.txt` (brk, mmap and munmap).
- **Boots.** `drive.sh` boots the guest into each kernel once with
  `grub-reboot` (GRUB's default entry stays `kdlock1`). The order is: a
  learning boot of kdall1 (one pass with the daemon, not counted), then
  kdnat1, kdall1, kdnat1, kdall1, kdnat1, kdall1. On kdall1 the order of
  off and on alternates between boots. Every value below is one run, so
  each mode has 3 values from 3 boots.
- **Suite.** `suite.sh MODE TAG` runs the workloads. The daemon's knowledge
  persists across boots (same build, `nokaslr`), so "on" starts with learned
  images. The locktorture module's text is new at every load, so its sites
  are learned again in each run (README of `kdall-deleg-20261117-64cpu`,
  section 4).
- **Ratios.** Medians of the three runs. A difference is called a result
  only when the three runs of the two modes do not overlap.
- **Files:**
  - `data/runs.txt` (every run, with the kd counters before and after);
  - `data/summary.md` (`cmp_summary.py`);
  - `data/suite-*.out`, `data/kdd-*.log.xz` (daemon, `xzcat`), `data/complaints.txt`;
  - `data/prof-*.log` (profiles, section 3).

No kernel complaint in any boot (`data/complaints.txt`).

## 2. The page fault benchmark (`bench/pf_random.c`)

`pf_random THREADS SECONDS -g 10 [-w]`. One round:

1. Thread 0 maps a 10 GB private anonymous region with `MADV_NOHUGEPAGE`,
   so every fault is a 4 KB fault.
2. All threads fault it in. The round walks a pseudo-random permutation of
   all 2.6 M page numbers (a bijection of `[0, 2^22)` made of multiply,
   add and xor-shift steps, with cycle walking). Thread t takes the
   positions t, t+T, t+2T, and so on. Every page faults exactly once per
   round, from a random thread, in random order, so no fault-around or
   huge-page path merges faults.
3. After a barrier, thread 0 unmaps the region, and the next round starts.

Without `-w` each thread reads a word of each page and checks it is 0.
With `-w` it writes a tag (round, page) and, after all threads are done,
reads its pages back and checks the tags. The program reports the faults
per second over the fault phases and the munmap and mmap times. Every run
of the comparison passed its check.

**Result: parity.** Read 1.00-1.02, write 0.97-1.05 (section 3). These
faults hardly touch a lock that kdlock replaces:

- **Per-VMA locks:** a fault finds its VMA under a per-VMA lock, which is a
  reference count, not a kdlock. It never takes the mmap lock.
- **Split PTE locks:** the PTE lock is per page-table page. 10 GB has
  about 5 000 of those, and the random order spreads the threads across
  them.
- **The barrier:** mmap and munmap never overlap the faults.

The kd counters show it. Per 15 s run there are 3.4 k, 6.2 k and 13 k
contended kdlock acquisitions for reads (16, 32 and 64 threads), against
110-130 M faults, about 0.003%. Writes have 30-160 k: page allocation and
the LRU lists. Lock contention on this path would need faults on few
page-table pages, or VMA changes concurrent with the faults.

## 3. Results

kdall1 (before the optimizations of section 4) against kdnat1, 3 boots each
(`data/runs.txt`, `data/summary.md`). Rates: pf in faults/s, will-it-scale in
iterations/s (average over the threads), api_stress in operations/s,
locktorture in writes per 30 s.

| workload | threads | native | kd off | kd on | off/native | on/native | delegated, handbacks per on run (median) |
|---|---|---|---|---|---|---|---|
| pf read | 16 | 7.52 M, 7.62 M, 7.32 M | 7.5 M, 7.67 M, 7.77 M | 7.51 M, 7.45 M, 7.68 M | **1.02** | **1.00** | 137, 2 |
| pf read | 32 | 8.44 M, 8.51 M, 8.54 M | 8.54 M, 8.5 M, 8.69 M | 8.85 M, 8.57 M, 8.59 M | **1.00** | **1.01** | 60, 1 |
| pf read | 64 | 8.36 M, 8.5 M, 8.69 M | 8.63 M, 8.65 M, 8.33 M | 8.6 M, 8.21 M, 8.51 M | **1.02** | **1.00** | 296, 1 |
| pf write | 16 | 3.79 M, 4.07 M, 3.89 M | 3.77 M, 3.67 M, 3.81 M | 4.25 M, 3.84 M, 3.96 M | **0.97** | **1.02** | 65, 1 |
| pf write | 32 | 4.64 M, 4.18 M, 4.03 M | 4.06 M, 4.24 M, 4.07 M | 4.31 M, 4.23 M, 4.95 M | **0.97** | **1.03** | 175, 3 |
| pf write | 64 | 6.24 M, 6.52 M, 6.34 M | 6.78 M, 5.78 M, 6.25 M | 6.11 M, 6.78 M, 6.63 M | **0.99** | **1.05** | 154, 2 |
| wis mmap1 | 16 | 303 k, 301 k, 308 k | 313 k, 302 k, 310 k | 391 k, 399 k, 381 k | **1.02** | **1.29** | 8.35 M, 39 |
| wis mmap1 | 32 | 303 k, 314 k, 300 k | 310 k, 308 k, 245 k | 405 k, 397 k, 384 k | **1.02** | **1.31** | 8.67 M, 36 |
| wis mmap1 | 64 | 177 k, 178 k, 178 k | 276 k, 277 k, 282 k | 314 k, 323 k, 317 k | **1.56** | **1.79** | 6.91 M, 8 |
| wis mmap2 | 16 | 368 k, 366 k, 338 k | 362 k, 346 k, 354 k | 394 k, 394 k, 395 k | **0.97** | **1.08** | 8.57 M, 125 |
| wis mmap2 | 32 | 355 k, 354 k, 357 k | 348 k, 350 k, 351 k | 369 k, 387 k, 389 k | **0.98** | **1.09** | 8.47 M, 26 |
| wis mmap2 | 64 | 209 k, 205 k, 213 k | 314 k, 310 k, 312 k | 306 k, 312 k, 317 k | **1.49** | **1.49** | 6.81 M, 5 |
| wis brk1 | 16 | 853 k, 716 k, 811 k | 765 k, 748 k, 756 k | 1.03 M, 1.08 M, 1.13 M | **0.93** | **1.34** | 11.6 M, 1558 |
| wis brk1 | 32 | 698 k, 676 k, 679 k | 729 k, 736 k, 721 k | 1.08 M, 1.03 M, 1.12 M | **1.07** | **1.59** | 11.2 M, 56 |
| wis brk1 | 64 | 395 k, 397 k, 403 k | 789 k, 796 k, 778 k | 849 k, 904 k, 907 k | **1.99** | **2.28** | 9.83 M, 54 |
| wis page_fault1 | 16 | 2.95 M, 2.98 M, 3.01 M | 2.57 M, 2.65 M, 2.62 M | 2.3 M, 2.37 M, 2.49 M | **0.88** | **0.80** | 79, 6 |
| wis page_fault1 | 32 | 2.88 M, 2.86 M, 2.88 M | 2.92 M, 2.94 M, 2.9 M | 2.95 M, 2.91 M, 3.02 M | **1.02** | **1.02** | 84, 12 |
| wis page_fault1 | 64 | 4.06 M, 4.18 M, 4.16 M | 4.42 M, 4.32 M, 4.47 M | 4.45 M, 4.29 M, 4.46 M | **1.06** | **1.07** | 192, 23 |
| wis page_fault_shared1 | 16 | 3.26 M, 3.27 M, 3.17 M | 3.1 M, 3.08 M, 3.07 M | 2.99 M, 3.12 M, 3.02 M | **0.94** | **0.93** | 65, 2 |
| wis page_fault_shared1 | 32 | 4.91 M, 4.9 M, 4.9 M | 4.6 M, 4.6 M, 4.55 M | 4.55 M, 4.57 M, 4.54 M | **0.94** | **0.93** | 44, 2 |
| wis page_fault_shared1 | 64 | 6.33 M, 6.32 M, 6.44 M | 6.22 M, 6.3 M, 6.19 M | 6.25 M, 6.28 M, 6.17 M | **0.98** | **0.99** | 290, 0 |
| wis page_fault_shared3 | 16 | 1.57 M, 1.59 M, 1.6 M | 1.64 M, 1.62 M, 1.64 M | 1.61 M, 1.64 M, 1.64 M | **1.03** | **1.03** | 77, 1 |
| wis page_fault_shared3 | 32 | 1.72 M, 1.71 M, 1.7 M | 1.44 M, 1.43 M, 1.44 M | 1.43 M, 1.44 M, 1.43 M | **0.84** | **0.84** | 56, 0 |
| wis page_fault_shared3 | 64 | 1.02 M, 1.01 M, 1.05 M | 1.1 M, 1.07 M, 1.09 M | 1.08 M, 1.09 M, 1.09 M | **1.07** | **1.06** | 5, 0 |
| api setfd | 16 | 1.48 M, 1.39 M, 1.41 M | 1.85 M, 1.82 M, 1.69 M | 3.24 M, 3.19 M, 3.63 M | **1.28** | **2.29** | 17.8 M, 0 |
| api setfd | 64 | 665 k, 680 k, 668 k | 1.88 M, 1.89 M, 1.98 M | 6.32 M, 6.17 M, 6.19 M | **2.82** | **9.27** | 34.8 M, 0 |
| api ofd | 16 | 1.1 M, 986 k, 949 k | 1.5 M, 1.42 M, 1.49 M | 2.61 M, 2.66 M, 2.61 M | **1.51** | **2.65** | 19.6 M, 0 |
| api ofd | 64 | 405 k, 474 k, 452 k | 1.1 M, 1.17 M, 1.18 M | 2.76 M, 2.74 M, 2.73 M | **2.59** | **6.07** | 20.6 M, 0 |
| api pipe | 16 | 517 k, 529 k, 514 k | 515 k, 524 k, 504 k | 485 k, 479 k, 481 k | **1.00** | **0.93** | 1.54 M, 1557 |
| api pipe | 64 | 524 k, 529 k, 506 k | 475 k, 480 k, 479 k | 452 k, 449 k, 445 k | **0.91** | **0.86** | 1.46 M, 542 |
| api seek | 16 | 1.28 M, 1.19 M, 1.24 M | 1.17 M, 1.14 M, 1.13 M | 1.15 M, 1.27 M, 1.1 M | **0.92** | **0.93** | 26, 810 |
| api seek | 64 | 1.07 M, 1.15 M, 1.2 M | 959 k, 976 k, 978 k | 941 k, 948 k, 880 k | **0.85** | **0.82** | 0, 318 |
| api uts | 16 | 1.13 M, 1.27 M, 1.2 M | 3.13 M, 3.15 M, 3.18 M | 3.87 M, 3.85 M, 3.9 M | **2.63** | **3.22** | 2.44 M, 92 k |
| api uts | 64 | 916 k, 912 k, 914 k | 2.76 M, 2.78 M, 2.79 M | 4.42 M, 4.48 M, 4.45 M | **3.04** | **4.88** | 4.07 M, 39 k |
| api xattr | 16 | 1.79 M, 1.81 M, 1.81 M | 1.71 M, 1.68 M, 1.71 M | 1.68 M, 1.74 M, 1.75 M | **0.94** | **0.96** | 90, 3 |
| api xattr | 64 | 1.77 M, 1.79 M, 1.72 M | 1.63 M, 1.61 M, 1.62 M | 1.67 M, 1.71 M, 1.73 M | **0.92** | **0.97** | 0, 0 |
| torture spin_lock | 128 | 22 M, 20.3 M, 21.4 M | 75.7 M, 76.4 M, 76.9 M | 92.9 M, 91.6 M, 96.1 M | **3.58** | **4.35** | 69.5 M, 2388 |
| torture rw_lock | 128 | 4.13 M, 4.26 M, 3.99 M | 4.94 M, 5.02 M, 4.67 M | 4.93 M, 4.71 M, 4.81 M | **1.20** | **1.17** | 1.57 M, 1709 |
| torture mutex_lock | 128 | 45.4 M, 45.6 M, 46.2 M | 34.3 M, 33.2 M, 37.8 M | 44.7 M, 49.8 M, 49.1 M | **0.75** | **1.08** | 23.4 M, 1031 |
| torture rwsem_lock | 128 | 655 k, 620 k, 543 k | 340 k, 435 k, 340 k | 387 k, 346 k, 360 k | **0.55** | **0.58** | 92 k, 326 |
| torture ww_mutex_lock | 128 | 25.6 M, 25.6 M, 26.2 M | 5.93 M, 5.95 M, 5.91 M | 5.79 M, 5.94 M, 5.93 M | **0.23** | **0.23** | 93, 3 |

### Gains

Results where the three runs of each mode do not overlap:

- **Syscall locks, delegation on:**
  - setfd: 2.29× at 16 threads, 9.27× at 64.
  - ofd: 2.65× and 6.07×.
  - uts: 3.22× and 4.88×.
- **Plain mode already gains**, without delegation, where native collapses
  at 64 threads across both nodes:
  - setfd 1.28 / 2.82 and ofd 1.51 / 2.59 (16 / 64 threads);
  - uts 2.63 / 3.04;
  - will-it-scale mmap1, mmap2 and brk1 at 64 threads: 1.56, 1.49, 1.99.
- **mmap lock delegation** (brk, mmap, munmap):
  - mmap1 1.29 / 1.31 / 1.79 at 16 / 32 / 64 threads;
  - mmap2 1.08 / 1.09 / 1.49;
  - brk1 1.34 / 1.59 / 2.28.
- **locktorture:**
  - spin_lock 4.35 (off 3.58);
  - rw_lock 1.17;
  - mutex_lock 1.08 on, but 0.75 off (bad case 3).
- **Page faults** (pf_random, page_fault1 at 32 and 64 threads,
  page_fault_shared3 at 16 and 64): parity, or a few percent better.

### Bad cases and what the profiles show

Profiles: `prof.sh`, 5 s flat profiles (`perf record -a`, no call
graphs), context switches and kd counters per workload. They were taken on
kdnat1 (`data/prof-kdnat1.log`) and on kdall1 without and with the daemon
(`data/prof-kdall1-{off,on}.log`), one boot each.

1. **locktorture ww_mutex: 0.23** (off and on).
   - **Cause:** kd's ww_mutex never spun. A contended acquisition parked,
     and while waiters were parked, every acquisition walked all of them
     under the wait lock.
   - **Fixed in part:** section 4.1.

2. **locktorture rwsem: 0.55 off, 0.58 on.**
   - **Profiles:** native 97.8% `delay_halt_tpause` (the readers' 50 ms
     `mdelay`) and 1.5% `osq_lock`.
   - **Cause** (README of `kdall-deleg-20261117-64cpu`, sections 1 and 4):
     - native writers spin and pass the lock writer to writer while the
       readers sleep in FIFO order;
     - kd follows each write with a reader phase;
     - delegation gets few writers, because they rarely wait behind
       another writer and the module's text is learned again at each load.
   - **Not changed here:** it is the reader-admission policy that the
     nano bench and the mmap lock were tuned with.

3. **Mutex in plain mode with waiters on both nodes:**

   | case | kd/native |
   |---|---|
   | locktorture mutex_lock, off | 0.75 |
   | seek, 64 threads | 0.85 off, 0.82 on |
   | pipe, 64 threads | 0.91 off |

   - **Profiles:** both kernels spin: native in `osq_lock` (94-96%), kd in
     its spinner queue (`kd_wait_sleepable`, 96-97%).
   - **The nano bench separates the cause** (kdnat1 has kdlock built in,
     so native and kd run in one boot): with a 16-line body, kd/native is
     1.05 at 32 workers on one node and falls with the workers on the
     second node, 0.95 / 0.87 / 0.73 / 0.66 / 0.65 with 4 / 8 / 16 / 24 /
     32 of them. Native's rate stays flat.
   - **Cause:** kd's queue hands over in arrival order, so the data moves
     between nodes at about every other handover.
   - **Fixed:** section 4.2.
   - **For locktorture specifically:** it also spends 50% of its time in
     the mutex's internal wait lock (`kd_q_lock_plain`), with 128 writers
     on 64 CPUs. Native: about 1%.

4. **pipe, delegation worse than plain:** 0.93 / 0.86 on, against 1.00 /
   0.91 off (16 / 64 threads).
   - **Counters:** per 15 s, 11 M sections were offered, 4.3 M delegated
     in 2.6 M sessions, and 6.7 M sessions ended at a plain waiter
     (`stop_plain`).
   - **Cause:** read and write hand back at the user copy, so the sites are
     switched off and on again; waiters with and without images alternate,
     and the sessions are too short to pay.
   - **Not changed:** taking `anon_pipe_read` and `anon_pipe_write` out of
     `bench/allow/api.txt` would make "on" equal to "off" for pipe.

5. **page_fault1 at 16 threads: 0.80 on, 0.88 off** (32 and 64 threads:
   1.02 and 1.07).
   - **Profiles:** the same shares on both kernels (`_raw_spin_lock` 34.9%,
     `kd_spin_lock` 35.3%; `charge_memcg` 15-16%).
   - **Not explained.**

6. **page_fault_shared1 at 16 and 32 threads: 0.93-0.94.**
   - **What contends:** all threads share one page-table page, so its
     split PTE lock (`pte_offset_map_lock`), a spinlock.
   - **Profiles:** native 58.9% in the queued spinlock slow path, kd 64-68%
     in `kd_q_lock_slow`.
   - **Not changed:** the spin class has no node order in plain mode.

7. **page_fault_shared3 at 32 threads: 0.84** (16 and 64 threads: 1.03 and
   1.06).
   - **What contends:** kernel-mode faults take the mmap lock for reading,
     and mprotect takes it for writing.
   - **Profiles:** native makes 3.57 M context switches in 5 s (readers
     sleep and are woken), kd 16 k. kd's readers wait outside, spinning
     (`kd_down_read_slow` 28%).
   - **Not changed:** this too is the rwsem policy.

8. **xattr: 0.92-0.94 off, 0.96-0.97 on.**
   - **What contends:** the inode's `i_rwsem`, taken for writing by
     setxattr. Its site (`vfs_setxattr`) is not on the allow list, so the
     writers wait in plain mode.
   - **Nano:** rwsem writers alone, in plain mode, run at 0.55-0.60 of
     native (section 4.3).

## 4. Optimizations

All in `kernel/`. The nano measurements ran in one boot of a kdnat kernel
(native locks, kdlock built in, no daemon, so kd runs plain), with
`run_grid.py`, 2 rounds of 2 s per point. Every point passed the bench's
data check (no torn body, counters equal to completed writes), and no
kernel complained.

| kernel | from | contents |
|---|---|---|
| kdall2 #4 | `48f57b3b` | 4.1 |
| kdnat2 #2, kdall3 #5 | `130cc457` | 4.1 + 4.2 (the final kernel) |
| kdnat3, kdall4 | rejected | + conditional era stores (4.3) |
| kdnat4, kdall5 | rejected | + era measurement before the write side (4.3) |

### 4.1 ww_mutex: spin while the holder runs (`48f57b3b`)

- **The change:** a ww acquisition spins in the mutex's spinner queue
  while the holder runs, before it parks (`kd_mutex_spin_lock()`).
- **When:** only when that is safe for wait-die, as native
  `ww_mutex_spin_on_owner()` decides it. The context holds no lock, so it
  never has to back off, and no waiter is parked, so it never takes the
  lock from an older parked context.

Focus runs (`focus.sh`, `data/focus.txt`, 6 boots alternating kdall2,
kdnat1 and kdall1, 2 runs each), locktorture ww_mutex, 30 s:

| | writes |
|---|---|
| kdnat1 | 25.7-26.5 M |
| kdall1 | 5.66-5.98 M (0.22) |
| kdall2 | 12.4-13.3 M (**0.48**) |

Nothing else in the focus set moved. locktorture ww_mutex for 60 s ends in
SUCCESS, and test-ww_mutex reports as before.

**What is left:** native keeps its wait list in stamp order and checks only
the first waiter with a context on each acquisition
(`__ww_mutex_check_waiters`). kd keeps FIFO order and walks every parked
waiter.

### 4.2 Plain mode: a waiter of the head's node first (`130cc457`)

A queue head of the mutex or rwsem-writer queue that still waits for the
holder looks up to 8 waiters ahead for one on its own node. It moves that
waiter directly behind itself (`kd_q_local_first()`, ARCHITECTURE 7a).
Each waiter it passes counts the pass, and one passed `kd_numa_plain` (16)
times is not passed again. kdnat2, one boot, kd/native with
`kd_numa_plain` 0 / 16 / 64 (`numa_plain.sh`):

| mutex nano body | 32 workers | 48 | 64 |
|---|---|---|---|
| 16 lines | 1.02 / 1.02 / 1.02 | 0.72 / **1.05** / 1.05 | 0.66 / **0.90** / 0.89 |
| 1 line | 1.05 / 1.07 / 1.07 | 1.19 / **1.50** / 1.51 | 1.02 / **1.35** / 1.35 |

The rwsem nano bodies did not change. There were about 15 000 moves per 2 s
point at 64 workers, against more than 4 million handovers: once a few
waiters move, the queue stays in node batches.

### 4.3 rwsem writers in plain mode: the era measurement (not adopted)

With writers only, kd's rwsem in plain mode runs at 0.55-0.60 of native,
on one node as well as across both. With 20% writes it is at 1.6-4.7.

**Locating the cost (kdnat3, one boot, 32 workers on one node):**

| setting | Mops/s |
|---|---|
| default | 2.18 |
| eras that can never start (`kd_rw_era_drain_ns=0`) | 2.21 |
| no era code (`kd_rw_era_ns=0`) | 3.21 |

So the cost is the measurement each writer makes right after taking the
write side, on the handover path: a two-node queue walk and stores to the
shared averages. Eras cannot simply go: with readers they are worth 1.8x
(1 line, 20% writes, 64 workers: 4.10 with eras against 2.30 without).

**Two changes were tried; neither is in the tree.** They are kept as
`rejected/*.patch` against `130cc457`.

- `era-conditional-store.patch`: store the averages only when they
  change. **No gain** (0.55 at 32 workers). The queue depth in the
  pressure changes from writer to writer, so the values change nearly
  every time.
- `era-measure-early.patch`: when no reader is in, measure before taking
  the write side, while the holder ahead still runs. **A trade-off:** 32
  workers 0.55 -> 0.67, but 48 and 64 workers 0.55 / 0.56 -> 0.51 / 0.51.
  Unchanged paths agree within 3% between those two boots.

**What is left even without any era code:** 0.59-0.86 of native. A writer
takes the queue mutex and then the writer bit, and changes the phase
counter, where native does one cmpxchg. With delegation, rwsem writers go
through sessions instead, which is where the mmap lock gains of section 3
come from.

## 5. After: kdall3 against native

The same suite and method as section 3, with kdall3 (`130cc457`: 4.1 + 4.2)
against kdnat1 in a second series of boots (a1-a6). A learning boot
(learn3) came first, so the daemon's knowledge for the new build existed.
Files:

- `data/runs.txt` (tags a1-a6 and learn3);
- `data/summary-final.md` (all values);
- `data/before_after.md` (`before_after.py`), reproduced below;
- `data/drive-final.log`, `data/suite-a*.out`, `data/kdd-a*.log.xz`.

No kernel complaint in any boot.

Each series is compared with its own native boots. A ratio in bold means
the three kd runs and the three native runs do not overlap; "~" means they
do.

| workload | threads | before: off/native | before: on/native | after: off/native | after: on/native |
|---|---|---|---|---|---|
| pf read | 16 | ~1.02 | ~1.00 | ~1.00 | ~1.02 |
| pf read | 32 | ~1.00 | **1.01** | ~0.99 | ~1.00 |
| pf read | 64 | ~1.02 | ~1.00 | ~0.99 | ~1.00 |
| pf write | 16 | ~0.97 | ~1.02 | **0.99** | ~0.98 |
| pf write | 32 | ~0.97 | ~1.03 | **0.95** | ~0.96 |
| pf write | 64 | ~0.99 | ~1.05 | ~0.97 | ~1.00 |
| wis mmap1 | 16 | ~1.02 | **1.29** | ~1.06 | **1.28** |
| wis mmap1 | 32 | ~1.02 | **1.31** | ~1.03 | **1.29** |
| wis mmap1 | 64 | **1.56** | **1.79** | **1.55** | **1.77** |
| wis mmap2 | 16 | ~0.97 | **1.08** | ~0.99 | **1.06** |
| wis mmap2 | 32 | **0.98** | **1.09** | ~1.01 | **1.10** |
| wis mmap2 | 64 | **1.49** | **1.49** | **1.55** | **1.56** |
| wis brk1 | 16 | ~0.93 | **1.34** | ~1.07 | **1.55** |
| wis brk1 | 32 | **1.07** | **1.59** | **1.09** | **1.61** |
| wis brk1 | 64 | **1.99** | **2.28** | **2.08** | **2.45** |
| wis page_fault1 | 16 | **0.88** | **0.80** | **0.80** | **0.81** |
| wis page_fault1 | 32 | **1.02** | **1.02** | **1.03** | ~1.05 |
| wis page_fault1 | 64 | **1.06** | **1.07** | **1.07** | **1.07** |
| wis page_fault_shared1 | 16 | **0.94** | **0.93** | **0.92** | **0.94** |
| wis page_fault_shared1 | 32 | **0.94** | **0.93** | **0.93** | **0.93** |
| wis page_fault_shared1 | 64 | **0.98** | **0.99** | **0.98** | **0.97** |
| wis page_fault_shared3 | 16 | **1.03** | **1.03** | **1.03** | **1.02** |
| wis page_fault_shared3 | 32 | **0.84** | **0.84** | **0.83** | **0.83** |
| wis page_fault_shared3 | 64 | **1.07** | **1.06** | **1.05** | **1.06** |
| api setfd | 16 | **1.28** | **2.29** | **1.25** | **2.32** |
| api setfd | 64 | **2.82** | **9.27** | **3.13** | **9.31** |
| api ofd | 16 | **1.51** | **2.65** | **1.43** | **2.56** |
| api ofd | 64 | **2.59** | **6.07** | **2.78** | **6.64** |
| api pipe | 16 | ~1.00 | **0.93** | **1.38** | **1.14** |
| api pipe | 64 | **0.91** | **0.86** | **1.15** | **1.02** |
| api seek | 16 | **0.92** | ~0.93 | **1.75** | **1.72** |
| api seek | 64 | **0.85** | **0.82** | **1.13** | **1.11** |
| api uts | 16 | **2.63** | **3.22** | **2.46** | **2.94** |
| api uts | 64 | **3.04** | **4.88** | **3.04** | **4.85** |
| api xattr | 16 | **0.94** | **0.96** | **0.94** | **0.97** |
| api xattr | 64 | **0.92** | ~0.97 | **0.92** | **0.96** |
| torture spin_lock | 128 | **3.58** | **4.35** | **3.72** | **4.65** |
| torture rw_lock | 128 | **1.20** | **1.17** | **1.26** | **1.23** |
| torture mutex_lock | 128 | **0.75** | ~1.08 | **0.70** | ~1.03 |
| torture rwsem_lock | 128 | **0.55** | **0.58** | **0.53** | **0.61** |
| torture ww_mutex_lock | 128 | **0.23** | **0.23** | **0.68** | **0.66** |

**What changed.** A ratio can also move because the native boots of the
two series differ: uts at 16 threads, for example, ran at 1.13-1.39 M
operations/s on native. So the absolute kd values decide what changed
(`data/runs.txt`).

These moved, with no overlap between before and after:

| workload | kd off, before -> after | kd on, before -> after | native |
|---|---|---|---|
| locktorture ww_mutex (writes / 30 s) | 5.9 M -> 17.1-18.1 M | 5.8-5.9 M -> 16.9-17.8 M | 25.3-26.4 M |
| api seek, 16 threads | 1.13-1.18 M -> 1.96-2.11 M | 1.10-1.28 M -> 2.00-2.12 M | 1.15-1.28 M |
| api seek, 64 threads | 0.96-0.98 M -> 1.36-1.40 M | 0.88-0.95 M -> 1.35-1.40 M | 1.07-1.23 M |
| api pipe, 16 threads | 504-524 k -> 706-709 k | 479-485 k -> 558-588 k | 508-529 k |
| api pipe, 64 threads | 475-480 k -> 588-602 k | 445-452 k -> 522-535 k | 506-529 k |

- **ww_mutex** gets more than the 4.1 focus runs showed (0.48 there with
  kdall2). The spin of 4.1 runs in the mutex's spinner queue, so the node
  order of 4.2 applies to it as well.
- **setfd at 64 threads, off,** also rose by about 10% (1.89-1.98 M ->
  2.10-2.12 M). Its lock, `files->file_lock`, is a spinlock, which neither
  change touches, so this is not counted as a result of them.
- **Everything else** has the same kd values within the spread of the
  runs, the gains of section 3 included.

**What is still behind native** (kdall3, on/native and off/native):

| case | kd/native | where it is explained |
|---|---|---|
| locktorture rwsem | 0.61 on, 0.53 off | bad case 2 |
| locktorture ww_mutex | 0.66, from 0.23 | 4.1: native checks one waiter per acquisition, kd walks them all |
| locktorture mutex, off | 0.70 (on 1.03) | bad case 3: the internal wait lock with 128 writers on 64 CPUs, not node order |
| page_fault1, 16 threads | 0.81 | bad case 5, not explained |
| page_fault_shared3, 32 threads | 0.83 | bad case 7, rwsem policy |
| page_fault_shared1, 16 and 32 threads | 0.92-0.94 | bad case 6, PTE spinlock |
| xattr | 0.92-0.97 | bad case 8 and 4.3, rwsem writers in plain mode |

**Correctness of kdall3:** `run_corr.py` and `mm_stress`, section 6.

## 6. Correctness of kdall3

Run in the last kdall3 boot (a6), after the suite.

- **`run_corr.py`** (`data/corr3-*`): the bench module built against kdall3
  (`out3`). It checks every lock family and test body against its data
  oracle, every kd API variant once, and the kernel log.
  - Plain, no daemon: 442 points, 0 failed, API check 0 failed, 0 kernel
    complaints. This runs the node order (4.2) and the ww spin (4.1).
  - With the daemon for the bench module only
    (`bench/allow/kd_bench.txt`, after one warm-up pass): 442 points, 0
    failed, 0 kernel complaints, 88.7 M delegated sections.
- **`mm_stress`** (`data/mm_check-kdall3.*`, `mm_check.sh` of
  `kdall-deleg-20261117-64cpu`): the data-checked mmap, munmap, mprotect,
  mremap, brk and fork stress, with brk, mmap and munmap delegated
  (`bench/allow/mm.txt`), 30 s each:

  | threads | operations | pages checked | forks | result |
  |---|---|---|---|---|
  | 16 | 58 153 | 15.0 M | 7 035 | ok |
  | 32 | 57 189 | 14.7 M | 4 800 | ok |
  | 64 | 48 283 | 12.4 M | 2 639 | ok |

  No kernel complaint.
- **The suite itself:** every api_stress run passed its data check, and
  every locktorture run ended with no kernel complaint (sections 3 and 5).

## 7. Files

| file | what |
|---|---|
| `suite.sh`, `drive.sh`, `cmp_summary.py`, `before_after.py` | the comparison: suite, boot driver, tables |
| `focus.sh` | the bad cases only, 2 runs each (4.1) |
| `prof.sh` | profiles (section 3) |
| `numa_plain.sh`, `nano_check.sh`, `nano_summary.py` | nano measurements in one boot of a kdnat kernel (4.2, 4.3) |
| `rejected/*.patch` | the two era changes that were not adopted (4.3) |
| `data/runs.txt`, `data/focus.txt` | every run |
| `data/nano-nat1*.jsonl` | kdnat1: mutex nano against native, and the node spread (section 3, bad case 3) |
| `data/numa_plain-kdnat2.jsonl.*` | kdnat2: `kd_numa_plain` 0 / 16 / 64 (4.2) |
| `data/era-kdnat2.jsonl.*`, `data/nat3.jsonl`, `data/nat4.jsonl*` | eras on and off on kdnat2; the two rejected era changes on kdnat3 and kdnat4 (4.3) |
