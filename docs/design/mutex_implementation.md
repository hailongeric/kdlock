# Mutex implementation: KD, TCLock and Linux Native

Read [lock protocols](lock_protocols.md) for the algorithm/ownership comparison
and [KD locking](locking.md#5-mutex-delegation-protocol) for nested owner/ACK
details. This page maps the current ordinary mutex paths to their data and
source. [Spin implementation](spin_implementation.md) owns the shared wrapper,
code-pool and spin-continuation geometry; those allocations are not duplicated
per mutex request.

## Source and call paths

| Arm | Workload entry | Backend implementation |
| --- | --- | --- |
| Native | `(mutex_lock)` / `(mutex_unlock)` | Captured kernel `kernel/locking/mutex.c`, `include/linux/mutex.h` |
| TCLock | `komb_mutex_lock` / `komb_mutex_unlock` | [komb_mutex.c](../../tclock_backend/komb_mutex.c), [combiner.c](../../tclock_backend/combiner.c), [mutex_provider.c](../../tclock_backend/mutex_provider.c) |
| KD outer | `KD_MUTEX_OUTER_LOCK/UNLOCK` | [kd_mutex_direct.h](../../include/kd_mutex_direct.h), [mutex_calls.inc](../../kernel_module/lock/mutex_calls.inc) |
| KD general/nested | `KD_MUTEX_DIRECT_LOCK/UNLOCK` and retained bridge endpoints | Same routing file, [kd_mutex.c](../../kernel_module/kd_mutex.c), [native.inc](../../kernel_module/execution/native.inc) |

All three use distinct compiled functions in
[mutex_cacheline/module.c](../../workload_modules/mutex_cacheline/module.c).
The mutex translation unit reuses payload, ioctl runner and timing sources;
there is no per-operation runtime `is_mutex` branch. Measurement runs through
[run_mutex.py](../../bench/tclock_compare/run_mutex.py), sharing reporting with
the spin runner. Registration and final context drain are outside measurement.

The existing kernel build is `/root/linux-6.1.159-kdclobber2` in the guest. Its
release, configuration, source/interface hashes and live Build ID are checked
by the [kernel identity verifier](../../bench/spin_cacheline/kernel_identity.py)
against the [captured baseline](../../kernel_baseline/README.md). Native source
paths above refer to that build, not to a second Linux implementation in this
repository.

## Linux Native implementation

`struct mutex` contains `owner`, `wait_lock`, an optimistic spin queue when
configured, and `wait_list`. With the captured configuration it is 32 bytes;
debug/RT configurations change the layout and implementation. Owner low bits
are WAITERS=1, HANDOFF=2, PICKUP=4; pointer comparisons mask all three.

The original lock function's successful owner CAS returns directly. Its
slowpath first retries acquisition and optimistic spinning, then installs a
stack `mutex_waiter` under `wait_lock`. Sleep state publication, rechecking
ownership and wait-list insertion prevent a missing unlock wake. A first
waiter can request handoff instead of repeatedly losing to a fresh contender.
The unlock slowpath preserves flagged state, prepares a wake queue and
performs handoff when requested; the receiving task consumes PICKUP with
acquire ordering.

The Native arm deliberately parenthesizes function names to bypass the
experimental caller-clobber macros. No KD selector is installed, so it reaches
the original Linux algorithm. It does not allocate a KD task record/shadow,
use a JIT frame, or move to a TCLock shadow stack.

## TCLock implementation

The fixed upstream source is commit
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef`, retained byte-for-byte in
[upstream](../../tclock_backend/upstream/) with hashes in
[UPSTREAM.json](../../tclock_backend/UPSTREAM.json). The external module
replaces custom `task_struct` fields with
[tc_mutex_context](../../tclock_backend/mutex_compat.h). It retains ordinary
mutex parking, wakeup, NUMA selection and real stack switching. The provenance
and build boundary are in the [backend README](../../tclock_backend/README.md).

| Storage | Location and purpose |
| --- | --- |
| `komb_mutex` | 24 bytes; workload-owned pointer tail, state/locked byte and combiner task; no original Linux mutex owner |
| `tc_mutex_context` | 336 bytes, preallocated per possible CPU on its preferred NUMA node; registered task, stack pointer, waiter links, lock-address stack, batch counter, observations and embedded node |
| `komb_mutex_node` | 160 bytes embedded in that context; next/task/lock, CPU/socket, real RSP and completion/locked notification |
| Shadow stack | 8 KiB per possible CPU, NUMA-local allocation with allocator fallback; retained until controlled backend unload |
| Native context | Six callee-saved GPRs plus CALL return address on existing task/shadow stacks; no KD register packet or software frame |

These sizes are verified from the cleanup's guest-built DWARF. The node starts
at context offset 176; its completion/locked bytes are at node offsets 136/137.
The type has no KD-style 64-byte alignment/whole-line stride requirement.
Allocator overhead, alignment and existing task stacks are separate from
`sizeof`, and object geometry does not measure cache misses.

`tc_mutex_worker_register()` requires single-CPU affinity and an unused
context, takes a task reference, and binds the context before workers report
ready. `tc_mutex_task(task)` looks up by `task_cpu(task)`; registration and
fixed affinity are part of its correctness contract, not approximate
profiling information. Only ordinary operations on registered workers are
supported. Interruptible/killable/IO, rwsem and general unregistered kernel
callers are not ported APIs.

`komb_mutex_lock()` CASes the locked byte. On failure it disables preemption,
sets node CPU/socket/task identity, and enters `__komb_mutex_lock()`. The
assembly saves six GPRs, records RSP through the original implicit helper
CALLs, switches to the context shadow stack and calls the queue slowpath.
That slowpath exchanges `lock->tail`, links behind the predecessor and waits
on the node. Parking/scheduling follows the state machine in
[the protocol](lock_protocols.md#tclock-mutex); it is not a Linux mutex wait-list
implementation.

A queue head obtains the gate. A terminal follower with no successor is
handed physical control; otherwise the combiner records `combiner_task` and
calls `execute_cs()`. `komb_context_switch()` moves physical RSP to the
waiter's native acquisition return. On delegated unlock, WWJUMP records the
waiter's post-unlock RSP and either switches directly to the next eligible
waiter or returns to the combiner. Previous waiter completion is published
only after its stack is no longer executing. Out-of-order state/lock-address
handling remains in the port but does not expand the comparator's single-lock
validation scope.

NUMA selection walks linked successors, defers remote nodes in the context
list and rejoins that list before physical handoff. The default WWJUMP value
1024 is checked against a counter starting at zero, allowing 1025 bodies.
There is no separate KD-style scan limit. Selected waiter stacks receive six
`prefetchw` hints at saved RSP through RSP+320, plus a successor-node hint.
Switching stacks does not switch hardware task/GS identity.

`parks` counts actual successful parking transitions. `batches` and
`delegated` update once after a returned batch, using `counter_val + 1`.
Whole-session deltas prove delegation but do not identify the selected
300 ms peak's delegation share. They are observational values; context
lifetime is checked independently.

`tc_mutex_workers_drain()` requires all workers to have exited and the lock,
queue, saved waiter links, lock-address stack and shadow stack pointer to be
idle. A still-live exiting task yields EBUSY for a bounded retry outside
measurement. Only after cohort drain are task references released. Backend
unload frees preallocated contexts/stacks; no forced context release is used.

## KD implementation

### Entry and native routing

The outer pair attempts an acquire CAS on the original `mutex.owner` in the
caller. Success increments only the approximate CPU-local entry observation
and stores the exact native result in the lexical cookie. Unlock uses the
original function, preserving its owner/flag slowpath. Cookie zero routes to
KD, including native fallbacks after joining KD ownership routing.

`kd_mutex_outer_contended_clobber_v1()` does not retry the failed initial CAS.
`kd_mutex_contended_acquire()` records that contention once and checks heat,
source OPEN, target comm, active-task routing and JIT policy before shadow/task
work. A native-only result is returned only when this acquisition obtained no
KD routing reference. The general direct and bridge APIs keep their void
contract; their unlock uses task membership, native requests and exact shadow
physical ownership rather than a fresh admission decision.

`kd_mutex_prepare()` registers the named post-lock continuation with
`KD_ENTRY_ABI_MUTEX_CLOBBER_V1`. Translation/admission/control tables recognize
direct symbols and kernel bridge aliases. The direct admitted unlock can use
terminal COMPLETE; bridge aliases use checked generic FULL dispatch. The
outer returning entry has a separate physical C return and JIT continuation
which defines route zero, so a nested translated call never consumes an
unmodelled native result.

### Current storage and lookup

| Object | Current storage/lifetime |
| --- | --- |
| Original Linux mutex | Workload's `struct mutex`; authoritative native-peer exclusion and physical ownership |
| Shadow table | 1024 resident `kd_mutex_shadow_entry` objects in [kd_lock.c](../../kernel_module/kd_lock.c); each gate is 32 bytes with tail, state, physical owner, immutable original address and exact waiter count |
| Task routing record | RCU hash, 256 buckets, dynamically allocated records and a writer lock in [kd_mutex_tasks.c](../../kernel_module/kd_mutex_tasks.c); exact acquisition refs and retained `task_struct` ref |
| `kd_mutex_node` | Four independently bitmap-reserved slots per possible CPU; 256 bytes each, 64-byte aligned |
| Waiter stacks | Four 8 KiB stacks per possible CPU, allocated by [lifecycle.inc](../../kernel_module/mutex/lifecycle.inc) with `vzalloc_node(..., cpu_to_node(cpu))` |
| Execution frames | Shared per-CPU context, up to eight frames; physical owner remains fixed through sleep/ACK; root borrows node packet until FULL detachment |
| Batch state | Physical combiner's stack; retains current retirement flag, exact successor, outer-release callback and image-slot identity |

Shadow hits acquire-load the immutable exact address without a lock. The
current collision policy is `address % 1024` plus linear probing; misses take
`kd_mutex_shadow_lock`, recheck, initialize and release-publish the address.
Entries are not individually cacheline-isolated and are not removed/reused
while callers are live. Exhaustion falls back to the original mutex. The
fully hashed/cacheline-isolated table and retained 1024-task cache experiments
were not retained; they are not properties of the current code.

`kd_mutex_task_get()` still allocates a candidate with GFP_ATOMIC and takes
the registry writer lock. It increments an existing acquisition ref or
publishes a new RCU record. Last put removes routing membership immediately;
the RCU callback drops the task ref and frees storage. Read-side membership
lookups allocate nothing. Approximate heat/counter values cannot replace
these exact references or the final owner ACK.

Mutex heat has separate entry/contention counters from spin. Every 1024
contentions the accepted policy checks `(entries >> 10) < 256`, resets both
counters, then samples the clock. The earlier proposed limit 2 is not the
current mutex setting. CPU and exact-address heat windows remain separate;
see [heat and roles](../JIT_EXECUTION.md#heat-and-roles) for the full policy.

### Packet/cacheline and prefetch layout

The node's first line contains next, GS base, saved physical RSP, stack
base/top, lock, task and saved entry identity. `completed/locked` occupy
offsets 64/65, separated from successor writes to `next`. ABI/native-result/
packet/tail/slot state follows; `regs` begins at offset 80. Thus IP/SP/BP at
80/88/96 share the notification/state line. The full private packet is
168 bytes; Linux `pt_regs` is unchanged.

The root frame's own hot header contains entry/lock identity and frame state.
For spin its inline IP/SP/BP share that first aligned line. A mutex simple
frame instead borrows `node->regs`; the frame header and node packet are
distinct objects. Caller stack memory keeps its original addresses/aliases
and is not relocated into either header. These are layout facts, not measured
cache misses or a claim that all request state occupies one line.

Before the current body, `kd_mutex_prefetch_successor()` hints the known-live
successor header, `regs.sp`, `regs.bp` and stack addresses SP and SP-64. It uses
read prefetches and does not fetch the entire frame/FULL packet on every
minimal request. The pointer is queue-owned until wake; no successor or
current-node read is allowed after its completion/native publication. Prefetch
grants no ownership, admission or lifetime.

### Queue, batch execution and recovery

[queue.inc](../../kernel_module/mutex/queue.inc) encodes `(CPU+1, slot)` into
the tail, reserves nodes, and acquires the original Linux mutex only after
the scheduling gate. A same-CPU reserved predecessor on that queue refuses
before publication so a pinned follower cannot prevent a sleeping head from
resuming. [clobber.inc](../../kernel_module/mutex/clobber.inc) switches to the
reserved waiter stack before publication and restores the post-completion
boundary without returning through potentially overwritten hook frames.

[combiner.inc](../../kernel_module/mutex/combiner.inc) keeps FIFO order and
an exact 1024-body cap. It takes one enclosing source lease and uses
`kd_exec_frame_push_mutex_batch()` plus `kd_exe_mutex_batch_prepare()` for
eligible simple ABI2 roots. Each request still checks source OPEN and current
image readiness/publication/ABI; caching slot identity is not caching readiness.
The physical QUEUE_OWNER ledger is initialized before body entry. Cold
complex routing is materialized only when needed.

The first wrapper invocation either returns terminal COMPLETE and retires
through the dedicated mutex helper, or its returned FULL/refusal enters
`kd_exe_mutex_batch_resume()` once. It never reruns the first body. Packet
state and lock-ledger state are distinct: MINIMAL/COMPLETE only authorize the
documented clobber fields; FULL authorizes generic recovery GPRs.

Committed terminal nodes retire before any wake: retain a linked successor,
or remove the exact tail by CAS; losing that CAS waits for the owed link.
The saved `current_retired` flag prevents repeated node reads after native
wake/reuse. Normal results retire/pop before release publication. FULL native
resume first detaches frame-owned state, copies the resume packet, retires the
queue node and publishes native readiness. The combiner then services the
exact physical-owner unlock/final ACK and pops the retained frame. Early A
release uses the same saved batch state and reacquires A for the combiner's
own operation after B finishes. [The detailed protocol](locking.md#53-nested-ab-and-native-continuation)
defines that ownership ordering.

Exact per-CPU active-waiter/reserved-node balances and slot bitmaps are
checked separately at drain; opposite imbalances on two CPUs cannot cancel.
The shared original-owner ledger, task refs, nested waiters and ACKs keep
their own exact state. Pure observations are per-CPU totals read after drain.
Native mutex release precedes gate release. The batch source lease outlives
all native/ACK/frame processing.

Every returning combiner holds the original mutex and normal gate value 1.
Refusal and ordinary completion publish that value before waking a successor;
early outer release reacquires it before returning. Terminal and outer-progress
fixtures check this contract independently of the caller's repeated restoration.

## Scope and evidence

KD keeps pinned published waiters and has no accepted NUMA queue grouping for
mutex. NUMA-local stack allocation does not imply NUMA-local FIFO selection.
TCLock supports parking, but this port's fixed-affinity context contract does
not validate arbitrary oversubscription. Both stack/context protocols require
independently runnable dependencies and controlled drain.

The benchmark KD provider defaults to UBSAN off; a standalone provider build
inherits the existing kernel configuration. Backend/workload ELF identity
and instrumentation policy are recorded separately. The captured kernel is
unchanged. Build/use instructions belong in the
[workload README](../../workload_modules/mutex_cacheline/README.md) and
[runner README](../../bench/tclock_compare/README.md).

The final full-thread comparison, returned-body JIT/delegation evidence and
remaining performance gaps are in the
[completed report](../../results/380G10/bench/tclock_compare/20261008-protocol-simplification/README.md).
Earlier grouping/cache candidates remain in
[fixed benchmark records](../../results/380G10/bench/tclock_compare/HISTORY.md#mutex-followup).
The earlier [mandatory-JIT trials](../../results/380G10/bench/tclock_compare/20261008-mutex-priority-trials.md)
retain runtime behavior after rejecting task retention and finding no repeatable
gain from smaller entry/execution changes under `nopvspin`.
Source review and synthetic unit fixtures do not substitute for those live
results or prove starvation freedom.
