/* SPDX-License-Identifier: GPL-2.0 */
/*
 * kdlock internals: continuation packet, queue nodes, per-CPU state and the
 * MCS queue primitives shared by all four lock families.
 *
 * Model
 * -----
 * A lock is in plain mode or in delegation mode (kd_core.c, "adaptive
 * delegation"). In plain mode a contended caller waits as on the native
 * lock, on its own stack. The rest of this comment is delegation mode.
 *
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
 *     lock. Nothing is replayed. C then either waits for the lock like any
 *     queue head, or offers itself as a waiter that W serves when it
 *     releases (kd_core.c, "role exchange").
 */
#ifndef KD_INTERNAL_H
#define KD_INTERNAL_H

#include <linux/kernel.h>
#include <linux/percpu.h>
#include <linux/sched.h>
#include <linux/preempt.h>
#include <linux/jump_label.h>
#include <asm/rmwcc.h>
#include <linux/hash.h>
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
	/*
	 * Spin-class locks this continuation was handed back with whose
	 * combiner offered itself to the origin (role exchange). The origin
	 * moves it to kd_cpu.xcount when it resumes.
	 */
	u8 xoffers;
	void *jit_resume;		/* generated code to continue at after KD_STOP_DONE */
	void *roots[KD_MAX_ROOTS];
	/*
	 * Sleepable-class lock this continuation was handed back with whose
	 * combiner offered itself (role exchange); becomes kd_cpu.xs_hint.
	 */
	void *xs_root;
	/*
	 * Preemptible-RCU read-side sections the continuation is inside right
	 * now. Whoever executes it holds that many itself, and the origin
	 * brings its own count in line when it resumes (kd_rcu_sync()).
	 */
	int rcu_depth;
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
	KD_N_HEAD_D,		/* spin class: promoted, lock is in delegation mode */
	KD_N_HWAIT,		/* queue head offering itself to the lock holder (role exchange) */
	KD_N_HBACK,		/* that offer was declined or withdrawn: head as before */
};

struct kd_node {
	struct kd_node	*next;
	u32		state;
	u16		tail;		/* this node's id in kd_qlock.tail encoding */
	u16		nid;		/* NUMA node of the waiting CPU (published nodes only) */
	struct kd_regs	*regs;		/* valid while ->entry is set */
	void		*entry;		/* generated code for the waiter's section; NULL: not delegable */
	/*
	 * In nodes[0] only: the per-CPU state every contended spin-class
	 * caller touches. It sits in the node's own line, where the native
	 * queued spinlock keeps its node count: the count is the first thing a
	 * contended caller reads and the last it writes, which brings the node
	 * line in before the queue needs it and takes it back afterwards. With
	 * the count in a line of its own, the plain path measured 4 to 12%
	 * below Native at 3 to 5 workers. The rest is here because it is
	 * written at those same two moments, so the plain path dirties no line
	 * the native lock does not.
	 */
	int		count;		/* spin-class nodes of this CPU in use (LIFO) */
	unsigned long	nplain;		/* KD_STAT_PLAIN, spin class */
	struct kd_qlock	*mode_q;	/* lock this CPU last waited for ... */
	bool		mode_deleg;	/* ... and the mode it was in (kd_mode_note()) */
} ____cacheline_aligned_in_smp;

#define KD_MAX_NODES	4

/* Spin-class nodes of CPU state @kc in use; see struct kd_node. */
#define kd_nr_nodes(kc)	((kc)->nodes[0].count)

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
	/* Why sessions stopped before the queue was empty or the budget spent. */
	KD_STAT_STOP_PLAIN,	/* next waiter has no generated code */
	KD_STAT_STOP_RESCHED,	/* the combiner's CPU is wanted elsewhere */
	KD_STAT_STOP_HANDOFF,	/* a parked mutex/rwsem waiter asked for the lock */
	KD_STAT_STOP_CTX,	/* next waiter's IRQ/BH state cannot be honored here */
	KD_STAT_STOP_BUDGET,	/* kd_batch executions reached */
	/* Sleepable families: how waiting ended up off the queue. */
	KD_STAT_NO_SPIN,	/* did not queue: owner off CPU or resched pending */
	KD_STAT_ABANDON,	/* queued waiter withdrew to sleep */
	KD_STAT_HEAD_SLEEP,	/* queue head gave up spinning for the lock */
	KD_STAT_PARKED,		/* schedule() calls of parked waiters */
	KD_STAT_HANDOFF,	/* releases that handed ownership to a parked waiter */
	/* Adaptive mode (kd_core.c, "adaptive delegation"). */
	KD_STAT_MODE_ENTER,	/* a queue head switched its lock to delegation mode */
	KD_STAT_MODE_EXIT,	/* a combiner switched its lock back to plain mode */
	/* Role exchange after a handback. */
	KD_STAT_XCHG_OFFER,	/* combiners that offered themselves to the new holder */
	KD_STAT_XCHG_TAKEN,	/* releases that took the head role over */
	KD_STAT_XCHG_DECLINED,	/* releases that could not and gave it back */
	KD_STAT_XCHG_RETRACT,	/* offers withdrawn because the holder stopped running */
	KD_STAT_NR,
};

/*
 * A cache line together with the line the adjacent-line prefetcher fetches
 * with it. Whatever other CPUs write (queue nodes, the packet) is kept in
 * blocks of this size apart from what only this CPU writes; otherwise a
 * remote access to a node drags this CPU's own hot line along (measured on
 * the bench objects, see bench/kd_bench.c).
 */
#define KD_BLOCK	128

/*
 * Per-CPU state. The first fields are read and written by kd_entry.S and by
 * generated code through %gs; their offsets are fixed in kd_asm.h.
 */
struct kd_cpu {
	/* ---- block 0: this CPU only ---- */
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
	/* C only. */
	u32		anc;		/* outer roots of the running section (generated code reads it) */
	int		depth;		/* sections this CPU is executing, nested */
	/*
	 * Plain queue heads since boot, for sampling. Not in the node line:
	 * it is written by a head that was just promoted, when that line is
	 * shared with its neighbours again, and a store that waits for a line
	 * holds up every later store of this CPU, the lock handover included
	 * (measured: 5 to 15% of the plain rate at 3 to 5 workers).
	 */
	u32		probe;
	/*
	 * Spin-class locks the task on this CPU holds for which a queue head
	 * waits to be taken over (role exchange). A spin-class holder cannot
	 * leave its CPU, so its release finds out here, without a look at the
	 * lock word before the release.
	 */
	u32		xcount;
	/*
	 * Sleepable-class lock the task that last resumed here holds with such
	 * an offer. Only a hint: that task may have moved on, and then its
	 * release finds the offer by the mark in the lock word instead.
	 */
	void		*xs_hint;

	/* ---- the combiner that serves this CPU reads and writes this ---- */
	struct kd_regs	regs __aligned(KD_BLOCK);	/* this CPU's own packet while it waits */

	/* ---- other CPUs link and promote these ---- */
	struct kd_node	nodes[KD_MAX_NODES] __aligned(KD_BLOCK);
	struct kd_node	mnodes[KD_MAX_NODES] __aligned(KD_BLOCK);	/* sleepable class, FREE-state allocated */

	/* ---- this CPU only ---- */
	unsigned long	stat[KD_STAT_NR] __aligned(KD_BLOCK);
} __aligned(KD_BLOCK);

DECLARE_PER_CPU_ALIGNED(struct kd_cpu, kd_cpu);
DECLARE_STATIC_KEY_FALSE(kd_delegation);
extern unsigned int kd_batch;
extern bool kd_numa;
extern bool kd_adapt;
extern unsigned int kd_deleg_enter, kd_deleg_enter_sleep, kd_deleg_exit;
extern unsigned int kd_xchg;

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
 * @always_deleg: the lock is never in plain mode (rwlock, rwsem). There a
 *		session saves more than cache transfers: the writers it serves
 *		share one wait for the readers to leave, so delegation pays
 *		off with a single queued writer.
 */
struct kd_family {
	bool (*post)(void *root);
	void (*release)(void *root);
	void (*set_owner)(void *root, struct task_struct *t);
	/*
	 * Sleepable class: set or clear the mark that tells the holder's
	 * release about a waiting offer (role exchange, kd_core.c). It is a
	 * bit of the word the release changes atomically, so the release
	 * learns it from the value that operation returns. The spin class
	 * needs none: see kd_cpu.xcount.
	 */
	void (*xflag)(void *root, bool set);
	bool keeps_q;
	bool always_deleg;
};

/* kd_entry.S */
void kd_jit_enter(struct kd_regs *regs, void *code);
void kd_jit_exit(void);

/* kd_core.c */
int kd_wait_spin(struct kd_qlock *q, void *root, const struct kd_family *f,
		 struct kd_regs *nested, void *entry);
int kd_wait_sleepable(struct kd_mutex *m, void *root, const struct kd_family *f,
		      struct kd_regs *nested, void *entry, bool offer);
void kd_finish_resume(int pin);
void kd_q_lock_plain(struct kd_qlock *q);
bool kd_q_queue(struct kd_qlock *q, bool probe);
bool kd_q_lock_slow(struct kd_qlock *q, unsigned long site);
bool kd_can_offer(unsigned long rip);
bool kd_release_combine(struct kd_qlock *q, struct kd_mutex *m, void *root,
			const struct kd_family *f);
void kd_release_decline(void *root, const struct kd_family *f);
void kd_unpin(void);
unsigned long kd_stat_sum(int stat);

/*
 * C functions reached only from the stubs in kd_entry.S.
 *
 * *_slow: contended acquisition on the caller's own stack, as the native
 * lock would do it. Spin class (kd_q_lock_slow() for the spinlock, whose
 * queue word is the lock): true means the lock is held, false means the
 * caller should publish its continuation (the stub then calls *_wait on
 * the wait stack). Sleepable class: 0 or -EINTR, or KD_SLOW_OFFER with
 * preemption left disabled for the stub's offer path.
 */
int kd_spin_wait(struct kd_spinlock *l);
void kd_spin_lock_plain(struct kd_spinlock *l);
bool kd_write_lock_slow(struct kd_rwlock *rw, unsigned long site);
int kd_write_wait(struct kd_rwlock *rw);
void kd_write_lock_plain(struct kd_rwlock *rw);
int kd_mutex_lock_slow(struct kd_mutex *m, unsigned long site);
int kd_mutex_lock_slow_interruptible(struct kd_mutex *m, unsigned long site);
int kd_mutex_lock_slow_killable(struct kd_mutex *m, unsigned long site);
int kd_mutex_lock_slow_io(struct kd_mutex *m, unsigned long site);
int kd_mutex_wait(struct kd_mutex *m);
int kd_mutex_lock_sleep(struct kd_mutex *m, int why);
int kd_mutex_lock_sleep_interruptible(struct kd_mutex *m, int why);
int kd_mutex_lock_sleep_killable(struct kd_mutex *m, int why);
int kd_mutex_lock_sleep_io(struct kd_mutex *m, int why);
int kd_down_write_slow(struct kd_rwsem *sem, unsigned long site);
int kd_down_write_slow_killable(struct kd_rwsem *sem, unsigned long site);
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
struct kd_ww_wait;
bool kd_mutex_trylock_as(struct kd_mutex *m, struct task_struct *t);
int kd_mutex_sleep(struct kd_mutex *m, unsigned int state, struct kd_ww_wait *ww);
bool kd_mutex_can_spin(struct kd_mutex *m);

/* kd_ww_mutex.c: deadlock avoidance hooks for a parked ww waiter. */
struct kd_ww_wait {
	struct kd_ww_mutex	*lock;
	struct ww_acquire_ctx	*ctx;
};
bool kd_ww_must_back_off(struct kd_ww_wait *ww);
void kd_mutex_wake_matching(struct kd_mutex *m,
			    bool (*fn)(struct ww_acquire_ctx *waiter, void *arg),
			    void *arg);

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

#define KD_PENDING_LOOPS	(1 << 9)	/* bound on waiting for pending -> locked */

static __always_inline u16 kd_tail(int cpu, int idx)
{
	return ((cpu + 1) << 2) | idx;
}

static __always_inline struct kd_node *kd_node_of(u16 tail, bool sleepable)
{
	struct kd_cpu *kc = per_cpu_ptr(&kd_cpu, (tail >> 2) - 1);

	return sleepable ? &kc->mnodes[tail & 3] : &kc->nodes[tail & 3];
}

/*
 * Lock byte by cmpxchg, regardless of a queue. Only the sleepable class
 * takes its lock this way (mutex: parked waiters, the queue head and new
 * callers compete). The spin class never does; see kd_q_head_take().
 */
static __always_inline bool kd_q_trylock(struct kd_qlock *q)
{
	return !READ_ONCE(q->locked) && cmpxchg(&q->locked, 0, 1) == 0;
}

/* Spin class: succeeds only if the lock is free and nobody waits. */
static __always_inline bool kd_q_trylock_fifo(struct kd_qlock *q)
{
	int old = 0;

	return atomic_try_cmpxchg_acquire(&q->val, &old, KD_Q_LOCKED);
}

/* The same after a look: no locked instruction while the lock is not free. */
static __always_inline bool kd_q_trylock_fifo_read(struct kd_qlock *q)
{
	return !atomic_read(&q->val) && kd_q_trylock_fifo(q);
}

static __always_inline void kd_q_unlock(struct kd_qlock *q)
{
	smp_store_release(&q->locked, 0);
}

/* Set the pending bit; returns the word as it was (x86: one locked bts). */
static __always_inline u32 kd_q_fetch_set_pending(struct kd_qlock *q)
{
	u32 val;

	val = GEN_BINARY_RMWcc(LOCK_PREFIX "btsl", q->val.counter, c,
			       "I", KD_QF_SHIFT) * KD_Q_PENDING_VAL;
	val |= atomic_read(&q->val) & ~KD_Q_PENDING_MASK;
	return val;
}

/*
 * Pending waiter of the native queued spinlock: while no queue exists, one
 * contender waits on the lock byte itself. It needs no node, and it takes
 * the lock with a plain store, because nobody else can: the fast path needs
 * the whole word zero and a queue head waits for the pending bit to clear.
 *
 * Returns true with the lock held. Otherwise the caller must queue; *@valp
 * is the last value read.
 */
static __always_inline bool kd_q_pending(struct kd_qlock *q, u32 *valp)
{
	u32 val = atomic_read(&q->val);

	/* A pending waiter is about to take the free lock: let it (bounded). */
	if (val == KD_Q_PENDING_VAL) {
		int cnt = KD_PENDING_LOOPS;

		val = atomic_cond_read_relaxed(&q->val,
					       (VAL != KD_Q_PENDING_VAL) || !cnt--);
	}
	*valp = val;
	if (val & ~KD_Q_LOCKED_MASK)
		return false;

	val = kd_q_fetch_set_pending(q);
	if (unlikely(val & ~KD_Q_LOCKED_MASK)) {
		/* Somebody queued, or was pending first: undo and queue. */
		if (!(val & KD_Q_PENDING_MASK))
			WRITE_ONCE(q->pending, 0);
		*valp = val;
		return false;
	}
	if (val & KD_Q_LOCKED_MASK)
		smp_cond_load_acquire(&q->locked, !VAL);
	/*
	 * Pending to locked in one store. The mode bit of the previous holder
	 * is kept: a pending waiter says nothing about the queue depth, and
	 * dropping the bit would make the waiters that arrive during this
	 * hold queue without their continuation in the middle of a
	 * delegating phase.
	 */
	WRITE_ONCE(q->locked_pending, KD_Q_LOCKED | (val & KD_Q_DELEG));
	return true;
}

/*
 * Remember the mode this CPU found the spin-class lock @q in: what a
 * contended caller goes by while the lock byte is momentarily empty. One
 * lock per CPU is enough; a caller that alternates between contended
 * locks just starts each wait in plain mode. Preemption is off.
 */
static __always_inline void kd_mode_note(struct kd_qlock *q, bool deleg)
{
	struct kd_node *n0 = &raw_cpu_ptr(&kd_cpu)->nodes[0];

	if (n0->mode_q != q || n0->mode_deleg != deleg) {
		n0->mode_q = q;
		n0->mode_deleg = deleg;
	}
}

/*
 * Is the spin-class word @q, last read as @val, in delegation mode? The
 * holder says so in the lock byte. Between a release and the next head
 * taking the lock the byte is empty, and that is when a waiter that was
 * just served comes back; it goes by what it saw last time. Nothing else
 * is read here: any look at the queue would cost this caller a cache miss
 * that the native lock does not have.
 */
static __always_inline bool kd_q_deleg_mode(struct kd_qlock *q, u32 val)
{
	struct kd_node *n0;

	if (!READ_ONCE(kd_adapt))
		return true;
	if (val & KD_Q_LOCKED_MASK)
		return val & KD_Q_DELEG;
	n0 = &raw_cpu_ptr(&kd_cpu)->nodes[0];
	return n0->mode_q == q && n0->mode_deleg;
}

/* Sleepable class: the mode is a flag that outlives single holds. */
static __always_inline bool kd_qs_deleg_mode(struct kd_qlock *q)
{
	return !READ_ONCE(kd_adapt) || (READ_ONCE(q->flags) & KD_QF_DELEG);
}

/*
 * Append @n. Returns its predecessor, in which case @n must wait for a
 * state change, or NULL if @n is the queue head. The predecessor's node is
 * only written: reading it first would turn the one cache transfer the
 * native lock pays here into two.
 */
static __always_inline struct kd_node *kd_q_enqueue(struct kd_qlock *q,
						    struct kd_node *n,
						    bool sleepable)
{
	u16 old = xchg(&q->tail, n->tail);
	struct kd_node *prev;

	if (!old)
		return NULL;
	prev = kd_node_of(old, sleepable);
	WRITE_ONCE(prev->next, n);
	return prev;
}

/*
 * Number of waiters linked behind @n, counted up to @limit. Each step reads
 * another waiter's node, so callers sample. For a combiner these are the
 * nodes it is about to serve.
 */
static __always_inline int kd_q_depth(struct kd_node *n, int limit)
{
	int d = 0;

	while (d < limit && (n = READ_ONCE(n->next)))
		d++;
	return d;
}

/*
 * Queue head @me of a spin-class word takes the lock, the way the native
 * queued spinlock does: wait until neither a holder nor a pending waiter
 * is left, then store the lock byte @lv. No atomic operation is needed,
 * because while a queue exists the head is the only possible taker (see
 * kd_q_pending() and kd_q_trylock_fifo()).
 *
 * If @me is also the last waiter, lock and tail are settled in one cmpxchg
 * and @me is out of the queue: returns true. Otherwise @me stays the head
 * and must pass that role on with kd_q_pass().
 */
static __always_inline bool kd_q_head_take(struct kd_qlock *q, struct kd_node *me, u8 lv)
{
	int val = atomic_cond_read_acquire(&q->val, !(VAL & KD_Q_LOCKED_PENDING_MASK));

	if (((u32)val >> KD_Q_TAIL_SHIFT) == me->tail &&
	    atomic_try_cmpxchg_relaxed(&q->val, &val, lv))
		return true;
	WRITE_ONCE(q->locked, lv);
	return false;
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
 * @head_state is what a spin-class successor is promoted with (KD_N_HEAD or
 * KD_N_HEAD_D); the sleepable class keeps its mode in the lock flags.
 */
static __always_inline void kd_q_pass(struct kd_qlock *q, struct kd_node *me,
				      bool sleepable, u32 head_state)
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
			smp_store_release(&succ->state, head_state);
			return;
		}
		if (cmpxchg(&succ->state, KD_N_WAIT, KD_N_HEAD) == KD_N_WAIT)
			return;
		kd_q_detach(q, me, succ);
		smp_store_release(&succ->state, KD_N_FREE);
	}
}

#endif /* KD_INTERNAL_H */
