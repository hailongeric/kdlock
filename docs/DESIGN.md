# kdlock Design

This document describes current implementation contracts, not a chronological
test log. Usage and execution flow: [JIT_EXECUTION](JIT_EXECUTION.md).
Exact registers: [JIT_REGISTER_ABI](JIT_REGISTER_ABI.md).
Current failures and historical evidence: [VALIDATION](VALIDATION.md).
Priorities and explicit deferrals: [TODO](TODO.md).

## 1. Motivation And Scope

The implementation, tests and planned work target x86_64 machines only.
Cross-architecture adaptation is outside the project, not a deferred feature.
The [delivery scope](TODO.md#delivery-scope) prioritizes supported main paths;
rare-case generalization and dedicated tests are optional. The limits below
describe unsupported or unproven behavior, not a requirement to implement and
test every exceptional interleaving before current delivery.

kdlock combines lock delegation with dynamic translation of existing kernel
critical-section machine code. A combiner executes a waiter's supported code
under real lock protection without rewriting that critical section's source.
Existing patched lock hooks are required. The current tests use purpose-built
workloads, not a validated unmodified production subsystem.

The design is inspired by TCLock-style delegation and BCD's binary execution
machinery, but adapting user execution to kernel code requires additional
ownership, context and lifetime rules. Address substitution is not a context
switch. JIT is not a security boundary, and a performance benefit remains to
be demonstrated separately from correctness tests.

## 2. System Overview

```text
benchmark ioctl -> klock workload -> existing Linux lock hooks
                                       |
                                       v
             kd_lock / kd_hotlock -> spin or mutex scheduler
                                       |
                         native physical lock + execution frame
                                       |
                                       v
                  exe.c <-> /dev/kd_dev <-> daemon
                    |                       |
                    v                       v
               JIT wrapper             miasm translator
                    ^                       |
                    +-------- jit.bin ------+
```

Hooks discover entry RIP and register backend kind. The daemon reads kernel
text, selects the possible JIT range, checks admission, emits/assembles code
and publishes it. Executors use explicit waiter registers and frame state.
Only the frame-backed spin/mutex entry remains; no user/futex frontend is active.

## 3. Kernel Hook Layer

Existing spin and mutex hook pointers pass the lock address, saved hook RSP
and return RIP. The latter is the instruction after lock acquisition.
Exact hook stack offsets are defined in the ABI document and the captured
[kernel baseline](../kernel_baseline/README.md).

`target_process` matches an exact task comm. Spin also recognizes live local
acquisition tickets; mutex recognizes active task records. These preserve
unlock routing through rename and native continuation. Eligibility affects
delegation, never which physical exclusion lock protects the data.

Hotlock sampling uses a bounded 131071-slot append-only table:
`INIT -> CHECKING -> DELEGATE/IGNORE`. After a module-wide one-billion-cycle
warmup, 10000 samples before the lock's own deadline promote it. Each lock
captures the same fixed 2.5-billion-cycle window at INIT-to-CHECKING. Another
lock's speed or discovery order cannot shrink either new or in-flight windows.
The former global shrinking policy made a slower B permanently IGNORE after a
fast A, even when B met the original threshold; that coupling is removed.
Elapsed time equal to the deadline still selects IGNORE, including at sample
10000. Frequency, warmup, bounded allocation and ordinary admission are not
bypassed, and no production force-promotion switch is added.
The initial TSC read serves only the warmup fast check; sample timestamps are
read again under the table lock so their order matches state updates. Otherwise
an earlier caller arriving at that lock later could subtract a newer begin
timestamp, underflow elapsed time and select IGNORE. This serialization does
not establish TSC synchronization across CPUs.
Spin samples lock/unlock, mutex samples lock. Decisions are sticky.
Frequency is not measured contention or a guarantee that delegation pays off.
This is deterministic only for the same per-lock sample timestamps, not for
arbitrary scheduling, CPU frequency or workload changes. Sticky IGNORE entries
are not automatically resampled if a workload later becomes hotter. Timing and
failure interpretation are in [usage 3.2](JIT_EXECUTION.md#32-热锁晋升与翻译准备).

Default work changes kdlock only. Missing hook capabilities and hook-reader
lifetime need separate assessment, not incidental guest kernel edits.

### 3.1 Source, Lock And Hook Lifetimes

These are separate contracts, not solved by preserving a mutex's physical
owner or by the deferred immutable-JIT work. The earlier capability audit is in
[VALIDATION](VALIDATION.md#source-and-hook-lifetime-review).

| Object | Current identity and retention | What is not established |
| --- | --- | --- |
| JIT entry/source text | `(0, RIP)` key; root/read/ordinary-target pins retain up to 64 LIVE modules for the session; retirement invalidates every used entry before releasing dependencies | No concurrent code versions or in-session source replacement; init/unknown source is refused |
| Translation session | Daemon/cache/children share a writer open description; real kcore reads acquire source pins before inspection | The trusted publisher must follow this path; pins do not prove byte immutability or arbitrary pointer/resource lifetime |
| Hotlock / mutex shadow | Append-only address-keyed maps for the kdlock session | A reused address inherits sampling/metadata; no lock allocation/free notification or per-object retirement |
| Spin gate | Stable address-keyed gate; `generation` distinguishes physical ownership intervals | Not a lock allocation epoch or source-code version; an idle entry can serve the same address again |
| Active request | Tickets, task records, native registrations and owner ACKs; successful frame push retains a provider ref/source lease until actual pop | No containing lock-allocation pin or protection before entering the guest hook/after frame pop |
| Hook provider | Plain guest function pointers into kdlock; device fops has `.owner=THIS_MODULE` | A `/dev/kd_dev` reference is not protection for independent lock-hook readers |

See [registration](../kernel_module/exe.c), [hook publication/removal](../kernel_module/kd_main.c),
[mutex shadow lookup](../kernel_module/kd_lock.c) and
[spin gate ownership](../kernel_module/kd_spin_gate.c). An idle reused lock
address does not by itself establish broken exclusion: both backends still
acquire the newly initialized original lock. But the tables cannot tell old
and new object lifetimes apart, reset policy or prove safe reuse while any
old request/physical owner still exists. A logical final A ACK can precede
physical batch release; it is not permission to free a containing object
still used by another request or owner.

The captured guest has four plain spin/mutex lock/unlock dispatch sites.
Each calls `is_kd_test()` or `is_kd()` before deciding whether the task is a
target, so non-target kernel tasks are readers too. `exc_int3` also reads the
shared spin predicate before checking the legacy `kd_do_int3` pointer, even
though kdlock does not install that trap callback. Clearing the six lock-hook
pointers and calling `synchronize_rcu()` does not provide these readers with a
matching acquisition/lifetime protocol. Stopping benchmark callers and draining
requests is necessary for current recovery experiments, not proof of generic
hot unload. `rcu_barrier()` for task records solves a different lifetime.

The current guest exports `try_module_get/put` and module notifier registration.
`__module_address/__module_text_address` are not exported in its Module.symvers;
the implementation resolves `__module_address` through existing kallsyms support.
A raw spinlock keeps preemption disabled through lookup and successful reference
acquisition. Such a reference
must span source inspection, publication and any execution/native return using
that source, including learned callees. A pointer lookup or text hash alone
does not pin code or module-owned data. The normal delete-module path sets
GOING, calls the module's `exit()`, then sends the GOING notifier. That notifier
cannot veto an exit that has already destroyed source-owned resources.

Blindly pinning every source module until kdlock exit is also insufficient:
the current `klock_module.ko` already depends on `kdlock_km`, so pinning it in
the reverse direction prevents either module being normally unloaded first.
A separate terminal retirement boundary now releases source pins before either
exit; force-unload is not a solution. The benchmark's own fops
reference and module dependency protect its controlled ioctl lifetime, not an
arbitrary module source or cached image after source reload.

The device-session prerequisite is now implemented in userspace: one daemon
descriptor spans requests, compilation and publication; only translator children
inherit it, and Python validates the device identity before real text reads.
An orphaned translator retains the same open description. The live cdev probe
checks normal unload refusal at each stage, not reader protection after the last
close. Detailed flow, control commands and direct-CLI restrictions live in
[the daemon guide](../daemon/README.md#device-session). Wire structures and the
two-word wrapper ABI are unchanged; source controls are separate ioctls.

`kd_source.c` implements session-wide residency, not per-image reclamation:

1. Root registration pins LIVE module core text before installing metadata.
   Each real read pins its bounded range before kcore inspection, including
   learned/cold windows. Core kernel init and module init ranges are refused.
   Read windows can include resident data, but roots and ordinary native CALL
   targets must be text. Dependencies are deduplicated and retained even after
   partial refusal, because older images can still use them.
2. A writer get and frame push serialize with OPEN-to-DRAINING. Frame leases
   cover native/remote continuation through actual pop, including failed-push
   rollback. Ordinary CALL miss pins the target before native transfer/learning;
   failed target residency after progress is non-continuable, never entry replay.
3. Retirement serializes against uploads, closes fresh selection/registration,
   and refuses while writers/frames or known queue/task/origin state remain.
   Existing task/origin routing survives closing for owner unlock notifications.
   Existing leased reads/targets can finish while DRAINING, not new publication.
4. With the external no-new-callers boundary and all holders drained, retirement
   publishes NATIVE_ONLY under the registry gate, then drops source references
   outside the raw lock. RETIRED is terminal; slots/images are not reused or
   reopened. All source/provider modules can then exit in dependency order.

The source limit is 64 distinct modules, with no hook-time allocation; each
read is limited to 256 KiB. Built-in resident ranges need no module ref. These
checks do not pin arbitrary dynamically freed objects or prove source bytes
unchanged. Idle observations are not a generic hook-reader barrier. A frame's
provider ref also cannot protect the earlier dispatch or code after its pop.

The dual-queue lifecycle gate also fills the actual 64-block executable pool
through real cold mutex CALL sites while both earlier native frames remain
live. An independent three-client queue then hits pre-wrapper not-ready refusal
and completes under each caller's own native ownership. Existing block identities
and images survive; the old frames subsequently complete all owner ACKs. This
does not compile the filler sites, exhaust all 511 registry slots, reclaim code
or authorize replay after progress. The same gate then tests a surviving
compiler-child writer and source replacement under terminal retirement. The
writer can inspect pinned
text while DRAINING but cannot publish, and it independently blocks retirement
after frames finish. Once fully retired, the same provider/registry remains
loaded while the test source is normally reloaded. ELF lock-CALL return sites,
module bytes and runtime code/lock addresses must match; both native mutex wait
lists must reach three callers. Six fresh records complete without JIT or owner
ACKs from kdlock. This is a quiescent, retired-session reuse test, not concurrent
source replacement or proof of arbitrary lock allocation lifetime. It does not
exercise multiple live source modules. The separate learned-depth gate now
executes a second module's translated seven-lock prefix and returns to its real
local helper before the eighth-child capacity exit. Root and learned text each
add one
source pin. The helper's native loader reference is observed separately:
1 before its CALL miss, 2 after pinning, 1 after retirement, 0 after the importing
module unloads. Both sources normally unload with the old registry terminal.
This is two-module coverage, not live saturation of the 64-module bound.

The two-frame gate also tests task routing independently of target comm:
both borrowed waiters rename in their native callees, then acquire/unlock
independent C mutexes as their own physical owners while A/B remain borrowed.
Both frames are live and source admission is still OPEN. The C unlock must
not consume A's active-task reference or become a borrowed-owner ACK. The
renamed identity remains through the later B/A ACKs and completion record.
This uses existing routing and physical ownership, not owner handoff.

Non-target callers then queue on both retained native B mutexes. Each actual
wait list must contain its identified peer; pidfd SIGUSR1 cancels each native
interruptible wait, returns EINTR to userspace and permits one explicit retry
by that same caller. Both wait lists must be observed again before retirement.
After the first frame's B release, its peer acquires/releases B as its own
Linux owner while the other frame's B still rejects trylock. That frame cannot
resume until this observation and the first original waiter's final ACK
complete. No peer enters JIT, borrows a lock or adds a kdlock task reference.
These are composed routing/native-peer checks, not arbitrary cancellation,
fairness, object lifetime or additional hook-reader protection. Execution
order, evidence and affected-only commands are maintained in
[usage 6.6](JIT_EXECUTION.md#66-独立队列的并行-native-frame).

The same two drain orders now compose signals to the original borrowed waiters:
SIGKILL for the first, SIGUSR1 for the survivor, after native-peer requeue and
before source closing. Each waiter is one ioctl process. The first completes
its native record and real B/A owner ACKs before fatal syscall exit. A bounded
fixture gate keeps the second frame alive until the controller's retained
pidfd observes that exit and source reports one frame. The second then completes
under its unchanged physical owners and returns after one userspace signal.
This adds no task reference or production lock policy; it is pending-signal
completion, not permission to abandon a frame, call do_exit inside the suffix
or claim arbitrary task/RCU/hook-reader lifetime safety.

Capability assessment under the no-guest-edit default:

- Bounded source pins and terminal metadata retirement are implemented entirely
  in kdlock. They require a real external no-new-callers boundary and are not
  concurrent versioning or automatic subsystem lifetime integration.
- Generic lock allocation/free identity is absent from the lock hooks. An
  arbitrary `kfree()` or embedded-object reuse cannot be inferred from an
  unlock. It needs subsystem lifetime integration or separately approved
  allocation/free interfaces, not owner handoff or a guessed idle timer.
- Generic provider hot unload requires protection before a guest reader
  enters the predicate/callback, coherent hook publication, and draining of
  dispatches plus retained requests. A reference added inside the callback
  cannot protect the earlier jump into it. An unconditional put after the
  hook call is not enough either: `jump_to_saved_regs*()` may bypass that C
  return. Reference release must cover those nonlocal continuations too.
- A future kernel-side design must audit at least the four existing lock
  dispatch sites and the shared `exc_int3` reader, plus registration/drain and
  nonlocal-exit interfaces. That is more than an unverified extra condition;
  no implementation-backed line estimate or approval is claimed here. Actual
  guest-kernel changes for this review: **zero**.

Retain stable lock-allocation lifetimes during a session, retire source pins
explicitly, and use only the controlled recovery procedure in
[AGENTS](AGENTS.md#验收与清理). Replacing a source module requires a fresh kdlock
and daemon session after draining, not merely a new TGID or clearing daemon
workspaces. This remains an experimental boundary, not safe hot-reload support.

## 4. Spin Delegation Protocol

### 4.1 Native Lock And Private Queue

Linux qspinlock **L** remains the sole physical exclusion lock. kdlock uses a
separate scheduler word/tail **S** and private nodes; native and kdlock queue
encodings must never share L's tail. A scheduler handoff alone does not permit
critical-section execution: the physical executor first acquires L.

Native plain/trylock/IRQ-save/BH participants use Linux L. Their mutual
exclusion does not imply that IRQ/BH operations can be delegated; known
context-sensitive wrappers refuse translation.
The old shared-tail protocol and its compatibility claims are obsolete.

### 4.2 Acquisition Tickets And Node Lifetime

The physical hold and original waiter acquisition are different objects.
`kd_spin_hold` records real owner task/CPU/generation.
`kd_spin_ref` points into a stable origin-ticket pool with a generation.
A virtual B request carries the original HOOK waiter's `spin_origin`, while
its physical executor's acquisition ticket belongs to that executor.

Only the original waiter can end its pin/preemption obligation. A combiner
cannot remotely unpin it. Native borrow references defer completion until
the last owner ACK. These metadata do not add wrapper arguments.

Each CPU has four exact node reservations. Reserved-but-not-yet-acquired
nodes count as occupied; completion cannot release a different slot or use
a held-only count. Reservation spans every published queue pointer, saved RSP,
request and borrowed reference. Published/woken nodes may immediately be
reused; snapshot needed data before wake and never read them afterward.

Spin completion release-publishes the combined `completed=1/locked=0` word
after the final register packet is copied. Lone/IRQ-native and batch-successor
handoffs also use release stores; their acquire-side waiters may immediately
consume or reuse the node. Queue splicing must finish before publication, and
the publisher uses its saved successor afterward. This makes the publication
contract explicit; it does not transfer physical ownership or prove arbitrary
memory ordering, task lifetime or flags semantics through a userspace fixture.

### 4.3 Combiner And Native Returns

The combiner owns L and S while processing an eligible batch, validates entry
readiness/context, reconstructs waiter registers and enters a frame.
Unstarted work can receive native handoff. Partial JIT progress cannot be
converted into entry replay.

Ordinary acquisition returns restore `kd_spin_native_input.rsp`.
Nonlocal paths restore the lower of saved node RSP and virtual RSP before
copying state, preserving virtual CALL frames that grew into the old hook
frame. Completed paths end their own ticket only after taking the needed
snapshots. Return 5 means native continuation and retains the origin pin
until the final native ACK, not full completion.

The combiner eventually executes its own original critical section.
If logical A was released early, it must reacquire A first; see 9.4.

### 4.4 Nested Contention And Stack Resources

At B's lock CALL, a virtual spin waiter copies current GPR/RIP/RSP, explicit
held locks, GS/task and origin reference. A remote B combiner can execute it.
It uses the root/parent artifact with B's continuation RIP, not a separately
truncated B artifact that cannot represent A's later flow.

Logical requester/`resume_target` chains differ from physical C-frame chains.
A physical parent may wait on its own shadow stack while a child executes on
another CPU. Its C locals, frame and stack remain live until child completion.

Each shadow stack is 8 KiB; frame and held-lock depths are bounded at eight.
Frame count, logical depth, held-lock count and node reservations are distinct
resources. Sampled stack margins are not an arbitrary IRQ/NMI safety proof.
NUMA-local batching is opt-in; it is not a different physical lock protocol.

## 5. Mutex Delegation Protocol

### 5.1 Physical Lock And Scheduling Gate

`kd_mutex_shadows[]` maps original mutex addresses to 1024 bounded scheduler
entries under `kd_mutex_shadow_lock`. An entry contains a queue, `locked` gate,
and `physical_owner`. **Neither the gate nor a queue handoff grants exclusion
without the original Linux mutex being held by the tracked physical owner.**
Borrowed native execution does not change that owner; it follows the explicit
execution/unlock-notification protocol in section 5.3.
Unlock lookup never creates entries; table exhaustion uses the original mutex.
The old `delegated` transition and `mutex_origin_users` draining are removed.
There is no interval in which promotion substitutes a different exclusion lock.

The module's `kd_origin_mutex_lock/unlock()` use the existing native owner
fast paths and already-exported `__mutex_lock_slowpath` /
`__mutex_unlock_slowpath`. Ownership is checked against `current`, masking the
three native owner flag bits. kdlock does not invent an owner value, assign
ownership to the waiter, or modify native wait lists or handoff flags. This
implementation is tied to the tested non-RT 6.1.159 configuration without
DEBUG_MUTEXES/DEBUG_LOCK_ALLOC; other configurations require separate review.

Native trylock/interruptible/killable callers use the same original mutex.
Linux handles their cancellation and HANDOFF flags under its own wait lock.
They are independent native callers, not cancellable delegated requests.
The workload observers never rewrite owner flags or wait lists; bounded
signal/release tests do not cover every internal interleaving.

The existing nested mode 4 workload now tests a bounded seven-role/two-CPU
schedule: B's holder observes A's physical executor in B's real wait list on
the same CPU before releasing B. That executor subsequently completes JIT;
this is not original-waiter native continuation or a change to mutex ownership.
The [execution flow](JIT_EXECUTION.md#612-同-cpu-的嵌套-mutex-jit) distinguishes
this scheduling check from PENDING recovery and independent-queue refusal.

Mode 4 also has a separate shared-B session: A0's physical combiner retains
A0/B across an ordinary CALL miss while A1's combiner and a non-target peer
both wait on that exact Linux B. The waiter requests owner-side unlock/ACKs;
A1 then completes its own JIT and the native peer acquires as its own owner.
This exercises cross-frame exclusion, not a spin-style remote B combiner or
owner transfer. The [shared-B flow](JIT_EXECUTION.md#615-两个-a-combiner-共享原生-mutex-b)
keeps publication, actual JIT, real wait-list identities and exact effects
distinct from merely completing all clients.

### 5.2 Entry, Completion, And Task Routing

1. Cold locks, `mutex_jit=0`, shadow/task-record allocation failure, and nested
   acquisitions by an already-active task go directly to the original mutex.
2. A promoted, eligible request registers its task before entering the scheduler.
   Winning the gate calls `kd_mutex_claim_origin()`, which acquires the original
   mutex and records `physical_owner=current`, before entering any CS.
3. Queued waiters capture the hook stack and waiter GS/task. Their combiner
   verifies real ownership, reconstructs `pt_regs`, checks exact entry readiness,
   and executes the translated CS in a frame. Missing code or a busy per-CPU
   frame context receives an unexecuted queue handoff. That next owner must
   acquire the original mutex; it cannot inherit exclusion from the gate alone.
4. Successful JIT execution reaches the final required unlock and completes its
   frame: normally A, or the last nested B after an earlier logical A unlock.
   The waiter snapshots published registers, releases its exact bitmap slot,
   restores preemption/migration state, drops its task record, and resumes
   after the logical unlock. The combiner can retain the original mutex across
   several requests, then run its own CS before unlocking as its real owner.
   Early A-before-B release instead detaches this batch, lets A's queue proceed,
   and requires reacquisition before the old combiner's own CS; see section 9.4.
5. `_kd_mutex_unlock_checked()` releases the original mutex before opening the
   scheduling gate. Native participants can acquire it between scheduler owners.

Each CPU has four independently reserved 8 KiB waiter stacks. An exhausted task
never publishes a queue node; it waits on its native stack for the gate and
then acquires the original mutex. Migration stays disabled during queued waits,
but preemption is temporarily enabled where scheduling or native locking is
required. A scheduled combiner retains ownership of its per-CPU frame context;
another task cannot overwrite it.

Resource tests compile the production reservation, shadow lookup, hooks and
entry/return consumer. They check no-node acquisition and copy-before-slot-reuse
with the guest's complete `pt_regs`; physical locks, scheduler, task records and
assembly are substitutes. Their scope and live-test separation are maintained
in [the mutex resource guide](JIT_EXECUTION.md#61-mutex-资源与恢复包).

`kd_mutex_tasks.c` keeps RCU-readable task membership with a task reference and
lock-protected acquisition refs. The existing mutex `is_kd` callback matches
target comm or membership. This preserves unlock routing after a rename; it
does not replace the original lock. `mutex_task_fail_once=1` tests pre-entry
allocation failure. No allocations are needed in the predicate. Unload requires
all callers stopped and records/queues drained; `rcu_barrier()` only completes
deferred task-record frees, not general hook hot-unload protection.

The opt-in `test_22` connects these real task functions to the production
native request/ACK path, with an actual RCU reader spanning final removal.
It covers both B-before-A and A-before-B unlock, shared acquisition refs and
deferred callback execution. Its constructed continuation and outer batch
callback do not exercise JIT or queue scheduling; see
[the lifecycle guide](JIT_EXECUTION.md#62-task-引用最终-ack-与-rcu).

#### Runnable Polling And Event Parking

`kd_cond_load_acquire_sched()` observes a linked waiter's `locked` byte with
acquire ordering, calls `cpu_relax()`, and temporarily enables preemption for
`schedule()` when `need_resched()` is set. It does not set a sleeping task state
or register an event wakeup. The scheduling gate follows the same runnable
polling policy. Migration remains pinned to retain the reserved CPU-local node
and stack. Direct Linux mutex B acquisition and native-owner ACK handling are
different waits, not covered by a linked-node parking change.

A promoted, published entry does not guarantee a delegatable batch. A queue
head can remove its sole tail and run its own original CS; `run_combiner()`
hands the last follower onward when it has no successor. Eight userspace
threads on two CPUs need not produce eight simultaneous queued requests.
The [CPU-mask assessment](VALIDATION.md#mutex-oversubscription-assessment)
records an actual prepared-but-unexecuted JIT point, not an admission failure
or permission to count native completion as JIT.

The local TCLock revision identified in section 13 has a different linked-waiter
handshake in both `rcuht/locks/komb_mutex.c` and its Linux `kernel/locking/mutex.c`:
when rescheduling is needed and another task can run, an UNPROCESSED waiter
sets TASK_INTERRUPTIBLE and atomically enters PARKED. The waker changes it to
PROCESSING and wakes a parked task with `wake_up_process()`. Its queue-head gate
still polls, and its last-node handoff also avoids delegation. This is a source
inspection, not a TCLock run or proof that it solves this measured workload.

Do not copy those completion values into kdlock: here PROCESSED is 1, which
TCLock uses for PARKED. A future module-only implementation needs an explicit
sleep/wake handshake spanning normal completion, unexecuted handoff, early outer
release and native-resume publication. The waker must retain the task/node until
its last access; the existing final release-store permits immediate node reuse.
Original Linux owners, pending native unlocks and final ACK order stay unchanged.
Current measurements do not isolate polling cost or justify a default policy
change. Event parking remains unimplemented performance work, not a guest-kernel
edit, a flags change or a claim of arbitrary-oversubscription support.

### 5.3 Nested A -> B And Native Continuation

Nested B no longer creates a virtual mutex waiter or remote B combiner:

1. At translated `mutex_lock(B)`, validate the frame, return address, depth and
   non-recursion before touching B. Mixed spin/mutex control calls are rejected.
2. The same A combiner enables preemption while remaining migration-pinned,
   tries the original B, and waits via its native slowpath if contended.
3. Once it physically owns B, record B as `KD_EXEC_LOCK_NATIVE`. **Only then**
   consume the virtual CALL return address and resume A's artifact after the
   lock call. B need not be promoted or have a separate artifact.
4. Translated B instructions execute under real A/B ownership. Its known unlock
   releases B on the same combiner, pops the frame entry, and increments
   `nested_jit`; A continues in the same artifact until its outer unlock, or
   completes there if A was already logically released (section 9.4).

An ordinary CALL miss instead preserves exit GPRs/RIP/virtual stack and resumes
the original waiter natively. The combiner retains real A and any still-held B,
stops processing its own batch, and services that waiter's unlock messages.
Other CPU-local combiners for independent lock queues are not globally paused.
The waiter cannot directly unlock a mutex owned by the combiner. Native nested
unlocks release B on the actual owner; outer unlock acknowledges logical
completion while A stays held until the combiner finishes its own ownership
interval. No native `owner` handoff or new kernel protocol is introduced.

The waiter's acquisition reference survives until the combiner releases this
frame's last retained logical lock, removes its native registration, and drops
that reference before acknowledging. The final reference removes task membership;
RCU readers can retain the unlinked entry until its deferred free callback.
This logical ACK need not release physical A in a still-owned batch.
New native acquisitions by the waiter are ordinary original mutex acquisitions.
The combiner must not inspect a published waiter
node after wakeup because it can already have been released and reused.
Native continuation is counted by `kd_native`, not all-JIT completion counters;
unhandled post-entry errors remain fail-stop, never entry replay.

The original native waiter can share a CPU with its retained physical owner.
Its new B acquisition uses the native route, not another JIT context; queued
waits and owner/ACK waits must allow the peer task to run. The existing
`native-4-4` gate now checks this with three A queue tasks on one CPU, real B
contention and an injected PENDING exit. Only mutex workload barriers and
observations change, not the production scheduling or ownership protocol.
Flow, placement evidence and limits are in
[usage 6.1](JIT_EXECUTION.md#61-mutex-资源与恢复包). This successful continuation
is distinct from refusing another queue's unstarted JIT request below.

Native registrations are matched by logical task, backend and retained lock,
not by a single global "current waiter". The opt-in
[dual-queue workload](JIT_EXECUTION.md#66-独立队列的并行-native-frame) keeps two
real mutex native frames alive at once and checks both drain orders. Each has
its own physical A/B owner, waiter record and stack-local ACKs. It uses separate
published entries with the daemon stopped; an ordinary miss makes its entry
not-ready, so this does not test concurrent code replacement or imply that a
second invocation of the same entry can always start after that miss.

A scheduled mutex combiner retains ownership of its CPU-local execution
context, not only its physical mutexes. A different combiner on that CPU must
refuse an unstarted JIT request even when its entry is ready, then use ordinary
queue handoff and native ownership. The
[same-CPU workload](JIT_EXECUTION.md#67-同-cpu-的-mutex-jit-拒绝) keeps the first
frame live until the second queue finishes natively. Its one body/frame and
two ACKs are distinct from the two-frame overlap case; the refused entry
stays NORMAL. Neither path overwrites or borrows the foreign task's frame.
Its pressure extension retains that frame while four genuine CPU-local nodes
are occupied. The extra request reserves no node, waits for the private gate
on its own stack and then acquires the original mutex as physical owner.
This unstarted fallback neither borrows a frame nor sends owner ACKs. It is
distinct from a progressed JIT continuation and does not establish gate fairness.
The same test then injects one task-allocation failure for a different request
before its A1 queue entry. A node-refused request already owns an A1 routing
reference and waits for its scheduling gate; a task-refused request has no such
reference and acquires original A1 directly. Its later native B1 hook can still
establish its own bookkeeping. Both must finish their exact records and own
unlocks before the older frame resumes and receives its retained owner ACKs.
The added task diagnostic identifies the pre-entry branch; it does not change
native ownership, task reclamation or the guest hook. This is one combined
allocation-refusal schedule, not global memory saturation or arbitrary task exit.

Signals do not transfer physical ownership or cancel a retained frame. The
ordinary native `mutex_lock(B)` suffix waits uninterruptibly, including with a
fatal signal pending. It must finish B, the remaining effects and the final A
owner ACK before Linux delivers the signal on return to userspace. The opt-in
[original-waiter signal test](JIT_EXECUTION.md#64-原-waiter-的信号与退出) checks
this bounded path and direct ordinary CALL misses to native
`mutex_lock_interruptible/killable(B)`. With B kept held, Linux returns
`-EINTR` on the original waiter: B was not acquired, so its error suffix skips
B's critical section and unlock. In a signal/release race the API may instead
return 0; the waiter then really owns B and executes/unlocks B once. Both
branches still complete the borrowed A unlock and final owner ACK. A release
request is not proof of physical unlock; the test records the actual owner's
unlock bracket and the native return separately. This is a new B acquisition,
not rollback of A or cancellation of its retained delegated frame. These APIs are
not added as translated lock controls or hostcalls. `do_exit` inside the suffix
and arbitrary abandonment remain unsupported.

Borrowed execution does not make `mutex.owner == current` true on the waiter.
Code that inspects ownership, recursively acquires a borrowed mutex, relies on
lockdep ownership, or requires task/CPU-local lock side effects is outside this
subset. It needs eligibility rejection or a separately evaluated service,
not an assignment to native owner bits.

Mode 4 uses actual independent B contention. Mode 11 is now a context-refusal
negative test, not a positive nested-JIT oracle. Current main-mode results and
the scope of the separately bounded fixtures are recorded in [VALIDATION](VALIDATION.md).

### 5.4 Differences from Spinlock Path

| Aspect | Spinlock | Mutex |
|--------|----------|-------|
| Queue structure | Per-CPU `kd_spin_node[4]` | Bitmap-reserved per-CPU `kd_mutex_node[4]` |
| Exclusion | Original Linux qspinlock L, held by the physical executor | Original Linux mutex and its actual owner |
| Scheduler state | Private S word/tail, never overlaid on L | `kd_mutex.locked/tail`, never sufficient for exclusion |
| Scheduling | Non-sleeping spin protocol | Waiters may schedule while migration-pinned |
| Nested contention | Virtual spin waiter and combiner snapshot | Same combiner waits for native B |
| OOO unlock | Owner-side A/S release, logical-parent rendezvous and ticket-preserving reclaim | Native A/S early release, same-owner B and A reacquisition after suffix |
| JIT disabled | Per-lock spin readiness policy | All mutex calls use original native protocol |


## 6. JIT Execution Engine (exe.c)

### 6.1 Code Block Management

At module init, `kd_exe_init()` pre-allocates a pool of 64 executable memory
blocks (each 160 pages = 640KB).  These are vmalloc'd and marked executable via
`set_memory_x()`.  When `kd_exe_add()` is called from the lock hook (possibly
with IRQs disabled), it takes a block from the pool without calling vmalloc.
Only blocks for which both allocation and `set_memory_x()` succeeded enter the
pool. Pool or translation-table exhaustion fails closed.

Registration publishes a new key only after obtaining its code block. If the
pool is empty, the unused slot is left unchanged and existing entries remain
usable. Re-registering an existing key consumes no block, even after a miss or
terminal policy refusal. Allocated blocks are retained until drained module
teardown, not returned to the pool on native-only publication. Thus the 64-block
pool fills before the 511-slot execution table in the current configuration;
the full-table lookup guard still has an independent bounded-probe test.

The full executable pool is 40 MiB. These blocks remain writable; there is no
RW-staging/RX-publication transition or code-generation lifetime protocol.

Kernel critical-section text is shared across all tasks, so kernel-lock JIT
entries use a **RIP-only key**: the hook calls `kd_exe_add(0, ret_addr, kind)` and
`kd_exe_on_call_hl_entry()` looks up `kd_get_exe(0, entry_ip)`. This avoids binding a
translation to one short-lived benchmark thread or process ID.

Registration records immutable `KD_EXE_LOCK_SPIN` or `KD_EXE_LOCK_MUTEX` in
`kd_exe_info.lock_kind`, using offset 12's former alignment padding. The entry
remains 64 bytes and existing field offsets are unchanged. Different kinds at
the same key make it native-only, not a second executable backend. High-level
entry checks the frame kind before invoking the wrapper. This does not revoke
already-started execution or provide immutable JIT versions.

The translation hash probes at most `KD_MAX_EXE` slots. It returns `NULL` when
full rather than looping in atomic/IRQ-disabled context. Code-block allocation
uses an atomic gate and never waits for the userspace daemon.

An unavailable root entry returns before wrapper execution; spin/mutex queue
handling then lets the unstarted waiter obtain native execution. This is not
PENDING-lock continuation after progress. Resource classes, tests and remaining
coverage gaps are listed in [the usage guide](JIT_EXECUTION.md#6-资源拒绝与测试边界).

### 6.2 Entry Lifecycle

```
KD_EXE_UNUSED -> KD_EXE_UNINIT -> KD_EXE_NORMAL
                                      |  ^
                 daemon recompiles   |  | complete write-back
                                      v  |
                        KD_EXE_CALL_MISS / KD_EXE_IJ_MISS

KD_EXE_NORMAL -> KD_EXE_ERROR_INST  (terminal unsupported instruction)

UNINIT / NORMAL / miss -> KD_EXE_NATIVE_ONLY  (terminal policy/backend refusal)
```

`KD_EXE_HOSTCALL` and `KD_EXE_ENTRY_REFUSED` are deliberately absent from this
lifecycle. They are transient sandbox exit reasons handled by the kernel
executor, not translation-entry states observed by the daemon.

### 6.3 kd_exe_on_call_hl_entry()

This is the core execution function called by the combiner. Its actual signature
is:

```c
int kd_exe_on_call_hl_entry(struct pt_regs *regs, unsigned long entry_ip,
                            unsigned long outer_lock_addr);
```

1. Validate the active frame, waiter GS/task, and exact `(0, entry_ip)` readiness.
   Require a fresh root or a published logical spin child with matching entry,
   task, GS, post-lock-CALL packet and lock depth. A CPU-local physical parent
   alone is insufficient; this checks logical scope, not image generation.
2. Install the two inputs `{frame->gsbase, frame->logical_task}` and enter the
   wrapper. Conditional images check entry disjointness before body. Only an
   explicit `ENTRY_REFUSED` on the first pristine root call, with original
   RIP/RSP and zero witness, can clear the conservative executed mark and
   return `NO_RUN`. It is not a retry after progress or a daemon state change.
3. On hostcall, enforce budgets, dispatch the typed service, pop the virtual
   return address, save continuation state, and re-enter the same artifact.
4. On a control-call exit, use `handle_known_call()` to acquire/release nested
   locks or recognize the matching outer unlock. Nested and OOO handling may
   continue execution rather than complete the frame. Local mutex controls
   first establish and then verify their stack checkpoint; a changed window
   takes the separately validated native suffix after the completed CALL.
5. On an ordinary CALL miss, retain the virtual CALL frame, record the target
   for future translation, and return `KD_EXE_RUN_NATIVE`. A remote child's
   native exit propagates through `KD_EXE_KNOWN_NATIVE` without re-entering JIT.
   Known nested acquisition has separate phase metadata. A PENDING resource
   failure restores its original CALL RIP/RSP and takes the same native handoff
   without publishing a translation miss; see 9.5.
6. Other unsupported exits return an error. Once `frame->executed` is set,
   backends fail-stop rather than replaying the entry. No stores or services
   are undone. IJ, budget, and arbitrary fault continuation remain deferred.

### 6.4 End-Point Detection

The `end_points[]` array lists kernel functions whose address signals the end of
a critical section.  These are resolved dynamically at module init via
`kallsyms_lookup_name`:

```c
end_points[end_point_count] = kallsyms_lookup_name("_raw_spin_unlock");
end_points[end_point_count] = kallsyms_lookup_name("mutex_unlock");
```

When the sandbox encounters a `CALL` to one of these addresses, it reports
`KD_EXE_CALL_MISS`. For the active high-level path, an endpoint address alone
is insufficient: `regs->di` must match `outer_lock_addr`, known-call handling
must finish any deferred spin OOO release, and the backend must validate frame
completion. An inner B unlock normally resumes A. Only the legacy
`outer_lock_addr == 0` branch accepts `is_end_point()` alone.


## 7. Translation And Publication

### 7.1 Possible JIT Episode

`context_policy.jit_phase_blocks()` selects reachable decoded blocks using
entry and learned targets as roots. For an ordinary direct CALL to a callee
absent from those blocks, it retains the CALL/exit stub but removes the native
return edge. The waiter will complete that suffix without returning to this
JIT invocation.

Control calls, allowlisted hostcalls, decoded callees and indirect calls retain
their relevant successors. An alternate JIT path to a suffix keeps it in scope;
a deleted native edge must not contaminate that path's dataflow.
Every recompile rechecks the newly learned scope. Admission, lexical lock
boundaries, constant propagation, emitted blocks and entry dispatch share it.
Missing reachable branch text is not an implicitly safe empty block.
For a cross-window placeholder whose bytes are already cached, the translator
seeds the owning decoder window and recomputes the selected graph. Decoder roots
are split into dispatch blocks even when they lie inside an earlier block.
These seeds do not become independent admission roots. Text reads and decoder
reseeding share the 32-expansion bound; genuine undecodable blocks still refuse.

### 7.2 Context And Memory Admission

Production admission rejects retained GS memory, FS/base operations, known
per-CPU/current/scheduling/preemption/IRQ/BH/RCU references, backend mismatches
and other recognized unsupported context operations.
The retained GS/current lowering helpers do not imply permission to delegate
those operations. No read-only GS exception is granted.
These unconditional byte/operand checks run across every selected emitted block
before value propagation or its guarded retry. A rewritten RET may leave a
connected block without a propagated input, but its code and whitelist target
still exist. Such a block cannot bypass GS/FS, IRQ, known context-symbol or
foreign-backend checks. This pass uses the already selected JIT episode; it
does not reintroduce an ordinary CALL miss's waiter-only suffix.

Analysis covers explicit operands and lifted IR memory effects, including
implicit/internal-IR accesses, decoded CALL arguments/RET results and CALL
return-slot writes. Bounded facts propagate through selected CFG edges; merges
retain sensitive alternatives. Memory values, masks, alias origins and writes
are checked conservatively. It does not read runtime memory or treat source
RBP/RSP as private memory. Analysis limits affecting addresses refuse admission.

Eligible single-root nested entries can retry address-precision failures with
entry disjointness predicates. Every premise is enforced before generated body
execution; independently enterable callees cannot borrow those root facts.
For learned direct callees, a separate single-entry analysis seeds only the
checked root and propagates real CALL packets and RET effects. It removes the
fabricated immediate CALL fall-through and verifies the complete RET graph
against the generated whitelist. Selected text must be structurally connected
to the checked root before value-based refinement; disconnected targets,
indirect control, IJ history and adjusting RETs are refused. Default
independent-root analysis remains unchanged.
This does not assume callee-saved registers or untouched source memory for an
ordinary function. The predicate/continuation contract is in
[JIT_EXECUTION](JIT_EXECUTION.md#5-入口条件与嵌套续点).

Scoped flow keeps a bounded disjunction of RSP value/origin facts, preserving
the relation between different CALL depths, saved registers and shared RETs.
It checks the plain 64-bit pop IR, then reads its pre-pop target through the
existing sequential memory model. Only an entirely exact numeric domain
restricts effect propagation to its intersection with the emitted whitelist.
An unknown, partially overwritten or widened slot keeps every target; those
destinations join normally instead of enumerating hypothetical pop-depth cycles.
No CALL/RET balancing, runtime stack read or private-stack assumption is added.
Each block permits at most 64 partitions, and total partitions/visits remain
bounded by the CFG work budget. Exhaustion refuses the entry. A structurally
connected continuation skipped by a proven return-slot rewrite need not gain
a fabricated input state. Unconditional checks still cover its emitted bytes;
register/memory effects use the sequential model, not a proof that another
executor cannot rewrite a return slot or pointer before its later load.

The emitted return-table builder groups direct call sites by callee and walks
each callee iteratively with a visited set. Shared RET tails retain the union
of every caller continuation, including targets reached after return-slot
rewrites; a matching source CALL is not assumed. Location offsets come from
the decoded location database, not formatted label names. A 65536-unit work
budget counts instructions, traversed nodes/edges and return-target additions.
An unresolved location, missing walked successor/database or exhausted budget
raises an explicit refusal without committing a partial table. Both scoped
comparison and final emission handle that error as native-only. This is a
translation graph budget, not a runtime instruction limit, hard memory/time
bound or executable-version publication protocol.

Preserving handler GPRs does not prove that saved stack words stayed unchanged.
The two-level mutex helper therefore requires the following runtime checkpoint,
not a private-stack or arbitrary callee-ABI assumption. RET emission, thunk
mitigations and alias checks are unchanged.

The runtime checkpoint for the checked mutex summary is wired into
`handle_known_mutex_call()`. It snapshots 256 bytes above the virtual CALL word,
bounded to the original waiter's live kernel stack, using nofault reads. After
the real local mutex control, it compares those bytes and separately verifies
the captured target/return token and exact post-CALL RIP/RSP. Equal contents
permit the existing JIT continuation. Changed contents set a distinct
`KD_CALL_STACK_CHANGED` phase: the original waiter resumes after the completed
control, with current memory and registers, while the combiner retains native
owners and services unlock ACKs. No writes are restored or acquisition replayed.
An insufficient window exits before the control using a validated PENDING CALL;
an invalid token/read/packet remains fail-stop after progress. Final completion
does not need a preservation check because it never returns to this JIT episode.

The real contention gate now extends the existing seven-role driver. B's native
owner waits for the combiner in Linux's mutex wait_list before writing an
explicitly exposed live waiter-local word. The original waiter observes the new
value after the completed CALL, with A and B still owned by that combiner;
the two unlock ACKs precede suffix completion. The oracle requires the distinct
stack-change warning, actual source CALL successor and unchanged NORMAL root,
not only successful native code. This is one bounded shared-slot history, not
arbitrary concurrent mutation or a stack-privacy assumption; see
[the execution gate](JIT_EXECUTION.md#53-mutex-控制-call-的栈检查).

The provider now advertises this immutable implementation contract through
the separate 16-byte `KD_JIT_CAPS` ioctl. Translation queries its validated
device description once before text inspection, caches only that lease's bound
and clears it on close. Absent/unknown contracts leave the bound zero; actual I/O
errors abort inspection. Version 1 still describes the old mutex bound but lacks
the module range required by current translation (7.2.2). Source INFO remains
mandatory. This is not a mutable
admission bit or executable generation. Guarded mutex analysis now uses the bound
only at registered local controls whose IR matches the exact eight-byte CALL
push and source return token. It first applies that write, then derives checked
window starts from every possible post-push RSP+8. It never restores pre-CALL
facts. Only identical-base, fully covered byte/word facts survive the clobber;
partial words use the byte model. Unknown bases/packets, spin, hostcall and other
memory retain the existing uncertainty and work limits. Coverage checks cannot
refill the analysis budget or add an alias separation to assume membership.
Spin remote controls can execute later source instructions, so this local mutex
contract must not be generalized to them. The check compares
values across this one control boundary; it is not protection from arbitrary
concurrent writes outside that interval, a private-stack proof, or code-version
isolation.

The real depth gate now learns the local and external helpers in two separate,
joined waves, without inlining either CALL level. The final JIT acquires seven
children in the external helper, executes its RET, and reaches the local
helper's eighth-child capacity exit. The remaining local suffix/RET runs natively
with retained owners and ACKs. Source pins and native importer references are
checked separately through retirement; generated userspace tests also execute
both RETs across substituted control successes. This bounded increment is
complete; broader context/alias work remains in TODO C5.

This remains incomplete for arbitrary pointers, unlifted instructions and
concurrent mutation. Improving precision is not grounds for removing safety
probes. A refusal makes future entries native-only; it does not undo earlier
work or validate owner-sensitive native suffixes.

### 7.2.1 Dynamic Address Gap

Unknown entry pointers and addresses loaded from runtime memory are admitted
unless another rule rejects them. `mov rax,[rdi]; mov rax,[rax]` therefore can
reach even a known sensitive interval without embedding its address in text.
A sequentially tracked store does not prevent another thread from changing
that word before a later load. Holding A only excludes users of A; it does not
exclude per-CPU operations or another writer that does not acquire A.

The bounded [pointer audit](VALIDATION.md#dynamic-pointer-screening-gap) executes
these paths against harmless user allocations labelled by mock symbols.
It confirms a missing check, not actual kernel context corruption or a rate of
failure. The entry predicates, local mutex checkpoint, retained native owner
and unconditional emitted-block scan do not close this gap. Successful code
generation now reports `CONTEXT_SCREENING_ONLY`; no runtime guard is added.

**2026-09-13 user decision:** the access-time guard, pre-instruction waiter
continuation and their local condition-code preservation remain deferred and
unimplemented. This is a retained limitation, not a pending scope decision.
The following order is for a future explicit reopening of this feature,
**not an implemented safety contract or the current implementation agenda**:

1. Define the enforceable address/object policy and its lifetime first. Linked
   kallsyms intervals alone do not enumerate runtime per-CPU allocations, task
   objects or aliases with context-sensitive behavior. A known-range denylist
   would protect only that declared range, not establish context equivalence.
   Core static and boot-reserved module ranges are handled below; object coverage remains
   open. Assess existing kdlock/kernel APIs before considering any guest change.
2. Separate entry-only predicates from use-time validation. Entry GPR checks
   cannot validate a later memory-loaded pointer. An access guard must compute
   and check the effective address once, then use that same address for the
   original load/store/RMW, including width/overflow and implicit accesses.
   Reloading a mutable pointer after checking it leaves a check/use race.
3. Define a pre-instruction native exit with unchanged current GPRs, virtual
   stack and required flags. Preserve completed stores and retained owners;
   the original waiter continues at that instruction and unlocks through ACKs.
   Do not reuse entry refusal after progress or treat a generic fault as a
   validated escape. Necessary local guard flags preservation belongs to this
   deferred feature; general flags repair is also still deferred. The
   [future packet contract](JIT_REGISTER_ABI.md#31-访问时续跑的前置契约待实现)
   separates pass-path preservation from native-target restoration; neither
   reading the stale packet flags nor relying on the existing MOV/RET stubs
   implements it.
4. Validate memory/RET assumptions at their uses or conservatively join their
   effects. Keep the complete emitted return whitelist; unconditional byte
   bans alone do not check computed addresses in a dataflow-skipped block.
5. Convert the bounded counterexamples into refusal/forward-continuation gates
   in existing test programs, with exactly-once stores and owner ACK checks.
   Keep affected complex spin/mutex modes actually executing JIT, including
   `mutex_jit=1`; blanket unknown-pointer refusal is not a passing JIT result.

Until an enforceable policy and these exits exist, limit use to audited
experimental workloads. More static examples or successful stress runs cannot
justify a claim that every context-sensitive critical section is refused.

### 7.2.2 Static Per-CPU Ranges

The captured x86-64 kernel's `__per_cpu_start` is zero; `current_task` and other
static per-CPU symbol values are offsets, not each CPU's dereferenceable address.
Translation now reads `nr_cpu_ids`, `__cpu_possible_mask` and `__per_cpu_offset`
through its existing pinned kcore/device lease, before text admission. For every
possible CPU it adds the interval starting at `__per_cpu_start + offset[cpu]`
(modulo 64 bits), with size `__per_cpu_end - __per_cpu_start`. Offline possible
CPUs remain covered. The linked section itself is not added as a low-address
interval, which would incorrectly classify ordinary small immediates.

This uses the captured boot-time initialization contract in
`arch/x86/kernel/setup_percpu.c` and `smpboot.c`: possible CPUs are established
before per-CPU setup and offsets become read-only after init. Each translation
reads the metadata anew and compares a second read. Counts are bounded to 8192,
the static section to 16 MiB, and offset reads to 64 KiB. Missing/ambiguous core
symbols, invalid counts/masks/addresses, short or changed reads, wrapping or
overlapping runtime intervals abort as infrastructure errors, not successful
native-only verdicts.

On the captured x86-64 SMP kernel, both first-chunk allocators reserve
`PERCPU_MODULE_RESERVE` (8192 bytes) after the core section aligned to
`PCPU_MIN_ALLOC_SIZE` (4 bytes). `kernel/module/main.c` uses
`__alloc_reserved_percpu()`; `mm/percpu.c` serves it only from the reserved chunk
when that boot-fixed chunk exists, failing rather than spilling to a dynamic
chunk when full. Normal module unload frees allocations within that arena,
not the arena's address classification. This does not pin or validate an object.

The provider reports this bound using version 2 of the existing 16-byte CAPS
packet on the same device lease. It checks the build constants and the non-NULL
`pcpu_reserved_chunk` pointer, which is read-only after init; it never dereferences
the private chunk layout. Translation adds `[base + ALIGN(core_size, 4),
base + ALIGN(core_size, 4) + module_bytes)` for each possible CPU. Version 1,
unavailable or invalid capability cannot silently omit the module check: current
translation reports an infrastructure error before reading source text. Source
inspection/retirement can still query older providers. Neither the ioctl number
nor its size, guest code or wrapper arguments change.

Do not extend coverage to `pcpu_unit_size`: the embedded allocator returns unused
tail pages to ordinary memory. Alignment padding is not claimed as module data,
and ordinary dynamic chunks/objects remain outside this range contract.

Whole-area coverage is separate from named-symbol intervals, so an interior
symbol cannot truncate it. Existing explicit-operand, derived-address and IR
checks then reject statically resolvable accesses, including boundary overlap.
`STATIC_PERCPU_SCREENING` reports possible `cpus`, `core_bytes`, `module_bytes`
and their sum `bytes_per_cpu`, not runtime address enforcement. Core and module
arenas retain separate labels. The optional name-only/core-only parser remains
for byte fixtures; the real translator must supply its leased reader and
negotiated module bound. This is not a runtime memory snapshot
of the protected areas, and it does not establish code-version isolation.

The API audit found that `is_kernel_percpu_address()` only recognizes core
static areas, while `is_module_percpu_address()` recognizes module static areas.
Neither is an arbitrary dynamic-allocation classifier. `per_cpu_ptr_to_phys()`
requires an already valid, live per-CPU pointer; the private allocator lookup
assumes an allocator pointer and cannot safely classify arbitrary JIT addresses.
Module/dynamic allocation lifetimes, other task/context objects, unresolved
runtime pointers and concurrent pointer replacement therefore remain open.
No such helper is called from generated code in this increment.

### 7.3 Build And Publication

The daemon has flat RIP and RIP/tgid workspace modes, independent of benchmark
mode. It maintains callee/indirect-target tables, reads /proc/kcore, combines
generated assembly with the wrapper, assembles/links and transfers jit.bin.
The [device session](../daemon/README.md#device-session) remains held across this
flow; opening a new device after an error is not a supported recovery path.
Policy refusal removes stale outputs and exits 2; launch failures/exceptions
are errors/retry conditions, not successful native-only decisions.

Images must be nonempty and fit 640 KiB. Transfers use up to 4000-byte chunks;
the last complete chunk sets NORMAL. The kernel checks entry, offset, payload
size and status, but does not establish complete image continuity/generation
or protect live executors. Recompilation overwrites the existing block.

Independent locks may share the RIP-keyed artifact; early A unlock can also
allow overlapping execution. Lock serialization is not version retirement.
Immutable versions, full publication validation and reclamation are explicitly
deferred under [C3](TODO.md#c3-immutable-jit-publication-and-lifetime).
See [daemon README](../daemon/README.md) for CLI and diagnostics.

## 8. Sandbox Code Model

### 8.1 Registers And State

The wrapper takes `pt_regs *` and exactly two words:
`{waiter kernel GS base, logical waiter task}`.
Inputs are reinstalled for every continuation. Hardware GS/current, scheduler,
IRQ/RCU state, flags and SIMD/FPU are not switched to the waiter.

Physical RSP/RBP belong to the wrapper; R13/R12 initially represent virtual
RSP/RBP. R11 is the branch-block budget. R12-R15 also form the special-register
mapping pool; ordinary instructions cannot hardcode guest R14/R15 locations.
R14 is target RIP at exit, R15 carries an IJ source. Exact slots and supported
GPR persistence are defined only in [the ABI](JIT_REGISTER_ABI.md).

### 8.2 Execution Witness And Budgets

Optional generated-body MOV instrumentation sets the reused args[1] output to
one; the wrapper initializes it to zero. The executor logs a matching positive
witness only after wrapper return. Public tests force this on; manual daemon
launches default off. A marker proves entry into generated body, not full
instruction/path coverage or version identity. Zero never authorizes replay.

Branch-ending blocks increment R11 and test bit 24; the counter resets at each
wrapper entry. It is not a retired-instruction or whole-CS budget.
Entry predicates, dispatcher CMP and budget INC/TEST can clobber flags. No
flags liveness verifier enforces the limitation. INT-to-NOP and warning-only
special lowering remain; diagnostics do not repair instruction semantics.

### 8.3 Calls And Memory Boundaries

CALL pushes the original return RIP on the virtual stack. Decoded callees can
run inside JIT; an ordinary miss retains the CALL packet for waiter-native
execution. Control/hostcall handlers consume it only when their respective
operation has succeeded. The final unlock return is deliberately left for
successful waiter restoration.

No effective canonical-address or general bounds guard is emitted.
Neither admission nor the word "sandbox" implies a security isolation boundary.

### 8.4 Native Hostcalls

`include/kd_hostcalls.def` is the shared declarative service manifest. The
kernel expands it into a registry of stable IDs, symbol names, safety flags,
resolved addresses, and typed handlers. `disassem/hostcall.py` parses the same
manifest and maps resolved targets to hostcall stubs. Runtime dispatch matches
the exact address against the kernel registry; translated code cannot request an
arbitrary function pointer.

For a hostcall, translated CALL lowering has already pushed the post-CALL RIP
onto the virtual stack. The generated stub puts the service target in R14,
returns `KD_EXE_HOSTCALL`, and deliberately does not pop that RIP. The kernel
handler writes its result to `regs->ax`, calls
`advance_and_save_continuation()`, and invokes the same JIT artifact again. The
outer lock and current `kd_exec_frame` remain active across this boundary.

Each `kd_exe_on_call_hl_entry()` invocation has a 16-hostcall budget and shares
a 16-continuation counter with normal known-call resumes. Child invocations
have their own counters; the early outer-unlock/OOO branch bypasses the normal
known-call limit check, so this is not a strict whole-nesting budget.

At either CALL-count limit, the next callee has not executed. The executor
validates the frame/retained-lock scope, pending-request state, original task's
bounded readable CALL word and source residency for both target and return RIP.
For a HOSTCALL it also checks the existing manifest policy without invoking the
service. A valid packet takes `KD_EXE_RUN_NATIVE`: retain all current GPRs, the
callee RIP and pushed CALL RSP, clear only a previous completed control phase,
and let the original waiter run the callee and remaining native suffix. Physical
owners retain their locks and acknowledge unlocks; this request never reenters
JIT. Quota is not a learning miss and leaves the published image NORMAL.
Invalid packets/targets, synthetic faults and post-dispatch service failures
remain fail-stop. Source pinning does not certify the stack's concurrent privacy.
This is an existing CALL-boundary exit, not instruction-budget recovery,
access-time checking or new flags preservation.

Module-exit diagnostics report `exits`, `executed`, `resumed`, `rejected`,
`failed`, and `limit`. Normal mode 2 and mode 5 service phases require matching
nonzero execution/resume counts and no rejection/failure/limit. Mode 5 keeps
those normal completions and adds a final quota phase in the same session;
its excess callee runs natively on the waiter, not through the hostcall adapter.
The combined counter equations and required CALL/native/ACK witnesses are in
[the mode 5 flow](JIT_EXECUTION.md#613-call-次数额度与原生后缀), not the old
one-service-per-JIT equality for the whole case.

The current manifest has three fixed-signature services. Only symbols resolved
in the running baseline are enabled; the x86-64 contracts are:

| ID / symbol | Saved input | Saved output | Native execution contract |
| --- | --- | --- | --- |
| 1 / `ktime_get` | None | RAX: signed 64-bit nanoseconds | Existing atomic-safe clock adapter; no logical-task context switch |
| 2 / `ktime_get_ns` | None | RAX: unsigned 64-bit nanoseconds | Same clock contract when this symbol is available |
| 3 / `int_sqrt` | RDI: full unsigned 64-bit `unsigned long` | RAX: floor square root, 0 through `2^32-1` | At most 32 scalar iterations in the captured kernel implementation; no pointer argument, allocation, sleeping, lock, callback or task/per-CPU dependency |

All three preserve other saved GPRs. Native execution uses the combiner's C
stack; its ordinary compiler register clobbers do not replace the saved waiter
packet. `int_sqrt` calls the exported kernel helper, not a copied algorithm.
Its input covers the full unsigned range without truncation or signed-result
extension; there is no caller-supplied memory whose lifetime must be validated.
Mode 2/5 consume one scalar result after their clock loop. Thus each normal
JIT completion returns from two services, while mode 5's quota suffix reaches
the scalar operation only on the original waiter after the 17th clock call.

These contracts are atomic-context-safe, independent of the proxy task's
`current`, and retry-safe; they do not authorize replay of a progressed CS.
Variadic `printk`, sleeping APIs, task-context-dependent APIs, opaque pointer
services and side-effecting calls remain excluded. A future side-effecting
service needs a fixed ABI and an exactly-once rule for failures after native
execution. No new access-time check or flags contract is introduced here.


### 8.5 Workload Oracle

Each physical lock protects its own state object with sequence, sum, branch
mix, rotate/checksum, four indexed lanes and commit value. Native replay after
worker drain compares every field and an independently protected completion
count. Generated artifacts are checked for actual executable branch, rotate,
multiply and indexed-access instructions, not source comments.

This catches many wrong updates and continuations, but identical deterministic
transitions cannot distinguish every duplicated/skipped request pair.
Native-register probes separately check marked JIT samples, saved registers,
CALL stack, waiter identity and exactly-once effects. Native fallback is not
a positive JIT result. Current results belong in VALIDATION, not this design.

## 9. Nested Ownership And Continuation

### 9.1 Frames And Lock Ledger

A frame tracks backend, logical task, GS, supported registers, explicit held
locks, parent/requester links and control-call phase. Physical ownership is
not inferred from logical depth. Cross-backend controls are rejected.
Pre-entry context/resource refusal leaves valid queue/native ownership intact;
it does not grant permission to replay an executed frame.

### 9.2 A/B Execution

Spin B may enqueue a virtual request and resume remotely; mutex B is acquired
by the same A combiner. Both record the actual acquisition before consuming
the lock CALL. Inner unlock normally continues A, while final completion uses
the last required unlock return, including A-before-B execution.

### 9.3 Capacity And Refusal

Frame, logical held-lock, CPU-local shadow-held-lock, ticket and node pools have
independent limits. Capacity checks precede acquiring/publishing a new B.
A valid pre-acquisition PENDING resource failure can hand the original lock
CALL to the waiter. Already entered/acquired operations cannot use that path.

Spin's ticket refusal is earlier than virtual-node cancellation: a full
32-slot physical-CPU pool returns E2BIG without publishing a B ticket or
retaining its temporary preemption pin. The real-capacity gate holds 31
additional hook-acquired locks across the A combiner, then checks B's PENDING
packet, native suffix and A ACK. Only promotion is controlled; this does not
itself prove gate saturation. The same case now fills the real 1024-slot gate
table during that suffix, then submits a separate prepared A2 JIT root. Its
CPU has free tickets, but the new C gate cannot be allocated: ENOMEM must
leave the virtual request unpublished and preserve the PENDING packet.
The original waiter acquires Linux C while A2 remains owned by its combiner;
only A2 needs a borrowed-owner unlock ACK. Existing A/B remain live throughout.
An ordinary cold entry's unstarted fallback does not prove this progressed
branch. Neither branch supplies access-time guards, generic fault recovery
or lifetime/version guarantees. Flow and test substitutions remain in
[usage 6.3](JIT_EXECUTION.md#63-spin-虚拟请求取消与续跑); current evidence is
[progressed gate refusal](VALIDATION.md#progressed-spin-gate-refusal).

A virtual pre-entry refusal preserves the caller's full register packet and
queue connection. Already-progressed work cannot be recast as fresh native
entry. Exact node reservation and stack lifetimes persist through readmission,
child completion and native ACK; selected bounded tests are not arbitrary-depth
or arbitrary-schedule guarantees.

### 9.4 Out-Of-Order And Remote Completion

A logical unlock of A while B remains held is performed by A's real owner.
It drops A/S once, detaches the old batch and lets saved A successors progress.
B ownership is unchanged. The old combiner must reacquire A before running
its own original CS, without rereading a possibly reused old node.
Spin waits for full S availability and reuses its released ticket without
adding a new pin or switching back to a stale stack.

Remote child state is published as WAITING/NATIVE/DONE. Clear the child's
resume_target before release-publishing final DONE; do not touch the parent
after final publication. A parent with no remaining local locks still waits
for its child while keeping its frame alive.

NUMA deferred-list publication and nested-list isolation must preserve the
same ownership and completion rules. Native-aware waits must continue servicing
owner-side unlock requests, including ancestor release.
A zero-local-lock COMPLETE relay propagates the register packet only: no
extra ACK, borrowed reference or unpin. The last real lock ACK ends the origin
waiter's obligation. Deferred observation must not itself change queue state.

A no-lock ancestor may finish after the waiter's final ACK and normal task
exit. Its completion/pop must not dereference the old logical task, queue slot
or waiter stack; diagnostics use the PID cached while the waiter was blocked.
The bounded live schedule is maintained in
[usage 6.9](JIT_EXECUTION.md#69-无锁祖先与-waiter-退出). It observes TID detachment,
not completed task-memory reclamation or arbitrary request cancellation.

The same terminal rule applies to an owned remote B after its native ACK.
Mode 8's mixed phase pauses at B's validated pop, while A0 finishes its own
ACK and the original waiter exits; only then may that same B combiner execute
the next independent root. This is a SELFTEST schedule, not a production
all-owner/exit barrier. It holds a PID identity, not a task ref, and keeps the
real source-frame lease through pop. Waiting before B publishes its ACK would
block the very exit being observed. The [shared-B flow](JIT_EXECUTION.md#614-两个独立-root-共享-b-combiner)
distinguishes the full software-frame comparison from live register/flags or
completed task-memory reclamation evidence.

### 9.5 Forward Native Continuation

For an ordinary CALL miss, keep current GPRs, callee RIP and virtual CALL RSP.
The original waiter enters that callee, returns natively and finishes the suffix
without reentering this JIT invocation. Memory writes and completed B sections
remain committed; there is no transaction rollback.

The combiner retains its acquired physical locks and pauses its own batch;
independent combiners can keep their separate native registrations active.
The waiter borrows protection, not Linux ownership. Unlock requests return to
the physical owner and wait for ACK. The ACK resides on the waiter's native
stack; the executor drops borrow references before release-publishing done.
The spin waiter ends its origin pin only on the last ACK; a mutex waiter has
already restored migration/preemption state before entering its native suffix.
Borrowing several remote frames does not add lexical lock-depth pins on the
waiter: the existing root origin pin persists through the final ACK. This is
not full preemption-count/context reconstruction; the concrete contract and
mixed B/native-successor test are in [usage 6.14](JIT_EXECUTION.md#614-两个独立-root-共享-b-combiner).
The owner must not reread a queue node after publishing its native wakeup, or
a stack-local unlock request after publishing that request's ACK. The owner's
live frame remains until its own completion/pop. A completion log is not the
ACK's linearization point.

Every allocated frame initializes an empty native routing head. Physical-LIFO
pop refuses both an outstanding `native_request` and a still-linked native
registration, even in ERROR/COMPLETE state; refusal preserves the output packet,
context storage and source lease. The owner must still finish the native wait
protocol before popping. This final guard does not send an ACK, unlink routing,
release physical locks, or make an arbitrary failed frame recoverable. The
[retirement checks](JIT_EXECUTION.md#frame-回收门禁) separate direct bad-state
unit inputs from real owner/ACK schedules; no live use-after-free is claimed.

Acquisition phases are NONE/PENDING/ENTERED/ACQUIRED/COMPLETE. Validated PENDING
-ENOMEM/-E2BIG before acquisition/publication can restore the original lock
callee RIP/CALL RSP while retaining current GPRs and effects. The mutex stack
precheck can also hand off an unstarted CALL when the bounded window is too
short, without inventing an allocation error. A changed post-control window
instead uses the distinct STACK_CHANGED phase and exact already-consumed packet.
For a local spin post-acquisition EIO, `finish_acquired_spin_call()` validates
the unreleased top local lock record, current physical gate owner, original
lock target/token in the waiter stack and exact post-CALL RIP/RSP. Only this
checked boundary receives SPIN_NATIVE: B stays acquired and the waiter resumes
after the CALL. Remote publication, missing records or a bad packet remain
errors. See [flow and tests](JIT_EXECUTION.md#611-spin-获取后的受检续跑).
Native registration independently checks these states, ordinary NONE and
validated spin remote COMPLETE relay before borrowing/publishing/accounting.
A still-held A does not make arbitrary later-phase failures recoverable; the
checked local boundaries are not general ACQUIRED/COMPLETE recovery permission.

If pending B is first acquired by the native waiter, B really belongs to that
waiter; earlier combiner-owned locks still use notifications. After A release,
continuation requires a consistent remaining ledger. Unhandled IJ/budget/fault
and later-phase errors fail-stop, not entry retry.

The existing [early-A dependency workload](JIT_EXECUTION.md#610-提前释放-a-的原生依赖)
checks a native C owner needing the released A while B remains borrowed, then
seven owner ACKs after real ledger exhaustion. It is selected separately from
ordinary held-B register continuation; neither contract subsumes the other.

Borrowed mutex execution does not satisfy mutex.owner == current on the waiter.
Recursive acquisition, owner-sensitive code, lockdep or task-local locking
effects remain outside the supported subset; no owner-bit assignment fixes
those requirements.

### 9.6 BCD Comparison And Continuation Scope

The local BCD source inspection used revision
`dbde52c57a961a5cdb87c0212f9b032947d2df13`, not a BCD runtime test.
Its active daemon/asm/wrapper.S preserves supported registers in the waiter's
syscall pt_regs. Ordinary CALL miss retains the pushed original return address
and callee RIP; the syscall-return path resumes the updated user context.
Learning a missing callee is for future work, not an entry restart.

kdlock adopts forward progress but cannot reuse syscall return as its kernel
lock-ownership protocol. It additionally needs frames, phase validation,
physical-owner retention and native-unlock rendezvous. The old entry-register
retry and popped CALL frame were incompatible with this purpose.

Neither inspected BCD code nor kdlock's current wrapper preserves arbitrary
live arithmetic flags. Saving GPRs alone is not proof of arbitrary-fault
recovery. Supported outcomes are: native entry for unstarted work, current
callee continuation for ordinary CALL miss, validated pending-lock acquisition,
successful post-unlock return, or fail-stop for unsupported progressed state.

## 10. Kernel-Only Execution Entry

Only `kd_exe_on_call_hl_entry()` executes frame-backed spin/mutex requests.
The unused legacy futex entry, private result and unpinned task-CPU GS sampler
were removed. Historical guest futex/INT3 hooks remain untouched and unregistered.
Reintroducing userspace delegation requires a separate ABI/context/lifetime
design, not restoring an old function.

## 11. Configuration

`target_process` defaults to kd_test; `mutex_jit` defaults to 1.
Batch limits are fixed at 1024. Spin NUMA is opt-in via KDLOCK_NUMA=1.
Recovery-only fault/capacity/rename probes are test controls, not production
recovery guarantees. Use scripts and their preconditions from
[JIT_EXECUTION](JIT_EXECUTION.md), never synthetic post-entry faults as safe
rollback tests.

## 12. Supported Scope And Limits

The concise support matrix is in `README.md`, current execution evidence is in
`docs/VALIDATION.md`, and actionable gaps are tracked only in `docs/TODO.md`.
The implementation boundaries are:

1. **x86-64 only** — inline assembly, stack frame layout, and register
   conventions are architecture-specific.
2. **Patched kernel required** — the hook function pointers and exported
   symbols must exist in the running kernel.
3. **KASLR must be disabled** — `/proc/kcore` reading assumes fixed kernel
   text layout. (`end_points[]` is resolved dynamically and unaffected.)
4. **miasm dependency** — the translator requires miasm 0.1.5 and
   `/proc/kcore` access from userspace.
5. **No rwsem support** — only spinlock and mutex are implemented.
6. **NUMA-aware combining off by default** — `KDLOCK_NUMA=1` opts into the
   existing spin `NUMA_AWARE` branch. Test 21 covers bounded, directly observed
   deferred-follower histories; results depend on source version and fixture. This is not validation of
   arbitrary list lengths, fairness or NUMA-enabled deep physical stacks. Mutex
   delegation has no NUMA-local queue implementation.
7. **No general instruction verifier** — segment/decoder rejection is
   implemented, but `special_inst.py` lowers `INT` to NOP and only warns for
   unhandled special operations such as its `PUSHF`/`POPF` cases. Ordinary
   mnemonics are emitted without a general privilege allowlist. Some unsafe
   instructions can therefore be mistranslated or executed, not rejected.
8. **Nested resources are bounded** — execution frames and lock stacks allow
   eight entries; each CPU has four spin nodes and four bitmap-reserved mutex
   nodes. Before execution, exhaustion uses native handoff; an unhandled
   post-progress exhaustion is fail-stop.
9. **Partial progress is not replayed** — ordinary CALL misses use native
   continuation, as do proven PENDING acquisition resource failures; other
   exits after entering JIT fail-stop until supported.
10. **Hostcalls are an explicit allowlist** — only fixed-signature, atomic-safe,
    task-context-independent, retry-safe services are currently accepted.
    General variadic `printk` and side-effecting services are unsupported.
11. **Persistent processor state is partial** — GS/current lowering helpers
    remain, but GS memory and known context operations are refused before JIT
    publication. Hardware FS/GS switching, FS operands, EFLAGS, and SIMD/FPU
    state are not supported as general cross-exit state. The optional
    `args[1]` body witness adds no processor-state restoration. See `docs/JIT_REGISTER_ABI.md`.
12. **Memory checks are incomplete** — the translator currently emits no
    effective canonical-address or bounds guard, so the JIT must not be treated
    as a security isolation boundary. Access-time checking and its pre-instruction
    native exit, including local condition-code preservation, remain explicitly
    deferred and unimplemented; static screening can miss runtime pointer changes.
13. **Batch limits are fixed** — spin and mutex combiners process at most 1024
    waiters per round; these constants are not module parameters.
14. **Flags can be clobbered inside JIT** — entry predicates, dispatcher comparisons and inserted
    branch-block `INC`/`TEST` are not transparent to live flags. No liveness
    verifier enforces the restriction, even without a wrapper exit.
15. **Continuation is not rollback** — see 9.5; completed stores and child
    sections are retained. Register entry retry is limited to not-started work.
16. **Publication and lifetime are incomplete** — concurrent code replacement
    remains deferred under C3; source-module, lock-object and hook-provider
    lifetimes are separate unresolved contracts in 3.1. Guest predicates are
    called by non-target tasks too, without a matching reader/drain protocol.
    Stopping benchmark callers and draining requests is an experimental
    prerequisite, not a proof of safe provider hot unload.
17. **Scope is narrower than all kernel lock APIs** — delegation supports plain
    raw spin lock/unlock and non-RT mutex lock/unlock. Native mutex participants
    include non-target tasks and successful trylock/interruptible/killable calls;
    those alternate acquisitions are not themselves delegated. Controlled native
    interruptible/killable cancellation while the combiner retains L is tested,
    including head/non-head removal and survivor progress. Bounded native
    signal/release races also cover observed acquisitions/cancellations and
    real HANDOFF requests, not every internal removal/handoff interleaving.
    Separate original-waiter tests cover uninterruptible native B waiting and
    direct cancellable B CALL misses after JIT progress, including pidfd signal
    versus real B-owner release races. Acquired B runs/unlocks once; cancellation
    skips B, not A's completed stores or final owner ACK. Neither outcome
    cancels an arbitrary delegated request or supports exit inside a native suffix.
    Arbitrary cancellation schedules, WW/PI/RT mutexes, irqsave/bh and
    lock-address reuse need separate work.
    Known mixed spin/mutex references in the discovered CFG now refuse before
    codegen using registered entry kind. Unresolved targets/callees can still
    hide such calls; the runtime backend guard remains fail-stop if reached
    after JIT entry. This is not complete call-graph or native-suffix safety.

## 13. Performance Comparator Contract

The [instrumented driver](JIT_EXECUTION.md#33-带观测的负载测量) provides a timing
boundary, not three interchangeable lock implementations. Keep these comparison
groups distinct before interpreting a comparison; all target x86_64:

| Candidate | Actual execution path | Valid comparison boundary |
| --- | --- | --- |
| Native with existing hooks | Same guest/module/workload, nonmatching `target_process`, original Linux locks | A possible same-kernel reference; still includes the installed selector hooks, not pristine unmodified Linux |
| kdlock JIT | Matching task, published supported CS, `mutex_jit=1`, actual returned body and complete state | Instrumented delegation; measured invocations can also contain direct native acquisitions or checked native suffixes |
| `mutex_jit=0` | `__kd_mutex_lock()` calls `kd_origin_mutex_lock()` before shadow scheduling | Explicit debug/native control with its own target/promotion overhead; **not native delegation** |
| Upstream TCLock | Native stack-switch delegation with TCLock lock/task state | Not available as an unchanged mutex module on this guest; a different kernel or an explicitly assessed port is required |
| TCLock LiTL userspace library | Interposes `pthread_mutex_*` through `LD_PRELOAD` | Does not replace the kernel locks reached through `/dev/lock_dev`; not a kernel comparator |

The local read-only TCLock checkout is `~/TCLocks`, revision
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef`. The decisive source locations, relative
to that checkout, are:

- `src/kernel/rcuht/locks/komb_mutex.c`: `get_shadow_stack_ptr()`,
  `get_komb_mutex_node()` and nested combiner paths directly access task fields.
- `src/kernel/linux-5.14.16/include/linux/sched.h`: the `komb_*` task-state
  block; `kernel/fork.c` allocates/initializes and frees its storage.
- `src/kernel/linux-5.14.16/include/linux/mutex.h`: TCLock replaces the mutex
  representation with tail/state/combiner fields. The nano-benchmark's separate
  `src/kernel/rcuht/include/mutex/komb_mutex.h` likewise defines `komb_mutex`;
  neither may be cast onto this guest's owner/wait_list-based Linux mutex.
- `src/kernel/rcuht/rcuht.c`: explicit table/bucket lock adapters and kthread
  state initialization. Its hash-table operations are not kdlock's CS workload.
- `src/userspace/litl/README.md` and `src/liblock.in`: userspace interposition
  contract; the latter path is relative to the LiTL directory.

The [guest compile audit](VALIDATION.md#tclock-comparator-feasibility) builds a
normal external control object but rejects the unchanged TCLock mutex object
for nine missing task members. This is a concrete incompatibility, not a
failed runtime test or proof that every possible module-only port is impossible.
No TCLock module was linked/loaded; spin and LiTL were not compiled in this audit.

An upstream-kernel comparison would change more than a condition and hook:
task layout, task allocation/free and the physical lock representation/protocol
are involved. It is outside the current no-guest-edit default. A module-owned
task/stack table could be investigated separately, but its lifecycle, nested
switching, cleanup and overhead need a new port contract and acceptance; it
must be labelled an adaptation, not unmodified TCLock. Do not introduce a
JIT-disabled production delegation mode merely to fill a results table.

The opt-in [paired experiment](JIT_EXECUTION.md#34-原生锁与-jit-配对实验) implements
native-with-hooks/JIT comparison groups on ordinary mode 2/5, without changing
the guest kernel. The native-delegation comparison group stays explicitly open in
[TODO](TODO.md#comparator-feasibility-and-matched-experiments). Each pair needs
identical workload text, parameters, state preparation, affinity and accounting
boundaries, fresh/drained sessions, retained failures and repeated balanced
order. Native must have no JIT; JIT must have new matching returned bodies in
the measured phase. Different mode timings or old runs are not paired trials.
Do not turn a SELFTEST role that waits for a JIT frame, queue or combiner event
into a native reference: its progress conditions can require delegation.
Use matched ordinary CS paths for measurement and retain those specialized
roles as independent correctness gates.
The implementation retains even, alternating repetitions and explicit thread/
workload sweeps, preparation records, full-session rebuilds and failed pairs.
Generated images and NORMAL registry identity are checked before/after the
payload with translators stopped; this is an experimental constraint, not C3
version isolation. Equal CPU masks and state do not imply equal cache/thermal
conditions, exclusive CPUs or identical native/JIT execution proportions.
Cost separation and amortization remain work, not inferred from these gates.

Routine mutex queue/JIT traces use INFO, not ALERT; their text and availability
in dmesg are preserved. At console level 4 without `ignore_loglevel`, these
records no longer force serial output from native framework code that may
still hold the physical mutex. This is not a sandbox hostcall-policy change.
The [severity follow-up](VALIDATION.md#mutex-routine-log-severity) diagnoses the
initial mode-5 anomaly with unchanged console controls and actual-JIT gates;
it does not remove logging cost or provide a complete cost breakdown. Retain
console settings alongside comparisons, since verbose consoles can emit INFO
again. The paired controller now collects them at initial, phase and publication
boundaries, rejects changes and requires identical settings across groups; these
samples do not prove continuous control of external sysctl writers.

Opt-in daemon accounting measures each translator child from pre-fork to reap,
with wait4 CPU and largest-process RSS, separately from the prepared payload.
The controller joins each record to the published entry and retains both raw
attempts and summaries. Preparation latency includes polling and settling;
translation can overlap promotion, so those intervals cannot be summed as
disjoint costs. Neither child CPU/RSS nor the process/worker-envelope difference
measures kernel queue, hostcall or pure-JIT cost. Detailed boundaries live in
the [paired flow](JIT_EXECUTION.md#34-原生锁与-jit-配对实验); P2 remains open.

The separate, default-off `jit_timing` module parameter records inclusive C
intervals for dispatch, actual wrapper calls, typed hostcall dispatch and lock
control handling, plus spin/mutex physical-owner native waits, private-queue
residence and native-handoff envelopes. Selection is read-only after load; drained unload emits ten
aggregate rows. Invalid clocks/overflow invalidate measurements only, never
execution or native-replay decisions. The paired controller's ordinary mode 2/5
contract joins one body to 1/3/2/1 calls respectively, requires native-wait/handoff
rows to be zero, matches the active backend's queue samples to drained slowpath
counts and rejects missing or
inconsistent timing rows. Statistics span the whole loaded session, including
preparation; nested intervals can overlap and cumulative elapsed is not CPU or
experiment wall time. Native wait starts after publication, so it may miss a
waiter suffix prefix and includes unlock/ACK handling and scheduling. Only local
timestamp/backend values are used after the final ACK, not waiter storage. Remote
relay waits overlap; they cannot be added as disjoint costs.

The wider `native_*_handoff` starts in the backend before validated borrowing,
including before spin's remote-native publication can release an ancestor. It
ends after successful owner-wait return and before frame cleanup. Thus it covers
the early waiter work omitted by the inner wait, without adding fields or
touching waiter/node storage after publication. Handoff contains wait; matching
completed counts and nondecreasing outer elapsed totals are required. It is
not pure waiter CPU time: borrowing, publication, scheduling, unlock/ACK and
measurement overhead remain included. Remote parent/child envelopes overlap,
and code after the last source unlock returns is outside this boundary.

Each queue node has one additional 64-bit timestamp, initialized before tail
publication. A queue owner consumes it after acquiring Linux L, before running
followers or releasing its node. A combiner saves the dispatch-start endpoint,
then accounts it only after a body actually ran and before waking/releasing the
waiter. Thus body/native-suffix time is not charged to this queue interval, a
pre-body refusal retains its start, and immediate node reuse cannot double count.
This covers kdlock-published nodes, not every native/fastpath acquisition or
pre-publication refusal; mutex's nested Linux B wait remains outside this queue
metric. No frame, wrapper argument, instruction or flags contract changes.
Complete acquisition, pure native execution and observation costs remain open. Commands and
subtraction limits live in
[boundary timing](JIT_EXECUTION.md#可选的-jit-边界计时).
