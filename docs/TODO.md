# kdlock Open Tasks

Last reviewed: 2026-09-05, including CALL continuation and native-owner mutex
changes on base `c08368d`. The existing Linux 6.1.159 hooks are reused without
new guest kernel changes. The BCD comparison uses local revision `dbde52c`.
C1/C2 describe implemented subsets and their remaining boundaries. Other P0
findings remain source-audit findings, not newly reproduced runtime failures. The
historical promotion-test failure is recorded separately in `VALIDATION.md`.

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

Implemented: ordinary CALL miss preserves the virtual CALL frame and current
registers, resumes the original waiter, and retains the combiner's physical
locks through native-unlock rendezvous. Single spin/mutex, A after completed B,
still-held B, and independent remote spin B are covered by
`test_10_native_resume.sh`. Post-entry errors without a continuation protocol
are fail-stop; not-started work can still use native entry handoff. Frame/node
metadata was extended, not the two-word wrapper args. See `DESIGN.md` 9.5/9.6.

Flags are explicitly deferred at the user's request. CALL-boundary tests do
not establish general flags correctness or basic-block/budget continuation.

- [ ] Complete control-call phase metadata so a failed nested acquisition can
      resume the pending call without pretending its post-CALL RIP owns B.
      Mutex now consumes the CALL only after native B acquisition and frame
      recording. The remaining fail-stop behavior avoids duplicate execution
      but does not recover failed control calls.
- [ ] Define precise original-code state for IJ, budget, guard, and service
      exits. Distinguish pending from completed operations and preserve virtual
      stack, live flags, and code/stack lifetimes. An arbitrary JIT machine IP
      or a saved GPR set alone is not a valid native continuation.
- [ ] Before delegation, validate a bounded supported CFG, instruction policy,
      required continuations, resource needs, and source-text generation. An
      unresolved entry should receive native handoff without starting JIT.
- [ ] Until a particular exit has a proven continuation protocol, reject its
      unsupported paths before execution. Post-entry fail-stop is implemented,
      but it is not a substitute for this eligibility pass. Memory undo is not the
      default remedy: externally observed effects after releasing B cannot
      generally be restored by a local write log.
- [ ] Acceptance: inject CALL/IJ/limit/capacity failures before the first write,
      after writes to shared data and stack, after B acquisition, after remote
      B completion/unlock, and after hostcall execution. Use distinct request
      IDs and an independent observer to prove no lost or duplicated A/B work.
      Include nested mutex cleanup, not only spin mode 9.
- [ ] Extend native rendezvous tests beyond the current distinct-request
      before/call/after oracle, mutex in-CS exclusion guard, CPU-1 waiters and
      comm changes: add randomized histories, deep/OOO exits, and teardown while
      a native continuation is active. Do not claim arbitrary
      kernel compatibility from the tested nested spin/mutex subset.

### C2. One Protocol Per Physical Lock

Implemented for the tested non-RT mutex subset: the original Linux mutex is
the exclusion lock, the shadow is a scheduling gate, and all scheduler owners
acquire/release the original mutex as `current`. Native continuation borrows
the combiner's protection and returns unlock requests to it. Nested B uses the
same combiner's native acquisition, not remote mutex delegation. No native
owner handoff or new kernel hook/export is required. `mutex_jit=0` is native-only.

The module's RCU task registry preserves the existing `is_kd` routing after
rename. `test_11_mutex_native_protocol.sh` checks mixed native/delegated users,
an in-CS exclusion guard, task allocation failure and slot exhaustion;
`test_10_native_resume.sh` also checks renamed native continuation. Current
results, including which variants actually ran, belong in `VALIDATION.md`.

- [ ] Extend native participant validation to signal-aborted interruptible /
      killable waits, systematic promotion timing and randomized histories.
      Successful alternate APIs are native participants, not translated services.
- [ ] Audit lock-address reuse, WW/PI/RT and debug/lockdep kernel configurations.
      Keep production lock selection restricted until context/lifetime issues
      in C3-C5 are resolved. Hot unload is not made safe by task-record RCU.
- [ ] Reject owner-sensitive native suffixes before delegation, or define a
      separate service contract. A borrowed waiter does not become the native
      owner; direct owner checks, recursive reacquisition and task-bound lock
      side effects cannot be made equivalent by the unlock rendezvous alone.
- [ ] Audit native qspinlock interoperability separately, including target
      renaming and irqsave/bh. Shared lock-word layout is not a proof.

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
- [ ] Extend the frame's backend check into preflight eligibility and a full
      execution-context contract. Known mixed spin/mutex calls now reject before
      service, but post-entry rejection still fail-stops. Carry a common budget
      through child frames if a global
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
      The 2026-09-05 rerun retained per-mode logs and hashes externally, and
      `test_10_native_resume.sh` now archives its own evidence. Extend automatic
      retention to the strict suite and add generation identity.
- [ ] Make nested-test promotion deterministic without weakening JIT checks.
      Mode 6 initially generated only one of three artifacts on 2026-09-05:
      C's promotion tightened the shared sampling window and A/B became
      ignored. An unchanged rerun and the later CALL-continuation regression
      passed; the policy is still unchanged. Isolate/reset sampling policy or
      add a controlled test-only promotion mechanism; preserve failed attempts.
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
