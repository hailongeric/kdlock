# Shared interfaces

These headers define the public lock APIs and the data layouts shared by C,
assembly and the Python translator. Helpers used only inside a backend live under
[kernel_module](../kernel_module/README.md). Payload ioctls live under
[workload_modules](../workload_modules/README.md).
API means application programming interface; ABI means the machine-level
calling agreement. JIT means just-in-time compilation for delegated execution.
The [terminology guide](../docs/TERMINOLOGY.md) explains the remaining protocol
terms. Local KD execution uses KD physical locking on the original caller;
it does not mean using the Linux Native backend.

| Interface | Files | Boundary |
| --- | --- | --- |
| Explicit spin object/API | [kd_spin_type.h](kd_spin_type.h), [kd_spin_direct.h](kd_spin_direct.h), [kd_spin_fast.h](kd_spin_fast.h) | One KD word; ordinary preemption pair; no Linux/TCLock mixing |
| Spin queue and ticket | [kd_spinlock.h](kd_spinlock.h), [kd_spin_entry.h](kd_spin_entry.h), [qspinlock_i.h](qspinlock_i.h) | Reusable nodes, stable continuation and exact native borrowing |
| Mutex | [kd_mutex.h](kd_mutex.h), [kd_mutex_api.h](kd_mutex_api.h), [kd_mutex_direct.h](kd_mutex_direct.h), [kd_mutex_compat.h](kd_mutex_compat.h) | KD-only object, unified ABI2 blocking calls, local task-sensitive APIs and separate outer cookie |
| Read-write lock | [kd_rwlock.h](kd_rwlock.h) | 128-byte object, 64-byte alignment; local readers, native fast writers and ABI3 JIT writers |
| Sleeping semaphore | [kd_rwsem.h](kd_rwsem.h), [kd_rwsem_direct.h](kd_rwsem_direct.h) | Ordinary sleeping APIs and outer ABI2 writers; phase reservations and reader drain precede the unchanged KD mutex queue |
| Frames and controls | [kd_exec.h](kd_exec.h), [kd_call.h](kd_call.h), [kd_lock.h](kd_lock.h) | Logical state, held-lock ledger, source CALL and final ACK |
| Registry and execution | [exe.h](exe.h), [exe_info.h](exe_info.h), [kd_jit_batch.h](kd_jit_batch.h) | Backend/ABI/layout identity, readiness and distinct wrapper/C results |
| Image lifetime | [kd_image.h](kd_image.h) | Immutable mutex images and spin images requiring address checks or string services; upload identity and generation-bound frames |
| Packet and wrapper | [kd_regs.h](kd_regs.h), [asm_head.h](asm_head.h), [wrapper.S](wrapper.S) | Layout2, virtual register backing and two-word input |
| Heat | [kd_hotlock.h](kd_hotlock.h) | Approximate future admission, not ownership |
| Source/device | [kd_source.h](kd_source.h), [kd_source_api.h](kd_source_api.h), [sys.h](sys.h) | Text residency, capabilities and irreversible retirement |
| Services/context | [kd_hostcall.h](kd_hostcall.h), [kd_hostcalls.def](kd_hostcalls.def), [kd_segment.h](kd_segment.h) | Typed effects and origin GS/logical task |
| Original kernel string APIs | [kd_hostcall.h](kd_hostcall.h) | Read-only versus 64-byte writing effects and invocation limits; argument validity follows the native caller's contract |

When changing a shared layout, update the C offsets, wrapper assembly and Python
translation together. [Register ABI](../docs/JIT_REGISTER_ABI.md) gives exact offsets
and exit rules; [frames](../docs/design/frames.md) explains when storage can be reused.
A frame's lock list, a completed queue node, an unlock ACK and a source lease each
track different work. One cannot substitute for the others.

## Ordinary direct pairs

Spin callers use `KD_SPIN_DIRECT_LOCK/UNLOCK`. The heat cookie reads one per-CPU
value to choose how to enter the lock. It does not record how acquisition actually
succeeded. Unlock uses the exact ownership record instead.
[Execution flow](../docs/JIT_EXECUTION.md#heat-and-roles) explains the heat samples.

Bodies that call ordinary C helpers can opt into `KD_SPIN_DIRECT_HELPER_LOCK`,
paired with the same `KD_SPIN_DIRECT_UNLOCK` and ABI1 preparation. A helper often
saves registers when it enters, even if it overwrites them immediately afterward.
The minimal KD entry supplies only the stack and frame pointers, so saving another
incoming register would otherwise fail the defined-value check. The helper entry
sets the five already-discarded registers `RBX` and `R12`–`R15` to zero before the
compiler reloads the body's values. These five source instructions execute on
both local hot returns and delegated entry; ordinary cold execution already has
valid native registers. This adds five instructions to hot acquisitions selecting
this API, without extra captures or stack saves. Other instruction, address and
context checks remain unchanged; selecting it does not authorize arbitrary helper
functions. Ordinary `KD_SPIN_DIRECT_LOCK` has no added instructions.

Taskname uses the ordinary `KD_SPIN_DIRECT_LOCK` pair. Its
`strscpy_pad(..., 64)` service invokes the original kernel API. The translator
does not translate the helper prologue or need the five register initializations.
The optional helper entry and the separate
[source constant proof](../docs/design/admission.md#source-branches-with-proven-constant-inputs)
remain available for other translated code.

The version 10 dispatcher implementation without helper-specific checks passed
[focused correctness checks](../docs/VALIDATION.md#taskname-and-xattr-helper-validation)
through candidate 6 and completed the
[`88bb5a4` standard-grid comparison](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/README.md).
Read-only KD taskname returned delegated bodies. Its 20% mutation control used no helper
preparation and recorded zero JIT, so it establishes correctness only.
The frozen `c79d84f` version used helper checks: its read-only taskname check
completed delegated bodies, while its 20% mutation check produced correct
results and drained but completed no delegated bodies during measurement.
Those [historical receipts](../bench/results/10.176.26.71/bench/taskname-xattr-20261018/DEVELOPMENT.md)
and the [comparison record](../bench/results/10.176.26.71/bench/taskname-xattr-20261018/README.md)
remain evidence for that earlier source version.
The final version 11 direct bridge passed its focused unit and live checks,
separate KD screen and all 18 diagnostic profiles. The
[development record](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md#candidate-3-checks)
retains exact counts and earlier failures. The separate
[`05876a4` standard-grid comparison](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
completed all 567 sessions with validation and drain for the three API
workloads. Archive verification and the separate n129 quota control are complete;
that control verified native waiter completion after quota exhaustion and drain.
The ordinary taskname call shell and original APIs are unchanged.

Mutex outer callers pair `KD_MUTEX_OUTER_LOCK/UNLOCK` with one opaque
`kd_mutex_outer_cookie` per acquisition. Do not copy, modify, transfer or reuse it
before its matching same-task unlock. The native CAS saves an exact owner; contended
KD entry saves zero. Nested translated operations use `KD_MUTEX_DIRECT_LOCK/UNLOCK`;
prepare uses `kd_mutex_prepare(..., KD_ENTRY_ABI_MUTEX_CLOBBER_V1)`. Registration
can succeed before immutable image allocation; only complete NORMAL publication
allows JIT execution. Provider, daemon and translator must agree on
immutable-image and exclusive-KD-object capabilities. Ordinary mutex images
accept compatible capability versions 5 through 11. Images with checked
instruction-exit markers require version 6 through 11 with feature bit 5 and declare
image requirement bit 0; see
[the admission contract](../docs/design/admission.md#checked-instruction-exits).
[Ownership](../docs/design/locking.md#mutex-outer-direct) explains the routing.

Restricted ABI1 spin pointer-load checks require provider version 7 through 11 feature
bit 6 and image requirement bit 1. A failed check resumes the exact load on the
original waiter and disables delegation for that entry; it does not change the
object's lock protocol. The source must prove its incoming arithmetic flags are
no longer needed. Bodies that also need source constant-branch simplification
remain refused, because a removed branch could hide a native flags read.
Entries use immutable images from their first address-check or typed string-service version
onward; ordinary spin and ABI3 rwlock entries do not all gain that lifetime
contract. The packet and two-word wrapper stay unchanged. See the
[complete guard contract](../docs/JIT_REGISTER_ABI.md#checked-spin-address-exit).

The current provider reports capability version 11. Feature bit 9 means that
original string APIs use the native caller's memory and lifetime guarantees,
without helper-specific checks. `strcmp` also requires feature bit 7 and image
requirement bit 2; `strscpy_pad` requires feature bit 8 and image requirement bit
3. Optional bit 10 enables direct original-helper calls inside one generated
invocation; these images add requirement bit 4, value 16. It does not add a
wrapper argument. Direct calls require a pristine ABI1 spin root and cannot
combine with address guards, scalar dispatcher services or nonterminal lock
controls. Other eligible string bodies keep the dispatcher route.

The caller supplies valid, stable ordinary strings and a valid destination.
The `strscpy_pad(..., 64)` analysis accounts for all 64 destination bytes,
including truncation and padding. KD does not inspect either helper's
instructions, scan strings or recheck destination bounds. It retains the exact
physical owner and frame. The dispatcher checks the pending CALL word before
invocation; the direct route preserves the source CALL store and checks the
actual saved return after the helper. Either route consumes the word once.
One invocation permits at most 128 comparisons and 16 other continuations,
including writing services. See
[read-only API admission](../docs/design/admission.md#original-strcmp-service)
and [writing API admission](../docs/design/admission.md#original-strscpy_pad-writing-service)
for the complete caller and continuation contracts.

The private `kd_jit_batch_call` descriptor is 112 bytes: its original 96-byte
prefix is unchanged, and offsets 96 and 104 hold direct comparison and padding
call counts. The wrapper uses previously reserved stack slots for the remaining
allowances and aligns the executor stack once at direct entry. Its quota and
return checks preserve RCX and arithmetic flags through register operations,
without per-call stack alignment or flags scratch. Its two argument words,
0/1 body witness and register packet remain unchanged. A direct image exports
counts once on return; counts do not replace ownership or completion evidence.

Direct generated CALLs initially contain zero displacement operands. The
`KDNC0001` directory names these slots; the provider fills their relative helper
addresses in separate preallocated executable storage near kernel text before
immutable publication. The upload hash therefore does not identify the loaded
bytes by itself. Benchmark evidence captures the loaded generated image outside
timing and checks its reconstruction from the original upload and symbol
addresses. No helper instructions or arguments are inspected. Allocation and
entry restrictions are defined in
[direct-call admission](../docs/design/admission.md#direct-original-helper-calls);
[the register guide](../docs/JIT_REGISTER_ABI.md) owns exact offsets and exit 10,
which resumes an unexecuted excess call on the waiter without JIT reentry.

Rwlock readers pair `kd_read_lock/unlock`; explicitly native writers pair
`kd_write_lock/unlock`. Delegating writers use `KD_RWLOCK_DIRECT_WRITE_LOCK/UNLOCK`
with `kd_rwlock_direct_cookie` and a named continuation in a `noipa` function.
Prepare it with `kd_rwlock_prepare(..., KD_ENTRY_ABI_RWLOCK_CLOBBER_V1)` (ABI3).
The writer has exclusive access before entering that continuation. At unlock,
it clears the writer byte before completing through the spin engine. Older ABI1
rwlock callers must be rebuilt with matching provider, daemon and translator.
See [the rwlock API and protocol](../docs/design/rwlock_implementation.md).
All rwlock pairs keep preemption disabled until unlock. IRQ/BH variants and
read-to-write upgrades are unsupported.

Rwsem readers use `kd_down_read/up_read`; ordinary writers use
`kd_down_write/up_write`, with trylock, interruptible/killable and downgrade
variants. Explicit outer writers pair `KD_RWSEM_OUTER_WRITE_LOCK/UNLOCK` with
one `kd_rwsem_outer_cookie`. The pair reserves writer admission and drains
readers before the mutex can publish a pinned request, then releases that
reservation on the origin after the mutex unlock returns. It reuses ABI2 and
does not support cancellation, downgrade or nested translated acquisition.
See [the rwsem API and ordering](../docs/design/rwsem_implementation.md).

## Preparing a delegating body

Direct calls to `kd_mutex_lock/unlock` in `kd_mutex_api.h`, including ordinary
blocking aliases in `kd_mutex_compat.h`, use ABI2 with an internal continuation.
They need no caller cookie or named label and permit supported nested translated
locking. Addressable lock calls and signal/try/I/O acquisitions remain local;
public unlock retains exact provider routing for all successful acquisitions.
Scope guards acquire locally and guard/free cleanup uses routed public unlock;
their C symbols remain native-only admission boundaries. The compatibility
header explicitly redirects the captured Linux cleanup helper names to KD.
Ordinary rwlock and rwsem writers run locally. Use an explicit direct/outer pair
for those delegation interfaces, or to prepare named mutex entries; see the
[workload decisions](../docs/BENCHMARK_WORKLOADS.md#kd-api-use-and-delegation).

The following steps describe explicit named entries:

1. Initialize the appropriate KD object and make every reader/writer use the
   same protocol. Rebuild callers when changing object types; casting a Linux
   mutex to a KD mutex cannot convert its layout or ownership protocol.
2. Put the pair around the exact protected body in a function marked `noipa`,
   which prevents the compiler from inlining or cloning it across callers.
   Give its body-entry continuation a unique label. Retain the per-acquisition
   cookie for mutex/rwsem outer pairs. Spin/rwlock pairs use the supplied shared
   per-CPU routing cookie without modifying it. Match every acquisition with
   its corresponding release.
3. Before workers start, register that exact entry with `kd_spin_prepare()` for
   spin, `kd_rwlock_prepare()` for rwlock writers, or `kd_mutex_prepare()` for
   mutex. Their entry identities are ABI1, ABI3 and ABI2 respectively. The
   current rwsem adapter registers its internal mutex gate with ABI2 as shown
   in [direct_rwsem.h](../workload_modules/rwlock_bench/direct_rwsem.h), while
   acquisition/release always uses the rwsem outer pair to preserve reader
   exclusion. Do not use the gate directly to bypass that pair.
4. Let the daemon translate and publish the compiled entry, retaining refusal
   diagnostics. A successful prepare call or `NORMAL` image is not evidence
   that the body executed remotely. Validate completed returned bodies,
   protected results and full drain before reporting delegated performance.

The outer rwsem pair is for a same-task acquisition/release around one body;
its admission wait is uninterruptible. It does not provide killable admission,
downgrade or acquisition inside another translated body. Ordinary KD rwsem
APIs retain local cancellation and downgrade support.

## Explicit IRQ/BH spin interfaces

These operate on `kd_spinlock_t`, execute locally through native pending/MCS, and
need no preparation, continuation, daemon or heat cookie:

```c
DEFINE_KD_SPINLOCK(lock);
unsigned long flags;

kd_spin_lock_irqsave(&lock, flags);
/* IRQs disabled; flags describe this acquisition's prior state. */
kd_spin_unlock_irqrestore(&lock, flags);

kd_spin_lock_irq(&lock);
/* Requires IRQs initially enabled; matching unlock enables them. */
kd_spin_unlock_irq(&lock);

kd_spin_lock_bh(&lock);
/* Local BH/preemption disabled; hard IRQ state is preserved. */
kd_spin_unlock_bh(&lock);
```

Nested irqsave acquisitions use independent `unsigned long flags`. Match each
unlock variant to its acquisition; release lock/in-flight state before restoring
IRQ/BH and preemption. BH is not hard-IRQ protection. These variants do not send
local context to a remote combiner or provide supported JIT nested controls;
admission rejects those context-sensitive symbols. See [the consumer test](../tests/kernel/spin/irq_api/README.md).
