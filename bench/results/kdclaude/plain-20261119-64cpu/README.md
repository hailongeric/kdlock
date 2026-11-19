# kd without delegation against native: the baseline, the losses and their fixes

Started 2026-11-19 from the user's list of that day: kd without delegation
("off": a kdall kernel, no daemon) is to stay at 0.90 of native Linux or
above (0.93 where delegation is not supported), page_fault1 and mmap1
first; the era logic's cost on that path is to be measured; handbacks are
to be analysed. kdclaude VM, 64 vCPUs as 2 nodes of 32, host at 2.7 GHz.
Points are few on purpose (the user asked for short runs): one run each
unless said otherwise, so a ratio within about 5% of 1 is not a result.

## 1. The native baseline was not the queued spinlock

**Finding.** In a KVM guest `native_pv_lock_init()` enables the static key
`virt_spin_lock_key`, and `queued_spin_lock_slowpath()` then takes every
contended spinlock as a test-and-set lock (`virt_spin_lock()`). The only
code that switches the key off is `kvm_spinlock_init()` (which the
`nopvspin` parameter reaches), and it is compiled only with
`CONFIG_PARAVIRT_SPINLOCKS=y`. `CONFIG_KDLOCK_ALL` depends on
`!PARAVIRT_SPINLOCKS`, and the native twins `kdnat1`-`kdnat10` inherited
that configuration: `nopvspin` on their command line did nothing. Read on
the running kdnat10 from `/proc/kcore`: `virt_spin_lock_key` enabled.

A test-and-set lock hands nothing over, so it is far faster than a fair
queue with 2-8 contenders and collapses with many. Every native column of
`kdall-native-20261117-64cpu`, `appgrid-20261118-64cpu` (g1),
`appgrid-20261119-64cpu` (g2) and `lkp-macro-20261118-64cpu` (s1) was
measured that way, for spinlocks, for rwlocks (their wait lock) and for
whatever else waits on a spinlock. kd kernels are not affected. Rounds up
to r12 ran on `7.0.0-38-kdclaude1`, which had `PARAVIRT_SPINLOCKS=y` and
therefore the real lock.

**Corrected twin.** `7.0.0-38-kdnat11` #1: kdnat10's configuration with
`CONFIG_PARAVIRT_SPINLOCKS=y` (out dir `outnat3`). On it: "PV spinlocks
disabled, forced by nopvspin" and `virt_spin_lock_key` off
(`/root/skey.py virt_spin_lock_key` in the guest). Check that before
trusting a native column.

**Nano grid on kdnat11** (g3: `nano_grid.sh` of appgrid-20261118, 14 worker
counts, 1 round; `data/g3-nano*.jsonl`, `data/nano-g3-ranges.md`):

| profile | kd/native 1-8 | 12-32 | 36-64 | kd/TCLock 1-8 | 12-32 | 36-64 | plain kd/native 1-8 | 12-32 | 36-64 | kd Mops/s at 32 / 60 | native | TCLock |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| spin_c01 | 0.88-1.00 | 0.92-1.00 | 1.42-1.71 | 1.00-1.75 | 1.42-1.48 | 1.45-1.48 | 0.91-1.03 | 0.99-1.09 | 0.97-1.01 | 6.52 / 6.44 | 6.51 / 3.85 | 4.59 / 4.44 |
| spin_c08 | 0.89-1.03 | 1.04-1.07 | 1.52-1.77 | 1.00-1.51 | 1.58-1.61 | 1.63-1.63 | 0.91-1.00 | 0.95-0.97 | 0.89-1.05 | 5.15 / 5.12 | 4.92 / 3.02 | 3.20 / 3.14 |
| mutex_c01 | 0.98-1.10 | 1.07-1.12 | 1.73-2.23 | 1.00-2.07 | 1.08-1.26 | 1.11-1.16 | 0.97-1.16 | 1.19-1.22 | 1.57-1.93 | 3.90 / 3.76 | 3.47 / 1.69 | 3.61 / 3.25 |
| mutex_c08 | 1.00-1.26 | 1.29-1.31 | 1.84-2.05 | 1.00-1.59 | 1.53-1.59 | 1.51-1.54 | 0.99-1.18 | 1.18-1.20 | 1.43-1.76 | 3.70 / 3.65 | 2.82 / 1.78 | 2.43 / 2.40 |
| rwsem_c01_w1 | 1.00-1.96 | 2.01-2.48 | 2.74-2.85 | 0.84-1.00 | 0.75-0.85 | 0.83-0.92 | 1.00-1.96 | 2.11-2.44 | 2.79-2.84 | 10.89 / 10.79 | 5.41 / 3.79 | 14.48 / 13.05 |
| rwsem_c08_w1 | 1.00-1.65 | 1.92-2.05 | 2.60-2.84 | 0.98-1.03 | 0.98-1.03 | 1.09-1.17 | 1.00-1.65 | 1.89-1.96 | 2.52-2.66 | 9.88 / 9.74 | 5.15 / 3.43 | 10.11 / 8.96 |
| rwsem_c01_w20 | 1.00-2.65 | 2.67-2.68 | 3.86-5.64 | 0.92-1.14 | 0.93-1.06 | 1.15-1.19 | 1.00-2.65 | 2.57-2.66 | 3.75-5.44 | 7.03 / 6.89 | 2.64 / 1.27 | 7.54 / 5.97 |
| rwsem_c08_w20 | 1.00-2.46 | 2.51-2.55 | 3.76-5.13 | 0.87-1.17 | 0.99-1.07 | 1.24-1.28 | 1.00-2.07 | 2.01-2.04 | 3.03-4.10 | 5.98 / 5.84 | 2.36 / 1.17 | 6.03 / 4.71 |
| rwlock_c01_w1 | 0.93-1.02 | 0.92-1.11 | 1.04-1.14 | 1.00-1.12 | 1.01-1.23 | 0.94-1.03 | 0.95-1.02 | 0.91-1.09 | 0.93-0.96 | 13.90 / 13.35 | 14.81 / 12.28 | 13.73 / 13.66 |
| rwlock_c08_w1 | 0.83-1.00 | 0.87-0.93 | 1.01-1.06 | 0.89-1.01 | 0.98-1.01 | 0.95-0.97 | 0.82-1.00 | 0.85-0.91 | 0.98-1.03 | 8.64 / 8.35 | 9.24 / 8.09 | 8.86 / 8.81 |
| rwlock_c01_w20 | 0.83-1.00 | 0.85-0.87 | 1.10-1.20 | 1.00-1.38 | 1.23-1.24 | 1.21-1.23 | 0.83-1.00 | 0.84-0.87 | 0.88-0.90 | 6.12 / 6.11 | 7.04 / 5.08 | 4.98 / 5.03 |
| rwlock_c08_w20 | 0.88-1.00 | 0.95-1.00 | 1.38-1.52 | 0.95-1.15 | 1.09-1.11 | 1.10-1.11 | 0.84-1.00 | 0.83-0.87 | 0.89-0.90 | 4.80 / 4.79 | 4.80 / 3.15 | 4.34 / 4.34 |

Against g2's table (same kd code, test-and-set native):

- **spin:** plain kd is 0.89-1.09 of native at every worker count (g2:
  0.57-0.61 at 3 workers). Across nodes delegation gives 1.42-1.77 (g2:
  1.87-2.77); on one node with one cache line the delegated lock is *below*
  the plain one, 0.88-0.95 against 0.95-1.00 at 6-16 workers.
- **rwlock:** the 3-5x of g2 across nodes is 1.01-1.52 here, and plain kd
  is **below native**: 0.83-0.91 with 20% writes from 4 workers on, 0.85-0.91
  for c08 with 1% writes at 12-32. Open (section 6).
- **mutex, rwsem:** as in g2 (native waits by optimistic spinning, not on
  a contended spinlock): rwsem 2.0-5.6, mutex 1.07-2.23 from 4 workers.

**Application grid, native on kdnat11** (g3: will-it-scale, FxMark and
LevelDB; Metis, Psearchy and Apache were not rerun, `data/g3-native-runs.txt`)
against g2's kd columns from kdall13 (another boot and kernel build:
indicators; `data/app-g2kd-g3native*.md`):

| benchmark | off/native 1-8 | 12-32 | 36-64 | on/native 1-8 | 12-32 | 36-64 | native / off / on at 32 | at 60 | delegated at 60 |
|---|---|---|---|---|---|---|---|---|---|
| wis lock1 | 0.93-1.02 | 0.86-0.94 | 0.86-1.00 | 0.95-1.01 | 0.83-0.93 | 0.88-0.96 | 10.80M / 9.33M / 8.97M | 5.98M / 6.00M / 5.32M | 0 |
| wis mmap1 | 0.97-1.03 | 1.00-1.01 | 1.57-1.91 | 0.96-1.24 | 1.24-1.28 | 1.84-2.25 | 302k / 305k / 387k | 171k / 327k / 384k | 12235807 |
| wis mmap2 | 0.98-1.03 | 0.99-1.01 | 1.49-1.85 | 0.97-1.20 | 1.08-1.14 | 1.55-1.93 | 359k / 357k / 386k | 198k / 367k / 328k | 10397576 |
| wis brk1 | 0.91-1.69 | 1.01-1.10 | 1.59-2.04 | 0.97-1.68 | 1.53-1.72 | 1.89-2.50 | 682k / 727k / 1.17M | 383k / 783k / 940k | 14870360 |
| wis page_fault1 | 0.81-1.01 | 0.80-1.01 | 1.00-1.06 | 0.79-0.99 | 0.80-1.05 | 1.02-1.06 | 2.79M / 2.83M / 2.93M | 4.09M / 4.34M / 4.34M | 31 |
| wis page_fault2 | 0.87-0.98 | 0.86-0.95 | 0.85-0.98 | 0.88-0.99 | 0.84-0.95 | 0.88-0.98 | 2.00M / 1.91M / 1.89M | 3.68M / 3.12M / 3.23M | 36 |
| wis page_fault3 | 0.82-0.99 | 0.71-0.98 | 0.99-1.00 | 0.81-0.99 | 0.69-0.98 | 1.00-1.01 | 12.56M / 12.33M / 12.32M | 12.15M / 12.04M / 12.15M | 35 |
| fxmark MWRM | 0.98-1.09 | 1.05-1.07 | 1.09-1.24 | 0.99-1.08 | 1.04-1.08 | 1.08-1.25 | 335k / 354k / 350k | 267k / 330k / 335k | 0 |
| fxmark MRDM | 0.93-1.13 | 1.00-1.04 | 0.90-0.99 | 0.99-1.15 | 0.96-1.01 | 0.78-0.94 | 5.17M / 5.19M / 5.06M | 3.20M / 2.87M / 3.02M | 0 |
| leveldb readrandom | 0.91-1.03 | 0.96-1.05 | 0.97-1.04 | 0.93-1.06 | 0.99-1.05 | 0.96-1.03 | 1.14M / 1.14M / 1.13M | 598k / 620k / 617k | 203 |

- **lock1:** native holds 10 M ops/s at 8-32 threads and 6-7 M at 40-60;
  g2's "0.48 at 8 threads, 2.5-3.6x at 40-60" was the test-and-set lock.
  Really 0.86-0.94 from 8 threads on: a loss (section 6).
- **FxMark MRDM:** 0.90-1.13 instead of up to 4.5x.
- **mmap1, mmap2, brk1:** unchanged, with and without delegation (the mmap
  lock is an rwsem): off 1.49-2.04 and on 1.55-2.50 at 40-60 threads.
- **page_fault1-3:** unchanged and real: 0.71-0.93 at 3-24 threads.
- **LevelDB:** 0.91-1.05 everywhere; the 0.87 at 56 threads of g2 is gone.

## 2. Where page_fault1-3 lose: the mmap lock's write side

`prof.sh` (flat profile and call chains of all CPUs while a point runs),
`data/prof/`; then the blocked time of the workers from
`/proc/PID/task/*/schedstat`, mmap and munmap times from `perf trace -s`,
and the call chains of `sched:sched_switch` (scripts in the guest:
`/root/offtime.sh`, `/root/offcpu.sh`).

page_fault3, 16 threads (each thread maps 128 MB of a file, touches every
page, unmaps):

| | native (kdnat11) | kd off (kdall13) |
|---|---|---|
| rate | 13.0-13.3 M faults/s | 9.1-10.3 M |
| workers blocked | 7.7% of the time | 12.7-12.8% |
| samples of a 5 s profile (all CPUs) | 35 K | 30 K |
| munmap, average | 5.4-5.6 ms (minimum 2.2 ms) | 5.4-5.5 ms |
| **mmap, average** | **0.14-0.15 ms** (minimum 6 us) | **1.6-1.7 ms** |
| where the workers sleep (4 s) | 1604 times in munmap's `down_write`, never in mmap's | 1286 times in mmap's and 1621 in munmap's `kd_down_write` |

The CPU profiles have the same shape in both kernels (page_fault1:
`kd_spin_lock` 35.4% against `_raw_spin_lock` 36.8%, both called from
`do_anonymous_page` for the page table lock with about 1% in a slow path;
`charge_memcg` 15-16%). kd spends no extra CPU anywhere: its workers sleep.
Every lock on these paths is a kd lock in kdall13 (page table lock, mmap
lock, allocator and LRU locks); memcg's counters are atomics.

**Mechanism.** munmap takes the mmap lock for writing, detaches its area,
downgrades and unmaps the pages as a reader for 2 ms or more. The next
writer has to wait for that reader. In the kd rwsem it became the holder of
the queue mutex `m`, spun for 50 us and then slept *holding `m`*; every
writer after it saw the owner of `m` off its CPU and parked as well. When
the reader left, the lock was free but reserved for the sleeping holder of
`m`: a thread whose munmap had just returned could not take it for its
mmap and went to the back of the sleeping writers. The native rwsem lets a
running writer take a free lock while a waiter sleeps (and bounds that with
a handoff after 4 ms), so there the mmap that follows a munmap returns in
microseconds and only munmap waits.

## 3. The fix: write stealing in the kd rwsem

`kernel/kd_rwsem.c` (LOCKS.md 5): while the holder of `m` sleeps on
`count`, a writer that finds no reader and no writer in takes the writer
bit past it; a sleeper that has waited `kd_rwsem_handoff_ms` (4) sets
`KD_RWSEM_HANDOFF` and nobody steals until it has had the lock. Nothing is
stolen from a holder of `m` that is awake, so combining sessions are not
bypassed. `kd_rwsem_steal=0` switches it off.

**In-boot comparison** on `7.0.0-38-kdall14` #19, no daemon (`steal_ab.sh`,
`data/k14-steal.txt`, `steal_summary.py`; native from g3, another boot):

| test | workers | steal off | steal on | on/off | off/native | on/native | wr_steal, wr_handoff, parked (on) | parked (off) |
|---|---|---|---|---|---|---|---|---|
| page_fault1 | 4 | 1.594e+06 | 1.985e+06 | 1.25 | 0.81 | 1.00 | 137, 0, 10 | 1107 |
| page_fault1 | 8 | 2.072e+06 | 2.797e+06 | 1.35 | 0.75 | 1.01 | 361, 25, 157 | 1742 |
| page_fault1 | 16 | 2.66e+06 | 3.039e+06 | 1.14 | 0.88 | 1.00 | 1037, 440, 334 | 2399 |
| page_fault1 | 32 | 2.987e+06 | 2.849e+06 | 0.95 | 1.07 | 1.02 | 1411, 946, 1550 | 3925 |
| page_fault1 | 60 | 4.423e+06 | 4.441e+06 | 1.00 | 1.08 | 1.09 | 2161, 1367, 2404 | 4628 |
| page_fault2 | 4 | 1.361e+06 | 1.504e+06 | 1.10 | 0.90 | 1.00 | 102, 1, 32 | 701 |
| page_fault2 | 8 | 1.669e+06 | 1.909e+06 | 1.14 | 0.88 | 1.00 | 209, 5, 70 | 1206 |
| page_fault2 | 16 | 1.9e+06 | 2.019e+06 | 1.06 | 0.94 | 1.00 | 784, 10, 87 | 1527 |
| page_fault2 | 32 | 1.937e+06 | 1.992e+06 | 1.03 | 0.97 | 1.00 | 957, 389, 1057 | 1783 |
| page_fault2 | 60 | 3.445e+06 | 3.695e+06 | 1.07 | 0.94 | 1.00 | 1688, 956, 1919 | 3135 |
| page_fault3 | 4 | 3.494e+06 | 3.756e+06 | 1.08 | 0.93 | 1.00 | 535, 0, 9 | 1837 |
| page_fault3 | 8 | 6.005e+06 | 7.383e+06 | 1.23 | 0.81 | 1.00 | 1454, 0, 46 | 4161 |
| page_fault3 | 16 | 9.278e+06 | 1.335e+07 | 1.44 | 0.70 | 1.01 | 6063, 6, 3650 | 7570 |
| page_fault3 | 32 | 1.252e+07 | 1.319e+07 | 1.05 | 1.00 | 1.05 | 6293, 2, 6294 | 11209 |
| page_fault3 | 60 | 1.219e+07 | 1.278e+07 | 1.05 | 1.00 | 1.05 | 5818, 0, 5943 | 11079 |
| mmap1 | 4 | 3.567e+05 | 3.543e+05 | 0.99 | 1.03 | 1.02 | 11563, 0, 1203 | 1676 |
| mmap1 | 8 | 3.061e+05 | 3.054e+05 | 1.00 | 1.01 | 1.01 | 6560, 0, 2233 | 2052 |
| mmap1 | 16 | 3.121e+05 | 3.122e+05 | 1.00 | 1.01 | 1.01 | 4305, 0, 2319 | 2074 |
| mmap1 | 32 | 3.094e+05 | 3.104e+05 | 1.00 | 1.02 | 1.03 | 4083, 0, 1968 | 1668 |
| mmap1 | 60 | 3.306e+05 | 3.198e+05 | 0.97 | 1.94 | 1.87 | 933, 0, 1304 | 782 |
| brk1 | 4 | 7.583e+05 | 7.584e+05 | 1.00 | 1.07 | 1.07 | 11593, 0, 1126 | 1769 |
| brk1 | 8 | 7.358e+05 | 7.43e+05 | 1.01 | 0.98 | 0.99 | 6357, 0, 1855 | 1903 |
| brk1 | 16 | 7.471e+05 | 7.668e+05 | 1.03 | 1.06 | 1.09 | 3787, 0, 2019 | 1717 |
| brk1 | 32 | 7.199e+05 | 7.595e+05 | 1.05 | 1.06 | 1.11 | 3099, 0, 1823 | 2047 |
| brk1 | 60 | 7.785e+05 | 7.796e+05 | 1.00 | 2.03 | 2.03 | 682, 0, 1347 | 1239 |

- page_fault1, 2 and 3 are at 1.00-1.09 of native at every point with
  stealing (0.70-0.94 without at 4-16 threads).
- mmap1 and brk1 keep their rates (0.97-1.05 of the rate without it; mmap1
  at 60 threads 0.97, one run).
- The handoff is used: 440-1367 sleepers asked for it per 10 s in
  page_fault1 at 16-60 threads.
- No kernel complaint during the comparison.

**Correctness on kdall14** (`data/k14-check.out`; `kdall_check.sh` without
the era step): locktorture ww_mutex, mutex and rwsem 2 runs each, all
SUCCESS; `run_corr.py` plain and with the daemon 240 points each, 0 failed,
API check 0 failed; test-ww_mutex passes (the `stress_inorder_work -35`
line is in every earlier run); `mm_stress` 16/32/64 threads ok; 0 kernel
complaints. kdall14 also carries the removal of the clobber entries.

## 4. Era logic on the path without delegation

Not measured yet (`era_ab.sh`: eras on, eras off and reader phase off in
one boot, mmap1, mmap2, brk1, page_fault1).

## 5. Psearchy and LevelDB in other published configurations

Not measured yet (`ivm_apps.sh`; desk research in section 5 of the
session's notes: the curves that turn over at 36 and at 4 threads are the
IntervalVM configurations, `pedsort -m 2048` and an 8 GB LevelDB whose
table cache thrashes, both bound on mmap lock writers).

## 6. Open

1. **rwlock, plain:** 0.83-0.91 of native with 20% writes (section 1).
2. **lock1** (`files->file_lock`, a spinlock, not on an allow list):
   0.86-0.94 from 8 threads on; both kernels spend 91% in their spinlock
   slow path there (`data/prof/p1-*-lock1-32.txt`).
3. **spin, delegated, one node, one cache line:** below the plain lock.
4. Delegation on kdall14 (the daemon state is per build), Apache and the
   other applications against a kdnat11 baseline, the lkp screening on
   kdnat11, sections 4 and 5, the handback analysis.

## 7. Files

| file | what |
|---|---|
| `prof.sh` | profile of single grid points; `data/prof/` (tag p1: native on kdnat11, off on kdall13) |
| `steal_ab.sh`, `steal_summary.py` | section 3; `data/k14-steal.*` |
| `era_ab.sh`, `ivm_apps.sh` | sections 4 and 5 |
| `data/g3-*`, `data/nano-g3-ranges.md`, `data/app-g2kd-g3native*` | section 1 |
| `data/k14-check.out` | correctness of kdall14 |
