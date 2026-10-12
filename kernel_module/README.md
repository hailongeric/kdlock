# KD kernel provider

This module implements KD spinlocks, mutexes and rwlocks. It also exposes
`/dev/kd_dev` for translation requests and code uploads. Builds require the recorded
`kdclobber2` spin and mutex clobber-v1 interfaces and fail if either is missing.
Loading the module does not redirect ordinary Linux lock calls.
[Lock protocols](../docs/design/lock_protocols.md) and
[the code map](../docs/CODE_MAP.md) define behavior and source responsibilities.

## Build

Build only in the verified recovery guest:

```sh
make -C kernel_module KDIR=/root/linux-6.1.159-kdclobber2 W=1 UBSAN_SANITIZE=n
```

The benchmark builds a separate copy of the provider with measurement counters
and defaults to UBSAN disabled. A standalone build follows the kernel's sanitizer
policy unless overridden, as in the command above. Keep the kernel, mitigations and
frame-pointer settings fixed. Known objtool warnings come from stack switching
and restoration; inspect the built instructions instead of hiding the warnings
or replacing the trampoline.

For selected internal regression checks, use a separate SELFTEST build after the
previous session has drained:

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
| [kd_rwlock.h](../include/kd_rwlock.h) and `spin/{direct,combiner,execute,restore}.inc` | Reader/count protocol and ABI3 writer admission, refusal/retry and completion over the spin backend |
| `spin/ticket_*.inc` via [kd_spin_entry.c](kd_spin_entry.c) | Exact acquisition generation, root borrowing and final retirement |
| [mutex](mutex/) via [kd_mutex.c](kd_mutex.c) | Original mutex acquisition, shadow queue, terminal batch, pinned waiter and restore |
| [lock](lock/) via [kd_lock.c](kd_lock.c) | Direct/bridge mutex routes and nested spin/mutex control CALLs |
| [execution](execution/) | Registry, wrapper preparation, frame/ledger, control/services, native and remote ACK |
| [kd_source.c](kd_source.c), [sys.c](sys.c) | Text pins, device session, capabilities, publication and retirement |
| [kd_hotlock.c](kd_hotlock.c) | Exact-address per-type tables and approximate sampling |
| [kd_mutex_tasks.c](kd_mutex_tasks.c) | Exact task/acquisition refs and RCU lifetime |
| [kd_main.c](kd_main.c) | Setup, rollback and drained shutdown |

Private `.inc` files are fragments included into their parent translation unit.
This preserves static state, declaration order, GCC attributes and stack-switch
labels. Do not compile them as separate Kbuild objects or expose their internal
symbols. Kbuild tracks the includes, and source snapshots or provider copies must
include those files too. Shared APIs live in [include](../include/README.md).

## Current settings

| Setting | Default and meaning |
| --- | --- |
| `KDLOCK_NUMA` build variable | 1; spin/mutex local grouping and CPU-node stack allocation |
| `KDLOCK_SPIN_BATCH` build variable | 1024, allowed 1..1024 bodies; separate scan budget uses the same initial value |
| Mutex batch | Uses `KDLOCK_SPIN_BATCH` (default 1,024) with bounded NUMA selection and remote-cohort handoff |
| `spin_delegate` | Enabled; false selects native KD spin/rwlock-writer self-execution |
| `spin_prefetch` | 2; producer hints. Modes 0/1 select off/consumer lookup |
| `spin_entry_ratio_limit` | 2; 0 disables only the ratio filter |
| `mutex_entry_ratio_limit` | 256; read-only power of two from 2 through 256, exclusive `(entries >> 10)` bound per 1,024 failed native attempts |
| `mutex_native_route` | False; read-only diagnostic control routing new mutex acquisitions natively after admission sampling |
| `hotlock_stats` | Optional final approximate observation totals |
| `target_process` | Task comm eligible for direct mutex delegation |
| `mutex_spin_limit` | 4096 PAUSE iterations before sleeping; 0 parks immediately, maximum 1048576 |
| `mutex_wait_stats` | Read-only observations: result schedule calls, successful wakes, gate wait calls |

Blocking result waits recheck completion after one jiffy if their batched wake
has not arrived. This permits a completed caller to make progress while a later
translated body delays the flush. Gate waits use ordinary wait-queue notification.

KD mutexes always use bounded polling followed by uninterruptible sleep; load
with `insmod kdlock_km.ko`. The `mutex_blocking` selector has been removed.
The original Linux mutex retains its real owner. Published waiters retain their
reserved stack and migration pin while sleeping; translations that require
origin-CPU GS storage are refused. See the [mutex runner](../bench/tclock_compare/README.md)
for benchmark commands and the implementation guide for wake ordering.

[Execution flow](../docs/JIT_EXECUTION.md#heat-and-roles) owns full heat rules;
[spin](../docs/design/spin_implementation.md) owns layout/prefetch/batch details;
[mutex](../docs/design/mutex_implementation.md) owns its separate storage and owner
protocol. [Rwlocks](../docs/design/rwlock_implementation.md) reuse the spin settings,
source leases and request storage. Their ABI3 prelude and exact native writer
references require no new kernel backend or kernel rebuild. Approximate
observation never controls final lifetime.

## Validation and shutdown

Use [tests](../tests/README.md) for basic and affected checks; performance can run
directly through the [spin/mutex](../bench/tclock_compare/README.md) or
[rwlock](../bench/rwlock_compare/README.md) comparison. Do not turn
source organization changes into an automatic full matrix.

Stop new calls and wait for workers and translators to finish. Retire sources,
then unload workloads, then the provider. If retirement returns EBUSY, keep the
pins and investigate the remaining users; never force unload. NORMAL means code
was published, not that JIT ran. Frames, physical owners, unlock ACKs and source
pins have separate lifetimes, as explained in [operations](../docs/AGENTS.md).
