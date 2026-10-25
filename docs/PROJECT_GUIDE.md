# Project guide

The primary checkout on `380G10` is the source of truth. `master` contains the
accepted KD-only mutex from `d2a2304`, with its legacy delegation protocol and
compatibility backports. `accepted/kd-only-mutex-20261018` preserves the measured
implementation. The authorized October 25 local fast-forward integrated the
IRQ-safe rwsem/mmap correction at `e6fc371` and its preparation through `92f773f`
into `master`; later documentation and diagnostic preparation commits are local.
`current/kd-mutex` retains the earlier `af330db` instruction-exit checkpoint and
does not include the later spin helper work. The earlier consolidation is retained
in [branch dispositions](history/main-consolidation-20261018.md).

Start with the [current lock catalog](LOCKS.md), then its implementation guide
for spinlock, mutex, rwlock or rwsem. [Design](DESIGN.md) explains shared execution;
[lock protocols](design/lock_protocols.md) compares backends, and the
[code map](CODE_MAP.md) locates source. The [documentation index](README.md) separates API,
execution, operations, benchmark and historical material.

## Basic working version

Reuse the validated functional implementation. The current
[throughput-only roadmap](THROUGHPUT_PLAN.md) separates documented lock workloads,
actual mmap and actual page faults. The shared-mm payload/client preparation is
build-ready. The earlier plain/sampled October 25 attempt
[stopped before boot](../bench/results/10.176.26.71/bench/mmap-kdmm31-paired-20261025/README.md)
when host admission found 73 QEMU tasks versus 67; all 24 measured sessions remain
unrun. Its 24-case plan cannot be reduced by skipping sampled cases. The explicit
12-case `plain-v1` runner/report mode passed 25 focused mocked tests and still
requires exact live approval; a generic actual page-fault throughput driver still
needs preparation. There is no
qualified new timing or optimization gain. Earlier rejected measurements remain
rejected; new tail-latency work is deferred.

| Task | Working interface and scope |
| --- | --- |
| Unsupported operations | Reviewed markers stop before the original operation, return execution to its waiter without replaying the prefix, and disable delegation of that entry for the source session. Mutex/rwsem use ABI2; root spin/rwlock use ABI1/3. Unknown operations still fail admission. See [continuation checks](../tests/kernel/jit_escape/README.md). |
| Unified mutex | Direct `kd_mutex_lock/unlock` and blocking aliases use DIRECT, retaining nesting and exact unlock routing. Signal, try, I/O and callable-symbol paths execute locally on the KD object. See [API mappings](design/kd_only_mutex.md). |
| Reader/writer locks | Readers are concurrent and local. Rwlock DIRECT writers can delegate. Use `include/kd_rwsem.h` and `struct kd_rwsem` for ordinary sleeping rwsem operations; explicit OUTER writers use `include/kd_rwsem_direct.h`. See the [lock catalog](LOCKS.md) for cancellation and downgrade limits. |
| Real mmap and faults | The maintained integration changes the lock backend and minimal API/lifetime wrappers only. Readers stay concurrent and local; mmap, munmap, advice and page-fault bodies retain native algorithms and run on the originating task. Operation-specific body delegation is retired. See [scope and validation](../kernel_integration/mmap_lock/README.md). |
| Nano benchmark | The resident-list payload supports spin, public mutex, rwlock and rwsem. The [basic runner](../bench/basic/run.py) runs one 16-node KD case per family: 16 workers for spin/mutex/rwsem, the established 60-worker preset for mixed rwlock. It checks data, returned JIT bodies and retirement. Comparison runners remain available; original TCLock rwsem is available for registered fixed-affinity workers; general TCLock MM remains unsupported. |

The rwsem's internal local mutex gate supplies physical writer exclusion after
reader admission closes; callers must not bypass that public read/write protocol.
The mmap adapter uses ordinary local operations behind Linux's `mmap_*` wrappers.
The [corrected-image receipt](../bench/results/10.176.26.71/tests/mmap-irq-trylock-20261025/README.md)
records 137 Native and 161 KD assertions on actual mm objects. The 352 standalone
assertions and two basic programs are separate validation classes. These checks
do not establish full Native semantics, fairness, whole-kernel, RT or lockdep
equivalence. Atomic final-reader release avoids synchronous wakeups; writers
recheck drain after one jiffy (4 ms at HZ=250, plus possible scheduling delay).
Mmap's killable writer path bypasses the ordinary 16,384-probe polling stage;
see [rwsem waiting](design/rwsem_implementation.md#waiting-and-wakeups).

The following basic smoke workflow retains its previously approved 90-second
settling interval after idle synchronization and the
[VM recovery checks](operations/VM.md). It is separate from the pending mmap
comparison and cannot requalify a rejected timing endpoint. Capture a fresh host
receipt on the source host:

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

The [basic-version results](../bench/results/10.176.26.71/tests/basic-version-20261022/README.md)
record returned-body passes for all four presets and the retained 16-worker
rwlock `NO_JIT` failure. That smaller case was correct and drained but did not
demonstrate delegation. The 60-worker preset is functional coverage, not a fix
or performance comparison. Its earlier follow-up order covered low-cohort
delegation, the seven regression causes and MM wake attribution. The current
bounded mmap proposal measures whole-cycle throughput and sampled latency;
it does not establish those causes or replace the retained functional evidence.

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
