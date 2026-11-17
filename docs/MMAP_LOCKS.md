# The locks inside the mmap write section, and which of them kdlock can take over

This answers one question: **can every lock in the mmap critical section be
replaced with kdlock?** The short answer is no, and the reason is not a missing
feature list — it is that the section contains four different kinds of
serialization, only one of which is a lock in the sense kdlock implements.

Everything below is from the development VM's kernel source,
`/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/source` (Linux 7.0.0-38 with
`CONFIG_PER_VMA_LOCK=y`, `CONFIG_LOCK_MM_AND_FIND_VMA=y`), and from the
will-it-scale measurements in
[`../bench/results/kdclaude/wis-20261115-64cpu/`](../bench/results/kdclaude/wis-20261115-64cpu/README.md).

## 1. What the mechanism requires of a lock

Two separate conditions, and both must hold:

1. **The lock object must be routed through a kdlock family.** kdlock has four:
   spin, rwlock, mutex, rwsem ([LOCKS.md](LOCKS.md)). The object must be a
   `struct kd_*`, initialized as such for its whole life, and *all* its users
   must use the same protocol (`AGENTS.md`). For `mm->mmap_lock` this is
   `CONFIG_KDLOCK_MM`: `struct kd_mm_lock` is a union of a native
   `rw_semaphore` and a `struct kd_rwsem`, and each new `mm` picks one before
   it is published (`include/kdlock/kd_mm_types.h`).
2. **The critical section's code must be executable by the combiner.** The
   combiner runs a relocated copy of the waiter's section. Whatever the
   translator cannot copy faithfully becomes a *frontier*: the session stops
   and the lock goes back to the origin at the exact next instruction
   ([TRANSLATOR.md](TRANSLATOR.md)). The frontier set is explicit in
   `jit/kdjit/translator.py`, and it is what decides whether replacing a lock
   buys anything.

Condition 2 is the one that matters here, because the frontier list already
contains the nested locks of the mmap path:

```python
# jit/kdjit/translator.py, "frontier": callees only the origin may execute
"mutex_lock", ..., "down_read", "down_write", "down_write_killable", ...
"flush_tlb_mm_range", "flush_tlb_multi", "smp_call_function_many_cond", ...
"schedule", "__schedule", "_copy_from_user", "_copy_to_user", ...
```

and the "native" list — callees the combiner may simply call on its own CPU —
already contains the *spinning* locks:

```python
"_raw_spin_lock", "_raw_spin_lock_irq", "_raw_spin_lock_irqsave",
"_raw_spin_lock_bh", "_raw_spin_unlock", ..., "_raw_read_lock",
"_raw_write_lock", "queued_spin_lock_slowpath",
```

So a native spinlock inside a delegated section needs no replacement at all:
it has no task identity, and its preempt-count change is measured and moved to
the origin like any other. A native *sleeping* lock inside a delegated section
is a frontier, because its slow path prepares to sleep for the task — task
state, wait entries, optimistic spinning on per-CPU queue nodes — before it
reaches `schedule()`.

## 2. What is actually inside the section

Taken from the Linux 7.0 source along the four will-it-scale paths. "Under the
write side" means while `mmap_lock` is held for write, which is the part a
combiner would run.

| # | Serialization | Type | Where | Reached by |
|---|---|---|---|---|
| 1 | `mm->mmap_lock` | `rw_semaphore` | `include/linux/mmap_lock.h` | every path |
| 2 | `anon_vma->root->rwsem` | `rw_semaphore`, `down_write` | `mm/vma.c:311` (`vma_prepare`), `mm/vma.c:3147`, `mm/vma.c:3226`, `mm/rmap.c:133,208,353` | anon mmap that merges, `fork`, `anon_vma_clone`, `unlink_anon_vmas` |
| 3 | `mapping->i_mmap_rwsem` | `rw_semaphore`, `down_write` | `mm/vma.c:297,1780,1817`, `mm/mmap.c:1829`, `include/linux/fs.h:510` | every **file** mapping: insert, remove, merge |
| 4 | per-VMA lock: `vma->vm_refcnt` + `mm->mm_lock_seq` | refcount plus seqcount, with a wait for readers | `include/linux/mmap_lock.h:342` `__vma_start_write`, 13 call sites in `mm/vma.c` | every path that changes a VMA |
| 5 | `mm->page_table_lock` and the split PTE/PMD locks | `spinlock_t` | `mm/memory.c:440,1884,1931,2025` (`pmd_lock`, `pte_offset_map_lock`) | fault, `zap_pte_range`, `free_pgtables`, `copy_page_range` |
| 6 | `zone->lock`, per-CPU pageset lock | `spinlock_t` / `local_lock` | `mm/page_alloc.c:1511,1593`, `pcp_spin_trylock` | every page allocated or freed |
| 7 | folio lock, `lruvec->lru_lock` | bit lock that sleeps, `spinlock_t` | `mm/vmscan.c`, `mm/swap.c` | reclaim and LRU work along the way |
| 8 | TLB shootdown | cross-CPU IPI, not a lock | `flush_tlb_mm_range`, `flush_tlb_multi` | any unmap of a *populated* range |
| 9 | RCU read sections, `mm_lock_seq` seqcount | not locks | `lock_vma_under_rcu`, `vma_start_read` | the fault path |
| 10 | `mm_all_locks_mutex` | `mutex` | `mm/vma.c:2205` | `mm_take_all_locks`, i.e. mmu-notifier registration only |
| 11 | `mmlist_lock`, `mm->arg_lock`, `mm->context.lock` | `spinlock_t`/`mutex` | `kernel/fork.c`, x86 LDT | `fork`, `execve`, LDT changes |

## 3. What the measurements show

Four unchanged will-it-scale tests, Native and kd alternating in one boot
(`kd_mm` chooses the backend per new `mm`), build #72. Full tables in the
results README; the columns that matter here are the kdlock counters.

| test | what it maps | kd/Native, threads | delegated bodies | handback |
|---|---|---|---|---|
| `mmap1` | 128 MiB anonymous, never touched | 1.25-1.37 at 4-32, 2.06 at 64 | 6.7-7.0 M per run | ~10<sup>3</sup> |
| `mmap2` | 128 MiB of a file, never touched | **0.78-0.86** | 15-35 per run | **1.28 M, all `hb_frontier`** |
| `page_fault1` | 128 MiB anonymous, every page touched | **0.84-0.91** at 2-16, 1.02-1.06 at 32-64 | ~10<sup>2</sup> per run | ~10<sup>2</sup> |
| `brk1` | one page, grown and shrunk | 0.84-1.07 (inside the spread) | ~10<sup>3</sup> per run | ~ all sessions |

Three different outcomes, three different causes, and the counters separate
them without any guessing:

**`mmap1` is the case the mechanism was built for.** 1870 sessions execute
6.57 M waiter sections — about 3500 per session, at `kd_batch` 4096 — with 132
handbacks in the whole run. That works because an *untouched* anonymous
mapping has no page tables and no present PTEs, so `tlb_flush_mmu_tlbonly()`
returns at its first test (`include/asm-generic/tlb.h:495`), no IPI is sent,
and `vma_prepare` finds neither a file nor an `anon_vma`. The section contains
only maple-tree and slab work, all of it copyable. Half the sections also enter
the virtual downgrade (`vdown` 3.3 M of 6.6 M): `munmap` downgrades the write
side at `mm/vma.c:1321` and the combiner keeps the write gate and runs the read
tail, which is what keeps the chains long.

**`mmap2` is the case where one nested lock is enough to lose everything.**
The only difference from `mmap1` in the source is the file: `vma_prepare()`
takes `i_mmap_lock_write(vp->mapping)` at `mm/vma.c:297`, which is
`down_write(&mapping->i_mmap_rwsem)` (`include/linux/fs.h:510`), and
`down_write` is in the translator's frontier list. The counters say exactly
that: 1 279 253 sessions, 1 279 244 handbacks, **all of them `hb_frontier`**,
16 bodies delegated. Every session pays for an offer, a packet, a queue node
and a handback and executes nothing. That is the 14-22% loss.

**`page_fault1` shows the cost of the replacement itself, with no delegation at
all.** Faults do not take `mmap_lock` in this kernel: `CONFIG_PER_VMA_LOCK=y`
and `arch/x86/mm/fault.c:1325` calls `lock_vma_under_rcu()`. So there is almost
nothing to delegate (about 100 bodies per run) and the 9-17% loss at 2-16
threads cannot come from delegation. What does change is that `mmap_lock` is a
`struct kd_rwsem` instead of a `rw_semaphore`, and the test's `munmap` of a
fully populated 128 MiB region holds the write side for milliseconds, far
longer than a kd reader's bounded spin. See section 5 for the attribution run.

**`brk1` is the short-section case.** `brk` write-locks `mmap_lock` on every
call, but the section reaches a frontier almost immediately (the shrink path
flushes the TLB), so sessions and handbacks are equal and nothing is gained;
the rate stays inside the run-to-run spread (the two kd rounds at 4 threads
differ by 10% by themselves).

Ruling out the downgrade for `mmap2`: with `kd_vdown=0` the handback count is
unchanged (1.29-1.38 M, still all at the frontier) and the ratio moves from
0.78 to 0.88 at 4 threads and from 0.80 to 0.83 at 16. The cost is opening a
session that executes nothing, not the downgrade inside it.

In the `processes` model all four tests give each worker its own `mm`, so there
is no contention to delegate and every ratio is 0.95-1.11 — the expected
no-op.

## 4. Lock by lock: what replacing it would do

| # | Lock | Can it be a kdlock object? | Would it help? |
|---|---|---|---|
| 1 | `mm->mmap_lock` | Yes, done (`CONFIG_KDLOCK_MM`) | Yes for `mmap1`; it is also what costs `page_fault1` |
| 2 | `anon_vma->root->rwsem` | Yes in principle: an rwsem, one per `anon_vma`, taken in task context | It would remove a frontier from merging anon mmap, `fork` and `unlink_anon_vmas`. Nested delegation of a second rwsem inside a delegated rwsem section is the open piece |
| 3 | `mapping->i_mmap_rwsem` | Yes in principle: same shape, one per `address_space` | This is the one that decides `mmap2`. Nothing else in the file path is untranslatable for an untouched mapping |
| 4 | per-VMA lock | **No.** It is not a lock object: a refcount in the VMA plus `mm->mm_lock_seq`, with `__vma_start_write` sleeping until readers leave. There is no acquire/release pair to route | Not applicable. It stays a handback when a writer has to wait for a per-VMA reader |
| 5 | page-table locks | Possible, but **unnecessary**: `_raw_spin_lock` is already in the translator's native list, so the combiner takes them on its own CPU | No. Replacing them would add object preparation for every page table and remove nothing |
| 6 | `zone->lock`, pcp lock | Same as 5 for `zone->lock`. The per-CPU pageset lock is **not replaceable**: `local_lock` protects *this CPU's* state, and the combiner is a different CPU from the origin | No. Correct either way, but the pages land on the combiner's node |
| 7 | folio lock, `lru_lock` | `lru_lock` as 5. The folio lock is **not replaceable**: it is a bit in `folio->flags` whose slow path sleeps on a wait-bit queue | No |
| 8 | TLB shootdown | **Not a lock.** It is an IPI that may wait for the origin's own CPU, which can be spinning with interrupts off; that is why it is a frontier | No. It will always end a delegated section that unmaps populated pages |
| 9 | RCU, `mm_lock_seq` | **Not locks** | No |
| 10 | `mm_all_locks_mutex` | Yes (a mutex), but it is taken once per mmu-notifier registration | No |
| 11 | `mmlist_lock`, `arg_lock`, LDT lock | 5/10 apply | No |

## 5. Attribution of the `page_fault1` loss

`page_fault1` pays for the replacement without using it, so it isolates the
cost of a kd rwsem standing in for `mm->mmap_lock`. The suspect is the reader
admission path: a reader that finds the write side held registers behind it and
spins up to `kd_rwsem_rspin_ns` (50 us by default) before it deregisters and
queues on `->m` to sleep (`kernel/kd_rwsem.c`, `kd_down_read_admit`). A native
`rw_semaphore` reader queues and sleeps straight away. When the write holder is
a 128 MiB `munmap`, every blocked reader burns the full spin budget and keeps
touching the counter line the writer is using.

Measured, `threads`, same boot, build #72, M faults/s (median of two rounds):

| workers | Native | kd, defaults | kd, `kd_rwsem_rspin_ns` 0 | kd, `kd_rwsem_rphase_ns` 0 |
|---|---|---|---|---|
| 2 | 1.116 | 1.023 (0.92) | 1.015 (0.91) | 1.010 (0.91) |
| 8 | 2.763 | 2.248 (0.81) | **2.575 (0.93)** | 2.350 (0.85) |
| 16 | 3.031 | 2.406 (0.79) | **2.707 (0.89)** | 2.495 (0.82) |

Reader spinning accounts for about two thirds of the loss at 8 and 16 threads;
the reader phase accounts for none of it. Lowering the default is not the
answer, because reader spinning is what the reader-heavy rwsem profiles of
round 10 live on. The rule that is missing is that a reader which registered
behind an *active* writer should stop spinning once the phase counter has
stood still for a while, instead of running out a fixed 50 us budget against a
holder that will not leave for milliseconds. That is open work.

A test that does contend for `mmap_lock` through faults is in
[`../bench/results/kdclaude/pfshared-20261116-64cpu/`](../bench/results/kdclaude/pfshared-20261116-64cpu/README.md):
threads fault on one shared mapping while `mprotect` splits it, so faults
fall back to the read side behind the writer. There kd's reader spinning is
what puts it ahead of Native (1.02-1.13 at 2-16 threads), and with every
fault a reader it is also what costs it at 48 threads.

## 6. Answer

No. Of the eleven kinds of serialization in the mmap write section, **three**
are rwsems that kdlock could own (`mmap_lock`, already done;
`anon_vma->root->rwsem`; `mapping->i_mmap_rwsem`), **five** are spinning locks
that need no replacement because the combiner may already take them natively,
and **three** are not locks at all — a refcount plus seqcount per VMA, a
sleeping bit lock on a folio, and a cross-CPU IPI. The last group is a hard
floor: a delegated section that unmaps populated memory will always hand the
lock back at the TLB flush.

What that leaves as useful work, in order of measured value:

1. **Nested delegated acquisition of a second kd rwsem**, then
   `mapping->i_mmap_rwsem` as a kd rwsem. That is the whole of the `mmap2`
   regression (1.28 M frontier handbacks, 0.78-0.86 of Native) and it is the
   only one of the three with a measurement attached.
2. **`anon_vma->root->rwsem`** next, which widens delegation from "mappings
   that never merge" to the ordinary anon case, and reaches `fork`.
3. **The kd rwsem reader admission**, which is a cost the replacement imposes
   on workloads that barely delegate at all (`page_fault1`, and the
   reader-heavy cross-node profiles in
   [`../bench/results/kdclaude/grid-20261115-r10-64cpu/README.md`](../bench/results/kdclaude/grid-20261115-r10-64cpu/README.md)).

Only after 1 and 2 would "replace the locks in the mmap section" describe
something that exists; today the honest statement is that one lock of the
section is replaced, and that it pays for itself exactly when the section it
guards contains nothing else that has to run on the waiter's own CPU.
