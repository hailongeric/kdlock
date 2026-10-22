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

## Basic working version

The current priority is functional delivery. Reuse validated implementations;
causal profiling, p95, exhaustive matrices and performance tuning are deferred.
Earlier rejected measurements remain rejected.

| Task | Working interface and scope |
| --- | --- |
| Unsupported operations | Reviewed markers stop before the original operation, return execution to its waiter without replaying the prefix, and disable delegation of that entry for the source session. Mutex/rwsem use ABI2; root spin/rwlock use ABI1/3. Unknown operations still fail admission. See [continuation checks](../tests/kernel/jit_escape/README.md). |
| Unified mutex | Direct `kd_mutex_lock/unlock` and blocking aliases use DIRECT, retaining nesting and exact unlock routing. Signal, try, I/O and callable-symbol paths execute locally on the KD object. See [API mappings](design/kd_only_mutex.md). |
| Reader/writer locks | Readers are concurrent and local. Rwlock DIRECT writers can delegate. Ordinary sleeping rwsem writers are local; explicit OUTER writers can delegate. See the [lock catalog](LOCKS.md) for cancellation and downgrade limits. |
| Real mmap and faults | Separate untouched mmap/munmap and page-fault tests use the experimental guest's actual `mm->mmap_lock` adapter. Readers and writers execute locally; this is not MM-body delegation. See [commands](../kernel_integration/mmap_lock/README.md#basic-correctness-commands). |
| Nano benchmark | The resident-list payload supports spin, public mutex, rwlock and rwsem. The [basic runner](../bench/basic/run.py) runs one 16-node, 16-worker KD case per family, checking data, returned JIT bodies and retirement. Comparison runners remain available; TCLock sleeping rwsem and TCLock MM are unsupported. |

After idle synchronization and the [VM recovery checks](operations/VM.md), use
the approved 90-second settling interval after the guest idle check. Capture a
fresh host receipt on the source host:

```sh
ssh -o BatchMode=yes -o ConnectTimeout=10 eric@10.176.26.71 \
  'sudo -n python3 -' \
  < bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/capture-host.py \
  > /tmp/kd-basic-host.json
scp -P 2222 /tmp/kd-basic-host.json root@10.176.26.71:/tmp/kd-basic-host.json
```

In the same recovery guest, after verifying the actual snapshot:

```sh
cd /root/host_fs/kdlock
export PATH=/root/kdlock-translation-venv-20261019/bin:$PATH
export LC_ALL=C PYTHONDONTWRITEBYTECODE=1
export KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z
python3 bench/basic/run.py --host-state /tmp/kd-basic-host.json \
  --output /root/kdlock-evidence/10.176.26.71/tests/basic-NEW
```

Use a new output name each time. Dependencies, both basic programs and focused
runner guards precede the four serial cases. `--families mutex` selects one
family; `--dry-run` prints commands without building or loading modules. Each
child status and complete session receipt is retained. Failure stops the run;
a deadline reports unknown drain without killing the child. Establish drain
before later work or unload.

This mode produces no performance score. Additional QEMU `worker` threads are
recorded and allowed only on CPU 63. Original QEMU identity, task identities,
pins, frequency policy, memory bindings, topology, isolation, recovery and
correctness protections remain. The strict 67-thread timing gate and every
historical refusal stay unchanged. Local-only or partial execution cannot pass
the returned-JIT smoke requirement.

## Folder ownership

Keep one directory per responsibility. Similar names do not imply interchangeable
protocols or workloads:

| Location | Contents |
| --- | --- |
| `include/` | Public APIs and the shared execution ABI |
| `kernel_module/` | KD provider; private `spin/`, `mutex/`, `lock/` and `execution/` fragments remain with their owning translation units |
| `daemon/`, `disassem/` | Publication/control service and Python translation/admission, respectively |
| `tclock_backend/` | Independent comparator implementation and upstream provenance |
| `workload_modules/` | Benchmark and shared kernel payloads; correctness-only payloads live under `tests/kernel/` |
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
