# mmap lock backend and API integration

The maintained scope is **lock implementation plus minimal API and lifetime
wrappers**. Native mmap, munmap, advice and page-fault algorithms remain unchanged
and execute on the originating task. Readers stay concurrent and local. The
operation-specific body-delegation experiments are retired, including their
prepared VMA splits, page classification/ownership and table-retention machinery.

The active integration uses the local-reader/local-writer adapter restored from
`b8b31a7b2f895b18226538b8a409331623b4ddc7`, with the shared rwsem's IRQ-safe read
trylock/rollback/release correction described below. This is an experimental
adapter, not a validated whole-kernel
replacement or a claim that every Linux mutex semantic has been established.

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
do not transfer native MM bodies' task context. The mmap adapter uses ordinary
acquisitions so every native MM body remains on its originating task.

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
See the [focused correction receipt](../../bench/results/10.176.26.71/tests/mmap-irq-trylock-20261025/README.md)
for checks and limits.

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

All compilation and tests run in the existing VM at `10.176.26.71`, serially.
The source host performs edits and static review. Preserve the recovery kernel
`6.1.159-kdclobber2`; no kernel image build, installation or boot is needed for the
following check after an approved idle source synchronization:

```sh
# In the guest, using a fresh evidence directory:
cd /root/host_fs/kdlock
/root/kdlock-translation-venv-20261019/bin/python3 \
  tests/kernel/mmap_lock/scope.py \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/10.176.26.71/tests/lock-only-mm-cleanup-20261024/check-1
```

This checks the nine-file wrapper patch on copies, generates and compiles only
the five local lock objects, checks unchanged native MM source hashes, and runs
the two basic programs plus the existing unified mutex API driver. It does not
load the new objects or validate actual-mm runtime behavior on the recovery kernel.

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
reused. It does not rerun those checks or count them as newly executed.
RT, lockdep, whole-kernel substitution
and broader Linux semantic equivalence remain unvalidated. Performance work is deferred.

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
