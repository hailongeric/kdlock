# kdlock (clean rewrite)

**Status: boots and passes functional checks; not measured.** The kernel with
kdlock built in boots in the `kdclaude` VM; all four families, two-level
nesting and handback keep the data exact with and without delegation (see
[docs/BUILD_AND_TEST.md](docs/BUILD_AND_TEST.md)). It was written from the goal and from TCLocks, BCD and the
redesign notes in `../docs/design/kdlock_redesign/` (the repository-level docs), without reference to the
existing kdlock implementation.

**Complete documentation is in [docs/](docs/README.md)**: architecture, lock
protocols, translator, interfaces, kernel integration, build/test status, a
review of differences from the earlier documents, and the performance plan.
This file is the short overview.

## Idea

TCLocks lets the lock holder (the combiner) run waiters' critical sections
by switching to their stacks, so the protected data stays in one cache.
It cannot delegate code that depends on the running task, because
`current` and the stack canary are read through `%gs`, which still belongs
to the combiner.

kdlock keeps the TCLocks mechanism and changes one thing: the combiner does
not run the waiter's original code but a **relocated copy** produced by a
userspace translator. In the copy, the few task-identity accesses read the
waiter's values. Anything the copy cannot execute correctly ends it with an
exit, and the waiter continues natively from exactly that instruction.

```
waiter W                         combiner C (queue head, holds the lock)
--------                         ---------------------------------------
lock() contended
save rbx rbp r12-r15 rsp rip
switch to per-CPU wait stack
queue node -> packet, image
spin on node state               for each queued node with an image:
                                   rsp := W.rsp, registers := W packet
                                   run copy of W's critical section
                                   ...
                                   call unlock(this lock)  -> exit, done
                                 or
                                   untranslated / sleeping / faulting code
                                                           -> exit, handback
resume from packet               next waiter, then C's own section
```

## What differs from the redesign notes, and why

The notes prescribe the BCD backend as is: software register
virtualisation (five reserved registers, a virtual stack pointer),
`%gs`-base rewriting, per-lock images and fragments that end at every lock
operation. This rewrite deliberately does less:

| Topic | Redesign notes | Here | Reason |
| --- | --- | --- | --- |
| Stack and registers | Virtual SP/BP, remapped R11-R15, spill/reload | Real `rsp` on the waiter's stack, no register is reserved | Instructions are copied byte for byte; no per-instruction overhead and no mapper to get wrong. BCD needed virtualisation to supervise user code in the kernel; trusted kernel code does not. |
| `%gs` | Every access rebased to the waiter's per-CPU area | Only `current_task`, `__stack_chk_guard`, `cpu_current_top_of_stack` are redirected (to `kd_cpu` fields) | Per-CPU data means "the CPU running this code". Rebasing it would make the combiner update another CPU's allocator caches and counters without that CPU's interrupt exclusion. |
| Lock operations in a section | Every lock and unlock ends a fragment | Uncontended spin-class lock calls and ordinary releases are native calls. Generated code is left only for the release of a session root, a contended inner lock, and sleeping-family acquires | A nested spinlock costs what it costs natively when it is free. The lock functions act for the waiter by themselves (`kd_logical_current()`). |
| Handback | Session states, release mailboxes, ACKs | The lock word stays "held" and now belongs to the waiter; the combiner waits as queue head | No extra lock states: a handed-back waiter releases with the ordinary unlock. |
| Nested delegation | Child nodes sharing one state through several combiners, with mailboxes and sequence numbers | Recursive, as in TCLocks: the executor queues the continuation it is running for the inner lock (see "Nesting") | One packet per origin, a small stack of session roots in it, and ordinary C recursion on the executor. |
| Images | Entries, fragments, generations | One immutable image per call site, replaced whole, freed after an RCU grace period | Waiters and combiners are non-preemptible from lookup to resume, so no reference counting is needed. |

Kept from the notes: delegation is optional and decided by one atomic
transition; exactly one participant advances a continuation; handback is
exact and never replays; learning is cumulative and never blocks the
current invocation; readers stay on their own task.

## Layout

| Path | Content |
| --- | --- |
| `include/kdlock/kd_types.h` | Lock objects, same sizes as the native types |
| `include/kdlock/kd_api.h` | Lock API |
| `include/kdlock/kd_uapi.h` | `/dev/kdlock` interface, exit and event codes |
| `kernel/kd_entry.S` | Delegable entry stubs, `kd_resume`, `kd_jit_enter/exit` |
| `kernel/kd_internal.h` | Packet, node, per-CPU state, MCS queue primitives |
| `kernel/kd_core.c` | Waiting, combining session, section executor |
| `kernel/kd_spinlock.c`, `kd_rwlock.c`, `kd_mutex.c`, `kd_rwsem.c` | The four families |
| `kernel/kd_image.c`, `kd_dev.c` | Sites, images, event ring, device, stats |
| `jit/kdjit/translator.py` | Section translator (capstone) |
| `jit/kdjit/kernel.py` | Device, kallsyms, text and exception-table access |
| `jit/kd_daemon.py` | Event loop, cumulative knowledge, publication |
| `integration/` | How to map the Linux lock API and types onto kdlock; `apply_to_tree.sh` |
| `bench/` | Nano benchmark module and runner |
| `docs/` | Full documentation |

## Lock protocol

All families share one queue word (`locked` byte, `flags` byte, 16-bit MCS
tail) and one set of queue primitives.

**Waiter.** The entry stub tries the fast path. On failure it claims the
CPU's packet and wait stack (`kd_cpu.busy`), stores the continuation, moves
to the wait stack and calls the C wait function. The waiter looks up its
call site; with an image it queues a delegable node, otherwise a plain one
and the site's contention counter may request a translation.

**Combiner.** A waiter promoted to queue head takes the lock and runs a
session: for each following delegable node it executes the section, unlinks
the node and publishes `RESUME`. It stops at the batch limit, at a plain
node, on `need_resched()`, or when a section's interrupt state is
incompatible with its own. Then it passes headship on and returns to run
its own section. Fast-path owners never combine.

**NUMA order.** As in TCLocks, a session serves only waiters of the
combiner's NUMA node. A delegable waiter of another node is unlinked onto a
list private to the session, still waiting, and the session continues with
the waiters behind it. At the end the list is put back in front of the
queue in its original order, so its first waiter becomes the next head and
combines for its own node. Passed-over waiters count against the batch
limit. Plain waiters are never passed over. `kd_numa=0` restores FIFO.

**Section end.** In the copy, every release call first compares its
argument with `kd_cpu.root`. Equal means the waiter's section is complete:
the release is not performed (the combiner keeps the lock), its effects on
the waiter's context (preempt count, interrupt flag) are recorded in the
packet, and the waiter resumes after the call.

**Handback.** Any other exit leaves the packet at the first instruction
not executed. The lock stays held and now belongs to the waiter, which
resumes natively and later releases normally. The combiner goes back to
waiting for the lock as queue head.

**Nesting.** When the section a combiner C_A is executing for W meets a
contended inner lock B, C_A does what a TCLocks combiner does: it becomes
the waiter for B, publishing the continuation it is running. The `_jit`
lock entry stores that continuation in W's packet (the same packet, no
copy) and returns to the executor, which queues a node for B that points at
it. From there the inner queue decides:

- B's combiner C_B claims the node and runs W's continuation onwards. When
  it reaches `unlock(B)`, C_A's node is resumed and C_A continues W's
  section in generated code from the state C_B left.
- C_A reaches the head of B's queue. It takes B, serves B's other waiters
  as a nested combiner (up to `KD_MAX_DEPTH` open sessions per CPU), and
  continues W's section.
- B is a mutex or rwsem and waiting would require sleep: W gets the
  continuation back with the call to B still pending.

The packet records the locks it is being executed for (`roots[]`, at most
`KD_MAX_ROOTS`). If an inner executor meets the release of an outer root
(`lock(A); lock(B); unlock(A); ...; unlock(B)`), it must not unlock it,
because A is still held by C_A's session; it sets a bit in `released` and
applies only the logical effects. C_A sees the bit when its node resumes
and ends W's turn on A. To keep ordinary releases free of this check, the
copy consults `kd_cpu.anc` (number of outer roots) and leaves generated
code for a non-root release only when that is nonzero.

A handback from an inner executor propagates outwards through the same
node states: each level either keeps its lock (its root was already
released) or passes it to W, and W resumes natively exactly once.

**Context transfer.** While a section runs, the combiner's interrupt flag
is the waiter's logical flag (`popfq` on entry, `pushfq` on exit), and
preemption is disabled. The preempt-count change the section caused on the
combiner is measured, undone there and added on the waiter at resume, so
both stay balanced across nested spinlocks and handbacks.

| Family | Grant | Delegable | Notes |
| --- | --- | --- | --- |
| spinlock | queue word | `kd_spin_lock{,_irq,_irqsave,_bh}` | `kd_raw_*` never publish; FIFO, no pending bit |
| rwlock | writer byte in `cnts`; `wait` orders slow paths | writers | Combiner keeps `wait` and the writer byte for the session; readers local; interrupt-context readers do not queue behind waiting writers |
| mutex | lock byte; MCS queue for spinners, list for sleepers | `kd_mutex_lock{,_interruptible,_killable}` | A spinner withdraws (`WAIT -> ABANDON`) before sleeping, the combiner claims with `WAIT -> RUN`; handoff flag bounds sleeper starvation |
| rwsem | writer bit in `count`; a kd mutex `m` orders slow paths | writers | Only the holder of `m` sleeps on `count`, so `m.owner` is the wake target; downgrade is one atomic and is always handed back inside a section |

A delegated section never sleeps on the combiner. Calls that can sleep are
frontiers in the copy. A mutex or rwsem-writer acquire inside a section is
queued and spun for like any other nested lock while its holder is
running, and handed back with the call pending once that would need sleep.

## Translator

For a site the translator decodes from the return address of the lock
call, following direct jumps and up to five direct-call edges, and emits a
copy with these rewrites only:

- direct jumps and calls target the copy; a call pushes the *source* return
  address, so the waiter's stack always holds ordinary kernel addresses;
- returns and indirect branches are compare chains over known targets,
  ending in a learnable exit (this also removes return and indirect-branch
  mitigations from the copied path);
- rip-relative displacements are recomputed; the three task-identity
  per-CPU symbols are redirected;
- release calls get the root comparison; sleeping acquires become exits;
- frontiers become exits: instructions with an exception-table entry,
  privileged/CPU-state instructions (`stac`, `swapgs`, `wrmsr`, `invlpg`,
  `ud2`, ...), scheduler entry points, user-copy helpers, unknown text;
- listed leaf helpers (`memcpy`, ...) and all `kd_` functions are called
  natively.

Unknown targets are reported through `/dev/kdlock`; the daemon adds them to
the site's knowledge (kept in a JSON file across restarts) and republishes.
The kernel disables a site whose sections are mostly handed back until a
new image arrives.

## Known limits and open points

1. **Partly tested.** See [docs/BUILD_AND_TEST.md](docs/BUILD_AND_TEST.md)
   section 6 for what has not run yet (deeper nesting, interrupt-context
   interactions, signals, hotplug, the kernel API switch).
2. **Handback inside a per-CPU-bound region.** If a section is handed back
   while it has preemption disabled beyond its locks (counted as
   `handback_pinned`), the waiter continues on a different CPU than the
   code before the exit ran on. The preempt count is transferred, per-CPU
   pointers already taken are not.
3. **Flags across call/ret.** Return and indirect-branch dispatch clobber
   flags; the System V rule that flags are dead there is assumed.
4. **Text patching.** Images are built from live text. Later jump-label,
   static-call, ftrace or livepatch changes are not tracked.
5. **Module load/unload drops every image** (correct but coarse; sites are
   translated again).
6. **Unwinding.** No ORC data for images, the wait stack or the stack
   switch; stack traces through them stop early.
7. **Not delegated:** readers, trylocks, `raw_spinlock_t`, waiters in
   interrupt context. Native code called from a section (leaf helpers, lock
   internals) that itself blocks on a lock waits without publishing.
8. **Nesting bounds:** a continuation nested under more than
   `KD_MAX_ROOTS` (4) session locks, or an executor with `KD_MAX_DEPTH` (3)
   sessions open, waits for the next inner lock without publishing or
   combining. A release reached through a sibling `jmp` in a nested run is
   handed back.
9. **NUMA order** uses the node of the CPU that queued the node. For a
   nested waiter that is the executor, not the origin of the continuation.
10. **API coverage:** see `integration/README.md` for what the kernel patch
   still has to supply (`ww_mutex`, owner helpers, `arch_spin_*` users).
