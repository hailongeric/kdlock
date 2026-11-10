# kdlock redesign documentation set

**Status:** integrated design with private source implementations, not a runtime/support claim
**Target:** Linux 7.0, x86_64, non-PREEMPT_RT
**Revision:** 1.11, direct MCS state and task-owned auxiliary entry
**Scope:** a complete kdlock redesign for general lock replacement, independent of the ongoing mmap1 workstream

## Purpose and conclusion

Rebuild kdlock as a lock implementation with optional delegated execution. Like TCLock, acquisition, combiner election, waiting, recursive delegation and unlock handling are all parts of the lock implementation. The original UB-derived JIT remains the execution engine for admitted delegated source code. The word **runtime**, when used in earlier material, means helper functions inside this lock implementation. It does not identify a separate subsystem, service, worker pool or architectural component.

This set integrates `kdlock_nested_delegation_proposal.md` revision 1.2 and `kdlock_mixed_nesting_design_v0_6.md` revision 0.6. It resolves their conflicting language using the latest user direction:

> Every encountered lock operation and every encountered unlock operation ends the current JIT fragment. The lock implementation handles that operation, including recursive delegation when appropriate.

An inner lock or an ancestor unlock is not executed through the old generated fragment merely because the outer protected scope remains live. After the operation, the lock code may resume a separately admitted JIT fragment with current state, transfer that continuation through recursive combining, or return the exact unfinished continuation to the originating task.

Each original thread W has exactly **one canonical execution state S_W**. A's node, B's node and suspended execution relationships reference that same state: `N_A.state == N_B.state == &S_W`. They do not own separate copies of W's continuation or register packet. A physical combiner's own thread state is distinct from the active W state it borrows. This cardinality is fixed. C02 keeps active/nested source lookup on each MCS node's direct S_W pointer. A stable task-owned root/auxiliary header supplies the initial own core; no external registry or redundant active-S_W task field is used. Task-time provisioning and transfer implementation remain separate duties.

The physical target has two storage/reference levels: W's thread-owned core containing its one canonical regs packet, and lock/control users pointing directly to that core. Users must not reserve an unused full W packet, duplicate source continuation or packet-sized owned/borrowed union. This is a layout requirement, not a two-lock nesting limit: A -> B -> C still uses the same S_W within proved resource/stack bounds. Required per-lock authority/control and native call-stack register preservation remain. Private source implements this split, with no measured memory-saving claim.

The starting proposal is the target one-core/two-level model with bounded structured recursive lock calls, call-local outer combining control and lock-local selection/return ordering. It can use a fresh layout or deliberately reuse suitable current components; the initial mutex core now has a private source implementation, while complete kernel integration and support remain unproved. The field sketch describes semantic information, not required allocations. Nested acquisition adds no execution frame by itself; returning ownership to W adds no handback object. Extra stable records, notification storage, explicit stacks or refcounts need a demonstrated escape, stack-bound, lifetime or measured requirement. [The minimal mechanism table](01_lock_protocol.md#minimal-starting-mechanism-versus-optional-extensions) states those conditions without dropping ownership or last-user obligations.

**Selected C05 storage for the initial mutex lane:** use task-owned preallocated persistent request records for the unified ordinary local/proxy path. Simultaneously live records remain distinct through every exact physical-owner/release, grant, return, notification, image/binding and current-native-endpoint user. Finite caller-supplied capacity covers concurrent nested requests and all still-retained records, not only depth. The user guarantees an available record for every need in the supported workload; attachment/resources supply the actual count, with no configured deployment value or mathematically unbounded claim. Exhaustion is a documentation-only support limitation, with no handler, recovery/local fallback or new special assertion. A normal local winner retains the same persistent request/control duties. See [the selected storage contract](01_lock_protocol.md#selected-task-owned-persistent-request-storage).

Private source milestones now also include current-task setup composition
(`57599619`), caller-established source-epoch retention/validation (`a660342c`),
copied-exit fact classification (`c9b468ee`), exact artifact input records and
final-slot NULL retirement (`0c3ccb10`), and the code/source image-owner envelope
(`a23b82c1`). They have independent source review. They acquire no live provider
lease or executable allocation and automate no task lifecycle. Source commit
`5989fbbb` implements the C08 fact pool, independent producer/source retention
and exact publication/ACK bridge. The host coordinator (`af997cb6`) cumulatively
merges inputs before compilation and reconciles actual publication/ACK receipts.
Source checkpoint `40ae39ce` adds actual immutable-contract source snapshots,
complete native-source holds, cold task storage, retained stack-word operations
and kernel shutdown settlement. `236c287a` and `80095bfb` connect the fd channel,
control, execmem loader, GNU host build/session, managed task lifecycle and
fsynced archive-to-SETTLED shutdown. `c6becf81` supplies exact exported slot/base
identities. The exact-target installer and focused-check source exist at
`97130fe4`; the later focused VM host checks passed 12/12 on `c6becf81`,
including GNU construction. Exact target/kernel execution remains separate. The [evidence file](04_evidence_and_reconciliation.md#21-rebuild-status)
separates this source functionality from deployment inputs and unrun checks.

**Selected C08 feedback retention:** use a preallocated pool of JIT-miss facts
with explicit finite caller capacity sufficient for the supported workload.
No numeric deployment value or mathematically unbounded storage is implied.
Keep source site, resolved target, transfer/exit phase and exact producer/source-
version identity. Pending facts or translation do not by themselves disable new
JIT/delegation; the existing context/source/image checks still apply. Valid
same-version observations are cumulative compiler input before building an image.
Recording a fact, emitting coverage, actually publishing and acknowledging it
remain different events; uncovered/later facts stay pending. The reviewed kernel
source records coverage misses once before consumption, retains them without
pinning old code and binds ACK only to validated inputs of an actual publication.
Nonobservations and uncovered misses remain pending during normal execution.
The selected shutdown route archives exact copied facts/provenance with fsync
and content receipts before kernel SETTLED, after image/native/JIT drain;
SETTLED is separate from coverage ACK. Kernel settlement has source at `40ae39ce`,
and actual host/channel/runtime composition has reviewed source at `80095bfb`.
Explicit capacity covers all retained miss records until their final ACK or
settlement release. Source implementation is separate from actual deployment,
crash/restart reconstruction and unrun runtime evidence.

The goal covers native-legal source patterns across the declared Linux target, subject to the explicitly selected ordinary-mutex outer-unlock deferral below. That policy establishes no generic native timing or progress parity. Structures, keys and dispatch use lock/API, original-state, operation, source and ABI identities. Application names do not select a different protocol. Observations from mmap/munmap expose generic constraints; they do not select application-specific adaptations. Ordinary local/native execution remains a valid lock route where delegation is unavailable. Reader concurrency/mode/API semantics are required; execution placement is an open target policy. Origin-local readers are the conservative initial proposal, not a permanent restriction or authorization of remote readers.

## Authority and statement origins

This set guides a refactor or rewrite. The latest explicit user directions and semantic/native-API obligations govern the **target design**. Current kdlock/TCLock mechanisms are evidence and possible reuse, never target requirements merely because they exist. Repository operational rules still govern editing, execution environments and validation; this design does not change the running implementation or authorize an implementation step.

| Class | Origin and force | Examples |
| --- | --- | --- |
| F | Explicit fixed user direction | Original UB-derived JIT/GS lowering, lock-integrated helpers, optional unique selection, source-operation boundaries, exact no-replay handback, cumulative learning, general replacement, one core/two reference levels, selected ordinary-mutex outer-unlock deferral and Linux 7.0 x86_64 non-PREEMPT_RT |
| S | Semantic correctness or native-API obligation | Required exclusion/concurrency, API results, unique grant/release authority, actual context effects, ordering, exact continuation and last-user lifetime |
| P | Target mechanism/policy requiring a deliberate choice | Adapter ABI, integration compatibility, backend/queues, reader placement, pinning/waiting, capacities, node control, update/reclamation and rollout |
| E | Historical/current source or execution evidence | Pinned packet offsets/two-word adapter, node arrays, 32-row ledger, existing owner routing, support limits and recorded receipts |

Proposed defaults are P, including the explicitly approved **current five-edge direct-CALL discovery default**. That default remains selected unless deliberately changed; it is not immutable architecture. Normative statements in the protocol express F/S unless identified as a proposal, example or condition of a selected backend. The C register records P choices; the evidence file preserves E and the [audit/correction register](04_evidence_and_reconciliation.md#32-authority-audit-and-correction-register) records reclassifications. Historical revision records describe their original scope, not new target mandates.

API result, context, lifetime, exclusion and ordering duties remain required. The selected ordinary-mutex policy below changes outer release-timing/progress expectations only; it does not waive last-use proof or lock-container validity. The initial ordinary-mutex lane requires stable lock-object storage through actual physical release and final backend object access. C12 selects source-rebuilt integration with fresh private layouts; old binary lock/object-layout compatibility is not promised. C01 starts with ordinary mutex lock/unlock in sleepable task context, with other families later. C03 selects retention of the responsible physical outer-combiner context for deferred outer unlocks. C11 selects an MCS queue for the initial mutex lane; C04 retains the KD physical-R11 canonical-packet-base mapping. Private optional local/proxy claims, exact state/operation bridges, persistent records and recursive driving are connected in source through `ce423858`; source review does not prove their runtime ordering/lifetimes. Managed task provisioning/fork/exit and provider/compiler orchestration now have source through `c6becf81`; exact target application/build and runtime validation require separate receipts. C02 uses each MCS node's direct S_W pointer for active and nested requests. A stable task-owned root/auxiliary header supplies initial own backing before the first node; no external registry or active-S_W task field is used. C05 selects task-owned preallocated persistent request records and auxiliary control. The supported workload guarantees record availability within an explicit finite caller-supplied capacity covering all concurrently live and retained users. It selects no exhaustion recovery or separate local fallback; ordinary local winners stay in the unified persistent path. Complete control/context/lifetime validation remains work. R11 optimization discussion and T56 are deferred future work, not an active mapping choice. No selection establishes support evidence.

### Selected ordinary-mutex outer unlock

For an out-of-order outer mutex unlock, end the source fragment before the operation, record its exact source-unlock request and deferred marker, and notify/unwind to the retained responsible outer combiner. That combiner handles the marker, continues its normal batch protocol and physically releases through that protocol. This user selection supersedes the earlier transferable-grant recommendation and immediate outer-release requirements only for this mutex route. It changes neither the original UB JIT/GS lowering nor the one S_W and every-source-operation boundaries.

Source request/return, deferred acceptance, unwind readiness, owner handling, actual physical release and last-use/reclamation are distinct events. A marker or owner-handled result is not physical release. Extra waiting is accepted, without a generic native release-timing or progress-parity claim. Spin/rwlock/rwsem and downgrade contracts receive no deferral exception.

The user selected stable lock-object storage through actual physical release for the initial mutex lane, including the complete backend unlock's final object access. A source unlock/deferred marker is not permission to destroy or reinitialize the object. Owner/control records and any allocation containing them remain valid through their own exact source/return/notifier last users, which may extend beyond physical release; callback code remains retained through callback return. The caller must establish these lifetimes: retaining a combiner pointer alone does not retain its lock container. This permits a correctly materialized post-unlock continuation without waiting solely for physical release/object lifetime; no further lifetime-related resumption choice is pending. The release helper does not advance source. At `ce423858`, ordinary source macros/native bootstrap, the recursive episode driver, existing-grant native unlock and final auxiliary-actor cleanup connect the private CALL/return/cursor bridge in source. Managed provider/task orchestration is connected through `c6becf81`; exact target integration and runtime proof require separate receipts. A marker alone authorizes no arbitrary execution. The selected MCS queue and KD physical-R11 mapping do not by themselves implement optional claims or the exact state bridge. Other availability-dependent handshakes retain their explicit progress limits.

## Current iteration policy and assumption

Ordinary trusted critical-section source is intended to translate with the original backend. This is a target policy, not verified universal instruction/kernel equivalence. Lock/unlock operations split fragments. A recognized unsupported special instruction cuts only its affected control-flow path before that instruction; bypassed alternatives and independently safe shared joins remain translatable. Handback to native W occurs only if execution reaches that frontier, from the exact first-unexecuted instruction and current S_W, without replay. A real inability to provide that forward state remains a specific correctness issue, not a blanket reason to reject every region containing a recognized frontier.

**AS01 — explicit user-selected design assumption/scope:** general flags and SIMD are assumed correct in this iteration and need no separate general handling. This assumption is not an evidence claim or comprehensive equivalence proof. Do not add a general RFLAGS/SIMD capture/virtualization subsystem, flags shadow state or blanket admission gate. The explicit local exception is simulated PUSHFQ/POPFQ lowering through a reserved/mapped temporary GPR and the virtual source stack, described in [the JIT contract](02_jit_contract.md#35-local-pushfq-and-popfq-lowering). Existing selected special CPU-state frontiers and actual Linux context, authority and last-user duties remain.

## Read this set in order

1. [Lock protocol and state](01_lock_protocol.md): the one S_W, reference and ownership flowcharts, optional publication, recursive combining, release routing, ordering and lifetime.
2. [Original JIT contract](02_jit_contract.md): operation boundaries, per-lock entries and fragments, state bridge, exact handback and cumulative learning.
3. [Implementation plan and decisions](03_implementation_plan.md): confirmation choices, work packages, support matrix and acceptance tests.
4. [Evidence and reconciliation](04_evidence_and_reconciliation.md): source versions, existing versus proposed behavior, old-section crosswalk and primary references.

The files are one design. A proposal in one file is not an implementation claim in another. The original documents remain historical evidence rather than two competing specifications.

## Established target directions and semantic requirements (F/S)

- The target is Linux 7.0 on x86_64 without PREEMPT_RT. Support depends on the exact kernel revision, configuration and API variant.
- The goal is general lock replacement with valid local/native routes. No mmap/munmap-specific structure, dispatch key, function-name exception or execution architecture is selected.
- kdlock is the lock. Its delegation and JIT helpers execute within lock acquisition, combining, waiting and release paths. No background execution worker is required by this architecture.
- Delegation is optional. Publishing eligibility does not irrevocably assign the source continuation to another task.
- A publishing waiter can win local acquisition, execute its own source body, or become the combiner and serve eligible requests before executing its own body. An exclusive claim must first close the competing remote route.
- A different combiner can instead claim the request and execute its admitted JIT fragments. Exactly one participant advances a logical continuation.
- Each original W has one S_W containing its canonical packet, current cursor and operation phase. All nested nodes reference it directly without unused full packets or packet-sized unions. Exclusive execution and transfer ordering determine who may update and advance it; they do not require a particular lock/token/counter framework. Retained grants and image descriptors are not additional execution states.
- Every encountered lock and unlock terminates the current JIT fragment **before that operation is performed**. The lock implementation performs the operation once, then chooses the next continuation route.
- This boundary applies to source-program lock operations. kdlock's internal queue/metadata locks stay inside its implementation and never become recursive source requests or W's logical grants.
- After any successful acquisition, release or mode operation, the design must support admission of a valid current-state fragment where its source/context contract permits. A correct terminal native suffix remains a fallback and does not prove whole-root JIT completion.
- Recursive delegation is serial. An outer combiner can acquire the inner lock, wait for its combiner, or become its combiner while preserving the outer execution relationship.
- Lock nesting does not mean native same-lock reentrancy. Recursive acquisition of a nonrecursive lock is not legalized.
- Nested locks can have separate entries and image generations from the same original backend. One protected scope can contain several JIT fragments separated by lock operations.
- Original UB-style translation, software register virtualization and kdlock's original GS-relative lowering remain. No replacement JIT backend or native borrowed-stack engine is selected.
- A miss hands the current unfinished continuation back to the originating task without replay. Learning serves later execution and cannot be needed to finish the current invocation.
- JIT updates accumulate source-versioned observations and make complete validated code/metadata versions visible coherently. Active code/return bindings remain valid through their actual last users; C06/C09 select quiesced RCU pointer replacement with exact retained users and old-reader grace.
- Non-LIFO source unlock retains exact acquisition identity and follows the selected family release protocol. The chosen ordinary-mutex route can defer outer physical release; other families retain their declared release duties. Operation phase/results and actual Linux context/lifetime duties remain exact. AS01 supplies the flags/SIMD design scope only; it proves no general equivalence and introduces no IRQ/NMI support.
- Reader concurrency, mode, result and context semantics hold under the execution placement explicitly selected by C10. No unselected remote-reader or other unsupported route is enabled by this document.
- Intentional lock boundaries and permanent capability frontiers are distinct from ordinary learning misses. Compiler budgets have precise resource classes and bounded forward behavior.
- Observability separates application completion, local execution, fragment completion, native handback and whole-root JIT return, with actual exit cursor/reason and ownership phase when attribution matters.
- This design specifies the active model and incremental implementation plan. Current implementation progress is recorded in the [repository README](../../../README.md); design statements do not establish kernel integration or performance results.

## Vocabulary

| Term | Meaning |
| --- | --- |
| Origin or W | The task whose source program, lock API results and observable effects must be preserved. It may wait, execute locally, or become a combiner. |
| Executor | The task currently allowed to advance W's continuation. It can be W or a combiner. |
| Combiner C | A task temporarily holding the lock's combining role and serving selected requests under actual backend grants. It is not a dedicated worker. |
| Published request | An eligible, retained description offered to the lock's selection protocol. Publication is not remote selection and is not acquisition. |
| S_W | The one stable canonical execution state of original W: packet, current cursor/phase, execution owner/sequence and grant/relationship/source/image references. |
| Continuation | The current forward execution described by S_W. It is not a second mutable state object or a per-lock packet copy. |
| Protected scope | The source-level lifetime of one successful acquisition, including any legal mode change. Track it separately from an outer mutex batch whose physical exclusion remains held after a deferred source-unlock request. |
| JIT fragment | Generated source execution from an admitted entry/resume cursor to the next encountered lock/unlock, supported miss/terminal, or completed-scope return. |
| Execution record | Logical lock-role control, return routing and retained references pointing to S_W; normally embedded or bounded call-local information, not a required separate allocation. |
| Grant | Exact successful acquisition identity, mode, backend authority, release route and context effects; physical release duties can remain after a deferred source unlock. |
| Deferred outer unlock | A selected ordinary-mutex source-unlock request retained for the responsible outer combiner; neither its marker nor owner handling is actual physical release. |
| Lock helpers | Functional code inside kdlock acquisition/unlock/combiner paths, called runtime in older discussions. |
| Native suffix | Transfer of the unfinished continuation to W; terminal handling is the conservative proposed default, with separately validated resumable services/reentry an open choice. |

`current`, hardware GS and the address space still belong to the physical executor. A logical W field and software GS lowering do not switch those kernel contexts.

## The design in one example

For `lock(A); prefix; lock(B); middle; unlock(A); suffix; unlock(B)`:

1. A's lock code arbitrates local execution or optional delegation.
2. A selected combiner runs a fragment containing only `prefix`, with its active state pointing to W's S_W. Encountering `lock(B)` exports resident logical registers and the pending operation into that same state and ends the fragment.
3. Lock code handles B. It may acquire B on the current task, become B's combiner, or publish an optional child node pointing to the same S_W and suspend the outer continuation. A new executor must win lock selection and become the exclusive source executor under that ordering.
4. The chosen executor runs `middle` in an admitted fragment. Encountering `unlock(A)` ends that fragment even though B remains held.
5. For the selected ordinary-mutex route, lock code records A1's exact source-unlock request and deferred marker. A remains physically excluded while the responsible outer-combiner context is retained and notified/unwound to; the marker is not RELEASED.
6. The selected stable-object contract permits a correctly materialized post-unlock continuation without waiting solely for A's physical release. It uses the exact current operation/CALL-return/cursor phase, exclusive executor, remaining logical grants and pending A physical duties, once only. The private C04 bridge is connected to the managed source path; exact target integration remains unvalidated; the marker alone advances no source. Encountering `unlock(B)` always ends its fragment.
7. On return to the responsible outer context, it handles A1's marker and continues its normal batch/release protocol. Actual physical release and last-user retirement are recorded separately. Ownership of the same S_W follows the saved execution relationship or returns to W; only outer combiner control is restored, never a pre-B packet or old whole-region cursor.

The exact source operation determines which acquisition receives an unlock request. For the selected mutex route, the exact acquisition binding and live execution relationship identify the responsible retained outer combiner; ancestry alone is not acquisition identity and the source request is not physical release. Ending a fragment neither releases exclusion nor retires an execution record.

## Review boundary

Fixed F directions and S obligations are not mechanism questions. The plan records selected C12 integration, the C01 initial lane, C02 direct MCS state pointers and task-owned initial backing, C03 owner-retained mutex deferral/stable object lifetime, C11 MCS queue and C04 retained KD physical-R11 canonical-packet-base mapping. C05 task-owned auxiliary entry/persistent requests with supported-workload availability and C06/C09 quiesced RCU replacement with exact users are also selected. Source checkpoint `40ae39ce` implements cold task storage and immutable-contract source snapshots/native holds, plus shutdown SETTLED. The selected source contract covers every dependency/mutator; module_get alone is not a freeze. Managed fork/failure/exit hooks, channel/compiler/executable-provider/runtime composition and fsynced archival settlement are source-implemented through `c6becf81`. Remaining deployment work supplies exact source/configuration/GS inputs, pool/control-stack sizes and context proof; exact kernel application/build and execution require separate receipts. Crash/restart reconstruction beyond the implemented session/archive workflow is not provided. The ordinary native/recursive path is connected in source at `ce423858`; all runtime/lifetime/progress acceptance evidence remains unrun. Further API/context lanes retain their separate choices. No choice can replace the original JIT, duplicate W state, extend the selected mutex deferral exception to other semantics or substitute an application-specific design. Choosing an extension requires its own scope and proof; leaving it open neither prohibits it permanently nor authorizes it now. See the plan's prioritized confirmation list.

This Linux 7.0-only baseline keeps the five individual Markdown documents for incremental audit. The complete unsanitized design snapshot remains recoverable through the archive reference named in the repository README.
