# Source, lock and hook lifetimes

Correct locking does not by itself make memory safe to free or a module safe to
unload. A caller can finish its body while another executor still needs its frame,
source code or containing lock object. This guide separates those lifetimes.
Start with the [design overview](../DESIGN.md); [tests](../../tests/README.md)
records validation for specific source versions.

### 3.1 Source, Lock And Hook Lifetimes

The table shows what the current references protect. Keeping the physical mutex
owner is necessary for correct unlock, but does not solve these other lifetimes.
The earlier audit is in [VALIDATION](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#source-and-hook-lifetime-review).

| Resource | What keeps it alive | Limit |
| --- | --- | --- |
| JIT entry and source code | Entries use `(0, RIP)`. Registration, text reads and ordinary call targets pin up to 64 LIVE modules for the session. Retirement invalidates every used entry before dropping those pins. | No concurrent source-code versions or source replacement within a session. Init and unknown source are refused. |
| Generated image | Frames bind an image descriptor independently of their acquisition ticket. Mutex images and ABI1 spin entries that publish checked pointer loads, `strcmp` or `strscpy_pad` retain immutable generations until session teardown. Direct helper images use a separate preallocated pool near kernel text; both pools share 64 descriptors. | Ordinary spin/rwlock descriptors initially refer to in-place code. Binding that descriptor alone does not make its bytes immutable. Image lifetime does not pin source data or lock allocations. |
| Translation session | The daemon, cache and translator children share one writer-open device description. Real kcore reads pin source before inspecting it. | Publishers must follow this path. A pin keeps a module loaded; it does not prove its bytes are unchanged or arbitrary pointers remain valid. |
| Hotlock record | Per-CPU records match exact typed addresses, have bounded capacity and reset their sampling windows without eviction. | Reusing an address does not identify a new allocation. Statistics cannot authorize unlock or request retirement. |
| KD mutex object | The caller owns the 32-byte physical mutex; delegation scheduling uses a separate address-indexed record. | Join callers and drain physical/OSQ/sleeping/delegation queues, ACKs and frames before destroy or reuse. `kd_mutex_is_idle` checks stopped objects; it does not pin storage. |
| Mutex auxiliary record | Exact atomic invocation and gate-owner references retain queue/frame/ACK state. RCU protects lookup until a reference is acquired and defers reclamation after final unlink. | Empty registry membership can precede callback completion. A deferred free never touches the caller object; controlled provider exit drains callbacks with `rcu_barrier()` before slab destruction. This does not replace caller drain. |
| KD spin word and ticket | The caller owns the four-byte word. A stable ticket retains task, CPU and acquisition generation. | There is no separate gate map or second Linux lock. The caller must keep storage alive through every owner and request. |
| KD rwlock count and gate | The caller owns the 128-byte object. Fast native writers hold an exact nondelegated reference; gated writers use spin tickets and frames. | Source pins do not pin lock allocations or reader data. Join all readers and writers before freeing or reinitializing them. |
| Active request | Spin continuations outlive queue-node reuse. Native executors retain root tickets; mutex requests retain exact task acquisition references and owner ACKs. Source/provider leases last through frame removal, once per eligible spin/mutex batch or per generic push. Inactive cached mutex identities retain only task lifetime, with routing disabled. | These references do not pin the containing lock allocation or protect execution before hook entry or after frame removal. |
| Hook provider | Device operations use `.owner=THIS_MODULE`; preserved guest hooks are plain function pointers into KD. | A `/dev/kd_dev` reference does not protect independent readers of lock-hook pointers. |

See [registration](../../kernel_module/exe.c), [hook publication/removal](../../kernel_module/kd_main.c),
[KD physical exclusion](../../kernel_module/kd_mutex_local.c) and
[spin ticket ownership](../../kernel_module/kd_spin_entry.c) for implementation.

Address reuse alone does not prove an exclusion bug: KD still acquires an initialized
spin word or KD physical mutex. However, address-keyed tables cannot distinguish
two allocations at the same address, reset policy for a new allocation, or prove
that old users have finished. Keep storage alive until all of them finish. Even
the final logical ACK for lock A can arrive before the batch physically releases
A, so that ACK alone is not permission to free the containing object.

An idle rwlock gate is also insufficient: fast readers and native fast writers
can be active without holding it. Stop callers, then check the count, gate and exact
acquisition/frame state. An ABI3 body that resumes natively after making progress
keeps writer admission; a refusal before the body starts cancels it before physical
handoff. [Rwlock ownership](rwlock_implementation.md) explains release and retry.

#### Preserved kernel hooks

Global spin dispatch is removed and the mutex installer is disabled. The
following reader limitation applies if the preserved kernel hooks are re-enabled.
The preserved legacy hooks have four plain spin/mutex lock/unlock dispatch
sites; the current kernel adds distinct versioned spin and mutex bridges.
Each calls `is_kd_test()` or `is_kd()` before deciding whether the task is a
target, so non-target kernel tasks are readers too. `exc_int3` also reads the
shared spin predicate before checking the legacy `kd_do_int3` pointer, even
though kdlock does not install that trap callback. Clearing the six lock-hook
pointers and calling `synchronize_rcu()` does not provide these readers with a
matching acquisition/lifetime protocol. Stopping benchmark callers and draining
requests is necessary for current recovery experiments, not proof of generic
hot unload. `rcu_barrier()` for task records solves a different lifetime.

The current guest exports `try_module_get/put` and module notifier registration.
`__module_address/__module_text_address` are not exported in its Module.symvers;
the implementation resolves `__module_address` through existing kallsyms support.
A raw spinlock keeps preemption disabled through lookup and successful reference
acquisition. Such a reference
must span source inspection, publication and any execution/native return using
that source, including learned callees. A pointer lookup or text hash alone
does not pin code or module-owned data. The normal delete-module path sets
GOING, calls the module's `exit()`, then sends the GOING notifier. That notifier
cannot veto an exit that has already destroyed source-owned resources.

Keeping every source pin until KD unloads would create a dependency cycle.
For example, `spin_cacheline.ko` depends on `kdlock_km`. If KD also pins that workload
until its own exit, neither module can unload first. Source retirement breaks the
cycle by releasing source pins before either module exits. Force-unload is not a
substitute. The benchmark's device reference and module dependency protect its
controlled ioctl calls; they do not make arbitrary source reloads or cached images
safe.

#### Device session and source retirement

The device-session prerequisite is now implemented in userspace: one daemon
descriptor spans requests, compilation and publication; only translator children
inherit it, and Python validates the device identity before real text reads.
An orphaned translator retains the same open description. The live cdev probe
checks normal unload refusal at each stage, not reader protection after the last
close. Detailed flow, control commands and direct-CLI restrictions live in
[the daemon guide](../../daemon/README.md#device-session-and-source-residency). Wire structures and the
two-word wrapper ABI are unchanged; source controls are separate ioctls.

`kd_source.c` keeps source resident for the whole session. It does not reclaim
individual image versions. Its lifecycle is:

1. **Pin source before reading it.** Root registration pins LIVE module core text
   before installing metadata. Every real read pins its bounded range before
   kcore inspection, including learned callees and cold code extensions. Kernel
   and module init ranges are refused. Read windows may contain resident data,
   but roots and ordinary native CALL targets must be text. Duplicate dependencies
   share pins. Even after a partial refusal, retain dependencies that an older
   image may still use.
2. **Count admitted work.** Source writers use the source lock. Frame admission
   uses one atomic word with a closed bit and a 32-bit live count. Retirement sets
   the closed bit before inspecting the count. A racing frame therefore either
   takes a counted lease first or is refused. Failure to obtain the module reference
   rolls back the reservation. Frame get/put do not take the source raw spinlock;
   snapshots read the atomic count. Closure stays permanent even if retirement
   returns busy. A spin batch holds one lease through all native/remote child
   removal and batch completion. Legacy and mutex pushes hold per-frame leases,
   including rollback after a failed push. An ordinary CALL miss pins its target
   before native transfer or learning. If that pin fails after progress, execution
   cannot continue or restart from entry.
   For a direct original-helper image, publication pins the original helper and
   each source continuation while holding the device writer lease. The frame or
   batch lease keeps these session references resident throughout the direct
   invocation; the generated helper calls do not repeat source lookups.
3. **Close new work and wait for users.** Retirement serializes with uploads and
   closes new selection and registration. It refuses to finish while source
   writers, frames or known queue/task/origin state remain. Existing task/origin
   routing stays available for owner unlock notifications. During DRAINING,
   already leased reads and targets may finish, but new publication is blocked.
4. **Invalidate entries, then release pins.** Once the caller has stopped new calls
   and all holders have drained, retirement publishes NATIVE_ONLY under the
   registry gate. It drops source references outside the raw lock. RETIRED is
   permanent: slots and images are not reused or reopened. Workload and provider
   modules can then unload in dependency order.

Repeated `kd_exe_add()` calls use a read-only registration check: acquire the
published slot, match PID/RIP/backend/ABI, and observe source OPEN. Spin entries
also require allocated code storage; mutex registration may precede its first
immutable upload.
The initial UNINIT release publishes both immutable metadata and completed root
pinning. UNINIT, miss and terminal native-only entries need no new registration;
they do not become executable by passing this check. An UNUSED slot is only a
lookup candidate and must not count as registered, even if its key is visible.
Misses, backend conflicts and closed admission retain the registration gate and
source checks. A concurrent retire may follow the OPEN observation, but the fast
return only skips redundant work: it reads no source bytes, calls no code and
acquires no execution lease. Readiness and frame admission still gate execution;
pins are released only after invalidation and drain. Slots are never reused
within the session, and controlled module teardown still requires no callers.

#### Executable images and guarded spin transition

An ordinary spin/rwlock entry receives its first descriptor with its allocated
code block. Successful wrapper preparation binds that descriptor to the frame;
refused preparation leaves the frame unchanged. The descriptor and the exact
spin acquisition ticket occupy separate fields and protect different lifetimes.
Ordinary recompilation may still replace that initial block in place.

The first ABI1 image requiring [checked pointer loads](admission.md#checked-spin-pointer-loads),
[`strcmp`](admission.md#original-strcmp-service) or
[`strscpy_pad`](admission.md#original-strscpy_pad-writing-service)
is staged in a separate block and validated before publication. This includes
the [direct original-helper route](admission.md#direct-original-helper-calls).
Each guard's source instruction is pinned and its bytes checked while source admission is
open. Publishing the new descriptor does not overwrite the earlier block or
redirect frames already bound to it. Every subsequent image for that entry uses
another immutable block, even if it no longer requires guards or typed services.
The upload destination is fixed by the first chunk; an older in-place upload
cannot overwrite a newly published immutable image. Old-generation misses cannot
change the current generation's metadata.

An address-guard exit validates its source target again under the active frame's
source lease before native transfer. A dispatcher-based string service validates
ownership and saves the pending CALL's return state before invocation. The direct
route establishes its pristine root ownership once before entry, retains the
source CALL word, then consumes its actual value in generated return handling.
It cannot reenter from a full register packet after leaving that invocation.
The original C caller supplies argument validity and lifetime; publication and execution perform
no helper-specific code, string or buffer checks. A failed address guard disables
the stable entry under the same publication gate that installs images, preventing
a concurrent upload from reenabling delegation.
Already admitted frames keep their own code, exact owners and source references
until retirement. All generations share 64 descriptors and remain allocated until
session teardown; there is no in-session generation reclamation. The original
64-block pool remains in use for ordinary and mutex images. Direct helper images
use up to 64 additional blocks, each 640 KiB, allocated near kernel text so a
generated relative CALL can reach the original helper. This reserves at most
40 MiB of additional memory without increasing the number of published images.
The provider pairs `module_alloc` with `module_memfree` for this pool; the original
pool keeps its existing allocator. Only a private, unpublished upload may return
its block to its own free pool. Registration and uploads refuse descriptor
exhaustion even when either pool still has spare blocks.

Version 11 bit 10 advertises direct-call support only when the startup allocation
is available and the kernel does not require call-depth tracking, which adds
special accounting to CALL instructions that this bridge does not implement.
Without it, eligible string APIs use the existing dispatcher path. Relocation
or source-pin failure also prevents publication; it never rewrites an older
generation. The generated CALL directory describes patch locations and source
continuations, not validated helper instructions. Its lifetime is the immutable
image's lifetime. These rules do not extend immutable publication to
ordinary spin/rwlock entries that have never made this transition.

Source-code pins do not keep arbitrary string allocations alive or stop writers.
The string-service caller must establish both properties under its physical
source lock. Translation models a known 64-byte local destination; the reviewed
caller supplies its validity and lifetime. Both routes retain common ownership
and actual return-word handling; the direct route moves code-residency work to
publication while the dispatcher saves the pending token before each helper.
Exhausted direct quotas and untranslated CALLs retain the original waiter,
physical exclusion and source lease through the native suffix and final unlock
acknowledgement. Neither completion counters nor direct-call totals can release
those references. These obligations preserve the existing ownership and
retirement rules without a new lock API.

The final direct bridge passed [focused VM correctness checks](../VALIDATION.md#taskname-and-xattr-helper-validation),
its separate KD screen and all 18 diagnostic profiles. Those profiles recorded
no source-pin lookup during direct-body measurement: residency was established
before publication, not omitted. The [development record](../../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md#final-diagnostic-profiles)
retains the counts and earlier failures. The separate
[`05876a4` standard-grid comparison](../../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
completed all 567 sessions with validation and drain across its three API
workloads. Archive verification is complete. The separate n129 quota control
also passed: the original waiter finished each quota-limited body and released
its ownership records; generated prefixes were not counted as completed bodies.
The completed version 10 comparison is historical evidence for the
dispatcher path; the selected KD mutex protocol and its source/owner retirement
rules are unchanged.

The source limit is 64 distinct modules, with no hook-time allocation; each
read is limited to 256 KiB. Built-in resident ranges need no module ref. These
checks do not pin arbitrary dynamically freed objects or prove source bytes
unchanged. Idle observations are not a generic hook-reader barrier. A frame's
provider ref also cannot protect the earlier dispatch or code after its pop.

Earlier hook-based multi-frame/source/task live histories remain in
[VALIDATION](../VALIDATION.md). Their workload and launch scripts have been
removed because the current provider does not install those hooks. Stable
request, task/RCU and final-ACK checks remain in production and directed
fixtures; this does not assert fresh live coverage of those old schedules.

Capability assessment under the no-guest-edit default:

- Bounded source pins and terminal metadata retirement are implemented entirely
  in kdlock. They require a real external no-new-callers boundary and are not
  concurrent versioning or automatic subsystem lifetime integration.
- Generic lock allocation/free identity is absent from the lock hooks. An
  arbitrary `kfree()` or embedded-object reuse cannot be inferred from an
  unlock. It needs subsystem lifetime integration or separately approved
  allocation/free interfaces, not owner handoff or a guessed idle timer.
- Generic provider hot unload requires protection before a guest reader
  enters the predicate/callback, coherent hook publication, and draining of
  dispatches plus retained requests. A reference added inside the callback
  cannot protect the earlier jump into it. An unconditional put after the
  hook call is not enough either: `jump_to_saved_regs*()` may bypass that C
  return. Reference release must cover those nonlocal continuations too.
- A future kernel-side design must audit at least the four existing lock
  dispatch sites and the shared `exc_int3` reader, plus registration/drain and
  nonlocal-exit interfaces. That is more than an unverified extra condition;
  no implementation-backed line estimate or approval is claimed here. Actual
  guest-kernel changes for this review: **zero**.

Retain stable lock-allocation lifetimes during a session, retire source pins
explicitly, and use only the controlled recovery procedure in
[AGENTS](../operations/VM.md#drain-and-evidence). Replacing a source module requires a fresh kdlock
and daemon session after draining, not merely a new TGID or clearing daemon
workspaces. This remains an experimental boundary, not safe hot-reload support.
