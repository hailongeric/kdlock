# kdlock

The [current evidence checkpoint](docs/design/kdlock_redesign/04_evidence_and_reconciliation.md#current-evidenced-checkpoint)
records exact build/boot, focused checks and live attempts, preserving failures,
partial execution and the limits of each result. Source, publication, returned
execution and performance remain separate evidence classes.

An incremental, independent rebuild for **Linux kernel 7.0, x86_64,
non-PREEMPT_RT**.

## Current state

The [fixed-image recursive fixture](tests/evidence/runtime-recursive-20261110/README.md)
returned `protected_jit_recursive_mechanism_pass` on kernel3. It records complete
protected JIT episodes, actual CA → CB → CA execution on one canonical S_W,
and separate original-owner physical release and final request-retirement
observations. The unprotected C-function epilogue remains native. This is bounded
ordinary-mutex mechanism evidence; it establishes no general progress,
performance, whole-kernel or real-world syscall/API result. Earlier partial
attempts below retain their original evidence boundaries.

The kernel4 fixture at `db7d7d6e` records protected recursive JIT completion
for plain spin and a separate mutex regression. Plain spin uses IRQ-enabled task
context with actual preemption pins and synchronous physical-release ACKs.
The source provider now retains the exact built-in return-thunk bytes through
the existing ordinary compiler path. The earlier `0a07f678` source-frontier
failure and rejected recovery request remain separate historical records.
Renewed ordinary recovery completed before the corrected runs. Native C
function epilogues, general support, progress and performance remain outside
this fixture evidence.
[Current evidence checkpoint](docs/design/kdlock_redesign/04_evidence_and_reconciliation.md#current-evidenced-checkpoint).

The private [compiler front end](disassem/compiler.py) connects a finite,
immutable source snapshot to the original Miasm decoder and
[fragment planner](disassem/fragment.py). It retains complete decoded records,
source-operation boundaries, safe alternatives/joins, matched CALL/RET paths and
versioned observed indirect targets. Explicit entry roots share discovery budgets
and retain independent per-entry planning; another root supplies no CALL/RET
proof. Unknown targets invent no callee return.
Only direct CALL edges consume the selected five-edge discovery default; other
source/decode/CFG bounds are explicit caller inputs. Observations are compiler
inputs, not emitted-coverage acknowledgments or live feedback storage.

The [original-backend lowerer](disassem/lowering.py),
[mapper](disassem/backend) and [entry wrapper](include/wrapper.S) construct
source assembly under the selected physical-R11 packet-base mapping. They retain
actual source CALL/RET words, original GS/current-task lowering and local
PUSHFQ/POPFQ temporary-GPR handling. Typed operations, special frontiers,
construction gaps and resource exits remain path specific. The coordinated
private ABI is version 1: a 168-byte packet and 56-byte control IO. Focused host
checks assemble/link generated images with GNU tools. Separate live receipts
record generated prefixes, publication and learning stages with their exact
frontiers and native continuations in the current checkpoint.

The [artifact exporter](disassem/artifact.py) returns the same assembly with
coordinated C image/site metadata, exact source-version bytes, retained decoded
bytes/GS inputs and a construction receipt (`0c3ccb10`). The caller supplies the
actual retained source-epoch object; generated strings/descriptors are neither source leases nor publication acknowledgments.

The [source epoch](kernel/source_epoch.c) (`a660342c`) validates supplied
coherent version/region/configuration/load inputs and retains a lease already
established by the caller. The [image owner](kernel/image_owner.c) (`a23b82c1`)
binds exact construction inputs to that epoch and an existing code-provider hold,
then retains published slots through actual drain/grace retirement. These
components validate and retain supplied ownership. The concrete source
provider, executable loader and publication orchestrator described below supply
their live inputs; retention alone establishes no text-mutation exclusion.

The [copied-exit adapter](disassem/feedback.py) (`c9b468ee`) preserves exit
facts and derives only matched ordinary indirect CALL/JMP compiler inputs.
It implements no C08 storage, transport, capacity, persistence or coverage ACK.

C08 now selects a preallocated feedback-fact pool for JIT misses, with finite
explicit caller capacity sufficient for the supported workload. No numeric
capacity or unbounded claim is supplied. Pending facts or translation alone do
not disable new JIT/delegation; existing context/source/image checks still apply.
Facts keep source site, resolved target, exit/transfer phase and exact producer/
source-version identity. Valid same-version observations accumulate in compiler
input before building; fact capture, emitted coverage, actual publication and
ACK stay distinct, and uncovered/later facts remain pending.

Reviewed source commit `5989fbbb` adds the [kernel fact pool](kernel/feedback.c),
which records each reached coverage miss before exit consumption, using an
explicit pure target classifier. Exact record incarnations and claims separate
copied history from record reuse. A durable producer and source-epoch users retain facts independently of old code.
The [publication bridge](kernel/feedback_publish.c) binds only the validated
candidate input subset to its actual image transaction and returned old image;
a separate atomic ACK covers only that subset's emitted ordinary observations.
The current checkpoint separates actual publication and exact fact ACK from
construction. Nonobservations and uncovered misses remain pending during normal
execution. The selected shutdown route actually
archives exact facts/provenance with fsync and a content receipt, then marks
exact reservations SETTLED after images and native/JIT users drain. Settlement
is separate from coverage ACK; kernel receipts do not themselves perform archival
I/O. The kernel settlement API is source-implemented at `40ae39ce`. The actual host
archive and channel/runtime shutdown workflow are connected at `80095bfb`; they
have source review. Focused host checks exercise archive/codec components;
the earlier recovery receipt separately records zero-fact shutdown/settlement,
and the historical live3 prefix receipt records all eight pending facts
archived/SETTLED before ordinary unload.

The [host learning coordinator](disassem/learning.py) (`af997cb6`) retains finite
caller-bounded fact/claim/candidate/publication histories and merges valid
same-version observations before discovery, lowering and export. It preserves
nonobservations/foreign/late facts, freezes each claim's MERGED candidate inputs
and reconciles actual publication and exact ACK receipts separately. It performs
no kernel transport, persistence or publication. Its actual-object identity and
retention mapping remain caller duties. Focused host checks exercise this
coordinator, without actual kernel publication or ACK.

The [MCS mutex](kernel/mutex.c) supplies sleepable physical exclusion, optional
local/proxy selection and retained physical batches on top of the
[exact release protocol](kernel/mutex_release.c). Queue removal, source return,
physical release and record retirement have separate conditions. Source,
result/binding, child-return and notifier users retain their exact controls;
only the responsible physical owner releases/reaps its batch. The native-local
fixture completed eight ordinary lock/body/unlock iterations; earlier attempts
observed limited proxy-generated prefixes. The fixed-image fixture now records
nested protected JIT completion, deferred outer release and final retirement on
its exact task/request paths. General recursive/deferred correctness, progress,
performance and a complete public mutex lane remain unvalidated.

C05 uses task-owned preallocated persistent request records for the unified
ordinary local/proxy path. Simultaneously live requests use distinct records,
reused only after all exact users finish. The finite caller-supplied capacity
covers concurrent nested requests and retained physical-owner/release, return,
notification, image/binding and current-native-endpoint records, not just depth.
The supported workload guarantees an available record whenever one is needed.
Task attachment/resources supply the actual count; no deployment value or
one-node sufficiency is configured here. Pool exhaustion is a documentation-only
limitation, with no exhaustion handler, recovery/local fallback or new special
assertion. This is neither a mathematically unbounded pool nor a public error
result. A normal local winner still uses the same persistent request path.

At reviewed source commit `2c3f7cbc`, the [request pool](kernel/request_pool.c)
implements exact persistent-slot users/reuse and atomic final detach, and
[owner progress](kernel/owner_progress.c) retains actual physical-task batches
through deferred handling, physical release and later reaping. Task-root and
JIT/wait callbacks connect those components; source review is not execution.

The [canonical state](kernel/state.c) owns W's register packet exactly once.
The [JIT bridge](kernel/jit.c) connects exact execution bindings, image-bound
pending exits, once-only source operation transitions, MCS acquisition and
source unlock. A compiler-clobber root continuation skips the translated-CALL
pop recipe. [Native restore](include/native_resume.S) resumes exact IP/SP on W
under its declared retained-stack contract. Every active/nested MCS node points
directly to that same S_W. The [task root](kernel/task_state.c) contains one own
core and the task-owned auxiliary-stack header for initial entry, with no
registry or active-S_W task field. Its [Linux task patch](kernel/integration/README.md)
contains the task field and managed fork/failure/exit hooks as an unapplied
context template. The [exact-target installer](kernel/integration/apply_target.py)
(`97130fe4`) checks pinned whole-file contexts and stages new-inode replacements
for a separate target tree. Applied-tree evidence is separate from this
source/template description.

The [current-task setup helper](kernel/task_setup.c) (`57599619`) composes
caller-owned range checks, root attachment, episode-resource setup/binding and
exact unused-root rollback. Its teardown composes one progress pass and detach;
it supplies no allocator or automatic fork/exit/stack integration.

Source checkpoint `40ae39ce` adds [task storage](kernel/task_storage.c): cold
heap/request/frame/auxiliary allocations with explicit caller sizes and no
packet clear, setup-error retention and exact teardown before freeing. Its
[stack adapter](kernel/source_stack.c) independently holds the original kernel
stack for bounded single-word accesses. A native-provider lease spans the whole
declared source activity and releases last. The [managed lifecycle](kernel/lifecycle.c)
(`80095bfb`) prepares private unpublished children with independent core/pool/
auxiliary backing, unwinds failed clones and drains exact current-task users
before exit. Unmanaged tasks stay outside this lane. Exact target hooks were
applied and built; the managed fork/child-exit fixture passed. Full auxiliary
scheduler/IRQ/unwinder compatibility remains unproved.

The [source provider](kernel/source_provider.c), also at `40ae39ce`, pins the
complete supplied module set and copies actual source bytes under the selected
all-dependency immutable-text contract. The caller excludes every text mutator
through the final native/JIT/feedback user; module residency alone does not
freeze text. Version/configuration/load identities and the exact GS offset stay
explicit inputs. [Control](kernel/control.c), the [fd channel](kernel/channel.c),
[execmem image loader](kernel/compiled_image.c) and [runtime composition](kernel/runtime.c)
have source at `236c287a` and `80095bfb`. The loader reserves the real code address
before the host [GNU image builder](disassem/image_builder.py) assembles and links
there. The loader validates typed metadata; control publishes through the exact
image-owner transaction.
The [host session](disassem/session.py) and [wire codec](disassem/wire.py) drive
actual claim, stage, commit and separate ACK commands with retry identities.
`c6becf81` exposes the exact source slot and nullable current image baseline for
that workflow. Focused VM checks exercise host compiler/codec/archive and real
GNU construction. Live2 failed before STAGE_LOAD; the separately retained live3
attempt published one image and returned eight generated prefixes at the same
unsupplied compiler-produced target before inner B. This establishes neither a
complete protected JIT body nor recursive JIT execution.

Reviewed source commit `ce423858` connects the
[ordinary source pair](include/kd_mutex_api.h),
[native bootstrap](kernel/mutex_api.c) and
[serial episode driver](kernel/episode.c). Distinct operation CALL targets enter
the persistent request path; the driver consumes exact image exits and serial
child returns, then exports before deferred notification. Empty/closing root
images can decline proxy eligibility while retaining normal persistent local
acquisition. Native unlock uses its existing exact grant and hardware CALL/RET,
without a new request slot or stale packet restoration.

The [prepared prefix](include/kd_mutex.h), [stack switch](include/mutex_entry.S)
and [native entry preflight](kernel/native_entry.c) preserve source SP/IP/BP and
switch wait/control code to the task-owned auxiliary stack before lending W's
source stack. Exact PREPARED/ENTERED/COMPLETE phases retain auxiliary occupancy;
the final auxiliary actor closes only after all entry/binding reads, before
restoring the current canonical native continuation. The
[native task progress helper](kernel/task_progress.c) connects owner progress,
episode/grant actor collection and pool collection. These paths have independent
source review and bounded native/fork/protected-JIT observations, without
complete stack/lifecycle proof. See the
[integration guide](kernel/integration/README.md).

The [image slot](kernel/image.c) uses RCU lookup plus exact linked users for
sleeping/suspended execution, source and return dependencies. New admission
closes before replacement; publication requires all active users to drain and
old readers pass a grace period before reclamation. JIT entry reserves a
separate claimed pending-exit use, which ordinary put cannot drop early.

Source commit `a65016e3` adds opt-in [Kbuild](Kbuild)/[Kconfig](Kconfig)
packaging for the original 15 C units and three concrete assembly entries, with
the fixed Linux 7.0/x86_64/non-RT C target gate. It excludes the unexpanded image
wrapper and supplies no automatic API conversion or provider/lifecycle policy.
Kbuild at `5989fbbb` added the fact pool and publication bridge for 17 C units
at that revision. At `c6becf81`, Kbuild lists 26 C units and the same three concrete
assembly entries. `1b50e373` adds scalar observations for 27 C units and the
same three entries; the kernel3 build has its own exact receipt. The
[build guide](kernel/integration/BUILDING.md) records
exact-tree prerequisites; actual core/full-build results have separate receipts
in the current evidence checkpoint.

The declared source path is connected through `c6becf81`: managed task storage/
lifecycle, immutable-contract source/native holds, fd control, executable image
construction/publication, cumulative learning and exact fsynced shutdown archives
with separate SETTLED. This is source functionality, not a running learning
service or complete integrated kernel support. Exact target application/build
and fixture-specific provider/configuration/GS inputs now have receipts. General
deployment capacities and complete auxiliary/control-stack context proof remain
outstanding. Recovery of a session after a
crash/restart is not implemented by retaining an archive alone. No general deployment
request/fact count or complete control-stack budget is configured.
Generated execution requires a distinct physical task
and admitted nonoverlapping executor/source/wait-control stacks. W's own body
uses a native route; a runtime instruction budget does not establish stack
separation. The fixed-image fixture establishes its protected JIT episodes;
compilation, earlier native/prefix checks and that bounded result do not establish
a complete runtime support claim.

The VM focused pipeline checks passed **12/12** on `c6becf81`, including the real
GNU cpp/as/ld/objcopy image-construction case. The frozen 99-file input remained
unchanged; Python was 3.14.4 on `7.0.0-38-kdlock1`, with unchanged boot and taint 0.
These are host-pipeline mechanism checks, not kernel mutex/JIT/lifecycle execution.
The [later multi-entry receipt](tests/evidence/multi-entry-pipeline-20261111/README.md)
records separate 4/4, 12/12 and corrected-config 5/5 passes on `18c8f2e4`, while
retaining the initial zero-test GS refusal and failed aggregate. It executes no
generated code. The older ten planner cases remain tied only to `13f2630f` and
Python 3.10.12.
The exact-target installer was added at `97130fe4`; subsequent target
application/build, installation and boot have separate receipts linked from the
current checkpoint. The retained
[focused receipt](tests/evidence/runtime-pipeline-20261110/README.md)
(`c6fbf7bb`) records the exact limits. T01-T56 remain unrun. See the
[evidence limits](docs/design/kdlock_redesign/04_evidence_and_reconciliation.md#21-rebuild-status).

Read the design in order:

1. [Overview](docs/design/kdlock_redesign/00_overview.md)
2. [Lock protocol](docs/design/kdlock_redesign/01_lock_protocol.md)
3. [Original JIT contract](docs/design/kdlock_redesign/02_jit_contract.md)
4. [Implementation plan and open decisions](docs/design/kdlock_redesign/03_implementation_plan.md)
5. [Evidence and reconciliation](docs/design/kdlock_redesign/04_evidence_and_reconciliation.md)

C12 is selected: source-rebuilt integration with fresh private layouts and no
compatibility promise for old binary lock/object layouts. C01 starts with
ordinary mutex lock/unlock in sleepable task context on Linux 7.0 x86_64 without
PREEMPT_RT. A later selected plain-spin extension supplies IRQ-enabled,
preemption-pinned task-context source operations at `2d0ad60b`. The corrected
kernel4 fixture records scoped protected recursion and exact release/retirement
for that lane. These selections authorize implementation scope. Other API/context lanes retain their
own outstanding validation. C03 now selects TCLock-style out-of-order outer
mutex unlock deferral: retain the responsible outer combiner, notify/unwind to
it, continue its normal batch protocol and physically release through that
protocol. Extra waiting is accepted; this is not a generic native release-timing
or progress-parity claim. The earlier transferable-grant proposal is superseded.
C11 now selects an MCS queue for the initial mutex lane. C04 retains the KD
physical-R11 canonical-packet-base mapping; R11 optimization discussion and T56
are deferred future work. Private local/proxy arbitration and adapter bridges now have source
implementations connected to the managed provider/compiler workflow. Exact
target build/boot and limited native checks are recorded; complete recursive
correctness/progress remain unvalidated. Selecting MCS does not select TCLock's borrowed-stack
execution or complete the integration.

The initial mutex lane now requires stable lock-object storage through actual
physical release and the backend's final object access. A source unlock or
deferred marker cannot authorize destruction/reinitialization. Owner/control
storage, including any containing allocation, must remain valid through its
separate source/return/notifier last users after physical release; callback code
remains retained through its return. The selected contract permits a correctly
materialized post-unlock continuation without waiting solely for physical
release/object lifetime. The private bridge now implements explicit CALL/return/cursor phases;
a marker alone authorizes no arbitrary execution. Whole-lane integration and
runtime correctness remain unvalidated. Availability-dependent source
handshakes keep their stated progress limits.

## Git history

`archive/before-main-20261109` at
`7ce7db54334960fe0d9db2c425c5c581cdedf4b0` preserves the complete tracked tree
plus the eight pre-rebuild modified/untracked files, including the original five
redesign documents and comparison audit. Its parent is the untouched `master`
revision `2e9016915632ab4a488f444d06fe881ffcca0616`.

Legacy implementation, guides, results and deployment-specific content have
been removed from the `main` tree through a normal descendant commit. History
has not been rewritten. The original checkout, its untracked/ignored evidence
and other linked worktrees remain unchanged. The preserved material is not a
current implementation or support promise. No changes have been pushed.
