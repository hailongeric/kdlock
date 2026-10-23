# Minimal whole-VMA munmap body

Status: `kdmm6` extends the validated one-page removal to one through four
resident anonymous pages whose neighbors retain their page tables. All 11
focused serial cases passed, including 18 multi-page removals on other tasks
with 69 original-page receipts, late admission rollback, exact handback/ACK
(acknowledgement) matching and cleanup. The single-page, advice, anonymous
first-write and unpopulated paths passed a small preservation smoke set. Recovery
is restored. See the [result record](../../bench/results/10.176.26.71/tests/mm-range-unmap-20261023/README.md)
for run identities and essential logs. Performance, p95, the seven mutex
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
The origin therefore prepares both allocation chains before entering the queue.
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

The original opt-in supports one small isolated VMA with absent PGDs. The
populated opt-in additionally supports one through four resident pages with
retained tables as described above. Neither delegates larger populated ranges,
general page-table destruction, partial unmap, file/device or notifier callbacks,
or mapping creation. Partial
populated removal, old zero-page/PGD refusal and one-page missing-neighbor refusal
were individually exercised in earlier stages. This stage exercised partial
removal again, a busy final page, and the five-page limit. Cross-PMD ranges,
partially absent PTE ranges and other guards remain source-reviewed exclusions.
The ordinary local path retains its native downgrade and release logic.

Forced reserve-allocation failure, tree-height growth during preparation, slot
exhaustion, the 256-request handoff boundary, post-admission cancellation,
advice/unmap queue interleaving, broad reader/fault races, concurrent fast-GUP
(fast page pinning), swap/reclaim pressure, different non-root memory cgroups and
oversubscribed progress remain untested. The run checked the same 73 runtime
modules, not every configured module. RT, lockdep, whole-kernel replacement,
performance, p95 and the seven mutex regressions remain outside this milestone.
