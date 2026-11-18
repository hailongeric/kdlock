// SPDX-License-Identifier: GPL-2.0
/*
 * Diagnostic: print the addresses of the locks a locktorture run contends
 * on, so that lock words sampled by perf can be named: the pi_lock of every
 * locktorture task and the run queue lock of every CPU (struct rq starts
 * with its lock). The module never stays loaded.
 */
#include <linux/module.h>
#include <linux/sched.h>
#include <linux/sched/signal.h>
#include <linux/percpu.h>
#include <linux/string.h>

static unsigned long rq_addr;
module_param(rq_addr, ulong, 0);

static int __init kd_addrs_init(void)
{
	struct task_struct *g, *p;
	int cpu;

	rcu_read_lock();
	for_each_process_thread(g, p)
		if (!strncmp(p->comm, "lock_torture", 12))
			pr_info("kd_addrs: task %d %s pi_lock %px\n",
				p->pid, p->comm, &p->pi_lock);
	rcu_read_unlock();
	if (rq_addr)
		for_each_possible_cpu(cpu)
			pr_info("kd_addrs: rq %d %lx\n", cpu,
				rq_addr + per_cpu_offset(cpu));
	return -EAGAIN;
}
module_init(kd_addrs_init);
MODULE_LICENSE("GPL");
