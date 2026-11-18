// SPDX-License-Identifier: GPL-2.0
/*
 * Diagnostic: print the mmap lock state of every process whose name
 * starts with comm= (default "httpd"): the rwsem count, the queue mutex
 * word and owner, whether tasks are parked on it, and the state of each
 * thread. Read without locks, so a snapshot. The module never stays loaded.
 */
#include <linux/module.h>
#include <linux/sched.h>
#include <linux/sched/signal.h>
#include <linux/sched/mm.h>
#include <linux/mm_types.h>
#include <linux/string.h>
#include <kdlock/kd_types.h>

static char *comm = "httpd";
module_param(comm, charp, 0);

static int __init kd_mmdump_init(void)
{
	struct task_struct *g, *t;

	rcu_read_lock();
	for_each_process(g) {
		struct mm_struct *mm = g->mm;
		struct kd_rwsem *s;
		struct task_struct *o;

		if (strncmp(g->comm, comm, strlen(comm)) || !mm)
			continue;
		s = &mm->mmap_lock.kd;
		o = READ_ONCE(s->m.owner);
		pr_info("kd_mmdump: pid %d mm %px count %#lx m.q %#x wait_lock %#x owner %d(%s) parked %d users %d\n",
			g->pid, mm, atomic_long_read(&s->count), atomic_read(&s->m.q.val),
			atomic_read(&s->m.wait_lock.val), o ? o->pid : 0, o ? o->comm : "-",
			!list_empty(&s->m.waiters), atomic_read(&mm->mm_users));
		for_each_thread(g, t)
			pr_info("kd_mmdump:   tid %d state %#x flags %#x on_cpu %d\n",
				t->pid, READ_ONCE(t->__state), t->flags, READ_ONCE(t->on_cpu));
	}
	rcu_read_unlock();
	return -EAGAIN;
}
module_init(kd_mmdump_init);
MODULE_LICENSE("GPL");
