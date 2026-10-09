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
separation, with local slow-reader admission and JIT writer execution. Both have
an ungated native writer fast path. KD retains its existing packet, source lease,
completion and ACK protocol; it does not use TCLock stack switching.

## State and ordering

The 128-byte, 64-byte-aligned `kd_rwlock_t` places its four-byte count and
four-byte KD spin gate on separate cache lines. This keeps queue polling apart
from reader increments, at the cost of a larger object than the original
eight-byte layout. The count's low byte distinguishes gated writer ownership
(`0xff`) from an ungated native writer (`0xf0`); bit 8 represents a waiting
writer, and bits 9..31 count readers in units of `0x200`.

1. A reader pins preemption and increments the count with acquire ordering.
   With no writer bits it enters immediately. Otherwise it withdraws that
   speculative increment **before** joining the native gate queue. Once it owns
   the gate it adds its reader count, waits for any ungated writer to release,
   then releases the gate. Its count prevents a new ungated writer from entering.
   It retains its preemption pin until read unlock, which uses a release-ordered
   locked SUB without computing an unused return value.
2. A pinned writer first tries a zero-count CAS to `0xf0`. This native fast path
   keeps an exact per-CPU nondelegated acquisition reference until release. A
   preliminary count read avoids a failed locked CAS when the object is busy.
3. A writer that misses the fast path takes the KD gate. It changes a zero
   count to `0xff`, or publishes WAITING and waits for existing readers and any
   ungated writer to drain. New readers withdraw and queue while WAITING is
   set. An acquire observation of the last release precedes the writer body.
4. Write unlock release-stores zero to **only the low byte**, preserving
   speculative reader increments and any queued writer's WAITING bit. An ungated
   writer drops its exact acquisition reference and preemption pin. A gated
   writer reaches the ordinary KD spin unlock endpoint. Batching, NUMA grouping
   and native fallbacks retain the existing spin policy; strict FIFO fairness
   is not promised.

The prepared ABI3 continuation starts **after writer admission** and contains the
application body and writer-byte release. A native pinned acquisition helper
acquires the gate and count before returning. For a delegated physical root,
the combiner acquires the count before its first JIT dispatch. Virtual nested
spin requests inherit the packet ABI without acquiring a second writer count.
This keeps reader-drain atomics outside translated payload analysis and avoids
false alias widening when an RCUHT writer subsequently follows list pointers.

A pre-body refusal clears the admitted writer byte while the physical gate is
still held. When that waiter becomes queue owner, its native retry reacquires
writer admission before jumping to the prepared body. A progressed native
continuation retains admission through its existing exact packet and ACK path.
Successful bodies clear the writer byte before the spin completion endpoint;
completion must never clear it a second time after a successor can run.

The gate address remains the spin registry, heat, frame and ownership identity.
`kd_rwlock_prepare` uses `KD_ENTRY_ABI_RWLOCK_CLOBBER_V1` (3), with the existing
IP/SP/BP clobber packet and two-word wrapper input. Registry, daemon, generated
image and frame must agree on ABI3. The count is exact shared lock state, never
an approximate profiling counter. Older ABI1 rwlock callers must be rebuilt.

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
`kd_rwlock_prepare(&rw, (unsigned long)update_entry, KD_ENTRY_ABI_RWLOCK_CLOBBER_V1)`.
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
Reader admission drains in native code before the JIT body. Readers must still
finish in bounded time; this spinning lock cannot make a stalled reader progress.

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
The [RCUHT comparison](../../bench/rwlock_compare/results/20261010-rcuht/README.md)
records the current 1%/20% write mixes and strict performance target. The
[initial comparison](../../bench/rwlock_compare/results/20261009/README.md) retains
the historical ABI1 hash-writer admission refusal, resolved by ABI3.
