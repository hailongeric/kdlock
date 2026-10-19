Static review covers runtime commit `372be892f3e87538a204ab9f6eddc32ca332d047`.
No blocking race or protocol regression was identified in the inspected change.
This is source reasoning, not proof from execution: this reviewer ran no builds,
tests, modules or workloads. VM command receipts, probe results and comparison
records separately establish what was executed and measured.

The physical owner word remains authoritative. In
[kd_mutex_state.h](../../../../../include/kd_mutex_state.h), lines 21–49,
FREE-to-ACQUIRING CAS reserves delegation before physical acquisition; HELD is
published only after acquisition returns (`mutex/queue.inc:98`). Unlock publishes
RELEASING before releasing the physical mutex and FREE afterward
(`kd_mutex.c:333`). Thus an ordinary owner encountered while a delegator waits
sees ACQUIRING, and an ordinary successor acquiring before gate publication
finishes sees RELEASING. Neither phase authorizes delegation unlock. The final
successful FREE CAS is followed by no further gate write, so it cannot erase a
successor's reservation.

`kd_mutex_delegation_owned()` (`kernel_module/kd_mutex.c:128`) accepts only a
query for `current`, requires the masked physical owner to equal `current`,
rejects PICKUP, and accepts only HELD or COMBINER. Current's completed physical
acquisition stabilizes ownership while it reads the phase; an arbitrary-task
snapshot would lack this guarantee. PICKUP names a designated successor before
that task has acquired the mutex and therefore is deliberately insufficient.
WAITERS and HANDOFF do not invalidate an already completed acquisition. The
combiner observation remains a hint and does not authorize ownership.

The physical sleeping queue in
[kd_mutex_local.c](../../../../../kernel_module/kd_mutex_local.c), lines 54–90,
uses the first real stack waiter as a circular doubly linked ring's anchor.
Its previous link supplies the tail, retaining constant-time append and removal.
NULL alone means empty; a singleton's self-links still describe a live waiter.
All link mutations, head replacement and waiter-task dereferences remain under
the existing physical `wait_lock`. The unlocked first-waiter test at line 225
only compares the sampled pointer with its own live stack waiter. It never
dereferences another task's potentially retiring stack. Removal precedes stack
return; unlock takes the wake queue's task reference under the same lock.
Pickup-before-signal cancellation ordering, HANDOFF/PICKUP transfer and the
separate OSQ algorithm remain unchanged.

The embedded atomic state uses eight phase bits and 24 exact waiter-count bits.
Every phase CAS retries while preserving the count; count entry/exit add or
subtract 256 without modifying the phase. Unsigned extraction handles the sign
bit correctly. Each counted waiter retains a reserved per-CPU slot, and
`mutex/lifecycle.inc:67` checks that `NR_CPUS * KD_MUTEX_MAX_NODES` fits the count.
Overflow and underflow are fatal invariant failures. This count is neither an
ownership record nor a substitute for frame, node or ACK lifetime. The encoded
delegation tail addresses the existing reserved nodes directly. Build assertions
at `mutex/lifecycle.inc:58` retain 32-byte size, native alignment and offsets
16/24/28 for the ring head, state and tail.

Controlled drain still requires callers to stop and join. Exact per-CPU waiter
balances, reservation counts and slot bitmaps are checked independently, then
active task identities are checked (`mutex/lifecycle.inc:128`). Immediate gate
owners and node-overflow owners retain their task reference through final
unlock. An early outer release retains the combiner's original invocation,
reserved slot and frame/source lease through reacquisition. Native routing and
the logical task reference are retired before the final unlock ACK
(`execution/native.inc:227`); the enclosing executor and frame remain live.
Completed JIT producers release their node before dropping their task reference.
Ordinary physical-only calls still depend on the existing stop/join condition.

The per-lock delegation root now lives inside the caller-owned mutex. It needs
no auxiliary allocation, address lookup, shared auxiliary reference count, RCU
retirement or auxiliary registry lock. This does not remove the physical
`wait_lock`, or the existing task-routing registry's locks and RCU lifetime.
Caller object lifetime, source leases, frame retirement and exact unlock ACKs
remain required by the established protocol; no new caller cleanup is added.
