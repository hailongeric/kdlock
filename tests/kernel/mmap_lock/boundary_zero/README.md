# Shared-zero target in a retained boundary table

This probe validates `kdmm17` one-page prefix/suffix removal from a three-page
anonymous VMA (virtual memory area) crossing a 2-MiB page-middle-directory (PMD)
boundary. The target has a genuine shared-zero PTE (leaf page-table entry) and
occupies its interval alone. Both survivors occupy the adjacent interval, within
the same upper directory. Both real outer VMA neighbors must establish the
unchanged native table-retention bounds. Ordinary private boundary targets remain
refused. See the [mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#shared-zero-target-in-a-retained-boundary-table)
and [single result record](../../../../bench/results/10.176.26.71/tests/mm-boundary-zero-20261023/README.md).

## Reuse the installed candidate

On source host `380G10`, with the same idle VM and sufficient current boot/log
headroom, select a fresh attempt number. Attempt 1 is completed evidence:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-zero-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-zero-20261023/workflow.py recovery --attempt 2
```

These verify the real recovery snapshot, pins, kernel identity and runtime
modules, run 74 cases serially, then normally unload after verified drain. They
do not rebuild. On an already verified kdmm17 boot use `run --attempt 2` instead
of `kd`. Do not interrupt an existing run, force unload or reboot after a failure
until drain is established.

Direct invocation **inside the already verified guest**, using a fresh run name:

```sh
env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mm-boundary-zero-20261023/control-2/focus.py \
  --build-attempt 1 --run focused-2
```

`control/inputs.json` binds the compiled source; `control-2/inputs.json` binds the
installation continuation and current run controls. `build-1` completed all
compilation/basic checks, then failed on an installer metadata filename.
`finish-build-1/result.json` binds the successful no-rebuild continuation,
`probes-1` and captured image. Do not repeat `prepare`, `build` or `finish` in
completed directories. Candidate boot reconstructs its identity in RAM from the
compressed ELF; it does not compile anything. Four existing clients are reused.

## Fixture and controls

The new client accepts `native|target prefix|suffix-PAIR [MODE]`. PAIR lists
survivors in increasing address order: R is ordinary private resident, Z is
shared zero, U is untouched. All nine pairs run in both directions. Setup uses
real read faults for the target and target-side retaining neighbor. Read-only
walks verify the zero PTE, exact target table, upper levels and untouched slots.
No target write or private-page pin is used. Origin tasks warm R/Z translations
and leave U addresses untouched before the initial observations.

| Mode | Focus |
| --- | --- |
| `success` | Different-task zero removal, exact native retention, all survivor pairs |
| `error` | ENOMEM after the single edge split; original zero PTE and harmless split retained |
| `change-private` | Admitted local reader creates a private target after publication; require handback and exact acknowledgment (ACK) |
| `free-table` | Move the retaining neighbor away before publication; handback must match native release of one table |
| `shared` | Refuse target/survivor interval sharing |
| `cancel` | Cancel the queued victim before admission; retain its mapping and retire caller resources |
| `fault` | A real U-survivor fault waits behind writer admission, then resolves locally |
| `busy` | Hold the last private survivor busy; release the exact earlier hold before handback |

The new `UB_CHANGE_EDGE_ZERO_PRIVATE_ARM` ioctl uses the established local-reader
control and native `get_user_pages()`, with two requests published and two reader
shares held. It verifies the original shared-zero entry, same table after the
private write fault, and exact new page reference through native removal and
final release. It supplies no synthetic removal body. VMA retention loss is
controlled before publication; replacing a VMA inside those reader shares would
need conflicting writer ownership and is not claimed.

Receipts bind real completion/error to the exact request/mm and different task,
zero physical identity, no target ownership, retained tables and balanced
survivor holds. Observations check removed-address faults, VMA/page/table
accounting, surviving PTEs/content, neighboring mappings, zero-fill faults,
isolated private writes and the independent shared-zero mapping. Complete local
cleanup must release all fixtures and the upper table hierarchy. Negative
controls mutate actual observations and receipts. Local fallback is never
counted as delegation.

The runner labels six reversed **empty-target** layouts as `empty-gap-*`, using
the existing empty client and native comparisons. Seven `*-smoke` cases preserve
missing/empty boundary paths, empty-to-private refusal, same-table zero targets
and the earlier same-table target transition. Their counts remain separate from
the 38 new zero-boundary removals.

Private boundary targets, interior crossing, larger mappings, complex ancestry,
missing higher levels, huge/other special entries and general delegated table
destruction remain refused. Controlled transitions and waiting faults do not
cover uncontrolled write-fault, neighbor replacement, reclaim or pinning races.
Missing/empty-to-zero queued transitions were not newly exercised. There is no
performance, p95, mutex-regression or nano campaign in this stage.
