# KD, TCLock and Linux Native lock protocols

This guide compares how the maintained backends acquire, delegate and release
spinlocks, mutexes, rwlocks and sleeping rwsems. Linux Native and KD cover all four
families; the TCLock port covers spin, mutex and rwlock only. It describes the
captured x86_64 implementation, not interchangeable object layouts. Start with
the [lock catalog](../LOCKS.md) for current KD APIs and the
[glossary](../TERMINOLOGY.md) for terms such as combiner, frame, native suffix and ACK.
Read [spin](spin_implementation.md), [mutex](mutex_implementation.md),
[rwlock](rwlock_implementation.md) and [rwsem](rwsem_implementation.md) for
storage, source files and execution details. KD's nested ownership, recovery and ACK contract remains in
[locking](locking.md) and [frames](frames.md).

## Backend and ownership matrix

| Backend | Exclusion object | Who executes a contended request? | Wait policy | Native peers on the same object |
| --- | --- | --- | --- | --- |
| Linux Native spin | Linux `raw_spinlock_t` / qspinlock word | The acquiring caller | Native pending/MCS in the current VM | Ordinary compatible Linux APIs |
| TCLock spin | A qspinlock-shaped word owned exclusively by TCLock | Caller or combiner on the waiter's real stack | Pinned polling | Not supported |
| KD spin | Explicit four-byte `kd_spinlock_t` | Caller or combiner running translated code | Pinned polling | KD native variants only; no Linux/TCLock mixing |
| Linux Native mutex | Original `struct mutex` | Its actual Linux owner | Optimistic spinning and sleeping | Ordinary compatible Linux APIs |
| TCLock mutex | Separate `struct komb_mutex` | Caller or combiner on the waiter's real stack | Polling, scheduling and parking | Not supported |
| KD mutex | 32-byte KD physical mutex with embedded delegation phase and encoded tail | Actual KD owner executes JIT, or services a borrowed native suffix | Published KD waiters poll pinned; physical owners may sleep | Every caller must use the KD object and APIs |
| Linux Native rwlock | Linux `rwlock_t` / queued rwlock | Each reader or writer executes its own body | Concurrent readers; spinning reader/writer admission | Ordinary compatible Linux rwlock APIs |
| TCLock rwlock | Separate `struct komb_rwlock` count and gate | Readers run locally; queued writer bodies may run on a borrowed waiter stack | Pinned polling and upstream gate delegation | TCLock rwlock pairs only |
| KD rwlock | 128-byte `kd_rwlock_t`, count and KD gate on separate cache lines | Readers run locally; writers run natively or through ABI3 JIT | Pinned readers/writers; KD gate queues contended admission | KD native and direct pairs only; no Linux/TCLock mixing |
| Linux Native rwsem | Linux `struct rw_semaphore` | Readers and writers execute their own bodies | Concurrent readers or one writer; blocked callers may sleep | Ordinary compatible Linux rwsem APIs |
| KD rwsem | 320-byte `struct kd_rwsem`, reader count and phase reservations around a KD mutex | Readers and ordinary writers run locally; outer writers may use mutex ABI2 delegation | Admission/drain waits may sleep; published mutex waiters poll pinned | KD ordinary and outer-writer pairs only; no Linux/TCLock mixing |

A queue-head notification tells a waiter it may try to acquire the lock. It does
not mean the waiter owns the lock or that its body has run. A completion
notification tells the original caller that its body has already run and must be
skipped. For KD mutex, the scheduling gate and physical exclusion have
separate roles for the same KD lock: the executor must own both before running a body.

The workload builds a separate version for each backend. Every operation on a
lock uses that backend's matching API. Loading KD or TCLock does not redirect
other Linux lock calls. KD still recognizes the captured kernel bridge endpoints
when restoring FULL register state, but those endpoints do not enable global
interception.

## Linux Native spin

`__raw_spin_lock()` establishes the ordinary preemption protection and invokes
the kernel's architecture lock implementation. The uncontended qspinlock path
uses an acquire CAS from zero to locked. The native queued slowpath can use a
pending waiter for light contention, then per-CPU MCS nodes and an encoded
tail for heavier contention. The MCS notification transfers queue-head
eligibility; that caller still obtains the physical lock before its own body.
Unlock releases the ownership byte and balances preemption protection.

The kernel is compiled with paravirtual spinlock support, but benchmark boot
policy requires `nopvspin`. This selects native pending/MCS locking and disables
PV stealing, PV wait/kick parking and the virtualization TAS shortcut. Earlier
samples retain their recorded boot policy; see [VM configuration](../PROJECT_GUIDE.md#native-qspinlocks-in-the-vm).
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

At the final clobber unlock, KD can return COMPLETE directly after checking the
root request, unlock target and ownership state. If that check fails, it constructs
the original virtual CALL once and saves FULL register state for generic recovery.
If JIT never started—for example, because no image was ready—the caller can run
the body natively after acquiring the lock. Once the body has made progress,
recovery must resume from that point; it cannot restart the body.

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
acquire CAS on the KD physical owner bypasses admission, queue/task
records and translation. Its lexical cookie holds the exact native owner
result; matching unlock calls the KD local physical function. The cookie belongs
to that acquisition and cannot be copied, transferred or reused.

The caller probes at most eight times, with read guards and pauses on failure.
Only the successful zero-owner CAS grants ownership. This bounded window can
resolve a short clash before admission and uses no worker-count threshold.
The active-combiner gate state (3) ends retries immediately; a lone gate owner
(state 1) may finish during the bounded window. The observed state is a retry hint
and never grants ownership or permission to retire a request.

On contention the provider checks its separate mutex heat policy, source
admission, target comm and active task routing. A native fallback before any
KD acquisition reference returns an exact native result. A queued acquisition
returns route zero, including local native fallbacks that still need KD-aware
unlock routing. General `KD_MUTEX_DIRECT_LOCK/UNLOCK` and bridge entries keep
their void ABI and are also used by translated nested control calls.

An eligible acquisition holds an exact task routing reference, uses the embedded
queue, and reserves a CPU-local node/stack. A delegation
follower keeps migration/preemption disabled, moves off its caller stack and
polls. A queue head first takes the private gate, then acquires KD physical
exclusion as `current`; only that physical owner executes/releases bodies.
It may enable preemption while sleeping for the KD physical mutex or nested B,
while retaining its CPU reservation and frame ownership.

The combiner uses bounded NUMA selection, a default 1024-body limit and a source
lease covering the batch. At most 64 fully linked remote nodes can be deferred;
they take priority by the 256-body local cohort boundary. Eight or more deferred
requests receive handoff with the prefix rejoined first. A smaller prefix is
serviced by the current owner, followed by FIFO selection for the remaining batch.
Deferred nodes rejoin before any exit publishes a wake. A terminal ABI2/MINIMAL
node can also be delegated when no detached chain would be stranded.
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
nested B ownership retain the explicit ledger; there is no physical owner
transfer to the logical waiter. Final ACK/frame retirement precede dropping
the enclosing source lease. Physical mutex release precedes opening its gate.

## Linux Native rwlock

The workload calls Linux `read_lock/unlock` and `write_lock/unlock` on its own
`rwlock_t`. Multiple read holders may execute concurrently; writers exclude all
readers and other writers. The captured non-RT kernel uses queued spinning
admission on contention. Each holder executes its own application body on its
original CPU, with ordinary preemption protection and IRQ state preserved.
There is no body delegation, translation preparation or provider module.

## TCLock rwlock

The comparator ports the pinned upstream `komb_rwlock.c`, including its count-word
fast writer, queued writer and slow reader paths. An uncontended writer owns the
count without the gate. Slow writers retain the gate while draining readers and
executing their body. Slow readers withdraw their speculative count before
queueing, add it back under the gate, wait for an active writer, then release the
gate before their application read body.

Gate delegation switches six saved GPRs and the real waiter stack. It can serve
short reader admission or a queued writer body; application reads remain local.
This rwlock combiner returns between delegated requests and has no WWJUMP chain.
Callers pin the complete operation, with one non-nested worker per CPU. Count,
gate, queue, node and stack state must drain before unload. See
[port scope and provenance](../../tclock_backend/README.md#rwlock-comparator).

## KD rwlock

KD follows the count/admission structure with local readers and a KD spin gate.
The 128-byte object separates count updates from queue polling. Native fast
writers CAS zero count to `0xf0` and retain an exact nondelegated reference.
Gated writers acquire `0xff`, publishing WAITING while existing readers drain.
The same exclusion applies to native and delegated writers.

ABI3 registers the gate with the spin backend. Before the prepared body starts,
native code waits for readers and acquires exclusive write access. This happens
whether the caller or a combiner will run the body, so the translated code does
not include the reader-drain loop. Writer unlock clears only the count's low byte
before spin completion. If JIT refuses before starting, KD clears that byte while
still holding the gate; a native retry must acquire write access again. If the
body has already made progress, its native continuation keeps write access and
must complete the usual spin unlock acknowledgement and retirement steps.

Readers are never delegated. Native and direct KD writer pairs may share this
object, each with its matching unlock. Recursive reads, upgrades/downgrades,
IRQ/BH variants and sleeping bodies are unsupported. The full state machine,
API and lifetime contract live in [rwlock implementation](rwlock_implementation.md).

## Linux Native rwsem

The comparison uses `down_read/up_read` and `down_write/up_write` on a Linux
`struct rw_semaphore`. Readers share access and writers exclude all readers and
other writers. Blocked tasks can sleep; acquisition and release use the kernel's
own reader/writer synchronization. The body runs on the acquiring task, without
translation or delegation. The benchmark mappings are in
[direct_rwsem.h](../../workload_modules/rwlock_bench/direct_rwsem.h).

This arm is a sleeping semaphore, not the spinning Native rwlock above. Results
must retain the lock kind even when both protect identical c01/c08/RCUHT payloads.
There is no sleeping TCLock rwsem port in this repository; TCLock rwlock results
are a separately labelled reference and cannot serve as its replacement.

## KD rwsem

The reader count and writer-admission word sit outside the embedded KD mutex.
Admission `0` lets readers enter; `-1` reserves one ordinary writer; a positive
value counts exact outer-writer reservations. Readers increment and recheck
admission before touching data, undoing speculative increments if a writer won.
They always execute locally and may sleep while holding read access.

An ordinary writer reserves `-1`, takes the physical mutex locally and waits for
existing readers to finish. It retains local cancellation, trylock and downgrade
semantics. Downgrade publishes its reader count before releasing the mutex and
reopening admission, so no writer can enter between exclusive and shared access.

An outer writer joins a positive phase and drains readers while still
schedulable, before `KD_MUTEX_OUTER_LOCK` can publish a pinned request. The phase
prevents new admitted readers and ordinary downgrades during that cohort.
Writers then use the unchanged KD mutex exclusion, queue and ABI2 execution.
After the matching mutex unlock/acknowledgement returns, the original task
releases its reservation. Only the final reservation reopens reader admission.

The accepted wait policy uses separate phase and reader-drain waitqueues. Before
an uninterruptible sleeping wait, a caller checks its condition at most 16,384
times, stopping early when scheduling is needed. A predicate can retain its own
atomic retry loop, so this is not an elapsed-time bound. Published mutex waiters
do not adopt this sleeping policy. Outer writers cannot cancel after publication,
downgrade or act as nested rwsem controls inside a translated body.

New outer writers may extend a positive phase while readers or ordinary writers
wait; this does not reproduce Linux's fairness policy. No bounded wait or general
oversubscription guarantee follows. See the [rwsem implementation](rwsem_implementation.md)
for ordering, exact reservations, wakeups and retained performance limitations.

## Publication, lifetime and validation

KD uses acquire/release queue/result publication and exact ownership,
reference and ACK state. PAUSE and prefetch supply neither ordering nor
lifetime. TCLock retains the upstream x86 atomics, barriers and WRITE_ONCE
notifications; a WRITE_ONCE store is not a portable release contract by
itself. The stack-switch ports are scoped x86 implementations.

For shutdown, stop new calls and join every worker. Wait for queues, frames and
unlock acknowledgements to finish, then retire KD sources and clear TCLock's
diagnostic target pointers. Unload the workload before the provider. A single
idle sample cannot prove that another caller will not enter. If a drain returns
EBUSY, keep its storage and references alive; never force unload.

Returned-body KD JIT evidence and TCLock mutex returned-batch delegation
counts are separate from payload correctness. TCLock spin and rwlock delegation
counts remain unmeasured. For KD rwlock and rwsem, JIT share uses completed writes
as its denominator. Performance acceptance, failed candidates and remaining gaps live in
the [current performance status](../PERFORMANCE.md),
[RCUHT rwlock report](../../bench/results/380G10/bench/rwlock_compare/20261010-rcuht/README.md) and
[historical spin/mutex report](../../bench/results/380G10/bench/tclock_compare/20261008-protocol-simplification/README.md).
Those original-host reports retain their historical source and topology. The
[current mutex report](../../bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md)
compares accepted compatibility and KD-only mutexes on c01/post64 and pipebytes n16.
The [accepted rwsem report](../../bench/results/10.176.26.71/bench/rwsem-optimization-20261018/README.md)
retains its sleeping-semaphore comparison and separate spinning-rwlock reference.
The [current taskname/xattr report](../../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
measures the direct original-helper path on spinlocks. These source revisions,
lock families and workload results are not pooled.
