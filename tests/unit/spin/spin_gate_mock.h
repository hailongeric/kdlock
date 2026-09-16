/* SPDX-License-Identifier: GPL-2.0 */
#ifndef SPIN_GATE_MOCK_H
#define SPIN_GATE_MOCK_H
/* Minimal two-CPU/type/atomic substitutes shared by extracted C fixtures.
 * Their deterministic results are not Linux memory-ordering guarantees. */
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef __LITTLE_ENDIAN
#define __LITTLE_ENDIAN 1
#endif

typedef uint8_t u8;
typedef uint16_t u16;
typedef struct {
	int counter;
} atomic_t;
typedef struct {
	bool held;
} raw_spinlock_t;
struct task_struct {
	int pid;
	int migration_disabled;
	char comm[16];
};

static struct task_struct tasks[2];
static struct task_struct *current = &tasks[0];
static int mock_cpu, mock_preempts[2];
static bool mock_irq, mock_in_task = true;
static unsigned int native_claims, native_releases, checks;

#define mock_preempt mock_preempts[mock_cpu]
#define CHECK(condition)           \
	do {                       \
		assert(condition); \
		checks++;          \
	} while (0)
#define READ_ONCE(value) (value)
#define WRITE_ONCE(value, new) ((value) = (new))
#define PREEMPT_MASK 0xff
#define preempt_count() mock_preempt
#define raw_smp_processor_id() mock_cpu
#define irqs_disabled() mock_irq
#define in_task() mock_in_task
#define atomic_read(value) ((value)->counter)
#define DEFINE_RAW_SPINLOCK(name) raw_spinlock_t name
#define __percpu
#define this_cpu_ptr(p) (&(p)[mock_cpu])
#define per_cpu_ptr(p, cpu) (&(p)[cpu])
#define for_each_possible_cpu(cpu) for ((cpu) = 0; (cpu) < 2; (cpu)++)
#define raw_spin_lock_init(lock) ((lock)->held = false)
#define preempt_disable() (mock_preempt++)
#define preempt_enable()                 \
	do {                             \
		CHECK(mock_preempt > 0); \
		mock_preempt--;          \
	} while (0)
#define spin_release(...) ((void)0)
#define cmpxchg(p, expected, value)        \
	({                                 \
		__auto_type before = *(p); \
		if (before == (expected))  \
			*(p) = (value);    \
		before;                    \
	})

static unsigned long hash_long(unsigned long key, unsigned int bits)
{
	(void)key;
	(void)bits;
	return 0; /* Force all map entries through the same probe chain. */
}

static void mock_map_lock(raw_spinlock_t *lock, unsigned long *flags)
{
	CHECK(!lock->held);
	lock->held = true;
	*flags = mock_irq;
	mock_irq = true;
	mock_preempt++;
}

static void mock_map_unlock(raw_spinlock_t *lock, unsigned long flags)
{
	CHECK(lock->held && mock_irq);
	lock->held = false;
	mock_irq = flags;
	mock_preempt--;
}

#define raw_spin_lock_irqsave(lock, flags) mock_map_lock(lock, &(flags))
#define raw_spin_unlock_irqrestore(lock, flags) mock_map_unlock(lock, flags)

static void kd_preempt_disable_raw_spin_lock(raw_spinlock_t *lock)
{
	CHECK(!lock->held && mock_preempt > 0);
	lock->held = true;
	native_claims++;
}

static void do_raw_spin_unlock(raw_spinlock_t *lock)
{
	CHECK(lock->held && mock_preempt > 0);
	lock->held = false;
	native_releases++;
}
#endif
