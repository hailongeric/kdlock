/* SPDX-License-Identifier: GPL-2.0-only */
/* Test-only scalar history. No listener changes source or queue authority. */
static unsigned long event_capacity;
module_param(event_capacity, ulong, 0444);
MODULE_PARM_DESC(event_capacity, "Explicit preallocated scalar-observation record count");
static struct kd_observation *event_rows;
static unsigned long event_count, event_overflow;
static DEFINE_RAW_SPINLOCK(event_guard);
static DECLARE_WAIT_QUEUE_HEAD(event_wait);
static bool event_registered;

enum fixture_scene_role { SCENE_HA, SCENE_HB, SCENE_CA, SCENE_CB, SCENE_W, SCENE_ROLES };
static bool scene_active;
static struct completion scene_go[SCENE_ROLES], scene_release[SCENE_ROLES];
static unsigned long scene_queued, scene_held, scene_nodes[SCENE_ROLES], scene_child;

static void notrace fixture_observe(void *unused, const struct kd_observation *event)
{
	unsigned long flags;
	unsigned int role;

	(void)unused;
	raw_spin_lock_irqsave(&event_guard, flags);
	if (event_count < event_capacity)
		event_rows[event_count++] = *event;
	else
		event_overflow++;
	if (READ_ONCE(scene_active) && event->kind == KD_OBS_ENQUEUE) {
		for (role = 0; role < SCENE_ROLES; ++role) {
			struct kd_mutex *lock = role == SCENE_HB || role == SCENE_CB ? &lock_b[0] : &lock_a[0];

			if (event->task == (unsigned long)READ_ONCE(workers[role].task) &&
			    event->origin == event->task && event->object == (unsigned long)lock) {
				scene_nodes[role] = event->node;
				scene_queued |= 1UL << role;
			}
		}
		if (event->task == (unsigned long)READ_ONCE(workers[SCENE_CA].task) &&
		    event->origin == (unsigned long)READ_ONCE(workers[SCENE_W].task) &&
		    event->object == (unsigned long)&lock_b[0] && scene_nodes[SCENE_CB] &&
		    event->related == scene_nodes[SCENE_CB])
			scene_child = event->node;
	}
	raw_spin_unlock_irqrestore(&event_guard, flags);
	wake_up_all(&event_wait);
}

static int notrace fixture_events_start(void)
{
	int result;

	if (!event_capacity || event_capacity > (SIZE_MAX - 5 * sizeof(u64)) / sizeof(*event_rows) ||
	    event_capacity > ((unsigned long)LLONG_MAX - 5 * sizeof(u64)) / sizeof(*event_rows))
		return -EINVAL;
	BUILD_BUG_ON(sizeof(struct kd_observation) != 20 * sizeof(unsigned long));
	event_rows = kvcalloc(event_capacity, sizeof(*event_rows), GFP_KERNEL);
	if (!event_rows)
		return -ENOMEM;
	result = register_trace_kdlock_observe_tp(fixture_observe, NULL);
	if (result) {
		kvfree(event_rows);
		event_rows = NULL;
		return result;
	}
	event_registered = true;
	return 0;
}

static void notrace fixture_events_stop(void)
{
	if (event_registered) {
		unregister_trace_kdlock_observe_tp(fixture_observe, NULL);
		tracepoint_synchronize_unregister();
		event_registered = false;
	}
}

/* Header: ABI1,20words,capacity,count,overflow; then immutable native x86_64
 * little-endian rows. A reader takes one header and exactly that prefix's rows;
 * later appends do not change any earlier row. No uaccess under event_guard.
 */
static ssize_t notrace events_read(struct file *file, char __user *output,
		size_t size, loff_t *position)
{
	u64 header[5];
	struct kd_observation row;
	unsigned long flags, index;
	loff_t relative;
	size_t offset, length;

	(void)file;
	if (*position < 0)
		return -EINVAL;
	raw_spin_lock_irqsave(&event_guard, flags);
	header[0] = 1; header[1] = 20; header[2] = event_capacity;
	header[3] = event_count; header[4] = event_overflow;
	if (*position < sizeof(header)) {
		raw_spin_unlock_irqrestore(&event_guard, flags);
		return simple_read_from_buffer(output, size, position, header, sizeof(header));
	}
	relative = *position - sizeof(header);
	index = relative / sizeof(row);
	offset = relative % sizeof(row);
	if (index >= event_count) {
		raw_spin_unlock_irqrestore(&event_guard, flags);
		return 0;
	}
	row = event_rows[index];
	raw_spin_unlock_irqrestore(&event_guard, flags);
	length = min(size, sizeof(row) - offset);
	if (copy_to_user(output, (char *)&row + offset, length))
		return -EFAULT;
	*position += length;
	return length;
}

static __poll_t notrace events_poll(struct file *file, poll_table *wait)
{
	unsigned long flags, count;

	poll_wait(file, &event_wait, wait);
	raw_spin_lock_irqsave(&event_guard, flags);
	count = event_count;
	raw_spin_unlock_irqrestore(&event_guard, flags);
	return file->f_pos < 5 * sizeof(u64) + count * sizeof(struct kd_observation) ?
		EPOLLIN | EPOLLRDNORM : 0;
}

static const struct file_operations event_operations = {
	.owner = THIS_MODULE, .read = events_read, .poll = events_poll, .llseek = default_llseek,
};
static struct miscdevice event_device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_runtime_fixture_events",
	.fops = &event_operations, .mode = 0400,
};

/* Holders and candidate C_B execute ordinary native C outside the exported W
 * source regions. Their gates never enter the delegated source or core queue.
 */
static void notrace scene_single(struct fixture_worker *worker)
{
	struct kd_mutex *lock = worker->role == SCENE_HA ? &lock_a[0] : &lock_b[0];
	unsigned long flags;

	kd_mutex_lock(lock);
	if (worker->role == SCENE_HA || worker->role == SCENE_HB) {
		raw_spin_lock_irqsave(&event_guard, flags);
		scene_held |= 1UL << worker->role;
		raw_spin_unlock_irqrestore(&event_guard, flags);
		wake_up_all(&event_wait);
		wait_for_completion(&scene_release[worker->role]);
	}
	kd_mutex_unlock(lock);
}

static bool notrace scene_finished(void)
{
	unsigned int index;

	for (index = 0; index < worker_count; ++index)
		if (!smp_load_acquire(&workers[index].finished))
			return false;
	return true;
}

static int notrace start_scene(unsigned int mode)
{
	unsigned int index;
	int result;

	if (!runtime || worker_count || (mode != 1 && mode != 2) || !fixture_locks_clear())
		return -EBUSY;
	for (index = 0; index < FIXTURE_MAX_ITERATIONS; ++index) {
		protected_a[index] = 0; protected_b[index] = 0; pointer_value[index] = 0;
	}
	for (index = 0; index < SCENE_ROLES; ++index) {
		init_completion(&scene_go[index]);
		init_completion(&scene_release[index]);
		scene_nodes[index] = 0;
	}
	scene_queued = 0; scene_held = 0; scene_child = 0;
	requested_mode = mode; requested_iterations = 1;
	reinit_completion(&start_gate);
	atomic_set(&ready_count, 0);
	WRITE_ONCE(ready_goal, SCENE_ROLES);
	WRITE_ONCE(abort_start, false);
	WRITE_ONCE(scene_active, true);
	for (index = 0; index < SCENE_ROLES; ++index) {
		struct fixture_worker *worker = &workers[index];

		*worker = (struct fixture_worker) { .scene = true, .role = index,
			.mode = index == SCENE_W ? mode : 0, .iterations = 1 };
		worker->task = kthread_create(worker_main, worker, "kd-scene/%u", index);
		if (IS_ERR(worker->task)) {
			result = PTR_ERR(worker->task); worker->task = NULL;
			WRITE_ONCE(abort_start, true);
			for (index = 0; index < SCENE_ROLES; ++index)
				complete_all(&scene_go[index]);
			stop_workers();
			WRITE_ONCE(scene_active, false);
			return result;
		}
		get_task_struct(worker->task);
		worker_count++;
		wake_up_process(worker->task);
	}
	return 0;
}
