# Code map

This map locates maintained source. [Design](DESIGN.md) explains the shared model;
[lock APIs](LOCKS.md) and the four implementation guides own protocol details.
Build outputs and frozen result snapshots are evidence, not another source tree.
The [lock replacement contract](design/kdlock_lock_replacement_contract.md)
separates the selected original JIT correction, its component evidence and
partial live results from the historical reached backend. This map identifies
source responsibility, not a build or runtime pass.

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
| [kd_rwsem.c](../kernel_module/kd_rwsem.c), [types](../include/kd_rwsem_types.h) | Local readers, exact selected writer phase, waiting, cancellation, real downgrade and atomic read release |
| [kd_rwsem_api.h](../include/kd_rwsem_api.h), [kd_rwsem_api.c](../kernel_module/kd_rwsem_api.c) | Public writer names and quiescent prepared capture; shared admission checks actual gate/reader readiness; typed release follows exact owner/ACK |
| [kd_lock.c](../kernel_module/kd_lock.c), [lock/](../kernel_module/lock) | Supported nested controls and exact direct/public mutex routing |
| [kd_exec.c](../kernel_module/kd_exec.c), [exe.c](../kernel_module/exe.c), [execution/](../kernel_module/execution) | Shared frames, ledger, image binding, native/remote ACKs, registry and dispatcher |
| [kd_admission.c](../kernel_module/kd_admission.c), [kd_wait_queue.c](../kernel_module/kd_wait_queue.c) | Exact acquisition predicates, shared request selection, cancellation and queue membership |
| [kd_service.c](../kernel_module/kd_service.c), [kd_service_api.c](../kernel_module/kd_service_api.c), [kd_service_calls.c](../kernel_module/kd_service_calls.c) | Retained origin/executor requests, exact owner custody, returning API intervals and current-position worker handback; source-specific component and application receipts are indexed in validation |
| [continuation.inc](../kernel_module/execution/continuation.inc), [service_control.inc](../kernel_module/execution/service_control.inc), [wrapper_entry.inc](../kernel_module/execution/wrapper_entry.inc), [native.inc](../kernel_module/execution/native.inc) | Retained frame/packet joins, original-JIT miss packets, Native owner routing, packet acceptance and typed release/ACK handling; component join covers acceptance/final ACK with supplied task/physical primitives |
| [images.inc](../kernel_module/execution/images.inc), [kd_image.h](../include/kd_image.h) | Image descriptors, immutable generations and retained compatibility publication checks |
| [kd_source.c](../kernel_module/kd_source.c), [sys.c](../kernel_module/sys.c) | Source pins, device session, capabilities, uploads and retirement |
| [kd_hotlock.c](../kernel_module/kd_hotlock.c) | Per-type exact-address tables and approximate heat policy; never ownership |
| [include/](../include/README.md) | Public interfaces, packet/frame ABI and wrapper assembly |

Private `.inc` files share their parent compilation unit and declaration order;
include them in snapshots. They are not independent Kbuild objects.

Operation IDs 14/15/16 are partitioned by
[`device_session.py`](../disassem/device_session.py), with discovery registration
in [`kd_rwsem_provider.c`](../kernel_module/kd_rwsem_provider.c).
`kd_service_write_owned` retains its narrow `ATOMIC_ORIGIN` custody proof.
`kd_service.c` owns synchronous home-CPU and serialized already-offline retirement.
[Validation](VALIDATION.md#retained-original-jit-and-proxy-read) separates component
fixtures, the historical failed targeted checker, later mmap1 results and static
master integration. A source location or prior component pass does not validate
the merged runtime combination.

## Linux 7 and MM integration

| Source | Responsibility |
| --- | --- |
| [Linux 7 integration](../kernel_integration/linux70/README.md) | Authenticated Ubuntu source, kernel prerequisites, build/signing and mitigation boundary |
| [capture.py](../kernel_integration/linux70/capture.py), [verify.py](../kernel_integration/linux70/verify.py) | Explicit normal/enabled-MM schema-2 identities and running policy |
| [prepare_mmap.py](../kernel_integration/linux70/prepare_mmap.py), [mmap-lock.patch](../kernel_integration/linux70/mmap-lock.patch) | Linux 7 source-bound MM preparation and wrapper/lifetime integration |
| [adapter.c](../kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/adapter.c), [pool.c](../kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/pool.c) | Per-mm Native/KD backend, local concurrent readers/writers and preallocated records |
| [mmap_fault](../workload_modules/mmap_fault), [mmap_writer](../workload_modules/mmap_writer) | Distinct device/private-backing fault and actual shared-mm workload payloads |

The local MM adapter executes unchanged bodies on the original task. Later
retained candidates run the same native bodies on E through the general lock
and service layer; this does not introduce operation-specific MM algorithms.
Ordinary `kdlock1`, historical `kdmm1` and scoped retained kernels have separate
identities. Their builds and measurements are not interchangeable.

At checkpoint `ebae17c1`, `kd_service.c` and `kd_exe_resume_retained` still select
the separate reached path through `reached_active`. Historical implementation
paths at that revision include `kernel_module/kd_reached_jit.c`,
`kernel_module/reached_jit_emit.inc`, `kernel_module/execution/reached.inc` and
`kernel_module/execution/reached_dispatch.inc`. Checkpoint `10ef078a` removes
those production paths and their selected emitter/cache/dispatcher, using
original compiled images. The C reference engine/adapter moves into test
fixtures. Stale reached-state fields remain. Later source-specific builds and
component results above do not establish live execution. Use `ebae17c1` when
examining the deleted historical source paths.

## Translation and reference backends

| Source | Responsibility |
| --- | --- |
| [daemon](../daemon/README.md) | Source-resident device session, compiler child and upload lifecycle |
| [disassem.py](../disassem/disassem.py) | Trusted-source default, original bounded CFG/history translation and image construction; eager ordinary-callee closure disabled by the correction |
| [translation_scope.py](../disassem/translation_scope.py), [translation_image.py](../disassem/translation_image.py) | Selected graph, wrapper dispatch and generated image |
| [release_units.py](../disassem/release_units.py) | Final source reachability at physical release boundaries, including the narrow retained-writer downgrade exception |
| [hostcall.py](../disassem/hostcall.py), [indirect_jump.py](../disassem/indirect_jump.py) | Selected scalar services and exact generated return/target routing |
| [normal.py](../disassem/normal.py), [special_inst.py](../disassem/special_inst.py), [wrapper.S](../include/wrapper.S) | Original saved-origin GS/logical-task lowering, virtual source SP/BP, actual CALL pushes/RET pops and current logical packet export |
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
| [mmap1/settled.py](../bench/mmap1/settled.py), [execution_session.py](../bench/mmap1/execution_session.py) | Bounded learning, fixed image/session receipts, compilation-excluded actual-syscall point and exact retirement |
| [tests/unit](../tests/unit), [tests/kernel](../tests/kernel), [tests/protocols](../tests/protocols) | Guest-only fixtures, provider probes and trace/ownership oracles |
| [results](../bench/results/README.md) | Published tables/charts and ignored raw evidence policy |

[Tests](../tests/README.md) owns check selection. Historical Linux 6.1 experiment
bundles and old helper probes retain their recorded scope; they are not current
setup instructions or proof of the trusted-source path.
