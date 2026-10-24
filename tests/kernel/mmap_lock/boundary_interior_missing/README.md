# Interior removal with a missing target table

`kdmm23` removes the middle page of a three-page anonymous VMA (virtual memory
area) crossing one 2-MiB page-table boundary. The target's leaf PTE (page-table
entry) table must actually be missing, with all required upper levels present.
The near survivor shares that missing table range and must remain untouched;
the far survivor may be ordinary private resident, shared zero or untouched.
Both original outer-neighbor guards remain mandatory. An existing empty target
table, populated target, missing upper level, huge/special mapping or complex
reverse-map ancestry is refused. No table is allocated merely to unmap.

The [result record](../../../../bench/results/10.176.26.71/tests/mm-boundary-interior-missing-20261024/README.md)
records 44 serial cases, two basic tests and 1,092 negative receipt controls.
Six feasible layouts matched native behavior; 16 new removals executed in a
different task, including 12 with no private-page holds. Six preservation smokes
add 12 separately counted remote removals. Recovery is restored and modules
are unloaded.

## Geometry and execution

Let P = 4 KiB and B be a 2-MiB boundary. R/Z/U mean private resident/shared
zero/untouched, in increasing survivor-address order.

| Orientation | Original VMA | Removed target | Near survivor | Feasible pairs |
| --- | --- | --- | --- | --- |
| `left` | `[B-2P,B+P)` | `[B-P,B)` | slot 0, U | `middle-ur`, `middle-uz`, `middle-uu` |
| `right` | `[B-P,B+2P)` | `[B,B+P)` | slot 2, U | `middle-ru`, `middle-zu`, `middle-uu` |

No other near-survivor state is geometrically possible with a missing target
table. An independent third-table read establishes upper levels without touching
target or near survivor. Locked kernel walks verify PMD (page-middle-directory)
absence, upper-table identity and each PTE class; reading zero bytes is not proof
of an absent table or a shared-zero PTE.

1. The origin prepares two VMA descriptors, maple-tree reserves (storage for the
   VMA index) and reverse-map links before publishing its request. A reverse map
   associates private physical pages with their VMAs; absent metadata consumes
   no links. Preparation retains no unlocked VMA or table pointer.
2. Under the actual mmap writer, the executor rewalks current mappings and page
   tables, checks both outer neighbors and the complete native retention proof,
   and takes exact references/locks only on eligible private survivors.
3. Two native prepared splits create left, target and right VMAs. The surviving
   left end is exactly `start`; the right start is exactly `end`. Actual bounds,
   VMA/page counts and unchanged table bytes are checked before removal.
4. Native removal detaches the middle VMA. Native `free_pgd_range()` with floor
   `start` and ceiling `end` returns before walking any table in both geometries.
   The missing target owns no page or cached translation. Holds are released
   after native teardown; unused caller resources retire after exact completion.
5. A pre-effect refusal hands ownership back to the waiter, matches its ACK
   (acknowledgment), and makes later calls local. Once splitting begins, an error
   is returned as an admitted operation error, never permission for local replay.

## Reproduction

On `380G10`, after confirming the original VM is idle and current boot/log
capacity is sufficient, reuse the installed image and completed probes:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-missing-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-missing-20261024/workflow.py recovery --attempt 2
```

`run --attempt 2` skips the boot on an already verified kdmm23 candidate. The
runner performs 38 new cases and six preservation smokes serially, with strict
validators and negative controls. Attempt 1 is immutable completed evidence;
do not repeat `prepare` or `build` in its directories. Do not reboot or force
unload after a timeout without establishing actual drain.

The corresponding guest invocation, after verified candidate boot, is:

```sh
env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mm-boundary-interior-missing-20261024/control/focus.py \
  --build-attempt 1 --run focused-2
```

The thin client accepts `native|target middle-PAIR left|right [MODE]`:

| Mode | Verified behavior |
| --- | --- |
| `success` | Real body execution, exact mappings/accounting, references and retirement |
| `error1` / `error2` | ENOMEM after split one/two; native-compatible harmless splits, no removal or replay |
| `table` | An outer-neighbor read creates an empty target table before publication; handback |
| `appear` | A native target read creates a zero PTE after two requests publish; locked refusal, exact ACK and sticky local third call |
| `free-table` | Move the target-side outer neighbor before publication; unchanged missing target table, explicit refusal |
| `fault` | A real near-survivor read fault waits for writer release, then creates the table locally |
| `cancel` | Queued fatal cancellation preserves the victim mapping and retires resources |

Both orientations exercise every mode. Split errors use a private far survivor
on the left and absent ancestry on the right. Initial PTE/residency observations
precede survivor reads. Then full-page contents, zero-fill faults, isolated
private writes, neighboring mappings and independent shared-zero isolation are
checked. The removed address must still fault after survivor reads and writes.
Local cleanup checks that the fixture's upper hierarchy is absent.

Native controls execute the ordinary native body on the same KD backend with
delegation disabled. They are not a separate Native-off boot. Two local readers
overlap in KD cases. The waiting near-survivor fault is local fault evidence,
not delegated page-fault execution. The new target has no populated translation
to invalidate; populated-target TLB (translation lookaside buffer) checks belong
to the preservation smokes.

Queued private-target or near-survivor transitions, interior queued-neighbor
replacement, opposite-side outer-guard loss, missing-upper/huge/special entries,
and resource exhaustion were not live-tested in this stage. Existing-table
interior targets remain refused. Controlled zero appearance and waiting faults
do not cover uncontrolled fault/reclaim/pinning races. Larger VMAs, complex
ancestry, general table destruction and performance work remain deferred.
