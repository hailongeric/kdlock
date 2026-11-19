# Interfaces

Everything a user, the translator or a benchmark touches from outside the
kernel code: `/dev/kdlock`, debugfs, kernel parameters, and the benchmark
device. Structures are in `include/kdlock/kd_uapi.h` and
`bench/kd_bench_uapi.h`; the Python mirrors are in `jit/kdjit/kernel.py` and
`bench/run_nano.py`.

## 1. `/dev/kdlock` (misc device, `CAP_SYS_ADMIN`)

| Call | Purpose |
| --- | --- |
| `read()` | drain events (`struct kd_event`, 32 bytes each); never blocks; returns 0 bytes when empty. Producers run under arbitrary locks and do not wake anybody, so the daemon polls |
| `KD_IOC_INFO` | `struct kd_info`: ABI version, address of `kd_jit_exit`, GS-relative addresses of the `kd_cpu` fields generated code uses (`pcpu_task`, `canary`, `stack_top`, `root`, `exit_ip`, `resume`, `aux`, `exit_code`, `anc`), the kernel per-CPU symbols to redirect, and up to 96 `struct kd_sym` (address, class, op, alternative entry) for the lock API |
| `KD_IOC_READ` | copy kernel text/data to user space (the translator's only view of the kernel) |
| `KD_IOC_IMAGE_ALLOC` | allocate executable memory of a given size; returns the address the image will run at and an id |
| `KD_IOC_IMAGE_LOAD` | copy image bytes, make them read-only executable, bind them to a site, publish the entry. Carries the text generation the image was built from: `-ESTALE` if text changed since, `-ENOENT` if the site is not in live text. A refused image is freed |
| `KD_IOC_SITE_DROP` | unpublish a site (image freed after an RCU grace period) |
| `KD_IOC_ENABLE` | global delegation switch (static key) |
| `KD_IOC_TEXT` | for an address: the text region holding it (core kernel text, or one module's text / init text while it is coming), every instruction in that region with an exception-table entry, and the current text generation. Address 0 reads only the generation |

ABI version is `KD_ABI_VERSION` (5; version 4 had a release class and an exit for the clobber entries, removed 2026-11-19); the translator refuses a mismatch.

### Text generation

Module load (`COMING`) and the points where module text disappears (`LIVE`,
when init text is about to be freed, and `GOING`) increment the generation.
When text disappears the kernel drops **every** site, since any image may
contain code copied from that range, clears the request table so busy sites
ask again, and queues `KD_EV_TEXT_GONE`. The translator reads the generation
before it reads symbols and text for a build and passes it to
`KD_IOC_IMAGE_LOAD`.

### Events (`read()`)

| Event | Fields |
| --- | --- |
| `KD_EV_REQUEST` | contended site without an image; repeated every 4096 contended waits while it has none |
| `KD_EV_MISS_CODE` / `MISS_IND` / `MISS_RET` | `ip` = missing address / branch / `ret`, `target` = destination (64 per image) |
| `KD_EV_SITE_OFF` | the site was switched off: handbacks dominated its last 256 executions |
| `KD_EV_TEXT_GONE` | text `[site, ip)` went away; all sites were dropped; `target` = new generation |

### Symbol classes (`struct kd_sym.cls`)

| Class | Meaning for generated code |
| --- | --- |
| `KD_SYM_UNLOCK` | release API: compare `rdi` with the session root before calling |
| `KD_SYM_ACQUIRE` | sleeping-family acquire: always leave generated code |
| `KD_SYM_NESTED` | spin-class acquire: call `alt` (`*_jit`) instead; same fast path, exits `NESTED` when contended |
| `KD_SYM_LOCAL` | never sleeps and acts for the origin by itself (trylocks, reader spin locks and releases, raw acquires): call natively |

A `kd_` function that is not in the list is a frontier for generated code.

### Exit codes (`kd_cpu.exit_code`, low byte = kind, bits 8-15 = `enum kd_op`)

`UNLOCK 1, ACQUIRE 2, MISS_CODE 3, MISS_IND 4, MISS_RET 5, FRONTIER 6,
BUDGET 7, UNLOCK_ANC 8, NESTED 9`; `KD_X_TAIL` (0x10000) marks a release made
by a tail jump.

### Events (`struct kd_event`: type, cpu, site, ip, target)

`REQUEST 1` (contended site without image), `MISS_CODE 2`, `MISS_IND 3`,
`MISS_RET 4`, `SITE_OFF 5`. The ring holds 4096 entries and is **lossy**: when
full the newest event is dropped; a repeated miss is reported again later.

## 2. debugfs `kdlock_stats`

Read-only, `/sys/kernel/debug/kdlock_stats`. One `name value` line each:

| Name | Counts |
| --- | --- |
| `delegation` | global switch state |
| `sessions` | combining sessions that executed at least one waiter |
| `delegated` | sections completed in generated code |
| `handback` | sections returned to their origin unfinished |
| `handback_pinned` | ... while the section had preemption disabled beyond its locks |
| `nested_local` | contended inner locks the executor took itself |
| `nested_delegated` | inner sections advanced by the inner lock's combiner |
| `offered` | waiters queued with an image |
| `plain` | waiters queued without |
| `numa_deferred` | waiters of another node passed over by a session |
| `numa_local` | plain mode, sleepable class: waiters of the queue head's node moved directly behind it (`kd_q_local_first()`) |
| `stop_plain`, `stop_resched`, `stop_handoff`, `stop_ctx`, `stop_budget` | why sessions stopped before the queue was empty |
| `no_spin`, `abandon`, `head_sleep`, `parked`, `handoff` | mutex and rwsem: how waiting ended up off the queue, and releases that took the lock again for a parked waiter |
| `mode_enter`, `mode_exit` | locks switched to delegation mode by a queue head / back to plain mode by a combiner |
| `xchg_offer`, `xchg_taken`, `xchg_declined`, `xchg_retract` | role exchange: combiners that offered themselves after a handback, releases that took the head role over, releases that could not, offers withdrawn because the holder stopped running |
| `era_start`, `era_gate`, `era_claim` | eras of the rw families (ARCHITECTURE 7b): eras started by a queue head, callers that waited for their node's era, waits that ended by taking the era over |

Counters are per-CPU, summed on read, non-atomic and approximate by design.

## 3. Kernel command line

`kd_batch=<n>` (default 4096), `kd_numa=<0|1>` (default 1), `kd_adapt=<0|1>`
(1), `kd_deleg_enter=<n>` (5), `kd_deleg_enter_sleep=<n>` (3),
`kd_deleg_exit=<n>` (2), `kd_xchg=<0|1|2>` (1), `kd_numa_after=<n>` (32),
`kd_rw_era_ns=<ns>` (200000; 0 switches eras off and measures nothing),
`kd_rw_era_press=<n>` (225), `kd_rw_era_drain_ns=<ns>` (5000); meanings in
LOCKS.md 7. All
are also writable at runtime under `/sys/module/kernel/parameters/` (core
params, mode 0644), which is what `bench/run_ab.sh` uses to compare settings
within one boot.

## 4. Benchmark device `/dev/kdbench` (module `bench/kd_bench.ko`)

`KDB_IOC_APITEST` calls every kd lock API variant once on one task and
checks lock state, interrupt flag and preempt count; it returns the number of
failed checks (`run_nano.py --api-test`).

`KDB_IOC_RUN` with `struct kdb_run`: family (`spin, mutex, rwlock, rwsem`, and
the bodies listed below), backend (`native, kd, tclock`),
counters per body (1 to 16), write (or for `nest_*` outer) percentage, post-work
rounds, workers, first CPU, duration in ms. Returns elapsed ns, total ops,
writes, torn reads, counter delta and per-worker ops/writes. One call is one
timed point; the kernel threads are pinned to CPUs `first_cpu ..
first_cpu+workers-1`.

`bench/run_nano.py` wraps it: warmup run, `--repeat` measured runs, JSON line
per point with `ok`, `mops` and the kdlock counter deltas. A point is `ok`
only if every worker progressed, no reader saw unequal counters and the
counters add up to the completed writes.

Test bodies (correctness, not workloads; both backends from the same macro):

| Family | Body |
| --- | --- |
| `nest_spin` | `pct`% take spin A then spin B, the rest take B alone, so B is contended inside A. The outer counter must not change while A is held, also across the inner section |
| `nest_mutex` | the same with a mutex as A |
| `mix` | mutex section that compares `current` (read through a non-inlinable helper) with the task taken before the lock, calls through a function pointer, and in 1/16 each calls `yield()` (frontier) or takes a second mutex (sleeping acquire) |

| `spin_curr`, `mutex_curr` | the spin / mutex body plus one read through `current` |
| `spin_curw`, `mutex_curw` | the same plus `rcu_read_lock(); rcu_read_unlock()`, which with preemptible RCU count in the task structure |
| `ww` (kd only, 2 counters) | two of four ww mutexes in random order under one acquire context, backing off on `-EDEADLK` |
| `spin_raw` | the spin body through `kd_raw_spin_lock` (the plain path alone); with the native backend, the native queued spinlock code on the kd lock object |
| `spin_hb`, `rwlock_hb` | write sections of which every sixteenth meets an instruction with a fault fixup (`copy_from_kernel_nofault`): handed back there |
| `rwsem_hb` | write sections of which every sixteenth calls `yield()` |

For these, `torn_reads` also counts broken outer/`current` checks and any
difference between outer sections run and the final outer counter.

`bench/run_corr.py` runs short points of every family and body with the data
oracle, the API check, and a look at the kernel log for warnings raised
meanwhile.
