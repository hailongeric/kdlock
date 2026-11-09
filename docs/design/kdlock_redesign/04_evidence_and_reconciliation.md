# kdlock evidence and reconciliation

**Status:** source and design provenance for the documentation set  
**Original review date:** 9 November 2026  
**Clarification revision:** 1.6, path-specific special frontiers and assumed general flags/SIMD
**Important distinction:** source mechanisms, candidate tests and proposed complete-redesign behavior are separate evidence levels

## 1 Input documents

| Input | Retrieved identity | Role in this set |
| --- | --- | --- |
| `kdlock_nested_delegation_proposal.md` | Revision 1.2, modified 6 November 2026, 50,305 bytes | Recursive combining structure, stable grant/continuation records, release routing, original-backend ABI and separate nested images |
| `kdlock_mixed_nesting_design_v0_6.md` | Revision 0.6, modified 6 November 2026, 80,769 bytes | Invariants I01 through I26, decisions D01 through D22, audit A01 through A41, source/image/feedback and lifetime/progress requirements |
| Initial integrated user direction | 9 November 2026 conversation | Whole kdlock redesign independent of mmap1; every lock and unlock ends current JIT; helpers called runtime are part of the lock, like TCLock |
| Established clarification for revision 1.1 | Documentation-edit handoff to this session | One S_W per original W with synchronized shared-pointer ownership; general native-legal lock replacement; source/internal lock distinction; generic post-operation admission and truthful exit attribution |
| Minimal mechanism clarification for revision 1.2 | Focused documentation handoff | Existing state/queue storage, bounded recursive calls and lock-local ordering first; extra records/stacks/refcounts only for a demonstrated need, while all semantic obligations remain |
| Physical layout clarification for revision 1.3 | Focused documentation handoff and supplied pinned-source facts | One thread-owned core/regs backing; referring nodes/control have direct core pointers and no reserved duplicate W packets; two storage levels do not limit nesting to two locks |
| Node-control proposal for revision 1.4 | Focused audit handoff and supplied pinned-source evidence | Evaluate control in a request-lifetime node, distinct from an acquisition-only slot; retention, capacity and cache placement remain open; no mandatory node/capture on the uncontended local route |
| Historical roadmap reader lane (E/P) | [Project roadmap](../../ROADMAP.md#stage-1-establish-the-mechanism-and-performance-envelope), as interpreted in revisions 1.1-1.4 | Origin-local readers were treated as fixed in those revisions. Revision 1.5 corrects that classification: target placement is open C10, with concurrency/mode/API semantics required and no implicit remote authorization |
| Target-authority clarification for revision 1.5 | Latest rewrite/audit directive | F/S govern the target; mechanisms are explicit P choices and existing code is E. Five-edge discovery is the current approved default; compatibility scope is open C12 |

| JIT policy clarification for revision 1.6 | Latest explicit design direction | Ordinary-source translatability intent; path-only known-special cuts with reached-only native handback; general flags/SIMD assumed correct without extra handling, except local temporary-GPR PUSHFQ/POPFQ simulation |
| Prior TCLock discussion | [Analyze TCLock Lock Nesting](https://chatgpt.com/c/6ae844fe-73fc-83ea-8eb1-7bf68dd9ce14?messageId=98f293a1-8785-51ac-98e2-484ec8ae53cd) | Earlier source-grounded comparison and integration limitations |

The actual retrieved v0.6 filename uses `v0_6`; references to `v0.6` in the request denote that document. Initial integration recorded reading both inputs in full without overwriting them. Those audit/source records remain historical evidence. The current target follows the [F/S/P/E authority rule](00_overview.md#authority-and-statement-origins), not every normative sentence in an older input.

Sections 2, 4, 5 and prior revision entries in section 6 record E. Section 1.1 identifies a user-selected assumption separately from proof, and section 3's crosswalk/register distinguish target F/S from P. Latest corrections change no old receipt outcome or source file; operational rules still apply.

### 1.1 Assumption and target policy versus evidence

| Item | Authority/scope | Evidence limit |
| --- | --- | --- |
| Ordinary trusted-source translatability | Explicit target intent using the original backend; special frontiers clip only their affected paths | Not verified universal instruction or kernel equivalence; actual missing exact-forward-state contracts remain specific correctness issues |
| AS01: general flags/SIMD | User-selected assumption for this iteration: assume correct, with no extra general capture/virtualization/shadow handling or blanket admission gate | Not a factual equivalence claim. Earlier fixtures, source changes, merges and application returns do not prove comprehensive correctness |
| PUSHFQ/POPFQ local exception | Intermediate temporary GPR plus exactly one virtual-source push/pop under the chosen lowering; preserve live values and physical-stack balance | Concrete sequence and locally covered POPFQ values/effects need implementation/testing; no arbitrary-bit/general-flags proof or bypass of selected CPU-state frontiers |
| Target downgrade | Separate C10 mode/lock-operation decision with native API semantics and generic boundaries | The candidate-only proxy exemption/retained writer described in section 2.7 is E, not the target contract |

## 2 Existing versus proposed

### 2.1 Historical pinned kdlock source

`20fde062729703208ac54445f51fc0f21f24e0e8` is the pinned source used by the prior documents and earlier read-only ABI/source inspection.

It records historical mechanisms available for possible reuse, not target architecture:

- spin-to-spin local acquisition, outer combiner becoming inner combiner, and remote virtual child;
- remote early spin-ancestor release and exact request/ACK duties;
- local nested mutex handling, not proof of a general remote sleeping child;
- restricted mixed mutex-to-spin handling and specific prepared read/write exclusions;
- existing wrapper/register conventions and separate physical frame/grant counts;
- historical parent-entry child selection, which is not the final separate-entry requirement.

A source mechanism is not proof of the full combination, exact Linux 7 integration or performance.

The focused revision 1.2 read-only check in this exact project confirmed that `kd_spin_prepare_jit_node()` in `kernel_module/spin/nested.inc` at `20fde062729703208ac54445f51fc0f21f24e0e8` already sets `frame->regs_ref = regs` (line 36). Lines 10-12 explicitly describe sharing the logical packet without an intermediate context copy. That sharing is reuse evidence for the one-core goal; neither the `regs_ref` field nor the historical owner ledger dictates the target storage/index layout. This narrow source fact proves neither the complete one-state-per-thread design nor all mixed lock routes. [The minimal mechanism table](01_lock_protocol.md#minimal-starting-mechanism-versus-optional-extensions) separates the fixed semantic duties from optional storage/accounting.

The supplied verified source facts for revision 1.3 add the physical distinction: at that same commit, `include/kd_exec.h:120-121` declares both embedded `struct kd_regs regs` and `struct kd_regs *regs_ref` in `kd_exec_frame`, and the per-CPU context contains an array of those frames. Thus the child pointer sharing at `kernel_module/spin/nested.inc:36` alone does not prove the old structure stopped reserving per-frame packet space. This does not establish that every old embedded packet is unused on every route. The proposed thread-core/user split is not implemented here, and neither pointer aliasing nor this source declaration is a measured memory saving. No new source research or execution was needed for this clarification.

The supplied revision 1.4 source review at the same kdlock commit distinguishes scheduling from request lifetime: `include/kd_spinlock.h` describes reusable `kd_spin_node` storage pointing to longer-lived `kd_spin_continuation` state, with scheduling-node reuse separate from continuation/native users. `include/kd_mutex.h` describes independent abortable-MCS `kd_mutex_osq_node` membership in a reserved slot: delegation can remain published while native-spin membership comes/goes, and links/notifications must not alias. The current mutex node also deliberately separates polling from packet writes across cache lines. These describe actual constraints of a retained current path, not required target queues, links, layout or pinning; a newly selected backend needs equivalent semantic proofs and no duplicate W packets. See the pinned [spin node declarations](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/include/kd_spinlock.h) and [mutex membership/layout declarations](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/include/kd_mutex.h).

### 2.2 Later candidate inspection

On 8 November, read-only inspection found a clean candidate at:

- checkout `/tmp/kdlock-reached-path-translation`;
- branch `codex/kdscope5-provider-prep`;
- commit `ac0b5b8271f0d88fe3ce0a5b040868973dfa62cc`.

The inspection covered ABI/entry headers, image publication/learning code, indirect dispatch and relevant design/evidence files. It found existing bounded cumulative learning on the immutable mutex ABI2 retained-miss path: 32 non-evicting rows, base-generation/receipt acknowledgement and overflow reporting. It also found rejection of stale-image reports. This corrects the scope of older single-slot wording without claiming lossless or universal learning.

An intermediate read-only check on 9 November observed HEAD `367825106a474f95a44f9af83215714e65a8767f` with ongoing dirty changes. The then-final read-only check observed clean HEAD `04325fcf658aa42b1d707f3b1a44870cc737afa0`, with the release-boundary source recorded as `40edde00525b71207246bbde4935767cbcb21fb7`. These are receipts from the separate mmap1 workstream, not a baseline implementation of this complete redesign. No files in that checkout were edited by this documentation task. The later receipt inspection for revision 1.1 is recorded in section 2.5.

### 2.3 Optional publication already exists on an ordinary path

Current implementation review distinguishes two paths:

- **Ordinary KD mutex:** publication is eligibility-only. The same wait lock serializes mutually exclusive local and proxy selection. The origin can acquire, serve others as combiner, then execute its own body.
- **Specialized retained-service mmap roots:** these are excluded from the ordinary origin election. Physical admission can precede capture/transfer to a dedicated retained-service path. That specialized restriction is not a property of all kdlock.

Optional publication/unique selection is F because the user selected it, not because the ordinary path implements it. That wait lock and specialized roots are E; target C11 can choose another arbitration while keeping optional local/proxy/origin-combiner behavior and lock-integrated execution.

The separate mmap1 source commit `40edde00525b71207246bbde4935767cbcb21fb7` implements recognized release-boundary source cutoffs and performs the actual release once, followed by exact native continuation when owners/read credit remain. Its verified receipt at `bench/results/10.176.26.71/tests/release-units-40edde00-20261109/README.md` reports six focused VM drivers passing and a matching 128-image kdscope5 provider build. The build retains eleven warning lines; component fixtures supply scheduler/task primitives, so this is not live kernel concurrency evidence. At that focused-check receipt the patch had not been loaded or measured; section 2.5 records later live execution, without performance qualification. It does not implement acquire boundaries, separate nested JIT images, JIT-to-JIT resumption or retained-root origin election. The later any-lock redesign requirement is not silently assigned to that task.

### 2.4 Narrow synthetic JIT evidence

The inspected evidence file was:

`bench/results/10.176.26.71/tests/munmap-tail-e5c73eff-20261108/README.md`

It records a joined synthetic generated image covering outer CALL, learned JMP through RDX, callback inner CALL, inner RET, shared RET and outer continuation. The corrected fixture observed effects once, source CALL words and SP checks; its negative control missed the shared RET. The cited test-only source commit was `035546aa79409e9eaa95488e178f2acf6ff389ba`, production base `e5c73eff`; ac0b5b8 records the evidence.

This was one synthetic test on the normal-boot VM. It did not exercise a provider/device/live kernel source, kernel installation, mmap1 or performance. A narrow flags fixture is not proof of general incoming flags/SIMD support. No new execution tests were run for this documentation set.

### 2.5 Recorded live diagnostic from the separate workstream

Read-only inspection for revision 1.1 found `/tmp/kdlock-reached-path-translation` clean on branch `codex/release-unit-boundaries` at receipt commit `69fcfaa52593b12543713abe70ca8f9107b5dadd`. The inspected files are `bench/results/10.176.26.71/tests/release-live-40edde00-v1/README.md` and `receipt.json` in that commit, available in the inspected checkout as [README](/tmp/kdlock-reached-path-translation/bench/results/10.176.26.71/tests/release-live-40edde00-v1/README.md) and [receipt.json](/tmp/kdlock-reached-path-translation/bench/results/10.176.26.71/tests/release-live-40edde00-v1/receipt.json). The JSON SHA256 is `4e3354ee437a10330e6178e81ecd3dcc9ecf121ffd83bcfcc831a22f393bc563`. These paths are evidence locations, not new implementation components.

A later check observed concurrent source/test edits in that separate worktree at the same HEAD. Both inspected receipt files still matched `69fcfaa52593b12543713abe70ca8f9107b5dadd` byte for byte. This revision leaves those edits untouched and makes no source-support claim about the later dirty state.

The receipt records tested source `40edde00525b71207246bbde4935767cbcb21fb7` from its frozen archive and the previously built 128-image kdscope5 provider. Provider and workload started. All eight short eight-process applications exited zero, drained and passed per-root counter conservation. The diagnostic was unscored learning; this documentation edit did not run a driver, build or workload.

Each replacement was exercised through g6 `NORMAL`. The final applications had these outcomes for the munmap root:

| Application | Startup generation | JIT entries | Finished native handbacks | Retained-root returns |
| --- | ---: | ---: | ---: | ---: |
| 6 | 6 | 425,584 | 425,584 | 0 |
| 7 | 6 | 426,048 | 426,048 | 0 |

No final ordinary CALL/IJ report remained pending for that root. The last admitted CALL, `mas_spanning_rebalance` at `0xffffffff826bfd20`, was learned from g5 and included in g6. Static g6 contained nine release terminals and fifteen `SOURCE_FRONTIER`s. Concrete static candidates included a nonfinal `_raw_spin_unlock` CALL in `mas_nomem` at `0xffffffff826c6b6a`, return word `0xffffffff826c6b6f`, and `STD` in `__memmove` at `0xffffffff826f0777`. The assembly SHA256 is `c98154797e822db9583a3b6fb1cf344bffd47fd0abaa6c08f09e325611104a28`.

**Actual per-invocation cause remains unproven.** `service_trace` was off and `exact_runtime_handback_reason_retained` is false. Counters did not retain the exit cursor/reason or owner state. Static candidates cannot establish whether an invocation reached a release boundary, the `STD` frontier or another exit. Application completion and hundreds of thousands of JIT entries do not establish retained-root return or generic post-operation JIT reentry. An empty ordinary CALL/IJ pending set does not imply that permanent exits disappeared.

The other root remained g0 `NATIVE_ONLY`, reporting `CONTEXT_NATIVE_ONLY` at `vma_interval_tree_insert`, `0xffffffff817d4690`, with `reachable text exceeds 32 CFG expansions`. Preserve this as the reported resource limit, not proof of a different exhausted resource. The combined learning condition failed within the eight-application allowance despite stable g6: `bounded short learning did not settle during an application`. The campaign was incomplete and not performance-qualified.

Exact retirement separately passed: state 2, modules/frames/writers zero and final idle. Normal recovery verified `7.0.0-38-kdlock1`, Build ID `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot `d794c6f4-85cc-484b-a290-471c44d68497`. The recorded evidence archive has 393 indexed entries and SHA256 `e1a933d892078ff6450ff39e68efa538a54220ab7264f8591fabcccd5640857e`; this revision did not reopen, modify or recreate it.

These are facts about that tested source/image/configuration. They expose generic lock, continuation, instruction/context, compiler-resource, lifetime and observation constraints. Neither its specialized root admission nor an experiment-specific release-unit suggestion selects the architecture of the new general lock. This review does not transfer those receipts to unimplemented S_W or fragment mechanisms.

### 2.6 Generic constraints and decisions

In this table, **E-live** means the pinned README/JSON and their exact source/image identity in section 2.5. A confirmed static candidate or reported refusal is labelled as such; it is not an observed execution cause. Fixed requirements are separate from open primitives and validation.

| Confirmed symptom | Reusable requirement | Current limitation | Open mechanism/validation | Source evidence |
| --- | --- | --- | --- | --- |
| g6 was exercised; its final 425,584 and 426,048 entries all ended in native handback with zero retained-root returns | Generic current-state admission after any successful lock/release/mode operation; preserve one S_W and source effects | No whole-root return or generic post-operation reentry was demonstrated; actual exit cause unknown | C04/C06 bridge and current-state adapters; T38/T41/T42 | E-live application 6/7 `service_delta` and README counter table |
| Static g6 had nine release terminals and fifteen source frontiers; exit trace was off | Distinguish intentional operation boundaries, permanent capability dispositions and ordinary misses; record actual cursor/owner/phase | A reached release boundary and per-invocation cause remain unproven | Typed exit receipts and generic boundary dispatch, without compiling boundaries away; T07/T09/T42 | E-live `static_release_terminals`, `static_source_frontiers`, `service_trace` and `exact_runtime_handback_reason_retained` |
| Static `STD` candidate exists in ordinary `__memmove` source | Preserve its selected path frontier and exact reached handback; no function-name model | Current recorded frontier remains and actual cause was unproven; AS01 is not a validation result | Path-only emission/joins and T43/T52; no new general flags/SIMD subsystem | E-live README locations and `munmap.possible_boundaries` |
| Another root reported the 32-CFG-expansion limit and stayed NATIVE_ONLY | Precise source/compiler resource classes, bounded compilation and safe forward completion | Reported CFG refusal persists; it is not evidence of text-cache/image/frame exhaustion | C08 deliberately selects target bounds; record limit/usage/cursor and prove local admission or exact forward completion; T24/T44 | E-live `mmap_refusal`, final registry and README daemon-log reference |
| No final ordinary CALL/IJ report remained pending; combined learning still failed within the allowance despite stable g6 | Learning accumulates valid coverage and cannot be required for current completion or erase permanent boundaries | Stable image generation did not settle all roots or establish full JIT capability | C08 pending/settled policy, bounded backoff and separate capability validation; T31-T36/T44 | E-live `munmap.pending_call_or_ij`, `error`, `learning_budget` and README |
| Eight applications completed/drained; retirement and normal idle recovery passed separately | Separate application/local/fragment/handback/root outcomes and independent S_W/grant/read-credit lifetimes | Cleanup success does not prove the proposed per-hop ownership/lifetime model | C02/C03/C11 last-user and ACK protocol; T38-T42/T45 | E-live application results, `finalization.retired`, `retirement_passed` and `normal_recovery` |
| Earlier ordinary-mutex inspection records optional selection; specialized roots have narrower election | General family-specific local/proxy arbitration, original-origin lookup and one exclusive executor | Specialized root behavior is not general lock behavior; no new S_W protocol is implemented | C01/C02/C11 concrete family/transfer serialization and W/V switching; T01-T04/T38-T40/T47 | Section 2.3 source-review record, separate from E-live counters |

### 2.7 Newer proxy-downgrade and flags-stack evidence

This revision's read-only checkout snapshot was master `2e9016915632ab4a488f444d06fe881ffcca0616`. The supplied integration history contains tested checkpoint `7e3c90b469c1f824ba0e82773880c605f3fbcfe2`, implementation `adf4d2680d0b07e38cf5a0a2f9d609673b425636`, fixture alignment `3ceb7f002672e8e9a4b2a14de6660944338088e5`, evidence `2c819210` and merge `6badc60e`. These identities locate existing work; this documentation task implemented/ran nothing.

**Candidate behavior (E):** a typed downgrade actually consumed during proxy/JIT execution makes the acquisition logically read-only while retaining the physical writer gate and selected admission phase `-1`. The read tail continues in the same root image until matching typed UP_READ releases that writer once. Only this candidate's typed proxy downgrade is exempted from its release-unit cut. If native handback occurs before downgrade, native-first/local handling publishes genuine reader credit and releases the writer gate/phase. The candidate limits final proxy release to the original logical task in ordinary task context.

That retained writer/read label is a narrow experimental choice. It is not a generic exception to target source lock/unlock boundaries, a selected target downgrade policy or proof of native reader-admission/concurrency equivalence. C10 still has to supply the chosen target mode operation and native API semantics.

The [focused receipt](../../../bench/results/10.176.26.71/tests/rwsem-proxy-read-20261109/README.md) records the fresh basic/affected checks and builds passing after preserved fixture failures. Its bounded live attempt failed quiescent learning: the eight-worker roots recorded 274,767 and 274,766 entries, all finished handbacks and zero returned JIT bodies. The application returned/drained and exact retirement/recovery passed separately. This did not establish consumed proxy downgrade; no performance gain was established.

The later [stable instrumented point](../../../bench/results/10.176.26.71/bench/mmap1-proxy-read-7e3c90b4-v3/README.md), bound to unchanged `7e3c90b4`, returned all 398,610 mmap and 398,608 munmap JIT entries across the complete fixed application, with zero completed handbacks. It reports 256,709 measured pairs in ten nominal seconds, 25,670.9 pairs per nominal second, and separate successful retirement/recovery. It is one instrumented point, not Native gain/quiet-performance acceptance, and it identifies neither a particular consumed downgrade branch nor a physical chain. Earlier failed receipts and their verdicts remain intact.

The point excludes master's independent flags-stack changes (the receipt names `39e916c8` and `111ac671`). [Maintained execution documentation](../../JIT_EXECUTION.md) distinguishes tested `7e3c90b4` from the merged combination and its source-specific/static checks. That combined runtime was not validated by this receipt. Neither the merge, focused fixtures nor whole-root returns verify comprehensive general flags/SIMD equivalence; AS01 remains an explicit design assumption. The current PUSHFQ/POPFQ simulation requirement is a target local contract, not a claim that this measurement tested the merged lowering.

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

The acceptance register is T01 through T56. T01-T51 retain their audit identities and chosen-target scope. T52 adds special-path/bypass/shared-join behavior, T53 safe callee returns/caller fallthrough, T54 local temporary-GPR PUSHFQ/POPFQ effects under AS01, and T55 target downgrade versus the candidate-only exception. T56 adds the matched original-backend mapping comparison without a speed/AS01 validation claim. These are future specifications and were not run by this documentation task.

### 3.2 Authority audit and correction register

N IDs identify this normative-origin audit, distinct from the historical v0.6 A01-A41 register. "Corrected" means the text's authority/classification changed; no mechanism was implemented or validated. Current source facts and numeric receipts above remain E.

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
| N12 | Current signal/reader/downgrade/IRQ/debug exclusions read as permanent bans | E support limits and P initial scope/extension choices; no new route/configuration is claimed. Linux 7 x86_64 non-PREEMPT_RT remains fixed F | C01/C10, support matrix/P7 |
| N13 | Terminal native suffix read as only possible architecture | Terminal suffix is conservative P; no replay/exact state is F/S. Resumable service/reentry requires an explicit new contract, never automatic old-cursor revival | C04/C06/C10, JIT section 4.3 |
| N14 | "Preserve current implementation first" made architectural | Native/API semantics and evidence history are S/E. Incremental migration and clean reimplementation are P delivery alternatives, with compatibility chosen explicitly | C01/C12, P0-P8 |
| N15 | Node-owned control treated as settled storage | Remains open P. Request lifetime, acquisition-slot lifetime and cache layout are audited only for the selected backend; no packet duplication or automatic frames/refcounts | C02/C05, node proposal/T48/T49 |
| N16 | Deferred/unproved general flags/SIMD text could become a new gate | AS01 is the user's explicit assumed-correct iteration scope, not evidence; no separate general subsystem/shadow/gate, with local PUSHFQ/POPFQ simulation the exception | JIT section 3.5, C04, T54 |
| N17 | Broad admission/frontier wording could reject a whole root | Ordinary trusted-source translation is target intent; recognized special instructions clip only affected paths. Keep safe alternatives/joins/returns and exact reached handback without replay | JIT section 1.3, T43/T52/T53 |
| N18 | Experimental typed proxy downgrade could weaken target boundaries/native semantics | Retained writer/admission and same-root exception are E only; target mode handling/native equivalence remain separate decisions. Stable point/merge does not prove a consumed branch or general flags correctness | Section 2.7, C10, T55 |
| N19 | Reserved packet-base versus resident logical R11 read as a settled optimization | Pinned mappings are E and C04 optimization candidates under one original backend. Compare remap/spill work versus boundary materialization/transfer with one canonical core, no per-user spare packet and no measured gain claim | JIT section 3.1.1, T56 |

## 4 TCLock guidance and limits

The original TCLock artifact uses native borrowed-stack execution and explicit task/per-CPU stack metadata. Its stack switch preserves native callee-saved context; it does not switch physical `current`, hardware GS or CR3.

For kdlock, borrow the **lock protocol idea**: an outer combiner can become an inner waiter/combiner and restore its outer combining state. Do not transplant the borrowed-stack execution engine in place of the original JIT.

The supplied public-source review at `bbfb9f00a12af51dff6ca291cb9829a82960c2ef` gives narrow placement precedent. TCLock's mutex node holds links, saved stack pointer, task/lock identity and completion/lock flags. [Mutex node declaration](https://github.com/rs3lab/TCLocks/blob/bbfb9f00a12af51dff6ca291cb9829a82960c2ef/src/kernel/linux-5.14.16/include/linux/mutex.h#L52-L83). Its nested combining code saves/restores outer combining control outside the node, so it does not put all control in nodes. [Nested mutex combining](https://github.com/rs3lab/TCLocks/blob/bbfb9f00a12af51dff6ca291cb9829a82960c2ef/src/kernel/linux-5.14.16/kernel/locking/mutex.c#L490-L547). The spin implementation uses bounded per-CPU nodes, adjusts their count around acquisition/combiner transitions and has separate shadow-stack control. [Spin node and combining transitions](https://github.com/rs3lab/TCLocks/blob/bbfb9f00a12af51dff6ca291cb9829a82960c2ef/src/kernel/rcuht/locks/komb.c#L494-L690). These are protocol precedents for the open lifetime audit, not validation of kdlock's proposed node retention or permission to copy native borrowed-stack execution and semantic shortcuts.

The inspected original Linux 5.14.16 artifact has semantic shortcuts/limitations, including killable-path treatment and unimplemented downgrade; its integration also changed task/boot/stack arrangements and disabled stack protector in that artifact. These are not accepted Linux 7 kdlock semantics. Source observation and benchmark similarity do not authorize copying them.

## 5 Primary source map

### Original UB

Pinned commit: `1a5b98a06b058a7adce9805c8c6d061e2212f56a`.

- [Indirect target dispatch and miss stubs](https://github.com/glarer/UserspaceBypass/blob/1a5b98a06b058a7adce9805c8c6d061e2212f56a/source_codes/ub/zz_disassem/indirect_jump.py)
- [Original wrapper and state export](https://github.com/glarer/UserspaceBypass/blob/1a5b98a06b058a7adce9805c8c6d061e2212f56a/source_codes/ub/zz_daemon/asm/wrapper.S)
- [Feedback and recompilation loop](https://github.com/glarer/UserspaceBypass/blob/1a5b98a06b058a7adce9805c8c6d061e2212f56a/source_codes/ub/zz_daemon/main.c)
- [Register allocator](https://github.com/glarer/UserspaceBypass/blob/1a5b98a06b058a7adce9805c8c6d061e2212f56a/source_codes/ub/zz_disassem/conflict.py)
- [Historical packet/segment macros](https://github.com/glarer/UserspaceBypass/blob/1a5b98a06b058a7adce9805c8c6d061e2212f56a/source_codes/ub/zz_disassem/asm/asm_head.h)

### Historical pinned kdlock

Pinned commit: `20fde062729703208ac54445f51fc0f21f24e0e8`.

- [Spin nested construction](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/kernel_module/spin/nested.inc) and [spin execution](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/kernel_module/spin/execute.inc)
- [Mutex call routing](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/kernel_module/lock/mutex_calls.inc) and [mutex waiter path](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/kernel_module/mutex/waiter.inc)
- [Remote ancestor release](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/kernel_module/execution/remote.inc)
- [Grant ledger](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/kernel_module/execution/lock_ledger.inc) and [frame lifecycle](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/kernel_module/execution/frame_lifecycle.inc)
- [Private register packet](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/include/kd_regs.h), [wrapper](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/include/wrapper.S), [register aliases](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/include/asm_head.h)
- [Register allocator](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/disassem/conflict.py), [stack/CALL/flags lowering](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/disassem/special_inst.py), [GS/current-task lowering](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/disassem/normal.py)
- [Historical JIT ABI contract](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/docs/JIT_REGISTER_ABI.md)
- [Read/write scope and limitations](https://github.com/hailongeric/kdlock/blob/20fde062729703208ac54445f51fc0f21f24e0e8/docs/design/rwsem_implementation.md)

### TCLock and Linux

- [TCLocks paper](https://www.usenix.org/system/files/osdi23-gupta.pdf)
- [Original TCLock mutex implementation](https://github.com/rs3lab/TCLocks/blob/bbfb9f00a12af51dff6ca291cb9829a82960c2ef/src/kernel/linux-5.14.16/kernel/locking/mutex.c#L419-L840)
- [Original spin combining](https://github.com/rs3lab/TCLocks/blob/bbfb9f00a12af51dff6ca291cb9829a82960c2ef/src/kernel/rcuht/locks/komb.c#L494-L690)
- [Original rwsem limitations](https://github.com/rs3lab/TCLocks/blob/bbfb9f00a12af51dff6ca291cb9829a82960c2ef/src/kernel/linux-5.14.16/kernel/locking/rwsem.c#L996-L1075)
- [Linux lock types](https://docs.kernel.org/locking/locktypes.html)

## 6 Delivery and verification record

The initial integration recorded reconciliation against both complete source documents and review of optional selection, operation boundaries, non-LIFO release, image bridging and no-replay handback, with artifact-preparation language/link/fence/archive checks. Those historical records remain above. Revision 1.1 checks the five existing documents for local links/anchors, English content, fence/flowchart structure, one-state/reader/source-operation consistency and unchanged non-document work; no archive is created or repacked.

No code was implemented. The user supplied the exact existing session `01a1bc4f-fc6c-7be3-8fe9-be6744999b40` on `remote-ssh-discovered:380G10-1`; reading it verified the title **restructure the kdlock** and project `/home/eric/vm/vm-shared/kdlock`. The similarly located **kdlock will-it-scale mmap1 task** was not used as a substitute.

Delivery through revision 1.4 used the same five individual Markdown files in `docs/design/kdlock_redesign/`, in the same order, preserving prior audit/source/evidence and unrelated work. Its then-current C01-C11 choices and acceptance gates were open. Those records do not establish present source support or dictate the target compatibility contract. Revision 1.5 retains the files/history and adds C12 with explicit target authority.

Revision 1.2 makes only the focused minimal-mechanism clarification and the pinned shared-packet source check above. It preserves the revision 1.1 receipt snapshot and distinction from subsequent concurrent work, without new live-evidence research. C02/C05/C11 now start from reuse and structured lifetime proofs; allocation/refcount choices remain conditional. Local links, English/fence/flowchart consistency and unchanged non-document work are checked for this edit. No code, build, workload, commit, installation or archive creation is part of it.

Revision 1.3 adds only the two-level physical layout requirement, its supplied narrow source evidence and T48. The five file identities/order, earlier audit/receipt snapshots, semantic obligations and open placement/lifetime mechanisms remain. Links, layout wording, flowchart structure and unchanged non-document files are checked without implementation, builds, workloads, commits, installations, new source research or archive creation.

Revision 1.4 adds the proposed node-owned-control audit, C02/P1 alignment, T49 and the supplied pinned kdlock/TCLock evidence. The JIT contract and fixed one-core model remain as before. Retaining a composite request node versus escaping small control, outer-control placement and cache layout are open choices; no lifetime simplification, 64-byte layout, memory saving or performance gain has been demonstrated. No new source research, implementation, build, workload, commit, installation or archive creation is included. Document links/structure and unchanged non-document work are checked.

Revision 1.5 rereads all five current documents and corrects normative origins under the latest rewrite direction. It adds the authority rule, N01-N15 correction register, C12 compatibility decision, prioritized confirmation list and T50/T51; earlier receipt hashes/counts/outcomes and source maps remain. Current reader/pinning/ABI/queue/update mechanisms become explicit P or conditional E rather than architecture. Document links/flowcharts/language and unchanged non-document work are checked. No source implementation, builds, workloads, commits, installation, archive creation or other-session communication is part of this audit.

Revision 1.6 adds the explicit AS01 scope, path-only special-instruction frontiers and safe-join/callee example, local PUSHFQ/POPFQ temporary-GPR contract, the C04 mapping comparison, T52-T56 and N16-N19. It reads only the supplied existing receipts/execution documentation and preserves earlier receipt snapshots. Target authority, core/reference layout, optional delegation and source-operation boundaries remain. Links/fences/diagram structure, cross-references and unchanged non-document work are checked without source implementation, builds, workloads, commits, installation or archive creation.
