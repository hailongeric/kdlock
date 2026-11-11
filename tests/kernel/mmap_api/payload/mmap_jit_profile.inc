/* SPDX-License-Identifier: GPL-2.0-only */
/* Optional source composition; ABI1 never allocates or enables these roles. */
#include "../../payload/native_context_boundaries.inc"

static bool enable_jit_profile;
module_param(enable_jit_profile, bool, 0444);
MODULE_PARM_DESC(enable_jit_profile, "Cold experimental ABI2 source profile opt-in (default false)");

struct mmap_jit_reader;
struct mmap_jit_selection {
	struct selected_mm *selected;
	struct kd_mmap_jit_config config;
	struct kd_jit_source_load_region *regions;
	unsigned char *version;
	struct module *modules[2];
	struct kd_jit_source_provider *source;
	struct kd_jit_runtime *runtime;
	struct kd_task_storage *storage;
	unsigned long state, origin_gs;
	size_t source_bytes;
	int last_error, setup_error;
	bool trace_live, binding_live, owner_left, source_closing;
	raw_spinlock_t event_guard;
	struct kd_observation *events;
	unsigned long event_count, event_overflow;
	struct list_head readers;
	bool event_admission;
};
struct mmap_jit_reader {
	struct list_head link;
	struct mmap_jit_selection *jit;
	u64 header[5];
};
/* The anchor guard only transfers event-open ownership. It is never acquired
 * by the trace listener; anchor -> per-selection event guard is the sole order.
 */
static DEFINE_RAW_SPINLOCK(jit_anchor_guard);
static struct mmap_jit_selection *jit_event_anchor;
static struct kd_mmap_jit_status saved_jit_status;
static bool jit_event_device_live;

static void notrace jit_observe(struct mmap_jit_selection *jit,
		const struct kd_observation *event)
{
	unsigned long flags;

	raw_spin_lock_irqsave(&jit->event_guard, flags);
	if (jit->event_count < jit->config.event_capacity) {
		jit->events[jit->event_count] = *event;
		/* A reader snapshots count only after the entire immutable row is copied. */
		++jit->event_count;
	} else {
		jit->event_overflow = 1;
	}
	raw_spin_unlock_irqrestore(&jit->event_guard, flags);
}

static int jit_events_open(struct inode *inode, struct file *file)
{
	struct mmap_jit_reader *reader;
	struct mmap_jit_selection *jit;
	unsigned long flags;
	int result = 0;

	(void)inode;
	if (!capable(CAP_SYS_ADMIN))
		return -EPERM;
	reader = kzalloc(sizeof(*reader), GFP_KERNEL);
	if (!reader)
		return -ENOMEM;
	raw_spin_lock_irqsave(&jit_anchor_guard, flags);
	jit = jit_event_anchor;
	if (!jit) {
		result = -ENODEV;
	} else {
		raw_spin_lock(&jit->event_guard);
		if (!jit->event_admission) {
			result = -ESHUTDOWN;
		} else {
			reader->jit = jit;
			reader->header[0] = 1; reader->header[1] = 20;
			reader->header[2] = jit->config.event_capacity;
			reader->header[3] = jit->event_count;
			reader->header[4] = jit->event_overflow;
			list_add_tail(&reader->link, &jit->readers);
		}
		raw_spin_unlock(&jit->event_guard);
	}
	raw_spin_unlock_irqrestore(&jit_anchor_guard, flags);
	if (result)
		kfree(reader);
	else
		file->private_data = reader;
	return result;
}

/* Each fd owns one frozen prefix. Reopen for a later prefix/final overflow
 * report. No pointer is read after the VFS final release removes its exact
 * membership; END refuses any such membership, rather than guessing from a count.
 */
static ssize_t jit_events_read(struct file *file, char __user *output,
		size_t size, loff_t *position)
{
	struct mmap_jit_reader *reader = file->private_data;
	struct kd_observation row;
	loff_t relative;
	size_t index, offset, length;

	if (*position < 0)
		return -EINVAL;
	if (*position < sizeof(reader->header))
		return simple_read_from_buffer(output, size, position, reader->header,
				sizeof(reader->header));
	relative = *position - sizeof(reader->header);
	index = relative / sizeof(row);
	offset = relative % sizeof(row);
	if (index >= reader->header[3])
		return 0;
	/* The exact fd membership retains backing; this published row never changes. */
	row = reader->jit->events[index];
	length = min(size, sizeof(row) - offset);
	if (copy_to_user(output, (const char *)&row + offset, length))
		return -EFAULT;
 *position += length;
	return length;
}

static int jit_events_release(struct inode *inode, struct file *file)
{
	struct mmap_jit_reader *reader = file->private_data;
	struct mmap_jit_selection *jit = reader->jit;
	unsigned long flags;

	(void)inode;
	raw_spin_lock_irqsave(&jit->event_guard, flags);
	list_del(&reader->link);
	raw_spin_unlock_irqrestore(&jit->event_guard, flags);
	/* No jit or event backing access follows the exact final reader unlink. */
	kfree(reader);
	return 0;
}

static const struct file_operations jit_event_operations = {
	.owner = THIS_MODULE, .open = jit_events_open, .read = jit_events_read,
	.release = jit_events_release, .llseek = default_llseek,
};
static struct miscdevice jit_event_device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_mmap_api_events", .mode = 0400,
	.fops = &jit_event_operations,
};

static bool jit_execution_ready(void *context, struct task_struct *origin)
{
	struct mmap_jit_selection *jit = context;
	struct mm_struct *mm = jit->selected->mm;

	/* Necessary same-address-space check, not a full current/per-CPU/RCU/fixup
	 * context proof. Both tasks and the mm have independent retained lifetimes.
	 */
	return current->mm && current->mm == mm && READ_ONCE(origin->mm) == mm;
}

static void jit_snapshot(struct selected_mm *selected,
		struct kd_mmap_jit_status *status)
{
	struct mmap_jit_selection *jit = selected->jit;
	struct mmap_jit_reader *reader;
	unsigned long flags;
	u64 readers = 0;

	snapshot(selected, &status->native);
	status->state = jit->state;
	status->roles = KD_MMAP_JIT_ROLE_NATIVE |
		(jit->trace_live ? KD_MMAP_JIT_ROLE_OBSERVER : 0) |
		(jit->source ? KD_MMAP_JIT_ROLE_SOURCE : 0) |
		(jit->runtime ? KD_MMAP_JIT_ROLE_RUNTIME : 0) |
		(jit->storage ? KD_MMAP_JIT_ROLE_OWNER : 0) |
		(jit->binding_live ? KD_MMAP_JIT_ROLE_BINDING : 0);
	status->last_error = (u64)(s64)jit->last_error;
	status->setup_error = (u64)(s64)jit->setup_error;
	status->killable_source_calls = selected->binding.killable_source_calls;
	status->source_closing = jit->source_closing;
	status->owner_left = jit->owner_left;
	status->source_identity = (unsigned long)jit->source;
	status->runtime_identity = (unsigned long)jit->runtime;
	status->storage_identity = (unsigned long)jit->storage;
	status->origin_gs = jit->origin_gs;
	status->event_capacity = jit->config.event_capacity;
	raw_spin_lock_irqsave(&jit->event_guard, flags);
	status->event_count = jit->event_count;
	status->event_overflow = jit->event_overflow;
	list_for_each_entry(reader, &jit->readers, link)
		++readers;
	raw_spin_unlock_irqrestore(&jit->event_guard, flags);
	status->event_readers = readers; /* Diagnostic; actual memberships gate END. */
	status->source_regions = jit->config.source_region_count;
	status->source_bytes = jit->source_bytes;
	/* Raw JIT rows are exported without a guessed gate count. The host must join
	 * exact GRANT/READ_ACQUIRE, SLOT incarnation, FORWARD/JIT and source CALL bytes.
	 */
	/* The ABI1 prefix keeps its unavailable count; raw event_* is separate. */
}

static int jit_copy_inputs(struct mmap_jit_selection *jit,
		const struct kd_mmap_jit_config *config)
{
	struct kd_mmap_jit_region *input;
	size_t wire_bytes, region_bytes, metadata, total = 0, frame;
	unsigned int index;

	if (!config->native_capacity || config->native_capacity > UINT_MAX ||
		!config->event_capacity || !config->metadata_capacity ||
		!config->source_byte_capacity || !config->source_regions ||
		!config->source_region_count || config->source_region_count > UINT_MAX ||
		!config->source_version || !config->source_version_bytes ||
		!config->feedback_capacity || config->feedback_capacity > UINT_MAX ||
		!config->cycle_capacity || config->cycle_capacity > UINT_MAX ||
		!config->image_capacity || config->image_capacity > UINT_MAX ||
		!config->claim_capacity || config->claim_capacity > UINT_MAX ||
		!config->code_capacity || !config->artifact_capacity || !config->flat_capacity ||
		!config->entry_capacity || config->entry_capacity > UINT_MAX ||
		config->source_capacity > UINT_MAX || config->observation_capacity > UINT_MAX ||
		!config->frame_capacity || !config->request_capacity || config->request_capacity > UINT_MAX ||
		!config->auxiliary_bytes || !config->required_control_bytes ||
		!config->proxy_limit || config->proxy_limit > UINT_MAX ||
		config->event_capacity > ((unsigned long)LLONG_MAX - 5 * sizeof(u64)) /
		sizeof(*jit->events))
		return -EINVAL;
	if (check_mul_overflow((size_t)config->source_region_count, sizeof(*input), &wire_bytes) ||
		check_mul_overflow((size_t)config->source_region_count, sizeof(*jit->regions), &region_bytes) ||
		check_add_overflow(wire_bytes, region_bytes, &metadata) ||
		check_add_overflow(metadata, (size_t)config->source_version_bytes, &metadata))
		return -EOVERFLOW;
	if (metadata > config->metadata_capacity)
		return -E2BIG;
	input = memdup_user(u64_to_user_ptr(config->source_regions), wire_bytes);
	if (IS_ERR(input))
		return PTR_ERR(input);
	jit->regions = kvmalloc_array(config->source_region_count, sizeof(*jit->regions), GFP_KERNEL);
	if (!jit->regions) {
		kfree(input);
		return -ENOMEM;
	}
	for (index = 0; index < config->source_region_count; ++index) {
		unsigned long start = input[index].start;
		size_t length = input[index].length;

		if (!length || length - 1 > ULONG_MAX - start ||
		check_add_overflow(total, length, &total)) {
			kfree(input);
			return -EINVAL;
		}
		jit->regions[index].start = start;
		jit->regions[index].length = length;
	}
	kfree(input);
	if (total > config->source_byte_capacity)
		return -E2BIG;
	/* SOURCE exports all regions in one response; the runtime adds its actual
	 * API boundary table and returns EMSGSIZE if the explicit frame is too small.
	 * STAGE must at least fit its five blobs plus the current 80-byte framing.
	 */
	if (check_add_overflow((size_t)config->artifact_capacity, (size_t)config->code_capacity, &frame) ||
		check_add_overflow(frame, (size_t)config->flat_capacity, &frame) ||
		check_add_overflow(frame, (size_t)80, &frame))
		return -EOVERFLOW;
	if (frame > config->frame_capacity || total > config->frame_capacity)
		return -EMSGSIZE;
	jit->version = memdup_user(u64_to_user_ptr(config->source_version), config->source_version_bytes);
	if (IS_ERR(jit->version)) {
		int result = PTR_ERR(jit->version);

		jit->version = NULL;
		return result;
	}
	jit->config = *config;
	/* Input user addresses are no longer retained, consulted or used as leases. */
	jit->config.source_regions = 0;
	jit->config.source_version = 0;
	jit->source_bytes = total;
	return 0;
}

static int jit_start(const struct kd_mmap_jit_request *request)
{
	struct kd_jit_source_provider_args source;
	struct kd_jit_runtime_config config;
	struct mmap_jit_selection *jit;
	struct selected_mm *selected;
	size_t bytes;
	unsigned long flags;
	unsigned int index;
	int result;

	if (!enable_jit_profile)
		return -EOPNOTSUPP;
	if (selection || saved_status.state != KD_MMAP_API_IDLE ||
		saved_jit_status.state != KD_MMAP_JIT_IDLE)
		return -EALREADY;
	if (request->contract_flags != KD_MMAP_JIT_CONTRACTS)
		return -EINVAL;
	if (!current->mm || current != current->group_leader || get_nr_threads(current) != 1 ||
		smp_load_acquire(&current->kd_root_context))
		return -EPERM;
	BUILD_BUG_ON(sizeof(struct kd_observation) != 20 * sizeof(u64));
	selected = kzalloc(sizeof(*selected), GFP_KERNEL);
	jit = kzalloc(sizeof(*jit), GFP_KERNEL);
	if (!selected || !jit) {
		kfree(selected); kfree(jit);
		return -ENOMEM;
	}
	selected->jit = jit;
	jit->selected = selected;
	result = jit_copy_inputs(jit, &request->config);
	if (result)
		goto free_private;
	if (check_mul_overflow((size_t)request->config.native_capacity,
		sizeof(*selected->records), &bytes)) {
		result = -EOVERFLOW;
		goto free_private;
	}
	selected->record_bytes = bytes;
	selected->records = kvcalloc(request->config.native_capacity, sizeof(*selected->records), GFP_KERNEL);
	jit->events = kvcalloc(jit->config.event_capacity, sizeof(*jit->events), GFP_KERNEL);
	if (!selected->records || !jit->events) {
		result = -ENOMEM;
		goto free_private;
	}
	kd_rwsem_init(&selected->gate);
	/* Private query target; source flags are published only by the final bind. */
	selected->binding.lock = &selected->gate;
	result = kd_rw_native_pool_init(&selected->gate.core, &selected->pool,
			selected->records, request->config.native_capacity);
	if (result)
		goto free_private;
	for (index = 0; index < COUNT_TOTAL; ++index)
		atomic64_set(&selected->counts[index], 0);
	atomic_set(&selected->count_overflow, 0);
	raw_spin_lock_init(&jit->event_guard);
	INIT_LIST_HEAD(&jit->readers);
	selected->mm = current->mm;
	selected->owner = current;
	selected->owner_pid = task_pid_nr(current);
	selected->owner_tgid = task_tgid_nr(current);
	mmgrab(selected->mm);
	get_task_struct(selected->owner);
	if (!try_module_get(THIS_MODULE)) {
		result = -ENODEV;
		put_task_struct(selected->owner); mmdrop(selected->mm);
		goto free_private;
	}
	/* From here every setup error is a retained QUERY-accessible selection. */
	selection = selected;
	jit->state = KD_MMAP_JIT_SETTING_UP;
	jit->event_admission = true;
	raw_spin_lock_irqsave(&jit_anchor_guard, flags);
	jit_event_anchor = jit;
	raw_spin_unlock_irqrestore(&jit_anchor_guard, flags);
	result = register_trace_kdlock_observe_tp(observe, selected);
	if (result)
		goto retained;
	jit->trace_live = true;
	jit->modules[0] = THIS_MODULE;
	jit->modules[1] = NULL; /* All other declared source text is built-in. */
	source = (struct kd_jit_source_provider_args) {
		.contract = KD_JIT_SOURCE_IMMUTABLE_DEPENDENCIES,
		.version = jit->version, .version_length = jit->config.source_version_bytes,
		.regions = jit->regions, .region_count = jit->config.source_region_count,
		.configuration_identity = jit->config.configuration_identity,
		.load_identity = jit->config.load_identity,
		.current_task_gs_offset = jit->config.current_task_gs_offset,
		.modules = jit->modules, .module_count = ARRAY_SIZE(jit->modules),
	};
	result = kd_jit_source_provider_create(&source, &jit->source);
	if (result)
		goto retained;
#define MM_JIT_SYMBOL(text) { .data = (const unsigned char *)(text), .length = sizeof(text) - 1 }
	config = (struct kd_jit_runtime_config) {
		.source = jit->source,
		.boundaries = kd_test_native_context_boundaries,
		.boundary_count = ARRAY_SIZE(kd_test_native_context_boundaries),
		.feedback_capacity = jit->config.feedback_capacity,
		.cycle_capacity = jit->config.cycle_capacity,
		.image_capacity = jit->config.image_capacity,
		.claim_capacity = jit->config.claim_capacity,
		.compiled = { .code_capacity = jit->config.code_capacity,
			.artifact_capacity = jit->config.artifact_capacity, .flat_capacity = jit->config.flat_capacity,
			.entry_capacity = jit->config.entry_capacity, .source_capacity = jit->config.source_capacity,
			.observation_capacity = jit->config.observation_capacity },
		.symbols = { .descriptor = MM_JIT_SYMBOL("kd_mm_image"), .source = MM_JIT_SYMBOL("kd_mm_epoch"),
			.producer = MM_JIT_SYMBOL("kd_mm_producer"), .entry = MM_JIT_SYMBOL("kd_mm_entry") },
		.channel_name = "kd_mmap_jit", .owner = THIS_MODULE,
		.frame_capacity = jit->config.frame_capacity, .request_capacity = jit->config.request_capacity,
		.auxiliary_bytes = jit->config.auxiliary_bytes,
		.required_control_bytes = jit->config.required_control_bytes,
		.proxy_limit = jit->config.proxy_limit, .family = KD_LOCK_FAMILY_RWSEM,
		.execution_ready = jit_execution_ready, .execution_context = jit,
	};
#undef MM_JIT_SYMBOL
	result = kd_jit_runtime_create(&config, &jit->runtime);
	if (result)
		goto retained;
	preempt_disable();
	rdmsrl(MSR_GS_BASE, jit->origin_gs);
	preempt_enable();
	result = kd_jit_runtime_enter_current(jit->runtime, jit->origin_gs, &jit->storage);
	if (result)
		goto retained;
	/* No source-enabled object is exposed before complete cold provisioning and
	 * original-owner enrollment. Child clone hooks later create independent S_W.
	 */
	result = kd_linux_rwsem_bind_killable_source(&selected->mm->mmap_lock,
			&selected->binding, &selected->gate);
	if (result)
		goto retained;
	jit->binding_live = true;
	jit->state = KD_MMAP_JIT_SELECTED;
	return 0;
retained:
	if (jit->storage) {
		struct kd_task_root_context *root = smp_load_acquire(&current->kd_root_context);

		/* A bind failure after enrollment must not admit descendants/source.
		 * Read only the exact current retained header, never a second packet.
		 */
		if (root && root->task == current && root->storage == jit->storage) {
			root->source_closing = true;
			jit->source_closing = true;
		}
	}
	jit->setup_error = result;
	jit->last_error = result;
	jit->state = KD_MMAP_JIT_RETAINED;
	return result;
free_private:
	kvfree(jit->events); kvfree(selected->records);
	kvfree(jit->version); kvfree(jit->regions);
	kfree(jit); kfree(selected);
	return result;
}

static bool jit_owner_current(struct selected_mm *selected)
{
	return current == selected->owner && current->mm == selected->mm &&
		get_nr_threads(current) == 1;
}

static int jit_leave(struct selected_mm *selected)
{
	struct mmap_jit_selection *jit = selected->jit;
	struct kd_task_root_context *root;
	struct kd_execution_binding *native;
	bool pending;
	int result;

	if (!jit_owner_current(selected))
		return -EPERM;
	if (jit->storage) {
		root = smp_load_acquire(&current->kd_root_context);
		if (!root || !root->attached || root->task != current ||
		root->storage != jit->storage || root->aux_entry)
			return -EBUSY;
		root->source_closing = true;
		jit->source_closing = true;
		native = smp_load_acquire(&root->core.binding);
		result = kd_jit_runtime_leave_current(jit->storage, native, &pending);
		if (result)
			return result;
		/* Successful leave ended all old root/storage/native endpoint accesses. */
		jit->storage = NULL;
	}
	jit->source_closing = true;
	jit->owner_left = true;
	jit->state = KD_MMAP_JIT_OWNER_LEFT;
	return 0;
}

static int jit_readers_close(struct mmap_jit_selection *jit)
{
	unsigned long flags;
	int result = 0;

	raw_spin_lock_irqsave(&jit_anchor_guard, flags);
	raw_spin_lock(&jit->event_guard);
	if (!list_empty(&jit->readers))
		result = -EBUSY;
	else
		jit->event_admission = false;
	raw_spin_unlock(&jit->event_guard);
	raw_spin_unlock_irqrestore(&jit_anchor_guard, flags);
	return result;
}

static void jit_readers_reopen(struct mmap_jit_selection *jit)
{
	unsigned long flags;

	raw_spin_lock_irqsave(&jit->event_guard, flags);
	jit->event_admission = true;
	raw_spin_unlock_irqrestore(&jit->event_guard, flags);
}

static int jit_end(struct selected_mm *selected)
{
	struct mmap_jit_selection *jit = selected->jit;
	unsigned long flags;
	int result;

	if (!jit_owner_current(selected))
		return -EPERM;
	if (!jit->owner_left || jit->storage || !kd_rw_native_pool_idle(&selected->pool) ||
		kd_linux_rwsem_is_locked(&selected->binding) ||
		kd_linux_rwsem_is_contended(&selected->binding))
		return -EBUSY;
	result = jit_readers_close(jit);
	if (result)
		return result;
	/* Destroy enforces actual SHUTDOWN, drained native/image/feedback users,
	 * settled claims and closed channel. It supplies no fabricated host receipt.
	 * On partial teardown the still-live binding routes unprepared calls through
	 * the same native pool. Caller excludes all users across these final steps.
	 */
	if (jit->runtime) {
		result = kd_jit_runtime_destroy(jit->runtime);
		if (result)
			goto retained;
		jit->runtime = NULL;
	}
	if (jit->binding_live) {
		result = kd_linux_rwsem_unbind(&selected->binding);
		if (result)
			goto retained;
		jit->binding_live = false;
	}
	if (jit->source) {
		result = kd_jit_source_provider_close(jit->source);
		if (result && result != -EALREADY)
			goto retained;
		result = kd_jit_source_provider_destroy(jit->source);
		if (result)
			goto retained;
		jit->source = NULL;
	}
	/* Unregister can change traced text only after all source uses have ended. */
	if (jit->trace_live) {
		unregister_trace_kdlock_observe_tp(observe, selected);
		tracepoint_synchronize_unregister();
		jit->trace_live = false;
	}
	jit->last_error = 0;
	jit_snapshot(selected, &saved_jit_status);
	saved_jit_status.state = KD_MMAP_JIT_RETIRED;
	saved_jit_status.roles = 0;
	saved_jit_status.native.state = KD_MMAP_API_RETIRED;
	saved_jit_status.native.cleanup_required = 0;
	raw_spin_lock_irqsave(&jit_anchor_guard, flags);
	jit_event_anchor = NULL;
	raw_spin_unlock_irqrestore(&jit_anchor_guard, flags);
	selection = NULL;
	put_task_struct(selected->owner); mmdrop(selected->mm);
	kvfree(selected->records); kvfree(jit->events);
	kvfree(jit->regions); kvfree(jit->version);
	kfree(jit); kfree(selected);
	/* The control fd separately retains provider code through this return. */
	module_put(THIS_MODULE);
	return 0;
retained:
	jit_readers_reopen(jit);
	return result;
}

static long jit_ioctl(unsigned int command, unsigned long argument)
{
	static const struct kd_mmap_jit_config zero;
	struct kd_mmap_jit_request *request;
	struct kd_mmap_jit_request reply = { .abi = KD_MMAP_JIT_ABI };
	int result;

	if (!capable(CAP_SYS_ADMIN))
		return -EPERM;
	/* Keep the sole input capture off the task stack. Cold construction reads
	 * it synchronously; retained source/runtime state never stores this pointer.
	 */
	request = memdup_user((void __user *)argument, sizeof(*request));
	if (IS_ERR(request))
		return PTR_ERR(request);
	if (request->abi != KD_MMAP_JIT_ABI) {
		result = -EINVAL;
		goto out;
	}
	if (command != KD_MMAP_API_START_JIT &&
		(memcmp(&request->config, &zero, sizeof(zero)) ||
		request->contract_flags != (command == KD_MMAP_API_QUERY_JIT ? 0 : KD_MMAP_API_QUIESCENT_CHANGE))) {
		result = -EINVAL;
		goto out;
	}
	mutex_lock(&control_mutex);
	if (selection && !selection->jit) {
		result = -EBUSY;
	} else if (command == KD_MMAP_API_START_JIT) {
		result = jit_start(request);
	} else if (command == KD_MMAP_API_QUERY_JIT) {
		result = 0;
	} else if (!selection) {
		result = -ENODEV;
	} else if (command == KD_MMAP_API_LEAVE_JIT) {
		result = jit_leave(selection);
	} else {
		result = jit_end(selection);
	}
	if (selection && selection->jit) {
		if (command != KD_MMAP_API_QUERY_JIT) {
			selection->jit->last_error = result;
			if (result)
				selection->jit->state = KD_MMAP_JIT_RETAINED;
		}
		jit_snapshot(selection, &saved_jit_status);
	}
	reply.status = saved_jit_status;
	mutex_unlock(&control_mutex);
	if (copy_to_user((void __user *)argument, &reply, sizeof(reply)))
		result = -EFAULT;
out:
	kfree(request);
	return result;
}
