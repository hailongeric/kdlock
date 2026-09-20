#ifndef _LINUX_KD_MUTEX_H
#define _LINUX_KD_MUTEX_H

/*
 * kd_mutex — JIT-sandbox mutex delegation protocol.
 *
 * Follows the same JIT execution model as kd_spinlock: the combiner calls
 * kd_exe_on_call_hl_entry() with the waiter's saved pt_regs. The translated
 * sandbox runs the critical section and returns KD_EXE_RUN_TO_UNLOCK when it
 * reaches mutex_unlock. JIT replaces the body handoff, while queue execution
 * still uses physical shadow stacks with their own lifetime constraints.
 *
 * The kd_mutex is a scheduling gate beside the kernel's struct mutex. Every
 * executor also acquires the original mutex; only that task releases it.
 */

#define KD_MUTEX_SHADOW_STACK_SIZE 8192L
#define KD_MUTEX_MAX_NODES 4 /* concurrent waiter slots per CPU */

#include <asm/ptrace.h>

struct kd_exec_frame;
struct mutex;

bool kd_mutex_check_idle(void);

/*
 * kd_mutex_node — per-waiter queue node.
 *
 * Each CPU owns KD_MUTEX_MAX_NODES independently reserved slots. A slot also
 * owns its shadow stack, so an executor acquiring a sleeping native mutex cannot
 * have its stack reused by another target task running on the same CPU.
 * A published delegation waiter keeps preemption disabled while polling.
 * The combiner feeds node->regs
 * into kd_exe_on_call_hl_entry() to execute the waiter's critical section
 * inside the JIT sandbox.
 */
struct kd_mutex_node {
	struct kd_mutex_node *next;
	unsigned long gsbase; /* logical waiter's kernel GS base   */
	uint64_t rsp; /* saved real stack ptr (for restore) */
	void *shadow_stack_base;
	uint64_t shadow_stack_ptr;
	struct kd_mutex *lock;
	struct task_struct *task_struct_ptr;
	/* Explicit clobber continuation, or legacy hook return-slot validation. */
	unsigned long saved_ret_addr; /* CS entry point (ret_addr)         */

	/* Removing unused snapshots must not make adjacent reservations share
	 * a cache line. Keep a four-line stride and put notification bytes on a
	 * different line from next, which a successor writes during polling.
	 * Unlike spin, mutex has no combined locked/completed word consumer. */
	u8 completed __attribute__((aligned(64)));
	u8 locked;
	bool native_resume;
	u8 entry_abi; /* immutable acquisition identity; CPU is encoded in tail */
	unsigned int packet_state; /* published with completed/native_resume */
	int tail; /* encoded tail (cpu+idx)            */
	int slot; /* reserved per-CPU slot index       */
	struct pt_regs regs; /* waiter context → JIT sandbox      */
	/* Optional queue residence clock, not critical-section execution time. */
	uint64_t queued_at_ns;
};

/*
 * Scheduling state beside one original Linux mutex.
 */
struct kd_mutex {
	u32 tail; /* encoded CPU/slot; zero means no queued tail */
	union {
		atomic_t state;
		struct {
			u8 locked;
		};
	};
	struct task_struct *physical_owner; /* task holding the original mutex */
	unsigned long origin_mutex_addr; /* original struct mutex *, if shadow */
	atomic_t waiter_count;
};

void kd_mutex_init(struct kd_mutex *lock);
int kd_mutex_init_percpu(void);
void kd_mutex_exit(void);

void _kd_mutex_lock_abi(struct kd_mutex *lock, unsigned long rsp_value,
		       unsigned long ret_addr, unsigned long bp, unsigned int abi);
int _kd_mutex_unlock_checked(struct kd_mutex *lock);
void _kd_mutex_unlock(struct kd_mutex *lock);

bool kd_mutex_jit_is_enabled(void);
int kd_mutex_debug_nested_waiters(void);
int kd_mutex_nested_lock(struct mutex *lock);
int kd_mutex_nested_unlock(struct mutex *lock);
void kd_mutex_note_nested_jit(void);
int kd_mutex_waiter_count(struct kd_mutex *lock);
void kd_mutex_note_nested_abort_release(void);

#endif /* _LINUX_KD_MUTEX_H */
