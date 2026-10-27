# Benchmark workloads and critical sections

These definitions remain reference workloads after
[Linux 6.1 retirement](history/kernel-retirement-20261027.md). Ubuntu 26.04 /
Linux 7.0 is the active adaptation platform. KD and runner compatibility still
require validation before matched measurements; the retained results keep
their original kernel identities. See the
[migration record](history/vm-ubuntu2604-migration-20261027.md) for OS readiness and
the [Linux 7 port record](../bench/results/10.176.26.71/tests/linux70-port-20261027/README.md)
for source and validation status. Active API adapters target the authenticated
Ubuntu source package `linux=7.0.0-38.38`, with development release
`7.0.0-38-kdlock1`. Build and live validation remain separate gates.

This catalog defines the synthetic and system-call/application programming
interface (syscall/API) workloads selected for
benchmarks on `master`. Use [benchmark commands](../bench/README.md) for execution and
[performance status](PERFORMANCE.md) for measured outcomes. Selection is not
a claim that the current KD version has passed every configuration.
The [project roadmap](ROADMAP.md) separates micro/nano evidence, scoped actual-MM
experiments and final kernel replacement. Its planned `mmap1_threads` comparison
uses 128 MiB untouched anonymous private mappings and a real mmap-lock backend;
`mmap1_processes` is a separate control. These are new comparison targets, not
aliases for the existing 4 KiB device mapping or private-backing fault workloads,
and do not change the completed historical catalog's workload count.
The [terminology guide](TERMINOLOGY.md) explains lock names, execution status
labels and measurement terms. In particular, a reader/writer spinlock (rwlock)
waits by spinning, while a reader/writer semaphore (rwsem) can sleep while
waiting. Just-in-time (JIT) compilation supplies code for delegated execution.

The standard grid is 1–8 workers by one and 12–60 by four, three repetitions per
configuration, comparing KD, TCLock and Linux Native where supported. Rwlock and
rwsem use 1% and 20% writes. The historically accepted `c21345b` rwsem matrix
compares KD with Linux Native; the separate original TCLock rwsem port supports
only its documented ordinary registered-worker pairs, without equivalent
cancellation, downgrade or mmap APIs.
Pass the worker grid explicitly using the linked runner commands: the
reader/writer runner's historical default and `--full-matrix` stop at 36 workers.
Synthetic bodies run repeatedly inside one ioctl per phase; API workers issue
syscalls individually. The active lock/API catalog has **61 configurations**:
the 51 micro/API configurations selected for the October 26 screen plus the
10 padded-counter nano profiles below. The original c01/c08 micro cases remain
selected: their call shells and post-work differ from nano c01/c16/post256.
The three separately implemented MM suites are also included when requesting
all implemented workloads. This means benchmark coverage, not the full unit-test
suite. At 21 worker counts and one round, the lock/API plan has 3,843 points
and the MM suites add 126; preparation failures remain failed points, not passes.
The maintained [current command plan](../bench/catalog_single/current_plan.py)
defines the 61 lock/API configurations; its historical `plan.py` counterpart
continues to define the earlier 51-case screen.
The [October 27 full catalog at fixed 2.0 GHz](../bench/results/10.176.26.71/bench/catalog-fixedfreq-20261027/README.md)
at source `a9aeb280` completed all 61 lock/API configurations: 3,704 valid measurements and 139 retained failed points.
The separate MM suites have 126/126 archive-audited measurements. Independent-mm mappings, private-backing faults and actual shared-mm mappings retain their separate kernel/backend identities.
Every measured coordinate has one round. Failed preparation has no rate;
strict host timing qualification remains failed under the authorized exploratory
policy. Frequency telemetry and exact data/drain validation are separate
from timing qualification. [Per-workload tables and ratios](../bench/results/10.176.26.71/bench/catalog-fixedfreq-20261027/COMPARISON.md)
retain all workload, call-shell, source and kernel distinctions. No rates are pooled.

In that Linux 6.1 catalog, xattr preparation failed at 139/168 KD coordinates,
versus 47/168 in the earlier catalog. These attempts retained exact drain and
have no throughput. That campaign retained its fixed eight-worker helper cohort
and returned-body prerequisite; the reason for the increased failure incidence
is not established. [Preparation evidence and limits](../bench/results/10.176.26.71/bench/catalog-fixedfreq-20261027/XATTR_PREPARATION.md).
The new Linux 7 xattr workload uses an rb-tree and local shared readers, so it
has no helper-learning phase or eligible JIT body. Its new revision and future
measurements must remain separate from those list/spin results.

The explicitly requested [single-round October 26 screen](../bench/results/10.176.26.71/bench/catalog-single-20261026/README.md)
attempted the 51 then-selected lock/API configurations on that grid.
It retains 3,166 valid timed observations and 47 drained KD xattr preparation
failures. Its exploratory host policy and one repetition do not establish
strict timing qualification or repeat variability. The separate
[mmap/fault extension](../bench/results/10.176.26.71/bench/catalog-mmap-single-20261026/README.md)
completed 126 single-round points across independent-mm mmap/munmap,
private-backing CPU faults and actual shared-mm Native/KD mmap/munmap, keeping
their distinct kernel and workload identities. Planned 64-node lists and generic
actual-mmap-backend page-fault throughput remain unimplemented.

The [current mutex comparison](../bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/README.md)
covers c01/post64, c08/post64, exclusive-update RCUHT, seek set/end, pipebytes
n16 and pipecap n16 with fresh Native/TCLock/KD controls. Its 567 valid, drained
sessions use three repetitions at `1 2 4 8 16 32 36 48 60` workers, a nine-point
subset of the standard grid. Collection revision `bd9d4ce` retains the
`752fec1` shared-node mutex runtime. Synthetic generated-body entries and API
returned-body probes remain separate; local `NO_JIT` sessions retain that class.
The c08 two-worker point has one local and two entry-witnessed repetitions,
so it has no complete three-repeat class result.

The historical [KD-only matrix](../bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md)
covers c01/post64 and `api-pipebytes-query-n16` on its recorded 256-byte mutex.
It does not measure the current shared-node 32-byte implementation. Broader historical owned-mutex
coverage remains in [history](history/README.md), with its original implementation
identity. The rwsem waiting policy selected at **`c21345b`** remains the baseline,
including its documented two-worker throughput regressions. Those measurements
predate the compact gate and IRQ-safe reader-release correction and do not
establish current performance. Sleeping rwsem with
outer writer delegation and extracted proc snapshots have explicit
runner modes described below. Full [process inspection and mmap candidates](#process-inspection-and-mmap-candidates)
remain proposals where stated, outside the runnable standard catalog. The current
lock-only mmap adapter has actual shared-mm device-writer evidence. The
[throughput campaign plan](THROUGHPUT_PLAN.md) retains the original 24/12-case
plans and the distinct three-repeat scaling matrix alongside the completed
single-round screen. Exact mmap1 comparison and actual page-fault throughput
remain future work; new latency sampling is deferred.
The earlier [24-case plain/sampled preparation](../bench/mmap_lock/README.md)
has passed. Its authorized October 25 attempt
[stopped at initial host admission](../bench/results/10.176.26.71/bench/mmap-kdmm31-paired-20261025/README.md)
before any boot or workload: 73 QEMU tasks versus the required 67. No qualified
measurement resulted from that attempt.

## KD API use and delegation

The [active nano workloads](../bench/nano/README.md) are separate additions
to the micro/API catalog. All ten reuse one or sixteen directly addressed,
64-byte-aligned counters and perform 256 register-only post-unlock rounds.
Every writer increments all selected counters; shared readers compare their
values, including a repeated load for the one-counter case.

| Active nano profiles | Lock and writes | Payload |
| --- | --- | --- |
| `mutex-throughput`, `mutex-locality` | Mutex, 100% writes | c01, c16 respectively |
| `rwsem-throughput-read`, `rwsem-throughput-mixed` | Rwsem, 1% / 20% writes | c01 |
| `rwsem-locality-read`, `rwsem-locality-mixed` | Rwsem, 1% / 20% writes | c16 |
| `rwlock-throughput-read`, `rwlock-throughput-mixed` | Rwlock, 1% / 20% writes | c01 |
| `rwlock-locality-read`, `rwlock-locality-mixed` | Rwlock, 1% / 20% writes | c16 |

Default nano runs select all ten profiles, Native/TCLock/KD and the 21 worker
counts (`1..8,12..60`, stepping by four above eight), with one round: 630 points.
Mutex uses public ABI2 calls; rwsem uses local readers and explicit outer writers;
rwlock uses local readers and direct writer pairs. Matching payload work, exact
write totals and separate JIT entry/return evidence remain required. The earlier
two-word `mutex`, `rwsem-read` and `rwsem-mixed` profiles are removed from the
active launcher; their frozen sources and results remain historical evidence.
The new selection does not fill or alter the earlier 51-configuration screen.
The user-directed promotion follows an exploratory
[factor screen](../bench/results/10.176.26.71/bench/mutex-profile-20261026/factor-grid/README.md)
under the earlier 256 NUMA boundary and a separate boundary experiment with
cross-NUMA gains and mixed within-node outcomes. The completed
[126-point fixed-frequency mutex comparison](../bench/results/10.176.26.71/bench/nano-mutex-fixedfreq-20261027/README.md)
uses the promoted 768 boundary; its results remain separate from those selection
studies. It does not validate the new rwsem/rwlock nano selection. The
[earlier tables and analysis](../bench/results/10.176.26.71/bench/nano-pair-20261026/README.md)
retain both successful and unsuccessful simplifications and explicit local controls.
See the [per-workload analysis](../bench/results/10.176.26.71/bench/catalog-single-20261026/PERFORMANCE_ANALYSIS.md)
for the selection and the distinction between delegated mutex wins and local
rwsem reader-path wins.

The 2026-10-18 source review, against `af330db`, confirmed that the then-implemented
workloads already called KD APIs. The table below describes the maintained
calls, including the new Linux 7 local-reader xattr port. Delegation means another executor
runs the protected body on behalf of the waiting caller. Current direct
`kd_mutex_lock/unlock` calls and blocking compatibility aliases use the unified
DIRECT ABI2 boundary. Callable mutex functions and signal/try/I/O acquisitions,
`kd_write_lock()` and `kd_down_write()` execute locally. Readers of KD rwlock
and KD rwsem also execute locally while holding shared read access.

The explicit pairs below permit delegation of admitted bodies. Admission is
the translator/runtime check that the compiled body can execute safely with
the captured inputs and execution context. It can still refuse a body, and an
eligible call can execute locally because of contention or admission policy.
An image labelled `NORMAL` proves publication only. Where completion probes are
enabled, a completed, returned JIT body proves successful delegated execution;
entry without completion is `PARTIAL_JIT`, and no entry is `NO_JIT`. The retained
synthetic mutex rounds cited here record entry witnesses only, so their return
count remains unknown. New resident-list profiles also read the existing root
completion counter. Keep these evidence classes separate in performance reports.

| Workload and lock | KD API already used | Delegation decision and protected boundary |
| --- | --- | --- |
| c01, c08, RCUHT: spin | `KD_SPIN_DIRECT_LOCK` / `KD_SPIN_DIRECT_UNLOCK` | Exclusive counter updates and hash searches/moves are eligible. Storage is preallocated; there is no per-operation allocation or reclamation. |
| c01, c08, RCUHT: mutex | OUTER by default; `--mutex-api public` uses literal `kd_mutex_lock/unlock` | The same bounded payloads are eligible through the selected KD mutex protocol. Caller shells remain separate measurement identities. |
| c01, c08, RCUHT: rwlock | `KD_RWLOCK_DIRECT_WRITE_LOCK` / `KD_RWLOCK_DIRECT_WRITE_UNLOCK`; `kd_read_lock` / `kd_read_unlock` | Writers may delegate; shared readers stay local. |
| c01, c08, RCUHT: rwsem | `KD_RWSEM_OUTER_WRITE_LOCK` / `KD_RWSEM_OUTER_WRITE_UNLOCK`; `kd_down_read` / `kd_up_read` | Writers may delegate after existing readers finish. Shared readers stay local. `--delegate off` uses ordinary local writers instead. |
| `ofd` | Spin direct pair above | Eligible list search and conflict-result copy, limited to the bound file's fixed OFD locks without callbacks. |
| `setfd` | Spin direct pair above | Eligible bitmap update. The caller's `current->files` lookup happens before acquisition; descriptor creation/removal and table resizing are excluded while bound. |
| `pipebytes`, `pipecap` | Mutex outer pair above | Eligible ring-length sum or capacity read. `pipebytes` copies to the user pointer after unlock; `pipecap` returns the value after unlock. Pipe mutation and resizing are excluded while bound. |
| `seek` | Mutex outer pair above | Eligible offset checks and `f_pos` updates. Linux 7 removed `f_version`; current adapters do not emulate that retired store. File-reference acquisition/release stays outside the protected body. |
| `utsname` | Rwlock writer pair and local read pair above | Only the fixed-size name update may delegate. User copies, permission checks, entropy mixing and notification execute on the original caller outside the lock. The current KD adapter uses a spinning rwlock, not KD rwsem. |
| `argbounds` | Spin direct pair above | Eligible four-word copy under exclusive spin ownership. Optional mutations execute locally through the same KD physical lock. This is an extracted record, not a live process's memory map. |
| `taskname` | `KD_SPIN_DIRECT_LOCK` / `KD_SPIN_DIRECT_UNLOCK` | Generated code calls the original `strscpy_pad(..., 64)` and models all 64 destination writes. Read-only correctness, returned-body checks and the `05876a4` standard-grid comparison are complete. The preceding version's separate 20% mutation control passed correctness with zero KD generated bodies; mutation-case delegation remains unestablished. |
| Linux 7 `xattr` (`xattr-rbtree-read-v1`) | `kd_read_lock` / `kd_read_unlock` | Shared readers execute locally across the original rb-tree search, `strcmp` comparisons and value copy. Zero operations are JIT-eligible; any generated-body entry or published image is rejected. Historical Linux 6.1 list/spin delegation results remain below. |

The corresponding source is in the [spin shell](../workload_modules/spin_cacheline/direct.h),
[mutex shell](../workload_modules/mutex_cacheline/module.c),
[rwlock shell](../workload_modules/rwlock_bench/direct.h),
[rwsem shell](../workload_modules/rwlock_bench/direct_rwsem.h),
[snapshot shell](../workload_modules/rwlock_bench/direct_spin.h) and the real API
[spin](../workload_modules/real_api/module.c),
[mutex](../workload_modules/real_api/mutex.c) and
[UTS](../workload_modules/real_api/uts.c) adapters.
The [interface guide](../include/README.md#preparing-a-delegating-body) gives
the required object, continuation, registration and matching-unlock rules.
Every consumer of a protected object must use the same lock protocol. An
ordinary API rename, an extra private lock around only some consumers, or a
cast from a Linux mutex to KD mutex does not implement that conversion.

Eligibility in this table is a source assessment, not a fresh benchmark result.
The current mutex comparison cited above measures all seven mutex cases at its
nine worker counts; it does not validate every catalog parameter. Its KD
synthetic evidence contains 68 entry-witnessed and 13 local sessions; its API
evidence contains 78 returned-body and 30 local sessions. Current results and
their source identities are listed in [performance status](PERFORMANCE.md).
The accepted rwsem matrix covers c01,
c08 and RCUHT. Other API measurements retain their historical source identities.
The latest [instruction-exit validation](../bench/results/10.176.26.71/tests/native-instruction-exit-20261018/README.md)
also completed delegated rwsem c08 and RCUHT writers, but it is a functional
check, not a new throughput matrix. The snapshot and API sections below retain
their successful execution evidence and refusals.

The new [checked instruction exits](design/admission.md#checked-instruction-exits)
apply only to mutex bodies and rwsem outer writers using ABI2, the mutex
machine-level calling agreement. Twelve reviewed processor instructions can
become markers that return execution to the original waiter before the
instruction runs and disable future delegation of that entry. The full source
body must still pass existing address, captured-register and execution-context
checks, including paths after a marker. Spin and rwlock writers retain static
instruction refusal. These mutex markers are separate from the spin-specific
taskname/xattr changes described below. Neither mechanism enables shared-reader
delegation or supplies the missing full mmap interfaces.

Taskname and xattr use the original kernel string APIs. Their effects are
described in the [admission guide](design/admission.md#original-strcmp-service).
Versions 10 and 11 perform no helper-code, helper-specific CALL, string-content or
runtime destination checks. They use the same valid storage and lifetime
guarantees as the native API caller. Ordinary address/register analysis and the
common physical-owner, frame and return-continuation checks remain active.
The taskname writer retains a statically known count of 64 and models all 64
output bytes. The reviewed callers also promise that ordinary data accesses do
not inspect or overwrite temporary return-address storage created by the
`strcmp` and `strscpy_pad` service calls. Analysis records that control storage separately from
ordinary object data; known attempts to observe it are refused. Every original
load, store and CALL return word remains present. This rule applies to selected
caller code, not to all kernel users of these APIs; see the
[selected-caller contract](design/admission.md#original-call-word-aliases).
Decoded `memcpy` remains an ordinary CALL with its original copy reads, writes
and RET dispatch. It has no special classification or return path. Generic
partial-CALL-alias refinement remains archived; the maintained revision keeps conservative
ordinary-CALL analysis and separate control storage only for the two string
services. Its focused unit and live correctness checks passed, as recorded in the
[preceding development record](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/DEVELOPMENT.md).
A body needing an address guard still needs independent proof that native
continuation does not consume incoming arithmetic flags; the string APIs do
not supply that proof. These changes do not validate arbitrary callers or
whole-kernel replacement.

Version 11 adds [direct original-helper calls](design/admission.md#direct-original-helper-calls):
eligible spin bodies call the original API without leaving generated code for
each comparison or copy. Source-code references are retained when the immutable
image is published. Ownership, the actual source return word, call limits and
completion evidence remain required. The original payload and KD mutex protocol
are unchanged. The [current development record](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md)
records completed focused checks, separate screening runs and diagnostic profiles.
The final bridge fixture passed 15,663 assertions, including register and flag
preservation, both incoming stack alignments, actual source return words and
quota exits. Profiles confirmed removal of the repeated source-pin lookups and
full-frame validations while generated bodies returned. Those diagnostic timings
are unscored. The [standard-grid report](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
now records the completed comparison against fresh Linux Native and TCLock runs.

Version 11 passed all eight xattr controls at 16 workers: front hit,
tail hit, missing name and size-only query, each with 16 and 128 attributes and
64-byte values. Each recorded correct results and matching generated-body
entries and completions. Read-only taskname passed on Linux Native, TCLock and
KD, including returned KD bodies. The original-string service, spin address-guard
recovery and mutex instruction-marker probes also passed. The preceding version's separate 20%
taskname mutation control with `--helper-waves 0` passed correctness on all
three backends but recorded zero KD generated bodies. That control does not
establish mutation-case delegation or replace the earlier strict failure.

The current [`05876a4` comparison](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
contains 567 correct, fully drained sessions: read-only taskname and
xattr tail queries at n16/n128, each with Linux Native, TCLock and KD on the
standard worker grid and three repetitions. Of its 189 KD sessions, 168 returned
at least one complete generated body (`PASS`) and 21 recorded no generated entry
(`NO_JIT`). None recorded entries without a completed body (`PARTIAL_JIT`).
`PASS` does not imply that most operations delegated: all three workloads had
zero generated entries at one and two workers, and some other low-worker cases
had few completed bodies. Taskname and xattr n16 had mixed statuses at three
workers; those repetitions are not pooled into one median.

At 60 workers, KD's whole-run medians were 4.521, 2.368 and 0.573 million
operations per second for taskname, xattr n16 and xattr n128 respectively.
Each exceeded its fresh Linux Native comparator and remained below TCLock.
These results do not imply the same ordering at other worker counts or for
peak rates. The [tables](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/tables.md)
retain the full grid, completed-body shares and separate peak measurements.
The main archive audit passed, checking 265 Git source files, 16 binaries and
315 actual loaded image captures. Separate development and quota archive checks
also passed preservation; their failed attempts and missing historical tracing
snapshot remain explicit in the [development record](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md#development-and-quota-archive-preservation).

The preceding [`88bb5a4` dispatcher comparison](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/README.md)
remains historical evidence: its 567 sessions were correct and drained, with
167 KD `PASS` and 22 `NO_JIT` results. At 60 workers its KD whole-run rates were
below both fresh comparators in all three cases. Current and historical samples
are kept separate; the current report compares compatible three-repetition
groups without pooling source revisions.

The older implementation frozen in `c79d84f` has separate
[functional evidence](../bench/results/10.176.26.71/bench/taskname-xattr-20261018/DEVELOPMENT.md)
for the ordinary taskname shell and all eight xattr query/list-size combinations.
At 16 workers, taskname's read-only check completed 3,200,000 operations with
3,194,222 matching generated entries and completed bodies. Its 20% mutation
case was correct and drained on all three backends, but KD completed nine bodies
only during preparation and zero during measurement. That strict measured-
delegation check remains failed; preparation does not substitute for a measured
completion. Keep this evidence and its Native/TCLock/KD matrix separate
from the revised version in the
[comparison record](../bench/results/10.176.26.71/bench/taskname-xattr-20261018/README.md).

## Synthetic cacheline updates

Each counter is a 64-bit value padded to a 64-byte slot. All workers access the
same selected counters under one lock. The bodies contain explicit updates:

| Label | Updates per operation | Selected payload footprint |
| --- | --- | ---: |
| `c01` | Increment counter 0 | 64 bytes |
| `c08` | Increment counters 0–7 | 512 bytes |

The micro catalog retains c01 and c08 for spin, mutex, rwlock and rwsem.
The separate nano profiles use c01 and c16 with post256, as defined above.
Select `--cachelines 1 8` in the
[spin/mutex runner](../bench/tclock_compare/README.md). KD mutex retains exact KD
physical ownership and pinned published delegation waiters; its OSQ and
delegation queues share preallocated storage with separate links and lifetimes.

For example, c01 performs a protected load/add/store:

```c
lock(L);
WRITE_ONCE(data[0].value, READ_ONCE(data[0].value) + 1);
unlock(L);
```

`READ_ONCE` and `WRITE_ONCE` do not make this an atomic increment by themselves;
the lock provides exclusion. There is no allocation, traversal or intentional
sleep in the plain payload. The `cNN` suffix counts payload cachelines only,
excluding lock storage and other metadata. Padding separates different counters;
every worker still shares the same counter in c01.

The current KD mutex occupies 32 bytes aligned to 8 bytes in the captured
configuration, matching Native's embedded footprint. Its delegation phase
and encoded tail are embedded; versioned waiter records and an independent
24-byte OSQ subrecord use existing node space. Four 320-byte slots per CPU serve
both memberships without changing their separate cancellation/retirement rules.
NUMA selection has a 64-node scan budget and a 768-body locality boundary;
eight or more deferred requests receive handoff and smaller prefixes continue FIFO,
within the configured total cap of 1024. There is no auxiliary lookup, shared
lock reference count or shared waiter-count update. Lock storage is separate
from workload counters and controls. The
recorded `d2a2304` KD-only comparisons used a 256-byte, 128-byte-aligned object;
they do not measure the compact layout or establish a performance gain for it.
The c01 name counts payload cachelines only. The historical spin/mutex loops include 64 dependent arithmetic rounds
after each unlock, defined in [post_work.h](../workload_modules/spin_cacheline/post_work.h).
The accepted c01 1–8-worker profile, later 22-count comparison and expanded
21-count mutex comparison use this post64 setting. An eight-round variant is
a different workload and needs its own baseline; it must not be pooled with
those results.
The current nano profiles use their separate reader/writer benchmark
payload with 256 rounds, as described above. The historical two-word controls
used four. Identical `c01` labels do not make these workload settings equivalent.

At completion, each selected counter must match the total completed increments;
unselected counters must remain unchanged.

## Resident linked-list traversal

The current micro catalog selects plain `list` with **16 nodes** (1 KiB of node
storage). A 64-node (4 KiB) case remains planned. List size 128 and the
`list-prefetch` variants at sizes 16 and 128 are excluded from the current
catalog. These resident traversals are separate from the ten active
padded-counter nano profiles.

The 64-node case is a planned addition, not implemented or measured yet. The
current runners and [shared payload](../workload_modules/spin_cacheline/list_payload.h)
accept only 16 and 128 nodes; their validation must be extended before running
64 nodes. The frozen nano campaign and its reports retain their original
128-node and prefetch measurements as historical evidence.

The payload uses preallocated, 64-byte-aligned nodes. An immutable circular next-pointer
permutation advances five array slots per link. Each write holds one exclusive
lock and visits exactly N nodes, incrementing every node once. Rwlock/rwsem
readers hold shared ownership and verify that all N values equal the first
value. There is no allocation, link mutation, reclamation, user-memory access
or deliberate scheduling point inside this payload.

The selected `list` workload omits software read-prefetch. The retained historical
`list-prefetch` variant adds a read-prefetch of the already loaded next pointer
on each iteration. All compared backends compile the same variant.
These hints target retained module storage and add no lifetime guarantee.
They are separate from KD's provider queue-prefetch option `--spin-prefetch`.
The traversal is bounded by N rather than by reaching a null pointer.

After callers join, the snapshot checks the independent expected permutation
before dereferencing each pointer, confirms every link and common value, and
returns that value in slot zero with the other 15 slots zero. Its measured
delta must equal completed operations for spin/mutex or completed writes for
rwlock/rwsem. Reader errors, damaged links, skipped nodes, lost/duplicated
increments and nonzero unused snapshot fields fail validation. The object and
payload stay resident until workers, source leases, frames and ACKs drain.

Spin and mutex support Native, TCLock and KD; rwlock supports all three with
local readers. Rwsem supports Native, original TCLock and KD. KD retains its ordinary/local
and explicit outer-writer modes; TCLock uses its original semaphore protocol
with registered fixed-affinity task contexts.
The public mutex example uses `--mutex-api public`. New list profiles record
both JIT entry and matching root-completion counts; entry-only execution does
not satisfy strict functional delegation acceptance. Workload, node count,
prefetch mode, lock family and caller shell remain distinct report identities.
`RETURNED_JIT` means a positive completion count; it does not require every
entry to return through that path. Keep both counts and the completion share.
Whole-interval counters do not establish the execution mix of the peak window.
This is a resident-memory microbenchmark, not an mmap or page-fault workload.

Before loading each backend, the runner decodes the exact compiled payload
functions and checks the requested read-prefetch variant. After stopping the
translator and before warmup, KD sessions compare uploaded and loaded image
bytes under a provider reference. The saved generated-object symbols delimit
the payload instruction interval, excluding wrapper headers and metadata from
the prefetch check. Ordinary spin/rwlock images retain their existing mutable
contract; this observation does not make them immutable. Publication checks
still bracket measurement, and returned-body evidence remains separate.
The decoder records hint opcodes and operands and proves their presence or
absence within those bounds. It does not prove the hint's pointer provenance
or loop placement; the shared source supplies the next-node traversal contract.
Native/TCLock ELF checks precede module relocations and alternatives and do not
claim to inspect their loaded text. Decoder failures retain diagnostics and fail
preparation through the runner's normal drain and failure-reporting path.

For the currently runnable selected case, spin/mutex runners use
`--workload list --list-nodes 16` and omit `--cachelines`; the reader/writer
runner uses `--workloads list --list-nodes 16`. Once 64-node support is
implemented and validated, use `--list-nodes 64` for its separate case. Do not
substitute 128 nodes for the planned 64-node case. The snapshot `lines` field
records N for these workload IDs. No ioctl structure
grows. Use the [standard worker grid](../bench/README.md#standard-worker-grid)
and matched backend/setup/post-work settings for performance comparisons.
Operation p95 latency is not sampled by these runners; inverse throughput
must not be reported as latency. Source eligibility and tests do not establish
a prefetch or delegation performance gain.
The separate [seven-point mutex diagnostic](../bench/results/10.176.26.71/bench/mutex-latency-20261021/README.md)
uses private caller copies to sample complete operations for c08, RCUHT and
pipe queries, with plain/disabled/sampled controls. It does not add latency
sampling to the resident-list runners or establish acquisition-only latency.

## Synthetic hash updates (`rcuht`)

The table contains 1,024 buckets and 4,096 preallocated nodes, with keys drawn
from 8,192 possible values. Buckets and nodes have 64-byte strides. One global
lock protects the entire table.

Each worker generates source and destination keys outside the lock. Inside the
critical section it searches the source bucket and, when necessary, the
destination bucket. A missing source or occupied destination ends the attempt.
Otherwise it changes the key in place within one bucket, or unlinks and relinks
the node across buckets. Outcome counters are local to the caller.

Every spin/mutex operation is an exclusive update attempt, including misses and
conflicts. Thus “100% writes” does not imply that every operation changes the
table. Despite the `rcuht` name, this payload performs no per-operation RCU
reclamation or allocation.
Final checks validate node count, unique keys, bucket placement and list links.

## Synthetic reader/writer mixes

| Payload | Reader critical section | Writer critical section |
| --- | --- | --- |
| Cacheline `c01`, `c08` | Load the first counter and compare every selected counter against it; c01 also reloads its sole counter | Increment all selected counters |
| `rcuht` | Search one bucket for a key | Perform the hash move attempt described above |

Readers hold the shared read lock; writers hold the exclusive write lock. Reader
validation uses caller-local results. Hash readers are not lock-free RCU readers.

The `wNN` suffix is the write percentage: `w01` means 1% writes and 99% reads;
`w20` means 20% writes and 80% reads. Every worker executes this mix, with a
deterministic initial phase and evenly spaced writes. It does not assign 20% of
workers to a dedicated writer role. The runner supports 0–100% writes and
defaults to the 1% and 20% mixes.

The micro reader/writer loop uses four dependent arithmetic rounds after each read or write
unlock, defined in its own [post_work.h](../workload_modules/rwlock_bench/post_work.h).
This differs from the spin/mutex post64 loop; compare backends within the same
lock family, payload and read/write mix. The active nano rwlock/rwsem profiles
select c01/c16 and explicitly override this setting to post256; their results
must remain separate from the c01/c08 micro cases.

For example, `rwlock-cacheline-c08-w20` means eight shared counter cachelines,
with readers checking all eight and writers incrementing all eight, at a 20%
write mix.

## Real API labels and parameters

The client issues syscalls on objects prepared before timing. The compact
subject labels used below spell out `n` for `entries` and `v` for `value_size`;
the runner's session names additionally record threads, repetition and backend:

```text
Compact label:  <kind>-<query>-n<entries>-v<value_size>
Session name:   <kind>-<query>-n<entries>-t<threads>-r<repeat>-<backend>
Plot file:      <kind>-<query>-<entries>-<value_size>.svg (or .png)
```

| Label component | Meaning |
| --- | --- |
| `kind` | Object/API case: `ofd`, `setfd`, `pipebytes`, `pipecap`, `seek`, `utsname` or `xattr` |
| `query` | Operation variant or lookup position, explained for each case below |
| `n16` | `--entries 16`; **the unit depends on the API**, as shown in the next table |
| `v64` | Recorded `--value-size 64`: xattr values contain 64 bytes; UTS requires fixed 64-byte names; the other cases retain this field but do not use it to size their payload |
| `t16` | 16 worker threads, independently of the `n` parameter |
| `r0` | First repetition, numbered from zero |
| Backend suffix | Selected implementation, such as `native`, `tclock`, `kdlock` or `stock` |

**`n16` is not a universal object count and does not mean 16 workers.** The runner
reuses the field name `entries` for several different workload parameters:

| Case | Meaning of `nN` / `--entries N` | Example values | What changing it changes |
| --- | --- | --- | --- |
| `ofd` | Number of preinstalled byte-range locks on one file | `n16` / `n128`: 16 / 128 ranges | List length and search work, particularly for tail and miss queries |
| `setfd` | Requested descriptor-number stride between workers | `n16` / `n512`: minima spaced by 16 / 512 descriptor numbers | Spacing of modified bits in the shared close-on-exec bitmap; the protected operation still changes one bit |
| `pipebytes` | Number of occupied 4 KiB pipe buffers | `n16` / `n128`: 64 KiB / 512 KiB buffered | Number of buffer descriptors traversed and summed per query |
| `pipecap` | Requested pipe capacity in 4 KiB pages | `n16`: request 64 KiB capacity | Capacity returned; the protected query remains a field read |
| `seek` | File length in 4 KiB pages | `n16`: 64 KiB file | File length and the reference point for `SEEK_END`; no file-data traversal |
| `utsname` | Percentage of operations that update a name | `n20`: 20% setters, 80% `uname()` | Read/write mix and frequency of exclusive acquisitions |
| `xattr` | Number of attributes attached to one file | `n16` / `n128`: 16 / 128 attributes | Linux 7 rb-tree size and search work; `vN` separately controls value bytes. Query-key names do not fix tree depth. |

The page-based cases use the client's fixed 4,096-byte setup units on the target
x86-64 kernel. Pipe capacity may be rounded by the kernel; the client records
and checks the actual returned capacity.

Examples:

- `ofd-tail-n128-v64`: query the last of 128 installed lock ranges. `v64` does
  not specify a 64-byte range; each installed range is one byte.
- `pipebytes-query-n16-t08-r0-native`: eight workers query a pipe containing 16
  buffers, in the first Native repetition.
- `utsname-host-n20-v64`: 20% hostname updates and 80% `uname()` reads, with
  fixed 64-byte names. Worker count is a separate field.

The archived [spinlock API report](../bench/results/10.176.26.71/bench/real_api/20261011/RESULTS.md)
and [mutex/reader-writer API report](../bench/results/10.176.26.71/bench/real_api/20261011-sync/RESULTS.md)
contain these real API combinations:
`ofd/tail` at n16/n128, `setfd/toggle` at
n16/n512, `pipebytes/query` at n16/n128, `pipecap/query` at n16, `seek/set` and
`seek/end` at n16, and `utsname/host` and `utsname/domain` at n20. Each records
v64. The client supports additional query variants described below.

## Real-world API critical sections

These workloads exercise kernel metadata accessed through ordinary userspace
APIs: file-lock lists, descriptor flags, pipe state, file offsets and namespace
names. Their critical sections range from a single field read to a linked-list
search or a structure copy. The protected object is shared by the workers in
each case.

OFD queries and descriptor flags use exclusive spinlocks. Linux 7 xattr queries
use shared reader/writer spinlock acquisitions. Pipe queries and file positioning
use exclusive mutexes. Consequently, even the read-only OFD and pipe queries
serialize on their target locks. UTS uses shared read
acquisitions for `uname()` and exclusive write acquisitions for name updates.
The descriptions below identify the actual reads, writes and traversal performed
between acquisition and release.

Active adapter bodies target Ubuntu `linux=7.0.0-38.38`; the full arrow chains
in the table are retained Linux 6.1 call-path references. The unchanged hook
names alone do not establish an identical call chain or body on Linux 7.
The runner preserves exact selected implementations and headers from the
separately bound source tree. Matched Native/TCLock/KD runs substitute the indicated function only for
the bound benchmark object and reproduce its relevant body in an adapter.
Stock runs retain the original body. Pipe and seek mutex cases support Stock,
Native, TCLock and KD controls. Native retains the kernel-owned mutex;
TCLock and KD use private adapter objects while all benchmark accesses obey the
selected protocol. KD never casts the kernel mutex to its own type. The
[runner contract](../bench/real_api/README.md#contract-and-comparison-limits)
defines allowed consumers and source/instrumentation differences. These are
syscall microbenchmarks on controlled objects, not complete application workloads.

| Case | Userspace API during measurement | Selected original kernel path | Substituted function |
| --- | --- | --- | --- |
| `ofd` | `fcntl(fd, F_OFD_GETLK, &flock)` | `__x64_sys_fcntl` → `do_fcntl` → `fcntl_getlk` → `vfs_test_lock` → `posix_test_lock` | `posix_test_lock` |
| `setfd` | `fcntl(fd, F_SETFD, flags)`, followed by `fcntl(fd, F_GETFD)` | `__x64_sys_fcntl` → `do_fcntl` → `set_close_on_exec` or `get_close_on_exec` | `set_close_on_exec`; verification remains original |
| `pipebytes` | `ioctl(fd, FIONREAD, &bytes)` | `__x64_sys_ioctl` → VFS ioctl dispatch → `pipe_ioctl` | `pipe_ioctl` for `FIONREAD` |
| `pipecap` | `fcntl(fd, F_GETPIPE_SZ)` | `__x64_sys_fcntl` → `do_fcntl` → `pipe_fcntl` | `pipe_fcntl` for `F_GETPIPE_SZ` |
| `seek` | `lseek(fd, offset, SEEK_SET)` or `lseek(fd, offset, SEEK_END)` | `__x64_sys_lseek` → `ksys_lseek` → `vfs_llseek` → `shmem_file_llseek` → `generic_file_llseek_size` → `vfs_setpos` | `ksys_lseek` for the selected file and modes |
| `utsname`, read | `uname(&utsname)` | `__x64_sys_newuname` → `newuname` syscall body | `__x64_sys_newuname` |
| `utsname`, write | `syscall(SYS_sethostname, name, 64)` or `syscall(SYS_setdomainname, name, 64)` | `__x64_sys_sethostname` or `__x64_sys_setdomainname` → corresponding syscall body | The selected setter entry |
| `xattr` | `fgetxattr(fd, name, buffer, size)` | `__x64_sys_fgetxattr` → `getxattr` → `do_getxattr` → `vfs_getxattr` → `__vfs_getxattr` → `shmem_xattr_handler_get` → `simple_xattr_get` | `simple_xattr_get` |

`F_OFD_GETLK`, `F_SETFD`, `F_GETFD` and `F_GETPIPE_SZ` are `fcntl()` commands;
`FIONREAD` is an `ioctl()` request. They are not separate syscall entry points.
For matched runs, the substituted body replaces the original at that point;
the full original helper chain is not additionally executed.

### OFD lock query: `ofd`

This API checks whether a proposed byte-range lock conflicts with an existing
lock on a file. OFD means open file description: ownership belongs to the open
description, rather than to an individual descriptor number.

Setup creates an anonymous tmpfs file with `memfd_create()` and installs N
nonadjacent one-byte write locks using `fcntl(owner_fd, F_OFD_SETLK, &flock)`.
Their starting offsets are 0, 2, …, `2*(N-1)`. Workers query through a separate
open file description, so the installed locks belong to a different OFD owner.

**Critical section.** For the populated file, `posix_test_lock()` holds the
exclusive spinlock `file_lock_context.flc_lock` while it:

1. Follows entries in the `flc_posix` linked list.
2. Compares each entry's owner, start/end offsets and read/write lock type with
   the proposed lock, skipping the same owner and nonconflicting ranges.
3. Copies the first conflict's owner, range, type and related fields into the
   caller's request, or sets its type to `F_UNLCK` if no conflict exists.

The Linux 7 adapter uses the embedded `file_lock.c`/`file_lock_core` fields
(`flc_list`, `flc_owner`, `flc_pid`, `flc_flags`, `flc_type`) and retains the
source's type/owner/range decisions, including the `F_UNLCK` request branch.
It rejects unsupported lock callbacks and keeps the existing fixed-OFD scope.

The shared list is only read; writes go to the query's result structure.
`F_OFD_GETLK` does not acquire or install the proposed lock. The spinlock protects
a consistent view of lock records that general file-lock operations can modify;
this benchmark keeps the installed records unchanged during queries. Tail and
miss cases exercise pointer traversal and repeated comparisons under the lock.

- `front`: query offset 0, matching the first installed range.
- `tail`: query offset `2*(N-1)`, matching the last range.
- `miss`: query offset `2*N+1`, which has no matching range.

Thus n16/tail queries offset 30, whereas n128/tail queries offset 254 and searches
a longer list. Every operation still makes one query. Allocation/conversion of
the temporary `file_lock` in `fcntl_getlk()` and userspace result copying occur
outside the target spinlock but remain part of the measured syscall.

### Descriptor flag update: `setfd`

This API changes whether a descriptor is automatically closed when its process
successfully executes a new program. The flag is stored per descriptor in the
file table's `close_on_exec` bitmap.

All workers share one `files_struct`, but each has its own descriptor and open
file description. Setup uses `fcntl(fd, F_DUPFD_CLOEXEC, 64 + worker_index*N)`.
This requests the lowest available descriptor at or above each minimum; the
actual allocation determines the final layout.

**Critical section.** `toggle` alternates `FD_CLOEXEC` between set and clear.
`set_close_on_exec()` holds the exclusive spinlock `files->file_lock` while it:

1. Gets the current descriptor table with `files_fdtable(files)`.
2. Sets the descriptor's bit with `__set_bit()` on the set path, or tests it with
   `test_bit()` and clears it with `__clear_bit()` when needed on the clear path.

This is a short update to one shared bitmap word, without list traversal or
allocation. After that section, the client issues a separate `F_GETFD` to verify
the bit through `get_close_on_exec()`. Thus **one counted operation contains two
syscalls**. It does not open or close a descriptor.

N changes bitmap placement, not the number of flags updated per operation.
With exact requested spacing, n16 separates bits by 16 positions (2 bytes),
whereas n512 separates them by 512 positions (64 bytes). This varies how many
workers write the same bitmap cacheline. All workers still contend on the same
file-table lock; independent bit locations do not create independent locks.

### Pipe byte count: `pipebytes`

This API reports how many bytes are currently readable from a pipe. The kernel
stores buffered data in a ring of `pipe_buffer` descriptors, each recording a
buffer's length and backing page.

Setup uses `mkfifo()`/`open()` to create a private FIFO, requests capacity with
`F_SETPIPE_SZ`, then writes N whole 4 KiB pages before timing. Workers use separate
open file descriptions referring to the same pipe. No pipe data is consumed or
added during the queries.

**Critical section.** For `ioctl(FIONREAD)`, `pipe_ioctl()` uses the exclusive
`pipe_inode_info.mutex` to protect this sequence:

1. Read `head`, `tail` and `ring_size`, deriving the ring-index mask.
2. Walk from the captured tail to head and load each occupied `bufs[index].len`.
3. Add those lengths into a local byte-count accumulator.

The mutex keeps the ring indices and buffer metadata consistent. This body reads
shared metadata and changes only local variables; it neither advances the pipe's
tail nor reads the contents of the backing pages. `put_user()` writes the total
to the user pointer after unlocking. n16 traverses 16 buffers and reports 65,536
bytes; n128 traverses 128 and reports 524,288 bytes. N therefore directly changes
the number of protected loads and loop iterations.

### Pipe capacity: `pipecap`

This API reports the pipe's capacity in bytes. This case uses the same pipe
setup, including prefilled pages; N specifies the requested capacity in pages.

**Critical section.** For `fcntl(F_GETPIPE_SZ)`, `pipe_fcntl()` takes the exclusive
`pipe_inode_info.mutex`, reads `pipe->max_usage`, multiplies it by `PAGE_SIZE`,
and releases the mutex. The protected payload reads one capacity field and
writes no shared data. The resulting byte count is returned as the `fcntl()`
return value. This isolates a very small mutex-protected metadata read.

Unlike `pipebytes`, increasing N does not add a buffer traversal to this critical
section. It changes the capacity value; the query remains a short protected read.
The client checks it against the actual capacity returned during setup.

### Shared file position: `seek`

This API changes the current offset associated with an open file description.
Threads sharing that description share its `f_pos`, so their position changes
must be serialized.

Setup creates a tmpfs file and calls `ftruncate(fd, N*4096)`. All workers share
one open file description and its `file.f_pos_lock`. Each operation chooses a
varying displacement `d` between 1 and 1,024 bytes:

- `set`: `lseek(fd, d, SEEK_SET)` returns `d`.
- `end`: `lseek(fd, -d, SEEK_END)` returns `N*4096 - d`.

**Matched critical section.** Native takes the original `file.f_pos_lock`;
TCLock and KD take their private adapter mutexes. Each protects the same steps:

1. Read the filesystem's maximum file size (`s_maxbytes`). For `SEEK_END`, also
   read the inode size with `i_size_read()` and add the requested displacement.
2. Reject a resulting offset below zero or above the maximum.
3. Compare the result with `file->f_pos`; if different, store the new position.
   Linux 7 has no `file->f_version` field; the old zeroing store belongs only
   to the preserved Linux 6.1 implementation and measurements.

The body performs a few metadata reads, checks and conditional shared stores.
N changes the file length and end-relative base. Neither variant traverses,
reads or writes file contents.

In the Linux 7 kernel path, `ksys_lseek()` uses `CLASS(fd_pos, f)` around
the llseek call, taking and releasing the position mutex for the shared description.
`shmem_file_llseek()` supplies `MAX_LFS_FILESIZE` and reads the inode size for
both supported modes; this tmpfs superblock sets `s_maxbytes` to that same limit.
The adapter uses `fdget()`/`fdput()`, the current `fd_empty()`/`fd_file()` accessors,
and performs the checks and stores above
under the selected lock, reading inode size only for `SEEK_END`.

### UTS names: `utsname`

These APIs read system-identification fields or change the hostname/UTS domain
name. A reader must see a complete name while another worker updates it.

Setup creates a private namespace with `unshare(CLONE_NEWUTS)` and initializes its
hostname and domain name. `host` selects hostname updates; `domain` selects UTS
domain-name updates. Both variants use `uname()` for their read operations.

Here N is the **write percentage**. Every worker interleaves setters and reads:
n20 means approximately one setter per five operations, while n100 means all
setters. The client accepts N from 1 to 100. This does not change the number of
namespaces or the string length; `value_size` must remain 64.

**Reader critical section.** `uname()` takes shared read access and copies the
entire `target_uts->name` (`struct new_utsname`) into a caller-local kernel
temporary with `memcpy()`. It then releases read access. `copy_to_user()` and
the client's result validation follow outside the lock. The protected body
reads the namespace fields and writes only the temporary copy.

**Writer critical section.** The selected setter takes exclusive write access,
copies exactly 64 bytes into `nodename` (`host`) or `domainname` (`domain`),
stores a terminating NUL, then releases write access. The other namespace fields
remain unchanged. The source name is already in a kernel temporary: privilege
checks, `copy_from_user()` and entropy mixing precede the protected update.

Stock uses the global `uts_sem`; matched Native uses a private rwsem, and matched
KD/TCLock use private reader/writer locks. Stock performs `uts_proc_notify()`
under the write lock; matched adapters perform it after unlocking. These scope
and notification differences are part of the comparison. N changes how often
the fixed-size exclusive copy interrupts shared readers.

### Extended attributes: `xattr`

This API retrieves a named metadata value attached to a file. The active Linux 7
tmpfs implementation stores these records in an rb-tree.

Setup attaches N `trusted.kdlock.*` attributes to an anonymous tmpfs file using
`fsetxattr(..., XATTR_CREATE)`. Each value contains `value_size` bytes.

#### Linux 7 rb-tree/shared-reader workload

Revision `xattr-rbtree-read-v1` preserves `simple_xattr_get()`'s `rb_find()`
lookup, `strcmp(node->name, key)` ordering, size result, `-ENODATA`/`-ERANGE`
behavior and real `memcpy()` value copy. Each matched Native, KD or TCLock arm
uses its own correctly typed private rwlock and holds shared read ownership
through search and copy. The original embedded Linux lock is not reinterpreted.
The bound private tmpfs file and its attributes remain fixed until all workers
join and the hook is removed; independent consumers and metadata writes are
outside this experiment.

`front` selects key N−1 and `tail` selects key 0, retaining the client labels.
These names no longer promise a head/tail location, exact comparison count or
tree depth. `miss` selects an absent key; `size` queries key 0 without a value
buffer. N changes tree size; `vN` changes value-copy work. No old N-comparison
or 128-call boundary interpretation applies to this workload.

All KD reads execute locally with `entry_abi=0`, `caller_shell=local_reader`,
zero JIT-eligible operations and expected `NO_JIT`. The runner still checks
entry/completion counters and refuses any JIT activity or publication. It
defaults `--helper-waves` to zero and rejects positive helper waves or
`--require-jit` for xattr. Shared-reader quiescence is required before unload.
The port's build/live status is recorded separately; old delegated-body results
are not passes for this new workload.

#### Historical Linux 6.1 list/spin workload

The remaining xattr description and numeric evidence in this subsection refer
to the retired list/spin implementation and its original source identities.

**Critical section.** `simple_xattr_get()` takes the exclusive spinlock
`simple_xattrs.lock` while it:

1. Traverses the attribute list, comparing each name with `strcmp()`.
2. Reads the matched attribute's size. With no output buffer, this size is the
   result; an undersized buffer produces `-ERANGE`.
3. Copies the value into the supplied kernel buffer with `memcpy()` when the
   buffer is large enough. A missing name produces `-ENODATA`.

The list and stored values remain unchanged; writes go to the query's result
buffer. Holding the spinlock across search and copy keeps the selected record
stable. Buffer allocation and the later copy to userspace are outside this
lock. The body combines pointer traversal, string comparisons and, for a
successful value query, a size-dependent copy.

- `front`: read the most recently inserted attribute, at the list head.
- `tail`: read the earliest inserted attribute, at the list tail.
- `miss`: query a name that was not installed; expect `ENODATA`.
- `size`: search for the tail attribute but pass `NULL, 0` to `fgetxattr()`,
  obtaining its length without copying the value.

N varies search-list length; `vN` varies value size and hence copy work for
successful value queries. These are independent dimensions. The current main
comparison uses tail queries at n16/n128 and v64: each operation searches the
list and copies the real 64-byte value. It is not the `size` query. A front hit
uses one `strcmp`; tail, miss and size queries use N comparisons. At n128, the
search reaches the allowance of 128 direct `strcmp` calls per generated
invocation. An additional comparison transfers the unexecuted call to the
original waiter, which finishes the native suffix under the existing lock.
The direct route cannot reenter to reset its quota. Other service/control
continuations use their own dispatcher route and allowance.

The separate n129 tail-query control passed at 16 workers with 64-byte values.
Of 329,728 correct measured operations, 329,228 entered generated code, reached
the 128-comparison limit and then completed the remaining original API calls on
the waiter. No complete generated body was recorded: this expected
`PARTIAL_JIT` result tests native continuation after earlier effects, not
full-body delegation or throughput. The session drained with exact source and
frame retirement. The [current report](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
keeps this unscored control separate from the n16/n128 matrix.

Version 11 passed all eight front/tail/miss/size controls at n16/n128,
v64 and 16 workers, with correct results and matching generated entries and
completed bodies. The original value-copy path remained present. These
[focused checks](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md)
establish correctness and actual delegation. The current
[`05876a4` comparison](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
completed the standard-grid tail-query measurements. The preceding
[`88bb5a4` comparison](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/README.md)
completed the standard-grid tail-query measurements for n16/n128. Front, miss
and size-only cases remain correctness controls, without their own throughput
matrix in either round.

The historical address-analysis refusal is retained in its source-specific
reports. Before the version 10 revision, candidate 11 passed all eight front/tail/miss/size
combinations at n16/n128, v64 and 16 workers, including the real `memcpy` path.
Each recorded matching generated entries and completed bodies, correct results
and clean teardown. Tail queries completed 133,378 bodies at n16 and 18,985 at
n128. These are [functional checks](../bench/results/10.176.26.71/bench/taskname-xattr-20261018/DEVELOPMENT.md),
not accepted throughput scores or validation of version 10.


## Sleeping rwsem and extracted proc snapshots

The [reader/writer runner](../bench/rwlock_compare/README.md) now also exposes
these explicit modes. They are separate lock/payload identities and are not
automatically added to an ordinary rwlock or full-catalog sweep.

| Mode | Payloads / backends | Execution contract |
| --- | --- | --- |
| `--lock-kind rwsem` | c01/c08 or RCUHT; `--backends native tclock kdlock` | Local readers and explicit writers that may delegate. KD blocks new readers and waits for existing readers before entering the unchanged mutex delegation queue. `--delegate off` selects a distinct ordinary-local KD control with zero JIT. TCLock uses the original rwsem and AQS reader gate; only ordinary read/write pairs are supported. |
| `--lock-kind spin --workloads argbounds` | Four-word argument-boundary snapshot; Native/TCLock/KD | Every snapshot takes an exclusive spinlock; KD may delegate reads. Controlled optional mutations use the same selected lock. |
| `--lock-kind spin --workloads taskname` | Exact `strscpy_pad()` copy from a 16-byte name field to a 64-byte padded buffer; Native/TCLock/KD | Read-only correctness, returned-body checks and the `05876a4` standard-grid comparison are complete. The preceding version's 20% mutation control passed correctness with zero KD generated bodies and does not supersede earlier strict delegation failures. Explicit `--delegate off` gives a separate KD local control. |

Snapshots use module-owned records, fixed lifetimes and worker-local kernel
outputs. They do not operate on live task/MM structures, invoke procfs, fetch
remote argument pages or time `ps`. `--write-percent 0` is read-only snapshot
traffic; a 20% mutation case alternates valid versions and checks the complete
tuple or padded name. Read operations remain exclusive spin acquisitions.
KD mutations use local execution through that same KD object; they do not
acquire a separate Linux Native lock.

Taskname's read-only state contains 15 equal letters and a terminating zero byte
inside its 16-byte source field. Mutations alternate three-letter and
fifteen-letter names and change the letter. After unlock, each reader verifies
the whole copied name and every zero-padding byte through the end of the
64-byte destination. This preserves the exact `strscpy_pad()` semantics;
substituting a different copy loop would define a different payload. The main
performance profile has no mutations; the 20% mutation profile is kept as a
separate correctness workload.

Snapshot preparation saves every published image and uses fully drained helper
learning waves. Readiness requires a complete returned body rather than just a
NORMAL image or entry witness. The benchmark-only provider counts entries and
matching completed bodies separately. Refusals and local controls remain
separate from actual delegated results.

The [rwsem design](design/rwsem_implementation.md) supports ordinary sleeping
read/write, trylocks, downgrade and interruptible/killable cancellation. Its
explicit outer writer pair can delegate permitted bodies through ABI2, the
existing mutex machine-level calling agreement. Each writer reserves permission
to enter, prevents new readers, and waits for existing readers while the scheduler
can still pause it. Only then can it publish a mutex request and become pinned
with preemption disabled. Ordinary writers hold an exclusive admission state,
so a writer-to-reader downgrade cannot introduce a reader after a delegated
writer has passed that wait. An outer writer keeps its reservation until its
original task receives the matching unlock acknowledgement (ACK); that pair
cannot downgrade or cancel after publication. Separate queues for those waiting
conditions and a limited number of checks before sleeping preserve the selected
KD mutex protocol. The
[scheduler probe](../tests/kernel/rwsem/README.md) exercises sleeping holders and
contenders sharing one CPU and checks pre-publication ordering across downgrade.
This object is not a replacement for the real `mmap_lock`. The
[branch review](history/feature-reintegration-20261018.md) explains why the
archived delegated rwsem could not be copied unchanged; the phase design
resolves those ordering hazards while preserving the selected mutex protocol.

The standard rwsem comparison uses c01, c08 and RCUHT, 1%/20% writes, three
two-second repetitions, and workers 1–8 by one then 12–60 by four. With Native
and KD this is 756 sessions. Use the [runner command](../bench/rwlock_compare/README.md)
and retain complete-body counts, NO_JIT controls, correctness, worker progress
and final drain. Admission and Linux rwsem fairness policies differ; the design
does not imply a throughput advantage.

The [accepted rwsem comparison](../bench/results/10.176.26.71/bench/rwsem-optimization-20261018/README.md)
records the `c21345b` implementation's measurements, smaller candidate comparisons,
separate baseline controls,
diagnostic profiles and actual execution groups. Its separate spinning-rwlock
reference selects Native/TCLock/KD on c01, c08 and RCUHT at 1%/20% writes and
1/8/32/36/60 workers, with three repetitions: 270 completed sessions. This reference
uses non-sleeping bodies and is not a TCLock rwsem implementation or a rwsem
parity result. The [focused validation](../bench/results/10.176.26.71/tests/rwsem-optimization-20261018/README.md)
records strict JIT checks, cancellation/downgrade ordering, ordinary local
controls and read-only cases. Neither report validates real MM or task-structure
integration.

The [initial writer-delegation comparison](../bench/results/10.176.26.71/bench/rwsem/20261018/README.md)
and its [validation receipt](../bench/results/10.176.26.71/tests/rwsem-delegation-20261018/README.md)
remain historical evidence for the shared-queue baseline, including its
high-count regressions, local fallback results and returned-body counts.

The [earlier 2026-10-18 validation](../bench/results/10.176.26.71/tests/feature-reintegration-20261018/README.md)
passed the prior ordinary-only rwsem scheduling and workload checks. Three default-policy timed
argbounds runs at eight workers returned complete delegated bodies; a shorter
16-worker acceptance attempt remained `NO_JIT`. Taskname's 16-worker preparation
exhausted its helper waves without a completed body; local controls passed.
These outcomes do not establish performance parity or full task/MM integration.

## Process inspection and mmap candidates

**Review, 2026-10-18:** process inspection reaches real task and memory locks,
but container count alone does not establish contention on any one lock. The
short `arg_lock` and task-name snapshots are restored extracted spin workloads.
Full procfs and mmap operations need Native scaling measurements first; the
selected KD provider cannot delegate these complete paths today. Explicit rwsem
writer delegation does not change that full-path boundary.

This review checked the current provider and the retained Linux 6.1.159 source
and procps-ng 3.3.17 traces. All 25 captured kernel/configuration files and the
three traces match their recorded hashes. The [source audit and offline recheck](../bench/results/10.176.26.71/tests/proc-mmap-audit-20261015/README.md)
record provenance and limits. No new live tracing or container experiment ran
for that source review; the separate feature validation above tests extracted
payloads and the explicit KD rwsem object. These are kernel-version-specific
findings; a different production kernel or `ps` version needs its own trace.

### Containers, processes and shared locks

There is no single lock protecting every field of every `task_struct`.
`task_lock(task)` acquires that task's `alloc_lock` for selected fields. Threads
normally share `mm_struct`, `signal_struct` and `sighand_struct`, while each has
its own task structure and `alloc_lock`. Independent processes normally have
separate address spaces and mmap locks, including processes in the same container.
Sharing a mapped file does not by itself make their `mm->mmap_lock` the same lock.

A host PID-namespace scan can see descendant-container processes, subject to
procfs visibility and access policy. A container's procfs normally exposes its
own PID namespace and descendants. Docker's
[PID namespace setting](https://docs.docker.com/reference/cli/docker/container/run/#pid)
can change that visibility, including use of the host namespace. Keep container
count, processes per container, threads per process and concurrent observers as
separate parameters. Here `ps` means the Linux process tool; `docker ps` is a
different container-listing operation.

More processes increase directory enumeration and procfs work. More threads in
one process increase whole-process accounting traversal; simultaneous observers
of the same process can share its signal/accounting locks. Mapping writers in
that process can delay mmap readers. Those are possible bottlenecks to measure,
not evidence that a slow host-wide scan is dominated by one lock.

The retained syscall traces establish the following paths for the audited `ps`:

| Command | Observed process files |
| --- | --- |
| `ps -e -o pid=,comm=` | `stat`, `status` |
| `ps -e -o pid=,args=` | `stat`, `status`, `cmdline` |
| `ps -eL -o pid=,tid=,comm=` | Process `stat`/`status`, `task` directory enumeration, per-thread `stat`/`status` |

None opened `maps` or `smaps`. Basic memory-counter helpers used by `stat`,
`statm` and `status` do not take mmap read ownership in this kernel.
`get_task_mm()` pins an MM reference under `task_lock()`; that is not an mmap
lock acquisition. Argument-displaying `ps` reaches the mmap lock through remote
`cmdline` page access. The kernel's [procfs guide](https://docs.kernel.org/6.1/filesystems/proc.html)
describes the interfaces and the more expensive page-table inspection in `smaps`.

### Task and process-inspection critical sections

Locations below refer to the hashed `kernel-inputs/` files in the source audit.
They identify relevant task/MM protection, not every VFS or security lock in a
complete syscall.

| Operation and source | Lock and protected work | Current KD delegation boundary |
| --- | --- | --- |
| `/proc` enumeration: `fs/proc/base.c:3536`, `next_tgid()` | RCU, PID lookup and task references; thread enumeration also uses RCU | No global `tasklist_lock` held across the scan; not a single lock-body benchmark |
| Name copy: `fs/exec.c:1219`, `__get_task_comm()` | Per-task `alloc_lock`; `strscpy_pad()` copies `comm` | Version 10 extracted read-only correctness and returned-body checks passed. Mutation correctness passed, but delegation remains unestablished and earlier strict failures remain recorded. Full procfs and live-task integration are unvalidated. |
| Task pointers/status: `kernel/fork.c:1388`, `get_task_mm()`; `fs/proc/array.c:170` | Per-task `alloc_lock`; MM reference or `fs`/`files` snapshot | Task references, surrounding RCU and mutable pointer lifetimes require a separate audit; not covered by a name-copy test |
| Signal snapshot: `fs/proc/array.c:275,505`; `kernel/signal.c:1389` | Shared `sighand->siglock` with IRQ saving and pointer revalidation; signal state, thread count and related fields | Explicit IRQ spin paths stay on the caller; no current delegated adapter |
| Whole-process statistics: `fs/proc/array.c:533`; `kernel/sched/cputime.c:308` | `signal->stats_lock` seqlock with normally lockless initial reads and RCU thread traversal; retry can take an IRQ-saving exclusive lock | Preserve seqlock/RCU semantics; cannot model the normal path as one exclusive delegated thread scan |
| CPU-time adjustment: `kernel/sched/cputime.c:554,644` | Raw IRQ-saving `signal->prev_cputime.lock`, or per-task equivalent; keeps reported CPU times monotonic | Caller-context accounting, separate from the long traversal; no current delegation |
| Command-line boundaries: `fs/proc/base.c:301` | Ordinary exclusive `mm->arg_lock`; load `arg_start`, `arg_end`, `env_start`, `env_end` | Best extracted KD spin candidate; argument bytes and mmap operations are outside this section |
| Command-line bytes: `fs/proc/base.c:336,358` → `mm/memory.c:5700` | Target mmap read lock with killable acquisition; VMA/page lookup, possible faults and remote copy | Sleeping rwsem and MM-context work; unsupported as a complete KD body |

The long statistics traversal in this 6.1.159 source already uses `stats_lock`,
rather than holding `sighand->siglock` throughout as older code did. Its initial
sequence read is lockless; exit and child-reaping writers can invalidate it and
force retries. Read-only observers do not themselves change the sequence. A
benchmark must retain this distinction when assessing many-thread processes.
The captured x86-64 tick-accounting configuration also uses the plain runtime
load in `read_sum_exec_runtime()`, not its 32-bit runqueue-lock fallback.

Global `tasklist_lock` still matters for fork, exit, reparenting and wait/reaping
paths, including IRQ-disabled write acquisitions (`kernel/fork.c:2476`,
`kernel/exit.c:252`). A creation/exit storm deserves its own workload; ordinary
procfs enumeration is not evidence of that global lock being the bottleneck.

### mmap critical-section boundaries

The source references below describe the retained native kernel. The current
[experimental mmap adapter](../kernel_integration/mmap_lock/README.md) changes
only lock implementation and minimal API/lifetime wrappers. The
[bounded shared-mm comparison](../bench/mmap_lock/README.md) is the active
performance plan. Operation-specific MM-body delegation and prepared teardown
campaigns are retired; the proposals below are historical context where they
depend on those mechanisms.

`include/linux/mm_types.h:597` declares `mmap_lock` as `struct rw_semaphore`.
It protects VMA layout and related MM operations. Page tables and reverse
mappings have additional locks; mmap ownership does not protect every task field.

| Entry / source | Acquisition and protected work |
| --- | --- |
| `mmap()` → `vm_mmap_pgoff()`, `mm/util.c:507` | Write-killable lock around `do_mmap()`: validate/select addresses, create/merge VMAs, update Maple Tree and accounting; allocation and filesystem/security callbacks can occur. Optional population follows unlock. |
| `munmap()` → `__vm_munmap()`, `mm/mmap.c:2926` | Write-killable lock for VMA removal; `do_mas_align_munmap()` can downgrade before unmapping pages, freeing page tables and completing TLB work. Release mode depends on the path. |
| `mprotect()`, `mm/mprotect.c:702`; `mremap()`, `mm/mremap.c:943`; `brk()`, `mm/mmap.c:181` | Write-killable acquisition around validation and VMA changes, with path-dependent splitting/merging, allocation, page-table and TLB work |
| `/proc/PID/maps`, `fs/proc/task_mmu.c:141,186` | `m_start()` takes a killable read lock and `m_stop()` releases it; VMA traversal and record formatting span a seq-file batch, not necessarily the whole file |
| `/proc/PID/smaps`, `fs/proc/task_mmu.c:613`; `smaps_rollup`, `:877` | Mmap read ownership plus nested page-table locks; collect resident/PSS statistics and allow rescheduling. Rollup explicitly drops/reacquires mmap ownership when contended. |
| `cmdline` → `__access_remote_vm()`, `mm/memory.c:5700` | Read-killable acquisition; VMA lookup, possible stack expansion, page acquisition and remote copy. The later `copy_to_user()` to the observer is outside this helper's mmap lock. |
| User faults, `arch/x86/mm/fault.c:1312` | Mmap read ownership for VMA/fault work, with retry and stack-growth paths requiring explicit lock-state handling |

Opening `maps`/`smaps` also uses `mm_access()` (`kernel/fork.c:1405`), which
takes the separate `signal->exec_update_lock` rwsem around MM acquisition and
access checks. This is distinct from the mmap read batches and from the plain
`cmdline` path's `get_task_mm()`.

### What would be required for delegation

Replacing every Linux **mutex** with KD mutex does not replace `alloc_lock`,
`siglock`, raw spinlocks, seqlocks or the **rwsem** `mmap_lock`. The current
[mutex aliases](../include/kd_mutex_compat.h) operate on rebuilt KD mutex objects;
direct blocking calls use the unified ABI2 interface and permit JIT. Callable
lock symbols and signal/try/I/O acquisitions remain local, with public unlock
retaining exact ownership routing.
The closest APIs for real-object conversion are listed below. General procfs
conversion remains unimplemented. The separate experimental mmap adapter now
supplies local reader/writer wrappers with focused validation; it does not
delegate native MM bodies. A killable
wait can return without acquiring the lock when a fatal signal is pending;
downgrade changes exclusive write ownership into shared read ownership.

| Actual kernel section | Closest KD API | Remaining boundary |
| --- | --- | --- |
| Plain `mm->arg_lock` and `task->alloc_lock` sections | `KD_SPIN_DIRECT_LOCK` / `KD_SPIN_DIRECT_UNLOCK` on a converted object | The extracted four-word body can delegate. Version 10 extracted name-copy correctness and returned-body checks passed. Live pointer/reference snapshots need their own lifetime and compiled-body review. All real-object consumers still need conversion. |
| `sighand->siglock` with interrupt-state saving | `kd_spin_lock_irqsave` / `kd_spin_unlock_irqrestore` | Local KD execution only; interrupt state belongs to the caller. The surrounding pointer revalidation and all signal-side consumers must be preserved. |
| Mmap readers and `exec_update_lock` readers | `kd_down_read_killable` / `kd_up_read`, with the appropriate trylock/retry handling | Local shared access only. The mmap adapter has focused wrapper tests; `exec_update_lock` conversion and full Native equivalence are unvalidated. |
| Mmap writers | `kd_down_write_killable` / `kd_up_write`, with `kd_downgrade_write` where required | These are local operations. The delegating outer pair waits uninterruptibly and cannot downgrade; it cannot replace the current mmap acquisition/release paths. |
| Sequence-lock statistics, raw accounting locks and interrupt-disabled task-list writers | No complete interchangeable KD API | Preserve sequence retries, read-copy-update (RCU) traversal, raw-lock rules and interrupt state. An ordinary exclusive delegated body is not equivalent. |

The retained `include/linux/mmap_lock.h` additionally uses nested lock-dependency
annotations, `mmap_read_unlock_non_owner()`, `rwsem_is_locked()` and
`rwsem_is_contended()`. KD rwsem has no corresponding complete interfaces.
Non-owner unlock permits a read acquisition to be released by a different task;
contention checks let `smaps_rollup` decide when to drop and reacquire read ownership.
`kd_rwsem_is_idle()` is an inspection helper after all users stop, not a
replacement for a live contention query. Providing ordinary killable lock APIs
therefore does not make even a fully local mmap conversion complete.

The following requirements still apply under the KD-only mutex assumption:

- **Matching lock semantics.** Current [KD rwlock](../include/kd_rwlock.h)
  disables preemption, requires non-sleeping bodies and delegates only writers;
  readers execute locally. It is not a sleeping rwsem. Mmap uses concurrent
  readers, killable waits, trylocks, downgrade and release/reacquire paths.
  KD mutex is exclusive and does not provide that contract. KD rwsem supplies
  the ordinary sleeping APIs and a distinct delegated outer writer pair. Its
  phase admission drains readers before acquire-time combining can run, and
  excludes ordinary downgrade until all outer reservations retire. The outer
  pair itself cannot downgrade or cancel after publication. These APIs do not
  establish real mmap-lock replacement or arbitrary MM-body delegation.
- **All consumers and lifetime.** A private KD lock around proc readers cannot
  exclude native mapping writers, faults, exec or exit. All accesses must use
  one protocol, including implicit kernel users. Task/MM references keep
  allocations alive but do not freeze fields or thread membership. Permission
  checks, exit/exec handling and nested lock ordering remain required.
- **Execution context.** A KD mutex executor can sleep, so sleep alone is not
  a universal prohibition. However, full MM bodies include faults, allocation,
  callbacks, nested locks, MMU notifications and TLB operations. Logical
  `current` handling does not switch the hardware address space or reproduce
  arbitrary credentials, CPU, IRQ, RCU or scheduler context. The
  [context admission rules](../disassem/context_symbols.py) refuse many of these
  operations; an admitted bounded copy is not evidence for a complete MM path.
- **IRQ and accounting semantics.** [Explicit IRQ/BH spin interfaces](../include/kd_spin_direct.h)
  execute locally. Moving `siglock`, the stats fallback or raw accounting
  sections would need a new audited context contract. Current KD rwlock also
  lacks the IRQ variants needed for `tasklist_lock` writers.

### Candidate workload plan

The extracted snapshots below map to restored runner modes; the full procfs,
mmap and lifecycle labels remain proposals, not accepted runner options. None
is automatically added to the default full-catalog sweep. Native screening
identifies the expensive shared object before a real-object adapter is designed.

| Proposed case | Measured operation and controls | Feasibility |
| --- | --- | --- |
| `proc-arg-bounds` | Copy four words under one module-owned exclusive spinlock into stable worker-local kernel storage; optionally alternate valid tuples under the same lock. Distinct-record control remains an extension. | Implemented as `--lock-kind spin --workloads argbounds`; require fresh returned-body evidence for current delegation claims. |
| `proc-comm-snapshot` | Exact `strscpy_pad()` name copy, 16-byte source and 64-byte padded destination, with separately labelled mutations; distinct-record control remains an extension | Implemented as `--lock-kind spin --workloads taskname`, including KD local control. Read-only correctness, returned-body checks and the `05876a4` standard-grid comparison are complete. The preceding version's mutation correctness control passed with zero KD generated bodies; earlier strict delegation failures remain recorded. A different copy loop is a different payload. |
| `proc-stat` / `proc-status` | Independent observers read the same large thread group versus distinct groups; idle, CPU-active and exit/reaping variants kept separate | Native-only candidates requiring implementation; preserve actual seqlock/RCU/IRQ paths. No full-path KD adapter. |
| `proc-cmdline-mmap` | Read stable arguments while target threads map/unmap disjoint scratch regions in that same MM. Include a no-writer control; vary argument length and VMA count. | Native mmap-contention candidate; no full mmap adapter for KD or TCLock. The synthetic KD rwsem comparison does not implement this path. |
| `proc-maps` / `proc-smaps` | Complete proc-file reads while a target changes separate mappings; vary actual VMA count and resident bytes independently | Native workloads; distinguish VMA formatting from page-table accounting and preserve allowed concurrent-update semantics |
| `mmap-churn` | Target threads perform matched map/unmap cycles or separately labelled protection changes; compare shared MM with independent processes and with/without observers | Native writer control; record map/unmap latency separately as well as cycle throughput. Full MM delegation unsupported. |
| `task-lifecycle` | Controlled process/thread creation, exit and reaping with/without proc observers | Native control for global task-list and statistics writers; no current KD IRQ-rwlock adapter |

The [historical proc snapshot report](../bench/results/10.176.26.71/bench/proc_snapshots/20261015/README.md)
records 93,229,983 complete delegated argument-boundary bodies across its timed
comparison. That is proof of feasibility for that frozen extracted spin workload,
not a current-version performance result or an end-to-end `ps` improvement.
In that historical version, the exact task-name helper was refused because
`strscpy_pad+0x8` saved uncaptured R13 under spin ABI1. Its KD timings used
explicit local execution. Image publication and an entry witness did not
establish a complete delegated body. Later API-service implementations are
distinct source versions and do not retroactively change those outcomes. The
preceding version 10 removed helper-specific checks. Its focused correctness and
read-only delegation checks passed, and the
[`88bb5a4` comparison](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/README.md)
records its completed extracted-taskname and xattr tail-query matrix. The current
version 11 calls the original helpers directly inside generated code; its
[`05876a4` comparison](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
also completed those three cases. Neither round measures full procfs or
end-to-end `ps` performance.

For a future round, use the standard 1–8 and 12–60-by-four observer/worker grid
and three repetitions, keeping target population independent of worker count:

1. Compare one shared process/MM with the same total target tasks spread across
   independent processes. Vary containers/PID namespaces separately, recording
   procfs policy, kernel/procps versions, CPU placement and runnable population.
   Large sleeping target populations need not imply oversubscribed KD workers;
   arbitrary KD producer oversubscription remains unvalidated.
2. Vary observer and mapping-writer counts independently. Keep idle, CPU-active,
   mapping and lifecycle churn as separate cases. Record actual VMA count to
   catch automatic merging, mapped/resident bytes, and argument bytes.
3. Give each proc observer an independent open file description. Define one
   operation as a complete read from offset zero; state whether open/close or
   rewind is timed. Shared descriptions can add seq-file/file-position
   serialization. An end-to-end `ps` run additionally times userspace parsing,
   selection and formatting; report it separately from proc-file reads.
4. Record whole-scan latency, reads/second, p50/p95/p99 latency, CPU time,
   errors and target progress. Use separate profiling runs to attribute wait
   and hold intervals to a specific lock address/MM and call stack. High CPU
   traversal cost alone is not evidence of lock contention.
5. For extracted comparisons, require identical bodies, one protocol for all
   accesses, exact tuple/name validation, actual returned JIT-body counts,
   per-worker progress and complete drain. Keep refused/local controls separate
   from delegated results. Procfs lifecycle tests must handle expected exit
   races; maps/smaps across multiple reads are not one atomic snapshot.

The captured kernel has mmap start/acquired/released tracepoints but
`CONFIG_LOCK_STAT` is disabled. Pair events by task and MM, track failed
killable/trylock attempts and explicit drop/reacquire paths. Downgrade emits a
successful read-acquired event without a new start or write-release event, so
it needs an explicit write-to-read transition. Release events precede physical
unlock; account for that measurement boundary, non-owner releases and lost
events. Keep probe overhead out of the throughput comparison.

## Scope and evidence

The API adapter substitutes only selected functions on controlled objects. KD
mutex uses a private KD object and never casts or falls back to the embedded
Linux mutex. This tests scoped behavior, not a rebuilt kernel where every mutex
has been replaced. See the [API contract](../bench/real_api/README.md#contract-and-comparison-limits)
and [KD-only assumptions](design/kd_only_mutex.md).

The full process/mmap proposals are grounded in retained source and trace
evidence. The extracted snapshots and phase-admitted rwsem have their
own runner contracts. Historical snapshot delegation does not validate current
performance, live task/MM replacement or a large-container deployment. Full
procfs/mmap candidates still need implementation and fresh VM validation.

The separate [opt-in mapping payload](design/mmap_fault.md) now supplies real
module-owned VMA callbacks and controlled fault-in transactions, validated with
Native/KD/TCLock private backing locks. It leaves `mm_struct::mmap_lock` native.
Its [focused runner](../tests/kernel/mmap_fault/README.md) checks correctness.
The separate [split workloads](../bench/mmap_fault/README.md) now measure
Native mmap/munmap without touching the range and real CPU fault cycles through
Native/KD/TCLock local backing readers. VMAs are created before fault timing;
fault-cycle latency includes PTE discard and the checked read. Readers stay
concurrent, and no artificial writer work is added to force delegation. Native
mmap locking remains unchanged, so there are no KD/TCLock mmap replacement arms.
Unsupported TCLock combined bodies are excluded. These workloads do not implement
the full procfs/mmap proposals; the [48-session receipt](../bench/results/10.176.26.71/tests/mmap-fault-split-20261021/README.md)
retains variance and a failed strict host endpoint without performance acceptance.

The distinct [Native shared-mm writer workload](../bench/mmap_writer/README.md)
now uses pthreads on one exact mm and its real mmap lock. Each cycle maps and
unmaps an untouched page; zero fault callbacks are mandatory. Correctness also
checks actual blocked-writer call sites, foreign-mm rejection, VMA splitting,
closed-descriptor lifetimes and exit teardown. Timing excludes the stack probe,
uses native mmap ownership throughout, and retains complete-cycle latency and
per-thread CPU time. Its [twelve-session receipt](../bench/results/10.176.26.71/tests/mmap-writer-native-20261021/README.md)
retains both failed probe attempts, repetition variance and the 76-versus-67
host endpoint failure. That original runner provides no KD or TCLock full-mmap
arm; the separate fault task keeps local readers concurrent. The current kdmm31
wrapper supplies a separately checked Native/KD mode for the same shared-mm
workload; no TCLock mmap arm exists. Its stopped plain/sampled plan kept
complete-cycle latency distinct from separate mmap/munmap latencies. Current
work is [throughput only](THROUGHPUT_PLAN.md); those historical samples remain
preserved. The private backing-lock fault timing above does not measure a
replacement of the real mmap lock, and the actual fault correctness drivers
are not yet a generic actual page-fault throughput harness.
