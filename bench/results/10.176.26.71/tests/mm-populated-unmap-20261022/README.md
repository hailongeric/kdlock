# Populated anonymous munmap: bounded functional stage

Status: the first kernel candidate built; focused probe preparation is in
progress and no live pass is claimed. Performance, p95, broad stress and the
seven mutex regressions remain deferred. Initial inspection found the original
MM VM idle on recovery boot
`880aa11b-ab56-4129-b700-06b037473530`, with the expected 73 modules and
9,757,523,968 bytes free on root. The real snapshot and original placement were
rechecked. Checkout commit `d575556` is confined to nano results; its work and
the pre-existing cleanup report remain untouched. MM work has one writer.

The selected extension is one writable resident 4-KiB private anonymous VMA
(virtual memory area), with ordinary exclusive anonymous memory, no swap/huge
page, callback, notifier, special state or memory-account reservation. Both
neighboring VMAs must lie in the same PMD span (the 2-MiB range described by one
page-middle-directory entry). This retains the leaf PTE table (page-table-entry
array), while the real original unmap body removes the mapping, drops its page
reference, updates the explicit mm accounting and completes its TLB flush
(invalidation of cached translations).

This restriction addresses a concrete review finding: freeing page-table pages
can allocate an RCU deferred-free batch using the executing task's allocation
context. The captured `free_pgd_range` returns before table removal for the
admitted neighbor bounds; the original helper is still executed. One data page
fits the native eight-page local gather. General page-table destruction and
larger populated ranges are deferred rather than run with another caller's
allocation context.

The origin prepares maple allocations and synchronizes its own deferred RSS
(resident-page accounting) and LRU additions (recently used page queues) before
publication. Admission takes a temporary page reference and tries its page lock
under the PTE lock; it never waits in the inverse lock order. The page lock
excludes reclaim/migration through removal. Normal teardown unlinks reverse
maps and updates the page's recorded memory cgroup, not the executor's cgroup.
After real teardown, the exact PTE must be empty, page mapcount zero and table
bytes unchanged. The executor releases its temporary page lock/reference before
publishing completion. Existing mmap writer ownership, node retirement and
handback/ACK routing are unchanged. Unsupported and busy-page cases make later
calls sticky-local. The separate populated opt-in leaves the validated old
unpopulated admission unchanged.

Review captured 20 actual `kdmm4` source/configuration files under
`bench/results/10.176.26.71/raw/tests/mm-populated-unmap-20261022/inspection/`.
The candidate uses a new `kdmm5` tree and baseline; recovery and all earlier
installations are retained. Focused serial tests must prove another task removed
the original physical page mapping, cached-translation invalidation, neighboring
contents, exact ACKs, sticky refusal, cancellation and complete cleanup, and
rerun the directly affected preserved paths before this stage can pass.

Kernel source `4b8ec51` built successfully on the first attempt: both basic
programs, five advice, five fault and five unpopulated-unmap receipt controls,
the `kdmm5` image and all 73 required runtime modules passed. The captured
manifest SHA-256 is
`8f9bd2899aa5c69bb2eb113b4d914d780dd5daa17f20b31ada3bced1a0f71cb1`.
No new image has been installed or booted yet. The single `serio_raw` target
uses the already validated one-job external-directory form, avoiding the
previous stage's competing builds.

The probe retains explicit original-page references for PFN (physical page
number), contents, mapcount and memory-charge ownership checks, then retires
every reference. An additional unreferenced case releases these test references
before real munmap, exercises normal final release, and deliberately does not
dereference freed pages. All originating CPUs repeat their earlier cached
access after unmap and must fault. A separate hardware fault to an untouched
neighbor must wait behind the writer and resolve normally after writer release.

Probe build attempt 1 failed at module symbol checking: `lru_add_drain` is not
exported by this kernel. No module loaded, installation started or boot changed.
The retained `test-build-1/build-module.log` and source snapshot are a failure,
not a pass. The follow-up probe uses the existing exported page-vector release
API to retire exact scratch references on the original pinned setup CPU; its
normal local LRU drain makes the same strict reference-count oracle usable.
No kernel candidate, admission check or ownership assertion changed.
