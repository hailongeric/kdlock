> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# kdmm22: missing leaf table shared with an untouched survivor

Completed on the original `10.176.26.71:2222` VM: **48 serial cases, two basic
tests and 1,709 negative receipt controls passed**. All **six feasible layouts**
matched native behavior. There were **20 different-task removals with the target
table still missing**, plus **two converted-empty, two converted-zero and two
converted-private removals** after queued real faults. Twenty of those 26
removals held no private pages. Two delegated split errors, four new-path
handback/acknowledgment (ACK) pairs and two cancellations passed. Recovery is
restored and modules unloaded. No build, probe or live case failed or needed a
retry. The [kdmm21 campaign](../mm-boundary-shared-empty-20261024/README.md) was
preserved and not repeated.

## Scope and implementation

The kernel needed a small change in `mm/kd_mmap_unmap.inc`. The shared-boundary
guard previously rejected a missing target leaf table, and its near-survivor
walk assumed an existing table. Admission and post-body checks now explicitly
skip leaf access for each slot whose actual PMD (page-middle directory) is
missing. A PTE is a leaf page-table entry; an existing table with an empty PTE is
distinct from a missing table. Post-body checks reject any private hold or
shared-zero mask on a missing slot and require unchanged table-byte accounting.

For P = 4 KiB and boundary B = a 2-MiB boundary:

| Direction | Three-page VMA | Removed page | Near survivor | Far survivor |
| --- | --- | --- | --- | --- |
| Prefix | `[B-2P,B+P)` | `[B-2P,B-P)` | Slot 1, untouched below B | Slot 2 above B: R/Z/U |
| Suffix | `[B-P,B+2P)` | `[B+P,B+2P)` | Slot 1, untouched above B | Slot 0 below B: R/Z/U |

VMA means virtual memory area; R/Z/U mean private resident/shared zero/untouched.
Both shapes retain `[B-P,B+P)`. A populated near survivor is geometrically
impossible while its target table is missing, so no R/Z near cases are omitted
as equivalents. All six valid initial layouts are tested. The far table may be
missing too. Both target and far PMDs must have the same existing ordinary upper
directory; missing higher levels, huge/device mappings and special non-present
entries remain refused.

Both outer-neighbor guards are unchanged: preceding VMA end above the first
PMD interval base and following VMA start below the second interval end. The
exact native `free_pgd_range()` floor/ceiling calculation must return before
walking tables. Neither table absence nor a populated far PTE substitutes for
that proof. Under actual mmap write ownership, execution rewalks VMA bounds,
simple or absent reverse-map ancestry, neighbors and upper/table identities.
A reverse map links a physical page to its virtual mappings. PMD locks establish
absence; existing tables use their PTE locks and complete existing classifiers.

Native split/removal removes the virtual target range without creating its
missing table, clearing unrelated PTEs or destroying retained tables. The absent
target and near survivor own no page/rmap/RSS reference; RSS is resident-page
accounting. An ordinary far page gets the existing exact temporary hold. Caller
split VMAs, mapping-index nodes and optional reverse-map links retain their
original ownership and exact retirement. Admission does not require any private
hold. Errors after a successful split return native-compatible results and can
never trigger destructive local replay. Queue ownership, ACK routing,
cancellation and sticky local fallback are unchanged. Readers stay concurrent
and local.

## Focused validation

Both retaining neighbors start untouched. A read fault on an independent third
leaf-table range creates the required upper levels without populating target or
near survivor. Read-only kernel walks prove actual target/near table absence
and classify far R/Z/U before publication. Native controls execute the native
body on the same KD-enabled image, not a Native-off boot.

| Group | Cases | Result |
| --- | ---: | --- |
| Six layouts × native/delegated | 12 | Six matches, 12 remote missing-table removals |
| Queued near zero fault, both directions/routes | 4 | Two missing and two converted-empty remote removals |
| Queued target zero fault, both directions/routes | 4 | Two missing and two converted-zero remote removals |
| Queued target private fault, both directions/routes | 4 | Two missing and two converted-private remote removals |
| New private target becomes busy, both directions/routes | 4 | Two pre-effect handback/ACK pairs, sticky local third call |
| Missing-table retention prerequisite lost before publication, both directions/routes | 4 | Two ACKs; native retains the shared table range without populating it |
| Post-split ENOMEM, prefix-UR and suffix-UU, both routes | 4 | Two delegated errors match native harmless splits; no replay |
| Queued cancellation, both directions | 2 | Victim mapping and exact resource retirement preserved |
| Near-survivor fault waiting for writer release, prefix-UU, both routes | 2 | Two missing-table remote removals followed by ordinary local table creation |
| Preservation smoke: shared empty/zero/private and isolated missing, both directions | 8 | 16 old-path remote removals, recorded separately |

The **40 new cases** rejected **1,427** corruptions and made **17 native success
comparisons plus two error comparisons**. The eight smokes rejected **282**
corruptions. Checks cover removed-address faults, retained VMA bounds/offsets,
PTE and content preservation, exact page references, RSS, table lifetimes,
neighboring mappings, an independent shared-zero mapping and full cleanup.
Only after initial-state observations do untouched survivors read-fault to zero
and receive isolated private writes. Rechecking the removed target after both
phases proves that creating the near survivor's table does not restore access.
The missing target has no translation to invalidate; zero/private appearance
controls separately verify native PTE/TLB (translation lookaside buffer)
completion. Shared zero pages are never owned, released or modified as private
pages. Local cleanup observes the fixture's upper hierarchy absent.

Test-only modes 16–18 perform real native faults after three requests publish,
using an already held local reader while two readers keep writer admission
closed. A near read creates the empty-target table, a target read creates a zero
PTE, and a target write creates a private page with one exact GUP
(`get_user_pages`) inspection reference. Fresh locked execution selects every
condition of kdmm21/kdmm20/kdmm19 respectively. Mode 19 locks that new private
page after two publications and requires safe handback. No synthetic removal,
PTE poke, stale table pointer or reader bypass is used.

Examples from the [audited receipts](../../raw/tests/mm-boundary-shared-missing-20261024/collect-1/audit.json):

- Prefix-UR request 2: origin **1907**, executor **1906**, target table absent;
  one far private hold/release, table-slot masks **3/4**.
- Suffix-UU request 2: origin **1948**, executor **1946**; both leaf tables
  absent, zero holds/releases, masks **6/1**.
- Queued near read: reader **2027** creates table **34bdb8**, zero PFN **3748**;
  request 3, origin **2024**, executor **2023**, removes the empty target through
  the complete retained-table path with no private hold.
- Queued target write: reader **2043** creates private PFN **35c47f** in table
  **348e7c**. Request 2, origin **2040**, executor **2039**, removes it with
  references **3 → 2** before KD's put and completed TLB teardown.
- Suffix injected error: origin **2007**, executor **2006**, result **-12**;
  target table remains missing, zero holds/releases, no local replay.

## Build, storage and evidence

Source **`5486cfded67a99ce682aa149f418b5ef26829e13`** changes only
`mm/kd_mmap_unmap.inc` among captured kernel sources. One new client and the
affected module compiled; **ten unchanged clients were reused**. The distinct
release required 3,157 dependency-driven C compilations and 73 runtime modules
in the existing RAM overlay. One incremental build/install, one candidate boot
and one focused run completed without retries or a historical matrix rerun.

Only the **96 exact approved inactive object files** were deleted. The
[cleanup receipt](../../raw/tests/mm-boundary-shared-missing-20261024/cleanup/result.json)
records **84,582,400 bytes reclaimed**, root free **43,499,520 → 128,081,920**.
The [verified backup](../../raw/tests/mm-boundary-shared-missing-20261024/cleanup/backup-receipt.json)
is retained on the source host: 23,467,056 bytes, SHA-256
`cf31ad8bc04dc36d98574652e5a73f81d804ed62a7c5ec69e9d6383a6dcaf9af`.
Earlier backups, source, installed kernels/modules, recovery and unique evidence
remain preserved; prior deletion approvals were not reused.

The measured root budget was 120,000,000 bytes including margin and recovery
retention; the compressed identity lives on the source host and packaging uses
RAM. Root free was **127,254,528** before build and **122,171,392** before install.
RAM use was **5,245,681,664** bytes within the 8-GB budget. Free root space later
increased to 1,788,645,376 bytes after build and **4,035,260,416 bytes** after
recovery. This additional increase is unexplained, recorded in
[capacity-change.json](../../raw/tests/mm-boundary-shared-missing-20261024/capacity-change.json),
and is not attributed to our approved cleanup. The bounded observation found
no active build/test/cleanup process; no additional deletion, resize or snapshot
change was performed by this task. Future operations must check current needs.

Essential evidence, collected once:

- [Build receipt](../../raw/tests/mm-boundary-shared-missing-20261024/build-1/result.json),
  [serial result](../../raw/tests/mm-boundary-shared-missing-20261024/kd-1/result.json),
  [audit](../../raw/tests/mm-boundary-shared-missing-20261024/collect-1/audit.json).
- [Essential logs/sources archive](../../raw/tests/mm-boundary-shared-missing-20261024/collect-1/essential.tar.gz):
  **619,364 bytes**, SHA-256
  `127cf7b025e8a767f655f4a651ace7f998ea965fc9f7dfe7bf0e477bdd9b0f67`.
  The audit binds **50 frozen inputs**, **33 maintained probe-source hashes** and
  **96 client/log hashes**. Generated module metadata is recorded separately.
- [Compressed kernel identity receipt](../../raw/tests/mm-boundary-shared-missing-20261024/identity/receipt.json):
  **142,624,436 bytes**, SHA-256
  `7ead40b01e32f788b9e1e3749826778d8fd99f55d6f6e13eb84f1a866995a15b`.
- [Final recovery health](../../raw/tests/mm-boundary-shared-missing-20261024/final-health.json)
  and [host placement/snapshot](../../raw/tests/mm-boundary-shared-missing-20261024/final-host.json).

Kernel **6.1.159-kdmm22**, Build ID
`f64c0542dcd5c756d28f1681d7f712d03babd159`, manifest SHA-256
`726e4d89eee54f013ea5b2270e9634c44aa74eeb44b1c5425a8c4f2706d07fb3`.
Candidate boot `3a34cad6-caa4-4041-8db7-573e42d9fcf9`; recovery boot
`1e3b0840-302a-4c4d-9c70-152a019b4c7e`. Final recovery is
**6.1.159-kdclobber2**, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, with **5,686 recovery-module hashes**
preserved, 73 runtime modules, no test modules, no armed one-shot boot and no
kdmm22 RAM scratch. Snapshot `before-mutex-kdonly-20261017T140354Z`, QEMU PID
257489, 64 vCPUs/24 GiB/two NUMA nodes and CPU placement remain unchanged.
There were no kernel faults; the six historical `fd0` read-error lines remain
in the recovery boot log and are unrelated to MM admission.

## Reproduction and remaining gaps

[Probe commands](../../../../../tests/kernel/mmap_lock/boundary_shared_missing/README.md)
reuse the installed image. Completed attempt 1 must not be overwritten:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-missing-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-missing-20261024/workflow.py recovery --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-missing-20261024/audit.py
```

The last command only audits the retained attempt-1 archive on the source host;
it does not start VM tests. On an already verified candidate boot, `run --attempt
2` avoids another reboot. The first build used `prepare`, `build`, `kd`,
`collect`, the audit, then `recovery`; do not rerun setup into completed paths.

Retention loss was tested before publication. Queued neighboring-VMA replacement
requires a separate writer-owned gate: native replacement cannot proceed while
the current fixture holds two read shares. It remains untested rather than
bypassing ownership. The concurrent near-fault wait was tested only for prefix
UU; both directions cover ordinary post-removal near demand faults. Controlled
appearances do not cover uncontrolled write-fault, fast-GUP/pinning or reclaim
races. Higher-level absence, huge/special entries, complex ancestry, larger
VMAs, interior removal and general page-table destruction remain refused or
outside this stage. Advice, first-write and broad historical campaigns were not
rerun; this change touches only the bounded-unmap body and its probe.

The next small validation step is a separate writer gate for queued neighbor
replacement. The next functional candidate is one-page interior removal within
the same three-page boundary geometry, after a separate two-split retention and
failure analysis. Neither is implemented here. Performance, p95, the seven
mutex regressions and nano reruns remain deferred.
