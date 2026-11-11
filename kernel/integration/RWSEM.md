# Generic Linux rwsem binding

This source lane extends the source-rebuilt Linux 7.0 x86_64, non-PREEMPT_RT
primitive. It now has [focused compilation and baseline checks](../../tests/evidence/kernel6-focused-20261111/README.md)
and [full build/linked-image identity](../../tests/evidence/kernel6-build-20261111/README.md).
The exact [kernel6 boot](../../tests/evidence/kernel6-boot-20261111/README.md) and
[native API and real syscall checks](../../tests/evidence/kernel6-native-api-mm-20261111/README.md)
passed. These bounded checks use the ordinary task-context contract below; they
supply no broader context, MM JIT or performance claim. Private reader fixtures
provide separate generated-execution mechanism evidence.

## One selected object and one gate

The exact target installer adds an optional `kd_binding` pointer to Linux's
`struct rw_semaphore`, initialized to NULL in static and dynamic initializers.
An unselected object follows its original Linux implementation. A selected
object routes every ordinary, callable, constructor, signalable, try, query and
nonowner API to the same `kd_rw` reader gate and MCS writer queue. Native count,
owner and wait-list fields never provide parallel exclusion for that object.
MM bodies, mmap trace calls, sequence counters and surrounding data structures
retain their native ordering and behavior.

The caller cold-initializes a `kd_rwsem`, a `kd_rw_native_pool` and an explicit
array of native records, then calls `kd_linux_rwsem_bind`. The binding, lock,
pool, records and callback code survive all API, queue, grant and final object
accesses. Binding is immutable while the object is reachable. Bind and unbind
require caller-established exclusion of **all** entry, waiters, held grants,
observers and final accesses across the transition. Merely seeing an unlocked
count, no contention or an idle pool cannot establish this exclusion. Busy
checks supplement that proof; they do not supply it. No automatic allocation,
selection, global task registry or mmap-specific lock protocol is introduced.
The actual Linux owner-query symbols also have GPL exports in the rebuilt
configuration, so module callers observe the same generic dispatch.
Every user of a selected object, including try and query callers, must remain
in the selected IRQ-enabled ordinary-task lane for its entire bound lifetime.
Objects with atomic, IRQ or NMI users or implicit perf observers are outside
this binding contract. Thread-count and quiescence checks cannot establish that
object-wide exclusion. Internal context errors describe a violated precondition;
a nonzero negative value is not a supported boolean try failure or safe runtime
refusal. Native Linux try/query interfaces have wider context behavior, which
this lane does not claim. Unselected objects retain those native interfaces.

Selected bindings currently refuse lockdep, DEBUG_LOCK_ALLOC and DEBUG_RWSEMS;
these configurations have no supported bound-object lane.

Native records contain physical control and exact credits, without an S_W or
register packet. The user-provided finite capacity guarantees an available
record for every supported need, including held credits, waiting calls and
canceled writers whose MCS membership still lives after `-EINTR`. Capacity is
not a nesting-depth bound or a deployment default. Exhaustion remains a
support limitation; there is no storage wait, recovery/fallback or new special
assertion. Owned native grants on an already attached task also link into its
exact `native_grants` list; attach precedes its first selected owned grant.
This list retains the root through release and blocks detach/exit while live.
Nonowner credits remain object-owned and can outlive their acquiring task.

## API and continuation behavior

Ordinary void source macros acquire-load the immutable binding and test
`source_calls` before reaching five distinct generic clobber entries. DI is the
actual KD lock pointer. Original-task eligibility and managed/native credit
selection run inside the native bootstrap, before source lending. Unprepared,
source-closed or native-credit-blocked acquisition uses the same KD native gate.
Unbound and source-disabled objects retain their normal callable route.

Active nested requests obtain W's canonical state from their direct
`node->state`. Before preparing a generic operation, the driver validates that
current JIT binding and the retained origin header's exact core identity.
It preserves source-closing/native-credit admission and latest-owned READ
ordering. An operation requiring native execution returns to W before executing
the operation, preserving its exact CALL phase; W then reaches the same alias's
native bootstrap. W's occupied
auxiliary entry is expected during borrowed execution and is not a refusal.
The exact root entry address is retained as small frame metadata. Private entry
identities, one canonical packet, auxiliary switching, the original UB backend,
GS lowering and current-state handback remain unchanged.

The C eligibility, prepare and query helpers and normal callable symbols remain
permanent SPECIAL frontiers. They are never reclassified as ordinary code by
learning or inferred to be typed entries from names or DI shape. This new
boundary-routing source has independent static review but no build or runtime
receipt; the kernel6 evidence below covers its earlier source identity.

Signalable read/write and try APIs initially use their normal C result ABI and
execute locally on the same KD gate. Successful signalable acquisition returns
0; interrupted acquisition returns `-EINTR` without a grant. Actual readiness
wins before pending signal cancellation. Try returns 1 or 0 and publishes no
queue membership on failure. An interrupted queued writer can return before
its predecessor releases; its persistent queue user remains until exact turn
selection or predecessor removal finishes. No source packet is allocated for
these calls and no unused typed result-return extension is added.

A shared active-reader ledger orders actual managed and native credits. Owned
`up_read` chooses the most recent exact credit for that original task across
both routes. Nonowner acquisition/release uses separate real credits, choosing
an actual eligible credit under the same guard, with no source-task dependency.
Queries report physical gate state and speculative owner identity; they never
create a hold or authorize release. A physical-task native grant also prevents
starting unrelated inner source batching before that task's new local grant,
preserving the existing extra-cycle restriction.

Native downgrade installs a real read credit before ending writer admission;
matching read release consumes that credit once. The private JIT-consumed
selected downgrade is unchanged: it retains the exact physical WRITE grant
through its logical read tail and matching typed UP_READ, including exact
native suffix handback. A native syscall downgrade observation alone cannot
prove that the JIT-consumed retained-write path executed.

## Directly affected validation

The compatibility fixture uses real Linux lock APIs on a private selected
object. The separate [userspace mmap/munmap workload](../../tests/kernel/mmap_api/README.md)
executes actual system calls, mapping effects, unmapping and fresh exact-address
reuse. Its control interface performs binding/routing/lifetime operations only;
it calls no MM test body. Initial real-MM selection uses `source_calls=false`,
so it needs no dummy source provider or task state and makes no MM JIT claim.
All compilation, project parsing and execution run only in the VM after source
review, fresh idle/space and exact recovery/identity checks. Skips, timeouts,
compile failures and unrun stages are not passes. Real syscall completion, KD
physical grants, native downgrade, JIT entry, returned generated body and
performance remain separate evidence.

The kernel6 native receipt records all twelve API cases passing with all 19
workers joined. Four syscall workers completed 64 iterations each, with zero
errors and exact mapping, absence, byte-effect and address-reuse observations.
The selected gate observed 1,285 native write grants, 772 ordinary write
releases and 513 real downgrades; 1,544 read grants plus those downgrades match
2,057 read releases. Actual END retired the idle, clear gate, followed by
ordinary unload of both modules. These counts include setup and cleanup and
are not syscall-count equivalents or performance measurements. Per-gate JIT
observation was unavailable.

The same image also passed [GS5 and the private rwsem/mutex regressions](../../tests/evidence/kernel6-private-regressions-20261111/README.md).
They retain the original backend and GS lowering, fixed-image continuation,
retained-writer handback and exact physical release/retirement checks. These
private mechanism results remain separate from the original-task native MM
run, broader context/progress obligations and the full acceptance matrix.

## Delegated syscall integration in progress

Actual delegated/JIT mmap/munmap remains unimplemented and unvalidated. The
ordinary void-entry routing above removes an early eligibility-helper frontier;
it does not enable the syscall roots' integer `down_write_killable` entry.
The next package needs a declared integer capture/return ABI, managed
cancel/grant arbitration, managed parent/child enrollment and complete immutable
source/dependency/native leases. The current MM provider remains
`source_calls=false`; killable operations execute on the original task through
the same KD gate with their existing native result and signal semantics. This
is an interim route, not the final delegation design. Query/assert frontiers,
executor context and source lifetime remain separate reached constraints.

The selected cancellation policy distinguishes an ungranted requester C from
an already-granted W. Selection or an MCS turn is not a grant. Actual grant
readiness wins over signal cancellation at admission; a committed acquisition
returns 0 before body effects and cannot later become `-EINTR`. If C has no own
grant but is serving W, C stops accepting new borrowers, finishes the current
W and its exact physical/release duties, and lets the existing lock-owned queue
pass subsequent service to another eligible combiner before C returns
`-EINTR`. The signal response is intentionally delayed; source effects are not
undone, replayed or interrupted through a guessed continuation.

The current supported workload excludes this specific circular dependency:
R retains a READ grant until C reports cancellation, while ungranted C is
serving W whose WRITE admission waits for R. No additional handling is selected
for that excluded pattern. This usage assumption is not general progress proof
and waives no grant, result, handback, task/object/storage or reclamation duty.
Other dependency and context limits remain explicit.

The selected storage direction allows task exit after `-EINTR` while exact
remaining queue users retain the existing core/register packet, request/control
backing and required task/stack/source/image references. This is not permission
to exit with an executable continuation or an outstanding physical owner duty.
Current managed exit still requires full drain: a new metadata-only detach and
finalization authority, requester-only cleanup before exit and callback-return
code retention need implementation and proof. No second packet or generic RCU
delay substitutes for those last-user obligations.
