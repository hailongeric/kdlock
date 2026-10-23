# Bounded anonymous munmap bodies

Status: `kdmm21` extends the retained-table empty-PTE (leaf page-table entry)
boundary path so one survivor may share the target leaf table and the other lies
across the 2-MiB PMD
(page-middle-directory) boundary. One prefix/suffix page is removed from a
three-page anonymous VMA (virtual memory area). Both outer-neighbor guards and
the native table-retention calculation remain mandatory. All 69 serial cases,
two basic tests and 2,254 negative receipt controls passed, with 42 new
different-task empty removals across 18 native-matched layouts, plus two queued
conversions to zero and two to private. Twenty-two empty removals held no private
pages. Recovery is restored and modules unloaded. See the
[result record](../../bench/results/10.176.26.71/tests/mm-boundary-shared-empty-20261024/README.md)
and [probe commands](../../tests/kernel/mmap_lock/boundary_shared_empty/README.md).
The [kdmm20 baseline](../../bench/results/10.176.26.71/tests/mm-boundary-shared-zero-20261023/README.md)
retains its separate shared-zero campaign. Eight smokes preserve shared private/zero
and isolated empty paths, with shared missing-table targets still refused.
The [kdmm19 baseline](../../bench/results/10.176.26.71/tests/mm-boundary-shared-20261023/README.md)
retains its separate private-target campaign. Its eight smokes checked private
and isolated zero/missing/empty paths; shared empty/missing targets refused on
that image.
The [kdmm18 baseline](../../bench/results/10.176.26.71/tests/mm-boundary-resident-20261023/README.md)
retains its separate isolated private-target campaign. Eight small smokes check
existing boundary paths and continued refusal of other target classes in the
new geometry; no historical matrix was repeated.
The [kdmm17 baseline](../../bench/results/10.176.26.71/tests/mm-boundary-zero-20261023/README.md)
retains its separate 74-case zero-boundary campaign and reversed empty-target
gap closure; neither was repeated. Five smokes preserve missing/empty/zero
boundary and same-table resident behavior.
The [kdmm16 baseline](../../bench/results/10.176.26.71/tests/mm-boundary-empty-20261023/README.md)
retains its separate 51-case empty-boundary campaign. All six reversed mixed
empty-target layouts passed separately on kdmm17; seven preservation smokes
cover missing/empty boundary and same-table zero behavior without repeating
historical matrices.
The [kdmm15 baseline](../../bench/results/10.176.26.71/tests/mm-boundary-edge-20261023/README.md)
retains its separate 49-case missing-target-table boundary evidence; its matrix
was not repeated. The kdmm16 campaign's four preservation smokes cover both missing-table edges,
the old controlled appearance refusal and same-table empty-entry removal.
The [kdmm14 baseline](../../bench/results/10.176.26.71/tests/mm-missing-table-20261023/README.md)
retains its 42 serial cases, 956 negative controls, 11 same-table missing-target
removals and three controlled table appearances; that campaign was not repeated.
The [kdmm13 milestone](../../bench/results/10.176.26.71/tests/mm-absent-target-20261023/README.md)
retains its 51 cases and 38 absent-target removals; the nine previously untested
reversed mixed layouts passed separately on kdmm14 using the unchanged client.
The [kdmm12 milestone](../../bench/results/10.176.26.71/tests/mm-zero-only-20261023/README.md)
retains its separate completed zero/untouched-only survivor evidence.
The [kdmm11 zero-target milestone](../../bench/results/10.176.26.71/tests/mm-zero-target-20261023/README.md)
retains its separate 15-layout and 32-zero-removal evidence.
The [kdmm10 zero-survivor milestone](../../bench/results/10.176.26.71/tests/mm-zero-partial-20261023/README.md)
retains its separate 44 cases and 31-removal evidence.
The [completed kdmm9 mixed matrix](../../bench/results/10.176.26.71/tests/mm-mixed-matrix-20261023/README.md)
retains all nine resident/untouched combinations and its separate 18-removal proof.
The [initial mixed milestone](../../bench/results/10.176.26.71/tests/mm-mixed-partial-20261023/README.md)
retains its 22 cases, both interior split-error points, missing-target and
zero-page-survivor refusals, and final-page-release evidence.
The [kdmm8 result](../../bench/results/10.176.26.71/tests/mm-resident-partial-20261023/README.md)
retains the fully resident and original split-error evidence.
The [untouched partial baseline](../../bench/results/10.176.26.71/tests/mm-partial-unmap-20261023/README.md)
keeps its separate 45-removal evidence. Performance, p95, the seven mutex
regressions and broad stress remain deferred.

## Reviewed boundary

A virtual memory area (VMA) describes one address range. The first supported
case removes one complete, isolated, private anonymous VMA of at most 16 pages,
with `MADV_NOHUGEPAGE`, no memory-account charge, callback, userfaultfd, memory
policy, name, huge/locked/growing state or reverse-map chain. Writable test VMAs
use `MAP_NORESERVE` to avoid `VM_ACCOUNT`. An MMU notifier is an external consumer
that receives mapping-change callbacks; any notifier subscription is refused.

For the original `kd_mmap_unmap_enable()` opt-in, every top-level
page-directory entry (PGD) covering the range must be
absent. This deliberately restricts the path more than merely checking empty
PTEs (leaf page-table entries). Even an empty lower-level table could require
table-free batching on the combiner. With absent PGDs, the original page-table
and TLB (cached address translation) teardown helpers run, but have no page or
table to release. Populated ranges return to the waiter for native teardown.

The actual `__vm_munmap()` entry submits eligible-range calls. The combiner uses
the shared original `do_mas_align_munmap_prepared()` body: it detaches the VMA
from the maple tree (the mapping index), updates counts, runs `unmap_region()`,
and frees the VMA. The ordinary native route calls the same helper without a
prepared reserve. Success requires a real VMA removal; empty-range success or
local continuation is never counted as a delegated body.

## Untouched partial ranges and VMA splitting

The original unpopulated opt-in now also accepts a proper subrange of one VMA.
The **entire original VMA**, including the retained ranges, must fit within the
opt-in interval, contain at most 16 pages and have absent PGDs and no reverse-map
chain. All common exclusions above still apply. A reverse map connects a
physical page back to its mappings. Splitting a resident anonymous VMA can
allocate new reverse-map links in the executing task's context; those resources
are not prepared by this original opt-in. Resident partial removal still refuses
on it and on the original populated opt-in. The separate resident-partial opt-in
below prepares these resources; it does not raise the resident-page limit.

The originating task allocates two VMA descriptors and separate maple reserves
for up to two splits, in addition to the existing removal reserves. A reserve
is storage allocated before queue publication, when the original caller's
allocation context still applies. Preparation reads only a scalar tree-height
hint; it does not walk an unlocked tree or retain a VMA pointer. It reserves for
two possible height increases, and the owner checks current capacity again under
the actual mmap write lock before changing any mapping.

The native split/adjust helpers accept these prepared objects; ordinary callers
use their original allocation path. Each prepared split inserts the higher
address VMA. This orientation matters: the captured native maple store destroys
its reserve after each store, whereas inserting below could need a second store
and allocate on the executor. The prepared path asserts its single-store
conditions. After one or two splits, the shared native removal body detaches and
frees exactly the requested interval. Retained bounds, flags, page offsets,
map count, mapped-page count and page-table bytes are checked before completion.
No callback or new reverse-map allocation is admitted on the combiner.

All refusal checks precede splitting. After the first split can take effect,
errors are returned as admitted operation errors, never as permission to replay
the original munmap locally. This preserves native partial-progress semantics
without repeating destructive work. A pre-effect refusal uses the existing
exact handback/ACK and sticky local fallback. Consumed descriptor pointers are
cleared when ownership transfers to the native helper; the origin frees unused
descriptors and reserves only after its exact queue node retires. Retirement
receipts bind the descriptor addresses, mm, originating task and range, including
refusal and cancellation.

The `kdmm7` validation removed one page from three-page VMAs in each shape.
Each shape produced 15 different-task completions and retained the expected
zero-filled contents; subsequent writes to surviving ranges also matched.
Interior removal increased map count by one per operation; edge removal left
it unchanged. Two local readers held shares concurrently, and a real later
fault waited for writer release before reporting the removed address absent.
A populated partial removal instead matched its handback/ACK, preserved the
surviving patterned bytes and invalidated the original CPU's cached translation;
the next call stayed local. Queued fatal cancellation left the victim's entire
mapping intact. The [probe guide](../../tests/kernel/mmap_lock/partial_unmap/README.md)
describes the checks and their limits.

## Resident partial removal and post-split errors

`kd_mmap_unmap_resident_partial_enable()` explicitly enables the path under
mmap write ownership. It admits one ordinary, writable, exclusive resident
anonymous 4-KiB target, or a shared-zero/absent target described below, in an
exactly three-page VMA. Each retained slot may be
an ordinary resident page, a validated shared zero page or an absent PTE. The
original exclusions and isolation remain required. For the same-table path,
both neighboring VMAs must remain within the same PMD span; the separate
boundary-edge extension below proves retention across two intervals. A PMD describes
a 2-MiB page-table interval here. Retaining its leaf table avoids allocation for
deferred table freeing on the executor. Private PTEs require exactly one
`anon_vma_chain` link pointing to the active `anon_vma` reverse-map object. With
only zero/empty PTEs, consistently absent metadata is also supported as described
below. Additional ancestry links, missing higher levels and unsupported PTE/page
types hand back.

The native `anon_vma_clone()` allocates a new link when splitting. The caller
now allocates two links, two VMA descriptors and the separate maple reserves
before publication, using its own allocation context. No live VMA or reverse-map
pointer is retained during preparation. For an existing leaf table, under the
actual mmap writer the owner rechecks the current VMA, ancestry, reserve capacity and all three original PTEs
(leaf page-table entries). It takes a temporary reference and tries the lock on
each resident page. References retain their original VMA slot indices; skipping
an untouched survivor never compacts them into a misleading dense prefix.
Absent leaf PTEs and the narrowly recognized shared-zero entries below
acquire no ordinary page reference. A later failure releases exactly the
held private slots before handback. Readers remain concurrent and local until
writer admission closes. Target type and absent or simple reverse-map metadata
are determined again under writer ownership. A valid zero or empty-leaf target may own no pages;
admission success is independent of the private-page count.

With reverse-map metadata present, the prepared clone consumes one supplied link
per split and shares native root locking, interval-tree insertion and active-VMA
accounting. With absent metadata it consumes no link.
Ordinary native callers retain their allocator path. Native split/adjust and
unmap then remove the requested slice. All originally resident pages remain held
through this body; after its TLB (cached address translation) flush, the removed
target's PTE must be empty. A private target's page must have mapcount zero;
zero and empty targets have no owned page. Surviving private PTEs must retain their original
physical pages, untouched survivor PTEs must remain absent, and table bytes must
be unchanged. The executor releases all
temporary page references/locks before completion. Unused prepared links and
descriptors retire on the origin after exact queue-node retirement. Consumed
links belong to the native VMA lifecycle, including later local cleanup.

Per-mm test injection can return `-ENOMEM` immediately after split one or two,
before any mapping removal. The native body and delegated body reach the same
semantic points. Interior split one leaves `[0,1)` and `[1,3)` page ranges;
split two leaves `[0,1)`, `[1,2)` and `[2,3)`. Every page remains mapped and the
harmless splits remain, matching native semantics. These are admitted errors,
not refusals: no sticky fallback or destructive local replay follows. A
pre-effect refusal instead uses the existing exact handback/ACK and sticky-local
protocol. Injection defaults to disabled and is armed only by the test probe.

The `kdmm8` cases compare native/delegated errors for all untouched shapes and
both interior resident split points. The native controls use the ordinary
native munmap body on the same KD lock backend with delegation disabled; they
are not a separate Native-off boot. Successful resident cases prove two remote
removals per shape and one more after dropping test references before execution.
Warm translations on each origin CPU become inaccessible; retained bytes,
VMA/mm accounting, exact page references and reverse-map link ownership match.
A busy third page proves release of two earlier holds before ACK; a subsequent
call stays local. Queued cancellation leaves its mapping intact. Two local
readers overlap, and a real fault on an untouched surviving neighbor waits for
writer release and resolves locally. That fault is not delegated fault evidence.

The `kdmm9` mixed cases add prefix/suffix/interior targets with both survivors
untouched, and interior targets with only the left or right survivor resident.
Ten removals execute on other tasks; a final-release case adds one more. The
probe pins only specified resident slots and independently reads all three
PTEs without faulting them in. Body receipts bind exact resident/untouched masks
to the same mm, request, origin and executor as the physical-page completion.
After writer release, a real fault inside an untouched surviving part of the
original VMA resolves locally to the zero page. Survivors then pass full-page
zero/pattern checks and local writes. The zero page is a shared physical page
mapped by a read fault; it is distinct from an absent PTE and is still refused
if already present during body admission on `kdmm9`. Busy-page,
zero-page-survivor and missing-target cases each release one earlier page hold before their exact
handback/ACK and then demonstrate sticky-local fallback. Sparse references also
retire correctly after either injected interior split error and cancellation.

The complete mixed matrix additionally exercises each edge target with either
the near or far survivor resident. There are nine distinct mixed combinations:
three target positions times three survivor patterns (both absent, only one or
only the other resident); none is deduplicated. Fully resident combinations
remain separately validated by `kdmm8`, with an interior preservation smoke.
For every mixed shape the ordinary native body and three KD calls agree on
normalized VMA bounds, offsets and flags. Two KD calls per shape finish on a
different task. Read-only PTE observations precede survivor reads. Independent
`/proc/self/smaps` walks report RSS (resident set size) and anonymous resident
bytes before removal, after completion and after explicit survivor writes.
These exact per-VMA observations match native behavior without relying on batched
process RSS counters. The intentional competing read fault resolves locally to
the shared zero page only after writer release; other absent slots remain empty
until explicitly read. Local writes then allocate normal writable anonymous
pages. The controller never pins or reads an absent slot before these checks;
the deliberate competing reader's single zero-page fault is recorded separately.

## Shared-zero-page survivors

`kdmm10` extends only retained slots of the resident-partial opt-in. An absent
PTE, a present special shared-zero PTE and an owned private resident page are
three separate states. Under mmap writer ownership and the PTE lock, a zero
survivor must be present, special, read-only, non-device, not protection-none,
and satisfy `is_zero_pfn()`. Other special entries remain refused. Zero targets
were still refused on `kdmm10`; the following extension handles them separately.
Whole-VMA eligibility is unchanged.

The native read-fault path installs a special zero-page PTE. `vm_normal_page()`
excludes that permanent page, and native zap skips ordinary anonymous-page
accounting/release for such entries. The extension never gets, locks, puts or
writes the zero page. Its retained PTE is recorded separately; after success
or an admitted split error, its complete identity/protection must be unchanged,
ignoring only the hardware accessed bit that concurrent readers may set.
No new caller-context allocation or queue storage is introduced. Existing caller
reserves, locked revalidation, exact private-page holds, native split/unmap,
completion/ACK routing and sticky refusal remain intact.

The new probe reuses the existing read-only PTE classifier. It intentionally
read-faults Z slots, leaves U slots absent and pins only private R slots. All five
survivor combinations containing Z (`ZU`, `UZ`, `ZR`, `RZ`, `ZZ`) run at all three
target positions with native comparisons; none is deduplicated. Per-VMA resident
accounting excludes Z and U. Pre-access snapshots precede controller reads;
subsequent zero reads and isolated private writes check both another survivor
and an independent shared-zero mapping. An explicit competing read fault waits
at local reader admission; no reader or that read-fault body is delegated.

Thirty matrix removals and one final release completed on other tasks. Two
interior post-split errors match native `ENOMEM` and harmless layouts with zero
PTEs intact. A busy retained private page and a zero-page target each release one
earlier hold before matched handback/ACK, then demonstrate sticky local fallback.
Queued cancellation preserves the victim mapping. Six small smokes preserve the
existing mixed/resident/untouched removal, whole removal, advice and first-write
paths. The [probe guide](../../tests/kernel/mmap_lock/zero_partial/README.md)
provides commands, observations and explicit race-coverage limits.

## Shared-zero-page targets

`kdmm11` established zero-target removal for a one-page partial range in an exactly
three-page VMA that still has an ordinary private resident survivor. The same
single-link ancestry, caller reserves and table-retaining neighbors are required.
Zero entries are recognized under the PTE lock using all the identity/protection
checks above. The shared zero page never enters the owned private-page array.
Missing/unsupported targets and a VMA with no ordinary resident slot refuse
before splitting on that image; a nonzero private-hold count was still required.

Native `zap_pte_range()` clears a zero target and records its TLB invalidation.
Its `vm_normal_page()` result is NULL, so it skips private RSS accounting, page
reverse-map removal and page release. Native VMA links and virtual-page counts
still follow normal splitting/removal semantics. After success the target PTE
must be absent, while retained zero PTEs must match their saved entries. On an
admitted error, every zero entry including the target remains. Separate zero
completion receipts avoid pretending there was an owned private target PFN or
mapcount. Private survivor holds still release exactly once. Whole removal,
caller preparation, ownership, handback/ACK and sticky fallback are unchanged.

All five survivor pairs containing an R page (`RU`, `UR`, `RZ`, `ZR`, `RR`) run at
all three positions, each with a native comparison and two remote completions.
R is ordinary private resident, U absent, and Z shared zero. No eligible pair is
deduplicated. Zero/U-only survivor combinations were refused at that stage.
The probe independently classifies PTEs before controller reads, checks private
resident accounting, original-CPU removed-address faults and survivor contents,
then checks zero reads and isolated private writes against an independent zero
mapping. A deliberate read fault resolves locally after writer release.

A deterministic test changes a proven Z target into a private page after three
unmap requests are published but before either of two local read shares is
released. The modifier uses native locked GUP (`get_user_pages`) write intent
on its existing share, verifies and retains the newly private page, and records
its physical identity. The later combiner revalidates that page through the
existing private path. Its exact PFN matches the change receipt, and it is
counted separately from actual zero-target removals. No admission bypass or
synthetic body callback is used; uncontrolled concurrent write faults and
reclaim/pinning races remain untested.

The [result](../../bench/results/10.176.26.71/tests/mm-zero-target-20261023/README.md)
records 32 zero removals, one changed-private removal, two remote split errors,
three matched refusal/ACK pairs, cancellation and seven preservation smokes.
The [probe guide](../../tests/kernel/mmap_lock/zero_target/README.md) provides
prebuilt commands and the exact limits of the controlled transition.

## Zero and untouched survivors without private pages

`kdmm12` admits all four Z/U survivor pairs at each of the three target positions.
On that image the target must be a verified shared-zero PTE; an absent target refuses.
The same isolated three-page VMA and same-PMD neighboring VMAs remain mandatory.
Native `free_pgd_range()` uses those neighbor bounds to retain tables, regardless
of whether a private resident page exists. No general table-freeing path is enabled.

Eligibility distinguishes absent metadata (NULL `anon_vma` and an empty chain)
from the existing single-link ancestry. A pointer/chain mismatch or a complex
chain refuses. Empty metadata can accompany only zero/absent PTEs; an ordinary
private PTE still requires valid metadata and all existing page checks. For an
empty chain, native `anon_vma_clone()` iterates no links and allocates nothing.
An inherited simple chain consumes caller-prepared links exactly as before.

The caller still prepares two VMA descriptors, two reverse-map links and mapping
index reserves without capturing a live VMA. This also covers a private fault that
creates metadata after publication. The later writer revalidates the actual VMA
and PTEs; unused resources retire on the caller after the exact queue node retires.
No zero page acquires an ordinary reference or release obligation.

The page walk now returns admission success separately from the number of private
holds. The retained-table pointer controls post-body checks, so a valid body with
`held=0 released=0` still verifies PTE absence, zero/untouched survivors and table
bytes after the native TLB flush. Split errors follow the same checks and admitted
return path; they cannot become a destructive local replay. Zero-target receipts
remain distinct from private-page completion.

All 12 new native/KD layout pairs passed. Additional cases checked simple inherited
metadata with no current private pages and a controlled queued Z-to-private target
change starting from absent metadata. Both post-split errors, missing-target and
busy-page refusal/ACK, cancellation and preservation smokes passed. The
[result record](../../bench/results/10.176.26.71/tests/mm-zero-only-20261023/README.md)
keeps the 27 removals without private holds separate from two resident-survivor smokes and one
changed-private removal. Readers remain concurrent/local; the controlled transition
does not establish uncontrolled fault, reclaim or pinning race coverage.

## Absent targets with retained leaf tables

`kdmm13` additionally admits `pte_none()` at the requested target. The address
must be inside the original three-page VMA and every page-table level through
the leaf table must already exist. A swap, migration or other nonempty non-present
entry is not an absent target. Missing upper levels still refuse on the resident
partial opt-in. This differs from the original untouched opt-in: that path
requires absent PGDs, whereas this path requires a retained leaf table and its
same-PMD neighbors. The probe establishes a table with a separate neighbor read;
it never touches the target to satisfy eligibility. All three target-VMA slots
can therefore remain untouched while the required table exists.

The old walk allowed empty survivors but refused an empty target. The new walk
accepts either only after validating the existing table, records a separate
absent-target outcome, and still runs native split/detach/unmap. There is no
physical target to hold, clear, reverse-map or release; virtual-page and VMA
accounting must nevertheless change and later target access must fault. Shared
zero entries likewise never enter the owned private-page array. Private survivors
retain their original references, locks and slot indices. No page-table allocation
or general page-table destruction is added. Caller reserves and exact retirement
are unchanged; empty metadata consumes no reverse-map links.

Writer ownership and the PTE lock revalidate current entries. A target populated
after preparation can use the existing zero/private path if all checks pass, or
hand back before effects. Once splitting can take effect, an error remains an
admitted return and cannot replay locally. Post-body checks cover empty entries,
zero entries and retained tables even with no held pages and on injected errors.
`KD_MM_ABSENT_TARGET` receipts bind the state and table identity to actual queue
completion by a different task. The probe independently verifies the same table
physical identity before and after, VMA boundaries, private resident accounting,
reference lifetimes, survivor state and later isolated writes. An empty target
has no positive cached translation to warm; its fault after removal proves VMA
absence, not a positive-target TLB invalidation. Zero/private preservation smokes
retain their warm-translation checks.

The kdmm13 campaign's 18 native/KD pairs use survivor pairs RR, RZ, RU, ZZ, ZU and
UU at each target position. R is private resident, Z shared zero and U untouched.
Its nine reversed mixed pairs were not rerun then. The separate kdmm14 coverage
group closes ZR, UR and UZ at all three positions with the unchanged absent-target
binary; the two kernel revisions' evidence remains distinct. Two controlled tests
use native GUP
(`get_user_pages`) on an already admitted local reader after three requests publish.
Read intent with no output page array takes no reference on the shared zero page;
write intent retains only the new private page. Their unchanged table identities
and later zero/private body receipts prove locked revalidation. These are
pre-execution changes, not uncontrolled concurrent fault races. Both interior
split-error points match native harmless splits; busy-survivor and missing-table
refusals match their ACKs and sticky continuation. Cancellation and cleanup pass.
See the [result](../../bench/results/10.176.26.71/tests/mm-absent-target-20261023/README.md)
for exact counts, identities and remaining gaps.

## Missing leaf tables with existing upper levels

`kdmm14` admits a separate state: valid PGD/P4D/PUD entries (the upper directory
levels) and `pmd_none()` at the target. A PMD, or page-middle-directory entry,
covers 2 MiB here; its missing entry means there is no 512-entry leaf PTE table
for that interval. This differs from `pte_none()` in an existing leaf table.
The captured x86-64 kernel supports five levels; the live probe reports 4-KiB
pages, 2-MiB PMD intervals, 1-GiB PUD intervals and a 256-TiB PGD interval.
Missing higher levels, huge/device mappings, bad entries and special non-present
states remain refused. `pmd_none()` uses native x86 semantics, including its
ignored erratum bits; it is not an arbitrary raw-entry equality test.

The same three-page VMA and both retaining-neighbor constraints remain. All three
slots share one leaf table, so a missing table requires all three to be untouched.
A zero/private survivor in that same interval would necessarily create the table.
The test therefore reads an independent anchor VMA in the adjacent PMD within the
same PUD, constructing the required upper levels without touching any target-VMA
slot. Read-only table walks verify both absence and exact upper identity. No VMA
is widened and no boundary-crossing case is claimed.

The caller prepares the existing VMA, mapping-index and reverse-map reserves.
Under actual mmap writer ownership, the combiner revalidates the current VMA,
ancestry, neighbors and upper levels, then tests `pmd_none()` under the PMD lock
used by native table installation. Admission records the PMD entry and its parent
table's physical identity separately from page ownership; it never computes a PTE
pointer or allocates the missing table. Consistently absent anonymous metadata
consumes no reverse-map links. The real native split/detach/unmap body changes
VMA boundaries and accounting even though there is no target PTE to clear.

Native zap skips the missing table. The retained neighbors make
`free_pgd_range()` return before freeing tables; no general table-free batching
is delegated. Success and admitted split errors require the same parent table,
still-missing PMD entry, unchanged table bytes and zero held pages.
`KD_MM_MISSING_TABLE` receipts bind this state to the exact request, origin,
different executor and native completion. Errors after a split remain admitted
returns, preserving harmless native splits without replay. Pre-effect refusal,
ACK routing, cancellation, resource retirement and sticky local fallback retain
the existing protocol. Readers stay concurrent and local.

Three deterministic controls create the missing table after requests publish,
using an already admitted local reader: a neighbor read leaves the target empty,
a target read creates a shared-zero PTE, and a target write creates a private
page and simple metadata. Locked revalidation selects the corresponding existing
supported body. A separate ordinary read fault waits at writer admission and
creates a survivor's table only after removal. These are distinct from uncontrolled
fault races. All survivors fault in normally after the initial observations,
then pass zero-fill and isolated-write checks. Complete cleanup runs locally and
verifies that the formerly retained upper tables disappear; that local teardown
is not counted as delegated table destruction.

## Boundary-crossing edge removal with retained tables

`kdmm15` extends the same explicit resident-partial opt-in to exactly one missing
leaf-table edge target across a PMD boundary. At boundary B and page size P,
prefix geometry is `[B-P, B+2P)` removing `[B-P, B)`; suffix geometry is
`[B-2P, B+P)` removing `[B, B+P)`. The target lies alone in its 2-MiB interval,
while both survivors share the adjacent interval. Both intervals must lie within
one valid PUD. A target sharing its interval with a survivor, interior crossing,
missing higher levels and, in the kdmm15 baseline, an existing target leaf table
are explicitly refused. The kdmm16 extension below admits only empty targets in
those existing tables.
The survivor table may be missing or contain ordinary private, shared-zero and
empty PTEs; two untouched survivors need not allocate a table.

Admission requires both actual outer VMA neighbors: preceding end greater than
the first PMD base, following start less than the end of the second PMD span.
Under mmap write ownership these neighbors cannot move. After the native split,
`unmap_region()` uses the following exact native `free_pgd_range()` bounds:

| Shape | Floor | Ceiling |
| --- | --- | --- |
| Prefix | original preceding VMA end | B, surviving VMA start |
| Suffix | B, surviving VMA end | original following VMA start |

Admission mirrors native PMD rounding of start/ceiling and adjustment of end,
and requires the early return before any table walk. This establishes retention
for both leaf intervals and every upper level. A populated survivor elsewhere
alone does not establish it. Native zap, reverse-map unlink, VMA release and TLB
completion still execute; no required cleanup is silently skipped. The test's
retaining neighbors are an explicit scope restriction, not proof of general
cross-boundary support.

Caller preparation and queue publication remain unchanged. The writer revalidates
all current geometry and metadata, checks the target `pmd_none()` under its PMD
lock, and classifies survivor PTEs under their leaf lock. The existing strict
private-page classifier is shared without weakening its checks; exact references
and trylocks retain original slot indices. Z/U slots own no private page, and
absent anonymous metadata consumes no prepared reverse-map link. Admission is
independent of the number of owned pages. No target PTE pointer or table is
created merely to remove the range.

After native splitting/removal, success and admitted errors verify the same
parent and survivor-table identities, still-missing target table, survivor PTEs
and unchanged table bytes. Private holds retire exactly. `KD_MM_BOUNDARY`
receipts bind these checks, native floor/ceiling, request and task identities to
completion or error. All refusals precede splitting; after a split any error is
an admitted return, never permission for local replay. Handback/ACK routing,
sticky local fallback and cancellation retain their original protocol.

The focused validation covers both directions and representative RR/RZ/RU/ZZ/ZU/UU
survivor pairs. Read-only walks precede survivor data access. The probe then
checks later normal faults/writes and full local table cleanup. Existing target
tables and target-sharing geometry hand back. Moving the target-side neighbor
away before opt-in makes native teardown free the target table; the KD route
also hands back and matches that release. A controlled target-table appearance
after publication causes locked refusal and exact ACK, while a separate ordinary
survivor fault waits behind writer admission and resolves locally afterward.
Neither control claims uncontrolled fault or neighbor-replacement race coverage.
The [result record](../../bench/results/10.176.26.71/tests/mm-boundary-edge-20261023/README.md)
separates these controls, actual remote removals, errors and preservation smokes.

## Empty target entry in a retained boundary table

`kdmm16` replaces only kdmm15's mandatory missing target PMD entry. The same
isolated-edge geometry, valid common upper directory and both neighboring-VMA
retention bounds above remain mandatory. An existing normal target leaf table
is accepted in kdmm16 only when its selected entry satisfies `pte_none()`; that
revision refuses zero/private targets. The kdmm17 extension below adds only a
verified shared-zero target. Special non-present entries, huge/device mappings
and missing higher levels still refuse. Same-table support does not authorize
an ordinary private boundary target.

After taking the actual mmap write lock, the executor walks the live hierarchy
afresh. It observes missing versus existing target tables under the PMD lock;
for an existing normal table it maps the current leaf under its PTE lock, records
the physical table identity and checks the target is empty. No earlier unlocked
table pointer survives queue publication. The mmap writer excludes ordinary
faults and VMA replacement during this body; the unchanged native floor/ceiling
proof ensures that the table remains live through teardown. Another populated
entry in that table is neither the retention proof nor an ownership reference.

Caller-prepared VMA/maple/reverse-map resources and survivor classification are
unchanged. Absent anonymous metadata consumes no reverse-map links; zero and
untouched slots need no private-page holds. The native split/detach/unmap body
removes the virtual mapping without allocating a target page/table, clearing
unrelated PTEs or suppressing native cleanup. Success and admitted split errors
verify the same parent, target and survivor table identities, still-empty target
PTE, unchanged table-byte accounting and exact survivor holds. New
`KD_MM_BOUNDARY_EMPTY` completion/error receipts record the target table identity
and `target_pte_none=1`; the original missing-table receipt remains distinct.
After a successful split, an error remains an admitted native-compatible return
and cannot authorize destructive replay.

The test allocates the target table by read-faulting a separate retaining
neighbor in that interval, never by touching the target. Read-only walks verify
its shared-zero PTE, target-table identity and empty target before admission and
after removal. Twelve representative prefix/suffix layouts matched native
behavior. Controlled local-reader faults change an empty target to zero/private
after publication; locked revalidation hands back with the exact acknowledgment
(ACK), then later calls remain local. Moving the retaining neighbor away before
publication also hands back and matches native table release. That prepublication
control is not a queued neighbor-replacement race: changing VMA bounds needs
writer ownership, incompatible with the two held reader shares in this fixture.
Readers remain concurrent and local. See the
[result record](../../bench/results/10.176.26.71/tests/mm-boundary-empty-20261023/README.md)
for counts, split errors, cancellation, waiting faults, full cleanup and untested
reversed pairs and races.

## Shared-zero target in a retained boundary table

`kdmm17` shares the existing exact zero-PTE classifier between the same-table
and boundary paths: present, special, read-only, not protection-none or device,
and `is_zero_pfn()`. The boundary target remains alone in its PMD interval,
within the same upper directory as both survivors. The complete two-neighbor
native floor/ceiling proof above is unchanged. Another zero/private PTE cannot
substitute for the missing retaining VMA.

Under actual mmap write ownership, the executor rewalks the hierarchy and
locks the current target PTE. It records the table identity and original zero
entry, ignoring only the hardware accessed bit for later comparisons. This
snapshot crosses neither publication nor an unlocked VMA change. An ordinary
private target refuses in kdmm17 before survivor holds or splitting; kdmm18
extends that case below. A shared-zero target acquires
no private-page reference, reverse map or lock; only eligible private survivors
use the existing exact hold/release records. Admission still permits zero holds,
missing survivor tables and absent anonymous ancestry. Caller-prepared VMA,
maple and reverse-map reserves retire through the unchanged protocol.

The real native `zap_pte_range()` clears the zero entry and records TLB
(translation lookaside buffer) invalidation. `vm_normal_page()` returns NULL for
the special zero mapping, so native teardown does not decrement private resident
accounting, remove a private reverse map, enqueue a page release or change the
shared zero page. The native VMA removal and TLB completion still execute.
Success requires the target PTE to be empty; an admitted post-split error instead
requires its original zero entry to remain. Both outcomes require identical
parent/target/survivor tables, unchanged table-byte accounting and exact survivor
references. `KD_MM_BOUNDARY_ZERO` receipts bind these checks to the request,
origin and different executor. Errors after splitting never authorize replay.

The focused run validates all nine R/Z/U survivor pairs in both directions.
Each target is read-faulted and classified before admission. Origin tasks warm
existing zero translations without touching U survivors, then check removal
faults on the same CPU. Controlled zero-to-private faults after publication
cause locked handback and an exact acknowledgment (ACK), followed by sticky local
calls. Retention loss is tested by moving the target-side neighbor away before
publication; native table release then matches the handback route. Queue-time
neighbor replacement is not tested because changing VMA bounds needs writer
ownership incompatible with the fixture's held reader shares. Readers remain
concurrent and local. The
[result record](../../bench/results/10.176.26.71/tests/mm-boundary-zero-20261023/README.md)
separates 38 zero removals, 12 empty-target gap-closure removals, split errors,
refusals, cancellation, smoke results and untested races.

## Private target in a retained boundary table

`kdmm18` retains the exact isolated prefix/suffix geometry and both native
floor/ceiling bounds above. Under the actual mmap writer it rewalks the current
hierarchy and PTE (leaf page-table entry), then reuses the same-table private-page
classifier: writable ordinary PTE, exclusive base anonymous page, one mapping,
simple ancestry, no compound/swap-cache/reserved/poisoned state or native
indication of a DMA pin. A nonblocking page lock refuses a busy target while
still under the PTE lock. Neither a matching old address nor same-table
eligibility substitutes for the current boundary retention proof.

The target joins the existing slot-indexed hold array with one temporary
reference. A survivor refusal releases that target and every earlier survivor
hold before handback. No split has occurred on that route. Caller-prepared VMA,
maple-tree mapping-index and reverse-map reserves still supply native splitting;
no new executor-side allocation is introduced. The single removed base page
fits the native local gather, and the retention proof excludes table freeing.

Native zap clears the PTE, removes its reverse map, updates RSS (resident-page
accounting), flushes TLB translations and drops the mapping reference before KD
unlocks and puts its temporary reference. Success requires the original target
physical identity, no remaining mapping and an empty target entry. A post-split
error requires the original entry and one mapping. Both require identical
parent/leaf tables and unchanged table-byte accounting. The `KD_MM_BOUNDARY_PRIVATE`
receipt binds completion/error, original page, holds/releases and reference
observations to the exact request and different executor. After splitting, any
error is admitted and never authorizes destructive local replay.

Most probes retain an ordinary test reference for post-unmap page inspection;
those observations prove logical removal and balanced ownership. Two delegated
controls drop every probe reference before publication. Their target count is
2 with the KD hold and 1 after native teardown, immediately before KD's final
put. No freed page is subsequently inspected; allocator reuse is not traced.
Caller resources, ACK routing, cancellation and sticky fallback are unchanged.
Readers remain concurrent and local.

A deterministic already-admitted reader locks the original target after two
requests are published. The same page/table/ancestry then hands back through
locked revalidation, with no added reference or PTE modification. Retention-loss
controls move the outer neighbor before publication; queued VMA replacement
would require writer ownership incompatible with the held reader shares and
remains untested. The [result record](../../bench/results/10.176.26.71/tests/mm-boundary-resident-20261023/README.md)
separates 24 new removals, two errors, seven ACKs, two cancellations, five smokes,
reference-held versus final-reference cases and omitted equivalent layouts.

## Private target sharing a boundary table

`kdmm19` extends only the preceding private target class. With page size P and
PMD boundary B, prefix VMA `[B-2P,B+P)` removes `[B-2P,B-P)`; suffix VMA
`[B-P,B+2P)` removes `[B+P,B+2P)`. Both retain `[B-P,B+P)`. Slot 1 shares the
target table; the far survivor is slot 2 for prefix or slot 0 for suffix. The
other table may be missing if its survivor is untouched. Both PMD entries still
share an existing ordinary upper directory. Zero, empty and missing targets were
refused on kdmm19; kdmm20 adds only the zero class below. Their isolated-edge
contracts are unchanged.

The old assumption that both survivors use the other table is replaced by
per-slot classification. Under actual mmap write ownership, the executor walks
the current hierarchy, checks both outer VMA bounds and mirrors native
`free_pgd_range()` floor/ceiling rounding. Both original neighbor guards remain;
no other populated PTE substitutes for them. Each surviving slot is then checked
under its own table's PTE lock, with no simultaneous PTE locks or cross-boundary
PTE pointer. Exact private references and page locks join the slot-indexed array;
zero and untouched slots own none. Any later refusal releases the entire held
prefix, including the target, before handback and its matching ACK.

Caller-prepared split and reverse-map resources are unchanged. Native removal
finishes PTE clearing, reverse-map/RSS updates and TLB invalidation before KD
puts its target hold. Post-body checks bind original page identity, each table,
every surviving PTE and table-byte accounting. Split errors preserve the original
target entry and return as admitted errors, never local replay. The distinct
`KD_MM_BOUNDARY_SHARED_PRIVATE` receipt binds the slot/table partition and actual
different-task completion to the request. Readers remain concurrent and local.

The focused matrix covers all nine survivor pairs in both directions because
near/far table roles differ. A real queued read fault changes the near survivor
from empty to zero while an already-admitted local reader holds its share.
Fresh locked classification then preserves the new zero entry without another
private hold, table allocation or ancestry change. A separate far-survivor fault
waits behind the writer and creates the other table only after release. These
controlled cases do not establish uncontrolled race coverage.

Removing an outer retaining neighbor before publication still forces KD handback.
In this new geometry, native code retains the target table because the near
survivor remains, so the inherited `free-table` control expects **zero** table
frees. This preserves the conservative guard without misreporting native behavior.
Queued neighboring-VMA replacement still conflicts with the fixture's held reader
shares and remains untested. See the [new evidence](../../bench/results/10.176.26.71/tests/mm-boundary-shared-20261023/README.md)
for 44 removals, two split errors, five ACKs, two cancellations and eight smokes.

## Shared-zero target sharing a boundary table

`kdmm20` adds the exact existing zero-PTE class to the preceding shared-table
geometry: present, special, read-only, non-protection-none, non-device and
`is_zero_pfn()`. Prefix `[B-2P,B+P)` removes `[B-2P,B-P)`; suffix `[B-P,B+2P)`
removes `[B+P,B+2P)`. Slot 1 shares the target table and the other survivor lies
across B. Both outer-neighbor guards and native floor/ceiling no-table-walk proof
remain mandatory. Current VMA bounds, ancestry, hierarchy and individual entries
are rewalked under actual mmap write ownership and the relevant PTE lock. No
captured pointer or private-page count substitutes for admission.

Caller-prepared resources and per-slot retirement are unchanged. Zero targets
take no private reference, page lock or reverse-map ownership. Native
`vm_normal_page()` returns NULL, so `zap_pte_range()` clears the translation and
records TLB invalidation without private RSS/rmap/release work. After native
completion, target PTE absence, unchanged table identities/accounting and every
surviving entry are checked. The request-bound `KD_MM_BOUNDARY_SHARED_ZERO`
receipt distinguishes this execution and its slot/table partition. A split
error preserves the original zero target and returns without destructive replay.
Readers remain concurrent and local.

All nine private/zero/untouched survivor pairs passed in both directions against
native-body controls, including missing far tables and no-private-hold cases.
Read-only walks precede intentional survivor faults/writes; removed-address
faults, private contents/references, zero-page isolation, neighbors, accounting
and full cleanup are checked. A queued real local-reader write fault converts
the target to private. Locked revalidation then uses every kdmm19 classifier and
reference/lock check; the busy variant hands back before effects and exact ACK.
These controlled transitions do not establish uncontrolled race coverage.

The [result record](../../bench/results/10.176.26.71/tests/mm-boundary-shared-zero-20261023/README.md)
separates 40 zero removals, two changed-private removals, two split errors, five
new ACKs, two cancellations and eight smokes. Losing a retention guard before
publication still refuses even though native retains the shared table. Queued
neighbor replacement remains untested because the fixture holds reader shares.
Empty/missing targets were explicitly refused on kdmm20. kdmm21 adds only the
empty leaf in an existing table below.

## Empty target sharing a boundary table

`kdmm21` permits an exact `pte_none()` target in the existing shared table, after
the current locked classifier succeeds. The prefix/suffix geometry and both
outer-neighbor guards above are unchanged. The native floor/ceiling calculation
must still return before any table walk. An empty entry is not a missing table,
swap/migration entry or another special non-present state; those classes remain
excluded from this new admission.

The executor rewalks VMA bounds, ancestry, neighbors and table identities under
actual mmap write ownership, then verifies entries under their table's PTE lock.
Native splitting/removal eliminates the virtual mapping without allocating a
target page, clearing unrelated entries or freeing the retained table. The empty
target has no private page/rmap/RSS ownership and no valid translation to clear.
Caller-prepared resources and exact retirement remain unchanged, including absent
ancestry and zero-private-hold admission. The existing
`KD_MM_BOUNDARY_SHARED_EMPTY` receipt binds request identity, table partition and
real different-task completion. Errors after harmless splits never allow local
replay; refusal before effects retains exact ACK and sticky fallback semantics.

The fixture read-faults the retaining neighbor to create the table while keeping
the target empty. Read-only walks precede survivor accesses. All nine R/Z/U
(private resident/shared zero/untouched) survivor pairs in both directions matched
native-body controls. Queued real read/write faults convert the empty target to
zero/private; locked revalidation
then selects every condition of the existing kdmm20/kdmm19 path. A busy converted
page hands back before effects. Empty targets do not need a fabricated TLB
invalidation; populated controls verify native PTE/TLB completion separately.

The [result record](../../bench/results/10.176.26.71/tests/mm-boundary-shared-empty-20261024/README.md)
separates 42 empty, two converted-zero and two converted-private removals, two
split errors, five new ACKs, two cancellations and eight smokes. Retention loss
is tested before publication. Queued neighbor replacement requires a separate
writer-owned gate; the current reader gate cannot safely replace a VMA. Neither
controlled transitions nor successful cleanup establish uncontrolled race or
general table-destruction coverage.

## One through four populated pages

The separate `kd_mmap_unmap_populated_enable()` opt-in keeps the common VMA
exclusions, but allows reverse mapping state for one through four writable
resident 4-KiB anonymous pages. Every page must be exclusive to one mapping, ordinary rather
than huge/compound, unswapped, healthy and without a detected DMA pin (a device's
retained reference for direct memory access). Their VMA must have one reverse
mapping chain and must not be mergeable. Multi-generation LRU, a page-reclaim
policy that uses implicit task context, is excluded in configuration admission.
The opt-in is an experimental kernel control under actual mmap write ownership;
ordinary applications do not enable it automatically.

The whole target must fit in one PMD span, the 2-MiB interval described by a
page-middle-directory entry. Both neighboring VMAs' end/start bounds must lie
strictly inside that span. The original
`free_pgd_range()` then returns before freeing the leaf PTE table. This is a
deliberate correctness restriction: general table freeing can allocate an RCU
batch, which defers freeing until concurrent readers finish, using the executor's
allocation context. Four data pages fit strictly below the native eight-page
local gather (the temporary list of pages awaiting a TLB flush and release).
The captured `__tlb_remove_page_size()` calls `tlb_next_batch()` immediately when
that list fills, which can allocate in the executor's context. Staying below
eight, with retained tables, avoids both allocation paths. A compile-time check
enforces this capacity relationship. The real unmap helpers still execute.

The origin prepares maple storage, synchronizes its deferred RSS (resident-page
accounting), and drains its local LRU (recently used page) additions before queue
publication. Under actual mmap writer ownership, the executor walks the explicit
mm's page tables and takes a temporary reference and tries the page lock for
every target page under the PTE lock. It never blocks in that inverse lock order.
All pages must pass before any removal. A busy or unsupported later page releases
every earlier page lock/reference before refusal; the existing protocol returns
the operation to its waiter and makes later calls local. The retained references
and locks protect the exact objects against freeing, reclaim and migration
through the real removal. Fixed four-entry stack arrays need no new allocation
or queue storage.

Native teardown removes the PTE and reverse map, updates explicit mm and page
accounting, and completes the TLB flush. The executor then requires every PTE
empty, every page's mapcount zero and page-table bytes unchanged, and releases
all its temporary page locks/references before completion. Final page-charge
release follows each page's recorded memory cgroup. The existing physical owner,
queue and exact ACK protocol
below are unchanged; unsupported table destruction returns to the original caller.

The `kdmm6` four-page case completed 15 whole-VMA removals on other tasks and
matched all 60 original PFNs (physical page numbers) to body receipts. A deliberately
locked fourth page proved that the three earlier temporary locks/references
were released before its exact handback/ACK; a five-page range also refused,
and later calls stayed local in both cases. Separate two-, three- and four-page
cases released all test references before the real body, exercising final page
release without dereferencing freed pages. The [probe guide](../../tests/kernel/mmap_lock/populated_unmap/README.md)
provides commands that reuse the built probes. Its kernel snapshot is for
identity verification, not a complete module build tree.

## Preserved single-page baseline

The earlier `kdmm5` main case paired 15 original PFNs with
different-task completions, verified every retained page byte and exact mapping
and test references, and invalidated 48 originating CPUs' cached translations.
Fifteen partial-unmap handbacks matched their ACKs; 16 later calls stayed local.
Two readers remained concurrent before writer admission closed. A real read
fault to an untouched surviving neighbor waited for writer release and then
resolved with zero-filled data, locally. That read is not delegated fault-body
evidence. The separate preserved first-write test recorded 133 real remote page
installations on this kernel.

Additional cases passed pending fatal cancellation, one exact handback when
missing neighbors required page-table destruction, and two real removals after
both test references were released, including one remote completion. The latter
exercises the native final-release path without dereferencing a freed page.
All four cases released 55 exact test references, performed 165 local cleanup
calls and unloaded normally. These counts are separate from the old unpopulated
path and earlier kernel runs.

The historical probe commands and all four baseline cases remain in the
`f7af0fd` revision of the probe guide and the stage record. Their `kdmm5` identity
is separate from the current candidate:

- Source: `/root/kdlock-kernel-work/mm-populated-unmap-20261022/candidate-1/linux`.
- Baseline: `/root/kdlock-kernel-baselines/mmap-kdmm5-20261022`.
- Build ID: `557ee1e502bacf98c48b3f21b2c328aa92e273e9`.

The [stage record](../../bench/results/10.176.26.71/tests/mm-populated-unmap-20261022/README.md)
keeps the initial failed probe build, follow-up revision, serial results and
archives distinct. No kernel admission check was removed to resolve that build.

## Caller context and resources

Address alignment and `TASK_SIZE` depend on the original caller's thread mode,
so the origin checks them before publication. The captured x86 `arch_unmap()`
is empty. No callback, file operation or user access is admitted remotely.

Maple-tree allocation can depend on the current task's allocation context.
The origin therefore prepares the live-tree and detach allocation chains before
entering the queue, plus the two split reserves/descriptors for partial opt-ins
and the two reverse-map links for resident partial removal described above.
An allocation-only helper reads a scalar tree-height hint with `READ_ONCE`; it
never walks a live tree or retains a VMA pointer. Its common allocation routine
is also used by the unchanged native preallocation API. The combiner checks the
actual reserve capacity against the current height under mmap write ownership;
insufficient capacity refuses before any effect. Preparation takes no mmap read
lock, avoiding a second origin waiting behind the first queued writer.

The prepared detach allocation chain and its flags transfer explicitly into
the native helper's local state; no whole packet or traversal state is copied.
The real preallocated stores consume the chains. The origin destroys whatever
remains only after its exact queue node retires, including cancellation/refusal.

## Lock and refusal protocol

Use the existing KD physical mmap writer gate, preallocated per-CPU nodes and
independent OSQ links. OSQ is the optimistic-spin queue for physical acquisition.
A separate munmap delegation tail prevents the preserved advice queue from
interpreting a different request layout. Both queues serialize through the same
actual mmap writer owner. The advice and fault body implementations are unchanged.

Readers stay local and concurrent until an actual writer closes admission and
waits for them to drain. An admitted munmap keeps its single writer acquisition;
the optional native downgrade is disabled for that body. Only the exact physical
owner releases it. A completed remote node is detached before DONE permits its
origin to retire; the head retains its own slot through physical unlock.

Unsupported requests set the munmap entry's sticky native-only flag. A remote
origin validates the exact node, mm, task and physical owner before acknowledging
the refusal. This ACK is for ownership/request retirement, not completion of the
native munmap. After DONE and slot retirement, the original `__vm_munmap()` tail
acquires, optionally downgrades and releases its own lock normally. The combiner
does not wait while arbitrary native callbacks execute on the origin.

Pending fatal cancellation remains linked until the owner consumes it before
body admission, then returns `-EINTR` without removing the VMA. Once admitted,
an error is returned directly and never replayed locally. Bounded cancellation
latency and oversubscribed progress remain unvalidated.

## Original unpopulated validation and commands

On the original `10.176.26.71:2222` MM VM, `native-1` passed four controls;
`kd-1` passed six preservation sessions, and `kd-2` passed the remaining six on
the same KD boot. The one failed initial munmap probe remains separate. The
[stage record](../../bench/results/10.176.26.71/tests/mm-unmap-body-20261022/README.md)
binds revisions, boot identities, result receipts and archives.

The successful main case removed 16 complete three-page VMAs, including 15
remote bodies with origin/mm/range-bound completion receipts. Two readers held
the actual read lock concurrently before the writer drained them. A subsequent
hardware read fault waited at reader admission and received `SEGV_MAPERR` after
the VMA disappeared. Partial removals of 16 populated VMAs went to their callers,
with 15 matching handback/ACK pairs and unchanged remaining contents. Sixteen
later eligible whole-range calls stayed local after sticky refusal.

Separate cases verified a queued fatal cancellation left its VMA intact, and a
prior real zero-page read forced full-range unmap back to its caller. Re-reading
on the original reader CPU then faulted, verifying local invalidation of the old
translation. That case matched one additional handback/ACK and one sticky local
call. All three cases checked mapping cleanup and exact idle retirement before
normal module unload. Their 159 explicit cleanup calls count as local calls,
never delegated removals. Built-in C bodies execute here; no JIT body is claimed.

[Probe commands](../../tests/kernel/mmap_lock/unmap_body/README.md) run the three
cases serially with the exact source/baseline arguments. They require an already
approved KD boot and verified recovery snapshot. For this recorded candidate:

- Kernel source: `/root/kdlock-kernel-work/mm-unmap-body-20261022/candidate-1/linux`.
- Baseline: `/root/kdlock-kernel-baselines/mmap-kdmm4-20261022`.
- Build ID: `a4f371bb5bca303f6b6d9354bfbf156275479dcb`.

## Remaining limitations

The original opt-in supports untouched whole/partial removal within its 16-page
bound and absent PGDs. The original populated opt-in supports whole removal of
one through four resident pages with retained tables. The new opt-in additionally
supports the three-page/one-page-slice cases above, including zero or empty-leaf
targets with only zero/untouched survivors, and a missing leaf table when upper
levels exist and all three slots are untouched. The new boundary-edge path
permits a missing target table, an empty/shared-zero PTE, or one eligible ordinary
private target in an existing table, with an adjacent survivor interval under the
explicit two-neighbor retention proof above. Private, exact shared-zero and empty
PTE classes also permit one survivor sharing the existing target table; missing
target tables still require the isolated-edge geometry. It refuses missing higher
levels on this opt-in, special non-present entries, inconsistent or multi-link reverse-map
ancestry, shared/COW
(copy-on-write) pages, swapped/huge pages and missing table-retaining neighbors.
General table destruction, file/device or notifier callbacks, memory-accounted
VMAs and mapping creation remain unsupported. Other untouched widths within the
16-page bound and multi-page partial slices are not newly validated. The ordinary
local path retains native downgrade and release behavior.

Forced prepublication allocation failure, maximum-VMA-count errors, tree-height
growth during preparation, slot exhaustion, the 256-request boundary,
post-admission cancellation, queue interleaving, broader reader/fault races,
concurrent fast-GUP (fast page pinning), swap/reclaim pressure, non-root memory
cgroups and oversubscription remain untested. Injected failures precede
destructive removal; the admitted native path has no recoverable error return
after destruction starts. Fork/complex ancestry, Native-off boot controls and the full historical fault-retry/API suite were not
repeated. The run checked the same 73 runtime modules, not every configured
module. RT, lockdep and whole-kernel replacement remain unvalidated.

All nine mixed survivor patterns and all 15 zero-survivor patterns retain their
separate native/delegated evidence. The 15 eligible zero-target patterns now have
live comparisons too. The absent-target extension adds 18 representative
native/KD pairs on kdmm13; the nine reversed mixed pairs passed separately on
kdmm14. No size limit was increased. Controlled pre-execution Z-to-private and
U-to-zero/private changes
are validated; forced VMA replacement and uncontrolled
mapping/residency races are not. Busy-page refusal exercises locked revalidation
and exact zero-effect release before ACK.

Zero/empty/missing-table admission is separate from private-page ownership.
Explicit receipts prove native VMA removal even with no physical target.
The next small extension is a missing target table with an untouched near
survivor in the shared boundary geometry. It needs explicit handling that never
walks either missing slot's PTE, plus the unchanged retention proof and feasible
geometry checks. Removing the guard alone would be unsafe. It remains refused
in kdmm21. General table destruction and
missing higher levels remain deferred. The kdmm16 reversed empty-target gaps
remain closed; the eight omitted kdmm18 isolated private layouts are not covered
retroactively by the new geometry. Queued zero-to-private and empty-to-zero/private
changes passed in the shared geometry, including busy-page handback. Uncontrolled
races were not exercised in this stage.
Broader mapping creation/removal support, performance, p95, the seven mutex
regressions and nano reruns remain deferred.
