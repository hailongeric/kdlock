# KD, TCLock and Linux Native lock protocols

This is the protocol entry point for the six benchmark backends. It describes
the current x86_64 implementation, including the ordinary mutex port, rather
than the historical transparent-hook experiment. Read
[spin implementation](spin_implementation.md) and
[mutex implementation](mutex_implementation.md) for storage, source files and
execution details. KD's nested ownership, recovery and ACK contract remains in
[locking](locking.md) and [frames](frames.md).

## Backend and ownership matrix

| Backend | Exclusion object | Who executes a contended request? | Wait policy | Native peers on the same object |
| --- | --- | --- | --- | --- |
| Linux Native spin | Linux `raw_spinlock_t` / qspinlock word | The acquiring caller | Kernel-selected spin/PV path | Ordinary compatible Linux APIs |
| TCLock spin | A qspinlock-shaped word owned exclusively by TCLock | Caller or combiner on the waiter's real stack | Pinned polling | Not supported |
| KD spin | Explicit four-byte `kd_spinlock_t` | Caller or combiner running translated code | Pinned polling | KD native variants only; no Linux/TCLock mixing |
| Linux Native mutex | Original `struct mutex` | Its actual Linux owner | Optimistic spinning and sleeping | Ordinary compatible Linux APIs |
| TCLock mutex | Separate `struct komb_mutex` | Caller or combiner on the waiter's real stack | Polling, scheduling and parking | Not supported |
| KD mutex | Original Linux mutex plus a private scheduling gate | Actual Linux owner executes JIT, or services a borrowed native suffix | Published KD waiters poll pinned; physical owners may sleep | Original Linux mutex callers remain excluded by that same mutex |

A queue-head notification grants scheduling eligibility. It does not prove
physical ownership or that the request's body ran. A completion notification
means a committed body must be skipped on the origin CPU. In particular, KD
mutex's gate never replaces the original Linux mutex.

The workload compiles a distinct arm for each backend; it does not switch
algorithms inside an operation or mix them on one object. Loading KD/TCLock
providers installs no global lock selectors. Captured KD kernel bridge
endpoints remain recognized for generic FULL recovery; their presence does
not enable interception.

## Linux Native spin

`__raw_spin_lock()` establishes the ordinary preemption protection and invokes
the kernel's architecture lock implementation. The uncontended qspinlock path
uses an acquire CAS from zero to locked. The native queued slowpath can use a
pending waiter for light contention, then per-CPU MCS nodes and an encoded
tail for heavier contention. The MCS notification transfers queue-head
eligibility; that caller still obtains the physical lock before its own body.
Unlock releases the ownership byte and balances preemption protection.

The recovery kernel enables paravirtual spinlock support. Its selected x86
slowpath may use PV wait/kick operations or the virtualization TAS shortcut;
the native MCS algorithm alone is not proof of which branch ran in a sample.
Linux does not delegate the critical-section body, lend its stack to another
CPU, or create a KD packet/frame/source lease.

## TCLock spin

Fast CAS and pending acquisition execute on the caller. A queued caller saves
six callee-saved GPRs and its real RSP, moves to its CPU's shadow stack, and
publishes a TCLock node. The workload holds its preemption pin across this
operation. A holder with eligible followers becomes a combiner.

The combiner switches physical RSP to a waiter's saved native continuation.
That stack resumes after lock acquisition, so the existing body runs under
the retained TCLock word. Delegated unlock saves the post-unlock continuation
and switches to another waiter or back to the combiner's shadow stack. Only
after leaving the borrowed stack does the executor publish completion. The
origin CPU resumes after unlock and does not execute that body again.

NUMA selection can defer remote followers and splice them back before the
next queue-head handoff. The configured batch value is 1024; upstream WWJUMP
starts its counter at zero and can execute 1025 bodies. It has no KD-style
independent scan budget or fairness guarantee. The current spin comparator
is limited to IRQ-enabled task-context single-lock workloads; IRQ checks and
explicit scheduling points are disabled.

Tail layout compatibility with Linux is insufficient: TCLock decodes tail
IDs into its own node pool, while Linux decodes into kernel qnodes. Native
Linux acquisition/unlock cannot participate in that same target lock.

## KD spin

The paired `KD_SPIN_DIRECT_LOCK/UNLOCK` API pins the caller once. A cold CPU
uses the inlined native CAS and complete KD pending/MCS slowpath; its locked
byte is 5 and an exact native in-flight count covers acquisition through
release. A hot CPU enters the clobber provider, which checks adaptive
CPU/lock admission, execution context and image readiness. Fast/pending
self-execution uses a fast-owner record; a contended root reserves a stable
acquisition ticket before publication.

An eligible producer prepares a continuation/frame and shared `kd_regs`
packet, switches away from the caller stack, and publishes its queue node.
The combiner acquires/retains the same KD exclusion word, binds the producer's
frame, and executes the translated body with logical waiter IP/SP/BP and
the existing two-word GS/task inputs. Hardware `current`, GS and physical
RSP remain those of the executor.

The ordinary clobber terminal unlock can return COMPLETE directly. It must
validate the exact root/unlock/ownership state; a failed minimal completion
constructs the original virtual CALL once and enters FULL dispatch. Missing
images and other unstarted refusals use native self-execution/handoff. An
exit after progress cannot replay the body from its entry.

Normal completion retires the frame before release-publishing the node's
combined completed/locked word. The origin restores the post-unlock
continuation. A ticket, frame and node have different lifetimes: node reuse
does not retire an acquisition, and borrowed native execution retains the
root ticket/continuation until final ACK and borrower retirement. Metadata
retirement precedes the unique physical release store; pending/tail remain
intact. Unlock selects ownership provenance rather than current heat or comm.

NUMA-on is the default. A batch executes at most 1024 delegated bodies and
has a separate scan budget initialized to 1024. Scans stop at non-combinable
native nodes and preserve deferred remote priority at handoff. Bounded work
and finite observed progress do not establish a starvation bound. Explicit
irqsave/irq/bh pairs use KD native execution on the origin CPU.

## Linux Native mutex

The workload calls `(mutex_lock)` and `(mutex_unlock)` to bypass the experiment
kernel's caller-clobber macros. The Linux mutex owner word holds a task pointer
plus WAITERS, HANDOFF and PICKUP flag bits. Uncontended acquisition CASes zero
to `current` with acquire ordering; fast release CASes that owner to zero with
release ordering.

Contention enters the original Linux slowpath. Optimistic spinning uses OSQ
serialization while the owner can run and scheduling permits. Otherwise a
stack waiter joins the wait list under `wait_lock`, rechecks acquisition and
sleeps; ordinary `mutex_lock` uses an uninterruptible wait. Unlock handles the
flagged state, wakes the top waiter and honors requested handoff/pickup. Only
the physical owner may unlock. No critical-section delegation occurs.

This description is tied to the captured non-RT 6.1.159 kernel with
`CONFIG_MUTEX_SPIN_ON_OWNER=y` and mutex/lockdep debugging disabled. It does
not describe RT, PI or WW mutexes.

## TCLock mutex

`komb_mutex_lock/unlock` operate on TCLock's own mutex object. Fast acquisition
uses the gate CAS. A slow caller uses its pre-registered fixed-CPU context,
saves six GPRs and RSP, moves to its shadow stack, and publishes a linked node.
The queue head takes the TCLock gate; linked eligible followers can be
executed through real stack switching and WWJUMP.

The waiter handshake has four values:

| `completed` | Meaning |
| --- | --- |
| 0 / UNPROCESSED | Queued, not claimed for processing |
| 1 / PARKED | Waiter won the parking CAS after setting task sleep state |
| 2 / PROCESSING | Executor claimed/woke the node |
| 4 / PROCESSED | Body finished; consume the updated unlock continuation |

When rescheduling is needed, the port retains upstream scheduling/parking.
The waker atomically changes the state to PROCESSING and calls
`wake_up_process()` if the old state was PARKED. A processing win before the
parking CAS prevents a lost wake. Completion follows the executor's departure
from the borrowed stack. A handed-off unprocessed node instead becomes a
physical owner and executes its body itself.

The port preserves NUMA deferral and the upstream terminal-node handoff;
its 1024 WWJUMP setting can execute 1025 bodies. It requires registered,
fixed-affinity workers, one worker per CPU. Registration/context/task refs
survive the entire cohort's exit and queue/stack drain. No ordinary Linux
mutex owner word provides interoperability for `struct komb_mutex`.

## KD mutex

The outer benchmark uses `KD_MUTEX_OUTER_LOCK/UNLOCK`. A successful caller-side
acquire CAS on the original Linux owner bypasses admission, shadow/task
records and translation. Its lexical cookie holds the exact native owner
result; matching unlock calls the original Linux function. The cookie belongs
to that acquisition and cannot be copied, transferred or reused.

On contention the provider checks its separate mutex heat policy, source
admission, target comm and active task routing. A native fallback before any
KD acquisition reference returns an exact native result. A queued acquisition
returns route zero, including local native fallbacks that still need KD-aware
unlock routing. General `KD_MUTEX_DIRECT_LOCK/UNLOCK` and bridge entries keep
their void ABI and are also used by translated nested control calls.

An eligible acquisition holds an exact task routing reference, finds the
original-address shadow, and reserves a CPU-local node/stack. A delegation
follower keeps migration/preemption disabled, moves off its caller stack and
polls. A queue head first takes the private gate, then acquires the original
Linux mutex as `current`; only that physical owner executes/releases bodies.
It may enable preemption while sleeping for the original mutex or nested B,
while retaining its CPU reservation and frame ownership.

The combiner executes FIFO JIT requests with a 1024-body limit and a source
lease covering the batch. A terminal ABI2/MINIMAL node can also be delegated.
Before waking any committed node, the batch retires its queue publication:
retain its successor, or CAS the exact tail to zero; a lost CAS requires the
publisher's delayed successor link before node reuse. An unstarted refusal
retains its tail/node and receives physical handoff. Legacy/FULL terminal
nodes retain that handoff path.

Normal COMPLETE validates and retires the frame, then release-publishes
completion; the waiter restores IP/SP/BP after logical unlock. A FULL exit
materializes recovery state once. For a native suffix, the waiter resumes
with progressed state while the original physical owner remains responsible
for mutex release and services unlock/ACK messages. Early A release and
nested B ownership retain the explicit ledger; there is no Linux owner
transfer to the logical waiter. Final ACK/frame retirement precede dropping
the enclosing source lease. Physical mutex release precedes opening its gate.

## Publication, lifetime and validation

KD uses acquire/release queue/result publication and exact ownership,
reference and ACK state. PAUSE and prefetch supply neither ordering nor
lifetime. TCLock retains the upstream x86 atomics, barriers and WRITE_ONCE
notifications; a WRITE_ONCE store is not a portable release contract by
itself. The stack-switch ports are scoped x86 implementations.

Stop new callers, join the entire cohort, drain queues/frames/ACKs, retire KD
sources, clear TCLock diagnostic target pointers, unload workload, then unload
provider. An idle sample alone is not a no-new-callers barrier. EBUSY retains
storage/references; forced unload is outside this protocol.

Returned-body KD JIT evidence and TCLock mutex returned-batch delegation
counts are separate from payload correctness. TCLock spin delegation counts
remain unmeasured. Performance acceptance, failed candidates and the remaining
mutex gaps are maintained in the [benchmark index](../../bench/README.md) and
[final mutex report](../../bench/tclock_compare/results/20261003-mutex-followup.md).
This documentation cleanup does not rerun those performance matrices.
