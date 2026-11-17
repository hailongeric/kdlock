# Eras: the rw families across NUMA nodes

The user asked on 2026-11-15 why rwsem and rwlock lose so much when the
workers cross NUMA nodes while mutex and spinlock do not, and whether the
delegation was NUMA-aware. This directory holds the measurements behind the
answer and behind the change that followed (`kernel/kd_era.c`,
ARCHITECTURE 7b). Every comparison is within one boot; files of different
builds are not pooled.

Host and guest as in the round 10 README: `kdclaude`, 64 vCPUs as 2 nodes of
32, host fixed at 2.7 GHz. `run_nano` puts worker *i* on CPU *first + i*, so
the first CPU decides how many workers each node gets
(`bench/run_place.py`). A profile is `family:lines:write-percent`.

## 1. The cause (`b72-placement.jsonl`, build #72)

The worker grid cannot separate "more workers" from "across nodes": from 36
workers on both change together. So: the same 32 workers, all on node 0 or
16 on each node. Rate on two nodes over rate on one, median of 2 rounds:

| profile | Native | kd | TCLock |
|---|---|---|---|
| mutex c01 | 0.52 | **0.95** | 0.97 |
| rwlock c01, writers only | 0.58 | **0.97** | 0.99 |
| rwsem c01, writers only | 0.54 | **0.95** | 0.99 |
| rwlock c01 / c16, 20% writes | 0.71 / 0.61 | 0.74 / 0.57 | 1.00 / 1.00 |
| rwsem c01 / c16, 20% writes | 0.64 / 0.62 | 0.63 / 0.57 | 0.71 / 0.71 |
| rwlock c01, 1% writes | 0.80 | 0.83 | 0.83 |
| rwsem c01, 1% writes | 0.79 | 0.88 | 0.83 |

* **Where every section is delegated, kdlock already was NUMA-aware and
  loses 3-5%.** A session serves the waiters of the combiner's node and
  passes the others over (`kd_numa`, ARCHITECTURE 7); the lock word and the
  protected data stay in one node for a whole session of up to 4096
  sections.
* **With readers it lost what the native lock loses.** Readers are never
  delegated. Each runs on its own CPU, writes the reader count there and
  reads the protected data there, and the next writer session has to fetch
  all of it back. The order of a session reaches writers only.
* **On the rwlock the order had nothing to act on.** A reader that meets a
  writer queues without a continuation and ends the session: round 10 has
  1.4-1.8 sections per session with 20% writes, and `stop_plain` at three
  times the number of sessions.
* **On the rwsem the deferral rarely began.** It starts after 32 served
  waiters (`numa_after`), and sessions with 20% writes serve about 30.
* TCLock's rwlock does not lose because its readers pass through the
  combining queue too, which is served one socket at a time. It pays for
  that within one node: 4.97 against kd's 6.23 on c01 with 20% writes.

## 2. The change, step by step

Each step is one build, measured with eras off and on in the same boot. The
meaning of `kd_rw_era_press` changed between builds (readers, then
hundredths of a reader, then hundredths of a caller); the files carry the
value that was set, the table says what it meant.

| build | what changed | file | result |
|---|---|---|---|
| #73 | readers only wait; the era follows the last writer session; 30 us | `b73-readers-only-30us.jsonl` | 0.87-0.95 of no era at 8+8 and 16+16 with 20% writes: an era lasted about 26 us and 95 operations, and every writer session of the other node ended it |
| #74 | writers wait too; an era ends only by a waiter taking it over; 200 us; pressure = readers found, threshold 1 | `b74-era-numa_after.jsonl` | rwsem 16+16: c16 20% writes 2.98 -> 4.79, c01 4.28 -> 5.50, 1% writes 8.96 -> 10.75; one node and writers only 0.99-1.01. `numa_after` 0 adds nothing with eras |
| #75 | shared file, rwlock joins (50 us) | `b75-rwlock-spin.jsonl` | rwlock c16 20% writes 1.29-1.45 across nodes. rwsem 1% writes on **one** node, 16 workers: 0.95 |
| #76 | the head only starts or renews an era, never clears it | `b76-low-counts.jsonl`, `b76-asym-no-look.jsonl` | the 0.95 is gone. New: with 31 workers and 1, 0.82-0.98 of no era; with 28 and 4 the 4 get half of the lock |
| #77 | each waiter looks at the lock once (time by CPU number) and takes the era if it is idle | `b77-asym-look-press.jsonl` | 31+1 is 1.00-1.24. Equal time per node remains: 24+8 least/most per worker 0.39-0.47 |
| #78 | time divided by callers; minimum an eighth of the bound; threshold a quarter reader | `b78-asym.jsonl`, `b78-low.jsonl`, `b78-one.jsonl` | 24+8 0.68-0.79. New: one worker on each node 0.72; 4+4 one node's workers do 11 times the other's (the look's time favours low CPU numbers modulo 32); at 31+1 the one worker gets 17-25% of a share |
| #79 | no look; minimum a quarter; pressure = readers found + callers queued behind the head, threshold 2.25 | `b79-asym.jsonl`, `b79-low.jsonl`, `b79-one.jsonl`, `b79-rwlock-bound.jsonl` | no loss at any placement or count; 1+1 and 2+2 have no era. rwlock bound 50 -> 200 us: +3-12% and 28+4 least/most 0.30 -> 0.76-0.93 |
| #80 | one bound for both families (200 us); the rwlock does not wait with bottom halves off | section 3 | no loss in any in-boot comparison of eras off and on; round 11 |
| #81 | `kd_rw_era_ns=0` measures nothing; the reader fast path's check can be put out of reach | section 4 | the check costs the rwsem 3-12% on one node and gains nothing across nodes |
| #82 | the check and `kd_rw_era_min` removed | section 5 | the committed state; round 12 |

What the rejected pieces cost is recorded where they were removed
(`kd_rw_era_wait()`, `kd_rw_era_bound()`, `kd_rw_era_writer()`).

## 3. Build #80: the first complete state

`kd_rw_era_ns` 200000 for both families, `kd_rw_era_press` 225,
`kd_rw_era_drain_ns` 5000, `kd_rw_era_min` 2, `kd_numa_after` 32. Round 11
(`../grid-20261115-r11-64cpu/`) is this build. Section 4 is what it still
had wrong; the tables of this section are superseded by section 5 for the
rwsem and stand for the rwlock, whose code did not change afterwards.

### Across nodes, three backends (`b80-three.jsonl`, 3 rounds)

32 workers; rate as 16+16 over the rate on one node, and the 16+16 rate
itself in Mops/s.

| profile | Native | kd | TCLock | kd, 16+16 | TCLock, 16+16 |
|---|---|---|---|---|---|
| mutex c01 | 0.52 | 0.97 | 0.98 | 3.66 | 3.11 |
| rwlock c01, writers only | 0.61 | 0.98 | 1.05 | 6.66 | 3.62 |
| rwsem c01, writers only | 0.50 | 0.96 | 0.96 | 3.63 | 3.06 |
| rwlock c01, 20% writes | 0.74 | **0.97** | 1.03 | 6.15 | 5.12 |
| rwlock c16, 20% writes | 0.64 | **0.96** | 1.02 | 4.23 | 4.08 |
| rwlock c01, 1% writes | 0.86 | **0.99** | 0.88 | 14.26 | 11.89 |
| rwlock c16, 1% writes | 0.83 | **0.87** | 0.83 | 10.29 | 9.68 |
| rwsem c01, 20% writes | 0.61 | **0.94** | 0.68 | 6.22 | 5.20 |
| rwsem c16, 20% writes | 0.60 | **0.93** | 0.71 | 4.92 | 3.66 |
| rwsem c01, 1% writes | 0.76 | **1.08** | 0.80 | 10.79 | 11.57 |
| rwsem c16, 1% writes | 0.76 | **1.04** | 0.80 | 9.79 | 9.37 |

Before (section 1) the kd column read 0.63 / 0.57 for the rwsem with 20%
writes and 0.74 / 0.57 for the rwlock. The rw families now lose across nodes
what the mutex loses. The one profile where TCLock is still ahead at 16+16 is
the rwsem with 1% writes on one line, and that is a gap it has within one
node already (14.45 against 10.03): it is about the reader fast path, not
about nodes.

### Eras off and on, by placement (`b80-asym.jsonl`, 3 rounds)

32 workers, kd, `kd_rw_era_ns` 0 against 200000 in the same boot. Rate with
eras over rate without; *fair* is the least over the most operations per
worker, without eras -> with.

| placement | rwsem 20% writes | rwsem 1% writes | rwlock 20% writes | rwlock 1% writes |
|---|---|---|---|---|
| one node | 1.00 | 1.00 | 1.00 | 1.00 |
| 16+16 | 1.50-1.62 | 1.25-1.26 | 1.34-1.70 | 1.10-1.23 |
| 24+8 | 1.44-1.57 | 1.27-1.38 | 1.30-1.57 | 1.15-1.20 |
| 28+4 | 1.40-1.45 | 1.26 | 1.26-1.36 | 1.14-1.18 |
| 31+1 | 1.09-1.18 | 1.13 | 1.01-1.06 | 1.06-1.09 |

| placement | fair, rwsem 20% | fair, rwsem 1% | fair, rwlock 20% | fair, rwlock 1% |
|---|---|---|---|---|
| one node | 0.97 -> 0.97 | 0.66-0.77 -> same | 0.89-0.95 -> same | 0.58-0.60 -> same |
| 16+16 | 0.95-0.97 -> 0.90-0.91 | 0.57-0.80 -> 0.61-0.78 | 0.90-0.92 -> 0.89-0.92 | 0.58-0.62 -> 0.55-0.64 |
| 24+8 | 0.97 -> 0.82-0.85 | 0.42-0.50 -> 0.66-0.80 | 0.91-0.94 -> 0.83-0.89 | 0.52 -> 0.55-0.60 |
| 28+4 | 0.97-0.98 -> 0.63-0.89 | 0.45-0.52 -> 0.63-0.78 | 0.87-0.95 -> 0.72-0.75 | 0.43-0.45 -> 0.42-0.45 |
| 31+1 | 0.96-0.98 -> 0.68-0.84 | 0.28-0.40 -> 0.67-0.74 | 0.84-0.94 -> 0.54-0.72 | 0.37-0.43 -> 0.43-0.45 |

No placement loses rate. What eras cost is evenness with 20% writes when the
nodes have unequal numbers: the least-served worker gets 0.54-0.89 of the
most-served one's operations where it got 0.84-0.98. With 1% writes the
shares were uneven without eras already, and eras leave them as they are or
better.

### Few workers (`b80-low.jsonl`, 2 rounds)

| workers | era on / off | eras started? |
|---|---|---|
| 1+1 | 1.00 in all six profiles | no |
| 2+2 | 1.00-1.04 | rwlock c16 20% writes only |
| 4+4 | 1.00-2.04 (rwlock c01 20% 4.23 -> 8.66, c16 2.33 -> 4.28, rwsem c16 20% 2.48 -> 3.82) | where the callers keep the lock busy |
| 8+8 | 1.14-1.74 | yes |

Two callers in all can never reach the pressure threshold; that is what
keeps a lock that two nodes merely share out of this.

### Correctness on the same boot

* `run_corr.py`, Native, kd and TCLock: 312 points, 0 failed, 0 kernel
  complaints (`b80-corr.jsonl`).
* `mm_stress` with `kd_mm=1` at 4, 32 and 63 threads, then the native
  control: all pass.
* `api_stress` (setfd, ofd, pipe, seek, xattr at 4, 32, 63): all pass except
  `setfd 63`, which runs into the test's own descriptor limit ("Too many
  open files") as on every build before.
* Kernel log from the start of the chain to the end of the grid: no BUG,
  WARNING, stall or lockup message.

### will-it-scale, eras off and on (`b80-wis-era0.jsonl`, `b80-wis-era200000.jsonl`)

`mm->mmap_lock` as a kd rwsem goes through the same code, so eras can start
on it. Threads, kd over Native, 2 rounds each:

| threads | mmap1 off -> on | mmap2 off -> on | page_fault1 off -> on |
|---|---|---|---|
| 8 | 1.29 -> 1.14 (see below) | 0.81 -> 0.84 | 0.84 -> 0.87 |
| 16 | 1.38 -> 1.32 | 0.79 -> 0.83 | 0.81 -> 0.92 |
| 32 | 1.34 -> 1.36 | 0.79 -> 0.78 | 1.03 -> 1.05 |
| 64 | 2.07 -> 2.08 | **0.80 -> 1.16** | 1.06 -> 1.06 |

* 8 to 32 threads are on one node, where an era holds nobody back
  (`era_gate` under 30 per run). The differences there are the spread of
  these tests.
* At 64 threads eras do start on `mmap_lock`. `mmap2` gains 48% in kd's own
  rate (135000 -> 199500): its sessions hand every section back at the file
  mapping's rwsem (MMAP_LOCKS.md), so the lock behaves like a plain
  contended rwsem there, and serving one node at a time helps it as it
  helps the nano profiles. `mmap1`, whose sessions run thousands of sections
  each, neither gains nor loses (315900 -> 309300, inside the two rounds'
  spread of 311700 to 320000).

## 4. What the era code costs where it holds nobody back (build #81)

Round 11 had the rw profiles with readers 1-7% under round 10 on one node,
and `rwsem_c01_w1` 13-20% under at 8-16 workers, although every in-boot
comparison of eras off and on had shown 1.00 there. Rounds are different
boots, so that alone proved nothing; but only the profiles with readers were
lower, which a difference between boots would not single out. The in-boot
comparisons could not see it either way: with eras off the same code still
ran, measuring in every queue head and checking the era word in the rwsem
reader's fast path whenever two readers were in.

Build #81 makes both removable at run time: `kd_rw_era_ns=0` measures
nothing, and `kd_rw_era_min` out of reach keeps the fast path away from the
era word. One node, kd, 4 rounds (`b81-one-node-cost.jsonl`), rate over the
rate with both removed:

| | rwsem 1% writes | rwsem 20% writes | rwlock |
|---|---|---|---|
| default of #80 (eras on, check) | 0.88-0.98 | 0.93-0.97 | 0.97-1.00 |
| eras on, no check | 0.99-1.00 | 0.99-1.00 | same as default: it never had the check |
| eras off, check | 0.89-0.98 | 0.93-0.99 | 1.00 |

(The ranges are 8 to 32 workers; at 4 every entry is 0.98-1.00.)

* The cost was the check in the reader fast path, 3-12% of every rwsem's
  read side on one node. What the queue heads measure costs 0-3%.
* Across nodes the check gains nothing (`b81-reader-fast-path.jsonl`, 3
  rounds, rate over no eras):

| placement | rwsem 1% writes, check -> none | rwsem 20% writes, check -> none |
|---|---|---|
| one node, 32 | 0.93-0.96 -> 0.99 | 0.95-0.98 -> 1.00 |
| 31+1 | 1.03-1.04 -> 1.10-1.11 | 1.03-1.18 -> 1.09-1.22 |
| 24+8 | 1.21-1.22 -> 1.23-1.31 | 1.37-1.55 -> 1.44-1.57 |
| 16+16 | 1.15-1.20 -> 1.21-1.29 | 1.40-1.59 -> 1.50-1.62 |
| 32+32 | 1.21-1.24 -> 1.22-1.31 | 1.31-1.35 -> 1.33-1.41 |

So it was removed. A reader now waits for its node's era only when it meets
a writer, as on the rwlock.

`mmap1` at 8 threads, which went from 1.29 to 1.14 of Native with eras in
the #80 run, is bimodal by itself (`b81-mmap1-8threads-era*.jsonl`, six runs
each): 264000-385000 without eras, three low and three high; 278000-389000
with, one low and five high.

## 5. The committed state (build #82)

`kd_rw_era_ns` 200000, `kd_rw_era_press` 225, `kd_rw_era_drain_ns` 5000,
`kd_numa_after` 32. Round 12 (`../grid-20261115-r12-64cpu/`) is this build.

### Across nodes, three backends (`b82-three.jsonl`, 3 rounds)

32 workers; rate as 16+16 over the rate on one node, and the 16+16 rate
itself in Mops/s.

| profile | Native | kd | TCLock | kd, 16+16 | TCLock, 16+16 |
|---|---|---|---|---|---|
| mutex c01 | 0.53 | 0.97 | 0.99 | 3.65 | 3.15 |
| rwlock c01, writers only | 0.59 | 0.98 | 0.98 | 6.57 | 3.50 |
| rwsem c01, writers only | 0.60 | 0.96 | 0.98 | 3.61 | 3.11 |
| rwlock c01, 20% writes | 0.73 | **0.97** | 0.99 | 6.18 | 4.99 |
| rwlock c16, 20% writes | 0.63 | **0.97** | 0.99 | 4.28 | 4.03 |
| rwlock c01, 1% writes | 0.85 | **1.01** | 0.81 | 14.67 | 11.44 |
| rwlock c16, 1% writes | 0.83 | **0.87** | 0.80 | 10.46 | 9.24 |
| rwsem c01, 20% writes | 0.60 | **0.95** | 0.70 | 6.57 | 5.26 |
| rwsem c16, 20% writes | 0.59 | **0.93** | 0.72 | 4.92 | 3.65 |
| rwsem c01, 1% writes | 0.78 | **1.17** | 0.86 | 12.25 | 11.92 |
| rwsem c16, 1% writes | 0.78 | **1.02** | 0.83 | 9.76 | 9.73 |

Section 1 has the kd column before the change: 0.63 / 0.57 for the rwsem
with 20% writes, 0.74 / 0.57 for the rwlock. The rw families now lose across
nodes what the mutex loses, and at 16+16 kd is at or ahead of TCLock in all
eleven profiles. (The rwsem with 1% writes gains across nodes because half
as many readers contend for the count at a time; on one node TCLock's rwsem
is still ahead there, 13.89 against 10.47.)

### Eras off and on, by placement (`b82-asym.jsonl`, 3 rounds)

32 workers, kd, `kd_rw_era_ns` 0 against 200000 in the same boot. Rate with
eras over rate without.

| placement | rwsem 20% writes | rwsem 1% writes | rwlock 20% writes | rwlock 1% writes |
|---|---|---|---|---|
| one node | 1.00 | 0.99-1.00 | 0.98-0.99 | 1.00 |
| 16+16 | 1.55-1.65 | 1.25-1.38 | 1.34-1.68 | 1.09-1.23 |
| 24+8 | 1.47-1.61 | 1.28-1.40 | 1.27-1.54 | 1.14-1.20 |
| 28+4 | 1.41-1.48 | 1.28-1.31 | 1.22-1.34 | 1.14-1.15 |
| 31+1 | 1.09-1.21 | 1.16 | 1.01-1.06 | 1.05-1.06 |

On one node eras hold nobody back; the 1-2% of the rwlock with 20% writes is
what the queue heads' measurements cost there, where nearly every writer is
a queue head of its own.

Least over most operations per worker, without eras -> with:

| placement | rwsem 20% | rwsem 1% | rwlock 20% | rwlock 1% |
|---|---|---|---|---|
| one node | 0.97-0.98 -> same | 0.65-0.79 -> same | 0.91-0.95 -> 0.90-0.95 | 0.58-0.62 -> same |
| 16+16 | 0.97 -> 0.90-0.93 | 0.61-0.81 -> 0.65-0.75 | 0.88-0.92 -> 0.89-0.93 | 0.48-0.63 -> 0.52-0.65 |
| 24+8 | 0.96-0.98 -> 0.78-0.79 | 0.32-0.40 -> 0.64-0.80 | 0.90-0.91 -> 0.87-0.89 | 0.52-0.54 -> 0.54-0.62 |
| 28+4 | 0.94-0.95 -> 0.54-0.83 | 0.44-0.58 -> 0.53-0.54 | 0.87-0.92 -> 0.75-0.81 | 0.48-0.59 -> 0.40-0.44 |
| 31+1 | 0.90-0.96 -> 0.77-0.93 | 0.38-0.42 -> 0.50-0.57 | 0.85-0.94 -> 0.54-0.71 | 0.35-0.46 -> 0.42-0.47 |

No placement loses rate. What eras cost is evenness with 20% writes when the
nodes have unequal numbers: the least-served worker gets 0.54-0.93 of the
most-served one's operations where it got 0.85-0.98. With 1% writes the
shares were uneven without eras already (0.32-0.59 with unequal numbers) and
are 0.40-0.80 with them.

### Few workers (`b82-low.jsonl`, 2 rounds)

| workers | era on / off | eras started? |
|---|---|---|
| 1+1 | 0.99-1.00 in all six profiles | never |
| 2+2 | 0.97-1.03, and 1.33 for rwlock c16 20% writes | rwlock and rwsem c16 20% writes only; the 0.97 and 0.98 are points without an era |
| 4+4 | 1.00-2.40 (rwsem c01 20% 3.47 -> 8.33, rwlock c01 20% 4.56 -> 8.94, c16 2.37 -> 4.22) | where the callers keep the lock busy |
| 8+8 | 1.09-1.77 | yes |

Two callers in all can never reach the pressure threshold; that is what
keeps a lock that two nodes merely share out of this. The least over the
most operations per worker is the same or better with eras at every one of
these points (0.62-0.98).

### Correctness on the same boot

* `run_corr.py`, Native, kd and TCLock: 312 points, 0 failed, 0 kernel
  complaints (`b82-corr.jsonl`).
* `mm_stress` with `kd_mm=1` at 4, 32 and 63 threads, then the native
  control: all pass.
* `api_stress` (setfd, ofd, pipe, seek, xattr at 4, 32, 63): all pass except
  `setfd 63`, which runs into the test's own descriptor limit ("Too many
  open files") as on every build before.
* Kernel log from the start of the chain to the end of the grid: no BUG,
  WARNING, stall or lockup message.

### will-it-scale, eras off and on (`b82-wis-era0.jsonl`, `b82-wis-era200000.jsonl`)

`mm->mmap_lock` as a kd rwsem goes through the same code, so eras can start
on it. Threads, kd over Native, 2 rounds each:

| threads | mmap1 off -> on | mmap2 off -> on | page_fault1 off -> on |
|---|---|---|---|
| 8 | 1.33 -> 1.45 | 0.77 -> 0.82 | 0.85 -> 0.84 |
| 16 | 1.36 -> 1.31 | 0.82 -> 0.79 | 0.94 -> 0.88 |
| 32 | 1.35 -> 1.33 | 0.81 -> 0.77 | 0.87 -> 1.04 |
| 64 | 2.09 -> 2.11 | **0.90 -> 1.37** | 1.04 -> 1.13 |

* 8 to 32 threads are on one node, where an era holds nobody back. The
  differences there are the spread of these tests (section 4 has six runs
  of `mmap1` at 8 threads; `page_fault1` at 16 and 32 threads moves by as
  much between the two columns in either direction).
* At 64 threads eras start on `mmap_lock`. `mmap2` gains 55% in kd's own
  rate (146600 -> 227500): its sessions hand every section back at the file
  mapping's rwsem (docs/MMAP_LOCKS.md), so the lock behaves like a plain
  contended rwsem there, and serving one node at a time helps it as it
  helps the nano profiles. That takes `mmap2` at 64 threads from below
  Native to 1.37 of it; at 8 to 32 threads it is still 0.77-0.82, for the
  reason MMAP_LOCKS gives. `mmap1`, whose sessions run thousands of sections
  each, neither gains nor loses (312800 -> 309300).
