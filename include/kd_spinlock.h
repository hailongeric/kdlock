#ifndef __KD_SPINLOCK_H__
#define __KD_SPINLOCK_H__

/* Spin scheduling-node and JIT handoff layouts. Nodes are bounded per CPU and
 * reusable; origin refs and physical holds have separate generation checks.
 * The internal qspinlock alias denotes the explicit KD object, never Linux L. */
#include <asm/ptrace.h>
#include <linux/atomic.h>
#include "qspinlock_i.h"
#include "kd_exec.h"

#define qspinlock kd_spinlock
#define ENABLE_IRQS_CHECK 1

#define MAX_NODES 4

struct kd_spin_jit_context;

/* Stable request storage, independent of the recyclable scheduling node.
 * Ordinary completion has one waiter user. Native handoff adds an owner user;
 * remote requests also retain the root packet until their own final release. */
struct kd_spin_diag_slot;

struct kd_spin_exec_request {
	/* The common producer/combiner/restore metadata precedes the frame.
	 * Align pool slots so another request's release cannot invalidate this
	 * header. Keep one authoritative value for each state discriminator. */
	struct kd_spin_diag_slot *diag __attribute__((aligned(64)));
	atomic_t users;
	bool jit_waiter;
	bool jit_retry;
	bool native_resume;
	bool pinned_context;
	bool native_regs_decoded;
	struct kd_exec_frame frame;
	/* These fields survive node reuse but are not ordinary JIT admission
	 * inputs. The frame/packet is still retained until the last user exits. */
	struct kd_spin_exec_request *packet_owner;
	struct kd_spin_jit_context *jit_context;
	unsigned long irq_flags;
	u64 queued_at_ns;
};

struct kd_spin_node {
	struct kd_spin_node *next;
	int tail;
	int count;
	int socket_id;
	int cpuid;
	/* Scheduler stack sentinel, not the logical register packet. */
	uint64_t rsp;
	/* Immutable while queued; hints only, never restoration/admission state.
	 * Keep these addresses with the queue links in the first cache line. */
	u8 prefetch_full;
	u8 prefetch_complex;
	struct kd_spin_exec_request *execution;
	struct pt_regs *prefetch_regs;
	unsigned long prefetch_sp;
	/* A successor writes next while this CPU polls locked. Isolate those
	 * accesses; only the release notification belongs on the polling line.
	 * Align the member so the type/array stride also covers whole x86 lines,
	 * including nested nodes. Keep the two bytes adjacent for one wake store.
	 * Execution completion itself still belongs to frame.state. */
	union {
		struct { u8 completed; u8 locked; };
		struct { u16 locked_completed; };
	} __attribute__((aligned(64)));
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

void kd_spin_lock(struct qspinlock *lock, unsigned long rsp_value,
		  unsigned long rip);
void kd_spin_lock_abi(struct qspinlock *lock, unsigned long sp,
                      unsigned long ip, unsigned long bp, unsigned int abi);
void kd_spin_unlock(struct qspinlock *lock);
/* Explicit callers prepare their continuation before starting the workload.
 * These clobber entries capture no registers themselves: use the caller shell
 * in kd_spin_direct.h so the compiler spills every live non-frame GPR. */
int kd_spin_prepare(kd_spinlock_t *lock, unsigned long ip, unsigned int abi);
void kd_spin_lock_clobber_v1(struct qspinlock *lock, unsigned long sp,
			   unsigned long ip, unsigned long bp);
void kd_spin_unlock_clobber_v1(struct qspinlock *lock, unsigned long sp,
			     unsigned long ip, unsigned long bp);
void kd_spin_lock_nondelegated(kd_spinlock_t *lock);
void kd_spin_unlock_nondelegated(kd_spinlock_t *lock);
/* Internal shadow/frame releases already know their protocol provenance. */
void kd_spin_unlock_protocol(struct qspinlock *lock);
/* The hook already found this acquisition ticket; reuse it through release. */
void kd_spin_unlock_ref(struct qspinlock *lock, const struct kd_spin_ref *ref);
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
/* Materialize the combiner checkpoint before the first complex wrapper exit. */
void kd_spin_jit_prepare_complex(struct kd_exec_frame *frame);

#endif /* __KD_SPINLOCK_H__ */
