# kdlock redesign documentation set

**Status:** integrated design for review, not an implementation claim  
**Target:** Linux 7.0, x86_64, non-PREEMPT_RT
**Revision:** 1.6, path-specific frontiers and local flags-stack contract
**Scope:** a complete kdlock redesign for general lock replacement, independent of the ongoing mmap1 workstream

## Purpose and conclusion

Rebuild kdlock as a lock implementation with optional delegated execution. Like TCLock, acquisition, combiner election, waiting, recursive delegation and unlock handling are all parts of the lock implementation. The original UB-derived JIT remains the execution engine for admitted delegated source code. The word **runtime**, when used in earlier material, means helper functions inside this lock implementation. It does not identify a separate subsystem, service, worker pool or architectural component.

This set integrates `kdlock_nested_delegation_proposal.md` revision 1.2 and `kdlock_mixed_nesting_design_v0_6.md` revision 0.6. It resolves their conflicting language using the latest user direction:

> Every encountered lock operation and every encountered unlock operation ends the current JIT fragment. The lock implementation handles that operation, including recursive delegation when appropriate.

An inner lock or an ancestor unlock is not executed through the old generated fragment merely because the outer protected scope remains live. After the operation, the lock code may resume a separately admitted JIT fragment with current state, transfer that continuation through recursive combining, or return the exact unfinished continuation to the originating task.

Each original thread W has exactly **one canonical execution state S_W**. A's node, B's node and suspended execution relationships reference that same state: `N_A.state == N_B.state == &S_W`. They do not own separate copies of W's continuation or register packet. A physical combiner's own thread state is distinct from the active W state it borrows. This cardinality is fixed; storage placement, lookup and transfer primitives remain mechanism choices.

The physical target has two storage/reference levels: W's thread-owned core containing its one canonical regs packet, and lock/control users pointing directly to that core. Users must not reserve an unused full W packet, duplicate source continuation or packet-sized owned/borrowed union. This is a layout requirement, not a two-lock nesting limit: A -> B -> C still uses the same S_W within proved resource/stack bounds. Required per-lock authority/control and native call-stack register preservation remain. The split is proposed, with no measured memory-saving claim.

The starting proposal is the target one-core/two-level model with bounded structured recursive lock calls, call-local outer combining control and lock-local selection/return ordering. It can use a fresh layout or deliberately reuse suitable current components; the complete target S_W is not claimed to exist already. The field sketch describes semantic information, not required allocations. Nested acquisition adds no execution frame by itself; returning ownership to W adds no handback object. Extra stable records, notification storage, explicit stacks or refcounts need a demonstrated escape, stack-bound, lifetime or measured requirement. [The minimal mechanism table](01_lock_protocol.md#minimal-starting-mechanism-versus-optional-extensions) states those conditions without dropping ownership or last-user obligations.

**Open proposal:** embed necessary per-lock control in a request-lifetime node where that simplifies the proof. An acquisition-only MCS scheduling slot is insufficient if it is reused before return, release/ACK or handback users finish. Ordinary uncontended local acquisition need not create a node or capture full execution state; outer combining control can stay bounded call-local. Node retention, capacity and cache placement remain choices to audit in [the proposal](01_lock_protocol.md#proposed-node-owned-control-open).

The goal covers native-legal source patterns across the declared Linux target. Structures, keys and dispatch use lock/API, original-state, operation, source and ABI identities. Application names do not select a different protocol. Observations from mmap/munmap expose generic constraints; they do not select application-specific adaptations. Ordinary local/native execution remains a valid lock route where delegation is unavailable. Reader concurrency/mode/API semantics are required; execution placement is an open target policy. Origin-local readers are the conservative initial proposal, not a permanent restriction or authorization of remote readers.

## Authority and statement origins

This set guides a refactor or rewrite. The latest explicit user directions and semantic/native-API obligations govern the **target design**. Current kdlock/TCLock mechanisms are evidence and possible reuse, never target requirements merely because they exist. Repository operational rules still govern editing, execution environments and validation; this design does not change the running implementation or authorize an implementation step.

| Class | Origin and force | Examples |
| --- | --- | --- |
| F | Explicit fixed user direction | Original UB-derived JIT/GS lowering, lock-integrated helpers, optional unique selection, source-operation boundaries, exact no-replay handback, cumulative learning, general replacement, one core/two reference levels and Linux 7.0 x86_64 non-PREEMPT_RT |
| S | Semantic correctness or native-API obligation | Required exclusion/concurrency, API results, unique grant/release authority, actual context effects, ordering, exact continuation and last-user lifetime |
| P | Target mechanism/policy requiring a deliberate choice | Adapter ABI, integration compatibility, backend/queues, reader placement, pinning/waiting, capacities, node control, update/reclamation and rollout |
| E | Historical/current source or execution evidence | Pinned packet offsets/two-word adapter, node arrays, 32-row ledger, existing owner routing, support limits and recorded receipts |

Proposed defaults are P, including the explicitly approved **current five-edge direct-CALL discovery default**. That default remains selected unless deliberately changed; it is not immutable architecture. Normative statements in the protocol express F/S unless identified as a proposal, example or condition of a selected backend. The C register records P choices; the evidence file preserves E and the [audit/correction register](04_evidence_and_reconciliation.md#32-authority-audit-and-correction-register) records reclassifications. Historical revision records describe their original scope, not new target mandates.

Public/native lock APIs and observable behavior remain S. Whether integration rebuilds all affected source or also promises binary/lock-object-layout compatibility is open C12. The current object size and private JIT adapter do not decide it. A versioned target adapter/layout is possible under the chosen integration contract; compatibility is neither promised nor discarded implicitly.

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
- JIT updates accumulate source-versioned observations and make complete validated code/metadata versions visible coherently. Active code/return bindings remain valid through their actual last users; immutable generations or a proved quiesced update/rebinding strategy are P choices.
- Non-LIFO release, exact acquisition/release authority, operation results and actual Linux context/lifetime duties remain. AS01 supplies the flags/SIMD design scope only; it proves no general equivalence and introduces no IRQ/NMI support.
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
| Protected scope | The logical lifetime of one successful acquisition, including any legal mode change. It can outlive several fragments and nested operations. |
| JIT fragment | Generated source execution from an admitted entry/resume cursor to the next encountered lock/unlock, supported miss/terminal, or completed-scope return. |
| Execution record | Logical lock-role control, return routing and retained references pointing to S_W; normally embedded or bounded call-local information, not a required separate allocation. |
| Grant | Exact successful acquisition identity, mode, backend authority, release route and context effects. |
| Lock helpers | Functional code inside kdlock acquisition/unlock/combiner paths, called runtime in older discussions. |
| Native suffix | Transfer of the unfinished continuation to W; terminal handling is the conservative proposed default, with separately validated resumable services/reentry an open choice. |

`current`, hardware GS and the address space still belong to the physical executor. A logical W field and software GS lowering do not switch those kernel contexts.

## The design in one example

For `lock(A); prefix; lock(B); middle; unlock(A); suffix; unlock(B)`:

1. A's lock code arbitrates local execution or optional delegation.
2. A selected combiner runs a fragment containing only `prefix`, with its active state pointing to W's S_W. Encountering `lock(B)` exports resident logical registers and the pending operation into that same state and ends the fragment.
3. Lock code handles B. It may acquire B on the current task, become B's combiner, or publish an optional child node pointing to the same S_W and suspend the outer continuation. A new executor must win lock selection and become the exclusive source executor under that ordering.
4. The chosen executor runs `middle` in an admitted fragment. Encountering `unlock(A)` ends that fragment even though B remains held.
5. The lock code routes the exact A1 release to its physical authority, waits for the promised actual release, and updates context/grant state. It does not keep A excluded merely to preserve a combining batch.
6. With B still live, a validated next fragment can execute `suffix`. Encountering `unlock(B)` ends that fragment.
7. B's lock code performs the exact release. Ownership of the same S_W returns through the saved execution relationship or to W. Only outer combiner control is restored; no pre-B packet or old whole-region JIT cursor is restored.

The source program, not frame depth or the first symbol containing "unlock," determines which grant ends. Ending a fragment does not itself release a grant or retire an execution record.

## Review boundary

Fixed F directions and S obligations are not mechanism questions. Decisions C01 through C12 select integration/compatibility, storage, adapter ABI, grant authority/arbitration, generation binding, learning/update policies and API/context/reader lanes. They cannot replace the original JIT, duplicate W state, weaken semantics or substitute an application-specific design. Choosing an extension requires its own scope and proof; leaving it open neither prohibits it permanently nor authorizes it now. See the plan's prioritized confirmation list.

This Linux 7.0-only baseline keeps the five individual Markdown documents for incremental audit. The complete unsanitized design snapshot remains recoverable through the archive reference named in the repository README.
