> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# kdmm22 follow-up: queued neighboring-VMA replacement

Completed on the original VM: **38 serial cases, two basic tests and 1,241
negative receipt controls passed**. This is test-only validation on installed
**6.1.159-kdmm22**; there was no kernel rebuild, installation or admission change.
The [48-case missing-table baseline](../mm-boundary-shared-missing-20261024/README.md)
was preserved and not rerun. Recovery is restored and modules are unloaded.

## What changed and why

The old fixture held two read shares, which prevented a real neighboring-VMA
replacement while requests queued. A VMA is a virtual memory area. The new
correctness-only `neighbor_gate.inc` uses native `mremap`'s callback while its
originating task holds the actual mmap writer. Native code has created the
new VMA; the old VMA remains nearest to the target at publication. After real
unmap requests queue, the controller releases the callback. Native code retires
the old VMA under the same owner and releases its lock. The combiner then uses
current locked neighbors and the unchanged retention proof. It never borrows
an owner or unlocks on the writer's behalf. `mremap` itself runs locally.

Each target is still a three-page anonymous VMA across a 2-MiB page-table boundary;
only one prefix/suffix page is removed. Both neighboring-VMA guards are mandatory:
preceding end above the first table interval base, following start below the
second interval end, plus native `free_pgd_range()` floor/ceiling rounding that
retains the tables. Missing leaf tables need existing upper levels and an
untouched near survivor. Empty PTEs (leaf page-table entries), shared-zero PTEs
and ordinary private targets retain their complete existing classifiers and
reference rules. No new page type, geometry or teardown operation is admitted.

Read-only device-backed neighbors start untouched. Their eventual faults map
one ordinary module-owned zero-filled page, never the kernel shared zero page.
Exact file-page references and VMA lifetimes are tracked through cleanup. PTE,
content, per-VMA resident accounting, independent shared-zero isolation and
removed-address fault checks run before/after survivor reads and writes. A
native move may allocate a destination table when its source table exists;
the receipt accounts for that caller-side allocation separately. The missing
target table is never allocated merely to remove its virtual mapping.

## Results

`focused-1` ran once without a build, client, kernel or receipt-validator failure.

| Group | Serial cases | Result |
| --- | ---: | --- |
| Missing table: both edges × both neighbor sides × preserving/loss move × native/KD | 16 | Eight native matches; eight remote removals, four handback/ACK pairs |
| Empty/zero/private targets: preserving and loss representatives, native/KD | 12 | Six native matches; six remote removals, three ACK pairs |
| Post-split ENOMEM after replacement, both edges, native/KD | 4 | Two remote errors match native harmless splits; no replay |
| Queued fatal cancellation, both edges | 2 | Victim mapping preserved, ownership/resources retired |
| Existing missing/empty/zero/private smoke clients | 4 | Eight separate remote removals, concurrent local readers |

The 34 new cases rejected **1,091** damaged receipts; four smokes rejected
**150**. There were **14 native success comparisons and two native error
comparisons**. Of the **14 different-task removals in new queues**, **seven
remove the VMA whose neighbor changed**, and seven remove unchanged peers.
Eight of the 14 hold no private pages. Seven loss cases verify exact handback
and acknowledgment (ACK), followed by a local third request. Local fallback and
native queue heads are excluded from remote counts. Split errors and two
cancellations leave no duplicate removal, lost survivor, stranded ACK or
reference/accounting leak.

Examples from the [audited receipts](../../raw/tests/mm-neighbor-replace-20261024/collect-1/audit.json):

- Prefix-UR: native writer **1932** retires the old left neighbor while three
  requests are pending. Origin **1930** then completes on combiner **1929**.
  The body's floor is **`0x80000047fc000`**, the new neighbor's end, rather than
  the old end `0x80000047fd000`. Target table remains absent; one far private
  page is held/released exactly.
- Suffix-ZU: writer **1967** retires the right neighbor; origin **1965** runs on
  **1964**, with zero private holds. Ceiling **`0x8000004804000`** is the new
  neighbor start. The target and near-survivor table remains absent.
- Suffix shared-zero target: origin **2007**, executor **2006**, writer **2009**;
  zero PFN `0x3748` is not owned or released, and native TLB (translation
  lookaside buffer) completion is recorded.
- Prefix retention loss: writer **1946** retires the old neighbor before origin
  **1944** receives handback/ACK from **1943**. The body performs no destructive
  effect before fallback, and the third request remains local.
- Suffix injected error: origin **2040**, executor **2039**, result **-12** after
  the harmless split; target table remains missing and the mapping is not replayed.

## Build, storage and evidence

Implementation source: **`73b1f35acfd943bcf5d147e17fc41048c096d389`**. One test
module and four new clients compiled; four unchanged smoke binaries were reused.
Captured kdmm22 sources/configuration/build identities were checked unchanged
after the external module build. Intermediates used a private RAM overlay and
vanished at the normal boot; the mount was removed before boot. No permanent
file was deleted and no old archive or compressed kernel identity was copied
into a new durable archive. Existing cleanup backups remain intact.

Measured root budget **19,545,442 bytes** derives from source **342,864**, prior
module **721,320**, maximum client **96,624**, prior focused logs **822,041**,
copy/growth allowance and the existing **15,000,000-byte** boot/test allowance.
RAM budget **1,836,378,852 bytes** includes captured ELF hydration and temporary
build/transport storage. Root free was **4,034,367,488** before build,
**4,032,602,112** afterward, and **4,028,477,440** after recovery. No cleanup or
new build/install cycle was needed to obtain headroom.

Essential records:

- [Build and capacity](../../raw/tests/mm-neighbor-replace-20261024/build-1/result.json),
  [serial result](../../raw/tests/mm-neighbor-replace-20261024/kd-1/result.json),
  [audit](../../raw/tests/mm-neighbor-replace-20261024/collect-1/audit.json).
- [Single essential archive](../../raw/tests/mm-neighbor-replace-20261024/collect-1/essential.tar.gz):
  **395,337 bytes**, SHA-256
  `8da3c492141ec4ebabfdccc78f4e69717a62635d28d1d116c4cd1bdb47631734`.
  Audit binds **48 frozen inputs**, **42 probe sources** and **76 client/log hashes**.
- [Recovery verification](../../raw/tests/mm-neighbor-replace-20261024/recovery-1/result.json),
  [final health](../../raw/tests/mm-neighbor-replace-20261024/final-health-2.json),
  [host snapshot/placement](../../raw/tests/mm-neighbor-replace-20261024/final-host.json).

Kernel Build ID remains **`f64c0542dcd5c756d28f1681d7f712d03babd159`**, manifest
SHA-256 **`726e4d89eee54f013ea5b2270e9634c44aa74eeb44b1c5425a8c4f2706d07fb3`**.
Candidate boot **`1523cdf6-3ec2-4a75-823b-798ff89dfebc`**; recovery boot
**`97f4636e-3a36-4b3b-9a8b-c76492ef1f42`**. Recovery is
**6.1.159-kdclobber2**, Build ID **`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`**,
with **5,686 recovery-module hashes** preserved, the original 73 runtime modules,
no test module, no armed next boot and no RAM build scratch. Original snapshot,
QEMU PID 257489, 64 vCPUs, 24 GiB, two NUMA nodes and placement are unchanged.

One **reporting check** failed after recovery: an overbroad `fb_` prefix matched
native `fb_sys_fops`. The exact expected-module comparison had passed. Its
[stderr](../../raw/tests/mm-neighbor-replace-20261024/final-health.json.stderr)
is preserved. The corrected read-only report requires the full exact module
set and absence of test modules; it passed without a test or boot rerun. This
was not a kernel correctness failure. Historical `fd0` boot I/O messages remain
separate; no new kernel fault was found.

## Commands and limits

[Probe guide and execution flow](../../../../../tests/kernel/mmap_lock/neighbor_replace/README.md)
contain guest commands and precise timing. Deliberate future reruns reuse the
installed kernel and completed build; do not overwrite attempt 1:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-neighbor-replace-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-neighbor-replace-20261024/workflow.py recovery --attempt 2
python3 bench/results/10.176.26.71/tests/mm-neighbor-replace-20261024/audit.py
```

`run --attempt 2` avoids a boot on an already verified kdmm22 VM. The audit is
read-only and checks the retained attempt-1 evidence, not a live test.

Destination creation precedes publication; native old-neighbor retirement
follows publication. This deterministic ordering does not cover uncontrolled
fault/reclaim/pinning races, same-address replacement, populated neighbor moves,
target-VMA replacement or forced native relocation allocation failure. New
empty/zero/private cases are representative controls, not full matrices.
The writer correctly excludes readers; four preservation smokes retain the
existing concurrent local-reader checks. Prior advice/first-write and broader
campaigns were not repeated.

The next small functional candidate is interior one-page removal in the same
three-page boundary geometry, after a separate two-split retention/error proof.
Larger VMAs, complex ancestry, missing higher levels, huge/special entries,
general table destruction, performance/p95, mutex regressions and nano reruns
remain deferred. This stage makes no performance or general mmap-support claim.
