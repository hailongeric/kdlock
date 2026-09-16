# kdlock Open Tasks

Scope: **x86_64 machines only**, for kernel spin/mutex delegation using existing
guest hooks. Cross-architecture ports and their tests are not project tasks or
deferred deliverables. Userspace/futex and rwsem are also outside this scope.
Do not modify/rebuild the guest kernel by default. Keep the two-word wrapper
ABI and physical native owners. New code needs purpose/constraint comments.
Complete the main behavior before optional features and performance work.

## Current Checkpoint

**2026-09-16:** spinlock and mutex delegation both support explicit GS memory
operations by default, using the origin waiter's base;
supported `current_task` reads use the logical task. Published delegation
waiters remain preemption-disabled and PAUSE-poll until completion or native
handoff. IRQ/NMI access and native-service context remain separate limits.
[GS validation](../tests/README.md#gs-polling-validation) records the two actual
JIT positives and affected unit checks; it does not validate old same-CPU
schedules that depend on a queued waiter yielding.

Tests are grouped by purpose, with two basic C programs as the default and
affected Python drivers selected explicitly. The
[directory validation](../tests/README.md#test-directory-validation) covers
basic and related functionality without a full or live rerun. Benchmark
assembly exports also group identical code by critical section while retaining
source sessions; their validation stays in the
[benchmark README](../bench/spin_cacheline/README.md#assembly-inspection).

The [current-version overview](PROJECT_GUIDE.md#1-当前进展) lists implemented and
deferred capabilities. This documentation/commit step adds no new experiments
or runtime changes. Earlier checkpoints remain in [VALIDATION](VALIDATION.md);
their PASS results are not acceptance of the complete current tree.

## Delivery Scope

**2026-09-14 user decision:** extremely uncommon scenarios do not require further
implementation or dedicated tests for the current delivery. Prioritize the
supported x86_64 main paths; do not continually expand corner-case coverage.

- Keep main-path acceptance: contended spin/mutex JIT, nested critical sections,
  allowlisted services returning to JIT and supported native continuation.
  Mutex positives use `mutex_jit=1`; require matching generated code, returned
  body evidence, correct effects and native-owner/ACK completion.
- Additional combinations of extreme pool pressure, exceptional cancellation/
  exit order, remote schedules or arbitrary aliases are optional coverage,
  not current completion gates. Do not add or run them merely because a broader
  C1/C2/C5 contract remains unproven. Revisit when a supported workload exposes
  a defect, a relevant main-path change needs regression, or the user requests it.
- Keep unimplemented behavior and untested risk in the limitations. A scoped-out
  case is not a PASS, and this priority decision is not a measured failure rate
  or a claim of general correctness. Existing refusal checks, warnings, owner
  rules and historical evidence stay intact; this is not a test-deletion task.
- Run affected existing units and representative JIT cases for code changes,
  not a mandatory full or rare-case matrix on every increment. A reproduced
  main-path crash, deadlock, incorrect effect or missing JIT is still a defect;
  do not dismiss it as rare or weaken the oracle to accept it.

**2026-09-16 test-scope decision:** use basic simple checks plus directly
affected functionality. Full unit and live suites require explicit selection;
directory, documentation and selector changes do not trigger a live matrix.
See [test commands](../tests/README.md#环境与单元测试).

Below, **optional coverage/generalization** is not a pending delivery obligation.
Ongoing protocol constraints apply when touching that code, not as standalone
unfinished features. C3/C4 and access-time guard deferrals remain unchanged.

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

**2026-09-13 user decision:** continue deferring the access-time address guard,
its pre-instruction original-waiter continuation and the required local
CF/PF/AF/ZF/SF/OF preservation. These remain **unimplemented limitations**, not
an outstanding authorization question or the next implementation step. The
[deferred work](#deferred-access-time-guard) and
[future packet contract](JIT_REGISTER_ABI.md#31-访问时续跑的前置契约待实现) remain
documented for a later explicit request to reopen this feature. C3/general C4
deferrals, the existing guest kernel and the two-word wrapper ABI are unchanged.

Core static per-CPU and boot-reserved module screening is implemented; it does
not validate each actual access or establish dynamic/context-object lifetimes.
Unknown or concurrently replaced pointers can still bypass static checks. Keep
this limitation explicit and restrict use to audited experimental workloads.
Completed examples are coverage references, not tasks to rerun or evidence that
the deferred guard is complete. Broader C1/C2/C5 claims remain unproven, but their
rare-case expansion is optional under the [delivery scope](#delivery-scope).

Current implementation priorities are:

1. Fix concrete defects affecting supported main paths under
   [C1](#c1-forward-continuation-after-partial-execution),
   [C2](#c2-one-protocol-per-physical-lock) and
   [C5](#c5-origin-context-and-nested-boundaries). Preserve packets, real lock
   owners, exactly-once effects and existing admission checks. Do not choose
   another extreme resource/schedule combination simply to extend coverage.
2. After affected main paths pass, work on useful services, usability and
   measurements under P1/P2 without first proving every rare interleaving.
   Generic hot unload and lock-object integration remain unsupported; any
   future expansion needs the separate assessment in
   [DESIGN 3.1](DESIGN.md#31-source-lock-and-hook-lifetimes).
3. Validate each increment with affected representative cases and focused units using
   [regression selection](JIT_EXECUTION.md#7-分层与增量回归). Keep independent
   shadow/three-lock, native-control and kernel-probe contracts; do not rerun
   covered basics by default or combine different source freezes into one PASS.

[C3 versioning](#c3-immutable-jit-publication-and-lifetime) and
[C4 instruction/flags semantics](#c4-instruction-flags-and-fault-semantics) remain
explicitly deferred. [Evidence/services](#p1-evidence-and-useful-services) and
[performance](#p2-performance-and-broader-scope) follow main-path correctness,
not exhaustive rare-case coverage. No bounded test proves C1/C2/C5 in general.

### Main-Plan Acceptance Audit

**2026-09-13:** separate finite implemented contracts from open-ended coverage
expansion and capability limits. The original objective is unchanged: actual
JIT delegation of existing kernel critical sections, including nested A/B,
services and forward native completion under real lock protection. A single
new schedule or a union of old PASS results is not whole-plan acceptance.

| Required behavior | Current implementation to inspect | Acceptance evidence and remaining boundary |
| --- | --- | --- |
| Discover, translate and execute an unchanged supported CS | `kd_lock.c` hooks, `daemon/daemon.c`, `disassem/disassem.py`, `exe.c:kd_exe_on_call_hl_entry` | Matching generated image, NORMAL publication, returned body and exact workload state; no validated unmodified production subsystem or speedup claim |
| Delegate nested A/B and preserve physical/logical parents | `kd_spinlock.c:execute_cs`, `kd_exec.c` remote protocol, native nested mutex handlers | `core`, mode 6, physical/remote depth and learned mutex gates; mutex B remains a real acquisition by A, not a spin-style remote mutex |
| Keep one physical lock protocol for target/native tasks | Spin L/S + origin tickets, native mutex owner + scheduling gate | Mixed/native-peer, same-CPU and parallel gates; a borrowed waiter is never made the Linux mutex owner |
| Leave large supported services out of translated code and return to JIT | `include/kd_hostcalls.def`, `exe.c` typed dispatch/return | Mode 2/5 cover a resolved clock and scalar int_sqrt, including clock quota; the audit freeze below predates the scalar increment. General variadic printk and new service contracts remain P1 work |
| Continue after partial progress without replay | Current CALL, PENDING, checked post-control and quota boundaries in C1 | Register/stack, retained-owner ACK and exact-effect gates; generic faults, IJ miss and instruction budget remain fail-stop, not recoverable exits |
| Preserve the two-word register/context ABI | Wrapper, two restore stubs and `kd_exec_frame` | Production/codegen units and eight register gates; software flags copies do not establish live flags restoration |
| Screen the actual possible JIT scope | `context_policy.py`, `context_memory.py`, entry predicates and range metadata | Twelve independent admission negatives plus generated-code units/audit; runtime pointer freshness/access checks remain explicitly deferred |
| Finish requests and retire source metadata coherently | Native routing, task/RCU refs, `kd_source.c` and device-session retirement | Task probes, dual-frame retirement/reload and waiter-exit gates; generic hook-reader and lock-allocation lifetimes remain separate capability gaps |
| Deliver usable commands and inspectable evidence | Manual/file map, existing selector, source/boot/archive verifier | One frozen input set, individual outcomes/drains/images and guest-local archives; no implied dependency-byte reproducibility or immutable JIT identity |

Finite closure steps for this audit:

1. [x] Inspect those production branches and distinguish supported continuation
   packets from the explicitly deferred features and missing hook capabilities.
2. [x] Freeze current host/guest inputs; run the existing 39 unit programs and
   independent admission audit in the recovery guest. A compile error, SKIP or
   missing prerequisite is a failure, not an accepted negative test.
   All 206 runtime/test hashes match. The guest reports 39 passed unit programs
   and 25 passed admission cases (17 expected refusals, eight accepted assembly
   cases); the latter is not native or kernel-JIT execution. Logs and source
   snapshots are in `/tmp/kdlock-acceptance-audit-units.sRPnuo` in the guest.
3. [x] Run the existing 64-case `extended` scope on the same freeze. Do not add
   baseline, native-controls or the eleven covered diagnostics. Mode 0/1/3
   retain their documented complex replacements; this is not a fresh direct
   run of those excluded modes or the historical 67-case selection.
   The runner exits 0 with 64/64 accepted cases: 50 actual-JIT positives,
   12 admission refusals and two kernel protocol probes without JIT.
4. [x] Inspect every case outcome, distinguish JIT/refusal/kernel-probe evidence,
   verify final drain/source/kernel identity and retain failures independently.
   Fix an identified contract gap before considering another coverage variant;
   never splice different freezes into a current-matrix PASS.
   All 64 result/archive records pass independent checks. Saved phase logs have
   1,538 distinct returned-body records with matching generated entries, not
   immutable-version or full-instruction coverage. The guest-local 592-member
   outer archive also verifies; final drain, 206 source hashes, boot and kernel
   baseline are unchanged. Commands, scope and archive identity are recorded in
   [VALIDATION](VALIDATION.md#main-plan-acceptance-audit).

Maintaining node/owner/ACK invariants below is an ongoing constraint, not an
unbounded invitation to add tests. Broader schedule/alias coverage is optional
under the delivery scope; no bounded matrix proves arbitrary concurrency.
Generic hot unload needs the guest reader/nonlocal-exit protocol assessed in
DESIGN 3.1, and lock-object
identity needs subsystem integration. They cannot be completed by an extra
kdlock callback-local ref under the no-guest-edit default. C3/C4 and access-time
guard deferrals are not pending permission questions. New services, environment
packaging and performance remain distinct P1/P2 requirements, not silently
removed by accepting the present supported execution contracts.

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
      refusal path. Preserve two arguments, unsupported-context refusal and progressed
      fail-stop behavior. Validate a non-root child's published logical parent,
      CALL phase/packet, task, GS and lock depth before first dispatch. This is
      logical scope, not a version certificate; C3 remains deferred. Conditional
      analysis permits one explicit root and no independently seeded callee.
- [x] Complete mode 8's cross-window CFG and interior-root dispatch labels.
      Decoder seeds do not become independent admission roots; unsupported
      context operations, bad instructions and expansion exhaustion still refuse. Ordinary mode 8 and
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
      corruption, context operations, return-table mismatch, disconnected/indirect
      entry and budget negatives. Explicit GS cases now expect origin-context
      execution under the 2026-09-16 policy. Run real helper learning and capacity/owner ACK checks
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
- [ ] Optional coverage: broaden composed CALL/RET and alias schedules.
      Any future eligibility change still needs its own affected-path checks;
      existing finite tests are not arbitrary-control-flow proofs.

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
      Test hook and direct entry paths with assertion-detected mutants.
- [x] Migrate retained node, mutex-transition, frame, CALL and tail model contracts
      into existing production fixtures, then remove the five copied programs.
      Cover rename/closing routes, dense ledger metadata, terminal/remote
      retirement and backend cleanup without adding routine test entries.
      Replace the obsolete early-outer deletion model with retained released
      records; helper cleanup tests do not authorize post-JIT rollback. The
      [per-contract map](TEST_EXAMPLES.md#52-单元精简进展与顺序) distinguishes
      current focused evidence from earlier unchanged producer checks. Typed
      service dispatch/return/budget checks and real nested mutex CALL producers
      replace the old service and remote-mutex model; physical primitives remain
      substitutes. Real mutex tail encode/decode now covers the 40-CPU/four-slot
      fixture topology with fixed wire values and producer node identity; remove
      the unused legacy mock/assert headers and rebuild the remaining C programs.
      This does not prove per-CPU concurrency. C1/C2/C5 are not closed.
- [x] Retain the independent remote protocol unit while replacing its three-field
      register substitute with the guest's full x86-64 pt_regs. Check packet/CALL
      preservation across ancestor RPC and native ACK, detach-before-DONE and
      immediate no-lock parent reuse; reject eight assertion-detected mutants.
      This extends one existing program, not the live selection. Deterministic
      publication observations do not prove hardware flags or general lifetimes;
      production and guest-kernel code remain unchanged in this increment.
- [x] Enforce native-reference retirement at the common frame pop boundary.
      Initialize empty routing on allocation; reject a terminal frame with a
      native request or linked registration without changing packet/storage or
      dropping its source lease. Reuse production frame and spin-combiner units,
      including independent bad-state combinations and assertion-detected guard
      mutants. This is a checked API invariant, not a reproduced live UAF or
      permission to abandon an unfinished native suffix; existing owner/ACK
      completion remains required. Flow is in
      [frame retirement](JIT_EXECUTION.md#frame-回收门禁); two focused units and
      eight affected complex JIT cases pass on the
      [recorded freeze](VALIDATION.md#native-frame-retirement). This does not
      close arbitrary resource/task-lifetime combinations under C1/C2.
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
      No new daily case or basic sweep. That earlier freeze validates only
      fresh-request gate fallback; the progressed increment follows below.
- [x] Keep the old ticket/native frame live while a second prepared A2 root
      executes JIT stores and reaches real gate-map ENOMEM at lock(C). Retain
      A2's physical owner, preserve the PENDING callee/CALL stack, observe both
      live frames and original-waiter Linux C contention, then require one
      suffix and final A2 ACK before releasing the old B. No capacity, owner,
      guest-kernel or recovery-ABI change. Two existing units plus upgraded
      `virtual-ticket-refusal` and shared-driver `virtual-node-refusal` pass on
      the [recorded freeze](VALIDATION.md#progressed-spin-gate-refusal).
      The production fixture checks full map/ticket/frame/node/context/packet
      preservation; actual JIT and Linux waiting remain separate live evidence.
      No new routine test entry; broader pressure/cancellation and C1/C2/C5
      remain open. This is a supported CALL boundary, not the deferred guard.
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
- [ ] Optional coverage: broaden combined pressure, task exit/cancellation and
      multiple native frame schedules. These bounded checks do not close
      C1/C2/C5 or prove saturation of every live pool. `test_22` constructs its continuation and outer
      batch callback; it does not replace the actual-JIT/queue matrix.
      Arbitrary cancellation order, exit inside the native suffix and dropping
      an unfinished delegated frame remain outside these bounded B API tests.
      Earlier freezes are indexed in VALIDATION rather than repeated here.
- [x] Extend the existing dual-frame drain orders with two single-process
      original waiters. Signal the first with SIGKILL and the survivor with
      SIGUSR1 while both frames retain A/B. Keep the second native suffix at
      a bounded fixture gate until a retained pidfd proves the first task exited
      after both real owner ACKs; require one remaining frame, then finish its
      exact record/ACKs and userspace signal return. Preserve pool pressure,
      native-peer cancellation and terminal source retirement/reload. No extra
      task refs, owner handoff, guest-kernel changes or new routine cases.
      Both orders and three affected regressions pass with actual JIT; see
      [original-waiter exit evidence](VALIDATION.md#original-waiter-exit).
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
- Ongoing constraint: if a new recoverable exit is added, verify registers,
  stack, ownership and exactly-once effects for that exit. No additional exit
  is required just to handle rare failures; unsupported post-entry exits remain
  fail-stop, not restart-at-entry fallbacks.
- [x] Implement checked call-count quota exits before dispatching the excess
      callee. Keep its current GPR/callee RIP/CALL RSP and physical owners;
      the original waiter finishes the native suffix without returning to this
      JIT. Validate the existing hostcall policy without invoking the service,
      and keep invalid packets/targets or post-dispatch failures fail-stop.
      Do not classify quota as a callee-learning miss, consume the pending
      return word, expand wrapper arguments, or change instruction-budget/flags
      semantics. Extend the existing production consumer unit and mode 5's
      complex service workload, preserving its normal JIT-return checks; no
      additional routine test entry. Four affected guest units and six complex
      JIT cases pass on their [recorded freeze](VALIDATION.md#call-quota-continuation).
      Ordinary mixed-control quota/invalid packets are unit coverage, not
      additional live quota cases. This increment is not access-time checking
      and does not close general C1 recovery or the explicitly deferred guard.
- [ ] Optional coverage: extend exhaustion/partial-progress combinations across
      frame, node, lock and code pools using production paths.
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
- [ ] Optional coverage: expand multi-request/remote schedules and protocol
      oracles. Sampled stack margins do not establish arbitrary IRQ/NMI depth
      safety.
- [x] Extend the existing mode-8 complex driver with two independent A queues
      feeding one B combiner. Keep both original logical task/outer-owner
      identities, published entry and exact per-root prefix/suffix state; require
      both remote children to execute JIT on the same B owner and all callers
      to return with clean context. Reuse the remote protocol unit/driver, not
      another routine case; preserve the original complex mode-8 phase. This
      tests multi-request scope isolation, not access-time checks or flags.
      Two focused units and three affected complex spin JIT cases pass on the
      [recorded freeze](VALIDATION.md#shared-b-combiner), preserving both mode-8
      phases. No production ownership change or new routine entry is needed;
      arbitrary remote schedules and C1/C2 remain open.
- [x] Extend that existing driver with mixed completion at the shared B:
      first child hits the supported CALL quota/native exit, B retains its
      owner while the original waiter runs, and the next logical root then
      executes JIT on that same B combiner. Preserve pure-JIT phases, published
      identity, exact per-root stores and owner ACKs; reuse existing units and
      case names. Do not use an ordinary learning miss to invalidate the shared
      entry or add a new flags/access-time exit.
      Two focused units and four complex spin JIT cases pass on the
      [corrected freeze](VALIDATION.md#shared-b-mixed-completion). The initial
      test incorrectly equated borrowed-lock depth with waiter preemption pins;
      preserve that failure separately and enforce the existing single origin
      pin plus final-ACK contract. No production protocol change is needed.
- [x] Upgrade the same mixed phase to observe the first waiter's normal TID
      detachment before the same B combiner starts the next root. Hold only a
      PID identity and the real frame/source lease at ACK-drained pop, never
      delay an owed ACK or add a task ref. Require unchanged software packet,
      CPU/preempt/IRQ, exact effects and the second JIT; retain the distinct
      no-lock root-finish gate. Three existing units and two complex live cases
      pass on the [recorded freeze](VALIDATION.md#shared-b-waiter-exit).
      This is SELFTEST scheduling, not a new production exit barrier, task-RCU
      reclamation guarantee or closure of general C1/C2 lifecycle work.

### C2. One Protocol Per Physical Lock

Implemented: spin L/S separation, acquisition tickets and origin references;
native mutex ownership with a private scheduling gate; active-task routing
through rename and native unlock; owner-side ACK and bounded remote-chain
publication. Native signal/trylock participants use Linux exclusion.

Remaining:

- [ ] Optional coverage: broaden non-target, oversubscribed, cancellation and
      remote/deferred follower combinations beyond maintained main paths.
- [x] Extend ordinary mode 4 with two independent A combiners sharing one
      native B: A0 retains physical A0/B across an ordinary CALL miss, while
      A1's executor and a non-target peer appear together in B's Linux wait
      list. Require A1's actual JIT, the original A0 waiter and two owner ACKs,
      native peer ownership and exact complete records. Preserve the existing
      two-CPU phase and separate independent-B retirement/signal contracts;
      this is not a spin-style remote B combiner. Two existing protocol units
      and three complex mutex JIT cases pass on the
      [corrected freeze](VALIDATION.md#shared-native-mutex-b). The first candidate
      wrongly expected only two generated artifacts; keep the extra hot-B image
      and select A entries by their actual source CALL returns. No production
      owner/queue change, guest patch, new routine entry or deferred feature.
- [x] Upgrade the existing mode 4 gate from seven separate CPUs to seven roles
      on two CPUs. Hold B until its real Linux wait list contains A's physical
      executor on B's holder CPU; require published code, returned JIT body,
      nested JIT completion and all original tasks returning with clean context.
      Ordinary/OOO variants and the shared mode 5 driver pass with mutex_jit=1.
      No new routine case, production owner/queue change or original-waiter
      native exit is introduced. This bounded scheduling observation does not
      prove arbitrary oversubscription/fairness or live node-pool exhaustion;
      [usage 6.12](JIT_EXECUTION.md#612-同-cpu-的嵌套-mutex-jit) distinguishes
      it from PENDING continuation and independent-queue context refusal.
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
- [ ] Optional generalization: define a provider reader/drain and nonlocal-exit
      lifetime protocol before claiming generic hot unload; no guest edits are
      authorized.
      Lock allocation/free identity also needs separate subsystem integration.
- Ongoing constraint: preserve strict node reservation, physical-owner/origin-ticket
  separation, release-published ACK and no accesses after waking the waiter.
- [x] Complete the spin node publication increment: replace plain completion
      and lone/batch handoff stores with release publication. In the existing
      production combiner fixture, check final register packets and immediate
      slot reuse, with assertion-detected plain-store/packet-overwrite mutants.
      Keep queue-head capacity accounting distinct from ordinary batch wakes.
      Validate affected complex spin JIT paths without new routine cases;
      this is not an arbitrary memory-ordering or task-lifetime proof.
      Nine complex cases pass; initial contract/fixture failures and corrected
      evidence remain separate in [spin publication](VALIDATION.md#spin-waiter-publication).
- Scope boundary: IRQ/BH, RT/PI/WW, arbitrary signal schedules and new lock APIs
  stay outside delegation until separately designed and tested.

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

Implemented: admission of the actual possible JIT scope; origin-based GS
lowering, unsupported FS/context and backend checks; reachable text/CFG handling; IR memory-effect/address analysis;
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
      condition-code restoration. Record the future packet contract in the ABI,
      not a new daily case. This is a prerequisite audit, not a runtime guard,
      kernel JIT result or permission to reopen C4.
- [ ] Optional generalization: broader context equivalence, hidden/unresolved
      calls and native suffix owner-sensitive operations need separate analysis
      before support can be claimed. Logical current is not a scheduling, IRQ,
      RCU or hardware GS switch; existing refusal policy is unchanged.

#### Deferred Access-Time Guard

**Deferred by explicit user decision on 2026-09-13.** The three items below,
including local CF/PF/AF/ZF/SF/OF preservation on pass and native-resume paths,
remain unimplemented. Keep these future requirements and the known safety gap;
do not implement them or repeatedly request authorization unless the user
explicitly reopens this feature. Existing entry checks and supported CALL/control
continuations are unchanged and do not provide this pre-instruction exit.

- [ ] Define enforceable dynamic/module/context object ranges and lifetimes
      before adding runtime checks. Core/module arena coverage is implemented, but
      kallsyms and entry alias separation are insufficient for the wider policy.
      Retain [the future implementation order](DESIGN.md#721-dynamic-address-gap).
- [ ] Validate each actual address once at its use, or reject before progress
      when the instruction/access cannot be supported. Establish a checked
      pre-instruction native packet, no replay, and physical-owner ACKs first.
- [ ] Cover dynamic pointer/RET replacement and implicit/RMW accesses in the
      existing negative/continuation gates; preserve complex actual-JIT modes.
      Source RBP/RSP are not private memory and entry GPRs are not stable C
      arguments. Sequential facts and mutex checkpoints do not prove freshness.

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
      - [x] Deliver version-pinned Python runtime dependencies and an isolated
        guest install procedure. Include the recipe in frozen source evidence;
        do not rely on globally installed packages or alter the guest kernel.
        Validate the clean environment with the existing unit/admission/core
        gates, using the same interpreter through daemon PATH inheritance.
        [Acceptance](VALIDATION.md#isolated-python-runtime): four runtime packages
        in a fresh CPython 3.10 venv, 40 existing units, 25 admission cases and
        core 5/5 with 484 returned bodies on 211 frozen inputs. No new test entry,
        rare-case expansion or JIT implementation change. The manual owns the
        install/PATH procedure; the recipe is included in captured sources.
        Package versions do not prove byte-identical builds or loaded JIT identity;
        full system/kernel reproduction remains open. Global distro pyparsing/
        pyelftools omit file lists, so only their metadata was compared; all four
        venv distributions' 411 recorded .py/.so files match before/after testing.
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
- [ ] Optional coverage: broaden production-code fixtures, randomized schedules
      and exactly-once/linearizability oracles beyond affected main-path tests.
      Selected tests still cannot accept missing dependencies as SKIP.
- [x] Improve deterministic nested promotion without weakening execution gates.
      Forced promotion is selftest-only, not a performance baseline.
      The current bounded implementation removes unrelated-lock discovery order
      from the decision, without promising deterministic OS scheduling:
      1. [x] Reproduce fast-first/slow-first decision differences using the
         existing production sampler fixture and identical per-lock timestamps.
      2. [x] Give each new lock the existing 2.5-billion-cycle window; remove
         cross-lock shrinking, preserve warmup, 10000 samples, strict deadline,
         sticky decisions, table bounds and ordinary JIT admission.
         Also sample TSC under the table lock for state updates: two real
         producer calls reproduce stale pre-lock time underflow and false
         IGNORE when update order differs. Keep the warmup fast check outside;
         this is not a proof of cross-CPU TSC synchronization.
      3. [x] Validate the same fixture, mutation checks and affected complex
         naturally promoted spin/mutex cases. Keep forced promotion confined
         to existing SELFTEST workloads; update policy, usage and evidence.
         The final fixture passes 211150 checks and four detected mutants;
         core plus parallel-drain-0 passes 6/6 on that same 206-input freeze.
         Keep the two reproduced defects and intermediate window-only pass
         separate in [VALIDATION](VALIDATION.md#hotlock-promotion-ordering).
      This closes cross-lock threshold coupling and pre-lock timestamp order,
      not deterministic scheduling, TSC synchronization, sticky-state resampling
      or performance/cost-based promotion. Those broader P2 questions remain.
- [ ] After affected main-path acceptance, add typed bounded services with
      explicit argument, clobber, context, sleeping, overflow and side-effect contracts.
      General variadic printk remains excluded.
      The supported-contract acceptance above permits the following scalar
      increment without reopening access-time checks or broad context claims:
      1. [x] Inspect the running baseline's exported `int_sqrt(unsigned long)`:
         x86-64 scalar input/output, at most 32 shift/subtract iterations, no
         pointer argument, allocation, sleeping or task/per-CPU dependency.
      2. [x] Add stable service ID 3 and a typed RDI-to-RAX adapter. Preserve all
         other saved GPRs, the pending CALL word, existing flags policy and the
         two-word wrapper ABI; use the native kernel implementation.
      3. [x] Extend existing mode 2/5 after their clock calls with high-bit
         integer inputs and consumed-result checks. Retain the full complex
         state oracle and mode 5's 17th-clock native suffix. Normal requests
         have two returning services; quota requests reach the scalar operation
         only on the original waiter's native suffix.
      4. [x] Run affected codegen/production-consumer/protocol units and complex
         service JIT cases; retain artifacts, exact per-service return counts,
         owner ACKs and drains. Update the ABI and execution-flow documents.
         This does not authorize pointer/variadic or side-effecting services.
         Four existing units and mode 2/5/8 pass on the same 206-input freeze;
         444 returned bodies, unchanged clock-quota behavior and full scalar
         results are recorded in [VALIDATION](VALIDATION.md#typed-scalar-service).
         This bounded service increment does not close broader P1 or reuse the
         prior full-matrix result as acceptance of the new implementation.
- The 2026-09-16 GS policy supersedes the prior parking investigation: published
  delegation waiters remain preemption-disabled and PAUSE-poll until result or
  native handoff. Sleeping/parking these waiters is outside the requested design.
  Earlier oversubscription measurements remain historical evidence in
  [VALIDATION](VALIDATION.md#mutex-oversubscription-assessment); they do not
  validate this contract. Native mutex acquisition and owner ACK service keep
  their existing protocol. See [pinned busy polling](DESIGN.md#pinned-busy-polling).

## P2: Performance And Broader Scope

### Instrumented Measurement Foundation

The existing benchmark's `Total Time` includes thread creation/join and
per-ioctl printing and uses a millisecond wall clock. Establish a usable
measurement boundary before drawing performance conclusions:

1. [x] Add opt-in structured measurements to the existing ioctl driver: a
   monotonic worker envelope after the start barrier and before return,
   nearest-rank ioctl p50/p99, summed worker CPU time and exact completed counts.
   Bound sample storage, reject malformed/overflowing input and make partial or
   timing-error runs nonpassing; preserve the workload/role and ioctl ABI.
2. [x] Exercise the production driver with real pthreads, deterministic clocks
   and an ioctl double, plus a real-clock run. Cover setup, ioctl and timer
   failures separately. This is measurement validation, not kernel JIT evidence.
3. [x] Retain measured payload logs in existing complex spin/mutex drivers,
   run affected units and complex JIT gates, and document commands and limits.
   Keep promotion/translation preparation outside the measured invocation.
   The final 208-input freeze passes 30 production-driver scenarios, 47
   evidence-controller tests and 5/5 existing core JIT cases. Four measured
   payloads have complete records and 451 new returned bodies with saved
   images in their before/after snapshots; all phases total 481 bodies.
   [VALIDATION](VALIDATION.md#instrumented-benchmark-measurements) records the
   guest-only archive, source identity and separate historical runs.

These are instrumented ioctl measurements, not pure CS/lock latency: generated
body witnesses, logging, oracles, scheduling and measurement overhead remain.
Worker CPU time excludes the daemon and external peers. `mutex_jit=0` uses the
original mutex path; it is a debug/native control, not a native-delegation
comparison group.
This foundation does not close the comparison and amortization work below.

### Comparator Feasibility And Matched Experiments

All comparison groups below use x86_64; they differ in execution strategy, not
machine architecture.

1. [x] Assess actual TCLock/native/JIT paths before selecting a third comparison
   group for native delegation.
   The unchanged upstream mutex object cannot compile against this guest's
   task layout; a normal external control object compiles. Preserve the failed
   observer and compiler evidence in [VALIDATION](VALIDATION.md#tclock-comparator-feasibility).
   The kernel has a CPU PMU node, but `perf` is not on the guest PATH; hardware
   counting is unverified, not proven unsupported. No kernel or project runtime
   change, new JIT run, native-comparator implementation or daily case is added.
2. [x] Implement matched native-with-existing-hooks/JIT trials using the same
   workload text, parameters/roles, state preparation and affinity. Preserve
   `mutex_jit=1` and all JIT gates; native selection uses a nonmatching target,
   not a second lock protocol. Record preparation separately, confirm published
   JIT entries, isolate measured-stage bodies, retain failed pairs and rebuild
   whole drained sessions when needed. Reuse existing workload/oracle logic.
   The initial ordinary mode 2/5 scope passes 16/16 independent sessions,
   eight pairs and 1,044 measured-stage returned bodies on 210 inputs;
   native comparison groups have no JIT. Two existing unit entries cover the
   driver and observer. Commands and interpretation live in the
   [paired flow](JIT_EXECUTION.md#34-原生锁与-jit-配对实验), results in
   [VALIDATION](VALIDATION.md#paired-native-jit-experiments). This does not
   establish a nested/SELFTEST or unmodified production-subsystem comparator.
3. [x] Add balanced repeat ordering and explicit thread/workload sweeps with
   paired metadata, not averages across unrelated modes. Mode 2/5 with 4/8
   threads and two opposite-order pairs per point are verified. No fixed live
   case or daily suite is added; failed/incomplete pairs remain fail-stop.
4. [x] Investigate the initial mode-5 anomaly before optimization: actual module
   ELF and serial records show routine queue/JIT traces at ALERT under console
   level 4. Move only these traces to INFO, retaining logs, errors and body
   gates. The existing mutex outer unit detects severity/disabled-log mutants;
   four mode-5 pairs and both mode-4 phases pass on the new 210-input freeze.
   At workload 100000, eight-thread times fall from about 2.1 s to 57-65 ms;
   four-thread participation rises from 2/128 to 94/128. This supports serial
   logging as a major contributor, not complete cost attribution or speedup.
   Source/console controls and scoped evidence are in
   [VALIDATION](VALIDATION.md#mutex-routine-log-severity).
5. [x] Record actual translator-child wall/CPU/RSS separately from preparation
   and payload envelopes, with an opt-in daemon flag and unchanged default.
   Join records to published entries, reject malformed/failed accounting,
   retain console settings across phases and comparison groups, and preserve
   historical pairs without inventing telemetry. Three existing unit programs and 32 sessions /
   16 pairs pass: modes 2/5, workload 10000/100000, eight threads, four balanced
   repeats per point. All 3,250 measured bodies have matching images and two
   service returns. The 3.27-3.40 s translator child is distinct from 8.77-9.68 s
   JIT preparation; no pure-compiler or whole-plan acceptance is inferred.
   [VALIDATION](VALIDATION.md#translation-resource-accounting) records the
   unchanged runtime/ABI scope and per-group sample sizing based on log capacity.
6. [x] Profile actual leased translation before optimizing symbol/text inspection,
   CFG/admission, emission and assembly. Context-name matching makes 4.32 million
   glob calls per image. Compile the unchanged rules into one regex union,
   without caching addresses or weakening checks. Five existing units, 25 audit
   cases, mode 2/5 profile/JIT gates, mode 4/8 and 12 refusals pass. Real names,
   intervals and generated bytes agree; plain translation falls from about
   3.3 s to 1.6 s. Keep raw profiler overhead separate from unprofiled timings;
   [VALIDATION](VALIDATION.md#context-symbol-matching) records both source freezes
   and the initial archive-observer error, not a failed JIT or a whole-plan PASS.
7. [ ] Separately measure kernel queueing, steady payload, hostcall/native and
   observation costs; broaden inputs, affinities/sockets and repetitions beyond
   the finite sweep above. Obtain verified counter tooling before reporting
   hardware/memory/cache transfers. Keep console/JIT share and failures, establish
   amortization, and use explicit experiments rather than new routine smokes.
   - [x] Add default-off, load-time-only `jit_timing` for inclusive dispatch,
     actual wrapper, typed service and lock-control C intervals. Report after
     drain; clock/overflow failures invalidate metrics without changing work.
     The initial paired entry validated loaded selection, four exact rows and
     ordinary mode 2/5's 1/3/2/1 call counts per body. All 40 existing units,
     external `W=1` build, 16 off/on sessions and five default-off core cases
     pass on one 210-input freeze, with 2,083 returned bodies. The old scalar
     adapter's registry-fixture compile regression is reproduced and repaired;
     service edits now explicitly select that independent unit. See
     [boundary evidence](VALIDATION.md#jit-boundary-timing).
   - [x] Extend optional timing to spin/mutex physical-owner native waits.
     Capture backend/timestamp locally, preserve every return and final ACK,
     and report six phases. Route direct/secondary test loads through one
     helper without changing their arguments or timeouts. On the new freeze,
     40 existing units, external W=1 build, eight paired sessions, five default-off
     core and five enabled complex cases pass. Six owner waits match native
     completion/identity and nine unlocks; first compile failure and stopped
     predecessor remain separate [evidence](VALIDATION.md#native-owner-wait-timing).
   - [x] Measure private spin/mutex queue residence, now eight timing phases.
     Record before tail publication and consume before node wake/reuse; stop
     at native L acquisition or the first executed body's pre-dispatch point.
     A refused no-body attempt retains its timestamp. Nine affected existing
     units, external W=1 build, eight paired sessions, default-off core 5/5 and
     enabled nested mode 4/8 pass on one 210-input freeze. Queue samples match
     drained slowpath totals; source, first fixture type failure and 1,334
     returned bodies are retained in [evidence](VALIDATION.md#private-queue-timing).
     This adds one field per node, not a frame/args change or a new test entry.
     Unpublished/fastpath acquisitions and direct nested mutex B waits are
     outside the queue interval; rare resource/schedule combinations are not
     added to this measurement increment.
   - [ ] Measure complete acquisition, native execution and observation costs with
     independently justified boundaries. Current elapsed totals include
     preparation, nested overlap and scheduling, not pure instruction/CPU cost.
     Owner wait starts after waiter publication; the wider handoff below includes
     that early prefix but also preparation/ACK. Private queue totals exclude pre-node preparation and native-only
     acquisition paths. Broader inputs, affinities, hardware tooling and
     amortization above remain performance work, not rare-case correctness gates.
     - [x] Add an opt-in native-handoff envelope around validated borrowing,
       remote/local publication and owner waiting, separately from the existing
       owner-wait interval. Start before remote publication can release an
       ancestor; finish after wait returns, using only executor-local values.
       Preserve owners, ACK order, frames and two-word args. Check disabled and
       enabled behavior in existing units and representative nested/native JIT
       cases; no new test entry or retry of the two-CPU missing-JIT experiment.
       Inclusive handoff is not waiter CPU time, post-unlock work or complete
       original lock acquisition; nested envelopes can overlap.
       [Acceptance](VALIDATION.md#native-handoff-timing): six existing units,
       W=1 external build, two off/nested cases, eight balanced paired sessions
       and three on/native cases pass on 211 inputs (nine changed files).
       Four per-owner handoffs match completion/inner-wait counts; 1,252 returned
       bodies remain joined to saved images. Preserve the initial repeats=1
       CLI rejection; it started no payload, and prior passing phases were not
       repeated. Broader cost attribution/amortization remains open.
8. [ ] Resolve a faithful native-delegation comparison separately. The checked
   upstream kernel requires task/lifecycle/lock changes beyond existing hooks;
   module-only adaptation is not yet designed or accepted. Do not boot/build
   another kernel or invent a raw-native production mode under the current
   default. The [comparator contract](DESIGN.md#13-performance-comparator-contract)
   preserves this native-delegation comparison gap; completing the native-lock
   and JIT groups does not close P2.

- [ ] Compare native locks, native delegation and JIT on equivalent workloads;
      separate translation, steady-state, queueing, hostcall and fallback cost.
      Measure throughput, p50/p99, CPU time, memory and cache transfers.
- [ ] Vary contention, CS size, input/state, threads and sockets with repeated
      trials. Establish amortization before claiming a JIT speedup.
- [ ] Evaluate contention/cost-based promotion, demotion, fairness and batching,
      then code-pool sizing and optional NUMA policies.
- [ ] Broaden opt-in spin NUMA tests before any default change; mutex currently
      has no NUMA-local delegation policy.
