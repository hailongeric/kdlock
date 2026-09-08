# kdlock Open Tasks

Scope: x86-64 kernel spin/mutex delegation using existing guest hooks.
Do not modify/rebuild the guest kernel by default. Keep the two-word wrapper
ABI and physical native owners. New code needs purpose/constraint comments.
Complete the main behavior before optional features and performance work.

## Direction And Priority

The approved JIT-episode scope is implemented: an ordinary direct CALL miss
ends this JIT invocation and the original waiter completes the native suffix.
Admission and emission share the same scope. This replaces the old requirement
to admit that waiter-only suffix; it does not allow unchecked live JIT paths.

Latest complete matrix: **53/53 pass**; 37 passes execute generated
code, 12 are context refusals, two are native controls and two are real kernel
task/RCU/owner-ACK probes without JIT. All 39 unit programs
and the 25-case admission audit pass. Mode 0-8, including guarded mode 1/4/8,
pass actual JIT. Mode 8's stage-2/3 register cases and learned mutex-depth
continuation also pass. This closes the matrix gates, not the whole project:
[VALIDATION](VALIDATION.md#mutex-task-lifecycle).

Implement next in this order:

1. Follow the [resource inventory](JIT_EXECUTION.md#6-资源拒绝与测试边界): broaden
   combined pre-entry/PENDING queue failures and task-record lifecycle schedules.
   Mutex node/shadow/hook components now use production paths with substituted
   primitives. Verify registers, retained locks and exactly-once effects without
   broadening post-entry recovery or mistaking fixtures for live scheduling.
   The real task/RCU/final-ACK probe covers two bounded unlock orders, not
   arbitrary task exit, cancellation or multiple outstanding native frames.
2. Broaden native-peer, signal/trylock, oversubscribed and multi-request remote
   schedules, using existing hooks. Keep source/lock lifetime review separate
   from owner handoff and the explicitly deferred immutable-version work.
3. Extend scoped CALL/RET negative coverage before broadening eligibility,
   especially shared tails, multiple call sites and aliased return slots.
4. Re-run affected main gates and the complete matrix on each resulting freeze.
   Optional services and performance follow the main correctness work. Do not
   mark C1/C2/C5 complete merely because this matrix is green.

### Guarded Admission Increment

Production conditional analysis collects required entry-range separations and
models callee-saved effects only at registered lock-control calls. Every premise
is checked before root body execution; missing cold text must be fetched first.
Current results and remaining gates are in
[VALIDATION](VALIDATION.md#mutex-task-lifecycle); this does not close C1/C2/C5.

- [x] Collect every required disjoint range and test the emitted entry predicate
      against concrete overlap, adjacency, wrap and register-preservation cases.
- [x] Validate the two production CALL advance helpers' packet preservation;
      retain memory clobbers and conservative ordinary/decoded call effects.
      Guarded mode 1/4 and their register continuations execute actual JIT.
- [x] Connect guarded analysis to code generation with a verified pre-body
      refusal path. Preserve two arguments, GS/current refusal and progressed
      fail-stop behavior. Validate a non-root child's published logical parent,
      CALL phase/packet, task, GS and lock depth before first dispatch. This is
      logical scope, not a version certificate; C3 remains deferred. Conditional
      analysis permits one explicit root and no independently seeded callee.
- [x] Complete mode 8's cross-window CFG and interior-root dispatch labels.
      Decoder seeds do not become independent admission roots; GS, genuine bad
      instructions and expansion exhaustion still refuse. Ordinary mode 8 and
      its two register gates execute actual JIT with the probes retained.
- [x] Close mutex learned-depth admission without deleting register probes or
      borrowing root facts for independent callees. Keep generated tests and
      full-matrix results separate from captured-text feasibility.

### Learned Callee Increment

The helper's translated nested locks now execute, rather than only its caller
prefix. The implementation and execution flow are in
[JIT_EXECUTION](JIT_EXECUTION.md#51-学习后的直接-callee).

- [x] Seed only the checked root on the conditional learned-callee path; require
      selected-block reachability and exact generated RET target correspondence.
      IJ history and indirect control cannot borrow one root's facts.
- [x] Propagate real post-push CALL packets and actual RET effects without a
      fabricated immediate fall-through. Preserve callee memory writes and
      native/control clobbers; keep default independent-root analysis unchanged.
- [x] Enforce the complete predicate set before body and retain bounded work,
      two-word ABI, physical owners and no replay. No kernel/flags/version change.
- [x] Add eight focused methods with generated-code positives, callee-pointer
      corruption, GS, return-table mismatch, disconnected/indirect entry and
      budget negatives. Run real helper learning and capacity/owner ACK checks
      with `mutex_jit=1`, then the complete 51-case frozen-source matrix.
- [ ] Broaden multi-callsite/shared-tail and actual return-slot alias execution
      tests before further eligibility changes. Existing scope fixtures and
      returned-body markers are not arbitrary-control-flow proofs.

## P0: Correctness Contracts

### Resource Coverage Increment

- [x] Inventory the principal pool/refusal classes and separate unstarted
      root fallback from progressed PENDING continuation and fail-stop exits.
- [x] Replace the copied execution hash model with production registration,
      partial-allocation/teardown, pool exhaustion and device-boundary tests.
      Add real registration-gate contention and seven assertion-detected mutants.
- [x] Use real lookup/ready in the high-level entry fixture; check 14 unavailable
      spin/mutex root cases without wrapper calls or packet/stack/ledger writes.
- [x] Finish full-matrix verification on the initial 173-input registry freeze:
      51/51 pass with 37 actual-JIT cases; all units/audit and postflight pass.
      Earlier 172-input results remain separate historical evidence.
- [x] Replace both mutex node/shadow copied models with one production resource
      fixture: 256 reservation inputs, full 1024-slot collisions, early hook
      failures, no-node acquisition and full-packet resume after slot reuse.
      Test hook and direct entry paths and eight assertion-detected mutants.
- [x] Finish the corrected mutex-resource freeze: 51/51 pass with 37 actual-JIT
      cases; all 39 units, 25 audit cases and postflight pass. Keep test 11's real
      four-slot overflow separate from substituted resource/assembly primitives.
- [x] Connect production task get/put and deferred free to final owner ACK in
      opt-in kernel `test_22`. Verify B->A and A->B with real mutex ownership,
      shared acquisition refs, allocation refusal and an RCU reader spanning
      removal. The release callback runs only after that reader leaves.
- [x] Verify the 175-input freeze with local/cross-NUMA task probes and the
      full 53-case matrix, 39 units, 25 audit cases and final identity/drain
      checks. Default `.text` is unchanged and contains no task probe.
- [ ] Broaden combined pressure, task exit/cancellation and multiple native
      frame schedules. These bounded checks do not close C1/C2/C5 or prove
      live pool saturation. `test_22` constructs its continuation and outer
      batch callback; it does not replace the actual-JIT/queue matrix.

### C1. Forward Continuation After Partial Execution

Implemented boundaries:

- Ordinary CALL misses resume the original waiter at current callee RIP with
  current GPRs and virtual return stack; no entry replay or memory rollback.
- Validated PENDING lock-resource failures can retain the original lock CALL
  packet before acquisition/publication. Later phases cannot use that path.
- Native registration checks NONE, eligible PENDING or validated spin remote
  COMPLETE relay before publishing borrow state or accounting progress.
- Physical owners keep locks and acknowledge waiter unlocks. Nested and
  out-of-order paths retain explicit ownership/lifetime records.

Remaining:

- [x] Recover mode 1/4 register/CALL, held-B and pending-B gates under guarded
      admission, with exactly-once protected-state and ownership checks.
- [x] Recover mode 8 register/CALL stages 2/3 with real body evidence and
      exactly-once checks; preserve GPR/stack probes and owner notifications.
- [x] Recover mutex learned-depth acceptance on current source; a successful
      first prefix does not validate expanded callee code.
- [ ] Prove/test each additional recoverable exit with registers, stack,
      ownership and exactly-once side effects. Unsupported post-entry exits
      remain fail-stop, not restart-at-entry fallbacks.
- [ ] Exercise bounded exhaustion and partial progress across frame, node,
      lock and code pools using production paths.
- [ ] Expand multi-request/remote schedules and protocol oracles. Sampled stack
      margins do not establish arbitrary IRQ/NMI depth safety.

### C2. One Protocol Per Physical Lock

Implemented: spin L/S separation, acquisition tickets and origin references;
native mutex ownership with a private scheduling gate; active-task routing
through rename and native unlock; owner-side ACK and bounded remote-chain
publication. Native signal/trylock participants use Linux exclusion.

Remaining:

- [ ] Broaden non-target, oversubscribed, cancellation and remote/deferred
      follower schedules.
- [ ] Review source/lock address reuse, source-module lifetime and metadata
      retirement. Existing guest hook readers lack a complete unload/drain
      protocol; module-side synchronize_rcu alone is insufficient.
- [ ] Evaluate missing hook capabilities separately before proposing any
      kernel edit. No owner handoff or mutex wait-list rewriting.
- [ ] Preserve strict node reservation, physical-owner/origin-ticket separation,
      release-published ACK and no accesses after waking the waiter.
- [ ] Keep IRQ/BH, RT/PI/WW, arbitrary signal schedules and new lock APIs outside
      delegation until separately designed and tested.

### C3. Immutable JIT Publication And Lifetime

**Deferred by explicit user decision.** Code currently overwrites RIP-keyed
executable blocks in place. Independent locks, early A release and concurrent
recompilation can overlap old execution. Low probability is a qualitative
assessment, not a measured rate or a correctness guarantee.

Future work: immutable code generations, complete-image validation, coherent
miss/publication state, generation identity and reclamation after all executors
finish. Do not implement these as incidental changes to current main work.
Source-text/hook-reader lifetime remains a separate C2 problem.

### C4. Instruction, Flags, And Fault Semantics

**Semantic fixes deferred by explicit user decision.** Diagnostics are present;
INT-to-NOP, warning-only special instructions, non-transparent budget/dispatcher
flags and incomplete cross-exit processor state remain limitations.
No absence of warnings proves all instructions safe.

Future work requires an explicit instruction subset, flags liveness/restoration,
unsupported-instruction policy, fault state and continuation contract.
For now retain actionable warning/error locations without claiming these issues
are fixed or broadening recovery based on a body marker.

### C5. Origin Context And Nested Boundaries

Implemented: admission of the actual possible JIT scope; GS/FS/context and
backend checks; reachable text/CFG handling; IR memory-effect/address analysis;
decoded CALL/RET effects; bounded memory facts and alias-origin diagnostics.
Known unsafe code on a retained JIT path is native-only, never a combiner
hostcall escape disguised as context restoration.

Remaining:

- [x] Admit eligible mode 1/4 loaded-pointer/register-sample prefixes using
      enforced entry disjointness conditions, not assumed private stacks.
- [x] Resolve mode 8's cold CFG without skipping any executable JIT block;
      check new cached-window targets again before admission and emission.
- [x] Resolve learned mutex helper admission while retaining full checks on
      every executable JIT path.
- [ ] Preserve alternate live paths, learned-target reanalysis, indirect-call
      conservatism and CALL stack-write checks while improving precision.
- [ ] Expand negative tests for aliases, implicit/internal IR accesses and
      concurrent mutation. Unknown pointers or runtime memory are not proved
      safe by the existing abstract model.
- [ ] Document and validate any additional entry-state assumptions first.
      Source RBP/RSP are not private memory; volatile entry GPRs are not stable
      C arguments. Do not add an ABI-preservation assumption to hide failures.
- [ ] Broader context equivalence, hidden/unresolved calls and native suffix
      owner-sensitive operations need separate analysis. Logical current is
      not a scheduling, IRQ, RCU or hardware GS switch.

## P1: Evidence And Useful Services

- [ ] Make full-matrix evidence retention reproducible from a fresh checkout:
      commands/env, source/kernel/artifact identity, exit statuses and drains.
      Returned body witnesses are implemented; generation identity is not.
- [ ] Broaden production-code fixtures, randomized schedules and exactly-once/
      linearizability oracles; never accept missing dependencies as SKIP.
- [ ] Improve deterministic nested promotion without weakening execution gates.
      In-flight hotlock windows are snapshotted, but new-lock sampling remains
      adaptive. Forced promotion is selftest-only, not a performance baseline.
- [ ] After correctness work, add typed bounded services with explicit argument,
      clobber, context, sleeping, overflow and side-effect contracts.
      General variadic printk remains excluded.
- [ ] Evaluate mutex parking/wakeup only after queue and stack lifetimes are
      covered under oversubscription.

## P2: Performance And Broader Scope

- [ ] Compare native locks, native delegation and JIT on equivalent workloads;
      separate translation, steady-state, queueing, hostcall and fallback cost.
      Measure throughput, p50/p99, CPU time, memory and cache transfers.
- [ ] Vary contention, CS size, input/state, threads and sockets with repeated
      trials. Establish amortization before claiming a JIT speedup.
- [ ] Evaluate contention/cost-based promotion, demotion, fairness and batching,
      then code-pool sizing and optional NUMA policies.
- [ ] Broaden opt-in spin NUMA tests before any default change; mutex currently
      has no NUMA-local delegation policy.
- [ ] Keep userspace/futex, rwsem and other ISAs outside the active scope.
