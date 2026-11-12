# Ordinary mmap and munmap syscall checks

This directory starts a bounded real syscall check for the main rebuild. It is
independent of master's mmap1 workstream. The userspace program invokes actual
`SYS_mmap`, `SYS_munmap` and `SYS_mincore`. Kernel MM bodies are unchanged. No
extracted kernel body or ioctl performs the mapping work. The client has passed
an [unselected syscall baseline](../../evidence/kernel6-focused-20261111/README.md),
and the provider has a [module build and signing receipt](../../evidence/kernel6-api-build-20261111/README.md).
The [selected native-gate run](../../evidence/kernel6-native-api-mm-20261111/README.md)
passed with four workers and 64 iterations each, including actual native
downgrades, exact retirement and ordinary provider unload. This supplies no
generated-execution or performance result.

The later [kernel8 ABI2 syscall run](../../evidence/kernel8-mm-prefix-20261111/README.md)
passed three rounds of eight workers and eight iterations each: 192 completed
worker iterations, 576 mmap successes and 384 munmap successes. Raw records
join 144 borrowed mmap prefixes and 103 munmap prefixes to their actual source
CALLs and native callee-entry handback. All 247 pending facts were archived and
settled without coverage ACK, followed by ordinary unload. Full protected-MM
completion remained false for both roots. Incidental and arena calls are outside
the worker counts; no performance or physical batch-chain claim follows.

The [provider frame fix](../../evidence/kernel8-mm-ioctl-frame-build-20261111/README.md)
compiled without warnings and reduced the fixed ioctl RSP reservation from
1,912 to 704 bytes. The trial used 64 KiB control space inside 128 KiB auxiliary storage
under the user's explicit experimental native-helper stack premise; this is not
a measured all-kernel or complete auxiliary bound.
[AUX review and premise](../../evidence/kernel8-aux-context-review-20261111/README.md).

The caller supplies all three required positive decimal arguments:

```text
userspace --threads N --iterations N --deadline-ms N
```

All pthread workers share one mm. Before starting them, the parent reserves an
anonymous private arena containing one disjoint two-page slot per worker, with
one untouched guard page on either side. Every worker is created before the
start gate opens. During the check, workers allocate only their own fixed slot
and the controller joins them before releasing the arena. This ownership keeps
one worker's reuse check separate from another worker's mapping operations.

Each complete iteration performs these actual operations in order:

1. Replace the worker's owned `PROT_NONE` slot with a two-page anonymous private
   read/write mapping. Read every byte as zero, write a deterministic pattern
   and read every byte back through volatile accesses.
2. Unmap both pages. Check each page separately with `mincore`, requiring
   `ENOMEM` for each absent mapping.
3. Map the exact same address with `MAP_FIXED_NOREPLACE`. Require the returned
   address to match, verify fresh zero contents, write a second deterministic
   pattern and read it back.
4. Unmap both reused pages and check each absent page again. Restore the slot's
   `PROT_NONE` reservation with `MAP_FIXED_NOREPLACE` before another iteration.

For each complete worker iteration, the explicit workload counters therefore
contain three mmap successes, two munmap successes, four mincore checks and one
successful address reuse. Fresh-zero reads, pattern writes and pattern readback
each cover four times the actual page size. The parent's initial arena mmap and
final whole-arena munmap are separate. Libc/pthread setup may perform additional
system calls, so these counters describe this program's explicit workload calls
rather than every MM operation by the process. Partial attempts preserve actual
per-worker counters and the first operation/errno/iteration/offset failure.

A final JSON object on stdout reports completion status, caller bounds, process
and thread IDs, arena/slot addresses, elapsed time and each worker's raw counters.
Elapsed time covers the start gate through worker joins, before control cleanup.
The syscall success status is `syscall_completion_pass`. Without a control
device, `kd_observations` is `not_collected`. Optional native-gate observations
appear separately under `selected_gate`, with `kd_observations` set to
`native_gate_only`. `overall_pass` additionally requires successful selected-gate
retirement when that option was requested. A borrowed-JIT claim would require
separate same-mm task-group enrollment, source/code leases and exact JIT
provenance. The ABI1 profile creates no S_W, image or dummy source provider.

The monotonic deadline is cooperative between finite userspace phases. An
in-flight syscall must return before its cleanup can finish. A supervising
controller must retain an incomplete attempt and must not infer task or kernel
drain from a timeout. An unsuccessful run is not a syscall-completion pass.

## Optional native-local binding

The [provider](payload/provider.c) exposes the fixed-width metadata ABI in
[abi.h](abi.h). Its START, QUERY and END ioctls never perform mmap, munmap or an
extracted MM body. The source-rebuilt Linux rwsem interface routes the selected
`current->mm->mmap_lock` through one KD gate. START always sets `source_calls`
false, so original-task callable operations use that gate without canonical
state, generated execution or a JIT enrollment requirement.

```text
userspace --threads N --iterations N --deadline-ms N \
  --control-device /dev/kd_mmap_api --native-capacity N --quiescent-mm
```

The caller starts this dedicated process with one thread before pthread creation
and guarantees that all mm-lock traffic and external users are quiescent across
selection changes. It excludes other mm users for this scoped check. The
`--quiescent-mm` option explicitly supplies that contract. A thread count, an
unlocked count or an idle snapshot cannot establish it. Every selected-object caller, including implicit perf, IRQ or NMI readers and
queries, must satisfy the ordinary IRQ-enabled task-context lane throughout the
selected interval. Such asynchronous users are excluded from this dedicated
workload contract; a single-thread/current-mm check does not prove their absence.
The provider requires privileged control and an exclusive open file. Native capacity is the explicit
finite count covering held credits, waiters and canceled queue/control users,
not just the thread count. It selects no default or exhaustion recovery.

START cold-allocates the gate, native pool and records before publishing the
binding. A module hold, task reference and mm reference retain that backing
through every native API and queue user. `mmgrab` retains the containing mm/lock
allocation. It does not retain `mm_users` or prevent `exit_mmap`; later exit
operations keep using the selected gate until a complete ordinary END.

After joining workers and unmapping the arena, the client checks QUERY's current
owner-thread count within the remaining explicit deadline. This corroborates
the caller contract because a pthread join wake can precede final kernel thread
accounting. END requires that exact original owner/current mm, caller-established
quiescence, an idle native pool and a clear gate. It unbinds before unregistering
and synchronizing the scalar listener and freeing backing. The open file retains
module entry/return code independently through the final selection-hold drop.
Later MM calls after the completed unbind use the original native backend.

The listener counts explicit native read/write acquire/release, real downgrade,
cancel and try-miss events on the exact selected gate. Queue/physical counts are
separate diagnostics and never stand in for a native writer grant. Live QUERY
counts are observations; final idle/retirement still needs the actual core
predicates and the caller's last-user exclusion. Counts include all selected
interval activity, such as pthread setup and cleanup, and are not syscall-count
equivalents or timing results. The selected check requires nonzero native read,
write and real-downgrade observations, no counter overflow and exact retired
object identities. The native-only route is configured by `source_calls=false`.
At actual retirement, the client also checks native write acquires equal ordinary
write releases plus real downgrades, and read releases equal read acquires plus
those downgrades. It checks addition overflow first. These event balances are
consistency observations beside the actual pool/gate predicates and caller
quiescence contract. They confer no release authority or independent drain proof.
Generic JIT-entry events have no object identity, so this per-gate listener
reports `jit_observation_available=0` and collects no JIT-entry count. Its zero
`jit_entries` value supplies no generated-execution absence proof.

A failed output copy may follow a completed START or END. The client reconciles
QUERY metadata and never assumes the error undid the operation. Busy END keeps
the binding and all references. On cleanup-required failure, the original owner
emits and flushes diagnostic JSON, retains its mm and open fd, and waits. After
inspecting the retained state and establishing quiescence, an operator can send
`SIGUSR1` to that recorded PID for one owner-side END retry. The handler only sets
a `sig_atomic_t` flag. No workload operation is replayed, and a failure remains
recorded even if later ordinary cleanup succeeds. Do not kill the retained owner
or force module unload. A failed thread gate/join leaves worker drain unverified
and requires inspection before any END, rather than attempting a signal retry.

Closing a selected fd or exiting its owner supplies no quiescence proof. The
provider keeps `cleanup_required`, the binding and its module hold. It performs
no guessed owner-exit or foreign-owner cleanup. The successful path completes
END before closing the file and permits ordinary module unload afterward.

All compilation and execution belong in the VM after the overall implementation
and static review are complete. The focused client build used the VM's explicit
C compiler with `-std=c11 -O2 -Wall -Wextra -Werror -pthread`; retain the actual
compiler identity, command, copied source hash, stdout, stderr and return status.

The reusable [source boundary helper](../../../disassem/source_boundaries.py)
accepts version-bound exact target metadata. Existing private KD clobber entries
keep typed LOCK/UNLOCK/MODE_CHANGE cuts. Ordinary callable Linux APIs receive a
permanent SPECIAL pre-operation frontier and return to original native execution.
The helper retains exact decoded CALL bytes and prefixes, introduces no helper
model or new backend, and establishes no runtime object-binding or lifetime proof.

## Optional source profile

The ABI2 profile is separate from the kernel6 ABI1 receipt. Kernel8 linked from
core `0d42063e`, and its five affected modules compiled and signed from snapshot
`140aecc4`. Two runner syntax checks passed. A separate continuation at test
source `4cc53e09` passed eight source-boundary and five linked GS checks. That
test-only correction rebuilt no module. The VM remained on normal boot
`afb0c5cd`, with no kernel8 boot, selected profile or generated MM execution in
these receipts. The provider's read-only `enable_jit_profile` module parameter
defaults to false. The selected object uses one generic KD rwsem gate. Native
MM bodies, surrounding data structures and syscall semantics are unchanged, and
every workload effect comes through the common userspace
`SYS_mmap`/`SYS_munmap` body. [Kernel build](../../evidence/kernel8-build-20261111/README.md),
[affected builds and checks](../../evidence/kernel8-affected-build-20261111/README.md)

START_JIT accepts explicit source/dependency, version, configuration/load/GS and
finite runtime/native capacities. It copies the region list and version once;
userspace addresses are never leases. The observer is registered before source
capture. Source provider, runtime and actual original owner enrollment precede
the final `kd_linux_rwsem_bind_killable_source` publication. Managed pthread
children receive independent task-owned cores and retain their own canonical
S_W. The same-mm executor predicate is additional restriction only; it does not
establish hardware-current, per-CPU, scheduler, RCU, uaccess, fault-fixup or
auxiliary-stack equivalence. Immutable complete dependencies and the declared
context/workload contracts remain caller obligations.

The shared native-context table
supplies the existing runtime boundary interface with four SPECIAL entry
addresses: `__rcu_read_lock`, `__rcu_read_unlock`, `_raw_spin_lock` and
`_raw_spin_unlock`. Page-table mapping enters RCU before its later PTL spin
acquisition, so a spin-only cut would already be inside read-side context.
The table stops at the actual API entry before its physical effects. A host
scanner may additionally cut before the actual source CALL. The entry table
alone can leave that CALL's return word already staged. Inline context effects
and IRQ/BH/NMI variants require their own exact metadata. This supplies a native
prefix continuation, not physical-context service, mixed-family execution or
full protected-MM completion. The default-disabled profile and ABI1 behavior
are unchanged. [Reusable metadata](../payload/native_context_boundaries.inc)

The ABI2 client requires `--jit-config`, `--jit-config-bytes`,
`--jit-phase-timeout-ms` and `--jit-rounds`, alongside explicit ordinary workload
bounds, `--control-device` and `--quiescent-mm`. Its configuration file is the
272-byte little-endian `{abi, contracts, config}` header from [abi.h](abi.h), with
both pointer fields zero, followed by the exact region array and source-version
bytes. `config.native_capacity` is authoritative; the ABI1 `--native-capacity`
option is not accepted in this profile. All extents and identities are retained
in the controller's input receipt.

The original owner emits `jit_ready`, then waits for a fresh SIGUSR2 to run one
ordinary syscall round. Each round joins its pthreads and unmaps the arena before
emitting `jit_round_complete`. A fresh SIGUSR2 advances another requested round;
SIGUSR1 instead starts LEAVE. Old phase signals are discarded before each
marker. Workload deadlines apply separately to each round, and phase deadlines
bound controller pauses. The host can learn from the cold round and publish an
image before the next round without replaying any completed syscall.

LEAVE closes the original owner's source admission and attempts exact storage
retirement. It retains binding, native pool, source, raw observations and compiler
channel. After `jit_owner_left`, the host finishes claims, sends SHUTDOWN,
archives exact facts durably, settles them, sends END and closes the channel.
Only a fresh SIGUSR1 after that marker permits the original owner to request
END_JIT. END requires actual runtime/channel/source drain and no exact raw-reader
memberships, then unbinds, destroys source and unregisters the observer before
freeing backing. A failed setup, syscall round, output copy or retirement keeps
its actual roles queryable. Later cleanup does not turn the failed run into a
pass. A timeout proves no drain; retain the owner/mm/fds for reviewed recovery.

The [VM-only controller](runner.py) composes the existing source export,
cumulative learning, GNU image builder, feedback and shutdown sessions. It
requires one explicit pinned configuration JSON and retains actual source,
wire, GNU objects, publication/ACK, raw events, archive and retirement receipts.
It admits roots only by exact request-incarnation/grant/continuation joins and
prefix-aware decoded source CALL bytes. It uses no MM helper-name model or
second translation backend.

ABI2 raw events come from `/dev/kd_mmap_api_events`. Each open owns a frozen
20-word-record prefix; reopen to collect later events and final overflow. The
native status prefix still reports JIT observation unavailable. Its zero
`jit_entries` is not an absence result. Join raw SLOT, GRANT, original state,
physical executor, image and source records before reporting delegation or
execution. Publication, JIT entry, returned fragment, actual MM-body coverage,
syscall completion and final retirement are separate findings. Ordinary callable
query helpers remain SPECIAL. Typed physical predicates have their own exact
operation/return route. Other reached boundaries can still stop generated
execution early, and a returned prefix does not establish meaningful MM-body
delegation.

The v3 recipe compiled into kernel8 adds explicit typed physical rwsem queries
for the existing inline assertions. This is a generic lock API service, with no
MM body or helper model. Kernel7's frozen integer/cancellation image does not
include it. Linked kernel8 identity and GS checks still require actual boot
verification before live use. Meaningful protected completion requires generated
UP_WRITE and current-JIT episode completion for mmap, or the same retained
grant's downgrade/read tail/UP_READ physical ACK followed by its selected
post-UP_READ handback for munmap. [Linked kernel8 evidence](../../evidence/kernel8-build-20261111/README.md)

The [completion reporter](completion.py) and runner integration have separate
[synthetic and syntax receipts](../../evidence/kernel8-host-completion-boundaries-20261111/README.md).
The actual prefix run retains zero protected-completion counts; it does not
validate positive full-MM witnesses. The reporter uses bounded ELF64 symbol
metadata only to attribute the two actual MM root CALL spans. Per-round frozen
event prefixes retain positive and rejected request-incarnation candidates.
A prior handback or non-typed miss prevents a completion claim. Every accepted query must return to its exact post-CALL entry.
Physical ACK, release users, request slot and shared owner retirement are joined
separately. The existing prefix verdict and cleanup workflow are unchanged.

`meaningful_returned_mm_body` is promoted only when at least one mmap protected
range and one retained-downgrade munmap protected range have complete witnesses,
all requested syscall rounds pass their actual effects, and ordinary shutdown,
archive/settlement, channel close, provider retirement and unload complete.
`completion-round-*.json` and `protected-completion-final.json` retain the
reporting details. These witnesses belong to passed real-syscall rounds. Current
scalar records cannot identify a particular worker iteration/address or prove
that an individual selected mmap returned success. They establish no complete
C-function return or context equivalence.
