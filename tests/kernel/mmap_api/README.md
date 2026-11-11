# Ordinary mmap and munmap syscall checks

This directory starts a bounded real syscall check for the main rebuild. It is
independent of master's mmap1 workstream. The userspace program invokes actual
`SYS_mmap`, `SYS_munmap` and `SYS_mincore`. Kernel MM bodies are unchanged. No
extracted kernel body or ioctl performs the mapping work. The source has not
been compiled or run yet, and it establishes no KD, generated-execution,
downgrade or performance evidence.

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
provenance. This provider creates no S_W, image or dummy source provider.

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
and static review are complete. A future focused build can use the VM's explicit
C compiler with `-std=c11 -O2 -Wall -Wextra -Werror -pthread`; retain the actual
compiler identity, command, copied source hash, stdout, stderr and return status.

The reusable [source boundary helper](../../../disassem/source_boundaries.py)
accepts version-bound exact target metadata. Existing private KD clobber entries
keep typed LOCK/UNLOCK/MODE_CHANGE cuts. Ordinary callable Linux APIs receive a
permanent SPECIAL pre-operation frontier and return to original native execution.
The helper retains exact decoded CALL bytes and prefixes, introduces no helper
model or new backend, and establishes no runtime object-binding or lifetime proof.
