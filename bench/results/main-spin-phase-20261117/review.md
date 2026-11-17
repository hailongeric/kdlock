# Main spin phase re-observation review

Reviewed commit: `5cd2e62bfdd015584e3ffbd7e81038ac90da92f0` on main.
The four changed source/documentation files in the main worktree match that
commit. This is a source review, not a build, runtime test or performance result.
No VM, network, other branch or other branch documentation was accessed.

## Candidate and bound

The optional `kd_spin_phase_wait` is zero by default. When adaptation is on,
`kd_q_deleg_mode(q, val)` performs additional observations only if its supplied
word has no holder or pending byte, has a nonzero tail, and delegation is
currently enabled. This identifies a queued handoff opportunity; it does not
establish that the queue is deep or in delegation mode.

The effective limit is sampled once and clamped to 128. Each iteration calls
`cpu_relax()` and reads the lock word once. It stops on an observed holder,
pending waiter, vanished tail, or exhaustion. At most the clamped number of
additional reads occurs. Zero performs no additional read. This is an
instruction/iteration bound, not a time bound: interrupts, VM scheduling and
hardware PAUSE behavior can extend elapsed time. `kd_adapt=0` keeps its previous
forced-mode result. With delegation disabled, this new loop is skipped.

## Ownership and lifetime

The returned result selects whether to try continuation capture. It is never
a grant of the lock. The supplied or reread value can become stale immediately;
this was already true of the holder-mode observation. A previously observed
DELEG bit can select capture after that holder leaves, but the actual queue,
head acquisition, context/resource checks and execution lifetime still govern
whether the continuation can run. A plain observation can conservatively miss
a later delegation phase. Neither case authorizes running a critical section
without the normal physical grant.

The helper reads only the caller's lock word. It does not dereference the tail
node, keep a per-address mode cache, claim a node, modify a link, acquire a
source lease or extend any packet lifetime. Thus it introduces no tail-slot
retirement/reuse race. A raw tail lookup would need additional lifetime
reasoning: a double-read of the tail alone does not rule out reuse of the same
per-CPU slot. This candidate deliberately does not use that mechanism.

The lock object's lifetime remains the existing caller obligation throughout
an acquisition attempt. There is no attempt to make an otherwise invalid lock
pointer safe. Pending and queue-head acquisition functions, capture/restore,
completion acknowledgement, source retirement and release are unchanged.

## Context and entry paths

Only the two existing helper call sites change: the ordinary spin slow entry
and `kd_spin_nested()`. The nested path short-circuits if there is no generated
entry. If it reaches the helper, the same bounded loop observes the inner lock;
it adds no recursive session, sleeping operation, packet ownership transfer or
scheduler call. The existing nesting limit and context checks remain required.

The loop does not change interrupt, BH or preemption state. IRQ-disabled
entries may therefore spend up to the bounded extra iterations with IRQs still
disabled; the bound does not justify treating that cost as zero. Raw spin paths
are unchanged. The one-CAS uncontended assembly prefix and byte-store unlock
were not edited. The internal helper gains a lock pointer argument; no public
lock ABI or object layout changes.

## Performance risks and attribution

A nonzero tail can occur at low queue depth, including a queue that never
enters delegation. Such a caller can pay the polling cost and still select
plain execution. Added reads and PAUSE instructions may compete for the lock
word's cache line, particularly across NUMA nodes. More observations need not
mean better throughput. Even setting zero retains the compiled eligibility
branches and altered register/code layout, so an in-image 0/8/32/128 comparison
is not an exact comparison against the unmodified binary.

Same-boot comparisons should keep kernel/config, topology, workload, JIT state,
module and instrumentation fixed; rotate order and retain all repetitions.
Report delegated, handback, offered, sessions, stop_plain and NUMA-deferral
deltas with every rate. A higher delegated count or lower stop_plain count can
support the proposed mechanism, but these approximate counters are not lock
ownership evidence, measured physical chain lengths or cycle attribution.
There is no new loop counter, so they do not directly establish how many calls
entered the re-observation loop or how many iterations were used.

Relevant boundaries include low-contention 1/5-worker controls, 8/32-worker
short and longer sections, balanced and packed NUMA placement, delegation off,
phase changes back to low contention, raw/IRQ/BH entry state, nested acquisitions
and actual handback execution. Preserve unsupported or unexercised cases as
such. No performance gain or complete context coverage is established by this
review alone.
