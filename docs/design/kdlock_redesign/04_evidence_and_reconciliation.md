# kdlock design reconciliation and evidence gates

**Status:** active design authority, reconciliation and validation boundaries
**Design basis:** revision 1.11, direct MCS state and task-owned auxiliary entry
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
transferable-grant recommendation is superseded. C11 now selects an MCS queue
and C04 retains the KD physical-R11 canonical-packet-base mapping. Optional
local/proxy/origin-combiner transactions, MCS/request lifetimes and exact
adapter/bridge details still need implementation/proof; C08 now selects
preallocated miss-fact retention with continued admission as recorded below.
C10 extensions remain separately scoped. Managed provisioning/lifecycle/provider
composition is now source-connected through `c6becf81`; deployment and exact
target validation remain separate. C05 selects task-owned preallocated persistent requests for normal
local/proxy selection. The supported workload guarantees availability
within an explicit finite caller capacity covering all live/retained users;
exhaustion is documentation-only, with no handler/recovery/local fallback or new
special assertion. Full provisioning/control/lifetime proof remains work. R11 optimization discussion/T56 are deferred future work. These selections establish no validated
support lane or generic native release-timing/progress parity.
Keep one canonical S_W, optional unique selection, every source lock/unlock as
a pre-operation fragment boundary, serial recursive delegation, exact no-replay
handback and cumulative source-versioned learning with the original backend.

**Selected C08:** use a preallocated JIT-miss fact pool with finite explicit caller
capacity sufficient for the supported workload. Pending facts or translation do
not by themselves disable new JIT/delegation; existing source/context/image
checks still apply. Each fact retains exact source site/resolved target,
transfer/exit phase and producer/source-version identity. Valid same-version
observations accumulate in compiler input before building; fact recording,
emitted coverage, actual publication and ACK remain distinct. Uncovered/later
facts stay pending. No numeric deployment value, unbounded claim or runtime
validation follows. Reviewed kernel source `5989fbbb` implements the pool,
code-independent producer/source retention and exact commit/ACK bridge;
host coordinator `af997cb6` composes cumulative merge and receipt reconciliation.
Source checkpoint `40ae39ce` adds immutable-contract source snapshots/native
holds, cold task storage/retained-stack words and kernel shutdown settlement.
Selected shutdown requires exact fsynced host archives/content receipts before
SETTLED after image/native/JIT drain; this is separate from coverage ACK.
Nonobservations and uncovered misses stay pending normally and count toward
capacity. Actual channel/compiler/executable-provider/runtime composition and
fsynced archive/receipt wiring have source at `236c287a` and `80095bfb`; exact
exported slot/base identities follow at `c6becf81`. Crash/restart reconstruction
beyond the session/archive workflow is not implemented. The prior pending-fact
forced-local/defer option is superseded.

### 1.1 Assumption and target policy versus evidence

| Item | Target authority/scope | Evidence limit |
| --- | --- | --- |
| Ordinary trusted-source translatability | Original UB-derived backend; known special instructions clip only affected paths, preserving safe alternatives/joins | No universal instruction or kernel equivalence is established |
| AS01: general flags/SIMD | Assume correct for this iteration, without extra general capture, virtualization, shadow state or blanket admission gate | An explicit assumption, not a general equivalence result |
| PUSHFQ/POPFQ local exception | Temporary GPR and exactly one virtual-source push/pop, preserved live values and balanced physical-stack temporaries | Lowering source is present; covered POPFQ effects and runtime proof remain unrun |
| Selected ordinary-mutex outer unlock | Exact source request and deferred marker, retained responsible outer combiner, notification/unwind and owner handling, normal batch then physical release | Extra waiting accepted; no generic native timing/progress parity. Initial mutex lock-object storage stays valid through actual physical release/final object access; owner/control/notifier last users and callback-code retention remain separate |
| Target downgrade | C10 chooses mode semantics with native API behavior and generic operation boundaries | A prior retained-writer/read-label mechanism is not a target boundary exception or concurrency proof; the mutex deferral choice creates no downgrade exception |

## 2 Evidence boundaries

### 2.1 Rebuild status

The declared ordinary source path is connected through `c6becf81` and has
independent source/static review. A subsequent focused VM check passed 12/12
on that exact source, including real GNU image construction. The
[retained focused receipt](../../../tests/evidence/runtime-pipeline-20261110/README.md)
is committed at `c6fbf7bb`. This is neither
exact-target kernel integration nor mutex/JIT runtime correctness or performance
evidence; kernel execution and the T01-T56 acceptance matrix remain unrun.

The focused run used Python 3.14.4 in the translation virtual environment on
`7.0.0-38-kdlock1`, boot `3d32656f-6162-4a0a-9304-bf383d34298d`, taint 0,
2026-11-10 14:34:16-17 UTC. Return code was 0; all 99 frozen input files were
reverified unchanged with no extras. The log SHA256 is
`2b207a2867c94ca9d61867bd7b46057e8c32cd08570e00a0dbd6b30573155752`.
Guest receipts are under
`/mnt/kdlock-builds/kdlock-main-work/run-c6becf81-01a1bc4f/receipts`. The GNU
case invokes actual cpp/as/ld/objcopy; its bytes/metadata are not loaded into the
kernel. These focused checks do not complete any T01-T56 acceptance item.

The [fragment planner](../../../disassem/fragment.py) retains typed source
boundaries, safe alternatives/joins, finite cycles, missing edges and unknown
alternatives. Explicit direct/indirect CALL records retain each call's own
continuation and known callee targets. A local least fixed point derives
boundary-free routes to explicit RET; only known returning callees contribute
caller return summaries. An unknown alternative cannot invent a return, and RET
sites are not connected indiscriminately to all callers. Changed source return
structures remain outside the matched-return input contract.

The [supplied-byte decoder](../../../disassem/source_decode.py) preserves the
original Miasm x86_64 interface and relative-target arithmetic from
`archive/before-main-20261109` at `7ce7db54334960fe0d9db2c425c5c581cdedf4b0`,
`disassem/reached_path.py`. It retains exact site/bytes/length, operands and the
actual Miasm instruction, including prefix/method metadata. Mutating lowerers
copy instructions/expressions independently. The dependency set in
[requirements.txt](../../../disassem/requirements.txt) dependency lane was used
by the focused VM checks above. Decoding is not source residence, semantic
equivalence or general lowering support.

The [integrated compiler](../../../disassem/compiler.py) consumes a finite,
immutable source/version snapshot and exact source-operation metadata. It
checks overlapping bytes, discovers/decode-plans both known direct and observed
ordinary indirect alternatives, and preserves source/decode/unmodeled/resource
outcomes. Observations must match the source version and accumulate immutably;
attachment to the graph is explicitly distinct from emitted coverage. Exact
source-operation metadata takes precedence over observations. Unknown dynamic
targets still require runtime API classification before operation effects.

Only the selected five direct-CALL discovery edges have a default. Observed
indirect target expansion keeps the current direct-call depth; explicit decode,
window and CFG limits bound it. Decoder-window consumption counts submitted
overlapping/failed windows, and CFG work counts popped redundant edges. Receipts
retain resource kind, site/edge, limit, consumed and required quantities. They
are not runtime nesting, unique source-cache or per-invocation exit evidence.
Zero available bytes, partial/unsupported decode, unmodeled flow and resource
refusal stay distinct; stopped paths do not refuse the whole function/root.

The [lowerer](../../../disassem/lowering.py),
[original mapper](../../../disassem/backend) and
[wrapper](../../../include/wrapper.S) now construct standalone assembly and
static emission/exit metadata. Physical R11 holds the one canonical packet;
logical R11 and mapped GPRs use that backing. Source CALL/RET words, GS and logical
current_task lowering remain explicit. PUSHFQ/POPFQ use temporary GPRs and one
virtual-source stack operation. Path-specific operation, special, construction
and resource exits preserve reached-only behavior. The coordinated private ABI
is version 1, packet 168 bytes and IO 56 bytes; it promises no legacy binary
compatibility. This is construction source, not executable publication, a
returned body, full instruction equivalence or a coverage ACK.

The [release protocol](../../../kernel/mutex_release.c) retains exact owner and
per-acquisition controls with HELD, REQUESTED, DEFERRED, UNWIND_READY,
OWNER_HANDLED, PHYSICALLY_RELEASED and RETIRED phases. REQUESTED publishes OWNER
versus DEFERRED_OUTER from the exact active relationship. Same-task equality
alone cannot classify an outer release. Bound complete unlock callback/object
are taken/cleared under the owner guard, called once outside it, and only then
marked physically released. Source/return/notifier users remain separate.
The protocol itself advances no source and performs no late object access.

The [MCS mutex](../../../kernel/mutex.c), committed in `4d3e40a1`, supplies actual
sleepable queue/exclusion source, optional local/proxy claims, exact batch grants
and physical release/reap paths. It never skips an immediate local-only/local
selected successor. Proxy service has an explicit total batch bound; successful
grants are not returned bodies or measured physical chains. Live-grant outcomes
publish a result before owner waiting so a retained actor can reach unlock.
Result/binding access, core grant membership, queue producer access, return and
notifier users all finish before retirement; owner reaping must progress
independently. Source review found no confirmed queue-link/retirement defect
under those contracts. No MCS callback has executed.

The [canonical state](../../../kernel/state.c) contains one W packet, one
current source operation, exact referring grants and execution bindings.
Distinct live offer/run/return endpoints avoid pointer reuse across an ownership
episode. The [JIT bridge](../../../kernel/jit.c) invokes that actual ABI and binds
a pending exit to its exact retained producing image. It classifies retained
targets without rereading operands, stages CALL words once, distinguishes
already-staged CALL and consumed RET, handles exact MCS acquisition/unlock and
collects logically closed physically completed grants. A compiler-clobber root
captures post-call continuation IP with pre-CALL SP; completion does not pop a
source word. Unsupported TARGET_READY calls must stage their retained target
before native handback; reentry cannot discard it.

The [native restore](../../../include/native_resume.S) restores source GPRs and
exact IP/SP on original W using one admitted writable SP-8 bridge word. That
bridge push/RET leaves final source SP unchanged and is not another logical
CALL/RET. General flags/SIMD use AS01. Return mitigation coverage and kernel
assembly wiring remain unvalidated. Generated execution uses a distinct physical
task/stack and requires executor/source/origin-wait control stacks to be
nonoverlapping; current==W JIT is refused. A budget is not stack-separation
proof. The private ordinary/auxiliary route is connected in source at `ce423858`,
but no live auxiliary-stack route has been validated.

Every active/nested request uses its direct node->state pointer. The
[task root](../../../kernel/task_state.c) contains the one own core and the
selected task-owned auxiliary header for initial native entry. It supplies no
active-S_W registry. Its [task field artifact](../../../kernel/integration/README.md)
contains the one field and managed fork/failure/exit hooks as an unapplied
context template. Child construction clears copied aliases before publication
and creates independent core/pool/auxiliary backing; current-native exit drains
exact users before detach/free. `apply_target.py` (`97130fe4`) applies only exact
pinned target contexts via new-inode replacement; it remains unexecuted.

The [ordinary source pair](../../../include/kd_mutex_api.h),
[native bootstrap](../../../kernel/mutex_api.c),
[prepared prefix](../../../include/kd_mutex.h),
[stack switch](../../../include/mutex_entry.S) and
[native preflight](../../../kernel/native_entry.c) preserve source SP/IP/BP and
switch to task-owned auxiliary control before publication. Descriptor phases
separate private preparation, entered control and completed native restore.
Range/alignment, mandatory return-word capacity, ordinary task context and exact
reservation checks are source implementations. Full callback/recursive capacity,
opaque control placement and scheduler/IRQ/unwind compatibility remain explicit
admission duties, without runtime evidence. Capture refreshes active kernel GS
under a short non-sleeping interval, not an episode-wide pinning guarantee.

The [image component](../../../kernel/image.c) implements the selected quiesced
RCU rule. Exact preallocated execution/return/source records retain sleeping and
suspended users. Closing blocks new roots; already-admitted parents can extend
child/return holds. A coherent pointer swap requires all exact users to drain,
and old lookup readers then pass a grace period. Expected-base and transaction
identities retain their own lifetimes. JIT invocation uses actual EXECUTION
records and claims a distinct pending-exit child before code; ordinary put
cannot remove it. The bridge clears pending observers before the final child
drop and copies required source scalars before final metadata access ends.

The temporary external-registry variant is unselected and retained only at
`archive/c02-registry-not-selected`, commit
`38d1bfb827f33e86ce2b50456d22a00aed89b8ad`. The earlier two-task-pointer
implementation remains at `archive/c02-direct-task-fields-not-selected`,
commit `727facf0537e60a1842f4ff8c89fa39aa217e9a0`. Current source derives borrowed
execution from MCS node pointers and uses the stable task root only for initial
own backing/auxiliary control. These snapshots are not runtime validation.

C05 selects preallocated persistent task-owned request records for the unified
normal local/proxy path. Distinct simultaneously live records stay occupied
through exact physical-owner/release, grant, control, return, notification,
image/binding and current-native-endpoint users. Queue detachment or source/
result completion alone is insufficient. Finite explicit caller capacity covers
concurrent nested requests and every still-retained record, not only depth.

The supported workload guarantees a record for every need. Task attachment/
resources supply the actual count; no deployment count, one-node sufficiency or
mathematically unbounded capacity is configured or proved. Exhaustion is a
documentation-only support limitation, with no handler, recovery/local fallback
or new special assertion. Normal local winners keep their persistent controls
in the same path. This supersedes the temporary-waiter/object-head fallback and
held-local native interval strategy preserved in Git at
`0cedb299618004d5867791551b45bdf66cfb81fa`, removed by the scoped follow-up
`26325fe4`. Earlier storage-choice history,
including `b95995b5`, remains reachable. Neither historical selection is runtime
evidence for the current contract.

Reviewed source commit `2c3f7cbc` connects the
[request pool](../../../kernel/request_pool.c), exact generic users and final
reuse/detach checks to the original core, and the
[owner-progress controller](../../../kernel/owner_progress.c) to the actual
physical task. Exact retained batches progress through owner handling, physical
release and later reaping independently of source/result completion. JIT and MCS
wait callbacks connect progress/readiness after source export; no callback has
executed. Caller-provisioned capacity and actual task lifecycle integration still
need their complete proof.

Reviewed source commit `ce423858` connects the ordinary source CALL pair/native
bootstrap to the [serial episode driver](../../../kernel/episode.c). It uses actual
producing-image exits, once-only operation phases, distinct child/returned/native
endpoints and deferred notification after export. A no-image root retains
persistent local eligibility. Native unlock uses its existing exact grant and a
temporary retained actor, completing through hardware CALL/RET without another
request slot or canonical native SP/IP restoration. Root completion retains its
separate auxiliary actor until the final entry/binding reads finish; that actor
closes before the native jump. The [task progress helper](../../../kernel/task_progress.c)
connects actual-owner progress, episode/grant actor collection and finished-slot
collection. The initial C07 logical-open scan fixes a new locally won batch's
service bound at zero while an outer logical grant is open, leaving the same
ready/external-proxy path. These private paths have independent source review;
no operation, generated fragment, callback or assembly path has executed.

Subsequent independently reviewed source milestones are:

- `57599619`: [current-task setup composition](../../../kernel/task_setup.c)
  validates explicit caller-owned ranges, composes attach/resources/bind and exact
  unused-root rollback, and attempts detach after one progress pass. It supplies
  no allocator or automatic fork/exit/stack integration.
- `a660342c`: [source epochs](../../../kernel/source_epoch.c) validate supplied
  coherent version/region/configuration/load inputs and retain an already-owned
  lease through exact BUILD/IMAGE/FEEDBACK users. Closure is retention-only;
  actual live acquisition/mutation admission and native-text holds stay external.
- `c9b468ee`: [copied-exit classification](../../../disassem/feedback.py)
  preserves original immutable facts and yields only matched ordinary indirect
  CALL/JMP compiler inputs. It implements no C08 storage/transport/capacity/
  saturation/late-report/reset/ACK policy.
- `0c3ccb10`: [artifact input maps](../../../kernel/image_inputs.h) retain exact
  version/GS/decoded-byte construction inputs; image-slot transactions also allow
  final NULL removal through the same exact drain/RCU grace. Neither is a lease
  acquirer or executable-memory allocator.
- `a23b82c1`: [image-owner envelopes](../../../kernel/image_owner.c) validate
  descriptor/input correspondence to an existing coherent epoch and code hold,
  derive IMAGE retention from BUILD, bridge publication with live parent users,
  and release old published memberships only through exact retirement transactions
  and the actual returned old descriptor after grace. Finalizers run the retained
  code callback before the final source put, with independent control/callback
  backing. This is retention ownership, not executable allocation or publisher
  orchestration.

Reviewed source commit `5989fbbb` additionally includes
[kernel miss facts](../../../kernel/feedback.c) and the
[publication/ACK bridge](../../../kernel/feedback_publish.c). The episode
records COVERAGE_MISS once before any staging/consumption, with a required pure
explicit target classifier; normal operation/resource/special exits are not
pooled automatically. Durable producer and epoch users retain copied facts
after old code/descriptor release. Exact record incarnations, claims and a
partial-end barrier prevent stale copied history or ACK from reusing an ended
claim. The publication bridge takes only validated MERGED inputs and the exact
candidate code hold/receipt, binds the actual transaction and returned old image,
then separately ACKs the emitted subset. It does not itself transport facts,
build/load code or settle nonobservations/uncovered misses. Those remain pending
during normal execution. The later selected shutdown settlement route is
recorded below; it does not turn these dispositions into coverage ACK.
The reviewed [host coordinator](../../../disassem/learning.py) at `af997cb6`
retains finite explicit fact/claim/candidate/publication/ACK histories, merges
valid same-version observations before compile/lower/export and preserves late/
foreign/nonobservation facts. It freezes per-claim MERGED input keys and
reconciles exact actual publication and ACK independently; it supplies no
transport, persistence or executable publication. No runtime or behavioral
evidence follows from these source reviews.

Source checkpoint `40ae39ce` adds the concrete
[source provider](../../../kernel/source_provider.c), which pins the complete
supplied module set and copies actual-address bytes under the explicitly selected
all-dependency immutable-text contract. The caller excludes every mutator through
final native/JIT/feedback use; module_get alone is not a freeze. Version/config/
load identities and the exact GS offset stay caller inputs. Independent NATIVE
epoch holds cover complete native activity. Cold
[task storage](../../../kernel/task_storage.c) allocates explicit heap/request/
frame/auxiliary backing and retains unsafe setup unwind, while
[stack words](../../../kernel/source_stack.c) retain the original task stack and
perform bounded single-word accesses. Exact detach/full caller last-use proof
precedes freeing and the final native-provider callback. No packet is cleared.
`lifecycle.[ch]` (`80095bfb`) adds managed initial entry, independent unpublished
child construction/failure cleanup and current-native exit drain. It never
fabricates unlocks or copies parent source state; unmanaged tasks remain outside
the declared lane. Exact target hook application and full auxiliary-context
proof remain outstanding.

The same checkpoint implements kernel archival settlement. Actual host archival
must fsync exact copied facts/provenance and produce a 32-byte content receipt.
The kernel validates exact claim keys/incarnations, CLOSED epoch with only
FEEDBACK users and closed producers without IMAGE users after image/native/JIT
drain, then marks SETTLED atomically. This is separate from coverage ACK; claim
end later releases settled holds. Kernel scalar receipts perform no host I/O.
`236c287a` and `80095bfb` connect actual fd channel/control, execmem loading,
the GNU host image builder/session and fsynced archive/shutdown workflow. The
loader reserves the actual executable address before host assembly/linking,
validates machine bytes plus flat typed metadata and binds the real image owner.
Control distinguishes actual publication, separate ACK and shutdown SETTLED;
sequence/cache identities preserve retry without repeating an operation. Runtime
keeps source/native/controller holds and finite control identities through exact
last users. `c6becf81` exports exact source-slot/current-image identities,
including a NULL baseline; BUILD_START validates and retains that base. These
source implementations have independent review, without build or deployment
evidence.

The [image integration guide](../../../kernel/integration/IMAGES.md) records the
conditional initial/NULL publication sequence, candidate/baseline bridges,
SOURCE self-drain avoidance and independent native-text/finalizer lifetimes.
Kernel ownership additions have source/static review only. The focused VM host
checks above import compiler components and construct a real GNU image; they do
not execute provider/image ownership or kernel mutex/JIT paths.

Reviewed source commit `a65016e3` adds the opt-in Kconfig/Kbuild group and fixed
Linux 7.0/x86_64/non-RT C target gate. Its original list has 15 runtime C units
and three concrete assembly entries; `5989fbbb` adds the fact pool and
publication bridge for 17 C units at that revision. Current `c6becf81` lists
26 C units and the same three concrete assembly entries. The unexpanded
per-image wrapper is excluded.
[The build guide](../../../kernel/integration/BUILDING.md) separates package
structure from actual target-tree insertion, task-field integration, provisioning
and provider duties. No Kconfig/Kbuild parser, preprocessing, compilation,
assembly, linking, enablement or kernel execution has run.

Remaining deployment work supplies exact source/dependency/configuration/load/GS
inputs, explicit finite pool/image/cycle capacities, complete control-stack bounds
and actual auxiliary-context proof. Managed allocation/fork/failure/exit, provider/
channel/compiler/executable/runtime composition and archival receipt wiring are
source-present through `c6becf81`. Crash/restart reconstruction beyond the
implemented session/archive workflow is not supplied. `97130fe4` adds focused
pipeline-check source and an exact-target installer. The 12 focused checks above
have now passed, including host assembly/linking; exact target application/core
build, kernel runtime, lifetime/progress and acceptance validation need separate
receipts. Selected stable object
storage extends through physical release and final object access; independent control/code users can last longer.

Ten private cases ran only on the earlier intraprocedural planner `13f2630f`
with Python 3.10.12: all four boundary kinds with a safe shared join and unchanged
input; a cycle with repeated edges; two predecessors of a missing target; a known
successor with an unresolved alternative; missing entry; boundary at entry; and
supplied scope end. They used no decoder/generated code/kernel lane and establish
only those old graph cases. They preceded the user's instruction to finish
overall functionality before further behavioral testing. They have not been
rerun on, and do not validate, any later component.

The 12 focused pipeline checks passed as recorded above. Exact-target installer
and kernel build/execution evidence remain separate. T01-T56 remain unrun
acceptance specifications. Source, build,
execution, integration, retirement and performance evidence stay separate for
exact source/configuration identities; no complete mutex lane is claimed.

### 2.2 Original backend

The original UB-derived JIT, software register virtualization and kdlock's
GS/current-task lowering remain fixed directions. C04 now retains the KD physical-R11 canonical-packet-base mapping, with logical
R11 virtualized; its optimization discussion is deferred. Exact private
adapter/layout inputs, source/return bindings, current-state bridges and local
temporary-GPR PUSHFQ/POPFQ sequence now have private source implementations.
The managed source path under C04/C06/C12 is connected through `c6becf81`; exact target integration and runtime proof require separate receipts.
Original source locations below are implementation references, not support
claims for an inherited runtime.

### 2.3 Optional selection

Publishing eligibility does not force remote execution. Local origin
acquisition, origin-as-combiner and remote selection must be exclusive under
the selected family's arbitration. C11 selects MCS for the initial ordinary-mutex queue, but its optional claims,
actual grant transitions and node/request last-use ordering must be implemented
and proved. This does not select inherited owner words, pools, capacities or
TCLock borrowed-stack execution merely because the comparison code uses them.

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
| MCS scheduling-node ownership interpreted as full request lifetime | Unified normal local/proxy requests retain every exact late user in task-owned persistent storage. Queue detachment/result alone does not permit reuse. Finite caller capacity covers concurrent nested and still-retained records under the supported-workload availability guarantee; no exhaustion fallback or handler is introduced |
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
| I05, I06, I19, I25 | R07, R08, R14: exact retained owner, source request/deferred/unwind/handling versus actual physical release, and per-acquisition/object lifetime |
| I07, I11, I14 | R09, R10, R14: separate ancestry/grants, stable records and final-access retirement |
| I08, I10, I24 | R11, R13: progress and resource-reserved forward completion |
| I13 | R15: direct MCS state pointers and stable task-owned initial backing; no borrowed-state registry; exact lookup/publication/identity and last-user lifetime remain required |
| I15, I20, I23 | R16, R17, R19: retained code, binding, independent source epoch and generation |
| I16, I17, I18 | R17, R18, R20: independent current completion, exact coverage ACK and distinct exit outcomes |
| I21, I22 | R19, R21: exact boundary recipe and full cross-task data ordering |
| I12, I26 | R22: precise evidence, admission and deferred capability limits |

The old decision topics remain covered: D01 through D09 and D12 map to C01/C05/C07/C10 and the family/context plan; D02/D10/D11/D21 map to C02/C03; D13/D14/D19/D22 map to C09/C10; D15/D18 map to C08; D16/D17/D20 map to C04/C06 and the mailbox/continuation contract.

R23-R29 retain fixed core cardinality/direct references, generic continuation and exact attribution/lifetime duties. R27 now preserves reader semantics while making placement C10, correcting the earlier roadmap-derived mandate. R15 similarly distinguishes preferred local ownership from an absolute shared-index ban. C12 source rebuild, C03 retained-owner deferral/stable objects, C11 MCS queue and C04 retained KD physical-R11 mapping are selected. Private queue/claim, adapter/bridge and managed source orchestration are connected through c6becf81; exact target integration and lifetime/progress proof remain outstanding. None of these selections reopens the fixed one-core/original-JIT model. The mutex timing policy is the explicit limited exception to earlier immediate-release requirements.

The acceptance register is T01 through T56. T01-T51 retain their audit identities and chosen-target scope. T52 adds special-path/bypass/shared-join behavior, T53 safe callee returns/caller fallthrough, T54 local temporary-GPR PUSHFQ/POPFQ effects under AS01, and T55 target downgrade versus the candidate-only exception. T56 preserves a deferred, unrun future original-backend mapping comparison without a speed/AS01 claim; it is not an active R11 optimization question or current-baseline implementation gate. These remain unrun acceptance specifications; private graph-helper checks and source/static review of compiler/C protocol code do not satisfy them. T15-T19, T25/T26, T41/T45/T48-T51 now attribute the selected deferred-release phases and lifetime limits rather than requiring early physical availability.

### 3.2 Authority audit and correction register

N IDs identify this normative-origin audit, distinct from the historical v0.6 A01-A41 register. "Corrected" means the audit changed the text's authority/classification, not that a mechanism was implemented or validated. Historical source observations remain E, not architecture or support claims; old numeric receipt records are outside the active main tree.

| ID | Reviewed coupling / origin | Current classification and correction | Decision / affected sections |
| --- | --- | --- | --- |
| N01 | Latest explicit target versus inherited architecture | F/S govern the target; source presence alone gives no mandate. Operational editing/testing rules remain in force | Overview authority rule; all five files |
| N02 | "Existing S_W/storage" implied a complete current core or mandatory reuse | F requires one thread-owned core and direct second-level users; fresh physical layout is allowed, current packet sharing is E | C02, protocol section 3, P1/T48 |
| N03 | Two-word args, 168 bytes/offsets, reserved registers, object size or entry offsets treated as fixed ABI | C04 explicitly retains KD physical R11 as canonical-packet base, not all old private offsets/layouts. C12 source rebuild is selected; complete target input/materialization/API contracts still need implementation/proof | C04/C12, JIT section 3, T12/T50 |
| N04 | Roadmap local-reader lane promoted to fixed direction | Placement is P; concurrency/mode/API/context are S. Origin-local is conservative initial P, with no unselected remote support | C10, R27, support matrix/T27/T46 |
| N05 | Current hotness, waiter pinning/parking, owner words, pool sizes and family order | E/P mechanism/rollout choices, not target invariants; prove selected eligibility/context/capacity/progress | C01/C02/C05/C11, P1/P3/P7 |
| N06 | OSQ plus delegation and separate links required everywhere | Conditional on a selected dual-membership backend. S requires every selection/cancel/progress/retirement duty; a merged/different protocol needs equivalent proof | C11, selected contexts/P1/T49 |
| N07 | Exact authority equated with an inherited backend or implicit S_W grant transfer | C03 now selects retained responsible physical outer-combiner context for deferred mutex unlocks; the transferable proposal is superseded. Exact source/deferred/physical phases and owner checks remain required | C03, protocol section 5, T15/T51 |
| N08 | Current pop/array/index/registry shape promoted to lifetime law | C02 uses direct MCS state pointers and stable task-owned initial backing, without a borrowed-state registry. Exclusive binding, valid retained references and final access before reuse remain mandatory; allocation/control layout and exact lifecycle wiring remain separate | C02/C05, R09/R10/R15, T25 |
| N09 | Lease counters, completion subleases, session-only/image-count retention | E/P storage/reclamation choices. S is valid text/code/return/object lifetime through actual last use and nonstranding drain | C06/C09, JIT sections 2.3/5.3, T29/T30 |
| N10 | Five CALL edges, compatibility depth, 32 ledger rows and other budgets | Five-edge discovery is the explicitly approved current default P, not immutable F. Other capacities/encoding and any change to the default require a deliberate P choice with bounded completion | C08/C05, JIT sections 1.2/5.2, T24/T44 |
| N11 | One build/upload owner, fd staging, receipt encoding or daemon organization | E/candidate P solutions; S is candidate isolation, coherent publication, exact cumulative coverage acknowledgement and valid restart/reset | C08/C09, JIT section 5, T31-T37 |
| N12 | Current signal/reader/downgrade/IRQ/debug exclusions read as permanent bans | E support limits and P initial scope/extension choices; no new route/configuration is claimed. Linux 7.0 x86_64 non-PREEMPT_RT remains fixed F | C01/C10, support matrix/P7 |
| N13 | Terminal native suffix read as only possible architecture | Terminal suffix is conservative P; no replay/exact state is F/S. Resumable service/reentry requires an explicit new contract, never automatic old-cursor revival | C04/C06/C10, JIT section 4.3 |
| N14 | "Preserve current implementation first" made architectural | Declared API/context/lifetime duties and evidence classification remain; selected mutex deferral is an explicit limited timing policy, not native parity. Independent source rebuild/fresh layouts are selected | C01/C03/C12, P0-P8 |
| N15 | Queue scheduling lifetime and persistent request/control lifetime conflated | C05 selects task-owned persistent request records for normal local/proxy selection. Finite explicit caller capacity includes concurrently live nested requests and every retained release/control/return/image/current-native user. The supported workload guarantees availability; exhaustion is documentation-only, with no handler/recovery/local fallback or new special assertion. Provisioning/reuse/lifecycle proof remains work; no deployment value or unbounded claim is supplied | C02/C05, selected storage/T48/T49 |
| N16 | Deferred/unproved general flags/SIMD text could become a new gate | AS01 is the user's explicit assumed-correct iteration scope, not evidence; no separate general subsystem/shadow/gate, with local PUSHFQ/POPFQ simulation the exception | JIT section 3.5, C04, T54 |
| N17 | Broad admission/frontier wording could reject a whole root | Ordinary trusted-source translation is target intent; recognized special instructions clip only affected paths. Keep safe alternatives/joins/returns and exact reached handback without replay | JIT section 1.3, T43/T52/T53 |
| N18 | Experimental typed proxy downgrade could weaken target boundaries/native semantics | Retained writer/admission and same-root exception are E only; target mode handling/native equivalence remain separate decisions. Stable point/merge does not prove a consumed branch or general flags correctness | Section 2.7, C10, T55 |
| N19 | Reserved packet-base versus resident logical R11 treated as an active optimization choice | User selected retention of KD physical-R11 canonical-packet-base mapping. Optimization discussion/T56 are deferred, unrun future work; selection implies no measured gain or general equivalence evidence | JIT section 3.1.1, T56 |
| N20 | Immediate outer physical release treated as unconditional | Latest user selection supersedes it only for ordinary-mutex out-of-order outer unlock: retain responsible combiner, defer/notify/unwind, handle and continue normal batch/release. Extra waiting is accepted without generic native timing/progress parity | Protocol section 5, P5, T15/T51 |
| N21 | Retained context or source unlock marker treated as lock-object lifetime | Initial mutex lane now requires stable lock-object storage through actual physical release/final access. Caller establishes validity; owner/control allocations and exact source/return/notifier users can outlive release, and callback code stays through return. Availability-dependent handshakes retain stated progress limits | Protocol section 3.2/5, C03, T16/T17 |

## 4 TCLock guidance and limits

Borrow TCLock's lock-protocol idea: an outer combiner can become an inner
waiter/combiner and restore its outer combining state. Delegation, arbitration,
waiting, recursive combining and release remain parts of the lock. Do not
replace the original JIT with a native borrowed-stack engine or introduce a
separate execution worker architecture.

Task-owned persistent requests and auxiliary control are selected under C05.
Normal local/proxy selection uses the unified persistent path; the supported
workload guarantees availability within finite explicit caller capacity covering
all concurrently live and retained records. Exhaustion is documentation-only,
without a separate local fallback, recovery handler or new special assertion.
Bounded call-local role control still needs its own last-user proof.
Source comparisons do not prove the target's retention, stack/resource
bounds, cache layout, native API behavior or progress. The explicit user-selected
ordinary-mutex outer-unlock deferral is the limited accepted policy; comparison
source alone selects no other shortcut, borrowed-stack engine or kernel target.
The selection creates no spin/rwlock/rwsem/downgrade exception and proves no
generic native release-timing/progress parity. The user also selected an MCS
queue, whose optional local/proxy/origin-combiner arbitration and lifetimes must
be implemented with the original UB JIT/KD GS lowering and one S_W. It does not
mechanically select TCLock's complete native borrowed-stack protocol.

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
compiler/decoder/planner/lowerer and original backend, selected private ABI,
MCS/release protocol, canonical state/JIT bridges, task-owned auxiliary entry,
exact RCU image users and connected in source ordinary/recursive mutex episodes,
existing-grant native unlock, final auxiliary cleanup and task progress at
`ce423858`, plus reviewed setup composition, source epochs, artifact input maps,
image-owner retention and stateless copied-exit facts at the commits listed in
section 2.1. Reviewed `5989fbbb` additionally implements the kernel miss-fact
pool/producer claims and exact publication/ACK bridge; `af997cb6` implements the
host cumulative coordinator described there. Checkpoint `40ae39ce` adds concrete
immutable-contract source snapshots/native holds, cold task storage/retained-stack
words and the separate kernel shutdown SETTLED API. `236c287a` and `80095bfb`
connect fd control, executable loading, the GNU host pipeline, managed fork/exit
and fsynced archival settlement. `c6becf81` supplies exact source-slot/base
export; `97130fe4` adds the exact-target installer and focused-check source.
The later 12 focused VM checks passed on `c6becf81`; they execute no kernel path.
Legacy implementation, receipts and datasets remain in preservation history;
none must be restored to claim source progress or select another kernel target.

C12 source rebuild, ordinary-mutex C01, C03 retained-owner deferral and stable
lock-object storage, C11 MCS, C04 physical-R11 mapping, C02 direct MCS pointers,
C05 task-owned auxiliary entry/persistent requests with supported-workload availability and C06/C09 quiesced RCU replacement are selected. R11 optimization/T56 stay deferred. Remaining
deployment source/configuration/GS identities, finite resource counts and full
stack/context provisioning are listed in section 2.1 and the plan. Managed task
lifecycle, provider/channel/executable/compiler orchestration and archival
settlement have source. Crash/restart reconstruction beyond that workflow is not
implemented. Exact target application/build and all runtime/context/lifetime/
progress acceptance evidence remain unrun.

Source/static inspection covers the new kernel components. The 12 focused VM
checks on `c6becf81` additionally exercise compiler/learning/wire/archive and real
GNU image construction, as recorded in section 2.1. They establish no executed
kernel mutex/JIT/lifecycle, retirement or performance result. T01-T56 stay unrun;
the older ten helper checks remain tied only to `13f2630f`.

An earlier staged whitespace check excluded only the original patch template's
required unified context markers before tab-indented source; the full check
reported those format lines. Its recorded `git apply --numstat` result was five
additions in sched.h and four in fork.c. Preserve that earlier parse-only
observation: it is not application evidence for the later managed lifecycle
template or exact-target installer, compilation or behavioral validation.
