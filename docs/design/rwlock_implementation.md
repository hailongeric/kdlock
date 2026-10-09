# KD read-write lock

[kd_rwlock.h](../../include/kd_rwlock.h) provides an x86_64 task-context
reader/writer spin lock. Multiple readers execute locally at the same time.
Contended writers can delegate their entire critical section through KD's existing
spin JIT engine. Unprepared, cold, refused and explicitly native calls retain the
same reader/writer exclusion protocol.

The reader count and admission protocol derive from
[TCLock's komb_rwlock.c](https://github.com/rs3lab/TCLocks/blob/bbfb9f00a12af51dff6ca291cb9829a82960c2ef/src/kernel/rcuht/locks/komb_rwlock.c).
TCLock keeps its contended writer gate across the application body and releases
its reader admission gate before the application read body. KD uses that same
separation, with local slow-reader admission and JIT writer execution. Every KD
writer takes the embedded gate; TCLock also has a separate ungated writer fast
path. No TCLock native stack-switching code or new runtime backend is needed.

## State and ordering

The eight-byte `kd_rwlock_t` contains a four-byte count and a four-byte KD spin
gate. The count's low byte holds writer ownership (`0xff`), bit 8 represents a
waiting writer, and bits 9..31 count readers in units of `0x200`.

1. A reader pins preemption and increments the count with acquire ordering.
   With no writer bits it enters immediately. Otherwise it withdraws that
   speculative increment **before** joining the native gate queue. Once it owns
   the gate it adds its reader count and releases the gate, retaining its pin
   until read unlock. Every writer also owns the gate, so admission cannot
   overlap an active writer. Read unlock decrements with release ordering.
2. A writer takes the gate through the ordinary KD spin API. It changes a zero
   count to writer ownership, or publishes WAITING and waits for existing
   readers to drain. New readers withdraw and queue while WAITING is set. An
   acquire observation of the final reader's release precedes the writer body.
3. Write unlock release-stores zero to **only the low byte**, preserving
   speculative reader increments, then reaches the ordinary KD spin unlock
   endpoint. The gate serializes writers and queues slow readers. Batching,
   NUMA grouping and native fallbacks retain the existing spin policy; strict
   FIFO fairness is not promised.

The prepared continuation starts immediately after gate acquisition and includes
writer admission, the application body and the writer-byte release. A JIT
combiner executes all three before completing the spin unlock endpoint. The
waiter resumes after that endpoint, so it cannot accidentally clear a successor's
writer state. An unstarted refusal executes the same admission/body locally;
partial native continuation uses the existing exact packet and ACK handling.

The gate address is the spin registry, heat, frame and ownership identity.
`kd_rwlock_prepare` registers that address with spin clobber-v1 ABI1. The reader
count remains ordinary shared lock state; it is never an approximate profiling
counter or a separate completion signal. No daemon, wrapper or registry ABI
changes are required.

## Public API

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

After the source module is LIVE and before starting workers, prepare with
`kd_rwlock_prepare(&rw, (unsigned long)update_entry, KD_ENTRY_ABI_SPIN_CLOBBER_V1)`.
Preparation registers the source; daemon publication and hot contended admission
are still necessary for actual delegation. Use one unique named continuation in
each `noipa` writer function. Runtime initialization is `kd_rwlock_init(&rw)` on
an unused, drained object.

`kd_write_lock`/`kd_write_unlock` provide an explicitly native writer pair for
callers that do not need delegation. These can coexist with delegating writers
on the same object, but each acquisition must use its matching unlock API.
Readers always use `kd_read_lock`/`kd_read_unlock`. Each pair pins preemption
once and preserves IRQ/BH state.

## Scope and lifetime

This is a spinning lock, not a sleeping rwsem. Bodies must not sleep. Recursive
reads, upgrades/downgrades, IRQ/BH variants, Linux-lock mixing, and general
oversubscription are unsupported. Nested translated operations retain existing
spin admission limits; this addition does not extend the nested control ABI.
The JIT writer admission loop shares the existing finite branch budget, so
unbounded reader holds are outside the supported execution contract.

Keep lock storage, reader data and source text alive through all readers,
writers, queued requests and retained frames. Stop callers and join them before
source retirement; successful retirement must precede workload/provider unload.
The inherited [spin](spin_implementation.md), [frame](frames.md) and
[JIT limitations](../TODO.md) remain applicable.

[The tests](../../tests/kernel/rwlock/README.md) distinguish native controls,
publication and actual returned JIT bodies, and verify reader overlap, writer
exclusion, exact updates, per-worker progress and final drain.

The [rwlock benchmark](../../bench/rwlock_compare/README.md) compares KD with
Linux native and the TCLock rwlock port using shared cacheline and hash workloads,
read/write mixes and warmed timed windows.
The [measured comparison](../../bench/rwlock_compare/results/20261009/README.md)
records the gains for larger write-only bodies, balanced-mix delegation costs,
and the current hash-writer JIT address-admission refusal.
