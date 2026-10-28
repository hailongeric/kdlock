# Source, lock and hook lifetimes

A completed body does not mean its request, lock allocation or code can be freed.
Physical owners, native executors, source pins, images and frames have separate
retirement obligations. Start with [design](../DESIGN.md) and follow
[ownership](locking.md) and [frames](frames.md) for exact unlock/ACK ordering.

## Resource lifetimes

| Resource | What is retained | Limit |
| --- | --- | --- |
| Source text | Session references to LIVE module core text, including learned callees | Pins do not retain arbitrary data or permit source replacement within a session |
| Image | Frame-bound descriptor; immutable mutex and transitioned spin generations survive until teardown | Binding an ordinary in-place spin/rwlock descriptor does not freeze its bytes |
| Physical acquisition | Exact owner, task/acquisition record or spin ticket | A heat, queue or completion counter is not ownership |
| Active request | Shared frame/packet, native executor references, source lease and unlock ACK obligations | DONE/NATIVE_READY or an idle hint alone is not retirement |
| Mutex node | Preallocated CPU/slot storage with separate OSQ and delegation memberships | One membership cannot overwrite another's links or retire the shared reservation early |
| Lock/data allocation | Caller keeps the containing object live through all users | Source/image pins do not retain that allocation |
| Provider | Device-session references and declared module dependencies | These do not establish arbitrary global-hook hot unload |

Address-keyed registration and heat tables cannot distinguish a new allocation
at the same address. Stop users and complete exact retirement before reuse.
An ACK for one logical release can precede final batch physical release; it is
not permission to free the object. An idle rwlock gate alone also misses fast
readers and ungated writers.

## Device session and source retirement

The daemon, cache and translator children retain one writer-open device session.
Real text reads pin their source before kcore access. Closing a parent does not
invalidate a child still holding the open description. Root registration and
ordinary call targets require resident source; kernel/module init text is not
made a valid long-lived target by the source-trust policy.

The source protocol is:

1. Pin source before text inspection, including cold extensions and learned
   callees. Reuse session references for repeated dependencies; retain anything
   an older image may still use even after a failed compilation.
2. Count admitted frame/batch leases exactly. Retirement sets the closed bit
   before inspecting the live count, so a racing admission either obtains its
   lease first or cannot enter. Failed module-reference acquisition rolls back
   its reservation.
3. Close new selection, registration and publication. Closure is permanent even
   if retirement reports busy. Existing owner/native ACK routes remain usable;
   already leased work may finish during DRAINING.
4. After callers stop/join and all source writers, queues, tasks, owners and
   frames drain, invalidate entries under the registry gate, then release source
   pins outside the raw lock. RETIRED is terminal; do not reopen or reuse slots.

A batch lease spans native/remote child cleanup and frame removal. An ordinary
CALL miss pins its target before native transfer or learning. If that fails after
progress, execution cannot restart at entry to hide it. Shared packet/frame
storage is transferred under explicit lifetime rules rather than copied.

Registration's read-only fast check is not an execution lease. It matches the
entry key/backend/ABI and observes source OPEN; readiness and frame admission
still govern execution. Slots are not recycled within the session.

The [daemon guide](../../daemon/README.md#device-session-and-source-residency)
owns device controls; [kd_source.c](../../kernel_module/kd_source.c) and the
[image code](../../kernel_module/execution/images.inc) implement retirement.

## Executable images and guarded spin transition

Frames bind a descriptor independently of acquisition tickets. Mutex uploads
construct a private immutable generation and publish it once. Old frames retain
that image, and old-generation misses cannot alter current metadata. Every
published generation consumes the shared image capacity until session teardown.

Ordinary spin/rwlock entries initially use an allocated in-place code block.
Supported root instruction-marker images (requirements exactly 33) stage a new
immutable block. The retained checked-address and historical string-image ABIs
also trigger their compatible immutable transition. Once transitioned, all later
generations for that entry remain immutable. Upload destination/generation checks
prevent an old in-place upload from overwriting a new immutable image.

Production trusts source and selects ordinary string CALL/RET; it does not emit
address guards or named string-service/direct-bridge images. The old direct route's
near-text pool, relocation and quota contracts remain
[historical compatibility](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/design/lifetimes.md#executable-images-and-guarded-spin-transition),
not a current translation requirement. Active call-depth policy and configured
near-text-pool restrictions remain in the [Linux 7 port guide](../../kernel_integration/linux70/README.md).

The registry has 511 slots and a shared maximum of 64 image descriptors. The
ordinary pool provides up to 64 blocks of 640 KiB. Optional legacy near-text
storage does not increase the shared descriptor limit. Descriptor exhaustion is
a real preparation failure; an available block alone does not grant publication.

Source pins do not stop concurrent writers to data or retain arbitrary string
allocations. The selected source/caller contract supplies those lifetimes;
production skips their semantic proof. Runtime source, actual return-word,
physical-owner and frame checks remain enforced independently.

## Object and provider teardown

Stop new calls, join users, close source admission and retire all work before
unloading workload/provider code or freeing locks/data. Check local sleepers,
OSQ/delegation memberships, reader counts, writer reservations, owners, ACKs,
source leases and frames. Never replace those records with an approximate balance.
An `EBUSY`, timeout or lost SSH connection is not drain. Retain pins and diagnose;
do not force unload or clear the guest source tree.

The maintained provider installs no whole-kernel lock replacement. Legacy global
hook experiments have separate reader/unload limitations and remain
[historical evidence](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/design/lifetimes.md#preserved-kernel-hooks).
A device reference alone cannot prove arbitrary hook-reader lifetime. Linux 7
MM integration uses its separate built-in local adapter and mm-reference/token
rules; see [MM identity and lifetime](../../kernel_integration/linux70/MMAP.md).

General hot reload, concurrent source versions, arbitrary allocation reuse,
whole-kernel replacement and broad oversubscription remain unvalidated.
