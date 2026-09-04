#ifndef __KD_SPINLOCK_H__
#define __KD_SPINLOCK_H__

// #define KERNEL_SYNCSTRESS

// #ifdef KERNEL_SYNCSTRESS
#include <asm/ptrace.h>  // ! pt_regs
#include "qspinlock_i.h"
#include "combiner.h"
#include "kd_exec.h"
#define qspinlock orig_qspinlock
#define ENABLE_IRQS_CHECK 1

#define MAX_NODES 4
#define DEFINE_KDSPINLOCK(x)                                                 \
	arch_spinlock_t(x) = (arch_spinlock_t)__ORIG_QSPIN_LOCK_UNLOCKED

//#define KD_SPIN_STATS 1

struct kd_spin_jit_context;

/*
 * TODO (Correctness optimization): 
 * Add for BIG ENDIAN
 */
struct kd_spin_node {
	struct kd_spin_node *next;
	int tail;
	int count;
	int socket_id;
	int cpuid;
	uint64_t rsp;
	struct qspinlock *lock;
	struct task_struct *task_struct_ptr;
	int irqs_disabled;
	char dummy1[12];
	union {
		struct {
			u8 completed;
			u8 locked;
		};
		struct {
			u16 locked_completed;
		};
	} ;
	// char dummy[48];
	struct pt_regs regs;
	struct kd_exec_frame *exec_frame;
	bool jit_waiter;
	bool jit_retry;
	struct kd_spin_jit_context *jit_context;
};

#define _Q_COMPLETED_OFFSET (_Q_LOCKED_OFFSET_HL + _Q_LOCKED_BITS_HL)
#define _Q_COMPLETED_BITS 8
#define _Q_COMPLETED_MASK _Q_SET_MASK_HL(COMPLETED)

/*
 * kd_spinlock_init and kd_spinlock_exit should be called only when the module
 * is loaded and unloaded. They set up and free per-core spinlock delegation
 * state.
 */
void kd_spinlock_init(void);
void kd_spinlock_exit(void);

/*
 * Public API
 */
extern void kd_spin_lock_init(struct qspinlock *lock);
extern int kd_spin_is_locked(struct qspinlock *lock);
extern int kd_spin_value_unlocked(struct qspinlock lock);
extern int kd_spin_is_contended(struct qspinlock *lock);
extern int kd_spin_trylock(struct qspinlock *lock);
extern void kd_spin_lock(struct qspinlock *lock, unsigned long rsp_value);
extern void kd_spin_unlock(struct qspinlock *lock);
/*
 * Acquire a lock for a translated waiter without switching the C stack.
 * The queue path can execute this virtual waiter remotely and return updated
 * registers at the instruction following the nested lock's unlock call.
 */
#define KD_SPIN_NESTED_ACQUIRED       0
#define KD_SPIN_NESTED_DELEGATED      1
#define KD_SPIN_NESTED_PARENT_OOO     2
#define KD_SPIN_NESTED_ACQUIRED_QUEUE 3
extern int kd_spin_nested_lock(struct qspinlock *lock, struct pt_regs *regs,
			       const struct kd_exec_frame *parent);
#define KD_SPIN_NESTED_UNLOCK_OK   0
#define KD_SPIN_NESTED_UNLOCK_OOO  1
extern int kd_spin_nested_unlock(struct qspinlock *lock);
extern int kd_spin_nested_shadow_push(struct qspinlock *lock);
extern int kd_spin_nested_shadow_pop(struct qspinlock *lock);
extern int kd_spin_nested_shadow_remove(struct qspinlock *lock);

/*
 * Diagnostics for the nested-JIT migration. These functions only record
 * state; they do not change lock ownership or delegation behavior.
 */
void kd_spin_debug_combiner(struct qspinlock *lock, unsigned int depth);
void kd_spin_debug_jit_success(struct qspinlock *lock, unsigned int depth);
void kd_spin_debug_jit_not_ready(struct qspinlock *lock, unsigned int depth);
void kd_spin_debug_nested_lock(raw_spinlock_t *lock, bool native_fallback);
void kd_spin_debug_nested_unlock(raw_spinlock_t *lock);
void kd_spin_debug_nested_remote(raw_spinlock_t *lock);
void kd_spin_debug_ooo_unlock(struct qspinlock *lock, unsigned int depth);
int kd_spin_debug_waiter_count(raw_spinlock_t *lock);

/*
 * JIT nested lock adapter. A positive return value means the known-call
 * handler consumed the nested lock and continuation; zero means the caller
 * must use the native fallback continuation; negative values are errors.
 */
#define KD_JIT_NESTED_NATIVE      0
#define KD_JIT_NESTED_CONSUMED    1
#define KD_JIT_NESTED_REMOTE      2
#define KD_JIT_NESTED_ERROR      -1

int kd_spin_jit_nested_lock_ctx(raw_spinlock_t *lock,
				struct pt_regs *regs,
				struct kd_exec_frame *parent);
int kd_spin_jit_nested_unlock_ctx(raw_spinlock_t *lock,
					  struct kd_exec_frame *frame);
int kd_spin_jit_outer_unlock_ooo_ctx(raw_spinlock_t *lock,
					     struct pt_regs *regs,
					     struct kd_exec_frame *frame);
int kd_spin_jit_nested_cleanup(struct kd_exec_frame *frame);
int kd_spin_jit_abort_cleanup(struct kd_exec_frame *frame);

struct task_struct *kd_spin_get_current(spinlock_t *lock);
void kd_spin_set_current_state(spinlock_t *lock, unsigned int state);
#endif
