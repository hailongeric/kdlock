// SPDX-License-Identifier: GPL-2.0
/* One selected virtual child, before wrapper entry. Report only after drain. */
#include <linux/moduleparam.h>

static unsigned int kd_refusal_kind;
static unsigned long kd_refusal_lock;
module_param_named(spin_selftest_refusal, kd_refusal_kind, uint, 0444);
module_param_named(spin_selftest_refusal_lock, kd_refusal_lock, ulong, 0644);
MODULE_PARM_DESC(
	spin_selftest_refusal,
	"selftest-only: one virtual pre-entry refusal, 1=NO_RUN, 2=RUN_ERROR");
MODULE_PARM_DESC(
	spin_selftest_refusal_lock,
	"selftest-only: arm after publication with the selected lock address");

static atomic_t kd_refusal_claimed = ATOMIC_INIT(0);
static struct {
	const struct kd_exec_frame *parent;
	struct pt_regs parent_regs, node_regs;
	unsigned long entry, ip, sp, lock, outer, gs, task;
	unsigned long reject_owner, acquired_owner;
	unsigned int reject_cpu, acquired_cpu, cancelled, acquired, finished;
	int pid, injected_ret, acquired_ret, end_ret;
	bool initial, cancel_valid, acquire_valid, end_valid;
} kd_refusal;

static noinline bool kd_spin_selftest_refuse(struct kd_exec_frame *frame,
					     const struct kd_spin_node *node,
					     int *ret)
{
	const struct kd_exec_frame *parent = frame->resume_target;

	if (kd_readmit_refusals)
		return kd_spin_selftest_readmit_attempt(frame, node, ret);
	if (!kd_refusal_kind || kd_refusal_kind > 2 || !node->jit_waiter ||
	    frame->outer_lock_addr != READ_ONCE(kd_refusal_lock) || !parent ||
	    frame->executed || !parent->executed ||
	    atomic_cmpxchg(&kd_refusal_claimed, 0, 1))
		return false;
	kd_refusal.entry = frame->entry_ip;
	kd_refusal.ip = node->regs->ip;
	kd_refusal.sp = node->regs->sp;
	kd_refusal.lock = frame->outer_lock_addr;
	kd_refusal.outer = parent->outer_lock_addr;
	kd_refusal.gs = frame->gsbase;
	kd_refusal.task = (unsigned long)frame->logical_task;
	kd_refusal.pid = frame->logical_pid;
	kd_refusal.reject_owner = (unsigned long)current;
	kd_refusal.reject_cpu = raw_smp_processor_id();
	kd_refusal.parent_regs = *kd_exec_frame_regs(parent);
	kd_refusal.node_regs = *node->regs;
	kd_refusal.initial = !frame->executed && parent->executed &&
			     kd_exec_frame_validate(frame) &&
			     kd_exec_frame_validate(parent) &&
			     parent->remote_result == KD_EXEC_REMOTE_WAITING &&
			     parent->control_call.phase == KD_CALL_ENTERED &&
			     parent->logical_task == frame->logical_task &&
			     parent->gsbase == frame->gsbase;
	WRITE_ONCE(kd_refusal.parent, parent);
	*ret = kd_refusal_kind == 1 ? KD_EXE_NO_RUN : KD_EXE_RUN_ERROR;
	kd_refusal.injected_ret = *ret;
	return true;
}

static noinline void
kd_spin_selftest_refusal_cancel(const struct kd_exec_frame *frame)
{
	const struct kd_exec_frame *parent = READ_ONCE(kd_refusal.parent);

	if (kd_readmit_refusals)
		kd_spin_selftest_readmit_cancel(frame);
	if (!parent || frame->outer_lock_addr != kd_refusal.lock ||
	    frame->logical_pid != kd_refusal.pid || frame->executed)
		return;
	kd_refusal.cancelled++;
	kd_refusal.cancel_valid =
		!frame->resume_target &&
		parent->remote_result == KD_EXEC_REMOTE_WAITING &&
		!memcmp(kd_exec_frame_regs(parent), &kd_refusal.parent_regs,
			sizeof(parent->regs)) &&
		!memcmp(kd_exec_frame_regs(frame), &kd_refusal.node_regs,
			sizeof(frame->regs));
}

static noinline void
kd_spin_selftest_refusal_return(const struct kd_exec_frame *parent,
				const struct kd_spin_node *node, int ret)
{
	if (kd_readmit_refusals)
		kd_spin_selftest_readmit_return(parent, node, ret);
	if (parent != READ_ONCE(kd_refusal.parent) ||
	    (unsigned long)node->lock != kd_refusal.lock ||
	    parent->logical_pid != kd_refusal.pid)
		return;
	kd_refusal.acquired++;
	kd_refusal.acquired_ret = ret;
	kd_refusal.acquired_cpu = raw_smp_processor_id();
	kd_refusal.acquired_owner = (unsigned long)current;
	kd_refusal.acquire_valid =
		(ret == 0 || ret == 2) &&
		parent->remote_result == KD_EXEC_REMOTE_WAITING &&
		parent->control_call.phase == KD_CALL_ENTERED &&
		!node->jit_retry && !node->completed && !node->native_resume &&
		kd_spin_debug_owner((void *)kd_refusal.lock) ==
			(unsigned long)current &&
		raw_spin_is_locked((raw_spinlock_t *)kd_refusal.lock) &&
		raw_spin_is_locked((raw_spinlock_t *)kd_refusal.outer) &&
		parent->executed && parent->gsbase == kd_refusal.gs &&
		(unsigned long)parent->logical_task == kd_refusal.task &&
		!memcmp(kd_exec_frame_regs(parent), &kd_refusal.parent_regs,
			sizeof(parent->regs)) &&
		!memcmp(node->regs, &kd_refusal.node_regs, sizeof(*node->regs));
}

static noinline void
kd_spin_selftest_refusal_end(const struct kd_exec_frame *frame, int ret)
{
	if (kd_readmit_refusals)
		kd_spin_selftest_readmit_end(frame, ret);
	if (frame != READ_ONCE(kd_refusal.parent) ||
	    frame->outer_lock_addr != kd_refusal.outer ||
	    frame->logical_pid != kd_refusal.pid || kd_refusal.finished)
		return;
	kd_refusal.finished++;
	kd_refusal.end_ret = ret;
	kd_refusal.end_valid =
		kd_refusal.acquired == 1 && frame->executed &&
		ret == KD_EXE_RUN_TO_UNLOCK &&
		frame->remote_result == KD_EXEC_REMOTE_IDLE &&
		(unsigned long)current == kd_refusal.acquired_owner &&
		raw_smp_processor_id() == kd_refusal.acquired_cpu &&
		frame->gsbase == kd_refusal.gs &&
		(unsigned long)frame->logical_task == kd_refusal.task;
}

static void kd_spin_selftest_refusal_report(void)
{
	bool valid;

	kd_spin_selftest_readmit_report();
	if (!kd_refusal_kind)
		return;
	valid = atomic_read(&kd_refusal_claimed) == 1 && kd_refusal.initial &&
		kd_refusal.cancelled == 1 && kd_refusal.cancel_valid &&
		kd_refusal.acquired == 1 && kd_refusal.acquire_valid &&
		kd_refusal.finished == 1 && kd_refusal.end_valid;
	pr_info("kd_refusal summary: kind=%u claimed=%d task=%d entry=%lx ip=%lx sp=%lx lock=%lx outer=%lx reject_cpu=%u reject_owner=%lx acquired_cpu=%u acquired_owner=%lx injected=%d cancelled=%u acquired=%u returned=%d finished=%u end=%d initial=%u cancel_valid=%u acquire_valid=%u end_valid=%u valid=%u\n",
		kd_refusal_kind, atomic_read(&kd_refusal_claimed),
		kd_refusal.pid, kd_refusal.entry, kd_refusal.ip, kd_refusal.sp,
		kd_refusal.lock, kd_refusal.outer, kd_refusal.reject_cpu,
		kd_refusal.reject_owner, kd_refusal.acquired_cpu,
		kd_refusal.acquired_owner, kd_refusal.injected_ret,
		kd_refusal.cancelled, kd_refusal.acquired,
		kd_refusal.acquired_ret, kd_refusal.finished,
		kd_refusal.end_ret, kd_refusal.initial, kd_refusal.cancel_valid,
		kd_refusal.acquire_valid, kd_refusal.end_valid, valid);
}
