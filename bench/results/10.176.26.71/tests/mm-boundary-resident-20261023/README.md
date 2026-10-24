> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# kdmm18: ordinary private target at a retained boundary

Completed on the original `10.176.26.71:2222` VM. **48 serial cases, two basic
tests and 1,238 negative receipt controls passed**, with **24 verified
different-task private-target removals**, including **two without a probe
reference during execution**. Ten representative layouts matched native
behavior. Two delegated split errors, seven handback/acknowledgment (ACK) pairs
and two queued cancellations passed. Recovery is restored and test modules are
unloaded. The [kdmm17 baseline](../mm-boundary-zero-20261023/README.md), its full
matrix and reversed-layout campaign remain separate; none was repeated.

## Mechanism and supported scope

For page size P = 4 KiB and a 2-MiB PMD (page-middle-directory) boundary B:

| Shape | Three-page anonymous VMA (virtual memory area) | Removed range | Native retention bounds after split |
| --- | --- | --- | --- |
| Prefix | `[B-P, B+2P)` | `[B-P, B)` | Original preceding VMA end to B |
| Suffix | `[B-2P, B+P)` | `[B, B+P)` | B to original following VMA start |

The target occupies its interval alone; both survivors occupy the adjacent one,
within the same valid upper directory. Both outer neighbors remain mandatory:
preceding end above the first interval's base, following start below the second
interval's end. Native `free_pgd_range()` rounding must return before a table
walk. Merely finding another populated PTE (leaf page-table entry) is insufficient.

The executor, under actual mmap write ownership, rewalks current VMA bounds,
upper levels, target PTE/table and both neighbor bounds. No prepublication table
or neighbor pointer supplies eligibility. A target uses the existing same-table
private-page classifier: writable present ordinary PTE, exclusive base anonymous
page, mapcount one, simple reverse-map ancestry, no compound/swap-cache/poisoned/
reserved state or native indication of a DMA pin. A reverse map associates a
page with its virtual mappings. `trylock_page()` refuses a busy page without
waiting under the PTE lock. Shared/COW (copy-on-write), huge/device/special and
otherwise unsupported states remain refused.

One exact temporary reference and page lock protect each admitted private page.
The target joins the existing slot-indexed hold array; every later refusal now
retires it along with any earlier survivor hold. Caller-prepared VMA,
mapping-index and reverse-map resources handle splitting without executor-side
allocation. One removed base page fits the native stack-local gather; no general
table destruction is admitted. Missing, empty and shared-zero targets retain
their separate non-ownership handling.

The real native body clears the target PTE, updates RSS (resident-page accounting)
and reverse maps, completes TLB (translation lookaside buffer) invalidation, and
drops the mapping reference. Only then does KD unlock and put its temporary
reference. Success checks the original physical target, zero mappings and empty
target entry; errors after splitting require the original PTE and one mapping.
Both require unchanged parent/leaf identities and table accounting. No admitted
error replays locally. Exact queue ownership, ACK, sticky local fallback,
cancellation and caller-resource retirement remain unchanged. Readers stay
concurrent and local. See the maintained
[execution flow](../../../../../kernel_integration/mmap_lock/UNMAP.md#private-target-in-a-retained-boundary-table).

## Focused results and page lifetimes

`focused-1` ran once on one candidate boot. Native controls call ordinary native
munmap on the same KD backend; they are not a Native-off boot. R/Z/U denote
private resident/shared-zero/untouched survivors in increasing address order.

| Group | Cases | Result |
| --- | ---: | --- |
| Prefix/suffix × RR/RZ/RU/ZU/UU × native/delegated | 20 | Ten matched layouts, 20 different-task removals |
| Drop probe references before execution, both directions, native/delegated | 4 | Two different-task final-reference removals |
| Waiting survivor fault, native/delegated | 2 | Two different-task removals; fault completes locally after writer release |
| Post-split ENOMEM: prefix-RZ and suffix-UU, native/delegated | 4 | Two delegated errors match native harmless splits and intact target mappings |
| Retention loss, both directions, native/handback | 4 | Two exact ACKs; native releases one target leaf table |
| Queued target becomes busy, both directions, native/handback | 4 | Same page/table/ancestry, no added reference, pre-effect handback and ACK |
| Unsupported shared-interval geometry, both directions | 2 | Two pre-effect handbacks and sticky fallback |
| Busy last private survivor | 1 | Target plus earlier survivor holds both released before the ACK |
| Queued cancellation, both directions | 2 | Victim mapping preserved; no stranded ownership/resources |
| Preservation smokes | 5 | Missing/empty boundary, two zero-boundary and one same-table resident case |

The **43 new-path cases** rejected 1,101 corrupted receipts/observations and
made 17 native success comparisons plus two separate native error comparisons.
The **five smokes** rejected 137 corruptions and produced eight boundary
removals (two missing, two empty, four zero) plus two same-table resident
removals, excluded from the 24 new-path count.

This representative private-target matrix omits ZR/UR/UZ/ZZ in each direction.
RZ/RU/ZU cover each mixed survivor-state pair; RR and UU cover three holds versus
only the target hold and a missing survivor table. Reversing survivors or
repeating zero classification does not change the newly added target ownership
path. Those survivor branches already have separate kdmm17 coverage. The eight
omitted private-target layouts are **not claimed as newly tested**.

Read-only observations precede survivor accesses. They verify real PTE states,
original target/survivor identities, VMA bounds/offsets/flags, map and RSS counts,
reverse-map links, exact references and retained tables. Removed addresses fault
on their originating CPU after warmed translations. U survivors remain absent
until the intentional fault/access phase; Z reads and subsequent isolated private
writes preserve other survivors, both neighbors and an independent zero mapping.
Full local cleanup removes all fixtures and observes the upper hierarchy absent.

Most cases use ordinary probe references to inspect pages after logical
unmapping: before the native body the target has mapping + probe + KD references
(3), after native teardown probe + KD (2), and after KD's put only the probe (1).
`UB_DROP` releases that probe reference after cleanup. These tests do not claim
immediate physical reclamation. The `free` controls drop all probe references
before publication: KD observes 2 then 1, performs the final put, and never
dereferences the freed page afterward. This exercises the native final-reference
release path; allocator/buddy reuse is not separately traced.

Request-bound examples from the archived receipts (physical frame numbers in hex):

- Prefix-RR request 2: origin **1905**, executor **1906**, target **34ac07**;
  three holds/releases, refs **3 → 2** before KD's put, mapcount 0.
- Suffix-UU `free` request 2: origin **2052**, executor **2051**, target
  **35d31f**, missing survivor table, one hold/release, refs **2 → 1**, final put.
- Suffix-UU error request 2: origin **2029**, executor **2028**, target
  **359e47**, result **-12**, refs **3 → 3**, original PTE/mapcount 1 preserved.
- Queued busy prefix: local reader **2005** locks original target **34caf6**
  with two requests published, two reader shares and closed admission. Request 2,
  origin **2002**, executor **2001**, then hands back and receives its matching
  ACK. It is not counted as a remote removal.

## Build, storage, evidence and recovery

Implementation commit **`5172bf5376ce9a90851bce757fd2abca730a29fd`** changes only
`mm/kd_mmap_unmap.inc` among captured kernel sources. One new client and the
affected test module were compiled; six unchanged clients were reused. The
distinct kernel release triggered 3,155 dependency-driven C compilations and 73
runtime modules. No clean/full-tree build command or repeated basic run was used.
Both basic programs, syntax, build, installation and all live cases passed.

Root initially had 42,450,944 bytes. Only the four explicitly approved inactive
objects (`fs/btrfs/btrfs.o`, `arch/x86/kvm/kvm.o`, `drivers/gpu/drm/drm.o`,
`arch/x86/boot/compressed/piggy.o`) were removed from the old candidate build
tree, reclaiming 84,897,792 bytes. See the exact-path
[proposal](../../raw/tests/mm-boundary-resident-20261023/cleanup/proposal.json),
[verified recovery copies](../../raw/tests/mm-boundary-resident-20261023/cleanup/backup-receipt.json)
and [deletion receipt](../../raw/tests/mm-boundary-resident-20261023/cleanup/result.json).
No source, captured identity, recovery input, unique result or active file was
deleted. Earlier approved recovery copies remain intact.

The 120,000,000-byte root budget derives from prior measured cycle growth minus
the compressed identity, plus observed boot growth and 37,835,084 bytes margin.
The new **142,633,372-byte** compressed identity is retained once on the source
host and staged in guest RAM for verification. Root had 126,472,192 bytes before
build, 121,536,512 before install, 47,468,544 afterward and **43,220,992 bytes
(41.22 MiB)** after recovery. RAM budget was 8,000,000,000 bytes; actual retained
build/identity consumption was 5,243,121,664. Another cycle must first establish
its own adequate headroom; the final root state is below this cycle's budget.

| Identity | Value |
| --- | --- |
| Run | `mm-boundary-resident-20261023 / build-1 / focused-1` |
| Candidate | `6.1.159-kdmm18` |
| Build ID | `a2591270bf009b08420a583da48fce9c6c97ad1f` |
| Manifest SHA-256 | `e4a5579b3b48113945bf5165c3a28df6fca057b49814a2a784981e35c5be746c` |
| Candidate boot | `8e060759-7142-43fa-8f21-3aed1f832199` |
| Compressed identity SHA-256 | `530b504cb3eda0476fbf8cc46d28cd3d5b3e0bc6055286e788cfefb879e64f9d` |
| Recovery boot | `98fa9969-c50d-4811-9791-7dadc9360676` |
| Essential archive | 609,028 bytes; SHA-256 `30bb6875705d93c3632decc82344aff9d91b1815f9c2a7048d98955c589f5d47` |

One [essential archive](../../raw/tests/mm-boundary-resident-20261023/collect-1/essential.tar.gz)
and its [audit](../../raw/tests/mm-boundary-resident-20261023/collect-1/audit.json)
bind 38 frozen input hashes, 21 archived maintained probe sources, 96 case-file
hashes and the counts above. Generated module metadata is recorded separately.
The initial inline audit misclassified that generated file as a Git input;
its [failure record](../../raw/tests/mm-boundary-resident-20261023/collect-1/audit-initial-failure.json)
is retained. Two read-only inspection helpers also initially failed (missing
Python import path and an older native function name); corrected inspections
remain alongside them. None was a kernel, build, installation or live-test
failure. No old archive was recopied or audited, and no live case was repeated.

[Final recovery health](../../raw/tests/mm-boundary-resident-20261023/final-health.json)
verifies idle `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, all 73 original runtime modules,
5,686 preserved module-file hashes, no test modules, cleared one-shot selection
and all three new RAM scratch paths absent. Snapshot and placement remain
verified. No kernel fault matched the run/recovery checks; the six historical
`fd0` read-error lines remain recorded.

## Commands, remaining gaps and next step

Reuse the installed candidate only on the idle original VM after a current
boot/log capacity check. No build is needed; use fresh attempt numbers:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-resident-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-resident-20261023/workflow.py recovery --attempt 2
# Optional read-only source-host evidence verification:
python3 bench/results/10.176.26.71/tests/mm-boundary-resident-20261023/audit.py
```

The [probe guide](../../../../../tests/kernel/mmap_lock/boundary_resident/README.md)
contains direct guest commands and modes. Preserve the source-host compressed
identity and its [receipt](../../raw/tests/mm-boundary-resident-20261023/identity/receipt.json);
the workflow restores it to RAM after candidate boot. Completed directories are
immutable. Never reboot an in-flight or undrained failed run.

Retention loss was changed **before publication**. Queued neighboring-VMA
replacement cannot run inside the fixture's existing reader shares without
conflicting writer ownership; no bypass or synthetic hook was added. The kernel
uses current native bounds under the writer, not an old address/pointer match,
but that queued replacement race remains untested. The deterministic busy
transition does not cover uncontrolled fault/reclaim/pinning races. Queued
empty/zero-to-private target transitions were not newly exercised; their former
blanket private-target refusal expectations do not describe kdmm18's supported
class. Unsupported COW/huge/special/DMA-pinned states retain guards but were not
newly injected. Forced allocation failure, post-admission cancellation and
Native-off controls remain untested. Larger VMAs, interior crossing, complex
ancestry and general table destruction remain outside scope.

The next narrow geometry extension is prefix/suffix removal when one survivor
shares the target table and the other lies across the boundary, retaining the
same native neighbor proof. It requires per-slot table classification and exact
hold rollback across both tables; the current `shared` controls explicitly
refuse it. Performance tuning, p95, mutex regressions and nano reruns stay deferred.
