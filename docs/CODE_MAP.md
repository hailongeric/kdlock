# Code map

Start with [the design](DESIGN.md) and [lock protocols](design/lock_protocols.md).
This map lists maintained source boundaries; build products and evidence archives
are not source directories.

## Provider and execution

| Entry | Responsibility |
| --- | --- |
| [kd_main.c](../kernel_module/kd_main.c) | Provider setup, drain and teardown; no global hooks |
| [kd_spin_runtime.c](../kernel_module/kd_spin_runtime.c) | One compilation unit for spin, mutex, dispatcher and frame helpers |
| [kd_spinlock.c](../kernel_module/kd_spinlock.c) → [spin](../kernel_module/spin/) | Direct entry, pending/MCS, batching, prefetch, continuation and restore |
| [kd_spin_entry.c](../kernel_module/kd_spin_entry.c) → `spin/ticket_*.inc` | Exact acquisition tickets, native borrowing and final retirement |
| [kd_mutex.c](../kernel_module/kd_mutex.c) → [mutex](../kernel_module/mutex/) | Original mutex owner, private scheduling gate, queue and waiter restore |
| [kd_mutex_tasks.c](../kernel_module/kd_mutex_tasks.c) | Exact task/acquisition references and RCU removal |
| [kd_lock.c](../kernel_module/kd_lock.c) → [lock](../kernel_module/lock/) | Nested control CALLs, direct mutex routing and retained bridge aliases |
| [kd_exec.c](../kernel_module/kd_exec.c), [exe.c](../kernel_module/exe.c) → [execution](../kernel_module/execution/) | Frame binding, lock ledger, remote/native ACKs, registry and JIT dispatch |
| [kd_hotlock.c](../kernel_module/kd_hotlock.c) | Per-type exact-address hot tables and approximate admission statistics |
| [kd_source.c](../kernel_module/kd_source.c), [sys.c](../kernel_module/sys.c) | Source pins, device session, capabilities, publication and retirement |
| [Shared headers](../include/README.md) | Direct APIs, ABI, packet/frame types and wrapper assembly |

Private `.inc` files keep static state and declaration order inside the original
translation unit. They are not separate Kbuild objects. Read ordinary spin from
`direct.inc` → `entry.inc` → queue/combiner → restore/unlock; read mutex from
`lock/mutex_calls.inc` → `mutex/queue.inc` → combiner/waiter/clobber.

## Translation and reference backends

| Entry | Responsibility |
| --- | --- |
| [Daemon](../daemon/README.md) | Request polling, workspace, compiler child and image upload |
| [disassem.py](../disassem/disassem.py) | Translation coordination and CLI |
| [translation_scope.py](../disassem/translation_scope.py), [translation_image.py](../disassem/translation_image.py) | Selected decode scope, dispatch table and generated body |
| `context_*.py` in [disassem](../disassem/) | Admission, bounded value/memory flow, register facts and guards |
| [komb.c](../tclock_backend/komb.c) → [TCLock spin](../tclock_backend/spin/) | State, queue, combiner, waiter, lifecycle, trampoline, lock and unlock |
| [komb_mutex.c](../tclock_backend/komb_mutex.c) → [TCLock mutex](../tclock_backend/mutex/) | Parking, queue, combiner, slowpath, trampoline and unlock |
| [TCLock providers](../tclock_backend/README.md) | Independent backend lifecycle, registered contexts and pinned upstream provenance |

## Workloads and checks

| Directory | Contents |
| --- | --- |
| [workload_modules](../workload_modules/README.md) | Separate spin/mutex payloads; shared timing and business logic |
| [bench/tclock_compare](../bench/tclock_compare/README.md) | Three-arm runners, sessions and current result reports |
| [bench/spin_cacheline](../bench/spin_cacheline/README.md) | Shared client, peak selection, provider preparation and offline readers |
| [tests/unit](../tests/unit/) | Guest-only basic and selected production-code fixtures |
| [tests/kernel](../tests/kernel/) | Provider observers and kernel selftests |
| [tests/protocols](../tests/protocols/) | Trace validation, topology and protocol oracles |
| [kernel_baseline](../kernel_baseline/README.md), [kernel_experiments](../kernel_experiments/README.md) | Captured kernel identity and independently authorized experiment bundles |

The large entry-scope fixture groups its cases under
[tests/unit/execution/jit_entry_scope](../tests/unit/execution/jit_entry_scope/).
Production-source fixtures expand private includes through
[source_text.py](../tests/unit/infrastructure/source_text.py).
