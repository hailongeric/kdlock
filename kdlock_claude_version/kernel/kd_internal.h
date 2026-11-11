/* SPDX-License-Identifier: GPL-2.0 */
/*
 * kdlock internals: continuation packet, queue nodes, per-CPU state and the
 * MCS queue primitives shared by all four lock families.
 *
 * Model
 * -----
 * A contended caller W of a delegable lock API records its continuation
 * (callee-saved registers, stack pointer, return address) in its CPU's
 * packet, moves to a per-CPU wait stack and queues. The caller's own stack
 * below the lock call is then unused.
 *
 * The queue head acquires the lock and becomes the combiner C. For each
 * queued waiter that has generated code for its call site, C switches its
 * stack pointer to W's stack and runs a relocated copy of W's critical
 * section. In that copy only task-identity accesses (current, stack canary)
 * are redirected to W; everything else, including per-CPU data, belongs to
 * the CPU that physically runs the code.
 *
 * The copy leaves generated code when it
 *   - reaches the release of the session lock: W's section is complete, W
 *     resumes after the release call, C keeps the lock for the next waiter;
 *   - reaches anything only W may execute (untranslated target, sleeping
 *     call, instruction with a fault fixup, ...): C records the exact
 *     pre-instruction state, W resumes there natively and now owns the
 *     lock; C waits for the lock like any queue head. Nothing is replayed.
 */
#ifndef KD_INTERNAL_H
#define KD_INTERNAL_H

#include <linux/kernel.h>
#include <linux/percpu.h>
#include <linux/sched.h>
#include <linux/preempt.h>
#include <linux/jump_label.h>
#include <kdlock/kd_types.h>
#include <kdlock/kd_api.h>
#include <kdlock/kd_uapi.h>
#include "kd_asm.h"

struct kd_site;

#define KD_MAX_ROOTS	4	/* session locks one continuation may be nested under */
#define KD_MAX_DEPTH	3	/* sessions one CPU may have open at once */

/*
 * Continuation packet: the one canonical execution state of an origin
 * task while its section is delegated. Exactly one participant advances
 * it at a time: the origin before it queues, the combiner while the node
 * is claimed, the origin again after RESUME.
 */
struct kd_regs {
	unsigned long rax, rbx, rcx, rdx, rsi, rdi, rbp, rsp;
	unsigned long r8, r9, r10, r11, r12, r13, r14, r15;
	unsigned long rip;		/* next source instruction */
	unsigned long rflags;		/* includes the origin's logical IF */
	struct task_struct *task;	/* origin */
	unsigned long canary;
	unsigned long stack_top;
	struct kd_site *site;		/* root call site, for accounting and learning */
	long pc_delta;			/* preempt count the origin must add on resume */
	u32 bh_off;			/* origin had softirqs disabled when it queued */
	/*
	 * Nested delegation. Each executor that runs this continuation pushes
	 * the lock it runs it for. A deeper executor that meets the release
	 * of an outer root marks it instead of releasing: that lock is still
	 * held by the outer combiner's session.
	 */
	u8 nroots;
	u8 released;			/* bit i: roots[i] was released by the continuation */
	u8 stop;			/* how the last executor left it: KD_STOP_* */
	u8 __pad;
	void *jit_resume;		/* generated code to continue at after KD_STOP_DONE */
	void *roots[KD_MAX_ROOTS];
};

enum {
	KD_STOP_DONE = 1,	/* reached the release of the executor's root */
	KD_STOP_HANDBACK,	/* must continue natively on the origin */
};

/* Queue node states. */
enum {
	KD_N_FREE = 0,		/* sleepable pool only: node may be allocated */
	KD_N_WAIT,		/* queued, not yet claimed */
	KD_N_RUN,		/* sleepable only: claimed by the combiner */
	KD_N_HEAD,		/* promoted: acquire the lock yourself */
	KD_N_RESUME,		/* packet holds the state to continue from */
	KD_N_ABANDON,		/* sleepable only: waiter left to sleep; skip and free */
};

struct kd_node {
	struct kd_node	*next;
	u32		state;
	u16		tail;		/* this node's id in kd_qlock.tail encoding */
	u16		nid;		/* NUMA node of the waiting CPU */
	struct kd_regs	*regs;		/* NULL: this waiter cannot be delegated */
	void		*entry;		/* generated code for the waiter's section */
} ____cacheline_aligned_in_smp;

#define KD_MAX_NODES	4

enum {
	KD_STAT_SESSIONS,	/* combining sessions that executed at least one waiter */
	KD_STAT_DELEGATED,	/* sections completed in generated code */
	KD_STAT_HANDBACK,	/* sections returned to their origin unfinished */
	KD_STAT_HANDBACK_PINNED,/* ... while the section had preemption disabled */
	KD_STAT_NESTED_LOCAL,	/* contended inner locks the executor obtained itself */
	KD_STAT_NESTED_DELEGATED,/* inner sections advanced by the inner lock's combiner */
	KD_STAT_OFFERED,	/* waiters queued with generated code */
	KD_STAT_PLAIN,		/* waiters queued without */
	KD_STAT_NUMA_DEFERRED,	/* waiters of another node passed over by a session */
	KD_STAT_NR,
};

/*
 * Per-CPU state. The first fields are read and written by kd_entry.S and by
 * generated code through %gs; their offsets are fixed in kd_asm.h.
 */
struct kd_cpu {
	/* Valid while this CPU executes a delegated section. */
	struct task_struct *task;	/* origin task; NULL when not executing */
	unsigned long	canary;
	unsigned long	stack_top;
	void		*root;		/* lock whose release ends the section */
	struct kd_regs	*cur;		/* packet being executed */
	unsigned long	host_rsp;	/* executor stack while in generated code */
	unsigned long	tmp;
	/* Written by the exit stub that left generated code. */
	unsigned long	exit_ip;
	unsigned long	resume;
	unsigned long	aux;
	u32		exit_code;
	/*
	 * Nonzero: this CPU may not publish a continuation now (packet or
	 * wait stack in use, or a session is running). Set with a single
	 * non-locked bts so interrupts on this CPU observe it atomically.
	 */
	u32		busy;
	void		*wait_stack;	/* top of the per-CPU wait stack */
	struct kd_regs	regs;		/* this CPU's own packet while it waits */

	/* C only. */
	u32		anc;		/* outer roots of the running section (generated code reads it) */
	int		depth;		/* sections this CPU is executing, nested */
	int		nr_nodes;	/* spin-class nodes in use (LIFO) */
	struct kd_node	nodes[KD_MAX_NODES];
	struct kd_node	mnodes[KD_MAX_NODES];	/* sleepable class, FREE-state allocated */
	unsigned long	stat[KD_STAT_NR];
};

DECLARE_PER_CPU_ALIGNED(struct kd_cpu, kd_cpu);
DECLARE_STATIC_KEY_FALSE(kd_delegation);
extern unsigned int kd_batch;
extern bool kd_numa;

#define kd_stat_inc(kc, s)	((kc)->stat[s]++)

/*
 * Family glue used by the generic wait/session code.
 *
 * @post:	called by the queue head once it holds the queue lock, to
 *		obtain the rest of the grant (writer bit). Returns false if
 *		that would require sleeping (rwsem only).
 * @release:	the queue lock is only a wait lock for this family; drop it
 *		when the session ends.
 * @set_owner:	record the logical owner (mutex).
 * @keeps_q:	a handback transfers the grant but not the queue lock.
 */
struct kd_family {
	bool (*post)(void *root);
	void (*release)(void *root);
	void (*set_owner)(void *root, struct task_struct *t);
	bool keeps_q;
};

/* kd_entry.S */
void kd_jit_enter(struct kd_regs *regs, void *code);
void kd_jit_exit(void);

/* kd_core.c */
int kd_wait_spin(struct kd_qlock *q, void *root, const struct kd_family *f,
		 struct kd_regs *nested, void *entry);
int kd_wait_sleepable(struct kd_mutex *m, void *root, const struct kd_family *f,
		      struct kd_regs *nested, void *entry);
void kd_finish_resume(int pin);
void kd_q_lock_plain(struct kd_qlock *q);
void kd_unpin(void);
unsigned long kd_stat_sum(int stat);

/* C functions reached only from the stubs in kd_entry.S. */
int kd_spin_wait(struct kd_spinlock *l);
void kd_spin_lock_plain(struct kd_spinlock *l);
int kd_write_wait(struct kd_rwlock *rw);
void kd_write_lock_plain(struct kd_rwlock *rw);
int kd_mutex_wait(struct kd_mutex *m);
int kd_mutex_lock_sleep(struct kd_mutex *m, int why);
int kd_mutex_lock_sleep_interruptible(struct kd_mutex *m, int why);
int kd_mutex_lock_sleep_killable(struct kd_mutex *m, int why);
int kd_down_write_wait(struct kd_rwsem *sem);
int kd_down_write_sleep(struct kd_rwsem *sem, int why);
int kd_down_write_sleep_killable(struct kd_rwsem *sem, int why);

/*
 * Nested acquisition for the continuation in @r by the CPU executing it.
 * @entry is the generated code following the lock call, or NULL if the
 * continuation may not be published again. Return KD_WAIT_LOCAL (held for
 * the origin), KD_WAIT_RESUMED (another combiner advanced @r) or
 * KD_WAIT_SLEEP (not acquired; the origin must make the call itself).
 */
int kd_spin_nested(struct kd_spinlock *l, struct kd_regs *r, void *entry);
int kd_write_nested(struct kd_rwlock *rw, struct kd_regs *r, void *entry);
int kd_mutex_nested(struct kd_mutex *m, struct kd_regs *r, void *entry);
int kd_down_write_nested(struct kd_rwsem *sem, struct kd_regs *r, void *entry);

/* Entries generated code calls instead of the public ones (kd_entry.S). */
void kd_spin_lock_jit(void);
void kd_spin_lock_irq_jit(void);
void kd_spin_lock_irqsave_jit(void);
void kd_spin_lock_bh_jit(void);
void kd_write_lock_jit(void);
void kd_write_lock_irq_jit(void);
void kd_write_lock_irqsave_jit(void);
void kd_write_lock_bh_jit(void);

/* kd_mutex.c */
bool kd_mutex_trylock_as(struct kd_mutex *m, struct task_struct *t);
int kd_mutex_sleep(struct kd_mutex *m, unsigned int state);
bool kd_mutex_can_spin(struct kd_mutex *m);

/* kd_rwsem.c */
bool kd_down_read_trylock_raw(struct kd_rwsem *sem);
bool kd_down_write_trylock_raw(struct kd_rwsem *sem);

/* kd_image.c */
struct kd_site {
	struct hlist_node hash;
	unsigned long	rip;		/* return address of the root lock call */
	void		*entry;		/* NULL: site known but not delegable now */
	struct kd_image	*img;
	u32		ok, bad;	/* approximate, combiner-updated */
	atomic_t	miss_budget;	/* learning reports left for this image */
	struct rcu_head	rcu;
};

struct kd_site *kd_site_find(unsigned long rip);
void kd_site_request(unsigned long rip);
void kd_site_account(struct kd_site *site, bool done);
void kd_event_push(u32 type, unsigned long site, unsigned long ip, unsigned long target);
long kd_image_ioctl(unsigned int cmd, unsigned long arg);
ssize_t kd_event_read(char __user *buf, size_t len);

/*
 * The task a lock operation is performed for. While a CPU executes a
 * delegated section, natively called lock functions act for the origin.
 */
static inline struct task_struct *kd_logical_current(void)
{
	struct task_struct *t = raw_cpu_read(kd_cpu.task);

	return (t && in_task()) ? t : current;
}

/* ---- queue primitives --------------------------------------------------- */

static __always_inline u16 kd_tail(int cpu, int idx)
{
	return ((cpu + 1) << 2) | idx;
}

static __always_inline struct kd_node *kd_node_of(u16 tail, bool sleepable)
{
	struct kd_cpu *kc = per_cpu_ptr(&kd_cpu, (tail >> 2) - 1);

	return sleepable ? &kc->mnodes[tail & 3] : &kc->nodes[tail & 3];
}

static __always_inline bool kd_q_trylock(struct kd_qlock *q)
{
	return !READ_ONCE(q->locked) && cmpxchg(&q->locked, 0, 1) == 0;
}

/* Fast path for FIFO users: succeeds only with no queue. */
static __always_inline bool kd_q_trylock_fifo(struct kd_qlock *q)
{
	int old = 0;

	return atomic_try_cmpxchg_acquire(&q->val, &old, KD_Q_LOCKED);
}

static __always_inline void kd_q_unlock(struct kd_qlock *q)
{
	smp_store_release(&q->locked, 0);
}

/* The queue head takes the lock; fast paths cannot barge while tail != 0,
 * but pool-overflow and mutex callers can, hence the cmpxchg. */
static __always_inline void kd_q_head_lock(struct kd_qlock *q)
{
	for (;;) {
		smp_cond_load_relaxed(&q->locked, !VAL);
		if (cmpxchg(&q->locked, 0, 1) == 0)
			return;
	}
}

/*
 * Append @n. Returns true if there was a predecessor, in which case @n
 * must wait for a state change; otherwise @n is the queue head.
 */
static __always_inline bool kd_q_enqueue(struct kd_qlock *q, struct kd_node *n,
					 bool sleepable)
{
	u16 old = xchg(&q->tail, n->tail);

	if (!old)
		return false;
	WRITE_ONCE(kd_node_of(old, sleepable)->next, n);
	return true;
}

/*
 * Head @me removes its direct successor @n from the queue and returns the
 * new successor (NULL: @me is the tail again). @n is not written, so the
 * caller may still publish a final state to it afterwards.
 *
 * me->next is cleared before the tail is swung back so that a waiter
 * arriving right after the cmpxchg cannot have its link overwritten.
 */
static __always_inline struct kd_node *kd_q_detach(struct kd_qlock *q,
						   struct kd_node *me,
						   struct kd_node *n)
{
	struct kd_node *succ = READ_ONCE(n->next);

	if (!succ) {
		WRITE_ONCE(me->next, NULL);
		if (cmpxchg(&q->tail, n->tail, me->tail) == n->tail)
			return NULL;
		succ = smp_cond_load_relaxed(&n->next, VAL);
	}
	WRITE_ONCE(me->next, succ);
	return succ;
}

/*
 * Head @me puts the chain @first..@last, which it detached earlier, back
 * directly behind itself.
 *
 * If @me is the tail, the tail moves to @last. last->next is cleared
 * first because a waiter arriving right after that cmpxchg links itself
 * there.
 */
static __always_inline void kd_q_splice_front(struct kd_qlock *q,
					      struct kd_node *me,
					      struct kd_node *first,
					      struct kd_node *last)
{
	struct kd_node *succ = READ_ONCE(me->next);

	WRITE_ONCE(last->next, NULL);
	if (!succ && cmpxchg(&q->tail, me->tail, last->tail) != me->tail)
		succ = smp_cond_load_relaxed(&me->next, VAL);
	if (succ)
		WRITE_ONCE(last->next, succ);
	WRITE_ONCE(me->next, first);
}

/*
 * Head @me leaves the queue: promote the first live successor, or clear the
 * tail. Abandoned sleepable nodes are skipped and returned to their pool.
 */
static __always_inline void kd_q_pass(struct kd_qlock *q, struct kd_node *me,
				      bool sleepable)
{
	struct kd_node *succ;

	for (;;) {
		succ = READ_ONCE(me->next);
		if (!succ) {
			if (cmpxchg(&q->tail, me->tail, 0) == me->tail)
				return;
			succ = smp_cond_load_relaxed(&me->next, VAL);
		}
		if (!sleepable) {
			smp_store_release(&succ->state, KD_N_HEAD);
			return;
		}
		if (cmpxchg(&succ->state, KD_N_WAIT, KD_N_HEAD) == KD_N_WAIT)
			return;
		kd_q_detach(q, me, succ);
		smp_store_release(&succ->state, KD_N_FREE);
	}
}

#endif /* KD_INTERNAL_H */
