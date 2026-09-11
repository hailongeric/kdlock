// SPDX-License-Identifier: GPL-2.0
/* Included only by kd_exec.c in SELFTEST builds. Delay one genuine no-lock
 * root relay until its waiter TID detaches; never fabricate a frame or ACK.
 */
#include <linux/jiffies.h>
#include <linux/moduleparam.h>
#include <linux/pid.h>
#include <linux/rcupdate.h>

static unsigned long kd_relay_exit_lock;
module_param_named(spin_selftest_exit_lock, kd_relay_exit_lock, ulong, 0644);
MODULE_PARM_DESC(
	spin_selftest_exit_lock,
	"selftest-only: delay one no-lock root relay until waiter TID exit");

static atomic_t kd_relay_exit_claimed = ATOMIC_INIT(0);
static struct {
	struct kd_exec_frame *frame;
	struct kd_exec_frame expected;
	struct pid *pid;
	unsigned int cpu, preempt;
	bool irq, valid;
} kd_relay_exit;

static void kd_exec_selftest_relay_arm(struct kd_exec_frame *frame,
				       unsigned int remaining)
{
	bool alive;

	if (frame->outer_lock_addr != READ_ONCE(kd_relay_exit_lock) ||
	    frame->mutex_backend || frame->resume_target ||
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
	kd_relay_exit.valid =
		alive && !remaining && !frame->parent && frame->executed &&
		kd_exec_current_frame() == frame &&
		kd_exec_frame_locks_released(frame) &&
		list_empty(&frame->native_link) && !frame->native_request &&
		!frame->remote_request &&
		frame->control_call.phase == KD_CALL_COMPLETE &&
		frame->remote_result == KD_EXEC_REMOTE_NATIVE &&
		kd_relay_exit.preempt && !kd_relay_exit.irq;
	kd_relay_exit.frame = frame;
	pr_info("kd_relay_exit arm: task=%d cpu=%u owner=%lx outer=%lx entry=%lx ip=%lx sp=%lx remaining=%u alive=%u valid=%u\n",
		frame->logical_pid, kd_relay_exit.cpu, (unsigned long)current,
		frame->outer_lock_addr, frame->entry_ip, frame->regs.ip,
		frame->regs.sp, remaining, alive, kd_relay_exit.valid);
}

static void kd_exec_selftest_relay_finish(struct kd_exec_frame *frame)
{
	unsigned long deadline = jiffies + 5 * HZ;
	bool detached = false, packet, context;

	if (frame != READ_ONCE(kd_relay_exit.frame))
		return;
	/* The child may publish DONE while the root waits, but nothing else may
	 * rewrite its packet or ledger. Only adjust the private expected snapshot.
	 * No owned locks/mailboxes remain here; delaying an owner would deadlock
	 * the final ACK needed for the original waiter to exit normally.
	 */
	kd_relay_exit.expected.remote_result = KD_EXEC_REMOTE_DONE;
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
	pr_info("kd_relay_exit release: task=%d cpu=%u owner=%lx outer=%lx entry=%lx ip=%lx sp=%lx detached=%u packet=%u context=%u valid=%u\n",
		frame->logical_pid, raw_smp_processor_id(),
		(unsigned long)current, frame->outer_lock_addr, frame->entry_ip,
		frame->regs.ip, frame->regs.sp, detached, packet, context,
		kd_relay_exit.valid && detached && packet && context);
}
