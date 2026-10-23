# kdmm21: empty target in a shared retained boundary table

Completed on the original `10.176.26.71:2222` VM: **69 serial cases, two basic
tests and 2,254 negative receipt controls passed**. All **18 new layouts** matched
native behavior. There were **42 different-task empty-target removals**, plus
**two converted-zero and two converted-private removals** after queued real
faults. Twenty-two empty removals and both converted-zero removals held no private
pages. Two delegated split errors, five new-path handback/acknowledgment (ACK)
pairs and two cancellations passed. Recovery is restored and modules unloaded.
No build, probe or live case failed or needed a retry. The completed
[kdmm20 campaign](../mm-boundary-shared-zero-20261023/README.md) was not repeated.

## Exact scope and mechanism

The kernel required a small change: the shared-table guard previously admitted
only private or shared-zero targets. It now explicitly permits `pte_none()` in
an **existing** target leaf table after the existing locked classifier succeeds.
PTE means leaf page-table entry; PMD means page-middle directory; VMA means
virtual memory area. An empty PTE is distinct from a missing PMD/PTE table,
swap/migration or other special non-present entry. Those states do not inherit
this admission. Huge/device mappings and missing higher levels remain refused.

For P = 4 KiB and a 2-MiB boundary B, both shapes retain `[B-P, B+P)`:

| Direction | Original VMA | Removed page | Survivor sharing target table | Other survivor |
| --- | --- | --- | --- | --- |
| Prefix | `[B-2P, B+P)` | `[B-2P, B-P)` | Slot 1 below B | Slot 2 above B |
| Suffix | `[B-P, B+2P)` | `[B+P, B+2P)` | Slot 1 above B | Slot 0 below B |

Both PMDs share an existing ordinary upper directory. The other leaf table may
be missing for an untouched far survivor. Both outer-neighbor guards remain
mandatory: preceding VMA end above the first PMD interval's base, following VMA
start below the second interval's end. The exact native `free_pgd_range()`
floor/ceiling calculation must return before walking tables. Neither a populated
neighbor PTE nor the near survivor replaces this proof.

Under actual mmap write ownership, the executor rewalks current VMA bounds,
ancestry, both neighbors, hierarchy and table identities. It checks the target
and each survivor under that table's PTE lock, without retaining an earlier
PTE pointer or crossing table boundaries with one pointer. Native splitting and
removal eliminate the virtual mapping even though there is no target page or
translation. No target is populated, no unrelated entry is cleared, and the
retention proof excludes table destruction. Post-body checks require the empty
target, original tables, survivor entries and unchanged table-byte accounting.

The empty target owns no page reference, page lock or reverse map (the metadata
linking physical pages to virtual mappings). Existing caller-prepared split VMAs,
mapping-index nodes and optional reverse-map links retain exact transfer and
retirement; absent ancestry is valid. Admission never depends on a nonzero hold
count. The existing `KD_MM_BOUNDARY_SHARED_EMPTY` receipt binds native completion
to the request and different executor. Queue ownership, ACK routing, cancellation
and sticky local fallback are unchanged. Readers remain concurrent and local.

## Focused validation

R/Z/U mean private resident/shared-zero/untouched survivors in increasing address
order. All nine pairs are needed: reversing a mixed pair changes its near/far
table role. A read fault on the target-side retaining neighbor creates the leaf
table without accessing the target. Read-only kernel walks verify `pte_none()`,
physical table identity and actual survivor states before publication. Native
controls execute the native body on the same KD-enabled image, not a Native-off
boot.

| Group | Cases | Outcome |
| --- | ---: | --- |
| Both directions × RR/RZ/RU/ZR/ZZ/ZU/UR/UZ/UU × native/delegated | 36 | 18 matched layouts, 36 remote empty removals |
| Queued empty-to-zero, both directions/routes | 4 | Two remote zero removals and two unchanged-empty removals |
| Queued empty-to-private, both directions/routes | 4 | Two remote private removals and two unchanged-empty removals |
| Queued private conversion becomes busy, both directions/routes | 4 | Two pre-effect handback/ACK pairs |
| Retention guard lost before publication, both directions/routes | 4 | Two ACKs; native retains the shared table despite conservative KD refusal |
| Post-split ENOMEM, prefix-RZ and suffix-UU, both routes | 4 | Two delegated errors match native harmless splits, target remains empty |
| Queued cancellation, both directions | 2 | Victim mapping and unused resources preserved/retired |
| Far-survivor fault waiting for writer release, both routes | 2 | Two empty removals; ordinary local fault creates other table afterward |
| Busy far private survivor | 1 | Earlier survivor hold released before exact ACK |
| Preservation/refusal smoke | 8 | Shared zero/private and isolated-empty paths; shared missing targets still refuse in both directions |

The **61 new cases** rejected **1,989** corruptions and made **27 native success
comparisons plus two error comparisons**. The eight smokes rejected **265**
corruptions, completed **12 old-path different-task removals** and checked two
additional ACKs, separate from the 46 new-path removals.

Checks cover removed-address faults, VMA bounds/offsets/flags, retained PTEs and
contents, exact private references, reverse-map state, RSS (resident-page
accounting), table lifetimes, neighbors and an independent shared-zero mapping.
Only after initial observations do untouched survivors fault in, zero survivors
receive isolated private writes, and retained pages prove normal writability.
The unchanged empty target has no valid translation to invalidate; it is never
faulted in just to test removal. Populated transition controls and preservation
probes check native PTE clearing and TLB (translation lookaside buffer) completion.
`zero_tlb_complete=0` identifies the empty class, not a zero-page teardown failure.
Full local cleanup observes the upper hierarchy absent and all workers/resources
retired before ordinary module unload.

Test-only modes 13/14 perform real local-reader read/write faults after three
requests are published, with two held readers and closed admission. No new reader
bypass or synthetic removal callback is used. The read owns no zero-page
reference; the write retains one exact GUP (`get_user_pages`) inspection reference.
Fresh locked execution selects the complete kdmm20 zero or kdmm19 private class.
Mode 15 locks the newly private page after two publications and requires handback
before effects, a matching ACK, and a sticky local third call. Post-split errors
remain admitted native-compatible errors, never destructive local replay.

Examples from the [audited receipts](../../raw/tests/mm-boundary-shared-empty-20261024/collect-1/audit.json):

- Prefix-RR request 2: origin **1906**, executor **1904**, target table **3538df**;
  empty target, two survivor holds/releases, table-slot masks **3/4**.
- Suffix-UU request 2: origin **2042**, executor **2040**, table **35338c**;
  **zero holds/releases**, other table absent, masks **6/1**.
- Prefix queued read: reader **2067** changes the empty target to zero PFN
  **3748** in table **34b7b6**. Request 3, origin **2064**, executor **2063**, then
  clears it through the zero path with no owned page and completed TLB teardown.
- Suffix queued write: reader **2119** creates private PFN **35a6e2** in unchanged
  table **355506**. Request 2, origin **2116**, executor **2115**, removes it;
  references **3 → 2** before KD's put. Busy conversion instead matches handback/ACK.
- Suffix error request 2: origin **2093**, executor **2092**, result **-12**;
  empty target and retained table **3501bd** unchanged, no local replay.

## Build, storage and evidence

Source **`9c81c0e8092a70c5d15e1b9ae3e5b4a01de0ef54`** changes only
`mm/kd_mmap_unmap.inc` among captured kernel sources. One new client and the
affected module were compiled; nine unchanged clients were reused. The distinct
release required 3,156 dependency-driven C compilations and 73 runtime modules
in the existing RAM overlay. There was one incremental build/install, one
candidate boot and one serial run, with no historical campaign repeated.

Only the **67 exact approved inactive objects** were deleted. The
[cleanup receipt](../../raw/tests/mm-boundary-shared-empty-20261024/cleanup/result.json)
records **84,987,904 bytes reclaimed**, root free **43,503,616 → 128,491,520**.
All [hash-verified recovery copies](../../raw/tests/mm-boundary-shared-empty-20261024/cleanup/backup-receipt.json)
remain in one source-host archive, SHA-256
`d3317531b311513657ef8b3391e5cf04b73d6f54b602ddabfeb569d8cb515ebd`.
Earlier backups, source, final kernels/modules, recovery and unique results remain.

The measured root budget was 120,000,000 bytes, including margin and recovery
retention, with compressed kernel identity stored on the source host. Root free
was 127,660,032 before build, 122,626,048 before install and 48,553,984 afterward.
The remaining boot/test budget was 15 MB. Final free space is **43,544,576 bytes
(41.53 MiB)**, insufficient for another equivalent build. RAM use was
5,244,764,160 bytes within its 8-GB budget. No further deletion is authorized.

| Identity | Value |
| --- | --- |
| Run | `mm-boundary-shared-empty-20261024 / build-1 / focused-1` |
| Kernel | `6.1.159-kdmm21` |
| Build ID | `07e9383411282db8aa151acf9c38d2db13108d52` |
| Manifest SHA-256 | `d70a5f893da2dc8da9afd734c241eed64a6084a6c1af9b1c0c7b8fb752bbc0fc` |
| Candidate boot | `fe7bab13-2f4c-4665-a15a-aa04a40ff6a5` |
| Recovery boot | `7234dcc5-a62e-4fdf-80fa-4618a7b56b94` |
| Essential archive | 633,395 bytes; SHA-256 `160377bfa9612348c0449cab42320170a34f78b8c8d90bdf634246eda3057634` |

The [single essential archive](../../raw/tests/mm-boundary-shared-empty-20261024/collect-1/essential.tar.gz)
and audit bind **47 frozen inputs, 30 maintained probe sources and 138 case-file
hashes**, with generated module metadata separate. The
[compressed identity receipt](../../raw/tests/mm-boundary-shared-empty-20261024/identity/receipt.json)
binds the one source-host kernel copy. No old archive was copied or rescanned.
[Final health](../../raw/tests/mm-boundary-shared-empty-20261024/final-health.json)
verifies idle recovery `6.1.159-kdclobber2`, original Build ID, 73 runtime modules,
5,686 recovery-module hashes, no test modules, cleared one-shot selection and
released candidate RAM scratch. The [original snapshot and placement](../../raw/tests/mm-boundary-shared-empty-20261024/final-host.json)
remain intact. No kernel fault was recorded; six historical `fd0` read-error
lines remain distinguishable in the health evidence.

## Commands and remaining gaps

The [probe guide](../../../../../tests/kernel/mmap_lock/boundary_shared_empty/README.md)
documents controls and direct guest invocation. On the source host, after
checking idle state and current boot/log capacity, reuse the installed image
with fresh attempt numbers. Attempt 1 is immutable; no build is required:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-empty-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-empty-20261024/workflow.py recovery --attempt 2
# Optional source-host, read-only evidence check:
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-empty-20261024/audit.py
```

Queued neighboring-VMA replacement remains untested: it requires writer ownership
while this fixture holds reader shares. A separate writer-owned queue gate is
needed; same-address reuse is not evidence that an old VMA/table pointer remains
valid. Retention loss here occurs before publication. Controlled target faults
do not establish uncontrolled fault/reclaim/pinning race coverage. Special-entry
injections, forced allocation failure, post-admission cancellation, Native-off
controls and broad memory-cgroup/swap/allocator-reuse cases remain untested.
Missing target tables in this shared geometry, interior removal, larger VMAs,
complex ancestry and general table destruction remain out of scope.

The next small extension is a missing target table with an untouched near
survivor. It requires explicit handling that never walks a PTE in either missing
slot, plus the same neighbor proof and feasible-geometry validation; removing
the remaining guard alone would be unsafe. Performance, p95, the seven mutex
regressions and nano reruns remain deferred.
