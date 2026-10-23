# Bounded anonymous munmap bodies

Status: `kdmm13` removes an absent leaf target in an existing retained table,
within the three-page/one-page-slice scope. Eighteen representative layouts matched
native behavior; 38 different-task absent removals include 20 owning no private
pages. Controlled absent-to-zero/private transitions also completed remotely.
All 51 serial cases, two basic tests and 966 negative receipt controls passed;
recovery is restored and modules unloaded. See the
[result record](../../bench/results/10.176.26.71/tests/mm-absent-target-20261023/README.md)
and [probe commands](../../tests/kernel/mmap_lock/absent_target/README.md).
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
anonymous 4-KiB target, or a shared-zero/empty-leaf target described below, in an
exactly three-page VMA. Each retained slot may be
an ordinary resident page, a validated shared zero page or an absent PTE. The
original exclusions, isolation and both neighboring VMAs within the same PMD
span remain required. A PMD describes
a 2-MiB page-table interval here. Retaining its leaf table avoids allocation for
deferred table freeing on the executor. Private PTEs require exactly one
`anon_vma_chain` link pointing to the active `anon_vma` reverse-map object. With
only zero/empty PTEs, consistently absent metadata is also supported as described
below. Additional ancestry links, missing upper tables and unsupported PTE/page
types hand back.

The native `anon_vma_clone()` allocates a new link when splitting. The caller
now allocates two links, two VMA descriptors and the separate maple reserves
before publication, using its own allocation context. No live VMA or reverse-map
pointer is retained during preparation. Under the actual mmap writer, the owner
rechecks the current VMA, ancestry, reserve capacity and all three original PTEs
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

The 18 native/KD pairs use survivor pairs RR, RZ, RU, ZZ, ZU and UU at each target
position. The nine reversed mixed pairs are not rerun: slot classification is
unchanged, the earlier zero-target matrices cover both orders, and RR exercises
private holds on both sides. This is representative new coverage, not a claim
that all 27 absent-target layouts ran. Two controlled tests use native GUP
(`get_user_pages`) on an already admitted local reader after three requests publish.
Read intent with no output page array takes no reference on the shared zero page;
write intent retains only the new private page. Their unchanged table identities
and later zero/private body receipts prove locked revalidation. These are
pre-execution changes, not uncontrolled concurrent fault races. Both interior
split-error points match native harmless splits; busy-survivor and missing-table
refusals match their ACKs and sticky continuation. Cancellation and cleanup pass.
See the [result](../../bench/results/10.176.26.71/tests/mm-absent-target-20261023/README.md)
for exact counts, identities and remaining gaps.

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
targets with only zero/untouched survivors. It refuses missing upper tables on
this opt-in, special non-present entries, inconsistent or multi-link reverse-map
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
after destruction starts. Resident edge-error injection, fork/complex ancestry,
Native-off boot controls and the full historical fault-retry/API suite were not
repeated. The run checked the same 73 runtime modules, not every configured
module. RT, lockdep and whole-kernel replacement remain unvalidated.

All nine mixed survivor patterns and all 15 zero-survivor patterns retain their
separate native/delegated evidence. The 15 eligible zero-target patterns now have
live comparisons too. The absent-target extension adds 18 representative
native/KD pairs; reversed mixed pairs were not repeated. No size limit was
increased. Controlled pre-execution Z-to-private and U-to-zero/private changes
are validated; forced VMA replacement and uncontrolled
mapping/residency races are not. Busy-page refusal exercises locked revalidation
and exact zero-effect release before ACK.

Zero/empty-target admission is separate from private-page ownership. Explicit
absent-target receipts prove native VMA removal even with no physical target.
The next narrow candidate is an empty target with a missing leaf table but
existing upper levels, still in the three-page scope. It needs a separate
no-table state and proof that native traversal neither allocates nor frees
tables. The current missing-table control retains safe handback; do not allocate
a table merely to pass admission.
Broader mapping creation/removal support, performance, p95, the seven mutex
regressions and nano reruns remain deferred.
