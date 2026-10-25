# Code map

Use this map to find the source file responsible for a feature. Start with
[Design](DESIGN.md) for the execution model and [lock protocols](design/lock_protocols.md)
for how each lock works. The tables list maintained source, not generated build
files or benchmark archives. The [lock catalog](LOCKS.md) organizes the four
public lock families and their canonical implementation guides.

The rwsem/mmap entries below include the `e6fc371` correction on
`codex/mmap-irq-trylock-20261025`. This branch's code and evidence are distinct
from maintained `master`; the [project guide](PROJECT_GUIDE.md) records that boundary.

## Provider and execution

| Entry | Responsibility |
| --- | --- |
| [kd_main.c](../kernel_module/kd_main.c) | Provider setup, drain and teardown; no global hooks |
| [kd_spin_runtime.c](../kernel_module/kd_spin_runtime.c) | One compilation unit for spin, mutex, dispatcher and frame helpers |
| [kd_spinlock.c](../kernel_module/kd_spinlock.c) → [spin](../kernel_module/spin) | Direct entry, pending/MCS, batching, prefetch, continuation and restore |
| [kd_rwlock.h](../include/kd_rwlock.h) → `spin/direct.inc`, `combiner.inc`, `execute.inc`, `restore.inc` | Local readers, native fast writers and ABI3 writer admission, cancellation and retry over the spin engine |
| [kd_spin_entry.c](../kernel_module/kd_spin_entry.c) → `spin/ticket_*.inc` | Exact acquisition tickets, native borrowing and final retirement |
| [kd_mutex.c](../kernel_module/kd_mutex.c) → [mutex](../kernel_module/mutex) | KD physical owner, legacy scheduling gate, queue and waiter restore |
| [kd_mutex_local.c](../kernel_module/kd_mutex_local.c), [kd_mutex_osq.c](../kernel_module/kd_mutex_osq.c) | KD-owned ordinary mutex exclusion, sleeping waiters, signal cancellation and private OSQ |
| [kd_mutex_state.h](../include/kd_mutex_state.h) | Embedded gate claim and owner phase stores; versioned waiter records in reserved nodes |
| [mutex/count.inc](../kernel_module/mutex/count.inc) | Cold exact waiter snapshots and controlled drain checks; no shared waiter-count updates |
| [kd_mutex_api.h](../include/kd_mutex_api.h), [kd_mutex_compat.h](../include/kd_mutex_compat.h) | Unified ABI2 blocking calls, callable local acquisition and source aliases for an exclusively KD mutex build |
| [kd_rwsem.h](../include/kd_rwsem.h), [kd_rwsem_types.h](../include/kd_rwsem_types.h) | Public read/write API and `struct kd_rwsem` layout/initializers; concurrent local readers and ordinary local writers |
| [kd_rwsem.c](../kernel_module/kd_rwsem.c) | Reader admission, exact writer reservations, cancellation/downgrade and reader drain; atomic read release omits synchronous wake, with timed rechecks by sleeping writers |
| [kd_rwsem_direct.h](../include/kd_rwsem_direct.h) | Explicit outer ABI2 writer pair; reserve/drain before publication and release the reservation on the origin after the mutex unlock/ACK |
| [kd_mutex_tasks.c](../kernel_module/kd_mutex_tasks.c) | Exact task/acquisition references and RCU removal |
| [kd_lock.c](../kernel_module/kd_lock.c) → [lock](../kernel_module/lock) | Nested control CALLs and direct KD mutex routing; no Linux mutex bridge |
| [kd_exec.c](../kernel_module/kd_exec.c), [exe.c](../kernel_module/exe.c) → [execution](../kernel_module/execution) | Frame binding, lock ledger, remote/native ACKs, registry and JIT dispatch |
| [kd_hotlock.c](../kernel_module/kd_hotlock.c) | Per-type exact-address hot tables and approximate admission statistics |
| [execution/images.inc](../kernel_module/execution/images.inc), [kd_image.h](../include/kd_image.h) | Immutable mutex and ABI1 guard/string images, private direct-call relocation, descriptor binding and generation-scoped misses |
| [execution/hostcalls.inc](../kernel_module/execution/hostcalls.inc), [execution/wrapper_entry.inc](../kernel_module/execution/wrapper_entry.inc) | Dispatcher services, direct-image entry/exit handling, exact ownership and CALL return state |
| [kd_source.c](../kernel_module/kd_source.c), [sys.c](../kernel_module/sys.c) | Source pins, device session, capabilities, publication and retirement |
| [Shared headers](../include/README.md) | Direct APIs, ABI, packet/frame types and wrapper assembly |

Private `.inc` files are source fragments included by a parent C file. They share
that file's static state and declaration order; they are not separate Kbuild
objects. Follow the ordinary spin path from
`direct.inc` → `entry.inc` → queue/combiner → restore/unlock; read mutex from
`lock/mutex_calls.inc` → `mutex/queue.inc` → combiner/waiter/clobber. Rwlock's
public count/gate protocol is in its header; the spin components acquire writer
admission before ABI3 execution and preserve it across native continuation.
Ordinary rwsem writers reserve admission and drain readers through `kd_rwsem.c`;
its internal `kd_mutex_local_*` calls supply physical writer exclusion. Accessing
the embedded gate directly bypasses reader admission and is invalid. Explicit
outer writers reserve/drain before `KD_MUTEX_OUTER_LOCK`; their reservation ends
on the origin after the matching mutex unlock/acknowledgement. The `gate` member
reuses the selected physical mutex and delegation queue.

## Mmap lock integration

| Entry | Responsibility |
| --- | --- |
| [adapter.c](../kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/adapter.c), [kd_mmap_lock.h](../kernel_integration/mmap_lock/overlay/include/linux/kd_mmap_lock.h) | Linux mmap read/write, trylock, killable, nested-write and downgrade wrappers; immutable Native/KD choice per mm; concurrent readers and writer bodies stay on the original task |
| [prepare.py](../kernel_integration/mmap_lock/prepare.py), [pool.c](../kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/pool.c) | Namespaced reuse of the shared local lock primitives and preallocated CPU/slot records; the built-in adapter omits delegation |
| [guest-kernel.patch](../kernel_integration/mmap_lock/guest-kernel.patch) | Lock field/routing, initialization/destruction and minimal API/lifetime wrappers, including the exact token/mm-reference transfer for asynchronous read release |

Native MM algorithms remain unchanged. Operation-specific body delegation and
prepared teardown are retired historical evidence. The
[integration guide](../kernel_integration/mmap_lock/README.md) records supported
interfaces, focused validation and unvalidated Native/RT/lockdep equivalence.

## Translation and reference backends

| Entry | Responsibility |
| --- | --- |
| [Daemon](../daemon/README.md) | Request polling, workspace, compiler child and image upload |
| [disassem.py](../disassem/disassem.py) | Translation coordination and CLI |
| [translation_scope.py](../disassem/translation_scope.py), [translation_image.py](../disassem/translation_image.py) | Selected decode scope, dispatch table and generated body |
| [constant_paths.py](../disassem/constant_paths.py) | Proves fixed branch outcomes before pruning unreachable source paths |
| [address_guards.py](../disassem/address_guards.py), [guard_flags.py](../disassem/guard_flags.py) | Restricted spin pointer-load checks and proof that incoming arithmetic flags are unused by the original native remainder |
| [strcmp_service.py](../disassem/strcmp_service.py), [strscpy_service.py](../disassem/strscpy_service.py) | Original C API memory effects: comparison preserves caller data; padding writes all 64 destination bytes. No helper-code inspection or runtime argument prechecks |
| [native_calls.py](../disassem/native_calls.py) | Direct original-helper calls inside the generated wrapper, register preservation, quotas, actual source returns and generated-call relocation metadata |
| `context_*.py` in [disassem](../disassem) | Admission, bounded value/memory flow, register facts and guards |
| [komb.c](../tclock_backend/komb.c) → [TCLock spin](../tclock_backend/spin) | State, queue, combiner, waiter, lifecycle, trampoline, lock and unlock |
| [komb_mutex.c](../tclock_backend/komb_mutex.c) → [TCLock mutex](../tclock_backend/mutex) | Parking, queue, combiner, slowpath, trampoline and unlock |
| [komb_rwlock.c](../tclock_backend/komb_rwlock.c), [rwlock_provider.c](../tclock_backend/rwlock_provider.c) | TCLock local readers, fast/queued writers, native stack delegation and count/gate/context drain |
| [TCLock providers](../tclock_backend/README.md) | Independent backend lifecycle, registered contexts and pinned upstream provenance |

## Workloads and checks

| Directory | Contents |
| --- | --- |
| [workload_modules](../workload_modules/README.md) | Spin/mutex/rwlock/rwsem payloads and API adapters; shared timing and business logic |
| [bench/tclock_compare](../bench/tclock_compare/README.md) | Three-arm spin/mutex runners, sessions and result reports |
| [bench/rwlock_compare](../bench/rwlock_compare/README.md) | RCUHT/cacheline rwlock and Native/TCLock/KD rwsem comparisons; TCLock rwsem uses restricted ordinary registered-worker pairs. Also proc spin snapshots, exact oracles and complete-body JIT evidence |
| [bench/mmap_lock](../bench/mmap_lock/README.md) | Prepared kdmm31 Native/KD shared-mm writer comparison: preparation, paired sessions, host capture and reporting; 24-session/six-boot live approval pending, no qualified new timing |
| [bench/spin_cacheline](../bench/spin_cacheline/README.md) | Shared client, peak selection, provider preparation and offline readers |
| [bench/spin_cacheline/native_image.py](../bench/spin_cacheline/native_image.py) | Captures loaded generated bytes outside timing and reconstructs relocated CALLs from uploaded placeholders and helper addresses; no helper-instruction inspection |
| [bench/api_profile.py](../bench/api_profile.py) | Separate unscored taskname/xattr function profiles, retained tracing state and exact restoration; diagnostic timings are excluded from benchmark scores |
| [tests/unit](../tests/unit) | Guest-only basic and selected production-code fixtures |
| [tests/kernel](../tests/kernel) | Provider observers and kernel selftests |
| [tests/kernel/spin/address_guard](../tests/kernel/spin/address_guard), [address-guard payload](../tests/kernel/spin/address_guard/payload) | Checked spin exit probe: completed JIT bodies, exact native continuation, retained effects, permanent delegation refusal and drain |
| [tests/kernel/spin/string_service](../tests/kernel/spin/string_service), [string-service payload](../tests/kernel/spin/string_service/payload) | Original `strcmp` service probe: short and 300-character comparisons, returned JIT bodies, unchanged published image, exact results and drain |
| [tests/kernel/rwlock](../tests/kernel/rwlock/README.md) | Native/KD correctness sessions: reader overlap, writer exclusion, exact updates, JIT and drain |
| [tests/kernel/rwsem](../tests/kernel/rwsem/README.md) | Sleeping/cancellation/downgrade and outer admission probe; checks ordering before publication without claiming JIT execution |
| [tests/kernel/mmap_lock](../tests/kernel/mmap_lock), [atomic-read payload](../tests/kernel/mmap_lock/irq/payload) | Actual-mm adapter checks and separate standalone IRQ/preemption read-trylock, rollback and writer-drain checks; distinct from provider/JIT and timing coverage |
| [tests/protocols](../tests/protocols) | Trace validation, topology and protocol oracles |
| [kernel_baseline](../kernel_baseline/README.md), [kernel_experiments](../kernel_baseline/experiments/README.md) | Captured kernel identity and independently authorized experiment bundles |

The large entry-scope fixture groups its cases under
[tests/unit/execution/jit_entry_scope](../tests/unit/execution/jit_entry_scope).
Production-source fixtures expand private includes through
[source_text.py](../tests/unit/infrastructure/source_text.py).
