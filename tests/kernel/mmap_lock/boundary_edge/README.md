# Boundary-crossing edge removal probe

This probe validates `kdmm15` removal of one missing-table edge page from a
three-page anonymous VMA (virtual memory area). The target occupies one 2-MiB
page-middle-directory (PMD) interval; both survivors occupy the adjacent one.
The two intervals share a valid upper directory. Real neighboring VMAs must
establish the native table-retention bounds. This is not general table destruction.
See the [mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#boundary-crossing-edge-removal-with-retained-tables)
and the single [result record](../../../../bench/results/10.176.26.71/tests/mm-boundary-edge-20261023/README.md).

## Reuse the installed candidate

On source host `380G10`, with the same idle VM and sufficient current boot/log
headroom, use a fresh attempt number. Attempt 1 is completed evidence:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-edge-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-edge-20261023/workflow.py recovery --attempt 2
```

This verifies the actual recovery snapshot, topology, image identity and runtime
module set, runs the 49 cases serially, and normally unloads after verified drain.
It does not rebuild. If already on the verified kdmm15 boot, use `run --attempt 2`
in place of `kd`. Do not interrupt an existing run or request recovery before
a failed run is known to have drained. No forced unload is allowed.

Direct invocation **inside the already verified guest**, using a fresh output
name and the frozen successful build/probes:

```sh
env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mm-boundary-edge-20261023/control-2/focus.py \
  --build-attempt 2 --run focused-2
```

The stage retains `build-1` and `probes-1` as failed compile evidence;
`build-2/result.json` binds the actual kernel, two modules, new client and six
reused clients. `control-2/inputs.json` binds all frozen input hashes.
Do not rerun `prepare` or `build` against these completed directories.
The persistent compressed ELF reconstructs the identity snapshot in RAM after
candidate boot; this is decompression, not a rebuild.

## Inputs and checks

The new client accepts `native|target prefix|suffix-PAIR [MODE]`.
PAIR orders survivors by increasing address: R is a private resident anonymous
page, Z a read-faulted shared-zero mapping, and U an untouched address. The default
mode is `success`. The live matrix selects RR, RZ, RU, ZZ, ZU and UU in each
direction. Reversed mixed pairs share the same survivor table and classifier;
their omission is recorded explicitly, not counted as a pass.

| Mode | Purpose |
| --- | --- |
| `error` | ENOMEM after the single successful edge split, with a same-table whole-removal queue head |
| `free-table` | Move the target-side outer neighbor away before opt-in; native must release the existing empty target table, KD must hand back |
| `table` | Keep an existing target table even with valid retention bounds; explicit refusal in this stage |
| `shared` | Edge shares a table interval with the middle survivor; explicit refusal |
| `cancel` | Cancel the queued victim before body admission; both edge offsets supported |
| `appear` | Already admitted local reader creates a shared-zero target and its table after publication; revalidation hands back |
| `fault` | A separate ordinary survivor fault waits behind writer admission, then resolves locally |
| `busy` | Hold the second private survivor busy; the first hold must be retired before refusal |

The runner constrains each mode to its reviewed fixture. Native comparisons use
the ordinary munmap body on the same KD backend. A read-only page-table walk
records actual missing PMD entries, upper-table identities and leaf-table
physical identities; untouched data alone does not establish table absence.
The fixture creates upper levels using an independent read-faulted anchor in a
third PMD interval. Retaining neighbors are initially untouched except in the
explicit existing-table control.

`UB_EDGE_BASES` records exact fixture addresses, including the same-table error
queue head. `UB_CANCEL_EDGE` selects prefix or suffix cancellation; old ioctl
encodings retain their behavior. `UB_CHANGE_EDGE_TABLE_ARM` uses the existing
local-reader control with two published requests, without bypassing admission.
No production hook supplies a synthetic removal body.

After removal, the probe checks address faults, VMA/page/table accounting,
physical page references, reverse-map links, exact neighbor state and table
lifetimes before touching survivors. It then checks zero-fill demand faults,
private-write isolation and the independent zero mapping. Complete local cleanup
must remove every fixture and release the upper hierarchy. `KD_MM_BOUNDARY`
receipts bind actual body completion/error to mm, request, original task and a
different executor, including exact retention bounds and released holds.
The validators also require matching handback/ACK, sticky local continuation,
cancellation and caller-resource retirement. Negative controls corrupt actual
receipts and observations; local fallback never counts as remote completion.

Existing target tables, general table destruction, higher-level absence, huge
or special entries and complex ancestry remain outside scope. The deterministic
appearance and waiting-fault controls do not establish uncontrolled fault,
neighbor replacement, reclaim or pinning-race coverage. Advice, first-write,
performance and historical matrices are not rerun by this focused stage.
