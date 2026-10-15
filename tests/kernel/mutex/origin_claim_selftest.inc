/* Constructed protocol probe, deliberately separate from returned-JIT evidence. */
static bool owned_mutex_origin_selftest;
module_param(owned_mutex_origin_selftest, bool, 0444);

struct kd_origin_probe {
	struct completion ready, done;
	struct kd_owned_mutex_node *node;
	bool go;
};

static int kd_origin_probe_worker(void *data)
{
	struct kd_origin_probe *test = data;
	struct kd_mutex lock;
	unsigned int i;

	kd_mutex_init(&lock);
	for (i = 0; i < 256; i++) {
		struct kd_owned_mutex_node *node;

		migrate_disable();
		preempt_disable();
		node = kd_owned_mutex_reserve(&lock);
		BUG_ON(!node);
		node->lock = &lock;
		node->saved_ret_addr = 0;
		node->outcome = KD_OWNED_MUTEX_QUEUED;
		node->waiter.task = current;
		test->node = node;
		WRITE_ONCE(test->go, false);
		smp_store_release(&node->readiness, KD_ORIGIN_READY);
		complete(&test->ready);
		while (!smp_load_acquire(&test->go))
			cpu_relax();
		kd_owned_mutex_wait_result(node);
		BUG_ON(node->readiness != KD_ORIGIN_FINISHED);
		kd_owned_mutex_unreserve(node);
		preempt_enable();
		migrate_enable();
		complete(&test->done);
	}
	return 0;
}

static int kd_origin_probe_run(void)
{
	struct kd_origin_probe test;
	struct task_struct *worker;
	struct kd_jit_image image = { .requirements = KD_IMAGE_ORIGIN_SPIN };
	unsigned int i;
	int cpu, origin;

	if (!owned_mutex_origin_selftest)
		return 0;
	if (!owned_mutex_origin_spin || num_online_cpus() < 2)
		return -EINVAL;
	init_completion(&test.ready);
	init_completion(&test.done);
	migrate_disable();
	cpu = raw_smp_processor_id();
	origin = cpumask_any_but(cpu_online_mask, cpu);
	worker = kthread_create(kd_origin_probe_worker, &test, "kd_origin_probe");
	if (IS_ERR(worker)) {
		migrate_enable();
		return PTR_ERR(worker);
	}
	/* The worker may finish before kthread_stop; retain its task explicitly. */
	get_task_struct(worker);
	kthread_bind(worker, origin);
	wake_up_process(worker);
	for (i = 0; i < 256; i++) {
		unsigned long voluntary, involuntary;
		struct kd_owned_mutex_node *node;

		wait_for_completion(&test.ready);
		node = test.node;
		preempt_disable();
		BUG_ON(!kd_owned_mutex_claim(node, &image));
		voluntary = READ_ONCE(worker->nvcsw);
		involuntary = READ_ONCE(worker->nivcsw);
		set_tsk_need_resched(worker);
		smp_store_release(&test.go, true);
		udelay(50); /* Includes zero-budget waits and explicit reschedule requests. */
		BUG_ON(READ_ONCE(worker->nvcsw) != voluntary ||
		       READ_ONCE(worker->nivcsw) != involuntary ||
		       READ_ONCE(node->readiness) != KD_ORIGIN_CLAIMED);
		kd_owned_mutex_finish_claim(node, true);
		kd_owned_mutex_notify(node, true);
		preempt_enable();
		wait_for_completion(&test.done);
	}
	kthread_stop(worker);
	put_task_struct(worker);
	migrate_enable();
	BUG_ON(!kd_owned_mutex_check_idle());
	pr_info("kd_owned_mutex origin probe: claims=256 scheduled_while_claimed=0 resched=256 reused=256 drained=1 jit_bodies=0\n");
	return 0;
}
