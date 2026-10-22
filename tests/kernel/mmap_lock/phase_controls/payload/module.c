// SPDX-License-Identifier: GPL-2.0
/* Explicit scheduler injections for correctness; never loaded for timing. */
#include <linux/completion.h>
#include <linux/cpu.h>
#include <linux/delay.h>
#include <linux/fs.h>
#include <linux/kallsyms.h>
#include <linux/kprobes.h>
#include <linux/kthread.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/mmap_lock.h>
#include <linux/module.h>
#include <linux/sched.h>
#include <linux/sched/mm.h>
#include <linux/sched/task.h>
#include <linux/uaccess.h>
#include "api.h"

#ifndef CONFIG_KD_MMAP_LOCK
#error "Captured kdmm1 integration kernel required"
#endif

static DEFINE_MUTEX(control);
static struct mm_struct *mm, *second;
static struct mm_struct *(*allocate_mm)(void);
static int (*phase_begin)(struct mm_struct *, struct mm_struct *);
static int (*phase_snapshot)(struct phase_result *);
static int (*phase_end)(struct phase_result *);
static struct control_result result;
static struct control_case *active;
static struct task_struct *target, *peer;
static struct completion peer_ready, peer_finished, writer_finished;
static bool peer_go, first_pending, used;
static u64 before_nvcsw, before_nivcsw;
static int writer_result;
static struct kprobe probes[2];

static void check_at(bool good, unsigned int line)
{
	result.checks++;
	if (!good) {
		result.errors++;
		pr_err("kd_phase_controls: check failed at line %u\n", line);
	}
}
#define check(c) check_at(!!(c), __LINE__)

static bool idle(struct mm_struct *object)
{
	struct kd_mmap_rwsem *s = &object->mmap_lock.kd;
	return object->mmap_lock.use_kd && !mmap_lock_is_contended(object) &&
		!kd_mmap_is_locked(&object->mmap_lock) &&
		!atomic_long_read(&s->readers) && !atomic_long_read(&s->admission) &&
		!atomic_long_read(&s->gate.owner) && !atomic_read(&s->gate.osq.tail) &&
		!READ_ONCE(s->gate.wait_head) && !atomic_read(&s->gate.delegation_state) &&
		!READ_ONCE(s->gate.delegation_tail);
}

static bool parked(struct task_struct *task, unsigned int calls)
{
	unsigned long until = jiffies + 5 * HZ;
	do {
		if ((!calls || smp_load_acquire(&active->schedule_calls) >= calls) &&
		    (READ_ONCE(task->__state) & TASK_UNINTERRUPTIBLE) &&
		    !READ_ONCE(task->on_cpu) && !READ_ONCE(task->on_rq))
			return true;
		msleep(1);
	} while (time_before(jiffies, until));
	return false;
}

static int peer_main(void *ignored)
{
	/* Publish readiness only after setting the sleeping state. A wake that
	 * arrives before schedule is still consumed by the acquire predicate. */
	set_current_state(TASK_UNINTERRUPTIBLE);
	complete(&peer_ready);
	while (!smp_load_acquire(&peer_go)) {
		schedule();
		set_current_state(TASK_UNINTERRUPTIBLE);
	}
	__set_current_state(TASK_RUNNING);
	complete(&peer_finished);
	return 0;
}

static int writer_main(void *ignored)
{
	writer_result = mmap_write_lock_killable(mm);
	if (!writer_result)
		mmap_write_unlock(mm);
	complete(&writer_finished);
	return 0;
}

static int inject(struct kprobe *kp, struct pt_regs *regs)
{
	struct control_case *c = READ_ONCE(active);
	if (!c || current != READ_ONCE(target))
		return 0;
	if (kp == &probes[0]) {
		/* schedule+9 is before its prologue. Require the exact phase-loop
		 * return address; kthread startup/teardown schedules are unrelated. */
		if (READ_ONCE(*(unsigned long *)regs->sp) != 0xffffffff811508f8UL)
			return 0;
		if (!c->schedule_calls) {
			before_nvcsw = current->nvcsw;
			before_nivcsw = current->nivcsw;
			first_pending = true;
			if (c->mode != 1) {
				/* wake_up_process is atomic-safe here. The production
				 * predicate and wait entry are deliberately left intact. */
				c->self_wake = wake_up_process(current);
				c->injected = 1;
				if (c->mode == 3) {
					smp_store_release(&peer_go, true);
					c->peer_wake = wake_up_process(peer);
				}
			}
		}
		smp_store_release(&c->schedule_calls, c->schedule_calls + 1);
	} else if (first_pending) {
		c->voluntary = current->nvcsw - before_nvcsw;
		c->involuntary = current->nivcsw - before_nivcsw;
		c->first_return++;
		first_pending = false;
	}
	return 0;
}

static void observed(struct kprobe *kp, struct pt_regs *regs, unsigned long flags) { }

static void join_workers(void)
{
	/* The holder has released before joining. No timeout or observation count
	 * is accepted as drain, and no signal is used to stop a stuck acquisition. */
	if (target) {
		check(!kthread_stop(target));
		check(completion_done(&writer_finished) && !writer_result);
		active->joined++;
		put_task_struct(target);
		target = NULL;
	}
	if (peer) {
		smp_store_release(&peer_go, true);
		wake_up_process(peer);
		check(!kthread_stop(peer));
		active->peer_done = completion_done(&peer_finished);
		check(active->peer_done);
		put_task_struct(peer);
		peer = NULL;
	}
}

static int scenario(unsigned int mode)
{
	struct phase_result before, after;
	struct control_case *c = &result.cases[mode - 1];
	unsigned int i;
	int ret = 0;
	active = c;
	c->mode = mode; c->mm = (unsigned long)mm;
	c->sem = (unsigned long)&mm->mmap_lock.kd;
	first_pending = peer_go = false;
	init_completion(&peer_ready); init_completion(&peer_finished);
	init_completion(&writer_finished);
	check(!phase_snapshot(&before));
	mmap_write_lock(mm);
	if (mode == 3) {
		peer = kthread_create(peer_main, NULL, "kd_phase_peer");
		if (IS_ERR(peer)) { ret = PTR_ERR(peer); peer = NULL; goto release; }
		get_task_struct(peer);
		kthread_bind(peer, 0);
		sched_set_fifo(peer); /* Only this short-lived fixture peer: priority 50. */
		c->peer_task = (unsigned long)peer;
		wake_up_process(peer);
		if (!wait_for_completion_timeout(&peer_ready, 5 * HZ) || !parked(peer, 0)) {
			check(false); goto release;
		}
	}
	target = kthread_create(writer_main, NULL, "kd_phase_writer");
	if (IS_ERR(target)) { ret = PTR_ERR(target); target = NULL; goto release; }
	get_task_struct(target);
	kthread_bind(target, 0);
	if (mode != 1)
		sched_set_fifo_low(target); /* Fixture-only priority 1; no global policy. */
	c->task = (unsigned long)target; c->tid = task_pid_nr(target);
	wake_up_process(target);
	if (mode == 1) {
		bool blocked = parked(target, 1);
		c->blocked_before_wake = blocked;
		check(blocked);
		if (!blocked) goto release;
		/* Deliberately unrelated to queue callbacks; admission stays owned. */
		c->self_wake = wake_up_process(target);
		c->injected = 1;
	}
	check(parked(target, 2));
	check(!completion_done(&writer_finished));
	check(atomic_long_read(&mm->mmap_lock.kd.admission) == -1);
	check(waitqueue_active(&mm->mmap_lock.kd.phase_wait));
release:
	mmap_write_unlock(mm);
	join_workers();
	check(!phase_snapshot(&after));
	check(!after.active && !after.errors && !after.missed && !after.count[PH_errors]);
	for (i = 0; i < PH_COUNT; i++) c->count[i] = after.count[i] - before.count[i];
	check(c->count[PH_entries] == 1 && c->count[PH_epilogues] == 1 &&
	      c->count[PH_success] == 1 && !c->count[PH_eintr]);
	check(c->injected == 1 && c->self_wake == 1 && c->first_return == 1 && c->joined == 1);
	check(c->count[PH_phase_blocked_return] >= 1);
	if (mode == 1) {
		check(c->blocked_before_wake && c->voluntary >= 1);
		check(c->count[PH_phase_after_block_fail] >= 1 && c->count[PH_phase_blocked_return] >= 2);
	} else if (mode == 2) {
		check(!c->voluntary && !c->involuntary && c->count[PH_phase_no_switch] >= 1);
	} else {
		check(!c->voluntary && c->involuntary >= 1 && c->peer_wake == 1 && c->peer_done);
		check(c->count[PH_phase_runnable_return] >= 1 && c->count[PH_phase_runnable_out] >= 1);
	}
	check(idle(mm) && atomic_read(&mm->mm_count) == 2);
	result.scenarios++;
	active = NULL;
	return ret;
}

static long run(void __user *user)
{
	struct phase_result final;
	unsigned int i;
	int ret = 0;
	bool armed = false;
	if (!mutex_trylock(&control)) return -EBUSY;
	if (used || !cpu_online(0)) { ret = -EBUSY; goto out; }
	used = true; result.abi = 1;
	mm = allocate_mm(); second = allocate_mm();
	if (!mm || !second) { ret = -ENOMEM; goto cleanup; }
	if (!idle(mm) || !idle(second)) { ret = -EINVAL; goto cleanup; }
	ret = phase_begin(mm, second);
	if (ret) goto cleanup;
	armed = true;
	for (i = 1; i <= 3 && !ret && !result.errors; i++) ret = scenario(i);
cleanup:
	if (armed) {
		check(!phase_end(&final));
		check(!final.active && !final.errors && !final.missed && !final.count[PH_errors]);
	}
	for (i = 0; i < ARRAY_SIZE(probes); i++) result.missed += probes[i].nmissed;
	check(!result.missed);
	result.idle = (!mm || (idle(mm) && atomic_read(&mm->mm_count) == 1)) &&
		(!second || (idle(second) && atomic_read(&second->mm_count) == 1)) && !target && !peer;
	check(result.idle);
	if (result.idle) {
		if (mm) mmput(mm);
		if (second) mmput(second);
		mm = second = NULL;
	} else __module_get(THIS_MODULE); /* Retain failed ownership until diagnosed. */
	if (!ret && copy_to_user(user, &result, sizeof(result))) ret = -EFAULT;
out:
	(mutex_unlock)(&control);
	return ret;
}

static long control_ioctl(struct file *f, unsigned int cmd, unsigned long arg)
{
	return cmd == CONTROL_RUN ? run((void __user *)arg) : -ENOTTY;
}
static const struct file_operations ops = {
	.owner = THIS_MODULE, .unlocked_ioctl = control_ioctl, .llseek = no_llseek,
};
static struct miscdevice device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_phase_controls", .fops = &ops, .mode = 0600,
};

static int __init controls_init(void)
{
	unsigned int i;
	int ret;
	/* These sites do not overlap the unchanged observer's breakpoints. */
	unsigned long addresses[] = { 0xffffffff81ee6da9UL, 0xffffffff811508fdUL };
	unsigned char bytes[][3] = { {0x55}, {0x4c, 0x89, 0xe6} };
	unsigned int sizes[] = { 1, 3 };
	if (kallsyms_lookup_name("schedule") != addresses[0] - 9 ||
	    kallsyms_lookup_name("kd_mmap_down_write_killable") != addresses[1] - 0x7d)
		return -ESTALE;
	for (i = 0; i < ARRAY_SIZE(probes); i++)
		if (memcmp((void *)addresses[i], bytes[i], sizes[i])) return -ESTALE;
	allocate_mm = (void *)kallsyms_lookup_name("mm_alloc");
	phase_begin = symbol_get(kd_phase_begin);
	phase_snapshot = symbol_get(kd_phase_snapshot);
	phase_end = symbol_get(kd_phase_end);
	if (!allocate_mm || !phase_begin || !phase_snapshot || !phase_end) {
		ret = -ENOENT; goto put;
	}
	for (i = 0; i < ARRAY_SIZE(probes); i++) {
		probes[i].addr = (void *)addresses[i];
		probes[i].pre_handler = inject; probes[i].post_handler = observed;
		ret = register_kprobe(&probes[i]);
		if (ret) goto unregister;
	}
	ret = misc_register(&device);
	if (!ret) return 0;
unregister:
	while (i--) unregister_kprobe(&probes[i]);
put:
	if (phase_end) symbol_put(kd_phase_end);
	if (phase_snapshot) symbol_put(kd_phase_snapshot);
	if (phase_begin) symbol_put(kd_phase_begin);
	return ret;
}

static void __exit controls_exit(void)
{
	unsigned int i;
	misc_deregister(&device);
	for (i = 0; i < ARRAY_SIZE(probes); i++) unregister_kprobe(&probes[i]);
	symbol_put(kd_phase_end); symbol_put(kd_phase_snapshot); symbol_put(kd_phase_begin);
}
module_init(controls_init);
module_exit(controls_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Deterministic schedule-path controls for the unchanged mmap phase observer");
