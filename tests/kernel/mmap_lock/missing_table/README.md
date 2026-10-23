# Missing-leaf-table removal correctness probe

`6.1.159-kdmm14` removes one page at prefix, interior or suffix position from a
three-page anonymous VMA (virtual memory area) when its leaf page table is missing
and all required upper directory levels exist. No leaf table is allocated for
removal. This is a separate state from an empty PTE (page-table entry) in an
existing table. See the [mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#missing-leaf-tables-with-existing-upper-levels)
and [completed result](../../../../bench/results/10.176.26.71/tests/mm-missing-table-20261023/README.md).

All three pages and the retaining neighbors stay within one PMD
(page-middle-directory) interval of 2 MiB. Therefore both survivors must be
untouched: a shared-zero or private survivor would populate that same leaf table.
An independent read-faulted anchor in the adjacent PMD, within the same 1-GiB PUD
(page-upper-directory) interval, creates the upper levels only. The new
`UB_TABLE_WALK` observation distinguishes missing upper levels, a missing leaf
table and an existing leaf table, recording physical identities without data
access or allocation. Old ioctl layouts remain unchanged.

## Reuse the installed candidate

Source host `380G10`, same idle VM, sufficient current capacity for boot/log
growth. Attempts 1 and 2 are completed evidence; use a new number, for example 3:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-missing-table-20261023/workflow.py kd --attempt 3
python3 bench/results/10.176.26.71/tests/mm-missing-table-20261023/workflow.py recovery --attempt 3
```

This reuses the installed image, module and frozen `probes-2`; it performs no
build. It verifies the actual recovery snapshot, pins, kernel identity and exact
runtime module set, runs 42 cases serially, then unloads normally after drain.
If already on the verified kdmm14 boot, substitute `run --attempt 3` for `kd`
to avoid a reboot. Never request recovery before a failed/in-flight run drains.

Direct guest invocation on that already verified boot, with a fresh result name:

```sh
env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mm-missing-table-20261023/control-2/focus.py \
  --run focused-3 \
  --probe-revision /root/kdlock-evidence/10.176.26.71/tests/mm-missing-table-20261023/probe-revision-2/result.json
```

The guest stage is `/root/kdlock-evidence/10.176.26.71/tests/mm-missing-table-20261023`.
`build-1/result.json` binds the kernel and module; `probe-revision-2/result.json`
binds the corrected new client and four reused binaries. Failed `focused-1` and
its original inputs remain frozen. Do not repeat `prepare`, `build` or `probe`
against their completed directories. The RAM identity snapshot is regenerated
from the captured compressed ELF during candidate boot verification, not rebuilt.

## Cases and exact observations

`native SHAPE` uses the ordinary native munmap body on the KD lock backend;
`target SHAPE` enables delegation. SHAPE is `prefix-uu`, `middle-uu` or `suffix-uu`,
where U means untouched and letters order the two survivors by address. Initial
walks require `pmd_none=7`, `upper_none=0`, no leaf PFNs (physical page numbers)
and one valid parent-table identity; mask 7 denotes all three slots. All slots
remain untouched before admission.
After removal the target produces `SEGV_MAPERR`; the parent identity and missing
table remain, table bytes are unchanged, and the VMA bounds, offsets, flags,
map count, virtual pages and private resident accounting match native results.
Neither a missing table nor the later shared-zero mapping owns a private page.

Survivor reads happen after these observations. They allocate a normal leaf
table and read zeros; subsequent isolated writes allocate private pages while
preserving other survivors and the independent zero mapping. Further walks
require the same newly installed table identity. Full local cleanup removes
every fixture VMA and observes missing upper entries. The final anchor lies
outside the enabled KD interval: all `4 * groups` cleanup calls are checked,
but exactly `4 * groups - 1` enter the KD counter path. The validator checks
both counts; this distinction fixed the preserved first-attempt probe failure.

The additional modes are:

| Mode | Controlled behavior |
| --- | --- |
| `native/target change-table-empty` | An already admitted local reader faults the left neighbor; the new leaf contains an empty target |
| `native/target change-table-zero` | The reader faults the target with read intent, acquiring no shared-zero page reference |
| `native/target change-table-private` | The reader faults the target with write intent and retains the exact new private page |
| `native/target fault` | A separate ordinary survivor read waits behind writer admission and creates its leaf after removal |
| `error native/kd resident middle-uu 1/2` | Inject `ENOMEM` after either interior split; the selected target remains untouched and native harmless splits must match |
| `target upper-refusal` | Leave one required PUD entry absent; require exact waiter handback/ACK and sticky local continuation |
| `target cancel-empty` | Cancel a published request before body admission; retain its VMA and retire unused resources |

For table-appearance controls, the KD observation requires three published
requests, two concurrent local reader shares and closed new-reader admission.
The later combiner must revalidate and complete the actual corresponding
empty/zero/private body. The tests do not claim uncontrolled write-fault races.

The final run contains 20 new-path cases, 18 separately labeled `coverage-*`
native/KD cases for kdmm13's reversed ZR/UR/UZ pairs, and four preservation smokes
for zero/private/empty targets and busy-page refusal. R denotes an ordinary
private resident page; Z denotes a verified shared-zero mapping. The old absent,
zero and resident clients are reused. Advice, first-write and whole-unmap campaigns
are not repeated because their implementation is unchanged.

## Limits

This is built-in native-body delegation, not JIT execution. A missing target has
no positive TLB (cached translation) entry to warm; its access fault proves VMA
absence. Existing zero/private smokes retain their positive-target invalidation
checks. Cross-PMD layouts, missing higher levels, huge/special entries, complex
ancestry and general delegated table destruction remain unsupported. No forced
VMA replacement, table disappearance after publication, uncontrolled fault,
reclaim/pinning race, pressure, post-admission cancellation or Native-off boot
campaign was added. These limits are not passes or general mapping support.
