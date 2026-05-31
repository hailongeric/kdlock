#ifndef _LINUX_KD_MUTEX_H
#define _LINUX_KD_MUTEX_H

/*
 * kd_mutex — JIT-sandbox mutex delegation protocol.
 *
 * Follows the same JIT execution model as kd_spinlock: the combiner calls
 * kd_exe_on_call_hl() with the waiter's saved pt_regs, the translated sandbox
 * runs the critical section, and returns KD_EXE_RUN_TO_UNLOCK when it reaches
 * mutex_unlock.  No raw context switches — all CS execution is sandboxed.
 *
 * The kd_mutex is a shadow lock that sits beside the kernel's struct mutex;
 * kd_lock.c maps each struct mutex * to a struct kd_mutex *.
 */

#define KD_MUTEX_SHADOW_STACK_SIZE  8192L
#define KD_MUTEX_MAX_NODES          4       /* per-CPU nesting depth */

#include "combiner.h"
#include <asm/ptrace.h>

/*
 * kd_mutex_node — per-waiter queue node.
 *
 * One per-CPU array of KD_MUTEX_MAX_NODES nodes is allocated.  During the
 * slowpath the node is initialised with the waiter's state and linked into
 * the queue.  The combiner feeds node->regs into kd_exe_on_call_hl() to
 * execute the waiter's critical section inside the JIT sandbox.
 */
struct kd_mutex_node {
	struct kd_mutex_node *next;
	int tail;                        /* encoded tail (cpu+idx)            */
	int count;                       /* nesting refcount                  */
	int socket_id;                   /* NUMA node id                      */
	int cpuid;                       /* CPU that owns this node           */
	uint64_t rsp;                    /* saved stack pointer (for restore)  */
	struct kd_mutex *lock;
	struct task_struct *task_struct_ptr;
	int irqs_disabled;

	union {
		struct { u8 completed; u8 locked; };
		struct { u16 locked_completed; };
	};

	struct pt_regs regs;             /* waiter context → JIT sandbox      */
};

/*
 * kd_mutex — the shadow lock itself.
 */
struct kd_mutex {
	struct kd_mutex_node *tail;      /* queue tail (NULL if empty)        */
	union {
		atomic_t state;
		struct { u8 locked; };
	};
	struct task_struct *combiner_task;
};

#define __KD_MUTEX_INITIALIZER(lockname) \
	{ .tail = NULL, .state = ATOMIC_INIT(0), .combiner_task = NULL }

#define DEFINE_KD_MUTEX(mname) \
	struct kd_mutex mname = __KD_MUTEX_INITIALIZER(mname)

void kd_mutex_init(struct kd_mutex *lock);
void kd_mutex_init_percpu(void);
void kd_mutex_exit(void);

void _kd_mutex_lock(struct kd_mutex *lock, unsigned long rsp_value);
void _kd_mutex_unlock(struct kd_mutex *lock);
int  _kd_mutex_trylock(struct kd_mutex *lock);

#endif /* _LINUX_KD_MUTEX_H */
