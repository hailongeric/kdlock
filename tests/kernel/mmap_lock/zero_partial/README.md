# Shared-zero survivor correctness probe

`kdmm10` supports a single private resident anonymous target in a three-page VMA
(virtual memory area), with shared-zero, untouched or private resident survivors.
The new [result record](../../../../bench/results/10.176.26.71/tests/mm-zero-partial-20261023/README.md)
reports 44 serial cases, 31 actual different-task removals, two basic programs
and 576 negative receipt controls. Recovery is restored. The
[mechanism and supported scope](../../../../kernel_integration/mmap_lock/UNMAP.md#shared-zero-page-survivors)
remain deliberately narrow; the removed target's type did not change.

## Reuse the installed image and probes

On source host `380G10`, after checking the original VM is idle and has adequate
headroom, these commands reproduce the focused run serially:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-zero-partial-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-zero-partial-20261023/workflow.py recovery --attempt 2
```

Attempt 1 is completed evidence. Use the next unused number, and run recovery
only after tests pass and drain. A timeout or failed command is not proof of
drain; inspect workers and retain loaded state, never force unload or reboot an
active test. Transitions verify the actual recovery snapshot, original VM/pins,
kernel identity, modules and recovery default. No rebuild is needed for unchanged
inputs; do not repeat `prepare` or `build` against the frozen destinations.

On an already verified `kdmm10` KD boot, the same focused runner avoids another
boot cycle. Run only with the serial VM slot available:

```sh
env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mm-zero-partial-20261023/control/focus.py \
  --run focused-2
```

Guest stage: `/root/kdlock-evidence/10.176.26.71/tests/mm-zero-partial-20261023`.
The runner loads four captured modules one at a time, runs each case serially,
validates exact receipts and unloads normally after drain. It reuses seven old
clients and compiles nothing. `build-1/result.json` binds binaries and the
baseline `/root/kdlock-kernel-baselines/mmap-kdmm10-20261023` (Build ID
`cc732abe659b1093c82b06c637ff8bb36948c672`). Its identity is reconstructed in RAM
from `/root/kdlock-kernel-work/mm-zero-partial-20261023`; it is not a complete
module build tree. Recovery clears that temporary identity.

## Cases and observations

R denotes a private resident anonymous page, U an absent PTE (page-table entry),
and Z a present read-only shared-zero PTE. Each of `prefix`, `middle`, `suffix`
combines with `-zu`, `-uz`, `-zr`, `-rz`, `-zz`. Letters describe survivors in
ascending address order, excluding the target. All 15 shapes run separately
with `native SHAPE` and `zero SHAPE`; none is deduplicated. Native uses the
ordinary native body on the same KD backend with delegation disabled.

The probe writes only R slots, reads only intended Z slots, pins only R slots,
and queries all PTEs through the unchanged module's read-only `UB_PTES` interface.
That interface uses `is_zero_pfn()` to prove Z; zero contents alone are insufficient.
U remains untouched before snapshots, except the explicit competing reader
whose fault and resulting Z are recorded. With no U survivor, that fault uses
an untouched neighbor. It waits behind the writer and executes locally. Two
local readers overlap before writer admission; no reader is delegated.

Before controller survivor reads, the probe checks exact mappings, original
page identities/references, reverse-map links and per-VMA `smaps` RSS (resident
set size)/anonymous bytes. Z and U contribute no private resident bytes.
Original CPUs verify that removed addresses fault after warming their TLB
(cached address translation). After zero reads, successive private writes must
change only the chosen PTE, preserve other survivor contents/zero entries and
leave an independent zero mapping unchanged. Each step records physical
identities and the independent mapping's zero classification. Cleanup removes
all mappings and drops exactly the owned test references.

Additional modes are `zero refusal` (busy resident survivor), `zero zero-target`
(explicit unsupported target), `zero cancel` and `zero free` (no test pins during
removal). `error native resident middle-zz 1|2` and its `error kd` counterpart
exercise both reachable interior split-error points. Native-compatible harmless
splits remain; destructive local replay is rejected. Handback/ACK
(acknowledgement), sticky fallback and allocation retirement retain exact identities.

`receipts.py` binds body, split, physical-page and zero-PTE evidence to the same
mm/request/origin/different executor. `controls.py` corrupts copies of real run
records to ensure these checks reject lost ownership, wrong executors, replay,
zero-state changes and incorrect accounting. Queue acceptance, local fallback
and synthetic callbacks never count as remote execution.

The six preservation smokes cover mixed, fully resident and untouched partial
removal, four-page whole removal, advice and separate first-write faults.
Forced mapping/residency replacement, concurrent zero-page write faults during
the body, reclaim/fast-pinning races, pressure and post-admission cancellation
remain untested. Larger mappings, complex ancestry and general table destruction
remain unsupported. Zero-page targets still hand back on this captured kdmm10
image; the [zero-target guide](../zero_target/README.md) documents the later
target extensions.
No performance result or general mmap/page-fault support is implied.
