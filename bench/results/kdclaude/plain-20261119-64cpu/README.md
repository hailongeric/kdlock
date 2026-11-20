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

`era_ab.sh k14` on kdall14, no daemon, one boot, one 10 s run per point,
the three settings alternating per point (`data/k14-era.txt`): eras on (the
default), eras off (`kd_rw_era_ns=0`: no era in either family and the queue
heads measure nothing), and the rwsem's reader phase off
(`kd_rwsem_rphase_ns=0`) with eras on.

| test | workers | eras on | eras off | reader phase off | off/on | no-rphase/on | on/native | era_gate (on) |
|---|---|---|---|---|---|---|---|---|
| mmap1 | 4 | 3.53e+05 | 3.602e+05 | 3.499e+05 | 1.02 | 0.99 | 1.02 | 0 |
| mmap1 | 16 | 3.125e+05 | 3.167e+05 | 3.136e+05 | 1.01 | 1.00 | 1.01 | 0 |
| mmap1 | 32 | 3.085e+05 | 3.11e+05 | 3.026e+05 | 1.01 | 0.98 | 1.02 | 34 |
| mmap1 | 48 | 3.095e+05 | 2.03e+05 | 3.124e+05 | 0.66 | 1.01 | 1.74 | 297704 |
| mmap1 | 60 | 3.258e+05 | 1.908e+05 | 3.27e+05 | 0.59 | 1.00 | 1.91 | 436111 |
| mmap2 | 4 | 3.489e+05 | 3.505e+05 | 3.482e+05 | 1.00 | 1.00 | 1.00 | 0 |
| mmap2 | 16 | 3.267e+05 | 3.338e+05 | 3.308e+05 | 1.02 | 1.01 | 0.98 | 0 |
| mmap2 | 32 | 3.579e+05 | 3.6e+05 | 3.574e+05 | 1.01 | 1.00 | 1.00 | 0 |
| mmap2 | 48 | 3.694e+05 | 2.32e+05 | 3.714e+05 | 0.63 | 1.01 | 1.73 | 381974 |
| mmap2 | 60 | 3.65e+05 | 2.216e+05 | 3.628e+05 | 0.61 | 0.99 | 1.85 | 477856 |
| brk1 | 4 | 7.885e+05 | 7.526e+05 | 8.213e+05 | 0.95 | 1.04 | 1.11 | 0 |
| brk1 | 16 | 7.698e+05 | 7.403e+05 | 7.66e+05 | 0.96 | 0.99 | 1.10 | 16 |
| brk1 | 32 | 7.217e+05 | 6.925e+05 | 7.223e+05 | 0.96 | 1.00 | 1.06 | 41 |
| brk1 | 48 | 7.715e+05 | 4.451e+05 | 8.356e+05 | 0.58 | 1.08 | 1.91 | 344656 |
| brk1 | 60 | 8.226e+05 | 4.196e+05 | 8.348e+05 | 0.51 | 1.01 | 2.15 | 453795 |
| page_fault1 | 4 | 1.953e+06 | 1.954e+06 | 1.962e+06 | 1.00 | 1.00 | 0.99 | 0 |
| page_fault1 | 16 | 3.028e+06 | 3.03e+06 | 3.033e+06 | 1.00 | 1.00 | 1.00 | 0 |
| page_fault1 | 32 | 2.856e+06 | 2.847e+06 | 2.847e+06 | 1.00 | 1.00 | 1.02 | 0 |
| page_fault1 | 48 | 4.128e+06 | 4.073e+06 | 4.127e+06 | 0.99 | 1.00 | 1.04 | 0 |
| page_fault1 | 60 | 4.425e+06 | 4.46e+06 | 4.455e+06 | 1.01 | 1.01 | 1.08 | 0 |

- **One node (4-32 threads):** without eras mmap1 and mmap2 are at
  1.00-1.02 of their rate with them, page_fault1 at 1.00, brk1 at 0.95-0.96.
  Whatever the era code costs on this path is inside the spread of single
  10 s runs (the gate counter is 0 there: no era exists on one node).
- **Two nodes (48-60 threads):** without eras mmap1, mmap2 and brk1 fall to
  0.51-0.66. The era is what makes the plain path 1.7-2.2 times native
  there (mmap1 at 60 threads without it: 191 k against native's 171 k).
- **Reader phase:** 0.98-1.08, no cost.

So the era logic costs the path without delegation nothing that these runs
can show, and it is not redesigned for the rwsem. (For the rwlock see
section 6: its queue heads run the same measurements once per write
acquisition in plain mode, and that family is below native.)

## 5. rwlock without delegation

In plain mode every contended writer is a queue head of its own, and
`kd_rw_post()` (a) announced its wait with one locked operation before
taking the lock with another, where the native slow path takes a lock that
is free with one, and (b) took the era measurements every time: two clock
reads and a store of the averages into a line all writers of the lock
share. Now a head that finds nobody in takes the lock at once, and a CPU's
heads measure at one write acquisition in `kd_rw_era_sample` (16).

`nano_ab.sh n12-rwera` on kdnat12 (the new code; no daemon; native rwlock
alongside; 2 rounds; `data/n12-rwera.md`), sampling 1 (measure every time,
as before), 16 and 64:

| profile | workers | native | kd kd_rw_era_sample=1 | /native | delegated | kd kd_rw_era_sample=16 | /native | delegated | kd kd_rw_era_sample=64 | /native | delegated |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rwlock_c01_w20 | 4 | 10.03 | 10.05 | 1.00 | 0 | 10.10 | 1.01 | 0 | 10.10 | 1.01 | 0 |
| rwlock_c01_w20 | 8 | 6.95 | 6.89 | 0.99 | 0 | 7.09 | 1.02 | 0 | 7.10 | 1.02 | 0 |
| rwlock_c01_w20 | 16 | 6.99 | 6.66 | 0.95 | 0 | 6.85 | 0.98 | 0 | 6.86 | 0.98 | 0 |
| rwlock_c01_w20 | 32 | 6.83 | 6.70 | 0.98 | 0 | 6.85 | 1.00 | 0 | 6.86 | 1.00 | 0 |
| rwlock_c01_w20 | 48 | 5.30 | 5.06 | 0.96 | 0 | 5.09 | 0.96 | 0 | 5.11 | 0.96 | 0 |
| rwlock_c01_w20 | 60 | 5.12 | 4.91 | 0.96 | 0 | 4.95 | 0.97 | 0 | 4.97 | 0.97 | 0 |
| rwlock_c08_w20 | 4 | 5.72 | 5.31 | 0.93 | 0 | 5.58 | 0.98 | 0 | 5.61 | 0.98 | 0 |
| rwlock_c08_w20 | 8 | 4.89 | 4.46 | 0.91 | 0 | 4.64 | 0.95 | 0 | 4.62 | 0.95 | 0 |
| rwlock_c08_w20 | 16 | 4.89 | 4.54 | 0.93 | 0 | 4.71 | 0.96 | 0 | 4.73 | 0.97 | 0 |
| rwlock_c08_w20 | 32 | 4.71 | 4.51 | 0.96 | 0 | 4.71 | 1.00 | 0 | 4.70 | 1.00 | 0 |
| rwlock_c08_w20 | 48 | 3.31 | 3.07 | 0.93 | 0 | 3.13 | 0.94 | 0 | 3.13 | 0.94 | 0 |
| rwlock_c08_w20 | 60 | 3.15 | 2.96 | 0.94 | 0 | 3.00 | 0.95 | 0 | 3.00 | 0.95 | 0 |
| rwlock_c08_w1 | 4 | 10.08 | 10.03 | 1.00 | 0 | 10.04 | 1.00 | 0 | 10.04 | 1.00 | 0 |
| rwlock_c08_w1 | 8 | 9.66 | 9.00 | 0.93 | 0 | 9.06 | 0.94 | 0 | 9.07 | 0.94 | 0 |
| rwlock_c08_w1 | 16 | 8.84 | 8.91 | 1.01 | 0 | 8.96 | 1.01 | 0 | 8.97 | 1.01 | 0 |
| rwlock_c08_w1 | 32 | 8.91 | 9.18 | 1.03 | 0 | 9.21 | 1.03 | 0 | 9.22 | 1.03 | 0 |
| rwlock_c08_w1 | 48 | 8.20 | 8.83 | 1.08 | 0 | 8.80 | 1.07 | 0 | 8.58 | 1.05 | 0 |
| rwlock_c08_w1 | 60 | 7.98 | 8.73 | 1.09 | 0 | 8.66 | 1.09 | 0 | 8.39 | 1.05 | 0 |

- 0.94-1.09 of native everywhere with 16 (g3 on the old code: 0.83-0.87
  with 20% writes from 6 workers on, 0.82-0.91 for c08 with 1% writes).
  Most of it is the single operation (sampling 1 already gives 0.91-1.00);
  sampling adds 2-4%.
- `kd_rw_era_ns=0` gives the same rates as sampling 16
  (`data/n12-rwnoera.md`): the measurements no longer show.

## 6. Spinlock: when delegation pays, and the plain handover

**Entering delegation mode.** `nano_ab.sh n12-enter` (daemon running,
`kd_deleg_enter` 5, 12 and 1000, kdnat12; `data/n12-enter.md`):

| profile | workers | native | kd kd_deleg_enter=5 | /native | delegated | kd kd_deleg_enter=12 | /native | delegated | kd kd_deleg_enter=1000 | /native | delegated |
|---|---|---|---|---|---|---|---|---|---|---|---|
| spin_c01 | 4 | 6.59 | 6.06 | 0.92 | 0 | 6.05 | 0.92 | 0 | 6.11 | 0.93 | 0 |
| spin_c01 | 6 | 6.87 | 6.04 | 0.88 | 931852 | 6.53 | 0.95 | 0 | 6.57 | 0.96 | 0 |
| spin_c01 | 8 | 7.01 | 6.18 | 0.88 | 4842445 | 6.78 | 0.97 | 0 | 6.77 | 0.97 | 0 |
| spin_c01 | 16 | 7.23 | 6.63 | 0.92 | 7006732 | 6.68 | 0.92 | 6979792 | 7.04 | 0.97 | 0 |
| spin_c01 | 32 | 6.65 | 6.50 | 0.98 | 6754551 | 6.52 | 0.98 | 6741490 | 6.58 | 0.99 | 0 |
| spin_c01 | 48 | 4.38 | 6.50 | 1.48 | 6618072 | 6.51 | 1.48 | 6843087 | 3.92 | 0.89 | 0 |
| spin_c01 | 60 | 4.11 | 6.40 | 1.56 | 6691193 | 6.41 | 1.56 | 6591623 | 3.57 | 0.87 | 0 |
| spin_c08 | 4 | 4.69 | 4.45 | 0.95 | 0 | 4.45 | 0.95 | 0 | 4.45 | 0.95 | 0 |
| spin_c08 | 6 | 4.57 | 4.30 | 0.94 | 1888425 | 4.53 | 0.99 | 0 | 4.52 | 0.99 | 0 |
| spin_c08 | 8 | 4.58 | 4.40 | 0.96 | 4386467 | 4.59 | 1.00 | 0 | 4.60 | 1.00 | 0 |
| spin_c08 | 16 | 4.72 | 4.33 | 0.92 | 4506320 | 4.35 | 0.92 | 4581398 | 4.57 | 0.97 | 0 |
| spin_c08 | 32 | 4.72 | 4.36 | 0.92 | 4507103 | 4.36 | 0.92 | 4383840 | 4.40 | 0.93 | 0 |
| spin_c08 | 48 | 3.12 | 4.34 | 1.39 | 4576593 | 4.33 | 1.39 | 4519529 | 2.81 | 0.90 | 0 |
| spin_c08 | 60 | 3.05 | 4.29 | 1.41 | 4452783 | 4.30 | 1.41 | 4492439 | 2.66 | 0.87 | 0 |
| spin_c01_sat | 4 | 6.61 | 6.24 | 0.94 | 0 | 6.24 | 0.94 | 0 | 6.24 | 0.94 | 0 |
| spin_c01_sat | 6 | 6.81 | 5.94 | 0.87 | 2520425 | 6.63 | 0.97 | 0 | 6.61 | 0.97 | 0 |
| spin_c01_sat | 8 | 6.84 | 6.63 | 0.97 | 6722612 | 6.78 | 0.99 | 0 | 6.80 | 0.99 | 0 |
| spin_c01_sat | 16 | 7.21 | 6.64 | 0.92 | 6962444 | 6.64 | 0.92 | 6978209 | 7.01 | 0.97 | 0 |
| spin_c01_sat | 32 | 6.69 | 6.53 | 0.98 | 6800116 | 6.50 | 0.97 | 6595049 | 6.59 | 0.99 | 0 |
| spin_c01_sat | 48 | 4.41 | 6.48 | 1.47 | 6748651 | 6.47 | 1.47 | 6628820 | 3.85 | 0.87 | 0 |
| spin_c01_sat | 60 | 4.28 | 6.40 | 1.49 | 6612177 | 6.38 | 1.49 | 6615566 | 3.63 | 0.85 | 0 |

On one node a lock that delegates is at or below the plain lock in this
boot whatever the depth it enters at; on two nodes delegation gives
1.39-1.56 and the plain lock 0.85-0.90. So the entry rule got a second
condition: a waiter of another NUMA node among the ones the queue head
samples (`kd_deleg_numa`, ARCHITECTURE 7a). `nano_ab.sh n13-numa` (kdnat13,
0 = by depth alone, 1 = the new default; `data/n13-numa.md`):

| profile | workers | native | kd kd_deleg_numa=0 | /native | delegated | kd kd_deleg_numa=1 | /native | delegated |
|---|---|---|---|---|---|---|---|---|
| spin_c01 | 6 | 5.36 | 4.90 | 0.92 | 704046 | 5.05 | 0.94 | 0 |
| spin_c01 | 8 | 5.28 | 5.60 | 1.06 | 4028564 | 5.05 | 0.96 | 0 |
| spin_c01 | 16 | 5.20 | 6.62 | 1.27 | 7015885 | 4.96 | 0.95 | 0 |
| spin_c01 | 32 | 6.42 | 6.62 | 1.03 | 6780342 | 6.20 | 0.97 | 0 |
| spin_c01 | 48 | 3.81 | 6.51 | 1.71 | 6754757 | 6.53 | 1.71 | 6829421 |
| spin_c01 | 60 | 3.83 | 6.48 | 1.69 | 6786874 | 6.50 | 1.70 | 6667083 |
| spin_c08 | 6 | 4.65 | 4.30 | 0.93 | 1797209 | 4.65 | 1.00 | 0 |
| spin_c08 | 8 | 4.67 | 4.30 | 0.92 | 4368436 | 4.66 | 1.00 | 0 |
| spin_c08 | 16 | 4.60 | 4.34 | 0.94 | 4533637 | 4.63 | 1.00 | 0 |
| spin_c08 | 32 | 4.74 | 4.42 | 0.93 | 4609263 | 4.64 | 0.98 | 0 |
| spin_c08 | 48 | 3.09 | 4.32 | 1.40 | 4442651 | 4.29 | 1.39 | 4346050 |
| spin_c08 | 60 | 3.02 | 4.31 | 1.43 | 4405819 | 4.33 | 1.43 | 4468678 |

- With the condition nothing is delegated on one node and kd is at
  0.94-1.00 of native; on two nodes it is unchanged (1.39-1.71).
- In this boot entering by depth alone looks better at 8-16 workers with
  one cache line (1.06-1.27): native and plain kd run at 5.0-5.4 Mops/s
  there, where the boot before had them at 6.5-7.2; the delegated rate is
  6.6 in both. The plain and native rates at 6-16 workers are bimodal
  between boots (not explained); the condition makes kd follow native.

**The plain handover.** A new queue head asked for its successor's node
line for writing while it still waited for the holder. The successor polls
that line and takes it back at once, so the handover paid the transfer
twice. `nano_ab.sh n13-dbg` with a temporary switch (0 = with the prefetch,
1 = without, 3 = also without the plain path's statistics and mode note;
plain mode, 3 rounds; `data/n13-dbg.md`):

| profile | workers | native | kd kd_dbg=0 | /native | delegated | kd kd_dbg=1 | /native | delegated | kd kd_dbg=3 | /native | delegated |
|---|---|---|---|---|---|---|---|---|---|---|---|
| spin_c01_sat | 8 | 5.24 | 5.09 | 0.97 | 0 | 5.34 | 1.02 | 0 | 5.39 | 1.03 | 0 |
| spin_c01_sat | 16 | 5.12 | 5.00 | 0.97 | 0 | 5.39 | 1.05 | 0 | 5.38 | 1.05 | 0 |
| spin_c01_sat | 32 | 6.39 | 6.28 | 0.98 | 0 | 6.65 | 1.04 | 0 | 6.59 | 1.03 | 0 |
| spin_c01_sat | 48 | 3.84 | 3.90 | 1.01 | 0 | 4.05 | 1.06 | 0 | 3.89 | 1.01 | 0 |
| spin_c01_sat | 60 | 3.89 | 3.92 | 1.01 | 0 | 3.98 | 1.02 | 0 | 3.89 | 1.00 | 0 |
| spin_c01 | 8 | 5.28 | 5.13 | 0.97 | 0 | 5.43 | 1.03 | 0 | 5.40 | 1.02 | 0 |
| spin_c01 | 16 | 5.19 | 5.01 | 0.97 | 0 | 5.42 | 1.04 | 0 | 5.40 | 1.04 | 0 |
| spin_c01 | 32 | 6.44 | 6.32 | 0.98 | 0 | 6.64 | 1.03 | 0 | 6.61 | 1.03 | 0 |
| spin_c01 | 48 | 3.84 | 3.84 | 1.00 | 0 | 3.84 | 1.00 | 0 | 3.86 | 1.00 | 0 |
| spin_c01 | 60 | 3.69 | 3.92 | 1.06 | 0 | 3.93 | 1.06 | 0 | 3.90 | 1.06 | 0 |

Without the prefetch the plain lock is 5-8% faster at 8-32 workers, with
and without work between the operations; the statistics and the mode note
cost nothing measurable. The prefetch is removed, the switch as well.

**lock1** (`files->file_lock` in `fcntl`, saturated; 0.82-0.94 of native in
the passes on kdall13 and kdall14): with the same switches on kdall16,
median of 3, at 16 / 32 / 60 threads: 0.94 / 0.90 / 0.92 as it was, 0.96 /
0.92 / 1.00 with both (`data/k16-dbg.txt`; single settings scatter by 4%).
Remeasured on kdall17 in section 9.

## 7. Apache without delegation: writers that spin for a reader-held lock

Native on kdnat12: 50.6 k, 41.7 k, 35.7 k, 34.2 k, 33.8 k requests per
second at 4, 16, 32, 48, 60 threads of one process; kd off on kdall14:
1.03, 1.06, 0.90, 0.73, 0.71 of that (`data/n12-native-apache-runs.txt`).
Eras are not the reason: on, off and with a 200 us bound give the same
rates (`data/k15-apache-era-runs.txt`).

`data/prof/apache-60-kd-off-and-native.txt`, 60 threads:

| | native (kdnat12) | kd off (kdall15) |
|---|---|---|
| CPUs the server's threads occupy | 3.5 | 34.3 |
| where their time goes | asleep in `rwsem_down_write_slowpath` (44 k sleeps/s), `rwsem_down_read_slowpath`, `folio_wait_bit` | 77% in `kd_wait_sleepable` (queue spinning), 12 k sleeps/s in `kd_mutex_sleep` |
| requests per second | 31.5 k | 23.2 k |

A queued kd writer spins while the holder of `m` runs, also when that
holder only waits for readers; the native rwsem's writers sleep behind a
reader-held lock. Spinning threads keep their mm live on their CPUs, so the
TLB flush of every munmap (in its read part) interrupts 34 CPUs instead of
3 and waits for them. Fix: `kd_rwsem_park_drain_ns` (LOCKS.md 5): in plain
mode a writer that has to wait parks when the readers of the lock take
longer than 5 us to leave on average.

In-boot comparison on kdall16 (threshold off / 5 us / 20 us, mean of 2;
`data/k16-park*.txt`), against native:

| | off | 5 us | 20 us |
|---|---|---|---|
| Apache single, 16 threads | 1.05 | 1.10 | 1.09 |
| 32 | 0.93 | 1.27 | 0.91 |
| 48 | 0.76 | 1.32 | 0.81 |
| 60 | 0.71 | 1.31 | 0.79 |
| Apache default configuration | 1.23 | 1.37 | 1.23 |
| mmap1 16 / 32 / 60 | 1.00 / 1.01 / 1.86 | 0.97 / 0.99 / 1.77 | 0.97 / 0.96 / 1.82 |
| brk1 16 / 32 / 60 | 1.07 / 1.09 / 2.06 | 1.06 / 0.97 / 2.00 | 1.03 / 1.04 / 2.01 |
| page_fault1, page_fault3 16-60 | 0.99-1.09 | 0.99-1.10 | 1.00-1.10 |

## 8. Psearchy and LevelDB in the IntervalVM configurations

The curves that turn over at about 36 threads (Psearchy) and at 4 (LevelDB)
are those of the IntervalVM paper (SOSP '25, Linux 6.8) and its artifact:
`pedsort -m 2048` without `-l`, and LevelDB `readrandom` on a database of
2 M entries of 4 KiB. The grid runs the TCLocks lines (`-m 128 -l 200000`; a
110 MB database). `ivm_apps.sh`, `data/ivm-runs.txt`; the desk research
with every source, what each published curve ran and why it turns:
[psearchy-leveldb-published-curves.md](psearchy-leveldb-published-curves.md).

**LevelDB.** Native (kdnat12, tag i1): 19.6 k, 114 k, 126 k, 103 k, 81 k,
62 k, 52 k operations per second at 1, 4, 8, 16, 32, 40, 60 threads: the
peak at 4-8 threads and the decline. The 6 GB database is 3229 table files
of 2 MB against a table cache of 990, so a lookup opens and maps a table
and evicts and unmaps another: 40 k mmap and 40 k munmap per second at 4
threads. With `--open_files=50000` the same database gives 306 k, 926 k,
1.29 M, 1.30 M, 1.31 M, 783 k, 678 k: ten times the rate and the shape of
the grid's LevelDB line, whose limit is LevelDB's own mutex (futex). So the
collapse elsewhere is an mmap lock writer collapse made by table cache
thrashing, and it is absent from the TCLocks configuration because all
tables stay mapped there.

*Comparing kernels needs one database.* How `fillrandom` and its
compactions leave the levels differs from fill to fill, and with it how
many tables a lookup opens: native did 114 k at 4 threads on one fill
(i1) and 62-63 k on another (i4, two passes within 3% of each other),
while kd did 66-69 k on its own fills. The first comparison (kd off at
0.61 of native at 4 threads) was between different databases and is void.
`ivm_apps.sh` now keeps the first fill on disk and copies it for every
pass; section 9 has the comparison on one database.

**Psearchy.** Native (kdnat12), jobs per hour at 1 / 16 / 32 / 60 threads:
`-m 128 -l 200000` 13.5 / 197 / 289 / 514; `-m 256` 13.7 / 189 / 248 / 407;
`-m 1024` 13.9 / 155 at 16 (four 256 MB arrays per thread: no more fit
into 24 GiB). No peak up to 60 threads; the larger the per-thread tables,
the less it scales (at 16 threads 12.3, 11.8 and 9.7 jobs per hour and
core). kd on kdall16: 0.99-1.06 of native without the daemon and 0.91-1.05
with it; at most 35 sections were delegated in a run, so the mmap lock is
hardly contended in these configurations. `-m 2048` on 36 and more threads,
where the paper's curve turns, needs about 1.5 GB per thread and cannot be
run in this VM. What the published sources give as the reasons for the
turn (kernel generation with and without per-VMA locks, glibc's stdio
buffers by mmap before 2.23, the table size) is in that file.

## 9. kdall17: everything together

`k17_exp.sh` in the guest (on the cloud host in `/root/kdwork/`): the
correctness checks, then a reduced grid off, two learning passes, on, and
on again with an allow list without `__vm_munmap`. One run per point;
native from g3 (will-it-scale, kdnat11), kdnat12 (Apache) and kdnat13
(LevelDB, mean of 2, the saved database). `data/k17-check.out`,
`data/k17-runs.txt`, `data/ivm-runs.txt` (tags i4, i5, i5nm),
`data/k17-summary.md`:

| bench | variant | workers | native | off/native | on/native | on without munmap/native | on: delegated, handbacks | without munmap: delegated, handbacks |
|---|---|---|---|---|---|---|---|---|
| wis | lock1 | 4 | 9.742e+06 | 1.00 | 0.99 | 0.99 | 0, 0 | 0, 0 |
| wis | lock1 | 16 | 1.064e+07 | 0.81 | 0.87 | 0.90 | 0, 0 | 0, 0 |
| wis | lock1 | 32 | 1.08e+07 | 0.87 | 0.87 | 0.87 | 0, 0 | 0, 0 |
| wis | lock1 | 48 | 6.347e+06 | 0.94 | 0.91 | 0.94 | 0, 0 | 0, 0 |
| wis | lock1 | 60 | 5.981e+06 | 0.92 | 0.94 | 0.86 | 0, 0 | 0, 0 |
| wis | mmap1 | 4 | 3.468e+05 | 0.99 | 1.17 | 0.97 | 12962925, 99 | 3094082, 24 |
| wis | mmap1 | 16 | 3.084e+05 | 0.98 | 1.24 | 0.95 | 12272085, 10 | 2757050, 1 |
| wis | mmap1 | 32 | 3.019e+05 | 0.99 | 1.28 | 0.95 | 12361947, 3 | 2522212, 0 |
| wis | mmap1 | 48 | 1.783e+05 | 1.63 | 1.77 | 1.58 | 10184158, 43 | 2346714, 0 |
| wis | mmap1 | 60 | 1.708e+05 | 1.81 | 1.82 | 1.74 | 10114410, 69 | 2428463, 0 |
| wis | mmap2 | 4 | 3.506e+05 | 1.00 | 1.09 | 0.95 | 12183361, 384 | 2968148, 31 |
| wis | mmap2 | 16 | 3.339e+05 | 0.99 | 1.13 | 0.94 | 12044463, 28 | 2717818, 0 |
| wis | mmap2 | 32 | 3.591e+05 | 0.96 | 1.07 | 0.91 | 12344918, 10 | 2752202, 0 |
| wis | mmap2 | 48 | 2.131e+05 | 1.67 | 1.50 | 1.58 | 10336747, 38 | 2749056, 0 |
| wis | mmap2 | 60 | 1.977e+05 | 1.79 | 1.58 | 1.70 | 10047287, 29 | 2715989, 0 |
| wis | brk1 | 4 | 7.107e+05 | 1.11 | 1.10 | 1.25 | 12267457, 356 | 13243673, 635 |
| wis | brk1 | 16 | 7.026e+05 | 1.05 | 1.63 | 1.55 | 18309469, 19 | 17386549, 170 |
| wis | brk1 | 32 | 6.819e+05 | 1.09 | 1.64 | 1.66 | 17924852, 20 | 18163189, 54 |
| wis | brk1 | 48 | 4.035e+05 | 1.83 | 2.00 | 1.98 | 13044933, 98 | 12931266, 114 |
| wis | brk1 | 60 | 3.832e+05 | 1.94 | 2.28 | 1.92 | 13961339, 88 | 12035315, 84 |
| wis | page_fault1 | 4 | 1.978e+06 | 1.00 | 0.98 | 0.98 | 0, 0 | 1, 0 |
| wis | page_fault1 | 16 | 3.025e+06 | 1.00 | 0.99 | 0.99 | 7, 2 | 4, 2 |
| wis | page_fault1 | 32 | 2.795e+06 | 1.03 | 1.02 | 1.02 | 18, 13 | 18, 12 |
| wis | page_fault1 | 48 | 3.961e+06 | 1.03 | 1.01 | 1.02 | 27, 15 | 30, 15 |
| wis | page_fault1 | 60 | 4.091e+06 | 1.09 | 1.07 | 1.07 | 33, 23 | 34, 19 |
| wis | page_fault2 | 4 | 1.507e+06 | 0.99 | 0.99 | 0.99 | 0, 0 | 0, 0 |
| wis | page_fault2 | 16 | 2.021e+06 | 1.00 | 1.00 | 1.00 | 11, 0 | 8, 0 |
| wis | page_fault2 | 32 | 2e+06 | 1.00 | 0.99 | 0.99 | 21, 0 | 22, 0 |
| wis | page_fault2 | 48 | 3.299e+06 | 1.01 | 0.98 | 0.97 | 32, 0 | 37, 0 |
| wis | page_fault2 | 60 | 3.682e+06 | 1.00 | 0.84 | 0.90 | 35, 0 | 35, 0 |
| wis | page_fault3 | 4 | 3.771e+06 | 0.99 | 1.00 | 0.99 | 0, 0 | 0, 0 |
| wis | page_fault3 | 16 | 1.324e+07 | 1.00 | 0.98 | 0.98 | 12, 0 | 8, 0 |
| wis | page_fault3 | 32 | 1.256e+07 | 1.04 | 1.01 | 1.01 | 18, 0 | 20, 0 |
| wis | page_fault3 | 48 | 1.221e+07 | 1.03 | 1.02 | 1.02 | 30, 0 | 35, 0 |
| wis | page_fault3 | 60 | 1.215e+07 | 1.03 | 1.03 | 1.03 | 36, 0 | 31, 0 |
| apache | single | 4 | 5.061e+04 | 1.09 | 1.04 | 1.03 | 21073, 72007 | 6719, 0 |
| apache | single | 16 | 4.166e+04 | 1.06 | 1.11 | 1.08 | 462857, 462384 | 110213, 0 |
| apache | single | 32 | 3.567e+04 | 1.24 | 1.24 | 1.19 | 445793, 444865 | 118556, 0 |
| apache | single | 48 | 3.423e+04 | 1.27 | 1.31 | 1.23 | 450125, 449742 | 124488, 0 |
| apache | single | 60 | 3.382e+04 | 1.27 | 1.31 | 1.23 | 444490, 443722 | 123407, 0 |
| apache | default | 0 | 1.391e+05 | 1.27 | 1.20 | 1.22 | 1228391, 1140249 | 445593, 1 |
| leveldb | ivm | 4 | 6.258e+04 | 0.86 | 1.00 | 0.83 | 298305, 174768 | 91828, 2005 |
| leveldb | ivm | 8 | 1.003e+05 | 0.98 | 0.95 | 0.98 | 1239799, 1181887 | 644027, 1289 |
| leveldb | ivm | 16 | 1.028e+05 | 1.13 | 1.00 | 1.15 | 1242837, 1240573 | 831698, 17 |
| leveldb | ivm | 32 | 8.101e+04 | 1.15 | 1.04 | 1.22 | 1007777, 1005592 | 707366, 30 |
| leveldb | ivm | 60 | 5.265e+04 | 1.16 | 1.17 | 1.21 | 718086, 711981 | 378995, 52 |

Correctness: locktorture 6 of 6, `run_corr.py` plain and with the daemon
240 points each 0 failed, API check 0 failed, test-ww_mutex, `mm_stress`
16/32/64; no kernel complaint and no fatal signal in any pass; per-CPU
lock bytes 0 of 64 after each benchmark of the delegated pass; `hb_region`
(upper bound) 1658 over the boot.

Without delegation everything is at 0.96 or above except

- **lock1 at 16-32 threads, 0.81-0.87** (section 10), and
- **LevelDB at 4 threads, 0.86**: the parking of section 7. In one boot of
  kdall16 the same point is 16% lower with the threshold than without, and
  8% lower at 8 threads (`data/ivm-runs.txt`, tags i3-park5000 and
  i3-park0); section 10.

`page_fault2` at 60 threads with the daemon (0.84, 35 sections delegated,
0.90 with the other allow list) is one run and not explained.

## 10. After kdall17: lock1, parking with few threads, handbacks

**lock1.** Three boots each of kdall17 and kdnat14, three rounds per boot
(`lock1_boot.sh`, `data/lock1-boots.txt`; median per boot, in M operations
per second):

| threads | native, 3 boots | kd, 3 boots | kd/native |
|---|---|---|---|
| 8 | 9.99-10.35 | 9.05-9.48 | 0.93 |
| 16 | 10.73-11.01 | 9.47-9.70 | 0.88 |
| 32 | 10.18-10.70 | 9.46-9.56 | 0.91 |
| 48 | 5.97-6.51 | 5.99-6.18 | 0.95 |
| 60 | 5.83-6.16 | 5.45-6.00 | 0.98 |

The native rate does not move between boots, so the gap on one node was
real. `files->file_lock` is passed on ten million times a second (93 ns
per handover on native) and nothing else in the benchmark is contended.
The two slow paths are the same algorithm step by step; the profiles
(`lock1_perf.sh`, `data/prof/lock1-16-native-kd.txt`) differ in one place:
kd has 1.4% of its slow-path samples on a load of the lock word before
the enqueue where native has none, and 2.95 L1 misses per operation
against 2.51. kd loaded the lock word on entry to the slow path, where
the native slow path is given the value the failed fast path returned, and
every such load by an arriving caller competes for the lock's line with
the holder and the queue head. In one boot of kdall19 with temporary
switches (`k19_lock1.sh`, `data/k19-dbg.txt`, 4 rounds, median, against
the native medians above):

| | 8 | 16 | 32 |
|---|---|---|---|
| load on entry (as before) | 9.06 M, 0.91 | 9.34 M, 0.85 | 9.51 M, 0.92 |
| value passed by the entry stub | 9.69 M, 0.97 | 10.16 M, 0.93 | 10.12 M, 0.97 |
| ... and no second look when a queue was seen | 9.73 M, 0.97 | 10.45 M, 0.95 | 10.05 M, 0.97 |
| ... with the successor prefetch again | 10.05 M, 1.00 | 9.83 M, 0.90 | 9.95 M, 0.96 |

The third line is the code now (LOCKS.md 2). On kdall20, nine rounds
(`data/k20-lock1.txt`): 0.98, 0.91, 0.98, 0.98, 1.05 at 8, 16, 32, 48, 60
threads against those native medians; the runs at 16 threads scatter from
8.9 to 10.6 M (native 10.0 to 11.0 M). L1 misses per operation there are
2.39 now; what is left at 16 threads is not explained.

**Parking with few threads.** Parking by the drain time alone (section 7)
cost LevelDB in the IntervalVM configuration 16% at 4 threads and 8% at 8
(kdall16, in one boot). A first second condition, the average number of
writers spinning behind the one that waits for the readers, did not hold:
once writers park the queue is short, the average falls and parking ends
(`k18_exp.sh`, `data/k18-park*`: Apache at 60 threads 0.78 with a
threshold of 4, 0.70 with 8, 1.28 without the condition). Counting the
parked writers too does (`k20_exp.sh`, `data/k20-park*`, kdall20, no
daemon, one boot, mean of 2, against native):

| | threads | never | by drain time alone | 4 waiting | 6 waiting (default) |
|---|---|---|---|---|---|
| Apache single | 16 / 32 / 60 | 1.07 / 0.89 / 0.70 | 1.09 / 1.27 / 1.28 | 1.09 / 1.24 / 1.27 | 1.12 / 1.24 / 1.27 |
| Apache default | | 1.19 | 1.26 | 1.35 | 1.35 |
| LevelDB ivm | 4 / 8 | 1.06 / 1.06 | 0.88 / 0.98 | 1.07 / 1.09 | 1.08 / 1.09 |
| | 16 / 32 | 1.10 / 1.07 | 1.12 / 1.15 | 1.11 / 1.14 | 1.10 / 1.14 |
| mmap1 | 8 / 16 / 32 | 1.01 / 1.00 / 1.01 | 0.96 / 0.97 / 0.99 | 0.97 / 0.98 / 0.98 | 0.97 / 0.97 / 0.99 |
| brk1 | 8 / 16 / 32 | 1.02 / 1.06 / 1.06 | 0.99 / 1.07 / 1.08 | 1.00 / 1.05 / 1.05 | 0.99 / 1.05 / 1.08 |

**Handbacks.** The only sections that are handed back almost every time
are those of `munmap` when it unmaps mapped pages: the combiner keeps the
downgrade (`kd_vdown=1`), zaps, and reaches the TLB flush, a frontier.
With `__vm_munmap` out of the allow list on kdall17 (section 9, last two
columns) LevelDB was at 1.15-1.22 where the full list gave 1.00-1.04 at
16-32 threads. In one boot of kdall20 (`k20b_exp.sh`, `data/k20-vdown*`,
mean of 2, against native; "off" from the parking comparison of the same
boot):

| | threads | off | on, kept downgrade | on, `kd_vdown=0` |
|---|---|---|---|---|
| LevelDB ivm | 4 / 8 / 16 / 32 | 1.08 / 1.09 / 1.10 / 1.14 | 1.01 / 0.96 / 0.98 / 1.03 | 1.04 / 1.01 / 1.05 / 1.07 |
| Apache single | 16 / 32 / 60 | 1.12 / 1.24 / 1.27 | 1.12 / 1.23 / 1.30 | 1.07 / 1.19 / 1.22 |
| Apache default | | 1.35 | 1.22 | 1.10 |
| mmap1 | 16 / 60 | | 1.24 / 1.83 | 0.89 / 0.99 |
| brk1 | 16 / 60 | | 1.32 / 2.23 | 1.07 / 1.27 |

LevelDB: 2.4 M sections in 20 s, 99.8% handed back, 7-12% below off.
Handing back at the downgrade instead is no better and takes away what
mmap1 and brk1 gain. So frequent handbacks do cost, and the site account
now counts a handback after a kept downgrade as one (it counted as useful
before): a `munmap` site whose sections mostly end that way is switched
off, and tried again after 1 to 4 s (64 s before: the same site serves
mmap1, whose sections complete). TRANSLATOR.md section 3.

## 11. kdall21 against its native twin

`k21_exp.sh` (kdall21: correctness, off, two learning passes, on, and the
will-it-scale tests once more right after LevelDB) and `n18_exp.sh`
(kdnat18, the twin built from the same source; `virt_spin_lock_key` 0).
One run per point. `data/k21-check.out`, `data/k21-runs.txt`,
`data/k21-leveldb-runs.txt`, `data/n18-*.txt`, `k21_summary.py`:

| bench | variant | workers | native | off/native | on/native | on/off | on: delegated, handbacks | on, after LevelDB / native |
|---|---|---|---|---|---|---|---|---|
| wis | lock1 | 4 | 9.825e+06 | 1.00 | 0.99 | 1.00 | 0, 0 | - |
| wis | lock1 | 16 | 1.024e+07 | 1.03 | 0.97 | 0.94 | 0, 0 | 1.01 |
| wis | lock1 | 32 | 1.065e+07 | 0.93 | 0.92 | 0.99 | 0, 0 | - |
| wis | lock1 | 48 | 6.172e+06 | 0.93 | 1.01 | 1.08 | 0, 0 | - |
| wis | lock1 | 60 | 5.813e+06 | 1.04 | 1.04 | 1.00 | 0, 0 | 0.92 |
| wis | mmap1 | 4 | 3.364e+05 | 1.04 | 1.21 | 1.16 | 12971714, 187 | - |
| wis | mmap1 | 16 | 2.926e+05 | 1.04 | 1.31 | 1.26 | 12252743, 30 | 1.31 |
| wis | mmap1 | 32 | 2.893e+05 | 1.04 | 1.33 | 1.27 | 12388256, 15 | - |
| wis | mmap1 | 48 | 1.715e+05 | 1.72 | 1.90 | 1.10 | 10413530, 83 | - |
| wis | mmap1 | 60 | 1.651e+05 | 1.85 | 1.83 | 0.99 | 9748476, 75 | 1.89 |
| wis | mmap2 | 4 | 3.381e+05 | 1.01 | 1.12 | 1.10 | 12067817, 433 | - |
| wis | mmap2 | 16 | 3.35e+05 | 0.98 | 1.12 | 1.14 | 12024735, 18 | 1.13 |
| wis | mmap2 | 32 | 3.538e+05 | 0.97 | 1.09 | 1.12 | 12355307, 9 | - |
| wis | mmap2 | 48 | 2.125e+05 | 1.68 | 1.53 | 0.91 | 10461673, 31 | - |
| wis | mmap2 | 60 | 2.029e+05 | 1.75 | 1.55 | 0.89 | 10122163, 27 | 1.48 |
| wis | brk1 | 4 | 6.934e+05 | 1.26 | 1.14 | 0.90 | 12538830, 430 | - |
| wis | brk1 | 16 | 6.929e+05 | 1.06 | 1.59 | 1.50 | 17599832, 32 | 1.53 |
| wis | brk1 | 32 | 6.708e+05 | 1.11 | 1.66 | 1.50 | 17918987, 26 | - |
| wis | brk1 | 48 | 4.177e+05 | 1.86 | 1.94 | 1.05 | 12965822, 97 | - |
| wis | brk1 | 60 | 3.666e+05 | 2.09 | 2.17 | 1.04 | 12705838, 71 | 2.53 |
| wis | page_fault1 | 4 | 1.953e+06 | 1.02 | 1.00 | 0.98 | 0, 0 | - |
| wis | page_fault1 | 16 | 2.991e+06 | 1.02 | 1.01 | 1.00 | 7, 2 | 1.01 |
| wis | page_fault1 | 32 | 2.854e+06 | 1.00 | 1.00 | 1.00 | 14, 12 | - |
| wis | page_fault1 | 48 | 3.993e+06 | 1.02 | 1.01 | 0.99 | 32, 13 | - |
| wis | page_fault1 | 60 | 4.187e+06 | 1.06 | 1.06 | 1.00 | 28, 23 | 1.07 |
| wis | page_fault2 | 4 | 1.511e+06 | 0.99 | 0.99 | 1.00 | 0, 0 | - |
| wis | page_fault2 | 16 | 2.019e+06 | 1.00 | 0.99 | 1.00 | 11, 0 | 1.00 |
| wis | page_fault2 | 32 | 1.995e+06 | 1.00 | 1.00 | 1.00 | 23, 0 | - |
| wis | page_fault2 | 48 | 3.274e+06 | 1.01 | 1.00 | 1.00 | 23, 0 | - |
| wis | page_fault2 | 60 | 3.666e+06 | 1.00 | 0.90 | 0.90 | 33, 0 | 0.91 |
| wis | page_fault3 | 4 | 3.744e+06 | 1.01 | 1.00 | 1.00 | 0, 0 | - |
| wis | page_fault3 | 16 | 1.306e+07 | 1.01 | 1.00 | 0.99 | 9, 0 | 1.00 |
| wis | page_fault3 | 32 | 1.251e+07 | 1.05 | 1.03 | 0.99 | 21, 0 | - |
| wis | page_fault3 | 48 | 1.214e+07 | 1.04 | 1.03 | 0.99 | 29, 0 | - |
| wis | page_fault3 | 60 | 1.214e+07 | 1.05 | 1.04 | 0.98 | 35, 0 | 1.02 |
| apache | single | 4 | 5.118e+04 | 1.03 | 0.98 | 0.95 | 11354, 918 | - |
| apache | single | 16 | 3.963e+04 | 1.15 | 1.11 | 0.96 | 106834, 769 | - |
| apache | single | 32 | 3.582e+04 | 1.22 | 1.19 | 0.97 | 119439, 774 | - |
| apache | single | 48 | 3.382e+04 | 1.29 | 1.24 | 0.96 | 125071, 781 | - |
| apache | single | 60 | 3.322e+04 | 1.30 | 1.25 | 0.96 | 126850, 775 | - |
| apache | default | 0 | 1.411e+05 | 1.33 | 1.23 | 0.93 | 497260, 772 | - |
| leveldb | ivm | 4 | 6.079e+04 | 1.08 | 1.06 | 0.99 | 140812, 1794 | - |
| leveldb | ivm | 8 | 1.005e+05 | 1.08 | 1.05 | 0.97 | 731900, 1538 | - |
| leveldb | ivm | 16 | 1.044e+05 | 1.10 | 1.08 | 0.98 | 780118, 1301 | - |
| leveldb | ivm | 32 | 8.216e+04 | 1.12 | 1.09 | 0.97 | 602188, 1305 | - |
| leveldb | ivm | 60 | 5.384e+04 | 1.10 | 1.04 | 0.94 | 230575, 1302 | - |

below the bounds (off 0.93, on 0.90): wis lock1 32 off 0.93

- Correctness: locktorture 6 of 6, `run_corr.py` plain and with the daemon
  240 points each 0 failed, API check 0 failed, test-ww_mutex, `mm_stress`
  16/32/64; no kernel complaint and no fatal signal in any pass; per-CPU
  lock bytes 0 of 64 after every benchmark of the delegated pass.
- Counters over the boot (`data/k21-on-stats.txt`): 455.6 M sections
  delegated, 1.33 M handed back (0.3%; the same passes on kdall20 with the
  old account: 264 M and 65.8 M), `vdown` 168.8 M of which handed back
  0.52 M, `site_retry` 207, `hb_region` (upper bound) 3757,
  `done_in_region` 0.
- Without delegation every point is at 0.93 of native or above (the
  lowest: lock1 at 32 and 48 threads, 0.93); with it at 0.90 or above
  (page_fault2 at 60 threads 0.90 with 33 sections delegated, as in
  section 9; lock1 at 32 threads 0.92).
- With the daemon LevelDB is at 1.04-1.09 (1.00-1.04 at 16-32 threads on
  kdall17), the `munmap` site off: 1300-1800 handbacks per run instead of
  one per section. Apache is 3-5% below its rate without the daemon (7% in
  the default configuration); on kdall17, where every munmap was delegated
  and handed back, single-process Apache was level with off.
- The last column is the pass right after LevelDB had switched the
  `munmap` site off: mmap1 1.31 and 1.89, as in the pass before it.

Not covered by this round: Psearchy, Metis, FxMark and the nano grid on
kdall21; the lkp workloads.

## 12. Files

| file | what |
|---|---|
| `prof.sh` | profile of single grid points; `data/prof/` (tag p1: native on kdnat11, off on kdall13) |
| `steal_ab.sh`, `steal_summary.py` | section 3; `data/k14-steal.*` |
| `era_ab.sh`, `data/k14-era.*` | section 4 |
| `nano_ab.sh`, `nano_ab_summary.py`, `data/n12-*`, `data/n13-*` | sections 5 and 6 |
| `data/k15-apache-era-runs.txt`, `data/k16-park*`, `data/prof/apache-60-*` | section 7 |
| `ivm_apps.sh`, `data/ivm-runs.txt` | section 8 |
| `k17_exp.sh`, `data/k17-*` | section 9 |
| `lock1_boot.sh`, `lock1_perf.sh`, `k19_lock1.sh`, `k18_exp.sh`, `k20*_exp.sh`, `data/lock1-boots.txt`, `data/k18-*`, `data/k19-dbg.txt`, `data/k20-*` | section 10 |
| `k21_exp.sh`, `n18_exp.sh`, `k21_summary.py`, `data/k21-*`, `data/n18-*` | section 11 |
| `data/g3-*`, `data/nano-g3-ranges.md`, `data/app-g2kd-g3native*` | section 1 |
| `data/k14-check.out` | correctness of kdall14 |
