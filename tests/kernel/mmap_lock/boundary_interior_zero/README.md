# Shared-zero interior target with retained tables

`kdmm25` removes the middle 4-KiB page of a three-page anonymous VMA (virtual
memory area) crossing a 2-MiB boundary when the target maps the shared zero
page. The near survivor stays untouched; the far survivor may be ordinary
private resident, shared zero or untouched. Both outer neighboring-VMA guards
and the separate two-split native retention proof remain mandatory.

All **40 serial cases, two basic tests and 867 negative receipt controls**
passed, including **16 new different-task removals**, 12 without private-page
holds. Six preservation smokes added 12 separately counted remote removals.
Recovery is restored and modules are unloaded. See the
[result record](../../../../bench/results/10.176.26.71/tests/mm-boundary-interior-zero-20261024/README.md)
and [mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#shared-zero-interior-target-with-native-clearing).

## Geometry and execution

For page size P and boundary B, `left` uses VMA `[B-2P,B+P)` and removes
`[B-P,B)`; `right` uses `[B-P,B+2P)` and removes `[B,B+P)`. Survivor pairs are
listed in increasing address order: R is ordinary private resident, Z is shared
zero, U is untouched. The supported pairs are left `middle-ur/uz/uu` and right
`middle-ru/zu/uu`. Populated near survivors remain outside this small subset.

The probe read-faults the target without writing it. A locked kernel walk proves
a present, read-only, special PTE (page-table entry) whose PFN (physical frame
number) is the shared zero page. Reading zero values alone is not evidence.
The near survivor must satisfy `pte_none()` before later access. Each origin
reads its target on its pinned CPU before publication, then checks that access
faults after removal, exercising cached-translation invalidation.

The caller prepares both VMA descriptors, maple-tree reserves (storage for the
mapping index) and reverse-map links. Reverse maps connect private pages to
their mappings; absent metadata consumes no links. Under actual mmap writer
ownership, the combiner rewalks current tables, checks the target under its PTE
lock, and revalidates VMA identity, both outer guards and native retention
bounds. It never owns or releases the zero page. Eligible far private pages
retain their existing exact temporary reference and lock.

The two native splits establish actual survivor bounds with floor=`start` and
ceiling=`end`, preventing native page-table freeing from walking these tables.
Native zap clears the target PTE and completes TLB (translation lookaside
buffer) invalidation. `vm_normal_page()` returns NULL for the zero page, so
ordinary private-page accounting, reverse-map removal and release are skipped.
The virtual mapping still disappears and mapped-page accounting decreases.

Pre-effect refusal uses waiter handback, exact ACK (acknowledgment) and sticky
local fallback. Errors after either split preserve native-compatible harmless
splits and return through the admitted request; removal is never replayed
locally. Readers remain concurrent and local.

The client accepts `native|target middle-PAIR left|right [MODE]`:

| Mode | Check |
| --- | --- |
| `success` | Real different-task removal, survivor state and accounting |
| `error1` / `error2` | Error after first/second split, preserving original zero PTE |
| `free-table` | Outer retention guard removed before publication; safe handback |
| `change-private` | Queued native write fault changes target to private; safe handback |
| `fault` | Near-survivor fault waits for writer release and fills the retained table locally |
| `cancel` | Published waiter cancels; mapping and exact retirement remain correct |

## Reproduction

On the source host, reuse the installed kernel and probes after confirming the
VM is idle and the recorded recovery snapshot is present:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-zero-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-zero-20261024/workflow.py recovery --attempt 2
```

`run --attempt 2` avoids a boot on an already verified kdmm25 candidate. These
commands run 34 new cases and six preservation smokes serially. Attempt 1 is
completed evidence; do not repeat its preparation or build. A timeout is not
drain; never force module unload. An equivalent guest invocation after verified
candidate boot is:

```sh
env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mm-boundary-interior-zero-20261024/control/focus.py \
  --build-attempt 1 --run focused-2
```

Private interior targets and populated near survivors remain refused. Queued
near-survivor changes, interior neighbor replacement, opposite outer-guard
loss, huge/special-entry injection, missing higher levels and allocation
exhaustion were not exercised here. The queued zero-to-private transition is
deterministic; it does not establish uncontrolled fault/reclaim/pinning race
coverage. Empty/missing-to-zero interior transitions were not newly tested.
Larger VMAs, complex ancestry and general page-table destruction remain outside
scope. No performance campaign was run.
