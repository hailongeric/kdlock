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
