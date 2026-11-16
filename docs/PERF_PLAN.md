# Performance work plan (nano first, then micro/API)

Status of this directory: tasks A and B below are done (2026-11-11; results
and the fixes they needed are in [BUILD_AND_TEST.md](BUILD_AND_TEST.md)
section 5). The kdlock kernel boots, local and delegated runs of all four
families, two-level nesting and handback keep the data exact. **Nothing has
been measured** (only single rounds). This plan lists what stands between that
state and defensible performance numbers, splits it into tasks, and records
what is already prepared. Known goal/effect differences from the earlier documents are in
[DIFFERENCES.md](DIFFERENCES.md); several of its items are inputs to the tasks
below. It is derived from the earlier project's documents (`docs/ROADMAP.md`,
`docs/BENCHMARK_WORKLOADS.md`, `docs/PERFORMANCE.md`, `bench/README.md`,
`bench/nano/README.md`, none of which are in this tree; tag
`full-tree-before-cleanup-20261115`); the rules below are theirs unless
stated otherwise.

## 1. What the old benchmarks expect, and what differs here

The established Stage 1 workload is the *nano* set: ten padded-counter
profiles (mutex c01/c16 at 100% writes; rwsem and rwlock c01/c16 at 1% and
20% writes), 256 register-only post-unlock rounds, workers on CPUs `0..N-1`
for `N` in `1..8,12..60` (21 counts), one two-second round per point,
compared Native / TCLock / KD. Spin has its own c01/c08 micro cases (post64).
Stage 1 then adds ~42 micro/API cases (hash table, proc snapshots, OFD,
setfd, pipe, seek, UTS, xattr) that go through real syscalls.

This rewrite differs in ways that change how it is benchmarked:

| Old setup | Here |
| --- | --- |
| KD provider loaded as modules, per-object API binding, ABI1/2/3 | kdlock is built in (`CONFIG_KDLOCK=y`); workloads call `kd_*` directly |
| Old runner, daemon and schema-2 identity bundles | `bench/kd_bench.c` + `bench/run_nano.py` (new, small); translator is `jit/kd_daemon.py` |
| Many micro/API cases need native kernel locks replaced | The API macro layer (`integration/kd_linux_map.h`) is **not applied** to the kernel yet |
| 64-vCPU VM, 2.0 GHz pinned host | 32-vCPU VM on a 2x20 host (`kdclaude`); absolute numbers are not comparable with old results |

Consequence: old numbers are context only. Every claim needs a matched
Native control on the same kernel, VM and call shell. Do not pool.

## 2. Gap list, in dependency order

Items 1–4 are done (2026-11-11, BUILD_AND_TEST.md section 5); their text is
kept as the record of what was checked.

1. **Boot the kdlock-enabled kernel** (`7.0.0-38-kdclaude1`, built from
   `/mnt/kdlock-builds/kdc`) in the `kdclaude` VM. Nothing in `kd_core.c`,
   `kd_entry.S` or the per-CPU layout has ever executed. Expect the first
   failures here (early-boot use of the entry stubs, `kd_core_init` timing,
   `execmem`, per-CPU offsets in `kd_asm.h`).
2. **Local-only correctness** (translator off, `delegation` off): load
   `kd_bench`, run all four families with the kd backend and verify data
   and progress. This tests the queue protocols (spin, rwlock writer/reader,
   mutex with sleepers, rwsem) without any JIT.
3. **Translator bring-up**: install `capstone` (not in the VM); run
   `jit/kd_daemon.py` against `/dev/kdlock`; make it produce and load an
   image for a `kd_bench` call site; confirm a delegated section completes
   (`delegated` in `/sys/kernel/debug/kdlock_stats` rises, `handback` stays
   low). This tests the relocation, `kd_jit_enter/exit`, the exit stubs, the
   `%gs` redirection and the release-root check. Highest-risk code.
4. **Correctness under contention with JIT on**: all four families, c01 and
   c16, 8/32 workers, data oracle exact, no torn reads. Then nesting
   (`lock(A); lock(B)` bodies) with a dedicated small test body; nested
   delegation has never run.
5. **Nano grid, Native vs kd** (new runner), with the execution class kept
   next to every rate: delegated / handed back / local. A rate without its
   class says nothing (existing rule: successful local runs are not
   delegation gains).
6. **Optimization loop** on the families that lose (see section 4).
7. **Micro/API stage**: needs the API switch (below) and real syscall
   runners; the old runners under `bench/real_api` etc. are written for the
   old provider and will need adapting or replacing.
8. **TCLock reference**: the old campaigns compared against TCLocks. It
   needs a separate kernel (`/home/eric/TCLocks`) and is optional for the
   first optimization rounds; Native is the mandatory control.

## 3. Tasks

### Task A: bring-up (boot, local correctness) — done 2026-11-11

* The kernel is already built (`/mnt/kdlock-builds/kdc/out`, release
  `7.0.0-38-kdclaude1`). Install it next to kdlock1 (`make modules_install install`
  in `/mnt/kdlock-builds/kdc/src` with `O=../out
  KERNELRELEASE=7.0.0-38-kdclaude1`); keep kdlock1 as the default entry and
  use `grub-reboot` to try the new one. The VM can be recovered from the
  host (`run_claude_vm.sh`, serial log `/tmp/qemu-claude-serial.log`).
* Boot, read `dmesg`, check `/dev/kdlock`, debugfs `kdlock_stats`.
* Build `bench/` against `/mnt/kdlock-builds/kdc/out`, load `kd_bench`, run
  the kd backend with delegation disabled.
* Done when: all four families pass the oracle at 1/8/32 workers, and
  repeated load/unload and a reboot are clean. Fix only what fails.

### Task B: translator and delegation bring-up — done 2026-11-11, except the depth/roots limits

Open from B: nesting deeper than two levels, `KD_MAX_DEPTH`/`KD_MAX_ROOTS`,
forced `MISS_CODE`/`MISS_RET` handback, `UNLOCK_ANC`, the irq variants.
Rebuild rounds per site: one extra round for the `mix` body (one indirect
target); the nano bodies need none.

* `pip install capstone` into a venv (not the system Python), run the
  daemon, get one site translated and one section delegated, then widen to
  all four families. Learn from `MISS_*` events until convergence; record how
  many rebuild rounds each site needs.
* Check handback exactness (no replay, no skipped instruction), preempt
  count and IF transfer, and that `handback_pinned` is zero for the nano
  bodies.
* Nested test body and the depth/roots limits.
* Done when: delegated and handed-back counts are non-zero and consistent,
  data oracle exact at 32 workers with JIT on, and no leaked preempt
  count or stuck node after a stress run followed by unload of the bench
  module.

### Task C: nano measurements and optimization

* Run the 21-count grid for the ten profiles, Native and kd, one round each
  first; then repeat the few points that matter (not the whole grid).
* Per family, find where kd loses to Native and why, using counters first
  (delegated share, handback rate, miss rebuilds, queue batch size), then
  `perf` if the VM exposes counters; otherwise `ftrace`/counters added
  behind a config option.
* Candidate levers (hypotheses, not findings): `kd_batch`; the NUMA
  deferral (`kd_numa`); prefetch of the next waiter's packet/stack; cost of
  the entry stub and wait-stack switch on the uncontended path; reader
  handling in rwlock/rwsem (readers never delegate); the `rwsem` handback
  on `post()` failure; node and packet cacheline layout; the translator's
  compare chains for `ret`/indirect branches (`call_depth`, learned
  targets); `popfq`/`pushfq` cost per section.
* Items from DIFFERENCES.md that are likely to matter first: D11 (rwsem
  readers sleep immediately; add a bounded spinning admission stage), D9 (no
  pending path in the spinlock), D8 (queue spin ignores signals), D13 (frontier
  list lacks TLB/mm helpers; needed before any mm lock work).
* Keep each change separable and measured against the previous source on the
  same kernel. Report losses together with gains.

Status 2026-11-11 (raw data and the build map:
`bench/results/kdclaude/README.md`):

* Round 1 (build #2, `9ba5a456`, one round) found three loss regions: mutex
  from 7 workers up (0.4–0.5 of Native), rwsem with 20% writers at 3–8
  workers (about 0.5), spin at 2–4 workers (0.6–0.8).
* Counters added (`stop_*`, `no_spin`, `abandon`, `head_sleep`, `parked`,
  `handoff`) located the causes; the fixes are in `63f8de2a` (DIFFERENCES
  D9–D11): mutex convoy after handoff to a sleeping waiter; per-section
  owner store and per-iteration owner polling on the queue's cache line;
  rwsem readers sleeping in sequence behind the holder of `->m`; no pending
  waiter in the spinlock.
* Round 2 (build #11, `63f8de2a`, two rounds, median): kd is within 0.97 of
  Native or above at every point except spin at 3–6 workers (0.66–0.96),
  mutex c01 at 3–5 workers (about 0.82) and rwsem c16/1% writers at 4
  workers (0.91). Large gains where delegation is full or readers no
  longer sleep: mutex c16 1.5–2.0, rwsem 1.5–3.5, spin 1.1–1.46 from 7
  workers up. Readers still never delegate.
* TCLock is now a third backend of the nano bench (`KDB_TCLOCK`, the
  original `tclock_backend` modules); round 3 compares all three.
* Open: the 3–6 worker region of spin and mutex (short sessions: the queue
  keeps draining), more rounds at the key points, fixed host frequency.

Status after the TCLock comparison (commits `94f91a77`..`7e05332e`):

* The bench now line-separates every shared object; before that, kd spin
  depended on linker placement by up to 20% (round 3 is marked).
* Small effects are decided by A/B **within one boot** (`bench/run_ab.sh`
  with a temporary core parameter), not across reboots.
* Accepted: owner poll every 1024 iterations and HANDOFF check every 16
  sections (mutex at 32 workers 1.5 → 3.4 Mops); session prefetch without
  dependent loads (+3–6%); spin-class early packet prefetch (+1–3%); rwsem
  holder spin (w20 at 20 workers +16–33%).
* Rejected with data (`bench/results/kdclaude/README.md`): link wait,
  unqueued mutex spinner, linger, time-bounded rwsem spins, check before
  add.
* Understood, not fixed:
  * 3–5 workers: each waiter's own cycle (resume, post work, offer, enqueue)
    limits the rate, not the combiner; TCLock is in the same place there.
  * rwsem across both NUMA nodes (20–32 workers): readers serialise through
    `->m` and its holder sleeps on the count; TCLock (separate AQS reader
    queue) is about 4 times faster. Needs a reader admission design of its
    own (D11), not tuning.

Status 2026-11-13 (adaptive delegation, role exchange, API coverage; commits
`594af5ee` and the one after it; data in `bench/results/kdclaude/`,
`probes-20261112/` and `grid-20261113-r5/`):

* The loss at 2-5 workers is gone for the spinlock and nearly gone for the
  mutex: a lock is in plain mode (the native algorithm, on the caller's
  stack) until its queue is deep (ARCHITECTURE 7a). Round 5, kd/Native:
  spin c01 0.99-1.05 at 2-7 workers (round 4: 0.67-0.98), mutex c01
  1.02-1.03 at 4-6 (0.81-0.96); left below Native: mutex c01 at 3 workers
  (0.89, Native bimodal there), mutex c16 at 2-3 (0.94-0.96).
* What the plain path needed beyond the algorithm is recorded step by step
  in the results README: cache-line placement of the queue node, its count
  and the sampling counter decided 4 to 15% each.
* Delegation mode got faster as a side effect of the same layout work and of
  a one-atomic mutex release: against TCLock, mutex c16 is now ahead from 6
  workers (1.12-1.25; round 4: 0.91-0.95) and mutex c01 at 12-32 workers is
  at 0.74-0.84 (0.70-0.74).
* Role exchange after a handback is implemented and on by default for mutex
  and rwsem writer; its measured effect is mixed (LOCKS 6a).
* Reading or RCU-locking through `current` in a section has no established
  cost (DIFFERENCES D3); it had two defects, both fixed (D19, TRANSLATOR 2).
* Still open, in order of size: rwsem and rwlock with writers across both
  NUMA nodes against TCLock (reader admission, unchanged); mutex c01 at
  12-32 workers against TCLock; spin c08 at 12-32 (0.88-0.90); a mode
  criterion that accounts for section length; sites that hand back often
  are slower than Native at 32 workers (spin body with a sixteenth handed
  back: about 0.8) and are not switched off until handbacks dominate.

Status 2026-11-14 (rwsem across NUMA nodes; the user asked to optimize the
cases where rwsem and similar locks across nodes are far from TCLock, which
touches the reader fairness area AGENTS.md lists as deferred). Data:
`grid-20261113-r6/` (380G10, #56) and `grid-20261114-r7-64cpu/`
(10.176.26.71, 64 vCPUs, #56). Details: DIFFERENCES D11, LOCKS 5.

* **Changes:**
  * rwsem readers wait outside `->m`, registered behind an active writer.
  * The read fast path looks before it adds.
  * NUMA deferral in rwsem writer sessions starts after 32 waiters
    (`kd_family.numa_after`).
  * `kd_rwsem_is_contended` also reports readers registered behind a
    writer.
* **Gain:** round 6 against round 5 (same host): rwsem with 20% writes is
  1.2-2.3 times faster from 8 workers. Across nodes kd/TCLock went from
  0.23-0.38 to 0.55-0.64.
* **Loss:** rwsem c16 with 1% writes is 0.80-0.94 of round 5, while TCLock
  and Native are flat at those points; not yet explained.
* **Rejected with data:**
  * the same admission for the rwlock, -18 to -46%;
  * writer-bit pass on release, archived as
    `refs/archive/kdclaude-rwsem-writer-pass-20261113`;
  * reader poll spacing.
* **On 64 vCPUs** (workers 1-32 on one node, 40-64 across both):
  * Across nodes, kd/TCLock is still 0.52-0.53 for rwsem with 20% writes,
    0.57-0.80 for the other rwsem profiles, 0.69-0.93 for rwlock with
    writers and 0.71-0.83 for mutex c01.
  * kd is ahead for mutex c16 (1.48-1.59), rwlock writers only (1.21-1.25)
    and spin c08 (1.14).
  * Within one node, delegation is below Native for spin (0.73-0.89 at
    6-32 workers), mutex c01 (0.84-0.91 from 8) and rwsem writers only
    (0.72-0.75).
* **Next:**
  * a head-only reader queue for rwsem;
  * longer writer phases under reader pressure;
  * the single-node spin and mutex region;
  * the rwsem c16 1% loss.

Status 2026-11-14, second part (the user asked why kd falls behind TCLock
across nodes and degrades with more workers, and to reduce cache
overhead). Data: `grid-20261114-r8-64cpu/` (#61, commit `3bf4bfaa`);
in-boot A/B numbers in LOCKS 4 and 5.

* **Causes found by profiling #56 at 64 workers:**
  * The combiner claimed every waiter with a cmpxchg on the node line
    that the waiter polls: 72% of `kd_session`'s samples.
  * A mutex handoff went to a sleeping waiter. The queue head and new
    callers then saw an owner off the CPU and parked in turn: 13000 parked
    waits per second at 64 workers.
  * Waiting rwsem readers polled `count`, which the readers that are in
    write on entry and exit.
  * Each rwsem reader got one section per writer phase.
* **Changes:** plain-store announcement one section ahead; handoff only to
  a running waiter; reader phase counter in its own line; reader phase of
  1000 ns per reader before the queue head closes the read side.
* **Round 8 against round 7:** mutex c01 1.17-1.54 times from 8 workers
  and flat to 64; rwsem writers only 1.45-1.52; rwsem 20% writes 1.3-1.8;
  rwsem 1% writes 1.2-1.4 from 16 workers. Across nodes kd/TCLock: mutex
  c01 1.15-1.21, rwsem writers only 1.13-1.21, rwsem 20% writes 0.85-0.90,
  1% writes 0.82-0.99.
* **Losses, unexplained:** spin c01 0.87-0.95 of round 7 at 2-24 workers
  and rwlock writers only 0.88-0.96 at 8-64, with TCLock up 0-10%.
* **Rejected with data:** dropping the look before the add on the read
  fast path (1% writes 9-11% lower, #59).
* **Defect found, older than this change set:** mmap1 with `kd_mm=1` hangs
  the 64-vCPU VM, also with the kernel source of `041653e4` (round 8
  README). Open, and it blocks measuring the reader phase on mmap1.
* **The hang is fixed** (#65, `mmap1-20261115-64cpu/`): a handback with
  interrupts off left the executor open to a timer interrupt that needed a
  lock the origin held. The reader phase cost mmap1 12% until a single
  reader was exempted (#66). mmap1 on this host: kd/Native 0.83-0.86 at 4
  threads, 0.92-0.99 at 16-32, 1.02-1.03 at 64.
* **The spin-class loss of round 8 did not reappear** on #66, but kd's
  spin-class rate turned out to differ between boots far more than that
  loss: spin c01 at 16 workers 3.70 (#61), 4.10 (#56) and 5.74 (#66) Mops/s,
  all fully delegated, with Native and TCLock unchanged. Cause unknown.
* **Next:** what makes kd's spin-class rate differ between boots; mmap1
  below Native on this host; rwsem with
  readers and rwlock with writers across nodes; spin within one node.

Status 2026-11-15 (the user asked for a fixed higher frequency, an
analysis of prefetching with CLDEMOTE on the waiter side, long sessions,
and the read part after a downgrade executed under the kept write side).
Data: `tune-20261115-2700MHz/` (in-boot A/B, builds #67-#71) and
`grid-20261115-r9-64cpu/` (#70, commit `ee5db2c5`).

* **Frequency:** the host was already fixed at 2.0 GHz. It is now fixed at
  2.7 GHz with turbo on. That did not remove the differences between
  boots; the next item did.
* **Site lines:** `struct kd_site` put the fields every waiter reads and
  the counters the combiner writes in one line or in two, by allocation.
  Each site ran at one of two rates per boot (spin c01 at 32 workers 6.4
  or 4.4 Mops/s). Split in #70; two boots now agree within 2.2%. Every kd
  number of rounds 1-8 carries the old behaviour.
* **CLDEMOTE:** a queued spin-class waiter demotes its packet and stack
  top: +1 to +3% for spin c01 and rwlock writers, about 0 for spin c08,
  nothing for the sleepable class (off there). The combiner demoting
  lines back: -3 to -20%, not kept.
* **Prefetch:** more than the existing one-ahead requests loses 1 to 27%;
  archived.
* **Session length:** `kd_batch` 4096; +1 to +5% across nodes, nothing
  within one. TCLock runs with 1024.
* **Downgrade under the write side (`kd_vdown`):** mmap1 kd/Native from
  0.77-0.96 to 1.11-1.38 at 4-32 threads and from 1.0 to 2.0 at 64.
* **Found and fixed on the way:** switched-off sites were never tried
  again (#71); the daemon reused the knowledge of earlier builds (#70).
* **Round 9:** writer-only profiles are flat from 8 to 64 workers and
  ahead of TCLock by 1.12-2.04. With readers across both nodes kd is
  behind TCLock: rwsem 1% writes 0.62-0.69, 20% writes 0.78-0.82, rwlock
  c16 20% writes 0.64-0.74.
* **Round 10:** the same shape on the user's full worker grid (1 to 8, then
  every fourth to 64), 1848 points, no failed point
  (`bench/results/kdclaude/grid-20261115-r10-64cpu/`). `r10.csv` is the
  plotting form.
* **Next:** rwsem and rwlock with readers across nodes (a longer reader
  phase helps 1% writes and costs 20% writes; it needs a rule, not a
  constant); the 3-worker points below Native; the effect of `kd_vdown`
  on a workload with readers.
* **Readers across nodes: eras (builds #73 to #80).** The user asked why
  rwsem and rwlock lose across NUMA nodes where mutex and spinlock do not.
  * *Cause, measured with the worker count fixed* (32 workers on one node
    or as 16+16, `bench/run_place.py`): where every section is delegated kd
    keeps 0.95-0.97 of its one-node rate, because a session serves its own
    node first. With 20% writes it kept 0.57-0.74, which is what the native
    locks keep (0.61-0.71). Readers are never delegated, and nothing
    ordered them by node.
  * *Change*: a reader-writer lock under pressure serves one node at a time
    (`kernel/kd_era.c`, ARCHITECTURE 7b). Callers of the other node wait
    before they touch the lock.
  * *Result* (#82, same placements): rwsem 0.93-1.17, rwlock 0.87-1.01 of
    the one-node rate. No placement, worker count or one-node point loses
    rate; with unequal numbers on the nodes the shares per worker are less
    even than without eras (20% writes: least over most 0.54-0.93, from
    0.85-0.98).
  * *Round 12* (#82): from 32 to 64 workers the rw families lose 3-12%
    (round 10: 18-43%); across nodes kd/TCLock is 0.99-1.29 for the rwlock
    and 1.08-1.24 for the rwsem with 20% writes (round 10: 0.65-1.08 and
    0.76-0.87). will-it-scale `mmap2` at 64 threads goes from 0.90 to 1.37
    of Native; `mmap1` and `page_fault1` do not move.
  * *A lesson about the method*: round 11 (#80) lost up to 20% on one node
    for the rwsem with readers, and no in-boot comparison of eras off and
    on had shown it, because the switch left the always-on code running. A
    switch that is to prove "no cost" has to remove the code's work
    (BUILD_AND_TEST 5a).
  * All of it, step by step, with what was tried and removed:
    `bench/results/kdclaude/era-20261115-64cpu/`.
* **Still open after round 12:**
  * The rwsem with 1% writes against TCLock, 0.75-0.93 on either side of
    the node boundary. It is the read side on one line of a 40-byte object
    against TCLock's 500 bytes; no change of the wait policy has moved it.
  * `rwlock_c01_w20` on one node, 0.89-0.95 of Native: every queued reader
    ends the writer session. With eras the rwlock no longer needs readers
    in its queue to be ordered across nodes, so admitting them outside the
    queue as the rwsem does can be tried again (#47 rejected it before the
    phase counter and the reader phase existed).
  * The 3- and 4-worker points, `mutex_c01` at 3 above all (0.94, 0.56 and
    0.83 of Native in rounds 10, 11 and 12 with the same mutex code).
  * Evenness of eras with very unequal numbers on the nodes (28+4 with 20%
    writes: 0.54-0.83).
* **Reader spinning needs a rule too.** A reader registered behind an
  *active* writer spins out `kd_rwsem_rspin_ns` (50 us) even when the holder
  will not leave for milliseconds. That is two thirds of will-it-scale
  `page_fault1`'s 9-17% loss at 2-16 threads, measured by switching the spin
  off (`bench/results/kdclaude/wis-20261115-64cpu/`). The fix is to stop
  spinning once the phase counter has stood still, not to lower the constant:
  the reader-heavy grid profiles live on that spin.
* **Nested delegated rwsem, then `mapping->i_mmap_rwsem`.** `mmap2` opens
  1.28 M sessions and hands every one back at `down_write` of the file
  mapping's rwsem, for 0.78-0.86 of Native. This is the largest single
  measured loss with a known cause; [MMAP_LOCKS.md](MMAP_LOCKS.md) has the
  lock-by-lock analysis and what else would follow from it.

### Task D: API switch and micro/API stage

Status 2026-11-13: the mmap lock is switched (`CONFIG_KDLOCK_MM`,
KERNEL_INTEGRATION 4a) and will-it-scale mmap1 runs on it with delegated
writers: kd/Native 0.98-1.00 at 1-4 threads and 1.06-1.23 at 8-32
(`bench/results/kdclaude/mmap1-20261113/`). Getting there needed one rwsem
fix (holders of the queue mutex spin by time before they sleep).
The syscall-path objects are switchable too (`CONFIG_KDLOCK_API`,
KERNEL_INTEGRATION 4b): files table, OFD lock list, pipe mutex, file
position mutex, tmpfs xattr lock, `uts_sem`. `bench/api_stress.c` drives each
through its real system calls with exact result checks
(`bench/results/kdclaude/api-20261113/`): setfd 1.61 and OFD 2.65 of Native at
32 workers (delegated), pipe/seek at parity or slightly above, xattr 0.90 at
8 workers (no delegation, reader path), uts 2.8-3.3 from the rwsem wait
policy, not delegation. The whole-kernel switch (first bullet) is still not
done; per the minimal-change rule only these objects are converted.


* Apply `integration/kd_linux_map.h`: replace `arch_spinlock_t`,
  `arch_rwlock_t`, `struct mutex`, `struct rw_semaphore` and their API
  (inline variants off, `osq_lock.c` etc. not built). Today only the
  directory is built in; no kernel user calls kd. Verify the whole kernel
  links and boots with it before any timing.
* Then adapt the syscall runners (OFD, setfd, pipe, seek, UTS, xattr) to the
  new kernel; the old kernel adapters are out of scope under the minimal-change
  constraint in the earlier `docs/BENCHMARK_WORKLOADS.md` (tag
  `full-tree-before-cleanup-20261115`), restated in `AGENTS.md` rule 11.
* Prerequisite: Tasks A and B.

Tasks A and B are sequential. C needs both. D can start after A.

## 4. Rules that apply to every task

* Build and run only in the `kdclaude` VM; do not touch the original VM on
  `10.176.26.71` or its files while another agent works there.
* Source edits are made on the host. Do not commit unless asked.
* Take a VM snapshot (`savevm` through the monitor) before the first boot of
  a new kernel and before loading modules for the first time.
* Report every timing with: kernel release, source hash, workers, family,
  profile, execution class, one-vs-many rounds. One round gives no variance
  claim. Strict frequency control is not available on this host.
* No performance claim without a matched Native run; no pooling across
  kernels, source versions or call shells.
* Keep Native control and kd on the same call shell (`kd_bench.c` already
  generates both from the same macro).
* Wording: avoid cybersecurity-associated terms in new names and prose
  (`AGENTS.md`).

## 5. Prepared

| Item | Where |
| --- | --- |
| kdlock-enabled kernel `7.0.0-38-kdclaude1`, **installed, boots** (one-shot; default stays `kdlock1`) | build `/mnt/kdlock-builds/kdc/out` in the VM; logs `/mnt/kdlock-builds/kdc/build*.log` |
| Translator venv (capstone 5.0.7) | `/root/kdvenv` in the VM |
| Image dry run | `jit/kd_dryrun.py` |
| Test bodies for nesting and handback | `nest_spin`, `nest_mutex`, `mix` in `bench/kd_bench.c` |
| Placing kdlock into a tree | `integration/apply_to_tree.sh` |
| Nano workload module (4 families x native/kd, c01/c16, post, write%) | `bench/kd_bench.c`, `bench/kd_bench_uapi.h`, `bench/Makefile` |
| Runner with data oracle and kd counters | `bench/run_nano.py` |
| In-VM checks | `/root/kdc/builtin.sh`, `/root/kdc/build.sh`, `/root/benchcheck.sh` |
| VM start/stop/pin | `/home/eric/vm/qemu-scripts/run_claude_vm.sh` |

Known gaps in the prepared items: there is no spin c08 or hash-table body yet
(only the nano set); the runner has only been used for single rounds.
