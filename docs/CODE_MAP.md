# Code map

Use this map to find the source file responsible for a feature. Start with
[Design](DESIGN.md) for the execution model and [lock protocols](design/lock_protocols.md)
for how each lock works. The tables list maintained source, not generated build
files or benchmark archives.

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
| [kd_mutex_compat.h](../include/kd_mutex_compat.h) | Source aliases for an exclusively KD ordinary-mutex build |
| [kd_rwsem.h](../include/kd_rwsem.h), [kd_rwsem_direct.h](../include/kd_rwsem_direct.h), [kd_rwsem.c](../kernel_module/kd_rwsem.c) | Sleeping readers, ordinary writers and outer ABI2 writers; phase reservations drain readers before the unchanged mutex queue |
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
| [workload_modules](../workload_modules/README.md) | Separate spin/mutex/rwlock payloads; shared timing and business logic |
| [bench/tclock_compare](../bench/tclock_compare/README.md) | Three-arm spin/mutex runners, sessions and result reports |
| [bench/rwlock_compare](../bench/rwlock_compare/README.md) | RCUHT/cacheline rwlock and Native/KD rwsem comparisons, proc spin snapshots, exact oracles and complete-body JIT evidence |
| [bench/spin_cacheline](../bench/spin_cacheline/README.md) | Shared client, peak selection, provider preparation and offline readers |
| [bench/spin_cacheline/native_image.py](../bench/spin_cacheline/native_image.py) | Captures loaded generated bytes outside timing and reconstructs relocated CALLs from uploaded placeholders and helper addresses; no helper-instruction inspection |
| [bench/api_profile.py](../bench/api_profile.py) | Separate unscored taskname/xattr function profiles, retained tracing state and exact restoration; diagnostic timings are excluded from benchmark scores |
| [tests/unit](../tests/unit) | Guest-only basic and selected production-code fixtures |
| [tests/kernel](../tests/kernel) | Provider observers and kernel selftests |
| [tests/kernel/spin/address_guard](../tests/kernel/spin/address_guard), [workload_modules/jit_address_guard](../workload_modules/jit_address_guard) | Checked spin exit probe: completed JIT bodies, exact native continuation, retained effects, permanent delegation refusal and drain |
| [tests/kernel/spin/string_service](../tests/kernel/spin/string_service), [workload_modules/jit_string_service](../workload_modules/jit_string_service) | Original `strcmp` service probe: short and 300-character comparisons, returned JIT bodies, unchanged published image, exact results and drain |
| [tests/kernel/rwlock](../tests/kernel/rwlock/README.md) | Native/KD correctness sessions: reader overlap, writer exclusion, exact updates, JIT and drain |
| [tests/kernel/rwsem](../tests/kernel/rwsem/README.md) | Sleeping/cancellation/downgrade and outer admission probe; checks ordering before publication without claiming JIT execution |
| [tests/protocols](../tests/protocols) | Trace validation, topology and protocol oracles |
| [kernel_baseline](../kernel_baseline/README.md), [kernel_experiments](../kernel_baseline/experiments/README.md) | Captured kernel identity and independently authorized experiment bundles |

The large entry-scope fixture groups its cases under
[tests/unit/execution/jit_entry_scope](../tests/unit/execution/jit_entry_scope).
Production-source fixtures expand private includes through
[source_text.py](../tests/unit/infrastructure/source_text.py).
