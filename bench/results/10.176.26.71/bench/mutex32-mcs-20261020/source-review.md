# Shared-node mutex source review

This historical review covers `f4d359d83e6b9ce54b4c4a10053f4e5c681ac204`
(shared optimistic-spin storage) and its parent
`7290327ddd89362a169333ecf6e274b1a3886a6f` (bounded FIFO continuation).
It records static source arguments, not VM validation or performance results.

## Geometry and independent memberships

On the captured x86-64 configuration, `struct kd_mutex` remains 32 bytes with
8-byte native alignment. Its fields are unchanged:

| Offset | Bytes | Field |
| ---: | ---: | --- |
| 0 | 8 | `owner` |
| 8 | 4 | `wait_lock` |
| 12 | 4 | `osq.tail` |
| 16 | 8 | `wait_head` |
| 24 | 4 | `delegation_state` |
| 28 | 4 | `delegation_tail` |

The preallocated `kd_mutex_node` remains 320 bytes, aligned to 64 bytes, with
four slots per CPU. The new 24-byte OSQ subrecord fills previous padding at
offset 104: `next` at 104, `prev` at 112, `locked` at 120, and immutable encoded
`tail` at 124. Exact waiter records remain at offsets 88/96, registers at 128,
and delegation completion/notification at 304/305. Lifecycle assertions check
these dimensions and native mutex size/alignment; callers still must use one
protocol consistently on each object.

This shares storage between two MCS-style memberships. It does not merge their
queues. `lock->osq.tail` identifies an abortable physical spinner;
`lock->delegation_tail` identifies a published delegation request. Their links
and notifications are separate because a reserved delegation head can remain
live while its optimistic-spin membership enters, cancels, or completes.
Tokens use `((cpu + 1) << 4) | (slot << 2)`; zero means empty. Direct decoding
selects the preallocated CPU/slot, with a compile-time signed-tail bound.

## Reservation, ownership, and retirement

Ordinary physical spinning reserves a free existing slot with preemption
disabled. The reservation bitmap and exact per-CPU balance cover the entire
membership. Exhaustion declines optimistic spinning and reaches the existing
physical sleeping-waiter path. No dynamic auxiliary allocation, shared
reference count, registry lock, or new RCU mechanism is added.

Initial delegation-head physical acquisition explicitly lends its own reserved
node. The head's migration pin retains CPU identity while physical acquisition
can sleep. The borrowed path changes only the OSQ subrecord; it cannot release
the delegation reservation, waiter record, packet, or shadow stack. Early outer
reacquisition passes no borrowed node because previously completed delegated
nodes may already have been reused. Overflow and ordinary entry also use the
unborrowed path.

OSQ grant only selects the spinner. Actual exclusion still requires the KD
owner-word acquisition. `ACQUIRING` reserves the delegation gate before physical
acquisition; `HELD` is published afterward. The per-body exact-current-owner,
PICKUP exclusion, gate, admission, frame, source-lease, and unlock-ACK checks
remain intact.

OSQ initialization precedes the full tail exchange. The existing write barrier
orders backward-link initialization before predecessor-link publication.
Cancellation retains the existing three stages: stabilize/unlink the
predecessor's forward link; obtain a successor or roll the tail back; repair
successor and predecessor links. Losing cancellation to a grant returns success
and retains membership until unlock. Predecessor movement reloads the current
backward link; immutable CPU/slot identity remains safe to inspect across slot
reuse. Delayed successor publication still waits for its link before retirement.

`IDLE=2` records completed unlink/handoff, independently of `WAITING=0` and
`GRANTED=1`; acquisition checks require exactly `GRANTED`. Every successful
unlock and cancellation-false path retires the OSQ subrecord. Temporary slots
are returned only afterward and before scheduling. Borrowed slots are never
returned by physical spinning. General node release checks OSQ retirement and
the existing exact waiter-record conditions; count generations remain intact.

## Bounded FIFO continuation

The locality selector still detaches only fully linked requests, with a
64-request scan budget. At the 128-body locality boundary, or before consuming
the retained terminal request, the deferred prefix is rejoined and selected
first. Setting `batch.numa_node = -1` then disables further locality bypass for
that batch. The removed condition was the forced handoff for eight or more
deferred requests; servicing that prefix can now keep the same physical owner.

The total `KDLOCK_SPIN_BATCH` bound remains unchanged (1024 in this experiment).
Refusal still hands off the uncompleted request with the rejoined successor
chain. Native completion still ends the batch. Unsupported terminal packets,
source refusal, terminal-tail CAS/delayed-link retirement, and early outer
release retain their existing boundaries. Early release retires/rejoins before
opening the outer mutex; the old successor is not inspected after wake.

## Review limits

Independent static review found no lifetime or extraction-fixture defect.
The added OSQ fixture contains 13 deterministic scenarios and 10 mutation
controls; the terminal fixture covers bounded rejoin and refusal order. This
review does not claim those checks passed: execution belongs in the VM evidence.
Serial callbacks are not weak-memory or kernel-concurrency proof. In particular,
the full-pool scenario establishes spin refusal; actual sleeping completion,
signals, JIT ownership/ACK behavior, drain, and performance require the affected
VM checks and workload measurements. No hardware benefit follows from source
inspection alone.
