// SPDX-License-Identifier: GPL-2.0
/*
 * Eras: a reader-writer lock under pressure serves one NUMA node at a time.
 *
 * Writers are delegated, so their sections run on the combiner's CPU, and a
 * session serves its own node first (kd_session()): with writers only, the
 * lock word and the protected data stay in one node. Readers are not
 * delegated. Admitted from every node, each of them writes the reader count
 * from its own CPU and reads the protected data there, and the next writer
 * session has to fetch all of it back. That is why the rw families lose
 * across nodes where the mutex and the spinlock do not. Measured (build #72,
 * 32 workers all on one node against 16 on each of two, rate on two nodes
 * over rate on one): writers only, mutex, rwsem and rwlock alike, 0.95-0.97;
 * rwsem with 20% writes 0.57-0.63 and rwlock 0.57-0.74, which is what the
 * native locks lose there as well (0.61-0.71).
 *
 * So a lock under pressure has an era: the node whose callers it serves. A
 * caller of another node that finds the lock in use waits before it touches
 * the lock at all, until the era is its node's. When its wait runs out it
 * takes the era over for its node, and the callers of the node that had it
 * wait in turn. The lock's lines then cross between the nodes once per era
 * instead of once per section. TCLocks gets the same from its queue, which
 * holds readers as well and is served one socket at a time.
 *
 * The era is advisory. It never admits a caller the lock word would not,
 * and a caller that ignores it is only slower. What keeps it from costing
 * where it cannot gain:
 *  - Pressure. There is an era only while a writer that reaches the queue
 *    head keeps finding company: readers in the lock, callers queued behind
 *    it (kd_rw_era_writer()). A lock that is merely shared by two nodes is
 *    left alone; so are writers without readers, for which the NUMA order
 *    inside the session already does the job.
 *  - Short read sections. With long ones the readers' parallelism is worth
 *    more than the lines. The queue head measures how long the readers it
 *    found take to leave (the drain); the average must stay under
 *    kd_rw_era_drain_ns.
 *  - Without writer sessions that meet these conditions there is no era:
 *    a queue head only starts or renews one, and its stamp runs out after
 *    a tick.
 *  - The lock's time is divided between the nodes by the number of their
 *    callers (kd_rw_era_bound()).
 *  - The wait is bounded, at most twice kd_rw_era_ns, and ends at
 *    need_resched(). An rwlock caller with interrupts or bottom halves off,
 *    or outside task context, does not wait at all.
 *
 * What it costs: order. A caller can be passed by callers of the era's node
 * that arrived after it, for at most its bound per acquisition. That is the
 * price of serving one node at a time, and the same kind of bound the NUMA
 * order of the sessions puts on a passed-over writer.
 *
 * The era words are shared between locks by hash, as the lock objects have
 * no room for one; a collision only makes two locks share their era. A word
 * changes when the era changes hands and when its stamp is renewed (once a
 * tick), so the fast paths can load it and waiting callers can poll it. The
 * averages are written by every queue head, the counts of waiting callers by
 * those callers; each lives in a line of its own.
 */
#include <linux/kernel.h>
#include <linux/jiffies.h>
#include <linux/topology.h>
#include <linux/sched.h>
#include <linux/sched/clock.h>
#include <linux/moduleparam.h>
#include <linux/hash.h>
#include "kd_internal.h"

/*
 * The bound of both families. An rwlock waits with preemption off, which
 * would speak for a shorter one, but its wait ends at need_resched() like
 * the rwsem's, and a shorter bound costs twice. Measured (build #79, rwlock,
 * 32 workers, 50 us against 200 us): 3-12% of the rate across nodes, and
 * with 28 workers on one node and 4 on the other the least-served worker
 * got 0.30-0.42 of the most-served one's operations instead of 0.76-0.93,
 * because a short era is used up by the other node's callers leaving.
 */
unsigned int kd_rw_era_ns __read_mostly = 200000;
core_param(kd_rw_era_ns, kd_rw_era_ns, uint, 0644);
unsigned int kd_rw_era_min __read_mostly = 2;
core_param(kd_rw_era_min, kd_rw_era_min, uint, 0644);
static unsigned int kd_rw_era_drain_ns __read_mostly = 5000;
core_param(kd_rw_era_drain_ns, kd_rw_era_drain_ns, uint, 0644);
/* In hundredths of a caller; see kd_rw_era_writer(). */
static unsigned int kd_rw_era_press __read_mostly = 225;
core_param(kd_rw_era_press, kd_rw_era_press, uint, 0644);
/* The last averages a queue head computed, to look at from outside. */
static unsigned int kd_rw_era_dbg_drain, kd_rw_era_dbg_press;
core_param(kd_rw_era_dbg_drain, kd_rw_era_dbg_drain, uint, 0444);
core_param(kd_rw_era_dbg_press, kd_rw_era_dbg_press, uint, 0444);

struct kd_rw_era_word kd_rw_eras[1 << KD_RW_ERA_BITS];

static struct kd_rw_era_avg {
	u32	drain;		/* ns */
	u32	press;		/* callers, fixed point KD_ERA_PRESS_ONE */
} ____cacheline_aligned_in_smp kd_rw_era_avgs[1 << KD_RW_ERA_BITS];

#define KD_ERA_PRESS_ONE	16

/*
 * Callers waiting for their era, by node, and how many there were when the
 * node last took the era over. Written by waiting callers only, in a line
 * of its own: the node that has the era never touches it.
 */
#define KD_ERA_WQ_NODES		4	/* nodes that differ by a multiple share a slot */

static struct kd_rw_era_wq {
	atomic_t	cur[KD_ERA_WQ_NODES];
	u32		last[KD_ERA_WQ_NODES];
} ____cacheline_aligned_in_smp kd_rw_era_wqs[1 << KD_RW_ERA_BITS];

/*
 * How long callers of node slot @mine wait before they take the era from
 * node slot @theirs.
 *
 * With one bound for everybody, two nodes that both keep the lock busy get
 * the same time whatever their numbers, so a node with few callers gets
 * several times its share per caller. Measured (build #77, 32 workers as 24
 * and 8, 20% writes): least over most operations per worker 0.39-0.47, from
 * 0.87-0.96 without eras; as 28 and 4 on the rwlock 0.23, where the 28 lost
 * about a quarter of their rate each while the total rose by 30%.
 *
 * So the time is divided by the number of callers: of twice @max_ns, the
 * node that has the era gets the share of its callers (as many as waited
 * when it took the era) among them and the ones waiting now. Equal numbers
 * give @max_ns each.
 *
 * Never under a quarter of @max_ns. An era starts with the lock still full
 * of the other node's callers that were past the wait already, and the new
 * node gets nothing done until they have left. Measured with an eighth
 * (build #78, 31 workers and 1): the one worker did 24000 operations per
 * second on the rwlock where each of the 31 did 141000, and 55000 against
 * 216000 on the rwsem.
 */
static __always_inline u64 kd_rw_era_bound(struct kd_rw_era_wq *wq, int mine, int theirs,
					   unsigned int max_ns)
{
	u64 w = atomic_read(&wq->cur[mine]), t = READ_ONCE(wq->last[theirs]);

	if (!t || mine == theirs)
		return max_ns;
	return max_t(u64, 2ULL * max_ns * t / (t + w), max_ns / 4);
}

/*
 * Wait for this node's era without touching the lock. The era word is
 * quiet, so polling it costs the node that has the era nothing, and a
 * waiter never looks at the lock itself: that would take the lock's line
 * across, which is what the era is there to prevent.
 *
 * The wait ends when the era is this node's or has run out, at
 * need_resched(), or when the bound has passed (kd_rw_era_bound(), at most
 * twice @max_ns); then the era is taken over. A change of hands between
 * other nodes starts the bound again, so that several waiting nodes do not
 * take the era from each other at once.
 *
 * Tried and removed (builds #77 and #78): one look at the lock per waiter,
 * each CPU at a time of its own, taking the era over if the lock was idle.
 * It ended the eras of a node with few callers after a few microseconds,
 * for which that node had waited nearly twice the bound, and with CPU
 * numbers deciding the time of the look the node with the lower numbers
 * modulo 32 kept winning (4 workers on each node, rwsem with 20% writes:
 * 1885000 operations per second per worker on one node, 168000 on the
 * other). The division by callers does what the look was for.
 */
noinline void kd_rw_era_wait(const void *lock, unsigned int max_ns)
{
	struct kd_rw_era_wq *wq = &kd_rw_era_wqs[hash_ptr((void *)lock, KD_RW_ERA_BITS)];
	u32 *era = kd_rw_era(lock), seen = 0, v;
	struct kd_cpu *kc = raw_cpu_ptr(&kd_cpu);
	/* The task may move while it waits (rwsem): the slot is the one it started in. */
	int mine = kd_era_node() % KD_ERA_WQ_NODES, i;
	u64 start = 0;

	kd_stat_inc(kc, KD_STAT_ERA_GATE);
	atomic_inc(&wq->cur[mine]);
	for (i = 0;; i++) {
		v = READ_ONCE(*era);
		if (!v || KD_ERA_NODE(v) == kd_era_node() || !kd_era_fresh(v))
			goto out;
		if (need_resched())
			goto out;
		if (KD_ERA_NODE(v) != seen) {
			seen = KD_ERA_NODE(v);
			start = 0;
		}
		if (!(i & 63)) {
			u64 now = local_clock();

			if (!start)
				start = now;
			else if (now - start > kd_rw_era_bound(wq, mine, seen % KD_ERA_WQ_NODES,
							       max_ns))
				break;
		}
		cpu_relax();
	}
	/* Lost races only shorten or lengthen an era. */
	kd_stat_inc(kc, KD_STAT_ERA_CLAIM);
	WRITE_ONCE(wq->last[mine], atomic_read(&wq->cur[mine]));
	WRITE_ONCE(*era, (v & ~0xffU) | kd_era_node());
out:
	atomic_dec(&wq->cur[mine]);
}

/*
 * Queue head that has just taken the write side. @nr readers were in when
 * it closed the read side, and they took @drain_ns to leave; @queued callers
 * were queued behind it (counted up to KD_POST_DEPTH). Update the averages
 * and decide whether the lock has an era: one started for this node if
 * there is none, otherwise left with the node that has it, whose stamp is
 * renewed.
 *
 * Pressure is the company the writer found, @nr + @queued, averaged over
 * the last sessions; an era needs kd_rw_era_press hundredths of a caller.
 * The default of 2.25 cannot be reached by two callers in all, and by a few
 * only if most of them are at the lock at once. Measured with the readers
 * alone and a threshold of a quarter reader (build #78, one worker on each
 * node, rwsem with 20% writes): 0.72 of the rate without eras, because every
 * meeting of the two then cost a wait.
 */
void kd_rw_era_writer(const void *lock, long nr, int queued, u64 drain_ns)
{
	struct kd_rw_era_avg *a = &kd_rw_era_avgs[hash_ptr((void *)lock, KD_RW_ERA_BITS)];
	u32 *era = kd_rw_era(lock), old = READ_ONCE(*era), v;
	u32 d = READ_ONCE(a->drain), p = READ_ONCE(a->press);

	if (nr) {
		d = d - d / 8 + (u32)min_t(u64, drain_ns, 1000000) / 8;
		WRITE_ONCE(a->drain, d);
	}
	p = p - p / 8 + (u32)min_t(long, nr + queued, 255) * KD_ERA_PRESS_ONE / 8;
	WRITE_ONCE(a->press, p);
	if (!(p & 7)) {				/* now and then */
		kd_rw_era_dbg_drain = d;
		kd_rw_era_dbg_press = p;
	}

	/*
	 * Only start or renew. An era the conditions no longer support is
	 * left to run out (one or two ticks): clearing it here would store
	 * to the word every time the averages cross a threshold, and every
	 * reader's fast path loads that word (measured, #75: rwsem 1% writes
	 * on one node, 16 workers, -5% when clearing).
	 */
	if (!READ_ONCE(kd_rw_era_ns) || d >= READ_ONCE(kd_rw_era_drain_ns) ||
	    p * 100 < READ_ONCE(kd_rw_era_press) * KD_ERA_PRESS_ONE)
		return;
	v = (((u32)jiffies & KD_ERA_STAMP_MAX) << 8) |
	    (kd_era_fresh(old) ? KD_ERA_NODE(old) : kd_era_node());
	/* Within one tick the word stays as it is: no store, no invalidation. */
	if (v != old) {
		WRITE_ONCE(*era, v);
		if (!kd_era_fresh(old))
			kd_stat_inc(raw_cpu_ptr(&kd_cpu), KD_STAT_ERA_START);
	}
}
