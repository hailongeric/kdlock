# Absent-target removal correctness probe

`6.1.159-kdmm13` removes one empty leaf PTE (page-table entry) from inside an
exactly three-page anonymous VMA (virtual memory area), at prefix, interior or
suffix position. All page-table levels through the leaf table must exist, with
the existing neighboring-VMAs constraint retaining that table. Swap, migration,
other special non-present entries and missing upper tables remain refused.
This is separate from the older untouched path requiring absent top-level PGDs
(page-directory entries). See the [mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#absent-targets-with-retained-leaf-tables)
and [completed result](../../../../bench/results/10.176.26.71/tests/mm-absent-target-20261023/README.md).

## Reuse the installed image

On source host `380G10`, with the VM/test slot idle and current capacity sufficient
for boot/log growth, use the next unused attempt number. Attempt 1 is completed
evidence. No rebuild or repeated preparation is needed for unchanged inputs.

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-absent-target-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-absent-target-20261023/workflow.py recovery --attempt 2
```

The workflow verifies recovery snapshot, VM placement, kernel identity and exact
runtime modules. It loads one test module, runs 51 cases serially and unloads only
after drain. A timeout is not drain; retain loaded state and inspect workers before
any recovery request. Final root capacity was only 27,774,976 bytes, so a future
build requires another capacity decision. Do not delete historical evidence.

On an already verified kdmm13 KD boot, the same focused run can execute without
another boot, with a new result name:

```sh
env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mm-absent-target-20261023/control/focus.py \
  --run focused-2
```

The frozen guest stage is
`/root/kdlock-evidence/10.176.26.71/tests/mm-absent-target-20261023`.
Its `build-1/result.json` binds the new absent client, one test module and four
reused clients to the kernel capture. The thin client includes the shared
zero-target source with `KD_TEST_ABSENT=1`; the reused zero-target **binary** still
has its original kdmm12 identity. No existing ioctl encoding or layout changed.

## Inputs and observations

R means ordinary private resident, Z verified shared-zero mapping and U an empty
leaf. `native SHAPE` uses the ordinary munmap body on the same KD lock backend;
`target SHAPE` enables the prepared delegation path. SHAPE combines `prefix`,
`middle` or `suffix` with `-rr`, `-rz`, `-ru`, `-zz`, `-zu`, `-uu` in the focused
run. Letters describe survivors in ascending address order; the target is U.
The reversed mixed pairs remain expressible but were not rerun: survivor-slot
classification is unchanged and both orders have earlier zero-target evidence.
The result is 18 representative pairs, not all 27 absent-target layouts.

A read of the independent left neighbor establishes the actual leaf table, even
for UUU. No target slot is touched to create it. `UB_PTE_TABLES` observes each leaf
under mmap read ownership and the PTE lock, returning separate masks for existing
leaves and absent upper levels plus the table PFN (physical page number). It
allocates no page/table and makes no data access. Before removal the target is
inside the VMA with an empty leaf; after removal that address gives `SEGV_MAPERR`
(no mapping). The same table PFN and total table bytes must remain.

Before controller reads, the probe checks VMA bounds/offsets/flags, reverse-map
metadata (links from private pages to VMAs), exact page references, PTE states
and per-VMA RSS (resident set size)/anonymous bytes. U/Z slots own no ordinary
page references and contribute no private RSS. A deliberate local read fault
waits at writer admission and then populates one recorded U survivor, or an
untouched neighbor if no U survivor exists. Other U slots remain absent until
explicit access. Subsequent zero reads and isolated private writes must preserve
every other survivor and an independent zero mapping.

An absent target has no positive cached translation to warm. Its removed-address
fault proves that native VMA removal ran; it is not positive-target TLB (cached
translation) invalidation evidence. The zero/private preservation smokes retain
that separate warm-translation check. Actual body receipts bind mm, request,
origin, different executor, range, table and ownership to queue completion.
Enqueueing, local heads and fallback are never counted as remote execution.

## Transitions, errors and limits

`native change-zero` / `target change-zero` and the `change-private` counterparts
start with U between Z survivors and no reverse-map metadata. One already admitted
local reader invokes native GUP (`get_user_pages`) after all three KD requests
publish and while two reader shares remain held. Read intent requests no page
array/reference and establishes Z; write intent retains only the new private page.
The later executor revalidates and uses the existing zero/private body. Table
identity, new metadata, exact references and receipt ordering are checked. These
deterministic pre-execution changes do not cover uncontrolled write-fault races.

`error native resident middle-zz 1|2` and `error kd` counterparts inject `ENOMEM`
after the first or second native split. The still-mapped U target is not read
until after its empty-state observations. Both routes retain the same harmless
splits, mappings and accounting; an admitted error must never trigger destructive
local replay. `target refusal` locks the last private survivor and requires exact
release of the earlier hold before matched handback/ACK (acknowledgement).
`target missing-table` distinguishes absent upper levels and checks safe handback
with sticky local continuation. `target cancel-empty` checks queued cancellation.

The validators and negative controls reject forged execution/ownership, stale
tables, pre-populated targets, lost survivors, accounting/reference leaks, replay
and lost ACKs. Four preservation smokes reuse zero-target and resident-target
clients. No advice/fault/whole-unmap campaign is repeated: those production paths
were unchanged. Forced VMA replacement, unsupported-entry injection, uncontrolled
fault/reclaim/pinning races, pressure and post-admission cancellation remain
untested. Larger mappings, complex ancestry and general table destruction remain
outside scope; no general mmap or performance claim follows.
