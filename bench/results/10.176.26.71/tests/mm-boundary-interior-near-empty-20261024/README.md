> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# kdmm27: empty interior target beside a shared-zero survivor

Completed on the existing MM VM: **44 serial cases, two basic tests and 1,139
negative receipt controls passed**. Six native-matched layouts and controlled
target changes produced **16 different-task completions**: 14 empty targets and
two targets changed to shared zero before execution. Twelve held no private
pages. Six preservation cases added 12 separately counted remote removals.
Recovery is restored and test modules are unloaded.

Implementation: **`5ec01ceac217ab708e7a07de4f98e04e05a34e34`**. This required one
narrow kernel eligibility change; the completed [kdmm26 campaign](../mm-boundary-interior-near-zero-20261024/README.md)
was not repeated.

## Mechanism and supported scope

An empty target PTE (page-table entry) in an existing table can now retain an
exact shared-zero near survivor. The near survivor shares the target table;
the far survivor lies across the boundary and remains ordinary private resident
(R), shared zero (Z) or untouched (U). For 4-KiB page P and 2-MiB boundary B:

| Orientation | Original VMA (virtual memory area) | Removed middle page | Survivor pairs, address order |
| --- | --- | --- | --- |
| left | `[B-2P,B+P)` | `[B-P,B)` | ZR, ZZ, ZU |
| right | `[B-P,B+2P)` | `[B,B+P)` | RZ, ZZ, UZ |

Setup read-faults the near survivor and target-side neighbor, leaving the target
empty. Locked walks prove the actual target/near PTEs and table identity. Far-U
addresses remain untouched through the initial checks; reading zeros alone is
not accepted as evidence of a shared-zero mapping.

Under actual mmap write ownership, execution rewalks current tables, classifies
the target under its PTE lock and checks both original outer neighbors. The
previous VMA must end beyond the first table-interval base; the next must start
before the second interval ends. Two native VMA splits then establish actual
floor=`start`, ceiling=`end`. Native rounding must prevent any page-table-freeing
walk. This proof and all existing post-body/error checks remain unchanged.

No target page/table is allocated to remove an empty mapping. The shared-zero
survivor is neither owned, released nor modified. Caller-prepared descriptors,
maple-tree reserves (mapping-index storage) and reverse-map links are reused;
reverse maps connect private pages to mappings, and absent ancestry consumes no
links. Any far private hold survives native teardown and retires exactly once.
Private targets or private near survivors refuse before splitting. Errors after
a split return through the admitted request without destructive local replay.
Successful removal increases VMA count by one and reduces mapped virtual pages
by one, without reducing private resident-page accounting for an empty/zero
target. Survivor and page-table accounting remain unchanged until later access.

## Focused results

`prepare-1`, `build-1`, candidate boot `kd-1` and `focused-1` passed on the first
attempt. No build, client, validator or kernel-correctness failure occurred.

| Cases | Count | Evidence |
| --- | ---: | --- |
| Six layouts, native/KD | 12 | Six native matches; 12 different-task empty removals |
| Both split-error points/orientations, native/KD | 8 | Four remote ENOMEM results match harmless native split layouts |
| Queued empty-to-zero target, both orientations, native/KD | 4 | Two zero-target and two unchanged empty-target remote completions |
| Outer-guard loss, private target and private near changes, native/KD | 12 | Six exact handback/ACK pairs, sticky fallback, no replay |
| Queued cancellation, both orientations | 2 | Victim mappings retained; exact retirement |
| Prior zero-target/zero-near and empty/missing-target/untouched-near preservation | 6 | Twelve separate remote removals |

The 38 new cases rejected **970** corrupted receipts; six preservation cases
rejected **169**. There were **14 native success comparisons and four native
error comparisons**. Native controls use the ordinary native body on the same
KD lock backend with delegation disabled. Local heads/fallback, admitted errors
and cancellations do not count as different-task completions.

Examples bound to exact mm, request, range and tasks:

- Left-ZR origin **1938** completed on **1937**, target-table PFN (physical frame
  number) `0x34d369`, with one exact far hold/release and no zero-page ownership.
- Right-UZ origin **1977** completed on **1976**, table PFN `0x35482f`, with zero
  private holds and a genuinely missing far table.
- Queued read-fault actor **2010** changed victim slot **4** from empty to shared
  zero with three pending requests and two readers. Table PFN `0x3504db` stayed
  unchanged; origin **2007** completed the validated zero body on **2006**, with
  `zero_owned=0` and native TLB (translation lookaside buffer) completion.
- Right near-conversion actor **2077** created a private survivor. Executor
  **2073** released its earlier far hold with `effects=0`, then handback and ACK
  (acknowledgment) matched origin **2074** before local completion.

Removed addresses faulted before and after survivor accesses. Initial checks
covered exact surviving boundaries, PTEs, contents, table bytes, private resident
accounting and reference lifetimes. Later zero reads, isolated private writes,
far-U demand faults, independent zero mappings and neighboring mappings passed.
Empty targets have no old target translation to invalidate; changed zero targets
use the validated native clearing/TLB path. Both split-error points preserved
the near zero PTE. Readers overlapped locally. Complete fixture cleanup retired
the upper hierarchy and every probe reference before normal module unload.

## Build, evidence and recovery

Only captured kernel source `mm/kd_mmap_unmap.inc` changed. The new client and
affected module were compiled; **16 unchanged clients were reused**. The distinct
release required 3,157 dependent C compilations and 73 runtime modules. The RAM
build overlay was unmounted before boot; normal reboot cleared its intermediates.
No permanent deletion or additional backup archive was needed.

The measured budgets were **120,000,000 root bytes** and **8,000,000,000 RAM bytes**.
Root free was **3,782,647,808** before build, **3,703,087,104** after installation,
and **3,858,186,240** at final recovery check. Final RAM free was
**12,613,750,784 bytes**. These are observed capacity readings, not a claimed
reclamation amount.

Three existing objtool warnings remain unresolved: two `ibt_selftest` stack-frame
warnings and `relocate_restore_code+0x43: relocation to !ENDBR: get_option+0x68`.
Hibernation/restore was not tested.

- [Build](../../raw/tests/mm-boundary-interior-near-empty-20261024/build-1/result.json),
  [serial result](../../raw/tests/mm-boundary-interior-near-empty-20261024/kd-1/result.json),
  [offline audit](../../raw/tests/mm-boundary-interior-near-empty-20261024/collect-1/audit.json).
- [Single essential archive](../../raw/tests/mm-boundary-interior-near-empty-20261024/collect-1/essential.tar.gz):
  **641,616 bytes**, SHA-256 `1482239624d8a710e555202f2474ac2d314324590df2bfbbef381c4b37a98822`.
  Audit binds **71 frozen inputs, 57 probe sources and 88 client/log hashes**.
- [Identity receipt](../../raw/tests/mm-boundary-interior-near-empty-20261024/identity/receipt.json):
  one source-host compressed ELF, **142,607,572 bytes**, SHA-256
  `e065c00641450de47ced73f58c51bc007b85eb072abd06edb3700246e73ad52a`.
- [Recovery](../../raw/tests/mm-boundary-interior-near-empty-20261024/recovery-1/result.json),
  [final health](../../raw/tests/mm-boundary-interior-near-empty-20261024/final-health.json),
  [snapshot/placement](../../raw/tests/mm-boundary-interior-near-empty-20261024/final-host.json).

Candidate **6.1.159-kdmm27**, Build ID `b321218a58b2f9c99722a451602d82692f1be62b`;
manifest SHA-256 `a2671f0c9ecf5856b6f9d5c75227006e32a9377641ba7e44533419c75db5e3b5`.
Candidate boot `2d705b2d-7fed-4d8e-a7a4-734ad680d7dc`; recovery boot
`5b7e8cdf-2575-43e6-a694-abe2f1f2fdcc`. Recovery **6.1.159-kdclobber2**, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, retains 5,686 recovery-module hashes
and exactly 73 runtime modules. No test module, armed next boot or kdmm27 RAM
scratch remains. Snapshot, QEMU PID 257489, 64 vCPUs, 24 GiB, two NUMA nodes and
placement are unchanged. No kernel fault was detected; recorded `fd0` boot I/O
messages remain separate.

## Commands and remaining limits

[Probe guide](../../../../../tests/kernel/mmap_lock/boundary_interior_near_empty/README.md).
Reuse installed outputs with fresh attempt directories after checking idle state:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-empty-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-empty-20261024/workflow.py recovery --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-empty-20261024/audit.py
```

`run --attempt 2` avoids rebooting an already verified candidate. The source-host
audit reads fixed attempt-1 evidence. Recovery/health records sit alongside the
single pre-recovery archive; unrelated checkout changes remain untouched.

Private interior targets/near survivors, larger VMAs, complex ancestry and
general page-table destruction remain unsupported. Queued interior neighbor
replacement, opposite outer-guard loss, zero-to-empty changes, huge/special-entry
injection, missing higher levels and allocation exhaustion were not exercised.
No new waiting-fault fixture was run; prior evidence remains separate.
Deterministic queued changes do not establish uncontrolled fault/reclaim/pinning
race coverage. Historical matrices, performance/p95, mutex regressions and nano
work remain deferred.

The next useful candidate is one ordinary private near survivor beside an empty
interior target, retaining these two-split bounds. It needs review of the exact
private-page hold, reverse-map splitting and survivor-reference checks. No
further stage was started; this is not general mmap support.
