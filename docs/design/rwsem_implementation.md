# Sleeping KD reader/writer semaphore

[`kd_rwsem.h`](../../include/kd_rwsem.h) provides an explicit sleeping reader/writer
object using the selected KD-only physical mutex for admission. Readers and
writers execute locally. Neither acquisition publishes a delegation request,
and no Linux mutex or Linux rwsem backs the object. The selected legacy mutex
queue, batching, ABI2 and published-waiter protocol are unchanged.

## API and scope

`DEFINE_KD_RWSEM()` and `kd_rwsem_init()` initialize static and dynamic objects.
`kd_down_read()` / `kd_up_read()` permit concurrent, sleeping readers.
`kd_down_write()` / `kd_up_write()` provide exclusive, sleeping writers. Read and
write trylocks return 1 on success and 0 on failure. Interruptible and killable
read/write acquisitions return zero on success and `-EINTR` on cancellation,
without leaving reader or gate ownership behind. Killable acquisition ignores
nonfatal signals. An immediately available acquisition may succeed despite a
pending signal, as with the physical mutex API.

`kd_downgrade_write()` converts an ordinary writer to a reader without admitting
an intervening writer; finish with `kd_up_read()`. `kd_rwsem_is_idle()` is an
inspection helper after callers have stopped and joined. It is not an admission
primitive and cannot replace source/frame drain for other provider users.

All participants must adopt this API for the same object. Do not access the
embedded gate directly or pass either object to Linux lock APIs. There is no
delegated outer-writer API, reader-to-writer upgrade, recursive locking guarantee,
non-owner release API, IRQ/BH variant, lockdep integration or RT support. This is
not a binary/layout-compatible replacement for Linux `struct rw_semaphore`.
The translator explicitly refuses these APIs inside an enclosing delegated body,
including calls discovered while learning a helper. The execution ledger has no
rwsem ownership mode or downgrade/cancellation contract; ordinary availability
does not make them valid nested JIT lock controls.

## Admission and ordering

The physical KD mutex gates admission. An atomic count records admitted readers.
A reader first observes the whole gate owner word as zero, publishes its count
with a fully ordered increment, then rechecks the owner word with acquire
ordering. Owner flags also close this fast path. A failed speculation rolls back
without touching protected data. Slow readers acquire the physical gate, publish
their count and release the gate; they never enter the delegation queue.

A writer acquires and retains the gate, executes a full barrier, then sleeps on
the drain wait queue until the reader count is zero. The reader's
increment/recheck and writer's gate/barrier/count check prevent both from missing
the other's admission. Speculative counts may overlap an executing writer, but
those readers cannot access the payload. The final reader's fully ordered
decrement precedes `waitqueue_active()` and wakeup, pairing with the writer's
enqueue and condition recheck to avoid lost wakeups.

A cancelled writer first removes its drain waiter through the wait-event helper,
then releases its KD gate before reporting `-EINTR`. Cancellation while acquiring
the gate uses the selected KD mutex's existing wait-list removal and handoff
rules. Downgrade publishes a reader count before releasing the gate, forcing any
successor writer to wait for the downgraded reader.

This is a gate/count construction, not a port of Linux's optimized rwsem reader
batching and fairness policy. No throughput advantage is implied by its design.

## Why the archived delegation cannot be copied unchanged

The prior implementation remains reachable at
`archive/task/sleep-rwsem-snapshots` (`82f92db`). Its ordinary gate/count interface
is the basis of this port. Its delegated writer integration depends on the
rejected owned-mutex protocol and is not compatible with the selected mutex:

1. The archived mutex combined writers during unlock, after the physical writer
   had already drained readers. The selected legacy queue can execute delegated
   bodies during acquisition, before an outer writer macro returns. Placing
   reader drainage after that macro would allow a delegated writer to overlap
   admitted readers.
2. In the selected mutex, `cookie.owner == 0` identifies every routed acquisition,
   including physical queue owners and some native fallbacks. It does not prove
   that this execution is a synthetic delegated entry. The archived conditional
   reader wait would therefore also miss some physical writers.
3. Published legacy producers poll with preemption disabled. A sleeping reader
   can retain a read count on a CPU subsequently occupied by a pinned writer;
   that reader then cannot resume to release its count. A pre-batch reader-drain
   hook alone does not resolve this progress problem.

Reserving a writer before queue publication can close reader admission and drain
existing readers before any producer becomes pinned. That is not a complete
solution when ordinary downgrade is allowed: a physical writer can create a new
reader after peers have already passed their drain check and published requests.
A correct delegated design must order that transition against publication, or
introduce a separately specified API that cannot downgrade. It must also retain
exact ownership, source leases, result acknowledgements and frame retirement.
Restoring the old owned mutex or parked producers is not part of this port.

## Mmap and validation boundaries

Sleeping/killable acquisition and downgrade are useful prerequisites for an MM
lock experiment. They do not integrate this object into `mm_struct::mmap_lock`.
That requires coordinated replacement of every reader/writer, Linux helper and
lockdep contracts, fault/VMA lifetimes, retry and lock-mode transitions, and
kernel configuration validation. Ordinary sleeping access does not establish
that `access_remote_vm()` or other task-dependent bodies can be delegated.

The [ordinary API probe](../../tests/kernel/rwsem/README.md) checks concurrent
sleeping readers, writer/late-reader exclusion, one-CPU scheduling progress,
trylocks, downgrade, both cancellation sites and final drain. No ordinary probe
result counts as returned-JIT evidence. The [current validation receipt](../../bench/results/10.176.26.71/tests/feature-reintegration-20261018/README.md)
records the passing probe and 24 Native/KD workload sessions. Historical delegated results remain in
the [archived receipt](../../bench/results/10.176.26.71/tests/rwsem-snapshots-20261015/README.md)
and must not be presented as validation of this implementation.
