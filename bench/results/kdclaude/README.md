# kdclaude nano results

All runs: VM `kdclaude` (32 vCPUs, 2 nodes x 16, vCPUs pinned to host CPUs
0-15 and 20-35), kernel `7.0.0-38-kdclaude1`, bench module `kd_bench.ko`
built against the running tree, translator daemon on (`delegation 1`).
Host CPU governor `powersave`, frequency not fixed, host load average about
4 during `grid-20261111-r1`. Every point is a single 1 s (grid: 2 s) run
after a warm-up, Native and kd alternating per point. One round gives no
variance claim. Do not pool files with different builds.

Each JSON line carries `kernel`, `build` (uname -v; the build number `#N`
identifies the source), `commit` (a tag naming the source state), the kd
counter deltas (`kd_delta`) and the data-oracle result (`ok`).

| Build | Source | Files |
| --- | --- | --- |
| #2 | commit `9ba5a456` | `grid-20261111-r1/` (full grid, 12 profiles x 14 worker counts) |
| #3 | + stop/abandon/park/handoff counters | `probes-20261111/probe1.jsonl` |
| #4 | + first parked mutex waiter spins on the owner | `b4.jsonl` (has a lost-grant bug, see #7) |
| #5 | + mutex owner written on handback only, not per delegated section | `b5.jsonl` |
| #6 | + queued sleepable waiters poll the owner every 64 iterations | none: hung at mutex n4 (the #4 bug) |
| #7 | + after the first-waiter spin, always recheck the grant before sleeping | `b7.jsonl`, `stress7.jsonl` (174 points exact) |
| #8 | + rwsem readers spin (bounded) before queueing on `->m` | `b8.jsonl` |
| #9 | + spinlock pending waiter, first version | `b9.jsonl` |
| #10 | + pending to locked in one atomic step | `b10.jsonl` (2 rounds) |
| #11 | + newcomers wait for a pending handover; pending waiter takes a free lock even with a queue | `b11.jsonl` (2 rounds), `corr11.jsonl` (168 points exact) |

`bench/grid_summary.py FILE` prints kd/Native per profile and worker count
with the execution-class shares.

## Later rounds

| Build | Bench | Files | Note |
| --- | --- | --- | --- |
| #11 | `63f8de2a` | `grid-20261111-r2/` (2 rounds, Native and kd) | |
| #11 | `374164c9` (TCLock backend) | `grid-20261111-r3/` (2 rounds, Native, kd, TCLock) | **placement-affected**: the bench objects were not line-separated, and this build placed the kd spinlock differently; kd spin at 8/16 workers ran about 0.8 times its rate with the earlier bench build in a direct A/B (4.9 vs 4.0 Mops). Do not use for kd vs TCLock; superseded by the next round |

From the commit after `374164c9` on, every lock object, the counter lines and
the run flags of the bench sit in their own 128-byte block (`KDB_BLOCK`). An
A/B of the two bench builds then agrees within run-to-run noise (kd spin n8
4.71–4.87 vs 4.84–5.18; Native within 2%).

## Candidates after round 3 (`probes-20261111b/`)

All with the line-separated bench (`94f91a77`), Native, kd and TCLock where
listed. `cN.jsonl`: candidate probe on build #N (spin c01/c08, mutex
c01/c16, 2–32 workers, 2 rounds). `abN*.jsonl`: A/B **within one boot**
(`bench/run_ab.sh`, a temporary core parameter selects the variant, order
rotated per round, 3 rounds; `bench/ab_summary.py` prints median [min–max]).

| Build | Change | Result | Kept |
| --- | --- | --- | --- |
| #11 | baseline (`c11`) | | |
| #12 | queued mutex waiters check the owner every 1024 iterations, not 64 | mutex c01 n32 1.51 → 3.03, c16 n32 1.46 → 2.45 Mops; others unchanged | yes |
| #13 | sleepable session checks `HANDOFF` every 16 sections | mutex c01 n32 3.03 → 3.43, c16 n32 2.45 → 2.69 | yes |
| #14/#15 | session prefetch without dependent loads (`ab15`: 0 old, 1 node `prefetchw`, 2 node shared prefetch) | mode 2: spin +3–6%, mutex c01 +3–5%, mutex c16 within 1%; mode 1 costs mutex c16 4% | mode 2 |
| #16 | session waits for a waiter that swapped the tail but has not linked (`ab16lw`) | no effect beyond noise | no |
| #16 | one unqueued mutex spinner while no queue exists (`ab16ms`) | mixed: +2.5–5% at two points, −3 to −6% at mutex n3/n4 | no |
| #16 | delegation on vs off (`deleg_ab`, daemon stopped) | off is better for spin at n4/n5 only; on is better for mutex at every n ≥ 3 | (diagnosis) |
| #17 | bounded linger for the next arrival when the queue empties (`ab17`: 0/300/600/1000 ns) | n2/n3 much worse (spin c01 n2 4.93 → 1.16), n4 unchanged | no |

`corr_tc.jsonl`: correctness pass with all three backends (288 points exact).
| #18 | early packet prefetch from the next node's address (`ab18`) | spin +1–3% at 8–32; mutex c01 −6% (cause not established) | spin class only |
| #19 | reader spin bound by time instead of 1024 iterations (`ab19r`: 0/5/20/50 µs) | bimodal: 5 µs helps rwsem w20 at 20–32 but halves 8/16 | no |
| #19 | writer head spin bound by time (`ab19w`: 0/20/100 µs) | no effect | no |
| #20 | holder of `->m` spins for the writer bit before sleeping (`ab20`) | w20 at 20 workers +16–33%; no change elsewhere | yes |
| #21 | diagnosis (`diag21`): at a give-up the owner of `->m` was runnable in only ~3% of cases; it sleeps on the count holding `->m` | | |
| #22/#23 | readers check the writer bits before adding (`ab22`, `ab23`: 1 read first, 2 `prefetchw` then read) | mixed: w20 +5–30%, c16 w1 −3% to −22% | no |

## Round 4 (`grid-20261111-r4/`)

Build #24 = commit `7e05332e`, bench `94f91a77` layout, Native, kd and TCLock
alternating per point, 2 rounds, 1008 points, no failures.
`corr24.jsonl`: correctness on the same boot, 297 points exact (all
families, three backends, plus nest/mix under kd), `handback_pinned` 0.
`summary.txt` holds the per-point table.

## Adaptive delegation (`probes-20261112/`)

Builds #25–#35 on 2026-11-12: plain mode (native algorithm on the caller's
stack) for spinlock and mutex, delegation mode entered and left by queue
depth, the complete Linux 7.0 lock API. `run_corr.py` is the correctness
pass (240 points plus the single-task API check).

| File | Build | What |
| --- | --- | --- |
| `c25_delegoff.jsonl` | #25 | first adaptive build with the translator stopped, so every point is plain mode. Recorded because it was the first measurement of the plain path alone (spin 0.73–0.85 of Native, mutex 0.95–1.12) |
| `c33.jsonl` | #33 | spin and mutex, Native/kd/TCLock, 2 rounds, after the plain spin path reached Native (below) |
| `c34.jsonl` | #34 | mutex and rwsem w20, 2 rounds, release by one locked subtraction. Shows rwsem writers no longer delegating under a depth threshold (0% delegated, n16 1.46 Mops against 3.09 in round 4), which is why rwlock and rwsem always delegate |
| `ab34enter.jsonl` | #34 | A/B in one boot: `kd_deleg_enter` 3/4/5 with `kd_deleg_exit` 2 |
| `c35.jsonl`, `c35.summary.txt` | #35 | the committed state: spin, mutex, rwlock w20, rwsem w20, three backends, 1 round |
| `corr35.jsonl` | #35 | correctness, 240 points exact, API check 65/65 |

What the plain spinlock path needed to match Native, each step measured (kd
spin c01, Native in the same boot; ratios are kd/Native at 3/4/5 workers):

| Build | Change | 3 / 4 / 5 workers |
| --- | --- | --- |
| #25 | native algorithm in C, called from the entry stub | 0.79 / 0.79 / 0.79 |
| #26 | no read of the predecessor's node before linking, no look at the tail node to learn the mode, look before the second trylock | 0.83 / 0.86 / 0.89 |
| #27 | per-CPU state in 128-byte blocks, so a remote access to a node does not drag a local line along | 0.87 / 0.91 / 0.92 (delegation mode at 16/32 workers +20%) |
| #29 | node count in the node's own cache line, as the native lock has it | raw API 1.00 / 1.00 / 1.00; delegable entry 0.92 / 0.95 / 0.95 |
| #32 | A/B of each remaining piece in one boot (temporary switch): only the sampling counter mattered, and only when it was written in the node line (0.85 / 0.95 / 0.94 against 1.00 / 0.99 / 0.99 with it in a local line) | |
| #33 | sampling counter in a local line, statistics and mode memory in the node line | 1.01 / 0.99 / 0.99 |

The node-count finding came from a replica of the slow path inside the bench
module with switchable variants (not kept): compact native-style nodes ran at
Native's rate, and moving only the count to another line cost 12% at 3
workers. A store that waits for its cache line holds up every later store of
that CPU, including the lock handover.

Rates between builds differ by up to about 15% in delegation mode for
reasons not established (#27 6.45, #28 5.58, #35 6.29 Mops for spin c01 at 16
workers with identical queue code). Compare only within one boot.

## Role exchange, `current`, RCU (`probes-20261112/`, builds #36–#39)

| File | Build | What |
| --- | --- | --- |
| `ab36xchg.jsonl` | #36 | A/B in one boot: `kd_xchg` 0 against 1 (then: every family offers), Native alongside, bodies with a sixteenth of the write sections handed back (`spin_hb`, `rwlock_hb`, `rwsem_hb`, `mix`), 3 rounds |
| `ab37xchg.jsonl` | #37 | the same, kd only, after the sleepable-class release learned to take over before it releases (`kd_cpu.xs_hint`). Effect unchanged; this is the table in docs/LOCKS.md 6a |
| `corr38.jsonl`, `corr38x2.jsonl` | #38 | correctness with `kd_xchg` 1 (default) and 2: 240 points exact each |
| `cur38.jsonl` | #38 | first run of the `current` bodies. **The `*_curw` rows are not delegated**: their sites failed to translate (see below), so they show plain mode only |
| `cur38b.jsonl` | #38 | the same after the translator fix. **Superseded**: during the run before it the kernel had reported an unbalanced RCU depth (below) |
| `cur39.jsonl`, `cur39.summary.txt` | #39 | `current` bodies with the RCU depth carried over: the numbers quoted in docs/DIFFERENCES.md D3 |
| `corr39.jsonl` | #39 | correctness: 240 points exact, API check 65/65, no kernel complaints (the pass now reads the kernel log) |

Two defects found by the `current` bodies:

* **Translator.** `rcu_read_unlock()` reaches `__raise_softirq_irqoff`, which
  contains `or %ax, %gs:x(%rip)`. The decoder reports a 2-byte displacement
  for an instruction with an operand-size prefix, the translator refused the
  instruction and with it the whole site, so no section with an
  `rcu_read_unlock()` was ever delegated. The displacement is now located and
  checked by the translator, and an instruction it cannot relocate ends only
  that path.
* **RCU depth.** Once those sections were delegated, the kernel warned
  ("Voluntary context switch within RCU read-side critical section", and a
  nonzero depth at the scheduler tick; build #38, 16 workers). The combiner
  was incrementing and decrementing the origin's `rcu_read_lock_nesting` from
  its own CPU while interrupt handlers on the origin's CPU did the same as
  the origin. Since #39 the RCU calls in a section count for the executor and
  the depth is carried over at the handover (docs/ARCHITECTURE.md 6). 12.5 M
  delegated `rcu_read_lock` sections and the correctness pass then ran
  without a complaint.

## Round 5 (`grid-20261113-r5/`)

Build #39 (the commit that adds this directory; its kernel sources differ
from the built ones only in comments of `kd_internal.h` and `kd_rwlock.c`),
Native, kd and TCLock alternating per point, 2 rounds, 1008 points, no failed
point, no kernel complaint. `corr39.jsonl`: correctness on the same build,
240 points exact. `summary.txt` holds the per-point table. Defaults:
`kd_adapt=1`, `kd_deleg_enter=5`, `kd_deleg_enter_sleep=3`, `kd_deleg_exit=2`,
`kd_xchg=1`. Host governor `powersave`, frequency not fixed; two rounds give
no variance claim.

kd/Native, medians of the two rounds (round 4 in brackets where it differed
most):

| Profile | 2-5 workers | 6-8 | 12-16 | 20-32 |
| --- | --- | --- | --- | --- |
| spin c01 | 0.99-1.05 (0.67-0.92) | 1.00-1.16 | 1.22 | 1.62-1.76 |
| spin c08 | 1.04-1.16 (0.75-0.98) | 1.17-1.24 | 1.16-1.19 | 1.29-1.36 |
| mutex c01 | 0.89-1.03 (0.79-1.02) | 1.03-1.19 | 1.30-1.31 | 1.86-2.81 |
| mutex c16 | 0.94-1.00 | 1.26-1.64 | 1.66 | 1.99-2.85 |
| rwlock (four profiles) | 0.97-1.10 | 1.00-1.13 | 0.99-1.14 | 0.98-1.24 |
| rwsem (four profiles) | 1.02-2.09 | 1.57-2.51 | 1.95-3.73 | 1.59-2.92 |

Below Native by more than 2%: mutex c01 at 3 workers (0.89; Native itself
ran between 3.5 and 5.4 Mops at that point across this day's runs), mutex c16
at 2 and 3 workers (0.94, 0.96), rwlock c01 w20 at 4 workers (0.97).

kd/TCLock: at or above 1 for spin and mutex up to 8 workers and for mutex
c16 everywhere from 6 (1.12-1.25). Below: mutex c01 at 12-32 workers
(0.74-0.84; round 4: 0.70-0.74), spin c08 at 12-32 (0.88-0.90), rwlock w20 at
20-32 (0.64-0.83), rwsem at 20-32 (w1 0.66-0.84, w20 0.23-0.38). The rwsem
and rwlock gaps across both NUMA nodes are the reader paths, which this
round of work did not change.

## Round 6 (`grid-20261113-r6/`)

* **Run:** 380G10, build #56 with the Task C rwsem changes (DIFFERENCES
  D11). 10 profiles, Native, kd and TCLock, 2 rounds, 840 points, no failed
  point.
* **Gain:** rwsem with 20% writes is 1.2-2.3 times round 5 from 8 workers.
  Across both nodes kd/TCLock went from 0.23-0.38 to 0.55-0.64.
* **Loss:** rwsem c16 with 1% writes is 0.80-0.94 of round 5.
* **`nodaemon.jsonl`:** the same grid on the same boot without the daemon
  (0% delegated); a control, not a kd result. The directory README has the
  tables.

## Round 7 (`grid-20261114-r7-64cpu/`)

* **Host:** 10.176.26.71, VM with 64 vCPUs (2 x 32) and 24 GiB; not
  comparable with rounds 1-6.
* **Run:** build #56, 14 profiles, workers 1-64, Native, kd and TCLock,
  2 rounds, 1512 points, no failed point. Workers 1-32 run on one node,
  40-64 span both.
* **Correctness on the same boot:** `corr56.jsonl` and the directory
  README.
* **Across nodes, kd/TCLock:** rwsem 0.52-0.80, rwlock with writers
  0.69-0.93, mutex c01 0.71-0.83.
* **Within one node:** spin and mutex c01 are below Native from 6-8
  workers (0.73-0.91).

## Round 8 (`grid-20261114-r8-64cpu/`)

* **Host and VM:** as round 7. Build #61, commit `3bf4bfaa`; same grid,
  1512 points, no failed point.
* **Changes:** session announcement without an atomic per section, mutex
  handoff only to a running waiter, rwsem reader phase counter and reader
  phase (LOCKS 4 and 5).
* **Against round 7:** mutex c01 1.17-1.54 times from 8 workers, rwsem
  writers only 1.45-1.52, rwsem 20% writes 1.3-1.8, 1% writes 1.2-1.4
  from 16 workers.
* **Across nodes, kd/TCLock:** mutex c01 1.15-1.21, rwsem writers only
  1.13-1.21, rwsem with readers 0.78-0.99, rwlock with 20% writes
  0.72-0.98.
* **Losses:** spin c01 0.87-0.95 of round 7 at 2-24 workers and rwlock
  writers only 0.88-0.96, unexplained.
* **Correctness on the same boot:** `corr61.jsonl`, `corr61.txt`.
* **Defect, older than this change set:** mmap1 with `kd_mm=1` hangs this
  VM, also with the previous commit's kernel source. The directory README
  has the evidence.

## mmap1 on 64 vCPUs (`mmap1-20261115-64cpu/`)

* **Hang fixed (#65):** after a handback with interrupts off the executor
  enabled interrupts before the origin was resumed; a timer interrupt then
  waited for a lock the origin held. Older than round 8.
* **Reader phase:** cost mmap1 12% at 4-32 threads on #65; none on #66,
  where a single reader gets no phase.
* **kd/Native on this host (#66):** 0.83-0.86 at 4 threads, 0.92-0.99 at
  16-32, 1.02-1.03 at 64.

## From 2026-11-15: 2.7 GHz

The host is fixed at 2.7 GHz with turbo on from here (before: 2.0 GHz,
turbo off). Do not compare with rounds 7 and 8 in absolute numbers or in
ratios.

### Tuning (`tune-20261115-2700MHz/`)

In-boot A/B on builds #67-#71: the site-line split that removed the
differences between boots, CLDEMOTE, session prefetch stages (rejected),
`kd_batch`, the downgrade kept under the write side on mmap1, the retry of
switched-off sites, the reader phase at 2.7 GHz. The directory README has
the tables.

### Round 9 (`grid-20261115-r9-64cpu/`)

* **Run:** build #70, commit `ee5db2c5`, same grid as rounds 7 and 8, 1512
  points, no failed point. Two boots of the build agree within 2.2%.
* **Writer-only profiles** are flat from 8 to 64 workers and ahead of
  TCLock: mutex c01 1.12-1.25, mutex c16 1.90-2.04, spin 1.34-1.56, rwlock
  writers 1.50-1.87, rwsem writers 1.13-1.26. kd's batch is 4096, TCLock's
  1024.
* **With readers across both nodes** kd is behind TCLock: rwsem 1% writes
  0.62-0.69, rwsem 20% writes 0.78-0.82, rwlock c16 20% writes 0.64-0.74.
* **Correctness on the same boot:** `corr70.jsonl`, `corr70.txt`.

### Round 10 (`grid-20261115-r10-64cpu/`)

* **Run:** build #72, source commit `b2958b0b`, the worker grid the user asked
  for on 2026-11-15 (1 to 8 one by one, then every fourth to 64) for all 14
  profiles and all three backends: 1848 points, no failed point.
* **Tables:** `r10.csv` (for plotting) and `r10.md`, from
  `bench/grid_table.py`. The directory README lists where kd leads and where
  it does not.
* **Same shape as round 9**, with the extra counts filling in the step at 36
  workers, which is the first count that crosses nodes.

### will-it-scale on 64 vCPUs (`wis-20261115-64cpu/`)

* **Run:** build #72, `mmap1`, `mmap2`, `page_fault1`, `brk1`, `threads` and
  `processes`, 1 to 64 workers, Native and kd alternating in one boot
  (`kd_mm`): 224 points, no failed point, no kernel complaints.
* **mmap1** 1.25-1.37 of Native at 4-32 threads, 2.06 at 64, with ~3500
  delegated waiter sections per session.
* **mmap2** 0.78-0.86: every session hands back at `down_write` of
  `mapping->i_mmap_rwsem` (1.28 M handbacks, all `hb_frontier`, 16 bodies
  delegated).
* **page_fault1** 0.84-0.91 at 2-16 threads with no delegation at all; faults
  take no `mmap_lock` in this kernel (`CONFIG_PER_VMA_LOCK=y`). Attributed to
  kd rwsem reader spinning (`kd_rwsem_rspin_ns`), which recovers two thirds of
  it when switched off.
* **brk1** parity inside the spread.
* The lock-by-lock analysis of the mmap section is `docs/MMAP_LOCKS.md`.

### Eras: the rw families across NUMA nodes (`era-20261115-64cpu/`)

* **Question** (the user, 2026-11-15): why rwsem and rwlock lose across
  nodes where mutex and spinlock do not, and whether the delegation is
  NUMA-aware.
* **Cause**, with the worker count fixed (32 on one node or 16+16, #72):
  kd keeps 0.95-0.97 where every section is delegated, 0.57-0.74 with 20%
  writes, like the native locks (0.61-0.71). A session's NUMA order reaches
  writers only; readers are not delegated and nothing ordered them.
* **Change** (#73 to #82, `kernel/kd_era.c`): under pressure an rw lock
  serves one node at a time. The directory README has every step, including
  the three that were removed again and what each cost.
* **Committed state** (#82): 16+16 over one node is 0.93-1.17 for the
  rwsem and 0.87-1.01 for the rwlock. No placement, worker count or
  one-node point loses rate. With unequal numbers on the nodes and 20%
  writes the least-served worker gets 0.54-0.93 of the most-served one's
  operations (0.85-0.98 without eras).
* **Correctness on the same boot:** `b82-corr.jsonl`, mm_stress, api_stress.

### Rounds 11 and 12 (`grid-20261115-r11-64cpu/`, `grid-20261115-r12-64cpu/`)

* **Round 11:** build #80, commit `72fd7552`, the grid of round 10 with
  eras. Across nodes as round 12; on one node the rwsem profiles with
  readers were up to 20% under round 10, which led to build #81 and the
  removal of a check in the reader fast path.
* **Round 12:** build #82, commit `9ac62b01`, 1848 points, no failed point.
  * From 32 to 64 workers the rw families lose 3-12% (round 10: 18-43%).
  * Across nodes kd is at or ahead of TCLock in twelve of fourteen profiles
    (round 10: six): rwlock 0.99-1.29, rwsem with 20% writes 1.08-1.24.
    Behind: the rwsem with 1% writes, 0.79-0.93, the same margin as within
    one node.
  * One node: kd's rates are 0.96-1.05 of round 10 in every profile.

### More threads than CPUs (`oversub-20261116-64cpu/`)

* **Run:** build #82, 1 to 8 workers per CPU on 8 and 16 CPUs, Native and
  kd, 224 points, every data check passed, no kernel complaint.
* **Spin class:** no effect, Native and kd alike; waiters and holders run
  with preemption off, so a CPU's other threads never reach the lock.
* **Sleepable class:** both lose, kd less; kd/Native 1.04-1.40 with one
  worker per CPU, 1.16-1.62 with more. kd's sessions get shorter; the rwsem
  with writers only falls to 11-33 sections per session and has less even
  shares per worker than Native there.
* **TCLock** crashed the guest with two workers per CPU on its spinlock
  (stack protector in `__schedule`, twice); its mutex and rwsem adapters
  allow one task per CPU. Not in the comparison.

### Clobber entries (`clobber-20261116-64cpu/`)

* **What:** the `kd_*_cl()` macros (LOCKS 8): a compact continuation, two
  packet lines instead of four per section.
* **Correctness:** 586 points with eight new bodies, 0 failed, on #83 and
  #84; the counters show a compact state exactly where both ends are
  clobber calls.
* **Gain** (in-boot A/B on #83): 2-4% for one-line spin and rwlock writer
  sections, 0.5-2% for the rwsem, up to 2% for the mutex, -0.5 to -0.8% for
  the mutex with sixteen lines.
