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

`kd_spin_runtime.c` includes `kd_exec.c`, `exe.c`, `kd_spinlock.c`,
then `owned_mutex/delegation.c` in declaration order. This keeps execution helpers
visible for inlining. Kbuild links only the combined object; the five included
files remain separate for reading.

| Component | Responsibility |
| --- | --- |
| [spin](spin/) | Direct entry, native pending/MCS, NUMA queue, batch, prefetch, stable request, restore and unlock |
| [kd_rwlock.h](../include/kd_rwlock.h) and `spin/{direct,combiner,execute,restore}.inc` | Reader/count protocol and ABI3 writer admission, refusal/retry and completion over the spin backend |
| `spin/ticket_*.inc` via [kd_spin_entry.c](kd_spin_entry.c) | Exact acquisition generation, root borrowing and final retirement |
| [owned_mutex](owned_mutex/) | Independent 32-byte object, Linux-derived SELF/OSQ, ABI4 leaf entry and late capture, guarded FIFO and outer-unlock delegation |
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
| `KDLOCK_NUMA` build variable | 1; spin local grouping and CPU-node stack allocation; owned selection uses its separate `owned_mutex_numa` option |
| `KDLOCK_SPIN_BATCH` build variable | 1024, allowed 1..1024 bodies; separate scan budget uses the same initial value |
| Owned mutex batch | Same total body cap; finite FIFO snapshot at explicit outer unlock, stopping at SELF/handoff boundaries |
| `spin_delegate` | Enabled; false selects native KD spin/rwlock-writer self-execution |
| `spin_prefetch` | 2; producer hints. Modes 0/1 select off/consumer lookup |
| `spin_entry_ratio_limit` | 2; 0 disables only the ratio filter |
| `owned_mutex_entry_ratio_limit` | Owned ABI2: independent limit 256 with the same ratio/cadence; ABI4 does not use heat admission |
| `owned_mutex_reuse_spins` | 0; allowed 0/8/32/128, one allowance after observing an unflagged release per optimistic OSQ turn; the measured ABI4 profile selects 32 |
| `owned_mutex_self_route` | False; read-only diagnostic control selecting only KD-owned SELF acquisition |
| `owned_mutex_refill` | False; opt-in further FIFO snapshots within the same cumulative batch cap |
| `owned_mutex_origin_spin` | False; permit the audited bounded origin-GS subset only while an exclusive spinning-origin claim is held |
| `owned_mutex_numa` | False; inspect at most eight delegates and retain four-bypass barriers within the existing batch cap |
| `owned_mutex_preflight_spins`, `owned_mutex_preflight_queue` | 0/false; bounded ABI2 C-preflight experiment, separate from ABI4's unbounded owner optimism |
| `owned_mutex_protocol` | Getter-only identity `linux_local_first_v1`; guarded owner release is mandatory |
| `hotlock_stats` | Optional final approximate observation totals |
| `target_process` | Task comm eligible for direct mutex delegation |
| `owned_mutex_spin_limit` | Delegation-result polling limit 4096; 0 parks immediately, maximum 1048576; does not limit SELF owner optimism |
| `owned_mutex_wait_stats` | Two read-only delegated-result counters: schedule calls and wakes; SELF sleeps are not counted |

Blocking result waits recheck completion after one jiffy if their batched wake
has not arrived. This permits a completed caller to make progress while a later
translated body delays the flush.

KD mutexes support blocking. SELF acquisition uses Linux-style optimistic
spinning and sleeping. Published delegates retain their reserved stack and
migration pin while sleeping after bounded result polling. Audited origin-CPU GS
access requires an exclusive origin-readiness claim; a parked origin is ineligible.
See the [policy contract](../docs/design/mutex_implementation.md#conditional-origin-readiness-and-bounded-numa-selection).

Owned uploads publish immutable image descriptors, binding a frame to one code
generation through completion and native continuations. Spin/rwlock images
retain in-place publication. The
[publication guide](../docs/JIT_EXECUTION.md#owned-image-publication-protocol-2)
defines staging, capability checks, pool exhaustion and teardown.

Caller build option `KD_OWNED_MUTEX_CABI=1` selects ABI4's local acquisition before
late capture. The default remains ABI2 capture-first, with optional
`KD_OWNED_MUTEX_PREFLIGHT=1`. These caller choices are not provider load parameters.
See the [mutex runner](../bench/tclock_compare/README.md#owned-c01-full-grid)
for the explicit measured profile and the implementation guide for wake ordering.
Owned callers now cover all five synthetic cacheline sizes and RCUHT. The
[private pipe/file adapter](../docs/design/mutex_implementation.md#private-pipefile-api-adapter)
also uses ABI4; this workload expansion changes neither the provider algorithm
nor its default policy. [Validation](../docs/VALIDATION.md#expanded-mutex-workload-verification)
records both ABI2/ABI4 synthetic checks and the scoped API checks.

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
[rwlock](../bench/rwlock_compare/README.md) comparison, or the
[scoped syscall/API runner](../bench/real_api/README.md). Do not turn
source organization changes into an automatic full matrix.

Stop new calls and wait for workers and translators to finish. Retire sources,
then unload workloads, then the provider. If retirement returns EBUSY, keep the
pins and investigate the remaining users; never force unload. NORMAL means code
was published, not that JIT ran. Frames, physical owners, unlock ACKs and source
pins have separate lifetimes, as explained in [operations](../docs/AGENTS.md).
