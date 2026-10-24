# Empty interior target in an existing table

`kdmm24` removes the middle 4-KiB page of a three-page anonymous VMA (virtual
memory area) across a 2-MiB boundary. Its leaf PTE (page-table entry) must be
empty in an existing table. The near survivor stays untouched; the far survivor
may be ordinary private resident, shared zero or untouched. Both original
neighboring-VMA guards and the kdmm23 two-split retention proof remain required.
No target page is allocated. A missing table uses the preserved kdmm23 path;
special entries, populated targets and populated near survivors are refused.

All **44 serial cases, two basic tests and 1,090 negative receipt controls**
passed, with **16 new different-task removals** and 12 separately counted remote
smoke removals. See the [result record](../../../../bench/results/10.176.26.71/tests/mm-boundary-interior-empty-20261024/README.md)
and [mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#empty-interior-target-in-an-existing-table).
Recovery is restored and test modules are unloaded.

## Setup and execution

For page size P and boundary B, the `left` VMA is `[B-2P,B+P)` with target
`[B-P,B)`; `right` is `[B-P,B+2P)` with target `[B,B+P)`. R/Z/U denote private
resident/shared zero/untouched in increasing survivor-address order. The six
supported layouts are left `middle-ur/uz/uu` and right `middle-ru/zu/uu`.

A read of the target-side outer-neighbor VMA creates the leaf table while target
and near survivor remain empty. Locked kernel walks verify both empty PTEs,
nonzero table PFN (physical frame number), upper levels and geometry before any
survivor access. No target write or read is used to establish this initial state.

The origin supplies the existing two VMA descriptors, maple-tree reserves
(storage for the VMA index) and reverse-map links before publication. Reverse
maps connect private pages to their mappings; absent metadata consumes no links.
Under the actual mmap writer, execution rewalks current tables and checks the
target with `pte_none()` under its PTE lock. The near survivor must also be empty.
Eligible far private pages receive exact temporary references/locks. Both native
splits and the actual surviving bounds establish floor=`start`, ceiling=`end`,
so native table freeing returns without walking any table. The table PFN, empty
target, surviving entries, VMA/page counts and reference retirement are checked
through completion and admitted errors.

Pre-effect refusal uses waiter handback, exact ACK (acknowledgment) and sticky
local fallback. Errors after either split retain native-compatible harmless
splits and never replay the removal locally. Readers remain concurrent and local.

The client accepts `native|target middle-PAIR left|right [MODE]`:

| Mode | Check |
| --- | --- |
| `success` | Real different-task removal and surviving state/accounting |
| `error1` / `error2` | ENOMEM after first/second split, compared with native |
| `change-zero` / `change-private` | A real native target fault after two queue publications; locked refusal and matching ACK |
| `free-table` | Target-side outer neighbor moves before publication; table stays present, retention prerequisite fails |
| `fault` | Near-survivor read fault waits for writer release, then fills an empty PTE locally without allocating a table |
| `cancel` | Queued fatal cancellation preserves the victim and retires prepared resources |

Each mode runs in both orientations. Private/zero/untouched state, resident
accounting and contents are observed before explicit survivor access. Later
zero-fill reads and isolated writes must preserve other mappings and leave the
removed address inaccessible. Independent shared-zero isolation and complete
fixture hierarchy cleanup are checked. Native controls use the ordinary native
body on the same KD backend with delegation disabled, not a Native-off boot.

## Reproduction

On `380G10`, verify the original VM is idle and has current boot/log headroom.
Reuse the installed candidate and completed probes with a fresh attempt:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-empty-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-empty-20261024/workflow.py recovery --attempt 2
```

`run --attempt 2` avoids a boot on a verified kdmm24 candidate. These commands
run 38 new cases and six preservation smokes serially, including strict receipt
validation and negative controls. Attempt 1 is completed evidence; do not repeat
its `prepare` or `build`. A timeout is not drain; never force module unload.

Equivalent guest invocation after verified candidate boot:

```sh
env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mm-boundary-interior-empty-20261024/control/focus.py \
  --build-attempt 1 --run focused-2
```

Queued near-survivor changes, interior neighbor replacement, opposite-side guard
loss, huge/special entries, missing higher levels and allocation exhaustion were
not injected here. Controlled target changes do not establish uncontrolled
fault/reclaim/pinning race coverage. Populated interior targets, populated near
survivors, larger VMAs, complex ancestry and general table destruction remain
unsupported. The empty target has no cached translation; populated-target TLB
(translation lookaside buffer) checks belong to preservation smokes. No broad
campaign or performance work was run.
