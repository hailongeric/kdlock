# kdlock Open Tasks

Last reviewed: 2026-09-05, against `ed00edb` and the recovery guest's patched
Linux 6.1.159 hook callers. The BCD comparison uses local revision `dbde52c`.
P0 findings below are source-audit findings, not newly reproduced runtime
failures. The observed promotion-test failure is recorded separately below
and in `VALIDATION.md`.

This file tracks unfinished work only. Completed behavior belongs in
`DESIGN.md`, the current register contract belongs in `JIT_REGISTER_ABI.md`,
and the latest mode 0/1/2/3/4/5/10/11 execution evidence belongs in
`VALIDATION.md`.

## Direction And Priority

The idea is to combine TCLock-style queue/context delegation with runtime
translation of existing kernel critical sections and typed native services at
explicit boundaries. JIT is a mechanism for selecting and adapting executable
code, not a reason by itself to expect speedup or safety. The useful next goal
is a precisely bounded, demonstrably correct delegation subset, then measured
benefit on unchanged critical-section source.

P0 items block claims of general kernel safety. Implement each with a failing
regression first, then unit/codegen checks, guest build, a minimal integration
test, and the existing strict JIT suite. Add new modes only when a missing
behavior cannot be tested in the existing harness. Do not expand services or
start production-kernel experiments while P0 is unresolved.

## P0: Correctness Contracts

### C1. Forward Continuation After Partial Execution

Evidence: [spin execute_cs](../kernel_module/kd_spinlock.c) and
[mutex execute_cs](../kernel_module/kd_mutex.c) restore `retry_regs` after a
failed run; [frame abort](../kernel_module/kd_exec.c) and lock cleanup do not
restore shared data or the waiter stack. Entry retry can repeat writes and
already completed nested B sections. BCD instead preserves the ordinary CALL
frame and resumes the waiter's original code from the exit context; see
`DESIGN.md` 9.6. The target is forward continuation, not transactional rollback.

- [ ] Introduce explicit outcomes for not-started, native-continuable,
      completed, and unrecoverable execution. Separate rejection before any
      side effect from exits after writes, nested unlock, or a native service.
      Keep progress metadata in the execution frame and retain two args words.
- [ ] Implement a single-lock ordinary CALL-miss continuation first. Retain
      the virtual return frame, preserve the callee-entry state and live flags,
      and return ownership to the original waiter without `retry_regs` entry
      replay. Provide spin and mutex continuation trampolines. Removing only
      the register reset is incorrect while the CALL stub still pops RSP.
- [ ] Extend to A exiting after B has completed/unlocked: retain B's effects
      and resume A after the completed work, without reacquiring/replaying B.
- [ ] Extend to exits while B is still held, including queued/remote child
      frames. Transfer logical ownership, lock-stack, queue/node, and execution
      context to the waiter; do not run generic abort cleanup that releases B.
      Record control-call phases so an acquisition failure cannot resume at
      post-lock RIP without owning the lock.
- [ ] Define precise original-code state for IJ, budget, guard, and service
      exits. Distinguish pending from completed operations and preserve virtual
      stack, live flags, and code/stack lifetimes. An arbitrary JIT machine IP
      or a saved GPR set alone is not a valid native continuation.
- [ ] Before delegation, validate a bounded supported CFG, instruction policy,
      required continuations, resource needs, and source-text generation. An
      unresolved entry should receive native handoff without starting JIT.
- [ ] Until a particular exit has a proven continuation protocol, reject its
      unsupported paths before execution and treat unexpected post-effect
      failure as fatal, not a successful native retry. Memory undo is not the
      default remedy: externally observed effects after releasing B cannot
      generally be restored by a local write log.
- [ ] Acceptance: inject CALL/IJ/limit/capacity failures before the first write,
      after writes to shared data and stack, after B acquisition, after remote
      B completion/unlock, and after hostcall execution. Use distinct request
      IDs and an independent observer to prove no lost or duplicated A/B work.
      Include nested mutex cleanup, not only spin mode 9.

### C2. One Protocol Per Physical Lock

Evidence: [target selection](../kernel_module/kd_main.c) is based on `comm`;
[mutex promotion](../kernel_module/kd_lock.c) drains only hooked native users
before entering an independent shadow mutex. The guest's `mutex.c` checks
`is_kd()` before routing, so other tasks can still acquire the original lock.

- [ ] Separate eligibility to delegate a request from the protocol used to
      acquire/release a promoted physical lock. All participants must agree on
      one protocol; a non-delegatable request still needs compatible handoff.
      Until then, explicitly restrict delegation to isolated test locks.
- [ ] Audit promotion, process renaming, unhooked callers, trylock,
      irqsave/bh, interruptible/killable mutex variants, and lock-address reuse.
      Do not treat `mutex_jit=0` as a fix for shadow/native mutual exclusion.
- [ ] Acceptance: targeted and non-targeted threads race on the same mutex
      before/during/after promotion; an in-CS guard never exceeds one. Repeat
      with process renaming and alternate lock APIs. Audit native qspinlock
      interoperability separately; shared lock-word layout is not a proof.

### C3. Immutable JIT Publication And Lifetime

Evidence: [sys.c](../kernel_module/sys.c) copies chunks into live executable
storage and trusts the final status; [exe.c](../kernel_module/exe.c) retains the
same pointer across continuation. Status acquire/release does not retire readers.

- [ ] Add generation and total-size metadata, coherent miss snapshots, checked
      chunk coverage, a single-writer/session policy, and publication
      acknowledgment after the image is complete. Reject stale/incomplete jobs.
- [ ] Stage in writable non-executable memory, validate the image, publish an
      immutable RX generation, and pin it across execution and hostcall/nested
      suspension. Retire old generations only after all readers drain, using
      a protocol that also supports scheduled mutex executors.
- [ ] Track original module-text lifetime and address reuse. Add a hook
      removal/drain protocol matched by patched-kernel callers; setting hook
      pointers to NULL followed by `synchronize_rcu()` alone does not protect
      those callers today. Preserve a reproducible kernel patch/config/build
      identity in the repository, rather than relying only on the live guest.
- [ ] Acceptance: execute the same RIP on independent locks while recompiling;
      inject missing/out-of-order chunks, failed copies, stale jobs, daemon
      restart, and teardown under a suspended continuation. Never execute a
      mixed image or freed source/generated text; enforce W^X.

### C4. Instruction, Flags, And Fault Semantics

Evidence: [special_inst.py](../disassem/special_inst.py) replaces `INT` with NOP
and warns on unimplemented special operations; [translation.py](../disassem/translation.py)
has no general privilege whitelist. [disassem.py](../disassem/disassem.py)
inserts flags-clobbering budget checks; [normal.py](../disassem/normal.py)
does not emit general memory guards.

- [ ] Build a fail-closed instruction/operand eligibility pass. Reject traps,
      privileged/system state, unknown addressing, and unsupported SIMD/FPU
      forms unless a specific lowering and state contract exists. Do not emit
      warning-only partial translations or treat every non-hostcall as safe
      to translate.
- [ ] Preserve live arithmetic flags across inserted instructions, dispatch,
      indirect jumps, and any supported exit. Validate PUSH/POP width and
      addressing semantics, subregister handling, implicit operands, and ABI
      stack alignment. In particular, the special LEA-to-MOV/ADD rewrite in
      `disassem.py` changes flags although LEA does not. Keep FS unsupported
      and the current two-word args ABI.
- [ ] Define permissible memory and exception behavior. Address-range checks
      alone do not prove object lifetime or recover from an already visible
      write. Resolve stack/unwind/objtool and SMAP/UACCESS concerns without
      simply suppressing warnings.
- [ ] Acceptance: native-versus-translated register/flags/memory differential
      tests, including flags live across basic blocks, ADC/SBB, register
      pressure, stack operands, bad addresses, and unsupported opcodes. Unsafe
      instruction tests must reject before execution, not run on the host.

### C5. Origin Context And Nested Boundaries

Evidence: [kd_segment.h](../include/kd_segment.h) supplies an origin GS base;
rewriting addresses does not stop local per-CPU writers. Native handlers still
observe the combiner's real task and CPU.

- [ ] Classify per-CPU/task accesses: supported read-only or explicitly
      synchronized data, logical-current reads, and unsupported CPU-local
      scheduler/IRQ/preemption/RCU state. Reject unsafe remote RMW or route a
      defined service to its origin context; do not blanket-rewrite every GS
      access as though it had identical concurrency semantics.
- [ ] Record/validate lock type and execution context at control boundaries;
      explicitly reject unsupported mixed spin/mutex nesting and sleeping in
      spin context. Carry a common budget through child frames if a global
      limit is intended; account for the early outer-unlock/OOO branch.
- [ ] Acceptance: controlled origin-CPU interrupt/task updates during remote
      delegation, known-call/hostcall context checks, maximum nesting and node
      pressure, lock-kind mismatch, and continuation-budget exhaustion. Verify
      safe rejection where equivalence is unavailable.

## P1: Evidence And Useful Services

- [ ] Test actual shared/kernel implementations where possible, not only C
      mirrors. Make missing miasm fail required codegen validation rather than
      count `SKIP` as success. Add runtime pool/table/shadow saturation tests.
- [ ] Retain per-mode dmesg, command/env, kernel/source revision, artifact hash,
      and executed generation/entry. Add in-JIT entry/exit markers rather than
      relying only on pre-call IP logs and aggregate success counters.
      Distinguish all generated artifacts from
      the subset required to execute. Run each fault variant explicitly.
      The 2026-09-05 rerun retained per-mode logs and hashes externally; make
      this automatic in the committed harness and add generation identity.
- [ ] Make nested-test promotion deterministic without weakening JIT checks.
      Mode 6 initially generated only one of three artifacts on 2026-09-05:
      C's promotion tightened the shared sampling window and A/B became
      ignored. An unchanged rerun passed. Isolate/reset sampling policy or add
      a controlled test-only promotion mechanism; preserve failed attempts.
- [ ] Add varied per-request inputs, multi-lock histories, branch coverage,
      randomized schedules and an exactly-once/linearizability oracle. Keep
      the existing nine-word state replay as a fast regression, not a proof.
- [ ] After C1/C4/C5, add a typed, bounded logging service backed by a controlled
      buffer, with clear argument validation, context, overflow, return values,
      and side-effect/commit policy. Demonstrate multiple services and calls
      surrounding nested locks. Raw variadic `printk` remains excluded.
- [ ] Define each service's clobbers, task/CPU affinity, sleeping constraints,
      and repetition semantics. Retry-safe flags are declarations, not runtime
      proof; logging and other irreversible effects need explicit handling.
- [ ] Add real waitqueue parking/wakeup for mutex only after queue ownership and
      waiter/frame/stack lifetime invariants are covered under oversubscription.
- [ ] Decide whether to remove or isolate the legacy futex execution entry.
      A userspace frontend would be a separate scope with TLS/task-lifetime
      semantics, not a natural consequence of kernel GS support.

## P2: Performance And Broader Scope

- [ ] Compare native Linux locks, TCLock-style native delegation, kdlock queue
      handoff, and kdlock JIT on equivalent workloads and kernel configurations.
      Separate cold translation, steady-state execution, queueing, hostcalls,
      and fallback cost. Measure throughput, p50/p99 latency, CPU time, cache
      transfers, and memory footprint; do not report only `jit_success`.
- [ ] Vary all workload modes, threads, CS sizes, service frequency, data size,
      contention, and socket placement; repeat runs and report variability.
      Establish the amortization threshold before claiming JIT helps.
- [ ] Replace frequency-only promotion with per-lock contention/cost signals
      and reconsideration/demotion. Reduce global accounting contention;
      evaluate adaptive batching, fairness, and configurable batch limits.
- [ ] Evaluate right-sized/lazy code storage and generation retirement against
      the current 64 x 640 KiB pool. Preserve allocation safety in atomic paths.
- [ ] Validate dormant spin `NUMA_AWARE` logic before enabling it; implement a
      mutex NUMA-local policy only with measured benefit. The two-node VM alone
      is not NUMA-aware protocol validation.
- [ ] Defer rwsem and broader kernel lock APIs until the correctness subset and
      performance case are established. Keep x86-64 as the only active ISA scope.
