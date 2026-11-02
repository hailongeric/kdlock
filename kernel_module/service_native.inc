/* SPDX-License-Identifier: GPL-2.0 */
/* Retained authority for ordinary Native spin/RCU APIs. O is the actual
 * Native owner. E receives permission only through the exact RPC ACK. */
static struct kd_native_owner *kd_service_native_reserve(
	struct kd_service_root *root, unsigned int kind, unsigned long object, u64 sequence)
{
	struct kd_native_owner *owner;

	list_for_each_entry(owner, &root->native_owners, link) {
		if (owner->kind != KD_NATIVE_OWNER_FREE)
			continue;
		owner->origin = root->owner.request.logical_origin;
		owner->identity = root->owner.request.identity;
		owner->generation = root->owner.request.generation;
		owner->sequence = sequence;
		owner->object = object;
		owner->held = false;
		owner->kind = kind;
		return owner;
	}
	BUG();
}

static int kd_service_native_prepare(struct kd_service_root *root)
{
	struct kd_origin_call *call = &root->continuation.origin_call;
	struct kd_native_owner *owner;
	unsigned int free = 0, needed = 0;
	unsigned int spins = kd_service_native_pins(root);
	unsigned int rcu = kd_service_native_depth(root, KD_NATIVE_OWNER_RCU);

	if (!(call->executor_irq_flags & X86_EFLAGS_IF) || preempt_count() != 1)
		return -EOPNOTSUPP;
	if (call->context_kind == KD_SERVICE_CALL_BALANCED_ORIGIN && (spins || rcu))
		return -EOPNOTSUPP;
	call->executor_pinned = spins || call->context_kind >= KD_SERVICE_CALL_PTE_LOCK;
	switch (call->context_kind) {
	case KD_SERVICE_CALL_PTE_LOCK:
		if (!call->object_out)
			return -EINVAL;
		needed = 2;
		break;
	case KD_SERVICE_CALL_SPIN_LOCK:
		if (!call->object || kd_service_native_find(root, KD_NATIVE_OWNER_SPIN,
			call->object))
			return -EINVAL;
		needed = 1;
		break;
	case KD_SERVICE_CALL_SPIN_TRYLOCK:
		/* Native trylock still returns false for an already held object.
		 * Its separate candidate must not overwrite the live owner record. */
		if (!call->object)
			return -EINVAL;
		needed = 1;
		break;
	case KD_SERVICE_CALL_RCU_LOCK:
	case KD_SERVICE_CALL_PTE_RCU:
		needed = 1;
		break;
	case KD_SERVICE_CALL_SPIN_UNLOCK:
		call->spin_owner = kd_service_native_find(root, KD_NATIVE_OWNER_SPIN,
			call->object);
		if (!call->spin_owner)
			return -EINVAL;
		break;
	case KD_SERVICE_CALL_RCU_UNLOCK:
		call->rcu_owner = kd_service_native_find(root, KD_NATIVE_OWNER_RCU, 0);
		if (!call->rcu_owner)
			return -EINVAL;
		break;
	case KD_SERVICE_CALL_BALANCED_ORIGIN:
	case KD_SERVICE_CALL_ATOMIC_ORIGIN:
		break;
	default:
		return -EOPNOTSUPP;
	}
	list_for_each_entry(owner, &root->native_owners, link)
		free += owner->kind == KD_NATIVE_OWNER_FREE;
	if (free < needed)
		return -EAGAIN;
	if (call->context_kind == KD_SERVICE_CALL_PTE_LOCK ||
	    call->context_kind == KD_SERVICE_CALL_SPIN_LOCK ||
	    call->context_kind == KD_SERVICE_CALL_SPIN_TRYLOCK)
		call->spin_owner = kd_service_native_reserve(root,
			KD_NATIVE_OWNER_SPIN, call->object, call->sequence);
	if (call->context_kind == KD_SERVICE_CALL_PTE_LOCK ||
	    call->context_kind == KD_SERVICE_CALL_PTE_RCU ||
	    call->context_kind == KD_SERVICE_CALL_RCU_LOCK)
		call->rcu_owner = kd_service_native_reserve(root,
			KD_NATIVE_OWNER_RCU, 0, call->sequence);
	return 0;
}

static void kd_service_native_trace(const char *stage,
	struct kd_service_root *root, struct kd_native_owner *owner)
{
	struct kd_origin_call *call = &root->continuation.origin_call;

	if (unlikely(READ_ONCE(kd_service_trace)))
		pr_info("kd_service native: stage=%s origin=%d executor=%d task=%d identity=%px generation=%llu sequence=%llu acquisition_seq=%llu kind=%u object=%lx preempt=%u rcu=%u\n",
			stage, owner->origin->pid, root->worker->pid, current->pid,
			owner->identity, (unsigned long long)owner->generation,
			(unsigned long long)call->sequence,
			(unsigned long long)owner->sequence, owner->kind, owner->object,
			preempt_count(), kd_service_origin_rcu_depth());
}

/* Runs on O's real task stack, after Native returns and before engine repin.
 * Exact records decide expected deltas; these counts cannot grant a lock. */
static void kd_service_native_finish(struct kd_service_root *root)
{
	struct kd_origin_call *call = &root->continuation.origin_call;
	unsigned int preempt = call->baseline_preempt;
	unsigned int rcu = call->baseline_rcu;
	bool spin_grant = false, rcu_grant = false;
	bool spin_release = false, rcu_release = false;
	unsigned long object;

	switch (call->context_kind) {
	case KD_SERVICE_CALL_PTE_LOCK:
		spin_grant = rcu_grant = !!call->packet->ax;
		if (spin_grant) {
			BUG_ON(copy_from_kernel_nofault(&object, (void *)call->object_out,
				sizeof(object)) || !object ||
				kd_service_native_find(root, KD_NATIVE_OWNER_SPIN, object));
			call->spin_owner->object = object;
		}
		break;
	case KD_SERVICE_CALL_SPIN_LOCK:
		spin_grant = true;
		break;
	case KD_SERVICE_CALL_SPIN_TRYLOCK:
		spin_grant = !!call->packet->ax;
		break;
	case KD_SERVICE_CALL_RCU_LOCK:
		rcu_grant = true;
		break;
	case KD_SERVICE_CALL_PTE_RCU:
		rcu_grant = !!call->packet->ax;
		break;
	case KD_SERVICE_CALL_SPIN_UNLOCK:
		BUG_ON(!call->spin_owner || !call->spin_owner->held ||
			call->spin_owner->object != call->object || !preempt);
		spin_release = true;
		--preempt;
		break;
	case KD_SERVICE_CALL_RCU_UNLOCK:
		BUG_ON(!call->rcu_owner || !call->rcu_owner->held || !rcu);
		rcu_release = true;
		--rcu;
		break;
	default:
		break;
	}
	preempt += spin_grant;
	rcu += rcu_grant;
	BUG_ON(preempt_count() != preempt || kd_service_origin_rcu_depth() != rcu ||
		irqs_disabled());
	if (call->spin_owner) {
		call->spin_owner->held = spin_grant;
		kd_service_native_trace(spin_grant ? "grant" :
			spin_release ? "release" : "not_granted", root, call->spin_owner);
		if (!spin_grant)
			call->spin_owner->kind = KD_NATIVE_OWNER_FREE;
	}
	if (call->rcu_owner) {
		call->rcu_owner->held = rcu_grant;
		if (rcu_grant && call->packet->ax &&
		    (call->context_kind == KD_SERVICE_CALL_PTE_LOCK ||
		     call->context_kind == KD_SERVICE_CALL_PTE_RCU))
			call->rcu_owner->object = call->packet->ax;
		kd_service_native_trace(rcu_grant ? "grant" :
			rcu_release ? "release" : "not_granted", root, call->rcu_owner);
		if (!rcu_grant)
			call->rcu_owner->kind = KD_NATIVE_OWNER_FREE;
	}
}
