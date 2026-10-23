# kdmm19: private target sharing a retained boundary table

Completed on the original `10.176.26.71:2222` VM: **69 serial cases, two basic
tests and 1,954 negative receipt controls passed**. All **18 new layouts** matched
native behavior; **44 new removals completed in a different task**, including
two with no probe reference during execution. Two delegated split errors, five
new-path handback/acknowledgment (ACK) pairs and two cancellations passed.
Recovery is restored and test modules are unloaded. No build or live test
failed or needed a retry. The [kdmm18 baseline](../mm-boundary-resident-20261023/README.md)
and earlier campaigns were not repeated.

## Mechanism and scope

P = 4 KiB; B is a 2-MiB PMD (page-middle-directory) boundary. A VMA is a virtual
memory area. Both directions leave the surviving VMA at `[B-P, B+P)`:

| Shape | Original VMA | Removed page | Survivor sharing target table | Other survivor |
| --- | --- | --- | --- | --- |
| Prefix | `[B-2P, B+P)` | `[B-2P, B-P)` | Slot 1, below B | Slot 2, above B |
| Suffix | `[B-P, B+2P)` | `[B+P, B+2P)` | Slot 1, above B | Slot 0, below B |

The old code assumed both survivors used the other leaf table. The executor now
classifies and verifies each slot in its actual table, under mmap write ownership
and that table's PTE (leaf page-table entry) lock. It never holds two PTE locks
or carries a PTE pointer across the boundary. The other table may be absent when
its survivor is untouched. Both PMDs must share a valid upper directory; no
missing higher level or huge/special entry is admitted.

The two outer-neighbor guards are unchanged: preceding VMA end above the first
PMD interval's base, following VMA start below the second interval's end. The
exact native `free_pgd_range()` floor/ceiling calculation must return before
walking any table. Prefix bounds are preceding-end to removed-end; suffix
bounds are removed-start to following-start. Mere populated PTEs never substitute
for the guards. Current VMA bounds, table identity and entries are rewalked under
the writer; no prepublication neighbor/table pointer establishes admission.

Only the kdmm18 private target class is extended: ordinary writable exclusive
base anonymous page, one mapping, simple reverse-map ancestry, no compound,
swap-cache, reserved, poisoned or native DMA-pin indication. A reverse map links
a physical page to its virtual mappings. Busy pages refuse through a nonblocking
page lock. Zero, empty and missing-table targets in this new geometry remain
explicitly refused, while their old isolated-edge paths still work.

Caller-prepared split VMAs, mapping-index nodes and reverse-map links are reused.
Each private slot has one exact temporary reference and page lock; zero and
untouched slots own neither. A later refusal releases all earlier holds before
handback. Native removal clears the target PTE, updates reverse maps and RSS
(resident-page accounting), completes TLB (translation lookaside buffer)
invalidation and drops the mapping reference before KD releases its hold.
Both tables and surviving PTEs must remain unchanged. An error after a successful
split returns the native-compatible result with the original target intact;
it never permits destructive local replay. Queue ownership, ACK routing, sticky
local fallback, cancellation and caller-resource retirement are unchanged.
Readers remain concurrent and execute locally.

## Focused evidence

R/Z/U mean private resident/shared-zero/untouched survivors in increasing address
order. All nine pairs are needed because near and far table roles differ. Native
controls invoke the ordinary native body on the KD-enabled boot, not a separate
Native-off boot.

| Group | Cases | Outcome |
| --- | ---: | --- |
| Prefix/suffix × RR/RZ/RU/ZR/ZZ/ZU/UR/UZ/UU × native/delegated | 36 | 18 matched layouts, 36 different-task removals |
| No probe holds, both directions, native/delegated | 4 | Two different-task final-reference removals |
| Queued near-survivor U-to-Z read fault, both directions, native/delegated | 4 | Four remote removals; two follow the controlled change |
| Far-survivor fault waiting for writer release, native/delegated | 2 | Two remote removals; local fault creates the previously absent other table afterward |
| Post-split ENOMEM: prefix-RZ and suffix-UU, native/delegated | 4 | Two delegated errors match native harmless splits, without replay |
| Outer-neighbor retention guard lost, both directions, native/handback | 4 | Two exact ACKs; native retains both tables in this shared geometry |
| Queued target becomes busy, both directions, native/handback | 4 | Same page/table/ancestry; pre-effect handback and two ACKs |
| Busy far private survivor | 1 | Target and near-survivor holds both released before ACK |
| Queued cancellation, both directions | 2 | Victim mapping preserved, resources retired |
| Preservation and unsupported-class smokes | 8 | Two old private, missing/empty/zero isolated-edge cases; three new-geometry target-class refusals |

The **61 new-path cases** rejected 1,714 corruptions, made 27 native success
comparisons and two separate error comparisons. The **eight smokes** rejected
240 corruptions, produced ten old-path remote removals and three refusal/ACK
pairs, kept separate from the 44 new removals.

Read-only walks prove actual initial PTE/table states without populating U
survivors. Checks cover removed-address faults after warmed translations on the
originating CPU; surviving bounds, offsets, flags and contents; exact physical
identity, page references, reverse maps, RSS and table accounting; neighbors and
an independent shared-zero mapping. Only after those observations do U survivors
read-fault, Z survivors receive isolated private writes, and all retained pages
prove normal writability. Full local cleanup observes the upper hierarchy absent.

The queued near-survivor control reuses the existing real `get_user_pages()` read
fault under an already-held local reader share. It runs after three publications,
with two readers and closed admission. It changes slot 1 from empty to shared
zero in the target's existing table, without a new private reference, leaf table
or ancestry change. Locked body revalidation preserves the newly created zero
PTE. This is a deterministic pre-execution transition, not uncontrolled race
coverage. Moving an outer neighbor occurs before publication. Native retains
the target table because the near survivor remains; KD still requires its outer
guard and safely hands back. The historical mode name `free-table` does not mean
that a table must be freed in this geometry.

Request-bound examples, with physical frame numbers in hexadecimal:

- Prefix-RR request 2: origin **1920**, executor **1919**, target **346f31**;
  three holds/releases; refs **3 → 2** before KD's put; table-slot masks **3/4**.
- Suffix-UU `free` request 2: origin **2132**, executor **2131**, target **35f6aa**;
  refs **2 → 1**, then final put; other table absent; table-slot masks **6/1**.
- Suffix queued read: local reader **2142** creates zero PFN **3748** at index 4
  in table **353c63**. Request 2, origin **2139**, executor **2138**, then removes
  target **34ef40**, preserving zero-mask **2** and the same table.
- Suffix error request 2: origin **2109**, executor **2108**, result **-12**;
  target **35fe58**, refs **3 → 3**, original PTE and mapcount one retained.

Ordinary cases hold a probe reference through post-body inspection; they prove
logical unmapping and balanced lifetime, not immediate physical reclamation.
The two `free` cases drop every probe reference before publication and execute
the final KD put after native teardown. No freed page is inspected afterward;
allocator/buddy reuse is not separately traced.

## Build, storage and recovery

Source commit **`ee7e6ee9d9d29b14172aa4aea31d61da4c9a9707`** changes only
`mm/kd_mmap_unmap.inc` among captured kernel sources. One new client and the test
module were compiled; seven client executables were reused. The distinct release
triggered 3,155 dependency-driven C compilations and 73 runtime modules. There
was one incremental build/install, one candidate boot and one serial run.

Only the nine explicitly approved inactive intermediates were removed. Exact
paths and hashes are in the [cleanup receipt](../../raw/tests/mm-boundary-shared-20261023/cleanup/result.json);
[hash-verified recovery copies](../../raw/tests/mm-boundary-shared-20261023/cleanup/backup-receipt.json)
remain on the source host. This reclaimed 85,442,560 bytes, bringing free root
space to 128,638,976 bytes. No source, recovery or unique evidence was deleted.

The enforced root budget was 120,000,000 bytes, derived from measured prior
persistent growth with the compressed identity kept on the source host, boot
growth and margin. Root had 127,787,008 bytes before build, 122,826,752 before
install, 48,721,920 after build/install and **43,732,992 bytes (41.71 MiB)** after
recovery. RAM consumption was 5,243,170,816 bytes within the 8-GB budget. Another
build cycle needs new headroom; this final free space is not sufficient for the
same budget. No further cleanup is authorized by this record.

| Identity | Value |
| --- | --- |
| Run | `mm-boundary-shared-20261023 / build-1 / focused-1` |
| Candidate | `6.1.159-kdmm19` |
| Build ID | `08092986b4ac201a04188efd4ab9b3c4aef0c3c2` |
| Manifest SHA-256 | `b446a73b57a575adb3eb794d293cd68b4104fc91856943f50843ef2738f19c74` |
| Candidate boot | `d53be731-2ceb-410f-9979-ad668105267d` |
| Compressed identity | 142,639,416 bytes; SHA-256 `0ffbd4a1d27972e93e0f7b08a7b5125aec719827717dba73495f629ad169db8a` |
| Recovery boot | `ea783c70-678c-4c7b-8f74-750521b07c18` |
| Essential archive | 632,499 bytes; SHA-256 `975d4b8b63788fd31584abd757fdbc3d242eaaa37a5b346b5a58602520f87c37` |

The single [essential archive](../../raw/tests/mm-boundary-shared-20261023/collect-1/essential.tar.gz)
and [audit](../../raw/tests/mm-boundary-shared-20261023/collect-1/audit.json) bind 41
frozen inputs, 24 archived maintained probe sources and 138 case-file hashes.
Generated module metadata is recorded separately. The compressed kernel identity
is retained once on the source host; see its [receipt](../../raw/tests/mm-boundary-shared-20261023/identity/receipt.json).
No old archive was copied or rescanned.

[Final health](../../raw/tests/mm-boundary-shared-20261023/final-health.json)
verifies idle recovery `6.1.159-kdclobber2`, original Build ID, all 73 runtime
modules, 5,686 preserved module hashes, no test modules, cleared one-shot boot
selection and all three new RAM scratch paths absent. The original snapshot,
QEMU process, topology and CPU placement remain verified. No kernel fault was
recorded; the six historical `fd0` read-error lines remain in the health evidence.

## Commands and remaining gaps

The [probe guide](../../../../../tests/kernel/mmap_lock/boundary_shared/README.md)
contains modes and direct guest commands. On the source host, after an idle and
current boot/log-capacity check, reuse the installed image with fresh attempt
numbers; no build is needed:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-20261023/workflow.py recovery --attempt 2
# Optional read-only verification of this new archive:
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-20261023/audit.py
```

Queued neighboring-VMA replacement remains untested: it requires writer
ownership incompatible with the fixture's held reader shares. No bypass was
added. Uncontrolled write-fault, fast pinning, reclaim/swap and memory-cgroup
races, forced allocation failure, post-admission cancellation, Native-off controls
and unsupported COW/huge/special-page injections remain untested. The eight
omitted kdmm18 isolated-edge layouts are not retroactively covered by this new
geometry. Larger mappings, interior crossing, complex ancestry, general table
destruction and mapping creation remain out of scope.

The next small extension is a shared-zero target in this shared-table geometry,
reusing the per-slot retention proof but separately validating zero-page
non-ownership and native PTE/TLB clearing. It is still refused here. Performance,
p95, the seven mutex regressions and nano reruns remain deferred.
