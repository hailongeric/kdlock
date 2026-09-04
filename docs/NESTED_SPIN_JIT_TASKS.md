# Nested Spinlock JIT Delegation Task List

Last updated: 2026-09-04

This checklist tracks the implementation of TCLock-style nested spinlock
delegation with kdlock's dynamic critical-section execution. The goal is to
keep the original kernel source unchanged while allowing both the outer and
inner critical sections to execute through the kdlock/JIT delegation path.

## Definition of Done

- A delegated `A -> B` critical section enters the kdlock protocol for both
  locks when both locks are promoted and translated.
- The JIT execution of B does not call the original raw spinlock path.
- After B completes, A's saved JIT registers and virtual stack resume at the
  correct continuation.
- Inner unlocks perform normal kdlock handoff/OOO processing.
- The outer unlock completes the delegated waiter exactly once.
- Native fallback never leaves a shadow lock, original lock, waiter, or frame in
  an inconsistent state.
- Mode 0, mode 1, and existing JIT/unit tests pass after each relevant change.

## Phase 0: Baseline and Instrumentation

- [x] Record the current worktree state and preserve all pre-existing changes.
- [x] Audit TCLock's nested combiner state against kdlock.
- [x] Confirm that `kd_spin_jit_nested_lock()` and
      `kd_spin_jit_nested_unlock()` currently bypass kdlock.
- [x] Add per-lock/per-depth diagnostic counters for nested execution.
- [x] Add assertions for frame depth, lock-stack ownership, and outer unlock.
- [x] Run and record the low-risk baseline:
      unit tests, Python checks, module builds, and post-adapter mode 0/1/2.

## Phase 1: Separate the Lock Protocol from the Execution Backend

- [x] Define a common combiner context containing saved TCLock state.
- [x] Define a JIT execution frame containing `pt_regs`, continuation RIP,
      virtual RSP, outer lock, parent frame, and held-lock depth.
- [x] Add a per-CPU bounded frame stack with overflow failure handling.
- [x] Split native waiter handoff from JIT continuation resume.
- [x] Restore the missing native ret1/ret3 handoff paths while keeping JIT
      retry on the explicit ret4 continuation path.
- [x] Add lock-stack push/pop/top helpers shared by acquire and unlock paths.
- [x] Add unit tests for frame push/pop and lock-stack invariants.

## Phase 2: One-Level Nested Spinlock JIT

- [x] Replace the direct original-lock calls in `kd_spin_jit_nested_lock()` and
      `kd_spin_jit_nested_unlock()` with context-aware kdlock entry points.
- [x] Define explicit JIT events for nested lock, nested unlock, outer unlock,
      completion, and error.
- [x] Save A's continuation before entering B.
- [x] Suspend A at B's acquisition and enter B through the same
      fastpath/queue/combiner protocol as a native
      waiter.
- [x] Execute B waiters through JIT using B as the frame's outer lock.
- [x] Restore A's frame after B handoff and resume at the continuation returned
      by B, without executing B's critical section twice.
- [x] Complete A only after all nested locks have been released.
- [x] Add a mode 1 test that proves both A and B entered delegation.

## Phase 3: Nested State and OOO Unlock Correctness

- [x] Preserve `lock_addr[]`, previous CPU, previous RSP, node counters, and
      next-node state across every nested frame.
- [x] Support A -> B -> C with a bounded maximum depth.
- [x] Handle A/B out-of-order unlocks without losing waiter handoff.
- [x] Reject repeated acquisition of the same lock with `-EDEADLK`; do not
      silently convert it into recursive locking or native fallback.
- [x] Verify node, lock-stack, and frame exhaustion fail closed without
      leaking their per-CPU depth counters.
- [x] Add stress tests with independent contention on A and B.

Current evidence:

- Mode 6 (`A -> B -> C`, reverse-order unlock) passes with three JIT artifacts,
  two nested lock/unlock events, and no native fallback.
- Mode 7 (`lock A, lock B, unlock A, unlock B`) passes with an observed
  out-of-order unlock and no invariant failure.
- Mode 8 constructs independent A and B queues in the exact kdlock order
  `pending -> combiner -> target -> trailer`. It waits on measured queue depth,
  not timing, and has passed three consecutive runs with A/B `combiner=1`,
  `jit_success=1`, B `nested_remote=1`, `native_fallback=0`, and `waiters=0`.
- Every delegated frame now compares the complete combiner state before and
  after nested execution. Mode 0/1/2/6/7/8 pass with
  `invariant_failures=0`.
- Unit tests reject repeated lock acquisition, reject frame/lock-stack pushes
  at capacity, roll back failed spin-node reservations, and prove capacity is
  reusable after release.

## Phase 4: Translation Readiness and Failure Recovery

- [x] Validate the currently executable entry with acquire semantics before
      every remote execution. A whole-CFG static preflight is not possible for
      runtime indirect targets; call/IJ/limit misses therefore use the same
      transactional abort path.
- [x] Check B's waiter entry before remote execution. If it is not published,
      register it for translation and hand B to the waiter without executing
      incomplete code.
- [x] Prevent daemon waits and sleeping allocation in combiner context by
      using a bounded translation table, a preallocated executable-block pool,
      and an atomic publication gate.
- [x] Restore nested locks in reverse order, restore the saved combiner state,
      and complete or abort every execution frame exactly once.
- [x] Test call misses, indirect-jump misses, instruction limits, and a stopped
      daemon after B has been acquired.
- [x] Scope failure fallback to the affected outer lock, expose it through
      per-lock `native_fallback`/`jit_disabled` statistics, and drain the
      failed waiter through native ownership before resuming its CS entry.

Current evidence:

- Mode 8 with `KD_MODE8_NOT_READY=1` observes `jit_not_ready`, safely hands B
  to the untranslated nested waiter, and finishes with zero queued waiters.
- Mode 8 with both `KD_MODE8_NOT_READY=1` and
  `KD_SPIN_ABORT_INJECT=1` forces that waiter to own B as
  `KD_EXEC_LOCK_QUEUE_OWNER`. The abort log records `kind=2`, `released=1`, A
  resumes at its saved CS entry, the exact counter is `12014`, and both lock
  queues drain to zero.
- Mode 9 passes one-shot post-B failure and runtime fault kinds 1/2/3
  (call miss, IJ miss, and instruction limit). Runtime tests stop the daemon
  before fault injection; recovery therefore has no daemon dependency.

## Phase 5: Regression and Recovery Validation

- [x] Run unit tests and static checks.
- [x] Build kernel module, workload module, daemon, and benchmark in the VM.
- [x] Run mode 0 and mode 2 spinlock regressions.
- [x] Run the new mode 1 nested-delegation test.
- [x] Run all default tests with `mutex_jit=0`.
- [x] Run high-risk nested-JIT tests only in a recovery VM with a confirmed
      QEMU snapshot.
- [x] Collect dmesg, serial output, JIT artifacts, and delegation counters.
- [x] Update `docs/DESIGN.md`, `docs/TODO.md`, and `README.md` only after the
      implementation and tests agree.

Final validation on 2026-09-04:

- All nine unit-test binaries passed; the execution-frame suite contains nine
  checks and the spin-node exhaustion suite contains three checks.
- `tests/test_04_spinlock.sh` passed its default modes 0/1/2/6/7/8. Modes 0
  and 1 both generated complete JIT artifacts, wrote them into the kernel, and
  executed translated critical sections.
- `tests/run_all.sh` passed all six default integration scripts with
  `mutex_jit=0`.
- Recovery-only mode 9 fault variants and the mode 8 queue-owner abort variant
  completed with exact counters, zero waiter leaks, clean dmesg, and
  `kd_exec invariant_failures=0`.

## Implementation Order

The work must proceed in this order:

1. Phase 0 instrumentation and baseline.
2. Phase 1 execution-frame/protocol split.
3. Phase 2 one-level A -> B delegation.
4. Phase 3 recursive and OOO correctness.
5. Phase 4 translation readiness and recovery.
6. Phase 5 regression, recovery validation, and documentation.

No phase is complete based only on a successful benchmark exit. Kernel logs,
per-lock delegation counters, exact final counters, and cleanup state are part
of every acceptance check.
