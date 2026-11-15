# Round 10: the full worker grid on 64 CPUs

The worker grid the user asked for on 2026-11-15: every count from 1 to 8, then
every fourth count to 64, for all 14 nano profiles and all three backends.
It is the data behind the comparison charts; `r10.csv` is the machine-readable
form and `r10.md` the same numbers as one table per profile.

## Identity

| | |
|---|---|
| guest | `kdclaude`, 64 vCPUs as 2 nodes of 32, 24 GiB (12 per node) |
| host | Xeon Gold 6438N, one vCPU pinned per host CPU, all 64 host CPUs fixed at 2.7 GHz (turbo on, `scaling_min_freq` = `scaling_max_freq` = 2700000, governor performance) |
| kernel | `7.0.0-38-kdclaude1` `#72 SMP PREEMPT_DYNAMIC Sun Nov 15 07:26:18 UTC 2026` |
| source | commit `b2958b0b` (the tree of `b46ac6c9` minus that commit's bench-only changes) |
| defaults | `kd_batch` 4096, `kd_vdown` 1, `kd_cldemote` 3, `kd_rwsem_rphase_ns` 1000, `kd_xchg` 1, `kd_adapt` Y, `kd_numa` Y, delegation on |
| runner | `bench/run_grid.py --rounds 2 --ms 1000 --backends native kd tclock` |
| points | 14 profiles x 22 worker counts x 3 backends x 2 rounds = 1848, 0 failed |

Worker *i* runs on CPU *i* (`run_nano`), and guest node 0 is CPUs 0-31, so 1 to
32 workers are one node and 36 to 64 span both. That is why every profile has a
step at 36: it is the first count that crosses nodes, not a scaling effect.

TCLock's own backend runs at its maximum batch of 1024; kdlock's `kd_batch` is
4096. Both are their respective maxima, so the two are compared at their best
setting, not at a shared one.

## Files

| file | content |
|---|---|
| `r10.jsonl` | one record per point: rate, identity, kdlock counter deltas |
| `r10.log` | the runner's live output |
| `r10.csv` | one row per (profile, workers): every backend's median, min, max, round count, the three ratios, failures |
| `r10.md` | the same as a markdown table per profile |

Regenerate either table with
`python3 bench/grid_table.py <path>/r10.jsonl [--format md]`.

## What the numbers say

Ahead of both references across the whole range:

| profile | kd/Native | kd/TCLock | where |
|---|---|---|---|
| `mutex_c01` | 1.20-1.22 / 1.46-2.31 | 1.13-1.22 | one node / across nodes |
| `mutex_c16` | 1.39-1.44 / 1.71-2.35 | 1.94-2.10 | |
| `spin_c01` | 0.97-1.07 / 1.32-1.65 | 1.42-1.51 | |
| `spin_c08` | 1.10-1.14 / 1.37-1.61 | 1.37-1.51 | |
| `rwlock_c01_w100` | 1.75-1.82 / 2.15-2.80 | 1.84-2.06 | |
| `rwsem_c01_w100` | 1.07-1.18 / 1.36-2.40 | 1.13-1.23 | |
| `rwsem_c16_w20` | 2.39-2.46 / 1.98-3.14 | 1.04-1.24 one node, 0.76-0.87 across | |

Behind one of them:

* **Reader-heavy rwsem across nodes.** `rwsem_c01_w1` 2.06-2.46x Native but
  0.60-0.75 of TCLock from 28 workers up; `rwsem_c16_w1` the same shape
  (0.70-0.84). kdlock admits readers outside the combiner, TCLock runs them
  through it; across nodes that costs more than it saves.
* **`rwlock` with readers.** `rwlock_c01_w1` and `rwlock_c16_w1` sit at
  0.96-1.21 of Native and fall to 0.86-0.91 of TCLock across nodes;
  `rwlock_c16_w20` 1.01-1.13 of Native but 0.65-0.75 of TCLock there.
  `rwlock_c01_w20` is the one profile below Native throughout (0.87-0.95).
* **Three workers.** `mutex_c01` 0.94, `rwlock_c01_w100` 0.88,
  `rwsem_c01_w100` 0.96. Three is where the queue is long enough to leave the
  uncontended path and too short for a session to pay for itself.

Native's own collapse across nodes (`mutex_c01` 3.12 -> 1.55 Mops from 32 to 64
workers) is what most of the large kd/Native ratios above 36 workers are made
of; kdlock's own rate is flat there (3.75 -> 3.58).
