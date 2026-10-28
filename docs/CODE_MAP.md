# Code map

This map locates maintained source. [Design](DESIGN.md) explains the shared model;
[lock APIs](LOCKS.md) and the four implementation guides own protocol details.
Build outputs and frozen result snapshots are evidence, not another source tree.

## Provider and execution

| Source | Responsibility |
| --- | --- |
| [kd_main.c](../kernel_module/kd_main.c) | Initialization, active call-depth refusal, drain and teardown; no global lock replacement |
| [kd_spin_runtime.c](../kernel_module/kd_spin_runtime.c) | Shared compilation unit for spin/mutex execution helpers |
| [kd_spinlock.c](../kernel_module/kd_spinlock.c), [spin/](../kernel_module/spin) | Direct entry, pending/MCS, request storage, combiner, restore and unlock |
| [kd_spin_entry.c](../kernel_module/kd_spin_entry.c), `spin/ticket_*.inc` | Exact acquisition tickets, native executor references and retirement |
| [kd_mutex.c](../kernel_module/kd_mutex.c), [mutex/](../kernel_module/mutex) | Delegation phase, queue, batch selection, waiter/clobber stacks and retirement |
| [kd_mutex_local.c](../kernel_module/kd_mutex_local.c), [kd_mutex_osq.c](../kernel_module/kd_mutex_osq.c) | KD physical exclusion, sleepers, cancellation and independent OSQ membership in shared slots |
| [kd_mutex_state.h](../include/kd_mutex_state.h), [count.inc](../kernel_module/mutex/count.inc) | Exact phase and versioned waiter records; stopped-object/drain observations |
| [kd_mutex_api.h](../include/kd_mutex_api.h), [kd_mutex_compat.h](../include/kd_mutex_compat.h) | Unified ABI2 blocking calls, callable local APIs and source aliases |
| [kd_mutex_tasks.c](../kernel_module/kd_mutex_tasks.c) | Exact task/acquisition references and RCU removal |
| [kd_rwlock.h](../include/kd_rwlock.h), `spin/direct.inc`, `combiner.inc` | Concurrent local readers, exclusive writer admission and ABI3 retry/continuation |
| [kd_rwsem.c](../kernel_module/kd_rwsem.c), [types](../include/kd_rwsem_types.h) | Reader/writer phases, reservations, waiting, cancellation, downgrade and atomic read release |
| [kd_rwsem_direct.h](../include/kd_rwsem_direct.h) | Explicit outer ABI2 writers; reserve/drain before publication, origin release after mutex ACK |
| [kd_lock.c](../kernel_module/kd_lock.c), [lock/](../kernel_module/lock) | Supported nested controls and exact direct/public mutex routing |
| [kd_exec.c](../kernel_module/kd_exec.c), [exe.c](../kernel_module/exe.c), [execution/](../kernel_module/execution) | Shared frames, ledger, image binding, native/remote ACKs, registry and dispatcher |
| [images.inc](../kernel_module/execution/images.inc), [kd_image.h](../include/kd_image.h) | Image descriptors, immutable generations and retained compatibility publication checks |
| [kd_source.c](../kernel_module/kd_source.c), [sys.c](../kernel_module/sys.c) | Source pins, device session, capabilities, uploads and retirement |
| [kd_hotlock.c](../kernel_module/kd_hotlock.c) | Per-type exact-address tables and approximate heat policy; never ownership |
| [include/](../include/README.md) | Public interfaces, packet/frame ABI and wrapper assembly |

Private `.inc` files share their parent compilation unit and declaration order;
include them in snapshots. They are not independent Kbuild objects.

## Linux 7 and MM integration

| Source | Responsibility |
| --- | --- |
| [Linux 7 integration](../kernel_integration/linux70/README.md) | Authenticated Ubuntu source, kernel prerequisites, build/signing and mitigation boundary |
| [capture.py](../kernel_integration/linux70/capture.py), [verify.py](../kernel_integration/linux70/verify.py) | Explicit normal/enabled-MM schema-2 identities and running policy |
| [prepare_mmap.py](../kernel_integration/linux70/prepare_mmap.py), [mmap-lock.patch](../kernel_integration/linux70/mmap-lock.patch) | Linux 7 source-bound MM preparation and wrapper/lifetime integration |
| [adapter.c](../kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/adapter.c), [pool.c](../kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/pool.c) | Per-mm Native/KD backend, local concurrent readers/writers and preallocated records |
| [mmap_fault](../workload_modules/mmap_fault), [mmap_writer](../workload_modules/mmap_writer) | Distinct device/private-backing fault and actual shared-mm workload payloads |

Native MM bodies execute unchanged on their original task. The normal `kdlock1`
kernel disables the mmap backend; `kdmm1` modes have separate identities.

## Translation and reference backends

| Source | Responsibility |
| --- | --- |
| [daemon](../daemon/README.md) | Source-resident device session, compiler child and upload lifecycle |
| [disassem.py](../disassem/disassem.py) | Trusted-source default and translation/CLI coordination |
| [translation_scope.py](../disassem/translation_scope.py), [translation_image.py](../disassem/translation_image.py) | Selected graph, wrapper dispatch and generated image |
| [hostcall.py](../disassem/hostcall.py), [indirect_jump.py](../disassem/indirect_jump.py) | Selected scalar services and exact generated return/target routing |
| `context_*.py`, [constant_paths.py](../disassem/constant_paths.py), [address_guards.py](../disassem/address_guards.py), [guard_flags.py](../disassem/guard_flags.py) | Optional `trusted_source=False` regression analysis; bypassed by production |
| [strcmp_service.py](../disassem/strcmp_service.py), [strscpy_service.py](../disassem/strscpy_service.py), [native_calls.py](../disassem/native_calls.py) | Retained historical compatibility utilities; current strings use ordinary decoded CALL/RET |
| [TCLock backend](../tclock_backend/README.md) | Pinned upstream provenance, four-family module ports, fixed-affinity contexts and controlled drain |

## Workloads and checks

| Source | Responsibility |
| --- | --- |
| [workload_modules](../workload_modules/README.md) | Shared benchmark payloads and scoped syscall adapters |
| [current_plan.py](../bench/catalog_single/current_plan.py), [plan.py](../bench/catalog_single/plan.py) | Ten nano plus 42 micro/API definitions |
| [linux70.py](../bench/catalog_single/linux70.py), [linux70_mm.py](../bench/catalog_single/linux70_mm.py) | Single-round lock/API and separate MM orchestration, telemetry and receipts |
| [nano/best_case.py](../bench/nano/best_case.py) | Ten c01/c16/post256 profiles and matched local controls |
| [basic/run.py](../bench/basic/run.py) | Four-family returned-JIT functional presets, no performance scoring |
| [tclock_compare](../bench/tclock_compare/README.md), [rwlock_compare](../bench/rwlock_compare/README.md), [real_api](../bench/real_api/README.md) | Matched family/API runners, data oracles and returned-body observation |
| [mmap_fault](../bench/mmap_fault/README.md), [mmap_writer](../bench/mmap_writer/README.md) | Private-MM and actual shared-MM correctness/timing interfaces |
| [tests/unit](../tests/unit), [tests/kernel](../tests/kernel), [tests/protocols](../tests/protocols) | Guest-only fixtures, provider probes and trace/ownership oracles |
| [results](../bench/results/README.md) | Published tables/charts and ignored raw evidence policy |

[Tests](../tests/README.md) owns check selection. Historical Linux 6.1 experiment
bundles and old helper probes retain their recorded scope; they are not current
setup instructions or proof of the trusted-source path.
