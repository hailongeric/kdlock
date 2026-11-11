// SPDX-License-Identifier: GPL-2.0
/*
 * kdlock core: waiting, combining sessions and execution of delegated
 * critical sections. Family files (spinlock, rwlock, mutex, rwsem) supply
 * only their grant rules through struct kd_family.
 */
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/percpu.h>
#include <linux/sched.h>
#include <linux/sched/task_stack.h>
#include <linux/prefetch.h>
#include <linux/gfp.h>
#include <linux/mm.h>
#include <linux/random.h>
#include <linux/topology.h>
#include <linux/moduleparam.h>
#include <linux/bottom_half.h>
#include <linux/hardirq.h>
#include <asm/processor.h>
#include <asm/processor-flags.h>
#include <asm/current.h>
#include <linux/stackprotector.h>
#include <asm/stackprotector.h>
#include "kd_internal.h"

/* busy starts set: no CPU publishes before kd_core_init() gave it a wait stack. */
DEFINE_PER_CPU_ALIGNED(struct kd_cpu, kd_cpu) = { .busy = 1 };
EXPORT_PER_CPU_SYMBOL_GPL(kd_cpu);

DEFINE_STATIC_KEY_FALSE(kd_delegation);

/* Most waiters one session serves before the combiner runs its own section. */
unsigned int kd_batch __read_mostly = 1024;
core_param(kd_batch, kd_batch, uint, 0644);


/* Serve waiters of the combiner's NUMA node first (see kd_session()). */
bool kd_numa __read_mostly = true;
core_param(kd_numa, kd_numa, bool, 0644);

#define KD_WAIT_STACK_ORDER	2	/* 16 KiB; interrupts taken while waiting land here */
#define KD_EXEC_PIN		32	/* extra preempt count while executing a section */
#define KD_OWNER_POLL		1024	/* queued sleepable waiter: owner check interval */
#define KD_HANDOFF_POLL		16	/* sleepable session: handoff check interval, in waiters */

#define KD_CHECK(type, member, off) \
	static_assert(offsetof(type, member) == (off))

KD_CHECK(struct kd_regs, rax, KD_R_rax);
KD_CHECK(struct kd_regs, rbx, KD_R_rbx);
KD_CHECK(struct kd_regs, rcx, KD_R_rcx);
KD_CHECK(struct kd_regs, rdx, KD_R_rdx);
KD_CHECK(struct kd_regs, rsi, KD_R_rsi);
KD_CHECK(struct kd_regs, rdi, KD_R_rdi);
KD_CHECK(struct kd_regs, rbp, KD_R_rbp);
KD_CHECK(struct kd_regs, rsp, KD_R_rsp);
KD_CHECK(struct kd_regs, r8, KD_R_r8);
KD_CHECK(struct kd_regs, r9, KD_R_r9);
KD_CHECK(struct kd_regs, r10, KD_R_r10);
KD_CHECK(struct kd_regs, r11, KD_R_r11);
KD_CHECK(struct kd_regs, r12, KD_R_r12);
KD_CHECK(struct kd_regs, r13, KD_R_r13);
KD_CHECK(struct kd_regs, r14, KD_R_r14);
KD_CHECK(struct kd_regs, r15, KD_R_r15);
KD_CHECK(struct kd_regs, rip, KD_R_rip);
KD_CHECK(struct kd_regs, rflags, KD_R_rflags);
static_assert(sizeof(struct kd_regs) == KD_R_SIZE);
KD_CHECK(struct kd_cpu, task, KD_CPU_task);
KD_CHECK(struct kd_cpu, canary, KD_CPU_canary);
KD_CHECK(struct kd_cpu, stack_top, KD_CPU_stack_top);
KD_CHECK(struct kd_cpu, root, KD_CPU_root);
KD_CHECK(struct kd_cpu, cur, KD_CPU_cur);
KD_CHECK(struct kd_cpu, host_rsp, KD_CPU_host_rsp);
KD_CHECK(struct kd_cpu, tmp, KD_CPU_tmp);
KD_CHECK(struct kd_cpu, exit_ip, KD_CPU_exit_ip);
KD_CHECK(struct kd_cpu, resume, KD_CPU_resume);
KD_CHECK(struct kd_cpu, aux, KD_CPU_aux);
KD_CHECK(struct kd_cpu, exit_code, KD_CPU_exit_code);
KD_CHECK(struct kd_cpu, busy, KD_CPU_busy);
KD_CHECK(struct kd_cpu, wait_stack, KD_CPU_wait_stack);
KD_CHECK(struct kd_cpu, regs, KD_CPU_regs);
KD_CHECK(struct kd_mutex, owner, KD_MUTEX_owner);
static_assert(KD_ASM_SOFTIRQ_LOCK_OFFSET == SOFTIRQ_LOCK_OFFSET);
static_assert(KD_ASM_RW_WLOCKED == KD_RW_WLOCKED);
static_assert(KD_ASM_RWSEM_WLOCKED == KD_RWSEM_WLOCKED);
static_assert(sizeof(struct kd_spinlock) == 4);
static_assert(sizeof(struct kd_rwlock) == 8);
static_assert(sizeof(struct kd_mutex) == 32);
static_assert(sizeof(struct kd_rwsem) == 40);
static_assert(KD_ASM_X_NESTED == KD_X_NESTED);
static_assert(KD_ASM_OP_NEST_SPIN == KD_OP_NEST_SPIN);
static_assert(KD_ASM_OP_NEST_WRITE == KD_OP_NEST_WRITE);
static_assert(KD_MAX_ROOTS <= 8);	/* kd_regs.released is one byte */
static_assert(KD_MAX_NODES == 4);	/* two index bits in the tail encoding */

/* Called from the stubs on the caller's own stack to drop the internal pin. */
noinline void kd_unpin(void)
{
	preempt_enable();
}

/* ---- execution of one delegated section ---------------------------------- */

/*
 * Logical effects of a release that is not physically performed because a
 * combiner keeps the lock for its session. What remains are the side
 * effects the origin's release call would have had on the origin's own
 * context.
 */
static void kd_apply_unlock(struct kd_regs *r, unsigned int op)
{
	switch (op) {
	case KD_OP_UNLOCK:
		r->pc_delta -= 1;
		break;
	case KD_OP_UNLOCK_IRQ:
		r->pc_delta -= 1;
		r->rflags |= X86_EFLAGS_IF;
		break;
	case KD_OP_UNLOCK_IRQRESTORE:
		r->pc_delta -= 1;
		r->rflags = (r->rflags & ~X86_EFLAGS_IF) | (r->rsi & X86_EFLAGS_IF);
		break;
	case KD_OP_UNLOCK_BH:
		r->pc_delta -= SOFTIRQ_LOCK_OFFSET;
		break;
	default:
		break;
	}
}

/*
 * A contended lock call inside the section being executed. As in TCLocks,
 * the executor now plays the waiter's part for the inner lock, with the
 * continuation it is executing: it queues a node that points at the same
 * packet. Three things can happen, decided by the inner lock's queue:
 *
 *  - the inner lock's combiner executes the continuation onwards
 *    (KD_WAIT_RESUMED) while this CPU spins on the node;
 *  - this CPU becomes the inner queue head, takes the lock, serves the
 *    inner lock's own waiters as a nested combiner, and continues
 *    (KD_WAIT_LOCAL);
 *  - sleeping families only: waiting would need sleep, which a pinned
 *    executor must not do for a spinning origin (KD_WAIT_SLEEP).
 *
 * A continuation is published again only while it has room for another
 * root; beyond that the executor waits without publishing.
 */
static int kd_nested_acquire(unsigned int op, struct kd_regs *r, void *resume)
{
	void *lock = (void *)r->rdi;
	void *entry = r->nroots < KD_MAX_ROOTS ? resume : NULL;

	switch (op) {
	case KD_OP_NEST_SPIN:
		return kd_spin_nested(lock, r, entry);
	case KD_OP_NEST_WRITE:
		return kd_write_nested(lock, r, entry);
	case KD_OP_MUTEX_LOCK:
		return kd_mutex_nested(lock, r, entry);
	case KD_OP_DOWN_WRITE:
		return kd_down_write_nested(lock, r, entry);
	case KD_OP_DOWN_READ:
		/* Readers are never delegated: uncontended or back to the origin. */
		return kd_down_read_trylock_raw(lock) ? KD_WAIT_LOCAL : KD_WAIT_SLEEP;
	}
	return KD_WAIT_SLEEP;
}

static void kd_report_exit(struct kd_regs *r, unsigned int kind, unsigned long ip,
			   unsigned long aux)
{
	struct kd_site *site = r->site;
	u32 type;
	unsigned long target = 0;

	switch (kind) {
	case KD_X_MISS_CODE:
		type = KD_EV_MISS_CODE;
		break;
	case KD_X_MISS_IND:
		type = KD_EV_MISS_IND;
		target = aux;
		break;
	case KD_X_MISS_RET:
		type = KD_EV_MISS_RET;
		target = *(unsigned long *)r->rsp;
		break;
	default:
		return;		/* frontier, budget, pending acquire: nothing to learn */
	}
	/* Bounded per image so a hot unlearned path cannot flood the ring. */
	if (atomic_add_unless(&site->miss_budget, -1, 0))
		kd_event_push(type, site->rip, ip, target);
}

/*
 * Execute the continuation of waiter @n for lock @root on this CPU.
 *
 * Returns true if this executor still holds @root afterwards: the
 * continuation released it (the release was intercepted, not performed).
 * Returns false if the grant on @root now belongs to the origin, which
 * continues natively from the packet.
 *
 * Nesting. The packet carries the stack of locks it is currently being
 * executed for. This run pushes @root at index `level`. If the
 * continuation queues for an inner lock and that lock's combiner runs it
 * further, the inner run may meet the release of @root; it then sets bit
 * `level` in ->released instead of unlocking, and this run learns about
 * it when its node is resumed. ->stop tells the outer level whether the
 * continuation can go on in generated code (->jit_resume) or must go
 * back to its origin.
 *
 * Context. While generated code runs, this CPU's interrupt flag follows
 * the origin's logical flag (popfq on entry, pushfq on exit) and
 * preemption stays disabled. Preempt-count changes made by the section
 * are measured here and moved to the origin, so both end balanced. A
 * nested session run from here balances itself the same way, so it does
 * not disturb this measurement.
 */
static bool kd_exec_one(void *root, struct kd_node *n, const struct kd_family *f)
{
	struct kd_cpu *kc = this_cpu_ptr(&kd_cpu);
	struct kd_regs *r = n->regs;
	void *code = n->entry;
	void *resume;
	unsigned long flags, ip, aux;
	unsigned int kind, op, level = r->nroots;
	bool done = false, native = true, bh = false;
	int pc0, d, i, ret;
	u32 x;

	local_save_flags(flags);
	/*
	 * A section entered with softirqs disabled may take softirq-safe
	 * locks without the _bh suffix. Give it the same protection here.
	 */
	if (r->bh_off && !softirq_count() && !raw_irqs_disabled_flags(flags)) {
		local_bh_disable();
		bh = true;
	}
	/*
	 * A section may release locks its origin took before it queued, and
	 * the native release decrements this CPU's count. The extra pin keeps
	 * the count from reaching zero, where that release would try to
	 * reschedule the executor in the middle of somebody else's stack.
	 */
	__preempt_count_add(KD_EXEC_PIN);
	pc0 = preempt_count();

	r->roots[level] = root;
	r->nroots = level + 1;
	r->released &= ~BIT(level);
	kc->depth++;

	for (;;) {
		/* Set up every time: a nested session reuses these fields. */
		kc->cur = r;
		kc->canary = r->canary;
		kc->stack_top = r->stack_top;
		kc->root = root;
		kc->anc = level;
		WRITE_ONCE(kc->task, r->task);

		kd_jit_enter(r, code);

		WRITE_ONCE(kc->task, NULL);
		x = kc->exit_code;
		ip = kc->exit_ip;
		resume = (void *)kc->resume;
		aux = kc->aux;
		kind = KD_X_KIND(x);
		op = KD_X_OP(x);

		if (kind == KD_X_UNLOCK && op != KD_OP_DOWNGRADE) {
			/* Release of our root: this level's section is complete. */
			kd_apply_unlock(r, op);
			if (x & KD_X_TAIL) {
				/* Sibling call: the API's ret would pop the caller's address. */
				r->rip = *(unsigned long *)r->rsp;
				r->rsp += 8;
				r->jit_resume = NULL;
			} else {
				r->rip = ip + 5;	/* past the call rel32 */
				r->jit_resume = resume;
			}
			done = true;
			native = false;
			break;
		}

		if (kind == KD_X_UNLOCK_ANC && !(x & KD_X_TAIL) && op != KD_OP_DOWNGRADE) {
			/*
			 * Release of some other lock while outer sessions exist.
			 * An outer root stays physically held by its combiner and
			 * is only marked; anything else is released for real.
			 */
			for (i = level - 1; i >= 0; i--) {
				if (r->roots[i] == (void *)r->rdi)
					break;
			}
			if (i >= 0) {
				r->released |= BIT(i);
				kd_apply_unlock(r, op);
			} else {
				unsigned long now;

				((void (*)(void *, unsigned long))aux)((void *)r->rdi, r->rsi);
				/* The call may have changed IF; the packet must follow. */
				local_save_flags(now);
				r->rflags = (r->rflags & ~X86_EFLAGS_IF) | (now & X86_EFLAGS_IF);
			}
			code = resume;
			continue;
		}

		if ((kind == KD_X_NESTED || kind == KD_X_ACQUIRE) && !(x & KD_X_TAIL)) {
			if (kind == KD_X_ACQUIRE)
				r->rax = 0;	/* what the acquire returns once it succeeds */
			ret = kd_nested_acquire(op, r, resume);
			if (ret == KD_WAIT_LOCAL) {
				kd_stat_inc(kc, KD_STAT_NESTED_LOCAL);
				code = resume;
				continue;
			}
			if (ret == KD_WAIT_RESUMED) {
				/* Another combiner advanced the packet; read its verdict. */
				kd_stat_inc(kc, KD_STAT_NESTED_DELEGATED);
				native = r->stop == KD_STOP_HANDBACK || !r->jit_resume;
				if (r->released & BIT(level)) {
					done = true;
					break;
				}
				if (native)
					break;
				code = r->jit_resume;
				continue;
			}
			/* Not acquired: fall through, the origin repeats the call. */
		}

		/* Handback: the origin executes the instruction at @ip itself. */
		r->rip = ip;
		kd_report_exit(r, kind, ip, aux);
		break;
	}

	kc->cur = NULL;
	kc->root = NULL;
	kc->depth--;
	r->nroots = level;
	r->released &= ~BIT(level);
	r->stop = native ? KD_STOP_HANDBACK : KD_STOP_DONE;
	/*
	 * The owner a mutex records is the task that runs with it: the
	 * combiner during its session, the origin once the grant is handed
	 * back. It is written only on handback, not per section: every queued
	 * waiter polls it to decide whether to keep spinning, so a store per
	 * section would move the lock's cache line to all of them each time.
	 */
	if (native && !done && f && f->set_owner)
		f->set_owner(root, r->task);

	d = preempt_count() - pc0;
	if (d) {
		__preempt_count_sub(d);
		r->pc_delta += d;
		if (native)
			kd_stat_inc(kc, KD_STAT_HANDBACK_PINNED);
	}
	__preempt_count_sub(KD_EXEC_PIN);
	local_irq_restore(flags);
	if (bh)
		local_bh_enable();

	kd_stat_inc(kc, native ? KD_STAT_HANDBACK : KD_STAT_DELEGATED);
	kd_site_account(r->site, !native);
	return done;
}

/*
 * May this CPU, in its current context, execute the section in @r?
 *
 * The executor never enables interrupts it had disabled itself: if it
 * holds interrupt-safe locks, a section that expects interrupts on would
 * open a window for a handler to deadlock on them.
 */
static bool kd_ctx_compatible(const struct kd_regs *r)
{
	return !(irqs_disabled() && (r->rflags & X86_EFLAGS_IF));
}

/*
 * Address of the packet of waiter @n without reading @n: a top-level
 * waiter publishes its own CPU's packet, and its node is the first slot of
 * the same per-CPU structure (slot 0 of nodes[]). For any other
 * waiter the guess is wrong, which only makes a prefetch useless.
 */
static __always_inline struct kd_regs *kd_packet_guess(struct kd_node *n)
{
	return &container_of(n, struct kd_cpu, nodes[0])->regs;
}

/*
 * Combining session. @me is the queue head and holds the full grant on
 * @root. Execute queued waiters' sections until the budget is used up, a
 * waiter that cannot be delegated, or a handback.
 *
 * Returns true if a waiter left with the grant: the caller must reacquire
 * before going on.
 *
 * Per waiter, the order is: claim (sleepable class), execute, unlink from
 * the queue, then publish RESUME. RESUME is the last access to the node
 * and to the packet; the waiter may reuse both immediately afterwards.
 *
 * NUMA order, as in TCLocks: a delegable waiter of another node is not
 * served. It is unlinked, still waiting, onto a private list, and the
 * session goes on with the waiters behind it, so the lock's data and the
 * sections' stacks stay within one node for the whole session. When the
 * session ends the list goes back in front of the queue in its original
 * order. Its first waiter is therefore the next queue head and combines
 * for its own node. A waiter can be passed over once per session it is
 * queued behind, and every session with a nonempty list moves headship to
 * the list, so the delay is bounded by the batch size times the number of
 * nodes ahead of it. Waiters without generated code are never passed
 * over: they end the session, which keeps interrupt-context waiters FIFO.
 *
 * @budget counts waiters served or passed over. The caller shares it
 * between the sessions of one wait so that handbacks cannot extend it.
 *
 * Sessions nest: this function is also reached from kd_exec_one() when the
 * executor becomes head of an inner lock's queue. kd_cpu.depth bounds that
 * recursion; at the limit the head just takes the lock. The passed-over
 * list is local, so nested sessions need no extra state.
 */
static bool kd_session(struct kd_qlock *q, struct kd_node *me, void *root,
		       const struct kd_family *f, bool sleepable,
		       unsigned int *budget)
{
	struct kd_cpu *kc = this_cpu_ptr(&kd_cpu);
	struct kd_node *n, *nn, *first = NULL, *last = NULL;
	bool numa = READ_ONCE(kd_numa);
	bool handed = false, ran = false;
	struct kd_regs *guess;

	if (!static_branch_likely(&kd_delegation) || !in_task() ||
	    kc->depth >= KD_MAX_DEPTH)
		return false;

	for (;;) {
		n = READ_ONCE(me->next);
		if (!n)
			break;
		if (*budget >= kd_batch) {
			kd_stat_inc(kc, KD_STAT_STOP_BUDGET);
			break;
		}
		if (!n->entry) {
			kd_stat_inc(kc, KD_STAT_STOP_PLAIN);
			break;
		}
		if (need_resched()) {
			kd_stat_inc(kc, KD_STAT_STOP_RESCHED);
			break;
		}
		/*
		 * The flags share the queue word's cache line, which every
		 * returning waiter swaps once per section; reading them per
		 * section would miss nearly every time. A handoff request is
		 * rare and may wait up to KD_HANDOFF_POLL short sections.
		 */
		if (sleepable && !(*budget % KD_HANDOFF_POLL) &&
		    (READ_ONCE(q->flags) & KD_QF_HANDOFF)) {
			kd_stat_inc(kc, KD_STAT_STOP_HANDOFF);
			break;
		}
		if (numa && n->nid != me->nid) {
			/*
			 * Not claimed: a sleepable-class waiter may still
			 * withdraw while it is on the list; whoever meets it
			 * in the queue later frees it as usual.
			 */
			kd_q_detach(q, me, n);
			if (last)
				WRITE_ONCE(last->next, n);
			else
				first = n;
			last = n;
			++*budget;
			kd_stat_inc(kc, KD_STAT_NUMA_DEFERRED);
			continue;
		}
		if (!kd_ctx_compatible(n->regs)) {
			kd_stat_inc(kc, KD_STAT_STOP_CTX);
			break;
		}
		if (sleepable &&
		    cmpxchg(&n->state, KD_N_WAIT, KD_N_RUN) != KD_N_WAIT) {
			/* Left to sleep before we got here. */
			kd_q_detach(q, me, n);
			smp_store_release(&n->state, KD_N_FREE);
			continue;
		}
		/*
		 * Warm the next waiter while this one runs, without loading
		 * through its lines: a dependent load here (node, then packet,
		 * then stack pointer) stalls the session on two remote misses
		 * before every section (measured: most of kd_session's time).
		 * The node line is requested now, shared: its waiter polls its
		 * state there, and an exclusive request would take the line
		 * away from it (measured: -4% for mutex c16). The packet is
		 * requested once the section is done, when the node has
		 * arrived. Prefetches cannot fault,
		 * and node storage is per-CPU and never freed, so a pointer
		 * that is stale by then only costs a useless prefetch.
		 */
		nn = READ_ONCE(n->next);
		guess = NULL;
		if (nn) {
			prefetch(nn);
			/*
			 * Spin class only. Measured A/B in one boot: spin
			 * +1-3% at 8-32 workers; mutex c01 -6%, cause not
			 * established, so the sleepable class does not use it.
			 */
			if (!sleepable) {
				guess = kd_packet_guess(nn);
				prefetchw(guess);
				prefetchw((void *)guess + 64);
				prefetchw((void *)guess + 128);
			}
		}

		handed = !kd_exec_one(root, n, f);
		if (nn) {
			struct kd_regs *nr = READ_ONCE(nn->regs);

			if (nr && nr != guess) {
				prefetchw(nr);
				prefetchw((void *)nr + 64);
				prefetchw((void *)nr + 128);
			}
		}
		kd_q_detach(q, me, n);
		smp_store_release(&n->state, KD_N_RESUME);
		++*budget;
		if (!ran) {
			ran = true;
			kd_stat_inc(kc, KD_STAT_SESSIONS);
		}
		if (handed)
			break;
	}
	if (first)
		kd_q_splice_front(q, me, first, last);
	return handed;
}

/* ---- waiter side ----------------------------------------------------------- */

/*
 * Decide whether this waiter can be delegated and, if so, complete its
 * packet. The register part was stored by the entry stub.
 */
static void kd_prepare_offer(struct kd_cpu *kc, struct kd_node *me)
{
	struct kd_regs *r = &kc->regs;
	struct kd_site *site;

	me->regs = NULL;
	me->entry = NULL;
	if (!static_branch_likely(&kd_delegation) || !in_task())
		goto plain;

	site = kd_site_find(r->rip);
	if (!site) {
		kd_site_request(r->rip);
		goto plain;
	}
	me->entry = READ_ONCE(site->entry);
	if (!me->entry)
		goto plain;

	r->task = current;
#ifdef CONFIG_STACKPROTECTOR
	r->canary = current->stack_canary;
#endif
	r->stack_top = this_cpu_read(cpu_current_top_of_stack);
	r->site = site;
	r->pc_delta = 0;
	r->bh_off = softirq_count() != 0;
	r->nroots = 0;
	r->released = 0;
	me->regs = r;
	kd_stat_inc(kc, KD_STAT_OFFERED);
	return;
plain:
	kd_stat_inc(kc, KD_STAT_PLAIN);
}

/* A nested waiter publishes the packet it is executing, not its own. */
static void kd_node_offer(struct kd_cpu *kc, struct kd_node *me,
			  struct kd_regs *nested, void *entry)
{
	if (!nested) {
		kd_prepare_offer(kc, me);
		return;
	}
	me->entry = entry;
	me->regs = entry ? nested : NULL;
}

/*
 * The section was executed elsewhere. Make this task's context match what
 * the section left behind; kd_resume then installs registers and flags.
 * Interrupts go off first: once the count is adjusted the task may be
 * preemptible, and it must not be preempted on the per-CPU wait stack.
 * @pin is the internal pin of the sleepable-class stubs.
 */
void kd_finish_resume(int pin)
{
	long d;

	local_irq_disable();
	d = this_cpu_ptr(&kd_cpu)->regs.pc_delta - pin;
	if (d > 0)
		__preempt_count_add(d);
	else if (d < 0)
		__preempt_count_sub(-d);
}

static void kd_node_init(struct kd_node *n, int cpu, int idx)
{
	n->next = NULL;
	n->tail = kd_tail(cpu, idx);
	n->nid = cpu_to_node(cpu);
	WRITE_ONCE(n->state, KD_N_WAIT);
}

/*
 * Queue for @q without publishing a continuation: interrupt context,
 * raw locks, internal wait locks, and CPUs that cannot publish right now.
 * Preemption is off. Never combines.
 */
void kd_q_lock_plain(struct kd_qlock *q)
{
	struct kd_cpu *kc = this_cpu_ptr(&kd_cpu);
	struct kd_node *me;
	int idx = kc->nr_nodes;

	if (unlikely(idx >= KD_MAX_NODES)) {
		while (!kd_q_trylock(q))
			cpu_relax();
		return;
	}
	kc->nr_nodes++;
	/* An interrupt taken from here on must see the incremented count. */
	barrier();
	me = &kc->nodes[idx];
	kd_node_init(me, smp_processor_id(), idx);
	me->regs = NULL;
	me->entry = NULL;

	if (kd_q_enqueue(q, me, false))
		smp_cond_load_relaxed(&me->state, VAL != KD_N_WAIT);
	kd_q_head_lock(q);
	kd_q_pass(q, me, false);
	kc->nr_nodes--;
}

/*
 * Spin-class wait.
 *
 * Top level (@nested == NULL): slow path of the delegable entries, on the
 * wait stack with preemption off and kd_cpu.busy set; publishes this
 * CPU's own packet if the call site has an image.
 *
 * Nested (@nested != NULL): called by the executor of @nested for a
 * contended lock inside that continuation; publishes @nested with @entry
 * as the code following the lock call.
 *
 * Returns KD_WAIT_RESUMED if a combiner advanced the published packet,
 * KD_WAIT_LOCAL if this CPU holds the lock.
 */
int kd_wait_spin(struct kd_qlock *q, void *root, const struct kd_family *f,
		 struct kd_regs *nested, void *entry)
{
	struct kd_cpu *kc = this_cpu_ptr(&kd_cpu);
	struct kd_node *me;
	bool have_q = false;
	unsigned int budget = 0;
	int idx = kc->nr_nodes;

	if (unlikely(idx >= KD_MAX_NODES)) {
		while (!kd_q_trylock(q))
			cpu_relax();
		if (f && f->post)
			f->post(root);
		if (f && f->release)
			f->release(root);
		return KD_WAIT_LOCAL;
	}
	kc->nr_nodes++;
	barrier();
	me = &kc->nodes[idx];
	kd_node_init(me, smp_processor_id(), idx);
	kd_node_offer(kc, me, nested, entry);

	if (kd_q_enqueue(q, me, false) &&
	    smp_cond_load_acquire(&me->state, VAL != KD_N_WAIT) == KD_N_RESUME) {
		kc->nr_nodes--;
		return KD_WAIT_RESUMED;
	}

	/* Queue head. Loop because a handback takes the grant away again. */
	for (;;) {
		if (!have_q)
			kd_q_head_lock(q);
		if (f && f->post)
			f->post(root);
		if (!kd_session(q, me, root, f, false, &budget))
			break;
		have_q = f && f->keeps_q;
	}
	if (f && f->release)
		f->release(root);
	kd_q_pass(q, me, false);
	kc->nr_nodes--;
	return KD_WAIT_LOCAL;
}

static struct kd_node *kd_mnode_alloc(struct kd_cpu *kc)
{
	int i;

	for (i = 0; i < KD_MAX_NODES; i++) {
		struct kd_node *n = &kc->mnodes[i];

		if (READ_ONCE(n->state) == KD_N_FREE) {
			kd_node_init(n, smp_processor_id(), i);
			return n;
		}
	}
	return NULL;
}

/*
 * Sleepable-class wait (mutex, rwsem writer); @nested and @entry as for
 * kd_wait_spin(). The caller is pinned, so this only spins. Whenever
 * progress would need sleeping it leaves the queue and returns
 * KD_WAIT_SLEEP or KD_WAIT_SLEEP_HELD.
 *
 * A waiter gives up by moving its node from WAIT to ABANDON; the combiner
 * claims by moving it from WAIT to RUN. One cmpxchg decides, so a section
 * is executed by exactly one of them.
 */
int kd_wait_sleepable(struct kd_mutex *m, void *root, const struct kd_family *f,
		      struct kd_regs *nested, void *entry)
{
	struct kd_cpu *kc = this_cpu_ptr(&kd_cpu);
	struct kd_qlock *q = &m->q;
	struct kd_node *me;
	bool have_q = false;
	unsigned int budget = 0, spins;
	u32 st;

	/* Queueing only pays off while the holder is making progress. */
	if (!kd_mutex_can_spin(m)) {
		kd_stat_inc(kc, KD_STAT_NO_SPIN);
		return KD_WAIT_SLEEP;
	}
	me = kd_mnode_alloc(kc);
	if (!me)
		return KD_WAIT_SLEEP;
	kd_node_offer(kc, me, nested, entry);

	if (kd_q_enqueue(q, me, true)) {
		/*
		 * The owner word shares its cache line with the queue tail that
		 * every new waiter swaps, so a queued waiter looks at it only
		 * once per KD_OWNER_POLL iterations; it mostly reads its own node.
		 */
		for (spins = 1;; spins++) {
			st = READ_ONCE(me->state);
			if (st != KD_N_WAIT)
				break;
			if (need_resched() ||
			    (!(spins % KD_OWNER_POLL) && !kd_mutex_can_spin(m))) {
				if (cmpxchg(&me->state, KD_N_WAIT, KD_N_ABANDON) == KD_N_WAIT) {
					kd_stat_inc(kc, KD_STAT_ABANDON);
					return KD_WAIT_SLEEP;	/* the queue frees the node */
				}
				continue;
			}
			cpu_relax();
		}
		if (st == KD_N_RUN)
			st = smp_cond_load_relaxed(&me->state, VAL != KD_N_RUN);
		if (st == KD_N_RESUME) {
			smp_acquire__after_ctrl_dep();
			smp_store_release(&me->state, KD_N_FREE);
			return KD_WAIT_RESUMED;
		}
	} else {
		WRITE_ONCE(me->state, KD_N_HEAD);
	}

	for (;;) {
		if (!have_q) {
			while (!kd_q_trylock(q)) {
				if (!kd_mutex_can_spin(m)) {
					kd_stat_inc(kc, KD_STAT_HEAD_SLEEP);
					goto sleep;
				}
				cpu_relax();
			}
			WRITE_ONCE(m->owner, current);
		}
		if (f->post && !f->post(root)) {
			/* Keep the queue mutex; the caller decides how to wait on. */
			kd_q_pass(q, me, true);
			smp_store_release(&me->state, KD_N_FREE);
			return KD_WAIT_SLEEP_HELD;
		}
		if (!kd_session(q, me, root, f, true, &budget))
			break;
		have_q = f->keeps_q;
	}
	if (f->set_owner)
		f->set_owner(root, current);
	if (f->release)
		f->release(root);
	kd_q_pass(q, me, true);
	smp_store_release(&me->state, KD_N_FREE);
	return KD_WAIT_LOCAL;
sleep:
	kd_q_pass(q, me, true);
	smp_store_release(&me->state, KD_N_FREE);
	return KD_WAIT_SLEEP;
}

/* ---- init ------------------------------------------------------------------- */

unsigned long kd_stat_sum(int stat)
{
	unsigned long sum = 0;
	int cpu;

	for_each_possible_cpu(cpu)
		sum += per_cpu_ptr(&kd_cpu, cpu)->stat[stat];
	return sum;
}

/*
 * Give every possible CPU its wait stack, then allow publishing. Until
 * then busy == 1 keeps all waiters on the non-delegable path, so the locks
 * are usable from the first instruction of boot.
 */
static int __init kd_core_init(void)
{
	int cpu;

	for_each_possible_cpu(cpu) {
		struct kd_cpu *kc = per_cpu_ptr(&kd_cpu, cpu);
		struct page *page;

		page = alloc_pages_node(cpu_to_node(cpu), GFP_KERNEL | __GFP_ZERO,
					KD_WAIT_STACK_ORDER);
		if (!page) {
			pr_err("kdlock: no wait stack for cpu %d; delegation stays off there\n", cpu);
			continue;
		}
		kc->wait_stack = page_address(page) + (PAGE_SIZE << KD_WAIT_STACK_ORDER);
		/*
		 * Remote clear is safe: nobody owns busy before this point, a
		 * CPU that found it set simply took the plain path.
		 */
		WRITE_ONCE(kc->busy, 0);
	}
	pr_info("kdlock: core ready, batch %u, numa order %d\n", kd_batch, kd_numa);
	return 0;
}
early_initcall(kd_core_init);
