#ifndef _LINUX_KD_MUTEX_H
#define _LINUX_KD_MUTEX_H

/*
 * kd_mutex — JIT-sandbox mutex delegation protocol.
 *
 * Follows the same JIT execution model as kd_spinlock: the combiner calls
 * kd_exe_on_call_hl_entry() with the waiter's saved pt_regs. The translated
 * sandbox runs the critical section and returns KD_EXE_RUN_TO_UNLOCK when it
 * reaches mutex_unlock. No raw context switches are used.
 *
 * The kd_mutex is a shadow lock that sits beside the kernel's struct mutex;
 * kd_lock.c maps each struct mutex * to a struct kd_mutex *.
 */

#define KD_MUTEX_SHADOW_STACK_SIZE 8192L
#define KD_MUTEX_MAX_NODES 4 /* per-CPU nesting depth */

#include <asm/ptrace.h>

struct kd_exec_frame;
struct kd_mutex_jit_context;

/*
 * kd_mutex_node — per-waiter queue node.
 *
 * Each CPU owns KD_MUTEX_MAX_NODES independently reserved slots. A slot also
 * owns its shadow stack, so a scheduled waiter cannot have its stack reused by
 * another target task running on the same CPU. The combiner feeds node->regs
 * into kd_exe_on_call_hl_entry() to execute the waiter's critical section
 * inside the JIT sandbox.
 */
struct kd_mutex_node {
	struct kd_mutex_node *next;
	int tail; /* encoded tail (cpu+idx)            */
	int slot; /* reserved per-CPU slot index       */
	int socket_id; /* NUMA node id                      */
	int cpuid; /* CPU that owns this node           */
	unsigned long gsbase; /* logical waiter's kernel GS base   */
	uint64_t rsp; /* saved real stack ptr (for restore) */
	void *shadow_stack_base;
	uint64_t shadow_stack_ptr;
	struct kd_mutex *lock;
	struct task_struct *task_struct_ptr;
	int irqs_disabled;

	union {
		struct {
			u8 completed;
			u8 locked;
		};
		struct {
			u16 locked_completed;
		};
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
	unsigned long saved_ret_addr; /* CS entry point (ret_addr)         */

	struct pt_regs regs; /* waiter context → JIT sandbox      */
	struct kd_mutex_jit_context *jit_context;
	bool jit_waiter;
};

/*
 * kd_mutex — the shadow lock itself.
 */
struct kd_mutex {
	struct kd_mutex_node *tail; /* queue tail (NULL if empty)        */
	union {
		atomic_t state;
		struct {
			u8 locked;
		};
	};
	struct task_struct *combiner_task;
	unsigned long origin_mutex_addr; /* original struct mutex *, if shadow */
	atomic_t waiter_count;
};

#define __KD_MUTEX_INITIALIZER(lockname) \
	{ .tail = NULL,                  \
	  .state = ATOMIC_INIT(0),       \
	  .combiner_task = NULL,         \
	  .origin_mutex_addr = 0,        \
	  .waiter_count = ATOMIC_INIT(0) }

void kd_mutex_init(struct kd_mutex *lock);
int kd_mutex_init_percpu(void);
void kd_mutex_exit(void);

void _kd_mutex_lock(struct kd_mutex *lock, unsigned long rsp_value,
		    unsigned long ret_addr, unsigned long s_rbx,
		    unsigned long s_r12, unsigned long s_r13,
		    unsigned long s_r14, unsigned long s_r15,
		    unsigned long s_rbp);
int _kd_mutex_unlock_checked(struct kd_mutex *lock);
void _kd_mutex_unlock(struct kd_mutex *lock);

#define KD_MUTEX_NESTED_ACQUIRED 0
#define KD_MUTEX_NESTED_DELEGATED 1
#define KD_MUTEX_NESTED_ACQUIRED_QUEUE 2

int kd_mutex_nested_lock(struct kd_mutex *lock, struct pt_regs *regs,
			 const struct kd_exec_frame *parent);
int kd_mutex_nested_unlock(struct kd_mutex *lock);
int kd_mutex_waiter_count(struct kd_mutex *lock);
void kd_mutex_note_nested_abort_release(void);

#endif /* _LINUX_KD_MUTEX_H */
