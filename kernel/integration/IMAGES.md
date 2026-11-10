# Source epochs and executable-image ownership

The compiler constructs assembly, C descriptors and construction metadata; it
does not acquire a live source lease, executable storage or publication rights.
The kernel components below keep those responsibilities explicit. They are
source-reviewed interfaces, with no new assembly, build or execution evidence.

## Source retention

[source_epoch.h](../source_epoch.h) defines the actual `kd_jit_source_epoch`
object named by an exported image. Its constructor receives an already-owned
coherent immutable source lease, exact version bytes, retained byte regions at
actual load addresses, configuration/load identities, the baked current-task GS
offset and a complete provider release callback. Success transfers that lease;
failure leaves its release with the caller. Numeric ranges and overlapping-byte
checks validate supplied input consistency, not live text or a mutation freeze.

Caller-preallocated BUILD, IMAGE and FEEDBACK memberships retain the epoch
independently of image-slot execution users. Build and feedback work can therefore
retain source/version information without preventing old image-slot drain.
Acquire each dependency before dropping its parent. An admitted same-epoch child
can extend retention while closed; this grants no new execution or publication
admission. A put invokes no provider callback. A serialized sleepable finalizer
claims release only after closure and an empty exact user list, calls the cached
provider outside the guard, then accesses neither epoch nor payload again.
RELEASE_CLAIMED alone proves no callback completion; successful return does.

Epoch closure denies new direct retention memberships. It does not close image
lookup or freeze source text. Before mutation/unload, the provider must stop
relevant build/publication admission, close/remove published images, drain their
execution/return/source users and old RCU lookups, and discharge every independent
native suffix/return hold. A module residency reference alone does not prevent
in-place text changes. Native source invocation lifetime cannot be inferred from
an image's grant ending. Epoch header, active callback code and finalizer backing
remain separately retained through the finalizer's actual return.

## Construction inputs and code holds

[artifact.py](../../disassem/artifact.py) keeps generated assembly unchanged and
emits a C `kd_jit_image_inputs` beside its actual descriptor. The sidecar records
that descriptor pointer, exact UTF-8 version bytes without a synthetic NUL, the
baked GS offset and raw bytes for every retained decoded instruction. The source
site table keeps each IP, next IP and source kind. Empty tables remain explicit.
All generated symbols participate in identifier/collision checks and appear in
the construction manifest. These records are neither source holds nor ACKs.

[image_owner.h](../image_owner.h) binds that descriptor/sidecar to a live BUILD
membership and an already-owned executable-provider hold. It validates actual
epoch identity, version, configuration/load incarnation, GS input, ABI sizes,
source maps and retained bytes. Source addresses are baked numeric inputs;
ordinary module relocation cannot repair a different source incarnation. These
checks do not prove generated-code equivalence or executable permissions. On
success, the owner derives one epoch IMAGE membership and takes code-release
ownership. The actual allocator/module/transport remains the provider's choice.

The owner has exact EXTERNAL, BASELINE and PUBLISHED_SLOT memberships, distinct
from a slot's execution users. Puts never invoke code release. A private candidate
can be cancelled only before publication; cancellation cannot replace retirement.
An owner close denies new direct memberships and supplies no execution-admission
closure. The code provider, owner control, callbacks and all observer backing
survive their exact last accesses.

## Publication and retirement sequence

The publisher serializes each slot's publication, binding and retiring APIs.
An initially empty slot can use the transaction below with a NULL baseline.
Alternatively, initializing a private slot with a non-NULL image requires its
EXTERNAL hold before `kd_jit_image_slot_init`, followed by the same live-parent
`kd_jit_image_owner_slot_get` bridge before dropping that hold or updating it.

1. Retain a non-NULL candidate with an EXTERNAL owner membership before exposing
   its pointer. Retain a non-NULL old descriptor from baseline observation through
   successful `kd_jit_image_update_begin`. A BASELINE owner membership is one
   route; an existing exact published-slot hold also retains its descriptor.
2. Begin the exact expected-old transaction. It closes new root lookup while
   allowing already-admitted image dependencies to finish. For a non-NULL old
   image, bind its PUBLISHED_SLOT membership to that same CLOSING transaction
   and owner identity. An empty baseline has no old owner membership.
3. Commit only after the slot's exact users drain. The existing transaction swaps
   the pointer and completes an old-reader RCU grace before returning the actual
   retired pointer. A NULL candidate retires the last image to empty; NULL to NULL
   is refused. An empty slot can decline proxy eligibility through the normal
   persistent local request path.
4. For a non-NULL candidate, derive its PUBLISHED_SLOT membership from its live
   EXTERNAL parent before dropping that parent or starting another update. This bridges the
   publication-to-binding interval, even if retention closure happened meanwhile.
   Bind every slot separately when one descriptor is used in several slots.
   Final removal to NULL has no candidate owner or new slot membership.
5. For a non-NULL old image, finish its membership with the exact prepared
   transaction, owner, slot and actual returned retired pointer. A saved expected-old address or phase alone
   is insufficient. End every baseline/descriptor observer before its final put.
   Complete every applicable candidate binding and old retirement before any
   later update or transaction reuse.

An abort before publication preserves the old pointer. Clear only the exact
ABORTED retiring binding when an old image exists, retain that published
membership, and separately cancel a non-NULL candidate if it was never published.
No rollback is possible after pointer publication. A publisher holding a SOURCE member in the image slot must
drop it after successful begin and before commit, so it does not prevent its own
drain. Epoch BUILD/FEEDBACK users and owner BASELINE users are outside that list.

After all published-slot and external/baseline memberships end, a closed owner's
serialized finalizer releases the cached code-provider hold outside its guard,
then puts its exact epoch IMAGE membership. It reads no descriptor/code payload
after code release, and no owner after the final source put. Active owner/header,
source-use and callback backing are independently retained through return.

The new feedback adapter classifies copied exit scalars against the exact
producing construction and retained epoch version. Only a matching ordinary
indirect CALL/JMP yields compiler input. Source boundaries, consumed returns,
frontiers and mismatches retain their distinct dispositions. This supplies no
transport, ledger, capacity/saturation, late-report, persistence/reset or runtime
ACK policy. Successful publication still needs an exact binding to the emitted
construction receipt before any observations can be acknowledged.

Actual coherent lease acquisition, source-mutation admission, executable storage,
transport, publisher orchestration and feedback policy remain integration work.
No control record or version comparison substitutes for those provider duties.
