# Spin and mutex ownership protocols

旧统一 spin 分发和站点缓存已删除；本页区分当前协议与固定版本验证。
当前直接入口为 `kd_spin_lock_abi`，快速所有权和 ticket 生命周期仍保留。

## 单锁字与本地哈希

显式 `kd_spinlock_t` 为 4 字节，直接承载 fast、pending、KD MCS tail 和
combiner 仲裁；gate 映射、独立 S、Linux L 二次获取均已删除。
普通 Linux 对象不进入 KD API。无 JIT、资源不足及上下文拒绝均使用 KD 字的
不代理 fast/pending/MCS 路径，保留 preempt 配对及在途计数；无 ticket 解锁也是 KD 释放。

稳定 ticket 记录 task/CPU/generation 和 ACK 借用状态。claim 只确认已拥有 KD
字，release_origin 只退休所有权元数据，调度器随后执行唯一的 release store，
不清除 pending/tail。提前释放、乱序解锁及重新获取保留该顺序。fast owner
单独记录，node 复用、waiter 唤醒均不代表 frame 已退休。caller-clobber、等待栈、
JIT 准入及部分执行受检恢复约束不变。模块及显式调用者接入，不安装全局 spin hook。

当前 spin/mutex 各自每 CPU 256 桶、256 条预分配记录，以槽索引处理冲突并匹配
完整锁地址。命中只增加该锁 count，没有候选排名、score/error 或淘汰。
满表保留已有记录，未收录锁在 adaptive 下走原生；地址映射保持至卸载。
spin在MCS达到1024时以`(spin_entries >> 10) < 2`比较本批获取数，清零两计数，再读取一次TSC；
CPU窗口400亿TSC ticks。spin单锁独立每512次检查12.5亿窗口，不随MCS间隔变化；mutex保持第1025次/25亿。
获取和MCS计数允许近似；已有busy guard保护热表修改，统计复用获取pin。
这些只决定后续准入，不承担owner、ACK或排空职责。降温/重新变热时重置单锁热度，
不取消已发布请求。当前仅保留adaptive；完整参数与query语义统一见
[热度与角色](../JIT_EXECUTION.md#21-热度与角色)，不在本页复制实验参数。

OWNER 保存在真实 fast owner/ticket 状态中；WAITER、COMBINER、DONE 保存于
稳定 frame 的 role 字段，使用原 state 布局内的空间，寄存器/帧偏移不变。
SELFTEST 的 `hotlock_role_trace=1` 按锁地址和稳定 request 输出角色；默认关闭。
`hotlock_lifetime_selftest=1` 检查热表碰撞及满容量时既有身份和真实 owner 仍保留及
mutex 等待从 CPU 1 迁移到 CPU 2；不是实际 JIT 验收的替代。

continuation 栈保留稳定 request，普通完成先 pop
再通知；native 先发布 NATIVE_READY，最终解锁等待包括无锁 relay 在内的根 ticket
借用全部退休。每次实际获取只持有一次入口抢占 pin，热度记录与原生回退复用它。
布局、分配位置和两后端数据流集中在 [执行路径](../../bench/spin_cacheline/EXECUTION_PATHS.md)。

验证结果与矩阵维护在 benchmark/tests 索引，未验证边界不得写成通过。


## 4. Spin Delegation Protocol

### 4.1 Native Lock And Private Queue

The historical section name is retained for links. Current spin callers use an
explicit four-byte `kd_spinlock_t`: fast ownership, pending, the KD MCS tail and
combiner arbitration share that word. The gate map, private S, Linux L second
acquisition and site cache have been removed. Linux spin objects retain their
own protocol; no global spin hook is installed and protocols must never mix on
one object. Explicit caller storage must outlive all requests and frames.

The paired broad-clobber spin shell is selected at caller compile time.
It pins once, then uses a C `if` with `this_cpu_read` to select an
inlined cold acquisition or the original broad-clobber hot call based only on CPU
heat. Cold acquisition
keeps the existing `nondelegated` in-flight count through the entire native acquisition
and hold. It inlines one CAS and the existing per-CPU entry count, calling
`kd_spin_direct_native_contended` only on failure to finish the complete native
pending/MCS path. The old outlined API shares this helper for existing callers. This root does not
transfer to a fast-owner record. Native ownership uses locked-byte value 5.
Paired unlock always calls `kd_spin_unlock_clobber_v1` with the broad clobber
contract and lock/SP/IP/BP metadata. The provider tests byte 5 before a release,
count decrement and unpin, preserving pending/tail; other states enter the
existing unlock core. JIT sees one completion endpoint without a caller-side
cold/hot unlock branch. The clobber provider permits sibling calls locally:
the native release needs no C frame, other owners tail-call `kd_spin_unlock`,
and a final pin requesting rescheduling tail-calls the exported kernel
trampoline through `static_call_mod(preempt_schedule)` on dynamic-preemption
builds. The release/count/decrement-test order and kernel return thunk remain;
the module does not access the scheduler's private static-call key.
The cookie is the sampler's sole static per-CPU
unsigned-integer gate, shared by all spin locks. One direct GS read replaces
the old per-CPU pointer followed by a dynamic-table load; no second heat flag,
acquisition path or nesting count is introduced. Mutex heat remains in its
own per-CPU allocation. Provider and direct callers must be rebuilt together
when changing this exported symbol's type. CPU heat
changes affect only subsequent acquisitions. Native MCS counts each actual
publication once, without consulting queue depth; every 1024 publications it
compares the MCS/entry ratio before sampling the clock, using the policy above. The drain scan includes the native in-flight count. Hot acquisitions use the
shared pinned core and existing fast-owner/ticket routing; the provider still
checks `spin_delegate` there. Both APIs use adaptive CPU/lock admission and the
same MCS-publication CPU sampling. `spin_entry_ratio_limit=0` bypasses only the ratio;
the native-head prefix check, CPU/lock heat and execution safety checks remain.
Only the hot acquisition branch declares acquisition clobbers; unlock always
declares the broad clobbers. The compiler owns live-register
saves and may place them before the C branch or inside it. There are no manual
five-register PUSH/POP adapters in the hot body; the named continuation follows
the hot CALL and the minimal register packet retains the original clobber ABI.

Every public spin acquisition pins once. When delegation is enabled, the entry
records heat and checks policy/context before attempting delegated fast/pending.
A sole root uses a fast owner on either success and reserves its ticket only at
the queue branch. Physical nested eligible callers reserve a ticket before CAS;
refused nested/IRQ callers retain an independent native in-flight count.
Neither route overwrites an outer fast owner.

The root CAS remains in the public entry; its failed word is passed to a
non-inlined contended helper, which owns the 24-byte stack request. No extra CAS
is introduced. Fast unlock checks ownership before a separate helper prepares
its 16-byte ticket reference. Fresh spin admission combines the two execution
context queries without changing their predicate or the acquisition pin.

Ticket presence, generation, locality and pin predicates are small inline
helpers, alongside the packed-state decoders and CAS helper. Reference validation
and publication ordering remain at their use sites. Keep the contended acquisition and
assembly/context-switch boundaries separate: forcing large helpers inline can
increase caller spills and instruction footprint. The explicit lock pointer is
the scheduling word itself; no identity-only conversion helper is needed.

At the queue branch, root ticket reservation precedes translation readiness.
A missing translation is registered for later attempts. Refusal before publication
uses the complete native fast/pending/MCS helper, retaining any existing ticket;
this can retry fast/pending but does not record a second heat sample. Native nodes
have no continuation/frame/packet. Only genuine four-node exhaustion polls the
whole word. After predecessor handoff and before physical-word polling, a native
head may veto future CPU admission at the existing approximate 1024-publication boundary.
It checks the MCS counter's low ten bits; the sampler's reset to zero marks this boundary.
It captures the held word and tail once, then requires six acquire-linked
successors within that captured prefix, without waiting or changing counters
or timestamps. The head blocks successor reuse; stopping at the captured tail
excludes an old holder which releases and requeues during the walk. A missing
link conservatively declines. This is not a universal thread-count test; see
[the admission policy](../JIT_EXECUTION.md#21-热度与角色).
The native head still acquires the word, hands queue-head eligibility to its
successor and releases its node; it holds the physical lock until unlock.

A virtual JIT CALL records and decides heat before selecting its route. The hot
route may register its lexical continuation, then reserves an independent virtual
ticket before CAS and virtual queueing. It has no shared pending helper or new
MCS admission check. Cold calls use the native bridge and NATIVE ledger entries.
Published virtual waiters service the parent remote mailbox. Continuation
exhaustion before publication uses native acquisition with the existing ticket;
checked node/context failures retain their existing continuation rules.

Explicit native bridges and outer-lock reacquisition use the complete native
helper without changing this acquisition's native route. Its queue-head veto
can affect only future admission. Reacquisition keeps the original ticket.
`kd_spin_prepare` registers a caller-owned continuation before the workload.
The deferred-admission experiment was rolled back; it is not the current protocol.

Physical claim records that the caller already acquired the KD word. Release
retires ticket ownership metadata, then the scheduler performs exactly one
release store on the ownership byte, preserving pending/tail. Early release and
reclaim keep the original ticket alive; reclaim first acquires the KD word again.
Claim/reclaim and release validate the local identity and commit the packed ticket
state with CAS; neither transition acquires a metadata spinlock or releases the
physical lock. The complete ticket protocol is defined below.
Every intact spin
slowpath return, including node/continuation capacity fallback, has already
claimed or reclaimed its ticket; the public entry does not repeat that claim.
The clobber unlock provider first handles paired cold ownership with locked-byte
value 5; otherwise it uses the existing fast-owner, native-ACK or ticket route.
Neither route consults hotness or comm.

The public header also supplies `kd_spin_lock_irqsave/unlock_irqrestore`,
`kd_spin_lock_irq/unlock_irq`, and `kd_spin_lock_bh/unlock_bh` pairs on the same
KD object. They select native byte-5 ownership directly: IRQ/BH exclusion is
CPU-local and the delegated frame does not transfer it to another executor.
IRQ acquisition saves/disables interrupts before its single preemption pin.
Unlock releases the byte and native count while pinned, restores/enables IRQs,
then unpins. BH uses the kernel's paired `SOFTIRQ_LOCK_OFFSET` operations, which
combine the BH disable and acquisition pin; it adds no second preemption pair.
Each irqsave flags value belongs to its caller, including nested acquisitions.
There is no new lock field, global state or change to plain adaptive entry.
See [API examples](../../include/README.md#显式-irqbh-spin-接口).

`spin_delegate=0` is an explicit fixed self-execution control (default is 1).
It bypasses admission and heat recording at the public entry. Combined record
APIs return adaptive policy decisions; queries return cached heat.
Unlock always uses ownership provenance. Off results are labeled
`DISABLED_CONTROL` and require zero JIT bodies; they do not measure the same
statistics workload as enabled delegation or the reverted note/admit experiment.

Like TCLock's non-combinable queue nodes, a native KD node uses the existing
`IRQ_NUMA_NODE` marker and has `execution == NULL`. The marker also applies to
ordinary task callers. Initial and intra-batch selection must stop at these
boundaries, including NUMA scans; no prefetch, observer or outer-release log
may dereference their absent frame. Queue-head handoff is not completion and
does not execute the successor's body. Acquisition retires the scheduling node;
physical ownership lasts until the caller's later unlock.

### 4.2 Acquisition Tickets And Node Lifetime

The physical hold and original waiter acquisition are different objects.
Fast holds record the actual owner; tickets retain task/CPU/generation.
`kd_spin_ref` points into a stable origin-ticket pool with a generation.
A virtual B request carries the original HOOK waiter's `spin_origin`, while
its physical executor's acquisition ticket belongs to that executor.

The current runtime assumes voluntary kernel preemption. Ticket lifetime still
retains the begin/end preemption pin, including native suffix execution and ACK
waiting. A caller without that pin cannot own a ticket, so lookup returns before
scanning the per-CPU pool. A pinned lookup adds no temporary pin/unpin pair.
IRQ-off task callers are admitted; hardirq/softirq contexts remain native.
Physical-owner checks remain independent of the kernel's preemption model.

Each CPU has 32 stable ticket slots and an owner-local occupied bitmap. Only the
pinned allocating task reserves or ends a slot; allocation and duplicate/lookup
scans use that bitmap. The task, origin word and CPU identity stay separate from
one `atomic64_t control`:

| Bits | Field | Meaning |
| --- | --- | --- |
| 63–16 | Generation | Nonzero acquisition identity, monotonically allocated by the local pool |
| 15–4 | Native borrows | Exact number of executor frames still borrowing this ticket |
| 3 | Virtual kind | Immutable for a live ticket; virtual tickets cannot admit native borrows |
| 2–0 | Phase | FREE, WAITING, OWNED, RELEASED or NATIVE |

Each entry stores generation, phase, kind and borrow count only in `control`,
with no private ticket guard. Remote get/put operations access only that word. They validate the
full `ref.sequence` and compare the complete word on every CAS attempt, so a
delayed operation cannot change a reused slot. Local operations check the original
CPU/task and acquisition pin before their first transition; the pin prevents slot
reuse across retries. Reading the local lock word and walking occupied slots
need no extra pin or atomic write.

| Operation | Transition and ordering |
| --- | --- |
| Reserve | Initialize owner metadata and local membership, then release-store a fresh generation in WAITING with zero borrows. No peer can mutate the preceding FREE generation. |
| Claim/reclaim | Confirm the caller already owns the physical KD word; CAS WAITING/RELEASED with zero borrows to OWNED. Claim is idempotent for an already OWNED live ticket. |
| Release origin | CAS OWNED to RELEASED, preserving the generation. The scheduler performs the separate physical release. |
| Borrow get | CAS-increment only a WAITING hook ticket, before publishing native readiness. A competing claim or end cannot commit over the increment. |
| Mark native | CAS WAITING to NATIVE, preserving all admitted borrows. Further gets fail; existing puts remain valid. |
| Borrow put/wait | After cleanup and frame pop, an ordered CAS decrements WAITING/NATIVE borrows. The owner polls with acquire loads and `cpu_relax()`; observing zero also observes the preceding retirements. Polling performs no locked RMW. |
| End | CAS a zero-borrow WAITING/RELEASED/NATIVE ticket to FREE while retaining its generation, then clear owner metadata and local membership. `end_pinned()` retains the request pin; `end()` consumes it. |

The public ticket API and 16-byte `kd_spin_ref` remain unchanged. Limits are
explicit: at most 4095 simultaneous borrows per ticket and a nonwrapping 48-bit
generation space (`2^48−1` acquisitions per CPU pool during a module lifetime).
Exceeding either limit returns
`-EOVERFLOW`; generations never wrap, and an out-of-range caller sequence cannot
alias a live generation. These are protocol counts, independent of approximate
hotness/diagnostic sampling and the hot table's separate busy guard.
The natural x86_64 ticket layout is 32 bytes, with no added cache-line padding.
Implementation and measured validation are tracked in the
[2026-09-27 flow report](../../bench/tclock_compare/results/20260927-flow.md).

One stack-local `kd_spin_request` carries that physical ticket and the KD word through
pending/tail helpers, node admission, queue-head claims and combiner batches.
The batch retains it across early outer release and reclaim; neither a recycled
node nor a nested waiter's ancestor `spin_origin` substitutes for this request.
Hook unlock passes its already-found ticket through release. Nested unlock
uses the direct word for its OOO result; an ancestor represented only by
frame/shadow state still needs its retained physical owner to release.

Only the original waiter can end its pin/preemption obligation. A combiner
cannot remotely unpin it. Native borrow references defer completion until
all native executors have cleaned up and popped, including zero-lock relays.
A physical ACK alone does not end the borrow. These metadata do not add wrapper arguments.

Each CPU has four exact node reservations. Reserved-but-not-yet-acquired
nodes count as occupied; completion cannot release a different slot or use
a held-only count. Reservation spans every published queue pointer, saved RSP,
request and borrowed reference. Published/woken nodes may immediately be
reused; snapshot needed data before wake and never read them afterward.

Spin completion release-publishes the combined `completed=1/locked=0` word
after final register state is ready and the frame has popped. Lone/IRQ-native and batch-successor
handoffs also use release stores; their acquire-side waiters may immediately
consume or reuse the node. Queue splicing must finish before publication, and
the publisher uses its saved successor afterward. This makes the publication
contract explicit; it does not transfer physical ownership or prove arbitrary
memory ordering, task lifetime or flags semantics through a userspace fixture.

At initial spin batch entry, a NULL `next` does not by itself prove the node is
last: the producer exchanges the KD tail before release-linking the predecessor.
With the KD word still held and before any NUMA splicing, a different nonzero decoded
tail proves a successor is in flight. Wait for that link, then acquire-read it.
A real tail node still receives the ordinary native handoff; this check is not
used on detached deferred lists. No body executes until the existing JIT
admission succeeds. The directed delayed-link mutation guards this boundary.

Inside an active batch, a missing link after the saved successor receives at
most eight `cpu_relax()`/`READ_ONCE` retries. Short bodies can otherwise catch
returning producers and repeatedly pay the physical handoff cost. Existing
links take no pause; a native successor or the body cap ends the batch
immediately. With NUMA enabled, an existing deferred remote group also ends
an empty-link batch immediately, so waiting for local replenishment cannot
delay that group's handoff. This check reads the existing per-CPU queue head
only at the empty-link boundary. The saved successor has not been woken and
remains queue-owned.
This grace needs no proof that a producer is coming: expiry hands off normally.
It does not change the six-successor admission rule or the NUMA scan budget.

### 4.3 Combiner And Native Returns

The combiner owns the KD word while processing an eligible batch, validates entry
readiness/context, reconstructs waiter registers and enters a frame.
Unstarted work can receive native handoff. Partial JIT progress cannot be
converted into entry replay.

Spin uses ordinary `raw_spin_lock` semantics: pin preemption without saving,
disabling or restoring IRQs/BH. Ticket metadata reuses the acquisition pin;
shared mutex/native infrastructure retains its separate synchronization contract.
Physical waiters switch to the 8 KiB polling stack before publication, so IRQ
entry cannot write the task stack lent to JIT. Virtual waiters keep an independent
executor stack. Hardirq/softirq callers are still routed to native MCS, and
translation of IRQ/BH-changing code retains the existing exclusions.

Both node producers use single-instruction per-CPU reservation. A combiner saves
its node state before releasing the slot and reserves it again before restoring
that state. A returning producer retains its node through its last state read;
interrupts can reuse the slot only after that release. Continuation storage is
CPU-pinned and task-only, independent of interrupt-native node reuse.

| Physical slowpath exit | Stack and continuation |
| --- | --- |
| Queue-head/combiner acquisition (`0/2`) | Body has not run on behalf of this caller; return through intact C frames with IRQ state unchanged. |
| Remote completion or native suffix | `spin/wait.inc` selects an aligned safe RSP and calls `kd_spin_resume_completed(node)` directly; old C frames never return. |
| Pre-body retry after acquisition (`4`) | Retain the acquired ticket/pin and enter `kd_spin_resume_waiter(node, 1)` on the safe stack. |

Virtual waiters keep their independent executor C stack and the existing
`1/3/5` parent-notification returns. These are no longer physical waiter
completion returns.

The restoration helper retains the continuation and ticket. `end_pinned()`
retires ticket metadata without consuming the acquisition pin. Final assembly
loads all registers, retires the continuation and collapses its CPU storage top;
only then does the GPR-preserving `kd_spin_restore_unpin()` enable preemption on
the restored task stack. No packet access follows that scheduling boundary.
Retry retains the acquired pin. Native suffixes retain it until all executors
retire after the final physical ACK; zero-lock suffixes retire before restoring.
IRQ state is unchanged and the restore performs no `popfq`. This introduces no
new JIT condition-code restoration ABI.

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
20 KiB region: low 12 KiB for at most twelve 704-byte continuations and high
8 KiB for physical waiter polling, following TCLock's separation
of the suspended task stack from the waiting CPU's live RSP. One assembly region
switches stacks before publication and saves only the old C RSP. An unexecuted
head handoff restores it; completed/native wakes abandon the old C chain and
start restoration below both the saved physical and final logical RSP. The CPU
leaves the shadow stack before releasing its pin or restoring IRQs. Virtual
waiters keep their executor C stack for nested owner/ACK service. Allocation
failure rolls back initialization; drained shutdown frees the shared regions.
Only the owning CPU changes the continuation top, collapsing contiguous retired
records without scanning holes or moving live records. Frame pop and storage
reclamation are separate boundaries; see [storage and data flow](../../bench/spin_cacheline/EXECUTION_PATHS.md). The lock
ledger and wrapper RSP scratch are separate metadata. Frame and held-lock
depths are bounded at eight.
Frame count, logical depth, held-lock count and node reservations are distinct
resources. Sampled stack margins are not an arbitrary IRQ/NMI safety proof.
NUMA-local batching is enabled by default, with an exact 1024-body batch cap
and a separate scan budget initialized to 1024 for each batch. Both use the
build-time `KDLOCK_SPIN_BATCH` value (1–1024) but are consumed independently.
A scan appends a contiguous remote run once,
reusing its existing links while advancing only the CPU-local tail.
Deferred remote nodes precede the final handoff;
native boundaries and nested save/restore remain. These bound batch work, not
scheduler latency. CPU storage prefers its owning NUMA node at initialization.
This is not a different physical lock protocol.

## 5. Mutex Delegation Protocol

Explicit callers use `KD_MUTEX_DIRECT_LOCK/UNLOCK` and prepare the named
post-lock continuation with `kd_mutex_prepare(..., KD_ENTRY_ABI_MUTEX_CLOBBER_V1)`.
The exported module entry points use ABI2's existing lock/SP/IP/BP shell; no
global interception or extra wrapper input is required. Translation, admission
and runtime control tables recognize both direct endpoints and the captured
kernel bridge aliases. Pristine COMPLETE metadata names the direct unlock;
bridge aliases continue through checked generic FULL handling. All forms keep
the original Linux mutex owner and final ACK protocol below.

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

The removed hook-based mode 4 workload historically tested a bounded seven-role/two-CPU
schedule: B's holder observes A's physical executor in B's real wait list on
the same CPU before releasing B. That executor subsequently completes JIT;
this is not original-waiter native continuation or a change to mutex ownership.
The [历史：execution flow](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/mutex_protocols.md#612-同-cpu-的嵌套-mutex-jit) distinguishes
this scheduling check from PENDING recovery and independent-queue refusal.

That historical workload also had a separate shared-B session: A0's physical combiner retains
A0/B across an ordinary CALL miss while A1's combiner and a non-target peer
both wait on that exact Linux B. The waiter requests owner-side unlock/ACKs;
A1 then completes its own JIT and the native peer acquires as its own owner.
This exercises cross-frame exclusion, not a spin-style remote B combiner or
owner transfer. The [历史：shared-B flow](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/mutex_protocols.md#615-两个-a-combiner-共享原生-mutex-b)
keeps publication, actual JIT, real wait-list identities and exact effects
distinct from merely completing all clients.

### 5.2 Entry, Completion, And Task Routing

<a id="mutex-outer-direct"></a>
#### Explicit outer direct pair

`KD_MUTEX_OUTER_LOCK(lock, cookie, continuation)` and
`KD_MUTEX_OUTER_UNLOCK(lock, cookie)` operate on the original Linux mutex.
Each lexical acquisition owns an opaque `struct kd_mutex_outer_cookie`; it stays
with the same task and must not be copied, transferred, modified or reused before
its paired unlock. This interface is for outer entries. Nested control calls
inside translated bodies retain `KD_MUTEX_DIRECT_LOCK/UNLOCK` and their lock ledger.

The caller performs `might_sleep()` and the original owner CAS. Native success
records one approximate mutex entry and stores the acquiring task pointer in its
cookie. Its unlock calls the original `(mutex_unlock)(lock)`, bypassing KD task
routing while retaining Linux owner/flags and slowpath behavior. The cookie
selects the route; it neither grants ownership nor replaces the original mutex.

A failed CAS enters the outer-only `kd_mutex_outer_contended_clobber_v1`, which
records that failed attempt once without retrying the first CAS. On a physical C
return, a native fallback made before acquiring a KD task reference or queue gate
returns the current task pointer. That exact acquisition result selects original
Linux unlock. Every call into the KD queue returns zero, even a later native
fallback which already dropped its routing reference. The old void
`kd_mutex_direct_contended_clobber_v1` remains compatible with existing callers.

The supplied JIT IP is a separate continuation: a normal return jumps over its
zeroing instruction and keeps the C result, while translated execution starts at
that instruction and defines zero before the cookie store and body. SP/BP and
the two-word wrapper input are unchanged; no incoming RAX fact is trusted. The
return-valued outer endpoint is explicitly refused inside translated bodies;
nested controls keep the old direct interface. Zero selects routed unlock: queue
owners still release the gate/task record, and borrowed native continuations
still request the physical owner's unlock and final ACK. COMPLETE resumes after
the routed unlock; FULL preserves the cookie and existing continuation path.

Both unlock branches end at recognized mutex control CALLs. An empty compiler
barrier keeps the native CALL from becoming a sibling tail jump; it adds no
hardware fence. The original native unlock call bounds that branch before the
caller's canary/epilogue. The direct unlock identity, ABI2 MINIMAL/COMPLETE metadata
and two-element wrapper input remain unchanged. Preparation still registers the
exact slow-call continuation through `kd_mutex_prepare`; native fast execution
does not supply JIT completion evidence. The current workload callers retain
their five callee-saved register spills.

#### Provider acquisition and completion

1. Try the original mutex's owner CAS first. The outer pair does this in the
   caller; the existing general direct entry does it in the provider. Success
   bypasses admission, shadow/task records and translation. The attempt and failed-CAS counts are
   separate approximate per-CPU mutex counters: every 1024 contentions compare
   `(entries >> 10) < 256`, reset both counts and update the CPU clock. The initial
   limit 2 rejected every CPU in the cacheline screen; the measured native owner
   bursts required a wider mutex window. Spin MCS
   counters are independent. A successful native CAS precedes any counting pin;
   its single x86 per-CPU increment is approximate and may follow migration.
   Failed attempts pin their entry/contention observations together, then end
   that pin before native blocking.
   Cold locks, `mutex_jit=0`, shadow/task-record allocation failure, and nested
   acquisitions by an already-active task use the original native slow route.
2. A promoted, eligible request finds its original-address shadow by acquire-reading
   the immutable key. Existing hits take no table lock. Cold insertion rechecks
   under the insertion lock, initializes the gate, then release-publishes the key;
   no slot is removed or reused before drain/unload. It then registers its task
   before entering the scheduler.
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
   Ordinary ABI2 roots now use mutex-specific batch preparation and terminal
   retirement. One enclosing source lease spans the whole batch, including
   synchronous native completion and the last owner ACK. Every new root still
   checks source OPEN and the image publication/ABI. Its explicit QUEUE_OWNER
   ledger remains available before executing any body. A returned FULL exit
   enters the generic dispatcher once; it never invokes the first body again.
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

#### Terminal FIFO waiter retirement

A final queued ABI2/MINIMAL waiter can execute without an already linked
successor. Legacy/FULL terminal packets keep the existing native handoff.
Eligibility changes neither image admission nor replay permission: a missing
image, busy frame context or other unstarted refusal retains its original node
and tail and receives ordinary physical handoff.

Before publishing a committed result, the batch removes that node's queue
publication. It retains an already linked successor; otherwise it attempts an
exact `tail == current.tail` CAS to zero. Losing the CAS means a publisher has
already exchanged the tail, so the batch waits for that publisher's delayed
successor link before allowing node reuse. Winning the CAS makes a later
`old_tail == 0` publisher an independent head: it never links through the old
node and still waits for the original mutex and private gate. This link-completion
wait preserves the MCS publication obligation; it is not a bounded refill or a
starvation guarantee.

The batch records `current_retired` once. Queue retirement precedes COMPLETE
publication, a native FULL resume publication, and any early outer release.
After a native wake the origin may immediately recycle its node, so subsequent
owner-ACK/early-release processing uses only the retained batch state. An early
release can detach an empty queue and log `next_task=0`; a later independent head
observes the gate opening itself. A nonempty successor receives one handoff.
The old executor finishes B and its final ACK, then reacquires A for its own
original operation. Once retirement occurred, execution is committed: a protocol
error cannot be converted into an unstarted retry of that request.

The physical-owner ledger, exact task/slot/waiter references and enclosing
source lease retain their existing lifetimes. The source lease spans the final
ACK and frame retirement. Normal completion keeps the original mutex for the
physical owner's own body. The batch remains FIFO with a 1024-body limit, and
checks the limit before inspecting the next candidate. No dummy node, queue
reordering, new prefetch access, waiter layout or wrapper ABI is introduced.

Each CPU has four independently reserved 8 KiB waiter stacks, allocated with its
CPU NUMA node as the preferred node. The combiner prefetches a known-live queued
successor’s header, register packet and two nearby caller-stack lines before the
current body; it never follows that successor after publishing a wake. Pure
observations use per-CPU counters, summed after drain. Exact waiter/slot/task
references and physical ownership remain independent of these observations.
An exhausted task
never publishes a queue node; it waits on its native stack for the gate and
then acquires the original mutex. Migration stays disabled during queued waits,
but preemption is temporarily enabled where scheduling or native locking is
required. A scheduled combiner retains ownership of its per-CPU frame context;
another task cannot overwrite it.

Resource tests compile the production reservation, shadow lookup, hooks and
entry/return consumer. They check no-node acquisition and copy-before-slot-reuse
with KD's complete software `kd_regs` packet; physical locks, scheduler, task records and
assembly are substitutes. Their scope and live-test separation are maintained
in [历史：the mutex resource guide](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/mutex_protocols.md#61-mutex-资源与恢复包).

`kd_mutex_tasks.c` keeps RCU-readable task membership with a task reference and
lock-protected acquisition refs. The existing mutex `is_kd` callback matches
target comm or membership. This preserves unlock routing after a rename; it
does not replace the original lock. `mutex_task_fail_once=1` tests pre-entry
allocation failure. No allocations are needed in the predicate. Unload requires
all callers stopped and records/queues drained; `rcu_barrier()` only completes
deferred task-record frees, not general hook hot-unload protection.

The directed [task/ACK probe](../../tests/kernel/mutex/run_task_selftest.py)
connects the real registry to the production native request/ACK path, with an
actual RCU reader spanning final removal. Three pinned kernel tasks exercise
both B-before-A and A-before-B unlock, shared acquisition refs and two deferred
frees after their readers exit. Its constructed continuation and outer batch
callback are explicitly JIT=0; ordinary benchmark returned-body evidence is
separate. Controlled source retirement and empty registry are checked before
provider unload.

#### Pinned Busy Polling

Both spinlock and mutex delegation support explicit GS memory operations by
default. Spinlock waiters keep preemption disabled from physical entry (before statistics)
through their queued wait. Physical waiters switch to the per-CPU shadow stack,
publish and PAUSE-poll in `spin/wait.inc`, with IRQ state unchanged; virtual waiters
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
`native-4-4` historical gate checked this with three A queue tasks on one CPU, real B
contention and an injected PENDING exit. Only mutex workload barriers and
observations change, not the production scheduling or ownership protocol.
Flow, placement evidence and limits are in
[历史：usage 6.1](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/mutex_protocols.md#61-mutex-资源与恢复包). This successful continuation
is distinct from refusing another queue's unstarted JIT request below.

Native registrations are matched by logical task, backend and retained lock,
not by a single global "current waiter". The opt-in
[历史：dual-queue workload](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/native_protocols.md#66-独立队列的并行-native-frame) keeps two
real mutex native frames alive at once and checks both drain orders. Each has
its own physical A/B owner, waiter record and stack-local ACKs. It uses separate
published entries with the daemon stopped; an ordinary miss makes its entry
not-ready, so this does not test concurrent code replacement or imply that a
second invocation of the same entry can always start after that miss.

A scheduled mutex combiner retains ownership of its CPU-local execution
context, not only its physical mutexes. A different combiner on that CPU must
refuse an unstarted JIT request even when its entry is ready, then use ordinary
queue handoff and native ownership. The
[历史：same-CPU workload](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/mutex_protocols.md#67-同-cpu-的-mutex-jit-拒绝) keeps the first
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
[历史：original-waiter signal test](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/native_protocols.md#64-原-waiter-的信号与退出) checks
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

Historical mode numbers describe removed hook workloads, not current live
entry points. Current direct/SELFTEST coverage is listed in
[tests](../../tests/README.md); historical evidence remains in [VALIDATION](../VALIDATION.md).

### 5.4 Differences from Spinlock Path

| Aspect | Spinlock | Mutex |
|--------|----------|-------|
| Queue structure | Per-CPU `kd_spin_node[4]` | Bitmap-reserved per-CPU `kd_mutex_node[4]` |
| Exclusion | Single KD word, held by the physical executor | Original Linux mutex and its actual owner |
| Scheduler state | Pending/tail in the same KD word | `kd_mutex.locked/tail`, never sufficient for exclusion |
| Scheduling | Non-sleeping spin protocol | Delegation waiters PAUSE with preemption disabled; native executors may sleep |
| Nested contention | Virtual spin waiter and combiner snapshot | Same combiner waits for native B |
| OOO unlock | Owner-side KD A release, logical-parent rendezvous and ticket-preserving reclaim | Native A/S early release, same-owner B and A reacquisition after suffix |
| JIT disabled | Per-lock spin readiness policy | All mutex calls use original native protocol |

### Spin diagnostic identity lifetime

The producer resolves its diagnostic slot once at the SLOWPATH observation and
retains it in the existing continuation. Waiter enter events remain after tail
publication and before predecessor linking; every existing exit records a
matching event. Both increment monotonic totals in the existing per-CPU
diagnostic storage, including when entry and exit run on different CPUs.
The combiner receives the owner's retained slot rather than looking through a
recyclable queue node. Slots are append-only until drained provider shutdown;
NULL slots still omit diagnostics without changing request handling.

The exported waiter observation sums all possible CPUs and returns the signed
enter-minus-exit balance. Live reads span different instants, so they can be
stale or negative; they neither clamp the result nor signal live underflow.
After entry references, physical owners and frames independently drain, the
aggregate is exact: either sign of nonzero final balance reports an invariant
failure, and final `waiters=0` remains a required diagnostic. This deliberately
loses the former immediate atomic-underflow signal, including a transient bad
hook order later balanced by another event. It does not replace ownership,
ACK, retirement, source-lifetime or actual-JIT evidence. Mutex waiter/drain
counters retain their existing exact semantics.

The shared slot keeps its 128-byte alignment; removing the unused waiter field
reduces its stride from 256 to 128 bytes and the 32-slot table from 8 to 4 KiB.
Two local totals
grow each dynamic counts record from 80 to 96 bytes, adding 512 bytes per CPU
without changing nodes, continuations or static per-CPU placement. Validation
and performance limits are recorded in the [peak investigation](../../bench/tclock_compare/results/20260924-warmed-peak.md#per-cpu-waiter观察保留).
