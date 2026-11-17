# Round 11: the full grid with eras

The grid of round 10 (1 to 8 workers one by one, then every fourth to 64; 14
profiles; Native, kd, TCLock; 2 rounds) on the first build that serves the
reader-writer families one NUMA node at a time under pressure
(`kernel/kd_era.c`, ARCHITECTURE 7b). What led to that change is in
[`../era-20261115-64cpu/`](../era-20261115-64cpu/README.md).

## Identity

| | |
|---|---|
| guest, host | as round 10: `kdclaude`, 64 vCPUs as 2 nodes of 32, host fixed at 2.7 GHz |
| kernel | `7.0.0-38-kdclaude1` `#80 SMP PREEMPT_DYNAMIC Sun Nov 15 20:30:43 UTC 2026` |
| source | commit `72fd7552` |
| defaults | as round 10, plus `kd_rw_era_ns` 200000, `kd_rw_era_press` 225, `kd_rw_era_drain_ns` 5000, `kd_rw_era_min` 2, `kd_numa_after` 32 |
| runner | `bench/run_grid.py --rounds 2 --ms 1000 --backends native kd tclock` |
| points | 1848, 0 failed; kernel log clean; correctness pass on the same boot in the era directory |

`r11.csv` and `r11.md` are the tables (`bench/grid_table.py`); `r11.jsonl`
and `r11.log` the raw points.

Rounds 10 and 11 are different builds and boots. Their ratios against Native
and TCLock, which ran in the same boot each time, can be set side by side;
absolute rates of the two rounds should not be.

## Across nodes (36 to 64 workers)

This is what the change was for. kd's own rate, in Mops/s, at the last
one-node count, the first count that crosses, and all 64:

| profile | r10: 32 / 36 / 64 | r11: 32 / 36 / 64 | TCLock r11: 32 / 36 / 64 |
|---|---|---|---|
| `rwlock_c01_w20` | 6.44 / 5.36 / 4.57 | 6.30 / **6.54 / 6.11** | 4.96 / 4.90 / 5.02 |
| `rwlock_c16_w20` | 4.53 / 3.38 / 2.60 | 4.40 / **4.30 / 4.22** | 3.98 / 3.89 / 3.97 |
| `rwlock_c01_w1` | 14.50 / 12.44 / 11.94 | 14.36 / **13.97 / 13.49** | 13.56 / 13.46 / 13.67 |
| `rwlock_c16_w1` | 11.86 / 9.94 / 9.69 | 11.84 / **11.20 / 10.93** | 11.66 / 11.48 / 11.45 |
| `rwsem_c01_w20` | 6.85 / 4.95 / 4.51 | 6.63 / **6.65 / 6.15** | 7.63 / 5.86 / 5.90 |
| `rwsem_c16_w20` | 5.31 / 3.34 / 3.55 | 5.25 / **4.99 / 4.72** | 5.14 / 4.08 / 4.14 |
| `rwsem_c01_w1` | 10.31 / 8.23 / 7.61 | 10.03 / **9.83 / 9.61** | 14.42 / 12.16 / 12.66 |
| `rwsem_c16_w1` | 9.52 / 7.61 / 7.41 | 9.42 / **9.20 / 8.97** | 11.69 / 9.67 / 10.60 |
| `mutex_c01` | 3.75 / 3.68 / 3.58 | 3.77 / 3.71 / 3.57 | 3.17 / 3.09 / 3.01 |
| `spin_c01` | 6.84 / 6.74 / 6.58 | 6.79 / 6.66 / 6.66 | 4.97 / 4.79 / 4.76 |

The step at 36 workers is gone from the rw families: they now lose 3-10%
from 32 to 64 workers, where they lost 18-43%. The rwsem keeps its rate
across the boundary better than TCLock's does.

Ratios over the whole range of each side of the boundary:

| profile | kd/Native 8-32 | kd/Native 36-64 | kd/TCLock 8-32 | kd/TCLock 36-64 (r10) |
|---|---|---|---|---|
| `mutex_c01` | 1.05-1.11 | 1.36-2.23 | 1.19-1.25 | 1.18-1.20 (1.13-1.21) |
| `mutex_c16` | 1.36-1.43 | 1.68-2.30 | 2.05-2.14 | 1.94-2.06 (1.94-2.02) |
| `spin_c01` | 0.92-0.99 | 1.39-1.74 | 1.37-1.45 | 1.39-1.45 (1.46-1.48) |
| `spin_c08` | 1.01-1.11 | 1.41-1.81 | 1.34-1.42 | 1.41-1.43 (1.44-1.51) |
| `rwlock_c01_w100` | 1.23-1.81 | 2.16-2.84 | 1.43-2.09 | 1.84-1.93 (1.84-1.90) |
| `rwsem_c01_w100` | 1.06-1.15 | 1.39-2.37 | 1.19-1.23 | 1.17-1.21 (1.13-1.23) |
| `rwlock_c01_w20` | 0.92-0.94 | 1.14-1.22 | 1.27-1.31 | **1.21-1.33** (0.91-1.08) |
| `rwlock_c16_w20` | 1.02-1.09 | 1.35-1.63 | 1.09-1.12 | **1.03-1.11** (0.65-0.86) |
| `rwlock_c01_w1` | 0.99-1.20 | 1.10-1.15 | 1.06-1.34 | **0.99-1.06** (0.88-0.91) |
| `rwlock_c16_w1` | 0.92-1.04 | 1.10-1.13 | 0.99-1.15 | **0.95-0.98** (0.86-0.89) |
| `rwsem_c01_w20` | 2.46-2.66 | 3.43-5.14 | 0.87-1.08 | **1.04-1.14** (0.77-0.84) |
| `rwsem_c16_w20` | 2.29-2.46 | 3.00-4.70 | 1.02-1.23 | **1.14-1.24** (0.76-0.87) |
| `rwsem_c01_w1` | 1.96-2.08 | 2.45-2.85 | 0.66-0.75 | **0.76-0.86** (0.60-0.69) |
| `rwsem_c16_w1` | 1.86-2.25 | 2.72-3.27 | 0.81-0.90 | **0.85-0.95** (0.70-0.79) |

Across nodes kd is now at or ahead of TCLock in eleven of the fourteen
profiles and within 5% in a twelfth (`rwlock_c16_w1`). Round 10 had six.

## Still behind

* **The rwsem with 1% writes against TCLock**: 0.76-0.86 on one line and
  0.85-0.95 on sixteen across nodes, 0.66-0.75 and 0.81-0.90 within one. This
  is not about nodes any more: TCLock's rwsem is ahead by the same margin on
  one node. Its object keeps the reader count, the reader wait lock and the
  writer queue in separate 128-byte blocks (over 500 bytes in all); kdlock's
  must fit the 40 bytes of a `struct rw_semaphore`, and its readers and
  writers share one line.
* **`rwlock_c01_w20` on one node** stays under Native (0.92-0.94), as in
  round 10: every queued reader ends the writer session there.

## One node: what this build still had wrong

kd's own rate at 8 to 32 workers, round 11 over round 10:

| profiles | r11 / r10 |
|---|---|
| mutex, spin, writers only | 0.96-1.04 |
| rwlock with readers | 0.93-1.06 |
| `rwsem_c16_w1`, `rwsem_c16_w20` | 0.96-1.01 |
| `rwsem_c01_w20` | 0.93-0.97 |
| `rwsem_c01_w1` | 0.80-0.87 at 8-16 workers, 0.93-0.97 at 20-32 |

Two rounds are two boots, and this comparison alone would not have been
evidence. It was followed up because only the profiles with readers were
lower. Build #81 measured the cause within one boot
(`../era-20261115-64cpu/README.md`, section 4): the rwsem's reader fast path
checked the era word whenever two readers were in, which cost 3-12% of every
read section on one node and gained nothing across nodes. The check was
removed in the next commit, and round 12 is the grid of that state. Read the
rwsem rows of this round with that in mind; the rwlock, mutex and spinlock
code is the same in rounds 11 and 12.

`mutex_c01` at 3 workers is 0.56 of Native in this round (4.39 against
7.82 Mops/s; round 10 had 0.94, round 9 0.89). The mutex code did not change.
Three workers is where the queue first forms; the point has been unstable in
every round and stays on the list in PERF_PLAN.
