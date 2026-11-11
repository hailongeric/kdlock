# kdlock implementation plan and decisions

Current build/boot, native checks, the earlier construction failure/recovery and
later returned generated prefix are scoped in the [current evidence checkpoint](04_evidence_and_reconciliation.md#current-evidenced-checkpoint).
Design requirements below do not establish complete generated-body or support evidence.

The [fixed-image fixture](../../../tests/evidence/runtime-recursive-20261110/README.md)
now records protected JIT completion across two distinct physical combiners,
with exact current-state return and separate physical-release/final-retirement
records. Its native C epilogue, general progress, full auxiliary context bounds
and broader API/workload support remain outside that evidence.

**Status:** active plan for the independent rebuild

**Current implementation:** private source discovery/decoding/planning with
versioned indirect observations, original-backend assembly construction, MCS
mutex/release control, one canonical state, direct MCS state pointers,
task-owned auxiliary entry and exact RCU image/JIT/native-restore bridges.
Reviewed commit `ce423858` connects in source ordinary source macros/native
bootstrap, recursive episodes, existing-grant native unlock, final auxiliary-actor
cleanup and task progress. Setup composition (`57599619`), caller-established
source-epoch validation/retention (`a660342c`), copied-exit classification
(`c9b468ee`), artifact source-input/NULL-retirement support (`0c3ccb10`) and
image-provider ownership (`a23b82c1`) also have independently reviewed source.
Reviewed kernel source `5989fbbb` adds the preallocated coverage-miss fact pool,
code-independent producer/source retention and an exact publication/ACK bridge.
The reviewed host coordinator `af997cb6` composes cumulative merge with the actual
compiler pipeline and separately reconciles publication/ACK receipts.
Checkpoint `40ae39ce` implements cold task storage, retained original-stack words,
immutable-contract source snapshots/native holds and kernel archived-fact
settlement. `236c287a` and `80095bfb` connect fd control, execmem loading, the
GNU host image/session pipeline, managed fork/failure/exit lifecycle and actual
fsynced archive-to-SETTLED shutdown. `c6becf81` exports the exact source slot and
nullable baseline. The exact-target installer and focused-check source exist at
`97130fe4`; later exact target application, core/full builds, kernel2 boot,
limited native-local and managed fork/exit checks now have separate receipts.
The first live image construction failed before loading/publication and its
reserved session was recovered and ordinarily unloaded. `18c8f2e4` corrects that
single-root/global-entry mismatch with explicit shared-budget multi-entry
planning. Opt-in core packaging began at `a65016e3`; its initial source-only
status is historical. See the [current evidence checkpoint](04_evidence_and_reconciliation.md#current-evidenced-checkpoint).
Full auxiliary context/resource and recursive lifetime/progress proof remain
outstanding. Deployment values beyond the fixture and crash/restart
reconstruction beyond the session/archive workflow are not supplied. The fixed
image fixture now records protected JIT completion and actual two-combiner
recursion, with separate release/retirement events. General support and the
T01-T56 matrix remain unvalidated. Live3's early prefix and later exact
learning/ACK stages keep their separate receipts in the current checkpoint.

The plain-spin extension is connected in source through the same compiler,
task, image and request interfaces. Its atomic queue, release and native
resume paths have separate context and progress requirements. Exact target
build and live evidence are recorded separately in the current checkpoint.

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

Minimal bounded structured recursion, call-local control and lock-local ordering are starting P; the current private S_W implementation is not runtime equivalence evidence. A fresh core/node/backend/adapter is allowed. Extra records/refcounts need a concrete reason. The choices below require review; proposed defaults are not user acceptance or implementation authorization.

## 2 Mechanism decisions and status

The user approved C12 source-rebuilt integration with fresh private layouts and
C01 ordinary mutex lock/unlock in sleepable task context as the first lane.
The user subsequently selected the separate ordinary plain-spin extension.
No old binary lock/object-layout compatibility
is promised. The user subsequently selected C03 owner-retained out-of-order
outer-mutex unlock deferral, superseding the transferable-grant recommendation.
The user now selects C11 MCS queue and C04 retained KD physical-R11 canonical-
packet-base mapping. Their exact claim/lifetime and adapter/bridge details and
deployment storage/context integration and C10 extensions still need their own proof; no lane is
validated. The initial mutex lane now requires stable lock-object storage through
actual physical release and final backend object access, as section 2.2 records.

| ID | Decision | Current selection or proposed starting point | Evidence needed before enabling |
| --- | --- | --- | --- |
| C01 | Initial lanes, policy and delivery order | Independent source rebuild. Ordinary sleepable mutex first, followed by a separate ordinary task-context spin runtime. Both use MCS under C11 | Exact API/context, release and lifetime contracts, eligibility and progress limits. Signal/try/I/O, reader and IRQ/BH lanes remain outside this scope |
| C02 | Core/users, control placement and lookup | Active/nested requests use MCS node->state directly. Initial own core and task-owned auxiliary stack have one stable root header; no external registry or active-S_W task field | Prove root attach/private child reset/detach, explicit node/parent routing and exact last users. Managed provisioning/fork/exit have source at 80095bfb; deployment capacity and exact target lifecycle validation remain outstanding |
| C03 | Grant identity and release authority | TCLock-style deferred outer-mutex unlock retains the responsible physical outer combiner. Plain spin uses one grant per turn and exact synchronous owner-release acknowledgement | Distinct source request, owner handling, physical release and last use. Mutex also needs its deferred marker and unwind proof. Stable lock-object storage through final physical access and later independent control/code users remain required |
| C04 | Target entry/exit/materialization ABI and local flags-stack lowering | Selected: retain KD physical R11 as the one canonical-packet base, with logical R11 virtualized. R11 optimization discussion/T56 are deferred. Keep original UB/KD GS lowering, AS01 and temporary-GPR PUSHFQ/POPFQ exception | Implement/prove complete GPR/virtual-stack/cursor/results/entry/exit/reentry contracts and local push/pop effects under that mapping; old packet sizes/offsets are not selected by this choice. AS01 is not equivalence evidence |
| C05 | Recursive control, request storage and stack/resource bounds | Selected: task-owned preallocated persistent requests and auxiliary control for the unified ordinary local/proxy path; supported workload guarantees an available record for every need | Finite explicit caller capacity covers concurrent nested requests plus retained release/control, return, notification, image/binding and current-native-endpoint users, not only depth. Task attachment/resources supply the count; no deployment value or unbounded claim. Exhaustion is documentation-only, with no handler/recovery/local fallback or new special assertion. Exact reuse and full lifecycle proof remain work |
| C06 | Code/return binding across fragments | Selected with C09: RCU pointer replacement after active users drain; exact sleeping/pending/return/source users retain old code/metadata | No RCU read section across sleeping source; preserve already-admitted child completion and exact pending producer; grace period before retired lookup data is freed |
| C07 | Nested batching and progress | Initial implementation strategy (P), connected in source at ce423858: scan exact logical_open grants before root/recursive acquire publication; an older open grant sets the new locally won batch's whole-lifetime proxy-service limit to zero. Ready/offered requests remain eligible for an external combiner. Broader inner batching is unselected | Show removal of the extra unrelated-service wait cycle without changing authority; native-root nesting is not just frame.parent. Closed retained physical duties remain separate. No arbitrary deadlock freedom or timing/progress parity follows; analyze selected deferral, affinities, scheduling and resources |
| C08 | Discovery, capacities and cumulative learning | Selected: preallocated JIT-miss fact pool with finite explicit caller capacity sufficient for the supported workload; pending facts/translation alone do not disable new JIT/delegation. Five direct-CALL edges remain the approved discovery default, not immutable architecture; 32 rows is E | Exact site/target/transfer-phase/producer/source-version facts and required holds; cumulative valid same-version compiler input BEFORE build; recording/emission/actual publication/ACK distinct, uncovered/later facts stay pending. Kernel pool/producer and actual commit/ACK bridge (`5989fbbb`) and host cumulative coordinator (`af997cb6`) have reviewed source. Shutdown selects actual fsynced host archival/content receipts followed by kernel SETTLED after image/native/JIT drain, separate from coverage ACK; kernel API source is 40ae39ce and the actual fd/host archive/runtime workflow has source at 80095bfb. Exact slot/base export follows at c6becf81. No numeric capacity or unbounded claim; deployment, crash/restart reconstruction and all acceptance evidence remain outstanding |
| C09 | Source lifetime, code publication and reclamation | Selected: quiesced RCU replacement with exact active-user records and old-reader grace. Source epochs, artifact input maps and image-provider envelopes have reviewed source. Initial provider selects an explicit all-dependency immutable-text contract (module_get alone is no freeze); source snapshots/native holds have source at 40ae39ce. Provider/channel/executable/runtime and compiler/staging composition have source through c6becf81; exact target integration and execution require separate receipts | Coherent source/code/metadata validation, exact baseline/transaction identity, no stranded descendants, no premature free or false coverage ACK |
| C10 | Reader placement and API/context support scope | Keep initial placement/API proposals and explicit signalable/downgrade/IRQ/BH/NMI/debug extension choices; AS01 removes separate general flags/SIMD handling from this iteration. PREEMPT_RT stays outside the fixed target | Native concurrency/mode/API/context/fault duties and chosen placement proof; test-specific retained-writer downgrade is E only, not a boundary exception or native-equivalence proof |
| C11 | Family arbitration and W-state transfer | MCS queue for ordinary mutex and the separate plain-spin runtime. Optional proxy selection retains the one S_W under the C04 mapping | Claim/grant ordering, one executor and exact queue/request/control last users. Spin adds the candidate's off-queue owner drain before one rejoin. Mutex retains the responsible deferred owner |
| C12 | Integration and compatibility contract | Selected: source-rebuilt integration with fresh private layouts; no old binary lock/object-layout compatibility promise. API result/context/lifetime/exclusion/order duties remain; selected outer release timing changes establish no generic native timing/progress parity | Enumerate rebuilt callers/modules, source/adapter contracts, version transitions and integration evidence; fresh layouts do not choose C02/C04 or validate integration |

Exclusion, exact source effects, owner authority and last-user obligations remain mandatory. The explicit mutex outer-unlock selection supersedes earlier immediate-release requirements only for that route; it is not generic native timing/progress parity. Other mechanism choices cannot extend that exception. Copied grant information still cannot create another physical mutation authority.

### Prioritized choices for confirmation

C12 and the initial C01 lane are approved as recorded above. The remaining
items below track deployment/proof duties and later-lane choices; the selected
ordinary source path is connected through `c6becf81`.

1. **Selected C03/C11 — deferred owner handling and MCS arbitration.** Retain the responsible physical outer combiner, record exact out-of-order unlock phases, notify/unwind to it, continue its normal batch and record physical completion only after actual release. Implement/prove optional local/proxy/origin-combiner selection and MCS/request lifetimes; the queue choice is settled. Apply selected stable lock-object storage through actual physical release and preserve separate later control/notifier/code lifetimes; S_W ownership alone grants no physical release right.
2. **Selected C04 with C06 — target adapter and reentry.** Retain KD physical R11 as canonical-packet base and implement complete current-state entry/exit/materialization/reentry, including the temporary-GPR PUSHFQ/POPFQ exception. Exact adapter inputs and code/return binding still need implementation/proof; C06/C09 quiesced RCU replacement and exact active-user retention are selected; their managed source integration is present, while exact target integration and execution require separate receipts. R11 optimization/T56 are deferred, not an active confirmation question.
3. **C10 — reader and API/context lanes.** Origin-local readers are the conservative first lane; another placement may broaden execution choices but needs full concurrency/context proof. Confirm initial lanes and extension scope; current exclusions are not permanent rewrite bans or new support.
4. **Selected C08 with C09 — retained facts and publication.** Integrate the source-present preallocated finite caller-capacity feedback-fact pool and exact publication/ACK bridge under the supported-workload availability guarantee. Keep new JIT/delegation eligible while facts are pending or translation runs, subject to existing context/source/image checks. Merge valid same-version observations before building; preserve uncovered/later facts and publication-bound ACK. Actual fd transport/compiler/staging/runtime composition has source through `c6becf81`; crash/restart reconstruction beyond the session/archive workflow is not implemented. Nonobservations/uncovered misses remain pending normally; selected shutdown requires exact fsynced host archival and separate SETTLED after image/native/JIT drain. Kernel API is source-present at `40ae39ce`; actual host archive transport is source-connected at `80095bfb`, and capacity covers retained records. Five-edge discovery is the approved current default.
5. **C02/C05 with remaining C07 — request lookup, auxiliary control and progress.** Use direct MCS state pointers, task-owned auxiliary entry and preallocated persistent requests for normal local/proxy selection. The supported workload guarantees record availability within a finite explicit caller capacity covering every concurrently live/retained user. No deployment value is configured; exhaustion is documentation-only, not another implementation route. Ordinary native routing/recursive progress have source code at `ce423858`; cold task storage and native/stack holds now have source at `40ae39ce`; managed fork/failure/exit and task-exit drain have source at `80095bfb`, with target application/build and a bounded managed fork/exit case now recorded; full capacity/lifecycle proof remains outstanding.

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

The user selected TCLock-style out-of-order outer mutex unlock deferral. The responsible physical outer-combiner context/state remains retained; record the exact request and deferred marker, notify/unwind to that combiner, let it handle the marker and continue its normal batch, then physically release under its normal protocol. The earlier transferable-grant recommendation is superseded and unselected. C11 now separately selects MCS, superseding the one-guard/FIFO recommendation. Optional local/proxy/origin-combiner claim ordering, queue/request lifetimes and exact serialization details still need implementation/proof; neither choice selects TCLock's borrowed-stack execution.

Every source lock/unlock still terminates its fragment before the operation. The original UB JIT, KD GS lowering and one canonical S_W remain fixed. Returning to the owner restores only its combining control and uses current S_W, never a pre-child packet or old JIT cursor. Passing S_W neither transfers physical ownership nor performs unlock.

The private [release protocol](../../../kernel/mutex_release.c) and [header](../../../kernel/mutex_release.h) retain physical-owner context and a list of exact per-acquisition controls. Their phase progression is:

```text
HELD -> REQUESTED(route=OWNER) --------------------> OWNER_HANDLED
HELD -> REQUESTED(route=DEFERRED_OUTER) -> DEFERRED
     -> UNWIND_READY -> OWNER_HANDLED
OWNER_HANDLED -> PHYSICALLY_RELEASED -> RETIRED
```

The source request atomically publishes OWNER versus DEFERRED_OUTER with REQUESTED. The caller resolves the exact active execution relationship; same-task identity alone does not make an outer unlock normal. Owner handling accepts OWNER+REQUESTED or DEFERRED_OUTER+UNWIND_READY only, and deferral rejects OWNER. The helper does not advance source. The selected stable-object contract permits a correctly materialized post-unlock continuation without waiting solely for physical release/object lifetime; the private C04 bridge records exact source transitions and the managed source path is connected through `c6becf81`; exact target/runtime proof remains outstanding.

Source-request, source-return and notifier users are tracked exactly and gate retirement. At owner initialization, the caller has already acquired physical exclusion and binds its exact ordinary backend unlock callback/object. The owner-only finish validates all obligations as OWNER_HANDLED, closes the batch/binding and takes/clears that saved callback/object under its internal guard, invokes the bound synchronous complete ordinary unlock once outside the guard, then records PHYSICALLY_RELEASED on the obligations. Owner operations check the current task. Correct binding and callback code/object lifetime through its return remain caller obligations; the protocol performs no later object dereference. Deferred acceptance, unwind readiness and owner handling are not actual release; physical release alone is not proof that every remaining control/notification user has finished.

At the initial release-helper checkpoint, this limited C protocol had static review only. Later build and native-local lock/unlock execution are recorded separately; the scoped live source checkpoints are recorded centrally, while complete deferred/proxy correctness remains unvalidated. Its internal owner guard is not the separately selected C11 MCS claim/acquisition protocol. It implements no concrete physical exclusion backend, acquisition/queue, JIT adapter, task-core anchor or source-cursor advancement. It contains no register mapper or C02 task-core anchor; C04 KD packet-base mapping is selected separately. The helper alone establishes no complete ordinary-mutex lane or full behavioral proof.

Extra waiting is explicitly accepted for this route. It supersedes immediate outer-release obligations only for the selected mutex policy; it establishes no generic native release-timing or progress parity and creates no spin/rwlock/rwsem/downgrade exception. Source handshakes depending on outer-lock availability retain their stated progress limits, without introducing a new source-admission whitelist.

Logical source grants are distinct from the physical batch acquisition. A held batch can have multiple exact per-acquisition controls; each retains its own completion identity and last-user obligations.

The user selected stable lock-object storage through actual physical release for the initial mutex lane, including the complete backend unlock's final object access. The caller must establish that validity; a retained owner context does not itself pin its caller-owned lock container, and a source unlock/deferred marker does not permit destruction/reinitialization. Physical release also does not retire owner/control records, their containing allocation or exact source-request/return/notifier users: keep them through their actual last use. Retain callback provider/code through its return. Keep exact acquisition identity and last-object-access/reuse proof; no separate allocation per acquisition is implied. A correctly materialized post-unlock continuation need not wait solely for physical release/object lifetime. This is the selected continuation contract, not another pending resumption choice; the helper advances no source and the private C04 CALL/return/cursor bridge has source code, while ordinary native wrapping/recursive driving are connected in source at `ce423858` and managed provider/task lifecycle composition has source through `c6becf81`; exact target integration and execution require separate receipts.

See [the protocol's selected phase contract and pinned public mutex source](01_lock_protocol.md#5-unlock-and-non-lifo-release). Source integration must enforce the selected stable-object contract and separate control/notifier/code retention. C11 MCS queue and C04 KD physical-R11 mapping are selected. Their exact arbitration, lifetime and adapter/bridge contracts still need implementation/proof; other affected integration choices remain separate.

### 2.3 Selected next integration baselines (C11/C04)

| User selection | Required implementation/proof still outstanding |
| --- | --- |
| C11: MCS queue for the initial ordinary-mutex lane | Preserve optional local/proxy/origin-combiner exclusivity, actual grant ordering, selected deferred outer owner and exact queue/request/control last users. MCS membership is not source acquisition or permission to execute. The choice does not select old TCLock borrowed-stack execution, node pools, capacities, parking or broad batching |
| C04: retain KD physical R11 as canonical-packet base | Keep logical R11 virtualized and all users on the one S_W/packet; implement a consistent original-backend mapper/wrapper, current-state export and exact CALL/RET/virtual-stack bridges with KD GS lowering. Preserve AS01 and temporary-GPR PUSHFQ/POPFQ. Old packet offsets/private ABI are not implied; R11 optimization discussion and T56 are deferred |

These are selected user decisions, not validation results. Private MCS acquisition/selection, mapper/wrapper, canonical-state and operation bridges have source implementations. Reviewed commit `2c3f7cbc` connects exact request-pool users/reuse, task-root pool binding/detach, physical-task owner progress and JIT/wait callbacks. Reviewed commit `ce423858` additionally connects ordinary source macros/native bootstrap, serial recursive episodes, exact existing-grant native unlock, final auxiliary-actor cleanup and native task progress. Those private components are present and independently reviewed, followed by setup composition `57599619`, source epochs `a660342c`, copied feedback facts `c9b468ee`, artifact input/NULL-retirement support `0c3ccb10` and image-owner retention `a23b82c1`. Reviewed kernel source `5989fbbb` further implements coverage-miss recording, exact claims/incarnations and code-independent producer/source retention, plus the actual commit/ACK bridge; host coordinator `af997cb6` composes cumulative merge before compilation and reconciles exact publication/ACK receipts. Source checkpoint `40ae39ce` implements cold task storage, retained-stack callbacks, immutable-contract source snapshots/native holds and kernel archived-fact settlement. Managed fork/failure/exit, actual channel/compiler/executable-provider/runtime composition and archival receipt wiring have source at `236c287a` and `80095bfb`; `c6becf81` supplies exact exported slot/base identities. Full auxiliary context proof, general deployment inputs and crash/restart reconstruction remain outstanding. Packaging at `a65016e3` was initially source-only; exact target application/build/boot and bounded native/control results now have separate receipts. The earlier 12 focused host-pipeline checks remain tied to `c6becf81`; scoped protected completion and release/retirement now have evidence; general correctness/progress acceptance remains unvalidated. C12 source rebuilding promises no old lock-object or adapter binary layout; current source progress is detailed in the README and evidence file.

The remaining deployment choices supply exact immutable source/dependency, configuration/load/GS inputs, finite request/fact/cycle/image capacities and complete control-stack/context bounds. The cold allocator, managed fork/failure/exit hooks, provider/control/runtime bindings, GNU build/session transport and fsynced archive/settlement path are now source-connected through `c6becf81`; they are not absent mechanisms. The selected all-dependency immutable-text contract and distinct shutdown SETTLED are settled choices, not pending alternatives. Input/owner checks do not create a generic text-mutation freeze: the provider must actually satisfy that contract. No deployment values or new policies are selected here. Crash/restart reconstruction beyond the session/archive workflow is not implemented. The 12 focused VM checks passed, including host GNU assembly/linking. Exact target application/core/full build and bounded ordinary native/fork execution now have receipts. The fixed-image fixture now records recursive protected execution and separate release/retirement events. General progress, broader retirement checks and T01-T56 remain unvalidated. Additional API/context lanes remain separately scoped under C01/C10.

### 2.4 Direct MCS state, task-owned auxiliary entry and RCU replacement

The latest C02 correction keeps every active/nested request on its direct
node->state pointer. No external registry or redundant borrowed-S_W task field
is selected. Initial native entry uses one stable task-owned root/auxiliary
header containing the sole own core. The one-field/fork/failure/exit integration
artifact and exact-target installer remain unapplied; managed child and exit
implementations are present in `lifecycle.[ch]`.

C05 follows TCLock's task-owned auxiliary wait stack while retaining the UB
JIT/GS engine. Prepared source SP/IP/BP capture precedes the switch; source
publication follows it. Source stack, auxiliary control frames, persistent
node/endpoint backing and complete context/capacity proofs remain distinct.

C06/C09 now use quiesced RCU replacement. Exact linked execution, return and
source users retain sleeping/suspended dependencies; each pending exit has a
claimed use. Closing blocks new roots but permits retained admitted descendants.
Only after those users drain may the pointer change; old lookup readers then
pass a grace period. Source-epoch/input validation and code-owner envelopes now
have source; checkpoint `40ae39ce` additionally implements source snapshots and
complete native holds under the selected immutable-text contract. Actual
channel/compiler/executable-provider/runtime composition and fsynced archival
settlement have source at `236c287a` and `80095bfb`, with exact slot/base export
at `c6becf81`. Nonobservations/uncovered misses remain pending normally; shutdown
archives exact facts before distinct kernel SETTLED after image/native/JIT drain.
Execution and crash/restart reconstruction are separate outstanding work.

Nested source operations use the same recursive lock-request path. C05 uses
preallocated persistent requests for normal local/proxy selection. Explicit
finite caller capacity includes concurrent nested and still-retained physical,
release, return, notification, image/binding and native-endpoint records. The
supported workload guarantees availability for every need; no numeric deployment
value or unbounded claim follows. Exhaustion remains documentation-only, with no
handler, recovery/local fallback or new special assertion. Concrete task-time
allocation, managed fork/exit and provider wiring have source; actual deployment
counts beyond the fixture and full execution proof remain outstanding. Target
application/build/boot and bounded native/fork checks are recorded separately.
The private ordinary entry/recursive path is connected in source; its full
stack/context/last-user proof remains unvalidated beyond the scoped fixed-image fixture evidence.

### 2.5 Plain spin extension

The spin runtime admits the typed plain lock/unlock pair in IRQ-enabled
ordinary task context. It uses the existing task-owned auxiliary stack,
persistent request records and canonical S_W. W holds a preemption pin
through capture and wait, then resumes with the depth required by its open
spin grants. A last-unlock handback restores the original stack before
enabling preemption. Each physical executor remains pinned while advancing
borrowed source or polling on its behalf.

The source implementation gives a selected proxy the sole grant of its
physical MCS turn. The local candidate publishes the proxy's result, drains
any terminal foreign physical duties off the queue and rejoins once for its
own local turn. A foreign unlock polls its exact physical owner's release
acknowledgement before the source operation completes. Retiring the grant
and request requires the later control and reference checks. See
[plain spin context and progress](01_lock_protocol.md#61-plain-spin-context-and-progress).

The existing preallocated request-capacity contract applies. Atomic progress
requires a runnable CPU route for every necessary actor while other actors
remain pinned. Mixed families, IRQ/BH/NMI variants, trylocks, unrelated
preemption guards and RT/debug configurations are outside this lane.
Acceptance needs separate target evidence for pinning, native and JIT
continuations, exact owner release and retirement. Source review supplies
no scheduling, throughput or broader progress result.

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

Implement the [selected storage contract](01_lock_protocol.md#selected-task-owned-persistent-request-storage): task-owned preallocated persistent request records for the unified normal local/proxy path. Each simultaneously live request/control has distinct storage, and reuse follows every exact final user. The finite caller-supplied capacity covers concurrent nested requests and retained physical-owner/release, grant, return, notification, image/binding and current-native-endpoint records, not only depth. The supported workload guarantees an available record for every need; task attachment/resources supply the actual count and no deployment value or one-node sufficiency is configured here. Exhaustion is a documentation-only limitation, without a handler, recovery/local fallback or new special assertion. Keep the ordinary void API and no-replay contract. Prove actual provisioning, control lifetime, progress and layout within the supported bound. Future queue memberships still discharge their own selection/cancel/retirement duties. Pinning/waiting/admission/cache refinements remain separate proof duties.

A selected owner-sensitive or reused path must remain correct under its actual backend/context constraints until replaced. The clean target may choose a new authority, queue, layout or admission policy under C03/C11/C12; current hotness thresholds, waiter pinning and byte layouts are not design gates.

**Gate:** target local/proxy semantics, distinct acquisition identities, one-core layout and last-user validity. Behavior-neutral old-path steps are a possible migration strategy, not a condition of clean reimplementation.

### P2 Make every lock and unlock a JIT boundary

**Implemented subset:** [disassem/fragment.py](../../../disassem/fragment.py)
walks a finite, caller-classified source graph. It stops before typed source
lock/unlock/mode/special sites, retains safe alternatives and independently
reached joins, and distinguishes missing targets from unresolved alternatives.
Explicit ordinary matched direct/indirect CALL/RET records have distinct
call-target and return-summary relations. Source-versioned observed targets
accumulate without replacing mutable decoded operands or removing unknown
alternatives. A local least fixed point finds modeled boundary-free
routes to RET; each reached call retains its continuation only if its callee has
such a route. This is structural return reachability, not a runtime-return or
semantic nonreturning-function proof. Only known callee paths with modeled RET seed caller returns; changed return
targets remain outside this helper's matched-return input contract.

The private [decoder adapter](../../../disassem/source_decode.py) converts only
caller-supplied stable bytes and exact boundary metadata through the original
Miasm x86_64 decoder. It retains decoded bytes/site/length and represents direct
control flow without successor discovery. Decode failures and unmodeled
transfers remain separate maps: a missing planner edge to one of those sites
must not be attributed to ordinary coverage. It now retains complete Miasm
instruction/prefix metadata; mutating lowerers must copy those records first.

The [integrated compiler front end](../../../disassem/compiler.py) binds a finite
immutable source snapshot/version, exact site metadata, source discovery,
decoding and fragment planning. It validates overlapping source bytes, cuts
boundary paths, re-expands sites reached at shallower direct-CALL depth and
retains all source/decode/unmodeled/resource outcomes. Only the selected five
CALL-edge discovery bound has a default; decode sites, submitted decoder-window
bytes and CFG work limits are explicit caller inputs. The byte counter includes
overlapping windows and failed attempts, not unique source-cache bytes. Missing
source means zero available bytes; a partial/unsupported decode remains a decode
failure, not proof of invalid source or permanent capability. Runtime source
identity/lifetime and complete operation metadata remain caller duties. The
concrete source-provider/runtime bridge now has source through `c6becf81`.

The private lowerer now constructs original-backend assembly; state/JIT bridge
code records exact CALL/RET and native forward phases. These components have not
executed. Native entry/recursive driving is source-connected at `ce423858`; current kernel
source also connects miss recording and exact publication/ACK receipts. Live
compiler transport/provider/publication orchestration is connected in source through `c6becf81`; the focused host checks exercise construction/codec pieces without actual kernel transport or publication;
compiler records select no remaining open mechanism.
Ten checks on the earlier intraprocedural planner do not validate these
extensions. They have static review plus the later 12 focused VM host-pipeline checks;
decoder dependencies were imported for those checks, not kernel execution. This does not complete P2 or T07/T08/T52/T53; all T01-T56
remain unrun.

Implement semantic API recognition and typed pre-operation exits in the original backend. Stop fragment emission across every admitted lock/unlock, including inner or ancestor release. Keep reached-only execution and direct-CALL lookahead as separate concepts.

Map boundary state to C04's chosen target ABI and C12 compatibility scope. Prove declared inputs and complete current-state export/reentry without treating old MINIMAL entry as arbitrary capture. Lock code performs the operation once and uses a validated next fragment or exact origin route.

Provide body-independent current-state admission after acquisition/release/chosen mode change. Known unsupported special instructions stop only the affected path; preserve independent safe alternatives/joins, safe callee returns and caller fallthrough. A reached special frontier hands the exact first-unexecuted instruction/current S_W to native W; an untaken one causes no handback. Keep ordinary misses and finite resource limits separate, with no whole-region semantic whitelist or general flags/SIMD gate under AS01.

**Gate:** source effects, acquisition/release counts, CALL words, stack and operation results are once-only for both success and failure; a known lock target cannot be compiled away as ordinary learned code.

### P3 Implement optional root arbitration

Implement the selected target arbitration for local winner, proxy winner and origin-as-combiner. Test it through the declared public integration APIs; current family algorithms are candidate mechanisms, not prerequisites. Publication must not force transfer.

Root-local means W executes; nested-local can mean C_A continues W under S_W. Serving X switches to S_X under exclusive execution and restores the prior explicit current-node/parent-role control. Logical origin does not change; reader placement follows the explicitly selected C10 lane.

Provide a valid local/native route when delegation is unavailable/ineligible before effects; hotness thresholds are a policy choice. No source-body execution worker is required. Compiler/learning organization is C09 and does not become an independent execution architecture.

**Gate:** race tests show one source-body executor, one grant and correct cleanup/lifetime in each outcome.

### P4 Add serial recursive combining

Use the same lock implementation recursively: C_A saves outer combining state, handles B locally, becomes B combiner, or publishes an optional B child. Carry current-state continuation/entry bridges and retained parent/grant duties.

Assert `N_A.state == N_B.state == &S_W` across W -> C_A -> C_B -> C_A/W. Returning C_A reads the current S_W rather than restoring pre-B source state. Exact active relationship/operation context identifies nesting even when W is itself combiner; `current != W` and pointer equality are not substitutes.

Children can cross multiple fragments; each lock operation returns to lock code. Parent wait paths handle required release/cancel/completion events. Same-task nested operations use local handling, not mailbox self-wait.

The private source at `ce423858` implements the initial C07 optional-service strategy (P): under the exact current binding, scan S_W's `logical_open` grants before every root/recursive acquire publication. An older open grant fixes the new local batch's proxy-service limit at zero for the whole batch, including a native root B with older A despite no parent frame. Preserve the same ready/offer and external proxy-selection path. This removes the extra C_A-held-A/local-B/unrelated-X/wait-A scheduling cycle; it does not select another authority mechanism or prove arbitrary deadlock freedom, timing or progress parity. Closed retained physical/return/image duties and ordinary owner progress remain separate; broader inner batching stays unselected.

**Gate:** selected A/B/C routes, independent fragment bindings, current-state return and no lost event/self-wait. Preserve other routes' no-added-cycle duty and analyze selected outer-mutex waiting/availability limits separately. C01 chooses family order; no mandatory mutex-first/writer-first rollout is inferred from existing support.

### P5 Complete non-LIFO release and native continuation routing

Resolve every source unlock by exact acquisition and selected authority. For the chosen outer-mutex route, record source request/return, deferred marker, unwind readiness, owner handling, normal physical release and last use separately. Retain the responsible owner context through its actual duty; a marker is not physical completion. The prior transferable route is unselected.

Terminal handback propagates outward, revoking old JIT-resume rights while keeping physical release duties alive. Imported ancestors, object reuse and origin context guards must be actionable before enabling the relevant entry.

Retain S_W and grant/read-credit custody independently of a nonresponsible executor/frame. A responsible outer-mutex context stays retained through its deferred physical-release duty and exact users. Queue-node retirement does not free state or custody. The current owner validates delayed ACKs against the matching operation or retained grant transaction; completing old custody must never overwrite newer source state or discard a release duty.

**Gate:** observe the selected deferred phase sequence and responsible owner context through normal physical release, without assuming another task acquires A before B completes. Preserve exact acquisition identities and last users. Enforce stable object storage through actual physical release/final access and the longer control/notifier last users. Native suffix never revives old code or drops retained release duties.

### P6 Implement cumulative learning and coherent publication

Integrate the source-present C08 preallocated fact pool and exact commit/ACK bridge with finite explicit caller capacity sufficient for the supported workload. Retain exact source site/resolved target/transfer phase/producer/source-version facts and required lifetimes. Pending facts or translation alone do not disable new JIT/delegation; existing context/source/image checks remain. No numeric deployment count or unbounded-storage claim is supplied.

Cumulatively merge valid same-version observations into compiler input BEFORE candidate construction. Fact recording, graph attachment, actual emission, coherent publication and ACK are distinct: acknowledge only exact emitted coverage bound to the actual publication, and keep uncovered/later facts pending. Preserve deliberate boundaries/capability dispositions separately. Private C receipts (`5989fbbb`) distinguish actual commit from exact-subset ACK, and the host coordinator (`af997cb6`) retains finite cumulative input/receipt histories. The initial fd transport and serialized private staging/publication workflow have source through `c6becf81` under selected quiesced RCU replacement and exact-user reclamation. Parallel builders and crash/restart reconstruction are not implemented. Nonobservations and uncovered misses stay pending normally and are included in the capacity contract. Selected shutdown actually archives exact facts/provenance with fsync/content receipts before distinct kernel SETTLED after image/native/JIT drain; the kernel API has source at `40ae39ce`, and actual archive/runtime transport has source at `80095bfb`. No live code/metadata user may see an incomplete or incompatible update.

**Gate:** X then snapshot then Y then publication preserves Y, candidate coverage is checked rather than assumed, and active/saved references remain valid during replacement.

### P7 Enable additional families and modes one at a time

The plain-spin extension has source code under the scope in section 2.5.
Keep its atomic context and synchronous release evidence separate from
sleepable mutex deferral.

Select additional reader/writer, signalable, mode, mixed-family and context/configuration lanes under C01/C10. Origin-local readers are the conservative proposed initial lane, not a fixed rewrite restriction. Remote reader placement, debug/lockdep configurations and IRQ-related extensions remain unselected/unvalidated until explicitly scoped and proved; the current support exclusions do not permanently decide the target.

The explicitly selected ordinary-mutex outer-unlock deferral is the limited accepted policy, not generic Linux release-timing/progress parity. Do not copy TCLock's other historical killable shortcut, disabled downgrade, forced caller changes or borrowed-stack/task metadata as faithful Linux 7.0 semantics. Do not infer that one-CAS mutex-to-spin success proves contended mixed support.

**Gate:** the support matrix records each successful route; unsupported ones take a valid pre-effect local route or admitted exact suffix.

### P8 Qualify the complete lock

The user selected overall functionality before behavioral testing during the
source implementation stage. That historical order preserved the earlier ten
private planner checks without counting them as acceptance. The connected
ordinary source path subsequently entered authorized focused VM verification;
current results and failures are recorded separately in the evidence checkpoint.
Missing mechanism choices must still be resolved rather than filled in merely
to reach testing. Full suites require an explicit request.

Run the basic and directly affected static/unit checks, generated-code structural tests, memory-order/lifetime tests and real API workloads on the authorized test environment. Kernel/module execution follows the eventual checkout's AGENTS instructions; do not run builds or benchmarks on a host reserved for source work.

Only then compare cold learning, warmed/frozen execution and changed-target adaptation. Separate application completion, native/local body work, origin-as-combiner, per-fragment completion, exact handbacks and whole-root JIT returns. Retain actual exit reason/cursor and owner/operation phase before attributing a limit. Compare Linux Native and TCLock only with explicit release-policy/configuration and actual-path attribution. Selected mutex deferral must remain visible; it is not matched native release-timing/progress evidence. Real-world API tests use actual userspace system calls, native bodies and minimal lock routing/lifetime glue under the existing workload contract; fixtures remain mechanism evidence.

**Gate:** no correctness support claim is inferred from throughput, local fallback or an image merely being published.

## 4 Support matrix template

This is a target-lane matrix, not a current support claim. Required behavior is S; initial routes/scope are P. C12 separately defines source/binary/layout compatibility.

AS01 is a user-selected design assumption/scope, not a verified behavior row: general flags/SIMD need no separate handling now. The local PUSHFQ/POPFQ exception remains a concrete C04 lowering task; it introduces neither a general capture/shadow subsystem nor removal of selected special CPU-state frontiers.

| API/context lane | Required behavior (S) | Initial proposal (P) | Open choice / enabling evidence |
| --- | --- | --- | --- |
| Plain spinlock | Native atomicity/context and exact physical release | IRQ-enabled task-context spin runtime with preemption pins and preallocated persistent requests. Source present | Target execution and guard checks, synchronous release and final retirement, off-queue drain and scoped topology progress |
| rwlock/rwsem writers | Write exclusion, API result and interaction with readers | Choose initial family in C01 | C03 authority/composite contract; no inherited writer-first order |
| rwlock/rwsem readers | Concurrent reader/mode/API/context semantics | Origin-local on W | C10 placement; C_A-local is still remote relative to W; no remote lane authorized yet |
| Mutex | Sleepable ordinary API lane with exact owner/release/lifetime phases; selected outer-unlock deferral accepts extra waiting | Owner-retained deferred outer unlock and MCS queue selected; ordinary source/native bootstrap, recursive episodes and progress connected in source at ce423858; managed task/provider/compiler source connected through c6becf81; target build/boot and bounded native checks recorded, with kernel3 fixed-image protected recursion observed | Distinct marker/unwind/handling/physical release, retained owner and exact users. Stable object storage through actual physical release selected; separate later control/notifier/code retention remains required; no native timing/progress parity |
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
- T16 Distinguish each logical source acquisition and its exact referenced control from the held physical batch. Match source-return and physical-completion events to the correct acquisition; delayed completion cannot mutate a newer grant or permit premature record reuse. This acceptance specification has not run.
- T17 Enforce the selected stable lock-object storage through actual physical release and final backend object access. Only afterward can the object be destroyed/reinitialized, while independent acquisition bookkeeping may remain. If owner/control records share that containing allocation, it stays valid through their later exact source/return/notifier last users; callback code stays retained through its return. A marker or OWNER_HANDLED is not destruction permission, and no late object dereference/release touches the new object.
- T18 B acquired before delegated A then unlock(B) requested inside A; establish exact imported provenance and retained responsible B owner, then follow the selected deferred/normal release phases. Do not infer physical completion from the source request.
- T19 Native suffix from a descendant revokes old ancestor JIT-resume rights while responsible outer contexts and deferred physical-release duties remain retained. Later native unlock follows exact selected phases; no old source snapshot resumes.
- T20 Verify the initial C07 implementation strategy (P): root and recursive acquisitions scan exact logical_open grants before publication, including native-root B with older A and no parent frame. An older open grant fixes the whole locally won batch's proxy-service limit at zero; external B proxy selection remains eligible on the same request/ready path. Show removal of the extra unrelated-X service cycle while C_A holds A, without claiming arbitrary deadlock freedom or timing/progress parity. Treat logically closed retained physical duties and selected outer-mutex batch continuation separately; broader unrelated inner batching is unselected. This acceptance specification has not run.

### Context, lifetime and ordering

- T21 Sleep/migrate a legal parent and race child/release events through the chosen wait/notification protocol. Prove no lost event or invalid storage; include per-CPU reservation cases only if used.
- T22 Spin A/B non-LIFO release preserves the pin on W and each physical executor. Join the A request to the original owner's actual physical release and acknowledgement before source continues with B held. Check final unpin after original-stack restoration and keep release evidence distinct from control and request retirement.
- T23 Exercise allowed affinity/oversubscription and scheduling cycles; document exclusions rather than assume fairness.
- T24 Exercise exhaustion only for other selected bounded resources, such as independently bounded frames, grants, mailboxes, tickets, states or images, at their declared effect boundaries. Exclude persistent request-pool exhaustion: the supported-workload availability guarantee makes it a documentation-only limitation, without a handler/recovery scenario or new special assertion. A semantic field group does not require a separate pool, and nested nodes still reference one S_W. This acceptance specification has not run.
- T25 Prove final dependent access, physical release duty and exact source-request/return/notifier last users precede retirement/reuse; deferred acceptance and source return alone permit neither. A retained pop-based migration lane obeys its real detach rule; a fresh target proves its selected equivalent mechanism.
- T26 Model OFFERED/GRANTED, child READY, source-unlock REQUESTED, DEFERRED, UNWIND_READY, OWNER_HANDLED, actual PHYSICALLY_RELEASED and final retirement/result data chains under LKMM; acceptance/handling cannot substitute for actual release.
- T27 Verify failed/cancelled read/write claims, concurrent readers, write exclusion and continuous downgrade under the selected C10 placement/API lane. Run origin-local as the proposed initial control; no unselected remote lane is implied.
- T28 Deliver signals to W and C independently; observe intended API result and one grant/cancellation winner.
- T29 Source close/mutation races build, commit, queued roots, children, native suffix and return/fixup users without stranding admitted work.

### Images and learning

- T30 Change A/B code versions while a child is suspended under the selected C06/C09 update/reclamation scheme. Keep code/return/source bindings valid, or wait for proved legal quiescence/rebinding without stranding the child; test the selected quiesced RCU replacement strategy.
- T31 Report X, build snapshot, report Y, publish only actual coverage of X; Y remains pending.
- T32 Snapshot X but fail to translate it; do not acknowledge false coverage. Track a lock boundary as a settled boundary, not translated-through code.
- T33 Within the selected finite feedback capacity/availability contract, retain duplicate and source-valid old-image facts with exact producer/version/phase identity; valid same-version observations accumulate before build. Pending facts or translation alone leave new JIT/delegation eligible under existing checks. Do not infer unbounded storage, emitted coverage or ACK; uncovered/later facts remain pending. This acceptance specification has not run.
- T34 Other selected compiler/codegen/image resource ENOSPC/backoff does not trigger impossible retry loops or reclaim live code. Feedback-pending/translation status is not a forced-local admission gate; the selected feedback capacity is an explicit supported-workload assumption. This acceptance specification has not run.
- T35 Test selected compiler/daemon restart/reset, if any, against cumulative source-valid coverage and live bindings. Reconstruct/preserve knowledge or execute the explicitly chosen coordinated reset; no daemon or counter format is required.
- T36 Cold, warm and new-target phases report actual local/proxy/handback work separately; no performance claim from local-only execution.
- T37 Race the selected candidate-build/publication/staging interface: bytes/metadata never mix and stale commit/abort affects only its candidate. If fd staging is retained, include independent and dup/fork-shared descriptions; another interface needs equivalent isolation tests.

### One canonical state and general replacement

- T38 Across W -> C_A -> C_B -> C_A/W, compare canonical state/packet addresses and the chosen scoped identities at every node/entry/return. Observe `N_A.state == N_B.state == &S_W`, current resident-value export and one source advancement; never restore a pre-B packet or substitute S_C_A.
- T39 Have one combiner serve distinct origins W and V, including origin-as-combiner W serving X. Observe distinct S_W/S_V/S_X, correct explicit current-node/parent-role routing and restoration, and no register/cursor mixing. Cover root-local W and nested-local C_A without changing logical origin.
- T40 Race local/proxy claims, transfer/return, stale linked nodes, cancellation and delayed grant ACKs at the relevant protocol phases. Only the matching current owner imports outcomes; stale nodes cannot regain authority or overwrite newer S_W state. Exercise reuse and any chosen counter-wrap checks while inspected references remain valid; no per-hop counter is assumed.
- T41 Use unrelated source bodies and matching API patterns to establish exact-phase routing after admitted acquire/unlock/mode operations, including deferred non-LIFO and last-grant cases. Observe one source operation, marker versus physical-release phase, and a validated post-unlock bridge that need not wait solely for physical release/object lifetime, or an explicit fallback. Preserve once-only current state, CALL/return/cursor effects, exclusive executor, remaining logical grants and physical duties. No marker alone advances source, and no body-specific dispatch or arbitrary unprotected remote suffix is implied.
- T42 Construct separate local-only, fragment-to-lock, capability-frontier, resource-boundary, native-suffix and whole-root-return cases. Check actual exit cursor/reason, owner/operation phase and the five completion categories; static frontier presence and application success cannot fill missing observations.
- T43 Exercise selected special CPU-state frontiers, including the recorded STD case, through reached and bypassed branches. Stop before the special instruction only on its path; preserve native context/ownership and prior effects. AS01 removes no deliberate frontier and requires no new general flags/SIMD subsystem or named string-helper model.
- T44 Reach the source/decode/CFG/image/control capacities selected for the target, with earlier effects. Record resource/limit/cursor and bounded forward completion without replay or impossible retry. Document chosen changes to defaults/bounds; current global constants are not frozen and application-specific exceptions remain excluded.
- T45 Retire only a nonresponsible child node/executor/frame while S_W and independent obligations remain. Retain each responsible outer-combiner context through its physical-release duty and exact request/return/notifier users. Observe custody, matching phase import and last-user drain before reset, incarnation reuse or task exit. Unsupported signal/IRQ/reentrant entry cannot allocate a second W packet or steal the active state.
- T46 Reach reader/downgrade boundaries while C_A executes W. Under the initial origin-local proposal, use an exact origin route or pre-effect restriction and never count C_A-local as W-local. If C10 later selects another placement, require its separate concurrency/mode/context/continuation receipts before enabling it.
- T47 Execute real source lock nesting whose helpers acquire internal queue/metadata locks. Observe one typed boundary/grant per source operation, no recursive interception of implementation bookkeeping, and correct active-origin lookup when physical current stays C while origins change.
- T48 Audit physical member/union layout, offsets, sizes and pool stride as depth grows from A through A/B/C to the admitted bound: W has one canonical regs backing in its thread core; every node/control points directly to it and reserves no unused full W packet, duplicate source continuation or packet-sized owned/borrowed union. Distinguish C_A's own origin core and required native register saves from W backing. Preserve per-lock owner authority, exact source/deferred/physical-release phases, one executor and exact continuation at every depth under the selected policy; infer no native release-timing parity. Record layout evidence without inferring measured memory savings; this acceptance specification has not run.
- T49 For selected task-owned persistent requests, race premature reuse against nested source request, deferral/unwind/owner handling, actual physical release, distinct acquisition identities, returns, cancellation, notification and handback; responsible owner and exact source-request/return/notifier last users finish before reuse. For a backend with OSQ/delegation, test both duties or its proved merged equivalent. Audit all concurrently live nested and non-free retained contexts through scheduling, including late physical-owner/release, control, return, notification, image/binding and current-native-endpoint users; depth alone is not the capacity bound. Verify normal local/proxy selection preserves the same persistent-control lifetime. Record the explicit caller capacity and supported-workload availability guarantee without adding an exhaustion scenario/handler or inferring an unbounded pool. Record offsets/alignment/stride and hot/cold accesses under the chosen integration contract; no mandatory topology, 64-byte layout or gain is implied.
- T50 Audit C12's integration/compatibility promise and C04's chosen ABI against actual rebuilt or binary consumers: declared API/context/lifetime effects including the explicit mutex deferral limit, object/module layout where promised, version transitions and complete valid-input/materialization/reentry; no generic native release-timing/progress parity. Neither source rebuild nor drop-in compatibility is silently assumed.
- T51 For selected C03 owner-retained outer-mutex deferral, race exact request/return/notifier users with atomic typed request-route publication, deferred publication, unwind readiness, route-checked owner handling, batch close/binding removal, invocation of the initially bound complete ordinary unlock outside the guard, physical completion and retirement. Observe responsible current-task checks, one actionable physical owner, distinct acquisition identities and no premature reuse. S_W movement neither transfers physical release authority nor completes release. The earlier transferable-grant proposal is unselected.
- T52 Use a conditional with a known special instruction and special-only suffix versus a safe alternative reaching a shared join. Inspect emission for no special/suffix through the frontier edge and retained safe/join code; run reached/bypassed cases with non-idempotent stores, grants and source stack effects. Only the reached special path hands exact first-unexecuted IP/current S_W to native W; no root/function rejection or replay. This specification has not run.
- T53 Place a special path and an ordinary safe return inside a callee. Preserve the safe RET and caller fallthrough; verify the terminated path invents no translated return, including the all-terminated-callee control. Check real source CALL/RET words and prior effects once across native handback; unknown ordinary targets and resource stops retain separate classifications. This specification has not run.
- T54 Test intermediate-GPR PUSHFQ/POPFQ lowering under the chosen mapper: force temporary/live-register conflicts and virtual R11-R15 spill/restore, verify one eight-byte source word/SP change per instruction and preserved values/cursor, and prove any physical-stack temporary sequence balanced. Include bypass/reached branch cases, following joins and selected special-boundary controls. State the locally covered POPFQ values/effects; add no second packet/general flags shadow and infer no arbitrary-bit or SIMD equivalence. This specification has not run.
- T55 For a selected target downgrade contract, require its mode-operation boundary and continuous native write-to-read API behavior independently of the experimental retained-writer proxy. A read-only logical label with physical writer/admission retained is not generic equivalence; neither returned-root counters nor an unobserved consumed branch establish it. This specification has not run.
- T56 Deferred future work, unrun: if R11 optimization discussion is deliberately reopened later, compare retained KD shared-packet-base and original-UB-style resident-R11/wrapper-backed mappings under the same original backend, matched source/admitted ABI-state semantics, workload, code generation and nesting/miss/handoff frequency. Current C04 retains physical R11 as canonical-packet base; T56 is not an active mapping choice or a gate on implementing that baseline. Account for remap/spill/reload work versus transfer/materialization, code size and memory/cache behavior; verify one canonical core and actual local/fragment/handback/root completion before any throughput claim. Working saves are not extra canonical states. This comparison has not run and validates neither AS01 nor general flags/SIMD equivalence.

## 6 Completion criteria

Each implemented lane can be enabled and claimed supported only when it has:

1. Concrete record/field mapping for the one S_W and its referring nodes, with sole packet mutation authority.
2. Exact selection and operation linearization points.
3. Validated entry/exit and first-unexecuted continuation recipes.
4. Lifetime, ordering, resource and progress arguments.
5. Generated-code and real-API receipts for that exact route.
6. Explicit unsupported cases and safe admission/fallback behavior.

This documentation set is a coherent basis for that process. It does not claim these gates have passed.
