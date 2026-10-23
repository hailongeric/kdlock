# Empty target in a retained boundary table

This probe validates `kdmm16` removal of one prefix/suffix page from a three-page
anonymous VMA (virtual memory area). The target has an empty PTE (leaf page-table
entry) in an existing table, alone in its 2-MiB page-middle-directory (PMD)
interval; both survivors occupy the adjacent interval. Actual outer neighboring
VMAs must prove native table retention. See the
[mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#empty-target-entry-in-a-retained-boundary-table)
and the single [result record](../../../../bench/results/10.176.26.71/tests/mm-boundary-empty-20261023/README.md).

## Reuse the installed candidate

On source host `380G10`, with the same idle VM and adequate current boot/log
headroom, use a fresh attempt number. Attempt 1 is completed evidence:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-empty-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-empty-20261023/workflow.py recovery --attempt 2
```

These commands verify the actual recovery snapshot, topology, captured kernel
identity and runtime modules, run all 51 focused cases serially, and unload only
after verified drain. They do not rebuild. If already on the verified kdmm16
boot, use `run --attempt 2` instead of `kd`. Do not interrupt another run or
request recovery after a failure until drain is established. Never force unload.

Direct invocation **inside the already verified guest**, using a fresh output
name and the frozen successful build/probes:

```sh
env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mm-boundary-empty-20261023/control-2/focus.py \
  --build-attempt 2 --run focused-2
```

`build-2/result.json` binds the new kernel/module/client and three reused clients;
`control-2/inputs.json` binds the frozen sources. `build-1` preserves the failed
client compile. Do not rerun `prepare` or `build` against completed directories.
Candidate boot reconstructs the captured identity in RAM from its compressed
ELF; this is decompression, not compilation. The original evidence stays intact.

## Fixture and controls

The client accepts `native|target prefix|suffix-PAIR [MODE]`, with default mode
`success`. PAIR orders the survivors by increasing address: R is an ordinary
private resident page, Z a read-faulted shared-zero mapping, and U an untouched
address. The matrix selects RR, RZ, RU, ZZ, ZU and UU in each direction. The
reversed mixed pairs are not claimed as live coverage; both survivor slots share
one table and the same classifier. The busy-second-survivor control separately
checks ordered partial acquisition and exact rollback.

The target-side retaining neighbor receives a read fault, creating the target
table without ever accessing the target. Read-only walks prove the actual table
identity, `pte_none()` target and neighbor's shared-zero mapping; zero data alone
would not prove these states. An independent anchor constructs the upper levels.
All survivors and neighbors are observed before reads/writes can change them.

| Mode | Purpose |
| --- | --- |
| `success` | Real removal with exact table retention and survivor checks |
| `error` | ENOMEM after the single successful edge split; native-matched layout, no replay |
| `free-table` | Move the target-side neighbor away before opt-in; require handback and native release of one target table |
| `change-zero`, `change-private` | Local reader faults the empty target after queue publication; require locked refusal and exact acknowledgment (ACK) |
| `shared` | Target shares an interval with a survivor; explicit geometry refusal |
| `cancel` | Cancel the queued victim before admission; verify mapping and resource retention/retirement |
| `fault` | A separate ordinary survivor fault waits behind writer admission and resolves locally |
| `busy` | Hold the last private survivor busy; retire the earlier hold before handback |

The runner restricts each control to its reviewed layout. New empty-target
change ioctls reuse the local-reader mechanism with two published requests, two
reader shares and closed admission. Their real read/write faults preserve the
same target table. The private change retains an exact test reference through
native removal, verifies the final mapping/reference counts, then releases it.
No synthetic removal callback or production bypass is used. Changing a retaining
VMA while those reader shares remain held would require conflicting writer
ownership, so retention loss is tested before publication, not as a queue-time
mapping race.

`KD_MM_BOUNDARY_EMPTY` receipts require a different executor, exact request/mm,
empty target, physical table identity, native retention bounds and balanced
private holds. Refusal requires matched handback and acknowledgment (ACK), plus
sticky local continuation. Post-split errors are admitted results, not fallback.
The probe checks removed-address faults, VMA/page/table accounting, neighbor
state and reference lifetimes before survivor demand faults and isolated writes.
Complete local cleanup must release every fixture and the upper table hierarchy.
The four preservation smokes reuse the old missing-boundary and same-table
empty-target binaries. Negative controls corrupt real observations and receipts.

Populated boundary targets, interior crossing, missing higher levels, huge or
special non-present entries, complex ancestry and general delegated table
destruction remain refused. Controlled changes and a waiting fault do not cover
uncontrolled write-fault, neighbor replacement, reclaim or pinning races. No
performance, advice, first-write or historical full-matrix rerun is included.
