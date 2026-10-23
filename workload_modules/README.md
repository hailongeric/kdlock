# Explicit kernel workloads

KD mutex workloads own [KD-only objects](../docs/design/kd_only_mutex.md).
Their Linux Native and TCLock controls keep separate object types. The real-API
adapter uses a private KD mutex around the controlled subsystem body; the running
kernel itself has not been rebuilt to replace every mutex.

JIT means just-in-time compilation: KD generates code for a lock holder to
execute a waiting task's protected operation. Additional implementation and
measurement terms are defined in the [terminology guide](../docs/TERMINOLOGY.md).

This directory contains benchmark kernel payloads and payloads shared by
benchmarks and correctness checks. Correctness-only modules live beside their
runners under [tests/kernel](../tests/kernel/README.md), in `payload/` subdirectories.
Userspace clients, timing and reports live under
[bench/tclock_compare](../bench/tclock_compare/README.md) and
[bench/rwlock_compare](../bench/rwlock_compare/README.md). Provider-specific
probes remain in [tests/kernel](../tests/kernel). Each backend is selected at
compile time. All participants on a target lock must use that same backend's API.

| Workload | Module / device | Content |
| --- | --- | --- |
| [spin_cacheline](spin_cacheline/README.md) | `spin_cacheline.ko` / `/dev/spin_cacheline` | Native/TCLock/KD spin, cacheline/RCUHT payloads and KD nested/early scenarios |
| [mutex_cacheline](mutex_cacheline/README.md) | `mutex_cacheline.ko` / `/dev/mutex_cacheline` | Separate ordinary mutex functions for the same three arms and shared cacheline/RCUHT payload logic |
| [rwlock_bench](rwlock_bench/README.md) | `rwlock_bench.ko` / `/dev/kd_rwlock_bench` | Native/TCLock/KD rwlock and proc spin snapshots; Native/TCLock/KD rwsem with original TCLock writers and explicit KD outer writers or a local control; separate shell identities |
| [real_api](../bench/real_api/README.md) | `real_api.ko` / scoped ftrace substitution | Real syscall critical sections: xattr/OFD, descriptor flags, pipe mutexes, file-position mutexes and bounded UTS reader/writer metadata; Native/TCLock/KD selection |

The top-level Makefile builds the spin and mutex Linux Native workloads by default; explicit
`spin_cacheline` and `mutex_cacheline` targets build one. Run it only in the
guest with the verified kernel build. Comparison runners build isolated
backend-specific copies with matching symbol dependencies and observer metadata.
The rwlock benchmark has its own Makefile and
[performance runner](../bench/rwlock_compare/README.md). Its separate
[correctness test](../tests/kernel/rwlock/README.md), along with instruction-exit,
address-guard and string-service probes, is managed under `tests/kernel/`.

The old transparent-hook workload is removed; its historical evidence remains
in Git and the validation/report indexes.

Lock behavior is documented in [nine protocols](../docs/design/lock_protocols.md)
and the [spin](../docs/design/spin_implementation.md),
[mutex](../docs/design/mutex_implementation.md) and [rwlock](../docs/design/rwlock_implementation.md)
implementation guides. Measurement commands and results belong in the runner README.

## Synthetic nano-benchmark payloads

Module names identify the lock shells; `*_cacheline` modules also support hash
and list bodies. The full [workload catalog](../docs/BENCHMARK_WORKLOADS.md)
defines configurations; [benchmark runners](../bench/README.md) own commands and
measurement policy.

| Payload | Implementation | Module shells |
| --- | --- | --- |
| Cacheline updates (1 or 8 lines) | [spin payload](spin_cacheline/payload.h), [reader/writer payload](rwlock_bench/payload.h) | `spin_cacheline`, `mutex_cacheline`, `rwlock_bench` |
| RCUHT hash operations | [hash_payload.h](spin_cacheline/hash_payload.h) | All three shells; reader/writer variants add read lookups |
| Resident list (`list`, 16 or 128 nodes) | [list_payload.h](spin_cacheline/list_payload.h) | All three shells |
| Resident list with prefetch (`list-prefetch`) | Same list implementation, selected at build time | All three shells |

`rwlock_bench` selects rwlock, spin or rwsem shells where supported. Shared
[latency instrumentation](latency/operation_latency.h) is not a separate workload.
The [mmap fault](../bench/mmap_fault/README.md) and
[mmap writer](../bench/mmap_writer/README.md) modules also remain here because
both correctness and timing runners consume them.
