#ifndef __KD_SPINLOCK_H__
#define __KD_SPINLOCK_H__

/* Spin scheduling-node and JIT handoff layouts. Nodes are bounded per CPU and
 * reusable; origin refs and physical holds have separate generation checks.
 * The qspinlock alias below denotes private scheduling storage, not Linux L. */
#include <asm/ptrace.h>
#include "qspinlock_i.h"
#include "kd_exec.h"

#define qspinlock orig_qspinlock
#define ENABLE_IRQS_CHECK 1

#define MAX_NODES 4

struct kd_spin_jit_context;

struct kd_spin_node {
	struct kd_spin_node *next;
	int tail;
	int count;
	int socket_id;
	int cpuid;
	unsigned long gsbase;
	uint64_t rsp;
	struct qspinlock *lock;
	struct task_struct *task_struct_ptr;
	int irqs_disabled;
	char dummy1[4];
	union {
		struct {
			u8 completed;
			u8 locked;
		};
		struct {
			u16 locked_completed;
		};
	};
	struct pt_regs regs;
	struct kd_exec_frame *exec_frame;
	bool jit_waiter;
	bool jit_retry;
	bool native_resume;
	bool pinned_context;
	/* regs holds the decoded packet, not the original callee-save RSP. */
	bool native_regs_decoded;
	struct kd_spin_jit_context *jit_context;
	/* Logical hook waiter, not this recyclable node's physical requester. */
	struct kd_spin_ref spin_origin;
	/* Optional queue residence clock; consumed before this node can be reused. */
	uint64_t queued_at_ns;
};

#define _Q_COMPLETED_OFFSET (_Q_LOCKED_OFFSET_HL + _Q_LOCKED_BITS_HL)
#define _Q_COMPLETED_BITS 8
#define _Q_COMPLETED_MASK _Q_SET_MASK_HL(COMPLETED)

/*
 * kd_spinlock_init and kd_spinlock_exit should be called only when the module
 * is loaded and unloaded. They set up and free per-core spinlock delegation
 * state.
 */
int kd_spinlock_init(void);
void kd_spinlock_exit(void);

void kd_spin_lock(struct qspinlock *lock, unsigned long rsp_value);
void kd_spin_unlock(struct qspinlock *lock);
/*
 * Acquire a lock for a translated waiter without switching the C stack.
 * The queue path can execute this virtual waiter remotely and return updated
 * registers at the instruction following the nested lock's unlock call.
 */
#define KD_SPIN_NESTED_ACQUIRED 0
#define KD_SPIN_NESTED_DELEGATED 1
#define KD_SPIN_NESTED_PARENT_OOO 2
#define KD_SPIN_NESTED_ACQUIRED_QUEUE 3
#define KD_SPIN_NESTED_NATIVE 4
int kd_spin_nested_lock(struct qspinlock *lock, struct pt_regs *regs,
			struct kd_exec_frame *parent);
#define KD_SPIN_NESTED_UNLOCK_OK 0
#define KD_SPIN_NESTED_UNLOCK_OOO 1
int kd_spin_nested_unlock(struct qspinlock *lock);
bool kd_spin_nested_shadow_has_space(void);
int kd_spin_nested_shadow_push(struct qspinlock *lock);
int kd_spin_nested_shadow_remove(struct qspinlock *lock);

#ifdef KDLOCK_SELFTEST
bool kd_spin_selftest_shadow_begin(raw_spinlock_t *lock, struct pt_regs *regs,
				   struct kd_exec_frame *frame);
void kd_spin_selftest_shadow_end(struct pt_regs *regs,
				 struct kd_exec_frame *frame, int result);
#endif

/*
 * Diagnostics for the nested-JIT migration. These functions only record
 * state; they do not change lock ownership or delegation behavior.
 */
void kd_spin_debug_nested_lock(raw_spinlock_t *lock, bool native_fallback);
void kd_spin_debug_nested_unlock(raw_spinlock_t *lock);
void kd_spin_debug_nested_remote(raw_spinlock_t *lock);
int kd_spin_debug_waiter_count(raw_spinlock_t *lock);
unsigned int kd_spin_debug_word(raw_spinlock_t *lock);
unsigned long kd_spin_debug_owner(raw_spinlock_t *lock);

/*
 * JIT nested lock adapter. A positive return value means the known-call
 * handler consumed the nested lock and continuation; zero means the caller
 * must use the native fallback continuation; negative values are errors.
 */
#define KD_JIT_NESTED_NATIVE 0
#define KD_JIT_NESTED_CONSUMED 1
#define KD_JIT_NESTED_REMOTE 2
int kd_spin_jit_nested_lock_ctx(raw_spinlock_t *lock, struct pt_regs *regs,
				struct kd_exec_frame *parent);
int kd_spin_jit_nested_unlock_ctx(raw_spinlock_t *lock,
				  struct kd_exec_frame *frame);
int kd_spin_jit_outer_unlock_ooo_ctx(raw_spinlock_t *lock, struct pt_regs *regs,
				     struct kd_exec_frame *frame);
int kd_spin_jit_nested_cleanup(struct kd_exec_frame *frame);
int kd_spin_jit_abort_cleanup(struct kd_exec_frame *frame);

#endif /* __KD_SPINLOCK_H__ */
