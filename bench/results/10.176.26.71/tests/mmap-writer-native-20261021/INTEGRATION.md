# Actual mmap-lock integration audit

Status: **BLOCKED — no KD replacement implemented or measured.** The Native
shared-mm workload and the separate local-reader fault workload are useful
controls, but neither substitutes the actual `mm_struct::mmap_lock`. No kernel
source, configuration, image or boot state was changed in this stage.

## Evidence and scope

The unchanged VM kernel is `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. The inert capture contains 61,567
C/header/assembly/configuration/build inputs, 1,229,941,474 bytes. All members
matched the independently captured source manifest. Archive SHA-256:
`9524af83f1bf9b1d8524d64e603ccde9f44c5eb8e9906dc2d1d56dda5aff31d5`;
manifest SHA-256:
`4136eb02bb788b6bb764a086adaae3115eb2881a9b97c45765e3c1235237b11d`.

The [inventory](participant-inventory.json) records 1,372 lexical rows in 247
candidate files, with file hashes and line numbers. [Audit metadata](kernel-audit.json)
records API counts, configuration and selected source hashes. This includes
comments, definitions, other objects also named `mmap_lock`, disabled code and
other architectures. It is **not** 247 proven runtime participants or a complete
transitive call graph. Actual participant reachability, aliases and callbacks
remain an explicit integration gap. Families requiring that review include MM,
architecture fault paths, fork/exit, procfs/filesystems/userfaultfd, drivers,
security, IPC, virtualization, io_uring and remote-mm users. An opt-in syscall
wrapper alone does not cover these participants.

Retained source paths below refer to the captured kernel, not the repository's
historical kernel experiment patches. The raw selected source is under
`raw/tests/mmap-writer-native-20261021/kernel-capture-1/kernel-review/` and every
other input is recoverable from the full archive.

## Object and API conversion work

| Native obligation | Current KD support | Required work before coherent integration |
| --- | --- | --- |
| `mm_types.h` native `struct rw_semaphore mmap_lock`; `MMAP_LOCK_INITIALIZER`, dynamic init, Maple Tree external-lock metadata and direct lockdep/status accesses | `kd_rwsem` has a different 320-byte, 64-aligned layout and separate reader/admission queues | Convert the real member, every initializer, embedded metadata, direct field/lockdep user and teardown coherently. The 32-byte KD mutex ABI does not make KD rwsem layout compatible. |
| `mmap_read_lock`, killable read and read trylock, then read unlock | Local concurrent `kd_down_read*` / `kd_up_read` | Keep readers local and concurrent; validate return/cancellation semantics at every fault/retry/remote-mm caller. Reader delegation is unnecessary. |
| Ordinary write, killable write, write trylock and write unlock | Local `kd_down_write*` / `kd_up_write` | Preserve the exact successful acquisition and release mode, including fatal-signal cancellation and failed trylock without residual admission. |
| `mmap_write_downgrade` followed by read unlock | Local `kd_downgrade_write` supports ordinary writer admission `-1` | Retain an atomic writer-to-reader transition and subsequent read release with no intervening writer. A delegating outer acquisition cannot use this local downgrade path. |
| `mmap_write_lock_nested`, lockdep annotations and assertions | No mmap adapter or validated lockdep integration | Preserve nesting class and actual acquisition provenance; adapt assertions without equating quiescence with ownership. |
| `mmap_read_unlock_non_owner` and external completion paths | No public non-owner release contract | Define explicit transferable acquisition/lifetime records, then validate exactly-once non-owner release. A plain count decrement is not sufficient evidence. |
| `mmap_lock_is_contended`, `rwsem_is_locked` and trace events | `kd_rwsem_is_idle` exists only for quiescent inspection | Define appropriate status/observation helpers, trace semantics and lockdep behavior. Idle cannot substitute for locked/owned/contended. |
| Delegating outer writer | Existing lexical `KD_RWSEM_OUTER_WRITE_LOCK/UNLOCK` reserves a positive phase until origin ACK | It is uninterruptible, cannot downgrade/cancel after publication or nest inside another generated body. Do not map killable mmap writers to this pair. |

The current definitions are [kd_rwsem.h](../../../../../include/kd_rwsem.h) and
[kd_rwsem_direct.h](../../../../../include/kd_rwsem_direct.h); their
[implementation contract](../../../../../docs/design/rwsem_implementation.md)
remains authoritative. No admission, queue, owner, source lease, ACK or frame
retirement check was relaxed by this audit.

## Concrete mode, origin and lifetime paths

| Captured path | Obligation |
| --- | --- |
| `mm/util.c:507` `vm_mmap_pgoff` | Uses `current->mm`; write-killable acquisition covers `do_mmap`, VMA/Maple Tree changes and callbacks. Population and userfault completion occur after release. File/security callbacks can allocate, sleep and consult current task context. |
| `mm/mmap.c:2926` `__vm_munmap` and `:2589` downgrade branch | The syscall permits downgrade. A helper return of 1 means ownership has become read mode, so the caller must use read unlock. Other paths release write ownership. A lexical mutex unlock endpoint cannot encode this change by itself. |
| `mm/mprotect.c`, `mm/mremap.c`, brk/stack growth paths | VMA splits, merges, mapping changes, accounting, allocations, page-table and TLB work require the same actual mmap-lock protocol and path-dependent releases. |
| `kernel/fork.c:583` `dup_mmap` | Locks old mm killably, then the new mm with nested write annotation. Both acquisitions and independent failure cleanup must be represented. Merely sharing a file does not make two address spaces share the lock. |
| `mm/mmap.c:3224` `exit_mmap`, `kernel/fork.c:1200` final mm user path | Read phase for unmap, then write phase for final VMA destruction. Descriptor lifetime and mm-user lifetime differ. Teardown can invoke callbacks after `current->mm` is detached; retain exact VMA/mm/file identities. |
| `mm/gup.c:992,1028,1054,1130` and `mm/filemap.c` fault helpers | Fault handling may drop read ownership or return `VM_FAULT_RETRY` / `VM_FAULT_COMPLETED`. Propagate whether the lock remains held; revalidate VMA/pointers after reacquisition. NOWAIT and completed paths must not double-release. |
| `fs/proc/task_mmu.c`, `mm/memory.c` remote access and `fs/userfaultfd.c` | Observers may use another task's mm; contention can require dropping/reacquiring ownership. Task, mm, VMA, file, page/folio and userfault state each need their own reference lifetime. |

`current`, GS-relative task/CPU state, user-memory access, sleepable allocation,
filesystem callbacks and fault-driven lock release cannot simply execute on an
unrelated combiner with the caller's register packet. Full delegation requires
admitted, origin-correct continuations for each such operation and exact mode
and reference transfer. The present JIT admission intentionally rejects
unsupported paths. TCLock is excluded from these complete critical sections;
its supported local backing-reader control is a separate workload.

If a future adapter chooses Native fallback, the choice must be immutable for
that entire mm before publication, and every participant must route through it.
It cannot change after contention, publication or partial execution, and it
cannot mix Native and KD ownership of the same object. Adding a private lock
around a module callback would not replace the actual mmap lock.

The minimum next integration stage therefore requires a coordinated kernel
adapter, full participant/API reachability review, missing mode/ownership APIs,
origin-context handling and new focused fault/fork/exit/remote-mm/lockdep checks.
Kernel changes and rebuilds are outside the current authorized default. This
stage stops at the measured Native control and this explicit blocked contract;
it establishes no whole-kernel, RT, ww_mutex, lockdep or arbitrary MM delegation
support. All seven mutex regression causes remain separately unresolved.
