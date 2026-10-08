# KD kernel provider

The provider exposes explicit spin/mutex APIs and `/dev/kd_dev` translation
services. It requires the captured `kdclobber2` spin and mutex clobber-v1 interfaces;
missing interfaces fail compilation. Loading it does not install global hooks.
[Lock protocols](../docs/design/lock_protocols.md) and
[the code map](../docs/CODE_MAP.md) define behavior and source responsibilities.

## Build

Build only in the verified recovery guest:

```sh
make -C kernel_module KDIR=/root/linux-6.1.159-kdclobber2 W=1 UBSAN_SANITIZE=n
```

The benchmark prepares a private provider with observation code and defaults to
UBSAN off. A standalone build inherits kernel policy unless explicitly overridden
as above. The existing kernel, mitigations and frame-pointer configuration stay fixed.
Stack-switch/restore objtool warnings are known; inspect actual machine code rather
than suppressing them or replacing the trampoline.

For selected internal regressions, use a separate drained build:

```sh
make -C kernel_module KDIR=/root/linux-6.1.159-kdclobber2 \
  W=1 UBSAN_SANITIZE=n KDLOCK_SELFTEST=1
```

SELFTEST-only probes are absent from normal builds. Never replace a loaded module's
inputs; stop callers, retire sources and unload before changing builds.

## Source organization

`kd_spin_runtime.c` includes `kd_exec.c`, `exe.c`, `kd_spinlock.c`, then `kd_mutex.c`
in declaration order. This keeps simple execution helpers visible for inlining;
Kbuild links only the combined object, not those four files again. Their source
boundaries remain separate for reading.

| Component | Responsibility |
| --- | --- |
| [spin](spin/) | Direct entry, native pending/MCS, NUMA queue, batch, prefetch, stable request, restore and unlock |
| `spin/ticket_*.inc` via [kd_spin_entry.c](kd_spin_entry.c) | Exact acquisition generation, root borrowing and final retirement |
| [mutex](mutex/) via [kd_mutex.c](kd_mutex.c) | Original mutex acquisition, shadow queue, terminal batch, pinned waiter and restore |
| [lock](lock/) via [kd_lock.c](kd_lock.c) | Direct/bridge mutex routes and nested spin/mutex control CALLs |
| [execution](execution/) | Registry, wrapper preparation, frame/ledger, control/services, native and remote ACK |
| [kd_source.c](kd_source.c), [sys.c](sys.c) | Text pins, device session, capabilities, publication and retirement |
| [kd_hotlock.c](kd_hotlock.c) | Exact-address per-type tables and approximate sampling |
| [kd_mutex_tasks.c](kd_mutex_tasks.c) | Exact task/acquisition refs and RCU lifetime |
| [kd_main.c](kd_main.c) | Setup, rollback and drained shutdown |

Private `.inc` files preserve one translation unit, static state, declaration
order, GCC attributes and stack-switch labels. Do not add them as Kbuild objects
or expose internal symbols. Kbuild tracks includes; snapshots/provider copies must
freeze them. Cross-unit APIs live in [include](../include/README.md).

## Current settings

| Setting | Default and meaning |
| --- | --- |
| `KDLOCK_NUMA` build variable | 1; spin local grouping and CPU-node stack allocation |
| `KDLOCK_SPIN_BATCH` build variable | 1024, allowed 1..1024 bodies; separate scan budget uses the same initial value |
| Mutex batch | Fixed 1,024 bodies, FIFO; rejected NUMA grouping is absent |
| `spin_delegate` | Enabled; false selects native KD self-execution |
| `spin_prefetch` | 2; producer hints. Modes 0/1 select off/consumer lookup |
| `spin_entry_ratio_limit` | 2; 0 disables only the ratio filter |
| `hotlock_stats` | Optional final approximate observation totals |
| `target_process` | Task comm eligible for direct mutex delegation |

[Execution flow](../docs/JIT_EXECUTION.md#heat-and-roles) owns full heat rules;
[spin](../docs/design/spin_implementation.md) owns layout/prefetch/batch details;
[mutex](../docs/design/mutex_implementation.md) owns its separate storage and owner
protocol. Approximate observation never controls final lifetime.

## Validation and shutdown

Use [tests](../tests/README.md) for basic and affected checks; performance can run
directly through [the benchmark](../bench/tclock_compare/README.md). Do not turn
source organization changes into an automatic full matrix.

Stop new calls and wait for workers/translators. Retire sources successfully before
unloading workloads, then unload the provider. EBUSY means keep pins and diagnose;
never force unload. NORMAL is publication, not actual JIT. Shared packet/frame,
physical owner, final ACK and source retirement remain separate boundaries under
[operations](../docs/AGENTS.md).
