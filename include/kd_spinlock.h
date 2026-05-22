#ifndef __KD_SPINLOCK_H__
#define __KD_SPINLOCK_H__

// #define KERNEL_SYNCSTRESS

// #ifdef KERNEL_SYNCSTRESS
#include <asm/ptrace.h>  // ! pt_regs 
#include "qspinlock_i.h"
#include "combiner.h"
#define qspinlock orig_qspinlock
// #else
// #define ENABLE_IRQS_CHECK 1
// #include <asm/qspinlock.h>
// #endif

#define MAX_NODES 4
#define DEFINE_KDSPINLOCK(x)                                                 \
	arch_spinlock_t(x) = (arch_spinlock_t)__ORIG_QSPIN_LOCK_UNLOCKED

//#define KD_SPIN_STATS 1

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

struct task_struct *kd_spin_get_current(spinlock_t *lock);
void kd_spin_set_current_state(spinlock_t *lock, unsigned int state);
#endif
