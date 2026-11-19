# Full grid on kdall13: nano (cachelines 1 and 8) and application benchmarks

Done on 2026-11-19 in the kdclaude VM (64 vCPUs as 2 nodes of 32, 24 GiB,
host fixed at 2.7 GHz, `nokaslr nopvspin`), driven from the cloud host. It
is the grid of [../appgrid-20261118-64cpu/](../appgrid-20261118-64cpu/README.md)
(round g1 there, on kdall10 and kdnat9) run again on the kernel that
carries the two fixes that round led to (its section 8): the mmap lock left
write-held by a delegated munmap (`a26a8578`) and the per-CPU lock bytes
left set by handbacks (`3a909d50`). Benchmarks, sources and methods are
that README's section 2; the scripts are the ones in that directory. This
README has what differs and the results.

## 1. What differs from g1

| | g1 | g2 (this round) |
|---|---|---|
| kd kernel | `7.0.0-38-kdall10` #13 (`787264dc`) | `7.0.0-38-kdall13` #18 (`3a909d50`) |
| native kernel | `7.0.0-38-kdnat9` #9 | `7.0.0-38-kdnat10` #10: the same source as kdall13 with `CONFIG_KDLOCK_ALL` off, built for this round; the nano grid runs kd as a bench backend of this kernel, so it needs the fixed kd code and the `KD_X_REGION` exit flag the translator now writes |
| workers | 1-8, then every fourth to 64 (22) | 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 40, 48, 56, 60 (14; the user's choice, 2026-11-19) |
| nano rounds | 2 | 1 |
| translator | before the per-CPU regions | per-CPU regions (TRANSLATOR.md 3a), `max_insns` 250000 |
| `kd_vdown` | 1 (the default; the hang of section 6 there) | 1 |
| daemon state for "on" | learned in a boot of its own (learn10) | learned in the previous boot of kdall13: two passes of the application grid at 8, 32 and 64 workers (`learn.sh`, tags `k13-learn1/2`, not counted); the second pass added 147 misses (`data/k13-learn.txt`), so the state had converged |
| recorded per point | delegated, handback, hb_frontier, hb_miss, offered, plain, sessions | also `hb_region` and `done_in_region`; after each benchmark the memcg per-CPU lock bytes (`data/pcpu.txt`) |

The worker ranges of the tables keep g1's column names: "36-64" holds the
points 40, 48, 56 and 60 here, and the last columns are at 60 workers.

Boots, in this order (`data/progress.txt`):

1. kdall13, fresh: a short check (`quick-g2`, 1 and 64 workers, not
   counted), kd off, then kd on (`kd_boot.sh g2`). Off ran first, so
   nothing had been delegated in the boot before it.
2. kdnat10, fresh: the nano grid, then the application grid with native
   locks (`nat_boot.sh g2`).

One run per application point and one round of the nano grid: a ratio
within about 5% of 1 is not a result (g1's 3-boot series,
kdall-native-20261117-64cpu section 5, has the spread).

## 2. Correctness and the state the fixes concern

- **Points:** 183 per mode (native, kd off, kd on), every one with a
  value; nano 504 points with the daemon (native, kd, TCLock) and 168 kd
  points without it, 0 failed data checks.
- **Kernel log:** no complaint in either boot; no fatal signal of a
  benchmark process in any pass (`data/complaints.txt`).
- **Apache default configuration with `kd_vdown=1`** completed and stopped
  cleanly (in g1 its stop hung the boot); no httpd was left after any stop.
- **Per-CPU lock bytes** (`obj_stock`, `memcg_stock`): 0 of 64 CPUs after
  every benchmark of kd on, as in kd off and native (`data/pcpu.txt`). In
  g1 57 of 64 were set after brk1.
- **Counters of the kd-on pass** (`data/g2-on-stats.txt`, per benchmark
  from `data/pcpu.txt`):

| benchmark group | delegated | handbacks | at a frontier | at a miss | `hb_region` | `done_in_region` |
|---|---:|---:|---:|---:|---:|---:|
| will-it-scale (7 tests) | 471 205 402 | 2 102 | 2 096 | 6 | 1 604 | 0 |
| FxMark | 0 | 0 | 0 | 0 | 0 | 0 |
| LevelDB | 1 226 | 119 | 119 | 0 | 0 | 0 |
| Metis | 3 362 | 4 054 | 4 054 | 0 | 0 | 0 |
| Psearchy | 1 567 | 99 | 98 | 1 | 0 | 0 |
| Apache | 5 614 133 | 5 669 659 | 5 669 653 | 0 | 38 | 0 |
| whole pass | 476 825 690 | 5 676 033 | 5 676 020 | 7 | 1 642 | 0 |

  `hb_region` is an upper bound (an exit flagged `KD_X_REGION` taken with
  the section's preempt count or IRQ-off raised; an inner lock held counts
  too): 1 642 such exits and no byte set. Apache's sections are handed back
  about as often as they complete: its munmap sections end at a frontier
  (the kept downgrade hands the read part back, LOCKS.md 5).
- **Nano grid:** kd delegated in every profile with the daemon (per point
  from 2 workers on, median 7 k to 6.5 M sections; 204 M in all), no
  handback, `hb_region` 0; nothing delegated without the daemon.

## 3. Application grid (native kdnat10, kd off and on kdall13)

`data/runs.txt`, `data/app-g2.md` (every point), `data/app-g2.csv`,
`data/app-g2-ranges.md` (below; `app_summary.py`, `app_ranges.py` of g1's
directory).

| benchmark | off/native 1-8 | 12-32 | 36-64 | on/native 1-8 | 12-32 | 36-64 | native / off / on at 32 | at 60 | delegated at 60 |
|---|---|---|---|---|---|---|---|---|---|
| wis lock1 | 0.48-1.00 | 1.27-3.91 | 2.48-3.58 | 0.49-1.00 | 1.26-3.76 | 2.52-3.36 | 2.39M / 9.33M / 8.97M | 1.68M / 6.00M / 5.32M | 0 |
| wis mmap1 | 0.98-1.03 | 1.00-1.02 | 1.49-1.86 | 0.98-1.25 | 1.24-1.29 | 1.75-2.27 | 301k / 305k / 387k | 182k / 327k / 384k | 12235807 |
| wis mmap2 | 1.00-1.02 | 0.99-0.99 | 1.49-1.71 | 0.98-1.21 | 1.07-1.12 | 1.52-1.84 | 360k / 357k / 386k | 216k / 367k / 328k | 10397576 |
| wis brk1 | 0.85-1.61 | 0.95-1.10 | 1.65-2.25 | 0.92-1.61 | 1.37-1.63 | 1.95-2.78 | 728k / 727k / 1.17M | 398k / 783k / 940k | 14870360 |
| wis page_fault1 | 0.82-1.02 | 0.80-1.01 | 1.01-1.08 | 0.79-1.01 | 0.80-1.05 | 1.02-1.06 | 2.79M / 2.83M / 2.93M | 4.16M / 4.34M / 4.34M | 31 |
| wis page_fault2 | 0.87-0.99 | 0.87-0.96 | 0.86-1.00 | 0.89-1.00 | 0.84-0.95 | 0.89-0.99 | 2.00M / 1.91M / 1.89M | 3.63M / 3.12M / 3.23M | 36 |
| wis page_fault3 | 0.82-1.00 | 0.71-0.99 | 1.00-1.01 | 0.81-1.00 | 0.69-0.99 | 1.01-1.01 | 12.46M / 12.33M / 12.32M | 12.04M / 12.04M / 12.15M | 35 |
| fxmark MWRM | 0.99-1.05 | 1.03-1.07 | 1.06-1.21 | 1.00-1.05 | 1.02-1.06 | 1.06-1.22 | 332k / 354k / 350k | 273k / 330k / 335k | 0 |
| fxmark MRDM | 0.96-1.10 | 1.39-4.54 | 3.26-3.96 | 1.00-1.17 | 1.35-4.43 | 3.09-3.83 | 1.14M / 5.19M / 5.06M | 787k / 2.87M / 3.02M | 0 |
| leveldb readrandom | 0.92-1.09 | 0.98-1.14 | 0.87-1.02 | 0.92-1.07 | 1.03-1.13 | 0.88-1.01 | 1.00M / 1.14M / 1.13M | 683k / 620k / 617k | 203 |
| metis wrmem | 0.99-1.08 | 0.98-1.00 | 0.97-1.05 | 0.98-1.13 | 1.00-1.02 | 1.00-1.04 | 7.78 / 7.77 / 7.6 | 6.62 / 6.32 / 6.34 | 307 |
| psearchy pedsort | 1.00-1.00 | 0.99-1.00 | 0.98-1.00 | 1.00-1.00 | 0.99-1.00 | 0.97-1.00 | 295 / 290 / 293 | 521 / 511 / 506 | 687 |
| apache single | 0.99-1.14 | 0.92-1.23 | 0.67-0.83 | 0.98-1.08 | 1.19-1.25 | 1.28-1.31 | 35k / 32k / 44k | 34k / 22k / 44k | 440650 |
| apache default (once) | 1.21 | | | 1.22 | | | 141k / 170k / 172k | | 1218519 |

Metis is wall time (s), ratios native/kd; Psearchy is jobs per hour over
all cores; "delegated at 60" is the sections completed by a combiner in
the 60-worker point of kd on.

What the numbers say:

- **Delegation on the mmap lock:**
  - mmap1 on/native 1.24-1.29 at 12-32 workers and 1.75-2.27 at 40-60
    (off/native 1.00-1.02 and 1.49-1.86);
  - brk1 1.37-1.63 and 1.95-2.78 (off 0.95-1.10 and 1.65-2.25);
  - mmap2 1.07-1.12 and 1.52-1.84 (off 0.99 and 1.49-1.71); at 60 workers
    on is below off (328 k against 367 k, one run each);
  - Apache single process 1.19-1.25 at 12-32 and 1.28-1.31 at 40-60, where
    kd off falls to 0.67-0.83 of native: native stays at 34-35 k req/s
    from 32 workers on, kd off falls from 32 k to 22 k, kd on holds 44-45 k.
- **Apache default configuration**, now measurable with delegation: 141 k
  (native), 170 k (off), 172 k (on) req/s, 1.21 and 1.22 of native (one run
  each). g1's kd-on value of 83 k belonged to the munmap failure.
- **Large gains without delegation, where native collapses:** FxMark MRDM
  3.26-3.96 at 40-60 workers and up to 4.54 at 32; will-it-scale lock1
  2.48-3.58 at 40-60 (native peaks at 19.5 M ops/s with 8 threads, where kd
  is at 0.48, and falls to 1.7 M at 60; kd stays at 5.3-9.6 M from 8
  threads on); mmap1, mmap2 and brk1 at 40-60 as above.
- **Losses, as in g1:** page_fault1 and page_fault3 below 32 workers
  (at 12-24: page_fault1 0.80-1.00, page_fault3 0.69-0.88, lowest at 16
  with 9.1-9.4 M against 13.2 M), at parity from 32; page_fault2 0.84-1.00
  throughout; LevelDB
  `readrandom` at 48-60 workers (0.87-0.93); Apache single process without
  delegation at 40-60. Still not profiled (HANDOFF.md section 4, item 5).
- **Small or no difference:** Metis, Psearchy, LevelDB below 48 workers,
  FxMark MWRM (0.99-1.22).
- **Single points to treat with care (one run each):**
  - brk1 at 2 workers: 1.60 M (off) and 1.59 M (on) against 0.99 M native;
    g1 had 1.04 M and 1.01 M there. The two kd runs were an hour apart and
    agree, so it is not one outlier, but it was not analysed.
  - FxMark MRDM at 56 workers: on 2.58 M against off 3.28 M (0.79), with
    nothing delegated (its locks are not on the allow lists); 0.86-0.95 at
    40 and 48, 1.05 at 60. g1 showed the same lean (median on/off 0.94) and
    attributed about 5% to the per-CPU bytes; the bytes are clean here, so
    that was not the cause. Open.

## 4. Nano grid (kdnat10, one boot, one round)

`data/g2-nano*.jsonl`, `data/nano-g2.md` (every point), `data/nano-g2.csv`,
`data/nano-g2-plain.md`, `data/nano-g2-ranges.md` (below; `nano_ranges.py`).
Ratios per point, min-max within the worker range; "plain" is kd without
the daemon against the same boot's native.

| profile | kd/native 1-8 | 12-32 | 36-64 | kd/TCLock 1-8 | 12-32 | 36-64 | plain kd/native 1-8 | 12-32 | 36-64 | kd Mops/s at 32 / 60 | native | TCLock |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| spin_c01 | 0.61-1.02 | 1.38-2.07 | 2.28-2.77 | 1.00-1.88 | 1.36-1.41 | 1.41-1.46 | 0.61-1.17 | 1.51-2.21 | 1.57-1.81 | 6.57 / 6.40 | 3.18 / 2.31 | 4.72 / 4.41 |
| spin_c08 | 0.57-1.00 | 1.05-1.69 | 1.87-2.29 | 1.00-1.51 | 1.53-1.57 | 1.60-1.62 | 0.58-1.00 | 1.01-1.56 | 1.18-1.29 | 5.19 / 5.05 | 3.07 / 2.20 | 3.30 / 3.13 |
| mutex_c01 | 0.93-1.01 | 0.90-0.92 | 1.40-1.69 | 1.00-1.71 | 1.06-1.19 | 1.11-1.15 | 0.98-1.05 | 1.02-1.08 | 1.29-1.49 | 3.76 / 3.65 | 4.07 / 2.15 | 3.53 / 3.17 |
| mutex_c08 | 0.96-1.08 | 1.05-1.09 | 1.29-1.50 | 0.97-1.47 | 1.42-1.50 | 1.44-1.48 | 0.98-1.02 | 0.99-1.01 | 1.04-1.31 | 3.65 / 3.57 | 3.35 / 2.38 | 2.43 / 2.41 |
| rwsem_c01_w1 | 1.00-1.95 | 2.37-2.66 | 3.52-4.07 | 0.90-1.02 | 0.76-1.04 | 0.84-0.94 | 1.00-1.96 | 2.39-2.63 | 3.66-4.19 | 10.70 / 10.67 | 4.47 / 2.62 | 14.10 / 12.73 |
| rwsem_c08_w1 | 1.00-1.40 | 1.86-2.21 | 3.04-3.73 | 0.94-1.00 | 0.97-1.03 | 1.09-1.15 | 1.00-1.40 | 1.83-2.19 | 2.95-3.49 | 9.67 / 9.59 | 4.37 / 2.57 | 9.93 / 8.80 |
| rwsem_c01_w20 | 1.00-2.70 | 2.21-2.27 | 3.65-5.38 | 1.00-1.13 | 0.93-1.05 | 1.17-1.20 | 1.00-2.71 | 2.20-2.30 | 3.66-5.30 | 6.97 / 6.84 | 3.07 / 1.32 | 7.49 / 5.86 |
| rwsem_c08_w20 | 1.00-2.21 | 2.30-2.43 | 3.70-4.90 | 0.87-1.13 | 0.98-1.04 | 1.24-1.27 | 1.00-1.92 | 1.88-1.96 | 3.01-3.94 | 5.97 / 5.84 | 2.46 / 1.22 | 6.12 / 4.72 |
| rwlock_c01_w1 | 0.98-1.00 | 0.93-2.26 | 2.82-3.82 | 1.00-1.22 | 1.02-1.35 | 0.97-1.03 | 0.97-1.00 | 0.92-2.23 | 2.43-3.36 | 14.38 / 13.54 | 6.37 / 3.55 | 14.04 / 14.02 |
| rwlock_c08_w1 | 1.00-1.19 | 1.28-2.44 | 2.64-3.52 | 1.00-1.06 | 0.97-0.99 | 0.93-0.96 | 1.00-1.19 | 1.27-2.40 | 2.60-3.46 | 9.14 / 8.61 | 3.74 / 2.45 | 9.40 / 9.24 |
| rwlock_c01_w20 | 0.92-1.40 | 1.81-3.00 | 3.44-4.46 | 0.97-1.26 | 1.24-1.26 | 1.21-1.24 | 0.90-1.37 | 1.78-2.97 | 2.80-3.40 | 6.31 / 6.13 | 2.10 / 1.38 | 5.08 / 5.07 |
| rwlock_c08_w20 | 0.96-1.74 | 2.19-3.45 | 3.99-5.01 | 0.92-1.17 | 1.09-1.12 | 1.09-1.11 | 0.95-1.55 | 1.95-3.06 | 2.62-3.01 | 4.97 / 4.82 | 1.44 / 0.96 | 4.45 / 4.41 |

- **Across nodes (40-60 workers) kd is ahead of native in every profile:**
  1.29-5.38 delegated, 1.04-5.30 plain.
- **Against TCLock** kd is ahead in spin (1.36-1.62 from 12 workers),
  mutex (1.06-1.50) and the rw profiles with 20% writes across nodes
  (1.09-1.27). TCLock is ahead in rwsem with 1% writes and 1 cache line
  (kd/TCLock 0.76-1.04 at 12-32, 0.84-0.94 at 40-60) and slightly in rwlock
  c08 with 1% writes (0.93-0.99 from 12 workers).
- **One node, few workers:** spin is behind native at 2-8 workers (lowest
  0.61 with 1 cache line and 0.57 with 8), ahead from 12; mutex c01 is at
  0.90-0.92 of native at 12-32 workers. As in g1; not analysed.

## 5. Against g1

`cmp_rounds.py`, `data/app-g2-vs-g1.md`: per benchmark, over the 14 worker
counts both rounds have, the median and range of g2/g1 per mode and of
on/off within each round. Different boots, and for kd different kernels and
translators: indicators only.

| benchmark | workers in both | native new/old | off new/old | on new/old | on/off old | on/off new |
|---|---|---|---|---|---|---|
| wis lock1 | 14 | 0.99 (0.90-1.09) | 1.03 (0.92-1.12) | 1.01 (0.93-1.14) | 1.00 (0.94-1.17) | 1.00 (0.89-1.11) |
| wis mmap1 | 14 | 1.01 (0.97-1.04) | 1.02 (1.00-1.06) | 1.01 (0.97-1.04) | 1.23 (0.99-1.28) | 1.20 (0.98-1.27) |
| wis mmap2 | 14 | 1.00 (0.98-1.04) | 1.02 (0.98-1.14) | 1.02 (0.91-1.28) | 1.04 (0.96-1.21) | 1.06 (0.89-1.21) |
| wis brk1 | 14 | 1.00 (0.73-1.17) | 1.05 (0.94-1.54) | 1.00 (0.89-1.58) | 1.28 (0.96-1.70) | 1.22 (0.93-1.61) |
| wis page_fault1 | 14 | 0.99 (0.96-1.01) | 1.06 (1.03-1.18) | 1.02 (0.98-1.09) | 1.04 (1.01-1.16) | 1.01 (0.96-1.07) |
| wis page_fault2 | 14 | 0.99 (0.98-1.00) | 1.03 (0.96-1.12) | 1.01 (0.96-1.10) | 1.03 (0.91-1.09) | 1.00 (0.95-1.04) |
| wis page_fault3 | 14 | 0.99 (0.98-1.00) | 1.03 (1.00-1.06) | 1.00 (0.96-1.02) | 1.03 (1.02-1.07) | 1.00 (0.97-1.04) |
| fxmark MWRM | 14 | 1.00 (0.97-1.02) | 1.01 (0.98-1.05) | 1.02 (0.99-1.06) | 0.99 (0.97-1.01) | 1.00 (0.98-1.02) |
| fxmark MRDM | 14 | 0.99 (0.88-1.11) | 0.99 (0.89-1.04) | 1.00 (0.83-1.14) | 0.94 (0.90-1.03) | 0.98 (0.79-1.12) |
| leveldb readrandom | 14 | 0.99 (0.89-1.03) | 1.00 (0.93-1.06) | 1.00 (0.93-1.08) | 1.01 (0.94-1.08) | 1.01 (0.96-1.09) |
| metis wrmem | 14 | 0.99 (0.89-1.16) | 1.01 (0.94-1.05) | 1.02 (0.95-1.05) | 1.00 (0.97-1.03) | 1.01 (0.95-1.05) |
| psearchy pedsort | 14 | 1.00 (0.99-1.02) | 1.00 (1.00-1.01) | 1.00 (0.99-1.00) | 1.00 (0.99-1.01) | 1.00 (0.98-1.01) |
| apache single | 14 | 1.07 (0.97-1.09) | 1.02 (0.97-1.11) | 1.01 (0.97-1.03) | 1.05 (0.95-1.93) | 1.04 (0.91-1.95) |
| apache default | 1 | 0.99 (0.99-0.99) | 1.05 (1.05-1.05) | 2.06 (2.06-2.06) | 0.51 (0.51-0.51) | 1.01 (1.01-1.01) |

- Native reproduces (medians 0.99-1.01; Apache single 1.07).
- kd off on kdall13 is at 0.99-1.06 of kdall10 (page_fault1 1.06, brk1
  1.05; the rest within 3%).
- kd on: medians 1.00-1.02 everywhere but **Apache default, 2.06** (the
  munmap fix). The on/off ratio of the page fault tests is 1.00-1.01 here
  against 1.03-1.04 in g1, because off is higher here, not because on is
  lower.
- The per-CPU bytes g1's kd-on pass carried after brk1 did not move its
  medians by more than the run-to-run spread: page_fault1-3, LevelDB,
  Metis, Psearchy and Apache single are at 1.00-1.02 of g1 in "on".
- The nano ranges agree with g1's within a few hundredths in most cells
  (g1: 2 rounds and 22 worker counts; this round: 1 and 14).

## 6. Limits

- One run per application point, one nano round, one boot per kernel.
- `hb_region` is an upper bound; far exits of per-CPU regions are not
  proven unreachable (TRANSLATOR.md 3a). What this round shows is 0 bytes
  set after 477 M delegated sections of these workloads.
- Only the lock users of `bench/allow/api.txt`, `torture.txt` and `mm.txt`
  are delegated; file-system, socket and futex locks run in plain mode in
  "on" as well.
- The crash checks of g1 (`crash_check.sh`) were not repeated; the
  per-pass fatal-signal counter stands in for them.

## 7. Files

| file | what |
|---|---|
| `learn.sh`, `kd_boot.sh` | the learning passes; the kdall boot (check, off, on) |
| `cmp_rounds.py` | section 5 |
| `data/runs.txt` | one line per application point (tags `k13-learn1/2`, `quick-g2`, `g2`) with the kd counters before and after |
| `data/pcpu.txt`, `data/g2-on-stats.txt` | per-CPU lock bytes and counters after each benchmark; all counters at the end of kd on |
| `data/app-g2*`, `data/nano-g2*`, `data/g2-nano*.jsonl` | results and tables |
| `data/k13-learn.txt`, `data/kds_cmp-kdall13.json` | the learning passes' counters; the daemon state used by "on" |
| `data/kdd-g2.log.xz`, `data/g2-nano.kdd.xz`, `data/g2-nano.log` | daemon logs; the nano driver's log |
| `data/progress.txt`, `data/complaints.txt` | times; kernel complaints and fatal signals per pass |
