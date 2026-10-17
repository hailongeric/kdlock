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
 * Each KD object owns its physical exclusion and legacy delegation state.
 * Every executor acquires the KD owner word; only that task releases it.
 * Linux mutex objects and waiters never participate in this protocol.
 */

#define KD_MUTEX_SHADOW_STACK_SIZE 8192L
#define KD_MUTEX_MAX_NODES 4 /* concurrent waiter slots per CPU */
#define KD_MUTEX_GATE_COMBINER 3 /* existing gate state while servicing a batch */

#include <linux/atomic.h>
#include <linux/spinlock.h>
#include <linux/list.h>
#include <linux/osq_lock.h>
#include "kd_regs.h"

struct kd_exec_frame;
struct kd_mutex;

bool kd_mutex_check_idle(void);

/*
 * kd_mutex_node — per-waiter queue node.
 *
 * Each CPU owns KD_MUTEX_MAX_NODES independently reserved slots. A slot also
 * owns its shadow stack, so an executor acquiring a sleeping KD mutex cannot
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

	/* Immutable identity and result tags are separate from the polled line.
	 * Reading the ABI must not first fetch the waiter's notification line. */
	u8 entry_abi __attribute__((aligned(64)));
	unsigned int packet_state; /* published with completed/native_resume */
	int tail; /* encoded tail (cpu+idx)            */
	int slot; /* reserved per-CPU slot index       */
	int numa_node; /* immutable slot locality, set before source publication */
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
	u8 completed;
	u8 locked;
	bool native_resume;
};

/*
 * KD-only physical exclusion and legacy delegation scheduling, in one object.
 */
struct kd_mutex {
	/* KD-owned physical exclusion for every local and delegated executor. */
	atomic_long_t owner;
	struct optimistic_spin_queue osq;
	raw_spinlock_t wait_lock;
	struct list_head wait_list;
	/* Keep physical ownership in the first 128-byte region. The other
	 * region contains producer-written queue and waiter-count fields, so
	 * 128-byte alignment keeps adjacent-line pairs within each group. */
	struct task_struct *physical_owner __attribute__((aligned(64)));
	union {
		atomic_t state;
		struct {
			u8 locked;
		};
	};
	u32 tail __attribute__((aligned(64))); /* encoded CPU/slot; zero means no queued tail */
	/* Exact probe count, independent of both queue publication and ownership.
	 * Its enter/exit RMWs must not invalidate either of those cachelines. */
	atomic_t waiter_count __attribute__((aligned(64)));
} __attribute__((aligned(128)));

#define KD_MUTEX_INITIALIZER(name) { \
 .owner = ATOMIC_LONG_INIT(0), .osq = OSQ_LOCK_UNLOCKED, \
 .wait_lock = __RAW_SPIN_LOCK_UNLOCKED(name.wait_lock), \
 .wait_list = LIST_HEAD_INIT(name.wait_list), \
 .state = ATOMIC_INIT(0), .waiter_count = ATOMIC_INIT(0) }
#define DEFINE_KD_MUTEX(name) struct kd_mutex name = KD_MUTEX_INITIALIZER(name)

void kd_mutex_init(struct kd_mutex *lock);
void kd_mutex_destroy(struct kd_mutex *lock);
void kd_mutex_local_lock(struct kd_mutex *lock);
void kd_mutex_local_unlock(struct kd_mutex *lock);
int kd_mutex_lock_interruptible(struct kd_mutex *lock);
int kd_mutex_lock_killable(struct kd_mutex *lock);
void kd_mutex_lock_io(struct kd_mutex *lock);
int kd_atomic_dec_and_mutex_lock(atomic_t *count, struct kd_mutex *lock);
int kd_mutex_trylock(struct kd_mutex *lock);
bool kd_mutex_is_locked(struct kd_mutex *lock);
bool kd_mutex_is_idle(struct kd_mutex *lock);
int kd_mutex_init_percpu(void);
int kd_mutex_local_runtime_init(void);
void kd_mutex_local_runtime_exit(void);
void kd_mutex_exit(void);

void _kd_mutex_lock_abi(struct kd_mutex *lock, unsigned long rsp_value,
		       unsigned long ret_addr, unsigned long bp, unsigned int abi);
int _kd_mutex_unlock_checked(struct kd_mutex *lock);
void _kd_mutex_unlock(struct kd_mutex *lock);

int kd_mutex_debug_nested_waiters(void);
int kd_mutex_nested_lock(struct kd_mutex *lock);
int kd_mutex_nested_unlock(struct kd_mutex *lock);
void kd_mutex_note_nested_jit(void);
int kd_mutex_waiter_count(struct kd_mutex *lock);
void kd_mutex_note_nested_abort_release(void);

#endif /* _LINUX_KD_MUTEX_H */
