// SPDX-License-Identifier: GPL-2.0
/* Two real attempts on one virtual packet; no queue or owner manipulation. */
#include <linux/moduleparam.h>

static unsigned int kd_readmit_refusals;
static unsigned long kd_readmit_lock;
module_param_named(spin_selftest_readmit, kd_readmit_refusals, uint, 0444);
module_param_named(spin_selftest_readmit_lock, kd_readmit_lock, ulong, 0644);
MODULE_PARM_DESC(
	spin_selftest_readmit,
	"selftest-only: decline 1 or 2 virtual attempts before wrapper entry");
MODULE_PARM_DESC(spin_selftest_readmit_lock,
		 "selftest-only: arm the readmission lock after publication");

static struct {
	const struct kd_exec_frame *parent;
	struct pt_regs parent_regs, node_regs;
	unsigned long entry, ip, sp, lock, outer, gs, task, node;
	unsigned long owner[2], head[2], tail[2], return_owner;
	unsigned int cpu[2], attempts, cancelled, ended[2], return_cpu;
	unsigned int returned, finished, unexpected;
	unsigned long follow_outer, follow_ip, follow_sp, follow_owner;
	unsigned int followed, follow_cpu, follow_depth;
	bool follow_valid;
	int pid, child_ret[2], queue_ret, parent_ret;
	bool initial[2], cancel_valid[2], child_executed[2], return_valid,
		end_valid;
} kd_readmit;

/* Only the locally acquired parent may publish the next remote request.
 * Its register packet has now advanced, but both physical locks must remain. */
static noinline void
kd_spin_selftest_readmit_follow(const struct kd_exec_frame *frame)
{
	const struct kd_exec_frame *parent = frame->resume_target;
	unsigned int depth;

	if (kd_readmit_refusals != 2 ||
	    parent != READ_ONCE(kd_readmit.parent) ||
	    kd_readmit.returned != 1 || frame->logical_pid != kd_readmit.pid)
		return;
	depth = parent->jit_lock_depth;
	kd_readmit.followed++;
	kd_readmit.follow_outer = frame->outer_lock_addr;
	kd_readmit.follow_ip = kd_exec_frame_regs(frame)->ip;
	kd_readmit.follow_sp = kd_exec_frame_regs(frame)->sp;
	kd_readmit.follow_cpu = raw_smp_processor_id();
	kd_readmit.follow_owner = (unsigned long)current;
	kd_readmit.follow_depth = depth;
	kd_readmit.follow_valid =
		kd_readmit.return_valid && kd_exec_frame_validate(parent) &&
		kd_exec_frame_validate(frame) && depth >= 2 &&
		depth <= KD_EXEC_MAX_LOCK_DEPTH &&
		parent->jit_lock_addr[depth - 1] == kd_readmit.lock &&
		!parent->jit_lock_released[depth - 1] &&
		parent->outer_lock_addr == kd_readmit.outer &&
		parent->remote_result == KD_EXEC_REMOTE_WAITING &&
		parent->control_call.phase == KD_CALL_ENTERED &&
		parent->gsbase == kd_readmit.gs &&
		frame->gsbase == kd_readmit.gs &&
		(unsigned long)parent->logical_task == kd_readmit.task &&
		frame->logical_task == parent->logical_task &&
		kd_spin_debug_owner((void *)kd_readmit.lock) ==
			kd_readmit.return_owner &&
		kd_spin_debug_owner((void *)kd_readmit.outer) ==
			kd_readmit.return_owner &&
		raw_spin_is_locked((raw_spinlock_t *)kd_readmit.lock) &&
		raw_spin_is_locked((raw_spinlock_t *)kd_readmit.outer);
}

static noinline bool
kd_spin_selftest_readmit_attempt(struct kd_exec_frame *frame,
				 const struct kd_spin_node *node, int *ret)
{
	const struct kd_exec_frame *parent = frame->resume_target;
	unsigned int index;

	if (!kd_readmit_refusals || kd_readmit_refusals > 2 ||
	    node->execution->kind != KD_SPIN_CONT_VIRTUAL || !parent || frame->executed ||
	    !parent->executed)
		return false;
	if (frame->outer_lock_addr != READ_ONCE(kd_readmit_lock)) {
		kd_spin_selftest_readmit_follow(frame);
		return false;
	}
	index = kd_readmit.attempts;
	if (index >= 2) {
		kd_readmit.unexpected++;
		return false;
	}
	if (!index) {
		kd_readmit.entry = frame->entry_ip;
		kd_readmit.ip = node->execution->frame.regs_ref->ip;
		kd_readmit.sp = node->execution->frame.regs_ref->sp;
		kd_readmit.lock = frame->outer_lock_addr;
		kd_readmit.outer = parent->outer_lock_addr;
		kd_readmit.gs = frame->gsbase;
		kd_readmit.task = (unsigned long)frame->logical_task;
		kd_readmit.pid = frame->logical_pid;
		kd_readmit.node = (unsigned long)node;
		kd_readmit.parent_regs = *kd_exec_frame_regs(parent);
		kd_readmit.node_regs = *node->execution->frame.regs_ref;
		WRITE_ONCE(kd_readmit.parent, parent);
	}
	kd_readmit.owner[index] = (unsigned long)current;
	kd_readmit.cpu[index] = raw_smp_processor_id();
#ifdef NUMA_AWARE
	kd_readmit.head[index] =
		(unsigned long)this_cpu_ptr(&kd_spin_cpu)
			->local_queue_head;
	kd_readmit.tail[index] =
		(unsigned long)this_cpu_ptr(&kd_spin_cpu)
			->local_queue_tail;
#endif
	kd_readmit.initial[index] =
		parent == kd_readmit.parent && kd_exec_frame_validate(frame) &&
		kd_exec_frame_validate(parent) &&
		frame->entry_ip == kd_readmit.entry &&
		(unsigned long)node == kd_readmit.node &&
		parent->outer_lock_addr == kd_readmit.outer &&
		frame->gsbase == kd_readmit.gs &&
		parent->gsbase == kd_readmit.gs &&
		(unsigned long)parent->logical_task == kd_readmit.task &&
		parent->logical_task == frame->logical_task &&
		frame->logical_pid == kd_readmit.pid &&
		parent->remote_result == KD_EXEC_REMOTE_WAITING &&
		parent->control_call.phase == KD_CALL_ENTERED &&
		!node->completed && node->execution->result != KD_SPIN_RES_RETRY && node->execution->result != KD_SPIN_RES_NATIVE_READY &&
		!memcmp(kd_exec_frame_regs(parent), &kd_readmit.parent_regs,
			sizeof(parent->regs)) &&
		!memcmp(node->execution->frame.regs_ref, &kd_readmit.node_regs,
			sizeof(*node->execution->frame.regs_ref)) &&
		!memcmp(kd_exec_frame_regs(frame), &kd_readmit.node_regs,
			sizeof(frame->regs));
	kd_readmit.attempts++;
	if (index >= kd_readmit_refusals)
		return false;
	*ret = KD_EXE_NO_RUN;
	return true;
}

static noinline void
kd_spin_selftest_readmit_cancel(const struct kd_exec_frame *frame)
{
	const struct kd_exec_frame *parent = READ_ONCE(kd_readmit.parent);
	unsigned int index;

	if (!parent || frame->outer_lock_addr != kd_readmit.lock ||
	    frame->logical_pid != kd_readmit.pid || frame->executed)
		return;
	index = kd_readmit.attempts - 1;
	if (index >= 2 || kd_readmit.cancelled != index) {
		kd_readmit.unexpected++;
		return;
	}
	kd_readmit.cancelled++;
	kd_readmit.cancel_valid[index] =
		!frame->resume_target &&
		parent->remote_result == KD_EXEC_REMOTE_WAITING &&
		!memcmp(kd_exec_frame_regs(parent), &kd_readmit.parent_regs,
			sizeof(parent->regs)) &&
		!memcmp(kd_exec_frame_regs(frame), &kd_readmit.node_regs,
			sizeof(frame->regs));
}

static noinline void
kd_spin_selftest_readmit_return(const struct kd_exec_frame *parent,
				const struct kd_spin_node *node, int ret)
{
	bool local = kd_readmit_refusals == 2;

	if (!kd_readmit.parent || parent != READ_ONCE(kd_readmit.parent) ||
	    (unsigned long)((struct qspinlock *)node->execution->frame.outer_lock_addr) != kd_readmit.lock ||
	    parent->logical_pid != kd_readmit.pid)
		return;
	kd_readmit.returned++;
	kd_readmit.queue_ret = ret;
	kd_readmit.return_cpu = raw_smp_processor_id();
	kd_readmit.return_owner = (unsigned long)current;
	kd_readmit.return_valid =
		kd_readmit.attempts == 2 &&
		kd_readmit.cancelled == kd_readmit_refusals &&
		(unsigned long)node == kd_readmit.node &&
		parent->control_call.phase == KD_CALL_ENTERED &&
		parent->executed && parent->gsbase == kd_readmit.gs &&
		(unsigned long)parent->logical_task == kd_readmit.task &&
		node->execution->result != KD_SPIN_RES_RETRY && node->execution->result != KD_SPIN_RES_NATIVE_READY &&
		ret == (local ? 2 : 3) && node->completed == !local &&
		parent->remote_result ==
			(local ? KD_EXEC_REMOTE_WAITING : KD_EXEC_REMOTE_DONE);
	if (local)
		kd_readmit.return_valid &=
			kd_spin_debug_owner((void *)kd_readmit.lock) ==
				(unsigned long)current &&
			raw_spin_is_locked((raw_spinlock_t *)kd_readmit.lock) &&
			raw_spin_is_locked(
				(raw_spinlock_t *)kd_readmit.outer) &&
			!memcmp(kd_exec_frame_regs(parent), &kd_readmit.parent_regs,
				sizeof(parent->regs)) &&
			!memcmp(node->execution->frame.regs_ref, &kd_readmit.node_regs,
				sizeof(*node->execution->frame.regs_ref));
}

static noinline void
kd_spin_selftest_readmit_end(const struct kd_exec_frame *frame, int ret)
{
	unsigned int index;

	if (!READ_ONCE(kd_readmit.parent) ||
	    frame->logical_pid != kd_readmit.pid)
		return;
	if (frame->outer_lock_addr == kd_readmit.lock) {
		index = kd_readmit.attempts - 1;
		if (index >= 2) {
			kd_readmit.unexpected++;
			return;
		}
		kd_readmit.ended[index]++;
		kd_readmit.child_ret[index] = ret;
		kd_readmit.child_executed[index] = frame->executed;
	} else if (frame == kd_readmit.parent &&
		   frame->outer_lock_addr == kd_readmit.outer) {
		kd_readmit.finished++;
		kd_readmit.parent_ret = ret;
		kd_readmit.end_valid =
			kd_readmit.returned == 1 && frame->executed &&
			ret == KD_EXE_RUN_TO_UNLOCK &&
			frame->remote_result ==
				(kd_readmit_refusals == 2 &&
						 !kd_readmit.followed ?
					 KD_EXEC_REMOTE_IDLE :
					 KD_EXEC_REMOTE_DONE) &&
			(unsigned long)current == kd_readmit.return_owner &&
			raw_smp_processor_id() == kd_readmit.return_cpu &&
			frame->gsbase == kd_readmit.gs &&
			(unsigned long)frame->logical_task == kd_readmit.task;
	}
}

static void kd_spin_selftest_readmit_report(void)
{
	unsigned int i;
	bool valid;

	if (!kd_readmit_refusals)
		return;
	valid = kd_readmit.attempts == 2 &&
		kd_readmit.cancelled == kd_readmit_refusals &&
		!kd_readmit.unexpected && kd_readmit.returned == 1 &&
		kd_readmit.return_valid && kd_readmit.finished == 1 &&
		kd_readmit.end_valid && kd_readmit.followed <= 1 &&
		(!kd_readmit.followed || kd_readmit.follow_valid) &&
		kd_readmit.owner[0] != kd_readmit.owner[1] &&
		kd_readmit.cpu[0] != kd_readmit.cpu[1];
	for (i = 0; i < 2; i++) {
		bool refused = i < kd_readmit_refusals;
		valid &= kd_readmit.initial[i] && kd_readmit.ended[i] == 1 &&
			 kd_readmit.child_executed[i] == !refused &&
			 kd_readmit.child_ret[i] ==
				 (refused ? KD_EXE_NO_RUN :
					    KD_EXE_RUN_TO_UNLOCK) &&
			 kd_readmit.cancel_valid[i] == refused;
		pr_info("kd_readmit attempt: index=%u cpu=%u owner=%lx head=%lx tail=%lx initial=%u cancelled=%u ended=%u executed=%u ret=%d\n",
			i, kd_readmit.cpu[i], kd_readmit.owner[i],
			kd_readmit.head[i], kd_readmit.tail[i],
			kd_readmit.initial[i], kd_readmit.cancel_valid[i],
			kd_readmit.ended[i], kd_readmit.child_executed[i],
			kd_readmit.child_ret[i]);
	}
	if (kd_readmit.followed)
		pr_info("kd_readmit follow: count=%u outer=%lx ip=%lx sp=%lx cpu=%u owner=%lx depth=%u valid=%u\n",
			kd_readmit.followed, kd_readmit.follow_outer,
			kd_readmit.follow_ip, kd_readmit.follow_sp,
			kd_readmit.follow_cpu, kd_readmit.follow_owner,
			kd_readmit.follow_depth, kd_readmit.follow_valid);
	pr_info("kd_readmit summary: refusals=%u attempts=%u task=%d entry=%lx ip=%lx sp=%lx lock=%lx outer=%lx node=%lx cancelled=%u returned=%u ret=%d cpu=%u owner=%lx finished=%u end=%d return_valid=%u end_valid=%u unexpected=%u valid=%u\n",
		kd_readmit_refusals, kd_readmit.attempts, kd_readmit.pid,
		kd_readmit.entry, kd_readmit.ip, kd_readmit.sp, kd_readmit.lock,
		kd_readmit.outer, kd_readmit.node, kd_readmit.cancelled,
		kd_readmit.returned, kd_readmit.queue_ret,
		kd_readmit.return_cpu, kd_readmit.return_owner,
		kd_readmit.finished, kd_readmit.parent_ret,
		kd_readmit.return_valid, kd_readmit.end_valid,
		kd_readmit.unexpected, valid);
}
