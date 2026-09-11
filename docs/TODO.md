# kdlock Open Tasks

Scope: x86-64 kernel spin/mutex delegation using existing guest hooks.
Do not modify/rebuild the guest kernel by default. Keep the two-word wrapper
ABI and physical native owners. New code needs purpose/constraint comments.
Complete the main behavior before optional features and performance work.

The **2026-09-11 reading handoff** adds purpose/constraint comments and the
[complete file map and manual sequence](PROJECT_GUIDE.md). It changes no runtime
statements and does not implement or unblock the pending guard. Verification
and its no-live-rerun boundary are recorded in [VALIDATION](VALIDATION.md#reading-handoff).

## Direction And Priority

The approved JIT-episode scope is implemented: an ordinary direct CALL miss
ends this JIT invocation and the original waiter completes the native suffix.
Admission and emission share the same scope. This replaces the old requirement
to admit that waiter-only suffix; it does not allow unchecked live JIT paths.

Main mode 0-8, guarded nested/register continuation and learned mutex-depth
gates pass actual JIT. Context refusals, native controls and real kernel
task/RCU/owner-ACK probes without JIT remain distinct acceptance categories.
Exact batch dates, counts and source identities live in [VALIDATION](VALIDATION.md),
not repeated task summaries. Passing these gates does not close the whole project.

Current correctness focus is C5's dynamic-address policy and checked use-time
native exits. Core static per-CPU and boot-reserved module ranges are implemented;
unresolved pointers and dynamic/module/context-object lifetimes are not. Resolve the local guard
flags boundary before changing execution semantics. The tracks below remain
open; their completed examples are coverage references, not tasks to rerun.
The pending [pre-instruction packet contract](JIT_REGISTER_ABI.md#31-访问时续跑的前置契约待实现)
now distinguishes successful guard preservation from original-waiter restoration.
Its flags changes are not yet authorized or implemented. Do not fill that decision
gap with more routine basic tests or reinterpret a prior scoped PASS as closure.

**Implementation blocked pending user decision:** allow or defer local
CF/PF/AF/ZF/SF/OF preservation for the new use-time guard and native resume
target. Existing C4 deferral remains binding; neither a guest-kernel change nor
a third wrapper argument is requested. The audit and packet requirements are
complete, not the guard or the project. Resume this implementation track only
after the scope decision; all remaining correctness items below stay open.

Open implementation tracks, in order, are below. Completed increments remain
checked off in their contract sections, not repeated as new work here.

1. Broaden combined pre-entry/PENDING resource failures and task-lifecycle
   schedules under [C1](#c1-forward-continuation-after-partial-execution).
   Preserve full packets, retained owners and exactly-once effects. The existing
   [resource coverage](#resource-coverage-increment) distinguishes production
   fixtures, live exhaustion, injected refusal and task/RCU probes.
2. Extend native-peer, cancellation, oversubscribed and multi-request remote
   schedules under [C2](#c2-one-protocol-per-physical-lock). Source leases and
   terminal retirement do not solve lock-object lifetime or arbitrary provider
   hot unload. Missing guest-reader/nonlocal-exit support requires separate
   assessment under [DESIGN 3.1](DESIGN.md#31-source-lock-and-hook-lifetimes).
3. Broaden composed CALL/RET, aliases and context-address handling under
   [C5](#c5-origin-context-and-nested-boundaries). Keep unconditional bans on
   every emitted block, including RET targets skipped by sequential facts.
   Checked mutex stack windows are not general stack privacy. Implement the
   new use-time exit only after resolving the local flags boundary above.
4. Validate each increment with affected complex cases and focused units using
   [regression selection](JIT_EXECUTION.md#7-分层与增量回归). Keep independent
   shadow/three-lock, native-control and kernel-probe contracts; do not rerun
   covered basics by default or combine different source freezes into one PASS.

[C3 versioning](#c3-immutable-jit-publication-and-lifetime) and
[C4 instruction/flags semantics](#c4-instruction-flags-and-fault-semantics) remain
explicitly deferred. [Evidence/services](#p1-evidence-and-useful-services) and
[performance](#p2-performance-and-broader-scope) follow correctness. No completed
bounded test closes C1/C2/C5 as a whole.

### Guarded Admission Increment

Production conditional analysis collects required entry-range separations and
models callee-saved effects only at registered lock-control calls. Every premise
is checked before root body execution; missing cold text must be fetched first.
Current results and remaining gates are in
[VALIDATION](VALIDATION.md); this does not close C1/C2/C5.

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
- [x] Add multi-callsite/shared-tail and actual rewritten-return execution to
      the existing guard test program, with exact callee/continuation stores.
      Reject a sensitive pointer carried from another caller through the same
      RET whitelist. These bounded guest-user images are not kernel lock tests.
- [x] Reproduce the long decoded-callee recursion failure and replace recursive
      return discovery with per-callee iterative traversal and staged tables.
      Check cycles, work exhaustion, incomplete CFG and final-emission refusal;
      no eligibility, wrapper ABI, flags or guest-kernel changes. The 1200-branch
      corpus tests table construction only; focused core/depth gates separately
      execute real JIT with mutex_jit=1. Do not repeat accepted basic cases.
- [ ] Broaden composed CALL/RET and alias schedules before further eligibility
      changes. These finite tests are not arbitrary-control-flow proofs.

## P0: Correctness Contracts

### Resource Coverage Increment

- [x] Inventory the principal pool/refusal classes and separate unstarted
      root fallback from progressed PENDING continuation and fail-stop exits.
- [x] Replace the copied execution hash model with production registration,
      partial-allocation/teardown, pool exhaustion and device-boundary tests.
      Add real registration-gate contention and seven assertion-detected mutants.
- [x] Use real lookup/ready in the high-level entry fixture; check 14 unavailable
      spin/mutex root cases without wrapper calls or packet/stack/ledger writes.
- [x] Replace both mutex node/shadow copied models with one production resource
      fixture: 256 reservation inputs, full 1024-slot collisions, early hook
      failures, no-node acquisition and full-packet resume after slot reuse.
      Test hook and direct entry paths and eight assertion-detected mutants.
- [x] Connect production task get/put and deferred free to final owner ACK in
      opt-in kernel `test_22`. Verify B->A and A->B with real mutex ownership,
      shared acquisition refs, allocation refusal and an RCU reader spanning
      removal. The release callback runs only after that reader leaves.
- [x] Join actual mode-8 JIT progress, real busy B and virtual-ticket/pin
      cancellation to native continuation for ENOMEM/E2BIG. Focused probes
      preserve full packets, frame/node/context storage, retained A and one
      native/owner-ACK lifecycle. Context absence and full count are injected
      inputs, not four live virtual nodes; execution flow is in usage 6.3.
- [x] Extend the same busy-B topology with 31 real physical lock acquisitions
      on each A candidate, filling its 32-ticket pool with A. Check genuine
      pre-publication E2BIG, unchanged packet/frame/node/context storage, retained
      A and exactly-once native completion/owner ACK. Extra promotion is
      controlled; ticket counts/capacity are not injected. Replace the simple
      PENDING smoke in routine scopes, retaining it for explicit diagnosis.
      The gate-map extension below adds real saturation; arbitrary pinned
      schedules remain outside this bounded case.
- [x] Extend the same real-ticket case with 1025 distinct hook-acquired locks
      while its JIT/native frame and A/B owners remain live. Observe all 1024
      allocated gates, per-lock membership/exact records and real refusal for
      fresh target requests. Require a non-target holder and a target to share
      Linux exclusion on an absent-gate lock, complete both records and join
      before releasing old B. Preserve the original packet/ticket/native/ACK
      checks, add only SELFTEST observations and test workload controls, and
      keep capacities/production ownership unchanged. Three focused units and
      the upgraded ticket plus shared-driver node-refusal complex gates pass;
      [gate pressure](VALIDATION.md#spin-gate-pressure) retains the evidence.
      No new daily case or basic sweep; this does not validate a progressed
      gate-allocation failure, arbitrary pressure combinations or cancellation.
- [x] Retain virtual cancellation, original-waiter signals/release races and main gates
      in the full-matrix manifest. Check shadow capacity separately, then units,
      audit, default build identity and drains on the same frozen inputs.
      Mode 3 waits for its exact published entry before JIT contention; failed
      attempts remain separate from corrected runs in VALIDATION.
- [x] Deliver real SIGUSR1/SIGKILL to the original waiter during native B
      waiting after JIT progress. Require the uninterruptible suffix, exact
      records and final owner ACK before userspace signal delivery/exit.
      Focused native-peer cancellation regressions also pass; usage 6.4 keeps
      these different participant/API contracts separate.
- [x] Exercise direct `mutex_lock_interruptible/killable(B)` ordinary CALL
      misses after actual JIT stores, without PENDING injection or helper
      indirection. Real `-EINTR` skips B's CS/unlock, completes A's record/ACK
      once and leaves B owned until after ACK. Keep fatal task lifetime checks
      free of extra test task refs; focused evidence and full-matrix results
      remain distinct in VALIDATION.
- [x] Race an identity-checked pidfd signal with the real B owner's release
      after actual JIT. Both native APIs return real 0 and -EINTR in focused
      tests; require branch-specific B ownership/work, exact JIT stores and
      final A ACK. Late signals wait in userspace only. Keep the actual unlock
      bracket distinct from the release gate, and scheduling bias distinct
      from a proven result; flow and regressions are in
      [usage 6.5](JIT_EXECUTION.md#65-原-waiter-与-b-释放的竞争).
- [ ] Broaden combined pressure, task exit/cancellation and multiple native
      frame schedules. These bounded checks do not close C1/C2/C5 or prove
      saturation of every live pool. `test_22` constructs its continuation and outer
      batch callback; it does not replace the actual-JIT/queue matrix.
      Arbitrary cancellation order, exit inside the native suffix and dropping
      an unfinished delegated frame remain outside these bounded B API tests.
      Earlier freezes are indexed in VALIDATION rather than repeated here.
- [x] Upgrade `native-4-4` to a same-CPU owner/waiter/trailer queue, with mutex
      workload barriers yielding to peers. Preserve actual JIT, PENDING packet,
      real B wait-list/ownership and final A ACK; check actual task/CPU context
      and exactly-once records. Focused register/signal regressions retain their
      independent contracts. Flow is in usage 6.1; no new daily case, owner
      handoff or guest-kernel change. Injected E2BIG is not capacity exhaustion,
      and this bounded schedule does not establish general oversubscription.
- [x] Extend `remote-late-3` with normal waiter TID detachment before a real
      no-lock root finishes. Keep the final ACK independent, compare the full
      saved frame/packet and executor context, and retain only a PID identity
      reference. Check the other retained-owner path and focused units, without
      another daily case or task-struct pin. Flow/limits are in usage 6.9;
      this does not establish RCU reclamation or arbitrary native-suffix exit.
- [x] Keep two independently queued mutex requests alive in real native
      continuation after each JIT prefix and B acquisition. Require distinct
      task/record/physical owners, both arrivals before either suffix resumes,
      and final ACK of the first before rechecking the second's retained locks.
      Both drain orders pass focused and frozen-matrix gates; usage 6.6 documents eight
      workers, separate entries, stopped daemon and exactly-once records.
- [x] Extend those two drain orders with real code-pool pressure while both
      frames are live. Register distinct loaded mutex CALL sites through normal
      hooks, verify 64 unique allocated blocks without partial entries/eviction,
      then observe a three-client queue's absent-entry pre-wrapper refusal and
      native ownership/exact records. Retain old images, four owner ACKs and
      terminal retirement/reuse of all 64 entries. Cold sites are not JIT
      positives; the existing shared-CPU pressure gate still passes separately.
      Evidence is in [the code-pool run](VALIDATION.md#code-pool-with-live-frames).
- [x] Extend the same two drain cases with 1025 distinct hook-acquired mutexes,
      exhausting the real 1024-slot shadow map. Require actual map membership,
      matched fallback identities and two target Linux waiters behind a native
      holder on an absent-shadow lock; all three complete before old frames
      resume. Keep the original JIT bodies, four ACKs and retirement/reuse gates.
      SELFTEST only controls promotion and observes counts; no new daily case,
      owner protocol or guest-kernel change. This unstarted fallback does not
      replace packet/RCU/other resource checks; flow and limits are in usage 6.6.
- [x] Consolidate duplicate smoke cases and replace unconditional baseline
      sweeps with explicit, deduplicated regression scopes. Keep independent
      hostcall/register/refusal/cancellation/RCU oracles; verify selection,
      failed-case stops, generated-file filtering and representative live JIT.
      Guard every routine scope against reintroducing superseded diagnostics;
      preserve explicit selections and a readable full unit inventory. The
      selection-only follow-up runs focused units/preview, not more live smoke.
      Incremental evidence and earlier complete acceptance remain separate.
      Retain forced interruptible/killable cancellation separately from release
      races: only the former requires native B to remain held through the final
      A ACK. The existing selection test checks this distinction without adding
      a daily case; the consolidation policy is complete for the reviewed cases,
      not a recurring baseline sweep or a claim that all tests are equivalent.
- [x] Repair the catalog omission of existing early-A/native-C dependency gates
      in both backends. Keep their real capacity/remaining-owner progress
      contract separate from ordinary held-B CALL misses, replace only the
      two plain stage-3 diagnostics with their register variants, and verify
      exact arguments, scoped inclusion, deduplication and explicit selection.
      The extended count stays unchanged; this selection-only check is not a
      new live JIT or arbitrary deadlock-recovery result. Flow is in usage 6.10.
- [x] Exercise same-CPU context refusal using the real mutex queue, a paused
      JIT/native frame and a second ready entry. Match task/entry/CPU/lock,
      retain the first frame until the refused waiter completes natively, and
      check both records without injected contexts or extra task references.
      This does not cover arbitrary task exit, fixed RCU readers, unrestricted
      oversubscription or concurrent replacement of a shared code image.
- [x] Extend the same workload with four real occupied mutex nodes on CPU 1
      while a JIT/native frame remains live. Verify the fifth request's full
      reservation mask, own-stack acquisition, native owner and exact record,
      alongside the second queue's context refusal and the first frame's ACKs.
      No resource injection, fabricated frame or guest-kernel change. Replace
      simpler same-CPU placement in daily scopes; keep it only for diagnosis.
      This covers one combined schedule, not arbitrary resource combinations.
- [x] Extend that same complex case with a distinct request whose A task-record
      allocation fails through the existing one-shot injection. Require native
      ownership and exact completion of both refused requests before the old
      frame resumes; check task/entry/lock identity and no extra body or ACK.
      Add only a production refusal diagnostic and purpose comments, and retain
      a type-checked logging substitute in the production resource fixture.
      This is not a new simple test, actual memory exhaustion, renamed-waiter
      coverage or a source/provider-lifetime solution.

### C1. Forward Continuation After Partial Execution

Implemented boundaries:

- Ordinary CALL misses resume the original waiter at current callee RIP with
  current GPRs and virtual return stack; no entry replay or memory rollback.
- Validated PENDING lock-resource failures can retain the original lock CALL
  packet before acquisition/publication. Later phases cannot use that path.
- Native registration checks NONE, eligible PENDING, validated spin remote
  COMPLETE relay, checked mutex STACK_CHANGED or local spin SPIN_NATIVE before
  publishing borrow state or accounting progress. Post-CALL tags never replay
  an acquired lock; generic ACQUIRED/COMPLETE remain rejected.
- Physical owners keep locks and acknowledge waiter unlocks. Nested and
  out-of-order paths retain explicit ownership/lifetime records.

Remaining:

- [x] Recover mode 1/4 register/CALL, held-B and pending-B gates under guarded
      admission, with exactly-once protected-state and ownership checks.
- [x] Recover mode 8 register/CALL stages 2/3 with real body evidence and
      exactly-once checks; preserve GPR/stack probes and owner notifications.
- [x] Recover mutex learned-depth acceptance on current source; a successful
      first prefix does not validate expanded callee code.
- [x] Revalidate both existing early-A/native-C dependency cases after the
      checked-stack analysis/executor changes. Require actual JIT, real ledger
      exhaustion with A already released, matching PENDING/native RIP/RSP,
      native C-owner progress and seven ordered owner ACKs with exact records.
      No runtime change or repeated basics are needed; the mutex's checked
      windows remain equal. This is not a new full-GPR/flags sample or general
      deadlock-recovery proof. Current evidence is in
      [early-outer continuation](VALIDATION.md#early-outer-continuation).
- [x] Add a checked local spin post-acquisition EIO checkpoint with retained
      B and exact post-CALL continuation. Verify full packet/stack preservation
      and owner/ledger/refusal predicates in production C fixtures, then reuse
      the complex nested workload for real JIT, B/A owner ACKs and exact effects.
      Keep ordinary spin/mutex register cases distinct; this live checkpoint is
      not full hardware-register/flags evidence or remote/fault recovery.
      Flow and scoped commands are in [usage 6.11](JIT_EXECUTION.md#611-spin-获取后的受检续跑).
- [x] Upgrade that same post-acquisition case from FAST to a real private B
      queue head with a follower. Check the committed A prefix, QUEUE_OWNER
      result, retained A/B owner, exactly-once native suffix and final ACKs.
      Keep the original complex B state and register probes; the redundant
      extra A state machine exceeded bounded admission and was removed without
      changing analyzer limits. Both this case and the affected early-A
      dependency pass actual JIT; the first rejection is archived separately.
      FAST remains explicit diagnosis, not an additional daily prerequisite.
- [ ] Prove/test each additional recoverable exit with registers, stack,
      ownership and exactly-once side effects. Unsupported post-entry exits
      remain fail-stop, not restart-at-entry fallbacks.
- [ ] Exercise bounded exhaustion and partial progress across frame, node,
      lock and code pools using production paths.
      Code-pool root refusal now passes the two-frame live gate above, alongside
      prior node/context/task combinations. Both existing eight-frame spin gates
      now check real inherited-lock-record saturation, the complete PENDING
      packet and retained owners through actual JIT/native/ACK execution. This
      does not reach the separate local-shadow refusal or prove arbitrary frame,
      held-lock, gate/ticket combinations. Do not fabricate entries, shrink
      capacities or count uncompiled filler sites as JIT.
- [x] Review apparent physical-depth/shadow-capacity duplication against actual
      branch order. Preserve the independent later shadow check, strengthen the
      complex chain observer without another workload, and retain the first
      failed premise as separate evidence. Flow and scope are in usage 6.8.
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
- [x] Join native B peers to both existing dual-frame drain orders. Require
      two genuine Linux wait lists, initial and cross-lock trylock exclusion,
      own native acquisition/exact records, and the second frame retaining B
      until the first peer unlocks. Keep four original owner ACKs, no peer JIT
      or kdlock task refs, and preserve source retirement/reload checks. Both
      orders and the shared-driver pressure case pass; usage 6.6 records flow
      and scope. This initial gate did not cover cancellation; the same cases
      are strengthened below, not retained as a second daily run.
- [x] Cancel each non-target B peer's real interruptible wait while both old
      frames remain live, verify userspace EINTR and exactly one explicit retry
      by the same task/PID, then observe both real wait lists again before
      source retirement/draining. Check pidfd/client identity, both retained
      owners, no peer acquisition/unlock on cancellation, original ACKs and
      resource/reload records. Both drain orders, shared-node pressure and
      independent legacy signal clients pass. No frame abandonment, test-owned
      task refs or owner handoff; arbitrary cancellation/fairness remains open.
- [x] Compose renamed original waiters with those two-frame schedules. Require
      both arrivals before independent native C acquisitions/unlocks, actual
      waiter-owned C and unchanged borrowed A/B owners while admission is OPEN.
      Preserve the non-target comm through pool pressure, peer cancellation,
      retirement and both owner ACKs; restore only after the final record.
      Check absent/idle C-shadow paths against production hook functions and
      reject wrong-identity/early-restore/extra-ACK evidence. Both live drain
      orders and the affected pressure driver pass. This is bounded active-task
      routing, not arbitrary rename/exit scheduling or RCU reclamation.
- [x] Review source/lock reuse, module dependency/pin order and actual guest
      hook readers. Record plain-address metadata, non-target/INT3 predicate
      readers, exit-before-GOING notification and skipped C-return boundaries.
      Evidence is a read-only source/interface audit, not live unload acceptance.
- [x] Separately assess missing hook capabilities without modifying the guest
      kernel. Four lock dispatch sites plus the shared trap reader, provider
      registration/drain and nonlocal reference release need a coherent design;
      an extra callback-local ref or RCU wait is insufficient. No owner handoff.
- [x] Design/implement bounded source dependency pins and explicit quiescent
      metadata retirement without reverse module-dependency retention. Cover
      root/learned text and prevent stale RIP acceptance after source reuse.
      Implementation order, each with its own evidence:
      1. **Done:** bind daemon I/O, cache and translating children to one device session;
         reject a lost/mismatched inherited descriptor instead of reopening.
         Focused units, real cdev-owner/orphaned-child observations and complex
         JIT/learned-callee/native-only gates pass; evidence is in VALIDATION.
      2. **Done:** pin bounded root/learned source dependencies before inspection and
         registration; distinguish LIVE core text from freed/init/unknown text.
      3. **Done:** close new JIT admission, drain writer sessions and execution/native
         frames, invalidate cached entries, then release pins. Retirement is
         terminal; rebuild the whole session before replacing source modules.
      4. **Done, bounded coverage:** production source/device/registry units and both live
         two-frame drain orders verify busy retirement, continued owner ACKs,
         dependency unload refusal, terminal invalidation and pin release.
         Existing hostcall, learned-depth, spin-native, remote and context gates
         also pass. A real fork/exec lease probe survives its parent, reads while
         DRAINING, refuses publication and independently blocks retirement after
         frames drain. Reloading the source with old RIP/lock addresses while
         preserving the retired registry now passes real native contention and
         six exact records without JIT or kdlock ACKs. `native-mutex-depth` now
         verifies local and cross-module CALL misses in separate joined waves,
         then the external helper's JIT execution/return before the same capacity
         exit in the local helper. Two source pins and native loader refs
         are checked separately through terminal invalidation and normal unload.
         This is not live cap saturation or broader CALL/RET/context acceptance;
         C5's bounded two-level increment is recorded separately below.
         Each increment retains its own frozen evidence.
         A device fops reference alone does not complete hook-reader protection.
- [ ] Define a provider reader/drain and nonlocal-exit lifetime protocol before
      claiming generic hot unload; no guest edits authorized by this audit.
      Lock allocation/free identity also needs separate subsystem integration.
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
- [x] Isolate shared RET joins from control-call spill clobbers using decoded
      two-depth prologues/epilogues. Preserve exact RSP partitions and pre-pop
      target facts without changing emitted whitelists; unknown/partial targets
      still join all effects. Execute the bounded generated positive and retain
      rewritten-return context negatives, disconnected text and budget refusal.
- [x] Reproduce explicit forbidden operations surviving in emitted, whitelisted
      RET successors that receive no sequential dataflow state. Run unconditional
      context/backend checks over the entire selected emission scope before
      precision retry; retain ordinary CALL-miss suffix exclusion and existing
      value/alias analysis. Extend the existing CALL/RET unit program for both
      backends, without executing forbidden instructions or adding daily smoke.
      This is not runtime return-slot validation or concurrent-mutation safety.
- [x] Preserve alternate live paths, learned-target reanalysis, indirect-call
      conservatism and CALL stack-write checks while improving precision.
      The two-level helper now uses the checked mutex summary below. Saved-value
      reloads outside its negotiated window, unrecognized CALL packets and other
      controls retain clobbers. Handler GPR preservation alone does not establish
      stack privacy; broader alias/control-flow schedules remain open.
- [x] Reproduce admitted runtime entry/loaded pointers and a pointer changed
      after a JIT store, using mock sensitive symbols and harmless generated
      userspace code. Keep static rejection as the control. Report successful
      screening's limit once per image without changing admission/emission;
      extend the existing diagnostic test, not the daily live catalog.
- [x] Audit existing per-CPU helper scopes and add core static runtime ranges
      through the existing leased reader. Validate all possible CPUs, bounded
      complete/stable metadata and interval boundaries; do not add the linked
      zero-based section as low memory. Preserve full-area coverage across
      interior names. Verify real-address refusals, existing unit/audit programs
      and affected complex JIT gates; no guest change or new daily case.
- [x] Extend the same range policy to the x86-64 boot-reserved module arena.
      Negotiate its extent through version 2 of the existing 16-byte CAPS on
      the validated lease; missing capability is an infrastructure error, not
      omitted screening. Check alignment, overlap/overflow, old/invalid packets
      and source retirement using existing unit programs. Actual module-arena
      operands are refused without execution, while affected complex JIT,
      writer/drain and stack-continuation gates pass. Do not classify whole
      units or infer module-object validity from a boot-fixed address range.
- [x] Audit the actual two native restore stubs and wrapper in guest userspace:
      restored GPR/RIP/RSP and copied software packets do not establish live
      condition-code restoration. Record the pending packet contract in the ABI,
      not a new daily case. This is a prerequisite audit, not a runtime guard,
      kernel JIT result or permission to reopen C4.
- [ ] Define enforceable dynamic/module/context object ranges and lifetimes
      before adding runtime checks. Core/module arena coverage is implemented, but
      kallsyms and entry alias separation are insufficient for the wider policy.
      Resolve the local guard-flags scope separately from deferred C4 work.
      Follow [the implementation order](DESIGN.md#721-dynamic-address-gap).
- [ ] Validate each actual address once at its use, or reject before progress
      when the instruction/access cannot be supported. Establish a checked
      pre-instruction native packet, no replay, and physical-owner ACKs first.
- [ ] Cover dynamic pointer/RET replacement and implicit/RMW accesses in the
      existing negative/continuation gates; preserve complex actual-JIT modes.
      Source RBP/RSP are not private memory and entry GPRs are not stable C
      arguments. Sequential facts and mutex checkpoints do not prove freshness.
- [ ] Broader context equivalence, hidden/unresolved calls and native suffix
      owner-sensitive operations need separate analysis. Logical current is
      not a scheduling, IRQ, RCU or hardware GS switch.

#### Checked Mutex Stack Increment

The runtime guarantee precedes analysis. This bounded increment now reaches the
actual two-level learned helper, without inlining away its local adapter; it
does not close the broader C5 context/alias work.

1. [x] Validate the wired 256-byte checkpoint around local mutex controls:
   original-task stack bounds, nofault reads, unchanged CALL token and exact
   post-CALL packet; a distinct changed-stack native boundary retains real
   owners. Insufficient space uses an unstarted PENDING CALL; unreadable or
   corrupted packets remain errors. Run production-function byte/packet/ledger
   checks, affected complex JIT/native gates and default kdlock builds.
   The original live freeze checked equality; the concurrency gate below now
   separately validates changed-stack handoff on real Linux mutex contention.
2. [x] Exercise a real native B holder writing an intentionally exposed waiter
   stack slot while the combiner waits. Require current value, exactly-once
   suffix and physical-owner ACKs; a fixture mutation is not this concurrency
   proof. Extend an existing complex driver, not another smoke prerequisite.
   `native-mutex-stack-change` now observes the combiner in B's native wait_list,
   writes the live local word, matches the post-CALL IP to the loaded module,
   retains the root's NORMAL entry and verifies two owner ACKs. This and four
   affected complex gates pass; source/evidence are in
   [the real stack mutation run](VALIDATION.md#real-mutex-stack-mutation).
3. [x] Negotiate this immutable runtime capability through the same device
   lease before analysis relies on it. Keep the 64B/24B and two-word wrapper
   ABIs. An absent/old/malformed capability must not enable preservation.
   `KD_JIT_CAPS` supplies a separate 16-byte packet; the validated descriptor
   is queried once before text inspection, and its cached bound clears on close.
   ENOTTY/unknown packets keep zero; other I/O errors abort the session. The
   actual surviving writer retains the same contract through DRAINING in both
   existing drain orders. Units and affected JIT/refusal gates pass; see
   [capability validation](VALIDATION.md#runtime-capability-negotiation).
4. [x] Retain only verified-window facts at registered mutex controls, with
   exact base/range membership for every RSP alternative. Preserve ordinary
   CALL, spin, out-of-window and alias clobbers and all work/partition limits.
   Check generated shared/private RET positives and sensitive-pointer negatives.
   Normalize and verify the eight-byte CALL push first; retain only post-write
   facts, never a restored pre-CALL snapshot. The same device lease supplies
   the bound, and unknown capability/addresses keep conservative behavior.
5. [x] Restore the real two-level helper in the existing learned-depth gate;
   prove both learning stages, translated helper/RET, real capacity exit,
   source pins, exactly-once records and native owner ACKs with mutex_jit=1.
   Two joined waves learn the local and external CALLs; the final JIT returns
   from the external helper before the local helper's capacity exit. The local
   RET then completes natively, not in JIT. Focused units/audit and affected live
   gates pass in [checked two-level validation](VALIDATION.md#checked-two-level-mutex).

## P1: Evidence And Useful Services

- [ ] Make full-matrix evidence retention reproducible from a fresh checkout:
      commands/env, source/kernel/artifact identity, exit statuses and drains.
      Returned body witnesses are implemented; generation identity is not.
- [x] Automatically retain each selected scope's frozen runtime/test source,
      captured kernel config/patch, boot notes, generated files and declared
      protocol/daemon logs. Preserve drained failures, record incomplete
      evidence and gate acceptance on capture success. Protocol symlinks are
      metadata only, never followed or extracted as links. Focused units and
      complex positive/refusal gates pass; retain the earlier capture failure.
      This does not provide the historical matrix's two external native-control
      helpers on that earlier freeze. The control-driver gap is resolved below;
      system dependencies and immutable/loaded-image identity remain separate.
- [x] Deliver the two historical pure-native register controls through the
      existing `test_10` driver and explicit `native-controls` selection, without
      a `/tmp` helper or another smoke script. Check the same assembly/GPR/stack
      records plus zero registry/source users, zero JIT and zero owner ACKs.
      Keep them out of all daily/extended scopes; verify the changed driver with
      two existing nested register JIT cases and focused units. Historical
      commands remain historical; pre-existing artifacts are not new execution.
      Usage 3.1 and VALIDATION carry commands and this freeze's evidence. This
      does not bundle a guest disk, system packages or a reproducible kernel build.
- [x] Observe the selected run's starting build environment, tool paths/versions/
      binary hashes, PATH-selected Python and installed translator dependency
      metadata, plus mount/preemption/sysctl settings. Bound read-only commands,
      retain failures and stop before workload execution on incomplete capture.
      Reuse the evidence/selection unit program; no extra smoke or JIT rerun.
      [Environment evidence](VALIDATION.md#environment-evidence) passes 41 methods.
      These observations do not bundle dependency bytes, prove loaded/imported
      image identity, freeze the environment during execution or cache a PASS.
- [x] Deliver an offline verifier for current captured-run directories, replacing
      temporary per-turn scripts for common integrity/status checks. Check exact
      source/archive membership and hashes, boot notes, selection/journal order,
      status/log/marker agreement and stable file identity without executing any
      payload or consulting the live guest. Bound reads/expansion, reject links
      and duplicate metadata, and keep failed/unrecorded cases nonpassing.
      The existing selection/evidence unit program and prior success/failure
      captures validate it; this is not a new JIT run, trusted provenance,
      current-source acceptance or a replacement for case-specific oracles.
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
