# mmap lock backend and API integration

The maintained scope is **lock implementation plus minimal API and lifetime
wrappers**. Native mmap, munmap, advice and page-fault algorithms remain unchanged
and execute on the originating task. Readers stay concurrent and local. The
operation-specific body-delegation experiments are retired, including their
prepared VMA splits, page classification/ownership and table-retention machinery.

The active integration restores the local-reader/local-writer adapter from
`b8b31a7b2f895b18226538b8a409331623b4ddc7`. The shared KD mutex/rwsem implementation
is preserved. This is an experimental adapter, not a validated whole-kernel
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

The original actual-mm lock API probe, mapping/fault checks, completed page-fault
probe and lock phase controls remain in `tests/kernel/mmap_lock/`. Their live
integration runs require a separately verified lock-only kernel and explicit
kernel authorization; a matching release prefix alone is insufficient. The
[original local integration evidence](../../bench/results/10.176.26.71/tests/mmap-kd-kernel-20261021/README.md)
is retained without repeating its campaign. RT, lockdep, whole-kernel substitution
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
