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
 *
 * IMPORTANT: the nesting refcount (count) lives ONLY in nodes[0].  All
 * increments and decrements MUST target this_cpu_ptr(&kd_mutex_nodes[0])->count.
 * The asm trampoline writes regs.sp to nodes[0]; kd_mutex_lock_slowpath copies
 * it to nodes[idx] when idx > 0.
 */
struct kd_mutex_node {
	struct kd_mutex_node *next;
	int tail;                        /* encoded tail (cpu+idx)            */
	int count;                       /* nesting refcount (valid in [0] only) */
	int socket_id;                   /* NUMA node id                      */
	int cpuid;                       /* CPU that owns this node           */
	uint64_t rsp;                    /* saved real stack ptr (for restore) */
	struct kd_mutex *lock;
	struct task_struct *task_struct_ptr;
	int irqs_disabled;

	union {
		struct { u8 completed; u8 locked; };
		struct { u16 locked_completed; };
	};

	/*
	 * Callee-saved registers captured at __kd_mutex_lock entry.
	 * Redundant with reading from the stack at regs.sp (which is the
	 * primary path in execute_cs), but kept for debugging/validation.
	 */
	unsigned long saved_rbx;
	unsigned long saved_rbp;
	unsigned long saved_r12;
	unsigned long saved_r13;
	unsigned long saved_r14;
	unsigned long saved_r15;
	unsigned long saved_ret_addr;     /* CS entry point (ret_addr)         */

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
	unsigned long origin_mutex_addr; /* original struct mutex *, if shadow */
};

#define __KD_MUTEX_INITIALIZER(lockname) \
	{ .tail = NULL, .state = ATOMIC_INIT(0), .combiner_task = NULL, \
	  .origin_mutex_addr = 0 }

#define DEFINE_KD_MUTEX(mname) \
	struct kd_mutex mname = __KD_MUTEX_INITIALIZER(mname)

void kd_mutex_init(struct kd_mutex *lock);
void kd_mutex_init_percpu(void);
void kd_mutex_exit(void);

void _kd_mutex_lock(struct kd_mutex *lock, unsigned long rsp_value,
		    unsigned long ret_addr,
		    unsigned long s_rbx, unsigned long s_r12,
		    unsigned long s_r13, unsigned long s_r14,
		    unsigned long s_r15, unsigned long s_rbp);
int _kd_mutex_unlock_checked(struct kd_mutex *lock);
void _kd_mutex_unlock(struct kd_mutex *lock);
int  _kd_mutex_trylock(struct kd_mutex *lock);

#endif /* _LINUX_KD_MUTEX_H */
