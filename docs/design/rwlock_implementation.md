# KD read-write lock

Use [kd_rwlock.h](../../include/kd_rwlock.h) when several readers should run at
once, but each writer needs exclusive access. Readers always run on their own
CPUs. A writer can run locally or let a combiner execute its critical section
through KD's spin JIT engine. Both routes use the same exclusion rules.

This is an x86_64 spinning lock for ordinary task context. Code inside it must
not sleep. The [lock catalog](../LOCKS.md) distinguishes this lock from sleeping
rwsem. The [design overview](../DESIGN.md#terms-used-in-these-guides) explains
terms such as combiner, continuation, source lease and ACK.

## Source and execution paths

| Stage | Implementation |
| --- | --- |
| Object, reader operations and native writer admission | [kd_rwlock.h](../../include/kd_rwlock.h): reader count, writer bits, spin gate and all public pairs |
| Writer preparation and pinned local entry | [spin/direct.inc](../../kernel_module/spin/direct.inc): `kd_spin_prepare` and `kd_rwlock_lock_pinned_clobber_v1` |
| Delegated writer admission, refusal and retry | [spin/combiner.inc](../../kernel_module/spin/combiner.inc): `kd_spin_rw_begin`, `kd_spin_rw_cancel`, `kd_spin_rw_retry` |
| Generated execution and waiter restoration | [spin/execute.inc](../../kernel_module/spin/execute.inc), [spin/restore.inc](../../kernel_module/spin/restore.inc), and shared execution frames |

There is no separate `kd_rwlock.c` or rwlock queue implementation. The embedded
gate uses KD's spin engine, while the header and writer-admission helpers add
read/write exclusion. A gated writer needs both writer admission and exact spin
ownership. The ungated fast writer instead retains its writer byte and exact
nondelegated reference through unlock; it does not acquire the gate.

## Public API

| Operation | API |
| --- | --- |
| Read | `kd_read_lock` / `kd_read_unlock` |
| Write without delegation | `kd_write_lock` / `kd_write_unlock` |
| Write with delegation available | `KD_RWLOCK_DIRECT_WRITE_LOCK` / `KD_RWLOCK_DIRECT_WRITE_UNLOCK` |
| Initialize an unused object | `DEFINE_KD_RWLOCK` or `kd_rwlock_init` |

Native and delegating writers may use the same object, but every acquisition must
use its matching unlock API. Each pair disables preemption once and restores it
on unlock. IRQ/BH state is preserved.

```c
#include <linux/objtool.h>
#include "kd_rwlock.h"

static DEFINE_KD_RWLOCK(rw);
static unsigned long value;
extern char update_entry[];

static __attribute__((noipa)) void update_value(void)
{
    KD_RWLOCK_DIRECT_WRITE_LOCK(&rw, kd_rwlock_direct_cookie,
        ".globl update_entry\nupdate_entry:\n\t" ANNOTATE_NOENDBR);
    value++;
    KD_RWLOCK_DIRECT_WRITE_UNLOCK(&rw, kd_rwlock_direct_cookie);
}

static unsigned long read_value(void)
{
    unsigned long result;
    kd_read_lock(&rw);
    result = value;
    kd_read_unlock(&rw);
    return result;
}
```

Once the source module is LIVE, prepare the writer before starting workers:
`kd_rwlock_prepare(&rw, (unsigned long)update_entry, KD_ENTRY_ABI_RWLOCK_CLOBBER_V1)`.
Use a unique named continuation in each `noipa` writer function. That name marks
where the body starts after successful acquisition.

Preparation registers the source. Delegation also needs a published JIT image and
enough contention to pass KD's heat checks. Unprepared, cold, refused or explicitly
native calls execute locally. Call `kd_rwlock_init` only when no reader, writer or
queued request can still use the object.

## State and ordering

The lock has two parts: a count that controls reader/writer access, and a KD spin
**gate** that orders contended writers and slow readers. The count and gate are
both four bytes. They sit on separate cache lines in a 128-byte object aligned to
64 bytes. This separates reader updates from queue polling, but uses more memory
than the original eight-byte layout.

| Count field | Meaning |
| --- | --- |
| Low byte = `0xff` | A writer owns the gate and exclusive write access. |
| Low byte = `0xf0` | A native writer owns exclusive write access without the gate. |
| Bit 8 / WAITING | A writer holds the gate and is waiting for existing holders to finish. |
| Bits 9..31 | Reader count; each reader adds `0x200`. |

### Readers

1. Disable preemption and add to the reader count with acquire ordering.
2. If there are no writer bits, enter the read body immediately.
3. Otherwise, remove that speculative count **before** joining the native gate
   queue. Keeping it while queued could make the writer ahead wait forever for
   this reader to finish.
4. After acquiring the gate, add the reader count again. Wait for any native writer
   that acquired without the gate to release its writer byte. The reader count now
   prevents another such writer from entering. Release the gate, then run the read
   body locally.
5. On read unlock, subtract the count with release ordering and enable preemption.
   The x86 locked SUB avoids computing a return value that the caller does not use.

### Writers

A writer first disables preemption and checks whether the count is zero. If so,
it takes an exact per-CPU nondelegated reference, then tries an acquire
compare-and-swap (CAS) from zero to `0xf0`. Success lets the caller run without
taking the gate. The reference stays live until unlock, so shutdown cannot miss
this writer. A failed CAS drops the reference before taking the gate. Reading the
count before the CAS avoids a failed locked instruction when the lock is visibly
busy.

If the fast attempt fails, the writer takes the KD gate. It then tries to change a
zero count to `0xff`. If readers or a fast writer are still active, it sets WAITING
and waits for them to finish. New readers remove their speculative count and queue
behind the gate while WAITING is set. The writer observes the last holder's release
with acquire ordering before entering its body.

### Write unlock

Write unlock uses a release store to clear **only the low byte**. It must preserve
reader increments and any waiting writer's WAITING bit in the rest of the count.

A writer that acquired without the gate then drops its exact reference and enables
preemption. A gated writer proceeds to the normal KD spin unlock endpoint. Queue
batching, NUMA selection and native fallback follow the existing spin policy;
there is no strict FIFO fairness guarantee.

### Why ABI3 starts after writer admission

Here, **writer admission** means waiting for readers and acquiring exclusive write
access. It happens in native code before the prepared JIT body:

- For local execution, the pinned acquisition helper takes the gate and acquires
  writer admission before returning to the body.
- For delegation, the combiner acquires writer admission before its first JIT
  dispatch for the physical root request.

The prepared body contains the application code and writer-byte release. It does
not contain the reader-drain atomics. In the older ABI1 body, those counter updates
could make the translator lose the pointer facts needed to accept the later RCUHT
list traversal. ABI3 changes the entry boundary while keeping the existing memory
checks. Nested virtual spin requests inherit the packet ABI, but do not acquire a
second rwlock count.

Refusal and completion must preserve this order:

| What happened | Required action |
| --- | --- |
| JIT refused before the body started | Clear the admitted writer byte while still holding the gate. When the waiter receives physical ownership, reacquire writer admission before resuming the prepared body. |
| The body made progress and must finish natively | Keep writer admission and resume from the saved current state. Use the existing packet and unlock-ACK path; do not restart the body. |
| The body completed | The body has already cleared the writer byte before spin completion. Completion must not clear it again, because a successor may now own it. |

The embedded gate's address identifies the lock in the spin registry, heat table,
frames and ownership records. `kd_rwlock_prepare` requires
`KD_ENTRY_ABI_RWLOCK_CLOBBER_V1` (3). Registry, daemon, generated image and frame
must all agree on that identity. Older ABI1 rwlock callers must be rebuilt.
ABI3 keeps the existing IP/SP/BP packet and two-word wrapper input. The reader/writer
count is exact lock state; approximate performance counters cannot replace it.

### Relation to TCLock

The count and admission algorithm derive from
[TCLock's komb_rwlock.c](https://github.com/rs3lab/TCLocks/blob/bbfb9f00a12af51dff6ca291cb9829a82960c2ef/src/kernel/rcuht/locks/komb_rwlock.c).
Both algorithms keep the gate through a contended writer's application body, but
release it before a reader's application body. Both also have a native writer fast
path that skips the gate. KD handles slow readers locally and delegates writers
through JIT; TCLock delegates by switching native stacks. KD retains its existing
packet, source lease, completion and ACK rules.

Production ABI3 uses the same trusted ordinary-callee policy as other current
entries. Historical ABI1-only direct string bridges and checked pointer-load
exits do not become ABI3 features merely by sharing the spin engine. Consult
[translation policy](admission.md) for construction and runtime requirements.

## Scope and lifetime

Readers must finish in bounded time: a spinning writer cannot make a stalled
reader progress. Waiting for readers happens before JIT execution. This API does
not support sleeping bodies, recursive reads, upgrades/downgrades, IRQ/BH variants,
mixing with Linux or TCLock APIs, or general oversubscription. Nested translated
operations keep the existing spin admission limits; ABI3 adds no new nested API.

Keep the lock, protected data and source text alive while any reader, writer,
queued request or frame can use them. For shutdown, stop new calls and join all
callers, then retire sources. Unload the workload and provider only after source
retirement succeeds. The [spin](spin_implementation.md), [frame](frames.md) and
[JIT limitations](../TODO.md) also apply.

[Correctness tests](../../tests/kernel/rwlock/README.md) check simultaneous readers,
writer exclusion, exact updates, worker progress and clean shutdown. They report
native execution, publication and returned JIT bodies separately.

The [benchmark guide](../../bench/rwlock_compare/README.md) compares KD with Linux
Native and TCLock using matched cacheline and hash workloads. The
[RCUHT report](../../bench/results/380G10/bench/rwlock_compare/20261010-rcuht/README.md) gives the
1%/20% results and the remaining performance gaps. The
[initial report](../../bench/results/380G10/bench/rwlock_compare/20261009/README.md) preserves the
older ABI1 hash refusal that ABI3 resolved.
