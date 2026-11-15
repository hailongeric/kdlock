# Round 6 (380G10, build #56)

## Setup

* **Host and VM:** 380G10, 32 vCPUs as 2 x 16 (guest node 0 = CPUs 0-15).
* **Kernel:** `7.0.0-38-kdclaude1` build #56.
* **Source:** commit `94b3e96e` plus the Task C rwsem changes that are
  committed together with this directory (DIFFERENCES D11).
* **Run:** `run_grid.py`, 10 profiles (rwsem x5 including writers only,
  rwlock x4, mutex c01), 14 worker counts, Native, kd and TCLock
  alternating per point, 2 rounds, 840 points.
* **Results:** no failed point. `summary.txt` has the per-point medians.

## Files

* **`r6.jsonl`:** the valid round, with the daemon running.
* **`nodaemon.jsonl`:** the same grid on the same boot, run first, while
  the translator daemon was not running (a stale pid check; `load3.sh`
  fixed). Every kd point there is 0% delegated, so it is a control for "kd
  without delegation", not a kd result. Example at 32 workers: mutex c01
  1.99 Mops without the daemon and 3.46 with it; rwsem writers only 2.04
  and 4.02.

## kd/Native and kd/TCLock, ranges per region

Workers 20-32 span both nodes.

| Profile | 2-5 kd/Nat | 6-8 kd/Nat | 12-16 kd/Nat | 20-32 kd/Nat | 2-5 kd/TC | 6-8 kd/TC | 12-16 kd/TC | 20-32 kd/TC |
|---|---|---|---|---|---|---|---|---|
| mutex_c01 | 1.01-1.05 | 1.03-1.08 | 1.17-1.17 | 1.58-2.51 | 0.91-1.58 | 1.02-1.10 | 0.81-0.82 | 0.73-0.79 |
| rwlock_c01_w1 | 0.98-1.00 | 0.91-0.94 | 0.97-0.99 | 0.97-0.99 | 0.98-1.00 | 0.94-0.95 | 1.00-1.00 | 1.00-1.02 |
| rwlock_c01_w20 | 0.92-1.00 | 0.98-0.99 | 0.99-1.00 | 1.01-1.02 | 0.95-1.06 | 1.08-1.12 | 0.99-1.01 | 0.74-0.81 |
| rwlock_c16_w1 | 1.00-1.06 | 1.05-1.08 | 1.08-1.08 | 1.19-1.25 | 0.97-1.00 | 0.98-1.00 | 1.00-1.01 | 0.96-1.01 |
| rwlock_c16_w20 | 1.01-1.09 | 1.10-1.12 | 1.13-1.13 | 1.17-1.19 | 0.95-1.05 | 1.07-1.09 | 0.98-0.99 | 0.61-0.69 |
| rwsem_c01_w1 | 0.92-1.48 | 2.33-2.79 | 2.72-2.74 | 2.44-3.29 | 0.90-0.94 | 1.02-1.19 | 1.16-1.18 | 0.72-0.83 |
| rwsem_c01_w100 | 0.75-1.01 | 1.16-1.38 | 1.47-1.49 | 2.01-3.00 | 0.90-1.14 | 1.17-1.28 | 0.93-0.96 | 0.84-0.88 |
| rwsem_c01_w20 | 0.94-2.30 | 1.99-2.10 | 4.26-4.98 | 3.55-4.22 | 0.91-1.18 | 0.95-1.12 | 0.71-0.78 | 0.55-0.58 |
| rwsem_c16_w1 | 0.95-1.11 | 1.53-1.70 | 1.66-1.69 | 1.90-2.43 | 0.72-0.92 | 0.77-0.80 | 0.80-0.80 | 0.68-0.76 |
| rwsem_c16_w20 | 1.27-2.08 | 2.03-2.08 | 4.10-4.73 | 3.24-3.87 | 0.93-1.08 | 0.96-1.06 | 0.78-0.84 | 0.60-0.64 |

## Against round 5 (same host, build #39)

kd Mops/s, medians. Different builds, so this is a before/after of the
change set, not a pooled result. TCLock and Native are shown to separate
host drift from code effects.

| Profile | n | r5 kd | r6 kd | r6/r5 | r5 TCLock | r6 TCLock | r5 Native | r6 Native |
|---|---|---|---|---|---|---|---|---|
| rwsem_c01_w20 | 8 | 3.73 | 4.49 | 1.20 | 4.82 | 4.73 | 2.37 | 2.26 |
| rwsem_c01_w20 | 16 | 2.95 | 4.05 | 1.37 | 5.82 | 5.69 | 0.80 | 0.81 |
| rwsem_c01_w20 | 20 | 1.30 | 2.20 | 1.69 | 4.07 | 4.02 | 0.61 | 0.62 |
| rwsem_c01_w20 | 32 | 1.02 | 2.38 | 2.34 | 4.32 | 4.24 | 0.57 | 0.57 |
| rwsem_c16_w20 | 16 | 2.67 | 3.50 | 1.31 | 4.51 | 4.48 | 0.72 | 0.74 |
| rwsem_c16_w20 | 32 | 0.84 | 1.93 | 2.29 | 3.17 | 3.24 | 0.53 | 0.52 |
| rwsem_c01_w1 | 4 | 9.36 | 8.68 | 0.93 | 9.26 | 9.21 | 8.64 | 8.14 |
| rwsem_c01_w1 | 16 | 7.84 | 10.05 | 1.28 | 8.96 | 8.70 | 3.73 | 3.70 |
| rwsem_c01_w1 | 32 | 4.87 | 5.31 | 1.09 | 7.39 | 7.35 | 1.67 | 1.65 |
| rwsem_c16_w1 | 4 | 7.92 | 6.44 | 0.81 | 7.78 | 7.76 | 6.86 | 6.77 |
| rwsem_c16_w1 | 8 | 8.06 | 6.47 | 0.80 | 8.25 | 8.07 | 3.92 | 3.81 |
| rwsem_c16_w1 | 16 | 6.94 | 6.04 | 0.87 | 7.55 | 7.51 | 3.56 | 3.59 |
| rwsem_c16_w1 | 32 | 4.11 | 3.87 | 0.94 | 5.77 | 5.32 | 1.62 | 1.59 |
| mutex_c01 | 16 | 4.34 | 3.85 | 0.89 | 5.16 | 4.77 | 3.31 | 3.29 |
| mutex_c01 | 32 | 3.76 | 3.46 | 0.92 | 5.06 | 4.77 | 1.37 | 1.38 |
| rwlock_c16_w20 | 32 | 2.43 | 2.32 | 0.96 | 3.81 | 3.78 | 2.07 | 1.96 |

* **Gain:** rwsem with 20% writes, 1.2-2.3 times round 5 from 8
  workers. Across both nodes kd/TCLock rose from 0.23-0.38 to 0.55-0.64.
* **Loss:** rwsem c16 with 1% writes, 0.80-0.94 of round 5 at 4-32
  workers, while TCLock and Native stayed flat there. This is a regression
  of the change set and is not yet explained. rwsem c01 with 1% writes is
  also lower at 4 workers (0.93).
* **mutex c01 and rwlock** are 1-11% lower. Their code paths did not
  change (`numa_after` is 0 for them), and TCLock moved by up to -8% at the
  same mutex points, so host drift is the likelier cause. It is not
  separated.
