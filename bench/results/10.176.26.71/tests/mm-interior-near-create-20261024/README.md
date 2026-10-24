> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# Queued near-survivor creation on unchanged kdmm29

**Complete, validation only:** 70 serial cases, two basic tests and 2,632 negative
receipt controls passed. All 24 layouts matched native behavior. There were
**24 different-task removals with a newly created private near survivor**, plus
24 unchanged peer removals and eight preservation removals. Four delegated
split errors, four handback/ACK (acknowledgment) pairs and two cancellations after
creation passed. Recovery is restored and test modules are unloaded.

The [completed kdmm29 baseline](../mm-boundary-interior-zero-near-private-20261024/README.md)
was reused, not rerun. Implementation/test commit: `c5d8164`. No production kernel
source, image, runtime module, initramfs or recovery configuration changed.

## Mechanism and supported scope

Remove the middle page of a three-page anonymous VMA (virtual memory area) across
a 2-MiB page-table boundary. With P=4 KiB and boundary B, left maps
`[B-2P,B+P)` and removes `[B-P,B)`; right maps `[B-P,B+2P)` and removes
`[B,B+P)`. The near survivor shares the target's leaf table; the far survivor is
across the boundary. The target is an empty PTE (page-table entry) in an existing
table or a verified shared-zero PTE. Both outer neighboring VMAs and the native
two-split floor=`start`, ceiling=`end` table-retention proof remain mandatory.

The near survivor initially has no PTE (U) or a read-faulted shared-zero PTE (Z).
The far survivor is an ordinary private resident page (R), Z or U. Every product
of target E/Z × left/right × initial near U/Z × far R/Z/U ran: 24 layouts, with
no deduplication. Locked kernel PTE walks prove U and Z separately before any
observation can populate U. Neighbor read faults establish the existing target
table without creating hidden target-page state.

A test-only control waits for three published requests and two local readers.
One already-held reader calls native `get_user_pages` with `FOLL_WRITE` to fault
the near survivor into a private page. This wrapper cannot drop/reacquire its
mmap read share on retry. It introduces no reader bypass or synthetic unmap body.
The probe owns exactly the new private reference and fills a known content
pattern. Busy/error/cancellation controls use two queued requests instead.

The unchanged combiner later acquires the actual mmap writer, rewalks the live
PTE/table and VMA, revalidates both outer guards and current simple reverse-map
ancestry (metadata linking a page to its mappings), then validates every page.
It takes an exact reference and nonblocking lock on the eligible new survivor.
Both split VMAs, mapping-index reserves and reverse-map links were prepared by
the original caller, even if ancestry was absent at publication. Sixteen of the
24 layouts create new ancestry; eight preserve existing ancestry from a far R.
The new near reference remains balanced before/during/after execution: 2/3/2.

Native zero-target clearing completes TLB (translation lookaside buffer)
invalidation without owning, modifying or releasing the shared zero page.
Empty targets require VMA removal but no target-page release. Both surviving
mappings, their contents and table identities remain valid. Current private
interior targets still refuse. No eligibility or retention check was weakened.

## Results and controls

| Group | Serial cases | Verified outcome |
| --- | ---: | --- |
| 24 layouts × native/KD | 48 | 24 changed-survivor remote bodies + 24 unchanged peer bodies |
| Four queued busy controls × native/KD | 8 | Four exact handback/ACK pairs and sticky local fallback |
| Two split points × two fixtures × native/KD | 8 | Four remote `-ENOMEM` returns matching native harmless splits |
| Cancellation after creation, two fixtures | 2 | Cancelled victim remains mapped; resources/reference retire exactly |
| Existing E/R, Z/R, E/Z and Z/U near paths | 4 | Eight separate preservation bodies |

The busy controls cover both traversal orders. Empty/left creates U→R then locks
the far R: the newly acquired near hold rolls back exactly before handback.
Empty/right creates U→R then locks that near page: the earlier far hold rolls
back. Zero/left Z→R with near busy and zero/right Z→R with far busy refuse before
any earlier hold. No state-changing fallback is counted as delegation.

Split errors and cancellation use empty/left with U near and U far, and
zero/right with Z near and R far. Errors occur after the first or second successful
split; neither requires rollback of native-permitted harmless splits, and neither
replays destructive work locally. Cancellation creates the near page before
sending the nonfatal and fatal signals, while both readers still hold their
shares. The cancelled request returns `-EINTR` with the target intact.

There are 28 native outcome comparisons and four native error comparisons.
All 28 admitted changed-survivor bodies/errors retired the exact near hold.
The 18 zero-private-hold remote bodies belong to unchanged peers/preservation;
newly created private survivors always acquire their required hold.

Examples from `focused-1`:

- `create-empty-target-left-uu`: local modifier **1929** created near PFN
  `0x359b6c` after publication with initially absent ancestry. Origin **1926**
  completed on **1925**, preserving the table and retiring one near hold.
- `create-zero-target-right-zz`: modifier **2089** changed near zero PFN `0x3748`
  to private PFN `0x34b5dd`; origin **2086** completed on **2085**. The target
  remained a real zero mapping until native clearing and TLB completion.
- `empty-target-left-create-far-busy`: PFN `0x4109d9` was held/released once with
  `effects=0` before origin **2102** acknowledged owner **2101**.

Pre-access checks cover VMA boundaries/offsets/flags, private residency,
reverse-map links, physical page identities, references and table bytes. Later
reads and isolated writes preserve other survivors, both neighbors and an
independent zero mapping. U survivors fault normally, and removed targets still
fault afterward. Full cleanup retires mappings, tables and every test reference;
normal module unload and idle checks passed. Readers remained concurrent/local.

## Build, evidence and recovery

Only two clients and one test module were compiled. Four smoke clients, the
installed kdmm29 image, all 73 runtime modules and initramfs were reused. The
new module regenerated split BTF (type metadata referencing kernel type IDs)
against the exact captured kdmm29 ELF. Both basic tests passed once; no full
historical suite, build retry, candidate reboot retry or live rerun was needed.

No build, probe or kernel correctness failure occurred. Module compilation kept
the previously observed Perl locale fallback warning. Both boots recorded six
`fd0` floppy-device I/O messages, also present in the prior recovery record;
there were no kernel-fault matches. The inherited kernel objtool warnings and
hibernation coverage remain outside this test-only stage.

- [Build](../../raw/tests/mm-interior-near-create-20261024/build-1/result.json),
  [serial results](../../raw/tests/mm-interior-near-create-20261024/kd-1/result.json),
  [offline audit](../../raw/tests/mm-interior-near-create-20261024/collect-1/audit.json).
- [One essential archive](../../raw/tests/mm-interior-near-create-20261024/collect-1/essential.tar.gz):
  347,095 bytes; SHA-256 `2e41e33b9e52824c3fc219673ca7baa1a47f9c7976dbb28d1043e694f3736893`.
  It contains the frozen probe sources and essential build/run logs. Audit binds
  43 frozen inputs, 40 probe sources and 140 client/kernel-log hashes, then
  rechecks all receipts and corruption controls offline.
- [Recovery](../../raw/tests/mm-interior-near-create-20261024/recovery-1/result.json),
  [final health](../../raw/tests/mm-interior-near-create-20261024/final-health.json),
  [snapshot/placement](../../raw/tests/mm-interior-near-create-20261024/final-host.json).

Kernel `6.1.159-kdmm29`, Build ID `f103e598e99e47a63b40d044ff8cbb0390492d50`;
manifest SHA-256 `bcb447e9d07cea07e6f215ee59131b6ee68fc143e8405cf6ab789d3a95af5945`.
Candidate boot `8a6368e6-a13c-4dbd-a058-fe71a1f76cd8`; recovery boot
`1602542f-b2ec-4f6b-b67d-db89dee83137`, release `6.1.159-kdclobber2`.
All recovery files, 5,686 recovery-module hashes and the exact 73 runtime modules
remain verified. No test module, armed next boot or temporary RAM build remains.
Snapshot, QEMU PID 257489, 64 vCPUs, 24 GiB, NUMA and placement are unchanged.

Budgets were 40 MB root and 2 GB RAM, based on the existing 818,240-byte module,
96,920-byte clients, two 780,204,992-byte ELF copies, 142,634,648-byte compressed
transport and observed boot growth. Root build growth was 3,313,664 bytes.
Final root free was **3,760,422,912 bytes**. No files were permanently deleted and
no new kernel identity archive was created; prior identity evidence was reused.

## Commands and remaining limits

[Probe guide](../../../../../tests/kernel/mmap_lock/interior_near_create/README.md).
For a deliberate reproduction on the same idle VM, reuse the installed outputs
and choose fresh attempt directories:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-interior-near-create-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-interior-near-create-20261024/workflow.py collect --attempt 2
python3 bench/results/10.176.26.71/tests/mm-interior-near-create-20261024/workflow.py recovery --attempt 2
```

The fixed evidence can be checked without any VM run:

```sh
python3 bench/results/10.176.26.71/tests/mm-interior-near-create-20261024/audit.py
```

This closes controlled U/Z→private near-survivor revalidation coverage, including
new/old simple ancestry. It does not cover uncontrolled write-fault, reclaim,
pinning or mapping-change races. Busy/error/cancellation combinations beyond the
listed fixtures, interior neighbor replacement, opposite guard loss, allocation
exhaustion, a new waiting-fault fixture and a Native-off boot were not exercised.
Private interior targets, larger VMAs, complex ancestry and general table
teardown remain unsupported. Performance/p95, mutex regressions and nano reruns
remain deferred.

The next useful implementation candidate is a private interior target with an
untouched near survivor, retaining exact target ownership through native teardown.
It remains explicitly refused and was not started.
