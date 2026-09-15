// SPDX-License-Identifier: GPL-2.0
/*
 * Independent lane validation and native CALL bodies retaining two real owners.
 * Private implementation included only by mutex_parallel_workload.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static bool kd_parallel_check(bool valid, unsigned int lane, const char *phase)
{
	if (!valid) {
		atomic_inc(&parallel_failures);
		pr_err("kd_parallel error: lane=%u phase=%s task=%d\n", lane,
		       phase, current->pid);
	}
	return valid;
}

static unsigned int kd_parallel_waiter_count(struct kd_parallel_lane *lane)
{
	struct mutex_waiter *waiter;
	unsigned long flags;
	unsigned int count = 0;

	if (!mutex_parallel_retired)
		return kd_mutex_debug_waiter_count(&lane->a);
	/* Retired admission does not create kdlock queue nodes. Observe Linux's
	 * real wait list so a no-contention call cannot pass as stale-JIT refusal. */
	raw_spin_lock_irqsave(&lane->a.wait_lock, flags);
	list_for_each_entry(waiter, &lane->a.wait_list, list)
		count++;
	raw_spin_unlock_irqrestore(&lane->a.wait_lock, flags);
	return count;
}

/* Bounded waits release fixture-owned locks on failure. They do not cancel a
 * kdlock request, unlock a foreign mutex, or manufacture an owner ACK. */
static bool kd_parallel_wait(struct kd_parallel_lane *lane, atomic_t *value,
			     unsigned int required)
{
	unsigned long deadline = jiffies + 10 * HZ;

	for (;;) {
		unsigned int queued = value ? 0 :
					      kd_parallel_waiter_count(lane);
		bool ready = value ? (atomic_read_acquire(value) & required) ==
					     required :
				     queued >= required;

		if (ready) {
			if (!value && required == 3 && mutex_parallel_retired)
				pr_info("kd_parallel native queued: lane=%u waiters=%u\n",
					(unsigned int)(lane - parallel_lanes),
					queued);
			return true;
		}
		if (time_after_eq(jiffies, deadline))
			return kd_parallel_check(false, lane - parallel_lanes,
						 "wait-timeout");
		usleep_range(100, 200);
	}
}

static bool kd_parallel_owners(struct kd_parallel_lane *lane,
			       struct kd_parallel_record *record)
{
	return record->task == current && !preempt_count() &&
	       !irqs_disabled() && record->owner &&
	       kd_test_mutex_owner(&lane->a) == record->owner &&
	       kd_test_mutex_owner(&lane->b) == record->owner;
}

/* A borrowed waiter can acquire an unrelated native mutex after changing
 * comm. That unlock must not consume A's routing reference or masquerade as
 * an owner ACK for A/B. Keep the rename through both later borrowed unlocks. */
static bool kd_parallel_routed_native(struct kd_parallel_lane *lane,
				      struct kd_parallel_record *record)
{
	unsigned long owner, after;
	bool valid;

	mutex_lock(&lane->native);
	owner = kd_test_mutex_owner(&lane->native);
	lane->native_acquired++;
	valid = owner == (unsigned long)current &&
		kd_parallel_owners(lane, record) && lane->native_acquired == 1;
	mutex_unlock(&lane->native);
	after = kd_test_mutex_owner(&lane->native);
	lane->native_released++;
	valid &= !after && kd_parallel_owners(lane, record) &&
		 lane->native_released == 1 &&
		 !strcmp(current->comm, "kd_renamed");
	pr_info("kd_parallel routed native: lane=%u task=%d waiter=%lx owner=%lx outer=%lx inner=%lx local=%lx local_owner=%lx after_owner=%lx acquired=%u released=%u comm=%s valid=%u\n",
		record->lane, current->pid, (unsigned long)current,
		record->owner, (unsigned long)&lane->a, (unsigned long)&lane->b,
		(unsigned long)&lane->native, owner, after,
		lane->native_acquired, lane->native_released, current->comm,
		valid);
	return kd_parallel_check(valid, record->lane, "native-task-routing");
}

/* This unlearned direct callee runs on the original waiter. Both lanes must
 * reach it before either can finish; the second also waits for the first's
 * post-unlock observation, so its own retained ownership is rechecked after
 * another frame/task record has really completed. */
static __attribute__((noipa)) noinline void
kd_parallel_native(struct kd_parallel_lane *lane,
		   struct kd_parallel_record *record)
{
	unsigned int index = record->lane;
	bool observe = mutex_parallel_armed && record->role == KD_PAR_WAITER;
	bool borrowed = observe && !mutex_parallel_retired &&
			(!mutex_parallel_shared_cpu || !index);
	bool valid;

	record->owner = kd_test_mutex_owner(&lane->a);
	valid = kd_parallel_owners(lane, record) && record->before == 1 &&
		record->held == 1 && !record->called && !record->after &&
		record->value == (index * 8UL + record->role + 1) * 3 + 17;
	valid &= (record->owner != (unsigned long)current) == borrowed;
	if (!kd_parallel_check(valid, index, "native-entry"))
		return;
	if (borrowed && native_resume_rename)
		kd_test_rename("kd_renamed");
	if (mutex_parallel_armed && mutex_parallel_shared_cpu && index &&
	    record->role == KD_PAR_OWNER) {
		/* The refused delegate returns to its combiner's own native CS.
		 * Record its identity on the same CPU, without inspecting or
		 * extending the other task's still-live executor frame. */
		pr_info("kd_parallel contender: task=%d owner=%lx cpu=%u valid=1\n",
			current->pid, record->owner, raw_smp_processor_id());
	}
	if (observe) {
		pr_info("kd_parallel arrive: lane=%u task=%d waiter=%lx owner=%lx outer=%lx inner=%lx record=%lx before=%u held=%u called=%u after=%u value=%lx cpu=%u comm=%s valid=1\n",
			index, current->pid, (unsigned long)current,
			record->owner, (unsigned long)&lane->a,
			(unsigned long)&lane->b, (unsigned long)record,
			record->before, record->held, record->called,
			record->after, record->value, raw_smp_processor_id(),
			current->comm);
		/* Full-order RMW publishes this observation to the other waiter. */
		atomic_fetch_or(BIT(index), &parallel_arrived);
		if (!kd_parallel_wait(lane, &parallel_arrived, 3))
			return;
		/* Both real frames must exist before either renamed waiter takes
		 * its unrelated native C. The controller observes both returns
		 * before starting pool pressure or closing source admission. */
		if (borrowed && native_resume_rename &&
		    !kd_parallel_routed_native(lane, record))
			return;
		/* The controller closes source admission only after observing both
		 * real arrivals. Retained physical owners and ACK routing must still
		 * work while draining; this gate never fabricates executor state. */
		if (READ_ONCE(mutex_parallel_source_hold)) {
			unsigned long deadline = jiffies + 10 * HZ;

			while (READ_ONCE(mutex_parallel_source_hold)) {
				if (time_after_eq(jiffies, deadline)) {
					kd_parallel_check(
						false, index,
						"source-retire-timeout");
					break;
				}
				usleep_range(100, 200);
			}
		}
		if (index != mutex_parallel_first &&
		    !kd_parallel_wait(lane, &parallel_done,
				      BIT(mutex_parallel_first)))
			return;
		/* Keep the second physical B owned until a non-target task has
		 * acquired/released the first B and failed trylock on this B.
		 * The bit comes from a real native unlock, never an owner ACK. */
		if (mutex_parallel_peers && index != mutex_parallel_first &&
		    !kd_parallel_wait(lane, &parallel_peer_done,
				      BIT(mutex_parallel_first)))
			return;
		/* A final ACK is not task exit. Keep the second real frame alive
		 * until the controller observes the first client's pidfd becoming
		 * readable. This gate adds no reference to either task or frame. */
		if (mutex_parallel_peers && index != mutex_parallel_first) {
			unsigned long deadline = jiffies + 10 * HZ;

			while (READ_ONCE(mutex_parallel_exit_hold)) {
				if (time_after_eq(jiffies, deadline)) {
					kd_parallel_check(false, index,
							  "waiter-exit-timeout");
					break;
				}
				usleep_range(100, 200);
			}
		}
		/* Neither new request's resource refusal may retire this older
		 * frame. Wait for both own-owner completions, not just their logs
		 * before entering A1, without assuming native/gate fairness. */
		if (mutex_parallel_pressure && !index &&
		    !kd_parallel_wait(lane, &parallel_pressure_done, 3))
			return;
		valid = kd_parallel_owners(lane, record) &&
			record->before == 1 && record->held == 1 &&
			!record->called && !record->after;
		if (mutex_parallel_peers)
			valid &= signal_pending(current) &&
				 !!fatal_signal_pending(current) ==
					 (index == mutex_parallel_first);
		kd_parallel_check(valid, index, "retained-owner");
		pr_info("kd_parallel resume: lane=%u task=%d owner=%lx arrived=%u done=%u comm=%s pending=%u fatal=%u valid=%u\n",
			index, current->pid, record->owner,
			atomic_read(&parallel_arrived),
			atomic_read(&parallel_done), current->comm,
			!!signal_pending(current), !!fatal_signal_pending(current),
			valid);
	}
	record->called++;
	record->value ^= 0x5a5a;
}

/* Per-request stores and B acquisition precede the miss; replay would change
 * the record and the A-protected sequence/digest. No logical-current read is
 * allowed in this translated prefix. */
static __always_inline void kd_parallel_body(struct kd_parallel_lane *lane,
					     struct kd_parallel_record *record)
{
	mutex_lock(&lane->a);
	record->before++;
	record->value *= 3;
	lane->sequence++;
	lane->digest = lane->digest * 33 + lane->sequence;
	mutex_lock(&lane->b);
	record->held++;
	record->value += 17;
	kd_parallel_native(lane, record);
	record->after++;
	mutex_unlock(&lane->b);
	mutex_unlock(&lane->a);
}

/* A CALL miss marks its entry not-ready. Separate lexical entries let both
 * requests start normally, without patching publication state or racing a
 * recompiler to keep a single entry executable for the second queue. */
static __attribute__((noipa)) noinline void
kd_parallel_cs0(struct kd_parallel_record *record)
{
	kd_parallel_body(&parallel_lanes[0], record);
}

static __attribute__((noipa)) noinline void
kd_parallel_cs1(struct kd_parallel_record *record)
{
	kd_parallel_body(&parallel_lanes[1], record);
}

#include "../mutex_code_pool_workload.c"
#include "../mutex_parallel_peers.c"
#include "../mutex_shadow_workload.c"
