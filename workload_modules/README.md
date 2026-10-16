# Explicit kernel workloads

This directory contains the kernel code exercised by tests and benchmarks.
Userspace clients, timing and reports live under
[bench/tclock_compare](../bench/tclock_compare/README.md) and
[bench/rwlock_compare](../bench/rwlock_compare/README.md). Provider-specific
probes remain in [tests/kernel](../tests/kernel/). Each backend is selected at
compile time. All participants on a target lock must use that same backend's API.

| Workload | Module / device | Content |
| --- | --- | --- |
| [spin_cacheline](spin_cacheline/README.md) | `spin_cacheline.ko` / `/dev/spin_cacheline` | Native/TCLock/KD spin, cacheline/RCUHT payloads and KD nested/early scenarios |
| [mutex_cacheline](mutex_cacheline/README.md) | `mutex_cacheline.ko` / `/dev/mutex_cacheline` | Separate Native/TCLock/KD cacheline and RCUHT functions; KD-owned ABI2 or ABI4 |
| [rwlock](rwlock/README.md) | `rwlock_test.ko` / `/dev/kd_rwlock_test` | Native/KD concurrent readers, exclusive writers and JIT writer correctness |
| [rwlock_bench](rwlock_bench/README.md) | `rwlock_bench.ko` / `/dev/kd_rwlock_bench` | Native/TCLock/KD rwlock performance; default 1%/20% RCUHT mixes and ABI3 JIT writers |
| [real_api](../bench/real_api/README.md) | `real_api.ko` / scoped ftrace substitution | Real syscall critical sections: xattr/OFD, descriptor flags and bounded UTS metadata use Native/TCLock/KD; pipe and file-position mutexes use Native/TCLock |

The top-level Makefile builds the spin and mutex Linux Native workloads by default; explicit
`spin_cacheline` and `mutex_cacheline` targets build one. Run it only in the
guest with the verified kernel build. Comparison runners build isolated
backend-specific copies with matching symbol dependencies and observer metadata.
The rwlock correctness and benchmark workloads have their own Makefiles and
separate [test](../tests/kernel/rwlock/README.md) and
[performance](../bench/rwlock_compare/README.md) runners.
The old transparent-hook workload is removed; its historical evidence remains
in Git and the validation/report indexes.

The [workload guide](../docs/BENCHMARK_WORKLOADS.md) describes the data and
operations protected by each lock. Lock behavior is documented in
[nine protocols](../docs/design/lock_protocols.md)
and the [spin](../docs/design/spin_implementation.md),
[mutex](../docs/design/mutex_implementation.md) and [rwlock](../docs/design/rwlock_implementation.md)
implementation guides. Measurement commands and results belong in the runner README.
