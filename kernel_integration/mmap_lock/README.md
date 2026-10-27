# mmap lock backend and API integration

This integration is stage 2 of the [project roadmap](../../docs/ROADMAP.md):
demonstrate improvement or parity for scoped real mmap/page-fault work before
broader kernel lock replacement. The next application-matching target is
will-it-scale `mmap1_threads`, with `mmap1_processes` as a separate control. The
existing 4 KiB device mapping and private-backing fault tests retain their own
identities; they are not measurements of mmap1. Stage 2's performance gate is open.

Linux 6.1 development and its MM kernel variants are retired. This source and
its results remain references for adaptation to the active Ubuntu 26.04 /
Linux 7.0 platform. OS readiness is recorded in the
[migration record](../../docs/history/vm-ubuntu2604-migration-20261027.md); KD and
MM compatibility remain unvalidated. The [retirement record](../../docs/history/kernel-retirement-20261027.md)
preserves one complete legacy recovery version. Commands requiring `kdmm1`,
`kdmm31` or `kdclobber2` describe archived workflows and do not authorize more
Linux 6.1 adaptation.

The maintained scope is **lock implementation plus minimal API and lifetime
wrappers**. Native mmap, munmap, advice and page-fault algorithms remain unchanged
and execute on the originating task. Readers stay concurrent and local. The
operation-specific body-delegation experiments are retired, including their
prepared VMA splits, page classification/ownership and table-retention machinery.

The retained integration uses the local-reader/local-writer adapter restored from
`b8b31a7b2f895b18226538b8a409331623b4ddc7`, with the shared rwsem's IRQ-safe read
trylock/rollback/release correction described below. This is an experimental
adapter, not a validated whole-kernel
replacement or a claim that every Linux rwsem semantic has been established.

## Retained components

| Component | Purpose |
| --- | --- |
| `include/kd_mutex*.h`, `include/kd_rwsem*.h`, corresponding `kernel_module/` implementations | Existing KD physical exclusion, public API, ownership and retirement protocols |
| `overlay/kernel/locking/kd_mmap/adapter.c` | Maps mmap read/write, trylock, killable, nested-write, downgrade and non-owner-release interfaces to one immutable backend per mm |
| `overlay/kernel/locking/kd_mmap/pool.c` | Preallocated CPU/slot records and exact local queue retirement |
| `overlay/include/linux/kd_mmap_lock*.h` and `prepare.py` | Local adapter types, declarations and namespaced reuse of the maintained lock primitives |
| `guest-kernel.patch` | Lock field, wrapper routing, initialization/destruction, build configuration and asynchronous read-unlock lifetime transfer only |

The patch touches nine files: `include/linux/{mm_types,mmap_lock}.h`,
`include/linux/sched/mm.h`, `kernel/bpf/{mmap_unlock_work.h,task_iter.c}`,
`kernel/fork.c`, `kernel/locking/Makefile`, `mm/Kconfig` and `mm/mmap_lock.c`.
It does not patch `mm/mmap.c`, `mm/memory.c`, `mm/madvise.c`, `mm/rmap.c` or
`lib/maple_tree.c`.

The BPF asynchronous release wrapper transfers an already acquired read share
through an exact token and holds an mm reference until completion. That lifetime
adaptation remains necessary; a reader count alone cannot authorize a transferred
unlock. It does not change a mapping algorithm or delegate a critical-section body.
`init_mm` stays Native, and a dynamic mm chooses Native or KD once before publication.
All users of each lock follow that choice. KD readers and writers execute locally.

## Public read/write API and atomic read trylock

Use `include/kd_rwsem.h` and `struct kd_rwsem` for the shared sleeping read/write
family: `kd_rwsem_init`, `kd_down_read` / `kd_up_read`, `kd_down_write` /
`kd_up_write`, `kd_down_read_trylock`, `kd_down_write_trylock`, the existing
`_interruptible` / `_killable` acquisitions and `kd_downgrade_write`.
`include/kd_rwsem_types.h` provides `DEFINE_KD_RWSEM` and `KD_RWSEM_INITIALIZER`.
This preserves concurrent readers; the exclusive `kd_mutex_api.h` family cannot
replace a read/write semaphore's semantics.

Linux MM callers retain the existing `mmap_*` interfaces in
`include/linux/mmap_lock.h`. The patch routes these through the declarations in
`overlay/include/linux/kd_mmap_lock.h`, using `struct kd_mmap_lock` and its immutable
backend selection. `prepare.py` namespaces the shared primitives, for example
`kd_down_read_trylock` becomes `kd_mmap_down_read_trylock` on
`struct kd_mmap_rwsem`. No new or implicit delegation interface is needed.

`kd_mutex_local_lock` / `kd_mutex_local_unlock` inside `kd_rwsem.c` implement
physical writer ownership behind that public family. Calling those functions
directly on the embedded gate would bypass reader admission/drain and is invalid.
Likewise, a caller selecting local mutex entry directly bypasses the source-level
ABI2 facade. Public mutex unlock retains its provider routing; rwsem ordinary and
outer acquisitions retain their distinct matching release protocols.
`KD_RWSEM_OUTER_WRITE_LOCK` / `KD_RWSEM_OUTER_WRITE_UNLOCK` in
`include/kd_rwsem_direct.h` explicitly opt eligible writers into delegation. They
retain the originating task's phase reservation until the matching mutex
unlock/ACK completes. They cannot downgrade, cancel after publication or nest
inside another translated body. They do not transfer native MM bodies' task
context. The mmap adapter uses ordinary acquisitions so every native MM body
remains on its originating task.

KD read trylock now accepts IRQ-disabled callers. Its fixed sequence is an
admission check, ordered reader increment, admission recheck and, on collision,
ordered rollback. Atomic rollback and matching read unlock never enter waitqueue
or scheduler locks, allocate, schedule, change IRQ/preemption state or leave a
deferred pointer. Writers use one-jiffy timed reader-drain rechecks, including
interruptible, killable and unpublished outer reservations. A timeout never
grants ownership: the acquire-ordered zero-reader predicate must succeed.
Task-context release still wakes the reader-drain queue immediately. The existing
BPF token/mm-reference transfer remains intact; Native release under an rq lock
still requires its asynchronous release wrapper.

This adds timer wakeups during a prolonged reader drain and can delay observation
of an atomic final release until the next recheck. With the validated `HZ=250`,
one jiffy is 4 ms; scheduling can add delay. No new performance result is claimed.
The mmap/munmap killable writer path bypasses the 16,384-probe polling macro used
by ordinary uninterruptible acquisitions. Changing that polling budget would
not directly tune these syscalls' killable admission or reader-drain waits.
See the [focused correction receipt](../../bench/results/10.176.26.71/tests/mmap-irq-trylock-20261025/README.md)
for checks and limits.

| Interface or semantic | Current scope |
| --- | --- |
| Concurrent readers, exclusive local writers, signal cancellation and downgrade | Implemented; the focused standalone and actual-mm probes exercise selected ordering, exclusion, cancellation and lifetime cases. |
| Read trylock and matching read release with IRQs or preemption disabled | Supported by the corrected shared API and tested in the documented contexts; sleeping acquisitions remain task-context operations. |
| BPF asynchronous read-share transfer | The wrapper requires the exact acquired-share token and retained mm reference; an observed reader count does not authorize release. |
| Explicit writer delegation | Separate opt-in interface with the restrictions above; native MM body delegation is outside the maintained scope. |
| Native fairness/handoff behavior, all callbacks, RT and lockdep semantics | Equivalence is unvalidated. Nested wrapper names and passing focused probes do not establish it. |

## Why native bodies stay on their caller

Changing a lock interface does not transfer `current`, allocation policy, memory
charging, task-local accounting, callback context or fault retry state to a
combiner. Native splitting and unmapping can allocate mapping-index and reverse-map
metadata; fault processing also has caller-dependent allocation and accounting.
The retired design changed those bodies to prepare resources or route selected
operations. Those changes exceed the lock-only scope.

A context-independent critical section may use the existing KD delegation
protocol when its ordinary admission requirements are satisfied. This adapter
makes no such claim for arbitrary native MM operations: it retains their original
execution context and algorithms. There is no operation-specific remote MM body,
second fault service gate, or per-mm advice/unmap opt-in in the active implementation.

## Validation and commands

The [archived Linux 6.1 scope-check procedure](https://github.com/hailongeric/kdlock/blob/cd6f1061ea1b3686dd6d43a7a180ab1942ea4e57/kernel_integration/mmap_lock/README.md#validation-and-commands)
retains the exact source/baseline paths and former Python environment. It compiled
five local lock objects, checked the nine-file wrapper patch and unchanged native
MM hashes, and ran two basic programs plus the unified mutex API driver. It did
not load the new objects or establish actual-MM runtime behavior.

The active Ubuntu 26.04 / Linux 7.0 environment requires new source/configuration
selection and KD/MM adaptation before those checks can establish compatibility.
All future compilation and tests remain confined to the designated VM; the
source host performs edits and static review. No further Linux 6.1 adaptation
is scheduled.

The separate [disabled-configuration check](../../bench/results/10.176.26.71/tests/mmap-disabled-build-20261025/README.md)
compiles the four affected native interface objects and compares real-header
fixtures with `CONFIG_KD_MMAP_LOCK` unset. Native wrapper code, layout and
initialization match; partial links resolve the added lifetime helpers without
KD service dependencies. Its runner is `tests/kernel/mmap_lock/disabled/run.py`.
This establishes affected-object compatibility, not a full disabled kernel build
or runtime validation.

The original actual-mm lock API probe, mapping/fault checks, completed page-fault
probe and lock phase controls remain in `tests/kernel/mmap_lock/`. Their live
integration runs require a separately verified lock-only kernel and explicit
kernel authorization; a matching release prefix alone is insufficient. The
[original local integration evidence](../../bench/results/10.176.26.71/tests/mmap-kd-kernel-20261021/README.md)
is retained without repeating its campaign. The
[runtime reconciliation](../../bench/results/10.176.26.71/tests/lock-only-reconcile-20261025/README.md)
verified the restored inputs and prepared outputs against the preserved kdmm1
image, configuration, compiler record, modules and initramfs. Its eight focused
Native/KD runtime results remain evidence for that restored baseline. The IRQ
correction changes shared lock/adapter inputs; kdmm1 still contains the old guard
and is not runtime evidence for the corrected path. The subsequent
[kdmm31 correction validation](../../bench/results/10.176.26.71/tests/mmap-irq-trylock-20261025/README.md)
passed 137 Native and 161 KD assertions on actual mm objects, using the same
verified kernel image and prebuilt probe. Both modes drained and unloaded normally;
recovery was restored. The runner's `--reuse-probe` option requires exact payload
source, ELF, kernel and live BTF bindings and records that basic/build checks were
reused. The separate standalone adapter probe passed 352 assertions, and the two
basic programs passed before those actual-mm runs. Reuse does not count these
checks as newly executed.

The subsequent [one-attempt provider diagnostic](../../bench/results/10.176.26.71/bench/mmap-perf-prep-20261025/README.md#retained-validation-and-artifacts)
successfully initialized the unchanged provider, checked its capabilities,
retired it with zero remaining modules/frames/writers and unloaded normally.
Exactly one load was attempted; no workload or JIT body executed. The earlier
7,592-byte reserved per-CPU allocation failure remains unexplained, and full
shared-provider workload coverage remains open.

RT, lockdep, whole-kernel substitution
and broader Linux semantic equivalence remain unvalidated. The next performance
work follows the [throughput campaign plan](../../docs/THROUGHPUT_PLAN.md);
the old `kdmm1` timing profile cannot establish performance of this correction.
The earlier plain/sampled proposal selected 24 shared-mm writer cases over five
candidate boots followed by recovery. Its authorized October 25 attempt
[stopped before boot](../../bench/results/10.176.26.71/bench/mmap-kdmm31-paired-20261025/README.md)
at 73 QEMU tasks versus 67. All 24 measured cases in that proposal remain unrun;
that attempt supplies no timing or performance gain. The explicit 12-case `plain-v1` runner/report mode
passed 25 focused mocked checks; its [authorized live attempt](../../bench/results/10.176.26.71/bench/mmap-plain-v1-20261025/README.md)
then stopped at 68 QEMU tasks versus 67 before any boot or payload check. All
twelve measurements remain unrun. The stopped older plan is not resumed by
omitting sampled cases.
The separate prospective `plain-scaling-v1` plan now prepares 21 counts and
126 plain Native/KD sessions, with [41 focused mocked passes](../../bench/results/10.176.26.71/tests/mmap-scaling-plan-20261026/README.md).
All cases in that three-repeat matrix remain unrun. The separate
[qualified validation pair](../../bench/results/10.176.26.71/bench/mmap-worker-screen-20261026/README.md)
and [completed exploratory screen](../../bench/results/10.176.26.71/bench/catalog-mmap-single-20261026/README.md)
retain their own evidence; neither establishes a current repeated gain/parity
baseline or exact mmap1 performance. Mock validation and the separate QEMU
diagnostic do not replace actual mmap runtime validation or original admission.

## Reusing the corrected build

This section preserves the historical reconstruction procedure. At the correction
checkpoint, the installed `kdmm31` build/source links named a temporary tree
removed by the completed reboot. The retained `candidate-1/runtime-identity` directory supports
identity verification, but is not a complete external-module build tree. Do not
point Kbuild at it or silently build against recovery/kdmm1 headers.

The historical reconstruction used a new private tree from the unchanged kdmm1
base and authenticated `kdmm31-delta.tar.gz`, using `new-volatile.json` to verify
the base, the 779 changed
entries and the full result. The two recorded removed `.fixdep.o.d` files must
be absent from the reconstructed tree; preserve displaced copies outside it.
Then apply the preserved post-install `modules.order` delta. Verify source,
configuration, ELF, generated build inputs and module CRC/BTF bindings before
building a new payload. Reconstruction does not require a kernel rebuild,
installation, boot-link change or deletion of retained evidence. Exact artifact
hashes remain in the [correction receipt](../../bench/results/10.176.26.71/tests/mmap-irq-trylock-20261025/README.md#preservation-and-final-state).

The [current preparation receipt](../../bench/results/10.176.26.71/bench/mmap-perf-prep-20261025/README.md)
records a completed private reconstruction and successful `build-3` of the
unchanged writer payload and clients. All 16 imported symbol CRCs matched;
the exact base and split BTF parsed with the existing pahole 1.25. This work
loaded no module and did not compile, install or boot a kernel. Earlier parser
failures remain failed attempts. Current tooling passed 30 mocked cases
(16 capture and 14 paired/report), including the latest four review fixes;
the two earlier basic programs also passed. Build and mock results do not replace both-mode live payload
validation or qualify timings. Use the linked benchmark guide for current
commands rather than replaying historical kernel-build instructions.

## Retired experiments and provenance

The complete body-delegation implementation and removed probes remain reachable
in Git through archive branch `codex/archive-mm-body-20261024` at
`806e9a855b97ded9c25a44d3e4b12e14c49b0c55`, including the previous
validated kdmm29 milestones. The `mm-*` result records preserve their numeric
evidence, failures, kernel identities and raw references, with explicit retirement
notices. Their deleted build/probe commands are historical, not current instructions.

The attempted kdmm30 extension was stopped after installation but before any
candidate boot or live MM case. Its two basic tests passed; the extension was
never functionally validated. Recovery remained running and verified. See the
[stop record](../../bench/results/10.176.26.71/tests/mm-boundary-interior-private-20261024/README.md)
and [scope cleanup](../../bench/results/10.176.26.71/tests/lock-only-mm-cleanup-20261024/README.md).
Non-Git artifacts and installed experimental kernels are retained pending explicit
cleanup approval. No historical evidence or recovery artifact is deleted by this
source cleanup.
