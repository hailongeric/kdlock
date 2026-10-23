# Missing target table shared with an untouched survivor

`kdmm22` removes one prefix/suffix page from a three-page anonymous VMA (virtual
memory area) spanning a 2-MiB boundary. The target and near survivor share an
actually missing leaf PTE (page-table entry) table; the near survivor must stay
untouched. The far survivor may be private resident, shared zero or untouched.
Existing upper levels, both neighboring VMAs and the exact native table-retention
calculation are required. No target table is allocated merely to unmap.

All **48 serial cases, two basic tests and 1,709 negative receipt controls**
passed. There were 20 different-task missing-table removals and six more after
queued appearances as empty/zero/private targets. Twenty of these 26 removals
held no private pages. Recovery is restored and modules unloaded. See the
[mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#missing-target-table-shared-with-an-untouched-survivor)
and [result record](../../../../bench/results/10.176.26.71/tests/mm-boundary-shared-missing-20261024/README.md).

## Reuse the installed image

On `380G10`, confirm the original VM is idle and current capacity covers the
remaining boot/log growth. Attempt 1 is completed evidence. A fresh attempt uses
the already installed image and ten retained client binaries without rebuilding:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-missing-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-missing-20261024/workflow.py recovery --attempt 2
```

The coordinator verifies the snapshot, placement and captured kernel identity,
transports the source-host compressed identity through guest RAM, and runs the
48 cases serially. Do not repeat `prepare`/`build` in completed directories. On
an already verified kdmm22 boot, `run --attempt 2` avoids another boot. The
corresponding guest command is:

```sh
env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mm-boundary-shared-missing-20261024/control/focus.py \
  --build-attempt 1 --run focused-2
```

A timeout is not proof of drain. Never force module unload or reboot an in-flight
run. Receipt validators and negative controls are part of the run, not optional.

## Geometry and controls

For page size P = 4 KiB and boundary B, prefix `[B-2P,B+P)` removes `[B-2P,B-P)`;
suffix `[B-P,B+2P)` removes `[B+P,B+2P)`. Both retain `[B-P,B+P)`. The near survivor
is slot 1. R/Z/U mean private resident/shared zero/untouched, in increasing
address order. All feasible initial layouts run natively and delegated:

- Prefix: `prefix-ur`, `prefix-uz`, `prefix-uu`.
- Suffix: `suffix-ru`, `suffix-zu`, `suffix-uu`.

A non-U near survivor cannot coexist with a missing target table. The far
survivor is in a different table range. Both outer neighbors are untouched; an
independent third-table read creates the upper levels. Read-only kernel walks
verify `pmd_none()` (missing leaf table), parent identity and all survivor states;
reading zero values alone is not evidence of table absence or a zero-page PTE.

The client accepts `native|target SHAPE [MODE]`:

| Mode | Purpose |
| --- | --- |
| `success` | Actual different-task body, correct mappings/accounting and exact resource retirement |
| `error` | ENOMEM after the edge split, native-matched harmless layout without destructive replay |
| `appear-near-zero` | Queued near read creates its table; the still-empty target uses the full kdmm21 path |
| `appear-zero` | Queued target read creates a shared-zero PTE; the full kdmm20 path clears it |
| `appear-private` | Queued target write creates a private page; the full kdmm19 eligibility/hold/teardown checks apply |
| `appear-private-busy` | Lock that new private page; handback/acknowledgment (ACK), then sticky local third call |
| `free-table` | Move an untouched outer neighbor before publication while target table stays missing; safe refusal |
| `cancel` | Queued fatal cancellation preserves the victim mapping and retires unused caller resources |
| `fault` | Near-survivor fault waits for writer release, then creates the missing table locally |

Appearance and waiting-fault controls use UU survivors. Modes 16–18 use native
faults through an already held local reader after three requests publish; mode
19 uses two publications for refusal. No reader bypass, synthetic removal or
PTE poke is used. Reads acquire no shared-zero-page reference; private conversion
retains one exact GUP (`get_user_pages`) inspection reference. Execution rewalks
current state under the actual mmap writer instead of using a saved table pointer.

Initial mapping/PTE/RSS (resident-page accounting) observations precede survivor
reads. Later zero-fill reads and isolated private writes must preserve other
survivors, both neighbors and an independent zero mapping. The target is checked
again after these reads and writes, proving that table creation does not restore
its removed virtual range. Missing targets have no translation to invalidate;
populated controls verify native TLB (translation lookaside buffer) completion.
Local cleanup verifies that the fixture's upper hierarchy is absent.

The concurrent near-fault wait was exercised for prefix UU; ordinary post-removal
near faults were checked in both directions. Retention loss precedes publication.
Queued neighboring-VMA replacement remains untested because it needs a separate
writer gate; the current two-reader gate cannot safely replace a VMA. Controlled
appearances do not cover uncontrolled fault/reclaim/pinning races. Interior
removal, larger VMAs, complex ancestry, missing upper levels, huge/special entries
and general table destruction remain outside this extension. No performance,
p95, mutex-regression or nano work was run.
