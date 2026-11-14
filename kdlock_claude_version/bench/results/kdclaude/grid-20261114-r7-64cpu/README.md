# Round 7: 64 vCPUs on 10.176.26.71 (build #56)

## Setup

* **Host:** the kdclaude VM was moved on 2026-11-14 from 380G10 to
  10.176.26.71, a 2-socket Xeon Gold 6438N host with 64 CPUs. The user had
  stopped the other VM on that host first.
* **Disks:** the qcow2 images were copied with matching SHA-256.
* **VM shape:** 64 vCPUs as 2 sockets x 32, one vCPU pinned per host CPU.
  Guest NUMA node 0 is CPUs 0-31 on host node 0, node 1 is CPUs 32-63 on
  host node 1. 24 GiB, 12 GiB bound per node.
* **Not comparable with earlier rounds:** rounds 1-6 ran on 380G10 with
  32 vCPUs as 2 x 16. Do not pool them with this round.
* **Kernel:** `7.0.0-38-kdclaude1` build #56.
* **Source:** commit `94b3e96e` plus the uncommitted Task C changes. These
  are rwsem reader admission outside `->m`, look-before-add on the read fast
  path, `kd_family.numa_after` (32 for rwsem) and `kd_rwsem_is_contended`
  counting readers behind a writer. They are committed together with this
  directory.
* **Source identity in the data:** the target's tree is a synced copy
  without `.git`, so `run_grid.py` takes it from `KD_COMMIT=94b3e96ea093`
  and `KD_DIRTY=1`.
* **Defaults:** `kd_adapt=1`, `kd_xchg=1`, `kd_numa=1`,
  `kd_rwsem_rspin_ns=50000`, `kd_rwsem_wspin_ns=50000`.
* **Daemon:** running and warmed before the grid (`delegation 1`). A
  watcher confirmed it stayed up for the whole grid.
* **Run:** `run_grid.py`, 14 profiles (the 12 default profiles plus
  `rwsem_c01_w100` and `rwlock_c01_w100`). Worker counts 1-8, 12-32 in
  steps of 4, and 40, 48, 56, 64. Native, kd and TCLock alternate per
  point; 2 rounds of 1 s; 1512 points.
* **Results:** no point failed its data oracle. The kernel log shows nothing
  besides the boot-time split-lock notice. `summary.txt` has the per-point
  table, with medians over the 2 rounds; two rounds give no variance claim.

**Placement.** `run_nano` puts worker *i* on CPU *i*. Up to 32 workers
therefore run on node 0 only; 40-64 workers span both nodes. The cross-node
region of earlier rounds (20-32 workers on 380G10) corresponds to 40-64
here.

## kd/Native and kd/TCLock, ranges per region

Ranges are of per-point medians.

| Profile | 2-5 kd/Nat | 6-8 kd/Nat | 12-32 kd/Nat | 40-64 kd/Nat | 2-5 kd/TC | 6-8 kd/TC | 12-32 kd/TC | 40-64 kd/TC |
|---|---|---|---|---|---|---|---|---|
| mutex_c01 | 1.00-1.17 | 0.87-1.05 | 0.84-0.91 | 1.13-1.36 | 1.00-1.68 | 0.96-1.50 | 0.81-0.98 | 0.71-0.83 |
| mutex_c16 | 0.90-1.00 | 1.09-1.24 | 1.23-1.24 | 1.46-1.71 | 0.95-1.36 | 1.49-1.65 | 1.62-1.68 | 1.48-1.59 |
| rwlock_c01_w1 | 0.94-1.00 | 0.90-0.91 | 0.93-1.00 | 0.97-0.98 | 1.00-1.01 | 1.04-1.05 | 0.98-1.05 | 0.85-0.88 |
| rwlock_c01_w100 | 0.86-1.00 | 1.00-1.14 | 1.24-1.26 | 1.58-1.83 | 0.99-1.13 | 1.10-1.24 | 1.30-1.38 | 1.21-1.25 |
| rwlock_c01_w20 | 0.71-1.00 | 0.74-0.91 | 0.92-0.97 | 0.89-0.92 | 0.96-1.22 | 1.24-1.28 | 1.21-1.23 | 0.85-0.93 |
| rwlock_c16_w1 | 0.96-1.00 | 0.91-0.93 | 0.92-1.00 | 0.97-1.00 | 0.99-1.03 | 1.04-1.06 | 0.97-1.04 | 0.89-0.91 |
| rwlock_c16_w20 | 0.96-0.99 | 1.03-1.04 | 1.03-1.10 | 1.04-1.04 | 0.99-1.13 | 1.12-1.16 | 1.06-1.11 | 0.69-0.78 |
| rwsem_c01_w1 | 1.00-1.39 | 1.54-2.10 | 1.76-2.05 | 1.64-1.72 | 1.00-1.09 | 1.15-1.27 | 0.88-1.25 | 0.67-0.80 |
| rwsem_c01_w100 | 0.70-1.00 | 0.72-0.73 | 0.73-0.75 | 1.05-1.46 | 0.98-1.05 | 0.76-1.10 | 0.69-0.83 | 0.70-0.75 |
| rwsem_c01_w20 | 0.98-2.74 | 1.80-1.98 | 1.60-1.68 | 1.97-2.27 | 0.98-1.06 | 0.94-1.06 | 0.58-0.79 | 0.52-0.53 |
| rwsem_c16_w1 | 1.02-1.32 | 1.37-1.76 | 1.67-1.77 | 1.70-1.91 | 0.95-1.08 | 0.92-1.05 | 0.83-1.06 | 0.63-0.71 |
| rwsem_c16_w20 | 1.30-2.05 | 1.92-1.97 | 1.97-2.01 | 2.16-2.34 | 0.99-1.16 | 1.05-1.08 | 0.82-0.95 | 0.57-0.63 |
| spin_c01 | 0.92-1.05 | 0.75-0.80 | 0.73-0.75 | 1.03-1.09 | 1.17-1.88 | 1.14-1.54 | 1.02-1.10 | 1.00-1.05 |
| spin_c08 | 0.91-1.00 | 0.86-0.89 | 0.83-0.86 | 1.11-1.19 | 1.11-1.52 | 1.15-1.28 | 1.15-1.16 | 1.14-1.15 |

## Reading

* **Across both nodes (40-64 workers), against TCLock:**
  * rwsem is still far behind, which is the Task C target. kd/TCLock is
    0.52-0.53 with 20% writes, 0.57-0.63 for c16 with 20% writes,
    0.63-0.80 with 1% writes and 0.70-0.75 writers only.
  * rwlock with writers is behind: 0.69-0.93.
  * mutex c01 is behind: 0.71-0.83.
  * kd is ahead for mutex c16 (1.48-1.59), rwlock writers only (1.21-1.25)
    and spin c08 (1.14).
* **Within one node (6-32 workers), against Native:**
  * Delegation loses for the spinlock (spin c01 0.73-0.80, c08 0.83-0.89),
    for the mutex with c01 (0.84-0.91 from 8 workers) and for rwsem
    writers only (0.72-0.75).
  * On 380G10, 12-16 workers were also on one node, and spin there was at
    or above Native (round 5: 1.22). That comparison crosses hosts and only
    marks the question; it is not a finding. These are losses on this host
    that the earlier host did not show, and they are open.
* **Native collapses** at the node boundary (32 -> 40 workers) for every
  writer-heavy profile, while kd stays nearly flat. kd/Native above 1 at
  40-64 is mostly that collapse.
* **rwsem w20 against Native:** kd is 1.6-2.7 everywhere from 4 workers on
  (reader admission and delegation). TCLock is higher still from 12
  workers.

## Correctness on the same boot

After the grid, with the daemon still running:

| Check | Result |
| --- | --- |
| `run_corr.py --backends native kd tclock` (`corr56.jsonl`) | 312 points, 0 failed, API test 0 failed checks (65), 0 kernel complaints |
| `mm_stress` 4/32/63 threads x 20 s, `kd_mm=1`, then the Native control | all 6 runs passed |
| `api_stress` ofd/pipe/seek/xattr at 4/32/63 threads x 20 s, kd | all passed; ofd 53-56 M, pipe 3.3-4.6 M delegated sections at 32/63 |
| `api_stress` setfd at 4/32 threads | passed; 75 M delegated sections at 32 |
| `api_stress setfd 63` | **fails with EMFILE** at the default `ulimit -n 1024`, under Native as well: 63 threads x 16 fds plus a `dup()` each exceed 1024. That is a limit of the test, not a lock failure. With `ulimit -n 4096`, kd passes (76 M delegated sections) and Native passes |
| Kernel log | no warning, stall or lock complaint; only the boot split-lock notice and apparmor denials of `who` |

`seek` and `xattr` showed no delegation (0 sections) at any thread count on this
host either.
