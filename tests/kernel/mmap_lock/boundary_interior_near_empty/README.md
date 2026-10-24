# Empty interior target beside a shared-zero survivor

`kdmm27` removes one empty middle page from a three-page anonymous VMA (virtual
memory area) crossing a 2-MiB boundary, while preserving a verified shared-zero
near survivor in the target table. The far survivor remains private resident,
shared zero or untouched. Both outer-neighbor checks and the separate two-split
native table-retention proof remain mandatory. Private interior targets and
private near survivors refuse before splitting.

All **44 serial cases, two basic tests and 1,139 negative receipt controls**
passed. The new cases produced **16 different-task completions**, 12 without
private-page holds: 14 empty targets and two after a controlled empty-to-zero
change. Six preservation cases added 12 separate remote removals. Recovery is
restored and modules unloaded. See the
[result record](../../../../bench/results/10.176.26.71/tests/mm-boundary-interior-near-empty-20261024/README.md)
and [mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#empty-interior-target-with-a-shared-zero-near-survivor).

## Setup and execution

For page P=4 KiB and boundary B=2 MiB, `left` maps `[B-2P,B+P)` and removes
`[B-P,B)`; `right` maps `[B-P,B+2P)` and removes `[B,B+P)`. Survivor letters are
in address order: R is ordinary private resident, Z is shared zero, U is
untouched. The six layouts are left `middle-zr/zz/zu` and right
`middle-rz/zz/uz`.

Read faults create the near and target-side neighbor zero mappings. The target
stays untouched and empty in that existing table. Locked PTE (page-table entry)
walks establish these states without populating the target or far-U survivor.
Both original outer guards must retain the two table intervals. The combiner
rewalks current VMA/table state under the mmap writer, checks prepared resources
and classifies the near survivor under its PTE lock. Shared zero pages acquire
no ordinary private-page ownership or release obligation.

The existing caller-prepared VMA descriptors, maple-tree reserves (mapping-index
storage) and reverse-map links suffice for both native splits. Reverse maps
connect private pages to mappings; absent ancestry consumes no link. Actual
post-split floor=`start`, ceiling=`end` must make native table teardown return
before any freeing walk. Native removal deletes the virtual mapping even though
its PTE was empty. Survivor PTEs, table identities, accounting and exact private
holds remain checked on success and error. Later survivor faults/writes must
not restore access to the removed address.

The client accepts `native|target middle-PAIR left|right [MODE]`:

| Mode | Check |
| --- | --- |
| `success` | Remote removal, survivor states, contents, layout and accounting |
| `error1` / `error2` | Native-matched error after first/second split; no replay |
| `change-zero` | Queued native read fault; fully revalidated kdmm26 zero body |
| `change-private` | Queued target write fault; safe handback |
| `change-near-private` | Queued near-survivor write fault; safe handback/hold rollback |
| `free-table` | Required outer guard removed before publication; safe refusal |
| `cancel` | Published waiter cancellation and exact resource retirement |

Queued changes use native `get_user_pages()` under an existing local read share.
The empty-to-zero control records three pending requests and two readers; it
owns no target page and preserves table/ancestry identity. Private transitions
record two pending requests and require exact handback/ACK (acknowledgment),
sticky fallback and no destructive replay. Left near conversion creates simple
ancestry; right near conversion retains an existing private far survivor and
proves release of its earlier hold before handback. Readers remain local and
concurrent. These are controlled transitions, not uncontrolled race coverage.

## Reproduction and limits

Attempt 1 is completed evidence. With the existing idle VM and verified recovery
snapshot, reuse installed outputs through the source-host coordinator:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-empty-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-empty-20261024/workflow.py recovery --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-empty-20261024/audit.py
```

`run --attempt 2` uses an already verified kdmm27 boot without another reboot.
The audit reads saved evidence on the source host. Do not repeat preparation or
build, overwrite attempt-1 evidence or force unload on a timeout.

Private targets/near survivors, larger VMAs, complex ancestry and general table
destruction are unsupported. Queued interior neighbor replacement, opposite
guard loss, zero-to-empty transitions, huge/special-entry injection, allocation
exhaustion and uncontrolled fault/reclaim/pinning races remain untested. No new
waiting-fault fixture or hibernation check was run. Three recorded objtool
warnings remain unresolved. Performance work remains deferred.
