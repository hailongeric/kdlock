# Source epochs and executable-image ownership

The compiler constructs assembly and exact metadata; the GNU host builder links
machine bytes at the real reserved code address. Neither creates a source lease
or publication authority. Concrete kernel provider/loader/control sources supply
those duties through `c6becf81`. Source, focused host construction, target build,
publication and kernel execution remain separate evidence.

## Source retention

[source_epoch.h](../source_epoch.h) defines the actual `kd_jit_source_epoch`
object named by an exported image. Its constructor receives an already-owned
coherent immutable source lease, exact version bytes, retained byte regions at
actual load addresses, configuration/load identities, the baked current-task GS
offset and a complete provider release callback. Success transfers that lease;
failure leaves its release with the caller. Numeric ranges and overlapping-byte
checks validate supplied input consistency, not live text or a mutation freeze.

Exact BUILD, IMAGE, FEEDBACK and NATIVE memberships retain the epoch
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
The descriptor also names an external durable feedback-producer object, and a
C emission receipt binds exact observation outcomes to those actual inputs.
All generated symbols participate in identifier/collision checks and appear in
the construction manifest. These records are neither source holds nor ACKs.

[image_owner.h](../image_owner.h) binds that descriptor/sidecar to a live BUILD
membership and an already-owned executable-provider hold. It validates actual
epoch identity, version, configuration/load incarnation, GS input, ABI sizes,
source maps and retained bytes. Source addresses are baked numeric inputs;
ordinary module relocation cannot repair a different source incarnation. These
checks do not prove generated-code equivalence or executable permissions. On
success, the owner derives one epoch IMAGE membership, retains an exact producer
IMAGE user and takes code-release ownership. Initialize that producer first
from the same descriptor and live BUILD, with a fresh per-construction identity.
Its control/identity backing is independent of executable payload. The initial
[compiled-image provider](../compiled_image.h) reserves real execmem RW/NX
storage and typed tables before host construction. It installs exact bytes once,
validates flat metadata/source inputs and completes RO/X before publication. Its
code-release callback follows actual owner drain; late facts retain producer
controls rather than code. The [control guide](CONTROL.md) describes the concrete
provider/transport workflow, not a generated-code equivalence result.

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
then drops its producer IMAGE user and exact epoch IMAGE membership. It reads no descriptor/code payload
after code release, and no owner after the final source put. Active owner/header,
source-use and callback backing are independently retained through return.

## Feedback records and compiler inputs

[feedback.h](../feedback.h) supplies a caller-sized preallocated fact pool. Its
nonzero `pool->capacity` is the actual supplied array count; there is no default
or configured deployment count in this tree. The supported workload guarantees
available storage for every reached coverage miss, including nonobservations,
uncovered facts, concurrent claims and late facts. Pending records are never
overwritten, and pending feedback or compilation does not close JIT/delegation
admission. Existing source, context and image-slot checks still apply. This is a
finite workload assumption, not a claim of unlimited storage or measured sizing.

The episode records each coverage miss once before nested operation handling,
forward CALL staging or exit consumption. It copies kind, detail, source site,
resolved target, current cursor, phase and entry result, plus exact source epoch,
version and producer/image identities. Known mutex entry targets are SOURCE_API;
an explicit pure target-classification callback identifies ordinary source or
leaves it unclassified. A resolver's NONE result alone proves no ordinary target.
Normal source-operation, special and resource exits are not miss-pool records.
The synchronous diagnostic report remains separate and confers no retention.

Every fact retains exact source FEEDBACK and durable producer FACT memberships.
The producer has a separate epoch hold, and refuses close while any image-owner
IMAGE user remains. After actual code retirement, FACT users can retain producer
metadata and source without keeping old executable code or slot users alive.
Producer close does not settle pending facts. Release requires all producer users
to end, then drops its source hold; control backing remains retained through return.

A fact key consists of its storage identity and exact 64-bit incarnation. Each
reservation advances that incarnation without wrap in the supported workload;
the sequence supplies identity only, never ownership or an activity estimate.
Transport maps that pair, the exact epoch and per-construction producer to the
matching retained compiler objects. Raw addresses or equal version bytes alone
are insufficient. The fd channel, little-endian wire codec and host session now
implement the retained identity mapping. Archive durability is not general
crash/restart reconstruction.

A caller-preallocated claim freezes a bounded FIFO selection of currently
unclaimed facts from one exact epoch. The claim, immutable item array, holders and
source/producer backing remain retained through compiler, publication and all
transport observers. Later facts stay pending. The host
[learning coordinator](../../disassem/learning.py) validates the exact producing
construction with [the copied-exit adapter](../../disassem/feedback.py), retains
every disposition and merges valid same-version ordinary indirect observations
into cumulative `SourceSnapshot` input before compile/lower/export. Input merge,
planner attachment and actual emitted coverage remain separate results. Host
record/claim/candidate/publication/ACK limits are explicit finite caller inputs.
A completed candidate freezes its included claim members and construction receipt;
facts arriving while construction runs do not become part of that candidate.

## Publication-bound acknowledgement

[feedback_publish.h](../feedback_publish.h) binds exact included claim members,
a live candidate owner user and the generated C emission receipt to the actual
CLOSING image transaction. Its included selection contains only host-adapter
validated facts merged into that candidate input; other claimed dispositions
remain pending even if an unrelated input has the same source/target pair.
Complete source discovery, cumulative merging,
construction, loading and input validation while the old slot is still OPEN;
only then begin the selected drain/swap/grace replacement protocol above.
The receipt and its backing must belong to that actual candidate's retained code
provider; pointer comparisons alone cannot establish this relationship.

After successful `kd_jit_image_update_try_commit`, pass its actual returned old
pointer to `kd_jit_feedback_publication_commit`. The bridge checks the same slot,
update, owner, expected old, candidate and completed transaction after grace.
This produces an immutable publication receipt and performs no ACK. A distinct
`kd_jit_feedback_publication_ack` marks only the exact included ordinary CALL/JMP
facts present as EMITTED in the candidate receipt, then returns its exact subset
in a separate ACK receipt. Empty-old publication is valid; removal to NULL has
no emitted-coverage ACK. Abort requires that exact ABORTED transaction and ACKs
nothing. Host publication recording and confirmation of the actual kernel ACK
remain separate operations; construction or publication alone cannot clear facts.

The caller serializes the ticket with claim end, candidate put, slot-owner
binding/retirement and all later slot updates. ACK scratch is explicit caller
storage, disjoint from immutable inputs. Later, uncovered and nonobservation
facts remain pending. After all compiler, ticket and transport observers end,
`claim_end` unclaims pending facts and releases acknowledged records outside the
pool guard. It can make individual records reusable before returning. If an end
operation fails, only retrying end is legal: earlier items may already have been
unclaimed or reused. No old record access follows its final publication as free.

Nonobservations and uncovered misses have no normal discard/reset path and
remain included in finite capacity. The implemented shutdown closes admission,
retires images to NULL through exact drain/grace and ends native/JIT/BUILD users.
The host then writes a fresh bounded archive with exclusive creation, file fsync
and parent-directory fsync before returning its actual 32-byte content digest.
Kernel SETTLED requires that receipt, exact claim keys/incarnations, CLOSED epoch
with only FEEDBACK users and closed producers without IMAGE users. It is separate
from coverage ACK; END later releases settled records after observers finish.

Runtime retains an independent controller FEEDBACK user until final channel/source
access, protecting exported descriptions after BUILD drop and final FACT release.
Code can retire before late facts, while durable producer/control identities stay
retained. Provider destruction follows exact final users, not timeout or fd close.
The caller still satisfies the all-dependency immutable-text contract: complete
module residency and nofault byte copies do not freeze tracing, probes, alternatives,
static-call/branch changes or live replacement. Every mutator is excluded from
before capture through final native/JIT/feedback use. Configuration/load/version
and actual GS offset remain explicit. Target/context execution needs separate
receipts; focused host checks establish no kernel retirement proof.
