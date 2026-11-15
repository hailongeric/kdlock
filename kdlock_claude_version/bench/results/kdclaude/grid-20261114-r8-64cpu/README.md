# Round 8: sleepable-class session and rwsem reader changes (64 vCPUs, build #61)

## Setup

* **Host and VM:** as round 7 (`../grid-20261114-r7-64cpu/`): 10.176.26.71,
  64 vCPUs as 2 x 32, workers 1-32 on node 0, 40-64 across both nodes.
* **Kernel:** `7.0.0-38-kdclaude1` build #61.
* **Source:** commit `3bf4bfaa`. The `dirty` field in the data reads true
  although the tree equals that commit: `run_grid.py` treats
  `KD_DIRTY=0` as set.
* **Changes against round 7** (LOCKS 4 and 5 have the in-boot A/B data):
  * the session announces a waiter with a plain store one section ahead
    instead of a cmpxchg per section;
  * a mutex handoff is granted only to a running waiter;
  * waiting rwsem readers poll a phase counter, not `count`;
  * an rwsem queue head leaves the readers a phase of 1000 ns per reader.
* **Run:** as round 7: 14 profiles, 18 worker counts, Native, kd and TCLock
  alternating per point, 2 rounds of 1 s, 1512 points. No point failed its
  data oracle; the daemon was up at the end; no kernel complaint.
  `summary.txt` has the per-point medians. Two rounds give no variance
  claim.

## kd/Native and kd/TCLock, ranges per region

| Profile | 2-5 kd/Nat | 6-8 kd/Nat | 12-32 kd/Nat | 40-64 kd/Nat | 2-5 kd/TC | 6-8 kd/TC | 12-32 kd/TC | 40-64 kd/TC |
|---|---|---|---|---|---|---|---|---|
| mutex_c01 | 1.00-1.21 | 1.09-1.16 | 1.11-1.12 | 1.50-2.06 | 1.00-1.72 | 1.21-1.62 | 1.19-1.21 | 1.15-1.21 |
| mutex_c16 | 1.02-1.18 | 1.15-1.44 | 1.47-1.51 | 1.78-2.33 | 0.88-1.38 | 1.52-1.87 | 1.92-2.02 | 1.89-1.94 |
| rwlock_c01_w1 | 1.00-1.00 | 1.00-1.03 | 1.01-1.04 | 1.05-1.07 | 1.00-1.00 | 0.97-1.01 | 0.97-1.03 | 0.90-0.92 |
| rwlock_c01_w100 | 0.94-1.04 | 1.04-1.14 | 1.15-1.17 | 1.46-1.76 | 0.94-1.08 | 1.05-1.13 | 1.16-1.19 | 1.12-1.16 |
| rwlock_c01_w20 | 0.96-1.07 | 1.00-1.06 | 0.96-1.03 | 0.93-0.97 | 0.98-1.10 | 1.22-1.25 | 1.17-1.20 | 0.89-0.98 |
| rwlock_c16_w1 | 0.98-1.00 | 0.99-1.02 | 1.02-1.04 | 1.06-1.08 | 0.99-1.00 | 0.97-1.00 | 0.98-1.02 | 0.94-0.96 |
| rwlock_c16_w20 | 0.99-1.06 | 1.10-1.13 | 1.12-1.14 | 1.08-1.09 | 0.98-1.07 | 1.11-1.13 | 1.05-1.12 | 0.72-0.80 |
| rwsem_c01_w1 | 1.00-1.64 | 1.86-2.44 | 2.35-2.54 | 2.54-2.64 | 1.00-1.03 | 1.11-1.25 | 1.07-1.29 | 0.89-0.99 |
| rwsem_c01_w100 | 0.80-1.00 | 0.97-1.17 | 1.12-1.17 | 1.52-2.30 | 0.95-1.08 | 1.17-1.29 | 1.17-1.19 | 1.13-1.21 |
| rwsem_c01_w20 | 1.00-3.43 | 2.75-2.84 | 2.88-2.96 | 3.73-4.05 | 0.96-1.20 | 1.29-1.33 | 0.99-1.19 | 0.85-0.90 |
| rwsem_c16_w1 | 1.03-1.45 | 1.55-2.03 | 2.16-2.23 | 2.56-2.91 | 0.95-1.03 | 0.94-1.05 | 1.01-1.12 | 0.82-0.90 |
| rwsem_c16_w20 | 1.37-2.33 | 2.43-2.56 | 2.66-2.72 | 2.85-3.28 | 0.94-1.15 | 1.28-1.31 | 1.08-1.20 | 0.78-0.82 |
| spin_c01 | 0.88-1.08 | 0.66-0.80 | 0.67-0.70 | 0.92-1.05 | 1.12-1.64 | 0.92-1.39 | 0.89-0.95 | 0.93-0.95 |
| spin_c08 | 0.92-1.08 | 0.89-0.98 | 0.88-0.91 | 1.12-1.25 | 0.99-1.44 | 1.06-1.27 | 1.02-1.05 | 1.00-1.04 |

## Against round 7 (same host and VM, build #56)

kd Mops/s, medians. Different builds and boots, so this is a before/after
of the change set, not a pooled result. TCLock and Native show the drift
between the two boots.

| Profile | n | r7 kd | r8 kd | r8/r7 | r7 TCLock | r8 TCLock | r7 Native | r8 Native |
|---|---|---|---|---|---|---|---|---|
| mutex_c01 | 8 | 2.63 | 3.24 | 1.23 | 2.75 | 2.69 | 3.01 | 2.89 |
| mutex_c01 | 32 | 2.47 | 3.19 | 1.29 | 3.06 | 2.67 | 2.91 | 2.87 |
| mutex_c01 | 64 | 1.99 | 3.08 | 1.54 | 2.81 | 2.55 | 1.46 | 1.49 |
| mutex_c16 | 8 | 2.59 | 2.90 | 1.12 | 1.56 | 1.55 | 2.09 | 2.01 |
| mutex_c16 | 32 | 2.53 | 3.11 | 1.23 | 1.57 | 1.54 | 2.06 | 2.05 |
| mutex_c16 | 64 | 2.30 | 2.97 | 1.29 | 1.56 | 1.55 | 1.35 | 1.27 |
| rwlock_c01_w1 | 8 | 7.27 | 7.78 | 1.07 | 6.93 | 7.67 | 7.98 | 7.53 |
| rwlock_c01_w1 | 32 | 7.85 | 7.92 | 1.01 | 7.88 | 7.93 | 7.83 | 7.83 |
| rwlock_c01_w1 | 64 | 6.77 | 7.20 | 1.06 | 7.96 | 7.90 | 6.93 | 6.83 |
| rwlock_c01_w100 | 8 | 3.70 | 3.54 | 0.96 | 2.99 | 3.13 | 3.25 | 3.11 |
| rwlock_c01_w100 | 32 | 3.97 | 3.63 | 0.92 | 3.06 | 3.06 | 3.18 | 3.17 |
| rwlock_c01_w100 | 64 | 3.77 | 3.59 | 0.95 | 3.12 | 3.10 | 2.08 | 2.04 |
| rwlock_c01_w20 | 8 | 4.45 | 4.70 | 1.05 | 3.60 | 3.85 | 4.88 | 4.50 |
| rwlock_c01_w20 | 32 | 4.61 | 4.55 | 0.99 | 3.79 | 3.83 | 4.75 | 4.73 |
| rwlock_c01_w20 | 64 | 3.27 | 3.40 | 1.04 | 3.85 | 3.83 | 3.56 | 3.53 |
| rwlock_c16_w1 | 8 | 7.21 | 7.62 | 1.06 | 6.93 | 7.68 | 7.94 | 7.50 |
| rwlock_c16_w1 | 32 | 7.48 | 7.66 | 1.02 | 7.64 | 7.71 | 7.49 | 7.48 |
| rwlock_c16_w1 | 64 | 6.88 | 7.22 | 1.05 | 7.66 | 7.64 | 6.88 | 6.83 |
| rwlock_c16_w20 | 8 | 3.44 | 3.59 | 1.04 | 3.06 | 3.21 | 3.31 | 3.18 |
| rwlock_c16_w20 | 32 | 3.59 | 3.63 | 1.01 | 3.25 | 3.24 | 3.26 | 3.24 |
| rwlock_c16_w20 | 64 | 2.25 | 2.32 | 1.03 | 3.22 | 3.24 | 2.15 | 2.14 |
| rwsem_c01_w1 | 8 | 8.97 | 9.76 | 1.09 | 7.08 | 7.80 | 4.27 | 4.01 |
| rwsem_c01_w1 | 32 | 6.70 | 8.53 | 1.27 | 7.62 | 7.94 | 3.80 | 3.63 |
| rwsem_c01_w1 | 64 | 4.64 | 6.56 | 1.41 | 6.96 | 7.37 | 2.70 | 2.52 |
| rwsem_c01_w100 | 8 | 2.17 | 3.22 | 1.49 | 2.84 | 2.69 | 3.00 | 2.75 |
| rwsem_c01_w100 | 32 | 2.14 | 3.19 | 1.49 | 3.08 | 2.71 | 2.84 | 2.85 |
| rwsem_c01_w100 | 64 | 2.04 | 3.09 | 1.52 | 2.87 | 2.55 | 1.39 | 1.34 |
| rwsem_c01_w20 | 8 | 3.76 | 5.48 | 1.46 | 4.00 | 4.19 | 2.10 | 1.93 |
| rwsem_c01_w20 | 32 | 3.27 | 5.70 | 1.74 | 5.59 | 5.78 | 1.98 | 1.92 |
| rwsem_c01_w20 | 64 | 2.30 | 4.01 | 1.74 | 4.45 | 4.73 | 1.06 | 1.04 |
| rwsem_c16_w1 | 8 | 7.26 | 7.99 | 1.10 | 6.92 | 7.62 | 4.13 | 3.93 |
| rwsem_c16_w1 | 32 | 6.00 | 7.56 | 1.26 | 7.23 | 7.49 | 3.51 | 3.39 |
| rwsem_c16_w1 | 64 | 4.31 | 6.08 | 1.41 | 6.84 | 7.41 | 2.25 | 2.13 |
| rwsem_c16_w20 | 8 | 3.29 | 4.22 | 1.28 | 3.14 | 3.25 | 1.67 | 1.65 |
| rwsem_c16_w20 | 32 | 3.32 | 4.42 | 1.33 | 4.05 | 4.11 | 1.65 | 1.62 |
| rwsem_c16_w20 | 64 | 2.00 | 2.94 | 1.47 | 3.51 | 3.58 | 0.92 | 0.90 |
| spin_c01 | 8 | 4.22 | 3.66 | 0.87 | 3.69 | 3.97 | 5.64 | 5.55 |
| spin_c01 | 32 | 3.92 | 3.91 | 1.00 | 3.84 | 4.11 | 5.24 | 5.59 |
| spin_c01 | 64 | 3.74 | 3.79 | 1.01 | 3.76 | 3.97 | 3.52 | 3.68 |
| spin_c08 | 8 | 3.24 | 3.15 | 0.97 | 2.82 | 2.97 | 3.75 | 3.50 |
| spin_c08 | 32 | 3.20 | 3.31 | 1.04 | 2.75 | 3.22 | 3.78 | 3.65 |
| spin_c08 | 64 | 3.07 | 3.17 | 1.03 | 2.69 | 3.05 | 2.65 | 2.54 |

## Reading

* **Gains (sleepable class):**
  * mutex c01 is 1.17-1.54 times round 7 from 8 workers and no longer
    falls with the worker count (3.2 Mops/s at 8-32 workers, 3.1 at
    40-64). kd/TCLock went from 0.71-0.98 to 1.15-1.21 from 12 workers.
  * rwsem writers only: 1.45-1.52 times from 8 workers; kd/TCLock from
    0.69-0.83 to 1.13-1.21.
  * rwsem with 20% writes: 1.3-1.8 times from 5 workers. Across both nodes
    kd/TCLock went from 0.52-0.53 to 0.85-0.90 (c16: 0.57-0.63 to
    0.78-0.82).
  * rwsem with 1% writes: 1.2-1.4 times from 16 workers; across both nodes
    kd/TCLock from 0.63-0.80 to 0.82-0.99.
* **Boot-to-boot variation limits the kd/TCLock ratios.** Mutex c01 at
  64 workers, single points in other boots of the same source: kd
  2.62-2.67 against TCLock 2.57 (#58) and kd 2.65 against TCLock 2.82
  (#64); this grid has 3.08 against 2.55. So "kd ahead of TCLock for
  mutex c01" holds for this boot only; across boots the two are within
  about 10% of each other. The gain against round 7 (1.99 Mops/s there)
  shows in every boot.
* **Losses and open points:**
  * spin c01 is 0.87-0.95 of round 7 at 2-24 workers, and rwlock writers
    only 0.88-0.96 at 8-64, while TCLock rose 0-10% at the same points.
    The spin-class paths were not meant to change (`kd_node` gained one
    byte, and `kd_session` one branch). Not explained and not separated
    from boot-to-boot placement effects by an in-boot A/B.
  * Within one node, spin is still below Native (c01 0.66-0.80 at 6-32
    workers, c08 0.88-0.91) and rwsem writers only is 0.80-0.86 at 4-5
    workers.
  * Across both nodes kd is still behind TCLock for rwsem with readers
    (0.78-0.99), rwlock with 20% writes (0.72-0.98) and spin c01
    (0.93-0.95).
  * Past the node boundary (32 -> 40 workers) rwsem with readers still
    drops: 20% writes 5.70 -> 4.08 Mops/s (TCLock 5.78 -> 4.5), c16 4.42
    -> 2.67.

## Correctness on the same boot (before the grid)

| Check | Result |
| --- | --- |
| `run_corr.py --backends native kd tclock` (`corr61.jsonl`) | 312 points, 0 failed, API test 0 failed checks (65), 0 kernel complaints |
| `mm_stress` 4/32/63 threads x 20 s, `kd_mm=1`, then Native | all 6 runs passed |
| `api_stress` setfd/ofd/pipe/seek/xattr at 4/32/63 threads x 20 s | all passed except `setfd 63`, the fd-limit case of the test (round 7) |
| Kernel log | no warning or stall |

`corr61.txt` is the raw output.

## Defect found while checking mmap1: not caused by this change set

will-it-scale mmap1 with `kd_mm=1` (`run_mmap1.py`, threads, 4-64 workers,
Native and kd alternating) hung the VM on this host.

* **With this source** (#61, #62): 3 hangs; 9 boots with 4 and 16 threads
  only passed (134 points).
* **With the previous commit's kernel source** (`041653e4`, rebuilt as
  #63): the same recipe hung in its first run, within 120 s. So the defect
  predates this change set. mmap1 had not been run on the 64-vCPU VM
  before.
* **What the hung system shows** (all-CPU backtrace on a soft lockup):
  one mmap1 thread, the holder of the queue mutex, spins in
  `hrtimer_interrupt` on its own CPU's hrtimer base lock with interrupts
  off, and its stack does not unwind (it was interrupted off its own
  stack). Other CPUs wait in `smp_call_function_many_cond` for it, and
  the queued writers wait in `kd_wait_sleepable`.
* **Found and fixed afterwards** (#65): `../mmap1-20261115-64cpu/`.
* An in-boot comparison of the reader phase on mmap1 could not be made for
  this reason. The reader phase delays writers, so its effect on mmap1 is
  unmeasured.
