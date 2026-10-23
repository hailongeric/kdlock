# Private target at a retained table boundary

`kdmm18` removes one ordinary private resident page from the prefix or suffix of
a three-page anonymous VMA (virtual memory area) crossing a 2-MiB PMD
(page-middle-directory) boundary. The target occupies one interval alone; both
survivors occupy the adjacent interval. The same two outer neighboring VMAs must
prove that native teardown retains the page tables. See the maintained
[mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#private-target-in-a-retained-boundary-table)
and [single result record](../../../../bench/results/10.176.26.71/tests/mm-boundary-resident-20261023/README.md).

For kdmm19's new shared-table geometry, use the separate
[boundary_shared guide](../boundary_shared/README.md). The `shared` refusal mode
below describes kdmm18 and is not a valid refusal expectation on kdmm19.

The initial target is a writable, exclusive base anonymous page with one mapping,
simple reverse-map ancestry, no compound/swap-cache/reserved/poisoned state and no
native indication of a DMA pin. The executor uses a nonblocking page lock and
one exact temporary reference. Shared/COW (copy-on-write), huge, special, busy
or otherwise unsupported pages hand back before splitting. Caller-prepared VMA,
mapping-index and reverse-map reserves remain unchanged. Readers stay local.

## Run using the installed candidate

On source host `380G10`, after checking the same VM is idle and has current
boot/log headroom, use a fresh attempt number. Attempt 1 is completed evidence:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-resident-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-resident-20261023/workflow.py recovery --attempt 2
```

The workflow verifies recovery, placement, installed identity and runtime
modules, then runs 48 cases serially. It restores the candidate's compressed ELF
from the hash-verified source-host file to guest RAM after boot. That durable
identity is **not stored on guest root**; preserve
`bench/results/10.176.26.71/raw/tests/mm-boundary-resident-20261023/identity/vmlinux.xz`
and its receipt. Boot/test reuse requires no build. Do not repeat `prepare` or
`build` in completed directories, interrupt an in-flight run or force unload.

On an already verified kdmm18 boot, `run --attempt 2` skips the boot. Direct guest
invocation also requires the verified RAM identity to exist:

```sh
env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mm-boundary-resident-20261023/control/focus.py \
  --build-attempt 1 --run focused-2
```

## Fixture and lifetime checks

The client accepts `native|target prefix|suffix-PAIR [MODE]`. Survivor letters in
increasing address order are R (private resident), Z (shared zero) and U
(untouched). The focused matrix uses RR/RZ/RU/ZU/UU in both directions. Read-only
PTE (leaf page-table entry) observations establish real state and physical
identity without touching U survivors. Each originating task warms existing
translations, then checks the removed address faults on that same CPU. The
retaining neighbors and an independent shared-zero mapping must remain intact.

| Mode | Required evidence |
| --- | --- |
| `success` | Different-task native body, original target identity, retained tables, exact VMA/RSS and survivor state |
| `free` | Drop every ordinary probe reference before publication; target has only the KD reference after native teardown, then receives its final put |
| `error` | ENOMEM after one split, native-matched layout, original target still mapped, no destructive replay |
| `change-busy` | Already-admitted local reader locks the original target after two requests are published; locked revalidation hands back with an exact acknowledgment (ACK) |
| `free-table` | Move the retaining neighbor before publication; handback must match native release of one leaf table |
| `shared` | Refuse the unsupported geometry where a survivor shares the target interval |
| `busy` | A busy final survivor causes exact release of the earlier target and survivor holds |
| `cancel` | Queued cancellation preserves the victim mapping and retires prepared resources |
| `fault` | A real untouched-survivor fault waits behind writer admission and completes locally |

`UB_PIN_MASK` takes ordinary `get_user_pages()` references, not DMA pins. Normal
cases retain these references to inspect the original pages after unmapping;
they prove logical removal and balanced references, not immediate physical
reclamation. Cleanup releases them through `UB_DROP`. The two delegated `free`
cases remove those probe references before execution. Their receipts record
reference counts 2 before native unmap and 1 before the final KD put; no freed
page is dereferenced afterward. Allocator reuse is not separately traced.

The new busy ioctl changes only page-lock eligibility through an existing local
reader share. It adds no reference, PTE replacement, reader-admission bypass or
synthetic body. Replacing a neighboring VMA while those shares are held requires
conflicting writer ownership; queued VMA replacement remains untested.

One small preservation set covers missing/empty/zero boundary targets and the
same-table resident path. Prior matrices and reversed-layout campaigns are not
repeated. Larger mappings, target/survivor interval sharing, interior crossing,
complex ancestry, general table destruction and uncontrolled fault/reclaim/pin
races remain outside this milestone.
