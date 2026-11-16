# Round 12: the full grid with eras, as committed

The grid of rounds 10 and 11 (1 to 8 workers one by one, then every fourth
to 64; 14 profiles; Native, kd, TCLock; 2 rounds) on the build in which the
reader-writer families serve one NUMA node at a time under pressure
(`kernel/kd_era.c`, ARCHITECTURE 7b) and the rwsem's reader fast path no
longer looks at the era. The road here, with every rejected step, is in
[`../era-20261115-64cpu/`](../era-20261115-64cpu/README.md).

## Identity

| | |
|---|---|
| guest, host | as round 10: `kdclaude`, 64 vCPUs as 2 nodes of 32, host fixed at 2.7 GHz |
| kernel | `7.0.0-38-kdclaude1` `#82 SMP PREEMPT_DYNAMIC Mon Nov 16 01:37:01 UTC 2026` |
| source | commit `9ac62b01` |
| defaults | as round 10, plus `kd_rw_era_ns` 200000, `kd_rw_era_press` 225, `kd_rw_era_drain_ns` 5000, `kd_numa_after` 32 |
| runner | `bench/run_grid.py --rounds 2 --ms 1000 --backends native kd tclock` |
| points | 1848, 0 failed; kernel log clean; correctness pass on the same boot (era directory, section 5) |

`r12.csv` (for plotting) and `r12.md` are the tables
(`bench/grid_table.py`); `r12.jsonl` and `r12.log` the raw points.

Rounds are different builds and boots. Ratios against Native and TCLock,
which ran in the same boot each time, can be set side by side; absolute
rates of two rounds are shown here only for kd's own shape over the worker
count.

## Across nodes (36 to 64 workers)

kd's own rate in Mops/s at the last one-node count, the first count that
crosses, and all 64:

| profile | r10: 32 / 36 / 64 | r12: 32 / 36 / 64 | TCLock r12: 32 / 36 / 64 |
|---|---|---|---|
| `rwlock_c01_w20` | 6.44 / 5.36 / 4.57 | 6.31 / **6.47 / 6.14** | 5.07 / 5.02 / 5.01 |
| `rwlock_c16_w20` | 4.53 / 3.38 / 2.60 | 4.43 / **4.35 / 4.29** | 4.09 / 4.00 / 4.01 |
| `rwlock_c01_w1` | 14.50 / 12.44 / 11.94 | 14.54 / **14.07 / 13.76** | 14.11 / 13.95 / 13.81 |
| `rwlock_c16_w1` | 11.86 / 9.94 / 9.69 | 12.06 / **11.51 / 11.20** | 11.54 / 11.30 / 11.32 |
| `rwsem_c01_w20` | 6.85 / 4.95 / 4.51 | 6.91 / **6.76 / 6.30** | 7.51 / 5.80 / 5.83 |
| `rwsem_c16_w20` | 5.31 / 3.34 / 3.55 | 5.33 / **4.95 / 4.71** | 5.04 / 4.02 / 4.09 |
| `rwsem_c01_w1` | 10.31 / 8.23 / 7.61 | 10.44 / **10.19 / 9.76** | 13.86 / 11.94 / 12.10 |
| `rwsem_c16_w1` | 9.52 / 7.61 / 7.41 | 9.57 / **9.20 / 8.96** | 11.63 / 9.88 / 10.41 |
| `mutex_c01` | 3.75 / 3.68 / 3.58 | 3.76 / 3.70 / 3.56 | 3.12 / 3.08 / 3.04 |
| `spin_c01` | 6.84 / 6.74 / 6.58 | 6.71 / 6.60 / 6.54 | 4.82 / 4.69 / 4.65 |

The step at 36 workers is gone from the rw families. From 32 to 64 workers
they now lose 3-12%; in round 10 they lost 18-43%, against 3-6% for the
mutex and the spinlock.

Ratios over the whole range on each side of the boundary; round 10 in
brackets:

| profile | kd/Native 8-32 | kd/Native 36-64 | kd/TCLock 8-32 | kd/TCLock 36-64 |
|---|---|---|---|---|
| `mutex_c01` | 1.16-1.20 | 1.45-2.28 | 1.18-1.22 (1.16-1.22) | 1.17-1.20 (1.13-1.21) |
| `mutex_c16` | 1.35-1.42 | 1.77-2.33 | 1.95-2.10 (2.03-2.10) | 1.92-2.03 (1.94-2.02) |
| `spin_c01` | 0.93-0.97 | 1.35-1.76 | 1.36-1.44 (1.42-1.51) | 1.41-1.43 (1.46-1.48) |
| `spin_c08` | 1.02-1.12 | 1.42-1.82 | 1.38-1.44 (1.37-1.42) | 1.43-1.47 (1.44-1.51) |
| `rwlock_c01_w100` | 1.35-1.76 | 2.13-2.83 | 1.50-1.94 (1.53-2.06) | 1.82-1.90 (1.84-1.90) |
| `rwsem_c01_w100` | 1.13-1.28 | 1.45-2.37 | 1.17-1.22 (1.17-1.21) | 1.16-1.20 (1.13-1.23) |
| `rwlock_c01_w20` | 0.89-0.95 | 1.10-1.24 | 1.24-1.30 (1.29-1.33) | **1.23-1.29** (0.91-1.08) |
| `rwlock_c16_w20` | 1.09-1.11 | 1.38-1.69 | 1.08-1.15 (1.12-1.18) | **1.06-1.09** (0.65-0.86) |
| `rwlock_c01_w1` | 0.99-1.23 | 1.10-1.18 | 1.03-1.29 (1.05-1.33) | **0.99-1.04** (0.88-0.91) |
| `rwlock_c16_w1` | 1.03-1.12 | 1.12-1.16 | 1.05-1.17 (1.03-1.10) | **0.99-1.02** (0.86-0.89) |
| `rwsem_c01_w20` | 2.68-2.80 | 3.57-5.37 | 0.92-1.14 (0.91-1.12) | **1.08-1.16** (0.77-0.84) |
| `rwsem_c16_w20` | 2.34-2.49 | 3.00-4.68 | 1.06-1.24 (1.04-1.22) | **1.15-1.24** (0.76-0.87) |
| `rwsem_c01_w1` | 2.11-2.57 | 2.59-2.95 | 0.75-0.91 (0.75-0.87) | **0.79-0.89** (0.60-0.69) |
| `rwsem_c16_w1` | 2.09-2.37 | 2.80-3.40 | 0.82-0.93 (0.82-0.92) | **0.84-0.93** (0.70-0.79) |

Across nodes kd is at or ahead of TCLock in twelve of the fourteen profiles;
round 10 had six. Within one node the ratios are those of round 10: eras
hold nobody back there.

## One node (8 to 32 workers): nothing lost

kd's own rate, round 12 over round 10, is 0.96-1.05 in every profile, and
1.00-1.03 for the rwsem with readers. Round 11 had the rwsem profiles with
readers at 0.80-1.01 of round 10 there; build #81 traced that to a check in
the reader fast path, which this build no longer has (era directory,
section 4).

## Still behind

* **The rwsem with 1% writes against TCLock**: 0.79-0.89 on one line and
  0.84-0.93 on sixteen across nodes, 0.75-0.91 and 0.82-0.93 within one. It
  is the same margin on both sides of the boundary, so it is not about nodes
  any more. TCLock's rwsem keeps the reader count, the reader wait lock and
  the writer queue in separate 128-byte blocks (over 500 bytes in all);
  kdlock's must fit the 40 bytes of a `struct rw_semaphore`, and its readers
  and writers share one line.
* **`rwlock_c01_w20` on one node** stays under Native (0.89-0.95), as in
  round 10: every queued reader ends the writer session there.
* **`spin_c01` on one node** is 0.93-0.97 of Native at 5 to 32 workers
  (round 10: 0.89-1.09). The spinlock code did not change; the two rounds
  differ in Native's rate, not kd's (kd 0.98-0.99 of round 10).
* **Three and four workers**, where a queue first forms: `mutex_c01` 0.83 at
  3 (round 10: 0.94, round 11: 0.56; the mutex code is the same in all
  three, the point is unstable), `rwsem_c01_w100` 0.83-0.87 at 4-5,
  `rwlock_c01_w100` 0.87-0.95 at 3-4, `rwlock_c01_w20` 0.85-0.91 at 4-8.
