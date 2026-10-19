This static review covers candidate commit
`c2f0d9c596cc4cdd9ce765a89e4e75c37b688cc9`, replacing runtime `372be89`'s shared
packed waiter count with versioned per-node records and owner-only phase stores.
No performance conclusion follows from this inspection. VM build, test and
measurement receipts remain separate evidence; this reviewer performed no
builds or tests on the source host.

The 32-byte, native-aligned mutex retains physical owner, wait lock, OSQ,
sleeping ring head, 32-bit delegation phase and encoded delegation tail.
`count_seq` and `counted_lock` occupy existing node padding at offsets 88 and 96.
Build assertions retain the 320-byte node, packet offset 128 and notification
offsets 304/305. Neither the physical sleeping ring nor the OSQ algorithm changes
in this candidate.

In [kd_mutex_state.h](../../../../../include/kd_mutex_state.h), FREE-to-ACQUIRING
remains a full-width atomic CAS. Only the reserved gate owner changes a busy
phase, so these changes use `atomic_set_release()`. HELD follows completed
physical acquisition. RELEASING is stored before physical unlock: every physical
release path, including handoff, uses a release owner CAS. A succeeding ordinary
owner's acquire therefore orders the preceding RELEASING store before its own
ownership check. FREE release follows the complete physical unlock and is the
old owner's final gate access. A successor claiming FREE cannot have its phase
overwritten afterward. There are no mixed-size byte/word atomic accesses.

`kd_mutex_delegation_owned()` still accepts only `current`, verifies the physical
owner pointer, rejects PICKUP, and requires HELD or COMBINER. PICKUP designates a
successor before acquisition and does not grant ownership. Restricting the query
to current prevents an unrelated observer from combining owner and phase reads
from different acquisitions. ACQUIRING and RELEASING exclude the two ordinary
owner windows around delegated physical acquisition and release.

Each migration-pinned origin alone updates its reserved node's counted record.
Entry and exit remain at the former shared-counter boundaries: entry follows
the tail exchange, and exit precedes return from the published queue path.
An enclosing combiner stays counted across early outer release and reacquisition.
Each update verifies the exact expected key, rejects odd or overflowing sequence
values, then writes odd sequence, write barrier, new key, write barrier, even
sequence. Node release rejects a live key or odd sequence and preserves the
generation across reuse. No queue entry/exit allocates, scans remote nodes or
performs a shared count RMW. Tail publication, node completion and native ACK
ordering retain their existing roles.

[mutex/count.inc](../../../../../kernel_module/mutex/count.inc) provides the cold
diagnostic count. It allocates per-call sequence scratch with `GFP_ATOMIC` and
reads each record as acquire sequence, key, read barrier, sequence validation.
After all records are collected, a read barrier precedes a second pass validating
every saved sequence. Unchanged nonwrapping versions establish overlapping
stable intervals with a common cut between passes. Slot exit/reentry using the
same lock address still changes the version and cannot pass as unchanged.
Eight failed attempts return `-EAGAIN`; scratch failure returns `-ENOMEM`.
Neither becomes an estimate or a successful zero. The diagnostic API does not
authorize acquisition or object lifetime.

Per-object idle checks avoid allocation and inspect exact keys only after that
object's callers stop and join; activity on another mutex does not prevent its
reuse. This precondition is essential. Global controlled drain independently
rejects odd or nonempty records, each CPU's waiter/reservation/slot state, and
active task acquisition identities. Existing frame, source lease and native ACK
checks remain. Immediate gate owners and detached combiners retain their task
references; record retirement does not substitute for those lifetimes.

The auxiliary address table, auxiliary references and auxiliary registry locks
remain absent. The existing task-routing cache still uses exact references,
bucket locks and RCU; native ACK serialization and the physical sleeping
`wait_lock` also remain. This change does not claim to remove all locks, all RCU
or all cacheline contention from the mutex subsystem.

Static fixture review checks adversarial A-to-B movement that would make a
single sweep report an impossible count, same-key reuse, persistent changes,
odd records, allocation refusal and node reuse. Separate owner-window and
early-release fixtures retain current/PICKUP, frame and ACK assertions.
Userspace primitive substitutes use strong atomic ordering: they exercise
algorithmic interleavings but cannot prove the sufficiency of kernel memory
barriers or detect every barrier-removal bug. Kernel scheduling, stack switching
and performance require the separately recorded VM checks.
