#ifndef __QUEUED_SPINLOCK_INTERNAL_H__
#define __QUEUED_SPINLOCK_INTERNAL_H__

#include <linux/smp.h>
#include <linux/bug.h>
#include <linux/percpu.h>
#include <linux/hardirq.h>
// #include <linux/prefetch.h>
#include <linux/atomic.h>
#include <asm/byteorder.h>
// #include "mcs_spinlock.h"

#ifndef CONFIG_PARAVIRT
#include <linux/types.h>
#include <linux/atomic.h>
#endif

/**
 * smp_cond_load_relaxed() - (Spin) wait for cond with no ordering guarantees
 * @ptr: pointer to the variable to wait on
 * @cond: boolean expression to wait for
 *
 * Equivalent to using READ_ONCE() on the condition variable.
 *
 * Due to C lacking lambda expressions we load the value of *ptr into a
 * pre-named variable @VAL to be used in @cond.
 */
#ifndef smp_cond_load_relaxed
#define smp_cond_load_relaxed(ptr, cond_expr) \
	({                                        \
		typeof(ptr) __PTR = (ptr);            \
		typeof(*ptr) VAL;                     \
		for (;;)                              \
		{                                     \
			VAL = READ_ONCE(*__PTR);          \
			if (cond_expr)                    \
				break;                        \
			cpu_relax();                      \
		}                                     \
		VAL;                                  \
	})
#endif

#ifndef atomic_cond_read_relaxed
#define atomic_cond_read_relaxed(v, c) smp_cond_load_relaxed(&(v)->counter, (c))
#endif

struct orig_qspinlock
{
	union
	{
		atomic_t val;

		/*
		 * By using the whole 2nd least significant byte for the
		 * pending bit, we can allow better optimization of the lock
		 * acquisition for the pending bit holder.
		 */
#ifdef __LITTLE_ENDIAN
		struct
		{
			u8 locked;
			u8 pending;
		};
		struct
		{
			u16 locked_pending;
			u16 tail;
		};
#else
		struct
		{
			u16 tail;
			u16 locked_pending;
		};
		struct
		{
			u8 reserved[2];
			u8 pending;
			u8 locked;
		};
#endif
	};
};

/*
 * Initializier
 */
#ifndef __ORIG_QSPIN_LOCK_UNLOCKED
#define __ORIG_QSPIN_LOCK_UNLOCKED \
	{                              \
		.val = ATOMIC_INIT(0)}
#endif

/*
 * Bitfields in the atomic value:
 *
 * When NR_CPUS < 16K
 *  0- 7: locked byte
 *     8: pending
 *  9-15: not used
 * 16-17: tail index
 * 18-31: tail cpu (+1)
 *
 * When NR_CPUS >= 16K
 *  0- 7: locked byte
 *     8: pending
 *  9-10: tail index
 * 11-31: tail cpu (+1)
 */
#define _Q_SET_MASK_HL(type) (((1U << _Q_##type##_BITS_HL) - 1) << _Q_##type##_OFFSET_HL)
#define _Q_LOCKED_OFFSET_HL 0
#define _Q_LOCKED_BITS_HL 8
#define _Q_LOCKED_MASK_HL _Q_SET_MASK_HL(LOCKED)

#define _Q_PENDING_OFFSET_HL (_Q_LOCKED_OFFSET_HL + _Q_LOCKED_BITS_HL)
#if CONFIG_NR_CPUS < (1U << 14)
#define _Q_PENDING_BITS_HL 8
#else
#define _Q_PENDING_BITS_HL 1
#endif
#define _Q_PENDING_MASK_HL _Q_SET_MASK_HL(PENDING)

#define _Q_TAIL_IDX_OFFSET_HL (_Q_PENDING_OFFSET_HL + _Q_PENDING_BITS_HL)
#define _Q_TAIL_IDX_BITS_HL 2
#define _Q_TAIL_IDX_MASK_HL _Q_SET_MASK_HL(TAIL_IDX)

#define _Q_TAIL_CPU_OFFSET_HL (_Q_TAIL_IDX_OFFSET_HL + _Q_TAIL_IDX_BITS_HL)
#define _Q_TAIL_CPU_BITS_HL (32 - _Q_TAIL_CPU_OFFSET_HL)
#define _Q_TAIL_CPU_MASK_HL _Q_SET_MASK_HL(TAIL_CPU)

#define _Q_TAIL_OFFSET_HL _Q_TAIL_IDX_OFFSET_HL
#define _Q_TAIL_MASK_HL (_Q_TAIL_IDX_MASK_HL | _Q_TAIL_CPU_MASK_HL)

#define _Q_LOCKED_VAL_HL (1U << _Q_LOCKED_OFFSET_HL)
#define _Q_PENDING_VAL_HL (1U << _Q_PENDING_OFFSET_HL)

#ifndef _Q_PENDING_LOOPS_HL
#define _Q_PENDING_LOOPS_HL 1
#endif


/*
 * Bitfields in the non-atomic socket_and_count value:
 * 0- 1: queue node index (always < 4)
 * 2-31: socket id
 */
#define _Q_IDX_OFFSET 0
#define _Q_IDX_BITS 2
#define _Q_IDX_MASK _Q_SET_MASK_HL(IDX)
#define _Q_NODE_OFFSET (_Q_IDX_OFFSET + _Q_IDX_BITS)

#endif /* __QUEUED_SPINLOCK_INTERNAL_H__ */
