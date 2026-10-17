# Shared interfaces

These headers define the public lock APIs and the data layouts shared by C,
assembly and the Python translator. Helpers used only inside a backend live under
[kernel_module](../kernel_module/README.md). Payload ioctls live under
[workload_modules](../workload_modules/README.md).

| Interface | Files | Boundary |
| --- | --- | --- |
| Explicit spin object/API | [kd_spin_type.h](kd_spin_type.h), [kd_spin_direct.h](kd_spin_direct.h), [kd_spin_fast.h](kd_spin_fast.h) | One KD word; ordinary preemption pair; no Linux/TCLock mixing |
| Spin queue and ticket | [kd_spinlock.h](kd_spinlock.h), [kd_spin_entry.h](kd_spin_entry.h), [qspinlock_i.h](qspinlock_i.h) | Reusable nodes, stable continuation and exact native borrowing |
| Mutex | [kd_mutex.h](kd_mutex.h), [kd_mutex_direct.h](kd_mutex_direct.h), [kd_mutex_compat.h](kd_mutex_compat.h) | KD-only object, ordinary API aliases, ABI2 and opaque outer cookie |
| Read-write lock | [kd_rwlock.h](kd_rwlock.h) | 128-byte object, 64-byte alignment; local readers, native fast writers and ABI3 JIT writers |
| Frames and controls | [kd_exec.h](kd_exec.h), [kd_call.h](kd_call.h), [kd_lock.h](kd_lock.h) | Logical state, held-lock ledger, source CALL and final ACK |
| Registry and execution | [exe.h](exe.h), [exe_info.h](exe_info.h), [kd_jit_batch.h](kd_jit_batch.h) | Backend/ABI/layout identity, readiness and distinct wrapper/C results |
| Mutex image lifetime | [kd_image.h](kd_image.h) | Immutable image descriptors, upload identity and generation-bound frames |
| Packet and wrapper | [kd_regs.h](kd_regs.h), [asm_head.h](asm_head.h), [wrapper.S](wrapper.S) | Layout2, virtual register backing and two-word input |
| Heat | [kd_hotlock.h](kd_hotlock.h) | Approximate future admission, not ownership |
| Source/device | [kd_source.h](kd_source.h), [kd_source_api.h](kd_source_api.h), [sys.h](sys.h) | Text residency, capabilities and irreversible retirement |
| Services/context | [kd_hostcall.h](kd_hostcall.h), [kd_hostcalls.def](kd_hostcalls.def), [kd_segment.h](kd_segment.h) | Typed effects and origin GS/logical task |

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

Mutex outer callers pair `KD_MUTEX_OUTER_LOCK/UNLOCK` with one opaque
`kd_mutex_outer_cookie` per acquisition. Do not copy, modify, transfer or reuse it
before its matching same-task unlock. The native CAS saves an exact owner; contended
KD entry saves zero. Nested translated operations use `KD_MUTEX_DIRECT_LOCK/UNLOCK`;
prepare uses `kd_mutex_prepare(..., KD_ENTRY_ABI_MUTEX_CLOBBER_V1)`. Registration
can succeed before immutable image allocation; only complete NORMAL publication
allows JIT execution. Provider, daemon and translator must negotiate the matching
version-4 legacy image capability.
[Ownership](../docs/design/locking.md#mutex-outer-direct) explains the routing.

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
