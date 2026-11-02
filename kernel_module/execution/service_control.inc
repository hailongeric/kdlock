/* SPDX-License-Identifier: GPL-2.0 */
/* Typed controls for retained roots. Preparation records a real CALL only;
 * physical acquisition/release is performed by the root's service engine. */
static int kd_jit_service_control(struct kd_exec_frame *frame, struct kd_regs *regs)
{
	struct kd_exec_continuation *cont = frame ? kd_exec_frame_continuation(frame) : NULL;
	enum kd_exec_service_api api = KD_SERVICE_NONE;
	unsigned int state = TASK_UNINTERRUPTIBLE;
	bool acquire = false, may_delegate = false, integer = false;
	unsigned long target = regs->ip;
	unsigned long object = regs->di;
	unsigned int operation, flags;
	void *normalized;
	int ret;

	if (!cont || !cont->service_ops)
		return 0;
	if (kd_rwsem_provider_lookup_control(target, (void *)regs->di,
		&operation, &flags, &normalized)) {
		object = (unsigned long)normalized;
		may_delegate = !!(flags & KD_RWSEM_CONTROL_CAPTURE);
		integer = !!(flags & KD_RWSEM_CONTROL_INTEGER);
		switch (operation) {
		case KD_RWSEM_OP_DOWN_WRITE:
			api = KD_SERVICE_RWSEM_WRITE;
			acquire = true;
			break;
		case KD_RWSEM_OP_DOWN_WRITE_INTERRUPTIBLE:
			api = KD_SERVICE_RWSEM_WRITE_INTERRUPTIBLE;
			state = TASK_INTERRUPTIBLE;
			acquire = true;
			break;
		case KD_RWSEM_OP_DOWN_WRITE_KILLABLE:
			api = KD_SERVICE_RWSEM_WRITE_KILLABLE;
			state = TASK_KILLABLE;
			acquire = true;
			break;
		case KD_RWSEM_OP_UP_WRITE:
			api = KD_SERVICE_RWSEM_UP_WRITE;
			break;
		case KD_RWSEM_OP_DOWNGRADE_WRITE:
			api = KD_SERVICE_RWSEM_DOWNGRADE;
			break;
		case KD_RWSEM_OP_UP_READ:
			api = KD_SERVICE_RWSEM_UP_READ;
			break;
		default:
			/* Local read/try/non-owner forms retain their ordinary facade,
			 * but do not yet have a retained CALL service contract. */
			return -EOPNOTSUPP;
		}
	} else if (target == (unsigned long)kd_mutex_direct_lock_clobber_v1 ||
	    target == (unsigned long)kd_mutex_direct_contended_clobber_v1 ||
	    target == (unsigned long)kd_mutex_local_lock ||
	    target == (unsigned long)kd_mutex_api_lock) {
		api = KD_SERVICE_MUTEX_LOCK;
		acquire = true;
		may_delegate = target == (unsigned long)kd_mutex_direct_lock_clobber_v1 ||
			target == (unsigned long)kd_mutex_direct_contended_clobber_v1;
	} else if (target == (unsigned long)kd_mutex_lock_killable ||
		   target == (unsigned long)kd_mutex_lock_killable_clobber_v1) {
		api = KD_SERVICE_MUTEX_LOCK_KILLABLE;
		state = TASK_KILLABLE;
		acquire = integer = true;
		may_delegate = target == (unsigned long)kd_mutex_lock_killable_clobber_v1;
	} else if (target == (unsigned long)kd_mutex_lock_interruptible ||
		   target == (unsigned long)kd_mutex_lock_interruptible_clobber_v1) {
		api = KD_SERVICE_MUTEX_LOCK_INTERRUPTIBLE;
		state = TASK_INTERRUPTIBLE;
		acquire = integer = true;
		may_delegate = target == (unsigned long)kd_mutex_lock_interruptible_clobber_v1;
	} else if (target == (unsigned long)kd_mutex_direct_unlock_clobber_v1 ||
		   target == (unsigned long)kd_mutex_local_unlock ||
		   target == (unsigned long)kd_mutex_api_unlock) {
		api = KD_SERVICE_MUTEX_UNLOCK;
	} else if (target == (unsigned long)kd_down_write ||
		   target == (unsigned long)kd_rwsem_down_write_clobber_v1) {
		api = KD_SERVICE_RWSEM_WRITE;
		acquire = true;
		may_delegate = target == (unsigned long)kd_rwsem_down_write_clobber_v1;
	} else if (target == (unsigned long)kd_down_write_killable ||
		   target == (unsigned long)kd_rwsem_down_write_killable_clobber_v1) {
		api = KD_SERVICE_RWSEM_WRITE_KILLABLE;
		state = TASK_KILLABLE;
		acquire = integer = true;
		may_delegate = target == (unsigned long)kd_rwsem_down_write_killable_clobber_v1;
	} else if (target == (unsigned long)kd_down_write_interruptible ||
		   target == (unsigned long)kd_rwsem_down_write_interruptible_clobber_v1) {
		api = KD_SERVICE_RWSEM_WRITE_INTERRUPTIBLE;
		state = TASK_INTERRUPTIBLE;
		acquire = integer = true;
		may_delegate = target == (unsigned long)kd_rwsem_down_write_interruptible_clobber_v1;
	} else if (target == (unsigned long)kd_up_write ||
		   target == (unsigned long)kd_rwsem_up_write_clobber_v1) {
		api = KD_SERVICE_RWSEM_UP_WRITE;
	} else if (target == (unsigned long)kd_downgrade_write) {
		api = KD_SERVICE_RWSEM_DOWNGRADE;
	} else if (target == (unsigned long)kd_up_read) {
		api = KD_SERVICE_RWSEM_UP_READ;
	}
	if (api == KD_SERVICE_NONE) {
		if (!frame->image || !(frame->image->requirements & KD_IMAGE_REQUIRE_ORIGIN_CALL))
			return 0;
		ret = kd_exec_cont_native_prepare(frame);
		return ret == -ENOENT ? 0 : ret ? ret : KD_EXE_KNOWN_ORIGIN_CALL;
	}
	if (may_delegate && (api == KD_SERVICE_RWSEM_WRITE ||
	    api == KD_SERVICE_RWSEM_WRITE_INTERRUPTIBLE || api == KD_SERVICE_RWSEM_WRITE_KILLABLE))
		may_delegate = !!READ_ONCE(((struct kd_rwsem *)object)->prepared_writes);
	ret = kd_exec_cont_service_prepare(frame, api, object, state,
		acquire, may_delegate, integer);
	return ret ? ret : KD_EXE_KNOWN_SERVICE;
}
