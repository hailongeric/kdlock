# kdlock design reconciliation and evidence gates

**Status:** active design authority, reconciliation and validation boundaries
**Design basis:** revision 1.8, selected stable mutex-object lifetime through physical release
**Target:** Linux kernel 7.0, x86_64, non-PREEMPT_RT

## 1 Active authority and scope

Use the [F/S/P/E authority rule](00_overview.md#authority-and-statement-origins).
Fixed user directions (F) and native semantic obligations (S) govern the target.
Proposed mechanisms (P) require an explicit selection and the corresponding
proofs. Existing source and prior experiment observations (E) do not select the
new architecture or establish support for the rebuilt lock.

The independent source-rebuilt C12 route is selected, with fresh private layouts
and no old binary lock/object-layout compatibility promise. C01 starts with
ordinary mutex lock/unlock in sleepable task context; other families follow
later. C03 subsequently selects TCLock-style out-of-order outer-mutex unlock
deferral with responsible physical-owner context retained. The earlier
transferable-grant recommendation is superseded; C11 queue/arbitration and
remaining C02-C11/C01 choices stay open. These selections establish no validated
support lane or generic native release-timing/progress parity.
Keep one canonical S_W, optional unique selection, every source lock/unlock as
a pre-operation fragment boundary, serial recursive delegation, exact no-replay
handback and cumulative source-versioned learning with the original backend.

### 1.1 Assumption and target policy versus evidence

| Item | Target authority/scope | Evidence limit |
| --- | --- | --- |
| Ordinary trusted-source translatability | Original UB-derived backend; known special instructions clip only affected paths, preserving safe alternatives/joins | No universal instruction or kernel equivalence is established |
| AS01: general flags/SIMD | Assume correct for this iteration, without extra general capture, virtualization, shadow state or blanket admission gate | An explicit assumption, not a general equivalence result |
| PUSHFQ/POPFQ local exception | Temporary GPR and exactly one virtual-source push/pop, preserved live values and balanced physical-stack temporaries | The concrete lowering and covered POPFQ values/effects remain C04 work |
| Selected ordinary-mutex outer unlock | Exact source request and deferred marker, retained responsible outer combiner, notification/unwind and owner handling, normal batch then physical release | Extra waiting accepted; no generic native timing/progress parity. Initial mutex lock-object storage stays valid through actual physical release/final object access; owner/control/notifier last users and callback-code retention remain separate |
| Target downgrade | C10 chooses mode semantics with native API behavior and generic operation boundaries | A prior retained-writer/read-label mechanism is not a target boundary exception or concurrency proof; the mutex deferral choice creates no downgrade exception |

## 2 Evidence boundaries

### 2.1 Rebuild status

The first implementation is the private
[source-flow fragment planner](../../../disassem/fragment.py). Its caller supplies
a finite, stable, already classified graph. The pass cuts before typed
boundaries, retains safe alternatives/joins, terminates on cycles and reports
known missing targets separately from unresolved alternatives. The current
extension also represents ordinary matched direct CALL/RET explicitly. A local
least fixed point establishes modeled boundary-free routes to RET, then each
reached call retains its own continuation only if its callee has such a route.
Call-target and return-summary relations remain distinct from ordinary edges;
RET sites are not connected indiscriminately to callers.

This is static source-flow planning, not a runtime-return or semantic
nonreturning-function proof. Indirect calls and changed return targets are
outside this helper's input contract; it cannot detect misclassified inputs.
It does not recognize APIs, emit/execute instructions, perform runtime CALL/RET
effects, materialize S_W or hand back execution. Runtime source/dependency
identity and lifetime remain future integration obligations.

The private [supplied-byte decoder](../../../disassem/source_decode.py) uses the
original Miasm x86_64 decoder interface and relative-target arithmetic preserved
in `archive/before-main-20261109` at
`7ce7db54334960fe0d9db2c425c5c581cdedf4b0`, `disassem/reached_path.py`. It decodes
only the first instruction at each supplied site, preserves its exact bytes and
length, and accepts exact BoundaryKind metadata. It has no provider/source read,
successor discovery, instruction lowering or packet/register mapping. Decode
failures and unmodeled transfers remain separately attributable; absence from
its modeled graph alone is not an ordinary coverage miss. The decoder pins in
[disassem/requirements.txt](../../../disassem/requirements.txt) retain the
archived decoder dependency set; they have not been installed or imported.
The decoder also retains its actual Miasm instruction, including prefix and
method metadata consumed by the original backend. Archived `disassem/assist.py`
uses prefix-group/default-prefix metadata for LOCK/REP spelling; name/operands
alone are insufficient. These nested decoder objects are read-only by contract;
a mutating lowerer must take an independent instruction/expression copy.

The [integrated front end](../../../disassem/compiler.py) now connects a finite
immutable source snapshot/version to discovery, decoding and fragment planning.
It checks overlapping bytes and retains the complete supplied snapshot in its
result, without provider reads or runtime leases. Boundary sites end discovery;
minimum direct-CALL depth permits shallower rediscovery, while the final planner
retains caller continuation only with a modeled returning callee. No global
function/root refusal follows from a stopped path.

The only default is the selected five direct-CALL discovery edges. Decode-site,
submitted decoder-window-byte and CFG-work limits must be supplied by the caller.
Resource receipts retain kind, source edge/site, limit, consumption and required
quantity. Window bytes include overlaps and failed attempts; CFG work counts
popped edges, including redundant visits. These are not runtime nesting bounds,
unique source-cache bytes or per-invocation exit observations. Zero source bytes,
decode failure, unmodeled flow and resource boundaries remain distinct. Partial
or unsupported decoding is a decode failure with available bytes retained, not
proof of invalid source or a permanent capability frontier. The integrated
front end has source/static review only; no import, build, behavioral execution,
emitted-coverage acknowledgement or runtime handback is claimed.

The private [C mutex-release protocol](../../../kernel/mutex_release.c) and
[header](../../../kernel/mutex_release.h) retain physical-owner context and a
list of exact logical per-acquisition controls within a physical batch. Logical
A1/A2 grants do not inherently require separate physical acquisitions or a free
gate between them; concrete same-source reacquisition under deferred custody
remains unimplemented and needs progress/authority evidence. No A2
batching/arbitration policy is selected. The controls record HELD, REQUESTED, DEFERRED,
UNWIND_READY, OWNER_HANDLED, PHYSICALLY_RELEASED and RETIRED separately. Exact
source-request, return and notifier users gate retirement; owner operations
check the current task. REQUESTED atomically includes OWNER or DEFERRED_OUTER
from the caller's exact active relationship; task equality alone is insufficient
for a same-task outer unlock. Owner handling accepts OWNER+REQUESTED or
DEFERRED_OUTER+UNWIND_READY, and deferral rejects OWNER. The helper does not
advance source; its actual C04 continuation bridge remains unimplemented.

At owner initialization the caller, which has already acquired physical
exclusion, binds the exact ordinary backend unlock callback and object. The
owner-only finish operation validates every obligation as OWNER_HANDLED, closes
the batch/binding and takes/clears that saved callback/object under its internal
guard. It then invokes the bound synchronous complete ordinary unlock once
outside the guard and only afterward records PHYSICALLY_RELEASED for the
obligations. A marker, an owner-handled result or a callback selected only at
release time cannot stand for physical release. Correct callback binding and
callback code/object lifetime through its return remain caller obligations;
there is no later object dereference by the protocol.

This is a limited protocol implementation with static review only, not a
concrete physical mutex backend, acquisition/queue/arbitration, source adapter,
C04 register mapping, C02 task-core anchor or source-cursor advancement. Its
internal owner guard does not select C11 family arbitration. No callback or
physical release has executed. The initial mutex lane now requires stable
lock-object storage through actual physical release and final backend object
access. The caller establishes that validity; a retained context alone does not
pin its lock container. Owner/control storage and any containing allocation
remain valid through exact source/return/notifier last users after physical
release, and callback code stays retained through its return. This selects no
C11 arbitration or C04 mapping. The selected stable-object contract permits a
correctly materialized post-unlock continuation without waiting solely for
physical release/object lifetime; no further lifetime-related resumption choice
is pending. The actual C04 bridge remains unimplemented. It must preserve
once-only CALL/return/cursor effects, the exclusive executor, remaining logical
grants and pending physical duties; a marker alone authorizes no arbitrary
execution. Same-source reacquisition and availability-dependent handshakes
still need explicit
progress/authority evidence, not a new source-admission whitelist.

The earlier intraprocedural implementation in `13f2630f` passed ten focused cases
with Python 3.10.12: each of the four boundary kinds with a safe shared join and
unchanged input, a cycle with repeated edges, two predecessors of a missing target, a known successor plus an
unresolved alternative, a missing entry, a boundary at entry and a supplied
scope end. These were in-memory helper checks with no decoder, generated code,
JIT/kernel execution or selected kernel configuration/API lane. They establish
only the exercised graph behavior, not exact handback or callee-return handling.
These checks preceded the user's clarification to finish overall functionality
before further behavioral testing. They have not been rerun on the CALL/RET
extension and do not validate it, the supplied-byte decoder or integrated front
end. The compiler extensions and C protocol have source/static review only. No
decoder dependency/import check or behavioral execution has run. Further behavioral tests and suites are deferred until
overall functionality is complete.

T01-T56 remain unrun acceptance specifications. Source, build, live execution,
integration, retirement and performance evidence must be recorded separately
for each implemented lane and exact source/configuration. The compiler helpers'
provisional records select no remaining kernel or adapter mechanism. The
C12/C01/C03 selections and C protocol source are separate from validation; no
complete mutex lane is claimed.

### 2.2 Original backend

The original UB-derived JIT, software register virtualization and kdlock's
GS/current-task lowering remain fixed directions. The private adapter/layout,
packet-base register choice, source/return bindings and locally simulated
PUSHFQ/POPFQ sequence remain selected target contracts under C04/C06/C12.
Original source locations below are implementation references, not support
claims for an inherited runtime.

### 2.3 Optional selection

Publishing eligibility does not force remote execution. Local origin
acquisition, origin-as-combiner and remote selection must be exclusive under
the selected family's arbitration. Reusing an old queue or owner word is an
open mechanism choice, not a requirement inferred from prior code.

### 2.4 Synthetic mechanism limits

A synthetic generated-image fixture can demonstrate only its exercised
instruction, source-stack, call/return and state effects. It cannot substitute
for actual kernel concurrency, legal context, API behavior or application
system-call validation.

### 2.5 Recorded live diagnostic from the separate workstream

Prior application completion, drain or large JIT entry counts do not establish
whole-root JIT return, a consumed downgrade branch, generic post-operation
reentry or a performance gain. Static source-frontier candidates do not prove
a per-invocation exit cause. Future receipts must retain the actual exit
cursor/reason and ownership phase when attribution matters. Old deployment
logs and measurements are outside the active main tree.

### 2.6 Generic constraints and decisions

Pin source/configuration and the exact family/API/context lane. Distinguish
intentional lock-operation boundaries, permanent capability frontiers, ordinary
learning misses and compiler-resource limits. Current invocations must finish
correctly without relying on a future compilation. Observe grants, state/code
last users and final-access-before-reuse separately from application return.

### 2.7 Newer proxy-downgrade and flags-stack evidence

A previous experimental typed downgrade retained a physical writer gate while
labelling its tail logically read-only. That narrow candidate does not select
C10's target mode operation or prove native reader-admission/concurrency
semantics. It creates no exception to every-source-lock/unlock fragment
boundaries. Do not revive that mechanism by treating previous receipts as
architecture.

Neither focused fixtures, source merges nor whole-root returns establish
general flags/SIMD equivalence. AS01 remains an assumption. PUSHFQ/POPFQ local
simulation is a concrete target contract requiring C04 implementation and its
own affected checks.

## 3 Reconciliation of old specifications

| Prior content | New authoritative treatment |
| --- | --- |
| Proposal sections 1, 4, 7, 10 and 11.7: a JIT region runs to its own matching unlock | A protected scope still has an exact matching acquisition/release, but every encountered lock/unlock ends a fragment |
| v0.6 section 4.1 rules 3 through 4: inner unlock does not end an outer translated region | Superseded. Inner or ancestor unlock ends the current fragment before lock code performs it |
| Proposal section 3.2 RESUME_JIT and section 4 child return | A validated current-state next-fragment outcome, not automatic revival of an old whole-scope cursor |
| Proposal section 6 return invalid because A image was clipped at A's release | Any terminated fragment supplies no automatic reentry right. Retained A routing is not a usable source grant; selected deferred physical batch exclusion and release duty are tracked separately |
| Proposal section 11.7 separate nested entries/images | Retained, with several possible fragments per entry and explicit post-operation bridge |
| v0.6 section 4.1 five-edge direct-CALL lookahead | User-approved current default (P, selected), distinct from fragment termination/lock depth; not immutable architecture; compatibility mode/budgets are explicit C08 choices |
| Proposal section 7 and v0.6 section 5.1 exact suffix | Exact first-unexecuted current state/no replay is F/S. Terminal suffix is conservative P; explicitly proved resumable services/reentry remain open |
| Earlier runtime vocabulary | Functional helpers within kdlock lock/unlock/wait/combiner paths; no independent execution component |
| Delegation publication interpreted as forced assignment | Corrected to optional eligibility with one serialized local/proxy/election claim |
| Historical single latest-miss description | Historical only; later particular path already has bounded cumulative learning |
| Current mmap/provider contract proposed as entire architecture | Rejected as a scope conflation. This set specifies an independent complete lock design |
| Earlier invocation/continuation sketch could imply separate mutable states | Consolidated into exactly one S_W; all lock nodes and suspended controls reference its one packet/cursor/phase |
| Semantic frame/grant/completion vocabulary read as mandatory allocations | Target one-core/users with proposed bounded calls/local ordering; fresh layouts are allowed and current reuse is optional; extra machinery needs a concrete lifetime/resource reason |
| Shared `regs_ref` interpreted as proof of the physical split | Audit actual members/unions/pool stride: one regs backing in the thread core, direct referring users with no reserved duplicate packet; preserve required native saves and per-lock control |
| MCS scheduling-node ownership interpreted as full request lifetime | Node-owned control is an open proposal: prove reservation through return/grant/cancel/ACK/native users or retain escaping small control elsewhere; uncontended local acquisition need not create a node |
| "Local" interpreted only by physical caller | Root-local is W; nested-local can be C_A executing W. Reader placement is open C10; the origin-local initial proposal must not count C_A execution as W-local |
| Every-operation wording applied to lock implementation bookkeeping | Only source operations enter boundary/nesting dispatch. Internal queue/metadata locks retain physical obligations but create no W source grants |
| Correct post-release native suffix treated as complete JIT support | Generic post-operation fragment admission is a design requirement; terminal suffix remains fallback with a distinct completion classification |
| Observed mmap symptoms used to select a body-specific design | General family/API/mode, S_W, operation phase, source cursor/epoch and ABI contracts; no application-name dispatch or exceptions |
| Reader and writer routes grouped under remote extensions | Reader concurrency/mode/API semantics are S; roadmap placement is E/P, not fixed user direction. Confirm target placement and prove any selected remote lane before enabling it |

### 3.1 Invariant coverage

| Original v0.6 IDs | Consolidated requirement |
| --- | --- |
| I01, I02, I03 | R01 through R05: exact grant, one executor, optional unique claim, every-operation boundaries, no replay |
| I04, I09 | R06, R12: physical/logical context and exact mode/cancellation results |
| I05, I06, I19, I25 | R07, R08, R14: exact retained owner, source request/deferred/unwind/handling versus actual physical release, and A1/A2/object lifetime |
| I07, I11, I14 | R09, R10, R14: separate ancestry/grants, stable records and final-access retirement |
| I08, I10, I24 | R11, R13: progress and resource-reserved forward completion |
| I13 | R15: prefer local/direct ownership (P); any shared routing choice needs necessity, scaling, completeness, publication, identity and lifetime proof (S) |
| I15, I20, I23 | R16, R17, R19: retained code, binding, independent source epoch and generation |
| I16, I17, I18 | R17, R18, R20: independent current completion, exact coverage ACK and distinct exit outcomes |
| I21, I22 | R19, R21: exact boundary recipe and full cross-task data ordering |
| I12, I26 | R22: precise evidence, admission and deferred capability limits |

The old decision topics remain covered: D01 through D09 and D12 map to C01/C05/C07/C10 and the family/context plan; D02/D10/D11/D21 map to C02/C03; D13/D14/D19/D22 map to C09/C10; D15/D18 map to C08; D16/D17/D20 map to C04/C06 and the mailbox/continuation contract.

R23-R29 retain fixed core cardinality/direct references, generic continuation and exact attribution/lifetime duties. R27 now preserves reader semantics while making placement C10, correcting the earlier roadmap-derived mandate. R15 similarly distinguishes preferred local ownership from an absolute shared-index ban. C12 source rebuild and C03 retained-owner deferral are selected; C11 queue/arbitration remains open. Neither selection reopens the fixed one-core/original-JIT model. The mutex timing policy is the explicit limited exception to earlier immediate-release requirements.

The acceptance register is T01 through T56. T01-T51 retain their audit identities and chosen-target scope. T52 adds special-path/bypass/shared-join behavior, T53 safe callee returns/caller fallthrough, T54 local temporary-GPR PUSHFQ/POPFQ effects under AS01, and T55 target downgrade versus the candidate-only exception. T56 adds the matched original-backend mapping comparison without a speed/AS01 validation claim. These remain unrun acceptance specifications; private graph-helper checks and source/static review of compiler/C protocol code do not satisfy them. T15-T19, T25/T26, T41/T45/T48-T51 now attribute the selected deferred-release phases and lifetime limits rather than requiring early physical availability.

### 3.2 Authority audit and correction register

N IDs identify this normative-origin audit, distinct from the historical v0.6 A01-A41 register. "Corrected" means the audit changed the text's authority/classification, not that a mechanism was implemented or validated. Historical source observations remain E, not architecture or support claims; old numeric receipt records are outside the active main tree.

| ID | Reviewed coupling / origin | Current classification and correction | Decision / affected sections |
| --- | --- | --- | --- |
| N01 | Latest explicit target versus inherited architecture | F/S govern the target; source presence alone gives no mandate. Operational editing/testing rules remain in force | Overview authority rule; all five files |
| N02 | "Existing S_W/storage" implied a complete current core or mandatory reuse | F requires one thread-owned core and direct second-level users; fresh physical layout is allowed, current packet sharing is E | C02, protocol section 3, P1/T48 |
| N03 | Two-word args, 168 bytes/offsets, reserved registers, object size or entry offsets treated as fixed ABI | E unless deliberately selected. P chooses/version-controls target adapter and source-rebuilt versus binary/layout compatibility; complete capture/materialization and API effects remain S | C04/C12, JIT section 3, T12/T50 |
| N04 | Roadmap local-reader lane promoted to fixed direction | Placement is P; concurrency/mode/API/context are S. Origin-local is conservative initial P, with no unselected remote support | C10, R27, support matrix/T27/T46 |
| N05 | Current hotness, waiter pinning/parking, owner words, pool sizes and family order | E/P mechanism/rollout choices, not target invariants; prove selected eligibility/context/capacity/progress | C01/C02/C05/C11, P1/P3/P7 |
| N06 | OSQ plus delegation and separate links required everywhere | Conditional on a selected dual-membership backend. S requires every selection/cancel/progress/retirement duty; a merged/different protocol needs equivalent proof | C11, node proposal/P1/T49 |
| N07 | Exact authority equated with an inherited backend or implicit S_W grant transfer | C03 now selects retained responsible physical outer-combiner context for deferred mutex unlocks; the transferable proposal is superseded. Exact source/deferred/physical phases and owner checks remain required | C03, protocol section 5, T15/T51 |
| N08 | Current pop/array/index/registry shape promoted to lifetime law | E mechanisms; S is exclusive binding, valid reference/lookup and final access before reuse. Local/direct ownership is preferred P; shared routing needs explicit justification, not an inherited ban | C02/C05, R09/R10/R15, T25 |
| N09 | Lease counters, completion subleases, session-only/image-count retention | E/P storage/reclamation choices. S is valid text/code/return/object lifetime through actual last use and nonstranding drain | C06/C09, JIT sections 2.3/5.3, T29/T30 |
| N10 | Five CALL edges, compatibility depth, 32 ledger rows and other budgets | Five-edge discovery is the explicitly approved current default P, not immutable F. Other capacities/encoding and any change to the default require a deliberate P choice with bounded completion | C08/C05, JIT sections 1.2/5.2, T24/T44 |
| N11 | One build/upload owner, fd staging, receipt encoding or daemon organization | E/candidate P solutions; S is candidate isolation, coherent publication, exact cumulative coverage acknowledgement and valid restart/reset | C08/C09, JIT section 5, T31-T37 |
| N12 | Current signal/reader/downgrade/IRQ/debug exclusions read as permanent bans | E support limits and P initial scope/extension choices; no new route/configuration is claimed. Linux 7.0 x86_64 non-PREEMPT_RT remains fixed F | C01/C10, support matrix/P7 |
| N13 | Terminal native suffix read as only possible architecture | Terminal suffix is conservative P; no replay/exact state is F/S. Resumable service/reentry requires an explicit new contract, never automatic old-cursor revival | C04/C06/C10, JIT section 4.3 |
| N14 | "Preserve current implementation first" made architectural | Declared API/context/lifetime duties and evidence classification remain; selected mutex deferral is an explicit limited timing policy, not native parity. Independent source rebuild/fresh layouts are selected | C01/C03/C12, P0-P8 |
| N15 | Node-owned control treated as settled storage | Remains open P. Request lifetime, acquisition-slot lifetime and cache layout are audited only for the selected backend; no packet duplication or automatic frames/refcounts | C02/C05, node proposal/T48/T49 |
| N16 | Deferred/unproved general flags/SIMD text could become a new gate | AS01 is the user's explicit assumed-correct iteration scope, not evidence; no separate general subsystem/shadow/gate, with local PUSHFQ/POPFQ simulation the exception | JIT section 3.5, C04, T54 |
| N17 | Broad admission/frontier wording could reject a whole root | Ordinary trusted-source translation is target intent; recognized special instructions clip only affected paths. Keep safe alternatives/joins/returns and exact reached handback without replay | JIT section 1.3, T43/T52/T53 |
| N18 | Experimental typed proxy downgrade could weaken target boundaries/native semantics | Retained writer/admission and same-root exception are E only; target mode handling/native equivalence remain separate decisions. Stable point/merge does not prove a consumed branch or general flags correctness | Section 2.7, C10, T55 |
| N19 | Reserved packet-base versus resident logical R11 read as a settled optimization | Pinned mappings are E and C04 optimization candidates under one original backend. Compare remap/spill work versus boundary materialization/transfer with one canonical core, no per-user spare packet and no measured gain claim | JIT section 3.1.1, T56 |
| N20 | Immediate outer physical release treated as unconditional | Latest user selection supersedes it only for ordinary-mutex out-of-order outer unlock: retain responsible combiner, defer/notify/unwind, handle and continue normal batch/release. Extra waiting is accepted without generic native timing/progress parity | Protocol section 5, P5, T15/T51 |
| N21 | Retained context or source unlock marker treated as lock-object lifetime | Initial mutex lane now requires stable lock-object storage through actual physical release/final access. Caller establishes validity; owner/control allocations and exact source/return/notifier users can outlive release, and callback code stays through return. Same-source reacquisition/handshakes remain unresolved progress/authority issues | Protocol section 3.2/5, C03, T16/T17 |

## 4 TCLock guidance and limits

Borrow TCLock's lock-protocol idea: an outer combiner can become an inner
waiter/combiner and restore its outer combining state. Delegation, arbitration,
waiting, recursive combining and release remain parts of the lock. Do not
replace the original JIT with a native borrowed-stack engine or introduce a
separate execution worker architecture.

Request-node control and bounded call-local outer control remain C02/C05
choices. Source comparisons do not prove the target's retention, stack/resource
bounds, cache layout, native API behavior or progress. The explicit user-selected
ordinary-mutex outer-unlock deferral is the limited accepted policy; comparison
source alone selects no other shortcut, borrowed-stack engine or kernel target.
The selection creates no spin/rwlock/rwsem/downgrade exception and proves no
generic native release-timing/progress parity.

## 5 Primary source map

### Original UB

Pinned commit: `1a5b98a06b058a7adce9805c8c6d061e2212f56a`.

- [Indirect target dispatch and miss stubs](https://github.com/glarer/UserspaceBypass/blob/1a5b98a06b058a7adce9805c8c6d061e2212f56a/source_codes/ub/zz_disassem/indirect_jump.py)
- [Original wrapper and state export](https://github.com/glarer/UserspaceBypass/blob/1a5b98a06b058a7adce9805c8c6d061e2212f56a/source_codes/ub/zz_daemon/asm/wrapper.S)
- [Feedback and recompilation loop](https://github.com/glarer/UserspaceBypass/blob/1a5b98a06b058a7adce9805c8c6d061e2212f56a/source_codes/ub/zz_daemon/main.c)
- [Register allocator](https://github.com/glarer/UserspaceBypass/blob/1a5b98a06b058a7adce9805c8c6d061e2212f56a/source_codes/ub/zz_disassem/conflict.py)
- [Historical packet/segment macros](https://github.com/glarer/UserspaceBypass/blob/1a5b98a06b058a7adce9805c8c6d061e2212f56a/source_codes/ub/zz_disassem/asm/asm_head.h)

### Original kdlock backend reference

Pinned source: `20fde062729703208ac54445f51fc0f21f24e0e8`.

- [Register allocator](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/disassem/conflict.py)
- [Source stack, CALL and local instruction lowering](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/disassem/special_inst.py)
- [GS and logical-task lowering](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/disassem/normal.py)
- [Private register packet](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/include/kd_regs.h) and [original wrapper](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/include/wrapper.S)

### Protocol references

- [TCLocks paper](https://www.usenix.org/system/files/osdi23-gupta.pdf)
- [Pinned TCLocks comparison source](https://github.com/rs3lab/TCLocks/tree/bbfb9f00a12af51dff6ca291cb9829a82960c2ef)
- [Selected public mutex out-of-order unlock path](https://github.com/rs3lab/TCLocks/blob/bbfb9f00a12af51dff6ca291cb9829a82960c2ef/src/kernel/linux-5.14.16/kernel/locking/mutex.c#L809-L855)
- [Selected public mutex inner completion reporting a deferred parent](https://github.com/rs3lab/TCLocks/blob/bbfb9f00a12af51dff6ca291cb9829a82960c2ef/src/kernel/linux-5.14.16/kernel/locking/mutex.c#L475-L491)
- [Selected public mutex outer handling with continued batching](https://github.com/rs3lab/TCLocks/blob/bbfb9f00a12af51dff6ca291cb9829a82960c2ef/src/kernel/linux-5.14.16/kernel/locking/mutex.c#L295-L333)

- [Linux lock types](https://docs.kernel.org/locking/locktypes.html)

The selected source references are the public `src/kernel/linux-5.14.16/kernel/locking/mutex.c` at `bbfb9f00a12af51dff6ca291cb9829a82960c2ef`, not the rcuht counterpart. The fetched file's SHA256 is `b7860666f3afe3b68c0b1f8696c9da0888321c34516bdf2fb16f3775ff226dce`. These are historical mechanism inputs, not another adaptation target or a validated Linux 7.0 implementation.

In that reference, the deferred value `7` keeps exclusion held; outer handling restores combiner value `3` and may serve more requests. [Batch exit](https://github.com/rs3lab/TCLocks/blob/bbfb9f00a12af51dff6ca291cb9829a82960c2ef/src/kernel/linux-5.14.16/kernel/locking/mutex.c#L400-L444) restores held value `1`, while [ordinary physical unlock](https://github.com/rs3lab/TCLocks/blob/bbfb9f00a12af51dff6ca291cb9829a82960c2ef/src/kernel/linux-5.14.16/kernel/locking/mutex.c#L819-L821) clears it. Neither deferred acceptance nor leaving the combiner role is physical release. The new C callback contract therefore requires the complete actual backend unlock, not merely batch-role exit.

## 6 Baseline verification

The active tree contains the five design documents, project instructions,
integrated source-discovery/decoder/planner code and the private retained-owner
C release protocol. No legacy implementation, receipt documents or datasets
need be restored. The complete original design snapshot remains in preservation history;
historical source links do not select another kernel target.

C12 source rebuild, the ordinary-mutex C01 lane and C03 retained-owner outer
unlock deferral and stable lock-object storage through actual physical release
are selected. C11 queue/arbitration, C02 placement, C04 mapping and other affected
mechanisms remain open. Separate owner/control allocations, exact
source/return/notifier users and callback-code retention keep their own last-use
requirements after physical release.
The C release protocol has source/static review only; its bound unlock callback
has not executed and no concrete backend, queue or JIT/source adapter is
implemented. Builds, runtime correctness, kernel integration, retirement and
performance checks remain unrun. T01-T56 remain unrun; the older ten helper
checks remain tied only to `13f2630f`. Further behavioral testing is deferred
until overall functionality is complete, which is not claimed here.
