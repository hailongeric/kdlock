> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# kdmm20: shared-zero target sharing a retained boundary table

Completed October 24 on the original `10.176.26.71:2222` VM: **65 serial cases,
two basic tests and 1,935 negative receipt controls passed**. All **18 new
layouts** matched native behavior. The combiner completed **40 shared-zero
removals in a different task**, plus **two private-target removals after a
controlled queued state change**. Twenty zero-target removals held no private
pages. Two delegated split errors, five new-path handback/acknowledgment (ACK)
pairs and two cancellations passed. Recovery is restored and modules are unloaded.
No build, probe or live case failed or required a retry. The immutable run name
retains October 23, when preparation began. The completed
[kdmm19 campaign](../mm-boundary-shared-20261023/README.md) was not repeated.

## Mechanism and exact scope

This required a kernel change. The prior shared-table boundary guard admitted
only a private target; it now also admits the existing exact shared-zero class:
present, special, read-only, not protection-none or device-mapped, and
`is_zero_pfn()`. PTE means leaf page-table entry; PMD means page-middle directory;
VMA means virtual memory area. With P = 4 KiB and a 2-MiB boundary B:

| Direction | Original VMA | Removed target | Survivor sharing target table | Other survivor |
| --- | --- | --- | --- | --- |
| Prefix | `[B-2P, B+P)` | `[B-2P, B-P)` | Slot 1 below B | Slot 2 above B |
| Suffix | `[B-P, B+2P)` | `[B+P, B+2P)` | Slot 1 above B | Slot 0 below B |

Both leave `[B-P, B+P)`. The target table exists; the other table may be missing
when its survivor is untouched. Both PMDs share an ordinary existing upper
directory. Both outer-neighbor guards remain mandatory: preceding VMA end above
the first PMD interval's base, following VMA start below the second interval's
end. The exact native `free_pgd_range()` floor/ceiling calculation must return
before walking any table. A populated survivor alone does not replace this proof.

Under actual mmap write ownership, the executor rewalks current VMA bounds,
neighbors, hierarchy, table identities and each slot under its own PTE lock.
No earlier table pointer establishes admission. The same caller-prepared split
VMAs, mapping-index nodes and reverse-map links are reused. A reverse map links
a physical page to its virtual mappings; absent anonymous ancestry remains valid.
Admission is independent of the private hold count, with exact resource retirement.

The shared zero page takes no private reference, lock or release obligation.
Native `vm_normal_page()` returns NULL for it; `zap_pte_range()` clears its PTE
and records TLB (translation lookaside buffer) invalidation, then skips private
RSS (resident-page accounting), reverse-map and page-release operations. See the
captured [native source](../../raw/tests/mm-boundary-shared-zero-20261023/native-memory.c).
The body returns after native teardown, checks retained tables and surviving
entries, then emits the request-bound `KD_MM_BOUNDARY_SHARED_ZERO` completion.
No shared-zero contents are changed. Readers remain concurrent and local.

A queued zero-to-private transition is classified afresh through every kdmm19
eligibility, page-reference, page-lock and boundary check. A busy new page or
failed retention guard hands back before effects, then uses the exact ACK and
sticky local fallback. After a successful split, an injected error preserves the
target and returns native-compatible harmless VMA splitting without local replay.
Empty/missing targets in this shared-table geometry remain explicitly refused;
their earlier isolated-edge paths are preserved. Huge mappings, other special
entries, complex ancestry and general table destruction remain unsupported.

## Focused evidence

R/Z/U mean private resident/shared-zero/untouched survivors in increasing address
order. All nine pairs are distinct because near/far table roles differ. Native
controls execute the native body on the same KD-enabled image; no Native-off
boot was added.

| Group | Cases | Result |
| --- | ---: | --- |
| Both directions × RR/RZ/RU/ZR/ZZ/ZU/UR/UZ/UU × native/delegated | 36 | 18 matched layouts, 36 different-task zero removals |
| Queued zero-to-private target, both directions/routes | 4 | Two changed-private and two unchanged-zero remote removals |
| Queued zero-to-private target becomes busy, both directions/routes | 4 | Two exact pre-effect handback/ACK pairs |
| Outer retention guard lost before publication, both directions/routes | 4 | Two exact ACKs; native retains the table in this geometry |
| Post-split ENOMEM: prefix-RZ and suffix-UU, both routes | 4 | Two delegated errors match native, original target intact |
| Queued cancellation, both directions | 2 | Victim mapping preserved, exact resources retired |
| Far-survivor fault waiting for writer release, both routes | 2 | Two remote zero removals; local fault creates other table afterward |
| Busy far private survivor | 1 | Earlier survivor hold released before matching ACK |
| Preservation/refusal smoke | 8 | kdmm19 private, isolated-zero, missing/empty isolated edges; shared empty/missing remain refused |

The **57 new cases** rejected **1,677** corruptions and made **25 native success
comparisons plus two error comparisons**. The eight smokes rejected **258**
corruptions, completed **12 old-path different-task removals** and checked two
additional ACKs; these are separate from the 42 new-path removals.

Read-only kernel walks verify real zero PTEs, empty entries and missing tables
before admission, without faulting untouched survivors. Checks cover inaccessible
removed addresses after warmed translations, VMA bounds/offsets/flags, surviving
PTEs and contents, exact private references, reverse maps, RSS and table accounting.
Only afterward do untouched survivors read-fault and zero survivors receive
isolated private writes. Neighbors and an independent shared-zero mapping remain
intact. Full local cleanup observes the upper hierarchy absent, followed by
worker retirement and normal module unload.

The new test-only queued control performs a real local-reader write fault through
`get_user_pages()` after publication, with two reader shares and closed admission.
It retains one exact inspection reference to the newly private page. Mode 11
queues three requests and delegates the fully eligible private path; mode 12
queues two, locks the new page and requires handback. These are deterministic
pre-execution transitions, not uncontrolled write-fault race coverage.

Examples from the [audited receipts](../../raw/tests/mm-boundary-shared-zero-20261023/collect-1/audit.json):

- Prefix-RR request 2: origin **1927**, executor **1928**, zero PFN **3748**;
  two survivor holds/releases, zero target ownership, table-slot masks **3/4**.
- Suffix-UU request 2: origin **2064**, executor **2063**, **zero holds/releases**;
  target table **34aee8**, other table absent, masks **6/1**, TLB completion.
- Suffix queued change: reader **2128** converts zero PFN **3748** to private
  **35c4cb** in unchanged table **349baf**. Request 3, origin **2125**, executor
  **2124**, removes that private target; references **3 → 2** before KD's put.
- Suffix error request 2: origin **2108**, executor **2107**, result **-12**;
  original zero PTE and table retained, no target ownership or destructive replay.

## Build, storage and recovery

Source **`e5d5cd91a908dd410fa4743c8aab5b4eb4ded705`** changed only
`mm/kd_mmap_unmap.inc` among captured kernel sources. One new client and the
affected test module were built; eight unchanged clients were reused. The new
release dependency required 3,155 C compilations and 73 runtime modules in the
incremental RAM overlay. There was one build/install, one candidate boot and one
focused run; no clean rebuild or historical campaign rerun.

Only the **35 explicitly approved objects** were deleted after verifying idle
state, identity exclusion and their recoverable copies. The
[cleanup receipt](../../raw/tests/mm-boundary-shared-zero-20261023/cleanup/result.json)
records **84,631,552 bytes reclaimed**, root free **43,700,224 → 128,331,776**.
The [backup receipt](../../raw/tests/mm-boundary-shared-zero-20261023/cleanup/backup-receipt.json)
retains every original hash; source-host `recoverable.tar.gz` SHA-256 is
`1d9429ec8df74f48d60940df667ae0bb7e4dd7e7ee2d88c1f6a3d45b8508bb06`.
Earlier backups, source, recovery and unique evidence remain intact.

The measured root budget was 120,000,000 bytes, retaining recovery and storing
the compressed identity on the source host. Root free was 127,483,904 before
build, 122,482,688 before install and 48,398,336 afterward. The remaining boot/test
budget was 15 MB. After recovery **43,540,480 bytes (41.52 MiB)** remain, insufficient
for another equivalent build. RAM use was 5,243,183,104 bytes within its 8-GB
budget; the candidate scratch paths disappeared on recovery boot. No additional
deletion is authorized by this record.

| Identity | Value |
| --- | --- |
| Run | `mm-boundary-shared-zero-20261023 / build-1 / focused-1` |
| Candidate | `6.1.159-kdmm20` |
| Build ID | `043cefe28b7b88cbd5cba471a9616e17b94bd4e3` |
| Manifest SHA-256 | `7dd360dc364292274af8000099413bbb63860ce8d6cf80dec011b5fd5033ec47` |
| Candidate boot | `7ffc4c0d-59c3-4fc5-8eb7-1873b316ea09` |
| Recovery boot | `ece984a7-402f-4e18-9050-159d808a80c7` |
| Essential archive | 628,921 bytes; SHA-256 `d1727261b16f1b4294958627ac4c7235d834b7ed57c9ade93cf82f5d0511f228` |

The single [essential archive](../../raw/tests/mm-boundary-shared-zero-20261023/collect-1/essential.tar.gz)
and audit bind **44 frozen inputs, 27 maintained probe sources and 130 case-file
hashes**, with generated module metadata separate. The
[compressed identity receipt](../../raw/tests/mm-boundary-shared-zero-20261023/identity/receipt.json)
binds the one source-host kernel copy. No old archive was copied or rescanned.
[Final health](../../raw/tests/mm-boundary-shared-zero-20261023/final-health.json)
verifies idle recovery `6.1.159-kdclobber2`, original Build ID, 73 runtime modules,
5,686 preserved module hashes, no test modules and cleared one-shot boot selection.
The [original snapshot and placement](../../raw/tests/mm-boundary-shared-zero-20261023/final-host.json)
remain verified. No kernel fault was recorded; the six historical `fd0` read-error
lines remain distinguishable in the health evidence.

## Reuse and remaining gaps

The [probe guide](../../../../../tests/kernel/mmap_lock/boundary_shared_zero/README.md)
documents modes and direct guest commands. After checking that the same VM is
idle and current space covers boot/log growth, reuse the installed image with
fresh attempt numbers. Attempt 1 is immutable evidence; no build is needed:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-zero-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-zero-20261023/workflow.py recovery --attempt 2
# Optional source-host, read-only verification of the completed evidence:
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-zero-20261023/audit.py
```

Queued neighboring-VMA replacement remains untested: it needs writer ownership
while this fixture deliberately holds reader shares. No admission bypass was
added. Retention loss was exercised before publication. Uncontrolled fault,
reclaim/swap, fast pinning and memory-cgroup races, post-admission cancellation,
forced allocation failure, Native-off controls and huge/special-page injections
remain untested. No physical allocator-reuse or general mapping-support claim is
made. Interior crossing, larger VMAs, complex ancestry and table destruction
remain out of scope.

The next small extension is an **empty target PTE in this shared-table geometry**,
reusing the current retention proof with separate non-ownership and mapping
removal validation. It remains refused here. Performance, p95, the seven mutex
regressions and nano reruns remain deferred.
