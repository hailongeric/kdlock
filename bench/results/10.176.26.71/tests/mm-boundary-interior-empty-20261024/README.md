# kdmm24: empty interior target in a retained table

Completed: **44 serial cases, two basic tests and 1,090 negative receipt controls
passed**. Six native-matched layouts produced **16 different-task removals**,
including 12 without private-page holds. Six preservation smokes added 12
separately counted remote removals. Recovery is restored and modules unloaded.
The [kdmm23 campaign](../mm-boundary-interior-missing-20261024/README.md) remains
separate and was not repeated. Implementation commit:
**`5a807e35dd7b0bb98673b3b86c8f8602255fa591`**.

## Mechanism and scope

The kernel previously refused any existing target leaf table for interior
boundary removal. The extension accepts only an empty PTE (page-table entry)
in the middle page of an exactly three-page anonymous VMA (virtual memory area)
crossing one 2-MiB boundary within one upper-table interval. The near survivor
remains untouched; the far survivor may be ordinary private resident, shared
zero or untouched. This keeps the kdmm23 survivor subset while adding a retained
target table. Empty means `pte_none()`, not merely non-present; special entries
and zero/private target PTEs refuse. The missing-table path remains supported.

Both original outer-neighbor guards and the separate two-split native retention
proof are unchanged. Under mmap writer ownership, execution rewalks upper levels,
table identity, current VMA state and retention bounds. It classifies the target
under the PTE lock and also requires the near survivor's PTE to be empty. No
target page/table is allocated, cleared on behalf of another address or released.
Native splits establish actual left end=`start` and right start=`end`; native
table freeing returns without walking a table. Completion/error checks require
the same table PFN (physical frame number), empty target, intact survivor entries
and unchanged page-table bytes.

Caller-prepared VMA descriptors, maple-tree reserves (mapping-index storage)
and reverse-map links are reused. Reverse maps associate private pages with
their mappings. Absent metadata consumes no links; zero private holds do not
prevent admission. Exact references, resource retirement, waiter handback/ACK
(acknowledgment), cancellation and sticky fallback remain intact. A failure
after splitting is an admitted error, never permission for destructive replay.

For boundary B and 4-KiB page P, left removes `[B-P,B)` from `[B-2P,B+P)`;
right removes `[B,B+P)` from `[B-P,B+2P)`. All six chosen survivor layouts were
tested: left UR/UZ/UU and right RU/ZU/UU, in increasing address order. R/Z/U mean
private resident/shared zero/untouched. A read of the target-side neighboring
VMA constructs the existing table without touching target or near survivor;
locked walks verify actual PTE/table states before admission.

## Validation

`build-1`, one candidate boot and `focused-1` passed without build, probe, kernel
correctness or validator failures. No rerun was required.

| Cases | Count | Result |
| --- | ---: | --- |
| Six layouts, native/KD | 12 | Six native matches, 12 remote empty-target removals |
| Both orientations, failures after split one/two, native/KD | 8 | Four remote ENOMEM results match native harmless layouts; no replay |
| Both orientations, queued zero/private target changes and prepublication retention loss, native/KD | 12 | Six handback/ACK pairs, sticky local third calls, exact state/reference cleanup |
| Both orientations, waiting near-survivor fault, native/KD | 4 | Four remote removals; later local fault fills the retained table |
| Both orientations, queued cancellation | 2 | Victim retained, ownership and resources retired |
| Missing interior both orientations, empty edge both directions, zero/private edge smokes | 6 | Twelve separate remote removals |

The 38 new cases rejected **880** corrupted receipts; six smokes rejected **210**.
There were **14 native success comparisons and four native error comparisons**.
Native controls run the ordinary native body on the same KD lock backend with
delegation disabled, not a separate Native-off boot. Local heads/fallback, errors
and cancellation are excluded from successful different-task counts.

Examples bound to exact table, request and owner identities:

- Left-UR origin **1930** completed on **1929**, retaining target-table PFN
  `0x34a1c9` with one far private hold/release and no target ownership.
- Right-UU origin **1969** completed on **1970**, retaining target-table PFN
  `0x35812c`, with no private holds and an absent far table.
- First-split error: origin **1978**, executor **1977**, result **-12**;
  second-split error: origin **2037**, executor **2036**, result **-12**.
  Native layout, accounting, retained entries and exact retirement matched.
- Queued zero transition: actor **2003**, origin **2000**, executor **1999**,
  unchanged table `0x3535b2`, zero PFN `0x3748`; exact handback/ACK preceded local
  completion. Queued private transition: actor **2063**, origin **2060**,
  executor **2059**, unchanged table `0x34b706`; its new private reference and
  reverse-map metadata were handled by the native waiter, never the combiner.

Each new remote completion matched the preflight proof and actual two-split
survivor bounds. Removed-address faults, PTEs, per-VMA resident accounting,
patterned/zero contents, isolated writes and neighboring/independent-zero
mappings passed. Untouched survivors stayed empty until access. Later faults
and writes retained table identity and never restored the removed virtual range.
Two local readers overlapped; the near-survivor fault waited for writer release.
Cleanup left the fixture's upper hierarchy absent and no worker/module reference
stranded. The empty target has no translation to invalidate; populated-target TLB
(translation lookaside buffer) checks remain separate preservation evidence.

## Build, evidence and recovery

Only `mm/kd_mmap_unmap.inc` changed relative to captured kdmm23 kernel sources.
One new client and one affected test module were built; **13 unchanged clients
were reused**. The distinct release required 3,157 dependent C compilations and
73 runtime modules. Private RAM build/packaging intermediates disappeared at
normal boot after unmount. No permanent file was deleted and no prior archive
was recopied. The installed candidate, its identity and reusable probes remain
for reproduction. Three objtool linker warnings are retained in archived
`build-1/image.log`: two about `ibt_selftest` stack frames and one
`relocate_restore_code+0x43: relocation to !ENDBR: get_option+0x68` warning.
There were no build errors. These warnings were not resolved in this MM stage;
hibernation/restore behavior was not tested.

The measured budget was **120,000,000 root bytes**, **8,000,000,000 RAM bytes**.
Root free was **3,943,002,112** before build, **3,863,519,232** after installation,
and **3,867,607,040** after recovery. No cleanup approval was needed.

- [Build](../../raw/tests/mm-boundary-interior-empty-20261024/build-1/result.json),
  [serial result](../../raw/tests/mm-boundary-interior-empty-20261024/kd-1/result.json),
  [audit](../../raw/tests/mm-boundary-interior-empty-20261024/collect-1/audit.json).
- [Single essential archive](../../raw/tests/mm-boundary-interior-empty-20261024/collect-1/essential.tar.gz):
  **638,836 bytes**, SHA-256 `ee2094afeb039cb644afc5b3ec90cb884a2ba6944357966ddc992345e654aee0`.
  Audit binds **62 frozen inputs**, **48 probe sources** and **88 client/log hashes**;
  generated module source is recorded separately.
- [Identity receipt](../../raw/tests/mm-boundary-interior-empty-20261024/identity/receipt.json):
  one source-host compressed ELF, **142,611,360 bytes**, SHA-256
  `836afc54f7ab944184d7e32887835059d94a9af05a95a4761321d930b11cd344`.
- [Recovery](../../raw/tests/mm-boundary-interior-empty-20261024/recovery-1/result.json),
  [final health](../../raw/tests/mm-boundary-interior-empty-20261024/final-health.json),
  [snapshot/placement](../../raw/tests/mm-boundary-interior-empty-20261024/final-host.json).

Candidate **6.1.159-kdmm24**, Build ID `ebdf44a9cbb21af648eed195d9811bda6fd24acc`;
manifest SHA-256 `0340ed9513dbf6257ae404fd36f58d83e9677618676db50d43bd58b0eb6b052a`.
Candidate boot `96b94b35-7a27-431e-873e-e4e24e9ac3ba`; final recovery boot
`ab5941aa-a409-426c-85c4-77106516950e`. Recovery **6.1.159-kdclobber2**, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, preserves 5,686 recovery-module hashes
and exactly 73 runtime modules. No test module, armed next boot or kdmm24 RAM
scratch remains. Original snapshot, QEMU PID 257489, 64 vCPUs, 24 GiB, two NUMA
nodes and placement are unchanged. Historical `fd0` boot I/O messages remain
separate; no kernel fault was detected.

## Reproduction and limits

[Probe guide and execution flow](../../../../../tests/kernel/mmap_lock/boundary_interior_empty/README.md).
Reuse installed outputs and fresh attempt directories after checking idle state:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-empty-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-empty-20261024/workflow.py recovery --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-empty-20261024/audit.py
```

`run --attempt 2` avoids a boot on a verified candidate. The read-only audit
checks fixed attempt-1 evidence. One archive was collected before recovery;
recovery/health records are alongside it. Unrelated checkout work is preserved.

Populated near survivors and zero/private interior targets remain unsupported.
Queued near-survivor changes, interior neighbor replacement, opposite-side guard
loss, huge/special entries, missing upper levels and allocation exhaustion were
not injected here. Controlled target faults do not cover uncontrolled fault,
reclaim or pinning races. Prior advice/first-write and historical matrices were
not repeated. Larger VMAs, complex ancestry, general table destruction,
performance/p95, mutex regressions and nano work remain deferred.

The next small candidate is a shared-zero interior target with this same
untouched-near subset and retention proof, after explicit native PTE/TLB handling
and zero-page ownership review. This milestone does not establish general mmap
support, and no subsequent extension was started.
