# kdlock lock protocol and state

**Status:** proposed complete design contract  
**Applies to:** the independent redesign described in [the overview](00_overview.md)  
**Implementation boundary:** every function described here belongs to kdlock's lock, unlock, wait or combining implementation

Apply the [F/S/P/E authority rule](00_overview.md#authority-and-statement-origins). Fixed behavior and semantic obligations do not prescribe the current owner word, queues, pinning, pools or byte layouts. State/flow diagrams and storage examples are P; current paths are E and impose their actual constraints only when deliberately retained.

## 1 Roles are temporary parts of the lock

W is the origin of a source continuation. C_A is a physical task combining A, which may itself be W. C_A can enter B's lock code while executing another origin's source and temporarily act as B's waiter or combiner. No dedicated task owns the combiner role.

The lock code has three responsibilities at a source lock boundary:

1. Preserve current continuation and operation phase.
2. Apply the selected lock family's acquisition, release or mode-change protocol.
3. Choose the next executor and admitted source continuation.

JIT code executes admitted source fragments between those operations. These are cooperating functions of one lock implementation, not a lock plus an independent execution service.

Keep four kinds of state distinct:

- **Request selection:** which participant may attempt this source operation/body.
- **Actual grant:** what physical backend protection was acquired.
- **Continuation authority:** which participant may advance the source program.
- **Storage lifetime:** which observers may still access records and notifications.

Publication, selection, acquisition, logical unlock, physical release and retirement are different events.

### 1.1 Original state and source-operation context

Each original W has exactly one canonical execution state S_W. When C_A executes W's source, its active-origin pointer resolves S_W. When it serves another origin V, the pointer resolves V's distinct S_V. C_A's own canonical state S_C_A remains distinct unless C_A is itself W. Saving C_A's lock-role control does not create another W state.

"Local" is relative to selection. A root local winner is W running its own source; a nested local B winner can be C_A continuing W's source through S_W. C_A does not become the logical origin. If origin-as-combiner W serves X, it uses S_X for X, then restores its active pointer to the same S_W for its own continuation.

Recognize a nested source operation from the active execution relationship, exact pending source API/phase and live-grant context. Neither `current != W` nor pointer equality alone identifies nesting: W can nest locally, and C_A can execute several origins. At W's nested lock(B), `N_B.state` must be `&S_W`, never `&S_C_A` merely because physical `current` is C_A.

Every-operation boundaries refer to the source program's lock/unlock/mode operations. Native helpers' internal queue, metadata and arbitration locks are implementation bookkeeping. They do not recursively enter source-operation dispatch or append grants to W's logical ledger. Define the source-operation versus internal-operation context in the wrapper/helper contract, rather than excluding particular application function names. Internal locks still impose their actual physical ordering, atomicity and scheduling obligations on the helper.

## 2 Optional publication and unique selection

### 2.1 Required behavior

Publishing a request offers delegation; it does not force it. While an offered request remains unclaimed, the origin can win the same lock's ordinary local path or become its combiner. Another combiner can instead select the request. The two outcomes must be mutually exclusive.

For each chosen backend, identify the transaction/ordering that makes these outcomes exclusive. The current mutex's shared wait-lock selection is E and a reuse candidate, not a required lock or owner-word protocol. A flag alone is insufficient unless the full queue/claim/result proof establishes:

- local acquisition selection;
- proxy selection;
- origin combiner election;
- cancellation or refusal;
- transfer and queue unlinking.

A successful local selection closes remote selection before the source body can run. A successful proxy selection closes the origin's local source-body path. A queue reservation or optimistic spinning membership does not by itself give either participant a successful source acquisition.

### 2.2 Proposed request states

These names describe semantics, not existing field names:

```text
PRIVATE
  -> OFFERED
       -> CLAIMED_LOCAL  -> ACQUIRING_LOCAL  -> ACQUIRED_LOCAL
       -> CLAIMED_PROXY  -> ACQUIRING_PROXY  -> ACQUIRED_PROXY
       -> CANCELLED or DECLINED
  -> RESULT_READY
  -> RESULT_CONSUMED
  -> RETIRABLE
```

Only one selection transition can win. Failure/interrupt results can also reach RESULT_READY without an acquired grant. RETIRABLE requires the final queue observer, grant operation, notification and continuation user to finish; it does not follow merely from RESULT_CONSUMED.

The origin can acquire physically after local selection, combine selected other requests under a valid batching contract, then execute its own body locally. Its source body is not accidentally treated as a proxy request for itself. If C_A wins a nested B selection, it may combine B while preserving its outer A execution state.

A source request may be selected but still waiting for a physical grant. Keep that phase explicit so cancellation or handback cannot reacquire a completed operation or abandon an incomplete backend claim.

Lock-specific selection cooperates with S_W transfer. A participant advances W only with a valid live request/state, pending operation, selected endpoint, actual grant and exclusive execution. Stale nodes cannot regain authority. C11 chooses target serialization/checks for its actual reuse/cancellation races; existing arbitration is only a candidate proof.

Owner/sequence names express exclusive execution and required ordering, not a per-S_W lock/token framework or counter on every hop. The starting P is lock-local selection plus sender-stop, receiver-start and structured return ordering; select its primitive rather than inheriting the current wait lock/queue. Explicit incarnation/sequence checks are needed only for actual reuse, cancellation or escaping-reference races. Scoped grant identity must distinguish A1/A2 and obsolete release without prescribing a ledger.

### 2.3 Publication sequence

1. Reserve the request's required completion, release and forward-continuation resources and retain S_W.
2. The current sequence holder exports resident logical registers, virtual stack/cursor and exact pending operation into S_W's one canonical packet/descriptor.
3. Freeze source advancement and finish the export before publishing READY. Initialize the node's `state = &S_W`, exact operation binding, transfer sequence, retained dependencies and queue links.
4. Publish OFFERED/READY with the family's required release ordering. The offering task can continue lock arbitration/wait code, not W's source suffix.
5. Local/proxy selection, origin election and cancellation serialize through the family protocol together with the declared state-transfer handshake.
6. The winner observes the ready state pointer through the family protocol, obtains the actual grant and establishes exclusive execution before source advancement; apply any identity/sequence checks needed by that protocol. Failed acquisition creates no grant and has its own serialized result route.
7. The authorized owner records the exact operation outcome in S_W, validates the next cursor/context and executes a fragment or transfers the exact suffix. Return transfers use the same export/freeze/sequence discipline on the same state.

No second task may write the canonical packet while its owner exports or executes it. If eligibility is published before export finishes, the chosen protocol must gate source execution on readiness; a separate READY field is one option. Export materializes the same canonical backing, without copying W's packet into a child node.

### 2.4 Cancellation and local reclamation

Cancellation of an OFFERED request races with selection at the same serialization point. If cancellation wins, close both source-execution routes and remove all temporary backend/queue claims before returning the error. If selection/acquisition wins, follow that operation's declared signal/API result contract; do not report cancellation and also execute the successful body.

A timeout is diagnostic. It cannot steal a grant, undo a selected body's effects or permit record reuse. "Remote did not respond" is not proof that remote selection never happened.

Local victory does not permit immediate reuse of published storage. Remote observers must either be excluded under the queue protocol or release retained references. Reuse needs the same exact identity and lifetime discipline as remote completion.

Transfer/cancellation metadata has a declared serialization authority distinct from permission to mutate W's running packet. A cancellation winner publishes its result through that protocol; the authorized S_W owner consumes it. A stale transfer/cancel sequence can neither change the packet nor select a new executor. Sequence rejection must occur while all inspected nodes/state remain retained, including the chosen wrap/reuse rule.

Delayed grant ACKs are imported by the current S_W owner only after the scoped state/request/acquisition identity and expected operation phase match, including explicit incarnation/sequence checks where the protocol needs them. An obsolete result cannot overwrite a newer operation, and a remote grant authority never writes S_W's packet directly.

An ACK for an older retained grant may still finish that grant's matching custody/retirement transaction. Validate it against that retained transaction, rather than treating it as the result of S_W's newer source operation. Rejecting an obsolete source-state update must not discard an outstanding physical release or last-reference duty.

## 3 Proposed records and their owners

**Fixed cardinality and physical target:** one thread-owned core S_W containing W's canonical regs packet once. The former invocation/continuation split is consolidated below. Nested entries, lock nodes and outer-control users point directly to that original core; none owns a duplicate source continuation or reserves another full W packet. C02 chooses the core's placement/anchor and reuse, not this physical separation or the number of W states.

Small synchronous control can use the C stack only while its call remains alive through every remote access and final ACK. The target core survives all admitted queue, grant, executor, return and native-suffix users. Nested relationships use the same S_W, not another execution state; the complete target core is not claimed to exist already.

### Two storage/reference levels

```text
Level 1: thread-owned cores
  S_W   { canonical regs once; current cursor/phase; ownership and dependencies }
  S_C_A { C_A's own canonical regs; its own source state }

Level 2: referring users, with no full W packet or duplicate continuation
  N_A.state             ------> &S_W
  N_B.state             ------> &S_W
  N_C.state             ------> &S_W
  outer_control.state   ------> &S_W
  C_A.active_state      ------> &S_W while executing W
```

Two levels describe storage/reference organization, not a maximum nesting depth of two. A -> B -> C and deeper admitted recursion retain direct pointers to the same S_W within proved stack/resource bounds. C_A uses S_C_A for its own program, but neither N_A nor nested N_B routes W through a packet owned by C_A's control record.

Keep only necessary selection/queue, family/mode/grant/operation identity, outer control and completion information under the proposed structured lifetime. A pointer alias is insufficient if users still reserve an unused full W packet or packet-sized owned/borrowed union. Preserve required per-lock authority/control and native call-stack saves. The fixed two-level target selects neither an allocator nor a private packet/frame layout and claims no measured saving.

### Minimal starting mechanism versus optional extensions

**P, starting proposal:** bounded structured recursion, call-local outer control and lock-local ordering in the target one-core/two-level model. The sketch names logical information and last-user obligations, not a required object graph. A fresh core/node layout is allowed; current sharing/queues are reuse evidence only. "Retain" means keep valid through the actual last user, not automatically increment a refcount. Extra machinery needs a concrete reason.

| Concern | Minimal starting mechanism | Condition requiring more machinery |
| --- | --- | --- |
| W execution and handback | One S_W/packet; users reference it; returning ownership changes its current binding/result | An actual reference escapes storage lifetime, requiring stable backing for the same S_W; no second packet or continuation/handback object merely for transfer |
| Nested outer control | Bounded recursive calls keep outer control call-local through child/release/result work | Return/nonlocal transfer invalidates referenced control or stack bounds fail: choose suitable stable target storage or a bounded explicit stack |
| Grants and identity | Exact authority, A1/A2 identity and results in chosen core/user fields or valid call-local control | A concrete non-LIFO/object/custody last user outlives that storage: retain necessary information independently of the invalidated storage |
| Results and ACKs | Chosen core/user fields, ordinary return and lock-local ordering; the waiting recursive parent still services ancestor releases | A callback/notification can access payload after its owner returns or permits reuse: extend its lifetime, finish notification before reuse, or use stable notification storage |
| Lifetime accounting | Structured call, queue ownership and return/ACK ordering prove last use without an added refcount | Independent asynchronous holders escape those proofs: select exact retention accounting, possibly a refcount; justify each extra holder/record rather than adding one per hop |

Materialization before transfer, one active executor, optional selection, timely actual non-LIFO release and physical context legality remain mandatory. Sleeping alone does not invalidate a still-live task stack; migration does require a valid ownership/reservation rule for CPU-local storage. No sleep is permitted under a live atomic obligation. Bound recursive depth and kernel-stack use before enabling the route; an unproved bound needs a supported forward/local route or a separately justified bounded mechanism, not unbounded recursion.

### Proposed node-owned control (open)

**P, recommendation for audit:** consider embedding a request's necessary control in a target node reserved through every actual user. This selects neither an existing layout nor MCS as the backend. W's core/regs and direct referring users remain fixed. Queued/delegated requests or a retained-control need can justify a node; an uncontended local path need not create one or capture full execution state.

| Information | Candidate placement | Lifetime/layout condition |
| --- | --- | --- |
| Selected queue/claim status and polling fields | Candidate compact hot part of the node | Account for each logical membership's duties and last observer; choose links/topology rather than requiring current queues |
| Exact family/mode/acquisition identity and physical release endpoint/token | Necessary request-node fields | A1/A2 stay distinct; authority remains actionable through successful grant/release duties and matching ACKs |
| Parent/child return route and request-specific control | Node fields only where the request needs them | Child/ancestor and native-handback users finish before reuse; ordinary saved outer combining control stays bounded call-local where its enclosing call proves lifetime |
| Result, cancellation, ACK and notification state | Chosen node fields where sufficient | Selection/cancel races serialize and final notification access ends before reuse; no automatic extra frame or refcount |
| W's regs and current source continuation | Only the one S_W core; node holds a direct pointer | No full W packet, duplicate source cursor/continuation or packet-sized owned/borrowed union in the node |

If MCS or another reusable scheduling slot is selected, distinguish it from a **request-lifetime node**. Unlink, acquisition, source unlock, physical unlock and retirement differ. N_A can be unlinked and A1 released while B still needs its control; A2 cannot overwrite it before those and queue/cancel/ACK/notification/native users finish. Structured ownership is the proposed default proof. If the selected slot is reused earlier, retain the composite request or put escaping small control in valid target core/user storage. Renaming a slot does not extend lifetime; other topologies need equivalent proofs.

**Conditional spin example (E/P):** an acquisition-only MCS/qspinlock slot can become reusable before body unlock under its backend contract. It is not automatically a long-lived control owner. If per-CPU reservations/pools are selected, prove their chosen capacity and nested progress; never wait for a slot held by an ancestor waiting for that child. The rewrite need not use those nodes or pools.

**Sleepable locks (S/P):** chosen control storage stays valid across allowed scheduling/migration. Pinning, parking/waiting and pool policy are C01/C02/C11 target choices, not fixed by current published-waiter code; its policy is unchanged by this document. If a backend uses both abortable OSQ and delegation memberships, discharge their separate selection/cancel/progress/retirement duties. Separate links are one solution. A merged protocol needs proof of all equivalent duties; neither OSQ nor two queues is required for every rewrite.

The target local route keeps exact acquisition/release provenance without forcing a node/full capture on every fast path. A later delegation importing an ancestor establishes actionable authority before effects or remains local; it cannot invent a past grant/node. Existing local routing is a candidate, not the only target route.

**Cache layout remains open and measured.** Keep contended queue/poll fields compact. Where access patterns require separation, isolate producer next-link writes from waiter polling and combiner control/result writes; W's regs stays in its separate core. Audit member offsets, alignment, pool stride and hot/cold writers/readers. An enriched node may span several cache lines and still be the simplest correct design; there is no 64-byte, performance-gain or measured-saving claim. C02/C05 and T49 gate retention/placement on concrete lifetime, progress, capacity and layout evidence.

The following field groups are a semantic inventory to embed or map into the minimal starting mechanism or this still-open node proposal. Reserving completion/release resources means ensuring that the required storage and progress route exist before effects; it need not allocate anything.

```text
canonical_thread_state S_W                 // exactly one for original W
  state_id, incarnation, original_task_ref  // scoped identity; encode only as needed
  invocation_id, invocation_phase
  canonical_regs_packet                   // physically once in this thread core
  packet_layout_id, valid_state_mask
  current_source_cursor, source_stack_and_return_map
  operation_descriptor                    // one current descriptor, below
  execution_owner_endpoint, execution_sequence // binding/order; counter optional
  transfer_phase, transfer_sequence        // chosen ordering or needed checks
  active_grant_index
  active_relationship_ref, retained_relationship_refs
  source_dependency_refs, bound_entry_image_refs
  native_suffix_state
  final_completion_state_or_binding

operation_descriptor                      // embedded in S_W
  operation_id, phase
  operation_domain = source_lock_API
  source_callsite, resolved_target, arguments
  family, API_variant, mode
  acquisition_ref_or_requested_object
  completed_result
  source_stack_transition_state
  next_source_cursor

execution_record                          // logical control; embedded/call-local
  relationship_id, incarnation
  state_ref = &S_W
  parent_ref, active_child_ref
  saved_outer_combining_control            // role/queue control, no W packet
  retained_entry_image_refs
  explicit_return_route
  relationship_phase
  completion_state_or_binding
  retained_release_duties

grant                                     // logical information; may be embedded
  acquisition_id, incarnation
  retained_state_ref_if_required
  object_identity, live_object_ref
  family, mode
  backend_authority, backend_token
  release_route, release_sequence
  grant_state, logical_scope_state
  context_effect_tokens
  dependency_refs

per_lock_node N_L                          // request/queue state only
  node_id, incarnation
  state = &S_W
  expected_state_incarnation, expected_execution_sequence // only where needed
  offering_execution_ref
  target_lock_identity, family, requested_API, mode
  operation_identity, selected_entry_ref
  publication_and_selection_state
  selected_executor_endpoint
  transfer_sequence
  queue_membership_refs
  completion_state_or_binding

operation_mailbox                         // optional channel in target fields
  retained_state_identity, incarnation
  request_identity, acquisition_identity, operation_sequence
  operation, payload, result
  publication_word
  storage_owner_ref
```

Map this semantic sketch to the chosen concrete target fields/layout. `N_A.state == N_B.state == N_C.state == &S_W` is fixed, not an allocation option. User/control records carry needed role, identity, routing, references and results without a competing packet/cursor/phase or unused full packet-sized union. Grant information, optional mailboxes and code/image descriptors are not additional W states or intermediate packet owners; no current kdlock structure must be retained merely to match this sketch.

| Record or field | Sole mutation authority | Retention rule |
| --- | --- | --- |
| S_W packet, cursor and current operation | Exclusive current execution-sequence holder | Same backing remains valid through all executors, native continuation and remote references |
| S_W transfer metadata and node claim | Declared family/ownership arbitration protocol | State/node incarnations and matching sequences remain retained through selection/cancel/return |
| Selection state and queue transition | Chosen family arbitration protocol | Published observers drain before reuse |
| Physical grant/backend token | Actual family-specific authority | Remains actionable until every release/mode obligation ends |
| Logical live-grant lookup | Current executor consuming matching authority results | Chosen identity/reference bindings remain valid through non-LIFO release/reuse; index and slot layout are open |
| Saved outer combining control and active-origin pointer | Physical task's lock implementation under the transfer protocol | Restore role and borrowed-state reference, never W's old packet |
| Completion result | Selected producer | Final publication only after producer's last retiring-payload access |
| Image/code publication state | Chosen isolated/coherent publication protocol | Every code/return binding stays valid; update/reclamation follows C06/C09 |
| Source admission state | Defined source-provider protocol | Closing roots cannot strand admitted completion chains |

An executor endpoint is a retained task/request endpoint with a duty to respond, not a CPU number assumed stable across scheduling. A pointer or origin label alone does not confer physical unlock authority.

The selected grant authority services its release/mode protocol while another participant may execute S_W; it never overwrites a foreign running packet. Only the authorized current executor imports matching results into W's operation/packet/index. Grant/read-credit custody can outlive an executor/control record; target core/user storage suffices if its proved lifetime covers that custody. Extra storage needs an actual last user that outlives the chosen storage, not a current record type.

### 3.1 Lookup and locality

**P:** prefer task/request/lock-local ownership and simple direct references. Shared/global routing is neither the default nor absolutely banned: C02 must justify necessity, contention/scaling, lookup completeness, publication, identity and last-user lifetime. Exact authority and valid lookup are S; inherited registries and blanket prohibitions are not architecture.

Public `unlock(A)` must resolve its exact live acquisition, and `lock(B)` must find active W state after allowed migration. Lock-resident data alone does not establish that lookup. C02 chooses an anchor/token/routing scheme with task-exit, restoration and any CPU lifecycle rules. A fresh implementation can supply it directly; migration keeps any retained compatibility route correct until replacement is proved.

The anchor must distinguish a physical task's own state from its active borrowed origin. While serving W, C's active pointer resolves S_W; while serving V, it resolves S_V. Switching origins preserves each state's sequence/lifetime and restores the outer pointer/control afterward. Physical `current = C` is insufficient for either lookup. Lock family/API/mode, original-state identity, source cursor/epoch, operation phase and ABI determine routing, not an application's root name.

Before switching away, materialize resident values into the outgoing origin's own canonical packet and stop its source advancement. Enter the other origin only with its valid sequence ownership. Restoring the outer role/pointer later reads that origin's current canonical state; it never copies the incoming origin's packet into it.

Original GS lowering does not automatically supply this anchor. Do not assume spare task fields or an unproved stack scan. C04/C12 may explicitly select a versioned adapter/integration contract; the pinned two-word ABI is neither a target constraint nor permission for an unannounced compatibility change.

### 3.2 Grant identity and native object lifetime

An address is not an acquisition identity. For:

```text
lock(A)  -> A1
lock(B)  -> B1
unlock(A1)
lock(A)  -> A2
```

A1 can remain as a released tombstone while A2 is live. Active lookup must choose A2 and never reject it merely because retained A1 has the same address. Releasing A1 cannot later affect A2.

Identity must distinguish object destruction/reinitialization where the native API permits it. Choose a concrete source of object incarnation or a protocol eliminating all delayed object dereferences. A retained record does not pin the caller's lock container. Once native unlock permits destruction, delayed bookkeeping uses retained identity/endpoint data and must not touch freed/reused A.

For imported ancestors acquired before delegated entry, capture exact provenance or enforce an actionable pre-entry exclusion. A logical task flag is not an inventory of all native locks.

### 3.3 Reference topology

The arrows below are retained references, not simultaneous execution rights or separate allocations. Every W node/control points directly to W's core, with no packet-owning middle level; grant/ACK/image metadata adds no W packet. Control, grant and ACK/result information may be embedded or call-local under the table's lifetime conditions. This snapshot has C_B owning S_W and C_A suspended. The dotted V route depicts an alternative allowed origin switch, not concurrent execution. Only the current sequence holder may advance S_W.

```mermaid
flowchart LR
    W["Original W"] --> SW["Thread-owned S_W: one regs packet, cursor, phase and execution binding"]
    NA["A node N_A: no W packet"] -->|direct state| SW
    NB["B node N_B: no W packet"] -->|direct state| SW
    NC["C node N_C when reached: no W packet"] -->|direct state| SW
    EA["A call-local or embedded control: role, return route; no W packet"] -->|direct state| SW
    CA["C_A retained suspended reference"] --> SW
    CB["C_B current executor reference"] --> SW
    SW --> GR["Logical grant/ACK information and image references in chosen target storage"]
    CA -. "own origin state" .-> SCA["S_C_A: C_A's own source"]
    V["Other origin V"] --> SV["S_V: distinct canonical state"]
    CA -. "when serving V, switch active pointer" .-> SV
```

For W's A-to-B-to-C path, `N_A.state == N_B.state == N_C.state == &S_W` even when executors differ. For V's work, nodes directly reference S_V. No origin's packet is merged with another's, and saving the combiner role never snapshots W's running state.

### 3.4 Sequential ownership transfer

This proposed flow illustrates W -> C_A -> C_B -> C_A/W when proxy routes win, with optional local branches. Every S_W reference denotes the same target core. Sequence/grant/result labels are conceptual information in chosen fields or live call-local control, not required counters/objects. C11 chooses arbitration/ordering. Successful acquisitions are shown; failed/cancelled outcomes create no grant and retain exact result/lifetime duties.

An additional source lock C repeats the nested pattern with `N_C.state = &S_W`; the two storage/reference levels neither cap lock depth at two nor insert another packet-owning level.

```mermaid
flowchart TD
    W0["W owns S_W at sequence q"] --> PA["Export to S_W; freeze source; offer N_A.state = &S_W and next transfer sequence"]
    PA --> AA{"A selection plus S_W transfer"}
    AA -->|local winner| WA["W retains exclusive ownership; acquire A; local or origin combiner"]
    AA -->|proxy winner| CA0["C_A gains exclusive sequence ownership and actual A grant"]
    WA --> B0["A executor reaches source lock B; export into the same S_W; freeze source"]
    CA0 --> B0
    B0 --> PB["Offer N_B.state = &S_W and next transfer sequence; retain outer control"]
    PB --> AB{"B selection plus S_W transfer"}
    AB -->|local winner| LB["Current A executor owns S_W and acquires B"]
    AB -->|proxy winner| CB0["C_B gains exclusive sequence ownership and actual B grant"]
    LB --> BODY["Execute admitted B fragments; update the same S_W"]
    CB0 --> BODY
    BODY --> RET["Export current result to S_W; stop source; publish matching return sequence"]
    RET --> AR{"Serialized next-owner transfer"}
    AR -->|resume outer executor| CA1["C_A or W reacquires sequence; restore outer control; read current S_W"]
    AR -->|terminal suffix| W1["W reacquires sequence; exact native suffix from current S_W"]
```

Returning C_A acquire-observes B's completed current state in S_W. It restores only its outer lock-role control and admitted return binding. It does not reload a pre-B packet. If C_A must serve V during another allowed episode, it changes its active borrowed pointer under the same ownership/lifetime rules; C07 separately gates whether that scheduling is legal.

Retiring N_A, N_B or an execution relationship retires only that record's references. S_W reuse, incarnation change and task exit require every remote, grant/read-credit, source/image, return, notification and native-continuation reference to drain. Sequential invocation reuse cannot leave old nodes able to select a new S_W incarnation. Concrete storage, task-exit retention and synchronization remain C02/C11 mechanisms.

Reset/new invocation reuses S_W only after its chosen admission/last-user/reuse proof; it cannot clear live state. Task exit completes or retains duties before storage is freed. Nested source calls use S_W. Unsupported signal/IRQ/reentrant entry cannot allocate another W packet or steal ownership; use a valid pre-entry route/exclusion. General IRQ/NMI is unvalidated current support and unselected initial scope, not a permanent target ban; C10 must choose/prove any added lane.

## 4 Recursive acquisition inside lock functions

At any reached B acquisition, the JIT fragment has already ended with B pending. Lock code then chooses one supported route:

| Route | Meaning |
| --- | --- |
| Current task acquires B | C_A performs B's actual acquisition in a legal context, records the exact grant/result and resumes an admitted fragment with current state |
| C_A becomes B combiner | C_A saves outer combining state, obtains B's combining role, serves admissible work and executes W's B continuation |
| Another C_B selects child | C_A offers an optional child request, suspends source advancement and continues necessary wait/release handling; C_B exclusively selects and obtains B before running source |
| Origin continuation | A validated transfer gives W the current unfinished continuation and correctly routed live grants |
| Native from initial entry | Before delegated effects, decline an invocation whose later forward continuation cannot be supported |

Routes apply only to explicitly selected/admitted lanes. C_A-local selection of W's reader is still remote execution relative to W. Under the proposed origin-local initial policy, use a proved origin route or pre-effect restriction. C10 may select another placement only with concurrency/mode/API/context and continuation proof; this section neither permanently excludes nor enables remote readers.

An unavailable B image does not prevent B acquisition. Use a supported local/native continuation, never a wait for compilation. Executing arbitrary source natively on C_A is not a generic recovery engine; native execution on a non-origin task requires its own proven context/continuation contract.

### 4.1 Recursive helper sketch

**P:** this sketch uses the proposed structured call/control and conservative terminal-suffix outcome. C04/C06/C10 may instead select a separately proved resumable origin-service contract; no choice can replay effects or revive an invalid cursor automatically.

```text
lock-path helper reached_operation(active_state_ref, pending_operation):
    resolve original S_W through active execution relationship
    validate source-operation domain, operation identity and owner sequence
    validate operation phase and all live context obligations
    if pending_operation is acquire:
        choose family-specific optional arbitration route
        preserve outer combining state if roles nest
        if another combiner wins:
            suspend this execution relationship
            while child has not produced an outcome:
                handle required release/cancel/return messages
                wait or poll only as allowed by this context
            validate outcome identity, current phase and transfer sequence
            if exclusive terminal suffix ownership passed to W:
                retire this control path without resuming source
            otherwise reacquire current S_W sequence ownership
            consume the exact matching outcome from current S_W
        else:
            perform or finish acquisition exactly once
            record grant on success or exact API failure
    else if pending_operation is unlock or mode change:
        resolve exact acquisition and physical authority
        perform locally or route through retained lock-path endpoint
        acquire the promised result before advancing
    choose validated current-state fragment or terminal origin continuation
```

This sketch is documentation, not executable code. Start with bounded structured recursive lock calls and ordinary call-local outer control whose enclosing call remains alive through the child and required release/result handling. A bounded explicit stack or extra stable record is an option only when a concrete stack bound or escaping reference requires it. C05 must prove stack use and sleeping/atomic legality; recursion is not unbounded by default.

### 4.2 Return is an outcome, not an old snapshot

When B's operation or execution episode produces an outcome, choose an explicit outcome:

- **CONTINUE_FRAGMENT:** a validated current-state cursor and retained/admitted image, possibly back on C_A.
- **ACQUIRE_FAILED:** the exact return code and caller's failure branch, without an invented B grant or B body.
- **ORIGIN_SUFFIX:** exclusive native-suffix authority transfers to W; suspended ancestors lose their old JIT-resume rights.
- **CONTINUE_CHILD:** a still-live descendant/other grant determines the next valid execution route; releasing A does not require popping B.

The old A fragment ended when lock(B) was encountered. Returning from B does not authorize jumping into an unvalidated old A cursor. A retained A image can contain an admitted post-B fragment, but it reads B's resulting current state from the same S_W packet. No A/B packet restoration occurs.

**S:** materialize current state, close exclusive child execution/bindings and finish dependent producer accesses before a result permits reuse/resumption. Storage stays valid through its actual last user. **E, conditional migration:** a retained pop-based path keeps its detach/final-access discipline until replaced; the target need not use its pop/continuation array or exact mechanism. Structured calls/flags or another proved scheme can meet the same S obligations. A matching result permits exactly one resumption.

Only one child advances a source continuation at a time. No sibling fan-out is proposed.

## 5 Unlock and non-LIFO release

Every unlock ends the current fragment, regardless of which scope it releases. The lock's unlock helper resolves exact acquisition identity and API semantics.

**Illustrative remote-release protocol (P):** for `lock(A); lock(B); unlock(A); ...; unlock(B)` on C_B, when A's selected authority remains at another endpoint:

1. C_B finishes earlier protected writes and publishes release(A1) with exact identity and sequence.
2. A's physical authority acquire-observes that request and executes every backend/context operation promised by physical release.
3. Only after that release does it publish RELEASED. An acceptance ACK is a different message.
4. C_B acquire-observes RELEASED before treating A as released or advancing beyond the source unlock.
5. A's execution record can remain retained for return routing. With B still live, the lock code admits the next fragment under B or transfers a proven origin suffix.
6. unlock(B1) later ends its fragment and follows B's own authority.

The data chain is:

```text
C_B protected writes
  -> release request publication
  -> A authority acquire observation
  -> actual backend unlock
  -> next task's native/backend acquire
```

If W's B suffix waits for another task to acquire A and set a flag, retaining A until B completes introduces a deadlock absent from the source program. Combining policy must honor early actual release when the source requires it.

A scope ending is not a frame pop. A frame pop is not permission to reuse completion storage. A logical batch grant ending is not necessarily physical batch release, so the batch contract must explicitly enforce source-visible release/progress obligations.

### 5.1 Composite and owner-sensitive locks

**S:** every acquisition has unique, actionable grant/release/mode authority and correct context/order effects. Moving S_W does not itself transfer that authority. An adapter using an owner-sensitive native backend obeys that backend's actual restrictions. **P, C03:** a new backend may provide explicitly transferable authority, with a proved transfer point, old-authority revocation, progress and API/memory/context behavior. A logical owner label substitutes for neither proof.

For rwsem/rwlock preserve required reader concurrency, write exclusion, mode/API results and release/progress semantics. If the backend uses reader tokens, writer reservations, drain gates or an embedded mutex, account for its actual composite duties; releasing one part does not prove availability. The target need not copy those structures. Read credit is custody, not automatic permission for remote execution. Placement is C10; origin-local is only the conservative initial proposal.

Downgrade remains a separate target mode/lock-operation decision C10 with native API semantics and continuous write-to-read protection. Unlock/relock, indefinitely retaining write exclusion or merely relabelling it read mode is not generic equivalence. Target lock code handles the mode operation at its declared fragment boundary. The current test-specific proxy-downgrade exemption and retained writer gate are E only, recorded in [the newer receipt section](04_evidence_and_reconciliation.md#27-newer-proxy-downgrade-and-flags-stack-evidence); they neither override source-operation boundaries nor prove faithful native downgrade.

Trylock failure and interrupted acquisition create no successful grant. Temporary queue/reservation claims still need cleanup. Signalable APIs must observe W's intended signals/results rather than silently substituting C's signals.

## 6 Context legality and progress

For non-PREEMPT_RT spinlocks/rwlocks, preserve native atomic/preemption effects. Never sleep, allocate through a sleeping path or acquire a sleepable lock while any live spin/atomic obligation forbids it. IRQ/BH variants need separate local CPU effects and explicit admission.

Mutex/rwsem semantics alone do not disable preemption. Pinning or CPU-local reservation, if selected, adds constraints to prove. Sleepable control stays valid across allowed scheduling/migration; an unreserved per-CPU slot is not task-private. These S duties do not mandate current pinning, parking or pools.

At native handback, W needs the required native context guard while an applicable logical spin/rwlock grant remains live, even if its physical hold is elsewhere. In A-to-B then unlock(A), dropping A's pin must not make W preemptible while B still requires atomic context. Context tokens belong to the physical task/CPU that applied them; never restore remote IRQ state from the top frame.

Parents waiting for a child must handle required ancestor-release/cancellation/completion work. Same-task requests dispatch locally rather than waiting for themselves. Sleeping waits need predicate checks, registration and wake ordering that cannot lose an event. Atomic waits need every required participant to have a legal scheduling/CPU progress route.

**Proposed first nested scheduling rule:** do not run unrelated B source bodies while W's outer continuation is suspended waiting for its B episode to finish. Release/cancel servicing remains allowed; pre-existing owner/queue obligations are not bypassed. Otherwise an unrelated B body may wait for a flag W publishes immediately after B release, while the combiner delays W until that unrelated body returns. Broader batching requires a separate demonstrated progress proof.

This restriction alone is not a proof. Draw the wait-for graph including affinities, oversubscription, physical owners, retained grants and CPU reservations. Bounded metadata does not guarantee bounded native lock waits or scheduler fairness.

## 7 Ordering and retirement

| Edge | Producer obligation before release publication | Consumer obligation after acquire observation |
| --- | --- | --- |
| OFFERED/READY | Export into S_W, stop source and retain node/state/sequence | Validate the same state pointer and enter family/ownership arbitration |
| GRANTED | Actual acquire and exact grant initialization | Execute source only after grant/context validation |
| CHILD READY | Stop S_W source writes; retain the same state and bridge | Validate request/state sequence, select uniquely and acquire B before source advancement |
| RELEASE request | Complete preceding source effects; retain mailbox | Act through the exact physical authority |
| RELEASED ACK | Complete promised actual release and retiring accesses | Rely on release only for matching identity/sequence |
| Child result | Export into S_W; finish dependent accesses and close child binding, including detach/pop where used | Observe the valid result/return ordering, reacquire ownership and resume once from current S_W |
| Origin suffix transfer | Materialize the exact forward continuation; revoke old resume rights | W advances only after exclusive ownership transfer |

Use Linux ordering primitives with an LKMM argument even on x86_64. `volatile`, `READ_ONCE`, `WRITE_ONCE`, a wakeup or an arbitrary atomic counter alone does not supply the whole data/lifetime chain.

**P:** if a mailbox is chosen, start with one outstanding operation in target core/user/lock-local fields; synchronous return may supply the channel without an allocation. **S:** arbitrate any actual multiple producers and match requests/acquisitions/results under the chosen identity/order scheme. Numeric wrap/reuse rules apply if such fields are used. Rejecting a stale number cannot make an invalid pointer safe.

After a final ACK/DONE allows storage reuse, its producer cannot touch embedded wake state or payload. Finish notification before retirement, or retain independent notification storage.

Keep S_W, source/module, image, grant/read-credit, queue link, ticket, object and CPU pool lifetimes separate. Node dequeue, logical unlock, executor/frame completion and native return each retire only their own obligations. Closing source admission must leave admitted descendants and native suffixes a legal completion path; it cannot free S_W or custody still needed by a different executor.

## 8 Consolidated invariants

These retain audit identities and cover v0.6 topics under the current F/S/P authority rule, not every old mechanism/policy as a mandate. R15 marks the local-state preference P and its correctness proofs S; code/source lifetime and actual context duties remain requirements.

| ID | Target condition (F/S unless explicitly labelled P) |
| --- | --- |
| R01 | Protected source work runs only under the exact family/mode grant. A published request or queue reservation is not a grant. |
| R02 | One participant advances a logical continuation. Local selection, proxy selection, election and cancellation serialize through the lock's family protocol. |
| R03 | Publication offers optional execution. A legal local winner can execute itself or become combiner after closing the competing proxy route. |
| R04 | Every lock/unlock ends its fragment before the operation. The lock code performs the operation once and chooses the next current-state continuation. |
| R05 | No recovery replays completed effects, CALL stack transitions, acquisition or release. |
| R06 | Logical W and physical current/context remain distinct, including task/CPU-specific context restoration. |
| R07 | Release and mode change resolve exact acquisition/authority, including imported ancestors and A1/A2 reuse. |
| R08 | ACK meaning is explicit; promised early physical release precedes RELEASED. |
| R09 | Execution ancestry, live grants and source scope remain independent; referenced identities/bindings stay valid under the chosen storage/index scheme. |
| R10 | Final dependent access and child-binding closure precede a result permitting reuse/resumption; the selected storage/return mechanism stays valid through its actual last user. |
| R11 | Waiting parents service required work; no new wait/resource cycle or sleep-under-spin is introduced. |
| R12 | Failed/cancelled acquisition creates no successful grant; reader/writer and downgrade semantics remain exact. |
| R13 | Resources for completion/release/forward continuation are reserved before the effects that need them. |
| R14 | Source/image, object, request, queue, task/stack and CPU lifetimes have separate last users and retirement rules. |
| R15 | Prefer local ownership/direct references (P); shared routing is an open justified choice with complete lookup, identity, scaling, publication and lifetime proof (S). |
| R16 | Lookup protection, source admission, candidate/publication isolation and execution lifetime have separate correctness proofs. |
| R17 | Current execution does not depend on learning success. Source epoch, image generation and feedback revision differ. |
| R18 | Translated coverage is acknowledged separately from settled capability/boundary dispositions; later pending observations survive publication. |
| R19 | Every admitted boundary has an exact current-state recipe and independently valid code/return binding. |
| R20 | Unsupported lowering, origin-required operations, ordinary misses and invariant failures have different outcomes/retry rules. |
| R21 | Cross-task publication has complete data ordering, matching identity/order and final-access-before-reuse; numeric sequences are conditional mechanisms. |
| R22 | Support claims name API/context/route and actual evidence. AS01 assumes general flags/SIMD correct without extra handling; it is not equivalence evidence and does not waive special frontiers, actual context/authority/fault or last-user duties. |
| R23 | Each original W has exactly one thread-owned S_W/regs backing. All nested nodes/controls reference it directly and reserve no duplicate W packet, continuation or packet-sized owned/borrowed union; two storage levels do not cap nesting depth at two. |
| R24 | Family selection, state transfer and cancellation preserve exact scoped identity and exclusive execution ordering, with incarnation/sequence checks where needed; stale nodes cannot regain continuation authority. |
| R25 | The active-origin pointer resolves the served origin, not physical current. Exact source-operation context identifies nesting; internal bookkeeping never becomes W's source grant. |
| R26 | General family/API/mode/source/ABI identities determine dispatch. Every successful source lock operation has a generic post-operation admission path; native suffix is fallback, not full JIT completion. |
| R27 | Reader concurrency/mode/API/context semantics hold under C10's explicitly chosen placement; origin-local is an initial proposal and no unselected remote lane is authorized. |
| R28 | Application, local, fragment, native-handback and whole-root completion evidence is distinct; attribution requires actual exit cursor/reason and ownership phase. |
| R29 | Canonical-state and grant/read-credit custody can outlive executor/frame/node completion; reuse/task exit waits for all retained last users. |
