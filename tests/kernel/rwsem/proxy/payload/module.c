// SPDX-License-Identifier: GPL-2.0
/* General API mechanism fixture. No application body or MM routing is used. */
#include <linux/bitops.h>
#include <linux/fs.h>
#include <linux/jiffies.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/objtool.h>
#include <linux/sched.h>
#include <linux/uaccess.h>
#include <linux/wait.h>
#include "kd_lock.h"
#include "kd_hotlock.h"
#include "kd_rwsem_api.h"
#include "api.h"

#define PROXY_POLLS 500000000U
static DEFINE_KD_RWSEM(sem);
static DECLARE_WAIT_QUEUE_HEAD(control_wait);
static atomic_t active = ATOMIC_INIT(0), errors = ATOMIC_INIT(0);
/* Address tokens only; each task remains alive through its own ioctl join. */
static unsigned long task[PROXY_ROLES], started, ready, done;
static unsigned long warm_eligible, entry_checked, entry_eligible;
static bool armed, predecessor_release, predecessor_done, holder_release;
static bool reader_held, reader_release;
static u64 prefix, tail_done, own_bodies, warm_ops, write_generation, own_generation;
extern char rwsem_proxy_entry[];
extern bool kd_hotlock_query_mutex(unsigned long address);

static unsigned long owner(void)
{
	return atomic_long_read(&sem.gate.owner) & ~KD_MUTEX_OWNER_FLAGS;
}

/* Every writer uses one lexical public entry and the same downgrade/up_read
 * endpoint. Scalar bounded barriers stay in the generated body. Independent
 * runtime records, not a logical current read in this body, prove execution. */
static __attribute__((noipa)) void write_body(unsigned int role)
{
	unsigned int polls;
	u64 expected;

	kd_down_write(&sem);
	asm volatile(".globl rwsem_proxy_entry\n.set rwsem_proxy_entry, 1b\n\t"
		     ".pushsection .discard.noendbr\n\t"
		     _ASM_PTR " rwsem_proxy_entry\n\t.popsection\n\t"
		     : : : "memory");
	if (atomic_long_read(&sem.readers) ||
	    atomic_long_read(&sem.admission) != -1)
		atomic_inc(&errors);
	if (!READ_ONCE(armed)) {
		WRITE_ONCE(warm_ops, READ_ONCE(warm_ops) + 1);
	} else if (role == PROXY_HOLDER) {
		for (polls = 0; polls < PROXY_POLLS && !READ_ONCE(holder_release); polls++)
			cpu_relax();
		if (!READ_ONCE(holder_release))
			atomic_inc(&errors);
	} else if (role == PROXY_WRITER) {
		if (READ_ONCE(prefix) || READ_ONCE(tail_done) || READ_ONCE(own_bodies) ||
		    (atomic_long_read(&sem.gate.owner) & ~KD_MUTEX_OWNER_FLAGS) !=
		    READ_ONCE(task[PROXY_EXECUTOR]) ||
		    (unsigned long)READ_ONCE(sem.selected_executor) !=
		    READ_ONCE(task[PROXY_EXECUTOR]))
			atomic_inc(&errors);
		WRITE_ONCE(write_generation, READ_ONCE(sem.phase_generation));
		WRITE_ONCE(prefix, READ_ONCE(prefix) + 1);
	} else if (role == PROXY_EXECUTOR) {
		if (READ_ONCE(prefix) != 1 || READ_ONCE(tail_done) != 1 ||
		    READ_ONCE(own_bodies) || !READ_ONCE(reader_release) ||
		    (atomic_long_read(&sem.gate.owner) & ~KD_MUTEX_OWNER_FLAGS) !=
		    READ_ONCE(task[PROXY_EXECUTOR]) ||
		    READ_ONCE(sem.phase_generation) <= READ_ONCE(write_generation))
			atomic_inc(&errors);
		WRITE_ONCE(own_generation, READ_ONCE(sem.phase_generation));
		WRITE_ONCE(own_bodies, READ_ONCE(own_bodies) + 1);
	} else {
		atomic_inc(&errors);
	}
	expected = READ_ONCE(warm_ops);
	kd_downgrade_write(&sem);
	if (READ_ONCE(armed) && role == PROXY_WRITER) {
		/* The ordinary reader enters only after this request has converted
		 * to a read share and the runtime has reopened admission. Its own
		 * share remains after our final release, forcing a fresh writer drain. */
		for (polls = 0; polls < PROXY_POLLS && !READ_ONCE(reader_held); polls++)
			cpu_relax();
		if (!READ_ONCE(reader_held) || READ_ONCE(reader_release) ||
		    READ_ONCE(own_bodies) || atomic_long_read(&sem.readers) != 2)
			atomic_inc(&errors);
		WRITE_ONCE(tail_done, READ_ONCE(tail_done) + 1);
	} else {
		for (polls = 0; polls < 128; polls++)
			cpu_relax();
	}
	if (READ_ONCE(warm_ops) != expected)
		atomic_inc(&errors);
	kd_up_read(&sem);
}

static void hold_predecessor(void)
{
	(kd_down_write)(&sem);
	set_bit(PROXY_PREDECESSOR, &ready);
	if (!wait_event_timeout(control_wait, READ_ONCE(predecessor_release), 10 * HZ))
		atomic_inc(&errors);
	(kd_up_write)(&sem);
	smp_store_release(&predecessor_done, true);
}

static void hold_reader(void)
{
	kd_down_read(&sem);
	WRITE_ONCE(reader_held, true);
	if (!wait_event_timeout(control_wait, READ_ONCE(reader_release), 10 * HZ))
		atomic_inc(&errors);
	kd_up_read(&sem);
}

static long proxy_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	void __user *user = (void __user *)arg;
	struct proxy_run run;
	unsigned int before_preempt, i;
	bool before_irqs;

	(void)file;
	if (cmd == PROXY_RUN || cmd == PROXY_WARMUP) {
		if (copy_from_user(&run, user, sizeof(run)))
			return -EFAULT;
		if (run.role >= PROXY_ROLES || !run.iterations || run.iterations > 200000 ||
		    preempt_count() || irqs_disabled() || cpumask_weight(current->cpus_ptr) != 1 ||
		    (cmd == PROXY_RUN && (!READ_ONCE(armed) || run.iterations != 1 ||
					test_and_set_bit(run.role, &started))) ||
		    (cmd == PROXY_WARMUP && (READ_ONCE(armed) || READ_ONCE(started))))
			return -EINVAL;
		atomic_inc(&active);
		before_preempt = preempt_count();
		before_irqs = irqs_disabled();
		run.returned = run.errors = 0;
		if (cmd == PROXY_WARMUP) {
			for (i = 0; i < run.iterations; i++)
				write_body(run.role);
			if (kd_hotlock_query_mutex((unsigned long)&sem.gate))
				set_bit(run.role, &warm_eligible);
			else
				clear_bit(run.role, &warm_eligible);
		} else {
			WRITE_ONCE(task[run.role], (unsigned long)current);
			if (run.role == PROXY_PREDECESSOR)
				hold_predecessor();
			else if (run.role == PROXY_READER) {
				set_bit(run.role, &ready);
				hold_reader();
			} else {
				bool eligible = kd_hotlock_query_mutex((unsigned long)&sem.gate);
				set_bit(run.role, &ready);
				set_bit(run.role, &entry_checked);
				if (eligible)
					set_bit(run.role, &entry_eligible);
				else
					run.errors++;
				if (eligible)
					write_body(run.role);
			}
		}
		run.returned = run.iterations;
		run.errors += preempt_count() != before_preempt || irqs_disabled() != before_irqs;
		if (run.errors)
			atomic_inc(&errors);
		if (cmd == PROXY_RUN)
			set_bit(run.role, &done);
		atomic_dec(&active);
		return copy_to_user(user, &run, sizeof(run)) ? -EFAULT : 0;
	}
	if (cmd == PROXY_PREPARE)
		return READ_ONCE(started) ? -EBUSY : kd_rwsem_prepare(&sem,
			(unsigned long)rwsem_proxy_entry, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
	if (cmd == PROXY_PREDECESSOR_RELEASE) {
		if (owner() != READ_ONCE(task[PROXY_PREDECESSOR]) ||
		    atomic_read(&sem.gate.delegation_state) != KD_MUTEX_GATE_ACQUIRING)
			return -EAGAIN;
		WRITE_ONCE(predecessor_release, true);
		wake_up_all(&control_wait);
		return 0;
	}
	if (cmd == PROXY_HOLDER_RELEASE) {
		if (owner() != READ_ONCE(task[PROXY_HOLDER]) ||
		    atomic_read(&sem.gate.delegation_state) != KD_MUTEX_GATE_HELD ||
		    kd_mutex_debug_waiter_count(&sem.gate) != 2)
			return -EAGAIN;
		WRITE_ONCE(holder_release, true);
		return 0;
	}
	if (cmd == PROXY_READER_RELEASE) {
		if (!READ_ONCE(reader_held) || !READ_ONCE(tail_done) ||
		    READ_ONCE(own_bodies) || atomic_long_read(&sem.readers) != 1 ||
		    atomic_long_read(&sem.admission) != -1)
			return -EAGAIN;
		WRITE_ONCE(reader_release, true);
		wake_up_all(&control_wait);
		return 0;
	}
	if (cmd == PROXY_ARM) {
		if (atomic_read(&active) || READ_ONCE(started) || !READ_ONCE(warm_ops) ||
		    !kd_rwsem_is_idle(&sem))
			return -EBUSY;
		WRITE_ONCE(armed, true);
		return 0;
	}
	if (cmd == PROXY_DRAIN)
		return atomic_read(&active) || READ_ONCE(done) != (1UL << PROXY_ROLES) - 1 ||
			!kd_rwsem_is_idle(&sem) ? -EBUSY : 0;
	if (cmd == PROXY_SNAPSHOT) {
		struct proxy_snapshot s = {
			.sem = (unsigned long)&sem, .gate = (unsigned long)&sem.gate,
			.entry = (unsigned long)rwsem_proxy_entry,
			.active = atomic_read(&active), .errors = atomic_read(&errors),
			.started = READ_ONCE(started), .ready = READ_ONCE(ready), .done = READ_ONCE(done),
			.armed = READ_ONCE(armed), .predecessor_release = READ_ONCE(predecessor_release),
			.predecessor_done = READ_ONCE(predecessor_done), .holder_release = READ_ONCE(holder_release),
			.reader_held = READ_ONCE(reader_held), .reader_release = READ_ONCE(reader_release),
			.prefix = READ_ONCE(prefix), .tail_done = READ_ONCE(tail_done),
			.own_bodies = READ_ONCE(own_bodies), .warm_ops = READ_ONCE(warm_ops),
			.warm_eligible = READ_ONCE(warm_eligible), .entry_checked = READ_ONCE(entry_checked),
			.entry_eligible = READ_ONCE(entry_eligible), .g_task = READ_ONCE(task[PROXY_HOLDER]),
			.c_task = READ_ONCE(task[PROXY_EXECUTOR]), .w_task = READ_ONCE(task[PROXY_WRITER]),
			.t_task = READ_ONCE(task[PROXY_PREDECESSOR]), .owner = owner(),
			.gate_state = atomic_read(&sem.gate.delegation_state),
			.tail = (unsigned long)READ_ONCE(sem.gate.delegation_tail),
			.waiters = kd_mutex_debug_waiter_count(&sem.gate),
			.readers = atomic_long_read(&sem.readers), .admission = atomic_long_read(&sem.admission),
			.generation = READ_ONCE(sem.phase_generation),
			.write_generation = READ_ONCE(write_generation), .own_generation = READ_ONCE(own_generation),
		};
		return copy_to_user(user, &s, sizeof(s)) ? -EFAULT : 0;
	}
	return -ENOTTY;
}
static const struct file_operations ops = { .owner = THIS_MODULE, .unlocked_ioctl = proxy_ioctl };
static struct miscdevice device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_rwsem_proxy", .fops = &ops, .mode = 0600,
};
static int __init proxy_init(void) { return misc_register(&device); }
static void __exit proxy_exit(void) { misc_deregister(&device); }
module_init(proxy_init);
module_exit(proxy_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("General delegated rwsem downgrade and writer reacquisition fixture");
