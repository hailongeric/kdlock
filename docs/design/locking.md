# Spin and mutex ownership protocols

旧统一 spin 分发和站点缓存已删除；下文相关伪代码仅说明基线历史路径。
当前直接入口为 `kd_spin_lock_abi`，快速所有权和 ticket 生命周期仍保留。

## 2026-09-20：已批准的单锁字与本地哈希改造（待实施）

比较基线为 `7e2460c`。当前代码仍使用 gate/S + Linux L 和全局晋升集合；
下面是待实施设计，不表示正确性或性能已经通过。

显式 `kd_spinlock_t` 的 32 位字同时承载快速获取、pending、KD MCS 队列和
combiner 仲裁。替代路径接入时一起删除 gate 映射、独立 S、原生 L 二次获取；
无法代理的 KD 对象仍执行 KD 不代理协议。仅迁移模块和显式调用者，不安装
全局 spin 替换。Linux 对象和 mutex 保留各自协议。

caller-clobber ABI、JIT 准入、等待栈、稳定 request/frame、owner/ACK 保留。
嵌套、提前释放、乱序解锁及重新获取都要求每次物理释放只写一次锁字；
node 复用不代表 frame 已退休，部分执行继续原有受检恢复约束。

spin 和 mutex 各自每 CPU 一张表：16 桶、6 个预分配候选、槽索引链表，哈希后
比较完整地址；只有满表淘汰时扫描六个分数。命中增加 score，替换最小项时
先摘链后插入，error 记录被替换分数，准入要求 `score-error >= 10000`。
删除全局晋升及查询，类型明确的本地记录/查询保留原批量时钟（10240 次）、
CPU 窗口（400 亿 TSC）和锁窗口（25 亿 TSC）。`adaptive` 控制新请求，
`observe` 固定准入用于协议对比；统计重入失败只丢样，mutex 不跨睡眠固定 CPU。
OWNER、WAITER、COMBINER、DONE 属于稳定请求/持锁记录/frame，输出关联角色；
表淘汰、窗口重置、CPU 迁移不改变所有权，解锁不查热表。

提交顺序：基线 → 文档/无行为变化清理 → 单锁字 → 本地哈希/角色。
每阶段在 guest 构建及运行基础和直接相关检查；联合检查淘汰中的活动请求及
mutex 等待迁移。JIT 正例必须取得实际正文证据；性能使用已有 1/16 cacheline、
1/4/8/16/20 线程三锁矩阵和同一负载，分开报告协议、记录成本、自适应效果。
不恢复已删除的调度检查，不把历史结果写成本次重跑。


Current implementation contract; start with the [design overview](../DESIGN.md).
Validation belongs to its frozen inputs in [tests](../../tests/README.md).

## 4. Spin Delegation Protocol

### 4.1 Native Lock And Private Queue

Linux qspinlock **L** remains the sole physical exclusion lock. kdlock uses a
separate scheduler word/tail **S** and private nodes; native and kdlock queue
encodings must never share L's tail. A scheduler handoff alone does not permit
critical-section execution: the physical executor first acquires L.

The fixed gate map is append-only for the provider session. Creation remains
serialized by the map's irqsave lock and rechecks the probe chain after a miss.
The creator initializes the slot before release-publishing `origin`; readers
acquire-load that key before using S. Existing `get`/`find` hits take no map lock.
A concurrent insertion may make a read miss transient, but cannot expose a
partially initialized gate. Slots are neither removed nor reassigned until
controlled drain and teardown. This does not pin the lock allocation or admit
an execution frame; source retirement and physical-owner checks still apply.

Each gate is 64-byte aligned with a 64-byte array stride, so independent locks
do not share a scheduling-word cache line. The 1024-slot table occupies 64 KiB.
This separates different gates; communication within one gate remains shared.

Native plain/trylock/IRQ-save/BH participants use Linux L. Their mutual
exclusion does not imply that IRQ/BH operations can be delegated; known
context-sensitive wrappers refuse translation.
The old shared-tail protocol and its compatibility claims are obsolete.

The independent TCLock backend instead owns its target lock word exclusively.
Retaining the `spin_lock` API does not make its protocol interchangeable with
unmodified Linux qspinlock: the same tail encoding resolves to different
per-CPU node arrays, and a delegated unlock needs TCLock's continuation and
completion handling. All accesses to such a target must use a compatible
protocol; uncontended CAS success cannot establish contended interoperability.
The backend's ordinary-spin hooks do not establish mixed native/IRQ/BH/trylock
support for that target. See the [TCLock compatibility boundary](../../tclock_backend/README.md#与-linux-原生-spinlock-的协议兼容边界).

kdlock preserves native interoperability by keeping those private queue tails
out of L. Normal delegated batches retain L across multiple critical sections;
they do not release/reacquire it for each waiter. Removing this layer requires
a unified protocol for every participant of that lock, or a separately verified
interoperability mechanism. Acquisition-order optimizations do not change that
requirement.

Spin acquisition retains an optional per-CPU L/RIP/gate lookup cache. The
read-only module parameter `spin_native_cache` defaults to 1; disabling it
selects the S-first path for every admitted root. After the CPU/lock frequency filters, a matching published site,
OPEN source, root CPU context and idle entire S permit a Linux trylock on L.
A successful cached try keeps a native-L owner record/pin through unlock, with
nested hooks remaining native as before. This does not acquire S or admit JIT.
The cache never replaces origin exclusion or source/frame lifetime checks.
The parameter uses the kernel's `bint` parser and integer storage, accepting
boolean inputs and reading back 0/1. This avoids a per-read UBSAN bool-load
handler path without disabling instrumentation. Clobber dispatch also puts
registration/scheduling in its cold helper, retaining continuation arguments
across C calls only after a cache miss.

On a cache miss, acquisition follows TCLock's ordering: attempt the scheduling
word before reserving a contended request. After frequency filtering, selection and entry
registration and context checks, pin the CPU, resolve the stable gate once, and
CAS S from zero to LOCKED. An uncontended root acquires Linux L through the
existing gate claim and retains its physical hold token in a per-CPU record.
It needs no ticket, node, frame or register capture; owner/CPU/generation checks
remain. A matching cache key also skips the old repeated NORMAL registry lookup
during cache population. Only a new key requires that eligibility lookup; cached
acquisition still checks OPEN and idle S on every attempt.

A failed root CAS transfers the existing pin and known gate into
`kd_spin_entry_begin_pinned`, then enters the existing pending/queue protocol.
Failure leaves the pin with its caller for balanced native fallback. Nested and
virtual requests retain ticket ownership; no remote owner/ACK rule changes.
Unlike TCLock's exclusive use of the original word, kdlock must still acquire L
because unmodified Linux participants do not use S. S ownership alone never
permits a critical-section access. Discovery and entry registration remain;
removing them would change which critical sections become translatable.

Both owner records preserve unlock routing through rename/closing and block
controlled retirement. An S/L root is ordinary ownership: nested hooks continue
to discover/register entries and acquire independent tickets. It must not be
classified as a native suffix. Unlock checks/releases the physical hold, releases
only S's locked byte (preserving pending/tail), clears ownership and unpins.
A cached L-only owner instead releases L and its pin without modifying S.
The S/L release call and its live pointers stay in a separate non-inlined helper;
otherwise the compiler adds callee-saved spills even to cached native unlocks.
The cache may persist after unlock, but never carries ownership into the next
acquisition. All source/frame and hook-reader hot-unload limits in 3.1 remain.

The cache-off experiment preserves a usable comparison but is not the default:
it substantially regressed the measured uncontended case. Structural preparation
savings and the measured cache/entry tradeoff are recorded in the
[entry benchmark](../../bench/spin_cacheline/results/20260918-spin-entry.md).

### 4.2 Acquisition Tickets And Node Lifetime

The physical hold and original waiter acquisition are different objects.
`kd_spin_hold` records real owner task/CPU/generation.
`kd_spin_ref` points into a stable origin-ticket pool with a generation.
A virtual B request carries the original HOOK waiter's `spin_origin`, while
its physical executor's acquisition ticket belongs to that executor.

The current runtime assumes voluntary kernel preemption. Ticket lifetime still
retains the begin/end preemption pin, including native suffix execution and ACK
waiting. A caller without that pin cannot own a ticket, so lookup returns before
scanning the per-CPU pool. A pinned lookup adds no temporary pin/unpin pair.
Reading a local ticket's gate also takes no guard: CPU/task/generation checks
remain, only its local task changes slot membership, and remote borrowers modify
`native_refs` only. Mutations still serialize with those borrowers under guard.
IRQ-off task callers are admitted; hardirq/softirq contexts remain native.
Physical-owner checks remain independent of the kernel's preemption model.

One stack-local `kd_spin_request` carries that physical ticket and S through
pending/tail helpers, node admission, queue-head claims and combiner batches.
The batch retains it across early outer release and reclaim; neither a recycled
node nor a nested waiter's ancestor `spin_origin` substitutes for this request.
Hook unlock passes its already-found ticket through release. Nested unlock
resolves S once and reuses it for the OOO result; diagnostics and an OOO ancestor
without a local ticket can still use the acquire-reading map.

Only the original waiter can end its pin/preemption obligation. A combiner
cannot remotely unpin it. Native borrow references defer completion until
the last owner ACK. These metadata do not add wrapper arguments.

Each CPU has four exact node reservations. Reserved-but-not-yet-acquired
nodes count as occupied; completion cannot release a different slot or use
a held-only count. Reservation spans every published queue pointer, saved RSP,
request and borrowed reference. Published/woken nodes may immediately be
reused; snapshot needed data before wake and never read them afterward.

Spin completion release-publishes the combined `completed=1/locked=0` word
after final register state is ready in the shared packet. Lone/IRQ-native and batch-successor
handoffs also use release stores; their acquire-side waiters may immediately
consume or reuse the node. Queue splicing must finish before publication, and
the publisher uses its saved successor afterward. This makes the publication
contract explicit; it does not transfer physical ownership or prove arbitrary
memory ordering, task lifetime or flags semantics through a userspace fixture.

At initial spin batch entry, a NULL `next` does not by itself prove the node is
last: the producer exchanges S's tail before release-linking the predecessor.
With S/L still held and before any NUMA splicing, a different nonzero decoded
tail proves a successor is in flight. Wait for that link, then acquire-read it.
A real tail node still receives the ordinary native handoff; this check is not
used on detached deferred lists. No body executes until the existing JIT
admission succeeds. The directed delayed-link mutation guards this boundary.

### 4.3 Combiner And Native Returns

The combiner owns L and S while processing an eligible batch, validates entry
readiness/context, reconstructs waiter registers and enters a frame.
Unstarted work can receive native handoff. Partial JIT progress cannot be
converted into entry replay.

Spin no longer allocates a private C stack. Before queue publication, the root
saves its incoming IRQ flags in preparation locals and then in the reserved node,
with local IRQs masked. One assembly region links the physical waiter and
polls its release-published wake without calls, pushes or compiler spills.
An unexecuted queue-head wake returns through intact C frames. Completion or
native suffix handoff instead abandons every old hook/queue frame and starts
the restoration helper below both saved physical RSP and final virtual RSP,
aligned for the C ABI. This protects virtual CALL frames even when they have
overwritten the old queue return addresses.

IRQ-off task context is a valid entry state, not a reason to refuse delegation.
The queue interval uses `local_irq_save()` / `local_irq_restore()` for both
incoming states; it never unconditionally enables IRQs. This interval covers
publication, waiting and any combiner work, not just each delegated body.
The original preemption pin remains necessary for per-CPU ticket/node lifetime.
Hardirq/softirq admission and translation of IRQ/BH-changing code retain their
existing exclusions. Masking ordinary local IRQs does not mask NMI or establish
general exception safety.

| Physical slowpath exit | Stack and continuation |
| --- | --- |
| Queue-head/combiner acquisition (`0/2`) | Body has not run on behalf of this caller; restore IRQs and return through intact C frames. |
| Remote completion or native suffix | `spin/wait.inc` selects an aligned safe RSP and calls `kd_spin_resume_completed(node)` directly; old C frames never return. |
| Pre-body retry after acquisition (`4`) | Restore the node's IRQ flags from the still-intact preparation local, then enter `kd_spin_resume_waiter(node, 1)` on the safe stack. |

Virtual waiters keep their independent executor C stack and the existing
`1/3/5` parent-notification returns. These are no longer physical waiter
completion returns.

The restoration helper retains the shared request pointer, ticket and incoming IRQ flags,
ends the completed ticket or marks the native continuation, and restores IRQs
only on the valid task stack after its final per-CPU/node access. It then
jumps to the saved continuation. Incoming IRQ-off state stays off; an IRQ-on
caller regains its original state. Ordinary queue-head/combiner returns also
restore their incoming IRQ flags. A native suffix retains the origin pin
until the final native ACK; its wake is not full completion. This is IRQ state
preservation, not a new general RFLAGS ABI.

The combiner eventually executes its own original critical section.
If logical A was released early, it must reacquire A first; see 9.4.

### 4.4 Nested Contention And Stack Resources

At B's lock CALL, a virtual spin waiter prepares its own request/frame but
references the existing logical GPR/RIP/RSP packet. Explicit held-lock and
physical owner state, GS/task and origin references remain independently
recorded. A remote B combiner can execute it.
It uses the root/parent artifact with B's continuation RIP, not a separately
truncated B artifact that cannot represent A's later flow.

Logical requester/`resume_target` chains differ from physical C-frame chains.
A physical parent waits on its own task stack while a child executes on
another CPU using the original logical waiter stack. Its C locals, frame and
stack remain live until child completion; virtual waiters still service remote
owner/ACK requests. Their queue interval saves, masks and restores local IRQs.

Spin combiners use the task kernel stack. Each possible CPU has a preallocated
8 KiB shadow stack for physical waiter polling, following TCLock's separation
of the suspended task stack from the waiting CPU's live RSP. One assembly region
switches stacks before publication and saves only the old C RSP. An unexecuted
head handoff restores it; completed/native wakes abandon the old C chain and
start restoration below both the saved physical and final logical RSP. The CPU
leaves the shadow stack before releasing its pin or restoring IRQs. Virtual
waiters keep their executor C stack for nested owner/ACK service. Allocation
failure rolls back initialization; drained shutdown frees the stacks. The lock
ledger and wrapper RSP scratch are separate metadata. Frame and held-lock
depths are bounded at eight.
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
The [execution flow](../testing/mutex_protocols.md#612-同-cpu-的嵌套-mutex-jit) distinguishes
this scheduling check from PENDING recovery and independent-queue refusal.

Mode 4 also has a separate shared-B session: A0's physical combiner retains
A0/B across an ordinary CALL miss while A1's combiner and a non-target peer
both wait on that exact Linux B. The waiter requests owner-side unlock/ACKs;
A1 then completes its own JIT and the native peer acquires as its own owner.
This exercises cross-frame exclusion, not a spin-style remote B combiner or
owner transfer. The [shared-B flow](../testing/mutex_protocols.md#615-两个-a-combiner-共享原生-mutex-b)
keeps publication, actual JIT, real wait-list identities and exact effects
distinct from merely completing all clients.

### 5.2 Entry, Completion, And Task Routing

1. Cold locks, `mutex_jit=0`, shadow/task-record allocation failure, and nested
   acquisitions by an already-active task go directly to the original mutex.
2. A promoted, eligible request registers its task before entering the scheduler.
   Winning the gate calls `kd_mutex_claim_origin()`, which acquires the original
   mutex and records `physical_owner=current`, before entering any CS.
3. Queued waiters retain the hook stack address and waiter GS/task. Their combiner
   verifies real ownership, checks exact entry/ABI readiness,
   and executes the translated CS in a frame. Missing code or a busy per-CPU
   frame context receives an unexecuted queue handoff. That next owner must
   acquire the original mutex; it cannot inherit exclusion from the gate alone.
   Ordinary clobber callers supply IP/SP/BP directly and switch to their reserved
   shadow stack before publication. Their root frame borrows node->regs; normal
   COMPLETE validates the unlock and restores only these three fields. Legacy
   callers still decode the kernel hook frame, without a duplicate hook snapshot.
   A FULL intermediate exit detaches into frame-owned storage before C handling:
   the native waiter may recycle its node while its owner still waits for ACK.
4. Successful JIT execution reaches the final required unlock and completes its
   frame: normally A, or the last nested B after an earlier logical A unlock.
   The waiter retains the valid published fields, releases its exact bitmap slot,
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
in [the mutex resource guide](../testing/mutex_protocols.md#61-mutex-资源与恢复包).

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
[the lifecycle guide](../testing/mutex_protocols.md#62-task-引用最终-ack-与-rcu).

#### Pinned Busy Polling

Both spinlock and mutex delegation support explicit GS memory operations by
default. Spinlock waiters keep preemption disabled from entry-ticket reservation
through their queued wait. Physical waiters switch to the per-CPU shadow stack,
publish and PAUSE-poll in `spin/wait.inc`, with local IRQs masked; virtual waiters
retain C polling and remote owner/ACK service on their executor stack. Neither
wait sleeps or schedules. The mutex waiter uses the same origin-task constraint;
GS support is not a mutex-only option.

`kd_mutex_wait_for_result()` observes the linked waiter's `locked` byte with
acquire ordering and executes `cpu_relax()` (x86 PAUSE) until completion or
native handoff. Preemption remains disabled from before publication through
consuming the result; neither this loop nor the scheduling-gate poll schedules
or parks. Other tasks therefore cannot replace the origin waiter while its GS
storage is being accessed remotely. IRQ/NMI access remains possible.

After taking the gate, the request is no longer eligible for delegation. Its
physical executor may acquire the real sleeping mutex, including nested B;
original-owner/native-suffix ACK handling retains its existing protocol.
Migration remains pinned for those executor paths and their reserved stacks.
Before publication, a mutex follower checks the reserved local nodes for the
same queue. If a predecessor is already reserved on this CPU, the new caller
drops its unneeded routing reference and acquires the original mutex natively
with scheduling enabled. It publishes no packet and never releases the private
gate. This prevents a local follower from blocking a queue head suspended while
claiming the original mutex; it does not solve arbitrary cross-lock dependencies.
Busy waiters require independently runnable owners/dependencies: a sleeping
owner pinned to a waiter's occupied CPU cannot make progress. Old same-CPU
waiter-scheduling/oversubscription evidence does not validate this new contract.

A promoted, published entry does not guarantee a delegatable batch. A queue
head can remove its sole tail and run its own original CS; `run_combiner()`
hands the last follower onward when it has no successor. Eight userspace
threads on two CPUs need not produce eight simultaneous queued requests.
The [CPU-mask assessment](../VALIDATION.md#mutex-oversubscription-assessment)
records an actual prepared-but-unexecuted JIT point, not an admission failure
or permission to count native completion as JIT.

The local TCLock revision identified in section 13 has a different linked-waiter
handshake in both `rcuht/locks/komb_mutex.c` and its Linux `kernel/locking/mutex.c`:
when rescheduling is needed and another task can run, an UNPROCESSED waiter
sets TASK_INTERRUPTIBLE and atomically enters PARKED. The waker changes it to
PROCESSING and wakes a parked task with `wake_up_process()`. Its queue-head gate
still polls, and its last-node handoff also avoids delegation. This is a source
inspection, not a TCLock run or proof that it solves this measured workload.

Do not copy those completion values or parking transitions into kdlock: here
PROCESSED is 1, which TCLock uses for PARKED. The requested GS policy requires
published waiters to keep polling with preemption disabled. Event parking is
outside this design; existing final release publication still permits immediate
node reuse, and original owners and final ACK ordering remain authoritative.

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
[usage 6.1](../testing/mutex_protocols.md#61-mutex-资源与恢复包). This successful continuation
is distinct from refusing another queue's unstarted JIT request below.

Native registrations are matched by logical task, backend and retained lock,
not by a single global "current waiter". The opt-in
[dual-queue workload](../testing/native_protocols.md#66-独立队列的并行-native-frame) keeps two
real mutex native frames alive at once and checks both drain orders. Each has
its own physical A/B owner, waiter record and stack-local ACKs. It uses separate
published entries with the daemon stopped; an ordinary miss makes its entry
not-ready, so this does not test concurrent code replacement or imply that a
second invocation of the same entry can always start after that miss.

A scheduled mutex combiner retains ownership of its CPU-local execution
context, not only its physical mutexes. A different combiner on that CPU must
refuse an unstarted JIT request even when its entry is ready, then use ordinary
queue handoff and native ownership. The
[same-CPU workload](../testing/mutex_protocols.md#67-同-cpu-的-mutex-jit-拒绝) keeps the first
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
[original-waiter signal test](../testing/native_protocols.md#64-原-waiter-的信号与退出) checks
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
the scope of the separately bounded fixtures are recorded in [VALIDATION](../VALIDATION.md).

### 5.4 Differences from Spinlock Path

| Aspect | Spinlock | Mutex |
|--------|----------|-------|
| Queue structure | Per-CPU `kd_spin_node[4]` | Bitmap-reserved per-CPU `kd_mutex_node[4]` |
| Exclusion | Original Linux qspinlock L, held by the physical executor | Original Linux mutex and its actual owner |
| Scheduler state | Private S word/tail, never overlaid on L | `kd_mutex.locked/tail`, never sufficient for exclusion |
| Scheduling | Non-sleeping spin protocol | Delegation waiters PAUSE with preemption disabled; native executors may sleep |
| Nested contention | Virtual spin waiter and combiner snapshot | Same combiner waits for native B |
| OOO unlock | Owner-side A/S release, logical-parent rendezvous and ticket-preserving reclaim | Native A/S early release, same-owner B and A reacquisition after suffix |
| JIT disabled | Per-lock spin readiness policy | All mutex calls use original native protocol |
