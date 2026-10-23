# Bounded anonymous munmap bodies

Status: `kdmm9` permits untouched surviving pages around a resident one-page
target in a three-page anonymous VMA (virtual memory area). All 22 serial cases
passed, including 11 different-task mixed-page removals and native comparisons
for errors after either interior split. Ownership, handback/ACK
(acknowledgement), cancellation, page references and cleanup passed. Resident
and untouched unmap, advice and first-write fault preservation smokes passed.
Recovery is restored. See the [result record](../../bench/results/10.176.26.71/tests/mm-mixed-partial-20261023/README.md)
and [prebuilt commands](../../tests/kernel/mmap_lock/mixed_partial/README.md).
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
anonymous 4-KiB target in an exactly three-page VMA. Each retained slot may be
an ordinary resident page or an absent PTE. The original exclusions, isolation and
both neighboring VMAs within the same PMD span remain required. A PMD describes
a 2-MiB page-table interval here. Retaining its leaf table avoids allocation for
deferred table freeing on the executor. The VMA must have exactly one
`anon_vma_chain` link, pointing to its active `anon_vma` reverse-map object.
A missing target, additional ancestry links and unsupported page types hand back.

The native `anon_vma_clone()` allocates a new link when splitting. The caller
now allocates two links, two VMA descriptors and the separate maple reserves
before publication, using its own allocation context. No live VMA or reverse-map
pointer is retained during preparation. Under the actual mmap writer, the owner
rechecks the current VMA, ancestry, reserve capacity and all three original PTEs
(leaf page-table entries). It takes a temporary reference and tries the lock on
each resident page. References retain their original VMA slot indices; skipping
an untouched survivor never compacts them into a misleading dense prefix.
Only an absent retained PTE may be skipped. A later failure releases exactly the
held slots before handback. Readers remain concurrent and local until writer
admission closes. The target's resident-page requirement is unchanged.

The prepared clone consumes one supplied link per split and shares the native
reverse-map root locking, interval-tree insertion and active-VMA accounting.
Ordinary native callers retain their allocator path. Native split/adjust and
unmap then remove the requested slice. All originally resident pages remain held
through this body; after its TLB (cached address translation) flush, the removed
PTE must be empty with mapcount zero, surviving PTEs must retain their original
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
if already present during body admission. Busy-page, zero-page-survivor and
missing-target cases each release one earlier page hold before their exact
handback/ACK and then demonstrate sticky-local fallback. Sparse references also
retire correctly after either injected interior split error and cancellation.

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
supports the mixed or fully resident three-page/one-page-slice case above. It
refuses nonresident targets, zero-page survivors, multi-link reverse-map ancestry, shared/COW
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

Live mixed coverage uses both untouched survivors for edge targets and zero or
one resident survivor for interior targets. Edge targets with one resident and
one untouched survivor are admitted by the same slot walk but were not directly
tested. No size limit was increased. Broader mapping creation/removal support,
performance, p95, the seven mutex regressions and nano reruns remain deferred.
