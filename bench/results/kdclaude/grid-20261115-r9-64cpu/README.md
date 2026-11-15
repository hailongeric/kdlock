# Round 9: 2.7 GHz, site lines split, longer sessions (64 vCPUs, build #70)

## Setup

* **Host and VM:** as rounds 7 and 8 (10.176.26.71, 64 vCPUs as 2 x 32,
  workers 1-32 on node 0, 40-64 across both nodes).
* **Host frequency:** turbo on and every CPU fixed at 2.7 GHz, the
  all-core turbo limit (BUILD_AND_TEST 1); 2699 MHz measured with 64 busy
  CPUs. Rounds 7 and 8 ran at 2.0 GHz with turbo off. **Not comparable
  with them in absolute numbers**, and not in ratios either: the
  reader-heavy profiles scale by more than the frequency ratio (TCLock
  rwsem 1% writes at 32 workers 7.94 -> 13.80 Mops/s, 1.74 times for 1.35
  times the frequency), the writer-only ones by less.
* **Kernel:** `7.0.0-38-kdclaude1` build #70, commit `ee5db2c5`.
* **Changes against round 8:**
  * `struct kd_site` is two cache lines (ARCHITECTURE 3). Before, each
    site ran at one of two rates per boot.
  * `kd_batch` 4096 (was 1024). **The TCLock backend runs with 1024**, its
    maximum, so kd's sessions are up to four times as long as TCLock's
    here. `../tune-20261115-2700MHz/batch68_b68.summary.txt` has kd at
    1024 against 4096 in one boot: across nodes (64 workers) 4096 is
    1.2-5.1% higher, within one node the same.
  * `kd_cldemote` 3: queued spin-class waiters demote their packet and
    stack top.
  * `kd_vdown` 1 (no effect on these profiles: no downgrade).
  * Executor interrupts stay off across a handback until the resume
    (`6c1618b6`), and a single rwsem reader gets no reader phase.
  * The translator daemon started without stored knowledge.
* **Defaults:** `kd_adapt=1`, `kd_xchg=1`, `kd_numa=1`,
  `kd_rwsem_rphase_ns=1000`, `kd_rwsem_rspin_ns=50000`.
* **Run:** as rounds 7 and 8: 14 profiles, 18 worker counts, Native, kd
  and TCLock alternating per point, 2 rounds of 1 s, 1512 points. No point
  failed its data oracle; the daemon was up at the end; no kernel
  complaint. `summary.txt` has the per-point medians.

## Two boots of the same build

kd Mops/s, medians of 3 rounds: the first boot of #70
(`../tune-20261115-2700MHz/dem70_b70.summary.txt`, column `kd_cldemote=3`),
the second boot before the grid (`boot2.jsonl`), and the grid itself. The
largest difference between the two boots is 2.2%. Before the site split
the same comparison gave 6.4 against 4.4 for spin c01 at 32 workers.

| Profile | Workers | boot 1 | boot 2 | grid (boot 2) |
|---|---|---|---|---|
| mutex_c01 | 8 | 3.76 | 3.75 | 3.76 |
| mutex_c01 | 32 | 3.83 | 3.83 | 3.82 |
| mutex_c01 | 64 | 3.65 | 3.64 | 3.66 |
| mutex_c16 | 8 | 3.56 | 3.59 | 3.50 |
| mutex_c16 | 32 | 3.69 | 3.68 | 3.68 |
| mutex_c16 | 64 | 3.50 | 3.53 | 3.54 |
| rwlock_c01_w100 | 8 | 5.12 | 5.13 | 5.16 |
| rwlock_c01_w100 | 32 | 6.44 | 6.42 | 6.41 |
| rwlock_c01_w100 | 64 | 6.43 | 6.40 | 6.37 |
| rwlock_c01_w20 | 8 | 6.47 | 6.32 | 6.31 |
| rwlock_c01_w20 | 32 | 6.35 | 6.37 | 6.37 |
| rwlock_c01_w20 | 64 | 4.61 | 4.55 | 4.56 |
| rwsem_c01_w100 | 8 | 3.79 | 3.75 | 3.78 |
| rwsem_c01_w100 | 32 | 3.85 | 3.82 | 3.83 |
| rwsem_c01_w100 | 64 | 3.71 | 3.69 | 3.71 |
| rwsem_c01_w20 | 8 | 7.02 | 6.96 | 6.95 |
| rwsem_c01_w20 | 32 | 7.11 | 6.97 | 6.96 |
| rwsem_c01_w20 | 64 | 4.60 | 4.60 | 4.59 |
| spin_c01 | 8 | 6.05 | 5.96 | 5.88 |
| spin_c01 | 32 | 6.45 | 6.43 | 6.43 |
| spin_c01 | 64 | 6.43 | 6.37 | 6.35 |
| spin_c08 | 8 | 4.57 | 4.67 | 4.77 |
| spin_c08 | 32 | 4.84 | 4.87 | 4.87 |
| spin_c08 | 64 | 4.80 | 4.81 | 4.83 |

## kd/Native and kd/TCLock, ranges per region

| Profile | 2-5 kd/Nat | 6-8 kd/Nat | 12-32 kd/Nat | 40-64 kd/Nat | 2-5 kd/TC | 6-8 kd/TC | 12-32 kd/TC | 40-64 kd/TC |
|---|---|---|---|---|---|---|---|---|
| mutex_c01 | 0.89-1.16 | 1.01-1.05 | 1.02-1.14 | 1.64-2.27 | 1.00-2.00 | 1.16-1.45 | 1.12-1.25 | 1.18-1.21 |
| mutex_c16 | 0.98-1.13 | 1.09-1.31 | 1.33-1.40 | 1.82-2.28 | 1.12-1.53 | 1.59-1.90 | 1.94-2.04 | 1.96-2.00 |
| rwlock_c01_w1 | 0.98-1.00 | 0.85-0.95 | 0.84-1.01 | 1.01-1.03 | 0.99-1.00 | 0.90-1.01 | 1.06-1.11 | 0.88-0.90 |
| rwlock_c01_w100 | 0.74-1.12 | 1.11-1.42 | 1.69-1.74 | 2.26-2.89 | 0.58-1.15 | 1.14-1.50 | 1.79-1.87 | 1.73-1.83 |
| rwlock_c01_w20 | 0.81-1.00 | 0.88-0.94 | 0.94-0.96 | 0.95-0.96 | 0.92-1.05 | 1.24-1.29 | 1.26-1.29 | 0.93-1.01 |
| rwlock_c16_w1 | 1.02-1.12 | 1.13-1.17 | 1.05-1.09 | 1.07-1.10 | 1.00-1.03 | 1.09-1.17 | 1.06-1.13 | 0.90-0.93 |
| rwlock_c16_w20 | 1.03-1.10 | 1.15-1.17 | 1.12-1.17 | 1.06-1.07 | 0.99-1.16 | 1.15-1.19 | 1.10-1.16 | 0.64-0.74 |
| rwsem_c01_w1 | 1.00-1.77 | 2.12-2.64 | 2.15-2.74 | 2.30-2.59 | 1.00-1.00 | 0.96-0.98 | 0.76-0.98 | 0.62-0.69 |
| rwsem_c01_w100 | 0.74-1.00 | 1.01-1.17 | 1.11-1.18 | 1.70-2.43 | 0.44-1.14 | 1.16-1.28 | 1.13-1.26 | 1.13-1.20 |
| rwsem_c01_w20 | 1.00-3.02 | 2.76-2.79 | 2.79-2.85 | 3.02-3.82 | 0.88-1.01 | 1.13-1.19 | 0.93-1.08 | 0.78-0.82 |
| rwsem_c16_w1 | 1.05-1.66 | 1.79-2.29 | 2.36-2.54 | 2.52-2.85 | 0.97-1.02 | 0.91-0.94 | 0.83-0.96 | 0.69-0.78 |
| rwsem_c16_w20 | 1.67-2.23 | 2.35-2.49 | 2.49-2.55 | 2.27-3.19 | 0.93-1.15 | 1.26-1.30 | 1.06-1.16 | 0.80-0.88 |
| spin_c01 | 0.84-1.11 | 1.00-1.13 | 0.97-1.17 | 1.42-1.70 | 1.15-1.71 | 1.34-1.49 | 1.39-1.48 | 1.45-1.48 |
| spin_c08 | 0.97-1.06 | 1.00-1.07 | 1.00-1.05 | 1.47-1.75 | 1.03-1.50 | 1.42-1.50 | 1.51-1.56 | 1.52-1.55 |

## Mops/s at selected worker counts

| Profile | kd 8 | kd 16 | kd 32 | kd 40 | kd 64 | TCLock 32 | TCLock 64 | Native 32 | Native 64 |
|---|---|---|---|---|---|---|---|---|---|
| mutex_c01 | 3.76 | 3.76 | 3.82 | 3.74 | 3.66 | 3.22 | 3.09 | 3.35 | 1.61 |
| mutex_c16 | 3.50 | 3.52 | 3.68 | 3.61 | 3.54 | 1.81 | 1.81 | 2.63 | 1.55 |
| rwlock_c01_w1 | 15.02 | 14.19 | 14.50 | 12.08 | 11.95 | 13.65 | 13.55 | 14.46 | 11.80 |
| rwlock_c01_w100 | 5.16 | 6.21 | 6.41 | 6.04 | 6.37 | 3.43 | 3.49 | 3.79 | 2.21 |
| rwlock_c01_w20 | 6.31 | 6.41 | 6.37 | 5.00 | 4.56 | 4.94 | 4.92 | 6.80 | 4.75 |
| rwlock_c16_w1 | 12.04 | 11.10 | 11.96 | 10.06 | 9.96 | 11.23 | 11.11 | 11.37 | 9.33 |
| rwlock_c16_w20 | 4.55 | 4.52 | 4.51 | 2.92 | 2.54 | 3.97 | 3.91 | 4.04 | 2.38 |
| rwsem_c01_w1 | 15.21 | 13.49 | 10.47 | 8.45 | 7.67 | 13.80 | 12.42 | 4.88 | 2.96 |
| rwsem_c01_w100 | 3.78 | 3.75 | 3.83 | 3.69 | 3.71 | 3.37 | 3.29 | 3.23 | 1.53 |
| rwsem_c01_w20 | 6.95 | 7.16 | 6.96 | 4.80 | 4.59 | 7.45 | 5.89 | 2.50 | 1.27 |
| rwsem_c16_w1 | 10.98 | 10.68 | 9.59 | 7.84 | 7.41 | 11.55 | 10.77 | 4.07 | 2.68 |
| rwsem_c16_w20 | 5.38 | 5.50 | 5.35 | 3.10 | 3.58 | 5.05 | 4.06 | 2.12 | 1.12 |
| spin_c01 | 5.88 | 6.39 | 6.43 | 6.15 | 6.35 | 4.47 | 4.30 | 6.63 | 3.73 |
| spin_c08 | 4.77 | 4.82 | 4.87 | 4.77 | 4.83 | 3.18 | 3.11 | 4.79 | 2.77 |

## Reading

* **Writer-only profiles no longer fall with the worker count,** within
  one node or across both: from 8 to 64 workers mutex c01 3.76 -> 3.66,
  mutex c16 3.50 -> 3.54, spin c01 5.88 -> 6.35, spin c08 4.77 -> 4.83,
  rwlock writers 5.16 -> 6.37, rwsem writers 3.78 -> 3.71. Native falls to
  a half or less past the node boundary; TCLock stays flat at a lower
  level.
* **Ahead of TCLock** from 8 workers: mutex c01 1.12-1.25, mutex c16
  1.90-2.04, spin c01 1.34-1.48, spin c08 1.50-1.56, rwlock writers
  1.50-1.87, rwsem writers 1.13-1.26. Part of the margin across nodes is
  the longer batch (above).
* **Behind TCLock across both nodes (40-64 workers), with readers:**
  * rwsem 1% writes: 0.62-0.69 (c16 0.69-0.78). kd 7.67 against TCLock
    12.42 Mops/s at 64 workers. Already behind within one node from 20
    workers (0.76-0.92).
  * rwsem 20% writes: 0.78-0.82 (c16 0.80-0.88).
  * rwlock c16 with 20% writes: 0.64-0.74; rwlock 1% writes 0.88-0.93.
  * These ratios are lower than in round 8 (rwsem 1% writes 0.82-0.99
    there). kd did not get slower; TCLock's reader paths gained more from
    the higher frequency. `../tune-20261115-2700MHz/rp70_b70.summary.txt`:
    a longer reader phase helps 1% writes (64 workers: 7.66 at 1000 ns per
    reader, 8.70 at 4000) and costs 20% writes (4.59 -> 4.41), so the
    setting stayed. **Open.**
* **Below Native within one node:**
  * rwlock 1% writes 0.84-0.95 at 6-24 workers; rwlock 20% writes
    0.81-0.96 from 4 workers.
  * 3 workers: mutex c01 0.89, rwlock writers 0.74, rwsem writers 0.74;
    rwsem writers 0.86-0.87 at 4-5. For the rwlock and rwsem writers
    TCLock is at 7.76 and 6.46 Mops/s there where kd is at 4.46 and 2.81
    (kd/TCLock 0.58 and 0.44): with 3 workers there is rarely a second
    waiter to serve, and TCLock's writers still get through without
    queueing.
  * spin c01 0.84 at 2 workers.
  * spin c01 and c08 are at Native within one node (0.97-1.17) and no
    longer below it as in rounds 7 and 8, whose kd spin values were at the
    slow rate of the site lines.

## Correctness on the same boot (before the grid)

| Check | Result |
| --- | --- |
| `run_corr.py --backends native kd tclock` (`corr70.jsonl`) | 312 points, 0 failed, API test 0 failed checks (65), 0 kernel complaints |
| `mm_stress` 4/32/63 threads x 20 s, `kd_mm=1` (with `kd_vdown=1`), then Native | all 6 runs passed |
| `api_stress` setfd/ofd/pipe/seek/xattr at 4/32/63 threads x 20 s | all passed except `setfd 63`, the fd-limit case of the test (round 7) |
| Kernel log | no warning or stall |

`corr70.txt` is the raw output.
