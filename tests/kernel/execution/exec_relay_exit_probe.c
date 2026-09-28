// SPDX-License-Identifier: GPL-2.0
/* Included only by kd_exec.c in SELFTEST builds. Observe retirement before final return at a
 * genuine no-lock relay or an ACK-drained child pop; never fabricate an ACK.
 */
#include <linux/jiffies.h>
#include <linux/moduleparam.h>
#include <linux/pid.h>
#include <linux/rcupdate.h>

static unsigned long kd_relay_exit_lock;
module_param_named(spin_selftest_exit_lock, kd_relay_exit_lock, ulong, 0644);
MODULE_PARM_DESC(
	spin_selftest_exit_lock,
	"selftest-only: select one outer lock for retirement-before-return observation");

static bool kd_relay_exit_after_ack;
module_param_named(spin_selftest_exit_after_ack, kd_relay_exit_after_ack, bool,
		   0444);
MODULE_PARM_DESC(
	spin_selftest_exit_after_ack,
	"selftest-only: observe an owned remote child only after its native ACK");

static atomic_t kd_relay_exit_claimed = ATOMIC_INIT(0);
static struct {
	struct kd_exec_frame *frame;
	int logical_pid;
	struct kd_regs expected_regs;
	struct pid *pid;
	unsigned int cpu, preempt;
	bool irq, valid, after_ack;
} kd_relay_exit;

static void kd_exec_selftest_relay_arm(struct kd_exec_frame *frame,
				       unsigned int remaining)
{
	bool after_ack = READ_ONCE(kd_relay_exit_after_ack);
	bool alive;

	if (frame->outer_lock_addr != READ_ONCE(kd_relay_exit_lock) ||
	    frame->mutex_backend || !!frame->resume_target != after_ack ||
	    atomic_cmpxchg(&kd_relay_exit_claimed, 0, 1))
		return;

	/* native_begin precedes the root's queue-slot publication. Its waiter is
	 * still blocked here, so capture only a PID identity ref, not a task ref
	 * that would hide the lifetime boundary or permit PID-reuse false passes.
	 */
	kd_relay_exit.pid = get_task_pid(frame->logical_task, PIDTYPE_PID);
	rcu_read_lock();
	alive = pid_task(kd_relay_exit.pid, PIDTYPE_PID) == frame->logical_task;
	rcu_read_unlock();
	kd_relay_exit.logical_pid = frame->logical_pid;
	kd_relay_exit.expected_regs = *kd_exec_frame_regs(frame);
	kd_relay_exit.cpu = raw_smp_processor_id();
	kd_relay_exit.preempt = preempt_count();
	kd_relay_exit.irq = irqs_disabled();
	kd_relay_exit.after_ack = after_ack;
	/* Stackless spin combiners retain the queue's IRQ mask. Either incoming
	 * state is admissible here; release must preserve the captured state,
	 * CPU and preemption pin until retirement before the waiter returns. */
	kd_relay_exit.valid =
		alive && !frame->parent && frame->executed &&
		kd_exec_current_frame() == frame &&
		!frame->native_request && !frame->remote_request &&
		kd_relay_exit.preempt;
	if (after_ack)
		kd_relay_exit.valid &=
			remaining == 1 && frame->outer_lock_index > 0 &&
			!frame->outer_unlock_seen &&
			!list_empty(&frame->native_link) &&
			frame->control_call.phase == KD_CALL_NONE &&
			frame->remote_result == KD_EXEC_REMOTE_IDLE;
	else
		kd_relay_exit.valid &=
			!remaining && kd_exec_frame_locks_released(frame) &&
			list_empty(&frame->native_link) &&
			frame->control_call.phase == KD_CALL_COMPLETE &&
			frame->remote_result == KD_EXEC_REMOTE_NATIVE;
	kd_relay_exit.frame = frame;
	pr_info("%s arm: task=%d cpu=%u owner=%lx outer=%lx entry=%lx ip=%lx sp=%lx remaining=%u alive=%u valid=%u preempt=%u irq=%u\n",
		after_ack ? "kd_child_exit" : "kd_relay_exit",
		frame->logical_pid, kd_relay_exit.cpu, (unsigned long)current,
		frame->outer_lock_addr, frame->entry_ip, kd_exec_frame_regs(frame)->ip,
		kd_exec_frame_regs(frame)->sp, remaining, alive, kd_relay_exit.valid,
		kd_relay_exit.preempt, kd_relay_exit.irq);
}

/* Native ACK is not retirement. The logical task must still be present at
 * pop; neither an empty relay nor a delayed child can outlive final return. */
static void kd_exec_selftest_relay_finish(struct kd_exec_frame *frame)
{
	if (frame != READ_ONCE(kd_relay_exit.frame) || kd_relay_exit.after_ack)
		return;
	kd_relay_exit.valid &= kd_exec_frame_can_complete(frame);
}

static void kd_exec_selftest_relay_pop(struct kd_exec_frame *frame)
{
	bool alive;

	if (frame != READ_ONCE(kd_relay_exit.frame))
		return;
	rcu_read_lock();
	alive = pid_task(kd_relay_exit.pid, PIDTYPE_PID) == frame->logical_task;
	rcu_read_unlock();
	kd_relay_exit.valid &= alive &&
		kd_exec_frame_state(frame) == KD_EXEC_FRAME_COMPLETE &&
		kd_exec_frame_can_complete(frame) && !frame->resume_target &&
		!frame->remote_request && !frame->native_request &&
		list_empty(&frame->native_link) &&
		!memcmp(kd_exec_frame_regs(frame), &kd_relay_exit.expected_regs,
			sizeof(frame->regs)) &&
		kd_exec_current_frame() == frame &&
		raw_smp_processor_id() == kd_relay_exit.cpu &&
		preempt_count() == kd_relay_exit.preempt &&
		irqs_disabled() == kd_relay_exit.irq;
}

/* This observer runs before notification, while storage is still reserved.
 * Validation must reject the retired frame; no task or packet is read here. */
static void kd_exec_selftest_relay_retired(struct kd_exec_frame *frame)
{
	bool rejected;

	if (frame != READ_ONCE(kd_relay_exit.frame))
		return;
	rejected = !kd_exec_frame_validate(frame);
	put_pid(kd_relay_exit.pid);
	kd_relay_exit.pid = NULL;
	kd_relay_exit.frame = NULL;
	pr_info("kd_spin retirement: task=%d child=%u retired=%u valid=%u\n",
		kd_relay_exit.logical_pid, kd_relay_exit.after_ack,
		rejected, kd_relay_exit.valid && rejected);
}
