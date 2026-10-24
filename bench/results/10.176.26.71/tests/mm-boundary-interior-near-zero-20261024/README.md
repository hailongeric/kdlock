> **Retired experiment — outside the current scope.** This is preserved historical evidence, not a current feature or runnable campaign. The maintained work is [lock implementation and minimal API adaptation](../../../../../kernel_integration/mmap_lock/README.md). Body-specific code and runners were removed; use the recorded historical source commit to inspect the experiment. Numeric results, failures and artifact identities below are unchanged.

# kdmm26: shared-zero near survivor for a zero interior target

Completed: **40 serial cases, two basic tests and 905 negative receipt controls
passed**. Six native-matched layouts produced **12 different-task removals**,
including eight without private-page holds. Six preservation smokes added 12
separate remote removals. Recovery is restored and modules are unloaded.
Implementation: **`fb06f775c7117f8f5ad7d1f4b25cbefb67331aa9`**. The completed
[kdmm25 campaign](../mm-boundary-interior-zero-20261024/README.md) was not repeated.

## Mechanism and scope

The previous interior path required the near survivor's PTE (page-table entry)
to be empty. The extension permits an exact shared-zero near PTE only when the
target is also shared-zero. Both remain outside private-page ownership,
reverse-map removal and page release. The far survivor retains the existing
ordinary private resident/shared-zero/untouched subset. Private interior targets
and private near survivors still hand back before either split. Missing/empty
targets keep their untouched-near restriction.

The VMA (virtual memory area) remains exactly three 4-KiB pages crossing one
2-MiB boundary within one upper-table interval. For boundary B and page P:

| Orientation | Original VMA | Removed target | Survivor pairs in address order |
| --- | --- | --- | --- |
| left | `[B-2P,B+P)` | `[B-P,B)` | ZR, ZZ, ZU |
| right | `[B-P,B+2P)` | `[B,B+P)` | RZ, ZZ, UZ |

R is ordinary private resident, Z is shared zero, U is untouched. Locked kernel
walks prove genuine shared-zero target/near PTEs after read faults. No setup
write or accidental far-U access substitutes for this evidence.

Under the mmap writer, execution rewalks current VMA/table state and both outer
guards: previous VMA end exceeds the first interval base; next VMA start is below
the second interval end. The separate two-split proof verifies actual left
end=`start`, right start=`end` and native floor/ceiling rounding before teardown.
It prevents page-table freeing from walking these intervals. Native zap clears
only the target PTE and finishes TLB (translation lookaside buffer) invalidation.
The original near PTE, ignoring only its hardware accessed bit, and table
identities are checked again on success and error.

Existing caller-prepared split descriptors, maple-tree reserves (mapping-index
storage) and reverse-map links remain sufficient. Reverse maps connect private
pages to mappings; absent metadata consumes no links. Far private holds retire
exactly once. Pre-effect refusal retains handback, exact ACK (acknowledgment),
cancellation and sticky fallback. Errors after a split preserve native harmless
layouts and return through the admitted request without destructive replay.

## Focused validation

`prepare-1`, `build-1`, candidate boot `kd-1` and `focused-1` passed on the first
attempt. No build, probe, kernel-correctness or validator failure occurred.

| Cases | Count | Result |
| --- | ---: | --- |
| Six layouts, native/KD | 12 | Six native matches; 12 actual different-task removals |
| Both split-error points/orientations, native/KD | 8 | Four remote ENOMEM results match native harmless splits |
| Retention loss and queued target/near conversion, both orientations, native/KD | 12 | Six exact handback/ACK pairs, sticky fallback, no replay |
| Both orientations, queued cancellation | 2 | Victim mapping retained and resources retired |
| Prior zero/empty/missing interior preservation | 6 | Twelve separately counted remote removals |

The 34 new cases rejected **740** corrupted receipts; six smokes rejected **165**.
There were **12 native success comparisons and four native error comparisons**.
Native controls run the ordinary native body on the same KD lock backend with
delegation disabled. Near-conversion comparisons match the changed victim's
resident accounting; unchanged peer requests retain separately verified input
states. Local heads/fallback, admitted errors and cancellations are excluded
from successful different-task counts.

Examples from the exact body/ownership receipts:

- Left-ZR origin **1924** completed on **1922**, target-table PFN (physical frame
  number) `0x356520`, shared-zero PFN `0x3748`; one far private hold was released,
  with no ownership of either shared-zero page.
- Right-UZ origin **1965** completed on **1966**, table PFN `0x355c44`, zero
  private holds and a missing far leaf table. The target became inaccessible;
  the near zero PTE survived and the far address later faulted normally.
- Right queued near conversion: actor **2050** changed slot **5** to private
  while two requests were pending and two readers held shares. Table PFN
  `0x342905` and existing reverse-map root remained unchanged. Executor **2046**
  released its one earlier far hold with `effects=0`, then handback/ACK matched
  origin **2047**. Native waiter completion retained both private survivors.

Target accesses were warmed on pinned origin CPUs and faulted after removal.
Pre-access checks verified near/far PTEs, exact VMA boundaries, table bytes,
private contents and resident accounting. Later zero reads, isolated private
writes, far-U demand faults and independent/neighbor mapping checks passed
without restoring the hole. Both split-error points preserved target and near
zero PTEs. Two local readers overlapped. One old zero-target smoke exercised a
fault waiting for writer release. Complete local fixture cleanup retired the
upper hierarchy and every probe reference; module unload was normal.

## Build, storage and evidence

Only captured kernel source `mm/kd_mmap_unmap.inc` changed. The new client and
affected module were compiled; **15 unchanged clients were reused**. A distinct
release required 3,157 dependent C compilations and 73 runtime modules. The
private RAM build overlay was unmounted before boot; normal reboot cleared
its intermediates. No permanent deletion or extra backup archive was needed.
Reusable installed outputs and all previous evidence remain.

The measured budget was **120,000,000 root bytes** and **8,000,000,000 RAM bytes**.
Root free was **3,867,172,864** before build, **3,787,628,544** after installation
and **3,783,487,488** after recovery. Final RAM free: **12,613,750,784 bytes**.

Three recorded objtool warnings remain: two `ibt_selftest` stack-frame warnings
and `relocate_restore_code+0x43: relocation to !ENDBR: get_option+0x68`.
No build error occurred. These warnings were not resolved; hibernation/restore
was not tested.

- [Build](../../raw/tests/mm-boundary-interior-near-zero-20261024/build-1/result.json),
  [serial result](../../raw/tests/mm-boundary-interior-near-zero-20261024/kd-1/result.json),
  [offline audit](../../raw/tests/mm-boundary-interior-near-zero-20261024/collect-1/audit.json).
- [Single essential archive](../../raw/tests/mm-boundary-interior-near-zero-20261024/collect-1/essential.tar.gz):
  **636,832 bytes**, SHA-256 `899928dd99597e1468ff0d53c3334f27f6166668d5f3c8d473ee3f5a77665789`.
  Audit binds **68 frozen inputs**, **54 probe sources** and **80 client/log hashes**;
  generated module source is recorded separately.
- [Identity receipt](../../raw/tests/mm-boundary-interior-near-zero-20261024/identity/receipt.json):
  one source-host compressed ELF, **142,612,832 bytes**, SHA-256
  `6d5ffd78598ed98b5384dc0a8e921bfa3f7c9e9a3982ae9d73a4fbfe047c3c9e`.
- [Recovery](../../raw/tests/mm-boundary-interior-near-zero-20261024/recovery-1/result.json),
  [final health](../../raw/tests/mm-boundary-interior-near-zero-20261024/final-health.json),
  [snapshot/placement](../../raw/tests/mm-boundary-interior-near-zero-20261024/final-host.json).

Candidate **6.1.159-kdmm26**, Build ID `e7e5ced0445c820534db50f77f3f6d93d8a6ece9`;
manifest SHA-256 `411d170244fb4683f16fa6630f333a5d4dd319b2f1b9222cf83ca16f49c44e92`.
Candidate boot `26e55146-aaf2-4e0a-8ca1-710d704ef403`; recovery boot
`618ee035-b7d5-47c6-9f73-6d7a9b9fcf0a`. Recovery **6.1.159-kdclobber2**, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, retains 5,686 recovery-module hashes
and exactly 73 runtime modules. No test module, armed next boot or kdmm26 RAM
scratch remains. Snapshot, QEMU PID 257489, 64 vCPUs, 24 GiB, two NUMA nodes and
placement are unchanged. Historical `fd0` boot I/O messages remain separate;
no kernel fault was detected.

## Commands and remaining limits

[Probe guide](../../../../../tests/kernel/mmap_lock/boundary_interior_near_zero/README.md).
Reuse installed outputs with fresh attempt directories after checking idle state:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-zero-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-zero-20261024/workflow.py recovery --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-zero-20261024/audit.py
```

`run --attempt 2` avoids booting an already verified candidate. The offline audit
checks fixed attempt-1 evidence. One archive was collected before recovery;
recovery/health records are alongside it. Unrelated checkout work is untouched.

Private interior targets/near survivors, larger VMAs, complex ancestry and
general page-table destruction remain unsupported. Interior neighboring-VMA
replacement, opposite outer-guard loss, zero-to-empty changes, huge/special-entry
injection, missing higher levels and allocation exhaustion were not exercised.
Deterministic conversion controls do not establish uncontrolled fault/reclaim/
pinning race coverage. Earlier matrices, performance/p95, mutex regressions and
nano work remain deferred.

The next small candidate is a shared-zero near survivor beside an empty interior
target, retaining the same native retention proof. It needs explicit class and
queued-transition validation. No further stage was started; this is not general
mmap support.
