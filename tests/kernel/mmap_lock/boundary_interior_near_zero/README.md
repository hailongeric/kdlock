# Shared-zero near survivor beside a shared-zero interior target

`kdmm26` removes the middle page of a three-page anonymous VMA (virtual memory
area) crossing a 2-MiB boundary while preserving a shared-zero near survivor.
The target also must map the shared zero page. The far survivor may be ordinary
private resident, shared zero or untouched. Both outer neighboring-VMA checks
and the separate two-split native table-retention proof remain mandatory.
Private targets and private near survivors are refused before splitting.

All **40 serial cases, two basic tests and 905 negative receipt controls**
passed. The new layouts produced **12 different-task removals**, eight without
private-page holds; six preservation smokes added 12 separate remote removals.
Recovery is restored and test modules are unloaded. See the
[result record](../../../../bench/results/10.176.26.71/tests/mm-boundary-interior-near-zero-20261024/README.md)
and [mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#shared-zero-near-survivor-for-a-zero-interior-target).

## Geometry and protocol

For 4-KiB page P and 2-MiB boundary B, `left` uses `[B-2P,B+P)` and removes
`[B-P,B)`; `right` uses `[B-P,B+2P)` and removes `[B,B+P)`. Survivor letters are
in address order: R means ordinary private resident, Z means a verified shared
zero mapping, U means untouched. All six selected layouts are left
`middle-zr/zz/zu` and right `middle-rz/zz/uz`.

The probe read-faults target and near survivor, then verifies their PTEs
(page-table entries) through locked kernel walks. Neither is written during
setup. The far U address stays untouched until after initial state/accounting
checks. Reading zero values alone does not establish a shared-zero mapping.

The caller supplies the existing two VMA descriptors, maple-tree reserves
(mapping-index storage) and reverse-map links. Reverse maps connect private
pages to their mappings; absent metadata consumes no links. The mmap writer
rewalks current tables and validates both outer guards and native retention
bounds. Under the PTE lock, a zero target permits an exact shared-zero near PTE;
missing/empty target classes retain their original untouched-near requirement.
Neither zero page receives a private-page hold. Any far private page keeps its
exact temporary reference and lock through native teardown.

Two native splits establish actual floor=`start`, ceiling=`end`, preventing a
table-freeing walk. Native removal clears only the target and completes TLB
(translation lookaside buffer) invalidation. The original near PTE, both table
identities and survivor contents remain checked through success and split
errors. Pre-effect refusal uses exact waiter handback/ACK (acknowledgment) and
sticky local fallback. Errors after splitting are returned through the admitted
request, preserving native-compatible harmless splits without local replay.

The client accepts `native|target middle-PAIR left|right [MODE]`:

| Mode | Check |
| --- | --- |
| `success` | Actual remote removal, near/far PTEs, contents and accounting |
| `error1` / `error2` | Native-matched error after first/second split |
| `free-table` | Prepublication loss of a required outer guard; safe handback |
| `change-private` | Queued target write fault; private target hands back |
| `change-near-private` | Queued near-survivor write fault; private near hands back |
| `cancel` | Published waiter cancellation and exact resource retirement |

The conversion controls use native `get_user_pages()` under an already held
local read share. They record two pending requests, two readers, closed writer
admission and unchanged table identity. Left near conversion starts without
reverse-map metadata; right conversion uses a private far survivor and checks
rollback of that earlier hold before ACK. The new private survivor reference
is tracked separately from immutable setup masks. Readers remain concurrent
and local; these are deterministic controls, not uncontrolled race coverage.

## Reproduction and limits

Reuse installed outputs after checking idle state and the existing recovery
snapshot; attempt 1 is completed evidence:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-zero-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-zero-20261024/workflow.py recovery --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-zero-20261024/audit.py
```

`run --attempt 2` runs the serial set without another boot on an already verified
kdmm26 candidate. The audit checks saved attempt-1 bytes on the source host.
Do not repeat preparation/build or force unload on a timeout.

Subsequent zero-fill reads, isolated writes and far-U demand faults are covered.
A waiting local fault is covered by one reused kdmm25 preservation case; no new
fault-wait fixture was needed for an already mapped zero near survivor. Queued
interior neighbor replacement, opposite guard loss, zero-to-empty transitions,
huge/special-entry injection, allocation exhaustion and uncontrolled fault,
reclaim or pinning races remain untested. Private targets/near survivors, larger
VMAs, complex ancestry and general page-table destruction remain unsupported.
