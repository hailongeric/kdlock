# Empty target sharing a retained boundary table

`kdmm21` removes one empty prefix/suffix target from a three-page anonymous
VMA (virtual memory area), with one survivor sharing the existing target leaf
table and another across a 2-MiB boundary. Both neighboring-VMA guards and the
exact native table-retention proof remain mandatory. See the
[mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#empty-target-sharing-a-boundary-table)
and [result record](../../../../bench/results/10.176.26.71/tests/mm-boundary-shared-empty-20261024/README.md).
All 69 serial cases, two basic tests and 2,254 negative receipt controls passed:
42 different-task empty removals and four more after queued zero/private faults.
Recovery is restored and modules unloaded.

## Reuse the installed image

On `380G10`, verify the original VM is idle and current capacity covers boot/log
growth. Use a fresh attempt; attempt 1 is completed evidence:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-empty-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-empty-20261024/workflow.py recovery --attempt 2
```

The workflow checks the original snapshot, placement and captured identity,
transports the retained source-host compressed identity through guest RAM, runs
69 cases serially and restores recovery. Nine unchanged client binaries are
reused. No build is needed; do not rerun `prepare`/`build` in completed directories.
A timeout is not drain; never force module unload or reboot an in-flight run.

On an already verified kdmm21 boot, `run --attempt 2` avoids another boot. The
equivalent guest command requires the verified RAM identity:

```sh
env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mm-boundary-shared-empty-20261024/control/focus.py \
  --build-attempt 1 --run focused-2
```

## Fixture and controls

The client accepts `native|target SHAPE [MODE]`. SHAPE is `prefix-PAIR` or
`suffix-PAIR`; PAIR orders survivors by increasing address with R (private
resident), Z (shared zero), U (untouched). All nine pairs run in both directions:
reversed pairs have different near/far table roles. Reading the retaining
neighbor constructs the target table without touching the target. Read-only
PTE (leaf page-table entry) walks verify an actually empty target and preserve
untouched survivors until the later intentional read/write checks.

| Mode | Purpose |
| --- | --- |
| `success` | Different-task body, removed-address faults, retained mappings/pages/tables and accounting |
| `error` | ENOMEM after the edge split; native-matched harmless layout without destructive replay |
| `change-zero` | Real queued read fault; locked revalidation selects the full kdmm20 zero path |
| `change-private` | Real queued write fault; exact new inspection reference and complete kdmm19 private checks |
| `change-private-busy` | Lock the new private target; pre-effect handback/acknowledgment (ACK), then sticky local third call |
| `free-table` | Move an outer neighbor before publication; KD refuses, while native still retains the shared table |
| `busy` | Prefix-RR far survivor busy; release the earlier hold before ACK |
| `cancel` | Queued cancellation preserves the victim mapping and retires caller resources |
| `fault` | Far-survivor fault waits for writer release and creates its missing table locally |

Transition and waiting-fault controls use UU survivors. Empty targets own no
page or translation; no target is populated to manufacture a TLB test. The
populated controls require native PTE/TLB completion. State checks precede
survivor demand faults and isolated writes, preserving neighbors and an
independent zero mapping. Full cleanup retires the fixture's upper hierarchy.

No shared missing-table support is claimed. Queued neighbor replacement needs a
separate writer-owned gate and remains untested; the current two-reader gate
cannot safely replace a VMA. Controlled target transitions do not cover
uncontrolled fault/reclaim/pinning races. Larger mappings, interior removal,
complex ancestry and general table destruction remain deferred.
