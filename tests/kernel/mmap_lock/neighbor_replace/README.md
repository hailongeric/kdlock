# Queued neighboring-VMA replacement on kdmm22

This correctness probe closes the writer-gate gap left by the
[missing shared-table milestone](../boundary_shared_missing/README.md).
It changes only test code. The installed **6.1.159-kdmm22** kernel, its admission
rules and native table-retention requirements are unchanged. A VMA is a virtual
memory area; a PTE is a leaf page-table entry.

## Mechanism and scope

Each target remains a three-page anonymous VMA crossing one 2-MiB boundary.
The request removes one prefix/suffix page, with one near survivor in the
target table range and one far survivor across the boundary. The missing-table
class requires an untouched near survivor and existing upper levels. Empty,
shared-zero and ordinary private targets reuse their complete existing checks.

The retaining neighbors are untouched, read-only, one-page test-device VMAs.
Native `mremap` relocates one neighbor farther from the target. Its VMA callback
runs after the destination VMA is copied but before the old VMA is retired,
with the actual mmap writer lock held. At this pause the old VMA is still the
nearest neighbor. Real `munmap` callers publish their prepared requests; local
read/write trylocks both fail. The controller releases only the scheduling
pause. Native code retires the old VMA, records the new nearest neighbor under
the same writer, and releases its own lock normally. The combiner then acquires
the writer and rewalks current VMA/table/retention state. It borrows no owner.
The native relocation itself is **not delegated** or counted as a remote body.

For target VMA `[L,L+3P)`, P = 4 KiB, initial neighbors are
`[L-2P,L-P)` and `[L+4P,L+5P)`. A `keep` move shifts the selected neighbor
outward by P; a `lose` move shifts it outward by 2 MiB. Admission still requires
both current outer neighbors: preceding end above the first table interval's
base and following start below the second interval's end, followed by the exact
native `free_pgd_range()` floor/ceiling proof. Loss of either prerequisite causes
pre-effect waiter handback, matching acknowledgment (ACK), then sticky local
fallback for the third request. No partially executed removal is replayed.

The callback and native close receipt bind old/new VMA identities, writer task
and owner, pending count, zero readers, unchanged typed-body counters and
VMA/page-table accounting. The destination can gain a table through native
`mremap` when its source table exists; this allocation occurs in the caller
before publication and is accounted separately. Missing-target cases never
allocate the missing target table merely to remove the target.

No neighbor data access occurs before target PTE, residency and layout snapshots.
Later neighbor reads map one module-owned ordinary zero-filled page, **not** the
kernel shared zero page. Its mapping count, exact references and VMA lifetimes
are checked before access, after access and after cleanup. Target survivors and
an independent shared-zero mapping retain their existing content/PTE/isolation
checks. Creating survivor mappings cannot restore either removed address.

## Validated cases

The [result record](../../../../bench/results/10.176.26.71/tests/mm-neighbor-replace-20261024/README.md)
contains **38 serial cases, two basic tests and 1,241 negative receipt controls**:

- Missing table: prefix and suffix, either neighbor side, preserving/loss moves,
  each with native-body and KD routes. Near stays untouched; far private/zero
  layouts cover successful moves, and far untouched layouts cover loss.
- Empty, shared-zero and private targets: one preserving and one loss case each,
  with native controls and opposite edge directions.
- Native/KD post-split ENOMEM in both directions; two queued cancellations.
- Four unchanged smoke clients preserve missing/empty/zero/private paths and
  their concurrent local-reader gate.

There are **seven different-task removals of the VMA whose neighbor changed**,
plus seven different-task peer removals in those queues. Eight of those 14
removals hold no private pages. Seven retention-loss ACK pairs, two delegated
split errors and two cancellations passed. The four smokes add eight separately
counted remote removals. Local fallback and native queue heads are not counted.

## Commands

Run orchestration from the source host. The committed workflow checks the
original snapshot, idle VM, placement, kernel identity, frozen inputs and capacity.
Completed attempt 1 is immutable. With the preserved installed kdmm22 image and
this stage's built probes, a deliberate new run uses:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-neighbor-replace-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-neighbor-replace-20261024/workflow.py recovery --attempt 2
```

On an already identity-verified kdmm22 boot, `run --attempt 2` avoids a reboot.
The completed run used `prepare`, `build`, `kd`, `recovery`, and one `collect`;
`build` compiles only the module and four clients. Do not run it into completed
paths or rebuild the kernel. These underlying guest commands illustrate the
fixture inputs; use the serial runner to capture kernel receipts and validate:

```sh
cd /root/kdlock-evidence/10.176.26.71/tests/mm-neighbor-replace-20261024/probes-1
# Only on a verified kdmm22 boot, with this stage's test module loaded:
./neighbor_replace/client-missing native prefix-ur keep-left
./neighbor_replace/client-missing target prefix-ur keep-left
./neighbor_replace/client-missing target suffix-uu lose-right
./neighbor_replace/client-zero target suffix-uu keep-right
./neighbor_replace/client-missing target suffix-uu keep-right error
./neighbor_replace/client-missing target prefix-uu keep-left cancel
```

## Limits

This is a deterministic old-neighbor retirement control, not an uncontrolled
mapping race. Destination creation precedes publication; old retirement follows
publication. Same-address replacement, populated neighbor movement, target-VMA
replacement, forced native relocation allocation failure and uncontrolled
fault/reclaim/pinning races remain untested. Empty/zero/private cases are focused
representatives, not new full matrices. Reader concurrency is covered by the
four smokes; the writer gate correctly excludes readers while held.

No production support is added for interior crossing, larger VMAs, complex
ancestry, missing higher levels, huge/special entries or general table destruction.
The next functional candidate is one-page interior removal in the same boundary
geometry, after separate two-split retention and error analysis. Performance,
p95, mutex regressions and nano reruns remain deferred.
