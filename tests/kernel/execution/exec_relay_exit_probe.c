// SPDX-License-Identifier: GPL-2.0
/* Included only by kd_exec.c in SELFTEST builds. Observe waiter TID exit at a
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
	"selftest-only: select one outer lock for waiter TID exit observation");

static bool kd_relay_exit_after_ack;
module_param_named(spin_selftest_exit_after_ack, kd_relay_exit_after_ack, bool,
		   0444);
MODULE_PARM_DESC(
	spin_selftest_exit_after_ack,
	"selftest-only: observe an owned remote child only after its native ACK");

static atomic_t kd_relay_exit_claimed = ATOMIC_INIT(0);
static struct {
	struct kd_exec_frame *frame;
	struct kd_exec_frame expected;
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
	kd_relay_exit.expected = *frame;
	kd_relay_exit.cpu = raw_smp_processor_id();
	kd_relay_exit.preempt = preempt_count();
	kd_relay_exit.irq = irqs_disabled();
	kd_relay_exit.after_ack = after_ack;
	kd_relay_exit.valid =
		alive && !frame->parent && frame->executed &&
		kd_exec_current_frame() == frame &&
		!frame->native_request && !frame->remote_request &&
		kd_relay_exit.preempt && !kd_relay_exit.irq;
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
	pr_info("%s arm: task=%d cpu=%u owner=%lx outer=%lx entry=%lx ip=%lx sp=%lx remaining=%u alive=%u valid=%u\n",
		after_ack ? "kd_child_exit" : "kd_relay_exit",
		frame->logical_pid, kd_relay_exit.cpu, (unsigned long)current,
		frame->outer_lock_addr, frame->entry_ip, frame->regs.ip,
		frame->regs.sp, remaining, alive, kd_relay_exit.valid);
}

static void kd_exec_selftest_relay_release(struct kd_exec_frame *frame)
{
	unsigned long deadline = jiffies + 5 * HZ;
	bool detached = false, packet, context;

	packet = !memcmp(frame, &kd_relay_exit.expected, sizeof(*frame));
	if (kd_relay_exit.valid && packet &&
	    kd_exec_frame_can_complete(frame)) {
		do {
			rcu_read_lock();
			detached = !pid_task(kd_relay_exit.pid, PIDTYPE_PID);
			rcu_read_unlock();
			if (detached)
				break;
			cpu_relax();
		} while (time_before(jiffies, deadline));
	}
	packet &= !memcmp(frame, &kd_relay_exit.expected, sizeof(*frame));
	context = kd_exec_current_frame() == frame &&
		  raw_smp_processor_id() == kd_relay_exit.cpu &&
		  preempt_count() == kd_relay_exit.preempt &&
		  irqs_disabled() == kd_relay_exit.irq;
	/* Detachment is not a claim that the task allocation's RCU reclamation
	 * completed. Never dereference logical_task or its old stack after exit.
	 * A timeout releases the test hold too, but the evidence oracle must fail.
	 */
	put_pid(kd_relay_exit.pid);
	kd_relay_exit.pid = NULL;
	kd_relay_exit.frame = NULL;
	pr_info("%s release: task=%d cpu=%u owner=%lx outer=%lx entry=%lx ip=%lx sp=%lx detached=%u packet=%u context=%u valid=%u\n",
		kd_relay_exit.after_ack ? "kd_child_exit" : "kd_relay_exit",
		frame->logical_pid, raw_smp_processor_id(),
		(unsigned long)current, frame->outer_lock_addr, frame->entry_ip,
		frame->regs.ip, frame->regs.sp, detached, packet, context,
		kd_relay_exit.valid && detached && packet && context);
}

static void kd_exec_selftest_relay_finish(struct kd_exec_frame *frame)
{
	if (frame != READ_ONCE(kd_relay_exit.frame) || kd_relay_exit.after_ack)
		return;
	/* Only the no-lock root can wait before native_finish publishes its ACK.
	 * A child may publish DONE meanwhile; no other root packet field changes.
	 * The owned-child variant must leave its PID observation armed until pop.
	 */
	kd_relay_exit.expected.remote_result = KD_EXEC_REMOTE_DONE;
	kd_exec_selftest_relay_release(frame);
}

static void kd_exec_selftest_relay_pop(struct kd_exec_frame *frame)
{
	if (frame != READ_ONCE(kd_relay_exit.frame) || !kd_relay_exit.after_ack)
		return;
	/* native_wait has published the B ACK and cleared its parent/routing, so
	 * A's owner can finish independently while this physical B batch pauses.
	 * Keep the real frame/source lease until pop; never pin the task, touch its
	 * old stack, change a queue, or allow the second child ahead of this hold.
	 */
	kd_relay_exit.valid &=
		kd_exec_frame_state(frame) == KD_EXEC_FRAME_COMPLETE &&
		kd_exec_frame_can_complete(frame) && !frame->resume_target &&
		!frame->remote_request && !frame->native_request &&
		list_empty(&frame->native_link) &&
		!memcmp(&frame->regs, &kd_relay_exit.expected.regs,
			sizeof(frame->regs));
	/* Unlock/completion legitimately changed the ledger since arm. Snapshot
	 * that terminal frame now, then require every byte to survive the wait.
	 */
	kd_relay_exit.expected = *frame;
	kd_exec_selftest_relay_release(frame);
}
