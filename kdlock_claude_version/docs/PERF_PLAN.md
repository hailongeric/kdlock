# Performance work plan (nano first, then micro/API)

Status of this directory: tasks A and B below are done (2026-11-11; results
and the fixes they needed are in [BUILD_AND_TEST.md](BUILD_AND_TEST.md)
section 5). The kdlock kernel boots, local and delegated runs of all four
families, two-level nesting and handback keep the data exact. **Nothing has
been measured** (only single rounds). This plan lists what stands between that
state and defensible performance numbers, splits it into tasks, and records
what is already prepared. Known goal/effect differences from the earlier documents are in
[DIFFERENCES.md](DIFFERENCES.md); several of its items are inputs to the tasks
below. It is derived from the existing project documents
(`docs/ROADMAP.md`, `docs/BENCHMARK_WORKLOADS.md`, `docs/PERFORMANCE.md`,
`bench/README.md`, `bench/nano/README.md`); the rules below are theirs unless
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

### Task D: API switch and micro/API stage

* Apply `integration/kd_linux_map.h`: replace `arch_spinlock_t`,
  `arch_rwlock_t`, `struct mutex`, `struct rw_semaphore` and their API
  (inline variants off, `osq_lock.c` etc. not built). Today only the
  directory is built in; no kernel user calls kd. Verify the whole kernel
  links and boots with it before any timing.
* Then adapt the syscall runners (OFD, setfd, pipe, seek, UTS, xattr) to the
  new kernel; the old kernel adapters are out of scope under the minimal-change
  constraint in `docs/BENCHMARK_WORKLOADS.md`.
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
