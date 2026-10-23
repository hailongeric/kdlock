# Bounded shared-zero target removal

Passed on `6.1.159-kdmm11`: **48 serial cases, two basic programs and 650 negative
receipt controls**. All 15 supported zero-target layouts matched native behavior.
There were **32 actual different-task zero-target removals**, plus **one separately
counted private-target removal after a controlled state change**. Recovery is
restored, test modules are unloaded and final health passed. No build or live
case failed; no performance, p95, mutex-regression or nano work ran.

Implementation/frozen inputs: `39571f0598e560744fd16a2c74509a9659ab4fdc`.
Only `mm/kd_mmap_unmap.inc` changed in the captured kernel. The test module adds
one deterministic native fault control without changing old ioctl layouts.
The [completed zero-survivor milestone](../mm-zero-partial-20261023/README.md)
remains unchanged evidence and was not rerun as a full campaign.

## Scope and mechanism

The target is one read-faulted shared-zero page in an exactly three-page anonymous
VMA (virtual memory area). At least one survivor must be an ordinary writable,
exclusive private resident page. The other may be untouched, another zero page
or another private page. Existing opt-in, simple reverse-map ancestry, caller
allocation and table-retaining neighbors remain required. A reverse map connects
pages to their mappings; VMA links may still be cloned/freed by native splitting,
but the shared zero **page** must not undergo ordinary page reverse-map removal.

The former refusal was more than a guard: completion assumed a held private
target and expected every zero PTE (page-table entry) to survive. The new path
classifies the target under mmap writer ownership and the PTE lock. A zero entry
must be present, special, read-only, non-device, not protection-none and satisfy
`is_zero_pfn()`. It receives no owned page pointer, lock or reference. The native
`zap_pte_range()` clears its entry and records a TLB (cached translation)
invalidation; `vm_normal_page()` returns NULL, bypassing private RSS (resident
set size), page reverse-map and page-release operations. Native VMA and virtual
page accounting still change normally.

After completion, the zero target must be absent; zero survivors retain their
saved entries, ignoring only the hardware accessed bit. On admitted split errors,
the target and zero survivors remain intact. Private survivor references and
locks retire exactly as before. Caller-prepared VMA descriptors, reverse-map
links and mapping-index reserves are unchanged. A newly private target uses the
existing checked private-page path. Unsupported current state hands back before
effects, matches its ACK (acknowledgement) and makes later calls local. After a
split can take effect, errors return directly; destructive local replay is forbidden.
Readers stay concurrent and local. See the [maintained scope](../../../../../kernel_integration/mmap_lock/UNMAP.md#shared-zero-page-targets).

## Cases and evidence

Guest stage: `/root/kdlock-evidence/10.176.26.71/tests/mm-zero-target-20261023`,
run `focused-1`. R is a private resident page, Z a verified shared-zero PTE,
U an absent untouched PTE. Each row contains five native/KD pairs and ten remote
zero removals. No supported combination is deduplicated.

| Removed position | Initial slots for `ru`, `ur`, `rz`, `zr`, `rr` |
| --- | --- |
| Prefix, slot 0 | ZRU, ZUR, ZRZ, ZZR, ZRR |
| Interior, slot 1 (`middle`) | RZU, UZR, RZZ, ZZR, RZR |
| Suffix, slot 2 | RUZ, URZ, RZZ, ZRZ, RRZ |

The 12 combinations whose survivors contain no R are outside this stage's
eligibility, not equivalent cases omitted from validation. A no-resident refusal
control covers that boundary. Native controls use the ordinary body with
delegation disabled on the same KD lock backend, not a Native-off boot.

Targets are created by read faults and proven Z through the unchanged read-only
PTE classifier, never written or pinned before initial observation. Removed
addresses fault on the original CPUs after their translations were warmed.
Resident survivors retain contents, physical identities and references. U slots
remain absent until explicit access, except a recorded competing read fault that
waits for writer release and resolves locally. Before controller survivor reads,
VMA bounds/offsets/flags and per-VMA `smaps` RSS/anonymous bytes match native.
Zero removal leaves private resident accounting unchanged. Later zero reads and
isolated private writes verify surviving Z/U pages and an independent zero mapping.

Example `target-prefix-ru`: mm `ff1100034998d700`, request 2, origin **1839**,
executor **1837**, zero PFN (physical page number) `0x3748`. Paired body/completion
records show resident mask 2, zero mask 1, untouched mask 4, one private hold/release,
zero owned-page holds, target PTE absent and tables retained. These receipts prove
real native unmap execution; queue acceptance and local fallback do not count.

The matrix supplies 30 remote zero removals. Removing without test-held references
adds one; the controlled-change case adds one unchanged zero-target removal and
one changed private-target removal. The 41 new cases include 16 native success
comparisons, two native/delegated split-error comparisons, **72 isolated survivor
write steps, 103 exact test-reference releases and 249 cleanup calls**.

## Deterministic target change and controls

In `target-change`, all three unmap callers finish preparation and publish while
two local readers hold their shares. An existing reader invokes native GUP
(`get_user_pages`) with write intent on the selected Z target. This wrapper keeps
its existing mmap share; it does not drop/reacquire the lock or bypass admission.
The native write fault creates a private page. The probe verifies zero fill,
writes a pattern only into that private page, drains its local page additions
and retains exactly the new test reference. It records the transition before
releasing either reader. No production delegation hook or PTE replacement is
fabricated by the test.

Actual transition: mm `ff1100034bfacfc0`, actor **2024**, pending **3**, readers
**2**, admission **-1**, zero PFN `0x3748` to private PFN `0x34db8d`. Afterwards,
request **3**, origin **2020**, executor **2019**, reports that exact private PFN,
two private holds/releases, removed PTE absent and mapcount zero. Ownership,
page identity/hash/charge, reference retirement and native comparison passed.
This completion is excluded from the zero-target count. It proves deterministic
pre-execution revalidation, not broader concurrent write-fault races.

Other controls passed: `ENOMEM` after interior split 1 and split 2 (two remote
errors matching native harmless splits); busy survivor and absent target (each
one held private reference rolled back before matched handback/ACK); no-resident
VMA refusal (no holds); sticky local follow-ups; queued fatal cancellation with
the victim mapping retained. All prepared resources retired; no replay or
stranded owner/ACK remained. Of 650 negative controls, 614 cover new target cases.

Seven preservation smokes passed: resident target with zero survivors (2 remote),
mixed resident/untouched partial (2), fully resident partial (2), untouched partial
(15), four-page whole removal (15, 60 physical receipts, 144 origin translation
checks), advice (1,650 returned remote bodies) and separate first-write faults
(116 real remote page installations). These are separate from the 32 zero removals.

## Build, recovery and retained artifacts

Only quick capacity checks were made against the previous measured build-cycle
budget of 234,189,644 bytes. The completed disk investigation/deletion was not
repeated. A private RAM overlay reused the existing build tree; Kbuild recorded
3,161 compile steps for the changed release dependencies. Eight unchanged clients
were reused. Runtime modules and test modules were built for the distinct release;
only the new userspace probe was compiled. No additional historical files were
deleted, and disks, snapshots, VM placement and recovery settings were unchanged.

Build/install/identity storage used **225,067,008 root bytes**. Final recovery has
**312,532,992 root bytes (298.05 MiB)** available, 10,031,104 data bytes, ample
inodes and empty RAM storage. The original 64-vCPU/24-GiB/two-NUMA VM, QEMU PID
257489 and real recovery snapshot were verified. Recovery boot files and 5,686
module files remain preserved, with the exact 73 runtime modules restored and
no test modules. No new kernel faults occurred; existing `fd0` floppy I/O messages
remain in captured boot logs. The unrelated cleanup document was left untouched.

| Identity | Value |
| --- | --- |
| Candidate Build ID | `4371336700c9bcccb45f455c9e85fd0af067e2a1` |
| Candidate manifest | `86e1e547e724bcef2e4b34848081a575a7cfc5ad8129682d8375d712639720d2` |
| Candidate boot | `7a77a5da-b0cd-472f-9e58-5cc4e3fe24ee` |
| New client SHA-256 | `83314067f6b7475e924d69b649c5838689f03fc65441a1e8bae490d83a9c57a7` |
| Focused result SHA-256 | `bb5393937a5ba82e13c219126d837425f5d68abb62981291d070c66b589c868b` |
| Recovery Build ID | `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960` |
| Recovery boot | `460c4f3d-2e21-4164-9d4e-46ec4125f3b4` |

One essential archive, **639,811 bytes**, is retained at
`bench/results/10.176.26.71/raw/tests/mm-zero-target-20261023/collect-1/essential.tar.gz`,
SHA-256 `d6c0460d08f58935839ac133145099083ccf00db27239fa2d860ba5af22e437d`.
One offline pass verified all 48 client/log pairs against recorded hashes.
The raw stage also keeps transport receipts, `final-health.json` and
`evidence-check.json`; previous archives and unchanged binaries were not copied
or rescanned. [Runnable commands](../../../../../tests/kernel/mmap_lock/zero_target/README.md)
reuse the image and frozen probes. This run executed `workflow.py prepare`,
`build`, `kd`, `recovery`, then one `collect`, each at attempt 1.

## Remaining limits and next step

Zero targets without an ordinary private survivor remain refused. Larger mappings,
complex ancestry, shared private pages, swap/huge/device pages, general table
freeing and mmap creation remain outside scope. Forced VMA replacement, uncontrolled
write faults, reclaim/pinning races, allocation pressure, post-admission cancellation,
Native-off controls and non-root memory cgroups were not tested. Accounting uses
exact per-VMA walks; batched global RSS races were not exercised.

The next narrow extension is zero-target removal with only Z/U survivors in the
same three-page scope. It needs a valid-admission result separate from a nonzero
private-hold count, explicit handling of absent versus inherited VMA ancestry,
and PTE/TLB/cleanup checks even when no ordinary page is owned. Keep table-retaining
neighbors and current refusal rules until that distinct path is validated.
