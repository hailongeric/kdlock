# kdlock

kdlock is an experimental x86_64 kernel lock-delegation provider. A combiner
translates and executes existing critical-section machine code for contending
callers. KD spin uses an explicit four-byte lock word; KD mutex retains the
original Linux mutex and its physical owner beside a private scheduling gate.
KD rwlock adds concurrent local readers and JIT-delegated writers over an embedded
KD spin gate.
The project also includes independent TCLock spin/mutex ports and Linux Native
comparison workloads. The optimization phase closed on 2026-10-09; the
[final results](bench/tclock_compare/results/20261008-protocol-simplification/README.md)
retain all requested thread counts and the remaining performance gaps.

Callers use explicit APIs. Loading a provider does not intercept ordinary Linux
locks. The captured `kdclobber2` guest interfaces remain required. The supported
execution paths, context limits and known limitations are documented below;
performance acceptance is workload-specific and belongs in the benchmark reports.

## Documentation

| Start here | Content |
| --- | --- |
| [Project guide](docs/PROJECT_GUIDE.md) | Current state, reading order and guest setup |
| [Six lock protocols](docs/design/lock_protocols.md) | KD/TCLock/Native spin and mutex: ownership, waiting, completion and lifetime |
| [Spin implementation](docs/design/spin_implementation.md) | Spin source paths, objects, cachelines, queues, prefetch and stack/packet flow |
| [Mutex implementation](docs/design/mutex_implementation.md) | Mutex native paths, contexts, task/shadow routing, frames, parking and ACKs |
| [Read-write lock](docs/design/rwlock_implementation.md) | Reader admission, writer JIT continuation and public API |
| [KD design](docs/DESIGN.md) | KD execution contracts and supported scope |
| [KD ownership](docs/design/locking.md) / [frames](docs/design/frames.md) | Nested ownership, source leases, native continuation and final retirement |
| [JIT execution](docs/JIT_EXECUTION.md) / [register ABI](docs/JIT_REGISTER_ABI.md) | Admission, translation, wrapper entry and COMPLETE/FULL exits |
| [Code map](docs/CODE_MAP.md) | Source and documentation responsibilities |
| [Operations](docs/AGENTS.md) | Host/guest boundaries, controlled drain and recovery |
| [Known limitations](docs/TODO.md) / [performance status](docs/PERFORMANCE.md) | Unresolved contracts, closed-phase outcome and deferred designs |
| [Validation and cleanup](docs/VALIDATION.md) | Completed checks, evidence retention and closeout scope |

## Repository

| Directory | Responsibility |
| --- | --- |
| [kernel_module](kernel_module/README.md) | KD direct spin/mutex provider and execution engine |
| [include](include/README.md) | Shared ABI, direct API headers and wrapper assembly |
| [disassem](disassem/README.md) | Decode, admission, register lowering and code generation |
| [daemon](daemon/README.md) | Translation requests and code publication |
| [tclock_backend](tclock_backend/README.md) | TCLock ports, compatibility contexts and upstream provenance |
| [workload_modules](workload_modules/README.md) | Separate spin and mutex kernel payloads |
| [bench](bench/README.md) | Clients, measurement instructions and performance evidence |
| [tests](tests/README.md) | Targeted verification entry points and evidence |
| [kernel_baseline](kernel_baseline/README.md) | Captured guest kernel configuration, interfaces and identity |
| [kernel_experiments](kernel_experiments/README.md) | Separately authorized historical kernel experiments |

Development, builds and execution target x86_64 only. Use the recovery guest
and the documented [operations procedure](docs/AGENTS.md); build/test commands
are maintained in the relevant directory guides. JIT is not a security sandbox:
[admission limits](docs/design/admission.md), [lifetime boundaries](docs/design/lifetimes.md)
and [deferred work](docs/TODO.md#delivery-scope) remain explicit.
