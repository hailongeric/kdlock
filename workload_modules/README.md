# Explicit kernel workloads

These payloads supply stage 1 lock/API experiments and supporting stage 2 MM
checks in the [project roadmap](../docs/ROADMAP.md). Actual kernel replacement
must be established by the integration and its real callers; a module-owned
object or extracted API body alone cannot close the stage 3 coverage requirement.

The active API port targets Ubuntu `linux=7.0.0-38.38`; Linux 6.1 results remain
historical. The new kernel has its own
[source/configuration identity](../kernel_integration/linux70/README.md).
The retained VM compilation matrix covers 97 provider, payload and support-module
configurations across its recorded initial and focused retry inputs. Archived
source provenance is incomplete after user-directed cleanup. Compilation
and live correctness are separate gates; this matrix does not validate workload
execution, drain or performance. A separate eight-session Native/TCLock
cacheline check passed data and normal drain for spin, mutex, rwlock and rwsem;
other API/payload configurations retain their own live gates. No previous timing
result establishes Linux 7 support. See the [port record](../bench/results/10.176.26.71/tests/linux70-port-20261027/README.md)
for the exact cases, failures, retries and remaining gates.

KD mutex workloads own [KD-only objects](../docs/design/kd_only_mutex.md).
Their Linux Native and TCLock controls keep separate object types. The real-API
adapter uses a private KD mutex around the controlled subsystem body; the running
kernel itself has not been rebuilt to replace every mutex.

JIT means just-in-time compilation: KD generates code for a lock holder to
execute a waiting task's protected operation. Additional implementation and
measurement terms are defined in the [terminology guide](../docs/TERMINOLOGY.md).

This directory contains benchmark kernel payloads and payloads shared by
benchmarks and correctness checks. Correctness-only modules live beside their
runners under [tests/kernel](../tests/kernel/README.md), in `fixture/` subdirectories.
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
| [real_api](../bench/real_api/README.md) | `real_api.ko` / scoped ftrace substitution | Real syscall critical sections: xattr rb-tree reads, OFD locks, descriptor flags, pipe mutexes, file-position mutexes and bounded UTS reader/writer metadata; Native/TCLock/KD selection |

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

Linux 7 xattr queries use [xattr.c](real_api/xattr.c), preserving the native
`simple_xattr_get` rb-tree lookup and shared-read behavior. Every matched arm uses
a private, correctly typed rwlock around an immutable tree pinned by a held file
reference. This `xattr-rbtree-read-v1` workload executes readers locally and records
`NO_JIT`; it has no delegation entry or helper-learning phase. Its front/tail
labels select keys, not list positions. It must not be pooled with the retired
list/spin xattr measurements. The controller joins all workers, checks readers
and gates drained, removes the hook and only then releases the pinned file.

Lock behavior is documented in [nine protocols](../docs/design/lock_protocols.md)
and the [spin](../docs/design/spin_implementation.md),
[mutex](../docs/design/mutex_implementation.md) and [rwlock](../docs/design/rwlock_implementation.md)
implementation guides. Measurement commands and results belong in the runner README.

## Synthetic benchmark payloads

Module names identify the lock shells; `*_cacheline` modules also support hash
bodies. The full [workload catalog](../docs/BENCHMARK_WORKLOADS.md)
defines configurations; [benchmark runners](../bench/README.md) own commands and
measurement policy.

| Payload | Implementation | Module shells |
| --- | --- | --- |
| Cacheline updates (1 or 8 lines) | [spin payload](spin_cacheline/body.h), [reader/writer payload](rwlock_bench/body.h) | `spin_cacheline`, `mutex_cacheline`, `rwlock_bench` |
| Nano counter updates (1 or 16 lines, post256) | [Reader/writer payload](rwlock_bench/body.h) | `rwlock_bench` with mutex, rwlock or rwsem shell |
| RCUHT hash operations | [hash_body.h](spin_cacheline/hash_body.h) | All three shells; reader/writer variants add read lookups |

The active catalog selects micro cacheline/RCUHT bodies for spin, rwlock and
rwsem. Mutex micro c01/c08/RCUHT bodies remain available to historical probes;
current mutex comparisons select the two nano profiles and retained API workloads.

`rwlock_bench` selects rwlock, spin or rwsem shells where supported. Shared
[latency instrumentation](latency/operation_latency.h) is not a separate workload.
The [mmap fault](../bench/mmap_fault/README.md) and
[mmap writer](../bench/mmap_writer/README.md) modules also remain here because
both correctness and timing runners consume them.
