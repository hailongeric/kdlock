# kdlock with delegation against native Linux, whole kernel

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
| `era_ab.sh`, `era_summary.py`, `mm_diag.sh`, `nano_era.sh`, `nano_era_summary.py`, `place_era.sh`, `split.sh`, `mprof.sh`, `mip.sh` | 8.1: era settings for the mmap lock tests, nano and placement fairness, mmap1 profiles |
| `ltw.sh`, `ltprof.sh`, `mutex_wake.sh`, `ltregs.sh`, `ltregs_an.py`, `ltkp.sh`, `diag/` | 8.3, 8.4: locktorture runs and profiles, wakeup counts, lock words from register samples, kprobe hit counts (`diag/kd_addrs.c`, `diag/kd_kpcount.c`, never left loaded) |
| `woken_ab.sh`, `rstall_ab.sh`, `rspin_nano.sh`, `ab_summary.py` | 8.4, 8.5: in-boot A/B of `kd_mutex_woken`, of the rejected reader stall rule and of the reader spin time |
| `nat_check.sh`, `natc_summary.py`, `kdall_check.sh`, `prof_gain.sh`, `pf1_regs.sh`, `cldemote_ab.sh` | 8.2, 8.4, 8.7, 8.8: kdnat checks (nano, oversubscription), correctness, gain profiles, page_fault1 lock words, `kd_cldemote` A/B |
| `drivers/` | the per-boot driver scripts and the build scripts of this round |
| `rejected/mutex-awake.patch`, `rejected/rwsem-rstall.patch` | 8.6, 8.5 |
| `data/era-ab/`, `data/kdc6/`, `data/nano-era/`, `data/place-era/` | 8.1 |
| `data/ltw/`, `data/mwake/`, `data/woken/`, `data/natc/`, `data/rstall/`, `data/prof9/` | 8.2-8.8 |

## 8. Second round: mmap1 at 64 threads, and plain mode against native

Two questions from the user:

1. Before every lock was switched, mmap1 with 64 threads ran at about 2x
   native; the whole-kernel build does not reach that. Can it still be
   optimized?
2. Without delegation (kd "off"), why are some cases much faster than
   native and some much slower? Analyse and optimize.

Kernels added in this round, all from `/mnt/kdlock-builds/kda/src` with the
configuration of section 1 (only `CONFIG_KDLOCK_ALL` differs between a kdall
kernel and its kdnat twin):

| kernel | contents |
|---|---|
| `kdall4`, `kdall5`, `kdnat3`, `kdnat4` | the rejected era changes (4.3) |
| `kdall6` #9, `kdnat5` | kdall3 + an rwsem era bound of its own, 1 ms (8.1) + the ww spin rule (8.3) + the AWAKE flag (8.6, rejected) |
| `kdall7` #10, `kdnat6` | kdall6 without AWAKE, + plain queued waiters stop watching the holder (8.3) |
| `kdall8`, `kdnat7` | kdall7 + `KD_QF_WOKEN` (8.4); built, not booted |
| `kdall9` #12, `kdnat8` | kdall8 + the reader stall rule (8.5, rejected) |
| `kdall10` #13, `kdnat9` #9 | kdall9 without the reader stall rule: **the final kernels**, the tree of the commits that come with this section |

### 8.1 mmap1 at 64 threads

**Where the 2x went.** kd's own rate did not drop; native's rose:

| kernel | kd, 64 threads | native, 64 threads | kd/native |
|---|---|---|---|
| #71 (`CONFIG_KDLOCK_MM`, mmap lock only; native in the same boot) | 306-308 k | 148-151 k | 2.02-2.08 |
| kdall1 / kdall3 (every lock), native twin kdnat1 | 314-323 k | 174-178 k | 1.77-1.79 |

The native twin is the same tree and configuration with native locks, and
it runs mmap1 at 64 threads about 18% faster than native in the #71 kernel
did. That kernel had a different configuration, so the comparison of the
two native rates is an indicator only. Against its own twin, kd kept its
rate and lost the ratio.

**What limits kd: the era bound.** At 48 threads and more, the mmap lock's
callers sit on both nodes, and the rwsem serves one node at a time (an era,
ARCHITECTURE 7b). The callers of the other node wait at the era gate, so a
combining session ends when the era does: about 136 mmap1 sections per
session at 200 us (`data/era-ab/`, kdall3, one boot, 3 rounds; mmap lock
writers delegated). Each new era moves the mm's data to the other node.
#71 predates eras. Measured in one boot of kdall3, two blocks of 3 rounds,
each against its own 200 us runs (`era_ab.sh`, `era_summary.py`):

| setting | mmap1 48 / 60 / 64 threads, median relative to 200 us | sections per session at 64 |
|---|---|---|
| eras, 200 us (then the default) | 325-334 k / 316-325 k / 308-318 k | 136 |
| no eras (`kd_rw_era_ns=0`) | 0.94 / 0.93 / 0.93 | 3459 |
| eras that never start (`kd_rw_era_press=400`) | 0.93 / 0.94 / 0.94 | 3479 |
| eras, 200 us, second block | 324-326 k / 315-317 k / 303-310 k | 137 |
| eras, 500 us | 1.05 / 1.07 / 1.09 | 363 |
| eras, 1 ms | 1.12 / 1.14 / 1.11 | 911 |

Without eras the sessions are 25 times longer, but the rate is lower: the
queue then holds callers of both nodes, which each session serves or steps
over. Eras help; they were too short.

**The change: an era bound of the rwsem's own,** `kd_rwsem_era_ns`, 1 ms
(`kernel/kd_rwsem.c`). The rwlock keeps 200 us: it gained nothing from a
longer bound (0-2%) and lost fairness, and its waiters spin with preemption
off. On kdall6, one boot, 3 rounds, 1 ms against 200 us for the rwsem only
(`data/kdc6/kdall6-era-*`): mmap1 at 48 / 60 / 64 threads 1.14 / 1.15 /
1.12, mmap2 1.12-1.19, brk1 0.78-1.12 (noisy). mmap1 ran at 348-373 k: about
2.0x the native twin's 178 k (other boots). Nano, kdall3, one boot
(`data/nano-era/`): rwsem bodies with 20% writes at 48 and 64 workers
1.08-1.22 in plain mode and 1.06-1.09 delegated; writers only and one node
unchanged.

**The cost** is the share of a node with very few callers
(`data/place-era/`, kdall3, run_place.py, 32 workers): with 31 workers on
one node and 1 on the other, the least-served worker got 0.68 instead of
0.85 of the most-served one's operations (1 line, 20% writes, plain), 0.72
instead of 0.94 delegated.

### 8.2 Plain mode against native: where the differences come from

From the a series (section 5, kdall3 off against kdnat1, medians of 3
boots), the rate at 64 threads relative to 16 threads:

| workload | native 64/16 | kd off 64/16 | off/native at 64 |
|---|---|---|---|
| api ofd | 0.40 | 0.78 | 2.78 |
| api setfd | 0.48 | 1.19 | 3.13 |
| wis brk1 | 0.55 | 1.08 | 2.08 |
| wis mmap2 | 0.58 | 0.90 | 1.55 |
| wis mmap1 | 0.60 | 0.88 | 1.55 |
| wis page_fault_shared3 | 0.64 | 0.66 | 1.05 |
| api uts | 0.71 | 0.87 | 3.04 |

**The large gains are native collapsing across nodes.** 64 threads run on
both nodes; 16 run on one.

Profiles at 64 threads (`prof_gain.sh`, kdnat9 and kdall9 without the
daemon, `data/prof9/*-gain.log`; 5 s flat profiles and context switches):

| workload | native | kd off |
|---|---|---|
| setfd (`files->file_lock`, spinlock) | 95.7% `queued_spin_lock_slowpath`, 645 k ops/s | 97.9% `kd_q_lock_slow`, 1.97 M ops/s |
| ofd (file lock list, spinlock) | 96.5% `queued_spin_lock_slowpath`, 385 k | 98.1% `kd_q_lock_slow`, 1.02 M |
| uts (`uts_sem`, rwsem) | 2.74 M context switches; 22% `queued_spin_lock_slowpath` (the rwsem's wait lock), `rwsem_down_read_slowpath` | 297 k context switches; 49% `kd_wait_sleepable`, 40% `kd_rw_era_wait`; 3.15 M ops/s against 877 k |
| brk1, mmap1 (mmap lock writers) | 95% `osq_lock`, 173-181 k context switches | 42-50% `kd_wait_sleepable`, 45-54% `kd_rw_era_wait` |

- **rwsem (mmap lock, `uts_sem`):** native writers spin in the
  optimistic-spin queue and hand over in arrival order, across the two
  nodes at about every other handover; native readers sleep and are woken.
  kd serves one node at a time (eras): the callers of the other node wait
  at the era gate, polling a line of their own, so the lock and the data
  stay on one node for an era, and readers do not sleep.
- **Spinlocks (setfd, ofd):** both kernels spend nearly all their time in
  the slow path, and kd's plain mode is the native queued spinlock's
  algorithm; still kd hands over 2.6-3 times as often. **Not
  attributed.** It is not `kd_cldemote` (the queued waiter demotes its
  lines): with it switched off, kdall10, one boot, 3 rounds
  (`cldemote_ab.sh`, `data/prof9/kdall10-cldemote.txt`), setfd ran at
  2.07-2.09 M against 1.81-2.03 M and ofd at 1.02-1.12 M against
  1.06-1.18 M. What remains of the differences is the prefetch of the
  successor's node and the layout of the queue nodes.


**The losses** (section 5, last table), and their causes:

| case | off/native (kdall3) | cause | this round |
|---|---|---|---|
| locktorture mutex_lock | 0.70 | queued waiters all watched the holder; every release took the wait lock while tasks were parked | 8.3, 8.4 |
| locktorture ww_mutex_lock | 0.68 | as mutex, plus kd walks every parked waiter where native checks one | 8.3, 8.4 |
| locktorture rwsem_lock | 0.53 | reader-phase policy: kd follows each write with a reader phase; native passes the lock writer to writer while readers sleep | not changed |
| page_fault1, 16 threads | 0.80 | threads sleep about a quarter of the time in the mmap lock; the spinlock share is the same as native's (8.5) | analysed, not changed |
| page_fault_shared3, 32 threads | 0.83 | readers spin behind mprotect writers; native readers sleep | 8.5, not changed |
| page_fault_shared1, 16 and 32 threads | 0.92-0.94 | the shared PTE spinlock; the spin class has no node order in plain mode | not changed |
| xattr | 0.92-0.97 | `i_rwsem` writers in plain mode: queue mutex, writer bit and phase counter where native does one cmpxchg (4.3) | not changed |

### 8.3 Mutex: only the queue head judges the holder (kdall7)

locktorture mutex_lock with one writer per CPU (no oversubscription) was at
0.62 of native on kdall6. Its profile: 75.8% in the spinner queue
(`kd_wait_sleepable`), 20.8% in `kd_q_lock_plain` (`data/ltw/kdall6-prof.txt`);
native: 95.6% `osq_lock`, 0.3% in its spinlock slow path
(`data/ltw/kdnat1-prof.txt`). In 13 s, 12 700 queued waiters withdrew and
15 400 times a waiter went to sleep.

**Cause:** every queued waiter looked at the holder every `KD_OWNER_POLL`
iterations and withdrew when it was off its CPU. A holder off its CPU for a
moment (the shuffler, a kworker) sent the whole queue into the wait lock and
to sleep at once, and they were woken one by one. In the native mutex only
the head of the optimistic-spin queue watches the owner.

**Change** (`kernel/kd_core.c`, `kd_wait_sleepable()`): only a waiter that
published its section polls the holder; a plain waiter leaves the queue only
at `need_resched()`. The queue head still parks at once when the holder does
not run (LOCKS.md 4).

**ww rule, in the same kernel** (`kernel/kd_mutex.c`,
`kd_mutex_ww_may_spin()`): a parked first waiter that holds locks does not
spin while the holder has a context, as native `ww_mutex_spin_on_owner()`.
Without it, two contexts could spin on each other.

kdall6 -> kdall7 against kdnat1 (`ltw.sh`, 30 s, 2 runs; other boots, so
indicators; kdall6 also had the AWAKE flag of 8.6, which changed nothing):

| test | writers | kdnat1 | kdall6 | kdall7 |
|---|---|---|---|---|
| mutex_lock | 64 | 56.3-59.0 M | 34.7-36.8 M (0.62) | 40.3-41.8 M (0.71) |
| mutex_lock | 128 | 46.2-48.5 M | 32.5-32.9 M (0.69) | 39.5-40.7 M (0.85) |
| ww_mutex_lock | 64 | 22.5-23.3 M | 14.4-14.8 M (0.64) | 17.2-17.7 M (0.76) |
| ww_mutex_lock | 128 | 25.0-27.1 M | 16.7-17.3 M (0.65) | 22.7-23.2 M (0.88) |

### 8.4 Mutex: a parked waiter is woken once (`KD_QF_WOKEN`, kdall9)

kdall7 still spent 15.7% of its samples in `kd_q_lock_plain`
(`data/ltw/kdall7-prof.txt`). Which lock: `ltregs.sh` samples the
interrupted registers (`perf record -I`, no call graphs); `%rdx` holds the
lock word for the whole of `kd_q_lock_plain`, and `diag/kd_addrs.c` prints
the addresses of the writers' `pi_lock`s and of the run queue locks
(`data/ltw/kdall7-regs.txt`):

| lock word | share of the samples in `kd_q_lock_plain` |
|---|---|
| the torture mutex's `wait_lock` | 98.9% |
| writers' `pi_lock` | 1.0% |

Who takes it: `diag/kd_kpcount.c` counts kprobe hits (tracefs refuses kd's
functions, which are built without ftrace) at the entries of the mutex slow
path and at each call of `kd_q_lock_plain` (`ltkp.sh`,
`data/ltw/kdall7-kp.txt`, 5 s with the probes):

| place | hits | of them contended |
|---|---|---|
| `kd_mutex_wake_first()` (release with parked waiters) | 915 k | 893 k (98%) |
| `kd_mutex_handoff()` | 16.5 k | all |
| `kd_mutex_sleep()`: entry / after a wait | 4.3 k / 5.9 k | 2.4 k / 4.4 k |
| `schedule()` in `kd_mutex_sleep()` | 3.5 k | |

**Cause:** while any task was parked, every release took the wait lock to
wake the first parked task: about 260 wakeup passes per parked wait. The
task had almost always been woken by the first of them and was on its way
to its CPU or spinning. The wait lock shares the mutex's cache line, so
those passes also pulled the lock word away from the next owner. Native
takes its wait lock in the same way, but with one writer per CPU its
waiters rarely sleep (118 k `wake_up_q()` per second against kd's 350 k,
`data/mwake/kdnat9-w64-native.txt`).

**Change** (`kernel/kd_mutex.c`, `include/kdlock/kd_types.h`; protocol in
LOCKS.md 4): the waker sets `KD_QF_WOKEN`, a release that finds it does
nothing more, and the first task clears it under the wait lock and tries
the lock once more before it sleeps again. `kd_mutex_woken=0` switches it
off for in-boot comparisons.

kdall9, one boot, 3 rounds, `kd_mutex_woken` 1 against 0 (`woken_ab.sh`,
`data/woken/kdall9.txt`, `ab_summary.py woken`), writes per 30 s:

| test | writers | woken=1 | woken=0 | 1/0 |
|---|---|---|---|---|
| mutex_lock | 64 | 52.5 / 51.0 / 59.4 M | 40.3 / 38.1 / 43.1 M | **1.30** |
| mutex_lock | 128 | 78.6 / 76.7 / 75.1 M | 44.6 / 41.5 / 41.3 M | **1.85** |
| ww_mutex_lock | 64 | 17.4 / 17.9 / 18.2 M | 16.5 / 15.7 / 16.7 M | **1.09** |
| ww_mutex_lock | 128 | 23.8 / 22.6 / 23.2 M | 21.3 / 21.2 / 24.3 M | ~1.09 |
| rwsem_lock | default | 449 / 470 / 482 k | 463 / 403 / 515 k | ~1.02 |

Every run ended in SUCCESS. Wakeup counts in the same boot (`mutex_wake.sh`,
ftrace function profiler, 20 s): `wake_up_q()` 350 k -> 3.8 k per second
with 64 writers, 961 k -> 3.8 k with 128. Profile with 64 writers
(`data/ltw/kdall9-woken1-prof.txt`): 97.2% `kd_wait_sleepable`, 0.08%
`kd_q_lock_plain`. Per-writer spread with 128 writers (locktorture
Max/Min): 783 k / 437 k with the flag, native 488-527 k / 209-247 k.

Against the native twin (kdnat9, another boot, `data/ltw/kdnat9.txt`):
mutex_lock 0.93 with 64 writers (native 54.7-57.7 M) and 1.65 with 128
(native 44.0-48.8 M); ww_mutex_lock 0.78 and 0.90 (native 23.0-23.2 M and
25.4-26.5 M).

**Oversubscription** (`nat_check.sh`, kdnat9 against kdnat5, nano, kd
against native in the same boot, `natc_summary.py`): with 2 workers per
CPU kd/native went from 0.97 / 1.19 / 1.11 / 1.12 to 1.39 / 1.51 / 2.03 /
1.99 (mutex 16 lines and 1 line, one node and 16+16 CPUs); with 1 worker
per CPU 1.01-1.47, as before. No worker starved. The cost: the
least-served worker's share with 2 workers per CPU is 0.31-0.44 of the
most-served one's on kd, 0.47-0.53 on native (kdnat5: kd 0.26-0.63).

### 8.5 rwsem readers: page_fault1 and the reader spin time

**page_fault1 at 16 threads (0.80)** is not a spinlock cost. `pf1_regs.sh`
(`data/prof9/*-pf1regs.txt`) classes the lock argument of the sampled
spinlock entries by region: on kdall9 all 35.6% of the samples in
`kd_spin_lock` are on split PTE locks in struct pages, about 32 samples per
page-table page, so uncontended locks on cold lines, as on native (35.9% in
`_raw_spin_lock`). The difference is idle time: in 5 s kd collected 60.8 k
samples, native 80.2 k, and 16 busy threads give 80 k. kd's threads sleep
about a quarter of the time in the mmap lock.

**A reader stall rule (rejected).** After one reader ran out of its 50 us
behind a write phase, later readers of that phase would queue at once
(`rejected/rwsem-rstall.patch`, applies to the final tree). kdall9, one
boot, 3 rounds (`rstall_ab.sh`, `data/rstall/`):

| test | threads | stall / no stall | readers barely spinning (`kd_rwsem_rspin_ns=0`) / no stall |
|---|---|---|---|
| page_fault1 | 8 / 16 / 32 | 0.97 / 1.01 / 0.99 | **1.16 / 1.13** / 0.99 |
| page_fault_shared3 | 16 / 32 | 1.00 / 0.99 | **1.12** / 1.04 |
| mmap1, mmap2, brk1 | 16-64 | 0.99-1.00 | 1.00-1.02 |
| rwsem nano with readers | 32, 64 | 1.00 | - |

The write phases these readers wait for are shorter than 50 us, so the rule
marks nothing that matters. It is not in the tree.

**What spinning costs, and what it is worth.** Readers that give up after
about 64 iterations make page_fault1 and page_fault_shared3 faster. With
50 us, readers register behind the writer and the next writer waits for
that batch. But the reader-heavy nano bodies lose without it (kdnat9, one
boot, kd backend, `rspin_nano.sh`, `data/natc/kdnat9-rspin.jsonl.*`):

| body | workers | native | kd, 50 us | 5 us / 50 us | 0 / 50 us |
|---|---|---|---|---|---|
| rwsem 1 line, 1% writes | 32 / 64 | 4.52 / 2.49 | 11.46 / 10.77 | 0.94 / 0.90 | 0.97 / 0.97 |
| rwsem 16 lines, 1% writes | 32 / 64 | 4.34 / 2.37 | 9.54 / 8.77 | 0.99 / 0.92 | 0.91 / 0.90 |
| rwsem 1 line, 20% writes | 32 / 64 | 3.09 / 1.31 | 6.85 / 6.58 | 1.00 / 0.99 | 1.00 / 0.95 |
| rwsem 16 lines, 20% writes | 32 / 64 | 2.30 / 1.15 | 3.75 / 3.65 | 1.00 / 0.99 | 1.00 / 0.94 |

The default stays at 50 us: a shorter time trades 3-10% of the reader-heavy
bodies for 4-16% in these two page-fault tests. A per-lock choice (spin
only where readers outnumber writers) is open work.

### 8.6 Rejected: the AWAKE flag (kdall6)

`rejected/mutex-awake.patch`: the first parked task set a flag while it
spun, and a release that saw the flag did not wake it. With 128 writers on
64 CPUs it changed nothing (`data/mwake/kdall6-kd.txt`: 708 k `wake_up_q()`
per second against 721 k on kdall3; writes within the spread), because the
first parked task was spinning only a small part of the time; most
wakeup passes came while it was still on its way to its CPU. 8.4 sets the
flag at the wakeup instead.

### 8.7 kdall10 against native: the c series

The suite of section 3 (`suite.sh`, with mmap1, mmap2 and brk1 at 48 and 60
threads added at the end of the pass, section 5 of the script), kdall10
against its twin kdnat9, after a learning boot (learn10, not counted), in
the boot order kdnat9, kdall10 (off, on), kdnat9, kdall10 (on, off), kdnat9,
kdall10 (off, on): `drive.sh`, tags c1-c6, `data/drive-c.log`. No kernel
complaint in any boot. Files: `data/runs.txt` (tags learn10, c1-c6),
`data/summary-c.md` (`cmp_summary.py`, every value),
`data/before_after-ac.md` (`before_after.py data/runs.txt a c`), reproduced
here. Each series against its own native boots; bold: the three kd runs and
the three native runs do not overlap.

| workload | threads | a (kdall3): off/native | a: on/native | c (kdall10): off/native | c: on/native |
|---|---|---|---|---|---|
| pf read | 16 | ~1.00 | ~1.02 | ~0.98 | ~0.98 |
| pf read | 32 | ~0.99 | ~1.00 | ~1.01 | ~0.98 |
| pf read | 64 | ~0.99 | ~1.00 | ~0.98 | ~0.98 |
| pf write | 16 | **0.99** | ~0.98 | ~0.98 | ~1.06 |
| pf write | 32 | **0.95** | ~0.96 | ~1.22 | ~1.03 |
| pf write | 64 | ~0.97 | ~1.00 | ~1.02 | ~1.03 |
| wis mmap1 | 16 | ~1.06 | **1.28** | ~0.99 | **1.28** |
| wis mmap1 | 32 | ~1.03 | **1.29** | ~1.00 | **1.27** |
| wis mmap1 | 64 | **1.55** | **1.77** | **1.83** | **2.06** |
| wis mmap2 | 16 | ~0.99 | **1.06** | ~1.06 | **1.14** |
| wis mmap2 | 32 | ~1.01 | **1.10** | **0.98** | **1.08** |
| wis mmap2 | 64 | **1.55** | **1.56** | **1.76** | **1.83** |
| wis brk1 | 16 | ~1.07 | **1.55** | **0.92** | **1.31** |
| wis brk1 | 32 | **1.09** | **1.61** | ~1.05 | **1.49** |
| wis brk1 | 64 | **2.08** | **2.45** | **2.10** | **2.12** |
| wis page_fault1 | 16 | **0.80** | **0.81** | **0.87** | **0.87** |
| wis page_fault1 | 32 | **1.03** | ~1.05 | **1.04** | ~1.03 |
| wis page_fault1 | 64 | **1.07** | **1.07** | **1.05** | **1.04** |
| wis page_fault_shared1 | 16 | **0.92** | **0.94** | **0.93** | **0.95** |
| wis page_fault_shared1 | 32 | **0.93** | **0.93** | **0.93** | **0.93** |
| wis page_fault_shared1 | 64 | **0.98** | **0.97** | **0.98** | **0.98** |
| wis page_fault_shared3 | 16 | **1.03** | **1.02** | **1.02** | ~1.01 |
| wis page_fault_shared3 | 32 | **0.83** | **0.83** | **0.83** | **0.83** |
| wis page_fault_shared3 | 64 | **1.05** | **1.06** | **1.07** | **1.07** |
| api setfd | 16 | **1.25** | **2.32** | **1.17** | **2.18** |
| api setfd | 64 | **3.13** | **9.31** | **3.11** | **9.65** |
| api ofd | 16 | **1.43** | **2.56** | **1.44** | **2.56** |
| api ofd | 64 | **2.78** | **6.64** | **2.82** | **8.04** |
| api pipe | 16 | **1.38** | **1.14** | **1.40** | **1.18** |
| api pipe | 64 | **1.15** | **1.02** | **1.39** | **1.07** |
| api seek | 16 | **1.75** | **1.72** | **1.80** | **1.87** |
| api seek | 64 | **1.13** | **1.11** | **1.41** | **1.43** |
| api uts | 16 | **2.46** | **2.94** | **2.67** | **3.20** |
| api uts | 64 | **3.04** | **4.85** | **3.51** | **5.21** |
| api xattr | 16 | **0.94** | **0.97** | **0.95** | **0.97** |
| api xattr | 64 | **0.92** | **0.96** | **0.94** | ~0.97 |
| torture spin_lock | 128 | **3.72** | **4.65** | **3.62** | **4.37** |
| torture rw_lock | 128 | **1.26** | **1.23** | **1.21** | **1.25** |
| torture mutex_lock | 128 | **0.70** | ~1.03 | **1.60** | **1.58** |
| torture rwsem_lock | 128 | **0.53** | **0.61** | **0.57** | **0.53** |
| torture ww_mutex_lock | 128 | **0.68** | **0.66** | **0.90** | **0.86** |
| wis mmap1 | 48 | - | - | **1.74** | **2.06** |
| wis mmap1 | 60 | - | - | **1.86** | **2.12** |
| wis mmap2 | 48 | - | - | **1.70** | **1.76** |
| wis mmap2 | 60 | - | - | **1.78** | **1.82** |
| wis brk1 | 48 | - | - | **1.88** | **2.37** |
| wis brk1 | 60 | - | - | **2.04** | **2.52** |

**What changed in kd's own rates** (a -> c, ranges of the three runs, no
overlap between the series; other boots and kernels, so indicators):

| workload | threads | kd off, a -> c | kd on, a -> c | native, a / c |
|---|---|---|---|---|
| wis mmap1 | 64 | 274-279 k -> 321-323 k | 314-320 k -> 357-379 k | 174-178 k / 175-176 k |
| wis mmap2 | 64 | 311-319 k -> 359-366 k | 317-322 k -> 349-382 k | 203-209 k / 205-209 k |
| torture mutex_lock | 128 | 32.0-36.9 M -> 71.1-79.5 M | 46.3-49.0 M -> 70.1-71.9 M | 45.0-46.7 M / 44.9-47.5 M |
| torture ww_mutex_lock | 128 | 17.1-18.1 M -> 22.8-23.5 M | 16.9-17.8 M -> 22.1-22.8 M | 25.3-26.4 M / 25.5-25.9 M |
| api seek | 64 | 1.36-1.39 M -> 1.69-1.74 M | 1.35-1.40 M -> 1.72-1.76 M | 1.12-1.23 M / 1.13-1.23 M |
| api pipe | 64 | 588-602 k -> 722-740 k | 522-535 k -> 553-569 k | 516-521 k / 519-530 k |
| api uts | 64 | 2.77-2.81 M -> 3.21 M | 4.44-4.45 M -> 4.74-4.79 M | 914-920 k / 913-914 k |

- **mmap1 at 64 threads: 2.06 of native with delegation** (1.77 on kdall3),
  2.12 at 60 threads and 2.06 at 48; 1.83 without delegation. mmap2 at
  64: 1.83. This is the rwsem era bound (8.1).
- **locktorture mutex_lock: 1.60 / 1.58** (0.70 / ~1.03 on kdall3), ww
  0.90 / 0.86 (0.68 / 0.66): 8.3 and 8.4. seek (`f_pos_lock`) and pipe
  (`pipe->mutex`) are mutexes as well.
- **brk1 did not gain:** with delegation 1.31 / 1.49 / 2.12 at 16 / 32 / 64
  threads against 1.55 / 1.61 / 2.45. kd's own rates overlap between the
  series (64 threads: 847 k-1.01 M on kdall3, 773-881 k on kdall10), and
  native brk1 at 16 threads ran faster in the c boots (825-882 k against
  699-789 k). At 48 and 60 threads, measured only in this series: 2.37 and
  2.52.
- **page_fault1 at 16 threads:** 0.87 (0.80); kd's rates overlap between
  the series, so this is not counted as a change.
- Everything else within the spread of the runs, the gains of section 3
  included.

### 8.8 Correctness of kdall10

Run in the last kdall10 boot (c6), after the suite (`kdall_check.sh` with
`ERA=0`, `drivers/kd10.sh`, `data/kdc6/kdall10*`):

- **locktorture**, no daemon, 30 s, 2 runs each: ww_mutex_lock, mutex_lock
  and rwsem_lock all end in SUCCESS.
- **`run_corr.py`**, bench module built against kdall10: plain 442 points,
  0 failed, API check 0 failed, 0 kernel complaints; with the daemon for
  the bench module only (after a warm-up pass): 442 points, 0 failed, 0
  kernel complaints.
- **test-ww_mutex**: "All ww mutex selftests passed", and the wound-wait
  stress `stress_inorder_work` fails with -35 (`-EDEADLK`), as it does on
  kdall6 and on the native kernel (KERNEL_INTEGRATION 4d; kd applies
  wait-die to both classes).
- **`mm_stress`** with brk, mmap and munmap delegated, 30 s each: 16 / 32 /
  64 threads, 54 149 / 57 164 / 47 447 operations, 14.0 / 14.7 / 12.2 M
  pages checked, 6 846 / 4 927 / 2 388 forks, all ok.
- No kernel complaint in this boot, nor in any boot of the c series
  (`data/suite-c-tails.txt`).
- WOKEN in kdall9 (8.4): every locktorture run of `woken_ab.sh` ended in
  SUCCESS under both settings.

### 8.9 What is still behind native

kdall10 against kdnat9 (8.7), off / on:

| case | kd/native | why | where |
|---|---|---|---|
| locktorture rwsem_lock | 0.57 / 0.53 | kd follows each write with a reader phase; native passes the lock writer to writer while readers sleep | bad case 2 |
| page_fault_shared3, 32 threads | 0.83 / 0.83 | readers spin behind mprotect writers; native readers sleep | bad case 7, 8.5 |
| page_fault1, 16 threads | 0.87 / 0.87 | threads sleep about a quarter of the time in the mmap lock; a shorter reader spin helps it and costs reader-heavy locks | 8.5 |
| locktorture ww_mutex_lock | 0.90 / 0.86 | kd walks every parked waiter; native keeps stamp order and checks the first | 4.1 |
| page_fault_shared1, 16 and 32 threads | 0.93-0.95 | the shared PTE spinlock: the spin class has no node order in plain mode | bad case 6 |
| xattr | 0.94-0.97 | `i_rwsem` writers in plain mode | bad case 8, 4.3 |

Open: a reader spin time chosen per lock (8.5), stamp order for the ww
wait list, and why kd's contended spinlock in plain mode hands over 2.6-3
times faster than native across the two nodes (8.2). Validation limits: CPU hotplug, and call-depth tracking
active (AGENTS.md), were not tested.
