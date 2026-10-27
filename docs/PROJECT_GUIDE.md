# Project guide

The ultimate objective is in-kernel replacement of relevant Linux locks and
end-to-end comparison of unchanged programs such as `mmap1`. The
[project roadmap](ROADMAP.md) defines the three stages: lock micro/nano evidence,
scoped mmap/page-fault improvement or parity, and broader kernel replacement with
application evaluation. This guide describes the working checkout and interfaces;
current implementation limits are not a redefinition of that long-term goal.

The development VM uses Ubuntu 26.04.1 LTS and the new development release
`7.0.0-38-kdlock1`. The reviewed kernel build and installation are complete.
Its first boot exposed unsigned distro-module copies and taint 8192 before any
project module load. Signing repair and the second boot passed with taint 0.
Earlier functional receipts remain tied to their recorded source versions.
The new trusted-translation policy passed its read-only taskname live control
with correct data, returned JIT bodies and drain. This does not validate other
source paths; live MM integration and performance remain unvalidated. The
[Linux 7 port record](../bench/results/10.176.26.71/tests/linux70-port-20261027/README.md)
owns current source, build and validation evidence. The preceding
[migration record](history/vm-ubuntu2604-migration-20261027.md) owns the OS upgrade;
the [retirement record](history/kernel-retirement-20261027.md) preserves Linux
6.1 recovery inputs. No further adaptation targets that legacy kernel.

The primary checkout on `380G10` is the source of truth. `master` contains the
accepted KD-only mutex from `d2a2304`, with its legacy delegation protocol and
compatibility backports. `accepted/kd-only-mutex-20261018` preserves the measured
implementation. The authorized October 25 local fast-forward integrated the
IRQ-safe rwsem/mmap correction at `e6fc371` and its preparation through `92f773f`
into `master`. Subsequent work added the expanded throughput plan and recorded
the stopped QEMU diagnostics; see the [throughput campaign plan](THROUGHPUT_PLAN.md).
`current/kd-mutex` retains the earlier `af330db` instruction-exit checkpoint and
does not include the later spin helper work. The earlier consolidation is retained
in [branch dispositions](history/main-consolidation-20261018.md).

Start with the [current lock catalog](LOCKS.md), then its implementation guide
for spinlock, mutex, rwlock or rwsem. [Design](DESIGN.md) explains shared execution;
[lock protocols](design/lock_protocols.md) compares backends, and the
[code map](CODE_MAP.md) locates source. The [documentation index](README.md) separates API,
execution, operations, benchmark and historical material.

## Current development workflow

The authenticated source package is `linux=7.0.0-38.38`. Its upstream content is
7.0.14 while its custom Ubuntu ABI release is `7.0.0-38-kdlock1`; keep both
identities. The development source and output are separate:

| Purpose | Guest path |
| --- | --- |
| Source | `/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/source` |
| Build output and external-module KDIR | `/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build` |
| Schema-2 identity bundle | `/root/kdlock-kernel-baselines/linux70-kdlock1-20261027` |
| Verified clean-platform recovery snapshot | `linux70-kdlock1-clean-20261027` |
| Pinned translator | `/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3` |

The [kernel prerequisite patch](../kernel_integration/linux70/README.md) provides
the real spin-clobber ABI and five required GPL exports, while ordinary Linux
spin macros remain unchanged. KD mutex retains its own clobber entry, physical
exclusion and ABI2. The separate [mmap adapter](../kernel_integration/linux70/MMAP.md)
has enabled/disabled object checks; `CONFIG_KDLOCK_MMAP` remains disabled in the
installed kernel. Native MM bodies and original-task execution remain intact.
Compilation of the optional adapter does not establish live shared-mm support.

Boot/signing validation and canonical schema-2 capture passed. Before any live
basic check, reverify the captured
[schema-2 identity](../kernel_integration/linux70/IDENTITY.md), and verify a real
current-platform recovery snapshot. The monitor listing confirms the named
clean-platform snapshot; keep the legacy snapshot separate. Running identity verification must return
`runtime_policy_verified: true`. The basic runner uses the canonical build as
`--kernel-source` and the captured identity as `--kernel-baseline`; it also
requires explicit host-reference bytes and SHA256, a fresh host capture, and
the matching snapshot tag. [VM operations](operations/VM.md) owns the exact
host, recovery, synchronization and dependency procedure.

The translator uses pinned dependencies and an exact Python 3.14
[Miasm compatibility patch](../disassem/compat/README.md), with a dependency-byte
preflight before decoding. Production trusts all selected kernel and module
code, skipping context/value, loop and minimal-entry input proofs. The compiler
clobber-entry input agreement is assumed; the IP/SP/BP packet does not grow.
Strings use ordinary decoded CALL/RET, with no special string service or summary.
`trusted_source=False` retains checked analysis as an explicit Python regression
option. Source leases, correct lowering, return routing and runtime ownership
remain mandatory. See the [translation policy](design/admission.md) and
[affected-check receipt](../bench/results/10.176.26.71/tests/ordinary-string-translation-20261027/README.md).
External-module wrappers receive KDIR;
do not globally export `KERNELRELEASE`, which can bypass their outer Makefile
targets. Full-kernel build/install invocations require the explicit custom
release. Keep source snapshots immutable while any build or check is active.

The basic runner produces functional evidence only: correct data, returned JIT
bodies and complete retirement for each selected family. It does not turn a
build, local completion, NORMAL image or host-placement pass into a performance
result. New Linux 7 measurements must retain their own source, topology,
configuration and mitigation identities.

The maintained basic presets now use c01 cacheline bodies: 16 workers for spin,
public mutex and rwsem, and 60 for mixed rwlock. Each requires correct data,
returned JIT bodies and complete drain. These replacement presets need fresh
functional receipts; previous-payload results do not validate them. General
semantic equivalence, live mmap/page-fault support, whole-kernel replacement
and performance remain separate gates. The
[port record](../bench/results/10.176.26.71/tests/linux70-port-20261027/README.md)
preserves the retained implementation and validation evidence.

The separate explicit-OUTER mutex and spin native-escape probes also passed
four phases of 160,000 operations each. Their cold delegated phases returned
158,037 and 158,711 JIT bodies respectively. Each hot phase recorded one JIT
entry, zero JIT completions and one native escape; the subsequent banned phase
recorded no JIT activity. The probes checked original-task resumption, effects,
flags, terminal banning and final drain. This is the bounded
[native-escape proof](../bench/results/10.176.26.71/tests/linux70-port-20261027/README.md)
for those two call paths, not a returned-body claim for the hot phase or a
performance measurement.

## Retained functional evidence

This section records the validated legacy functional implementation. The
[throughput campaign plan](THROUGHPUT_PLAN.md) separates documented lock workloads,
actual mmap and actual page faults. The shared-mm payload/client preparation is
build-ready. The earlier plain/sampled October 25 attempt
[stopped before boot](../bench/results/10.176.26.71/bench/mmap-kdmm31-paired-20261025/README.md)
when host admission found 73 QEMU tasks versus 67; all 24 measured sessions remain
unrun. Its 24-case plan cannot be reduced by skipping sampled cases. The explicit
12-case `plain-v1` runner/report mode passed 25 focused mocked tests, but its
[authorized attempt](../bench/results/10.176.26.71/bench/mmap-plain-v1-20261025/README.md)
also stopped before boot at 68 QEMU tasks versus 67; all twelve measurements
and six unscored checks remain unrun. The separate `plain-scaling-v1` plan
prepares 21 worker counts and 126 measured sessions. Its 41 focused mocked
tests passed; that three-repeat matrix remains unrun. The separate
[16-worker validation pair](../bench/results/10.176.26.71/bench/mmap-worker-screen-20261026/README.md)
qualified under its recorded policy, and the later
[one-round MM screen](../bench/results/10.176.26.71/bench/catalog-mmap-single-20261026/README.md)
completed exploratory measurements. Neither establishes a repeated current
mmap baseline or an optimization gain. A generic actual page-fault throughput
driver still needs preparation. Earlier rejected measurements remain rejected;
new tail-latency work is deferred.

| Task | Working interface and scope |
| --- | --- |
| Unsupported operations | Reviewed markers stop before the original operation, return execution to its waiter without replaying the prefix, and disable delegation of that entry for the source session. Mutex/rwsem use ABI2; root spin/rwlock use ABI1/3. Trusted source still needs supported decoding/lowering and valid runtime protocol state. See [continuation checks](../tests/kernel/jit_escape/README.md). |
| Unified mutex | Direct `kd_mutex_lock/unlock` and blocking aliases use DIRECT, retaining nesting and exact unlock routing. Signal, try, I/O and callable-symbol paths execute locally on the KD object. See [API mappings](design/kd_only_mutex.md). |
| Reader/writer locks | Readers are concurrent and local. Rwlock DIRECT writers can delegate. Use `include/kd_rwsem.h` and `struct kd_rwsem` for ordinary sleeping rwsem operations; explicit OUTER writers use `include/kd_rwsem_direct.h`. See the [lock catalog](LOCKS.md) for cancellation and downgrade limits. |
| Real mmap and faults | The maintained integration changes the lock backend and minimal API/lifetime wrappers only. Readers stay concurrent and local; mmap, munmap, advice and page-fault bodies retain native algorithms and run on the originating task. Operation-specific body delegation is retired. See [scope and validation](../kernel_integration/mmap_lock/README.md). |
| Nano benchmark | The [nano runner](../bench/nano/README.md) selects ten c01/c16/post256 profiles for public mutex, rwlock and rwsem. The separate [basic runner](../bench/basic/run.py) uses c01 for four-family functional checks, requiring data correctness, returned JIT bodies and retirement. Original TCLock rwsem supports registered fixed-affinity workers; general TCLock MM remains unsupported. |

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

The [archived basic smoke workflow](https://github.com/hailongeric/kdlock/blob/cd6f1061ea1b3686dd6d43a7a180ab1942ea4e57/docs/PROJECT_GUIDE.md#basic-working-version)
retains the exact Linux 6.1 command sequence, Python environment and recovery
assumptions. It is historical functional evidence, not a runnable Linux 7.0
quick-start. The new platform uses the separately captured workflow, live
functional evidence and recovery boundary above.

That workflow produced no performance score. It retained the strict 67-thread
timing gate, exact drain and returned-JIT requirements; neither the OS migration
nor a locally completed body turns its historical refusals into passes.

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
| `kernel_baseline/` | Legacy identity verifier, captured provenance and ABI test fixtures for the retained recovery version |
| `kernel_integration/linux70/` | Current kernel prerequisites, optional mmap preparation and schema-2 identity capture/verification |
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

The custom development image is `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, built from Ubuntu source package
`7.0.0-38.38` with Linux version code `458766`. Use the
[VM identity checks](operations/VM.md#kernel-identity) and schema-2 bundle to
bind built, installed and running states. The stock `7.0.0-38-generic` image and
its headers remain recovery inputs; their identity cannot qualify the custom
provider. The old `kdclobber2` identity belongs to the
[legacy retirement record](history/kernel-retirement-20261027.md).

## Native qspinlocks in the VM

The verified boot retains `nokaslr` and `nopvspin`, but the Linux 7.0 preemption
selector reports `full (lazy)`, not the legacy voluntary setting. Record current
configuration and runtime policy through [VM operations](operations/VM.md#boot-policy)
before new measurements; historical results do not establish equivalence.

Kernel/source adaptation, basic functional passes and broader support are
separate scopes. Save new evidence with its physical host, OS, kernel and source
identities, and verify recovery before live module/JIT work. No Linux 6.1 result
is relabelled as a Linux 7 pass.
