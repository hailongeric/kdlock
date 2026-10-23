# Shared-zero target correctness probe

`kdmm12` removes one shared-zero target from an exactly three-page anonymous VMA
(virtual memory area), with private, zero or untouched survivors. Private survivors
are no longer required. The new 12 zero/untouched-only layouts passed native
comparisons with 27 different-task removals owning no private pages, plus two
resident-survivor preservation removals and one separately counted changed-private
removal. The [result record](../../../../bench/results/10.176.26.71/tests/mm-zero-only-20261023/README.md)
contains 44 serial cases, two basic tests, 660 negative controls and restored recovery.
The [kdmm11 record](../../../../bench/results/10.176.26.71/tests/mm-zero-target-20261023/README.md)
retains its separate completed matrix and frozen probes.
See [mechanism and limits](../../../../kernel_integration/mmap_lock/UNMAP.md#zero-and-untouched-survivors-without-private-pages).

The commands below intentionally retain the frozen kdmm12 campaign. The later
[kdmm13 absent-target probe](../absent_target/README.md) reuses this client binary
for two preservation smokes and shares its source/receipt helpers. The old
`missing-empty` refusal is specific to kdmm12; a retained-table absent target is
supported on kdmm13 and has a separate completion contract.

## Reuse the installed image and frozen probes

On source host `380G10`, after confirming the VM/test slot is idle and checking
current capacity against boot/log needs, run serially:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-zero-only-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-zero-only-20261023/workflow.py recovery --attempt 2
```

Attempt 1 is completed evidence; use the next unused number. A timeout is not drain:
inspect workers and retain loaded state rather than force-unloading or rebooting
an active run. Transitions verify the actual recovery snapshot, original VM/pins,
exact kernel identity, module set and recovery default. Do not repeat preparation
or building for unchanged inputs; original stage directories remain frozen.

On an already verified `kdmm12` KD boot, run the focused tests without another
reboot, using a new result name:

```sh
env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mm-zero-only-20261023/control/focus.py \
  --run focused-2
```

Guest stage: `/root/kdlock-evidence/10.176.26.71/tests/mm-zero-only-20261023`.
`build-1/result.json` binds the new client, four test modules, eight reused clients
and `/root/kdlock-kernel-baselines/mmap-kdmm12-20261023`, Build ID
`d6a297a710d0ecc7f2867028c031d730452a2863`. Identity files are reconstructed in RAM
from `/root/kdlock-kernel-work/mm-zero-only-20261023`; no full rebuild is needed.
The runner loads one module at a time, retains each client/log pair and unloads
only after exact drain. Native means the ordinary body on the same KD backend,
not a Native-off boot.

## Matrix and observations

R is ordinary private resident, Z a present shared-zero PTE (page-table entry),
and U an untouched address with no PTE. Modes combine `prefix`, `middle`, `suffix`
with `-zz`, `-zu`, `-uz`, `-uu`; letters name survivors in increasing address order,
excluding the Z target. Each runs `native SHAPE` and `target SHAPE`. All 12 new
combinations run separately. Existing `-ru`, `-ur`, `-rz`, `-zr`, `-rr` shapes remain;
this focused run preserves one pair, `middle-rz`, without repeating the old matrix.

Read faults create Z and unchanged read-only `UB_PTES` queries prove `is_zero_pfn()`
identity. No initial Z/U slot is pinned or written. With zero private slots the
client skips `UB_PIN_MASK`; `UB_PAGESTATE` still proves zero owned references.
Before survivor reads, PTE masks, VMA/metadata layout, page/table accounting and
per-VMA `smaps` RSS (resident set size)/anonymous bytes are checked. Zero pages
contribute no private RSS. Original CPUs warm target translations and verify
removed-address faults, checking TLB (cached translation) invalidation.

A deliberate U-survivor read fault waits at writer admission and resolves locally;
if no U survivor exists it uses an untouched neighbor. All other U slots remain
absent until explicit access. Subsequent full-page zero reads and isolated private
writes check contents, distinct physical identities and an independent zero mapping.
Two local readers overlap before writer admission; no reader is delegated.

## Metadata, errors and controls

`native change-empty` and `target change-empty` begin with only Z pages and absent
reverse-map metadata (the structures connecting private pages to their VMAs).
After all three KD requests publish, one already admitted reader performs native
locked GUP (`get_user_pages`) with write intent while both read shares remain held.
The existing `UB_CHANGE_ARM/NOW/RESULT` controls are unchanged. The new private
page and metadata are revalidated by the later combiner; its exact page identity,
new surviving metadata and caller-prepared links are checked. This is a controlled
pre-execution change, not general concurrent write-fault race coverage.

`native inherited` and `target inherited` test simple metadata with no current
private pages. Only the target gets a temporary private history, then
`MADV_DONTNEED` discards that page and a read fault reestablishes Z before admission.
No survivor is populated to evade eligibility. Empty metadata consumes no prepared
reverse-map links; inherited/new metadata consumes exactly the needed split links.

`error native resident middle-zz 1|2` and `error kd` counterparts compare both
interior post-split errors with no private holds. `target missing-empty` leaves
its target PTE absent and verifies handback/ACK (acknowledgement), unused-resource
retirement and sticky local continuation. `target refusal` preserves the late
busy-page rollback check; `target cancel-empty` checks queued fatal cancellation.
Admitted errors retain native-compatible harmless splits and never replay munmap.

`receipts.py` binds mm, request, origin, different executor, PTE masks, private
holds, completion and exact retirement. Zero-target completion cannot claim an
owned page, and absent ancestry cannot claim consumed reverse-map links.
`controls.py` corrupts actual records to reject false ownership, stale target
identity, forged metadata, missing completion, destructive replay and lost ACKs.
Local heads, fallback and synthetic callbacks are excluded from remote counts.

Seven additional kdmm12 smokes preserve earlier resident-target, untouched/whole-unmap,
advice and separate first-write paths. Larger ranges, complex ancestry and general
table destruction remain unsupported. Absent targets have the separate kdmm13
scope linked above. Forced VMA replacement,
uncontrolled write faults, reclaim/pinning races, pressure and post-admission
cancellation remain untested. No general mapping or performance support is claimed.
