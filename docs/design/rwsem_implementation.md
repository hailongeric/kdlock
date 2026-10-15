# Sleeping KD reader/writer semaphore

[`kd_rwsem.h`](../../include/kd_rwsem.h) adds an ordinary task-context sleeping
API alongside the existing spinning `kd_rwlock`. It uses the current owned
`kd_mutex` as its admission gate. This is an explicit KD object; no caller may
pass it, or its gate, to Linux lock APIs. All users must adopt the same API and
keep the object alive until both callers and delegated frames have drained.

## API and scope

`DEFINE_KD_RWSEM()` and `kd_rwsem_init()` support static and dynamic
initialization. `kd_down_read()` / `kd_up_read()` allow concurrent, sleeping
readers. `kd_down_write()` / `kd_up_write()` provide ordinary physical writer
ownership. Read and write trylocks return 1 on success and 0 on failure.
`kd_downgrade_write()` converts an ordinary writer into a reader atomically;
finish with `kd_up_read()`. `kd_rwsem_is_idle()` is a quiescent inspection helper,
not an admission primitive or a substitute for provider/frame drain.

There is no killable/interruptible acquisition, reader-to-writer upgrade,
recursive locking guarantee, non-owner release or IRQ/BH API. The Linux mmap
integration remains separate: its killable waits, fault/VMA lifetimes, lock-mode
changes and task-dependent operations require additional work. Ordinary sleeping
acquisition alone does not establish that `access_remote_vm()` can delegate.

## Admission and memory ordering

The mutex gates admission, while an atomic count records readers that have
entered. A reader first observes the entire owner word as zero, publishes its
count with a fully ordered increment, and rechecks the owner word with acquire
ordering. If a writer arrived, the reader rolls back without accessing protected
data. Queue/handoff flags also close this fast path. A slow reader acquires the
ordinary SELF mutex, increments the count and releases it without combining.

A writer acquires and retains the gate, executes a full barrier, and sleeps on a
wait queue until the reader count reaches zero. The reader's increment/recheck
and writer's gate/barrier/count check prevent both sides from missing each
other. Speculative reader counts can overlap an executing writer, but those
readers cannot access its payload. The last reader's fully ordered decrement
precedes `waitqueue_active()` and wakeup, pairing with the waiter's enqueue and
condition recheck to avoid lost wakeups. A downgrade publishes its reader count
before releasing the gate, so the next writer must wait for it.

This construction follows the gate/count organization of the existing TCLock
rwlock port, replacing spinning writer admission/drain with the owned mutex and
a wait queue. It is not a port of Linux's optimized rwsem reader batching,
optimistic spinning or fairness implementation. No throughput advantage follows
from the construction alone.

## Delegated writers

Prepare an explicit writer entry with `kd_rwsem_prepare()`, then pair
`KD_RWSEM_OUTER_WRITE_LOCK()` with `KD_RWSEM_OUTER_WRITE_UNLOCK()` using a local
`struct kd_owned_mutex_outer_cookie`. The interface reuses the owned mutex ABI2
or ABI4, immutable images, request/result parking and FULL/ACK lifetime handling.
The comparison workload uses ABI4.

```c
/* Compile this caller with KD_OWNED_MUTEX_CABI=1 for ABI4. */
#include <linux/objtool.h>
#include "kd_rwsem.h"
static DEFINE_KD_RWSEM(sem);
static unsigned long value;
extern char update_entry[];

static __attribute__((noipa)) void update(void)
{
    struct kd_owned_mutex_outer_cookie cookie;
    KD_RWSEM_OUTER_WRITE_LOCK(&sem, cookie,
        ".globl update_entry\nupdate_entry:\n\t" ANNOTATE_NOENDBR);
    value++;
    KD_RWSEM_OUTER_WRITE_UNLOCK(&sem, cookie);
}
/* Once the module is LIVE, before starting callers: */
/* kd_rwsem_prepare(&sem, KD_OWNED_MUTEX_PREPARE_IP(update_entry),
                    KD_OWNED_MUTEX_ENTRY_ABI); */
```

The physical writer waits for readers before its critical section. A delegated
entry receives the existing synthetic zero owner cookie and inherits that
writer's exclusion, skipping the native-only reader-drain call. The physical
writer retains the admission gate throughout the entire delegated batch.
Ordinary slow-reader SELF waiters stop the batch; their ordinary unlock cannot
combine. Consequently an admitted reader cannot appear between two delegated
writers in one batch. An ordinary writer may take over the queue, but its
ordinary unlock also cannot begin a batch.

Only outer writers delegate. Readers run locally. An outer writer must use its
matching outer unlock and cannot downgrade. As for owned mutexes, acquisition
can sleep; arbitrary sleeping calls or task-dependent code inside a translated
body are not thereby admitted. Translation and execution-context checks remain
unchanged. Do not bypass those checks or directly use the embedded gate.
Use the outer API at an actual outer boundary with no enclosing lock, including
a read acquisition; use ordinary writer acquisition for nested call paths.

See the [ordinary API probe](../../tests/kernel/rwsem/README.md) and
[comparison runner](../../bench/rwlock_compare/README.md) for separate scheduler,
correctness, actual returned-JIT and performance evidence.
