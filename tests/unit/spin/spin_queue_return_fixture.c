/* Included after the production executor. CPU handoff is deterministic;
 * producer, rejection, queue acquisition and nested return bodies are real. */
static struct kd_spin_node queue_peer, *queue_resume;
static struct kd_exec_frame *queue_parent;
static unsigned int queue_polls, queue_switches, queue_enters, queue_exits;

#define _Q_LOCKED_PENDING_MASK 0xffff
#define _Q_TAIL_MASK_HL 0xffff0000u
#define KD_SPIN_DIAG_SLOWPATH 0
#define kd_spin_selftest_node_event(...) ((void)0)
#define smp_rmb() ((void)0)
#define prefetchw(p) ((void)(p))
#define smp_cond_load_relaxed_sched(p, condition) \
	({                                        \
		__auto_type VAL = *(p);           \
		BUG_ON(!(condition));             \
		VAL;                              \
	})
#define atomic_cond_read_acquire(p, condition) \
	smp_cond_load_relaxed_sched(&(p)->counter, condition)

static bool atomic_try_cmpxchg_relaxed(atomic_t *value, int *old, int new)
{
	if (value->counter != *old) {
		*old = value->counter;
		return false;
	}
	value->counter = new;
	return true;
}

static int encode_tail(int cpu, int index)
{
	CHECK(cpu == 0 && index == 0);
	return 1 << 16;
}

static int xchg_tail(struct qspinlock *word, int tail)
{
	int old = atomic_read(&word->val);

	CHECK(preentry_queue_case && mock_cpu == 0 && word->locked == 3);
	word->tail = tail >> 16;
	return old;
}

static struct kd_spin_node *decode_tail(int tail)
{
	CHECK((tail & _Q_TAIL_MASK_HL) == 3 << 16);
	return &queue_peer;
}

static void kd_spin_diag_waiter_enter(struct kd_spin_diag_slot *slot)
{
	CHECK((void *)slot == a_lock());
	queue_enters++;
}

static void kd_spin_diag_waiter_exit(struct kd_spin_diag_slot *slot)
{
	CHECK((void *)slot == a_lock());
	queue_exits++;
}

static void kd_spin_set_resume_node(struct kd_spin_node *node)
{
	queue_resume = node;
}

static bool kd_spin_is_ooo(struct qspinlock *lock)
{
	return kd_spin_word(lock)->locked == _Q_UNLOCKED_OOO_VAL;
}

static void check_and_set_combiner(struct qspinlock *word)
{
	CHECK(word->locked == 0);
	word->locked = _Q_LOCKED_COMBINER_VAL;
}

void kd_exec_remote_poll(struct kd_exec_frame *frame)
{
	CHECK(frame == queue_parent && mock_cpu == 0 &&
	      frame->remote_result == KD_EXEC_REMOTE_WAITING);
	queue_polls++;
}

static void kd_spin_diag_validate_lock_stack(const struct kd_spin_cpu_state *ptr)
{
	CHECK(kd_spin_lock_stack_depth(ptr) <= KD_EXEC_MAX_LOCK_DEPTH);
}

/* These scenarios exclusively queue virtual waiters on their executor's
 * stable C stack. Physical stack abandonment is tested by test_spin_wait. */
#define this_cpu_inc_return(v) (++(v))
#define this_cpu_inc(v) (++(v))
#define this_cpu_dec(v) (--(v))
#define barrier() __asm__ volatile("" ::: "memory")
static void kd_spin_publish_wait(struct kd_spin_node *node,
				 struct kd_spin_node *previous, void *wait_stack_top)
{
	(void)wait_stack_top;
	(void)node;
	(void)previous;
	abort();
}

#undef request
#undef run_combiner
#undef kd_spin_claim_origin
#define run_combiner checked_queue_combiner
#include "spin_queue_return_production.h"
#undef run_combiner
#define run_combiner checked_run_combiner
#define kd_spin_claim_origin test_claim_origin
#define request kd_spin_nodes[0]

static void preentry_queue_peer(void)
{
	kd_spinlock_t *gate = &origins[0];

	BUG_ON(queue_switches++ || mock_cpu != 0);
	CHECK(queue_peer.next == &request && request.locked &&
	      kd_spin_cpu.node_count == 1);
	CHECK(queue_parent->remote_result == KD_EXEC_REMOTE_WAITING);
	/* Publish a real trailing node before the rejected waiter takes the head. */
	request.next = &successor;
	gate->tail = 9;
	mock_cpu = 1;
	current = &tasks[1];
	run_combiner(a_lock(), &request);
	CHECK(!request.completed && !(fixture_request(&request)->result == KD_SPIN_RES_NATIVE_READY) &&
	      !(fixture_request(&request)->result == KD_SPIN_RES_RETRY));
	CHECK(queue_parent->remote_result == KD_EXEC_REMOTE_WAITING);
	CHECK(!request.locked && successor.locked && origins[0].held);
	kd_spin_release_origin(a_lock());
	gate->locked = 0;
	mock_cpu = 0;
	current = &tasks[0];
}

static unsigned int preentry_queue_return(void)
{
	const unsigned int reasons[] = { 8, 11, 12 };
	unsigned int cases = 0;

	for (unsigned int reason = 0; reason < ARRAY_SIZE(reasons); reason++) {
		struct pt_regs regs, before;
		unsigned long stack[2] = { 0x801, 0x802 };
		unsigned long locks[] = { (unsigned long)&origins[1] };
		enum kd_exec_lock_kind kinds[] = { KD_EXEC_LOCK_QUEUE_OWNER };
		kd_spinlock_t *gate;
		int ret;

		mode = reasons[reason];
		memset(kd_spin_nodes, 0, sizeof(kd_spin_nodes));
		memset(&queue_peer, 0, sizeof(queue_peer));
		memset(&successor, 0, sizeof(successor));
		memset(shadow_states, 0, sizeof(shadow_states));
		memset(&regs, 0x73, sizeof(regs));
		regs.ip = 0x801;
		regs.sp = (unsigned long)stack;
		regs.di = (unsigned long)a_lock();
		before = regs;
		mock_cpu = 0;
		current = &tasks[0];
		b_ref = (struct kd_spin_ref){ 0 };
		CHECK(kd_spin_entry_begin(&origins[1], KD_SPIN_ENTRY_HOOK,
					  &b_ref) == 0);
		kd_spin_entry_word(&b_ref)->locked = 3;
		kd_spin_claim_origin((struct qspinlock *)&origins[1]);
		queue_parent = real_frame_push(&regs, 0x900, locks[0], 1, 0x20000, &waiter);
		BUG_ON(!queue_parent);
		CHECK(kd_exec_frame_set_lock_entries(queue_parent, locks, kinds,
						     NULL, NULL, 1) == 0);
		queue_parent->spin_origin = b_ref;
		queue_parent->control_call.phase = KD_CALL_PENDING;
		shadow_states[0].lock_addr[0] = locks[0];
		for (unsigned int cpu = 0; cpu < 2; cpu++) {
			shadow_states[cpu].curr_cs_cpu = -1;
		}
		mock_cpu = 1;
		current = &tasks[1];
		executor_ref = (struct kd_spin_ref){ 0 };
		CHECK(kd_spin_entry_begin(&origins[0], KD_SPIN_ENTRY_HOOK,
					  &executor_ref) == 0);
		gate = kd_spin_entry_word(&executor_ref);
		gate->locked = 3;
		gate->tail = 3;
		kd_spin_claim_origin(a_lock());
		shadow_states[1].lock_addr[0] = (unsigned long)a_lock();
		successor.locked = true;
		fixture_request(&successor)->frame.logical_task = &waiter;
		successor.cpuid = 1;
		mock_cpu = 0;
		current = &tasks[0];
		scripts = pops = jit_disables = 0;
		queue_polls = queue_switches = queue_enters = queue_exits = 0;
		queue_resume = NULL;
		readmission_regs = regs;
		preentry_queue_case = true;
		ret = kd_spin_nested_lock(a_lock(), &regs, queue_parent);
		preentry_queue_case = false;
		printf("spin queued refusal: reason=%u result=%d parent=%d phase=%d registers=%u\n",
		       mode, ret, queue_parent->remote_result,
		       queue_parent->control_call.phase,
		       !memcmp(&regs, &before, sizeof(regs)));
		CHECK(ret == KD_SPIN_NESTED_ACQUIRED_QUEUE);
		CHECK(queue_parent->remote_result == KD_EXEC_REMOTE_IDLE &&
		      queue_parent->control_call.phase == KD_CALL_ACQUIRED);
		CHECK(!memcmp(&regs, &before, sizeof(regs)));
		CHECK(fixture_request(&request)->frame.gsbase == 0x20000 &&
		      fixture_request(&request)->frame.logical_task == &waiter);
		/* No ancestor notification arrives during this queue-head handoff. */
		CHECK(scripts == (mode != 8) && pops == scripts &&
		      !queue_polls && queue_switches == 1 &&
		      queue_enters == 1 && queue_exits == 1);
		CHECK(queue_resume == &request && !kd_spin_cpu.node_count &&
		      !request.completed && !(fixture_request(&request)->result == KD_SPIN_RES_NATIVE_READY) &&
		      (kd_exec_current_frame() != &fixture_request(&request)->frame));
		CHECK(origins[0].held && origins[1].held &&
		      kd_spin_entry_owner((raw_spinlock_t *)gate) == (unsigned long)current && mock_preempt == 2 &&
		      !mock_preempts[1]);
		kd_spin_release_origin(a_lock());
		/* The trailing peer is outside this return test; drain its saved tail. */
		gate->val.counter = 0;
		kd_spin_release_origin((struct qspinlock *)&origins[1]);
		CHECK(kd_exec_frame_abort(queue_parent) == 0);
		CHECK(real_frame_pop(queue_parent, NULL) == 0);
		CHECK(!mock_preempt && kd_spin_entries_check_idle() == 0);
		cases++;
	}
	return cases;
}
