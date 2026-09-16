// SPDX-License-Identifier: GPL-2.0
// Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi
//
// Ported to kdlock: kd_mutex — JIT-sandbox mutex delegation.
// Follows the same kd_exe_on_call_hl_entry() model as kd_spinlock.c.

/* Read in this order: reserve node, claim original mutex, execute_cs,
 * run_combiner, then waiter restoration. The private gate never substitutes
 * for Linux exclusion. Native continuation keeps the physical owner blocked
 * in its ACK service loop; it does not hand the mutex owner field to waiter.
 * Public lock/unlock and stack trampolines remain here. mutex/ components
 * separate queue reservation, delegated execution, waiting and lifecycle. */
#include <linux/module.h>
#include <linux/smp.h>
#include <linux/bug.h>
#include <linux/percpu.h>
#include <linux/hardirq.h>
#include <linux/prefetch.h>
#include <linux/atomic.h>
#include <asm/byteorder.h>
#include <linux/vmalloc.h>
#include <linux/sched/stat.h>
#include <linux/sched/task.h>
#include <linux/sched.h>
#include <linux/topology.h>
#include <linux/errno.h>
#include <linux/mutex.h>

#include "kd_mutex.h"
#include "kd_lock.h"
#include "kd_exec.h"
#include "kd_segment.h"
#include "exe.h"
#include "utils.h"

/* --------------------------------------------------------------------------
 * Debug
 * -------------------------------------------------------------------------- */
/* Queue/JIT entry traces are ordinary events, not alerts. ALERT forces these
 * frequent records onto a normal serial console while the mutex is held and
 * distorts both batch timing and cost. Keep INFO records in the kernel buffer;
 * actual warnings/errors and the returned-body witness retain their levels. */
#ifdef DSM_DEBUG
#define mutex_debug(fmt, ...)                                                \
	({                                                                   \
		printk(KERN_INFO "[%d] [%d] kd_mutex (%s) lock(%px): " fmt,  \
		       smp_processor_id(), current->pid, __func__,           \
		       lock, ##__VA_ARGS__);                                 \
	})
#else
#define mutex_debug(fmt, ...)
#endif

/* --------------------------------------------------------------------------
 * Constants
 * -------------------------------------------------------------------------- */
#define KD_MUTEX_WAITER_UNPROCESSED 0
#define KD_MUTEX_WAITER_PROCESSED 1

#define _Q_LOCKED_COMBINER_VAL 3

static const unsigned int kd_mutex_batch_size = 1024;

/* Always-on protocol counters used for validation and post-mortem diagnosis. */
static atomic64_t kd_mutex_slowpath_count;
static atomic64_t kd_mutex_combiner_count;
static atomic64_t kd_mutex_handoff_count;
static atomic64_t kd_mutex_jit_success_count;
static atomic64_t kd_mutex_jit_not_ready_count;
static atomic64_t kd_mutex_jit_failure_count;
static atomic64_t kd_mutex_jit_resume_count;
static atomic64_t kd_mutex_frame_failure_count;
static atomic64_t kd_mutex_node_overflow_count;
static atomic64_t kd_mutex_multi_slot_count;
static atomic64_t kd_mutex_context_busy_count;
static atomic64_t kd_mutex_nested_lock_count;
static atomic64_t kd_mutex_nested_fast_count;
static atomic64_t kd_mutex_nested_queued_count;
static atomic64_t kd_mutex_nested_jit_count;
static atomic64_t kd_mutex_origin_acquires;
static atomic64_t kd_mutex_origin_releases;
static atomic64_t kd_mutex_nested_unlock_count;
static atomic64_t kd_mutex_nested_abort_release_count;
static atomic_t kd_mutex_active_waiters;
static atomic_t kd_mutex_max_waiters;
static atomic_t kd_mutex_reserved_nodes;
static atomic_t kd_mutex_nested_waiters = ATOMIC_INIT(0);

int kd_mutex_debug_nested_waiters(void)
{
	return atomic_read(&kd_mutex_nested_waiters);
}
EXPORT_SYMBOL_GPL(kd_mutex_debug_nested_waiters);

/* Project default: mutex delegation runs enabled unless explicitly disabled. */
static int kd_mutex_jit_enabled = 1;
module_param_named(mutex_jit, kd_mutex_jit_enabled, int, 0644);

bool kd_mutex_jit_is_enabled(void)
{
	return READ_ONCE(kd_mutex_jit_enabled) != 0;
}

/* --------------------------------------------------------------------------
 * Per-CPU shadow stack
 * -------------------------------------------------------------------------- */
struct kd_mutex_shadow {
	unsigned long node_slots; /* reserved per-CPU waiter slots     */
	struct kd_mutex_node *resume_node; /* valid while waiter is CPU-pinned */
};

static DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_mutex_node,
				     kd_mutex_nodes[KD_MUTEX_MAX_NODES]);
static DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_mutex_shadow, kd_mutex_shadows);

#include "mutex/queue.inc"

#include "mutex/combiner.inc"

#include "mutex/waiter.inc"

/* --------------------------------------------------------------------------
 * Asm trampoline: save regs, switch to shadow stack, call slowpath
 * -------------------------------------------------------------------------- */
#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace static int
kd_mutex_lock_slowpath_asm(struct kd_mutex *lock,
			   struct kd_mutex_node *curr_node)
{
	register int ret_val;
	register struct kd_mutex_node *cur_node = curr_node;
	register uint64_t shadow_sp;

	/* Save the native call stack so this waiter can schedule while executing
	 * the queue protocol on its independently reserved shadow stack. */
	asm volatile("movq %%rsp, %c1(%0)\n"
		     :
		     : "r"(cur_node), "i"(offsetof(struct kd_mutex_node, rsp))
		     : "memory");

	shadow_sp = cur_node->shadow_stack_ptr;
	if (unlikely(!shadow_sp)) {
		KD_PR_ERR(
			"kd_mutex: waiter shadow stack is NULL on cpu %d slot %d\n",
			smp_processor_id(), cur_node->slot);
		kd_mutex_wait_and_lock(lock);
		return 0;
	}

	/* Switch to this reservation's shadow stack. */
	asm volatile("movq %0, %%rsp" ::"r"(shadow_sp) : "memory");

	ret_val = kd_mutex_lock_slowpath(lock, cur_node);

	/* Restore original stack before returning */
	asm volatile("movq %c1(%0), %%rsp\n"
		     :
		     : "r"(cur_node), "i"(offsetof(struct kd_mutex_node, rsp))
		     : "memory");

	return ret_val;
}
#pragma GCC pop_options

/* --------------------------------------------------------------------------
 * Public API
 * -------------------------------------------------------------------------- */

#include "mutex/lifecycle.inc"

/*
 * _kd_mutex_lock — fastpath cmpxchg, slowpath delegation queue.
 */
__attribute__((noipa)) noinline notrace void
_kd_mutex_lock(struct kd_mutex *lock, unsigned long rsp_value,
	       unsigned long ret_addr, unsigned long s_rbx, unsigned long s_r12,
	       unsigned long s_r13, unsigned long s_r14, unsigned long s_r15,
	       unsigned long s_rbp)
{
	struct pt_regs resume_regs;
	bool resume_ready = false;
	bool native_resume = false;
	int ret_val;

	if (likely(cmpxchg(&lock->locked, 0, _Q_LOCKED_VAL) == 0)) {
		kd_mutex_claim_origin(lock);
		return;
	}

	/* Published waiters keep preemption disabled until completion or native
	 * handoff: their origin GS storage must not be reused by another task.
	 * Migration stays pinned when an executor acquires a real sleeping mutex. */
	migrate_disable();
	preempt_disable();
	{
		struct kd_mutex_node *curr_node = kd_mutex_reserve_node();

		if (unlikely(!curr_node)) {
			/* No queue node was published. Wait on the native stack for the
			 * scheduling gate, then acquire the original mutex as its owner. */
			atomic64_inc(&kd_mutex_node_overflow_count);
			/* Identify the unstarted request and the stable reservation mask.
			 * A missing stack can also refuse a node, so only a full mask
			 * establishes actual per-CPU slot exhaustion. */
			KD_PR_DEBUG(
				"mutex node fallback: task=%d entry=%lx lock=%lx cpu=%u slots=%lx\n",
				current->pid, ret_addr, lock->origin_mutex_addr,
				smp_processor_id(),
				READ_ONCE(this_cpu_ptr(&kd_mutex_shadows)->node_slots));
			kd_mutex_wait_and_lock(lock);
			ret_val = 0;
			goto scheduler_restore;
		}

		memset(&curr_node->regs, 0, sizeof(curr_node->regs));
		curr_node->regs.sp = rsp_value;
		curr_node->locked = true;
		curr_node->completed = false;
		curr_node->native_resume = false;
		curr_node->next = NULL;
		curr_node->tail =
			encode_tail(smp_processor_id(), curr_node->slot);
		curr_node->socket_id = numa_node_id();
		curr_node->cpuid = smp_processor_id();
		curr_node->lock = lock;
		curr_node->task_struct_ptr = current;
		curr_node->gsbase = kd_read_kernel_gsbase();
		/* Store callee-saved registers captured at hook entry */
		curr_node->saved_rbx = s_rbx;
		curr_node->saved_r12 = s_r12;
		curr_node->saved_r13 = s_r13;
		curr_node->saved_r14 = s_r14;
		curr_node->saved_r15 = s_r15;
		curr_node->saved_rbp = s_rbp;
		curr_node->saved_ret_addr = ret_addr;
		ret_val = kd_mutex_lock_slowpath_asm(lock, curr_node);
		if (ret_val == 3 || ret_val == 5) {
			struct kd_mutex_shadow *shadow =
				this_cpu_ptr(&kd_mutex_shadows);
			struct kd_mutex_node *resume_node =
				READ_ONCE(shadow->resume_node);

			if (unlikely(!resume_node)) {
				atomic64_inc(&kd_mutex_frame_failure_count);
				KD_PR_ERR(
					"mutex JIT completion missing resume node\n");
				BUG();
			}
			resume_regs = resume_node->regs;
			WRITE_ONCE(shadow->resume_node, NULL);
			kd_mutex_release_node(resume_node);
			resume_ready = true;
			native_resume = ret_val == 5;
			if (!native_resume)
				atomic64_inc(&kd_mutex_jit_resume_count);
		} else {
			kd_mutex_release_node(curr_node);
		}
scheduler_restore:;
	}
	preempt_enable();
	migrate_enable();

	if (resume_ready) {
		if (native_resume)
			jump_to_saved_regs_in_cs(&resume_regs);
		kd_mutex_task_put(current);
		/* The combiner already executed this waiter's CS through
		 * mutex_unlock. Resume after that call only after restoring scheduler
		 * state, otherwise the waiter would execute its original CS again or
		 * remain permanently non-preemptible. */
		KD_PR_DEBUG("mutex JIT resume sp=%lx target=%lx ip=%lx\n",
			    resume_regs.sp,
			    READ_ONCE(*(unsigned long *)resume_regs.sp),
			    resume_regs.ip);
		jump_to_saved_regs(&resume_regs);
		BUG(); /* jump_to_saved_regs() must never return */
	}

	return;
}

/*
 * Release the original mutex as its real owner, then open the scheduling gate.
 *
 * Ordinary completion retains A through the batch and the owner's CS. An early
 * A unlock with B still live detaches the batch through kd_mutex_release_outer().
 */
__attribute__((noipa)) noinline notrace int
_kd_mutex_unlock_checked(struct kd_mutex *lock)
{
	u8 locked = smp_load_acquire(&lock->locked);

	if (locked == _Q_LOCKED_VAL || locked == _Q_LOCKED_COMBINER_VAL) {
		BUG_ON(READ_ONCE(lock->physical_owner) != current);
		WRITE_ONCE(lock->physical_owner, NULL);
		kd_origin_mutex_unlock((struct mutex *)lock->origin_mutex_addr,
				       _RET_IP_);
		atomic64_inc(&kd_mutex_origin_releases);
		smp_store_release(&lock->locked, 0);
		return 0;
	}
	/* Should not reach here in JIT sandbox model */
	KD_PR_ERR("kd_mutex_unlock: unexpected locked state %d\n", locked);
	return -EINVAL;
}

__attribute__((noipa)) noinline notrace void
_kd_mutex_unlock(struct kd_mutex *lock)
{
	_kd_mutex_unlock_checked(lock);
}
