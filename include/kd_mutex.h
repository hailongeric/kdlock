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
#include <linux/wait.h>

struct kd_exec_frame;
struct mutex;
struct rcuwait;

bool kd_mutex_check_idle(void);
int kd_mutex_wait_selftest(void);

/*
 * kd_mutex_node — per-waiter queue node.
 *
 * Each CPU owns KD_MUTEX_MAX_NODES independently reserved slots. A slot also
 * owns its shadow stack, so an executor acquiring a sleeping native mutex cannot
 * have its stack reused by another target task running on the same CPU.
 * A published waiter stays migration-pinned; blocking mode can schedule on its
 * reserved stack. Spin mode also keeps preemption disabled while polling.
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

	/* Immutable identity and result tags are separate from the polled line.
	 * Reading the ABI must not first fetch the waiter's notification line. */
	u8 entry_abi __attribute__((aligned(64)));
	unsigned int packet_state; /* published with completed/native_resume */
	int tail; /* encoded tail (cpu+idx)            */
	int slot; /* reserved per-CPU slot index       */
	int numa_node; /* immutable slot locality, set before source publication */
	/* Independently resident notification object, never recycled with packet. */
	struct rcuwait *wait;
	/* The combiner writes IP/SP and virtual registers while the producer
	 * polls locked. Sharing their cacheline makes every packet update fight
	 * the polling CPU for ownership, especially across NUMA nodes. */
	struct kd_regs regs __attribute__((aligned(64)));
	/* Optional queue residence clock, not critical-section execution time. */
	uint64_t queued_at_ns;
	/* The unused tail of the FULL packet's last line holds notification.
	 * MINIMAL/COMPLETE bodies write only the first packet line. Cold FULL
	 * handoff may share this line, but ordinary body writes never do. Keep
	 * the five-line stride and isolate the producer's next pointer too. */
	union {
		u16 result; /* x86: low byte completed, high byte waiting */
		struct {
			u8 completed;
			u8 locked;
		};
	};
	bool native_resume;
};

/*
 * Scheduling state beside one original Linux mutex.
 */
struct kd_mutex {
	/* Producers exchange the tail on every request. Keep their writes away
	 * from the physical ownership fields checked by every delegated body. */
	u32 tail; /* encoded CPU/slot; zero means no queued tail */
	struct task_struct *physical_owner __attribute__((aligned(64)));
	unsigned long origin_mutex_addr; /* original struct mutex *, if shadow */
	union {
		atomic_t state;
		struct {
			u8 locked;
		};
	};
	/* Exact probe count, independent of both queue publication and ownership.
	 * Its enter/exit RMWs must not invalidate either of those cachelines. */
	atomic_t waiter_count __attribute__((aligned(64)));
	/* Only the queue head (or an unpublished overflow) waits here. Result
	 * waiters use their own notification byte and never join this list. */
	wait_queue_head_t gate_wait;
};

void kd_mutex_init(struct kd_mutex *lock);
int kd_mutex_init_percpu(void);
void kd_mutex_exit(void);

void _kd_mutex_lock_abi(struct kd_mutex *lock, unsigned long rsp_value,
		       unsigned long ret_addr, unsigned long bp, unsigned int abi);
int _kd_mutex_unlock_checked(struct kd_mutex *lock);
void _kd_mutex_unlock(struct kd_mutex *lock);

int kd_mutex_debug_nested_waiters(void);
int kd_mutex_nested_lock(struct mutex *lock);
int kd_mutex_nested_unlock(struct mutex *lock);
void kd_mutex_note_nested_jit(void);
int kd_mutex_waiter_count(struct kd_mutex *lock);
void kd_mutex_note_nested_abort_release(void);

#endif /* _LINUX_KD_MUTEX_H */
