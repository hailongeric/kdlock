# kdlock implementation plan and decisions

**Status:** active plan for the independent rebuild

**Current implementation:** private P2 source-flow planner/decoder and owner-retained C mutex-release protocol; static review only for the extensions. No physical mutex backend, queue/arbitration, JIT adapter, source-cursor advancement, build, JIT execution, benchmark, install or reboot is claimed

Apply the [F/S/P/E authority rule](00_overview.md#authority-and-statement-origins). This plan implements the target semantic model; historical mechanisms are optional reuse evidence. Operational repository rules still govern any later authorized work.

## 1 Fixed directions and semantic gates (F/S)

These requirements govern either refactoring or clean reimplementation; they do not freeze current mechanisms:

- All execution/delegation helpers are part of kdlock's lock implementation, as in TCLock. There is no independent execution runtime or worker architecture.
- The goal is general replacement for native-legal source patterns on the declared target, with valid local/native routes and the explicit ordinary-mutex outer-unlock policy/lifetime limits below. No mmap/munmap adaptation, application-root dispatch key or function-name exception is selected.
- Each original W has exactly one canonical S_W/packet/current cursor/phase. Nested nodes and outer control records reference it; state cardinality and shared pointer identity are fixed.
- Users point directly to the one thread-owned core, with no reserved duplicate W packets, source continuations or packet-sized unions; two storage levels do not limit nesting to two locks.
- Publishing delegation eligibility is optional. The origin can win local execution or become combiner through mutually exclusive selection.
- Any reached lock and any reached unlock ends the current JIT fragment before that operation.
- Lock code handles the operation and serial recursive delegation, then chooses a valid current-state continuation.
- The boundary recognizes source operations through exact active-origin/operation context, not kdlock's own queue/metadata locks. Internal locks do not enter W's logical grant ledger.
- Every handled source acquisition, unlock or mode operation has a generic exact-phase route under its selected continuation/lifetime contract. A deferred marker is not physical release or source-return evidence. Native suffix is fallback, not proof of whole-root JIT completion.
- Separate nested entries/images use the original UB-derived backend and original kdlock GS lowering.

- Ordinary trusted source is intended to translate; recognized special instructions cut only their affected paths before execution, retaining bypassed alternatives/safe joins and exact reached-only native handback. This policy is not proof of universal instruction/kernel equivalence.
- AS01 explicitly assumes general flags/SIMD correct with no separate general handling in this iteration. PUSHFQ/POPFQ alone require the specified intermediate-GPR local lowering; no general subsystem, shadow state or blanket gate is selected.
- Miss handback preserves the unfinished current continuation without replay.
- Learning is cumulative, source-versioned and independent of current execution.
- Linux 7.0 x86_64 non-PREEMPT_RT and exact lock/API/context/lifetime duties remain the target, with the explicitly selected ordinary-mutex outer-unlock deferral. Extra waiting is accepted for that route; generic native release-timing/progress parity is not claimed. No other family receives this exception.
- Reader concurrency, modes, API results and actual context obligations remain correct under the explicitly chosen placement. Origin-local is a conservative proposed initial lane; remote-reader execution is neither permanently banned nor authorized.

Minimal bounded structured recursion, call-local control and lock-local ordering are starting P, not a claim that a complete current S_W exists. A fresh core/node/backend/adapter is allowed. Extra records/refcounts need a concrete reason. The choices below require review; proposed defaults are not user acceptance or implementation authorization.

## 2 Mechanism decisions and status

The user approved C12 source-rebuilt integration with fresh private layouts and
C01 ordinary mutex lock/unlock in sleepable task context as the first complete
lane. Other families follow later. No old binary lock/object-layout compatibility
is promised. The user subsequently selected C03 owner-retained out-of-order
outer-mutex unlock deferral, superseding the transferable-grant recommendation.
C11 queue/arbitration and remaining C02-C11/C01 details stay open; no lane is
validated. The lock-object lifetime choice described in section 2.2 is pending.

| ID | Decision | Current selection or proposed starting point | Evidence needed before enabling |
| --- | --- | --- | --- |
| C01 | Initial lanes, policy and delivery order | Selected: independent source rebuild; ordinary mutex lock/unlock in sleepable task context first, other families later. Hotness/admission, pinning/parking and queue topology remain open | Declare exact ordinary APIs/context, the selected deferral/lifetime contract, eligibility/progress limits and evidence scope; no signal/try/I/O, reader or IRQ/BH lane is implied |
| C02 | Core/users, control placement and lookup | One thread-owned core/packet with direct users is fixed; fresh layouts are allowed. Audit node-owned control versus bounded call-local storage; prefer local ownership | T48/T49 lifetime/layout, migration, own/borrowed lookup and reset; any shared index needs necessity, scaling, completeness, publication/identity/lifetime proof |
| C03 | Grant identity and release authority | Selected: TCLock-style deferred outer-mutex unlock with responsible physical outer-combiner context retained; exact referenced A1/A2 identities. The transferable-grant recommendation is superseded | Distinct source request/return, marker, unwind, owner handling, actual normal physical release and last use; owner authority and object lifetime. Stable objects versus holding post-unlock source continuation remains pending |
| C04 | Target entry/exit/materialization ABI and local flags-stack lowering | Select/version the original-backend adapter under C12; keep optional compatibility explicit. AS01 requires no extra general flags/SIMD handling; choose mapped-temporary PUSHFQ/POPFQ simulation | GPR/virtual-stack/cursor/results/reentry proofs, one source push/pop, balanced temporary physical stack and covered local POPFQ effects and the open shared-packet-base/wrapper-backed mapping comparison T56; AS01 is an assumption, not general equivalence evidence |
| C05 | Recursive control and stack/resource bounds | Start with bounded structured calls/call-local outer control; choose extra stable storage or explicit stack only for a proved escape/bound | A/B/C chains, stack and resource bounds, scheduling/atomic legality and actual last users; no mandatory current arrays or per-CPU pools |
| C06 | Code/return binding across fragments | Proposed immutable per-episode binding; choose newer-fragment admission or quiesced/rebound updates only with valid current-state maps | A/B updates during suspension, old return/fixup users, exact reentry and the selected C09 reclamation rule |
| C07 | Nested batching and progress | Responsible outer-mutex combiner continues its normal batch after deferred handling. The proposed restriction on unrelated inner B bodies remains separate; broader inner batching is unselected | Wait-for graph under selected deferral, affinities, scheduling and resources; extra waiting does not prove native progress parity. Early reacquisition/availability handshakes remain unresolved scope issues |
| C08 | Discovery, capacities and cumulative learning | Five CALL edges remain the user-approved current default, not immutable architecture. Choose target budgets, ledger/saturation/late-report policy and coverage encoding; 32 rows is E | Exact acknowledged coverage, X/Y races, bounded current completion, selected capacity/backoff/reset and valid old-version knowledge |
| C09 | Source lifetime, code publication and reclamation | Choose immutable replacement/last-user retention or proved quiesced updates, source mutation/admission, build/staging isolation and compiler/daemon/restart organization | No live code corruption or freed source/return use, coherent commit, truthful ACKs and drain; no required lease counters, upload fd or session-only retention |
| C10 | Reader placement and API/context support scope | Keep initial placement/API proposals and explicit signalable/downgrade/IRQ/BH/NMI/debug extension choices; AS01 removes separate general flags/SIMD handling from this iteration. PREEMPT_RT stays outside the fixed target | Native concurrency/mode/API/context/fault duties and chosen placement proof; test-specific retained-writer downgrade is E only, not a boundary exception or native-equivalence proof |
| C11 | Family arbitration and W-state transfer | Queue/arbitration remains open. Selected deferred-owner handling does not select the former transferable proposal's guard/queue or transfer physical release authority with S_W | One executor, local/proxy/election exclusion, exact deferred request/return/notifier users, retained owner context, actual physical completion and final access; materialization follows C04 |
| C12 | Integration and compatibility contract | Selected: source-rebuilt integration with fresh private layouts; no old binary lock/object-layout compatibility promise. API result/context/lifetime/exclusion/order duties remain; selected outer release timing changes establish no generic native timing/progress parity | Enumerate rebuilt callers/modules, source/adapter contracts, version transitions and integration evidence; fresh layouts do not choose C02/C04 or validate integration |

Exclusion, exact source effects, owner authority and last-user obligations remain mandatory. The explicit mutex outer-unlock selection supersedes earlier immediate-release requirements only for that route; it is not generic native timing/progress parity. Other mechanism choices cannot extend that exception. Copied grant information still cannot create another physical mutation authority.

### Prioritized choices for confirmation

C12 and the initial C01 lane are approved as recorded above. The remaining
choices below require a concrete design where they affect implementation.

1. **Selected C03 with remaining C11 — deferred owner handling and arbitration.** Retain the responsible physical outer combiner, record exact out-of-order unlock phases, notify/unwind to it, continue its normal batch and record physical completion only after actual release. Queue/arbitration remains open. Resolve stable lock-object lifetime versus holding post-unlock source continuation; S_W ownership alone grants no physical release right.
2. **C04 with C06 — target adapter and reentry.** Old-ABI compatibility reduces transition work; a versioned adapter can fit the new core/fragments. Confirm valid inputs/materialization and code/return binding, including terminal versus explicitly resumable origin service.
3. **C10 — reader and API/context lanes.** Origin-local readers are the conservative first lane; another placement may broaden execution choices but needs full concurrency/context proof. Confirm initial lanes and extension scope; current exclusions are not permanent rewrite bans or new support.
4. **C08 with C09 — learning, update and lifetime policy.** Choose capacities/dispositions and immutable replacement versus quiesced updates, with coherent acknowledgement and last-user proof. Confirm compiler/staging/restart organization only as needed; five-edge discovery is the current approved default.
5. **C02/C05/C07 — control placement and progress.** Request-node control may simplify retention but extend reservations; call-local control avoids that where lifetime is structured. Confirm lookup, bounds and batching policy from actual capacity/progress evidence, justifying any shared index.

### 2.1 Per-family selection design

Before enabling a chosen backend's optional path, provide its state diagram and exact transaction/ordering, naming queues/links/fields only if that design uses them. Explain:

- how local/proxy claims exclude each other;
- how origin-as-combiner fits the same protocol;
- whether physical acquisition precedes or follows selection;
- cleanup for a losing temporary claim;
- cancellation at OFFERED, CLAIMED and ACQUIRED;
- when source advancement stops and the exported packet becomes ready for the selected executor;
- when a selected executor may advance source;
- how the node claim and S_W owner/transfer sequence cooperate, including return/cancellation and stale linked nodes;
- who imports a delayed grant ACK after validating the current operation phase;
- how active-origin context excludes internal queue/metadata locking from source interception;
- when published storage can be reclaimed.

The ordinary mutex's shared wait-lock protocol is a useful existing example, not proof that an independent "claim CAS" solves every family.

### 2.2 Selected ordinary-mutex outer-unlock deferral (C03)

The user selected TCLock-style out-of-order outer mutex unlock deferral. The responsible physical outer-combiner context/state remains retained; record the exact request and deferred marker, notify/unwind to that combiner, let it handle the marker and continue its normal batch, then physically release under its normal protocol. The earlier transferable-grant recommendation is superseded and unselected. C11 pending-queue topology, selection/election and serialization details remain open; the former proposal's one-guard/one-queue mechanism is not selected by this decision.

Every source lock/unlock still terminates its fragment before the operation. The original UB JIT, KD GS lowering and one canonical S_W remain fixed. Returning to the owner restores only its combining control and uses current S_W, never a pre-child packet or old JIT cursor. Passing S_W neither transfers physical ownership nor performs unlock.

The private [release protocol](../../../kernel/mutex_release.c) and [header](../../../kernel/mutex_release.h) retain physical-owner context and a list of exact per-acquisition controls. Their phase progression is:

```text
HELD -> REQUESTED(route=OWNER) --------------------> OWNER_HANDLED
HELD -> REQUESTED(route=DEFERRED_OUTER) -> DEFERRED
     -> UNWIND_READY -> OWNER_HANDLED
OWNER_HANDLED -> PHYSICALLY_RELEASED -> RETIRED
```

The source request atomically publishes OWNER versus DEFERRED_OUTER with REQUESTED. The caller resolves the exact active execution relationship; same-task identity alone does not make an outer unlock normal. Owner handling accepts OWNER+REQUESTED or DEFERRED_OUTER+UNWIND_READY only, and deferral rejects OWNER. No default source-resumption policy is selected.

Source-request, source-return and notifier users are tracked exactly and gate retirement. At owner initialization, the caller has already acquired physical exclusion and binds its exact ordinary backend unlock callback/object. The owner-only finish validates all obligations as OWNER_HANDLED, closes the batch/binding and takes/clears that saved callback/object under its internal guard, invokes the bound synchronous complete ordinary unlock once outside the guard, then records PHYSICALLY_RELEASED on the obligations. Owner operations check the current task. Correct binding and callback code/object lifetime through its return remain caller obligations; the protocol performs no later object dereference. Deferred acceptance, unwind readiness and owner handling are not actual release; physical release alone is not proof that every remaining control/notification user has finished.

This helper is a limited C protocol implementation with static review only; no callback has executed. Its internal owner guard does not select C11 family arbitration. It implements no concrete physical exclusion backend, acquisition/queue, JIT adapter, task-core anchor or source-cursor advancement. It chooses neither C04 mapping nor C02 placement and claims no complete ordinary-mutex lane, build or behavioral execution.

Extra waiting is explicitly accepted for this route. It supersedes immediate outer-release obligations only for the selected mutex policy; it establishes no generic native release-timing or progress parity and creates no spin/rwlock/rwsem/downgrade exception. Early reacquisition and source handshakes depending on outer-lock availability remain unresolved scope issues, without introducing a new source-admission whitelist.

Logical A1/A2 source grants are distinct from the physical batch acquisition. A held batch can have multiple exact per-acquisition controls; this does not require physical zero between logical grants. A same-source reacquisition route under deferred custody is not implemented and needs its own progress/authority evidence; no A2 batching/arbitration policy is chosen here.

The user has not yet chosen the lock-object lifetime contract: stable lock objects through physical release versus holding post-unlock source continuation until physical release. Neither is selected. A retained owner context does not itself pin its caller-owned lock container, and a deferred marker does not permit destruction/reinitialization. Keep exact acquisition identity and last-object-access/reuse proof; no separate allocation per acquisition is implied.

See [the protocol's selected phase contract and pinned public mutex source](01_lock_protocol.md#5-unlock-and-non-lifo-release). C11 arbitration and the pending lifetime choice need concrete contracts before source integration can rely on them.

## 3 Work packages

### P0 Establish an independent baseline and contracts

The independent main worktree, source-rebuilt C12 contract and initial ordinary-mutex C01 lane are selected; keep ongoing mmap1 work separate. Record the remaining affected mechanism choices before implementing their kernel or adapter contracts. Private compiler work that does not decide those choices may proceed. Inventory current code only as evidence/reuse candidates, not an architectural prerequisite. Either leave old paths untouched while building the new implementation or propose a separate incremental migration with explicit coexistence boundaries.

Produce a target semantic-information inventory: scope, writer/authority, observers, publication, last use, capacity/failure and validation. Bind evidence to kernel/config/toolchain/source and the chosen target ABI. Preserve declared API/context/lifetime duties and truthful evidence classification, including selected mutex deferral and its unproven timing/progress limits. The archive named in the repository README preserves code/design recoverability. Old receipt documents and test datasets need not be restored into main; neither the current implementation, object size nor policy is required. Leave existing ignored data and other worktrees untouched.

Use the generic constraint/decision table in [the evidence file](04_evidence_and_reconciliation.md#26-generic-constraints-and-decisions) to separate symptoms from unresolved causes. Code keys and dispatch describe family/API/mode, original S_W, operation phase, source cursor/epoch and ABI. Application names remain evidence labels, not implementation structure.

**Gate:** target boundary/selection diagrams, C01-C04, C11 and C12 are reviewable; distinguish semantic gates from optional migration stages and do not call a prose design implemented.

### P1 Define target core, grant and control identities

Separate request, successful grant, logical scope, execution relationship and code/source identity semantically. Choose the representation/indexing that keeps every live reference valid through non-LIFO release and reuse; current arrays, ledgers and nonmoving indexes are not required formats.

Map exactly one stable S_W and canonical packet to each original W. All nested nodes reference it, while outer records save only role/control and dependencies. Specify how current-sequence ownership exports resident values, how grant authorities publish mailbox results and how the owner validates/imports them. Reset, task exit and unsupported reentrancy cannot allocate a replacement packet while old references remain.

Make the physical split explicit: regs resides once in the thread-owned core; per-lock/outer-control users reference it directly and contain only necessary queue, authority, identity, role and completion information. Remove per-user unused full W packets and packet-sized owned/borrowed unions from the proposed layout, while preserving required native call-stack saves and every per-lock duty. Inspect actual member/union/pool layouts, not only `regs_ref` equality. Two storage levels permit A -> B -> C within the same proved bounds; this is a design goal, not an implemented or measured saving.

Map information into the target core/users and proposed bounded live calls. Consider reuse only after it satisfies the target. A new lock/handback alone does not justify a new frame/object; justify escaped last users, invalidated storage, stack bounds or measured needs before adding machinery. Keep equivalent exact ownership/lifetime checks for implemented mechanisms and describe accepted, rejected and unrun evidence accurately. This requires neither restoring old receipt documents/test datasets nor retaining their counter/record implementation.

Evaluate [proposed node-owned control](01_lock_protocol.md#proposed-node-owned-control-open) against its chosen reservation end. Keep a local fast path without unnecessary node/capture. Call-local control or a retained request are alternatives. If the selected backend has OSQ/delegation memberships, preserve all duties or prove an equivalent merged protocol; neither OSQ nor two queues/pools is mandatory. Pinning/waiting/admission/cache policies are open, with progress/lifetime evidence.

A selected owner-sensitive or reused path must remain correct under its actual backend/context constraints until replaced. The clean target may choose a new authority, queue, layout or admission policy under C03/C11/C12; current hotness thresholds, waiter pinning and byte layouts are not design gates.

**Gate:** target local/proxy semantics, A1/B/A2 identity, one-core layout and last-user validity. Behavior-neutral old-path steps are a possible migration strategy, not a condition of clean reimplementation.

### P2 Make every lock and unlock a JIT boundary

**Implemented subset:** [disassem/fragment.py](../../../disassem/fragment.py)
walks a finite, caller-classified source graph. It stops before typed source
lock/unlock/mode/special sites, retains safe alternatives and independently
reached joins, and distinguishes missing targets from unresolved alternatives.
Explicit ordinary matched direct CALL/RET records have distinct call-target and
return-summary relations. A local least fixed point finds modeled boundary-free
routes to RET; each reached call retains its continuation only if its callee has
such a route. This is structural return reachability, not a runtime-return or
semantic nonreturning-function proof. Indirect calls and changed return targets
remain outside this helper's input contract.

The private [decoder adapter](../../../disassem/source_decode.py) converts only
caller-supplied stable bytes and exact boundary metadata through the original
Miasm x86_64 decoder. It retains decoded bytes/site/length and represents direct
control flow without successor discovery. Decode failures and unmodeled
transfers remain separate maps: a missing planner edge to one of those sites
must not be attributed to ordinary coverage. Source identity/coherence/lifetime
and API recognition remain caller or future integration obligations.

There is no emitter, machine-state mapping, runtime CALL/RET effect handling or
handback. The private records select none of the remaining C02-C11 mechanisms.
Ten checks on the earlier intraprocedural planner do not validate these
extensions. They have static review only; decoder dependencies have not been
installed or imported. This does not complete P2 or T07/T08/T52/T53; all T01-T56
remain unrun.

Implement semantic API recognition and typed pre-operation exits in the original backend. Stop fragment emission across every admitted lock/unlock, including inner or ancestor release. Keep reached-only execution and direct-CALL lookahead as separate concepts.

Map boundary state to C04's chosen target ABI and C12 compatibility scope. Prove declared inputs and complete current-state export/reentry without treating old MINIMAL entry as arbitrary capture. Lock code performs the operation once and uses a validated next fragment or exact origin route.

Provide body-independent current-state admission after acquisition/release/chosen mode change. Known unsupported special instructions stop only the affected path; preserve independent safe alternatives/joins, safe callee returns and caller fallthrough. A reached special frontier hands the exact first-unexecuted instruction/current S_W to native W; an untaken one causes no handback. Keep ordinary misses and finite resource limits separate, with no whole-region semantic whitelist or general flags/SIMD gate under AS01.

**Gate:** source effects, acquisition/release counts, CALL words, stack and operation results are once-only for both success and failure; a known lock target cannot be compiled away as ordinary learned code.

### P3 Implement optional root arbitration

Implement the selected target arbitration for local winner, proxy winner and origin-as-combiner. Test it through the declared public integration APIs; current family algorithms are candidate mechanisms, not prerequisites. Publication must not force transfer.

Root-local means W executes; nested-local can mean C_A continues W under S_W. Serving X switches to S_X under exclusive execution and restores the prior active pointer/control. Logical origin does not change; reader placement follows the explicitly selected C10 lane.

Provide a valid local/native route when delegation is unavailable/ineligible before effects; hotness thresholds are a policy choice. No source-body execution worker is required. Compiler/learning organization is C09 and does not become an independent execution architecture.

**Gate:** race tests show one source-body executor, one grant and correct cleanup/lifetime in each outcome.

### P4 Add serial recursive combining

Use the same lock implementation recursively: C_A saves outer combining state, handles B locally, becomes B combiner, or publishes an optional B child. Carry current-state continuation/entry bridges and retained parent/grant duties.

Assert `N_A.state == N_B.state == &S_W` across W -> C_A -> C_B -> C_A/W. Returning C_A reads the current S_W rather than restoring pre-B source state. Exact active relationship/operation context identifies nesting even when W is itself combiner; `current != W` and pointer equality are not substitutes.

Children can cross multiple fragments; each lock operation returns to lock code. Parent wait paths handle required release/cancel/completion events. Same-task nested operations use local handling, not mailbox self-wait.

**Gate:** selected A/B/C routes, independent fragment bindings, current-state return and no lost event/self-wait. Preserve other routes' no-added-cycle duty and analyze selected outer-mutex waiting/availability limits separately. C01 chooses family order; no mandatory mutex-first/writer-first rollout is inferred from existing support.

### P5 Complete non-LIFO release and native continuation routing

Resolve every source unlock by exact acquisition and selected authority. For the chosen outer-mutex route, record source request/return, deferred marker, unwind readiness, owner handling, normal physical release and last use separately. Retain the responsible owner context through its actual duty; a marker is not physical completion. The prior transferable route is unselected.

Terminal handback propagates outward, revoking old JIT-resume rights while keeping physical release duties alive. Imported ancestors, object reuse and origin context guards must be actionable before enabling the relevant entry.

Retain S_W and grant/read-credit custody independently of a nonresponsible executor/frame. A responsible outer-mutex context stays retained through its deferred physical-release duty and exact users. Queue-node retirement does not free state or custody. The current owner validates delayed ACKs against the matching operation or retained grant transaction; completing old custody must never overwrite newer source state or discard a release duty.

**Gate:** observe the selected deferred phase sequence and responsible owner context through normal physical release, without assuming another task acquires A before B completes. Distinguish exact A1/A2 identities and last users. Resolve lock-object lifetime versus post-unlock continuation before claiming safe early source destruction/reacquisition; native suffix never revives old code or drops retained release duties.

### P6 Implement cumulative learning and coherent publication

Implement F/S cumulative knowledge, exact coverage acknowledgement, isolated coherent commit and valid source/code bindings. C08/C09 choose capacities, receipt encoding, private staging/parallel builds, immutable replacement or quiesced update and reclamation; current working code may be reused where it meets those choices.

Keep deliberate boundaries/capability dispositions separate from ordinary coverage. Define the selected saturation/backoff, old-version knowledge and compiler/restart/reset behavior. Test the selected update strategy across its whole declared scope; no live code/metadata user may see an incomplete or incompatible update.

**Gate:** X then snapshot then Y then publication preserves Y, candidate coverage is checked rather than assumed, and active/saved references remain valid during replacement.

### P7 Enable additional families and modes one at a time

Select additional reader/writer, signalable, mode, mixed-family and context/configuration lanes under C01/C10. Origin-local readers are the conservative proposed initial lane, not a fixed rewrite restriction. Remote reader placement, debug/lockdep configurations and IRQ-related extensions remain unselected/unvalidated until explicitly scoped and proved; the current support exclusions do not permanently decide the target.

The explicitly selected ordinary-mutex outer-unlock deferral is the limited accepted policy, not generic Linux release-timing/progress parity. Do not copy TCLock's other historical killable shortcut, disabled downgrade, forced caller changes or borrowed-stack/task metadata as faithful Linux 7.0 semantics. Do not infer that one-CAS mutex-to-spin success proves contended mixed support.

**Gate:** the support matrix records each successful route; unsupported ones take a valid pre-effect local route or admitted exact suffix.

### P8 Qualify the complete lock

The user selected overall functionality before behavioral testing. During this
implementation stage, continue source/static review and defer further behavioral
tests and suites until that functionality is complete. The ten private planner
checks recorded in the evidence file preceded this clarification; they do not
change the order or count as acceptance. Missing mechanism choices must be
resolved rather than filled in merely to reach testing.

Once overall functionality is complete, run repository-required static/unit checks, generated-code structural tests, memory-order/lifetime tests and real API workloads on the authorized test environment. Kernel/module execution follows the eventual checkout's AGENTS instructions; do not run builds or benchmarks on a host reserved for source work.

Only then compare cold learning, warmed/frozen execution and changed-target adaptation. Separate application completion, native/local body work, origin-as-combiner, per-fragment completion, exact handbacks and whole-root JIT returns. Retain actual exit reason/cursor and owner/operation phase before attributing a limit. Compare Linux Native and TCLock only with explicit release-policy/configuration and actual-path attribution. Selected mutex deferral must remain visible; it is not matched native release-timing/progress evidence. Real-world API tests use actual userspace system calls, native bodies and minimal lock routing/lifetime glue under the existing workload contract; fixtures remain mechanism evidence.

**Gate:** no correctness support claim is inferred from throughput, local fallback or an image merely being published.

## 4 Support matrix template

This is a target-lane matrix, not a current support claim. Required behavior is S; initial routes/scope are P. C12 separately defines source/binary/layout compatibility.

AS01 is a user-selected design assumption/scope, not a verified behavior row: general flags/SIMD need no separate handling now. The local PUSHFQ/POPFQ exception remains a concrete C04 lowering task; it introduces neither a general capture/shadow subsystem nor removal of selected special CPU-state frontiers.

| API/context lane | Required behavior (S) | Initial proposal (P) | Open choice / enabling evidence |
| --- | --- | --- | --- |
| Plain spinlock | Native atomicity/context and exact release | Simple task-context lane first | Execution/guard/progress proof; pinning or pools only if selected |
| rwlock/rwsem writers | Write exclusion, API result and interaction with readers | Choose initial family in C01 | C03 authority/composite contract; no inherited writer-first order |
| rwlock/rwsem readers | Concurrent reader/mode/API/context semantics | Origin-local on W | C10 placement; C_A-local is still remote relative to W; no remote lane authorized yet |
| Mutex | Sleepable ordinary API lane with exact owner/release/lifetime phases; selected outer-unlock deferral accepts extra waiting | Owner-retained deferred outer unlock selected; physical backend and C11 queue/arbitration remain open | Distinct marker/unwind/handling/physical release, retained owner and exact users. Lock-object lifetime choice pending; no native timing/progress parity |
| Trylock | Exact success/failure; no grant on failure | Local route until another is selected | One result winner and cleanup under the chosen protocol |
| Killable/interruptible | W's intended signal/API result | Origin handling initially | Explicit cancellation/context contract, not C's substitute signals |
| Downgrade | Continuous write-to-read protection | Origin-local read suffix initially | C10 mode/placement with exact custody; no unlock/relock substitute |
| IRQ/BH variants | Correct physical CPU effects/restoration | Separate unselected extensions | Family/API-specific context and progress proofs |
| General IRQ/NMI | Actual Linux context/ownership/last-user behavior | Unselected/unvalidated initial scope | C10 must define/prove any added lane; AS01 supplies no IRQ/NMI support |
| Debug mutexes, debug allocation, lockdep | Correct behavior for any explicitly selected configuration | Not selected initially; unsupported in current code | C10 scope and integration/validation decision, with no implicit new support |
| PREEMPT_RT | Outside the fixed F target | Excluded | Not an open extension of this design |

Current source support facts remain E. A valid local route does not establish delegation support, and no blanket "mixed locks supported" label replaces per-lane evidence.

## 5 Acceptance tests and receipts

Each receipt records source commit and dirty state, kernel/config/toolchain, enabled feature flags, original S_W identity, actual executor/exclusive binding and any protocol incarnation/sequence used, source entry/fragment and generation, actual exit reason/cursor and operation phase, relevant grant/read-credit custody, expected observations, failure mode, artifacts and limitations. Classify application completion, local execution, per-fragment completion, native handback and whole-root JIT return independently. Missing attribution stays unproven. A helper/unit fixture is not live kernel evidence. The tests below remain unrun acceptance specifications; neither the earlier private graph-helper checks nor static review of compiler/C protocol code satisfies them. Interpret release results under the selected phase contract: deferred acceptance is not physical release or source-return evidence, and no mutex timing/progress parity is assumed.

### Selection and acquisition

- T01 Race OFFERED local selection against proxy selection repeatedly. Observe one executor, one result and one successful grant at most.
- T02 Origin wins, combines eligible other requests, then runs its own body once. Verify the proxy route closed first.
- T03 Another task wins proxy selection while the origin is in the lock wait code; origin does not run its body.
- T04 Cancel at private, offered, claimed and acquisition-result phases. Distinguish cancellation winner from successful acquisition.
- T05 Failed trylock/interrupted acquisition terminates the old fragment, produces no grant and follows the failure branch.
- T06 Attempt stale request/ACK after reuse and any chosen counter wrap; no obsolete observer dereferences freed storage. Test actual identity/order checks, not mandatory numeric fields.

### Boundaries and exact continuation

- T07 Every nested lock and every inner/ancestor unlock stops generated execution before the operation. Instrument actual lock-helper entry and backend side effects.
- T08 Bypass a branch containing a lock/unlock or supported terminal; the executed fragment continues correctly.
- T09 Indirect lock target recognition cannot enter the API as ordinary translated body code.
- T10 A non-idempotent prefix followed by a miss executes once; target evaluation and source CALL word occur once.
- T11 Test pending CALL, completed operation, pending JMP/RET and stack-changing service separately.
- T12 Verify the chosen C04 GPR/virtual-stack/cursor/operation capture/materialization contract across entries/exits; old two-word/offset/register tests apply only to retained compatibility. General flags/SIMD use AS01 with no blanket admission/capture test or equivalence claim; PUSHFQ/POPFQ have separate local tests T54.

### Recursive and non-LIFO behavior

- T13 Local B acquisition, C_A-as-B-combiner and C_B child each return correct current state.
- T14 A/B/C serial child chain retains each responsible outer context and handles exact deferred notification/unwind and normal-release outcomes without restoring old S_W snapshots.
- T15 unlock(A) inside B ends the fragment before its source request. Observe REQUESTED, DEFERRED, UNWIND_READY, OWNER_HANDLED and actual normal physical release separately. No marker is reported as RELEASED, and task T is not required to acquire A before B unlock.
- T16 Distinguish logical source acquisitions A1/A2 and their exact referenced controls from the held physical batch: multiple logical grants do not inherently require the gate to become free between them. Match every source-return/physical-completion event exactly and forbid stale A1 mutation or premature reuse of A2. The same-source reacquisition route while deferred custody remains is unimplemented and needs explicit progress/authority evidence; this specification selects no A2 batching/arbitration policy.
- T17 Under the explicitly chosen lock-object lifetime/post-unlock continuation contract, destroy/reinitialize A only after actual physical release and final object access while independent A1 bookkeeping may remain. A marker or OWNER_HANDLED is not destruction permission; no late dereference/release touches the new object. The lifetime choice is currently pending.
- T18 B acquired before delegated A then unlock(B) requested inside A; establish exact imported provenance and retained responsible B owner, then follow the selected deferred/normal release phases. Do not infer physical completion from the source request.
- T19 Native suffix from a descendant revokes old ancestor JIT-resume rights while responsible outer contexts and deferred physical-release duties remain retained. Later native unlock follows exact selected phases; no old source snapshot resumes.
- T20 Preserve the proposed unrelated inner B-body restriction: do not introduce a dependency cycle by scheduling extra inner bodies while W is suspended. Analyze selected responsible outer-mutex batch continuation separately; early reacquisition/availability-dependent handshakes remain unresolved and extra waiting is not native progress-parity evidence. Broader unrelated inner batching is not selected.

### Context, lifetime and ordering

- T21 Sleep/migrate a legal parent and race child/release events through the chosen wait/notification protocol. Prove no lost event or invalid storage; include per-CPU reservation cases only if used.
- T22 Spin A/B non-LIFO release preserves required atomic guards on W and each physical authority.
- T23 Exercise allowed affinity/oversubscription and scheduling cycles; document exclusions rather than assume fairness.
- T24 Exhaust the frame/grant/mailbox/ticket/state/image capacities actually selected by the mechanism at their declared effect boundaries; a semantic field group does not require a separate pool, and nested nodes still reference one S_W.
- T25 Prove final dependent access, physical release duty and exact source-request/return/notifier last users precede retirement/reuse; deferred acceptance and source return alone permit neither. A retained pop-based migration lane obeys its real detach rule; a fresh target proves its selected equivalent mechanism.
- T26 Model OFFERED/GRANTED, child READY, source-unlock REQUESTED, DEFERRED, UNWIND_READY, OWNER_HANDLED, actual PHYSICALLY_RELEASED and final retirement/result data chains under LKMM; acceptance/handling cannot substitute for actual release.
- T27 Verify failed/cancelled read/write claims, concurrent readers, write exclusion and continuous downgrade under the selected C10 placement/API lane. Run origin-local as the proposed initial control; no unselected remote lane is implied.
- T28 Deliver signals to W and C independently; observe intended API result and one grant/cancellation winner.
- T29 Source close/mutation races build, commit, queued roots, children, native suffix and return/fixup users without stranding admitted work.

### Images and learning

- T30 Change A/B code versions while a child is suspended under the selected C06/C09 update/reclamation scheme. Keep code/return/source bindings valid, or wait for proved legal quiescence/rebinding without stranding the child; test whichever immutable or quiesced strategy is selected.
- T31 Report X, build snapshot, report Y, publish only actual coverage of X; Y remains pending.
- T32 Snapshot X but fail to translate it; do not acknowledge false coverage. Track a lock boundary as a settled boundary, not translated-through code.
- T33 Duplicate storms, bounded saturation and source-valid old-image observations obey the selected policy.
- T34 ENOSPC/backoff does not trigger impossible retry loops or reclaim live code.
- T35 Test selected compiler/daemon restart/reset, if any, against cumulative source-valid coverage and live bindings. Reconstruct/preserve knowledge or execute the explicitly chosen coordinated reset; no daemon or counter format is required.
- T36 Cold, warm and new-target phases report actual local/proxy/handback work separately; no performance claim from local-only execution.
- T37 Race the selected candidate-build/publication/staging interface: bytes/metadata never mix and stale commit/abort affects only its candidate. If fd staging is retained, include independent and dup/fork-shared descriptions; another interface needs equivalent isolation tests.

### One canonical state and general replacement

- T38 Across W -> C_A -> C_B -> C_A/W, compare canonical state/packet addresses and the chosen scoped identities at every node/entry/return. Observe `N_A.state == N_B.state == &S_W`, current resident-value export and one source advancement; never restore a pre-B packet or substitute S_C_A.
- T39 Have one combiner serve distinct origins W and V, including origin-as-combiner W serving X. Observe distinct S_W/S_V/S_X, correct active-pointer and outer-role restoration, and no register/cursor mixing. Cover root-local W and nested-local C_A without changing logical origin.
- T40 Race local/proxy claims, transfer/return, stale linked nodes, cancellation and delayed grant ACKs at the relevant protocol phases. Only the matching current owner imports outcomes; stale nodes cannot regain authority or overwrite newer S_W state. Exercise reuse and any chosen counter-wrap checks while inspected references remain valid; no per-hop counter is assumed.
- T41 Use unrelated source bodies and matching API patterns to establish exact-phase routing after admitted acquire/unlock/mode operations, including deferred non-LIFO and last-grant cases. Observe one source operation, marker versus physical-release phase, and a validated bridge under the chosen lifetime contract or explicit fallback. No marker alone advances source, and no body-specific dispatch or arbitrary unprotected remote suffix is implied.
- T42 Construct separate local-only, fragment-to-lock, capability-frontier, resource-boundary, native-suffix and whole-root-return cases. Check actual exit cursor/reason, owner/operation phase and the five completion categories; static frontier presence and application success cannot fill missing observations.
- T43 Exercise selected special CPU-state frontiers, including the recorded STD case, through reached and bypassed branches. Stop before the special instruction only on its path; preserve native context/ownership and prior effects. AS01 removes no deliberate frontier and requires no new general flags/SIMD subsystem or named string-helper model.
- T44 Reach the source/decode/CFG/image/control capacities selected for the target, with earlier effects. Record resource/limit/cursor and bounded forward completion without replay or impossible retry. Document chosen changes to defaults/bounds; current global constants are not frozen and application-specific exceptions remain excluded.
- T45 Retire only a nonresponsible child node/executor/frame while S_W and independent obligations remain. Retain each responsible outer-combiner context through its physical-release duty and exact request/return/notifier users. Observe custody, matching phase import and last-user drain before reset, incarnation reuse or task exit. Unsupported signal/IRQ/reentrant entry cannot allocate a second W packet or steal the active state.
- T46 Reach reader/downgrade boundaries while C_A executes W. Under the initial origin-local proposal, use an exact origin route or pre-effect restriction and never count C_A-local as W-local. If C10 later selects another placement, require its separate concurrency/mode/context/continuation receipts before enabling it.
- T47 Execute real source lock nesting whose helpers acquire internal queue/metadata locks. Observe one typed boundary/grant per source operation, no recursive interception of implementation bookkeeping, and correct active-origin lookup when physical current stays C while origins change.
- T48 Audit physical member/union layout, offsets, sizes and pool stride as depth grows from A through A/B/C to the admitted bound: W has one canonical regs backing in its thread core; every node/control points directly to it and reserves no unused full W packet, duplicate source continuation or packet-sized owned/borrowed union. Distinguish C_A's own origin core and required native register saves from W backing. Preserve per-lock owner authority, exact source/deferred/physical-release phases, one executor and exact continuation at every depth under the selected policy; infer no native release-timing parity. Record layout evidence without inferring measured memory savings; this acceptance specification has not run.
- T49 If node-owned control is selected, race premature slot reuse against nested A1 source request, deferral/unwind/owner handling, actual physical release, distinct A2, returns, cancellation, notification and handback; responsible owner and exact source-request/return/notifier last users finish before reuse. For a backend with OSQ/delegation, test both duties or its proved merged equivalent. Audit chosen storage/reservations/capacity through scheduling without ancestor/child cycles, optional fast-path nodes/capture and imported authority. Record offsets/alignment/stride and hot/cold accesses under the chosen integration contract; no mandatory topology, 64-byte layout or gain is implied.
- T50 Audit C12's integration/compatibility promise and C04's chosen ABI against actual rebuilt or binary consumers: declared API/context/lifetime effects including the explicit mutex deferral limit, object/module layout where promised, version transitions and complete valid-input/materialization/reentry; no generic native release-timing/progress parity. Neither source rebuild nor drop-in compatibility is silently assumed.
- T51 For selected C03 owner-retained outer-mutex deferral, race exact request/return/notifier users with atomic typed request-route publication, deferred publication, unwind readiness, route-checked owner handling, batch close/binding removal, invocation of the initially bound complete ordinary unlock outside the guard, physical completion and retirement. Observe responsible current-task checks, one actionable physical owner, distinct acquisition identities and no premature reuse. S_W movement neither transfers physical release authority nor completes release. The earlier transferable-grant proposal is unselected.
- T52 Use a conditional with a known special instruction and special-only suffix versus a safe alternative reaching a shared join. Inspect emission for no special/suffix through the frontier edge and retained safe/join code; run reached/bypassed cases with non-idempotent stores, grants and source stack effects. Only the reached special path hands exact first-unexecuted IP/current S_W to native W; no root/function rejection or replay. This specification has not run.
- T53 Place a special path and an ordinary safe return inside a callee. Preserve the safe RET and caller fallthrough; verify the terminated path invents no translated return, including the all-terminated-callee control. Check real source CALL/RET words and prior effects once across native handback; unknown ordinary targets and resource stops retain separate classifications. This specification has not run.
- T54 Test intermediate-GPR PUSHFQ/POPFQ lowering under the chosen mapper: force temporary/live-register conflicts and virtual R11-R15 spill/restore, verify one eight-byte source word/SP change per instruction and preserved values/cursor, and prove any physical-stack temporary sequence balanced. Include bypass/reached branch cases, following joins and selected special-boundary controls. State the locally covered POPFQ values/effects; add no second packet/general flags shadow and infer no arbitrary-bit or SIMD equivalence. This specification has not run.
- T55 For a selected target downgrade contract, require its mode-operation boundary and continuous native write-to-read API behavior independently of the experimental retained-writer proxy. A read-only logical label with physical writer/admission retained is not generic equivalence; neither returned-root counters nor an unobserved consumed branch establish it. This specification has not run.
- T56 Compare the C04 pinned-KD shared-packet-base and original-UB-style resident-R11/wrapper-backed mappings under the same original backend, matched source/admitted ABI-state semantics, workload, code generation and nesting/miss/handoff frequency. Account for remap/spill/reload work versus transfer/materialization, code size and memory/cache behavior; verify one canonical core and actual local/fragment/handback/root completion before any throughput claim. Working saves are not extra canonical states. This comparison has not run and validates neither AS01 nor general flags/SIMD equivalence.

## 6 Completion criteria

Each implemented lane can be enabled and claimed supported only when it has:

1. Concrete record/field mapping for the one S_W and its referring nodes, with sole packet mutation authority.
2. Exact selection and operation linearization points.
3. Validated entry/exit and first-unexecuted continuation recipes.
4. Lifetime, ordering, resource and progress arguments.
5. Generated-code and real-API receipts for that exact route.
6. Explicit unsupported cases and safe admission/fallback behavior.

This documentation set is a coherent basis for that process. It does not claim these gates have passed.
