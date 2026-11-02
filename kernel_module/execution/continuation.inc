/* SPDX-License-Identifier: GPL-2.0 */
/* Retained logical requests and temporary physical bindings. Private to
 * kd_exec.c. Queue adapters retain grant/cancel authority and must finish the
 * old object-guard handover before an executor can release the object. */

static bool kd_exec_cont_valid(const struct kd_exec_continuation *cont)
{
	return cont && cont->request && cont->generation && cont->root &&
		cont->request->generation == cont->generation &&
		cont->root->generation == cont->root_generation &&
		cont->root->state != KD_CONT_UNUSED &&
		cont->root->state != KD_CONT_RETIRED &&
		(!cont->parent || cont->parent->generation == cont->parent_generation);
}

static bool kd_exec_cont_frame_valid(const struct kd_exec_frame *frame)
{
	const struct kd_exec_continuation *cont = frame->continuation;

	if (!kd_exec_cont_valid(cont) || &cont->frame != frame ||
	    frame->logical_task != cont->request->logical_origin ||
	    frame->regs_ref != cont->packet || frame->regs_borrowed ||
	    cont->state == KD_CONT_UNUSED || cont->state == KD_CONT_RETIRED)
		return false;
	if (kd_exec_frame_state(frame) == KD_EXEC_FRAME_SUSPENDED)
		return cont->state == KD_CONT_SUSPENDED && !cont->executor &&
		       !frame->parent && !frame->depth;
	return cont->state != KD_CONT_SUSPENDED;
}

static bool kd_exec_cont_no_stack_service(const struct kd_exec_frame *frame)
{
	return frame->complex_ready && !kd_exec_frame_remote_pending(frame) &&
		!frame->resume_target && !frame->remote_request &&
		!frame->native_request && list_empty(&frame->native_link) &&
		(frame->control_call.phase == KD_CALL_NONE ||
		 frame->control_call.phase == KD_CALL_COMPLETE ||
		 frame->control_call.phase == KD_CALL_PENDING);
}

int kd_exec_cont_init(struct kd_exec_continuation *cont,
	struct kd_wait_request *request, struct kd_regs *packet,
	unsigned long entry_ip, unsigned long lock, unsigned long gsbase,
	unsigned int entry_abi, struct kd_exec_continuation *parent)
{
	struct kd_exec_continuation *root = parent ? parent->root : cont;
	struct kd_exec_frame *frame;
	unsigned long flags, stack_base;
	bool source = false, stack = false;

	if (!cont || !request || !packet || !entry_ip || !lock || !gsbase ||
	    !request->logical_origin || !request->physical_waiter ||
	    !request->identity || !request->generation ||
	    READ_ONCE(request->state) != KD_WAIT_PRIVATE ||
	    (READ_ONCE(cont->state) != KD_CONT_UNUSED &&
	     READ_ONCE(cont->state) != KD_CONT_RETIRED))
		return -EINVAL;
	if (parent) {
		if (!kd_exec_cont_valid(parent) || parent->packet != packet ||
		    request->logical_origin != parent->request->logical_origin ||
		    gsbase != parent->frame.gsbase || parent->logical_depth == UINT_MAX)
			return -EINVAL;
		stack_base = root->stack_base;
	} else {
		if (!kd_exec_task_stack_put)
			return -EOPNOTSUPP;
		if (!kd_source_frame_get())
			return -ESHUTDOWN;
		source = true;
		get_task_struct(request->logical_origin);
		stack_base = (unsigned long)try_get_task_stack(request->logical_origin);
		if (!stack_base) {
			put_task_struct(request->logical_origin);
			kd_source_frame_put();
			return -ESRCH;
		}
		stack = true;
	}

	cont->request = request;
	cont->generation = request->generation;
	cont->packet = packet;
	cont->parent = parent;
	cont->parent_generation = parent ? parent->generation : 0;
	cont->root = root;
	cont->root_generation = parent ? root->generation : cont->generation;
	cont->logical_depth = parent ? parent->logical_depth + 1 : 0;
	INIT_LIST_HEAD(&cont->children);
	INIT_LIST_HEAD(&cont->child_link);
	INIT_LIST_HEAD(&cont->owners);
	INIT_LIST_HEAD(&cont->storage_owners);
	raw_spin_lock_init(&cont->guard);
	raw_spin_lock_init(&cont->lifecycle_guard);
	cont->packet_owner = parent ? NULL : cont;
	cont->executor = NULL;
	cont->pending_call.phase = KD_CALL_NONE;
	cont->stack_base = stack_base;
	cont->stack_put = stack ? kd_exec_task_stack_put : NULL;
	cont->state = KD_CONT_READY;
	cont->wait = KD_CONT_WAIT_NONE;
	cont->result = 0;
	cont->source_lease = source;
	cont->stack_lease = stack;

	frame = &cont->frame;
	kd_exec_frame_prepare(frame, entry_ip, lock, gsbase, request->logical_origin);
	kd_exec_frame_prepare_complex(frame);
	frame->regs_ref = packet;
	frame->entry_abi = entry_abi;
	frame->packet_state = parent || entry_abi == KD_ENTRY_ABI_LEGACY ?
		KD_PACKET_FULL : KD_PACKET_MINIMAL;
	frame->mutex_backend = true;
	/* The root anchor owns the lease even while no physical frame is bound. */
	frame->batch_lease = true;
	frame->continuation = cont;
	frame->mutex_mixed.transfer_requested = false;
	frame->mutex_mixed.transferred = false;
	frame->mutex_mixed.picked_up = false;
	if (parent) {
		raw_spin_lock_irqsave(&root->guard, flags);
		if (!kd_exec_cont_valid(parent) || parent->state == KD_CONT_RETURNED ||
		    parent->state == KD_CONT_RETIRED) {
			cont->state = KD_CONT_RETIRED;
			raw_spin_unlock_irqrestore(&root->guard, flags);
			return -ESTALE;
		}
		list_add_tail(&cont->child_link, &parent->children);
		raw_spin_unlock_irqrestore(&root->guard, flags);
	}
	return 0;
}

static struct kd_exec_frame *
kd_exec_cont_activate(struct kd_exec_continuation *cont)
{
	struct kd_exec_context *ctx = kd_exec_current_context();
	struct kd_exec_frame *frame = &cont->frame;
	struct kd_exec_continuation *root = cont->root;
	unsigned long flags;
	enum kd_wait_state acquired;

	/* The caller pins this physical CPU; request storage is not CPU-local
	 * activation storage and remains live across a later suspend. */
	if (!preempt_count() || !kd_exec_cont_valid(cont))
		return NULL;
	acquired = smp_load_acquire(&cont->request->state);
	if (acquired != KD_WAIT_ACQUIRED && acquired != KD_WAIT_EXECUTING)
		return NULL;
	if (!cont->request->may_delegate && cont->request->physical_waiter != current)
		return NULL;
	raw_spin_lock_irqsave(&root->guard, flags);
	if ((cont->state != KD_CONT_READY && cont->state != KD_CONT_SUSPENDED) ||
	    root->packet_owner != cont || cont->executor ||
	    ctx->depth >= KD_EXEC_MAX_NESTING ||
	    (!!ctx->depth != !!ctx->owner) ||
	    (ctx->depth && ctx->owner != current)) {
		raw_spin_unlock_irqrestore(&root->guard, flags);
		return NULL;
	}
	frame->parent = ctx->top;
	frame->depth = ctx->depth;
	frame->state = KD_EXEC_FRAME_RUNNING;
	frame->role = KD_ROLE_COMBINER;
	cont->executor = current;
	cont->state = KD_CONT_BOUND;
	cont->wait = KD_CONT_WAIT_NONE;
	ctx->owner = current;
	ctx->top = frame;
	ctx->depth++;
	raw_spin_unlock_irqrestore(&root->guard, flags);
	return frame;
}

struct kd_exec_frame *kd_exec_cont_bind(struct kd_exec_continuation *cont,
	struct kd_mutex *lock, struct kd_exec_outer_unlock *hook)
{
	struct kd_exec_frame *frame;

	if (!kd_exec_cont_valid(cont) || !lock || !hook ||
	    cont->state != KD_CONT_READY || cont->frame.executed ||
	    cont->frame.outer_lock_addr != (unsigned long)lock ||
	    !kd_origin_mutex_owned(lock, current))
		return NULL;
	frame = &cont->frame;
	frame->held_lock_depth = 1;
	frame->outer_lock_depth = 1;
	frame->jit_lock_depth = 1;
	frame->outer_lock_index = 0;
	frame->jit_lock_addr[0] = (unsigned long)lock;
	frame->jit_lock_kind[0] = KD_EXEC_LOCK_QUEUE_OWNER;
	frame->jit_lock_node[0] = lock;
	frame->jit_lock_released[0] = false;
	frame->outer_unlock_hook = hook;
	return kd_exec_cont_activate(cont);
}

/* Caller holds root.guard. There is no physical unlock, body replay, packet
 * copy, source release or return notification in this activation-only change. */
static int kd_exec_cont_unbind(struct kd_exec_continuation *cont, bool suspended)
{
	struct kd_exec_context *ctx = kd_exec_current_context();
	struct kd_exec_frame *frame = &cont->frame;

	if (cont->state != KD_CONT_BOUND || cont->executor != current ||
	    !ctx->depth || ctx->owner != current || ctx->top != frame ||
	    !kd_exec_cont_no_stack_service(frame))
		return -EBUSY;
	if (suspended && (frame->completion_seen ||
	    kd_exec_frame_state(frame) == KD_EXEC_FRAME_ERROR))
		return -EINVAL;
	ctx->depth--;
	ctx->top = frame->parent;
	if (!ctx->depth)
		ctx->owner = NULL;
	frame->parent = NULL;
	frame->depth = 0;
	frame->state = suspended ? KD_EXEC_FRAME_SUSPENDED : KD_EXEC_FRAME_COMPLETE;
	cont->executor = NULL;
	cont->state = suspended ? KD_CONT_SUSPENDED : KD_CONT_RETURNED;
	return 0;
}

int kd_exec_cont_suspend(struct kd_exec_continuation *cont,
	enum kd_exec_cont_wait reason)
{
	unsigned long flags;
	int ret;

	if (!kd_exec_cont_valid(cont) ||
	    (reason != KD_CONT_WAIT_CHILD && reason != KD_CONT_WAIT_SERVICE))
		return -EINVAL;
	raw_spin_lock_irqsave(&cont->root->guard, flags);
	ret = cont->root->packet_owner == cont ?
		kd_exec_cont_unbind(cont, true) : -EBUSY;
	if (!ret)
		cont->wait = reason;
	raw_spin_unlock_irqrestore(&cont->root->guard, flags);
	return ret;
}

struct kd_exec_frame *kd_exec_cont_resume(struct kd_exec_continuation *cont)
{
	if (!kd_exec_cont_valid(cont))
		return NULL;
	return kd_exec_cont_activate(cont);
}

int kd_exec_cont_child_begin(struct kd_exec_continuation *parent,
	struct kd_exec_continuation *child, const struct kd_call_state *pending)
{
	unsigned long flags;
	int ret = -EINVAL;

	if (!kd_exec_cont_valid(parent) || !kd_exec_cont_valid(child) || !pending ||
	    child->parent != parent || child->root != parent->root ||
	    pending->phase != KD_CALL_PENDING || !pending->target ||
	    !pending->stack || !pending->return_ip)
		return ret;
	raw_spin_lock_irqsave(&parent->root->guard, flags);
	if (parent->state == KD_CONT_SUSPENDED && parent->wait == KD_CONT_WAIT_CHILD &&
	    child->state == KD_CONT_READY && parent->root->packet_owner == parent &&
	    child->packet == parent->packet &&
	    child->packet->ip == pending->target && child->packet->sp == pending->stack) {
		child->pending_call = *pending;
		parent->root->packet_owner = child;
		ret = 0;
	}
	raw_spin_unlock_irqrestore(&parent->root->guard, flags);
	return ret;
}

static int kd_exec_cont_call_word(struct kd_exec_continuation *cont,
	unsigned long *return_ip)
{
	unsigned long sp = cont->packet->sp, base = cont->root->stack_base;

	if (!base || base > ~0UL - THREAD_SIZE || sp < base ||
	    sp > base + THREAD_SIZE - sizeof(*return_ip) ||
	    copy_from_kernel_nofault(return_ip, (void *)sp, sizeof(*return_ip)) ||
	    !*return_ip)
		return -EFAULT;
	return 0;
}

int kd_exec_cont_child_acquired(struct kd_exec_continuation *child)
{
	unsigned long flags, return_ip;
	enum kd_wait_state acquired;
	int ret = -EINVAL;

	if (!kd_exec_cont_valid(child) || !child->parent)
		return ret;
	acquired = smp_load_acquire(&child->request->state);
	if (acquired != KD_WAIT_ACQUIRED && acquired != KD_WAIT_EXECUTING)
		return ret;
	raw_spin_lock_irqsave(&child->root->guard, flags);
	if (child->state != KD_CONT_READY || child->root->packet_owner != child ||
	    child->pending_call.phase != KD_CALL_PENDING ||
	    child->packet->ip != child->pending_call.target ||
	    child->packet->sp != child->pending_call.stack ||
	    kd_exec_cont_call_word(child, &return_ip) ||
	    return_ip != child->pending_call.return_ip)
		goto out;
	child->packet->sp += sizeof(unsigned long);
	child->packet->ip = return_ip;
	child->packet->ax = 0;
	child->frame.entry_ip = return_ip;
	child->pending_call.phase = KD_CALL_COMPLETE;
	ret = 0;
out:
	raw_spin_unlock_irqrestore(&child->root->guard, flags);
	return ret;
}

int kd_exec_cont_child_return(struct kd_exec_continuation *child, int result,
	bool local_grant)
{
	struct kd_exec_continuation *parent;
	struct kd_exec_owner_ref *reference;
	unsigned long flags, return_ip;
	enum kd_wait_state acquired;
	int ret = -EINVAL;

	if (!kd_exec_cont_valid(child) || !(parent = child->parent))
		return ret;
	acquired = smp_load_acquire(&child->request->state);
	if (result == -EINTR) {
		if (local_grant || acquired != KD_WAIT_CANCEL_ACK || child->frame.executed)
			return ret;
	} else if (result || (local_grant ?
		(acquired != KD_WAIT_ACQUIRED && acquired != KD_WAIT_RETURN_ACK) :
		(acquired != KD_WAIT_RELEASED && acquired != KD_WAIT_RETURN_ACK))) {
		return ret;
	}
	raw_spin_lock_irqsave(&child->root->guard, flags);
	if (parent->state != KD_CONT_SUSPENDED ||
	    parent->wait != KD_CONT_WAIT_CHILD || child->root->packet_owner != child ||
	    child->executor || !list_empty(&child->children))
		goto out;
	if (local_grant || result == -EINTR) {
		if (child->state != KD_CONT_READY ||
		    child->pending_call.phase != KD_CALL_PENDING ||
		    child->packet->ip != child->pending_call.target ||
		    child->packet->sp != child->pending_call.stack ||
		    kd_exec_cont_call_word(child, &return_ip) ||
		    return_ip != child->pending_call.return_ip)
			goto out;
		if (result == -EINTR && !list_empty(&child->owners))
			goto out;
		if (local_grant) {
			/* The child wait has returned, not physically unlocked. Move the
			 * exact acquisition references into the continuing parent. */
			list_for_each_entry(reference, &child->owners, link)
				reference->continuation = parent;
			list_splice_tail_init(&child->owners, &parent->owners);
		}
		child->packet->ax = (unsigned int)result;
	} else {
		if (child->state != KD_CONT_RETURNED ||
		    child->pending_call.phase != KD_CALL_COMPLETE ||
		    !child->frame.completion_seen || !child->frame.outer_unlock_seen ||
		    !list_empty(&child->owners) || kd_exec_cont_call_word(child, &return_ip))
			goto out;
	}
	/* Only the current token owner consumes this CALL. After publication the
	 * child must not inspect or modify the shared packet again. */
	child->packet->sp += sizeof(unsigned long);
	child->packet->ip = return_ip;
	parent->frame.continuation_ip = child->packet->ip;
	parent->frame.continuation_sp = child->packet->sp;
	parent->frame.control_call = child->pending_call;
	parent->frame.control_call.phase = KD_CALL_COMPLETE;
	child->pending_call.phase = KD_CALL_COMPLETE;
	child->result = result;
	child->state = KD_CONT_RETURNED;
	parent->state = KD_CONT_READY;
	parent->frame.state = KD_EXEC_FRAME_RUNNING;
	parent->wait = KD_CONT_WAIT_NONE;
	child->root->packet_owner = parent;
	ret = 0;
out:
	raw_spin_unlock_irqrestore(&child->root->guard, flags);
	return ret;
}

void kd_exec_owner_ref_init(struct kd_exec_owner_ref *reference)
{
	INIT_LIST_HEAD(&reference->link);
	INIT_LIST_HEAD(&reference->borrowers);
	INIT_LIST_HEAD(&reference->borrow_link);
	INIT_LIST_HEAD(&reference->storage_link);
	reference->continuation = NULL;
	reference->storage_owner = NULL;
	reference->source = NULL;
	reference->ops = NULL;
	reference->identity = NULL;
	reference->generation = 0;
}

int kd_exec_cont_owner_get(struct kd_exec_continuation *cont,
	struct kd_exec_owner_ref *reference, const void *identity, u64 generation,
	const struct kd_exec_owner_ops *ops)
{
	unsigned long flags;
	int ret = -EINVAL;

	if (!kd_exec_cont_valid(cont) || !reference || !identity || !generation ||
	    !ops || !ops->valid || !ops->released || !ops->valid(identity, generation))
		return ret;
	raw_spin_lock_irqsave(&cont->root->guard, flags);
	if (!reference->continuation && list_empty(&reference->link) &&
	    (cont->state == KD_CONT_READY || cont->state == KD_CONT_BOUND) &&
	    cont->root->packet_owner == cont) {
		reference->continuation = cont;
		reference->storage_owner = cont;
		reference->identity = identity;
		reference->generation = generation;
		reference->ops = ops;
		reference->source = NULL;
		list_add_tail(&reference->link, &cont->owners);
		list_add_tail(&reference->storage_link, &cont->storage_owners);
		ret = 0;
	}
	raw_spin_unlock_irqrestore(&cont->root->guard, flags);
	return ret;
}

int kd_exec_cont_owner_borrow(struct kd_exec_continuation *cont,
	struct kd_exec_owner_ref *reference, struct kd_exec_owner_ref *source)
{
	struct kd_exec_continuation *ancestor;
	unsigned long flags;
	int ret = -EINVAL;

	if (!kd_exec_cont_valid(cont) || !reference || !source ||
	    !source->continuation || source->continuation->root != cont->root)
		return ret;
	raw_spin_lock_irqsave(&cont->root->guard, flags);
	for (ancestor = cont->parent; ancestor; ancestor = ancestor->parent)
		if (ancestor == source->continuation)
			break;
	if (!ancestor || reference->continuation || !list_empty(&reference->link) ||
	    (cont->state != KD_CONT_READY && cont->state != KD_CONT_BOUND))
		goto out;
	reference->continuation = cont;
	reference->storage_owner = cont;
	reference->source = source;
	reference->identity = source->identity;
	reference->generation = source->generation;
	reference->ops = source->ops;
	list_add_tail(&reference->link, &cont->owners);
	list_add_tail(&reference->storage_link, &cont->storage_owners);
	list_add_tail(&reference->borrow_link, &source->borrowers);
	ret = 0;
out:
	raw_spin_unlock_irqrestore(&cont->root->guard, flags);
	return ret;
}

int kd_exec_cont_owner_put(struct kd_exec_owner_ref *reference)
{
	struct kd_exec_continuation *cont;
	unsigned long flags;
	enum kd_wait_state acquired;
	int ret = -EBUSY;

	if (!reference || !(cont = reference->continuation) || !kd_exec_cont_valid(cont))
		return -EINVAL;
	/* Underlying records are retained by the caller; callbacks never inspect
	 * a released lock object and never run under the root metadata guard. */
	if (!reference->source &&
	    !reference->ops->released(reference->identity, reference->generation))
		return ret;
	acquired = smp_load_acquire(&cont->request->state);
	raw_spin_lock_irqsave(&cont->root->guard, flags);
	if (!list_empty(&reference->borrowers))
		goto out;
	if (reference->source && acquired != KD_WAIT_RELEASED &&
	    acquired != KD_WAIT_RETURN_ACK && acquired != KD_WAIT_CANCEL_ACK &&
	    cont->state != KD_CONT_RETURNED)
		goto out;
	if (reference->source)
		list_del_init(&reference->borrow_link);
	list_del_init(&reference->link);
	list_del_init(&reference->storage_link);
	reference->continuation = NULL;
	reference->storage_owner = NULL;
	reference->source = NULL;
	ret = 0;
out:
	raw_spin_unlock_irqrestore(&cont->root->guard, flags);
	return ret;
}

int kd_exec_cont_return(struct kd_exec_continuation *cont, int result)
{
	unsigned long flags;
	enum kd_wait_state acquired;
	int ret = -EINVAL;

	if (!kd_exec_cont_valid(cont))
		return ret;
	acquired = smp_load_acquire(&cont->request->state);
	if ((result == -EINTR && acquired != KD_WAIT_CANCEL_ACK) ||
	    (result != -EINTR && (result ||
	     (acquired != KD_WAIT_RELEASED && acquired != KD_WAIT_RETURN_ACK))))
		return ret;
	raw_spin_lock_irqsave(&cont->root->guard, flags);
	if (cont->root->packet_owner != cont || !list_empty(&cont->children) ||
	    !list_empty(&cont->owners))
		goto out;
	if (result == -EINTR) {
		if (cont->executor || cont->frame.executed || cont->state != KD_CONT_READY)
			goto out;
		cont->state = KD_CONT_RETURNED;
	} else {
		if (cont->state != KD_CONT_BOUND || !cont->frame.executed ||
		    !kd_exec_cont_no_stack_service(&cont->frame))
			goto out;
		if (!cont->frame.completion_seen && kd_exec_frame_complete(&cont->frame))
			goto out;
		ret = kd_exec_cont_unbind(cont, false);
		if (ret)
			goto out;
	}
	cont->result = result;
	cont->wait = KD_CONT_WAIT_NONE;
	ret = 0;
out:
	raw_spin_unlock_irqrestore(&cont->root->guard, flags);
	return ret;
}

int kd_exec_cont_retire(struct kd_exec_continuation *cont)
{
	struct task_struct *origin;
	struct kd_exec_continuation *root;
	unsigned long flags;
	enum kd_wait_state acquired;
	bool put_source, put_stack;
	int ret = -EBUSY;

	if (!kd_exec_cont_valid(cont))
		return -EINVAL;
	root = cont->root;
	acquired = smp_load_acquire(&cont->request->state);
	if (acquired != KD_WAIT_RETURN_ACK && acquired != KD_WAIT_CANCEL_ACK &&
	    acquired != KD_WAIT_RETIRED && acquired != KD_WAIT_PRIVATE)
		return ret;
	raw_spin_lock_irqsave(&root->guard, flags);
	if ((cont->state != KD_CONT_RETURNED &&
	     !(cont->state == KD_CONT_READY && acquired == KD_WAIT_PRIVATE)) ||
	    cont->executor || !list_empty(&cont->children) || !list_empty(&cont->owners) ||
	    !list_empty(&cont->storage_owners) ||
	    READ_ONCE(cont->request->memberships) || READ_ONCE(cont->request->selection) ||
	    READ_ONCE(cont->request->acquisition) ||
	    (cont->parent && root->packet_owner == cont))
		goto out;
	if (cont->parent)
		list_del_init(&cont->child_link);
	else
		root->packet_owner = NULL;
	put_source = cont->source_lease;
	put_stack = cont->stack_lease;
	origin = cont->request->logical_origin;
	cont->source_lease = false;
	cont->stack_lease = false;
	cont->state = KD_CONT_RETIRED;
	cont->frame.state = KD_EXEC_FRAME_UNUSED;
	cont->frame.role = KD_ROLE_DONE;
	ret = 0;
out:
	raw_spin_unlock_irqrestore(&root->guard, flags);
	if (ret)
		return ret;
	/* No object/packet access follows return ACK. Descendants cannot retain a
	 * reference once the root reaches here: its explicit child list was empty. */
	if (put_stack) {
		cont->stack_put(origin);
		put_task_struct(origin);
	}
	if (put_source)
		kd_source_frame_put();
	return 0;
}
