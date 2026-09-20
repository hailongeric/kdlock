/* Included by spin_shadow_fixture.c; all producers and queue exits are real.
 * Ticket/CPU/peer operations remain deterministic substitutes, not live load. */
enum producer_path {
	PRODUCER_HEAD,
	PRODUCER_COMBINER,
	PRODUCER_SHADOW_FULL,
	PRODUCER_COMPLETE,
	PRODUCER_NATIVE,
	PRODUCER_PARENT_OOO,
	PRODUCER_FAST,
};

static struct qspinlock producer_lock;
static struct kd_exec_frame producer_frame;
static unsigned long producer_return;
/* Physical producer reads eight hook words before publication; the virtual
 * producer instead consumes the single CALL return word above. */
static unsigned long producer_saved[8] = { 0, 1, 2, 3, 4, 5, 6, 0x78900 };
static struct pt_regs producer_regs;

static void producer_setup(int count, bool virtual, enum producer_path path)
{
	memset(kd_spin_nodes, 0, sizeof(kd_spin_nodes));
	memset(&kd_spin_cpu, 0, sizeof(kd_spin_cpu));
	memset(&peer, 0, sizeof(peer));
	memset(&follower, 0, sizeof(follower));
	memset(&producer_lock, 0, sizeof(producer_lock));
	memset(&scheduling_word, 0, sizeof(scheduling_word));
	memset(&producer_frame, 0, sizeof(producer_frame));
	producer_case = true;
	mailbox_case = false;
	producer_virtual = virtual;
	producer_count = count;
	producer_peak = count;
	produced_node = resume_node = NULL;
	producer_successor = &follower;
	active_lock = &producer_lock;
	initial_count = count + 1;
	initial_depth = path == PRODUCER_SHADOW_FULL ? 8 :
			path == PRODUCER_PARENT_OOO  ? 1 :
						       0;
	contended = path == PRODUCER_COMBINER || path == PRODUCER_SHADOW_FULL;
	parent_ooo = path == PRODUCER_PARENT_OOO;
	peer_result = path == PRODUCER_NATIVE ? 5 : 3;
	kd_spin_requests = request_pool;
	begin_error = ticket_count = poll_calls = relax_calls = try_calls = 0;
	entries = exits = combined = handoffs = origin_claims = 0;
	producer_preempt = 1;
	kd_spin_cpu.node_count = count;
	memset(&kd_node_observations, 0, sizeof(kd_node_observations));
	/* Seed only this deterministic refusal test, never the kernel observer. */
	kd_node_observations.live = count;
	for (int i = 0; i < MAX_NODES; i++) {
		kd_spin_nodes[i].rsp = 0x80000 + i * 0x100;
		fixture_request(&kd_spin_nodes[i])->jit_context.lock_depth = 7;
	}
	kd_spin_cpu.curr_cs_cpu = 19;
	for (int i = 0; i < initial_depth; i++)
		kd_spin_cpu.lock_addr[i] = 0x40000 + i * 0x100;
	if (path == PRODUCER_COMPLETE || path == PRODUCER_NATIVE || parent_ooo)
		scheduling_word.tail = 3;
	else if (virtual && path != PRODUCER_FAST)
		scheduling_word.locked = 1;
	follower.locked = true;
	follower.rsp = 0x56780;
	producer_frame.valid = true;
	producer_frame.logical_task = &logical_task;
	producer_frame.gsbase = 0x34000;
	producer_frame.spin_origin = (struct kd_spin_ref){ &peer, 17 };
	producer_frame.jit_lock_depth = 1;
	producer_frame.jit_lock_addr[0] = 0x40000;
	producer_frame.jit_lock_kind[0] = KD_EXEC_LOCK_QUEUE_OWNER;
	producer_frame.jit_lock_node[0] = &peer;
	producer_frame.control_call.phase = KD_CALL_PENDING;
	producer_return = 0x78900;
	producer_regs = (struct pt_regs){ .ip = 0x12340,
					  .sp = (unsigned long)&producer_return,
					  .di = (unsigned long)active_lock };
	kd_spin_native_inputs.rsp = 0x12345678;
	kd_spin_native_inputs.regs_sp = (unsigned long)producer_saved;
}

static void producer_live_prefix(const struct kd_spin_node *before,
				 const struct kd_spin_jit_context *contexts)
{
	CHECK(kd_spin_cpu.node_count == producer_count);
	if (kd_node_trace)
		CHECK(!kd_node_observations.first_event &&
		      kd_node_observations.live == producer_count);
	for (int i = 0; i < producer_count; i++) {
		CHECK(!memcmp(&kd_spin_nodes[i], &before[i],
			      sizeof(before[i])));
		CHECK(!memcmp(&fixture_request(&kd_spin_nodes[i])->jit_context, &contexts[i],
			      sizeof(contexts[i])));
	}
}

static void producer_path_case(int count, bool virtual, enum producer_path path,
			       bool complete)
{
	struct kd_spin_node before[MAX_NODES];
	struct kd_spin_jit_context contexts[MAX_NODES];
	struct pt_regs regs_before;
	int result, expected;

	producer_setup(count, virtual, path);
	producer_frame.complete = complete;
	regs_before = producer_regs;
	memcpy(before, kd_spin_nodes, sizeof(before));
	for (int i = 0; i < MAX_NODES; i++)
		contexts[i] = fixture_request(&kd_spin_nodes[i])->jit_context;
	result = virtual ? kd_spin_nested_lock(active_lock, &producer_regs,
					       &producer_frame) :
			   __kd_spin_lock_slowpath(active_lock);
	if (count == MAX_NODES && path != PRODUCER_FAST) {
		expected = virtual ? -E2BIG : 0;
		CHECK(!produced_node && !entries && !exits && !combined);
		CHECK(try_calls == (virtual ? 0 : 2));
		CHECK(relax_calls == (virtual ? 0 : 1) && !poll_calls);
	} else if (path == PRODUCER_FAST) {
		expected = KD_SPIN_NESTED_ACQUIRED;
		CHECK(!produced_node && !entries && !exits && !combined);
	} else {
		bool remote = path == PRODUCER_COMPLETE ||
			      path == PRODUCER_NATIVE ||
			      path == PRODUCER_PARENT_OOO;

		/* Physical completion now uses one nonlocal restore for both old
		 * return classes 1/3; virtual returns retain their parent result. */
		expected =
			path == PRODUCER_COMBINER ?
				(virtual ? KD_SPIN_NESTED_ACQUIRED_QUEUE : 2) :
			path == PRODUCER_NATIVE ?
				(virtual ? KD_SPIN_NESTED_NATIVE : 5) :
			path == PRODUCER_PARENT_OOO ?
				(virtual ? 1 : 3) :
			path == PRODUCER_COMPLETE ?
				(virtual ?
					 (complete ? KD_SPIN_NESTED_PARENT_OOO :
						     KD_SPIN_NESTED_DELEGATED) :
					 3) :
				0;
		CHECK(produced_node == &kd_spin_nodes[count] &&
		      resume_node == produced_node);
		CHECK(producer_peak == count + 1 && entries == 1 && exits == 1);
		CHECK(combined == (path == PRODUCER_COMBINER));
		CHECK(!poll_calls &&
		      relax_calls == remote);
		CHECK(produced_node->rsp ==
		      (virtual ? regs_before.sp : 0x12345678));
		CHECK(fixture_request(produced_node)->frame.gsbase == (virtual ? 0x34000 : 0x12000));
		CHECK(!fixture_request(produced_node)->pinned_context &&
		      fixture_request(produced_node)->native_regs_decoded == !virtual);
		if (remote)
			CHECK(peer.next == produced_node &&
			      !producer_lock.locked);
		else
			CHECK(producer_lock.locked == 1 && origin_claims == 1);
		if (virtual) {
			struct kd_spin_jit_context *context =
				&produced_node->execution->jit_context;
			struct kd_exec_frame *child = &produced_node->execution->frame;

			CHECK(context->requester == &producer_frame &&
			      context->lock_depth == 2);
			CHECK(child->jit_lock_addr[0] ==
			      producer_frame.jit_lock_addr[0]);
			CHECK(child->jit_lock_kind[0] ==
			      producer_frame.jit_lock_kind[0]);
			CHECK(child->jit_lock_node[0] == &peer &&
			      !child->jit_lock_released[0]);
			CHECK(child->jit_lock_addr[1] ==
			      (unsigned long)active_lock);
			CHECK(child->jit_lock_kind[1] ==
			      KD_EXEC_LOCK_QUEUE_OWNER);
			CHECK(child->jit_lock_node[1] == produced_node &&
			      !child->jit_lock_released[1]);
			CHECK(fixture_request(produced_node)->frame.spin_origin.entry == &peer &&
			      fixture_request(produced_node)->frame.spin_origin.sequence == 17);
		}
	}
	CHECK(result == expected);
	producer_live_prefix(before, contexts);
	if (virtual) {
		bool acquired = result == KD_SPIN_NESTED_ACQUIRED ||
				result == KD_SPIN_NESTED_ACQUIRED_QUEUE;
		bool advanced = path == PRODUCER_COMPLETE &&
				count < MAX_NODES && !complete;

		CHECK(ticket_count == acquired);
		CHECK(producer_frame.control_call.phase ==
		      (acquired	  ? KD_CALL_ACQUIRED :
		       result < 0 ? KD_CALL_PENDING :
				    KD_CALL_COMPLETE));
		CHECK(producer_regs.ip ==
		      (advanced ? producer_return : regs_before.ip));
		CHECK(producer_regs.sp ==
		      regs_before.sp + (advanced ? sizeof(unsigned long) : 0));
		CHECK(producer_regs.di == regs_before.di);
		if (acquired) {
			struct kd_spin_ref ref = { active_lock, 1 };
			CHECK(kd_spin_entry_end(&ref) == 0);
		}
	}
	CHECK(!ticket_count);
	if (kd_node_trace) {
		const unsigned long *events = kd_node_observations.events;
		bool full = count == MAX_NODES && path != PRODUCER_FAST;
		bool reserved = !full && path != PRODUCER_FAST;
		bool remote = path == PRODUCER_COMPLETE ||
			      path == PRODUCER_PARENT_OOO;

		CHECK(events[KD_NODE_NATIVE_RESERVE] == (reserved && !virtual));
		CHECK(events[KD_NODE_VIRTUAL_RESERVE] == (reserved && virtual));
		CHECK(events[KD_NODE_NATIVE_FULL] == (full && !virtual));
		CHECK(events[KD_NODE_VIRTUAL_FULL] == (full && virtual));
		CHECK(events[KD_NODE_CONTEXT_MISSING] == 0 &&
		      events[KD_NODE_PREPARE_CANCEL] == 0);
		CHECK(events[KD_NODE_REMOTE_RETURN] == (reserved && remote));
		CHECK(events[KD_NODE_NATIVE_RETURN] ==
		      (reserved && path == PRODUCER_NATIVE));
		CHECK(events[KD_NODE_COMBINER_ENTER] ==
		      (reserved && path == PRODUCER_COMBINER));
		CHECK(events[KD_NODE_HEAD_RETURN] ==
		      (reserved && (path == PRODUCER_HEAD ||
				    path == PRODUCER_SHADOW_FULL)));
		CHECK(events[KD_NODE_REMOTE_POLL] ==
		      (reserved && virtual &&
		       (remote || path == PRODUCER_NATIVE)));
		CHECK(kd_node_observations.peak == (reserved ? count + 1 : 0));
		CHECK(kd_node_observations.peak_task ==
		      (reserved ? current->pid : 0));
	}
	producer_case = parent_ooo = false;
}

/* An empty first poll must not enter the handler. A later mailbox request
 * must still be serviced before either remote completion or native relay. */
static void run_mailbox_cases(void)
{
	for (unsigned int native = 0; native < 2; native++) {
		producer_setup(0, true, native ? PRODUCER_NATIVE : PRODUCER_COMPLETE);
		mailbox_case = true;
		CHECK(kd_spin_nested_lock(active_lock, &producer_regs, &producer_frame) ==
		      (native ? KD_SPIN_NESTED_NATIVE : KD_SPIN_NESTED_DELEGATED));
		CHECK(poll_calls == 1 && relax_calls == 3);
		CHECK(!producer_frame.remote_request && !ticket_count);
		CHECK(!kd_spin_cpu.node_count);
	}
	mailbox_case = producer_case = false;
}

static void producer_cancel_case(int count, unsigned int failure)
{
	struct kd_spin_node before[MAX_NODES];
	struct kd_spin_jit_context contexts[MAX_NODES];
	struct pt_regs regs_before;
	int expected = -EINVAL;

	producer_setup(count, true, PRODUCER_HEAD);
	switch (failure) {
	case 0:
		producer_frame.valid = false;
		break;
	case 1:
		producer_frame.jit_lock_depth = KD_EXEC_MAX_LOCK_DEPTH;
		expected = -E2BIG;
		break;
	case 2:
		kd_spin_requests = NULL;
		expected = -ENOMEM;
		break;
	case 3:
		begin_error = -EDEADLK;
		expected = -EDEADLK;
		break;
	case 4:
		producer_frame.remote_result = KD_EXEC_REMOTE_WAITING;
		expected = -EBUSY;
		break;
	case 5:
		producer_frame.remote_request = &peer;
		expected = -EBUSY;
		break;
	case 6:
		break; /* NULL register packet. */
	case 7:
		break; /* NULL frame. */
	case 8:
		break; /* NULL lock. */
	default:
		abort();
	}
	regs_before = producer_regs;
	memcpy(before, kd_spin_nodes, sizeof(before));
	for (int i = 0; i < MAX_NODES; i++)
		contexts[i] = fixture_request(&kd_spin_nodes[i])->jit_context;
	CHECK(kd_spin_nested_lock(failure == 8 ? NULL : active_lock,
				  failure == 6 ? NULL : &producer_regs,
				  failure == 7 ? NULL : &producer_frame) ==
	      expected);
	CHECK(!produced_node && !entries && !exits && !combined);
	CHECK(!ticket_count && !poll_calls && !relax_calls);
	CHECK(producer_frame.control_call.phase == KD_CALL_PENDING);
	CHECK(!memcmp(&producer_regs, &regs_before, sizeof(regs_before)));
	producer_live_prefix(before, contexts);
	if (kd_node_trace) {
		CHECK(kd_node_observations.events[KD_NODE_VIRTUAL_RESERVE] ==
		      (failure < 2));
		CHECK(kd_node_observations.events[KD_NODE_PREPARE_CANCEL] ==
		      (failure < 2));
		CHECK(kd_node_observations.events[KD_NODE_CONTEXT_MISSING] ==
		      (failure == 2));
	}
	producer_case = false;
}

static void run_producer_cases(bool recursive)
{
	int previous_checks = checks, previous_failures = failures, cases = 0;

	for (int round = 0; round < 3; round++) {
		for (int count = 0; count <= MAX_NODES; count++) {
			for (int path = PRODUCER_HEAD; path <= PRODUCER_FAST;
			     path++) {
				if (path != PRODUCER_FAST) {
					producer_path_case(count, false, path,
							   false);
					cases++;
				}
				if (path != PRODUCER_PARENT_OOO) {
					producer_path_case(count, true, path,
							   false);
					cases++;
				}
			}
			producer_path_case(count, true, PRODUCER_COMPLETE,
					   true);
			cases++;
			if (count == MAX_NODES)
				continue;
			for (unsigned int failure = 0; failure < 9; failure++) {
				producer_cancel_case(count, failure);
				cases++;
			}
		}
	}
	printf("spin node producers: trace=%d %d cases, %d checks, %d failures\n",
	       kd_node_trace, cases, checks - previous_checks,
	       failures - previous_failures);
	if (!recursive)
		return;
	previous_checks = checks;
	previous_failures = failures;
	cases = 0;
	producer_chain = true;
	for (int virtual = 0; virtual <= 1; virtual++) {
		producer_chain_virtual = virtual;
		for (int depth = 2; depth <= NESTED_DEPTH; depth++)
			for (int followers = 1; followers <= MAX_FOLLOWERS;
			     followers++)
				for (int reject = 0; reject <= 2; reject++) {
					producer_peak = 0;
					run_nested_case(
						depth, followers, 0,
						reject ? KD_EXE_NO_RUN : 0,
						reject ? reject - 1 : 0);
					CHECK(producer_peak == 1);
					if (kd_node_trace) {
						CHECK(!kd_node_observations
							       .first_event &&
						      kd_node_observations.live ==
							      0);
						CHECK(kd_node_observations
							      .peak == 1);
						CHECK(kd_node_observations.events
							      [KD_NODE_COMBINER_ENTER] ==
						      (unsigned long)depth);
						CHECK(kd_node_observations.events
							      [virtual ?
								       KD_NODE_VIRTUAL_RESERVE :
								       KD_NODE_NATIVE_RESERVE] ==
						      (unsigned long)depth);
					}
					cases++;
				}
	}
	producer_chain = false;
	printf("spin recursive producers: trace=%d %d cases, %d checks, %d failures\n",
	       kd_node_trace, cases, checks - previous_checks,
	       failures - previous_failures);
}

static void run_observer_checks(void)
{
	struct kd_node_observation before;
	int previous = checks;

	memset(&kd_node_observations, 0, sizeof(kd_node_observations));
	kd_node_trace = false;
	kd_spin_cpu.node_count = 3;
	kd_spin_selftest_node_event(KD_NODE_NATIVE_RESERVE);
	CHECK(!kd_node_observations.peak && !kd_node_observations.events[0]);
	kd_node_trace = true;
	kd_spin_cpu.node_count = 1;
	kd_spin_selftest_node_event(KD_NODE_NATIVE_RESERVE);
	CHECK(kd_node_observations.peak == 1 &&
	      !kd_node_observations.first_event);
	kd_spin_cpu.node_count = 0;
	kd_spin_selftest_node_event(KD_NODE_HEAD_RETURN);
	CHECK(!kd_node_observations.first_event);
	kd_spin_selftest_node_event(KD_NODE_HEAD_RETURN);
	CHECK(kd_node_observations.first_event == KD_NODE_HEAD_RETURN + 1);
	CHECK(kd_node_observations.first_count == 0 &&
	      kd_node_observations.first_expected == -1);
	before = kd_node_observations;
	kd_spin_selftest_node_event(KD_NODE_REMOTE_POLL);
	CHECK(kd_node_observations.first_event == before.first_event);
	CHECK(kd_node_observations.first_expected == before.first_expected);
	CHECK(kd_spin_cpu.node_count ==
	      0); /* The observer cannot repair count. */
	memset(&kd_node_observations, 0, sizeof(kd_node_observations));
	producer_preempt = 0;
	kd_spin_selftest_node_event(KD_NODE_CONTEXT_MISSING);
	CHECK(kd_node_observations.first_event == KD_NODE_CONTEXT_MISSING + 1);
	CHECK(kd_node_observations.first_preempt == 0);
	producer_preempt = 1;
	memset(&kd_node_observations, 0, sizeof(kd_node_observations));
	printf("spin observer guards: %d checks\n", checks - previous);
}

static void run_observer_allocation_checks(void)
{
	struct kd_node_observation empty = { 0 };
	int previous = checks, allocations = node_allocs, frees = node_frees;

	kd_spin_selftest_nodes_free();
	CHECK(!kd_node_records && node_frees == frees + 1);
	kd_spin_selftest_nodes_free();
	CHECK(node_frees == frees + 1);
	kd_node_trace = false;
	CHECK(kd_spin_selftest_nodes_init() == 0 && !kd_node_records &&
	      node_allocs == allocations);
	kd_spin_selftest_node_event(KD_NODE_NATIVE_RESERVE);
	kd_spin_selftest_nodes_report();
	kd_node_trace = true;
	node_alloc_fail = true;
	CHECK(kd_spin_selftest_nodes_init() == -ENOMEM && !kd_node_records);
	kd_spin_selftest_nodes_report();
	kd_spin_selftest_nodes_free();
	node_alloc_fail = false;
	CHECK(kd_spin_selftest_nodes_init() == 0 && kd_node_records);
	CHECK(!memcmp(kd_node_records, &empty, sizeof(empty)));
	kd_spin_selftest_nodes_free();
	CHECK(!kd_node_records && node_frees == frees + 2 &&
	      node_allocs == allocations + 2);
	printf("spin observer allocation: %d checks\n", checks - previous);
}
