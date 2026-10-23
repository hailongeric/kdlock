# Retained-table boundary edge removal

Completed on **6.1.159-kdmm15**: **49 serial cases, two basic tests and 1,289
negative receipt controls passed**. The new path completed **26 different-task
removals**, including **14 without private-page holds** (temporary references).
Twelve representative
layouts matched native behavior. Two delegated post-split errors also matched
native return values and surviving layouts, without destructive replay.
Recovery is restored, both test modules are unloaded, and the VM is idle.

This is an implementation milestone, following the preserved
[kdmm14 baseline](../mm-missing-table-20261023/README.md). Kernel implementation:
`41caaacccb3c48b8cee51dcf2e2dcf19c35233fc`. Successful frozen build/probe inputs:
`f383451` (probe include-order correction; unchanged kernel source).
No historical matrix, nano run or timing campaign was repeated.

## Supported scope and mechanism

A VMA (virtual memory area) describes an address range. The new case removes
one 4-KiB page from a three-page private anonymous VMA spanning two adjacent
2-MiB PMD (page-middle-directory) intervals within one 1-GiB PUD
(page-upper-directory) interval. The target occupies its interval alone; both
survivors occupy the other interval. At boundary B and page size P:

| Direction | Original VMA | Removed range | Survivor interval |
| --- | --- | --- | --- |
| Prefix | `[B-P, B+2P)` | `[B-P, B)` | above B |
| Suffix | `[B-2P, B+P)` | `[B, B+P)` | below B |

The target PMD entry must be missing, meaning **no leaf PTE table exists**;
this differs from an empty PTE (page-table entry) in an existing table.
Survivors may be ordinary private resident pages (R), verified shared-zero
mappings (Z), or untouched addresses (U). Their table may itself be missing
only when both are untouched. All required upper levels must already exist.

Both outer neighbors are required. The preceding VMA must end inside the first
PMD interval; the following VMA must start inside the second. These actual VMA
bounds, not a populated survivor alone, establish retention. After the single
native split, prefix teardown uses the original preceding VMA's end and B as
floor/ceiling; suffix teardown uses B and the original following VMA's start.
The admission check mirrors native `free_pgd_range()` arithmetic and requires
its return before any table traversal. Native cleanup still runs; no table is
leaked or retained by bypassing required teardown. These neighboring VMAs are
an explicit supported-scope requirement, not general boundary-unmap support.

The caller prepares existing split descriptors, mapping-index reserves and
reverse-map links, which connect physical pages back to their mappings.
Under mmap write ownership, the combiner (the task servicing queued requests) revalidates layout,
neighbors, metadata and both table intervals. Private survivors use the same
strict classifier, exact references and nonblocking page locks as the old path.
Zero and untouched slots acquire no private-page ownership. Absent anonymous
metadata consumes no reverse-map links. The real native split/detach/unmap body
removes the target VMA range without allocating its missing table.
Completion checks exact parent/survivor table identities, unchanged table bytes,
survivor PTEs, accounting and exact resource retirement. See the maintained
[mechanism and retention proof](../../../../../kernel_integration/mmap_lock/UNMAP.md#boundary-crossing-edge-removal-with-retained-tables).

A handback returns unsupported work to its original waiter; its acknowledgment
(ACK) preserves exact request ownership. Sticky fallback makes later calls on
that address space execute locally. Errors after splitting remain admitted
returns and cannot trigger local replay.

## Validation

`focused-1` ran on one verified candidate boot. Native controls used the ordinary
munmap body on the same KD lock backend; they were not a Native-off boot.

| Cases | Count | Result |
| --- | ---: | --- |
| Prefix/suffix × RR, RZ, RU, ZZ, ZU, UU × native/delegated | 24 | 12 native-matched layouts; 24 remote completions |
| Post-split ENOMEM, both directions, native/delegated | 4 | Two remote errors; harmless split retained; no replay |
| Target table requires native destruction, both directions, native/handback | 4 | Exact ACK and sticky local route; one table released per selected operation |
| Existing retained target table, both directions | 2 | Explicit handback and sticky local route |
| Edge sharing a table interval with a survivor, both directions | 2 | Explicit handback and sticky local route |
| Queued cancellation, both directions | 2 | Victim VMA retained; caller resources retired |
| Controlled target-table appearance, native/handback | 2 | Locked revalidation refuses before split; exact ACK |
| Waiting survivor demand fault, native/delegated | 2 | Two further remote removals; local fault resolves after writer release |
| Busy final private survivor | 1 | Exact earlier hold released before refusal/ACK |
| Preservation smokes | 6 | Same-table missing target/cancellation, empty target with UZ survivors, zero target, private target, four-page whole removal |

There are 43 new-path cases and six preservation cases. Success comparisons
number 16: the 12 layouts plus two native table-free controls, table appearance
and the waiting fault. The two error comparisons are separate. Eight new-path
handbacks matched their ACKs; both new cancellation cases passed. Preservation
removal counts are separate from the 26 new-path completions.

ZR, UR and UZ were not repeated in this new boundary matrix. Both survivors are
adjacent entries in the same retained table, with the same per-slot classifier
and native surviving VMA; reversing their order introduces no new table geometry.
This is a representative reduction, not live coverage of those six reversed
boundary layouts. The busy-second-survivor case independently checks ordered
partial acquisition and exact rollback.

Before data access, read-only walks verify actual upper/leaf physical identities,
missing entries and R/Z/U states. The probe checks removed-address `SEGV_MAPERR`,
VMA bounds/offsets/flags, mapping counts, private resident accounting, reverse-map
links and page references. Neighbor mappings and PTE states remain exact.
Only then are survivors read and written: U demand-faults normally, Z reads zero,
private writes remain isolated, R contents remain intact, and an independent
zero mapping is unchanged. Full local cleanup removes every fixture and observes
missing upper entries, checking that retained tables are eventually released.

Examples from request-bound kernel receipts:

- `edge-target-prefix-rz`: origin **1846**, executor **1847**, request **2**;
  one private hold acquired/released, target unowned, tables unchanged.
- `edge-target-suffix-uu`: origin **1926**, executor **1927**, request **2**;
  both target and survivor tables missing, zero holds, native body completed.
- `edge-target-appear`: local reader **2006** creates the target table with two
  requests published, two reader shares and closed new-reader admission.
  Request **2**, origin **2003**, executor **2002**, subsequently hands back
  and ACKs exactly; the third call stays local. This is not a remote removal.

The deterministic appearance control is distinct from uncontrolled fault races.
The missing target has no positive cached translation to warm. Native TLB
(translation lookaside buffer) completion, removed-address faults, retained-table
identities and later demand faults were checked; private-target preservation
smokes also exercised positive translation invalidation. No claim is made about
all hardware TLB races or page-table reclamation races.

## Build, evidence and recovery

`build-1` failed while compiling the new client because `_GNU_SOURCE` followed
an earlier system include. No kernel compilation/install/boot occurred in that
attempt. The original source and failure log remain frozen. `build-2` fixes only
that include order, reuses six existing clients, runs the two basic tests once,
and builds the changed kernel plus required modules. Only
`mm/kd_mmap_unmap.inc` differs from kdmm14's captured kernel sources.
There were 3,157 dependency-triggered C compilations, including the two test
modules: the distinct kernel release regenerated shared build dependencies.
No clean/full-tree rebuild command was used.

Guest root had 661,934,080 bytes before the successful build, exceeding the
260,000,000-byte measured-cycle budget. Packaging and intermediates used RAM.
Root retained 435,597,312 bytes after recovery. No permanent deletion, snapshot
change, disk resize or VM configuration change occurred.

| Identity | Value |
| --- | --- |
| Run | `mm-boundary-edge-20261023 / build-2 / focused-1` |
| Candidate Build ID | `a87d2b5215bc87a1f31f8b503d8cac9887dd1644` |
| Candidate manifest SHA-256 | `a5c0854e903aa5bf267ac4bf60ecb138b60b768ae12ba51bb27b56d4dd933d83` |
| Candidate boot | `87836e45-6c0d-496e-8532-d206004537df` |
| Recovery boot | `b93f0ad4-02bb-4bf6-80b9-84377bd4e010` |
| Recovery Build ID | `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960` |
| Essential archive bytes | `713800` |
| Essential archive SHA-256 | `fb58c0efefe55a2ba9b2cd7d22aa87f4515fd678095f71afede6f26d784c1765` |

One [essential archive](../../raw/tests/mm-boundary-edge-20261023/collect-1/essential.tar.gz)
contains new logs, receipts and frozen source copies, including the failed build.
The [offline audit](../../raw/tests/mm-boundary-edge-20261023/collect-1/audit.json)
verified all 98 case-file hashes, 41 input hashes, 16 archived new probe source
hashes and different-task counts. Existing baseline archives were not recopied.
The live guest retains binaries and captured kernel identity under
`/root/kdlock-evidence/10.176.26.71/tests/mm-boundary-edge-20261023` and
`/root/kdlock-kernel-work/mm-boundary-edge-20261023` respectively.

The [final health record](../../raw/tests/mm-boundary-edge-20261023/final-health.json)
confirms recovery, all 73 original runtime modules, no test modules, idle state,
cleared one-shot boot selection and cleared RAM scratch. Recovery preservation
also verified 5,686 module-file hashes. No kernel fault/warning/panic matched the
run checks. Recovery again logged six `fd0` read-error lines, retained in its
transition evidence; these also occurred in the prior recovery record.

## Reproduction and limits

Use the installed artifacts on the same idle VM, after a quick capacity check.
Attempts already used are immutable. A new serial verification, with no build:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-edge-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-edge-20261023/workflow.py recovery --attempt 2
```

The [probe guide](../../../../../tests/kernel/mmap_lock/boundary_edge/README.md)
gives direct guest commands and exact modes. Do not reboot after a failed or
in-flight run until drain is established.

Existing target-side tables, target/survivor sharing across this boundary,
interior crossing, cross-PUD geometry, missing higher levels, huge/special
entries, complex ancestry and general delegated table destruction remain refused.
No neighbor-VMA replacement, uncontrolled fault/reclaim/pinning race, forced
allocation failure, post-admission cancellation or Native-off campaign was added.
Advice and first-write fault code did not change; their historical suites were
not repeated. The preservation set covers the shared page classifier and updated
probe cancellation path. Larger mappings, performance/p95, mutex regressions and
nano reruns remain deferred.

The next useful extension is an **existing target leaf table with an empty PTE**
in this same isolated-edge geometry, retaining the proven native floor/ceiling
rule and checking exact table identity. A private/zero target or general table
freeing should remain a separate later change.
