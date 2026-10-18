# Project guide

The primary checkout on `380G10` is the source of truth. `master` contains the
accepted KD-only mutex from `d2a2304`, with its legacy delegation protocol and
compatibility backports. `accepted/kd-only-mutex-20261018` preserves the measured
implementation; `current/kd-mutex` follows the consolidated main version.
See [branch dispositions](history/main-consolidation-20261018.md).

Start with [design](DESIGN.md), [lock protocols](design/lock_protocols.md) and
the [code map](CODE_MAP.md). The [documentation index](README.md) separates API,
execution, operations, benchmark and historical material.

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
