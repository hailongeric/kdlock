> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# kdmm25: shared-zero interior target with native clearing

Completed: **40 serial cases, two basic tests and 867 negative receipt controls
passed**. Six native-matched layouts produced **16 different-task removals**,
including 12 without private-page holds. Six preservation smokes added 12
separately counted remote removals. Recovery is restored and modules unloaded.
Implementation: **`4bc0520b015849cfb03f10462e9c6a619f3d88a7`**. The completed
[kdmm24 campaign](../mm-boundary-interior-empty-20261024/README.md) remains
separate and was not repeated.

## Mechanism and supported scope

The previous interior classifier accepted only an empty target PTE (page-table
entry). The extension also accepts an exact present, read-only, special
shared-zero entry, checked under the current PTE lock. It removes one middle
page from an exactly three-page anonymous VMA (virtual memory area) crossing
one 2-MiB boundary within a common upper-table interval. The near survivor stays
untouched; the far survivor may be ordinary private resident, shared zero or
untouched. Private interior targets and populated near survivors still refuse.

For boundary B and 4-KiB page P, left removes `[B-P,B)` from `[B-2P,B+P)`;
right removes `[B,B+P)` from `[B-P,B+2P)`. All six selected survivor layouts were
tested: left UR/UZ/UU and right RU/ZU/UU, in increasing address order. R/Z/U mean
private resident/shared zero/untouched. A target read fault creates a genuine
shared-zero mapping; locked walks verify its PTE and PFN (physical frame number)
before admission without populating the untouched survivor.

Both outer-neighbor guards remain unchanged: the previous VMA ends inside the
first 2-MiB interval and the next starts inside the second. The mmap writer
rewalks current tables and verifies identity, geometry, ancestry and retention.
The two native splits must establish actual left end=`start`, right start=`end`
and matching VMA/page counts. These floor/ceiling bounds make native table
freeing return before a table walk. No general table destruction is admitted.

The shared-zero classifier takes no private-page reference or lock. Native
`zap_pte_range()` clears the PTE and records translation invalidation;
`vm_normal_page()` returns NULL, skipping private resident-page accounting,
reverse-map removal and page release. Native TLB (translation lookaside buffer)
completion precedes the success receipt. The
[native source excerpt](../../raw/tests/mm-boundary-interior-zero-20261024/native-zero-teardown.txt)
records this dependency. The original table PFN, empty target after success,
unchanged survivor entries and table-byte accounting are checked through return.

Existing caller-prepared VMA descriptors, maple-tree reserves (mapping-index
storage) and reverse-map links remain sufficient. Reverse maps associate
private pages with mappings; absent metadata consumes no links. Eligible far
private pages keep exact temporary holds through teardown; no private holds
are required for admission. Pre-effect refusal retains waiter handback, exact
ACK (acknowledgment), cancellation and sticky fallback. A post-split error
returns through the admitted request, preserving native harmless splits and
the original zero PTE without destructive local replay.

## Validation

`build-1`, one candidate boot and `focused-1` passed. There were no build, probe,
kernel-correctness or validator failures, and no rerun.

| Cases | Count | Result |
| --- | ---: | --- |
| Six layouts, native/KD | 12 | Six native matches, 12 remote zero-target removals |
| Both orientations, errors after split one/two, native/KD | 8 | Four remote ENOMEM results match native harmless layouts; no replay |
| Both orientations, queued private-target change and prepublication retention loss, native/KD | 8 | Four handback/ACK pairs; sticky local calls and exact retirement |
| Both orientations, waiting near-survivor fault, native/KD | 4 | Four remote removals; later local faults fill the existing table |
| Both orientations, queued cancellation | 2 | Victim mapping retained; no stranded ownership or resources |
| Empty/missing interior and shared-zero edge preservation | 6 | Twelve separately counted remote removals |

The 34 new cases rejected **680** corrupted receipts; six smokes rejected **187**.
There were **12 native success comparisons and four native error comparisons**.
Native controls execute the ordinary native body on the same KD lock backend
with delegation disabled; they are not a separate Native-off boot. Local heads,
fallback, admitted errors and cancellation are excluded from successful remote
counts. Every new remote completion binds the body to the request, task/mm,
target/table PFNs, zero ownership and completed TLB handling, plus preflight and
actual two-split retention proofs.

Representative receipts:

- Left-UR origin **1912** completed on **1911**, with target-table PFN `0x344ccf`,
  shared-zero PFN `0x3748`, one far private hold/release and no zero ownership.
- Right-UU origin **1953** completed on **1951**, with table PFN `0x3551ed`,
  no private holds and an absent far table.
- First-split error: origin **1960**, executor **1959**, result **-12**;
  second-split error: origin **2011**, executor **2010**, result **-12**.
  Both retained the original shared-zero PTE and native-compatible layouts.
- Queued private transition: actor **1985**, origin **1982**, executor **1981**,
  unchanged table `0x3551eb`; the actual native write fault happened with two
  requests pending and two readers held. Exact handback/ACK preceded local
  completion; the combiner never removed the private interior target.

Origins warmed the target translation on their pinned CPUs before publication;
subsequent target accesses faulted. Surviving PTEs, private contents, per-VMA
resident accounting, independent zero mappings, neighboring mappings and table
identities passed. Untouched near survivors stayed empty until explicit access.
Later zero-fill reads, isolated private writes and demand faults worked without
restoring the hole. Two local readers overlapped, and the waiting near fault
completed only after writer release. Full fixture cleanup left its upper
hierarchy absent and no worker/module reference stranded.

## Build, evidence and recovery

Only captured kernel source `mm/kd_mmap_unmap.inc` changed relative to kdmm24.
One new client and the affected test module were built; **14 unchanged clients
were reused**. The distinct release required 3,157 dependent C compilations and
73 runtime modules. Build/packaging intermediates used a private RAM overlay,
unmounted before boot and discarded by normal reboot. No permanent file was
deleted and no old archive recopied. Reusable installed outputs remain.

Three objtool warnings remain in archived `build-1/image.log`: two
`ibt_selftest` stack-frame warnings and
`relocate_restore_code+0x43: relocation to !ENDBR: get_option+0x68`.
They were not resolved in this MM stage; hibernation/restore was not tested.
No build errors occurred.

The measured budget was **120,000,000 root bytes** and **8,000,000,000 RAM bytes**.
Root free was **3,867,869,184** before build, **3,788,374,016** after installation
and **3,868,065,792** after recovery. No cleanup approval was needed.

- [Build](../../raw/tests/mm-boundary-interior-zero-20261024/build-1/result.json),
  [serial result](../../raw/tests/mm-boundary-interior-zero-20261024/kd-1/result.json),
  [offline audit](../../raw/tests/mm-boundary-interior-zero-20261024/collect-1/audit.json).
- [Single essential archive](../../raw/tests/mm-boundary-interior-zero-20261024/collect-1/essential.tar.gz):
  **637,080 bytes**, SHA-256 `09b23208f0f42781e43a2af7c9dad93fded1ab89afd32e33dc59eb4b450e3157`.
  Audit binds **65 frozen inputs**, **51 probe sources** and **80 client/log hashes**;
  generated module source is recorded separately.
- [Identity receipt](../../raw/tests/mm-boundary-interior-zero-20261024/identity/receipt.json):
  one source-host compressed ELF, **142,601,820 bytes**, SHA-256
  `f6e5b84deb40ff97cfc32d04921c00c6eba61523857d7cc9df57d6b2f2444fb6`.
- [Recovery](../../raw/tests/mm-boundary-interior-zero-20261024/recovery-1/result.json),
  [final health](../../raw/tests/mm-boundary-interior-zero-20261024/final-health.json),
  [snapshot/placement](../../raw/tests/mm-boundary-interior-zero-20261024/final-host.json).

Candidate **6.1.159-kdmm25**, Build ID `aba661529fe80e63791529a6c8a2657b2e86884e`;
manifest SHA-256 `9170858418cb2dc56e88ac4efde681c598b28cd4c51bcfd08bcad4712ea88822`.
Candidate boot `76b9c275-faa3-450b-ade1-925737703456`; final recovery boot
`9857b529-ea81-42ad-8a80-07adbfdd4697`. Recovery **6.1.159-kdclobber2**, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, preserves 5,686 recovery-module hashes
and exactly 73 runtime modules. No test module, armed next boot or kdmm25 RAM
scratch remains. Original snapshot, QEMU PID 257489, 64 vCPUs, 24 GiB, two NUMA
nodes and placement are unchanged. Historical `fd0` boot I/O messages remain
separate; no kernel fault was detected.

## Commands and remaining limits

[Probe guide and execution flow](../../../../../tests/kernel/mmap_lock/boundary_interior_zero/README.md).
Reuse installed outputs and fresh attempt directories after confirming idle state:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-zero-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-zero-20261024/workflow.py recovery --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-zero-20261024/audit.py
```

`run --attempt 2` avoids a boot on a verified candidate. The read-only audit
checks fixed attempt-1 evidence. The archive was collected once before recovery;
recovery/health records sit alongside it. Unrelated checkout work is preserved.

Private interior targets, populated near survivors, larger VMAs, complex
ancestry and general table destruction remain unsupported. Queued near-survivor
changes, interior neighbor replacement, opposite outer-guard loss, live
huge/special-entry injection, missing higher levels and allocation exhaustion
were not tested. Empty/missing-to-zero interior transitions were not newly run.
Controlled target transitions do not cover uncontrolled fault/reclaim/pinning
races. Advice/first-write and historical matrices were not repeated. Performance,
p95, mutex regressions and nano work remain deferred.

The next small candidate is a read-faulted shared-zero near survivor with this
same zero interior target and retention proof. It needs explicit survivor-PTE
preservation and transition validation. No subsequent extension was started;
this milestone does not establish general mmap support.
