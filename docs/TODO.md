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

Latest complete matrix: **47/51 pass, 4 fail**; 33 passes execute generated
code, 12 are context refusals and two are native controls. All 40 unit programs
and the 25-case admission audit pass. Mode 0-7, including guarded mode 1/4,
pass actual JIT. The open gates are ordinary mode 8, its stage-2/3 register
cases and mutex learned-depth continuation:
[VALIDATION](VALIDATION.md#guarded-nested-admission).

Implement next in this order:

1. Resolve ordinary mode 8's retained empty/undecodable cold blocks. Distinguish
   missing text and decoder/CFG construction from real unsupported instructions;
   never omit a live block or remove register/context probes to pass admission.
2. Extend justified admission to the mutex depth helper learned after a real
   CALL miss. Current single-root guards cannot be borrowed by independent
   callee roots; the expanded image is refused even though its first prefix
   executes. Keep memory clobbers and two-word ABI; do not resume this native
   invocation inside JIT or silently add version isolation.
3. Re-run the complete matrix, retain failed attempts and classify actual JIT,
   context refusal and native-only controls separately.
4. Only then broaden context/resource coverage and consider optional services
   and performance. Do not mark C1/C2/C5 complete from selected fixtures.

### Guarded Admission Increment

Production conditional analysis collects required entry-range separations and
models callee-saved effects only at registered lock-control calls. Every premise
is checked before root body execution; missing cold text must be fetched first.
Results and remaining gates are in
[VALIDATION](VALIDATION.md#guarded-nested-admission); this does not close C1/C2/C5.

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
- [ ] Close the remaining ordinary mode-8 and mutex learned-depth gates without
      deleting register probes or treating missing/undecodable text as safe.
      Keep generated overlap-refusal tests and full-matrix results separate from
      fixture-only scope tests and captured-text feasibility.

## P0: Correctness Contracts

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
- [ ] Recover mode 8 register/CALL and mutex learned-depth acceptance on current
      source; a successful first prefix does not validate expanded callee code.
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

- [ ] Complete mode 8 and learned-depth acceptance, then broaden non-target,
      oversubscribed, cancellation and remote/deferred follower schedules.
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
- [ ] Resolve mode 8's cold CFG and learned mutex helper admission while retaining
      full checks on every executable JIT path.
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
