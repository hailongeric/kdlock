# Generic Linux rwsem binding

This source lane extends the source-rebuilt Linux 7.0 x86_64, non-PREEMPT_RT
primitive. Its earlier kernel6 source has [focused compilation and baseline checks](../../tests/evidence/kernel6-focused-20261111/README.md)
and [full build/linked-image identity](../../tests/evidence/kernel6-build-20261111/README.md).
The exact [kernel6 boot](../../tests/evidence/kernel6-boot-20261111/README.md) and
[native API and real syscall checks](../../tests/evidence/kernel6-native-api-mm-20261111/README.md)
passed. These bounded checks use the ordinary task-context contract below; they
supply no broader context, MM JIT or performance claim. Private reader fixtures
provide separate generated-execution mechanism evidence.
The later integer/cancellation source `0c97cd34` has separate
[kernel7 focused and full build evidence](../../tests/evidence/kernel7-build-20261111/README.md),
including retained preparation and final-idle failures. Kernel7 has no boot or
behavioral result here. The subsequent v3 typed-query core `0d42063e` has
separate [kernel8 build](../../tests/evidence/kernel8-build-20261111/README.md),
[boot identity](../../tests/evidence/kernel8-boot-20261111/README.md), and
[native API and real syscall receipts](../../tests/evidence/kernel8-native-api-mm-20261111/README.md).
Those actual syscall checks use `source_calls=false`; they do not establish
generated MM execution or typed query reentry.

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
boundary-routing source is included in the kernel7 focused/full build receipt,
with no runtime receipt for that image. Kernel6 covers its earlier source identity.

Callable signalable read/write and try APIs use their normal C result ABI and
execute locally on the same KD gate. Legacy bindings also keep the killable
writer macro on this route. Successful signalable acquisition returns
0; interrupted acquisition returns `-EINTR` without a grant. Actual readiness
wins before pending signal cancellation. Try returns 1 or 0 and publishes no
queue membership on failure. An interrupted queued writer can return before
its predecessor releases; its persistent queue user remains until exact turn
selection or predecessor removal finishes. No source packet is allocated for
these callable operations. The explicit source opt-in described below has a
separate result-bearing capture contract.

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

The [bounded kernel8 syscall run](../../tests/evidence/kernel8-mm-prefix-20261111/README.md)
records actual mmap/munmap completion with 144 and 103 borrowed JIT prefixes.
Four source regions stop at staged CALLs to omitted `do_mmap` and
`do_vmi_munmap`: their CALL stack effects are already applied, and original W
resumes at the unexecuted callee entry without replay. Full protected-MM JIT
completion remains unvalidated. Source changes after the kernel6 receipts add
integer capture, managed cancellation and queue-only storage retirement. Source
`0c97cd34` has independent source review and the separate kernel7 focused/full
build receipt. No kernel7 boot or kernel7 mechanism/MM JIT result is recorded.

`kd_linux_rwsem_bind` always sets `killable_source_calls=false`, preserving the
interim original-task native route. The new cold
`kd_linux_rwsem_bind_killable_source` explicitly selects both ordinary source
macros and the integer `down_write_killable` alias. It requires complete managed
task, request, auxiliary, source and native resources before publication. The
private integer entry uses the same four-input clobber contract; EAX is the
explicit result. Native preparation returns a two-word entry/result descriptor.
Managed operation kind 15 commits EAX and DONE only after exact grant or cancel
arbitration. Earlier operation and observation identifiers remain stable.

Initial managed killable capture is original-task/root-only. A proxy reaching
a nested killable entry hands the untouched operation to W before preparing it;
logical-origin signal notification for a separate foreign nested waiter is not
implemented. W then reaches the same alias and KD gate. This scope does not
establish arbitrary nested killable delegation.

An optional pure executor predicate is checked before each generated fragment.
A refusal uses existing exact native handback at the current cursor and grant.
The MM profile requires non-NULL matching current/origin mm identities. This is
an additional restriction, not proof of hardware-current, per-CPU, scheduling,
RCU, uaccess, fault-fixup or auxiliary-stack context equivalence. Normal query/assert
callable helpers remain SPECIAL frontiers; neither entering JIT nor
publishing an image proves that a meaningful MM body ran through generated code.

The optional metadata-only ABI2 MM profile cold-creates an immutable source
provider, runtime and original owner state before binding. Its module opt-in
defaults to false. ABI1 retains its existing layouts and native-only behavior.
Actual activity must still come from userspace mmap/munmap syscalls. The
provider with the generic context frontiers has separate
[earlier compilation evidence](../../tests/evidence/kernel8-provider-build-runner-ast-20261111/README.md).
The [later ioctl fix](../../tests/evidence/kernel8-mm-ioctl-frame-build-20261111/README.md)
reduces its fixed RSP reservation from 1,912 to 704 bytes without warnings.
That provider was loaded for the scoped prefix run only. The original JIT,
GS lowering, canonical S_W and generic rwsem path remain unchanged.

The trial declares 64 KiB of control space within a 128 KiB auxiliary allocation.
Its [44,024-byte conditional budget](../../tests/evidence/kernel8-aux-context-review-20261111/README.md)
includes measured KD frames and two assumed inclusive 16 KiB native allowances.
The user selected those native-helper/callback allowances as an experimental
premise. Their footprints and the complete auxiliary requirement are not proved
by this result. Independent scheduler, IRQ, unwinder and handback review remains
separate from that premise. These values are trial inputs, not deployment defaults.

The selected cancellation policy distinguishes an ungranted requester C from
an already-granted W. Selection or an MCS turn is not a grant. Actual grant
readiness wins over signal cancellation at admission; a committed acquisition
returns 0 before body effects and cannot later become `-EINTR`. If C has no own
grant but is serving W, C stops accepting new borrowers, hands back or finishes
W's current continuation, drains its exact physical/release duties, and
completes its own queue handoff before returning `-EINTR`. Subsequent grants
remain with the existing lock-owned queue; their actual execution need not
precede C's return. The signal response is intentionally delayed; source
effects are not undone, replayed or interrupted through a guessed continuation.

The current supported workload excludes this specific circular dependency:
R retains a READ grant until C reports cancellation, while ungranted C is
serving W whose WRITE admission waits for R. No additional handling is selected
for that excluded pattern. This usage assumption is not general progress proof
and waives no grant, result, handback, task/object/storage or reclamation duty.
Other dependency and context limits remain explicit.

The queue-only deferred-exit source lane permits task exit after `-EINTR` when
all executable continuation, physical owner, grant, image, auxiliary and native
endpoint duties have ended. Exact canceled queue users retain the existing
core/register packet, frame arrays, auxiliary allocation, original task/stack
and native lease until final queue access. A preheld per-frame actor bridges
the final pool API return; its last callback queues a built-in finalizer under
the storage guard. The worker performs metadata-only retirement, then drops
backing and calls the cached native release while holding its code owner.
Neither a task reference, a counter nor an RCU delay substitutes for last use.

Other residue still follows current-task exact drain. In particular, historical
physical-owner records must be reaped before this queue-only detach can qualify;
broader asynchronous owner-record retirement is not implemented. A task cannot
exit with an executable source continuation or an outstanding physical duty.
The [bounded kernel8 killable fixture](../../tests/evidence/kernel8-managed-killable-20261111/README.md)
records readiness before cancellation, cancellation while a reader remains held,
actual queued-task exit before predecessor release, foreign waiter notification,
and C returning `-EINTR` after W's physical release. W's later source unlock
return is a separate event. The fixture preserves exact physical and storage
retirement checks and all 19 actual child exits. It supplies mechanism evidence
for these scenes, without establishing
general nested cancellation or progress. The earlier exit-ACK wait cycle and
claim-validator failure remain preserved with their separate ordinary recoveries.

## Typed physical query source lane

A later source change adds distinct `is_locked` and `is_write_locked` entries.
The fresh v3 installer routes the existing inline rwsem query/assert branches
through these source forms on source-enabled bindings, using one acquired
binding pointer. It preserves the original WARN condition and unbound native
body. `KDLOCK_RWSEM_CALLABLE` definitions and normal C query addresses retain
their native route and SPECIAL classification. V2 applications and their frozen
kernel7 receipts are not upgraded in place.

Queries are explicit source operations, separate from acquisition, release and
mode change. Appended operation kinds 16/17, runtime boundary 5 and IO detail 4
leave earlier identifiers and the packet, IO and wire layouts unchanged. The
current node's canonical S_W and a dedicated operation identity carry the exact
CALL form. The driver reads the actual KD physical gate under its family guard,
commits boolean EAX once and returns through the existing source-stack adapter.
It creates no request, grant or credit and changes no owner or mode. Original
tasks complete the same predicate locally without capture or stack lending.
Observation 44 records the physical result and exact query kind independently
of acquisition events.

`is_write_locked` remains true during the selected retained-read tail because
its physical WRITE grant is still held. A real/native downgrade creates READ
and makes that predicate false. Neither query proves logical-task ownership or
authorizes release. This extension supplies no MM helper model and no task,
per-CPU, RCU or fault-context equivalence. Unsupported reached operations keep
exact native handback. The query core compiled and booted as kernel8. Its
[eight directly affected boundary cases and linked GS checks](../../tests/evidence/kernel8-affected-build-20261111/README.md)
passed after the separately retained test-input correction. The independent
[kernel8 rwsem query and mutex regressions](../../tests/evidence/kernel8-private-regressions-20261111/README.md)
also passed. The rwsem receipt records typed predicates through shared READ,
WRITE, retained logical READ with physical WRITE, and native real READ after
downgrade. These query observations do not establish generated MM completion.


## Native RCU and page-table context boundary

The optional MM profile supplies four generic permanent SPECIAL entries:
`__rcu_read_lock`, `__rcu_read_unlock`, `_raw_spin_lock` and
`_raw_spin_unlock`. The shared host scanner propagates their classification
to the actual source CALL before it executes. These records provide no
execution service or MM helper model. Registered entry implementation CALLs
remain implementation code, and SPECIAL returns are not generated fragment
entries. Inline context effects and IRQ/BH/NMI variants need their own exact
boundary or operation contract.

Static inspection of the linked kernel8 image identifies an RCU interval
before the PTE lock: `__pte_offset_map` calls `__rcu_read_lock` at
`0xffffffff81841237`; `pte_offset_map_lock` later calls `_raw_spin_lock` at
`0xffffffff8184159c`. The spin entry increments physical preemption depth at
`0xffffffff8276ccf5`. Normal PTE cleanup calls spin unlock at
`0xffffffff8181e89a`, then RCU unlock at `0xffffffff8181e89f`; retry and flush
paths have their own releases. A cut only before spin acquisition would
already be inside RCU. These linked bytes describe a possible source path;
they are not evidence that a generated syscall reached it.

Full generated protected-MM completion requires a generic context protocol
beyond these frontiers. Physical C must retain exact native RCU/PTL duties,
while any immediate first-unexecuted native handback must let W execute its
suffix with valid local context and route each matching release to C through
its final ACK. C cannot schedule while its native PTL preemption pin is open;
if W can run only on that occupied CPU, waiting for W to release cannot make
progress. Direct native W unlock balances the CPU executing W and does not
automatically discharge C's preemption duty.
The sleepable outer rwsem pump, root-family atomic reconciliation, same mm
and origin GS substitution do not supply this route. Declining before the
first context effect preserves the existing exact handback. Delaying that
handback or releasing and reacquiring native context would change the selected
contract. Neither policy is introduced by the frontier table, and this source
lane supplies no full protected-MM completion claim.
