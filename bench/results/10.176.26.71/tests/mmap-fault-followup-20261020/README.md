# Current mmap/fault integration review

Status: current-source capture and offline review complete. **Real KD mmap/fault
integration remains blocked and unvalidated.** No kernel build, installation,
reboot, module experiment or KD mmap/fault test ran.

The [capture script](capture.py) rechecked the live kernel and captured baseline,
recopied the 25 previously audited source/configuration files, and added
filemap/folio, userfaultfd, ext4/iomap, huge-page and lock/helper sources needed
to inspect implicit unlocks, retry and downgrade. Every old source hash
matched; all new file bytes and provenance remain explicit.

The existing [rwsem integration boundaries](../../../../../docs/design/rwsem_implementation.md#mmap-and-validation-boundaries)
remain in force. The KD object is not installed as `mm_struct::mmap_lock`;
all participants must use one protocol. Ordinary/local ownership, outer-writer
delegation, cancellation, downgrade and originating task context require
separate proofs. The review identifies concrete transitions and remaining
blockers; a native syscall result cannot validate KD integration.
No real mmap/page-fault execution through KD is claimed.

## Capture and preservation

Run `mmap-fault-followup-20261020/capture-1` ran serially after the rwlock
comparison, with the original guest idle. The [result](capture-1/result.json)
records unchanged boot `b65f0205-c8f9-4385-8b13-039cbce243a6`, kernel
`6.1.159-kdclobber2`, Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`,
and all 497 `f48b90e` source hashes unchanged before/after capture.
The kernel verifier matched its 20 selected source files, nine build files,
seven bundle files and configuration. The baseline manifest remains
`0f44870efd7ff604067a2436edcfd95ac8c4e413b42e3d534a51e3c011d3d013`.
This is not a reproducible-build proof for every newly captured source file.

The [46-file source map](capture-1/kernel-source-sha256.json) has SHA-256
`b86398958fa80cd8d030c30413f2ce1c9c6a2cf9c18d6080a82a01423b8b1881`.
The [independent audit](capture-1/offline-review.json) passed **1,470 checks**,
covering 63 archived files with no issues. The [archive manifest](capture-1/archives.json)
SHA-256 is `28f71ee6fbd53f6658964ff323fb3e9ea521ebd5e27b737401d1968e655b2c43`.
The kernel archive is 823,878 bytes, SHA-256
`eb4fe5797b94d5fac40728cefe9ecad0937c318a43b84251f42af500d262cf3d`;
metadata is 112,447 bytes, SHA-256
`cc0728deb19db742c8d8f7ed12d34a9df2db4bbf172690ab89f0b4d50dad32f1`.
Both reside under
`bench/results/10.176.26.71/raw/tests/mmap-fault-followup-20261020/capture-1/archives/`.
The [offline reader](offline-review.py) imports only a hash-pinned inert archive
helper and reads Git objects; it executes no captured program.

## Reviewed branches

The [review anchors](capture-1/review-anchors.json) bind 24 source intervals and
three KD boundaries by file and interval hashes. Paths and lines below refer
to this capture. They are a source review, not dynamic branch coverage.

| Source | Contract and implication |
| --- | --- |
| `include/linux/mm_types.h:597`, `include/linux/mmap_lock.h:63`, `kernel/fork.c:594` | `mmap_lock` is still a native `struct rw_semaphore`. Initialization, nested/killable/try acquisition, downgrade, non-owner read release, assertions and contention helpers use that protocol. Fork nests old/new-mm writes. A KD side lock or a single replaced call would not exclude native participants. |
| `include/linux/maple_tree.h:186`, `kernel/fork.c:1126` | The external lock's `dep_map` is used only with `CONFIG_LOCKDEP`; the macro is a no-op without it. The current configuration does not enable lockdep. This is a future configuration/adapter obligation, not evidence of an active lockdep dependency in this guest. |
| `mm/memory.c:5319` | Stack growth drops read ownership, obtains write ownership killably, refinds/revalidates the VMA, then downgrades; failures are unlocked. `mmap_upgrade_trylock()` returns false in this source. Reacquisition must have a new exact acquisition identity. |
| `arch/x86/mm/fault.c:1208` | Fault handling uses the actual task/mm, saved registers, IRQ state, exception fixups and signal/accounting state. Signal-pending and `COMPLETED` exits are already unlocked; `RETRY` starts a fresh lookup/acquisition, while ordinary completion unlocks explicitly. Logical-current substitution alone proves none of these context requirements. |
| `mm/internal.h:635`, `mm/filemap.c:1736` | `maybe_unlock_mmap_for_io()` pins the file before dropping read ownership, only on retry-first without NOWAIT. `__folio_lock_or_retry()` can return false with ownership retained under NOWAIT; other failure/wait paths release it. A false return is not an ownership record. |
| `mm/filemap.c:3062`, `filemap_fault:3219` | Folio lock success can coexist with mmap release, tracked by `fpin`. Retry cleanup separately releases folio/file references and mapping invalidation ownership. NOWAIT can return `RETRY` while mmap remains held. The original VMA must be refound after a drop. |
| `mm/memory.c:3033` | Dirty-page throttling can drop mmap through the file-pin helper, wait for writeback progress, put the file and return `VM_FAULT_COMPLETED`. The caller must avoid a second unlock. |
| `fs/userfaultfd.c:392` | NOWAIT returns `RETRY` with mmap held. The blocking path pins the userfault context, queues the actual `current`, changes task state, drops mmap and can schedule before removing the waiter and putting the context. This implementation does not reacquire on that blocking return. Early `NOPAGE`/error exits do not take that drop path. |
| `mm/userfaultfd.c:542`, `fs/userfaultfd.c:781` | Atomic userfault copying can drop the destination lock to fault/copy user memory, then reacquire and refind the VMA; its result is bytes/errno, not `VM_FAULT_*`. Remove notification can release the read lock and return false. Callback outcomes must carry ownership loss independently of fault flags. |
| `mm/shmem.c:2088` | Hole-punch waits distinguish retained `NOPAGE` from dropped-lock `RETRY` using the file pin. A waitqueue can live on another task's stack, requiring its existing wake/lifetime protocol. |
| `mm/hugetlb.c:5796,6188` | Userfault paths release VMA/fault-mutex ownership, and sometimes page-table/page resources, before a call that may also release mmap. These are separate nested ownership transitions. |
| `fs/ext4/file.c:680,755`, `fs/ext4/inode.c:6232` | Buffered and DAX callbacks differ. Page-mkwrite uses pagefault, mapping-invalidation, journal and page-lock protocols, including ENOSPC retry and successful locked-page returns. Those callback contracts cannot be replaced by one outer mutex unlock. |
| `fs/iomap/buffered-io.c:1247`, `fs/buffer.c:2486` | Mapping callbacks, stable-page waits, truncation errors and success retaining the page lock must preserve their own resource ownership. This capture does not close the complete transitive filesystem/DAX/journal call graph. |
| `mm/gup.c:1026,1358` | `COMPLETED` clears `*locked`; `RETRY` does so except under NOWAIT. `fixup_user_fault()` reacquires after completion/retry and sets `*unlocked`; held-at-return does not establish uninterrupted ownership. |
| `mm/mmap.c:2926` | Munmap return `1` selects read unlock after downgrade. The syscall allows downgrade; `vm_munmap()` disables it. The return mode must agree with the exact release route. |

The x86 fault handler's comment mentions userfault drop/reacquire possibilities;
the captured `handle_userfault()` implementation above determines this version's
actual branches. The broader internal drop/reacquire case is concretely present
in `__mcopy_atomic()`. No branch is inferred solely from that comment.

## Explicit integration blockers

1. **Object and participant conversion is absent.** KD's separately aligned
   reader/admission/waitqueue object is not a native rwsem layout. No coordinated
   mm initialization, all-participant API adapter, nested annotation, non-owner
   release, contention/assertion and configuration conversion exists.
2. **Delegated rwsem transitions are absent.** Ordinary KD writers have the
   exclusive `-1` phase and tested killable/downgrade behavior. Outer delegated
   writers use positive reservations and retain them through matching ACK.
   `kd_downgrade_write()` explicitly requires ordinary phase and exact origin
   ownership. JIT has no rwsem mode/owner ledger, cancellation/downgrade or
   non-owner-release protocol. The native and KD rwsem call refusals in
   `disassem/context_symbols.py:45` remain required.
3. **Origin context and lifetimes are unproved.** Real faults can touch user
   memory, allocate, sleep, run task-specific callbacks and invalidate VMAs.
   File/folio/mm/context pins, implicit release, fresh acquisition and page
   ownership all require explicit lifetime transfer. `kd_rwsem_is_idle()` is a
   quiescent inspection helper, not a live owner predicate.
4. **Integration validation is absent.** Existing probes exercise isolated
   reader/writer objects and selected delegated bodies. They do not execute KD
   as `mm_struct::mmap_lock`, cover all filesystem/DAX/journal callbacks, prove
   generic fault continuation, or validate RT/lockdep/whole-kernel replacement.
   The captured configuration enables userfaultfd, THP, hugetlbfs, ext4, iomap
   and DAX; disabled lockdep checks cannot validate an enabled configuration.

This completes the requested evidence-based blocker investigation, with real
integration explicitly unresolved. Removing admission refusals or interposing
only selected native calls would violate the single-protocol and exact ownership
requirements. No such experiment was attempted. A future integration stage needs
a coordinated kernel adapter and branch/lifetime validation under separately
authorized kernel changes.
