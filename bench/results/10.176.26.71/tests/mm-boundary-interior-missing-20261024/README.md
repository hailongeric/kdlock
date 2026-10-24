> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# kdmm23: interior missing-table removal

Completed on the original VM: **44 serial cases, two basic tests and 1,092
negative receipt controls passed**. Six feasible interior layouts matched native
behavior. **16 new removals executed in a different task**, including 12 with
no private-page holds. Six preservation smokes add 12 separately counted remote
removals. Recovery is restored and test modules are unloaded.

This is one narrow production extension from the completed
[kdmm22 baseline](../mm-boundary-shared-missing-20261024/README.md) and
[queued-neighbor validation](../mm-neighbor-replace-20261024/README.md).
Neither campaign was repeated. Source commit:
**`d2845d62aaece5d59fa330cec0d2c48e9492a0d7`**.

## Mechanism and supported scope

Remove only the middle 4-KiB page of an exactly three-page anonymous VMA
(virtual memory area) crossing one 2-MiB boundary within a single upper-table
interval. The target leaf PTE (page-table entry) table must genuinely be missing,
with existing upper levels. The near survivor shares that missing range and
therefore stays untouched. The far survivor may be ordinary private resident,
shared zero or untouched. The target owns no physical page; no table is allocated
merely to remove its virtual range.

For boundary B and page size P, left orientation removes `[B-P,B)` from
`[B-2P,B+P)`; right removes `[B,B+P)` from `[B-P,B+2P)`. All six feasible survivor
pairs run: left UR/UZ/UU, right RU/ZU/UU, in increasing address order. A populated
near survivor cannot coexist with an absent target table. Upper levels are
constructed through an independent third-table read; actual locked page-table
walks verify absence instead of inferring it from untouched addresses.

The previous boundary path assumed prefix/suffix removal and one split. The
new path derives table selection from addresses and prepares for two splits.
The origin already supplies two VMA descriptors, maple-tree reserves (storage
for the VMA index), and reverse-map links. A reverse map connects a private page
to its mappings. No new executor allocation is introduced; absent ancestry
consumes no link. Under the actual mmap writer, the executor rewalks current
VMAs/tables, checks page eligibility and holds only eligible private survivors.

Both original guards remain: preceding VMA end above the first table interval
base, following VMA start below the second interval end. Two native prepared
splits create exact adjacent survivors. Their actual bounds establish native
`free_pgd_range()` floor=`start`, ceiling=`end`; its rounding returns before
walking a table in both orientations. Actual bounds, map count, mapped-page
count and unchanged table bytes are checked before the shared native removal.
Existing-table interior targets, including empty and shared-zero entries, refuse
before holds or either split. Huge/special entries and missing higher levels
remain refused; this adds no general table destruction.

References, VMA/maple/reverse-map resources and queue nodes retain their existing
exact lifetimes. A pre-effect refusal uses waiter handback, matching ACK
(acknowledgment), and sticky local fallback. After splitting begins, an error is
an admitted return, never permission to replay destructive work locally. Readers
remain concurrent and local; ordinary faults wait while the writer owns the lock.

## Results

`build-1`, one candidate boot and `focused-1` completed without a build, client,
kernel correctness or receipt-validation failure. No test rerun was needed.

| Group | Serial cases | Observed result |
| --- | ---: | --- |
| Both orientations × R/Z/U far survivor × native/KD | 12 | Six native matches; 12 remote removals |
| Both orientations × error after split one/two × native/KD | 8 | Four remote errors match native ENOMEM and harmless surviving layouts |
| Both orientations × outer-guard loss/existing empty table/queued zero appearance × native/KD | 12 | Six handback/ACK pairs; intact pre-effect state and sticky local third calls |
| Both orientations × waiting near-survivor fault × native/KD | 4 | Four remote removals; new table appears locally after writer release |
| Both orientations, queued fatal cancellation | 2 | Victim mapping preserved, resources retired |
| Missing edges, shared empty/zero/private, queued-neighbor smoke | 6 | Twelve separate remote removals; existing strict checks preserved |

The 38 new cases rejected **868** damaged receipts; six smokes rejected **224**.
There were **14 native success comparisons and four native error comparisons**.
Native controls run the ordinary native body on the same KD lock backend with
delegation disabled, not a separate Native-off boot. Local heads, native fallback,
cancellation and admitted errors are excluded from successful remote counts.

Every new successful remote body binds a preflight record, actual two-split
survivor bounds and completion to the same mm, request, originating task and
different executor. For example, left-UR origin **1917** completed on **1916**,
removing `[0x80000047ff000,0x8000004800000)` with one exact far-page hold/release.
Right-UU origin **1957** completed on **1956**, holding no private page, with
both leaf tables still missing. Target-table PFN remained zero in both cases.

Left split-one error returned **-12** from executor **1964** to origin **1965**;
right split-two error returned **-12** from **2023** to **2024**. Native layout,
VMA/page accounting, surviving contents and resource retirement matched; no
target removal or local replay followed these errors. A queued native target
read by **1998** created zero PFN `0x3748` before origin **1995** received exact
handback/ACK from **1994**, demonstrating locked revalidation without borrowing
shared-zero-page ownership.

PTE and per-VMA residency observations precede survivor access. Subsequent
zero-fill reads, patterned contents, isolated private writes, both neighboring
mappings and an independent zero mapping passed. Removed addresses faulted
both before and after survivor table creation. Table bytes remained unchanged
by the new body; controlled appearance/waiting faults separately account for
one native leaf-table allocation. Local cleanup left the fixture's upper
hierarchy absent, with exact page references and no stranded worker/module
references. Missing targets have no cached translation to invalidate; populated
TLB (translation lookaside buffer) checks belong to the preservation cases.

## Build, storage, recovery and evidence

Only `mm/kd_mmap_unmap.inc` changed relative to captured kdmm22 kernel sources.
One new client and one affected test module were built; **12 unchanged clients
were reused**. The distinct release required dependent recompilation: 3,157 C
compilation commands and the required 73 runtime modules. RAM-backed build and
packaging intermediates disappeared at the normal boot after their private
mount was removed. No permanent file was deleted, prior archive recopied or
recovery configuration changed. The linker emitted two `ibt_selftest` objtool
warnings; their full text remains in `build-1/image.log` in the essential archive.

The measured budget was **120,000,000 root bytes** and **8,000,000,000 RAM bytes**.
Root free was **4,027,604,992** before build, **3,948,146,688** afterward and
**3,943,874,560** after recovery. The compressed identity is stored once on the
source host, using guest RAM for transport; no cleanup approval was needed.

- [Build receipt](../../raw/tests/mm-boundary-interior-missing-20261024/build-1/result.json),
  [serial result](../../raw/tests/mm-boundary-interior-missing-20261024/kd-1/result.json),
  [read-only audit](../../raw/tests/mm-boundary-interior-missing-20261024/collect-1/audit.json).
- [Single essential archive](../../raw/tests/mm-boundary-interior-missing-20261024/collect-1/essential.tar.gz):
  **636,464 bytes**, SHA-256
  `ddcf72869a279e9587aaa5afb5a011637e51b7f7d490a745d4fbc3ce93eb7f24`.
  The audit binds **59 frozen inputs**, **45 probe sources** and **88 client/log
  hashes**. Generated module source is recorded separately from maintained source.
- [Kernel identity receipt](../../raw/tests/mm-boundary-interior-missing-20261024/identity/receipt.json):
  compressed ELF **142,599,628 bytes**, SHA-256
  `cb003ce49dadbf1bc224667f19fd10287d7e0e6cdfb7bc23298f9ea3535c98e5`.
- [Recovery verification](../../raw/tests/mm-boundary-interior-missing-20261024/recovery-1/result.json),
  [final health](../../raw/tests/mm-boundary-interior-missing-20261024/final-health.json),
  [snapshot and placement](../../raw/tests/mm-boundary-interior-missing-20261024/final-host.json).

Candidate **6.1.159-kdmm23**, Build ID
`79f002482567b97d68c97364b5dbf5a3efb26ea1`; manifest SHA-256
`1b85c3ba41d760b5dbe3dbc484dae46cb9b8267a02d3f6b01017fb341d76d697`.
Candidate boot `23615cf2-dc01-4223-acd8-453f6dfe827f`; final recovery boot
`c43da7d3-6ec5-46e0-87d3-99418dfe396e`. Recovery is **6.1.159-kdclobber2**,
Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, with **5,686 recovery-module
hashes** preserved, exactly 73 runtime modules, no test module, no armed next
boot and no remaining kdmm23 RAM scratch. Original snapshot, QEMU PID 257489,
64 vCPUs, 24 GiB, two NUMA nodes and placement remain unchanged. Historical
`fd0` boot I/O messages are recorded separately; no kernel fault was detected.

## Commands and remaining gaps

The [probe guide](../../../../../tests/kernel/mmap_lock/boundary_interior_missing/README.md)
contains execution flow, geometry and guest commands. Deliberate future reruns
reuse installed outputs and a new attempt, after confirming idle state:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-missing-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-missing-20261024/workflow.py recovery --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-missing-20261024/audit.py
```

`run --attempt 2` avoids a boot on a verified candidate. The audit checks fixed
attempt-1 evidence only; it does not start a live test. There is one retained
archive, collected before recovery, with recovery/health receipts beside it.

Outer-guard loss here precedes publication. The queued-neighbor smoke uses the
completed edge geometry, not interior replacement. Queued interior neighbor
replacement, opposite-side guard loss, private/near-survivor queued transitions,
forced allocation failure, missing-upper/huge/special entries and uncontrolled
fault/reclaim/pinning races remain untested. Advice, first-write and historical
matrices were not rerun because their bodies were unchanged. Existing-table
interior targets remain explicitly unsupported.

The next small candidate is an **empty target PTE in an existing leaf table**
for these same interior geometries, retaining this two-split proof and adding
locked table identity/lifetime checks before admitting it. Larger VMAs, complex
ancestry, general table destruction, performance/p95, mutex regressions and nano
work remain deferred. This milestone does not establish general mmap support.
