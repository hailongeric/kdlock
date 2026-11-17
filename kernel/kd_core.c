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
#include <linux/rcupdate.h>
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

/*
 * Most waiters one session serves before the combiner runs its own section.
 *
 * Within one NUMA node the value does not matter from 1024 up. Across two
 * nodes every end of a session moves the lock's data to the other node,
 * so longer sessions pay (build #68, in-boot A/B, 3 rounds, 64 workers on
 * two nodes, 4096 against 1024): spin c01 +5.1%, rwlock writers +3.0%,
 * rwsem writers +2.0%, mutex +1.2 to +1.6%; 16384 adds under 1% more, 256
 * costs 10 to 17%. With NUMA order a waiter of the other node waits for up
 * to this many sections, so the bound on its delay is four times that of
 * 1024. The TCLock backend of the bench runs with 1024, its maximum.
 */
unsigned int kd_batch __read_mostly = 4096;
core_param(kd_batch, kd_batch, uint, 0644);


/* Serve waiters of the combiner's NUMA node first (see kd_session()). */
bool kd_numa __read_mostly = true;
core_param(kd_numa, kd_numa, bool, 0644);
/* For a family with kd_family.numa_after set: the value used. */
unsigned int kd_numa_after __read_mostly = 32;
core_param(kd_numa_after, kd_numa_after, uint, 0644);

/*
 * Adaptive delegation.
 *
 * Delegation pays off only while the combiner keeps finding the next
 * waiter queued: then the lock's data stays in one cache and a section
 * costs the combiner little more than its body. With a short queue the
 * combiner outruns its waiters, and every section costs a lock handover
 * plus the transfer of a continuation, which is more than the native lock
 * pays (measured: spin, 1 line, 4 workers: 0.67 of Native with every
 * waiter delegated).
 *
 * So a spinlock or mutex starts in plain mode. There a contended caller
 * waits as on the native lock: same algorithm, on its own stack, nothing
 * published. A queue head samples how many waiters are queued behind it
 * (kd_q_depth()) and switches the lock to delegation mode when there are
 * at least kd_deleg_enter (spinlock) or kd_deleg_enter_sleep (mutex). From
 * then on contended callers publish their continuation. A combiner
 * switches the lock back when fewer than kd_deleg_exit waiters are queued
 * behind it. A plain spin queue head can also switch back, even when no
 * caller has an image and no combining session can start. Spin admission
 * uses the current holder's bit, never a mode cached by an earlier wait.
 *
 * The defaults come from an A/B in one boot (bench/results/kdclaude,
 * ab34enter): a mutex gains from delegation at a smaller depth than a
 * spinlock (16-line section, 6 workers: +27% with 3 instead of 4), while
 * a spinlock entered at depth 3 or 4 loses 2-3% at 4 and 5 workers. The
 * break-even depth really depends on the section length, which nothing
 * here measures; see docs/DIFFERENCES.md.
 *
 * rwlock and rwsem writers always delegate (kd_family.always_deleg).
 * kd_adapt=0 keeps every lock in delegation mode.
 */
bool kd_adapt __read_mostly = true;
core_param(kd_adapt, kd_adapt, bool, 0644);
unsigned int kd_deleg_enter __read_mostly = 5;
core_param(kd_deleg_enter, kd_deleg_enter, uint, 0644);
unsigned int kd_deleg_enter_sleep __read_mostly = 3;
core_param(kd_deleg_enter_sleep, kd_deleg_enter_sleep, uint, 0644);
unsigned int kd_deleg_exit __read_mostly = 2;
core_param(kd_deleg_exit, kd_deleg_exit, uint, 0644);

/*
 * Measuring the queue means reading other waiters' nodes, which the plain
 * path otherwise never does, so it is sampled: once per KD_PROBE_PERIOD
 * contended acquisitions of a CPU in plain mode, and once per
 * KD_VOTE_PERIOD sections of a session (whose nodes are needed soon anyway).
 */
#define KD_PROBE_PERIOD		128	/* power of two */
#define KD_VOTE_PERIOD		32

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
KD_CHECK(struct kd_regs, kind, KD_R_kind);
static_assert(sizeof(struct kd_regs) == KD_R_SIZE);
/* What a compact state needs, and nothing a full one alone needs, in lines 0 and 1. */
static_assert(offsetof(struct kd_regs, roots[2]) == KD_R_COMPACT_SIZE);
static_assert(KD_R_rbx >= KD_R_COMPACT_SIZE && KD_R_kind < KD_R_COMPACT_SIZE);
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
static_assert(offsetof(struct kd_qlock, pending) == 1 && offsetof(struct kd_qlock, tail) == 2);
static_assert(sizeof(struct kd_node) == SMP_CACHE_BYTES);
static_assert(sizeof(struct kd_regs) <= 4 * SMP_CACHE_BYTES);	/* kd_session() prefetches four lines */
static_assert(offsetof(struct kd_cpu, xs_hint) + 8 <= KD_BLOCK);
static_assert(!(offsetof(struct kd_cpu, nodes) % KD_BLOCK));

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

/*
 * RCU read-side nesting, with preemptible RCU.
 *
 * rcu_read_lock() and rcu_read_unlock() count in the task structure, and a
 * task's count is only ever changed by code running as that task, which
 * includes the interrupt handlers on its CPU. A section that changed its
 * origin's count from the executor's CPU would race with those handlers
 * (seen as "Voluntary context switch within RCU read-side critical
 * section" and a nonzero depth at the tick, build #38). The read-side
 * section also has to be in force on the CPU that follows the protected
 * pointers.
 *
 * So the copy calls __rcu_read_lock()/__rcu_read_unlock() natively (the
 * translator lists them), where they count for the executor, and the
 * count is carried like the preempt count: the packet says how many
 * read-side sections the continuation is in (->rcu_depth), an executor
 * holds that many on top of its own while it runs it, and the origin
 * brings its own count in line when it resumes. The adjustments are real
 * lock and unlock calls, so each task does its own exit processing.
 *
 * No grace period can end between an executor leaving and the origin
 * catching up: both are non-preemptible throughout, and a CPU in that
 * state reports no quiescent state.
 *
 * Make this task hold @target read-side sections more than @base.
 */
static void kd_rcu_sync(int base, int target)
{
	int have = rcu_preempt_depth() - base;

	for (; have < target; have++)
		rcu_read_lock();
	for (; have > target; have--)
		rcu_read_unlock();
}

static void kd_report_exit(struct kd_regs *r, u32 x, unsigned long ip,
			   unsigned long aux)
{
	struct kd_site *site = r->site;
	u32 type, kind = KD_X_KIND(x);
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
		/* Frontier, budget, pending acquire: nothing to learn, but say where. */
		if (atomic_add_unless(&site->hb_budget, -1, 0))
			kd_event_push(KD_EV_HANDBACK, site->rip, ip, x);
		return;
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
/*
 * Interrupt state the executor still owes itself after a handback; see the
 * end of kd_exec_one().
 */
struct kd_irq_hold {
	bool		held;
	bool		bh;
	bool		no_offer;	/* the grant did not go to the origin as it was */
	unsigned long	flags;
};

static __always_inline void kd_irq_release(struct kd_irq_hold *h)
{
	if (!h->held)
		return;
	h->held = false;
	local_irq_restore(h->flags);
	if (h->bh)
		local_bh_enable();
}

/*
 * Downgrade inside a delegated rwsem section (munmap does it on every
 * call). kd_vdown = 0: the section is handed back at the downgrade, so
 * the origin runs the read part itself and the session ends there. With
 * 1 the combiner keeps the write side and goes on executing: the read
 * part needs no more than the write side gives. The read release of the
 * root then ends the section like a write release would. If the read part
 * has to be handed back after all, the downgrade is done for real at that
 * point and the origin continues as a reader.
 *
 * Cost: readers of that rwsem wait through read parts they could have
 * shared. It is a throughput choice for writer-dominated use.
 *
 * kd_cldemote (bits): a queued waiter moves its packet (1) and the top of
 * its stack (2) out of its private caches, so that the combiner finds
 * those lines in the shared cache level (CLDEMOTE; a no-op where the CPU
 * lacks it). 16 and 32 are the same for the sleepable class.
 *
 * Measured (build #67, in-boot A/B, 3 rounds, 2.7 GHz, against 0): with 3
 * the spin class gains 0 to 2% from 8 workers (spin c01 +0.6 to +1.2,
 * rwlock writers +0.6 to +2.2, spin c08 -0.1 to +1.6). The sleepable
 * class does not (mutex c01 -0.3 to +0.2, mutex c16 -0.4 to -0.9, rwsem
 * writers +0.2 to +1.4), so its bits are off. The effect is small because
 * the combiner already requests the packet one section ahead. The
 * combiner demoting the lines back after a section loses 3 to 20% and is
 * not kept.
 */
static unsigned int kd_vdown __read_mostly = 1;
core_param(kd_vdown, kd_vdown, uint, 0644);
static unsigned int kd_cldemote __read_mostly = 3;
core_param(kd_cldemote, kd_cldemote, uint, 0644);

static __always_inline void kd_demote(const void *p, long len)
{
	const char *c = (const char *)((unsigned long)p & ~63UL);
	const char *end = (const char *)p + len;

	for (; c < end; c += 64)
		asm volatile(".byte 0x0f, 0x1c, 0x00" : : "a" (c));	/* cldemote (%rax) */
}

/* The lines a section starts on: the packet and the origin's stack top. */
static __always_inline void kd_demote_packet(struct kd_regs *r, unsigned int how)
{
	if (how & 1)
		kd_demote(r, r->kind == KD_RS_COMPACT ? KD_R_COMPACT_SIZE : sizeof(*r));
	if (how & 2)
		kd_demote((void *)(r->rsp - 128), 448);
}

static bool kd_exec_one(void *root, struct kd_node *n, const struct kd_family *f,
			struct kd_irq_hold *hold)
{
	struct kd_cpu *kc = this_cpu_ptr(&kd_cpu);
	struct kd_regs *r = n->regs;
	void *code = n->entry;
	void *resume;
	unsigned long flags, ip, aux;
	unsigned int kind, op, level = r->nroots;
	bool done = false, native = true, bh = false, planned = false;
	int pc0, d, i, ret, rcu0;
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
	rcu0 = rcu_preempt_depth();
	kd_rcu_sync(rcu0, r->rcu_depth);

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
		/* Whoever continues it, here or elsewhere, starts from this. */
		r->rcu_depth = rcu_preempt_depth() - rcu0;
		x = kc->exit_code;
		ip = kc->exit_ip;
		resume = (void *)kc->resume;
		aux = kc->aux;
		kind = KD_X_KIND(x);
		op = KD_X_OP(x);

		if (kind == KD_X_UNLOCK && op == KD_OP_DOWNGRADE && !(x & KD_X_TAIL) &&
		    f && f->downgrade && READ_ONCE(kd_vdown)) {
			/* Keep the write side and run the read part too. */
			r->vdown |= BIT(level);
			kd_stat_inc(kc, KD_STAT_VDOWN);
			code = resume;
			continue;
		}

		if (kind == KD_X_UNLOCK && op != KD_OP_DOWNGRADE &&
		    (op != KD_OP_UP_READ || (r->vdown & BIT(level)))) {
			/* Release of our root: this level's section is complete. */
			r->vdown &= ~BIT(level);
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
			/* A read release only ends an outer root that was downgraded. */
			u8 ok = op == KD_OP_UP_READ ? r->vdown : 0xff;

			/*
			 * Release of some other lock while outer sessions exist.
			 * An outer root stays physically held by its combiner and
			 * is only marked; anything else is released for real.
			 */
			for (i = level - 1; i >= 0; i--) {
				if (r->roots[i] == (void *)r->rdi && (ok & BIT(i)))
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
				kd_rcu_sync(rcu0, r->rcu_depth);
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

		/*
		 * Handback: the origin executes the instruction at @ip itself.
		 * A downgrade is a planned one: the write part of the section
		 * was executed here, and only the read-side remainder belongs
		 * to the origin (munmap does this on every call). It counts as
		 * useful for the site, or such sites would be switched off.
		 */
		planned = kind == KD_X_UNLOCK && op == KD_OP_DOWNGRADE;
		switch (kind) {
		case KD_X_FRONTIER:
			kd_stat_inc(kc, KD_STAT_HB_FRONTIER);
			break;
		case KD_X_MISS_CODE:
		case KD_X_MISS_IND:
		case KD_X_MISS_RET:
			kd_stat_inc(kc, KD_STAT_HB_MISS);
			break;
		case KD_X_ACQUIRE:
		case KD_X_NESTED:
			kd_stat_inc(kc, KD_STAT_HB_ACQUIRE);
			break;
		default:
			kd_stat_inc(kc, planned ? KD_STAT_HB_DOWNGRADE : KD_STAT_HB_OTHER);
		}
		r->rip = ip;
		kd_report_exit(r, x, ip, aux);
		break;
	}

	kd_rcu_sync(rcu0, 0);
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
	if (r->vdown & BIT(level)) {
		r->vdown &= ~BIT(level);
		if (native && !done) {
			/* The read part goes back: the origin gets a read hold. */
			f->downgrade(root);
			hold->no_offer = true;
			planned = true;
			kd_stat_inc(kc, KD_STAT_VDOWN_HB);
		}
	}

	d = preempt_count() - pc0;
	if (d) {
		__preempt_count_sub(d);
		r->pc_delta += d;
		if (native)
			kd_stat_inc(kc, KD_STAT_HANDBACK_PINNED);
	}
	__preempt_count_sub(KD_EXEC_PIN);
	/*
	 * A section handed back with interrupts off usually holds an
	 * interrupt-safe lock it took here, and such a lock can belong to
	 * this CPU (the copy's per-CPU accesses are the executor's: a wakeup
	 * inside the section takes this CPU's runqueue lock and, for the
	 * fair server's timer, its hrtimer base lock). The origin releases
	 * it, but only after it has been resumed. If this CPU enabled
	 * interrupts first, a timer interrupt here would wait for that lock
	 * with the origin never resumed (seen as a hang of mmap1 on 64
	 * vCPUs: the combiner in hrtimer_interrupt() on its own base lock,
	 * every other CPU behind it). So interrupts stay off until the
	 * caller has published the resume; see kd_irq_release().
	 */
	if (native && !(r->rflags & X86_EFLAGS_IF) && !raw_irqs_disabled_flags(flags)) {
		hold->held = true;
		hold->bh = bh;
		hold->flags = flags;
	} else {
		local_irq_restore(flags);
		if (bh)
			local_bh_enable();
	}

	kd_stat_inc(kc, native ? KD_STAT_HANDBACK : KD_STAT_DELEGATED);
	if (done && !native && r->kind == KD_RS_COMPACT)
		kd_stat_inc(kc, KD_STAT_CL_DONE);
	kd_site_account(r->site, !native || planned);
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

/* The packet lines a section uses: two for a compact state, four for a full one. */
static __always_inline void kd_prefetch_packet(struct kd_regs *r, bool full)
{
	prefetchw(r);
	prefetchw((void *)r + 64);
	if (full) {
		prefetchw((void *)r + 128);
		prefetchw((void *)r + 192);
	}
}

/* ---- role exchange after a handback ----------------------------------------- */

/*
 * When a section is handed back, its origin W continues on its own CPU and
 * owns the lock, while the combiner C still has its own section to run.
 * C does not just wait for W's release as queue head. It offers itself:
 * its node, which already publishes C's own continuation, goes to state
 * KD_N_HWAIT. W's release takes the head role over
 * (kd_release_combine()): it links a node of its own in front of C's and
 * runs a session, which serves C first and then the rest of the queue. The
 * lock's data thus moves to W's CPU once and stays there, instead of going
 * to W and back to C.
 *
 * How W's release learns of the offer without reading the lock word before
 * it releases (that read can cost a cache transfer on the handover path):
 * a spin-class holder stays on its CPU, so the offer is counted in its
 * packet and from there in kd_cpu.xcount when it resumes. A sleepable-class
 * holder may move, so there are two ways: its packet names the lock, which
 * becomes kd_cpu.xs_hint on the CPU where it resumes, and a release on that
 * CPU takes over before it releases; elsewhere the release, one atomic
 * operation on the lock word, finds a mark (kd_family.xflag) in the value
 * that operation returns and takes the lock again for the session if
 * nobody was faster.
 *
 * The holder finds C's node in a small table keyed by lock address: the
 * lock words have no room for a second node id, and a mutex holder may
 * have changed CPU since it queued. An offer leaves KD_N_HWAIT only under
 * the bucket lock, together with its table entry, in one of three ways:
 *
 *   -> KD_N_WAIT   the holder took over; C is an ordinary queued waiter
 *   -> KD_N_HBACK  the holder declined (its release runs where a session
 *                  cannot), or C withdrew because the holder stopped
 *                  running (sleepable class); C is queue head as before
 *
 * kd_xchg selects who offers: 0 nobody, 1 the sleepable class (mutex and
 * rwsem writer), 2 every class. The default is 1. That is where a section
 * can block, and where a combiner that waits as queue head for a holder
 * that blocked ends up sleeping with the queue in its hands. Measured (A/B
 * in one boot, a sixteenth of the sections handed back, build #37; see
 * bench/results/kdclaude): rwsem +19% at 16 workers, mutex +10% at 32, but
 * mutex -4 to -5% at 8 and 16; the spinlock only lost (0 to -4%), and the
 * rwlock gained 5% at 32 workers and lost 3 to 5% at 8 and 16.
 */
unsigned int kd_xchg __read_mostly = 1;
core_param(kd_xchg, kd_xchg, uint, 0644);

#define KD_XHEAD_BUCKETS	64	/* power of two */
#define KD_XHEAD_WAYS		4

struct kd_xhead_bucket {
	struct kd_qlock	lock;
	struct {
		void		*root;
		struct kd_node	*node;
	} e[KD_XHEAD_WAYS];
} ____cacheline_aligned_in_smp;

static struct kd_xhead_bucket kd_xheads[KD_XHEAD_BUCKETS];

/* Interrupts off: the bucket lock is also taken by releases in any context. */
static struct kd_xhead_bucket *kd_xhead_lock(void *root, unsigned long *flags)
{
	struct kd_xhead_bucket *b =
		&kd_xheads[hash_ptr(root, ilog2(KD_XHEAD_BUCKETS))];

	local_irq_save(*flags);
	if (unlikely(!kd_q_trylock_fifo(&b->lock)))
		kd_q_lock_plain(&b->lock);
	return b;
}

static void kd_xhead_unlock(struct kd_xhead_bucket *b, unsigned long flags)
{
	kd_q_unlock(&b->lock);
	local_irq_restore(flags);
}

/*
 * Queue head @me, which holds the grant on @root and is about to resume a
 * waiter that leaves with it, offers itself to that waiter, whose packet is
 * @r. Every change @me makes to the queue is done. False: no offer (nothing
 * published by @me, table full).
 */
static bool kd_xhead_offer(struct kd_node *me, void *root, const struct kd_family *f,
			   struct kd_regs *r, bool sleepable)
{
	struct kd_xhead_bucket *b;
	unsigned long flags;
	int i;

	if (READ_ONCE(kd_xchg) < (sleepable ? 1 : 2) || !f || !me->entry)
		return false;
	b = kd_xhead_lock(root, &flags);
	for (i = 0; i < KD_XHEAD_WAYS; i++) {
		if (b->e[i].root)
			continue;
		b->e[i].root = root;
		b->e[i].node = me;
		WRITE_ONCE(me->state, KD_N_HWAIT);
		if (f->xflag)
			f->xflag(root, true);
		if (sleepable)
			r->xs_root = root;
		else
			r->xoffers++;
		break;
	}
	kd_xhead_unlock(b, flags);
	if (i == KD_XHEAD_WAYS)
		return false;
	raw_cpu_inc(kd_cpu.stat[KD_STAT_XCHG_OFFER]);
	return true;
}

/*
 * End the offer for @root by moving its node to state @to. @only limits
 * that to one node (the offering head withdrawing its own offer). Returns
 * the node, or NULL if there was no such offer any more.
 */
static struct kd_node *kd_xhead_settle(void *root, const struct kd_family *f,
				       struct kd_node *only, u32 to)
{
	struct kd_xhead_bucket *b;
	struct kd_node *n = NULL;
	unsigned long flags;
	int i;

	b = kd_xhead_lock(root, &flags);
	for (i = 0; i < KD_XHEAD_WAYS; i++) {
		if (b->e[i].root != root || (only && b->e[i].node != only))
			continue;
		n = b->e[i].node;
		b->e[i].root = NULL;
		b->e[i].node = NULL;
		if (f->xflag)
			f->xflag(root, false);
		smp_store_release(&n->state, to);
		break;
	}
	kd_xhead_unlock(b, flags);
	return n;
}

/* The holder cannot take over where it is (for example a downgrade). */
void kd_release_decline(void *root, const struct kd_family *f)
{
	if (kd_xhead_settle(root, f, NULL, KD_N_HBACK))
		raw_cpu_inc(kd_cpu.stat[KD_STAT_XCHG_DECLINED]);
}

/*
 * Record the mode of the lock behind @q. Spin class: the holder's lock
 * byte (the caller holds the lock). Sleepable class: a flag.
 */
static void kd_mode_set(struct kd_qlock *q, bool sleepable, bool on)
{
	struct kd_cpu *kc = this_cpu_ptr(&kd_cpu);

	if (sleepable) {
		if (on)
			atomic_or(KD_QF_DELEG << KD_QF_SHIFT, &q->val);
		else
			atomic_andnot(KD_QF_DELEG << KD_QF_SHIFT, &q->val);
	} else {
		u8 lv = READ_ONCE(q->locked);

		WRITE_ONCE(q->locked, on ? lv | KD_Q_DELEG : lv & ~KD_Q_DELEG);
	}
	kd_stat_inc(kc, on ? KD_STAT_MODE_ENTER : KD_STAT_MODE_EXIT);
}

/*
 * A queue head in plain mode: is the queue behind @me deep enough to
 * delegate? Sampled, because the answer costs a read of the newest
 * waiter's node, which the plain path does not otherwise touch.
 */
static __always_inline bool kd_probe_enter(struct kd_cpu *kc, struct kd_node *me,
					   bool sleepable)
{
	int enter;

	if (!static_branch_likely(&kd_delegation))
		return false;
	if (kc->probe++ & (KD_PROBE_PERIOD - 1))
		return false;
	enter = sleepable ? READ_ONCE(kd_deleg_enter_sleep) : READ_ONCE(kd_deleg_enter);
	return kd_q_depth(me, enter) >= enter;
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
 * Mode. The session counts the waiters still queued behind it, every
 * KD_VOTE_PERIOD sections and when it ends. Below kd_deleg_exit the lock
 * goes back to plain mode and *@deleg is cleared, so that the caller
 * promotes its successor accordingly.
 *
 * Role exchange. If a waiter leaves with the grant and @xowner is given,
 * @me offers itself to it (kd_xhead_offer()); *@xowner is then that
 * waiter's task and @me is in state KD_N_HWAIT.
 *
 * Sessions nest: this function is also reached from kd_exec_one() when the
 * executor becomes head of an inner lock's queue. kd_cpu.depth bounds that
 * recursion; at the limit the head just takes the lock. The passed-over
 * list is local, so nested sessions need no extra state.
 */
static bool kd_session(struct kd_qlock *q, struct kd_node *me, void *root,
		       const struct kd_family *f, bool sleepable,
		       unsigned int *budget, bool *deleg,
		       struct task_struct **xowner)
{
	struct kd_cpu *kc = this_cpu_ptr(&kd_cpu);
	struct kd_node *n, *nn, *first = NULL, *last = NULL, *claimed = NULL;
	bool numa = READ_ONCE(kd_numa);
	unsigned int numa_after = f && f->numa_after ? READ_ONCE(kd_numa_after) : 0;
	bool adapt = READ_ONCE(kd_adapt) && !(f && f->always_deleg);
	bool handed = false, leave = false;
	unsigned int served = 0, passed = 0;
	int exit_below = READ_ONCE(kd_deleg_exit);
	struct kd_regs *guess;
	bool guess_full;
	struct kd_irq_hold hold = { .held = false };

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
		if (numa && n->nid != me->nid && served >= numa_after) {
			/*
			 * Not claimed: a sleepable-class waiter may still
			 * withdraw while it is on the list; whoever meets it
			 * in the queue later frees it as usual.
			 */
			if (claimed == n) {
				WRITE_ONCE(n->claim, false);
				claimed = NULL;
			}
			kd_q_detach(q, me, n);
			if (last)
				WRITE_ONCE(last->next, n);
			else
				first = n;
			last = n;
			++*budget;
			passed++;
			kd_stat_inc(kc, KD_STAT_NUMA_DEFERRED);
			continue;
		}
		if (!kd_ctx_compatible(n->regs)) {
			kd_stat_inc(kc, KD_STAT_STOP_CTX);
			break;
		}
		if (sleepable) {
			/*
			 * Announced during the previous section as a rule; see
			 * kd_node_abandon() for the protocol.
			 */
			if (claimed != n) {
				if (claimed)
					WRITE_ONCE(claimed->claim, false);
				WRITE_ONCE(n->claim, true);
				claimed = n;
			}
			smp_mb();
			if (READ_ONCE(n->state) != KD_N_WAIT && kd_node_drop(n)) {
				/* Left to sleep before we got here. */
				claimed = NULL;
				kd_q_detach(q, me, n);
				smp_store_release(&n->state, KD_N_FREE);
				continue;
			}
			claimed = NULL;		/* ours now: nothing to take back */
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
		/*
		 * Whether the next packet is full is only known once its node
		 * has arrived; until then the waiter being served is the
		 * guess (a call site uses one kind of entry, and the waiters
		 * of one lock mostly come from the same sites).
		 */
		guess_full = READ_ONCE(n->full);
		if (nn && sleepable) {
			/*
			 * Announce the next waiter instead of prefetching its
			 * node: the store asks for the line while this section
			 * runs and nothing waits for it.
			 */
			WRITE_ONCE(nn->claim, true);
			claimed = nn;
		} else if (nn) {
			prefetch(nn);
			/*
			 * Spin class only. Measured A/B in one boot: spin
			 * +1-3% at 8-32 workers. The sleepable class gains
			 * nothing from it (build #68, at the address guessed
			 * from mnodes[0]: -2 to +1%).
			 */
			guess = kd_packet_guess(nn);
			kd_prefetch_packet(guess, guess_full);
		}
		/*
		 * Requesting more than this ahead loses (build #68, in-boot
		 * A/B, 8-64 workers): the next waiter's stack top after the
		 * section, mutex and rwsem writers -15 to -27% and spin -1 to
		 * -10%; node and packet of the waiter after next, -1 to -14%.
		 * The nano sections do not touch the origin's stack, and each
		 * extra line is one more transfer from a core that needs it
		 * back. Archived: refs/archive/kdclaude-session-prefetch-stages-20261115.
		 */

		hold.no_offer = false;
		handed = !kd_exec_one(root, n, f, &hold);
		if (nn) {
			struct kd_regs *nr = READ_ONCE(nn->regs);
			bool full = READ_ONCE(nn->full);

			if (nr && nr != guess) {
				kd_prefetch_packet(nr, full);
			} else if (nr && full && !guess_full) {
				prefetchw((void *)nr + 128);
				prefetchw((void *)nr + 192);
			}
		}
		kd_q_detach(q, me, n);
		if (handed) {
			/*
			 * The origin may release, and take the head role over,
			 * as soon as it is resumed: finish with the queue first.
			 */
			if (first) {
				kd_q_splice_front(q, me, first, last);
				first = NULL;
			}
			/* While this CPU still is the only head. */
			if (claimed) {
				WRITE_ONCE(claimed->claim, false);
				claimed = NULL;
			}
			if (xowner && !hold.no_offer &&
			    kd_xhead_offer(me, root, f, n->regs, sleepable))
				*xowner = n->regs->task;
		}
		smp_store_release(&n->state, KD_N_RESUME);
		kd_irq_release(&hold);
		++*budget;
		if (!served++)
			kd_stat_inc(kc, KD_STAT_SESSIONS);
		if (handed)
			break;
		if (adapt && !(served % KD_VOTE_PERIOD) &&
		    kd_q_depth(me, exit_below) + (int)passed < exit_below) {
			leave = true;
			break;
		}
	}
	if (claimed)
		WRITE_ONCE(claimed->claim, false);
	if (first)
		kd_q_splice_front(q, me, first, last);
	/*
	 * A handback leaves the lock with the origin; the mode is judged by
	 * the next session.
	 */
	if (adapt && !handed &&
	    (leave || kd_q_depth(me, exit_below) < exit_below)) {
		kd_mode_set(q, sleepable, false);
		*deleg = false;
	}
	return handed;
}

/* ---- waiter side ----------------------------------------------------------- */

/*
 * May a contended caller at call site @rip publish its continuation now?
 * Preemption is off. A site without generated code is counted, so that
 * the translator is asked for the ones that matter.
 */
bool kd_can_offer(unsigned long rip)
{
	struct kd_site *site;

	if (!static_branch_likely(&kd_delegation) || !in_task() ||
	    raw_cpu_read(kd_cpu.busy))
		return false;
	/*
	 * A holder with an offer to answer (role exchange) must release that
	 * lock itself, on this CPU; a combiner running its continuation would
	 * not know about the offer.
	 */
	if (unlikely(raw_cpu_read(kd_cpu.xcount)))
		return false;
	site = kd_site_find(rip);
	if (!site) {
		kd_site_request(rip);
		return false;
	}
	if (likely(READ_ONCE(site->entry)))
		return true;
	kd_site_retry(site);		/* switched off: time to try it again? */
	return READ_ONCE(site->entry) != NULL;
}

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
	r->vdown = 0;
	r->released = 0;
	r->xoffers = 0;
	r->xs_root = NULL;
	r->rcu_depth = rcu_preempt_depth();
	me->regs = r;
	kd_stat_inc(kc, KD_STAT_OFFERED);
	if (r->kind == KD_RS_COMPACT)
		kd_stat_inc(kc, KD_STAT_CL_OFFERED);
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
	} else {
		me->entry = entry;
		me->regs = entry ? nested : NULL;
	}
	/* The entry stub, or the exit that left generated code, set the kind. */
	me->full = me->regs && me->regs->kind != KD_RS_COMPACT;
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
	struct kd_cpu *kc;
	long d;

	local_irq_disable();
	kc = this_cpu_ptr(&kd_cpu);
	/* Offers of the combiners that handed this section back. */
	kc->xcount += kc->regs.xoffers;
	if (kc->regs.xs_root)
		kc->xs_hint = kc->regs.xs_root;
	/* RCU read-side sections the section entered or left for us. */
	kd_rcu_sync(0, kc->regs.rcu_depth);
	d = kc->regs.pc_delta - pin;
	if (d > 0)
		__preempt_count_add(d);
	else if (d < 0)
		__preempt_count_sub(-d);
}

static __always_inline void kd_node_init(struct kd_node *n, int cpu, int idx)
{
	n->next = NULL;
	n->tail = kd_tail(cpu, idx);
	n->claim = false;
	WRITE_ONCE(n->state, KD_N_WAIT);
}

/*
 * Queue for the spin-class word @q without publishing a continuation, and
 * take the lock: the queue part of the native queued spinlock. Preemption
 * is off. The caller has been through kd_q_pending().
 *
 * This is the whole contended path in plain mode, and the path of every
 * caller that can never be delegated: raw locks, internal wait locks,
 * rwlock readers, interrupt context. A waiter queued here never combines;
 * a session ends at its node (->entry is NULL: kd_wait_spin() clears it
 * again whenever it gives a node back).
 *
 * @probe: the lock is a delegable one, so this head may switch it to
 * delegation mode. The mode otherwise travels with the head role
 * (KD_N_HEAD_D), also through waiters that do not take part in it.
 * Returns whether the lock was taken in delegation mode.
 */
static __always_inline bool __kd_q_queue(struct kd_qlock *q, bool probe)
{
	struct kd_cpu *kc = this_cpu_ptr(&kd_cpu);
	struct kd_node *me, *next;
	u8 lv = KD_Q_LOCKED;
	int idx = kd_nr_nodes(kc);

	if (unlikely(idx >= KD_MAX_NODES)) {
		/* As the native lock does when it runs out of nodes. */
		while (!kd_q_trylock_fifo_read(q))
			cpu_relax();
		return false;
	}
	kd_nr_nodes(kc)++;
	/* An interrupt taken from here on must see the incremented count. */
	barrier();
	me = &kc->nodes[idx];
	kd_node_init(me, smp_processor_id(), idx);

	/* The node line may have been cold: the lock may be free by now. */
	if (kd_q_trylock_fifo_read(q))
		goto out;

	if (kd_q_enqueue(q, me, false)) {
		if (smp_cond_load_acquire(&me->state, VAL != KD_N_WAIT) == KD_N_HEAD_D)
			lv |= KD_Q_DELEG;
		/*
		 * The successor's node is written when the head role is passed
		 * on; ask for it now, while this CPU still waits for the lock.
		 */
		next = READ_ONCE(me->next);
		if (next)
			prefetchw(next);
		/*
		 * Measure the queue here, as the new head that still waits for
		 * the holder: the walk then costs nobody anything. Done after
		 * taking the lock it delays the holder and the next promotion
		 * (measured: 3.5% of the plain rate at 4 workers).
		 */
		if (probe && lv == KD_Q_LOCKED && READ_ONCE(kd_adapt) &&
		    kd_probe_enter(kc, me, false)) {
			lv |= KD_Q_DELEG;
			kd_stat_inc(kc, KD_STAT_MODE_ENTER);
		}
	} else {
		/* First in the queue: keep the mode of the current holder. */
		lv |= READ_ONCE(q->locked) & KD_Q_DELEG;
	}

	/*
	 * A plain head may have inherited a delegating phase without an
	 * image to serve it. Let it leave that phase too: waiting for a
	 * combiner to do this would retain the offer path after contention
	 * falls. Only the head examines its successors, before taking the
	 * lock. A link still being published can make us leave early; that
	 * only selects local execution and does not change queue ownership.
	 */
	if (probe && (lv & KD_Q_DELEG) && READ_ONCE(kd_adapt)) {
		int exit_below = READ_ONCE(kd_deleg_exit);

		if (kd_q_depth(me, exit_below) < exit_below) {
			lv &= ~KD_Q_DELEG;
			kd_stat_inc(kc, KD_STAT_MODE_EXIT);
		}
	}

	if (kd_q_head_take(q, me, lv))
		goto out;
	next = READ_ONCE(me->next);
	if (!next)
		next = smp_cond_load_relaxed(&me->next, VAL);
	smp_store_release(&next->state,
			  (lv & KD_Q_DELEG) ? KD_N_HEAD_D : KD_N_HEAD);
out:
	kd_nr_nodes(kc)--;
	return lv & KD_Q_DELEG;
}

bool kd_q_queue(struct kd_qlock *q, bool probe)
{
	return __kd_q_queue(q, probe);
}

/* Contended acquisition for callers that are never delegated. */
void kd_q_lock_plain(struct kd_qlock *q)
{
	u32 val;

	if (!kd_q_pending(q, &val))
		__kd_q_queue(q, false);
}

/*
 * Slow path of the delegable spinlock entries, called by the entry stub on
 * the caller's stack with preemption off. @site is the caller's return
 * address. One function, like the native slow path it stands for in plain
 * mode.
 *
 * Returns true with the lock held. Returns false, with nothing queued,
 * when the lock is in delegation mode and this caller can publish its
 * continuation; the stub then goes on to the wait stack and kd_wait_spin().
 */
bool kd_q_lock_slow(struct kd_qlock *q, unsigned long site)
{
	u32 val;

	if (kd_q_pending(q, &val))
		return true;
	if (kd_q_deleg_mode(val) && kd_can_offer(site))
		return false;
	raw_cpu_inc(kd_cpu.nodes[0].nplain);
	__kd_q_queue(q, true);
	return true;
}

/*
 * Spin-class wait with a published continuation.
 *
 * Top level (@nested == NULL): called by the entry stub on the wait stack,
 * after the *_slow function found the lock in delegation mode, with
 * preemption off and kd_cpu.busy set; publishes this CPU's own packet.
 *
 * Nested (@nested != NULL): called by the executor of @nested for a
 * contended lock inside that continuation; publishes @nested with @entry
 * as the code following the lock call.
 *
 * Returns KD_WAIT_RESUMED if a combiner advanced the published packet,
 * KD_WAIT_LOCAL if this CPU holds the lock.
 *
 * A waiter that reaches the queue head takes the lock and, in delegation
 * mode, serves the waiters behind it before it returns to run its own
 * section. A head without a predecessor keeps the mode it queued under.
 */
int kd_wait_spin(struct kd_qlock *q, void *root, const struct kd_family *f,
		 struct kd_regs *nested, void *entry)
{
	struct kd_cpu *kc = this_cpu_ptr(&kd_cpu);
	struct kd_node *me;
	bool have_q = false, out = false, deleg = true;
	struct task_struct *xowner;
	unsigned int budget = 0;
	int idx = kd_nr_nodes(kc);
	u32 st;

	if (unlikely(idx >= KD_MAX_NODES)) {
		while (!kd_q_trylock_fifo(q))
			cpu_relax();
		if (f && f->post)
			f->post(root, NULL);
		if (f && f->release)
			f->release(root);
		return KD_WAIT_LOCAL;
	}
	kd_nr_nodes(kc)++;
	barrier();
	me = &kc->nodes[idx];
	kd_node_init(me, smp_processor_id(), idx);
	me->nid = numa_node_id();
	kd_node_offer(kc, me, nested, entry);

	if (kd_q_enqueue(q, me, false)) {
		if (me->regs == &kc->regs && (READ_ONCE(kd_cldemote) & 3))
			kd_demote_packet(me->regs, READ_ONCE(kd_cldemote));
		st = smp_cond_load_acquire(&me->state, VAL != KD_N_WAIT);
		if (st == KD_N_RESUME) {
			me->entry = NULL;
			kd_nr_nodes(kc)--;
			return KD_WAIT_RESUMED;
		}
		deleg = st == KD_N_HEAD_D || !READ_ONCE(kd_adapt) ||
			(f && f->always_deleg);
	}

	/*
	 * Promoted in plain mode: measure the queue while waiting for the
	 * holder, as kd_q_queue() does.
	 */
	if (!deleg && kd_probe_enter(kc, me, false)) {
		deleg = true;
		kd_stat_inc(kc, KD_STAT_MODE_ENTER);
	}

	/* Queue head. Loop because a handback takes the grant away again. */
	for (;;) {
		if (!have_q)
			out = kd_q_head_take(q, me, deleg ? KD_Q_LOCKED | KD_Q_DELEG :
							    KD_Q_LOCKED);
		if (f && f->post)
			f->post(root, out ? NULL : me);
		if (out)
			break;		/* nobody is queued behind us */
		if (!deleg)
			break;
		xowner = NULL;
		if (!kd_session(q, me, root, f, false, &budget, &deleg, &xowner))
			break;
		have_q = f && f->keeps_q;
		if (!xowner)
			continue;
		/*
		 * We offered ourselves to the origin that left with the grant
		 * (it may have answered already). A spin-class holder cannot
		 * stop running, so its release answers: it takes the head role
		 * over, or declines.
		 */
		st = smp_cond_load_acquire(&me->state, VAL != KD_N_HWAIT);
		if (st == KD_N_HBACK)
			continue;
		if (st == KD_N_WAIT)
			st = smp_cond_load_acquire(&me->state, VAL != KD_N_WAIT);
		if (st == KD_N_RESUME) {
			me->entry = NULL;
			kd_nr_nodes(kc)--;
			return KD_WAIT_RESUMED;
		}
		/* Promoted again; the taker dropped the queue lock it inherited. */
		deleg = st == KD_N_HEAD_D || !READ_ONCE(kd_adapt) ||
			(f && f->always_deleg);
		have_q = false;
	}
	if (f && f->release)
		f->release(root);
	if (!out)
		kd_q_pass(q, me, false, deleg ? KD_N_HEAD_D : KD_N_HEAD);
	me->entry = NULL;
	kd_nr_nodes(kc)--;
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
 * Sleepable-class wait (mutex, rwsem writer) in the spinner queue. The
 * caller is pinned, so this only spins. Whenever progress would need
 * sleeping it leaves the queue and returns KD_WAIT_SLEEP or
 * KD_WAIT_SLEEP_HELD.
 *
 * @offer: publish a continuation. Set by the entry stub's offer path (on
 * the wait stack, kd_cpu.busy set) and for nested waits (@nested and
 * @entry as for kd_wait_spin()). Clear in plain mode, where the caller
 * waits on its own stack and nothing is published.
 *
 * A waiter gives up by moving its node from WAIT to ABANDON; the combiner
 * claims by moving it from WAIT to RUN. One cmpxchg decides, so a section
 * is executed by exactly one of them.
 */
int kd_wait_sleepable(struct kd_mutex *m, void *root, const struct kd_family *f,
		      struct kd_regs *nested, void *entry, bool offer)
{
	struct kd_cpu *kc = this_cpu_ptr(&kd_cpu);
	struct kd_qlock *q = &m->q;
	struct kd_node *me;
	struct task_struct *xowner;
	bool have_q = false, deleg, queued;
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
	if (offer) {
		me->nid = numa_node_id();
		kd_node_offer(kc, me, nested, entry);
	} else {
		me->entry = NULL;
		kd_stat_inc(kc, KD_STAT_PLAIN);
	}

	queued = kd_q_enqueue(q, me, true) != NULL;
	if (queued && me->regs == &kc->regs && unlikely(READ_ONCE(kd_cldemote) & 0x30))
		kd_demote_packet(me->regs, READ_ONCE(kd_cldemote) >> 4);
again:
	if (queued) {
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
				/* Announced: its section is about to run. */
				if (!READ_ONCE(me->claim) && kd_node_abandon(me)) {
					kd_stat_inc(kc, KD_STAT_ABANDON);
					return KD_WAIT_SLEEP;	/* the queue frees the node */
				}
			}
			cpu_relax();
		}
		if (st == KD_N_RESUME) {
			smp_acquire__after_ctrl_dep();
			smp_store_release(&me->state, KD_N_FREE);
			return KD_WAIT_RESUMED;
		}
	} else {
		WRITE_ONCE(me->state, KD_N_HEAD);
	}

	/*
	 * Queue head, usually still waiting for the holder: the time to
	 * measure the queue (see kd_q_queue()). The mode is a flag here, so it
	 * can be set before the lock is ours. The successor's node is written
	 * when the head role is passed on; ask for it now.
	 */
	if (!f->always_deleg && !kd_qs_deleg_mode(q) && kd_probe_enter(kc, me, true))
		kd_mode_set(q, true, true);
	if (READ_ONCE(me->next))
		prefetchw(READ_ONCE(me->next));

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
		if (f->post && !f->post(root, me)) {
			/* Keep the queue mutex; the caller decides how to wait on. */
			kd_q_pass(q, me, true, 0);
			smp_store_release(&me->state, KD_N_FREE);
			return KD_WAIT_SLEEP_HELD;
		}
		deleg = f->always_deleg || kd_qs_deleg_mode(q);
		/* A caller waiting on its own stack (plain mode) never combines. */
		if (!deleg || !offer)
			break;
		xowner = NULL;
		if (!kd_session(q, me, root, f, true, &budget, &deleg, &xowner))
			break;
		have_q = f->keeps_q;
		if (!xowner)
			continue;
		/*
		 * We offered ourselves to the origin that left with the grant
		 * (it may have answered already). Unlike a spin-class holder it
		 * may block; then the offer is withdrawn and this head goes on
		 * as it would without one.
		 */
		for (spins = 1;; spins++) {
			st = READ_ONCE(me->state);
			if (st != KD_N_HWAIT)
				break;
			if (need_resched() ||
			    (!(spins % KD_OWNER_POLL) && !owner_on_cpu(xowner))) {
				if (kd_xhead_settle(root, f, me, KD_N_HBACK)) {
					kd_stat_inc(kc, KD_STAT_XCHG_RETRACT);
					break;
				}
				continue;	/* the holder was faster */
			}
			cpu_relax();
		}
		if (READ_ONCE(me->state) == KD_N_HBACK) {
			WRITE_ONCE(me->state, KD_N_HEAD);
			continue;
		}
		/* Taken over: an ordinary queued waiter behind the new head. */
		have_q = false;
		queued = true;
		goto again;
	}
	if (f->set_owner)
		f->set_owner(root, current);
	if (f->release)
		f->release(root);
	kd_q_pass(q, me, true, 0);
	smp_store_release(&me->state, KD_N_FREE);
	return KD_WAIT_LOCAL;
sleep:
	kd_q_pass(q, me, true, 0);
	smp_store_release(&me->state, KD_N_FREE);
	return KD_WAIT_SLEEP;
}

/*
 * Release side of the role exchange. The caller holds the grant on @root
 * and may have an offer to answer for it: kd_cpu.xcount is nonzero (spin
 * class), kd_cpu.xs_hint names @root, or the release returned the family's
 * mark and the caller took the lock again (sleepable class). @m is the
 * queue mutex for the sleepable class, NULL for the spin class.
 *
 * Takes the head role over from the head that offered itself and serves
 * the queue, that head first. Returns false when the caller still holds
 * the grant and must release it as usual: after the session, or because
 * nothing was taken over (declined, or the offer was withdrawn). Returns
 * true when a section was handed back during the session, so the grant
 * left with that waiter.
 *
 * A session needs task context and a node, and it must not start inside a
 * delegated section (the release was called natively from generated code,
 * whose executor state is live). Otherwise the offer is declined.
 */
bool kd_release_combine(struct kd_qlock *q, struct kd_mutex *m, void *root,
			const struct kd_family *f)
{
	bool sleepable = m != NULL, deleg = true, handed, can, was_busy;
	struct kd_node *me = NULL, *c;
	unsigned int budget = 0;
	struct kd_cpu *kc;

	preempt_disable();
	kc = this_cpu_ptr(&kd_cpu);
	can = static_branch_likely(&kd_delegation) && in_task() &&
	      !READ_ONCE(kc->task) && kc->depth < KD_MAX_DEPTH;
	if (can) {
		if (sleepable) {
			me = kd_mnode_alloc(kc);
		} else if (kd_nr_nodes(kc) < KD_MAX_NODES) {
			int idx = kd_nr_nodes(kc)++;

			barrier();
			me = &kc->nodes[idx];
			kd_node_init(me, smp_processor_id(), idx);
		}
		can = me != NULL;
	}
	c = kd_xhead_settle(root, f, NULL, can ? KD_N_WAIT : KD_N_HBACK);
	if (c && !sleepable)
		kc->xcount--;
	if (!c || !can) {
		if (me && sleepable)
			smp_store_release(&me->state, KD_N_FREE);
		else if (me)
			kd_nr_nodes(kc)--;
		if (c)
			kd_stat_inc(kc, KD_STAT_XCHG_DECLINED);
		preempt_enable();
		return false;
	}
	kd_stat_inc(kc, KD_STAT_XCHG_TAKEN);

	/* We are the queue head now, in front of the head that offered. */
	me->entry = NULL;
	me->nid = numa_node_id();
	WRITE_ONCE(me->state, KD_N_HEAD);
	WRITE_ONCE(me->next, c);
	if (sleepable)
		WRITE_ONCE(m->owner, current);
	/* As during any session: this CPU must not publish meanwhile. */
	was_busy = kc->busy;
	kc->busy = 1;

	handed = kd_session(q, me, root, f, sleepable, &budget, &deleg, NULL);

	kc->busy = was_busy;
	if (f->release)
		f->release(root);
	kd_q_pass(q, me, sleepable, deleg ? KD_N_HEAD_D : KD_N_HEAD);
	if (sleepable)
		smp_store_release(&me->state, KD_N_FREE);
	else
		kd_nr_nodes(kc)--;
	preempt_enable();
	return handed;
}

/* ---- init ------------------------------------------------------------------- */

unsigned long kd_stat_sum(int stat)
{
	unsigned long sum = 0;
	int cpu;

	for_each_possible_cpu(cpu) {
		sum += per_cpu_ptr(&kd_cpu, cpu)->stat[stat];
		if (stat == KD_STAT_PLAIN)
			sum += per_cpu_ptr(&kd_cpu, cpu)->nodes[0].nplain;
	}
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
