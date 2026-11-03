/* SPDX-License-Identifier: GPL-2.0 */
/* Generic prepared killable acquisition. These test ioctls are mechanism
 * evidence; no application body or real-world API workload is substituted. */
#include <linux/jiffies.h>
#include <linux/sched/signal.h>
#include <linux/string.h>
#include "kd_mutex_api.h"

static DEFINE_KD_RWSEM(killable_inner);
static struct kd_rwsem killable_depth_sem[4];
static struct kd_mutex killable_depth_mutex[4];
static struct jit_killable_slot killable_slots[JIT_KILLABLE_SLOTS];
static u64 killable_release;
static atomic64_t killable_holders = ATOMIC64_INIT(0);
#ifdef JIT_CONTINUATION_HELPER
#include "helper.inc"
#endif

static bool killable_idle(void)
{
	unsigned int i;

#ifdef JIT_CONTINUATION_HELPER
	if (!kd_mutex_is_idle(&helper_child) || raw_spin_is_locked(&helper_native_lock) ||
	    rwsem_is_locked(&helper_native_write_a) || rwsem_is_locked(&helper_native_write_b))
		return false;
#endif
	for (i = 0; i < 4; ++i)
		if (!kd_rwsem_is_idle(&killable_depth_sem[i]) ||
		    !kd_mutex_is_idle(&killable_depth_mutex[i]))
			return false;
	return !atomic_read(&control) && continuation_idle() &&
		kd_rwsem_is_idle(&killable_inner) && !atomic64_read(&killable_holders);
}

static void killable_init(void)
{
	unsigned int i;

	for (i = 0; i < 4; ++i) {
		kd_rwsem_init(&killable_depth_sem[i]);
		kd_mutex_init(&killable_depth_mutex[i]);
	}
}

static __attribute__((noipa)) int
killable_body(struct jit_killable_slot *slot, unsigned int flags)
{
	bool outer_released = false;
	unsigned int i, sem_held = 0, mutex_held = 0;
	int result = kd_down_write_killable(&test_lock);

	asm volatile(".globl jit_continuation_entry\n.set jit_continuation_entry, 1b\n\t"
		     ".pushsection .discard.noendbr\n\t"
		     _ASM_PTR " jit_continuation_entry\n\t.popsection\n\t" : : : "memory");
	if (result)
		return result;
	if (atomic_inc_return(&writers) != 1)
		atomic_inc(&failures);
	WRITE_ONCE(prefix, READ_ONCE(prefix) + 1);
	WRITE_ONCE(slot->prefix, READ_ONCE(slot->prefix) + 1);
#ifdef JIT_CONTINUATION_HELPER
	if (flags & (JIT_KILLABLE_NATIVE_WRITE | JIT_KILLABLE_NATIVE_WRITE_EARLY)) {
		jit_test_native_write_lock(&helper_native_write_a);
		if (flags & JIT_KILLABLE_NATIVE_WRITE_EARLY) {
			WRITE_ONCE(suffix, READ_ONCE(suffix) + 1);
			if (atomic_dec_return(&writers))
				atomic_inc(&failures);
			kd_up_write(&test_lock);
			WRITE_ONCE(helper_native_write_body_after, READ_ONCE(helper_native_write_body_after) + 1);
			jit_test_native_write_unlock(&helper_native_write_a);
			return 0;
		}
		jit_test_native_write_lock(&helper_native_write_b);
		/* Keep B live across the non-LIFO release of the older A share. */
		jit_test_native_write_unlock(&helper_native_write_a);
		WRITE_ONCE(helper_native_write_body_after, READ_ONCE(helper_native_write_body_after) + 1);
		jit_test_native_write_unlock(&helper_native_write_b);
	}
	if (flags & (JIT_KILLABLE_MEMORY | JIT_KILLABLE_MEMORY_EARLY)) {
		jit_test_memory_observe(0);
		if (flags & JIT_KILLABLE_MEMORY_EARLY) {
			JIT_MEMORY_INSTRUCTION("incl", __preempt_count);
			JIT_MEMORY_PREEMPT_READ();
			jit_test_memory_observe(1);
			WRITE_ONCE(suffix, READ_ONCE(suffix) + 1);
			if (atomic_dec_return(&writers))
				atomic_inc(&failures);
			kd_up_write(&test_lock);
			WRITE_ONCE(helper_memory_body_after, READ_ONCE(helper_memory_body_after) + 1);
			JIT_MEMORY_INSTRUCTION("decl", __preempt_count);
			/* Final instruction restoration continues here on O with the
			 * original source SP/flags, outside every retained lock. */
			jit_test_memory_observe(2);
			return 0;
		}
		JIT_MEMORY_INSTRUCTION("incq", helper_memory_counter);
		jit_test_memory_observe(1);
		JIT_MEMORY_INSTRUCTION("incl", __preempt_count);
		JIT_MEMORY_PREEMPT_READ();
		jit_test_memory_observe(2);
		JIT_MEMORY_INSTRUCTION("decl", __preempt_count);
		JIT_MEMORY_INSTRUCTION("decq", helper_memory_counter);
		jit_test_memory_observe(3);
		WRITE_ONCE(helper_memory_body_after, READ_ONCE(helper_memory_body_after) + 1);
	}
	if (flags & (JIT_KILLABLE_NATIVE_PAIRS | JIT_KILLABLE_NATIVE_EARLY)) {
		jit_test_native_spin_lock(&helper_native_lock);
		if (flags & JIT_KILLABLE_NATIVE_EARLY) {
			WRITE_ONCE(suffix, READ_ONCE(suffix) + 1);
			if (atomic_dec_return(&writers))
				atomic_inc(&failures);
			kd_up_write(&test_lock);
			/* A Native ticket keeps this scalar tail on E after the KD
			 * writer is released. The final Native release ends the scope. */
			WRITE_ONCE(helper_native_body_after, READ_ONCE(helper_native_body_after) + 1);
			jit_test_native_spin_unlock(&helper_native_lock);
			return 0;
		}
		if (jit_test_native_spin_try(&helper_native_lock))
			atomic_inc(&failures);
		for (i = 0; i < 9; ++i)
			jit_test_native_rcu_lock();
		for (i = 0; i < 9; ++i)
			jit_test_native_rcu_unlock();
		jit_test_native_spin_unlock(&helper_native_lock);
		if (jit_test_native_spin_try(&helper_native_lock))
			jit_test_native_spin_unlock(&helper_native_lock);
		else
			atomic_inc(&failures);
		WRITE_ONCE(helper_native_body_after, READ_ONCE(helper_native_body_after) + 1);
	}
	if (flags & (JIT_KILLABLE_HELPER | JIT_KILLABLE_HELPER_WAIT | JIT_KILLABLE_HELPER_TAIL)) {
		unsigned long index = slot - killable_slots;
		unsigned long value;

		if (flags & JIT_KILLABLE_HELPER_WAIT)
			value = jit_test_call_wait(index, JIT_HELPER_A1, JIT_HELPER_A2,
				JIT_HELPER_A3, JIT_HELPER_A4, JIT_HELPER_A5);
		else if (flags & JIT_KILLABLE_HELPER_TAIL)
			value = jit_test_call_tail(index, JIT_HELPER_A1, JIT_HELPER_A2,
				JIT_HELPER_A3, JIT_HELPER_A4, JIT_HELPER_A5);
		else
			value = jit_test_call_scalar(index, JIT_HELPER_A1, JIT_HELPER_A2,
				JIT_HELPER_A3, JIT_HELPER_A4, JIT_HELPER_A5);
		WRITE_ONCE(helper_slots[index].body_result, value);
		if (value != JIT_HELPER_RESULT(index))
			atomic_inc(&failures);
		WRITE_ONCE(helper_slots[index].body_after, READ_ONCE(helper_slots[index].body_after) + 1);
	}
#endif
	if (flags & JIT_KILLABLE_NESTED) {
		/* A conventional nested entry remains on this executor while its
		 * killable predicate refers to the retained logical origin. */
		result = (kd_down_write_killable)(&killable_inner);
		WRITE_ONCE(slot->child_result, result);
		if (!result) {
			WRITE_ONCE(slot->child_prefix, READ_ONCE(slot->child_prefix) + 1);
			(kd_up_write)(&killable_inner);
		} else if (result != -EINTR) {
			atomic_inc(&failures);
		}
		WRITE_ONCE(hot_taken, READ_ONCE(hot_taken) + 1);
	}
	if (flags & JIT_KILLABLE_DEPTH) {
		/* Eight real distinct-object children plus the outer make depth9.
		 * Conventional calls are false requests on this executor; no helper
		 * hides the nesting from the translated source or owner protocol. */
		for (i = 0; i < 4; ++i) {
			result = (kd_down_write_killable)(&killable_depth_sem[i]);
			if (result)
				goto depth_cleanup;
			++sem_held;
			WRITE_ONCE(slot->child_prefix, READ_ONCE(slot->child_prefix) + 1);
			result = (kd_mutex_lock_killable)(&killable_depth_mutex[i]);
			if (result)
				goto depth_cleanup;
			++mutex_held;
			WRITE_ONCE(slot->child_prefix, READ_ONCE(slot->child_prefix) + 1);
		}
		WRITE_ONCE(slot->tail_ready, 9);
		if (flags & JIT_KILLABLE_EARLY) {
			WRITE_ONCE(suffix, READ_ONCE(suffix) + 1);
			if (atomic_dec_return(&writers))
				atomic_inc(&failures);
			kd_up_write(&test_lock);
			outer_released = true;
		}
depth_cleanup:
		WRITE_ONCE(slot->child_result, result);
		if (result)
			atomic_inc(&failures);
		/* Release in acquisition order, while later children remain held. */
		for (i = 0; i < sem_held; ++i)
			(kd_up_write)(&killable_depth_sem[i]);
		for (i = 0; i < mutex_held; ++i)
			(kd_mutex_unlock)(&killable_depth_mutex[i]);
		WRITE_ONCE(slot->tail_done, sem_held + mutex_held);
	}
	if (flags & (JIT_KILLABLE_REUSE | JIT_KILLABLE_TRUE)) {
		unsigned int count = flags & JIT_KILLABLE_REUSE ? 128 : 1;

		for (i = 0; i < count; ++i) {
			if ((flags & JIT_KILLABLE_TRUE) || (i & 1))
				result = kd_mutex_lock_killable(&killable_depth_mutex[0]);
			else
				result = (kd_mutex_lock_killable)(&killable_depth_mutex[0]);
			WRITE_ONCE(slot->child_result, result);
			if (result) {
				atomic_inc(&failures);
				break;
			}
			WRITE_ONCE(slot->child_prefix, READ_ONCE(slot->child_prefix) + 1);
			kd_mutex_unlock(&killable_depth_mutex[0]);
		}
	}
	if (outer_released)
		return 0;
	WRITE_ONCE(suffix, READ_ONCE(suffix) + 1);
	if (atomic_dec_return(&writers))
		atomic_inc(&failures);
	if (flags & JIT_KILLABLE_DOWNGRADE) {
		unsigned long budget = 1UL << 28;

		kd_downgrade_write(&test_lock);
		WRITE_ONCE(slot->tail_ready, 1);
		/* A bounded scalar tail remains on the executor. PAUSE must execute
		 * on every iteration; no original-task continuation is used. */
		while (!(READ_ONCE(killable_release) & JIT_KILLABLE_RELEASE_TAIL) && --budget)
			cpu_relax();
		if (!budget)
			atomic_inc(&failures);
		WRITE_ONCE(slot->tail_done, 0x1234);
		kd_up_read(&test_lock);
		return 0;
	}
	kd_up_write(&test_lock);
	return 0;
}

static void killable_hold(struct kd_rwsem *sem, u64 bit, bool read)
{
	unsigned long deadline = jiffies + 30 * HZ;

	if (read)
		kd_down_read(sem);
	else
		(kd_down_write)(sem);
	atomic64_or(bit, &killable_holders);
	while (!(READ_ONCE(killable_release) & bit)) {
		if (time_after(jiffies, deadline)) {
			atomic_inc(&failures);
			break;
		}
		schedule_timeout_uninterruptible(1);
	}
	atomic64_andnot(bit, &killable_holders);
	if (read)
		kd_up_read(sem);
	else
		(kd_up_write)(sem);
}

static void killable_queue_snapshot(struct kd_mutex *gate, u64 *pids,
				    u64 *states, u64 *count)
{
	struct kd_wait_node *node;
	unsigned long flags;

	raw_spin_lock_irqsave(&gate->wait_lock, flags);
	node = gate->wait_head;
	if (node) {
		do {
			if (*count == JIT_KILLABLE_SLOTS) {
				atomic_inc(&failures);
				break;
			}
			pids[*count] = node->request->logical_origin->pid;
			states[*count] = node->request->state;
			++*count;
			node = node->next;
		} while (node != gate->wait_head);
	}
	raw_spin_unlock_irqrestore(&gate->wait_lock, flags);
}

static long killable_ioctl(unsigned int cmd, void __user *user)
{
	struct jit_killable_snapshot state = { .version = 1 };
	struct jit_killable_run run;
	unsigned int i;
	unsigned int before_preempt;
	bool before_irqs;
	unsigned int max_operation = JIT_KILLABLE_INNER_HOLDER;
	u64 release;
	int result;

#ifdef JIT_CONTINUATION_HELPER
	if (cmd == JIT_HELPER_SNAPSHOT)
		return helper_snapshot(user);
	if (cmd == JIT_NATIVE_SNAPSHOT)
		return helper_native_snapshot(user);
	if (cmd == JIT_MEMORY_SNAPSHOT)
		return helper_memory_snapshot(user);
	if (cmd == JIT_NATIVE_WRITE_SNAPSHOT)
		return helper_native_write_snapshot(user);
	if (cmd == JIT_HELPER_UNREGISTER) {
		if (!killable_idle() || atomic_cmpxchg(&control, 0, -1))
			return -EBUSY;
		result = helper_unregister();
		atomic_set_release(&control, 0);
		return result;
	}
#endif
	if (cmd == JIT_KILLABLE_SNAPSHOT) {
		state.lock_address = (unsigned long)&test_lock.gate;
		state.inner_address = (unsigned long)&killable_inner.gate;
		state.entry = (unsigned long)jit_continuation_entry;
		state.active = atomic_read(&control);
		state.holder_mask = atomic64_read(&killable_holders);
		state.release_mask = READ_ONCE(killable_release);
		state.phase = atomic_long_read(&test_lock.admission);
		state.readers = atomic_long_read(&test_lock.readers);
		killable_queue_snapshot(&test_lock.gate, state.queue_pid,
			state.queue_state, &state.queue_count);
		killable_queue_snapshot(&killable_inner.gate, state.inner_queue_pid,
			state.inner_queue_state, &state.inner_queue_count);
		for (i = 0; i < JIT_KILLABLE_SLOTS; ++i) {
			struct jit_killable_slot *from = &killable_slots[i];
			struct jit_killable_slot *to = &state.slots[i];

			to->returned = smp_load_acquire(&from->returned);
			to->pid = READ_ONCE(from->pid);
			to->prefix = READ_ONCE(from->prefix);
			to->child_prefix = READ_ONCE(from->child_prefix);
			to->child_result = READ_ONCE(from->child_result);
			to->result = READ_ONCE(from->result);
			to->tail_ready = READ_ONCE(from->tail_ready);
			to->tail_done = READ_ONCE(from->tail_done);
		}
		state.errors = atomic_read(&failures);
		state.idle = killable_idle();
		return copy_to_user(user, &state, sizeof(state)) ? -EFAULT : 0;
	}
	if (cmd == JIT_KILLABLE_RELEASE) {
		u64 allowed = 15;

#ifdef JIT_CONTINUATION_HELPER
		allowed |= JIT_KILLABLE_RELEASE_HELPER | JIT_KILLABLE_RELEASE_NATIVE_WRITE;
#endif
		if (copy_from_user(&release, user, sizeof(release)))
			return -EFAULT;
		if (release & ~allowed)
			return -EINVAL;
		WRITE_ONCE(killable_release, READ_ONCE(killable_release) | release);
		return 0;
	}
	if (cmd == JIT_KILLABLE_RESET || cmd == JIT_CONTINUATION_PREPARE) {
		if (!killable_idle() || atomic_cmpxchg(&control, 0, -1))
			return -EBUSY;
		if (cmd == JIT_CONTINUATION_PREPARE)
			result = kd_rwsem_prepare(&test_lock,
				(unsigned long)jit_continuation_entry, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
		else {
			memset(killable_slots, 0, sizeof(killable_slots));
#ifdef JIT_CONTINUATION_HELPER
			memset(helper_slots, 0, sizeof(helper_slots));
			memset(helper_native_events, 0, sizeof(helper_native_events));
			WRITE_ONCE(helper_native_count, 0);
			WRITE_ONCE(helper_native_body_after, 0);
			helper_memory_reset();
			helper_native_write_reset();
#endif
			WRITE_ONCE(killable_release, 0);
			WRITE_ONCE(hot, 0);
			result = 0;
		}
		atomic_set_release(&control, 0);
		return result;
	}
	if (cmd != JIT_KILLABLE_RUN)
		return -ENOTTY;
	if (copy_from_user(&run, user, sizeof(run)))
		return -EFAULT;
#ifdef JIT_CONTINUATION_HELPER
	max_operation = JIT_KILLABLE_NATIVE_WRITE_PROGRESS;
#endif
	if (run.operation > max_operation || run.slot >= JIT_KILLABLE_SLOTS ||
	    (run.flags != 0 && run.flags != JIT_KILLABLE_NESTED && run.flags != JIT_KILLABLE_DOWNGRADE &&
	     run.flags != JIT_KILLABLE_DEPTH && run.flags != (JIT_KILLABLE_DEPTH | JIT_KILLABLE_EARLY) &&
	     run.flags != JIT_KILLABLE_REUSE && run.flags != JIT_KILLABLE_TRUE
#ifdef JIT_CONTINUATION_HELPER
	     && run.flags != JIT_KILLABLE_HELPER && run.flags != JIT_KILLABLE_HELPER_WAIT
	     && run.flags != JIT_KILLABLE_HELPER_TAIL
	     && run.flags != JIT_KILLABLE_NATIVE_PAIRS && run.flags != JIT_KILLABLE_NATIVE_EARLY
	     && run.flags != JIT_KILLABLE_MEMORY && run.flags != JIT_KILLABLE_MEMORY_EARLY
	     && run.flags != JIT_KILLABLE_NATIVE_WRITE && run.flags != JIT_KILLABLE_NATIVE_WRITE_EARLY
#endif
	    ) || run.reserved ||
	    (run.operation != JIT_KILLABLE_ROOT && run.flags))
		return -EINVAL;
	if (!atomic_add_unless(&control, 1, -1))
		return -EBUSY;
	if (cmpxchg(&killable_slots[run.slot].pid, 0, (u64)current->pid)) {
		atomic_dec(&control);
		return -EBUSY;
	}
	before_preempt = preempt_count();
	before_irqs = irqs_disabled();
#ifdef JIT_CONTINUATION_HELPER
	WRITE_ONCE(helper_slots[run.slot].origin_stack, (unsigned long)task_stack_page(current));
#endif
	if (run.operation == JIT_KILLABLE_ROOT)
		result = killable_body(&killable_slots[run.slot], run.flags);
#ifdef JIT_CONTINUATION_HELPER
	else if (run.operation == JIT_KILLABLE_NATIVE_WRITE_HOLDER) {
		helper_native_write_hold();
		result = 0;
	} else if (run.operation == JIT_KILLABLE_NATIVE_WRITE_PROGRESS) {
		WRITE_ONCE(helper_native_write_progress_pid, current->pid);
		WRITE_ONCE(helper_native_write_progress_cpu, raw_smp_processor_id());
		smp_store_release(&helper_native_write_progress, READ_ONCE(helper_native_write_progress) + 1);
		result = 0;
	}
#endif
	else {
		bool read = run.operation == JIT_KILLABLE_READ_HOLDER;
		u64 bit = run.operation == JIT_KILLABLE_INNER_HOLDER ?
			JIT_KILLABLE_RELEASE_INNER : read ?
			JIT_KILLABLE_RELEASE_READ : JIT_KILLABLE_RELEASE_WRITE;

		killable_hold(run.operation == JIT_KILLABLE_INNER_HOLDER ?
			&killable_inner : &test_lock, bit, read);
		result = 0;
	}
	if (preempt_count() != before_preempt || irqs_disabled() != before_irqs)
		atomic_inc(&failures);
	WRITE_ONCE(killable_slots[run.slot].result, result);
	smp_store_release(&killable_slots[run.slot].returned, 1);
	atomic_dec(&control);
	run.result = result;
	run.returned = 1;
	return copy_to_user(user, &run, sizeof(run)) ? -EFAULT : 0;
}
