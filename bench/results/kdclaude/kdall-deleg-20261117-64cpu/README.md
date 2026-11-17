# Whole-kernel switch: why ww_mutex and rwsem lose, and delegation from an allow list

Done on 2026-11-17, kernel `7.0.0-38-kdall1` #3 (all locks kdlock,
KERNEL_INTEGRATION 4d) and, for the native profile, `7.0.0-38-kdclaude1` #85
with `kd_mm=0`, `kd_api=0`. Host: 64 vCPUs, 2 nodes, 2.7 GHz fixed.

## 1. Why ww_mutex_lock and rwsem_lock lose under locktorture (delegation off)

`lt_diag.sh` runs rwsem_lock, ww_mutex_lock and mutex_lock for 40 s each.
At 10 s into each run it counts context switches for 10 s (`perf stat -a`)
and takes a 5 s flat profile (`perf record -a`, no call graphs). It also
records the kd stat counters across the run. Logs:
`ltdiag-kdclaude1-native.log`, `ltdiag-kdall1.log`. These are single runs
in different boots. The write totals below are indicators; the profiles
and counters are the evidence.

### ww_mutex: waiters never spin, so the wait lock becomes the bottleneck

| | native | kdall1 |
|---|---|---|
| writes in 40 s | 28.7 M | 7.9 M |
| context switches in 10 s | 0.55 M | 1.02 M |
| profile | `osq_lock` 81%, `kvm_vcpu_is_preempted` 12% | `kd_q_lock_plain` 59%, `kd_mutex_wake_matching` 7.9%, `kd_mutex_sleep` 2.8%, `kd_ww_waiter_dies` 2.4% |
| kd counters | | parked 1 610 214, handoff 129 414 |

The native ww_mutex waits in its optimistic-spin queue (`osq_lock`) while
the owner runs, as a plain mutex does. kd_ww_mutex.c never spins. A
contended `kd_ww_mutex_lock()` tries the lock once and then calls
`kd_mutex_sleep()`, the parked path. That has three consequences:

- Every contended acquisition parks, so there are 40 000 `schedule()` calls
  per second.
- Every parked waiter takes the mutex's internal wait lock again at each
  wakeup.
- While any waiter sleeps, each acquisition runs `kd_ww_set_ctx()`, which
  walks the whole waiter list under that wait lock with interrupts off
  (`kd_mutex_wake_matching()`).

With about 127 sleepers the walk touches 127 waiter records on other
tasks' stacks. Together, the wait lock is where 59% of the time goes
(`kd_q_lock_plain` is its slow path).

The native code walks its waiters as well (`__ww_mutex_check_waiters`).
But its waiters spin, so few of them are asleep. The root cause is the
missing spin phase, and the walk cost follows from it.

A fix would let a ww waiter spin before it parks. It would spin while the
owner runs, stopping when `kd_ww_must_back_off()` says it would have to
back off, which is what native `ww_mutex_spin_on_owner()` does. This is
not implemented here. ww mutexes are never delegated
(kd_ww_mutex.c), so delegation does not change this.

### rwsem: without combining, every writer opens a reader phase

locktorture's rwsem readers hold the lock for 50 ms (`mdelay(long_hold / 2)`).
Its writers' sections are empty. So the write rate counts how many
writes fit between reader phases.

| | native | kdall1 |
|---|---|---|
| writes in 40 s (min per writer) | 894 266 (6 558) | 496 621 (1 617) |
| context switches in 10 s | 69 658 | 16 609 |
| profile | `delay_halt_tpause` 95% (readers' mdelay), `osq_lock` 3.4% | `delay_halt_tpause` 93% |
| kd counters | | rd_queue 1 725, rd_behind 457, head_sleep 548, parked 3 866 |

kd's reader admission (kd_rwsem.c, "D11") registers a reader that meets an
active writer behind that writer. When the writer leaves, every registered
reader enters together, and the next writer waits for that batch. With
delegation the "writer" is a combiner's whole session, so one reader
phase follows many writes. With delegation off there are no sessions, so
**each single write is followed by a reader phase** of up to 50 ms. In
the native rwsem, readers that arrive while a writer holds the lock wait
in the FIFO wait list behind queued writers. Spinning writers also take
a writer-owned lock before the waiting readers (`osq_lock` 3.4%).

The test that tells the two explanations apart is `rwsem-rspin-kdall1.log`
(`rw_rspin.sh`). It changes `kd_rwsem_rspin_ns`, how long a reader waits
outside `->m` before it queues on `->m` in FIFO order with the writers.
Runs alternate in one boot, 40 s each:

| kd_rwsem_rspin_ns | writes | rd_behind | rd_queue |
|---|---|---|---|
| 50 000 (default) | 539 457, 535 079 | 479, 459 | 2 090, 2 169 |
| 1 000 000 000 | 2 134, 1 718 | 3 731, 4 223 | 996, 995 |

Readers that keep waiting outside register behind each writer, and
writes fall by a factor of 250. With the default bound about half the
readers end up in `->m`'s FIFO queue, which interleaves them with the
writers. That is the only thing that keeps writes at 55-60% of native.
So the loss is the per-writer reader phase. It is not the readers' queue
on `->m`, which was the first guess and which this test disproves.

The minimum writer (1 617 against 6 558) is the writer that parks in `->m`
(`head_sleep` 548). It is woken one at a time while spinning writers pass
it.

In short, this rwsem policy assumes combining sessions. Delegation is what
supplies them (section 2). Without delegation, under 50 ms read sections,
it favours readers far more than native does.

## 2. Delegation from an allow list

`jit/kd_daemon.py --allow FILE` builds images only for sites whose function
matches a pattern in FILE. Every other site keeps queueing plainly. The
lists are in `bench/allow/`:

- `api.txt`: the users of the six CONFIG_KDLOCK_API locks, found with an
  empty list (`disc.sh`, `kdd_disc.log`).
- `torture.txt`: locktorture.

There is no list for mmap_lock in this run. When it was made, AGENTS.md
still required MM bodies to run on their own task. That rule came from the
earlier implementation and was removed afterwards, on the same day. A first
A/B run used an `mm.txt` list with `vm_mmap_pgoff`, `__vm_munmap`,
`__do_sys_brk` and `do_mprotect_pkey`. That run livelocked in a delegated
`brk()` (section 3), and its numbers are not used. The serial log, the
daemon log and the partial results are in `softlockup-brk/`. Section 5
delegates brk, mmap and munmap with the fix of section 3.

### Results: delegation off against on, in one boot

`deleg_ab.sh`, kdall1 #3, in one boot after the translator fix of section 3.

- **Daemon:** `--allow` with `api.txt` and `torture.txt`, starting from empty
  knowledge.
- **Learning passes:** two passes with the daemon on, then three rounds that
  each run every workload once with the daemon off and once with it on.
  The order alternates (r1 off first, r2 on first, r3 off first).
- **Workloads:**
  - `api_stress`: 5 s per run, data checked, ops/s.
  - will-it-scale threads model: 5 s, ops/s average.
  - locktorture: 20 s, total writes of 128 writers, plus readers for rwsem.
- **"delegated" and "handbacks":** the changes of those two kd stat
  counters over one "on" run.
- **Files:** `ab.txt` (raw lines), `kdd_ab.log` (daemon log), and
  `ab_summary.py`, which produced the table.

| workload | threads | off (r1, r2, r3) | on (r1, r2, r3) | on/off (medians) | delegated per run (median) | handbacks per run (median) |
|---|---|---|---|---|---|---|
| api setfd | 16 | 1.75 M, 1.79 M, 1.79 M | 3.39 M, 3.76 M, 3.47 M | **1.94** | 19.3 M | 0 |
| api setfd | 64 | 2.04 M, 2.02 M, 2.17 M | 5.97 M, 5.92 M, 6 M | **2.93** | 33.7 M | 0 |
| api ofd | 16 | 1.49 M, 1.39 M, 1.52 M | 2.93 M, 2.58 M, 2.61 M | **1.76** | 19.6 M | 0 |
| api ofd | 64 | 1.24 M, 1.16 M, 1.13 M | 3.32 M, 3.33 M, 3.31 M | **2.87** | 25 M | 0 |
| api pipe | 16 | 525 k, 530 k, 522 k | 472 k, 474 k, 478 k | **0.90** | 1.49 M | 1560 |
| api pipe | 64 | 457 k, 484 k, 479 k | 461 k, 453 k, 455 k | **0.95** | 1.49 M | 536 |
| api seek | 16 | 1.09 M, 1.15 M, 1.18 M | 1.2 M, 1.16 M, 1.2 M | **1.05** | 0 | 806 |
| api seek | 64 | 957 k, 945 k, 946 k | 958 k, 955 k, 1.04 M | **1.01** | 0 | 318 |
| api uts | 16 | 3.15 M, 3.15 M, 3.18 M | 3.88 M, 3.79 M, 3.91 M | **1.23** | 2.44 M | 111 k |
| api uts | 64 | 2.79 M, 2.79 M, 2.79 M | 4.45 M, 4.46 M, 4.49 M | **1.60** | 4.08 M | 50 k |
| api xattr | 16 | 1.67 M, 1.65 M, 1.69 M | 1.74 M, 1.72 M, 1.72 M | **1.03** | 0 | 0 |
| api xattr | 64 | 1.59 M, 1.62 M, 1.56 M | 1.71 M, 1.67 M, 1.67 M | **1.05** | 0 | 0 |
| wis mmap1 | 16 | 319 k, 313 k, 309 k | 318 k, 306 k, 299 k | **0.98** | 0 | 0 |
| wis mmap1 | 64 | 277 k, 275 k, 279 k | 271 k, 273 k, 273 k | **0.99** | 0 | 0 |
| wis mmap2 | 16 | 338 k, 361 k, 344 k | 352 k, 346 k, 335 k | **1.00** | 0 | 0 |
| wis mmap2 | 64 | 312 k, 311 k, 319 k | 310 k, 310 k, 306 k | **0.99** | 0 | 0 |
| wis brk1 | 16 | 772 k, 746 k, 782 k | 765 k, 760 k, 754 k | **0.98** | 0 | 0 |
| wis brk1 | 64 | 816 k, 725 k, 790 k | 818 k, 811 k, 775 k | **1.03** | 0 | 0 |
| torture rwsem_lock | 128 | 228 k, 232 k, 216 k | 247 k, 220 k, 202 k | **0.96** | 30 k | 173 |
| torture mutex_lock | 128 | 23.7 M, 20.8 M, 26.1 M | 38 M, 38.9 M, 34.7 M | **1.60** | 25.9 M | 1250 |

No kernel complaint in the whole run, and every `api_stress` data check
passed (`ok`).

**Gains.** The users of the file-table lock (setfd: `set_close_on_exec`,
`alloc_fd`, `file_close_fd`) and of the file-lock lock (ofd:
`posix_test_lock`, `posix_lock_inode`) gain 1.8-1.9x at 16 threads and
2.9x at 64. The ranges of off and on do not overlap. `sethostname` (uts)
gains 1.23x and 1.60x. Its section reaches `x2apic_send_IPI` (a wakeup that
sends an interrupt) in some runs, which is a frontier, so 4% (16 threads) and
1% (64 threads) of its sections are handed back. locktorture's mutex gains 1.60x.

**Losses.** pipe loses 10% at 16 threads and 5% at 64, with no overlap at
16. Its read and write sections copy to or from user memory
(`_copy_to_iter`, `_copy_from_iter`), which is a frontier. So they are
handed back until the kernel switches the site off (`switched off` in
`kdd_ab.log`, once per daemon start). What stays delegated is the short
sections, about 1.5 M per run. The handbacks before each switch-off, and
the remaining sections, cost more than delegation saves.

**No change, because nothing was delegated:**

- **MM sites:** brk, mmap and munmap were refused by the allow list, and
  will-it-scale stays within 0.98-1.03.
- **xattr:** its contended lock is taken in `vfs_setxattr`, which is not on
  the list.
- **seek:** the `fdget_pos` site is handed back at
  `begin_current_label_crit_section` and switched off.

These rows show how far "on" and "off" differ with no delegation at all:
up to 5% (xattr at 64), so smaller differences elsewhere are not results.

**rwsem under locktorture** is not helped: 30 k sections delegated, and
0.96 lies within the spread. Section 1's loss against native, a reader phase
after each write, therefore remains in 20 s runs. Why only about one write
in seven is delegated is in section 4: it comes from the 20 s window after
each module load, and from writes that never wait behind another writer.

The handbacks at `preempt_schedule_thunk+0x11` (52 logged, for a site in
locktorture's module text) are the case left out of the static-call frontier
(section 3): `preempt_enable()` reached count 0 in a copied section, and
the thunk's `preempt_schedule` call ended it.

`trial.sh`, `trial.out` and `kdd_trial.log` are from the earlier trial runs
before the A/B run. Two of them delegated mmap_lock sections and the first
one ran two daemons at once, so they are kept only as a record.

## 3. Soft lockup in a delegated brk(): a scheduling point patched out of the text

In the first A/B run, `brk1_threads -t 16` (learning pass 2, daemon on)
never finished. At 3 684 s of uptime the kernel reported:

    watchdog: BUG: soft lockup - CPU#0 stuck for 2239s! [brk1_threads:49619]
    watchdog: BUG: soft lockup - CPU#11 stuck for 2242s! [brk1_threads:49630]

Registers and memory were read from the stopped guest through the QEMU
monitor (`mon.py`, `samples.txt`: 40 samples of CPU 15). The image was
disassembled from a memory dump (`image-brk-excerpt.dis`).

- **CPU 15** ran a brk1 thread as a combiner. It was executing another
  thread's delegated `__do_sys_brk` section, a shrink that unmaps:
  `unmap_page_range` → `zap_pmd_range` → `zap_pte_range`. All samples are
  in one loop, and the address (R15 = `0x55ba27d78000`) never moves.
  `zap_pte_range()` takes the PTE lock, finds `need_resched()` true, and
  breaks before zapping a single entry. `zap_pmd_range()` steps back
  (`pmd--`), calls `cond_resched()`, and retries the same address. The
  thread flags were `0x13`, which includes `TIF_NEED_RESCHED`. The preempt
  count was `0x21`.
- **CPUs 0 and 11** were brk1 writers in `kd_wait_sleepable+0x193`, queued on
  the same mm's mmap_lock (`mm+0x190`, the mm of CPU 15's section).

Natively this loop exits by being scheduled. With `preempt=full` (the
PREEMPT_DYNAMIC default), `cond_resched()` is a static call patched to
return 0. Its inline call sites are rewritten to `cs cs cs xor %eax,%eax`,
four of them in `unmap_page_range` alone. The code relies on preemption at
the PTE lock's `preempt_enable()` instead. An executor runs the whole
session with preemption off, so neither happens: `need_resched` is never
cleared, the loop never advances, and the session holding mmap_lock never
ends.

The translator's frontier list did have `__cond_resched`. But at run time no
call was left to find: the text held an `xor`. Step 2 of the plan, images
that follow runtime text patching, covers text changed *after* an image was
built. Here the text is stable, and the patched form is the problem.

**Fix** (`jit/kdjit/kernel.py`, `jit/kdjit/translator.py`), in its final
form after the MM runs of section 5:

- `KernelView.static_call_sites(name)` reads the kernel's own static-call
  site tables, starting from the key `__SCK__name`. It covers the core
  kernel and every module, and leaves out init text.
- Every inline `cond_resched` site (policy `frontier_static_call`) is copied
  behind a test of the origin's `TIF_NEED_RESCHED`, read through the
  redirected task: `mov rax, gs:[kd_cpu.task]; test byte [rax], 0x10`.
  - If the flag is set, the site is a frontier exit, and the origin takes
    over there and is scheduled as usual.
  - If it is clear, the copy runs the site's own `xor`, as native
    `cond_resched()` does when nothing needs to run.
  - A site patched to a real call stays a frontier.
  - The flag word and bit are those of the kernel's own `need_resched()`
    in `zap_pte_range()`: `mov %gs:current_task,%rax; mov (%rax),%rax;
    test $0x10,%al`.
- `__SCT__cond_resched` is a frontier by name.

**Versions that were measured and changed:**

- **The first version** made the `cond_resched` and `might_resched` sites
  unconditional frontiers. `sc_check.py` / `sc_check.out` are its static
  check, done without loading any image:
  - 644 `cond_resched` and 1 189 `might_resched` sites, all holding the
    5-byte `xor`;
  - the four in `unmap_page_range` among them (`+0x38d` is the `xor` at
    `0xffffffff817be53d` in the dumped text);
  - the images for `__do_sys_brk` and for the `unmap_page_range` lock
    sites end there.
- **`might_resched` was dropped.** It comes from `might_sleep()` and
  `might_alloc()`. Nothing waits there for `need_resched` to clear, and as
  a frontier it ended every delegated `mmap()` and `munmap()` at its first
  slab allocation (`kmem_cache_alloc_noprof+0x29d`;
  `mm/ab-mightresched-partial.txt`, `mm/kdd-mightresched-partial.log`).
  With voluntary preemption its sites call `__cond_resched`, a frontier by
  name.
- **The test was added.** An unconditional frontier at `cond_resched`
  handed back about half of all brk1 sections at `unmap_page_range+0x38d`.
  brk1 at 64 threads fell to 0.54 of no delegation (`mm/run2-decodefail/`).
  With the test it is at 1.10 (section 5).
- **The `preempt_schedule` sites** of `preempt_enable()` were never
  included. They are reached only at preempt count 0, and their thunk
  already ends at the `preempt_schedule` frontier.

The livelock did not come back:

- brk, mmap and munmap ran delegated in 8 passes of will-it-scale at 16,
  32 and 64 threads (section 5).
- `mm_stress` ran 30 s at each of 16, 32 and 64 threads. It unmaps touched
  memory, so the zap loop and its `cond_resched` points really run.
- There was no kernel complaint in any of these.

These runs do not show that a delegated section met `need_resched` set at
a `cond_resched` point: the `hb_frontier` counter does not say which
frontier was met.

Also open: any loop that waits for `need_resched()` to clear without passing
a `cond_resched()` would still spin in an executor. A bound on a session's
run time would cover that case as well. It is not implemented.

## 4. Why few locktorture rwsem writes are delegated

`rw_deleg.sh rwsem_lock 80 off|on` runs locktorture's rwsem test for 80 s,
first with the daemon off, then with it on (`torture.txt` only), in the same
boot as section 5. It samples every kd counter, and locktorture's own write
total, every 5 s. Files: `rwsem-ramp/rwsem_lock-{off,on}.log` (counters),
`rwsem-ramp/rwsem_lock-on.kdd` (daemon). The write totals per 5 s are
locktorture's `stat_interval=5` lines; they are summarised below.

| 80 s | writes | queued behind a writer (`plain` + `offered`) | delegated |
|---|---|---|---|
| off | 1.006 M | 188 k (19%) | 0 |
| on | 1.183 M | 561 k (47%) | 497 k (42% of writes, 89% of queued) |
| on, first 20 s | 218 k | 64 k (29%) | 48.5 k (22%) |
| on, first 5 s | 46 k | 1 k | 0 |

Three things limit it.

- **Only writes that wait behind another writer can be delegated.** A write
  that finds the lock free, or that waits at the head of the queue for the
  readers to leave, runs its own section. That is the session's own section,
  not a delegated one. Locktorture's 64 readers hold the lock for 50 ms each,
  so most writes are of that kind. Without delegation, only 19% of writes
  queue behind another writer at all.
- **Each load of the module starts from no knowledge.** The text is new, so
  the site has to be learned again. In order, the daemon needs:
  - the return of `torture_rwsem_down_write` into `lock_torture_writer`
    (`MISS_RET`);
  - the indirect call to `torture_rwsem_write_delay` (`MISS_IND`);
  - the indirect call to `torture_rwsem_up_write` (`MISS_IND`);
  - and a rebuild of an image of about 8 000 instructions after each one.
  Nothing is delegated in the first 5 s, and only 5.6 k sections are in the
  next 5 s. A 20 s run, as in the A/B of section 2, spends a large part of
  its time here. It sees 22% of writes delegated at best; the A/B measured
  14% (30 k of 220 k).
- **Once learned, the queue is served.** 89% of queued writes run delegated.
  Queueing itself grows with delegation (47% of writes against 19%): a
  session holds the lock longer, so more writers arrive while it runs.
  Sessions grow from about 15 sections (5-10 s) to 40-100. The delegated
  count per 5 s swings between 15 k and 74 k with the reader phases.

The write totals (1.18 M on against 1.01 M off) are one run each, so they
are an indicator, not a result. A comparison of delegation on and off for
this test needs runs of 80 s or more, several rounds, and the module loaded
once per round. A locktorture-specific fix would be keeping knowledge of
module sites across reloads, keyed by module and offset. Kernel lock users
do not need it: their text stays.

## 5. Delegating the mmap lock: brk, mmap and munmap

`deleg_mm.sh`, kdall1 #3, in the same boot as section 4, with the final
translator of section 3.

- **Daemon:** `--allow bench/allow/mm.txt` (`__do_sys_brk`, `vm_mmap_pgoff`,
  `__vm_munmap`), starting from empty knowledge. The images left loaded
  from earlier runs are dropped first.
- **Passes:** two learning passes, then three rounds with the daemon off
  and on, alternated as in section 2.
- **Workloads:** will-it-scale threads model, 5 s per run.
- **Files:** `mm/ab.txt` and `mm/kdd.log`. The handback causes per run
  (`hb_*`) are in the lines.

| workload | threads | off (r1, r2, r3) | on (r1, r2, r3) | on/off (medians) | delegated per run (median) | handbacks per run (median) |
|---|---|---|---|---|---|---|
| wis mmap1 | 16 | 285 k, 290 k, 282 k | 368 k, 368 k, 378 k | **1.29** | 8.11 M | 106 |
| wis mmap1 | 32 | 288 k, 240 k, 283 k | 375 k, 378 k, 370 k | **1.32** | 8.22 M | 53 |
| wis mmap1 | 64 | 262 k, 259 k, 265 k | 311 k, 309 k, 308 k | **1.18** | 6.72 M | 13 |
| wis mmap2 | 16 | 300 k, 301 k, 307 k | 386 k, 362 k, 373 k | **1.24** | 8.13 M | 96 |
| wis mmap2 | 32 | 312 k, 301 k, 299 k | 371 k, 371 k, 370 k | **1.23** | 8.17 M | 10 |
| wis mmap2 | 64 | 271 k, 271 k, 270 k | 304 k, 307 k, 300 k | **1.12** | 6.71 M | 10 |
| wis brk1 | 16 | 640 k, 655 k, 663 k | 895 k, 1.07 M, 1.06 M | **1.61** | 11.5 M | 261 |
| wis brk1 | 32 | 667 k, 657 k, 664 k | 1.05 M, 1 M, 951 k | **1.51** | 11.2 M | 28 |
| wis brk1 | 64 | 725 k, 715 k, 703 k | 788 k, 887 k, 690 k | **1.10** | 8.45 M | 11 |

No kernel complaint in the whole run.

- **Gains with no overlap of off and on:** mmap1 and mmap2 at every thread
  count, and brk1 at 16 and 32 threads.
- **brk1 at 64 threads:** the median is 1.10, but the runs overlap (on
  690-887 k, off 703-725 k). That point is not a result.
- **Nearly every section that waits is delegated** (delegated is within
  0.04-0.7% of `offered`). Handbacks are 10-261 per run.
- **What these tests do not cover:** they do not touch the memory they map,
  so an unmap here finds no page and needs no TLB flush.

**The runs before this one**, kept as a record, each found a defect:

- **`mm/ab-mightresched-partial.txt`**, stopped after two points: the
  `might_resched` frontier (section 3).
- **`mm/run2-decodefail/`**, complete, but delegating with stale images.
  - **The defect:** the translator decoded the learned code roots before
    the site itself. With 20-60 roots learned, they used up the budget of
    60 000 instructions before the site was reached. The build then failed
    ("cannot decode site"), the daemon gave the site up, and the kernel
    kept running its old image.
  - **When it happened:** for the mmap site in the first learning pass, and
    for the brk site from round 1 on.
  - **The fix:** the site is now decoded first, and the learned roots get
    the budget that is left.
  - **Its numbers:** brk1 0.54-0.94 and mmap2 0.87-0.92. They come from
    that defect and from the unconditional `cond_resched` frontier, and are
    not used.

**Data check.** `mm_check.sh` runs `bench/mm_stress.c` with the same
allow list and the daemon on (`mm/check.txt`, `mm/check.kdd`).
`mm_stress` is data-checked: every page each thread wrote is checked, and
it exercises mmap, munmap, mprotect, mremap, brk through large malloc,
and fork.

| threads, 30 s | operations | pages checked | forks | result | delegated | handed back (frontier / miss) |
|---|---|---|---|---|---|---|
| 16 | 57 073 | 14.7 M | 7 171 | ok | 1 683 | 3 487 (3 003 / 484) |
| 32 | 59 721 | 15.4 M | 4 692 | ok | 2 973 | 6 034 (6 029 / 5) |
| 64 | 47 465 | 12.2 M | 2 478 | ok | 2 466 | 3 528 (3 528 / 0) |

No kernel complaint. Here few sections run from an image: of 46-67 k
waiters that published a section per run, 5-9 k were run from an image.
Most of those were handed back, at two frontiers:

- the TLB flush of munmap (`tlb_flush_mmu_tlbonly`), because these unmaps
  free touched pages;
- `__vma_start_exclude_readers`, which waits for per-VMA-lock readers
  (page faults) to leave a VMA before it is changed.

Both act for the origin's CPU or task, so the handback is required. This
test therefore checks the handback path in the middle of MM sections more
than delegated execution. A workload that touches memory and gains from MM
delegation would need the TLB flush delegated, which is outside what a
section may do on another CPU today.
