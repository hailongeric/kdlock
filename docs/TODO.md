# kdlock — Task List & Known Gaps

Last updated: 2026-09-04

## Current Validation Status

- TCLock-style nested spin JIT is implemented with explicit per-CPU execution
  frames. Mode 1 delegates A -> B; mode 6 covers A -> B -> C; mode 7 covers
  out-of-order A/B unlock; mode 8 creates independent deterministic queues on
  A and B.
- The nested failure transaction releases locks in reverse order and retries
  only after the waiter owns A normally. Mode 9 passes post-B injection and
  runtime CALL/IJ/instruction-limit faults with the daemon stopped. Mode 8's
  not-ready fault variant additionally passes with B recorded as queue owner.
- On 2026-09-04 all nine unit binaries and all six default integration scripts
  passed. Default spin modes 0/1/2/6/7/8 generated and executed the required
  JIT artifacts; all lock queues and execution frames drained cleanly.
- Strengthened `test_05_mutex.sh` now primes the hot-lock timer and requires
  evidence of promotion, slowpath entry, combiner election, and waiter handoff.
  The previous workload could pass entirely through the original Linux mutex.
- Mode 4 initially exposed an original-to-shadow promotion race: in-flight
  original mutex owners were unlocked through the new shadow mutex, leaving
  the Linux mutex permanently locked.
- The transition-drain fix prevents shadow acquisition until all tracked
  original owners/waiters have drained and routes unlock by the Linux mutex
  owner. `test_mutex_transition` covers the transition interleavings.
- On a fresh VM, modes 3/4/5 all passed with `mutex_jit=0`; every mode observed
  promotion, slowpath entry, combiner election, and waiter handoff. No kernel
  error signatures or unexpected mutex states were reported.
- Default JIT pipeline tests now validate more than write-back: daemon target
  discovery, bytes read from kernel text, generated `jit.S` entry-label
  alignment, sandbox exit/miss paths, non-empty `jit.bin`, objdump output, and
  `/dev/kd_dev` write-back. They still avoid executing translated CS code.
- `test_07a_mutex_jit_smoke.sh` now confirms one real mode 3 sandbox completion
  end-to-end with `mutex_jit=1`. A benchmark start barrier makes the
  owner/three-waiter arrangement deterministic; the test passed with
  `jit_success=1` and exact final counter `12005`.
- The opt-in `test_07_mutex_jit.sh` keeps the bounded mode 3 path: artifact
  validation, daemon write-back, sandbox completion, waiter resume after
  `mutex_unlock`, `jit_success=1`, and exact final counter `14001`.
  Stress remains unverified.
- Recovery-protected `test_08_mutex_jit_modes.sh` now passes for modes 4/5
  with `mutex_jit=1`. Mode 4 validates nested mutex sandbox execution; mode 5
  validates API-in-critical-section sandbox execution. Both require complete
  translation/write-back evidence, exactly one sandbox completion, exact final
  counter accounting, and clean dmesg.
- `run_vm.sh recovery` now disables VirtFS/VFIO, persists the serial console,
  and exposes an interactive monitor. `savevm pre_mutex_jit` succeeded before
  the two opt-in mode 3 tests ran.

## Implemented

- [x] Raw spinlock delegation via kd_spinlock.c (ported from TCLocks komb.c)
- [x] Spinlock JIT sandbox execution via kd_exe_on_call_hl()
- [x] Nested spin JIT execution frames and TCLock-style A/B/C delegation
- [x] Nested spin OOO unlock, independent inner-lock combining, and ret1/ret3
      waiter handoff
- [x] Transactional nested abort cleanup and ret4 native-CS retry
- [x] Bounded translation lookup, preallocated executable blocks, and
      release/acquire JIT publication
- [x] kd_mutex delegation protocol (ported from TCLocks komb_mutex.c)
- [x] Mutex delegation protocol with safe handoff/fallback mode
- [x] Mutex JIT sandbox execution (bounded modes 3/4/5 confirmation pass;
      guarded by `mutex_jit=0` by default; stress remains unvalidated)
- [x] Mutex → kd_mutex shadow table mapping (kd_lock.c)
- [x] Shadow stack per-CPU setup (kd_spinlock_init / kd_mutex_init_percpu)
- [x] Character device /dev/kd_dev for daemon ↔ kernel communication
- [x] Userspace daemon (daemon.c) — polls /dev/kd_dev, drives disassem
- [x] Dynamic translation pipeline (disassem/ — miasm-based)
- [x] Assembly wrapper (include/wrapper.S) for JIT sandbox context save/restore
- [x] Test module (klock_module.c) with 10 benchmark modes (0-9)
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

- [x] **Nested spinlock bypassed kdlock** — the old known-call adapter acquired
      B through the original raw lock, so only A could be delegated. Promoted B
      now enters the same fastpath/queue/combiner protocol using an explicit
      virtual waiter and execution frame.
- [x] **Nested failure resumed the wrong node/RSP** — native handoff implicitly
      used `nodes[0]` even when the failed waiter occupied another per-CPU node.
      Every slowpath return now publishes/restores the actual resume node.
- [x] **Failed JIT waiter bypassed A ownership** — marking a failed waiter
      completed let it retry its CS while another combiner still owned A. It now
      remains uncompleted, acquires A normally, and uses ret4 to resume the
      saved CS entry.
- [x] **Missing native ret1 path** — completed waiters whose parent lock was OOO
      hit an unconditional BUG. ret1 and ret3 now restore the actual node's
      saved register context.
- [x] **Mutex JIT waiter executed the CS twice** — completion used relaxed
      waiter wakeups, and the trampoline's hidden `callq` clobbered the
      slowpath return value. Fixed with release/acquire completion publication,
      direct RSP restoration, migration pinning, scheduler-state restoration,
      and a long-jump to the sandbox-produced post-`mutex_unlock` address.
- [x] **Mutex JIT false-positive test result** — nonzero `jit_success` alone
      allowed a duplicated critical section to pass. The opt-in test now checks
      the exact final counter (`14001`) as well as sandbox and error logs.
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
- [x] **Mutex unlock shadow allocation leak** — `__kd_mutex_unlock` used the
      create-or-find shadow lookup, so unlocks for never-delegated mutexes could
      permanently consume fixed shadow-table slots. Fixed by using a lookup-only
      path on unlock and falling back to `origin_mutex_unlock` when absent.

## Near-term (correctness & stability)

- [x] **Validate nested spin JIT end-to-end** — modes 1/6/7/8 pass with exact
      counters, translated execution, per-lock evidence, zero waiters, and zero
      frame/combiner invariant failures.
- [x] **Validate nested translation failure recovery** — mode 9 fault kinds
      1/2/3 and injected post-lock failure pass without daemon assistance.
- [x] **Validate queue-owner cleanup** — mode 8 not-ready topology plus fault
      injection records B as `KD_EXEC_LOCK_QUEUE_OWNER`, releases it once, and
      drains both queues.
- [x] **Bound finite resources** — translation-table lookup terminates at
      `KD_MAX_EXE`; executable blocks are preallocated; node/frame/lock-stack
      exhaustion and repeated lock acquisition fail closed in unit tests.
- [x] **Test safe-mode mutex protocol end-to-end** — modes 3/4/5 passed with
      `mutex_jit=0` on 2026-07-01, including promotion, slowpath, combiner, and
      handoff assertions plus kernel error-log checks.
- [x] **Avoid creating shadow entries on the unlock path** — when
      __kd_mutex_unlock is called for a never-delegated mutex, use a
      lookup-only shadow-table path and fall back to origin_mutex_unlock
      without permanently occupying a table slot.
- [x] **Verify nested mutex safe-mode handoff** — mode 4 passed after adding
      original-to-shadow transition draining. Full translated-CS execution
      remains covered by the separate experimental `mutex_jit` task.
- [x] **Validate mutex JIT modes 4/5 under recovery** — both modes generated
      valid translation artifacts and passed end-to-end sandbox execution with
      exact counters under `pre_mutex_jit_modes45_fix`.
- [x] **Fix mutex JIT modes 4/5** — nested known-call continuations now resume
      inside the original JIT body without a partial fallback, and mode 5 API
      calls are handled in-kernel before resuming translated code.
- [ ] **Stress mutex JIT mode 3** — only after the bounded path remains stable
      and every run has snapshot/serial-log recovery.

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
- [ ] **Benchmark suite automation** — script that runs all 10 modes under
      varying thread counts and contention levels, collects dmesg stats.

## Kernel patch dependencies

These must exist in the patched kernel for the module to work:

- [x] `is_kd_test` / `is_kd` — identify target process
- [x] `kd_raw_spin_lock` / `kd_raw_spin_unlock` — spinlock hooks
- [x] `kd_mutex_lock` / `kd_mutex_unlock` — mutex hooks
- [x] `kd_do_int3` — int3 handler redirection
- [x] `__mutex_lock_slowpath` / `__mutex_unlock_slowpath` EXPORT_SYMBOL
- [x] `futex_wake_mark` / `futex_wait_setup` / etc. EXPORT_SYMBOL (for futex delegation)
