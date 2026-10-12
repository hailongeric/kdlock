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
| [kd_spinlock.c](../kernel_module/kd_spinlock.c) → [spin](../kernel_module/spin/) | Direct entry, pending/MCS, batching, prefetch, continuation and restore |
| [kd_rwlock.h](../include/kd_rwlock.h) → `spin/direct.inc`, `combiner.inc`, `execute.inc`, `restore.inc` | Local readers, native fast writers and ABI3 writer admission, cancellation and retry over the spin engine |
| [kd_spin_entry.c](../kernel_module/kd_spin_entry.c) → `spin/ticket_*.inc` | Exact acquisition tickets, native borrowing and final retirement |
| [kd_mutex.c](../kernel_module/kd_mutex.c) → [mutex](../kernel_module/mutex/) | Original mutex owner, private scheduling gate, blocking result/gate waits and waiter restore |
| [kd_mutex_tasks.c](../kernel_module/kd_mutex_tasks.c) | Exact task/acquisition references and RCU removal |
| [kd_lock.c](../kernel_module/kd_lock.c) → [lock](../kernel_module/lock/) | Nested control CALLs, direct mutex routing and retained bridge aliases |
| [kd_exec.c](../kernel_module/kd_exec.c), [exe.c](../kernel_module/exe.c) → [execution](../kernel_module/execution/) | Frame binding, lock ledger, remote/native ACKs, registry and JIT dispatch |
| [kd_hotlock.c](../kernel_module/kd_hotlock.c) | Per-type exact-address hot tables and approximate admission statistics |
| [kd_source.c](../kernel_module/kd_source.c), [sys.c](../kernel_module/sys.c) | Source pins, device session, capabilities, publication and retirement |
| [Shared headers](../include/README.md) | Direct APIs, ABI, packet/frame types and wrapper assembly |

Private `.inc` files are source fragments included by a parent C file. They share
that file's static state and declaration order; they are not separate Kbuild
objects. Follow the ordinary spin path from
`direct.inc` → `entry.inc` → queue/combiner → restore/unlock; read mutex from
`lock/mutex_calls.inc` → `mutex/queue.inc` → parking/combiner/waiter/clobber. Rwlock's
public count/gate protocol is in its header; the spin components acquire writer
admission before ABI3 execution and preserve it across native continuation.

## Translation and reference backends

| Entry | Responsibility |
| --- | --- |
| [Daemon](../daemon/README.md) | Request polling, workspace, compiler child and image upload |
| [disassem.py](../disassem/disassem.py) | Translation coordination and CLI |
| [translation_scope.py](../disassem/translation_scope.py), [translation_image.py](../disassem/translation_image.py) | Selected decode scope, dispatch table and generated body |
| `context_*.py` in [disassem](../disassem/) | Admission, bounded value/memory flow, register facts and guards |
| [komb.c](../tclock_backend/komb.c) → [TCLock spin](../tclock_backend/spin/) | State, queue, combiner, waiter, lifecycle, trampoline, lock and unlock |
| [komb_mutex.c](../tclock_backend/komb_mutex.c) → [TCLock mutex](../tclock_backend/mutex/) | Parking, queue, combiner, slowpath, trampoline and unlock |
| [komb_rwlock.c](../tclock_backend/komb_rwlock.c), [rwlock_provider.c](../tclock_backend/rwlock_provider.c) | TCLock local readers, fast/queued writers, native stack delegation and count/gate/context drain |
| [TCLock providers](../tclock_backend/README.md) | Independent backend lifecycle, registered contexts and pinned upstream provenance |

## Workloads and checks

| Directory | Contents |
| --- | --- |
| [workload_modules](../workload_modules/README.md) | Separate spin/mutex/rwlock payloads; shared timing and business logic |
| [bench/tclock_compare](../bench/tclock_compare/README.md) | Three-arm spin/mutex runners, sessions and result reports |
| [bench/rwlock_compare](../bench/rwlock_compare/README.md) | Mixed RCUHT/cacheline rwlock runner, exact read/write oracle, JIT accounting and parity reports |
| [bench/real_api](../bench/real_api/README.md) | Scoped syscall workloads, matched backends, Stock control and acceptance limits |
| [tools/vm](../tools/vm/README.md) | Source synchronization and complete 1–64-worker comparison |
| [bench/results](../bench/results/README.md) | Frozen measurements and validation receipts grouped by machine |
| [bench/spin_cacheline](../bench/spin_cacheline/README.md) | Shared client, peak selection, provider preparation and offline readers |
| [tests/unit](../tests/unit/) | Guest-only basic and selected production-code fixtures |
| [tests/kernel](../tests/kernel/) | Provider observers and kernel selftests |
| [tests/kernel/rwlock](../tests/kernel/rwlock/README.md) | Native/KD correctness sessions: reader overlap, writer exclusion, exact updates, JIT and drain |
| [tests/protocols](../tests/protocols/) | Trace validation, topology and protocol oracles |
| [kernel_baseline](../kernel_baseline/README.md), [kernel_experiments](../kernel_experiments/README.md) | Captured kernel identity and independently authorized experiment bundles |

The large entry-scope fixture groups its cases under
[tests/unit/execution/jit_entry_scope](../tests/unit/execution/jit_entry_scope/).
Production-source fixtures expand private includes through
[source_text.py](../tests/unit/infrastructure/source_text.py).
