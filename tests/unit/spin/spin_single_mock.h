/* SPDX-License-Identifier: GPL-2.0 */
#ifndef SPIN_SINGLE_MOCK_H
#define SPIN_SINGLE_MOCK_H
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
/* Guard primitive and KD word both occupy four bytes in this CPU model. */
typedef struct kd_spinlock {
 union { atomic_t val; struct { u8 locked, pending; };
         struct { u16 locked_pending, tail; }; u8 held; };
} raw_spinlock_t;
typedef struct kd_spinlock kd_spinlock_t;
#define KD_SPIN_TYPE_H
#define atomic_set(p, v) ((p)->counter = (v))
#define KD_SPINLOCK_INITIALIZER { .val = { 0 } }
static inline void kd_spin_init(kd_spinlock_t *p) { p->val.counter = 0; }
struct kd_spin_fast_cpu { kd_spinlock_t *held; struct task_struct *owner; unsigned int nondelegated; };
static struct kd_spin_fast_cpu kd_spin_fast_cpu[2];
struct task_struct {
	int pid;
	int migration_disabled;
	char comm[16];
};

static struct task_struct tasks[2];
static struct task_struct *current = &tasks[0];
static int mock_cpu, mock_preempts[2];
static bool mock_irq, mock_in_task = true;
static unsigned int checks;
static unsigned int map_locks;

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

static inline void mock_map_lock(raw_spinlock_t *lock, unsigned long *flags)
{
	map_locks++;
	CHECK(!lock->held);
	lock->held = true;
	*flags = mock_irq;
	mock_irq = true;
	mock_preempt++;
}

static inline void mock_map_unlock(raw_spinlock_t *lock, unsigned long flags)
{
	CHECK(lock->held && mock_irq);
	lock->held = false;
	mock_irq = flags;
	mock_preempt--;
}

#define raw_spin_lock_irqsave(lock, flags) mock_map_lock(lock, &(flags))
#define raw_spin_unlock_irqrestore(lock, flags) mock_map_unlock(lock, flags)

/* Task-only guards must preserve incoming IRQ state without masking it. */
static inline void plain_guard_lock(raw_spinlock_t *lock)
{
	map_locks++;
	CHECK(!lock->held);
	lock->held = true;
	mock_preempt++;
}
static inline void plain_guard_unlock(raw_spinlock_t *lock)
{
	CHECK(lock->held);
	lock->held = false;
	mock_preempt--;
}
#define raw_spin_lock(lock) plain_guard_lock(lock)
#define raw_spin_unlock(lock) plain_guard_unlock(lock)

#endif
