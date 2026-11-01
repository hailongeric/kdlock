/* Production reader publication/recheck and release with deterministic atomic
 * boundaries. These doubles check control ordering and exact count/wake effects;
 * they do not establish a weak-memory proof or exercise concurrent CPUs. */
#include <assert.h>
#include <limits.h>
#include <stdbool.h>
#include <stdio.h>

struct kd_rwsem {
    long readers, admission;
    int reader_drain;
};
static struct kd_rwsem sem;
static unsigned int stage, probes, before, increments, after, rechecks;
static unsigned int decrements, wake_calls, irq_checks, atomic_checks;
static unsigned int race_at;
static long writer_saw_readers;
static bool irq_off, atomic_context;
static bool enqueue_on_empty, enqueuer_rechecked;

static long atomic_long_read(long *counter)
{
    long observed;

    assert(counter == &sem.admission && !stage);
    probes++;
    observed = *counter;
    stage = 1;
    if (race_at == 1) {
        assert(!observed);
        writer_saw_readers = sem.readers;
        sem.admission = -1;
    }
    return observed;
}
static void smp_mb__before_atomic(void)
{ assert(stage == 1); before++; stage = 2; }
static void atomic_long_inc(long *counter)
{
    assert(counter == &sem.readers && stage == 2);
    increments++;
    ++*counter;
    stage = 3;
    if (race_at == 2) {
        assert(!sem.admission);
        writer_saw_readers = sem.readers;
        sem.admission = -1;
    }
}
static void smp_mb__after_atomic(void)
{ assert(stage == 3); after++; stage = 4; }
/* Model the full ordering of the returning atomic primitive. The mutation
 * cases replace it with individual steps to retain ordering controls. */
static long atomic_long_inc_return(long *counter)
{
    smp_mb__before_atomic();
    atomic_long_inc(counter);
    smp_mb__after_atomic();
    return *counter;
}
static long atomic_long_read_acquire(long *counter)
{
    assert(counter == &sem.admission && stage == 4);
    rechecks++;
    stage = 5;
    return *counter;
}
static bool atomic_long_dec_and_test(long *counter)
{
    assert(counter == &sem.readers && stage == 5 && *counter > 0);
    decrements++;
    return --*counter == 0;
}
static bool irqs_disabled(void)
{ irq_checks++; return irq_off; }
static bool in_atomic(void)
{ atomic_checks++; return atomic_context; }
static bool waitqueue_active(int *queue)
{
    assert(queue == &sem.reader_drain && !sem.readers && stage == 5);
    bool active = *queue != 0;
    if (!active && enqueue_on_empty) {
        *queue = 1;
        /* A racing enqueuer observes the fully ordered final decrement at
         * its ordinary post-publication predicate recheck and need not wait. */
        enqueuer_rechecked = !sem.readers;
    }
    return active;
}
static void kd_rwsem_wake(int *queue)
{
    assert(queue == &sem.reader_drain && !sem.readers);
    assert(!irq_off && !atomic_context && stage == 5);
    wake_calls++;
}

#include "rwsem_read_count_production.h"

static void reset(long readers, long phase)
{
    sem.readers = readers;
    sem.admission = phase;
    stage = probes = before = increments = after = rechecks = 0;
    decrements = wake_calls = irq_checks = atomic_checks = race_at = 0;
    writer_saw_readers = -1;
    irq_off = atomic_context = false;
    sem.reader_drain = 1;
    enqueue_on_empty = enqueuer_rechecked = false;
}

int main(void)
{
    const long closed[] = {-1, 1, LONG_MAX};
    unsigned int cases = 0;

    for (unsigned int i = 0; i < sizeof(closed) / sizeof(closed[0]); i++) {
        reset(3, closed[i]);
        assert(!kd_down_read_trylock(&sem));
        assert(probes == 1 && stage == 1 && sem.readers == 3);
        assert(!before && !increments && !after && !rechecks && !decrements);
        assert(!irq_checks && !atomic_checks && !wake_calls);
        cases++;
    }
    for (unsigned int prior = 0; prior <= 1; prior++) {
        reset(prior, 0);
        assert(kd_down_read_trylock(&sem));
        assert(stage == 5 && probes == 1 && before == 1 && increments == 1);
        assert(after == 1 && rechecks == 1 && !decrements && !wake_calls);
        assert(sem.readers == (long)prior + 1 && !sem.admission);
        kd_up_read(&sem);
        assert(sem.readers == (long)prior && decrements == 1);
        assert(wake_calls == !prior && irq_checks == !prior && atomic_checks == !prior);
        cases++;
    }
    for (unsigned int race = 0; race < 2; race++) {
        reset(0, 0); sem.reader_drain = 0; enqueue_on_empty = race;
        assert(kd_down_read_trylock(&sem));
        kd_up_read(&sem);
        assert(!sem.readers && decrements == 1);
        assert(!irq_checks && !atomic_checks && !wake_calls);
        assert(enqueuer_rechecked == (race != 0));
        cases++;
    }
    /* A writer can close between the first observation and publication, or
     * after publication before the acquire recheck. Both readers withdraw
     * exactly once; the latter writer saw a reader it must drain. */
    for (unsigned int race = 1; race <= 2; race++) {
        for (unsigned int prior = 0; prior <= 1; prior++) {
            for (unsigned int context = 0; context < 4; context++) {
                reset(prior, 0);
                race_at = race;
                irq_off = context & 1;
                atomic_context = context & 2;
                assert(!kd_down_read_trylock(&sem));
                assert(probes == 1 && before == 1 && increments == 1);
                assert(after == 1 && rechecks == 1 && decrements == 1);
                assert(sem.readers == (long)prior && sem.admission == -1);
                assert(writer_saw_readers == (long)prior + (race == 2));
                assert(irq_checks == !prior);
                assert(atomic_checks == (!prior && !irq_off));
                assert(wake_calls == (!prior && !irq_off && !atomic_context));
                cases++;
            }
        }
    }
    printf("PASS rwsem reader count: %u deterministic admission/release cases\n", cases);
    return 0;
}
