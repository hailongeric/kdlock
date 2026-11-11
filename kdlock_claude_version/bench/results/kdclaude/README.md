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
