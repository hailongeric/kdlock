# Shared-zero interior target beside a private survivor

`kdmm29` removes one shared-zero middle target from a three-page anonymous VMA
(virtual memory area) crossing a 2-MiB boundary. The near survivor, in the same
leaf table as the target, is an eligible ordinary private resident page; the far
survivor is private resident, shared zero or untouched. Both original outer
neighbors and the native two-split table-retention proof remain mandatory.

All **48 serial cases, two basic tests and 1,057 negative receipt controls**
passed. Six native-matched layouts produced **12 different-task zero removals**;
two queued empty-to-zero conversions added two more zero removals. Recovery is
restored and modules unloaded. See the [results](../../../../bench/results/10.176.26.71/tests/mm-boundary-interior-zero-near-private-20261024/README.md)
and [mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#shared-zero-interior-target-with-a-private-near-survivor).

For page P=4 KiB and boundary B=2 MiB, left maps `[B-2P,B+P)` and removes
`[B-P,B)`; right maps `[B-P,B+2P)` and removes `[B,B+P)`. Survivor letters are
in address order: R=ordinary private, Z=shared zero, U=untouched. All left
RR/RZ/RU and right RR/ZR/UR cases are covered, without deduplication. Read faults
create the zero target; locked PTE (page-table entry) walks prove its zero-page
classification and the untouched far state before any survivor data access.

The client accepts `native|target middle-PAIR left|right [MODE]`:

| Mode | Check |
| --- | --- |
| `success` | Different-task body, target faults, survivor identities/content/accounting |
| `error1`, `error2` | Native-matched `-ENOMEM` after first/second split; zero PTE preserved |
| `change-private` | Queued zero-to-private target fault; safe handback |
| `change-near-busy`, `change-far-busy` | RR survivor page lock changes after publication; early/late hold rollback |
| `free-table` | Required outer guard disappears before publication; safe refusal |
| `cancel` | Published cancellation, intact victim mapping and exact retirement |

Both orientations have native controls for every non-cancellation mode. The
existing empty-target/private-near client is also rebuilt for `change-zero`:
three queued requests and two local readers establish a pre-execution read fault,
then full revalidation selects the zero body. Other private target states still
hand back with exact ACK (acknowledgment) and sticky local fallback. Historic
refusal fixtures remain bound to their captured kernels and frozen clients.

Initial checks precede far-U access. Later zero reads, private writes, near-page
write isolation and demand faults preserve other survivors, neighbors and an
independent zero mapping. Removed addresses fault again afterward. Zero pages
have no ordinary page references; the PTE probe reports their classification,
while its `pfn[]` array contains only private-page frame numbers. Kernel receipts
and native/queued transitions independently record the shared-zero identity.

Reuse installed outputs on the same idle VM with verified recovery:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-zero-near-private-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-zero-near-private-20261024/workflow.py recovery --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-zero-near-private-20261024/audit.py
```

`run --attempt 2` avoids rebooting an already verified candidate. Audit checks
fixed evidence offline. Do not repeat build/preparation, overwrite attempts or
force unload. Exact final-image BTF (module type metadata) compatibility is
required; matching symbol versions alone is insufficient.

Private interior targets, larger VMAs, complex ancestry and general table
destruction remain unsupported. Queued zero/untouched-to-private near creation,
interior neighbor replacement, opposite guard loss, huge/special-entry injection,
allocation exhaustion, uncontrolled fault/write/reclaim/pinning races and
hibernation remain untested. No new waiting-fault fixture was run. Performance
and deferred campaigns remain out of scope.
