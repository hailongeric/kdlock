# KD kernel provider

This module implements KD spinlocks, mutexes, rwlocks and sleeping rwsems.
Rwsem readers and ordinary writers run locally; explicit outer writers can
delegate through mutex ABI2 after phase reservation and reader drain. It also exposes
`/dev/kd_dev` for translation requests and code uploads. Builds require the recorded
`kdclobber2` spin-clobber-v1 interface. The KD-only mutex supplies its own object
and clobber entry; it does not require or call the kernel mutex-clobber interface.
All private lock and execution services initialize before `/dev/kd_dev` is
published; teardown removes the device before releasing those services.
Loading the module does not redirect ordinary Linux lock calls.
[Lock protocols](../docs/design/lock_protocols.md) and
[the code map](../docs/CODE_MAP.md) define behavior and source responsibilities.
ABI2 is the machine-level calling agreement used by delegated mutex operations.
JIT means just-in-time compilation, which generates the code used for those
operations. The [terminology guide](../docs/TERMINOLOGY.md) explains other terms
used in this guide.

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
| [spin](spin) | Direct entry, native pending/MCS, NUMA queue, batch, prefetch, stable request, restore and unlock |
| [kd_rwlock.h](../include/kd_rwlock.h) and `spin/{direct,combiner,execute,restore}.inc` | Reader/count protocol and ABI3 writer admission, refusal/retry and completion over the spin backend |
| `spin/ticket_*.inc` via [kd_spin_entry.c](kd_spin_entry.c) | Exact acquisition generation, root borrowing and final retirement |
| [mutex](mutex) via [kd_mutex.c](kd_mutex.c) | Embedded legacy delegation queue, terminal batch, pinned waiter and restore |
| [kd_mutex_local.c](kd_mutex_local.c), [kd_mutex_osq.c](kd_mutex_osq.c) | KD-owned physical exclusion, sleeping callers and private optimistic spinning |
| [kd_rwsem.c](kd_rwsem.c) | Sleeping APIs, ordinary cancellation/downgrade and outer-writer phase admission before the unchanged mutex queue |
| [lock](lock) via [kd_lock.c](kd_lock.c) | Direct KD mutex routes and nested spin/mutex control CALLs |
| [execution](execution) | Registry, wrapper preparation, frame/ledger, control/services, native and remote ACK |
| [execution/images.inc](execution/images.inc) | Immutable mutex and ABI1 guard/service images, direct-call relocation in separate near-text storage, bound generations, stale-miss rejection and permanent delegation refusal |
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
| `KDLOCK_NUMA` build variable | 1; spin local grouping and CPU-node stack allocation |
| `KDLOCK_SPIN_BATCH` build variable | 1024, allowed 1..1024 bodies; separate scan budget uses the same initial value |
| Mutex batch | Fixed 1,024 bodies; accepted bounded NUMA grouping when enabled |
| `spin_delegate` | Enabled; false selects native KD spin/rwlock-writer self-execution |
| `spin_prefetch` | 2; producer hints. Modes 0/1 select off/consumer lookup |
| `spin_entry_ratio_limit` | 2; 0 disables only the ratio filter |
| `hotlock_stats` | Optional final approximate observation totals |
| `target_process` | Task comm eligible for direct mutex delegation |
| `native_escape_count` | Read-only total of validated instruction-exit markers; read after workers finish. It does not establish completion or control admission. |
| `address_guard_count` | Read-only total of validated spin pointer-load exits; read after workers finish. It does not establish body completion, lock ownership or drain. |

[Execution flow](../docs/JIT_EXECUTION.md#heat-and-roles) owns full heat rules;
[spin](../docs/design/spin_implementation.md) owns layout/prefetch/batch details;
[mutex](../docs/design/mutex_implementation.md) owns its separate storage and owner
protocol. [Rwlocks](../docs/design/rwlock_implementation.md) reuse the spin settings,
source leases and request storage. Their ABI3 prelude and exact native writer
references require no new kernel backend or kernel rebuild. Approximate
observation never controls final lifetime.
[Rwsems](../docs/design/rwsem_implementation.md) reuse the mutex protocol and
immutable ABI2 images. Their phase reservations protect reader drain and
ordinary downgrade; they do not change mutex owners, ACKs or frame retirement.

## Conditional instruction exits

Some processor instructions must execute on the task that requested the
operation. For the [reviewed instruction set](../docs/design/admission.md#checked-instruction-exits),
a matching mutex translation can contain a marker: generated code that stops
immediately before the original instruction. An untaken branch to that marker
does not stop delegation. If execution reaches it, the provider preserves the
current registers and resumes the original waiter at that instruction, without
repeating earlier writes.

The current provider advertises capability version 11, retaining the instruction
exit feature introduced in version 6. The translator requires the matching
capability bit and image requirement, which declares what the compiled code needs
from the provider. The existing two-word wrapper interface and ABI2
mutex protocol remain unchanged. The waiter regains arithmetic flags, which
describe calculation results, while retaining its own control flags, which
govern matters such as interrupts and access checks.

Reaching a valid marker changes the operation's registry state to `NATIVE_ONLY`,
meaning delegation is disabled for the rest of that source session. This change
uses the same publication lock as a replacement image, so a concurrent upload
cannot reenable the operation. Already admitted calls keep their original code
and ownership records until they finish. The existing physical owner still
services the waiter's unlock and acknowledges that the release completed.

The [focused live check](../tests/kernel/jit_escape/README.md) verifies both the
untaken and taken branches, resumption on the original task, and subsequent local
execution. Generic translation errors and exhausted execution limits do not use
this recovery path. The [register contract](../docs/JIT_REGISTER_ABI.md#checked-instruction-exit)
describes the exact saved state and validation conditions.

## Checked spin pointer loads

Version 11 retains the checked pointer-load feature introduced in version 7.
A limited ABI1 spin translation may check a pointer load against tracked stack
writes immediately before executing it. A
failed check resumes the original waiter at the same instruction and stack
position, preserves earlier effects and disables delegation for the entry.
The [admission guide](../docs/design/admission.md#checked-spin-pointer-loads)
defines the supported load and required proof that incoming arithmetic flags are
unused by the original remainder. This does not authorize arbitrary address or
fault recovery, nested spin ownership or ABI3 rwlock exits.

Such images publish in separate immutable blocks. Earlier frames retain their
original descriptor and code; all later generations of that entry are immutable
too. Ordinary spin/rwlock entries still use in-place images. The exit retains the
physical owner, acquisition ticket, source lease and required native references
and acknowledgements until normal retirement. The
[focused probe](../tests/kernel/spin/address_guard/run.py) checks those effects;
performance acceptance requires separate workload measurements.

## Original string API services

The contract introduced in version 10 uses the original [`strcmp` service](../docs/design/admission.md#original-strcmp-service)
and [`strscpy_pad` writing service](../docs/design/admission.md#original-strscpy_pad-writing-service)
without helper-specific instruction, CALL-encoding, string or runtime buffer
checks. Feature bit 9 identifies this contract; translation also requires bit 7
for `strcmp` or bit 8 for `strscpy_pad`. Both require ABI1, one outer physical
spin owner and an immutable image.

The selected reviewed caller supplies valid, stable ordinary strings and a
valid destination, as its native API call requires. It also promises not to
inspect or overwrite temporary CALL return storage or discarded helper stack
storage through ordinary data accesses. This additional promise applies only to
those reviewed callers, not arbitrary kernel code. Translation still models
the API's effects: `strscpy_pad(..., 64)` writes all 64 bytes of a known local
destination, including padding or truncation. Ordinary `memcpy` retains its
decoded copy effects and normal return dispatch.

The provider retains common frame, physical-owner and source-lifetime checks.
The dispatcher route reads the pending CALL return word before invoking the
original helper with the original arguments, then consumes that saved return
exactly once. It does not rescan strings or recheck destination bounds. A helper
that has run cannot be retried through native fallback. The admission guides
define the caller obligations and the remaining static memory analysis.

Only `strcmp` has the separate 128-call allowance. `strscpy_pad`, scalar services
and lock controls share the existing 16-call allowance, for at most 144 such
continuations before final unlock. These services preserve the two-word wrapper
ABI, exact owners, source leases and final acknowledgements. The version 10
[focused correctness checks](../docs/VALIDATION.md#taskname-and-xattr-helper-validation)
passed through candidate 6. The
[`88bb5a4` standard-grid comparison](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/README.md)
completed all 567 sessions with validation and drain. KD remains slower than
Linux Native and TCLock at 60 workers in all three measured workloads; taskname
mutation delegation remains unestablished.
The former helper prechecks and their fallback probe remain historical evidence
for `c79d84f`.

Version 11 adds optional capability bit 10 and image requirement bit 4, value 16,
for direct original-helper calls. A generated body can call `strcmp` or
`strscpy_pad` on the executor's stack without a dispatcher round trip per helper.
This is restricted to an immutable ABI1 spin image, a pristine single root with
a MINIMAL packet, and a waiter different from the executor. Its graph cannot
contain address guards, scalar services or nonterminal lock controls. Other
eligible string images retain the dispatcher path. The selected KD mutex
protocol and its allocation path are unchanged.

The provider preallocates a separate pool near kernel text, using `module_alloc`
and its matching `module_memfree`. It reserves up to 64 blocks of 640 KiB, at
most 40 MiB, while sharing the existing 64 image descriptors. A direct CALL uses
a signed 32-bit displacement from its following instruction, so publication must
check that the helper is within reach. Missing allocator support, no usable
startup block or kernel call-depth tracking disables capability bit 10. Later
exhaustion refuses publication rather than overwriting a retained image.

Publication reads the generated `KDNC0001` directory, fills only its private
CALL operands and pins the resolved helper and return-source addresses before
making the image immutable. These checks inspect generated code layout, not
helper instructions, source CALL encodings or arguments. The uploaded image
contains zero operands; publication records alone are not a hash of the loaded
image. Outside timing, the benchmark saves loaded generated bytes and checks
their reconstruction from the upload and independent symbol addresses.

The wrapper preserves its packet pointer and source argument state across each
helper. It retains the real virtual CALL store and reads and consumes that word
once after the helper, requiring the exact allowed return. Previously reserved
wrapper slots hold the remaining 128 comparison and 16 padding-call allowances,
while the executor stack is aligned once at direct entry. Flag-neutral register
operations check quotas and return equality, preserving RCX on every path;
there is no per-call alignment or flags scratch. The private invocation descriptor grows
from 96 to 112 bytes, with completed-call counts at offsets 96 and 104; its old
prefix, two argument words and body witness are unchanged. Counts are consumed
once on return and remain separate from actual dispatcher exits and body
completion evidence.

Quota exhaustion produces FULL exit 10 before the excess helper runs. The
original waiter finishes its pending CALL and native suffix under the existing
owner; the direct image cannot reenter with a full packet and reset the limits.
A successful invocation may reach minimal terminal completion without an
intermediate FULL export. See
[direct-call admission](../docs/design/admission.md#direct-original-helper-calls)
for the complete entry, lifetime and error contracts. The initial route passed
14 focused live sessions. Its later bridge-instruction reduction awaits focused
validation, and the standard worker-grid performance comparison is pending.
Earlier performance results do not measure direct calls.

## Validation and shutdown

Use [tests](../tests/README.md) for basic and affected checks; performance can run
directly through the [spin/mutex](../bench/tclock_compare/README.md) or
[rwlock](../bench/rwlock_compare/README.md) comparison. Do not turn
source organization changes into an automatic full matrix.

Stop new calls and wait for workers and translators to finish. Retire sources,
then unload workloads, then the provider. If retirement returns EBUSY, keep the
pins and investigate the remaining users; never force unload. NORMAL means code
was published, not that JIT ran. Frames, physical owners, unlock ACKs and source
pins have separate lifetimes, as explained in [operations](../docs/operations/VM.md).
