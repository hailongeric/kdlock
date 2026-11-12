/* SPDX-License-Identifier: GPL-2.0 */
/* Measurement records hold scalar identities only, never protocol authority.
 * Core request/free probes and leave_current still enforce actual last users.
 * Per-origin guards serialize records without adding a global accounting lock.
 */
#define RB_REQUESTS 256U
#define RB_RECORDS 512U
#define RB_STATE_MAP 128U
enum rb_count {
	RB_RESERVED, RB_FREED, RB_PREPARED, RB_PROXY, RB_ENTERED, RB_COMPLETED,
	RB_FORWARDED, RB_ERRORS, RB_LIVE, RB_ATTACHED, RB_DETACHED,
	RB_STATE, RB_ORIGIN, RB_PROOF, RB_READ_ACQUIRED, RB_READ_RELEASED,
};
struct rb_request_record {
	unsigned long node, acquisition, image;
	bool live, prepared, foreign, all_jit, unlock, done;
	struct kd_observation prepare;
};
struct rb_worker_evidence {
	raw_spinlock_t guard;
	struct kd_task_storage *storage;
	unsigned long sample_node;
	unsigned int map_index;
	bool mapped;
	struct rb_evidence_row row;
	struct rb_request_record records[RB_RECORDS];
};
static struct rb_worker_evidence *rb_evidence;
static bool rb_evidence_recorded;
static struct { unsigned long state; unsigned int worker; } rb_state_map[RB_STATE_MAP];
static unsigned long rb_unlock_ip, rb_unlock_cursor;

static struct rb_request_record *rb_record(struct rb_worker_evidence *w, unsigned long node)
{
	unsigned int i, start = hash_long(node, 9);
	for (i = 0; i < RB_RECORDS; ++i) {
		struct rb_request_record *r = &w->records[(start + i) & (RB_RECORDS - 1)];
		if (r->node == node || !r->node)
			return r;
	}
	return NULL;
}

static void notrace rb_observe(void *unused, const struct kd_observation *e)
{
	struct rb_worker_evidence *w = NULL;
	struct rb_request_record *r;
	unsigned int i, start;
	unsigned long flags, required;
	bool sampled;

	if (!e->state)
		return;
	start = hash_long(e->state, 7);
	for (i = 0; i < RB_STATE_MAP; ++i) {
		unsigned int at = (start + i) & (RB_STATE_MAP - 1);
		unsigned long key = smp_load_acquire(&rb_state_map[at].state);
		if (key == e->state) {
			w = &rb_evidence[rb_state_map[at].worker];
			break;
		}
		if (!key)
			return;
	}
	if (!w)
		return;
	raw_spin_lock_irqsave(&w->guard, flags);
	if (e->kind == KD_OBS_READ_ACQUIRE)
		++w->row.count[RB_READ_ACQUIRED];
	if (e->kind == KD_OBS_READ_RELEASE)
		++w->row.count[RB_READ_RELEASED];
	if (!e->node)
		goto out;
	r = rb_record(w, e->node);
	if (!r) {
		++w->row.count[RB_ERRORS];
		goto out;
	}
	if (e->kind == KD_OBS_SLOT_RESERVE) {
		if (r->live)
			++w->row.count[RB_ERRORS];
		r->node = e->node;
		r->acquisition = e->acquisition;
		r->live = true;
		r->prepared = r->foreign = r->unlock = r->done = false;
		r->all_jit = true;
		r->image = 0;
		++w->row.count[RB_RESERVED];
		++w->row.count[RB_LIVE];
		goto out;
	}
	/* Events for an unreserved node cannot establish a sampled lifetime. */
	if (!r->live || (e->acquisition && r->acquisition != e->acquisition)) {
		++w->row.count[RB_ERRORS];
		goto out;
	}
	sampled = w->sample_node == e->node;
	switch (e->kind) {
	case KD_OBS_FRAME_PREPARE:
		r->prepared = true;
		if (!w->row.count[RB_PROOF])
			r->prepare = *e;
		++w->row.count[RB_PREPARED];
		break;
	case KD_OBS_SELECT_PROXY:
		++w->row.count[RB_PROXY];
		break;
	case KD_OBS_JIT_ENTER:
		++w->row.count[RB_ENTERED];
		if (!r->image)
			r->image = e->image;
		if (r->image != e->image)
			r->all_jit = false;
		r->foreign |= e->task != e->origin;
		if (!w->sample_node && !w->row.count[RB_PROOF]) {
			w->sample_node = e->node;
			memcpy(w->row.proof[0], &r->prepare, sizeof(r->prepare));
			memcpy(w->row.proof[1], e, sizeof(*e));
		}
		break;
	case KD_OBS_JIT_EXIT:
		if (e->result != KD_JIT_EXIT_LOCK_OPERATION || e->image != r->image)
			r->all_jit = false;
		if (sampled)
			memcpy(w->row.proof[2], e, sizeof(*e));
		break;
	case KD_OBS_JIT_OPERATION:
		if (e->result == RB_UNLOCK_KIND && e->related == e->node &&
		    e->image == r->image && rb_unlock_ip && e->ip == rb_unlock_ip &&
		    e->cursor == rb_unlock_cursor) {
			r->unlock = true;
			if (sampled)
				memcpy(w->row.proof[3], e, sizeof(*e));
		}
		break;
	case KD_OBS_FORWARD:
		r->all_jit = false;
		++w->row.count[RB_FORWARDED];
		break;
	case KD_OBS_EPISODE_DONE:
		required = KD_OBS_FLAG_SOURCE_CLOSED | KD_OBS_FLAG_CURRENT_JIT;
		if (r->prepared && r->foreign && r->all_jit && r->unlock && !r->done &&
		    e->result == KD_MUTEX_PROXY_EPISODE_DONE && (e->flags & required) == required) {
			r->done = true;
			++w->row.count[RB_COMPLETED];
			if (sampled)
				memcpy(w->row.proof[4], e, sizeof(*e));
		}
		break;
	case KD_OBS_SLOT_FREE:
		required = KD_OBS_FLAG_POOL_USERS_EMPTY | KD_OBS_FLAG_COMPONENTS_IDLE;
		if (e->flags & KD_OBS_FLAG_ENQUEUED)
			required |= KD_OBS_FLAG_NODE_RETIRABLE | KD_OBS_FLAG_QUEUE_DONE;
		if ((e->flags & required) != required || e->source_user || e->return_user ||
		    e->notifier || e->flags & KD_OBS_FLAG_RESULT_USER_PRESENT)
			++w->row.count[RB_ERRORS];
		if (sampled) {
			memcpy(w->row.proof[5], e, sizeof(*e));
			w->row.count[RB_PROOF] = r->done;
			w->sample_node = 0;
		}
		r->live = false;
		++w->row.count[RB_FREED];
		--w->row.count[RB_LIVE];
		break;
	}
out:
	raw_spin_unlock_irqrestore(&w->guard, flags);
}

static void rb_evidence_reset(void)
{
	unsigned int i;
	/* Called with the admission gate reserved, after every exact task leave. */
	rb_evidence_recorded = rb_listening;
	memset(rb_state_map, 0, sizeof(rb_state_map));
	for (i = 0; i < RB_MAX_WORKERS; ++i) {
		BUG_ON(rb_evidence[i].storage);
		memset(&rb_evidence[i], 0, sizeof(rb_evidence[i]));
		raw_spin_lock_init(&rb_evidence[i].guard);
	}
}

static int rb_kd_enter(unsigned int worker)
{
	struct rb_worker_evidence *w = &rb_evidence[worker];
	struct kd_task_root_context *root;
	unsigned long gs, state;
	unsigned int i, start;
	int error;
	preempt_disable();
	rdmsrl(MSR_GS_BASE, gs);
	preempt_enable();
	error = kd_jit_runtime_enter_current(rb_runtime, gs, &w->storage);
	if (error)
		return error;
	root = kd_task_storage_root(w->storage);
	state = (unsigned long)&root->core;
	w->row.count[RB_STATE] = state;
	w->row.count[RB_ORIGIN] = (unsigned long)current;
	w->row.count[RB_ATTACHED] = 1;
	start = hash_long(state, 7);
	for (i = 0; i < RB_STATE_MAP; ++i) {
		unsigned int at = (start + i) & (RB_STATE_MAP - 1);
		unsigned long old = READ_ONCE(rb_state_map[at].state);
		if (old <= 1 && cmpxchg(&rb_state_map[at].state, old, 2) == old) {
			w->map_index = at;
			w->mapped = true;
			rb_state_map[at].worker = worker;
			smp_store_release(&rb_state_map[at].state, state);
			return 0;
		}
	}
	return -ENOSPC;
}

static int rb_kd_leave(unsigned int worker)
{
	struct rb_worker_evidence *w = &rb_evidence[worker];
	int error = 0, result;
	bool pending;
	while (w->storage) {
		struct kd_task_root_context *root = kd_task_storage_root(w->storage);
		struct kd_execution_binding *binding = smp_load_acquire(&root->core.binding);
		result = kd_jit_runtime_leave_current(w->storage, binding, &pending);
		if (!result) {
			w->storage = NULL;
			if (w->mapped) {
				/* Last callbacks ended before detach returned. Keep a tombstone
				 * so other keys in this measurement table remain reachable. */
				smp_store_release(&rb_state_map[w->map_index].state, 1);
				w->mapped = false;
			}
			w->row.count[RB_DETACHED] = 1;
			break;
		}
		if (result != -EBUSY && result != -EAGAIN)
			error = result;
		/* Keep this ioctl and source stack live until exact users have ended. */
		cond_resched();
	}
	if (w->row.count[RB_ERRORS] || w->row.count[RB_LIVE] ||
	    w->row.count[RB_RESERVED] != w->row.count[RB_FREED])
		error = -EUCLEAN;
	return error;
}
