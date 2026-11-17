# Whole-kernel switch: every lock is a kdlock, delegation off

Step 1 of the order of work in docs/KERNEL_INTEGRATION.md 4c, done on
2026-11-17: a kernel whose spinlock_t, raw_spinlock_t, rwlock_t, struct mutex,
struct ww_mutex and struct rw_semaphore all go through kdlock
(`CONFIG_KDLOCK_ALL`, `integration/apply_all.py`, KERNEL_INTEGRATION 4d),
built, booted and tested without the translator, so every lock is a plain
kd queued lock.

| | |
|---|---|
| kernel | `7.0.0-38-kdall1` `#3 SMP PREEMPT_DYNAMIC Tue Nov 17 03:28:38 UTC 2026`, tree `/mnt/kdlock-builds/kda` (pristine 7.0.0-38 source + `apply_to_tree.sh`), configuration of kdclaude1 #85 with `KDLOCK_ALL=y`, `KDLOCK_MM`, `KDLOCK_API`, `PARAVIRT_SPINLOCKS`, `DETECT_HUNG_TASK_BLOCKER`, `KDLOCK_CLOBBER_ENTRY` off, `LOCK_TORTURE_TEST=m`, `WW_MUTEX_SELFTEST=m` |
| build | vmlinux, bzImage and all 6 707 modules of the Ubuntu configuration, no compile error, no new warning (the two other warnings of the log, apparmor `tmp` and the maple tree frame size, are in the kdclaude builds as well) |
| reference | `7.0.0-38-kdclaude1` #85, daemon stopped, `kd_mm=0`, `kd_api=0`: native locks. A different boot and a different kernel, so the rates below are indicators, not performance results |
| host | 64 vCPUs as 2 nodes of 32, fixed at 2.7 GHz |
| snapshot | `pre-kdall1-boot` (internal, both disks), taken before the first boot |

## Is every lock switched?

`calls-lock.txt`: direct call and jump targets in the kdall1 vmlinux
(`objdump -d`), lock symbols only. 29 318 go to `kd_*` entries; 2 545 to the
generic `_raw_spin_*` layer of raw spinlocks, which takes the kd queue
algorithm through `kd_arch_spin_lock()`; 125 to the `ww_mutex_*` and 10 to
`mutex_init_generic` functions of `kernel/kd_all.c`, which are kd operations;
the rest are the counting semaphore (`down_interruptible` and others; native,
built on a raw spinlock). Nothing calls `queued_spin_lock_slowpath`, the qrwlock
slow paths, or a native mutex or rwsem function: `mutex.c` and `rwsem.c` are
not built, and the compiler rejected every read of a native mutex or rwsem
field (4d lists the three it found).

## Results

Files: `kdall1.log` (the test script `kda_test.sh` on kdall1),
`kdclaude1-native.log` (the same on kdclaude1), `kdclaude1-torture.log`
(locktorture and test-ww_mutex on kdclaude1, built as external modules by
`extmod.sh`, run by `nat_torture.sh`), `*-wwcount.txt` (`wwcount.py`),
`corr-kdall1.jsonl`.

| check | kdall1 | kdclaude1 (native) |
|---|---|---|
| boot to `multi-user`, `systemctl is-system-running` | running, no kernel complaint | (degraded: logrotate.service, unrelated) |
| locktorture, 60 s per type, 128 writer threads (64 + 64 readers for rw types) | all 11 lock types `SUCCESS`; `lock_busted` (broken on purpose) `FAILURE` | the same |
| test-ww_mutex | wound-wait stress "failed with -35" in 6 of 6 loads | the same in 3 of 3 loads |
| `api_stress` (data-checked syscalls: setfd, ofd, pipe, seek, uts, xattr; 16 and 64 threads, 20 s) | 12/12 ok | 12/12 ok (setfd at 64 after raising `ulimit -n`) |
| will-it-scale, 7 tests x threads/processes, 64 workers, 5 s, page contents checked | 14/14 ok | 14/14 ok |
| defconfig kernel build, `-j64` | ok, 58.3 s | ok, 58.4 s |
| `run_corr.py`, bench module built against kdall1, backends native and kd | 442 points, 0 failed, API check 0 failed, 0 kernel complaints | (build #85: 586 points incl. TCLock, clean) |
| uptime, shutdown | 27 min, then two more boots; clean reboot each time (serial log) | |

In kdall1 the bench module's "native" backend is the kernel's own lock API,
so both of its backends are kdlock there.

The only kernel log complaints on kdall1 are the two `WARNING`s that
`lock_busted` is designed to produce (`locktorture.c:934`, a second writer
inside the lock); kdclaude1 shows the same warning for it.

**test-ww_mutex** fails the same way on both kernels. `stress_inorder_work`
reports an `-EDEADLK` that arrives after its 2 s timeout instead of retrying
it, and almost every round sees one. The message is `pr_err_once`, so the
die class's failure is not printed and the module reports "All ww mutex
selftests passed" anyway. The counting copy (`wwcount.py`) shows it for both
classes and both kernels:

| per class, 3 loads | rounds in 2 s | rounds with -EDEADLK | workers ending on -EDEADLK (of 128) |
|---|---|---|---|
| kdclaude1, wound-wait | 18 594-19 790 | 95% | 95-107 |
| kdclaude1, wait-die | 21 718-32 755 | 95-97% | 8-106 |
| kdall1, wound-wait | 2 069-3 010 | 47-63% | 8-21 |
| kdall1, wait-die | 1 902-4 066 | 41-74% | 2-64 |

kd applies wait-die to both classes (kd_api.h), so its two rows are the same
algorithm. It backs off less often but completes 6-17 times fewer rounds.

### Indicators across boots (not performance results)

Single runs, different boot, different kernel (kdclaude1 carries the
`KDLOCK_MM`/`KDLOCK_API` switch branches); kdall1/kdclaude1:

| workload | ratio |
|---|---|
| locktorture writes: spin_lock, spin_lock_irq, raw_spin_lock, raw_spin_lock_irq | 0.99, 1.05, 0.93, 1.14 |
| locktorture writes: rw_lock, rw_lock_irq, mutex_lock | 0.97, 0.97, 1.00 |
| locktorture writes: **ww_mutex_lock** | **0.31** (12.0 M / 39.3 M) |
| locktorture writes: **rwsem_lock** | **0.50** (0.69 M / 1.38 M); min writer 4 010 against 14 614 |
| locktorture writes: rtmutex_lock, percpu_rwsem_lock (not kd locks; raw spinlocks inside) | 1.05, 0.90 |
| api_stress 16 / 64 threads: setfd, ofd, pipe, seek, xattr | 1.05/0.92, 1.17/1.16, 1.13/1.15, 1.28/1.11, 1.03/0.98 |
| api_stress uts 16 / 64 | 2.93 / 3.21 |
| will-it-scale threads: page_fault_shared1/2/3, page_fault1 | 1.00, 0.88, 1.15, 1.28 |
| will-it-scale threads: mmap1, mmap2, brk1 | 1.91, 1.72, 1.92 |
| will-it-scale processes: page_fault_shared1/2/3, brk1 | 0.95, 0.96, 0.95, 0.97 |
| will-it-scale processes: page_fault1, mmap1, mmap2 | 1.28, 1.24, 1.27 |
| defconfig kernel build | 1.00 (58.3 s / 58.4 s) |

Two losses are large enough to stand out of any noise: ww_mutex (0.31, and
the ww stress rounds above) and rwsem under locktorture (0.50, with one
writer thread falling far behind). The processes-model gains for
page_fault1, mmap1 and mmap2, where nothing is shared, say the two kernels
differ in more than the locks of the workload; that is why none of these
ratios is a result. A matched comparison needs native and kd in one boot,
which a whole-kernel switch cannot provide; it would need two kernels
differing only in `KDLOCK_ALL`, alternated over several boots.
