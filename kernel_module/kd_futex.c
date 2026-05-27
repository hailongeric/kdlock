/*
 * kd_futex.c — futex delegation engine.
 *
 * When a translated critical section executes a futex syscall (wait/wake),
 * the JIT sandbox reports it via KD_EXE_NORMAL.  This file intercepts those
 * futex operations and executes them on behalf of the waiter — waking
 * queued tasks directly rather than trapping to the kernel futex slowpath.
 *
 * The delegation path chains multiple wake operations together via
 * kd_exe_on_call(), building a batch of waiters to wake.
 */
#include <linux/sched.h>
#include <linux/sched/task.h>
#include <linux/sched/task_stack.h>
#include <linux/sched/topology.h>
#include <linux/spinlock.h>
#include <linux/futex.h>
#include <linux/atomic.h>
#include <asm/barrier.h>

#include "kd_lock.h"
#include "kd_futex.h"
#include "kd_int3.h"
#include "exe.h"
#include "utils.h"

/* --- globals shared with kd_lock.c --------------------------------------- */

extern long kd_success_cnt;
extern long kd_total_cnt;
extern long kd_success_wake_cnt;
extern unsigned long kd_wake_rets[];
extern long uaddr_cnt;
extern unsigned long uaddrs[];
extern unsigned long uaddr_cnts[];

/* --- task state helpers --------------------------------------------------- */

const struct futex_q futex_q_init = {
	.key = FUTEX_KEY_INIT,
	.bitset = FUTEX_BITSET_MATCH_ANY,
	.requeue_state = ATOMIC_INIT(Q_REQUEUE_PI_NONE),
};

void __nf_futex_queue(struct futex_q* q, struct futex_hash_bucket* hb,
		      struct task_struct* task)
{
	int prio;
	prio = min(task->normal_prio, MAX_RT_PRIO);
	plist_node_init(&q->list, prio);
	plist_add(&q->list, &hb->chain);
	q->task = task;
}

/* --- debug helpers -------------------------------------------------------- */

void print_regs(struct pt_regs* regs)
{
	KD_PR_INFO("regs: %lx, %lx, %lx, %lx, %lx, %lx, %lx, %lx, "
		   "%lx, %lx, %lx, %lx, %lx, %lx, %lx, %lx, %lx\n",
		   regs->ip, regs->sp, regs->bp, regs->ax, regs->bx,
		   regs->cx, regs->dx, regs->si, regs->di, regs->r8,
		   regs->r9, regs->r10, regs->r11, regs->r12, regs->r13,
		   regs->r14, regs->r15);
}

void add_uaddr(unsigned long u)
{
	int i;
	for (i = 0; i < uaddr_cnt; i++)
		if (uaddrs[i] == u)
			break;
	if (i == 102400)
		return;
	if (i == uaddr_cnt) {
		uaddr_cnt++;
		uaddrs[i] = u;
		uaddr_cnts[i] = 0;
	}
	uaddr_cnts[i]++;
}

void record_ret(int ret)
{
	if (ret >= 0 && ret <= KD_CNT_NUM)
		kd_wake_rets[ret]++;
	else if (ret > KD_CNT_NUM)
		kd_wake_rets[KD_CNT_NUM + 1]++;
}

int check_numa_node(struct futex_q* q, int node)
{
	int q_node;
	q_node = task_node(q->task);
	return (q_node == node) ? 1 : 0;
}

/* --- batch execution: run JIT sandbox for queued waiters ------------------ */

void kd_call_q(struct wake_q_head* wake_q, struct kd_exe_ret* r)
{
	struct wake_q_node* node = wake_q->first;
	struct pt_regs* regs;

	r->ret = -11;
	while (node != WAKE_Q_TAIL) {
		struct task_struct* task;
		task = container_of(node, struct task_struct, wake_q);
		regs = task_pt_regs(task);
		kd_exe_on_call(task, regs, r);
		node = node->next;
	}
}

void kd_call(struct task_struct* task, struct kd_exe_ret* r)
{
	struct pt_regs* regs;
	regs = task_pt_regs(task);
	kd_exe_on_call(task, regs, r);
}

void kd_prefetch_context(struct pt_regs* regs, unsigned long rsp)
{
	int i;
	stac();
	kd_prefetchw(regs);
	kd_prefetchw((char*)regs + 64);
	kd_prefetchw((char*)regs + 128);
	for (i = 0; i < prefetch_up_size; i++)
		kd_prefetchw((char*)rsp + 64 * i);
	for (i = 1; i <= prefetch_down_size; i++)
		kd_prefetchw((char*)rsp - 64 * i);
}

void kd_cldemote_context(struct pt_regs* regs, unsigned long rsp)
{
	stac();
	kd_cldemote(regs);
	kd_cldemote((char*)regs + 64);
	kd_cldemote((char*)regs + 128);
	kd_cldemote((char*)rsp);
	kd_cldemote((char*)rsp - 64);
}

void not_wake_up_q(struct wake_q_head* wake_q)
{
	struct wake_q_node* node = wake_q->first;
	while (node != WAKE_Q_TAIL)
		node = node->next;
}
