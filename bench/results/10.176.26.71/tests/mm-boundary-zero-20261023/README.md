# kdmm17: shared-zero target at a retained table boundary

Completed on the existing `10.176.26.71:2222` VM. `6.1.159-kdmm17` adds one-page
shared-zero prefix/suffix removal from a three-page anonymous VMA (virtual memory
area). **74 serial cases, two basic tests and 1,979 negative receipt controls
passed**, with **38 different-task zero-target removals**, including **18 without
private-page holds**. All 18 zero-target layouts matched native behavior.
Six reversed empty-target layouts also passed, closing the kdmm16 gaps.
Recovery is restored and test modules are unloaded. The
[completed kdmm16 campaign](../mm-boundary-empty-20261023/README.md) remains separate
and was not repeated. No timing was performed.

## Mechanism and exact scope

With 4-KiB page size P and 2-MiB page-middle-directory (PMD) boundary B:

| Shape | Original VMA | Removed range | Native retention bounds after split |
| --- | --- | --- | --- |
| Prefix | `[B-P, B+2P)` | `[B-P, B)` | original preceding VMA end to B |
| Suffix | `[B-2P, B+P)` | `[B, B+P)` | B to original following VMA start |

The target occupies its interval alone; both survivors occupy the adjacent one
within the same valid upper directory. Both real outer neighbors remain
mandatory: preceding end above the first PMD base, following start below the
second interval's end. Native `free_pgd_range()` rounding must return before any
table walk. Another populated leaf entry is not a substitute for that proof.

Under actual mmap write ownership, the executor walks the current hierarchy and
locks the target PTE (leaf page-table entry). It accepts only an empty entry or
a present, special, read-only, non-device, non-protection-none `is_zero_pfn()`
mapping. The strict zero classifier is shared with the earlier same-table path;
the complete boundary-specific retention proof remains separate. Ordinary
private targets and other special entries refuse before survivor holds or any
split. No unlocked/prepublication table pointer is reused.

The native body clears the zero PTE and records TLB (translation lookaside
buffer) invalidation. `vm_normal_page()` returns NULL for that special zero
mapping, so no private resident accounting, reverse-map unlink or page release
applies to the target. A reverse map associates private pages with their
mappings. Neither KD nor the native zero route owns or modifies the shared page.
Only private survivors receive the existing exact holds; admission also works
with zero holds, absent anonymous metadata and a missing survivor table.
Caller-prepared VMA, mapping-index and reverse-map resources retire unchanged.

Success requires a cleared target entry and exact parent/target/survivor table
identities. An admitted split error instead requires the original zero PTE to
remain, ignoring only the hardware accessed bit. Both outcomes check unchanged
table-byte accounting and exact survivor references. Errors after splitting
never authorize local replay. Unsupported work returns to the waiter with an
exact acknowledgment (ACK); sticky fallback keeps later calls local. Readers
remain concurrent and local. See the maintained
[execution flow](../../../../../kernel_integration/mmap_lock/UNMAP.md#shared-zero-target-in-a-retained-boundary-table).

## Results and separate coverage work

`focused-1` ran once on one candidate boot. Native controls use the ordinary
munmap body on the same KD backend, not a Native-off boot. R/Z/U denote private
resident, shared-zero and untouched survivors, ordered by increasing address.

| Group | Cases | Result |
| --- | ---: | --- |
| Prefix/suffix × all nine R/Z/U survivor pairs × native/delegated | 36 | 18 matched layouts; 36 remote zero removals |
| Post-split ENOMEM: prefix-RZ and suffix-UU, native/delegated | 4 | Two remote errors; original target zero PTE and native-compatible split preserved |
| Retention loss, both directions, native/handback | 4 | Exact ACK/sticky route; native releases one target table |
| Controlled zero-to-private target, both directions, native/handback | 4 | Same table, pre-effect refusal, exact new page lifetime/ACK |
| Shared target/survivor interval and queued cancellation, both directions | 4 | Two geometry refusals; two cancelled victims retain their mappings |
| Waiting survivor fault, native/delegated | 2 | Two more remote zero removals; fault resolves locally after writer release |
| Busy final private survivor | 1 | Exact earlier hold retired before refusal |
| Reversed empty-target gap closure | 12 | Prefix/suffix × ZR/UR/UZ × native/delegated; six matched layouts, 12 remote empty removals |
| Preservation smokes | 7 | Missing boundary edges, empty edge and private transition, same-table zero RZ/UU and target transition |

The **55 new-path cases** rejected 1,449 corrupted receipts/observations and
matched seven handbacks/ACKs and two cancellations. Their 23 native success
comparisons comprise 18 layouts, two retention-loss cases, two private
transitions and one waiting fault; two native error comparisons are separate.
The **12 gap-closure cases** rejected 344 corruptions and add six native
comparisons. No reversed zero-target pair was omitted. The **seven smokes**
rejected 186 corruptions and produced six missing/empty boundary removals, five
same-table zero removals, one same-table changed-private removal and one ACK.
These preservation counts are excluded from the 38 new-path completions.

Targets are established by real read faults and verified through read-only PTE
walks, not zero values alone. The retaining neighbor and independent anchor are
also verified shared-zero mappings. Origin tasks warm existing R/Z translations
without touching U slots, then check `SEGV_MAPERR` on the same CPU after removal.
Before survivor access, checks cover VMA bounds/offsets/flags, map counts, private
resident accounting, PTE/table identities, reverse-map links and exact page
references. Later U faults, zero reads and isolated private writes preserve
other survivors and the independent zero mapping. Neighbors remain unchanged.
Full local cleanup removes every fixture and observes missing upper entries,
proving eventual release of retained tables.

Request-bound examples from `KD_MM_BOUNDARY_ZERO` receipts:

- Prefix-RZ request **2**: origin **1879**, executor **1878**, shared-zero physical
  frame number (PFN) **3748**, target table **343692**, one private survivor
  hold/release.
- Suffix-UU request **2**: origin **2009**, executor **2008**, target table
  **35632a**, missing survivor table, zero private holds, target entry cleared.
- Suffix-UU error request **2**: origin **2051**, executor **2050**, result
  **-12**, target table **34efc2**, original zero PTE retained, zero holds.
- Prefix zero-to-private: local reader **2034** performs the write fault with
  two requests published, two reader shares and closed admission. Table **344589**
  stays identical; request **2**, origin **2031**, executor **2030**, then hands
  back and ACKs. It is not counted as remote removal. The new private reference
  moves from mapping/reference counts 1/2 to 0/1, then is released exactly.

Retention loss is controlled **before publication** by moving the target-side
neighbor away while observing the same target table and genuine zero PTE. A
queued VMA replacement would need writer ownership incompatible with the held
reader shares; it is not tested. The controlled write fault is also distinct
from uncontrolled concurrent write-fault, reclaim or pinning races.

## Build, storage, evidence and recovery

Implementation commit `e7b19e0` changes only `mm/kd_mmap_unmap.inc` in the captured
kernel source. `build-1` passed probe/module/kernel compilation, syntax checks and
both basic tests, then installation failed because the driver named the runtime
module record `modules-build-1.json` while the installer requires its historical
`modules-build-2.json` name. No install destination or boot had begun. Commit
`1551917` preserves the failure and adds `finish-build-1`: it reverified completed
outputs, supplied the metadata alias and finished installation/identity capture
**without recompiling or repeating basic tests**. This packaging failure is not
a kernel correctness failure. Four unchanged clients were reused. The distinct
release triggered 3,155 dependency-driven C compilations; no clean/full-tree
build command was used, and no correctness rerun was needed.

The initial root check found 208,068,608 bytes, below the existing measured
260,000,000-byte cycle budget. With exact-file approval, only
`/root/kdlock-kernel-work/mm-populated-unmap-20261022/candidate-1/linux/arch/x86/boot/compressed/vmlinux.bin`
was removed after verifying inactivity and its source-host recovery copy. This
regenerable intermediate is outside the captured identity. The
[cleanup receipt](../../raw/tests/mm-boundary-zero-20261023/cleanup/result.json)
records 61,775,872 bytes reclaimed; the
[verified backup](../../raw/tests/mm-boundary-zero-20261023/cleanup/backup-receipt.json)
and recoverable file remain intact. No other permanent deletion occurred.

Root had 268,984,320 bytes before building, 47,517,696 after installation/capture,
and **42,459,136 bytes (40.49 MiB)** after recovery. Packaging/link intermediates
used RAM; recovery images, sources, snapshots and VM configuration were preserved.
Another cycle with the same 260,000,000-byte budget is short 217,540,864 bytes
at that final observation and must not start without adequate headroom.

| Identity | Value |
| --- | --- |
| Run | `mm-boundary-zero-20261023 / build-1 → finish-build-1 / focused-1` |
| Compiled source commit | `e7b19e0518989353d131f999960be48362476874` |
| Candidate Build ID | `c45730fe4eeeda4bbfe2b868762d7035fbc15a7d` |
| Candidate manifest SHA-256 | `aaef3cc71de7dc3ec77bd0974a0f2d4adbde6529b8203e86e0f315ed78c318ad` |
| Candidate boot | `6db80377-9193-4df3-91a5-64eb84010ddc` |
| Recovery boot | `4ac13b89-1f03-4acc-8998-1394d72e49c1` |
| Recovery Build ID | `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960` |
| Essential archive bytes | `631691` |
| Essential archive SHA-256 | `2b4db4e0aafba4263b2f50836ffcb30a296b5be20deb14d5233b8d606ab747dd` |

One [essential archive](../../raw/tests/mm-boundary-zero-20261023/collect-1/essential.tar.gz)
contains the new logs, observations, receipts and frozen sources, including the
failed install invocation. The [offline audit](../../raw/tests/mm-boundary-zero-20261023/collect-1/audit.json)
verified all 148 case-file hashes, 32 original input hashes, 15 archived probe
source hashes, continuation controls and remote counts. Prior archives were not
recopied or rescanned. Guest binaries and captured kernel identity remain under
`/root/kdlock-evidence/10.176.26.71/tests/mm-boundary-zero-20261023` and
`/root/kdlock-kernel-work/mm-boundary-zero-20261023`.

After archive verification, [recovery verification](../../raw/tests/mm-boundary-zero-20261023/recovery-1/transition.json)
and [final health](../../raw/tests/mm-boundary-zero-20261023/final-health.json)
confirmed idle `6.1.159-kdclobber2`, all 73 original runtime modules, 5,686
preserved module-file hashes, no test modules, cleared one-shot selection and
RAM scratch. No kernel fault matched the run/recovery checks. The same six
historical `fd0` read-error lines remain recorded in recovery evidence.

## Reproduction and limits

Reuse the installed candidate on the same idle VM after a current boot/log
capacity check. Completed directories are immutable; no build is needed:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-zero-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-zero-20261023/workflow.py recovery --attempt 2
```

See the [probe guide](../../../../../tests/kernel/mmap_lock/boundary_zero/README.md)
for direct guest commands and frozen receipt paths. Never reboot an in-flight
or undrained failed run.

Ordinary private boundary targets, target/survivor interval sharing, interior
crossing, larger mappings, cross-upper-directory geometry, missing higher levels,
huge/other special entries, complex ancestry and general delegated table
destruction remain refused. Special-entry injection, queued neighbor replacement,
uncontrolled write-fault/reclaim/pinning races, forced allocation failure,
post-admission cancellation and Native-off controls were not tested. Queued
missing/empty-to-zero transitions were not newly exercised. Advice, first-write,
whole-removal matrices and the historical campaigns were not repeated.
Performance, p95, mutex regressions and nano reruns remain deferred.

The next useful extension is **one ordinary private boundary target under the
same retention proof**, after reviewing the existing bounded same-table page
hold, reverse-map unlink, TLB completion and final release path. It remains
explicitly refused in kdmm17; general table freeing is a separate later problem.
