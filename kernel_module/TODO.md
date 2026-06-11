# kdlock — Task List & Known Gaps

Last updated: 2026-06-11

## Implemented

- [x] Raw spinlock delegation via kd_spinlock.c (ported from TCLocks komb.c)
- [x] Spinlock JIT sandbox execution via kd_exe_on_call_hl()
- [x] kd_mutex delegation protocol (ported from TCLocks komb_mutex.c)
- [x] Mutex JIT sandbox execution via kd_exe_on_call_hl() in execute_cs()
- [x] Mutex → kd_mutex shadow table mapping (kd_lock.c)
- [x] Shadow stack per-CPU setup (kd_spinlock_init / kd_mutex_init_percpu)
- [x] Character device /dev/kd_dev for daemon ↔ kernel communication
- [x] Userspace daemon (daemon.c) — polls /dev/kd_dev, drives disassem
- [x] Dynamic translation pipeline (disassem/ — miasm-based)
- [x] Assembly wrapper (include/wrapper.S) for JIT sandbox context save/restore
- [x] Test module (klock_module.c) with 6 benchmark modes
- [x] Userspace benchmark driver (bench/klock_test.c)
- [x] Futex delegation engine in kd_lock.c (new_futex_wait / new_futex_wake)
- [x] Hot-uaddr promotion tracking (count_uaddr_cnt / check_uaddr_state)
- [x] int3 runtime call redirection (__kd_do_int3)
- [x] Batch combining (kd_combiner_batch_size / kd_mutex_batch_size)
- [x] Dynamic end_point resolution via kallsyms_lookup_name (exe.c)
- [x] Module exit race protection with synchronize_rcu() (kd_main.c)
- [x] lock_addr[] overflow protection (kd_spinlock.c, kd_mutex.c)
- [x] Shadow stack NULL safety check in kd_mutex_lock_slowpath_asm

## Recently Fixed Bugs

- [x] **Mutex delegated flag race** — `__kd_mutex_unlock` cleared `delegated=0`,
      causing subsequent unlocks to call `origin_mutex_unlock` instead of
      `_kd_mutex_unlock`, leaving the kd_mutex permanently locked. Fixed by
      keeping `delegated` as a one-way latch.
- [x] **Mutex count leak** — `curr_node->count--` in `__kd_mutex_lock_slowpath`
      decremented `nodes[idx].count` instead of `nodes[0].count`. After each
      lock/unlock cycle, `nodes[0].count` monotonically increased, causing
      subsequent operations to use wrong node indices. Fixed by decrementing
      `this_cpu_ptr(&kd_mutex_nodes[0])->count`.
- [x] **Mutex regs.sp not propagated** — `kd_mutex_lock_slowpath_asm` writes
      `regs.sp` to `nodes[0]`, but the actual waiter is `nodes[idx]`. When
      idx > 0, the combiner read uninitialized `regs.sp` from `nodes[idx]`,
      loading callee-saved registers from garbage addresses. This corrupted
      `local_shadow_stack_ptr` on other CPUs → RSP=0 double fault.
      Fixed by copying `regs.sp` from `nodes[0]` to `nodes[idx]`.
- [x] **run_combiner failure handling** — delegation failure marked waiter as
      completed and left it spinning. Fixed: on failure, hand lock to the
      waiter without marking completed.
- [x] **run_combiner NULL deref** — `next_node->locked = false` when
      `next_node` could be NULL. Fixed with NULL check.
- [x] **Mutex tail cmpxchg type mismatch** — compared node pointer vs encoded
      u32 tail value. Fixed to compare encoded tail.

## Near-term (correctness & stability)

- [ ] **Test mutex delegation end-to-end** — run mode 3/4/5 benchmarks
      with kdlock_km loaded and verify no hangs, OOO, or corruption.
- [ ] **Avoid creating shadow entries on the unlock path** — when
      __kd_mutex_unlock is called for a never-delegated mutex,
      get_kd_mutex_shadow creates a useless entry that permanently occupies
      a table slot.  Either skip creation on unlock, or add a periodic GC.
- [ ] **Verify nested mutex delegation** — test mode 4 (nested mutexes) to
      confirm the lock_addr[] tracking and OOO detection work correctly with
      the JIT sandbox.

## Medium-term (features & completeness)

- [ ] **Enable NUMA_AWARE in combiner.h** — currently commented out.
      Test with multi-socket config and re-enable.
- [ ] **Enable KD_SPIN_STATS / KD_MUTEX_STATS** — add counter tracking for
      combiner_count, waiter_combined, OOO unlocks, batch sizes.
- [ ] **Support for rwsem delegation** — TCLocks has komb_rwsem.c; kdlock
      could add kd_rwsem.c following the same port pattern.
- [ ] **Module parameter for batch sizes** — expose kd_combiner_batch_size
      and kd_mutex_batch_size as module_params.

## Long-term (research / performance)

- [ ] **NUMA-aware mutex queue** — implement add_to_local_queue / get_next_node
      for kd_mutex (currently stubbed behind #ifdef NUMA_AWARE which is off).
- [ ] **Sleepable mutex waiters** — park_waiter / wake_up_waiter support
      exists but is untested.  Verify that a waiter can safely schedule out
      and resume on a different CPU without losing per-CPU state.
- [ ] **Adaptive batch size** — tune kd_mutex_batch_size dynamically based
      on queue depth and contention.
- [ ] **Integrate with perf / ftrace** — expose delegation statistics as
      tracepoints for observability.
- [ ] **Support ARM64** — the TCLocks protocol is architecture-independent
      but the inline asm (stack switch trampolines) is x86-64 only.
- [ ] **Benchmark suite automation** — script that runs all 6 modes under
      varying thread counts and contention levels, collects dmesg stats.

## Kernel patch dependencies

These must exist in the patched kernel for the module to work:

- [x] `is_kd_test` / `is_kd` — identify target process
- [x] `kd_raw_spin_lock` / `kd_raw_spin_unlock` — spinlock hooks
- [x] `kd_mutex_lock` / `kd_mutex_unlock` — mutex hooks
- [x] `kd_do_int3` — int3 handler redirection
- [x] `__mutex_lock_slowpath` / `__mutex_unlock_slowpath` EXPORT_SYMBOL
- [x] `futex_wake_mark` / `futex_wait_setup` / etc. EXPORT_SYMBOL (for futex delegation)
