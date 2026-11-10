# kdlock

An incremental, independent rebuild for **Linux kernel 7.0, x86_64,
non-PREEMPT_RT**.

## Current state

The private [compiler front end](disassem/compiler.py) connects a finite,
immutable source snapshot to the original Miasm decoder and
[fragment planner](disassem/fragment.py). It retains complete decoded records,
source-operation boundaries, safe alternatives/joins, matched CALL/RET paths and
versioned observed indirect targets. Unknown targets invent no callee return.
Only direct CALL edges consume the selected five-edge discovery default; other
source/decode/CFG bounds are explicit caller inputs. Observations are compiler
inputs, not emitted-coverage acknowledgments or live feedback storage.

The [original-backend lowerer](disassem/lowering.py),
[mapper](disassem/backend) and [entry wrapper](include/wrapper.S) construct
source assembly under the selected physical-R11 packet-base mapping. They retain
actual source CALL/RET words, original GS/current-task lowering and local
PUSHFQ/POPFQ temporary-GPR handling. Typed operations, special frontiers,
construction gaps and resource exits remain path specific. The coordinated
private ABI is version 1: a 168-byte packet and 56-byte control IO. No assembly
has been assembled, loaded or executed.

The [artifact exporter](disassem/artifact.py) returns the same assembly with
coordinated C image/site metadata, exact source-version bytes, retained decoded
bytes/GS inputs and a construction receipt (`0c3ccb10`). The caller supplies the
actual retained source-epoch object; generated strings/descriptors are neither source leases nor publication acknowledgments.

The [source epoch](kernel/source_epoch.c) (`a660342c`) validates supplied
coherent version/region/configuration/load inputs and retains a lease already
established by the caller. The [image owner](kernel/image_owner.c) (`a23b82c1`)
binds exact construction inputs to that epoch and an existing code-provider hold,
then retains published slots through actual drain/grace retirement. These are
retention/validation components, without a live-text lease acquirer, executable
allocator or publication orchestrator.

The [copied-exit adapter](disassem/feedback.py) (`c9b468ee`) preserves exit
facts and derives only matched ordinary indirect CALL/JMP compiler inputs.
It implements no C08 storage, transport, capacity, persistence or coverage ACK.

The [MCS mutex](kernel/mutex.c) supplies sleepable physical exclusion, optional
local/proxy selection and retained physical batches on top of the
[exact release protocol](kernel/mutex_release.c). Queue removal, source return,
physical release and record retirement have separate conditions. Source,
result/binding, child-return and notifier users retain their exact controls;
only the responsible physical owner releases/reaps its batch. No callback has
executed, and no performance or complete public mutex lane is claimed.

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
is an unapplied context template; the exact kernel tree is absent from main.

The [current-task setup helper](kernel/task_setup.c) (`57599619`) composes
caller-owned range checks, root attachment, episode-resource setup/binding and
exact unused-root rollback. Its teardown composes one progress pass and detach;
it supplies no allocator or automatic fork/exit/stack integration.

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
source review, with no execution or complete stack/lifecycle proof. See the
[integration guide](kernel/integration/README.md).

The [image slot](kernel/image.c) uses RCU lookup plus exact linked users for
sleeping/suspended execution, source and return dependencies. New admission
closes before replacement; publication requires all active users to drain and
old readers pass a grace period before reclamation. JIT entry reserves a
separate claimed pending-exit use, which ordinary put cannot drop early.

Overall integration remains incomplete. Actual task allocation/fork/exit and
provider glue, actual coherent live-source lease acquisition/mutation admission,
executable allocation/publication orchestration, C08 compiler transport/cumulative
feedback policy and exact kernel/build wiring remain work. No deployment pool count or complete auxiliary/control-stack budget is configured.
Generated execution requires a distinct physical task
and admitted nonoverlapping executor/source/wait-control stacks. W's own body
uses a native route; a runtime instruction budget does not establish stack
separation. No build system or runtime support is claimed yet.

All new components have source/static review only. Ten focused private planner
cases passed earlier on `13f2630f` with Python 3.10.12; they validate only that
older helper. No new decoder import, assembly, compilation, behavioral check,
VM work, installation or reboot has run. Further behavioral tests remain
deferred until overall functionality is complete. Acceptance specifications
T01-T56 remain unrun. See the
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
PREEMPT_RT; other lock families follow later. These are implementation scope
approvals, not support evidence. C03 now selects TCLock-style out-of-order outer
mutex unlock deferral: retain the responsible outer combiner, notify/unwind to
it, continue its normal batch protocol and physically release through that
protocol. Extra waiting is accepted; this is not a generic native release-timing
or progress-parity claim. The earlier transferable-grant proposal is superseded.
C11 now selects an MCS queue for the initial mutex lane. C04 retains the KD
physical-R11 canonical-packet-base mapping; R11 optimization discussion and T56
are deferred future work. Private local/proxy arbitration and adapter bridges now have source
implementations; their full integration and correctness/progress proofs remain
work. Selecting MCS does not select TCLock's borrowed-stack
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
