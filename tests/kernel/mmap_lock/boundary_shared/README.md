# Private boundary target sharing its leaf table

`kdmm19` removes one ordinary private prefix/suffix page from a three-page
anonymous VMA (virtual memory area), with one survivor sharing the target's leaf
page table and one across the 2-MiB PMD (page-middle-directory) boundary. Both
outer-neighbor retention guards remain mandatory. See the maintained
[mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#private-target-sharing-a-boundary-table)
and [result record](../../../../bench/results/10.176.26.71/tests/mm-boundary-shared-20261023/README.md).
The old isolated-edge, same-table, advice and first-write implementations remain
separate. This fixture supports only the existing narrow private target class;
zero/empty/missing-table targets in the new geometry still hand back.

## Reuse the installed candidate

On `380G10`, confirm the same VM is idle and current capacity covers boot/log
growth. Use a fresh attempt; attempt 1 is immutable completed evidence:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-20261023/workflow.py recovery --attempt 2
```

This verifies the original recovery snapshot, placement, installed identity and
runtime modules, runs 69 serial cases, then restores recovery. Preserve the
hash-verified source-host `raw/tests/mm-boundary-shared-20261023/identity/vmlinux.xz`
under `bench/results/10.176.26.71/`; the workflow stages it in guest RAM after boot.
It is not stored on guest root. No build is needed for reuse; do not repeat
`prepare`/`build` in completed directories or interrupt an undrained run.

On an already verified kdmm19 boot, `run --attempt 2` avoids another boot. The
equivalent direct guest command requires the verified RAM identity:

```sh
env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mm-boundary-shared-20261023/control/focus.py \
  --build-attempt 1 --run focused-2
```

## Fixture and controls

The client accepts `native|target SHAPE [MODE]`, where SHAPE is `prefix-PAIR` or
`suffix-PAIR`. Survivor letters in increasing address order are R (private
resident), Z (shared zero) and U (untouched). All nine pairs run in each direction:
reversed pairs change which table is populated and are not equivalent. The
removed target is always private; slot 1 always shares its table. The other
survivor is slot 2 for prefix and slot 0 for suffix. Read-only PTE (leaf
page-table entry) walks prove these states before any survivor access.

| Mode | Purpose |
| --- | --- |
| `success` | Original target identity, different executor, retained tables, exact mapping/RSS accounting and survivor contents |
| `error` | ENOMEM after a split; compare harmless native layout, intact target and no local replay |
| `free` | Drop probe references before execution; observe native mapping removal followed by the final KD put |
| `change-near-zero` | Real read fault turns near survivor U to Z after publication, then locked revalidation succeeds |
| `change-busy` | Local reader locks the target after publication; exact pre-effect handback/acknowledgment (ACK) |
| `free-table` | Move outer neighbor before publication; conservative KD handback, while native retains the table because the near survivor remains |
| `busy` | Busy far survivor on prefix-RR; release earlier target and near-survivor holds before ACK |
| `cancel` | Cancel queued victim without losing its mapping or prepared resources |
| `fault` | Far-survivor fault waits for writer release, then creates its previously missing table locally |

Focused transition/fault modes use UU survivors. Ordinary probes retain temporary
inspection references and release them at cleanup; only `free` tests final
reference release during the body. Freed pages are not read afterward, and
allocator reuse is not traced. Checks precede intentional U read faults and Z
private writes, preserving an independent zero mapping and both neighbors.

The runner preserves raw JSON, kernel receipts and corruption-check results;
actual request-bound body completion is required. Acceptance/enqueue counters
alone are insufficient. All workers must drain before normal module unload.
Queued VMA replacement and uncontrolled fault/reclaim/pinning races remain
untested. No production reader-admission bypass or synthetic body was added.
