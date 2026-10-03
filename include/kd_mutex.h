#ifndef _LINUX_KD_MUTEX_H
#define _LINUX_KD_MUTEX_H

/*
 * kd_mutex — JIT-sandbox mutex delegation protocol.
 *
 * Follows the same JIT execution model as kd_spinlock: the combiner calls
 * kd_exe_on_call_hl_entry() with the waiter's saved kd_regs. The translated
 * sandbox runs the critical section and returns KD_EXE_RUN_TO_UNLOCK when it
 * reaches mutex_unlock. JIT replaces the body handoff, while queue execution
 * still uses physical shadow stacks with their own lifetime constraints.
 *
 * The kd_mutex is a scheduling gate beside the kernel's struct mutex. Every
 * executor also acquires the original mutex; only that task releases it.
 */

#define KD_MUTEX_SHADOW_STACK_SIZE 8192L
#define KD_MUTEX_MAX_NODES 4 /* concurrent waiter slots per CPU */

#include "kd_regs.h"

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
	/* Immutable request identity, notification state and the MINIMAL triple
	 * share line zero. The JIT's five virtual GPR backing slots start in line
	 * one, so generated spills do not invalidate the waiter's polling line.
	 * saved_ret_addr remains distinct from the packet's mutable IP. */
	unsigned long saved_ret_addr;
	unsigned long gsbase;
	struct task_struct *task_struct_ptr;
	struct kd_mutex *lock;
	u8 completed;
	u8 locked;
	bool native_resume;
	u8 entry_abi;
	unsigned int packet_state;
	struct kd_regs regs;

	/* A successor writes next while this waiter polls locked. Keep the link
	 * on line three, separate from both notification and virtual-GPR lines.
	 * This physical return anchor is not the packet's logical caller SP.
	 * Whole-line type alignment also isolates all four reserved array slots.
	 * Frame/native-ACK lifetime remains independent of this reusable node. */
	struct kd_mutex_node *next;
	uint64_t rsp;
	void *shadow_stack_base;
	uint64_t shadow_stack_ptr;
	int tail; /* encoded CPU/slot identity */
	int slot;
	/* Optional queue residence clock, not critical-section execution time. */
	uint64_t queued_at_ns;
} __attribute__((aligned(64)));

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
