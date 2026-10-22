# Minimal anonymous write-fault body

Status: the separate `kdmm3` kernel and its 73 runtime modules built successfully.
Live correctness is not yet validated. The validated [VMA advice body](BODY.md),
its installed `kdmm2` image and the recovery kernel remain preserved. Performance,
p95 latency and the seven mutex regressions are deferred.

## Selected boundary

A virtual memory area (VMA) describes one mapping. A page-table entry (PTE) maps
one virtual page to physical memory. The real x86 fault route is
`exc_page_fault -> do_user_addr_fault -> handle_mm_fault -> handle_pte_fault ->
do_anonymous_page`. For a first write to an ordinary anonymous page, the selected
body is its final PTE installation, including reverse mapping and resident-page
accounting. The original local route and combiner call the same extracted
`do_anonymous_page_install()` body.

Page allocation, zeroing, memory-cgroup charging, throttling, access checks,
task fault accounting and subsequent retry handling remain on the caller.
The combiner receives an explicit originating task, mm (address space), fault
record, prepared page and PTE value. It rechecks eligibility and PTE emptiness
under the real PTE spinlock before effects. A successful installation transfers
the prepared page to that PTE exactly once. Remote resident-page accounting
targets the explicit mm, avoiding the executor's deferred per-task counter.

Support is limited to private anonymous first-write faults in an explicitly
enabled address interval with `MADV_NOHUGEPAGE`. File/device callbacks, huge or
locked mappings, growing stacks, userfaultfd, memory policies and remote-access
faults are refused. Read faults remain entirely local. Multi-generation LRU
(a page-reclaim policy) uses implicit caller state; that configuration is refused
and is disabled in the captured kernel. The captured x86-64 `update_mmu_cache`
helper is empty. No arbitrary fault callback or JIT image is admitted.

## Readers, ownership and handback

The advice queue takes mmap write ownership. Reusing that gate for faults would
deadlock against the originating tasks' retained mmap read acquisitions. The
fault path instead uses a separate per-mm KD physical mutex and its independent
delegation queue, sharing the existing preallocated CPU/slot nodes and OSQ links.
OSQ is the optimistic-spin queue used to acquire the physical mutex. This gate
serializes only opted-in write-fault installation requests; mmap readers retain
their local acquisitions and can run concurrently with the combiner.

Each synchronous request retains its mm and caller stack until its queue link
and both node memberships retire. Only the exact physical gate owner may execute
the body. Unsupported requests set a permanent native-only flag for this mm's
fault entry. The advice entry has a separate flag and remains unchanged.

For a remote refusal, the origin verifies its exact node, mm, task and physical
owner before acknowledging the refusal. The ACK (acknowledgment) ends that
borrowed request; the physical owner then detaches it and publishes DONE. Only
after DONE and node retirement does the origin resume the existing native fault
tail. In particular, the combiner never waits for a userfaultfd handler while
retaining its own read share: that handler can require a mmap writer. This ACK
records refusal/ownership retirement, not completion of a native fault body.

A pending fatal-signal cancellation stays linked until consumed by the owner.
Before effects, cancellation leaves the prepared page with the origin. Only
the origin frees it, releases its exact mmap read acquisition and returns
`VM_FAULT_RETRY`. This edge is available only when retry can release the lock;
`RETRY_NOWAIT` is excluded. Cancellation after admission cannot replay effects.
No bounded cancellation latency or general oversubscription progress is claimed.

## Validation plan

Use only the original `10.176.26.71:2222` MM VM, one writer, and serial checks.
Keep Native control, advice preservation, actual page-fault body, cancellation,
fault retry/lock release and untouched mmap workloads distinct. Actual completion
requires differing origin/executor task IDs, the installed PTE's physical page
number, resulting memory contents and exact queue/owner/ACK cleanup. Local
fallback and control callbacks do not count as delegated bodies.

The [stage record](../../bench/results/10.176.26.71/tests/mm-fault-body-20261022/README.md)
will retain working commands, source identities, failures and untested cases.
