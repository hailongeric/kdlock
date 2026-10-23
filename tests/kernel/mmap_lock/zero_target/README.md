# Shared-zero target correctness probe

`kdmm11` permits one shared-zero target to be removed from an exactly three-page
anonymous VMA (virtual memory area), provided at least one survivor is an ordinary
private resident page. All 15 supported layouts passed native comparisons, with
32 actual different-task zero removals and one separately counted private removal
after a controlled target change. The [result record](../../../../bench/results/10.176.26.71/tests/mm-zero-target-20261023/README.md)
contains 48 serial cases, two basic programs, 650 negative controls and restored
recovery. See [mechanism and scope](../../../../kernel_integration/mmap_lock/UNMAP.md#shared-zero-page-targets).

## Reuse the installed image and frozen probes

On source host `380G10`, after confirming the existing VM/test slot is idle and
making a quick current-capacity check, run serially:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-zero-target-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-zero-target-20261023/workflow.py recovery --attempt 2
```

Attempt 1 is completed evidence; use the next unused number. Recovery follows
only after the tests pass and drain. A timeout is not drain: inspect workers
and retain loaded state rather than force-unloading or rebooting an active run.
Transitions verify the actual recovery snapshot, original VM/pins, exact kernel
identity, module set and recovery default. Do not repeat preparation or building
for unchanged inputs; the original stage directories are frozen.

On an already verified `kdmm11` KD boot, run the same focused tests without
another reboot, using a new result name:

```sh
env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mm-zero-target-20261023/control/focus.py \
  --run focused-2
```

The guest stage is `/root/kdlock-evidence/10.176.26.71/tests/mm-zero-target-20261023`.
`build-1/result.json` binds the new client, four module binaries, eight reused
clients and `/root/kdlock-kernel-baselines/mmap-kdmm11-20261023`, Build ID
`4371336700c9bcccb45f455c9e85fd0af067e2a1`. Identity files are reconstructed in RAM
from `/root/kdlock-kernel-work/mm-zero-target-20261023`, not a full build tree.
The runner loads one module at a time and unloads only after exact drain.
Each case retains `client.json`, `kernel.log` and receipt controls; the focused
result binds their hashes and native comparisons. Recovery clears temporary RAM.

## Matrix and checks

R is a private resident page, Z a present shared-zero PTE (page-table entry),
and U an untouched address with no PTE. Modes combine `prefix`, `middle`, `suffix`
with `-ru`, `-ur`, `-rz`, `-zr`, `-rr`; letters name survivors in increasing address
order, excluding the Z target. Each runs `native SHAPE` and `target SHAPE`.
All 15 eligible combinations run separately. The 12 no-R combinations are
unsupported, not equivalent omissions. Native uses the ordinary body with
delegation disabled on the same KD backend, not a Native-off boot.

The client creates Z by a read fault and uses the unchanged read-only `UB_PTES`
classifier (`is_zero_pfn()`) to prove it. It never writes or pins the initial
zero target. Only R slots receive test references. Before survivor reads, exact
PTE masks, VMA layout, private-page identities/references and per-VMA `smaps`
RSS (resident set size)/anonymous bytes are checked. Zero targets/survivors do
not contribute private RSS. Original CPUs warm target translations and verify
removed-address faults, checking TLB (cached translation) invalidation.

A deliberate U-survivor read fault waits at reader admission and resolves
locally after the body; if there is no U survivor, it uses an untouched neighbor.
Other U slots remain absent until explicitly read. Later full-page zero reads
and sequential private writes check content, distinct physical identities and
isolation from another zero survivor and an independent zero mapping. Two local
readers overlap before writer admission. No reader delegation is claimed.

## Controlled change, errors and refusal

`native change` and `target change` begin with a proven Z target. For KD, after
all three callers have published, one already admitted local reader performs
native GUP (`get_user_pages`) with write intent while both read shares remain
held. `UB_CHANGE_ARM` selects slot 4; the reader uses the locked GUP wrapper,
which cannot drop/reacquire its share on a retry. `UB_CHANGE_NOW` provides the
native control for slot 1 of its single group. The new private page is verified,
patterned and held by an exact test reference. `UB_CHANGE_RESULT` binds its
physical identity and queued/read-admission state to subsequent body receipts.
The body itself remains real munmap. These are controlled pre-execution changes,
not a claim of general write-fault race coverage.

`error native resident middle-rz 1|2` and the `error kd` counterparts compare
both reachable split-error points. `target refusal` locks the final private
survivor; `target missing` leaves the target absent; `target no-resident` tests
an all-zero VMA with no private survivor. Refusal releases held private pages
before exact handback/ACK (acknowledgement) and sticky local continuation.
Post-split errors retain native-compatible harmless splits and cannot replay
munmap locally. `target cancel` checks queued fatal cancellation. `target free`
drops all test references before execution; it does not imply freeing the
permanent shared zero page.

`receipts.py` distinguishes `KD_MM_ZERO_TARGET` completion from the changed
private target's `KD_MM_RESIDENT_PARTIAL` receipt. It binds mm, request, origin,
different executor, masks, physical identity, holds, completion and retirement.
`controls.py` corrupts real records to reject stale target identity, wrong
ordering, false zero-page ownership, destructive replay and lost mappings/ACKs.
Local heads, fallback and synthetic callbacks are excluded from remote counts.

Seven small smokes preserve zero-survivor, mixed and fully resident targets,
untouched partial removal, whole removal, advice and separate first-write faults.
No-R zero targets, larger ranges, complex ancestry and general table destruction
remain unsupported. Forced VMA replacement, uncontrolled write faults,
reclaim/pinning races, pressure and post-admission cancellation remain untested.
No performance or general mmap/page-fault claim follows.
