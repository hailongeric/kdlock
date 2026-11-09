# kdlock design reconciliation and evidence gates

**Status:** active design authority, reconciliation and validation boundaries
**Design basis:** revision 1.6
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
later. C02-C11 and remaining C01 policies stay open where the plan identifies a
choice. These scope approvals establish no validated support lane.
Keep one canonical S_W, optional unique selection, every source lock/unlock as
a pre-operation fragment boundary, serial recursive delegation, exact no-replay
handback and cumulative source-versioned learning with the original backend.

### 1.1 Assumption and target policy versus evidence

| Item | Target authority/scope | Evidence limit |
| --- | --- | --- |
| Ordinary trusted-source translatability | Original UB-derived backend; known special instructions clip only affected paths, preserving safe alternatives/joins | No universal instruction or kernel equivalence is established |
| AS01: general flags/SIMD | Assume correct for this iteration, without extra general capture, virtualization, shadow state or blanket admission gate | An explicit assumption, not a general equivalence result |
| PUSHFQ/POPFQ local exception | Temporary GPR and exactly one virtual-source push/pop, preserved live values and balanced physical-stack temporaries | The concrete lowering and covered POPFQ values/effects remain C04 work |
| Target downgrade | C10 chooses mode semantics with native API behavior and generic operation boundaries | A prior retained-writer/read-label mechanism is not a target boundary exception or concurrency proof |

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
It does not decode, recognize APIs, emit/execute instructions, perform runtime
CALL/RET effects, materialize S_W or hand back execution. Source/dependency
identity and lifetime remain future integration obligations.

The earlier intraprocedural implementation in `13f2630f` passed ten focused cases
with Python 3.10.12: each of the four boundary kinds with a safe shared join and
unchanged input, a cycle with repeated edges, two predecessors of a missing target, a known successor plus an
unresolved alternative, a missing entry, a boundary at entry and a supplied
scope end. These were in-memory helper checks with no decoder, generated code,
JIT/kernel execution or selected kernel configuration/API lane. They establish
only the exercised graph behavior, not exact handback or callee-return handling.
These checks preceded the user's clarification to finish overall functionality
before further behavioral testing. They have not been rerun on the CALL/RET
extension and do not validate it. The extension has source/static review only.
Further behavioral tests and suites are deferred until overall functionality is
complete.

T01-T56 remain unrun acceptance specifications. Source, build, live execution,
integration, retirement and performance evidence must be recorded separately
for each implemented lane and exact source/configuration. The helper's
provisional compiler records select none of the remaining kernel or adapter
mechanisms; the C12/C01 scope approvals are separate from validation.

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
| Proposal section 6 return invalid because A image was clipped at A's release | Generalized: any terminated fragment supplies no automatic post-operation reentry right; retained A state is not A protection |
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
| I05, I06, I19, I25 | R07, R08, R14: exact authority, physical-release ACK and A1/A2/object lifetime |
| I07, I11, I14 | R09, R10, R14: separate ancestry/grants, stable records and final-access retirement |
| I08, I10, I24 | R11, R13: progress and resource-reserved forward completion |
| I13 | R15: prefer local/direct ownership (P); any shared routing choice needs necessity, scaling, completeness, publication, identity and lifetime proof (S) |
| I15, I20, I23 | R16, R17, R19: retained code, binding, independent source epoch and generation |
| I16, I17, I18 | R17, R18, R20: independent current completion, exact coverage ACK and distinct exit outcomes |
| I21, I22 | R19, R21: exact boundary recipe and full cross-task data ordering |
| I12, I26 | R22: precise evidence, admission and deferred capability limits |

The old decision topics remain covered: D01 through D09 and D12 map to C01/C05/C07/C10 and the family/context plan; D02/D10/D11/D21 map to C02/C03; D13/D14/D19/D22 map to C09/C10; D15/D18 map to C08; D16/D17/D20 map to C04/C06 and the mailbox/continuation contract.

R23-R29 retain fixed core cardinality/direct references, generic continuation and exact attribution/lifetime duties. R27 now preserves reader semantics while making placement C10, correcting the earlier roadmap-derived mandate. R15 similarly distinguishes preferred local ownership from an absolute shared-index ban. C11 chooses synchronization and C12 now chooses integration/compatibility; neither reopens the fixed one-core/original-JIT model.

The acceptance register is T01 through T56. T01-T51 retain their audit identities and chosen-target scope. T52 adds special-path/bypass/shared-join behavior, T53 safe callee returns/caller fallthrough, T54 local temporary-GPR PUSHFQ/POPFQ effects under AS01, and T55 target downgrade versus the candidate-only exception. T56 adds the matched original-backend mapping comparison without a speed/AS01 validation claim. These remain unrun acceptance specifications; private graph-helper checks do not execute translated source or satisfy them.

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
| N07 | Exact authority equated with current physical-owner routing | S requires unique actionable authority; native owner constraints bind a retained adapter. Explicit transferable authority is an open P backend with revocation/order/context proof | C03, protocol section 5.1, T51 |
| N08 | Current pop/array/index/registry shape promoted to lifetime law | E mechanisms; S is exclusive binding, valid reference/lookup and final access before reuse. Local/direct ownership is preferred P; shared routing needs explicit justification, not an inherited ban | C02/C05, R09/R10/R15, T25 |
| N09 | Lease counters, completion subleases, session-only/image-count retention | E/P storage/reclamation choices. S is valid text/code/return/object lifetime through actual last use and nonstranding drain | C06/C09, JIT sections 2.3/5.3, T29/T30 |
| N10 | Five CALL edges, compatibility depth, 32 ledger rows and other budgets | Five-edge discovery is the explicitly approved current default P, not immutable F. Other capacities/encoding and any change to the default require a deliberate P choice with bounded completion | C08/C05, JIT sections 1.2/5.2, T24/T44 |
| N11 | One build/upload owner, fd staging, receipt encoding or daemon organization | E/candidate P solutions; S is candidate isolation, coherent publication, exact cumulative coverage acknowledgement and valid restart/reset | C08/C09, JIT section 5, T31-T37 |
| N12 | Current signal/reader/downgrade/IRQ/debug exclusions read as permanent bans | E support limits and P initial scope/extension choices; no new route/configuration is claimed. Linux 7.0 x86_64 non-PREEMPT_RT remains fixed F | C01/C10, support matrix/P7 |
| N13 | Terminal native suffix read as only possible architecture | Terminal suffix is conservative P; no replay/exact state is F/S. Resumable service/reentry requires an explicit new contract, never automatic old-cursor revival | C04/C06/C10, JIT section 4.3 |
| N14 | "Preserve current implementation first" made architectural | Native/API semantics and evidence history are S/E. Incremental migration and clean reimplementation are P delivery alternatives, with compatibility chosen explicitly | C01/C12, P0-P8 |
| N15 | Node-owned control treated as settled storage | Remains open P. Request lifetime, acquisition-slot lifetime and cache layout are audited only for the selected backend; no packet duplication or automatic frames/refcounts | C02/C05, node proposal/T48/T49 |
| N16 | Deferred/unproved general flags/SIMD text could become a new gate | AS01 is the user's explicit assumed-correct iteration scope, not evidence; no separate general subsystem/shadow/gate, with local PUSHFQ/POPFQ simulation the exception | JIT section 3.5, C04, T54 |
| N17 | Broad admission/frontier wording could reject a whole root | Ordinary trusted-source translation is target intent; recognized special instructions clip only affected paths. Keep safe alternatives/joins/returns and exact reached handback without replay | JIT section 1.3, T43/T52/T53 |
| N18 | Experimental typed proxy downgrade could weaken target boundaries/native semantics | Retained writer/admission and same-root exception are E only; target mode handling/native equivalence remain separate decisions. Stable point/merge does not prove a consumed branch or general flags correctness | Section 2.7, C10, T55 |
| N19 | Reserved packet-base versus resident logical R11 read as a settled optimization | Pinned mappings are E and C04 optimization candidates under one original backend. Compare remap/spill work versus boundary materialization/transfer with one canonical core, no per-user spare packet and no measured gain claim | JIT section 3.1.1, T56 |

## 4 TCLock guidance and limits

Borrow TCLock's lock-protocol idea: an outer combiner can become an inner
waiter/combiner and restore its outer combining state. Delegation, arbitration,
waiting, recursive combining and release remain parts of the lock. Do not
replace the original JIT with a native borrowed-stack engine or introduce a
separate execution worker architecture.

Request-node control and bounded call-local outer control remain C02/C05
choices. Source comparisons do not prove the target's retention, stack/resource
bounds, cache layout, native API behavior or progress. No comparison artifact's
semantic shortcut is an accepted Linux 7.0 contract.

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
- [Linux lock types](https://docs.kernel.org/locking/locktypes.html)

## 6 Baseline verification

The active tree contains the five design documents and minimal project
instructions. Legacy implementation, benchmark records, obsolete guides,
other-kernel source locations and deployment identifiers are absent. The
complete original design snapshot remains in preservation history; it is not
required content for this branch.

This baseline selects no additional family, ABI, grant/arbitration policy or
local PUSHFQ/POPFQ lowering. Document structure and local references can be
checked now. Implementation builds, runtime correctness, kernel integration,
retirement and performance checks remain unrun for the rebuilt lock.
