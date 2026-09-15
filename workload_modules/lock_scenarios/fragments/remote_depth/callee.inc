// SPDX-License-Identifier: GPL-2.0
/*
 * Deep chained critical sections and per-request native suffix probes.
 * Private implementation included only by remote_depth_workload.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static __always_inline void kd_deep_enter(unsigned int id)
{
	u32 word = atomic_read(&deep_locks[id].rlock.raw_lock.val) &
		   _Q_LOCKED_MASK;

	if (atomic_inc_return(&deep_inside[id]) != 1 ||
	    (word != _Q_LOCKED_VAL && word != (3U << _Q_LOCKED_OFFSET)))
		atomic_inc(&deep_failures);
}

static __always_inline void kd_deep_leave(unsigned int id)
{
	if (atomic_dec_return(&deep_inside[id]) != 0)
		atomic_inc(&deep_failures);
}

static __always_inline void kd_deep_step(unsigned int id)
{
	kd_cs_transition(&deep_states[id]);
	deep_completed[id]++;
}

static bool kd_deep_wait(unsigned int id, unsigned int queued)
{
	unsigned long deadline = jiffies + 15 * HZ;

	while (!READ_ONCE(deep_abort)) {
		int count = kd_spin_debug_waiter_count(&deep_locks[id].rlock);

		if (smp_load_acquire(&deep_holder[id]) &&
		    (!queued ||
		     (count >= 0 && (unsigned int)count >= queued &&
		      atomic_read(&deep_direct[id]) >= 2 &&
		      (queued < 2 || smp_load_acquire(&deep_published[id])))))
			return true;
		if (time_after_eq(jiffies, deadline)) {
			pr_err("kd_deep timeout: lock=%u queued=%u cpu=%u\n",
			       id, queued, raw_smp_processor_id());
			atomic_inc(&deep_failures);
			WRITE_ONCE(deep_abort, true);
			break;
		}
		cpu_relax();
	}
	return false;
}

/* Unlike kd_deep_wait(queued >= 2), this runs before the parent publishes
 * its nested request. Only actual predecessor admission opens this gate. */
static bool kd_deep_readmit_wait(unsigned int queued)
{
	unsigned long deadline = jiffies + 15 * HZ;
	unsigned int id = remote_chain_readmit_layer;

	while (!READ_ONCE(deep_abort)) {
		int count = kd_spin_debug_waiter_count(&deep_locks[id].rlock);

		if (smp_load_acquire(&deep_holder[id]) && count >= 0 &&
		    (unsigned int)count >= queued &&
		    atomic_read(&deep_direct[id]) >= (int)queued + 1)
			return true;
		if (time_after_eq(jiffies, deadline)) {
			pr_err("kd_deep readmit timeout: queued=%u cpu=%u\n",
			       queued, raw_smp_processor_id());
			atomic_inc(&deep_failures);
			WRITE_ONCE(deep_abort, true);
		}
		cpu_relax();
	}
	return false;
}

static __attribute__((noipa)) noinline bool
kd_deep_prepare(struct kd_deep_record *record)
{
	unsigned int i;
	unsigned int id = ++deep_requests;
	unsigned long deadline = jiffies + 15 * HZ;

	*record = (struct kd_deep_record){ .task = current,
					   .id = id,
					   .value = id };
	if (!READ_ONCE(remote_chain_stage))
		return true;
	WRITE_ONCE(deep_waiter, current);
	WRITE_ONCE(deep_origin_cpu, raw_smp_processor_id());
	while (!smp_load_acquire(&deep_dependency_ready)) {
		if (time_after_eq(jiffies, deadline)) {
			atomic_inc(&deep_failures);
			WRITE_ONCE(deep_abort, true);
			return false;
		}
		cpu_relax();
	}
	for (i = 0; i < remote_chain_depth; i++)
		if (!kd_deep_wait(i, 1))
			return false;
	if (remote_chain_readmit && !kd_deep_readmit_wait(3))
		return false;
	return true;
}

static __attribute__((noipa)) noinline void
kd_deep_native_probe(struct kd_deep_record *record)
{
	bool valid = current == record->task && record->before == 1 &&
		     !record->called && !record->after;

	if (!valid)
		atomic_inc(&deep_failures);
	record->called++;
	record->value += 17;
	pr_info("kd_deep native probe: task=%d cpu=%u record=%u valid=%u\n",
		current->pid, raw_smp_processor_id(), record->id, valid);
	if (native_resume_rename)
		kd_test_rename("kd_renamed");
}

static __always_inline void kd_deep_probe(struct kd_deep_record *record)
{
	record->before++;
	record->value *= 3;
	kd_deep_native_probe(record);
	record->after++;
	record->value ^= 0x5a5a;
}

static __attribute__((noipa)) noinline void
kd_deep_finish(const struct kd_deep_record *record)
{
	bool native = READ_ONCE(remote_chain_stage) > 1;
	unsigned long expected = native ? (record->id * 3UL + 17) ^ 0x5a5a :
					  record->id;
	bool valid = current == record->task && record->before == native &&
		     record->called == native && record->after == native &&
		     record->value == expected && !preempt_count() &&
		     !irqs_disabled();

	if (!valid)
		atomic_inc(&deep_failures);
	deep_checked++;
	if (native && native_resume_rename)
		kd_test_rename("klock_test");
	pr_info("kd_deep request: task=%d cpu=%u record=%u before=%u called=%u after=%u valid=%u armed=%u\n",
		current->pid, raw_smp_processor_id(), record->id,
		record->before, record->called, record->after, valid,
		!!remote_chain_stage);
}

/* Each configured depth has a bounded source CFG. Repeated runtime tests of
 * depth around an acquisition loop would lose the lexical lock boundary. */
#define DEEP_ACQUIRE(i)                              \
	smp_store_release(&deep_published[i], true); \
	spin_lock(&deep_locks[i]);                   \
	kd_deep_enter(i);                            \
	kd_deep_step(i)
#define DEEP_RELEASE(i, first)                             \
	kd_deep_leave(i);                                  \
	spin_unlock(&deep_locks[i]);                       \
	if ((first) && READ_ONCE(remote_chain_stage) == 4) \
	kd_deep_probe(&record)
#define DEEP_ACQUIRE_4   \
	DEEP_ACQUIRE(0); \
	DEEP_ACQUIRE(1); \
	DEEP_ACQUIRE(2); \
	DEEP_ACQUIRE(3)
#define DEEP_ACQUIRE_5  \
	DEEP_ACQUIRE_4; \
	DEEP_ACQUIRE(4)
#define DEEP_ACQUIRE_6  \
	DEEP_ACQUIRE_5; \
	DEEP_ACQUIRE(5)
#define DEEP_ACQUIRE_7  \
	DEEP_ACQUIRE_6; \
	DEEP_ACQUIRE(6)
#define DEEP_ACQUIRE_8  \
	DEEP_ACQUIRE_7; \
	DEEP_ACQUIRE(7)
#define DEEP_FORWARD_4      \
	DEEP_RELEASE(0, 1); \
	DEEP_RELEASE(1, 0); \
	DEEP_RELEASE(2, 0)
#define DEEP_FORWARD_5  \
	DEEP_FORWARD_4; \
	DEEP_RELEASE(3, 0)
#define DEEP_FORWARD_6  \
	DEEP_FORWARD_5; \
	DEEP_RELEASE(4, 0)
#define DEEP_FORWARD_7  \
	DEEP_FORWARD_6; \
	DEEP_RELEASE(5, 0)
#define DEEP_FORWARD_8  \
	DEEP_FORWARD_7; \
	DEEP_RELEASE(6, 0)
#define DEEP_REST_4         \
	DEEP_RELEASE(1, 0); \
	DEEP_RELEASE(0, 0)
#define DEEP_REST_5         \
	DEEP_RELEASE(2, 0); \
	DEEP_REST_4
#define DEEP_REST_6         \
	DEEP_RELEASE(3, 0); \
	DEEP_REST_5
#define DEEP_REST_7         \
	DEEP_RELEASE(4, 0); \
	DEEP_REST_6
#define DEEP_REST_8         \
	DEEP_RELEASE(5, 0); \
	DEEP_REST_7
#define DEEP_REQUEST(n)                                                       \
	static __attribute__((noipa)) noinline void kd_deep_request_##n(void) \
	{                                                                     \
		struct kd_deep_record record;                                 \
		if (!kd_deep_prepare(&record))                                \
			return;                                               \
		DEEP_ACQUIRE_##n;                                             \
		if (READ_ONCE(remote_chain_stage))                            \
			deep_prefix++;                                        \
		if (READ_ONCE(remote_chain_stage) == 2)                       \
			kd_deep_probe(&record);                               \
		if (READ_ONCE(remote_chain_reverse)) {                        \
			DEEP_RELEASE(n - 2, 1);                               \
			DEEP_REST_##n;                                        \
		} else {                                                      \
			DEEP_FORWARD_##n;                                     \
		}                                                             \
		if (READ_ONCE(remote_chain_stage) == 3)                       \
			kd_deep_probe(&record);                               \
		spin_lock(&deep_locks[n]);                                    \
		kd_deep_enter(n);                                             \
		if (READ_ONCE(remote_chain_stage) == 5)                       \
			kd_deep_probe(&record);                               \
		if (READ_ONCE(remote_chain_stage))                            \
			deep_suffix++;                                        \
		kd_deep_step(n - 1);                                          \
		kd_deep_leave(n);                                             \
		spin_unlock(&deep_locks[n]);                                  \
		kd_deep_leave(n - 1);                                         \
		spin_unlock(&deep_locks[n - 1]);                              \
		kd_deep_finish(&record);                                      \
	}
DEEP_REQUEST(4)
DEEP_REQUEST(5)
DEEP_REQUEST(6)
DEEP_REQUEST(7)
DEEP_REQUEST(8)
