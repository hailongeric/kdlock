# Source review of the cacheline contention candidate

This review compares baseline `0987358` with candidate `76af844`. Commit
`0c5dbfe` contains the queue-head and outer-hint changes; `76af844` adds inline
ownership validation. The original candidate arm times these changes together.
There is no separately measured `0c5dbfe` arm, so a measured combined effect
cannot be divided among the three changes.

Commit `09ebd8f` adds the separate benchmark placement diagnostic. Its provider
bytes match `0987358`, and its default private lock declaration remains
unchanged. The diagnostic compile option and its actual loaded placement are
retained separately from the ordinary comparison. See [PLACEMENT.md](PLACEMENT.md).

## Runtime changes

The production diff touches exactly three files:

| File | Change |
| --- | --- |
| [mutex/waiter.inc](../../../../../kernel_module/mutex/waiter.inc) | Check the reserved head's successor before attempting shared-tail retirement |
| [kd_mutex_direct.h](../../../../../include/kd_mutex_direct.h) | Read the existing active-combiner phase inline in the bounded outer probe |
| [kd_mutex.c](../../../../../kernel_module/kd_mutex.c) | Inline the unchanged exact ownership predicate at calls within this translation unit |

The previous queue head always tried to change `delegation_tail` from its own
encoded node to zero after acquiring physical exclusion. If a successor already
existed, that compare-and-exchange necessarily failed. On x86 the locked
instruction can still request exclusive ownership of the line containing the
tail. The candidate avoids that unnecessary instruction when queue state already
proves that the head is not the last node. This is a code-path change; profiles
do not count how many cache-line transfers it saves.

The outer probe still reads the physical owner at most eight times and attempts
an acquire CAS only after observing the entire owner/flags word as zero. It still
ends probing when the gate says COMBINER and enters the same admission path.
Replacing `kd_mutex_combiner_active()` with its acquire-load/compare removes an
out-of-line call without changing the hint or granting ownership from it. The
ordinary owner read, full zero-owner CAS and WAITERS/HANDOFF/PICKUP handling
remain. The exported helper still exists for its other callers.

`kd_mutex_delegation_owned()` keeps the same predicate: the argument must be
current, the physical owner must be current with PICKUP clear, and an acquire
read must observe HELD or COMBINER. `__always_inline __gnu_inline` permits its
calls within `kd_mutex.c` to inline while retaining a callable definition for
other translation units. No owner or phase load is removed. The independent
physical-owner probes at body entry and frame retirement are unchanged.
The retained ELF and VM checks, rather than this source review alone, establish
the resulting machine code and runtime behavior.

## Queue-head lifetime and ordering

The new `kd_mutex_head_successor()` executes while its origin retains the exact
CPU/slot reservation and physical exclusion. Its cases are:

1. Acquire-load `curr_node->next`. A linked successor proves this head is not
   the last queued node, so return that successor without reading or modifying
   the shared tail.
2. If no link is visible, read the encoded tail. Only equality with the current
   reserved node justifies attempting the existing full retirement CAS to zero.
   A successful CAS returns no successor; a later publisher starts a new queue
   head and waits on the existing gate protocol.
3. A different tail, or a failed retirement CAS, means a publisher owes the
   predecessor link. Poll that link with acquire loads until it arrives, then
   continue with the same combiner path.

The tail comparison cannot suffer slot-reuse ABA during this interval: the
origin cannot release or reuse its reserved CPU/slot before this invocation
finishes. A stale equality cannot retire a racing successor, because the full
CAS still decides removal. A publisher that wins the tail exchange but has
not yet linked its node is handled by the existing delayed-link handshake.
The head never interprets a changed tail as permission to discard that request.

Publication still initializes the successor before the producer's full tail
exchange and subsequent predecessor-link store. The new acquire link loads
preserve visibility when the head no longer executes a full CAS. Physical
ownership and the gate-acquisition ordering are unchanged. Published origins
remain pinned and poll; this is not a parked-producer or oversubscription
redesign.

The focused fixture compiles the actual production helper and deterministically
exercises an already linked successor, uncontended last-node retirement, a
delayed link after a different tail, and publication racing the CAS. Six negative
controls require failure if the helper touches a known-successor tail, issues an
unnecessary RMW, skips the exact CAS, ignores a losing CAS, skips the delayed-link
wait or loses the successor. These checks do not prove all kernel interleavings
or weak-memory architectures. The outer fixture also covers all five gate
phases and verifies that only the zero-owner CAS can acquire the mutex.

## Storage and protocol preserved

The public definition, node definition, state/count helpers, physical mutex,
OSQ, queue reservation, batch engine, frame retirement and routing sources are
unchanged from `0987358` except for the three runtime files listed above.
In particular, no changes are made to `include/kd_mutex.h`,
`include/kd_mutex_state.h`, `kernel_module/kd_mutex_local.c`,
`kernel_module/kd_mutex_osq.c`, or the existing `count.inc`, `queue.inc`,
`combiner.inc`, `lifecycle.inc`, frame-lifecycle and mutex-routing implementations.

| Storage | Retained geometry |
| --- | --- |
| Public `struct kd_mutex` | 32 bytes, native 8-byte alignment |
| Physical owner / wait lock / OSQ / wait-head pointer | Offsets 0 / 8 / 12 / 16 |
| Delegation phase / encoded tail | Offsets 24 / 28 |
| Reserved `struct kd_mutex_node` | 320 bytes, 64-byte alignment, four slots per possible CPU |
| Exact count version / lock key | Node offsets 88 / 96 |
| Saved register packet / completion / polling byte | Node offsets 128 / 304 / 305 |
| Shadow stack | Existing preallocated 8 KiB per reserved slot |

The current FREE → ACQUIRING → HELD/COMBINER → RELEASING → FREE gate sequence,
KD physical owner, ABI2 wrapper, legacy batching/NUMA policy and all instruction
admission checks remain. The head helper changes neither the count interval nor
when a node, borrowed packet, frame, source lease or native unlock ACK may retire.
Early outer release/reacquisition and exact drain records remain intact.

There is no per-lock auxiliary hash, shared lock reference count, new registry
lock, auxiliary RCU mechanism, allocation or cleanup obligation. Existing
physical sleeping-waiter serialization and existing task-routing references/RCU
remain part of the established protocol; this change neither adds nor claims to
remove them. Equal native geometry still does not permit mixing Linux and KD
operations on one object.

## Interpretation limits

The offset-32 versus offset-40 diagnostic separates owner writes from the
gate/tail line. Gate readers and tail writers still share a line at both
placements, so it does not isolate every possible owner/gate/tail interaction.
Both offsets also use dedicated padding, unlike the standard private object.
An effect at eight workers cannot establish the same cause at sixty workers.

No HITM, cache-transfer or failed-CAS event counter is collected by these flat
cycle profiles. Notification polling can dominate sampled periods, and sampled
instruction offsets can skid. The fresh ordinary throughput and returned-JIT
measurements are therefore reported separately from placement and profiling
diagnostics. Exact ownership/lifetime checks are correctness evidence; they are
not replaceable with approximate heat or aggregate performance counters.

Validation scope is basic plus directly affected checks and the selected live
probes. This review does not establish whole-kernel replacement, RT/ww_mutex,
lockdep, arbitrary native placements, weak-memory portability or oversubscription.
