# Project guide

The primary checkout on `380G10` is the source of truth. `master` contains the
accepted KD-only mutex from `d2a2304`, with its legacy delegation protocol and
compatibility backports. `accepted/kd-only-mutex-20261018` preserves the measured
implementation. Use `master` for current code: at this documentation review,
`current/kd-mutex` retains the earlier `af330db` instruction-exit checkpoint and
does not include the later spin helper work. The earlier consolidation is retained
in [branch dispositions](history/main-consolidation-20261018.md).

Start with the [current lock catalog](LOCKS.md), then its implementation guide
for spinlock, mutex, rwlock or rwsem. [Design](DESIGN.md) explains shared execution;
[lock protocols](design/lock_protocols.md) compares backends, and the
[code map](CODE_MAP.md) locates source. The [documentation index](README.md) separates API,
execution, operations, benchmark and historical material.

## Folder ownership

Keep one directory per responsibility. Similar names do not imply interchangeable
protocols or workloads:

| Location | Contents |
| --- | --- |
| `include/` | Public APIs and the shared execution ABI |
| `kernel_module/` | KD provider; private `spin/`, `mutex/`, `lock/` and `execution/` fragments remain with their owning translation units |
| `daemon/`, `disassem/` | Publication/control service and Python translation/admission, respectively |
| `tclock_backend/` | Independent comparator implementation and upstream provenance |
| `workload_modules/` | Kernel payloads; synthetic and real API workloads retain separate identities |
| `bench/` | Maintained runners and shared collection/archival helpers |
| `bench/archive/` | Historical offline analysis tools, with one index and dependency list |
| `tests/unit/`, `tests/protocols/` | Unit fixtures and directly affected protocol drivers |
| `tests/kernel/`, `tests/live/`, `tests/tools/` | Provider probes, lifecycle runner and specialized audit tool |
| `bench/results/<machine>/` | Compact reports under `bench/` and `tests/`; ignored raw records under `raw/` |
| `docs/design/`, `docs/operations/`, `docs/history/` | Current contracts, VM procedures and historical decisions |
| `kernel_baseline/` | Required kernel identity inputs and captured historical experiments |
| `tools/vm/` | Idle-only source synchronization |

Do not merge comparator implementations, measured machine identities or frozen
run inputs to reduce the directory count. Private `.inc` files remain source
inputs and must be included in snapshots. The empty `tests/clients/` directory
and the local `bench/.tmp` compatibility alias were removed; use the explicit
payload, runner and result locations above.

The October 21 cleanup removed source-host raw entries whose run names date
before October 1, 2026, without creating an archive ref. It did not use file
modification times to classify source or records. Undated records and required
kernel baseline inputs remain; see the [retention note](../bench/results/README.md#record-retention).

## Guest workflow

Edit `/home/eric/vm/vm-shared/kdlock` on the source host. Stage intended new files
and use `python3 tools/vm/sync_to_vm.py` to update the idle benchmark VM. Build and
run tests there, under `/root/host_fs/kdlock`, or in a verified frozen copy on its
data disk. The mirror and guest are not independent source checkouts.

The current VM has 64 vCPUs, two 32-core NUMA nodes and 24 GiB RAM. The standard
benchmark grid is 1–8 workers by one and 12–60 by four, with collector CPU 63.
Do not use the old temporary 66-vCPU launcher recipe. Exact environment and
verification commands are maintained in [VM operations](operations/VM.md).

## Kernel identity

Use the [identity verifier](operations/VM.md#kernel-identity). Expected release:
`6.1.159-kdclobber2`; Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`.
Source, config and live identity must agree; `uname -r` alone is insufficient.

## Native qspinlocks in the VM

The benchmark boot requires `nokaslr`, `nopvspin` and voluntary preemption.
Check the live command line and the independent PV-spinlock boot message, as
described in [boot verification](operations/VM.md#boot-policy). Preserve the
recorded kernel and mitigation settings; no kernel rebuild/reboot is implied.

Use [basic and affected tests](../tests/README.md) for changes, and the
[benchmark guide](../bench/README.md) for measurements. Save evidence outside
the checkout, with the physical host identity and frozen inputs. Confirm a
recoverable snapshot before live module/JIT work, then verify complete drain.
