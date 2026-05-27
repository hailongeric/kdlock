#ifndef _LINUX_KD_MUTEX_H
#define _LINUX_KD_MUTEX_H

/*
 * kd_mutex — TCLocks-style mutex delegation protocol.
 *
 * Ported from TCLocks komb_mutex.h.  The kd_mutex is a shadow lock that sits
 * beside the kernel's struct mutex; the kdlock hooks in kd_lock.c map each
 * struct mutex * to a struct kd_mutex *.
 *
 * Protocol overview:
 *   Lock:   fastpath cmpxchg(locked, 0→1).  On contention, the waiter is
 *           queued via a linked list (tail pointer), spins on node->locked,
 *           and either has its CS executed by the combiner or becomes the
 *           combiner itself.
 *   Unlock: if the combiner holds the lock, it context-switches to the next
 *           waiter (chaining) or back to its own shadow stack (end-of-batch).
 *           Out-of-order unlock is detected and flagged as OOO.
 */

#define KD_MUTEX_SHADOW_STACK_SIZE 8192L

#include "combiner.h"

/*
 * kd_mutex_node — per-waiter queue node.
 *
 * One per-CPU node is allocated (kd_mutex_nodes).  During the slowpath the
 * node is initialised with the waiter's state and linked into the mutex
 * queue.  The combiner switches to the waiter's stack via node->rsp.
 */
struct kd_mutex_node {
	struct kd_mutex_node *next;      /* next waiter in queue              */
	struct kd_mutex_node *next_rwsem;/* rwsem extension (unused)          */
	struct kd_mutex_node *tail;      /* self-pointer for cmpxchg          */

	int socket_id;                   /* NUMA node id                      */
	int cpuid;                       /* CPU that owns this node           */

	uint64_t rsp;                    /* saved stack pointer for ctx switch */
	struct task_struct *task_struct_ptr; /* owning task                   */
	void *lock;                      /* back-pointer to kd_mutex          */

	char dummy1[80];                 /* padding to avoid false sharing    */

	union {
		atomic_long_t val;       /* atomic access to whole word      */
		atomic_long_t cnts;
		struct {
			u8 completed;    /* KD_MUTEX_WAITER_* state          */
			u8 locked;       /* spin flag for waiter              */
			u8 __unused[6];
		};
		struct {
			u16 locked_completed; /* 16-bit access               */
			u8 __unused1[6];
		};
		struct {
			u16 wlocked;
			u8 rcount[6];
		};
	};

	char dummy[16];                  /* further padding                   */
};

/*
 * kd_mutex — the shadow lock itself.
 *
 * One kd_mutex is embedded in each kd_mutex_shadow_entry (see kd_lock.c).
 * The locked field doubles as the fastpath cmpxchg target.
 */
struct kd_mutex {
	struct kd_mutex_node *tail;      /* queue tail (NULL if empty)        */
	union {
		atomic_t state;          /* full-state atomic access          */
		struct {
			u8 locked;       /* 1 = held, 3 = combiner, 7 = OOO  */
		};
	};
	struct task_struct *combiner_task; /* task currently acting as combiner */
};

#define __KD_MUTEX_INITIALIZER(lockname) \
	{ .tail = NULL, .state = ATOMIC_INIT(0), .combiner_task = NULL }

#define DEFINE_KD_MUTEX(mname) \
	struct kd_mutex mname = __KD_MUTEX_INITIALIZER(mname)

void kd_mutex_init(struct kd_mutex *lock);
void kd_mutex_init_percpu(void);
void kd_mutex_exit(void);

static inline bool _kd_mutex_is_locked(struct kd_mutex *lock)
{
	return !!READ_ONCE(lock->locked);
}

void _kd_mutex_lock(struct kd_mutex *lock);
void _kd_mutex_lock_rwsem_writer(struct kd_mutex *lock);
int __must_check _kd_mutex_lock_interruptible(struct kd_mutex *lock);
int __must_check _kd_mutex_lock_killable(struct kd_mutex *lock);

#define _kd_mutex_lock_nested(lock, subclass) _kd_mutex_lock(lock)
#define kd_mutex_lock_interruptible_nested(lock, subclass) \
	_kd_mutex_lock_interruptible(lock)
#define kd_mutex_lock_killable_nested(lock, subclass) \
	_kd_mutex_lock_killable(lock)
#define _kd_mutex_lock_nest_lock(lock, nest_lock) _kd_mutex_lock(lock)

int _kd_mutex_trylock(struct kd_mutex *lock);
void _kd_mutex_unlock(struct kd_mutex *lock);

#endif /* _LINUX_KD_MUTEX_H */
