#ifndef KD_FUTEX_H
#define KD_FUTEX_H

/*
 * kd_futex.h — futex internal types and delegation constants.
 *
 * These are copies of kernel-internal futex structures needed by the
 * kdlock futex delegation engine (kd_futex.c).  They must match the
 * patched kernel's definitions.
 */

#include <linux/freezer.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>
#include <linux/sched/task_stack.h>
#include <linux/string.h>
#include <linux/kernel.h>
#include <asm/barrier.h>
#include <linux/futex.h>
#include <linux/rtmutex.h>
#include <linux/sched/wake_q.h>
#include <linux/types.h>
#include <linux/restart_block.h>
#include <linux/lockdep.h>
#include <linux/mutex.h>
#include <linux/spinlock.h>

#ifdef CONFIG_PREEMPT_RT
#include <linux/rcuwait.h>
#endif

#include <asm/futex.h>

/* --- futex internal structures (mirrored from kernel/futex/) ------------- */

struct futex_hash_bucket {
	atomic_t waiters;
	spinlock_t lock;
	struct plist_head chain;
} ____cacheline_aligned_in_smp;

struct futex_pi_state {
	struct list_head list;
	struct rt_mutex_base pi_mutex;
	struct task_struct* owner;
	refcount_t refcount;
	union futex_key key;
} __randomize_layout;

struct futex_q {
	struct plist_node list;
	struct task_struct* task;
	spinlock_t* lock_ptr;
	union futex_key key;
	struct futex_pi_state* pi_state;
	struct rt_mutex_waiter* rt_waiter;
	union futex_key* requeue_pi_key;
	u32 bitset;
	atomic_t requeue_state;
#ifdef CONFIG_PREEMPT_RT
	struct rcuwait requeue_wait;
#endif
} __randomize_layout;

enum {
	Q_REQUEUE_PI_NONE = 0,
	Q_REQUEUE_PI_IGNORE,
	Q_REQUEUE_PI_IN_PROGRESS,
	Q_REQUEUE_PI_WAIT,
	Q_REQUEUE_PI_DONE,
	Q_REQUEUE_PI_LOCKED,
};

#define FLAGS_SHARED           0x00
#define FLAGS_HAS_TIMEOUT      0x04

enum futex_access {
	FUTEX_READ,
	FUTEX_WRITE
};

/* --- futex inline helpers ------------------------------------------------ */

static inline int futex_match(union futex_key* key1, union futex_key* key2)
{
	return (key1 && key2
		&& key1->both.word == key2->both.word
		&& key1->both.ptr == key2->both.ptr
		&& key1->both.offset == key2->both.offset);
}

static inline int futex_hb_waiters_pending(struct futex_hash_bucket* hb)
{
#ifdef CONFIG_SMP
	smp_mb();
	return atomic_read(&hb->waiters);
#else
	return 1;
#endif
}

static inline void futex_hb_waiters_inc(struct futex_hash_bucket* hb)
{
#ifdef CONFIG_SMP
	atomic_inc(&hb->waiters);
	smp_mb__after_atomic();
#endif
}

static inline void futex_hb_waiters_dec(struct futex_hash_bucket* hb)
{
#ifdef CONFIG_SMP
	atomic_dec(&hb->waiters);
#endif
}

extern void __futex_queue(struct futex_q* q, struct futex_hash_bucket* hb);

static inline void futex_queue(struct futex_q* q, struct futex_hash_bucket* hb)
	__releases(&hb->lock)
{
	__futex_queue(q, hb);
	spin_unlock(&hb->lock);
}

/* --- delegation constants ------------------------------------------------- */

#define KD_WAKER                 20
#define KD_WAKE_NUM              20
#define KD_FAST_PATH_WAKE_NUM    20
#define KD_SLOW_PATH_WAKE_NUM    20
#define KD_CNT_NUM               40
#define KD_E_QUEUE_NUM           20

#define fast_path_uninit           0
#define fast_path_ready            1
#define fast_path_success          2
#define fast_path_fail             3
#define fast_path_timeout          4
#define fast_path_no_need_to_sleep 5

#define fast_wake_ready            6
#define fast_wake_success          7
#define fast_wake_timeout          8
#define fast_to_slow_wake          9

/* --- futex delegation helpers (kd_futex.c) -------------------------------- */

#include "exe.h"

#define prefetch_up_size   2
#define prefetch_down_size 1

void __nf_futex_queue(struct futex_q* q, struct futex_hash_bucket* hb,
		      struct task_struct* task);
void print_regs(struct pt_regs* regs);
void add_uaddr(unsigned long u);
void record_ret(int ret);
int check_numa_node(struct futex_q* q, int node);
void kd_call_q(struct wake_q_head* wake_q, struct kd_exe_ret* r);
void kd_call(struct task_struct* task, struct kd_exe_ret* r);
void kd_prefetch_context(struct pt_regs* regs, unsigned long rsp);
void kd_cldemote_context(struct pt_regs* regs, unsigned long rsp);
void not_wake_up_q(struct wake_q_head* wake_q);

int new_futex_wake1(u32 __user* uaddr, unsigned int flags, int nr_wake,
		    u32 bitset);

#define __set_task_state(task, state_value)				\
	do {								\
		debug_normal_state_change((state_value));		\
		WRITE_ONCE((task)->__state, (state_value));		\
	} while (0)

#define set_task_state(task, state_value)				\
	do {								\
		debug_normal_state_change((state_value));		\
		smp_store_mb((task)->__state, (state_value));		\
	} while (0)

#endif /* KD_FUTEX_H */
