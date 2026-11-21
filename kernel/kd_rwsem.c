// SPDX-License-Identifier: GPL-2.0
/*
 * kdlock rwsem.
 *
 * ->count holds the writer bit, a writer-waiting bit and the reader count,
 * as in the rwlock. ->m is a kdlock mutex used as the queue of writers that
 * cannot take the fast path, and of readers that waited too long to keep
 * spinning. Only the task holding ->m ever sleeps on ->count, so ->m.owner
 * names the single task a release may have to wake (KD_RWSEM_NEEDWAKE).
 *
 * Writers are delegable. A writer that reaches the head of ->m takes the
 * writer bit and then, as combiner, keeps the bit and ->m while executing
 * the writers queued behind it. Readers wait outside ->m, registered
 * behind the active writer (kd_down_read_admit()), so they do not end a
 * session; one that falls back to ->m does, as it publishes nothing.
 *
 * Releasing the write side clears the writer bit and wakes the holder of
 * ->m if it sleeps; it never touches ->m. That makes the release identical
 * for a fast-path writer, a combiner after its session and an origin that
 * got its section handed back.
 *
 * Readers always run on their own task.
 *
 * Under pressure from both NUMA nodes the lock serves one node at a time:
 * callers of the other node wait for their era before they touch ->count
 * (kd_era.c). The queue head's post supplies the measurements for it.
 */
#include <linux/kernel.h>
#include <linux/export.h>
#include <linux/sched.h>
#include <linux/sched/signal.h>
#include <linux/sched/clock.h>
#include <linux/moduleparam.h>
#include <linux/rcupdate.h>
#include <linux/preempt.h>
#include <linux/hash.h>
#include "kd_internal.h"

/*
 * How long the writer at the head of the queue spins for the readers to
 * leave before it sleeps holding ->m. Sleeping there is expensive: every
 * writer behind it sees an owner off the CPU and parks too, and they are
 * woken one by one. mmap writers wait like this behind munmap, which
 * downgrades and finishes its unmap as a reader (measured: at the old
 * bound of 1024 pauses the head slept in about one wait out of three and
 * mmap1 with 4 threads ran at a third of Native's rate). The native rwsem
 * spins on a reader-owned lock for a time bound as well.
 */
static unsigned int kd_rwsem_wspin_ns __read_mostly = 50000;
core_param(kd_rwsem_wspin_ns, kd_rwsem_wspin_ns, uint, 0644);

/* How long a reader that missed the fast path waits before it queues on ->m. */
static unsigned int kd_rwsem_rspin_ns __read_mostly = 50000;
core_param(kd_rwsem_rspin_ns, kd_rwsem_rspin_ns, uint, 0644);

/*
 * The era bound of the rwsem (kd_era.c); 0 uses kd_rw_era_ns, the rwlock's,
 * and kd_rw_era_ns=0 switches eras off for both families.
 *
 * Longer than the rwlock's 200 us. An rwsem caller waits for its era with
 * preemption enabled, and an era of the mmap lock is one session of
 * delegated writers of one node: at 200 us it ended after about 136 mmap1
 * sections, and every new era moved the mm's data to the other node.
 * Measured on kdall3 in one boot (3 rounds, the whole kd_rw_era_ns at 200 us,
 * 500 us and 1 ms): will-it-scale mmap1 at 48 / 60 / 64 threads 1.12 / 1.14 /
 * 1.11 times the rate at 200 us with 1 ms, mmap2 1.17 / 1.07 / 1.12, brk1
 * 1.05 / 1.08 / 1.04; the rwsem nano bodies with 20% writes at 48 and 64
 * workers 1.08-1.22 in plain mode and 1.06-1.09 delegated, 1% writes up to
 * 1.19, writers only unchanged within the spread, one node unchanged. The
 * cost is the share of a node with very few callers: with 31 workers on one
 * node and 1 on the other, the least-served worker got 0.68 instead of 0.85
 * of the most-served one's operations (1 line, 20% writes, plain), 0.72
 * instead of 0.94 delegated; at 28+4 it went from 0.49 to 0.86 with 16
 * lines. The rwlock gained nothing (0-2%) and lost that share as well, so
 * it keeps the shorter bound, which also bounds how long it spins with
 * preemption off.
 */
static unsigned int kd_rwsem_era_ns __read_mostly = 1000000;
core_param(kd_rwsem_era_ns, kd_rwsem_era_ns, uint, 0644);

static __always_inline unsigned int kd_rwsem_era_bound(void)
{
	unsigned int ns = READ_ONCE(kd_rwsem_era_ns);

	return ns ? ns : READ_ONCE(kd_rw_era_ns);
}

static __always_inline bool kd_rwsem_readers(long c)
{
	return (c >> KD_RWSEM_RSHIFT) != 0;
}

/*
 * What waiting readers poll instead of ->count.
 *
 * ->count is written by every reader that enters or leaves. A reader that
 * polls it keeps a shared copy of that line, so each of those locked
 * operations first has to take the line away from all the pollers; with
 * many readers waiting, the readers that are in cannot leave quickly and
 * the next writer waits for them (measured, build #56, 20% writes at 64
 * workers: 85 reads per reader phase took about 36 us).
 *
 * A waiting reader therefore polls a phase counter in a line of its own,
 * which is written only when the write side changes hands: when a writer
 * leaves with readers registered behind it, and when a queued writer gets
 * in. A changed counter only says "look at ->count again". The counters
 * are shared between semaphores by hash, as the object has no room for
 * one; a collision costs an extra look. A reader also looks again once in
 * a while without a change, so a missed event only delays it.
 *
 * The counter is written only while a reader waits (->waiters, in the same
 * line, counted by kd_down_read_admit()). Written at every change of the
 * write side, it was a line every writer of a lock took from the one
 * before, readers or not: one of three such lines that a write handover
 * of this rwsem had and the native one has not (the others: the era
 * averages and the queue nodes behind the head, kd_rwsem_post()). fio
 * with N jobs writing one tmpfs file (inode rwsem, writers only) was at
 * 0.82-0.90 of the native kernel without delegation
 * (lkp-macro-20261119-64cpu, section 7). Order: the reader counts itself
 * and then reads the counter and ->count; the writer changes ->count and
 * then reads ->waiters; all four are locked operations or follow one.
 */
#define KD_RWSEM_PHASE_BITS	8

static struct kd_rwsem_phase {
	atomic_t	seq;
	atomic_t	waiters;	/* readers in kd_down_read_admit() */
} ____cacheline_aligned_in_smp kd_rwsem_phases[1 << KD_RWSEM_PHASE_BITS];

static __always_inline struct kd_rwsem_phase *kd_rwsem_phase_of(struct kd_rwsem *sem)
{
	return &kd_rwsem_phases[hash_ptr(sem, KD_RWSEM_PHASE_BITS)];
}

static __always_inline atomic_t *kd_rwsem_phase(struct kd_rwsem *sem)
{
	return &kd_rwsem_phase_of(sem)->seq;
}

static __always_inline void kd_rwsem_phase_change(struct kd_rwsem *sem)
{
	struct kd_rwsem_phase *p = kd_rwsem_phase_of(sem);

	if (atomic_read(&p->waiters))
		atomic_inc(&p->seq);
}

/* Wake the holder of ->m if it sleeps on ->count. */
static void kd_rwsem_wake(struct kd_rwsem *sem)
{
	struct task_struct *t;

	rcu_read_lock();
	t = READ_ONCE(sem->m.owner);
	if (t)
		wake_up_process(t);
	rcu_read_unlock();
}

/*
 * Writer holding ->m: take the writer bit if no reader and no writer is in.
 * Its waiting marks (WWAIT, and HANDOFF if it had to ask for one) go with it.
 */
static __always_inline bool kd_rwsem_write_try(struct kd_rwsem *sem)
{
	long c = atomic_long_read(&sem->count);

	while (!(c & KD_RWSEM_WLOCKED) && !kd_rwsem_readers(c)) {
		if (atomic_long_try_cmpxchg_acquire(&sem->count, &c,
				(c & ~(KD_RWSEM_WWAIT | KD_RWSEM_HANDOFF)) | KD_RWSEM_WLOCKED))
			return true;
	}
	return false;
}

/*
 * Write stealing.
 *
 * The holder of ->m is the only task that may wait for ->count, and when the
 * readers it waits for stay long it sleeps there (KD_RWSEM_NEEDWAKE). From
 * then on the write side used to be reserved for that sleeper: the last
 * reader's release woke it, and until it ran again the lock stood free while
 * every other writer waited behind ->m, asleep as well, since they saw its
 * owner off the CPU. munmap makes this the common case for the mmap lock:
 * it takes the write side, downgrades and unmaps as a reader for
 * milliseconds. A thread whose munmap had just returned then waited for
 * its next mmap behind all the sleeping writers (will-it-scale page_fault3
 * with 16 threads on kdall13: mmap took 1.6 ms on average against 0.15 ms
 * on the native kernel, the threads were blocked 12.8% of the time against
 * 7.7%, and the rate was 0.71 of native's).
 *
 * The native rwsem does not reserve a free lock for a sleeping waiter: a
 * writer that is running takes it, and a waiter that keeps losing asks for a
 * handoff after a few milliseconds. The same here: while the holder of ->m
 * sleeps on ->count, a writer that finds no reader and no writer in takes
 * the writer bit past it, without ->m. Its release wakes the sleeper as any
 * release does while NEEDWAKE is set, and the sleeper tries again. A sleeper
 * that has waited kd_rwsem_handoff_ms sets KD_RWSEM_HANDOFF, after which
 * nobody steals until it has had the lock.
 *
 * Nothing is stolen from a holder of ->m that is awake: it is about to take
 * the lock itself, and in delegation mode it is the combiner the other
 * writers are queued behind. Readers are not affected: WWAIT keeps new
 * ones out as before, and those that register behind a stealing writer
 * enter when it leaves, like behind any writer.
 *
 * kd_rwsem_steal=0 switches it off (for comparisons within one boot).
 */
static unsigned int kd_rwsem_steal __read_mostly = 1;
core_param(kd_rwsem_steal, kd_rwsem_steal, uint, 0644);

static unsigned int kd_rwsem_handoff_ms __read_mostly = 4;
core_param(kd_rwsem_handoff_ms, kd_rwsem_handoff_ms, uint, 0644);

#define KD_RWSEM_NOSTEAL	(KD_RWSEM_WLOCKED | KD_RWSEM_HANDOFF | KD_RWSEM_XHEAD)

static __always_inline bool kd_rwsem_write_steal(struct kd_rwsem *sem)
{
	long c = atomic_long_read(&sem->count);

	while ((c & KD_RWSEM_NEEDWAKE) && !(c & KD_RWSEM_NOSTEAL) && !kd_rwsem_readers(c)) {
		if (atomic_long_try_cmpxchg_acquire(&sem->count, &c, c | KD_RWSEM_WLOCKED)) {
			kd_stat_inc(raw_cpu_ptr(&kd_cpu), KD_STAT_WR_STEAL);
			return true;
		}
	}
	return false;
}

/*
 * A writer that missed the fast path, before it queues: while the holder of
 * ->m sleeps, wait a bounded time for the lock to become free and take it.
 * Returns false at once when the holder of ->m is awake or wants a handoff.
 */
static bool kd_rwsem_steal_wait(struct kd_rwsem *sem)
{
	u64 end = 0;
	int i;

	for (i = 0;; i++) {
		long c = atomic_long_read(&sem->count);

		if (!(c & KD_RWSEM_NEEDWAKE) || (c & (KD_RWSEM_HANDOFF | KD_RWSEM_XHEAD)))
			return false;
		if (kd_rwsem_write_steal(sem))
			return true;
		if (need_resched())
			return false;
		if (!(i & 63)) {
			u64 now = local_clock();

			if (!end)
				end = now + READ_ONCE(kd_rwsem_wspin_ns);
			else if (now > end)
				return false;
		}
		cpu_relax();
	}
}

/*
 * Queue head (pinned, on the wait stack) obtains the writer bit. Returns
 * false when the current holders do not leave within the spin budget; the
 * caller then continues in kd_down_write_sleep() with ->m still held and
 * KD_RWSEM_WWAIT still set.
 */
/*
 * Holder of ->m: spin, bounded by time, until the writer bit can be taken
 * (@write) or no writer is in (!@write; the caller is a registered
 * reader). Any task that holds ->m spins here before it sleeps on
 * ->count, because a holder of ->m that sleeps makes every other waiter
 * see an owner off the CPU and park as well; they are then woken one by
 * one (measured: mmap1 with 4 threads at a third of Native's rate while
 * this happened).
 */
static bool kd_rwsem_spin_for(struct kd_rwsem *sem, bool write)
{
	u64 end = 0;
	int i;

	for (i = 0;; i++) {
		if (write ? kd_rwsem_write_try(sem) :
			    !(atomic_long_read(&sem->count) & KD_RWSEM_WLOCKED))
			return true;
		if (need_resched())
			return false;
		/*
		 * Bounded by time, not iterations: how long the holders keep
		 * the lock decides, and a pause costs very different amounts
		 * on different machines. The clock is read once in a while.
		 */
		if (!(i & 63)) {
			u64 now = local_clock();

			if (!end)
				end = now + READ_ONCE(kd_rwsem_wspin_ns);
			else if (now > end)
				return false;
		}
		cpu_relax();
	}
}

/*
 * Reader phase. A queue head that finds readers in does not close the read
 * side (KD_RWSEM_WWAIT) at once: it leaves the readers kd_rwsem_rphase_ns
 * per reader it found, at most KD_RWSEM_RPHASE_MAX_NS.
 *
 * Without this, every reader got exactly one section per writer phase: the
 * readers registered behind a session entered together, and the next head
 * had closed the read side before any of them came back, so all of them
 * then waited through the next session. Throughput follows the number of
 * phase changes, and the readers' share of a cycle was far below what they
 * can use in parallel. TCLocks gets the same effect from its reader queue:
 * the next writer queues behind the readers that waited.
 *
 * Measured (build #59, in-boot alternation, 2 rounds, fixed lengths, 20%
 * writes, Mops/s): 8 workers 4.64 -> 5.80 at 5 us; 32 workers 4.42 -> 5.82
 * at 20 us; 64 workers 2.92 -> 4.00 at 30 us; each falls again for longer
 * phases, and at 4 workers any length loses (7.29 -> 7.00 at 5 us). The
 * best length grows with the number of readers, hence the per-reader
 * setting. Per reader (build #60, same method): 1000 ns gives 5.71, 5.63
 * and 3.98 at 8, 32 and 64 workers and 7.41 against 7.47 at 4; 400 and
 * 700 give less, 1500 no more with 20% writes. It delays a writer by a
 * bounded time per phase. 0 switches it off.
 */
static unsigned int kd_rwsem_rphase_ns __read_mostly = 1000;
core_param(kd_rwsem_rphase_ns, kd_rwsem_rphase_ns, uint, 0644);
#define KD_RWSEM_RPHASE_MAX_NS	50000

/*
 * Parking of plain-mode writers (kd_rwsem_park(), below): the readers of
 * this lock take longer than kd_rwsem_park_drain_ns to leave on average
 * (0: never park) ...
 */
static unsigned int kd_rwsem_park_drain_ns __read_mostly = 5000;
core_param(kd_rwsem_park_drain_ns, kd_rwsem_park_drain_ns, uint, 0644);
/* ... and this many writers spin in the queue already, on average. */
static unsigned int kd_rwsem_park_queue __read_mostly = 6;
core_param(kd_rwsem_park_queue, kd_rwsem_park_queue, uint, 0644);

static __always_inline bool kd_rwsem_park_slow(struct kd_rwsem *sem)
{
	unsigned int ns = READ_ONCE(kd_rwsem_park_drain_ns);

	return ns && READ_ONCE(kd_rw_era_ns) && kd_rw_era_drain(sem) > ns;
}

static bool kd_rwsem_post(void *root, struct kd_node *head)
{
	struct kd_rwsem *sem = root;
	u64 rphase = READ_ONCE(kd_rwsem_rphase_ns);
	/*
	 * Without eras nothing is measured: kd_rw_era_ns=0 costs this one
	 * load. With them, a CPU's queue heads measure at one acquisition in
	 * kd_rw_era_sample, as the rwlock's do (kd_rw_post()): the walk over
	 * the nodes behind the head and the store into the averages are
	 * lines that every writer of the lock otherwise takes in turn.
	 */
	bool era = READ_ONCE(kd_rw_era_ns) && kd_rw_era_sampled();
	u64 t0 = 0;
	long nr;

	if (rphase) {
		nr = atomic_long_read(&sem->count) >> KD_RWSEM_RSHIFT;

		/*
		 * One reader gets no phase. In mmap1 the one reader is the
		 * tail of the previous munmap after its downgrade, and waiting
		 * for it per operation cost 12% at 4-32 threads (build #65,
		 * in-boot alternation, 5 runs: about 203000 -> 180000
		 * iterations per second).
		 */
		rphase = nr > 1 ? rphase * (nr - 1) : 0;
	}
	if (rphase) {
		u64 end = local_clock() + min_t(u64, rphase, KD_RWSEM_RPHASE_MAX_NS);
		int i;

		/* Not polling ->count: the readers are writing it. */
		for (i = 1; !need_resched(); i++) {
			if (!(i & 15) && local_clock() > end)
				break;
			cpu_relax();
		}
	}
	nr = atomic_long_fetch_or(KD_RWSEM_WWAIT, &sem->count) >> KD_RWSEM_RSHIFT;
	if (era && nr) {
		t0 = local_clock();
		/*
		 * For kd_rwsem_park(): the writers that spin behind this one.
		 * Looked at here, before the wait for the readers and only
		 * when there is one, so that the walk delays nobody.
		 */
		if (kd_rwsem_park_slow(sem))
			kd_rw_era_queue_note(sem, head ? kd_q_depth(head, KD_PARK_DEPTH) : 0);
	}
	if (!kd_rwsem_spin_for(sem, true)) {
		/* The readers stay longer than the spin budget: no eras. */
		if (era)
			kd_rw_era_writer(sem, nr, 0, READ_ONCE(kd_rwsem_wspin_ns));
		return false;
	}
	if (era)
		kd_rw_era_writer(sem, nr, head ? kd_q_depth(head, KD_POST_DEPTH) : 0,
				 t0 ? local_clock() - t0 : 0);
	/* Readers that stayed out for this writer may register behind it. */
	kd_rwsem_phase_change(sem);
	return true;
}

static void kd_rwsem_release_queue(void *root)
{
	struct kd_rwsem *sem = root;

	kd_mutex_unlock(&sem->m);
}

/* Role exchange mark: a bit of ->count, which the write release changes anyway. */
static void kd_rwsem_xflag(void *root, bool set)
{
	struct kd_rwsem *sem = root;

	if (set)
		atomic_long_or(KD_RWSEM_XHEAD, &sem->count);
	else
		atomic_long_andnot(KD_RWSEM_XHEAD, &sem->count);
}

/* kd_family.downgrade: the origin continues as a reader. */
static void kd_rwsem_grant_downgrade(void *root)
{
	kd_downgrade_write(root);
}

static const struct kd_family kd_rwsem_family = {
	.post		= kd_rwsem_post,
	.release	= kd_rwsem_release_queue,
	.xflag		= kd_rwsem_xflag,
	.downgrade	= kd_rwsem_grant_downgrade,
	.keeps_q	= true,
	.always_deleg	= true,
	/*
	 * NUMA deferral only in long sessions; see kd_family.numa_after.
	 * Measured (build #49, in-boot alternation, 3 rounds, 32 workers):
	 * deferral +128% with writers only (1.56 -> 3.56 Mops/s), -22% with
	 * 20% writers (2.34 -> 1.82), where sessions serve 6-11 writers.
	 */
	.numa_after	= 32,
};

/* Called by the entry stub on the wait stack. */
int kd_down_write_wait(struct kd_rwsem *sem)
{
	int ret = kd_wait_sleepable(&sem->m, sem, &kd_rwsem_family, NULL, NULL, true);

	if (ret == KD_WAIT_RESUMED)
		kd_finish_resume(1);
	return ret;
}

/*
 * kd_down_write*() reached inside a section; see kd_mutex_nested(). If the
 * executor got the queue mutex but the count holders do not leave within
 * the spin budget, it gives the queue up again before handing back.
 */
int kd_down_write_nested(struct kd_rwsem *sem, struct kd_regs *r, void *entry)
{
	int ret;

	if (kd_down_write_trylock_raw(sem))
		return KD_WAIT_LOCAL;
	ret = kd_wait_sleepable(&sem->m, sem, &kd_rwsem_family, r, entry, true);
	if (ret == KD_WAIT_SLEEP_HELD) {
		atomic_long_andnot(KD_RWSEM_WWAIT, &sem->count);
		kd_mutex_unlock(&sem->m);
		ret = KD_WAIT_SLEEP;
	}
	return ret;
}

/*
 * Sleep on ->count as the holder of ->m until @cond holds. Returns
 * -EINTR if a signal permitted by @state arrives first.
 *
 * NEEDWAKE is set with a full-barrier atomic before the condition is
 * re-read, and releasers change ->count with an atomic before testing
 * NEEDWAKE, so one side always sees the other.
 */
#define kd_rwsem_sleep_on(sem, state, cond)				\
({									\
	int __ret = 0;							\
	atomic_long_or(KD_RWSEM_NEEDWAKE, &(sem)->count);		\
	for (;;) {							\
		set_current_state(state);				\
		if (cond)						\
			break;						\
		if (signal_pending_state(state, current)) {		\
			__ret = -EINTR;					\
			break;						\
		}							\
		schedule();						\
	}								\
	__set_current_state(TASK_RUNNING);				\
	atomic_long_andnot(KD_RWSEM_NEEDWAKE, &(sem)->count);		\
	__ret;								\
})

/*
 * The holder of ->m sleeps until it has the writer bit. Writers may steal
 * the lock meanwhile (kd_rwsem_write_steal()); once this one has waited
 * kd_rwsem_handoff_ms it forbids that. HANDOFF is set before the lock is
 * looked at again, so a release that follows finds it, and every release
 * while NEEDWAKE is set wakes this task.
 */
static int kd_rwsem_write_sleep_on(struct kd_rwsem *sem, unsigned int state)
{
	unsigned long handoff_at = jiffies + msecs_to_jiffies(READ_ONCE(kd_rwsem_handoff_ms)) + 1;
	bool asked = false;
	int ret = 0;

	atomic_long_or(KD_RWSEM_NEEDWAKE, &sem->count);
	for (;;) {
		set_current_state(state);
		if (kd_rwsem_write_try(sem))
			break;
		if (signal_pending_state(state, current)) {
			ret = -EINTR;
			break;
		}
		if (!asked && time_after(jiffies, handoff_at)) {
			atomic_long_or(KD_RWSEM_HANDOFF, &sem->count);
			kd_stat_inc(raw_cpu_ptr(&kd_cpu), KD_STAT_WR_HANDOFF);
			asked = true;
			continue;
		}
		schedule();
	}
	__set_current_state(TASK_RUNNING);
	/* kd_rwsem_write_try() cleared HANDOFF with the lock; after a signal it is still set. */
	atomic_long_andnot(ret ? KD_RWSEM_NEEDWAKE | KD_RWSEM_HANDOFF : KD_RWSEM_NEEDWAKE,
			   &sem->count);
	return ret;
}

/*
 * Plain mode: should a writer that has to wait do so asleep (parked on ->m)
 * instead of spinning in the queue?
 *
 * A queued writer spins for as long as the holder of ->m runs, and that
 * holder may itself only be waiting for readers. When the readers stay
 * long, a queue of spinning writers is pure cost, and for the mmap lock it
 * is more than that: every spinning thread keeps its mm live on a CPU, and
 * the TLB flush of each munmap, made in the read part after the downgrade,
 * has to interrupt all of them and wait for their answers. Apache with one
 * process of 60 threads on kdall15: the server's threads occupied 34 CPUs,
 * 77% of their time in kd_wait_sleepable(), at 23 k requests per second; on
 * the native kernel, whose rwsem waiters sleep behind a reader-held lock,
 * 3.5 CPUs and 31.5 k.
 *
 * The queue heads already measure how long the readers they find take to
 * leave (kd_rw_era_writer(), an average per lock by hash). Above
 * kd_rwsem_park_drain_ns a writer parks (0: never, always queue), if on
 * average kd_rwsem_park_queue writers or more wait behind the one that
 * waits for the readers: the ones a queue head finds spinning behind it
 * (up to KD_PARK_DEPTH) plus the ones parked at that moment.
 *
 * The second condition is for few threads. Parking pays through the CPUs
 * it takes out of the mm; with four threads there are at most three to
 * take out, and each parked wait costs a wakeup. LevelDB readrandom with a
 * thrashing table cache (40 000 munmap a second at 4 threads) against the
 * native kernel, kdall20, one boot, mean of 2: never parking 1.06 / 1.06 /
 * 1.10 / 1.07 at 4 / 8 / 16 / 32 threads, parking by the drain time alone
 * 0.88 / 0.98 / 1.12 / 1.15, with 6 waiting writers 1.08 / 1.09 / 1.10 /
 * 1.14; Apache single process at 16 / 32 / 60 threads 1.07 / 0.89 / 0.70,
 * 1.09 / 1.27 / 1.28 and 1.12 / 1.24 / 1.27. Counting only the spinning
 * writers does not work: once writers park the queue is short, the
 * average falls and parking ends (kdall18: Apache at 60 threads 0.78).
 *
 * Measured on kdall16, no daemon, one boot, thresholds off / 5 us / 20 us,
 * mean of 2 runs, against the native twin (another boot): Apache single
 * process at 16, 32, 48 and 60 threads 1.05, 0.93, 0.76, 0.71 of native
 * without it, 1.10, 1.27, 1.32, 1.31 with 5 us, 1.09, 0.91, 0.81, 0.79 with
 * 20 us; Apache's default configuration 1.23 -> 1.37. will-it-scale with
 * 5 us against none: mmap1 0.95-0.98, brk1 0.90-0.99 (the average crosses
 * the threshold at times: 48 000 parked waits in 10 s at 16 threads against
 * 4 000), page_fault1 and page_fault3 unchanged. The threshold is the one
 * above which a lock gets no era either (kd_rw_era_drain_ns).
 */
static __always_inline bool kd_rwsem_park(struct kd_rwsem *sem)
{
	unsigned int n = READ_ONCE(kd_rwsem_park_queue);

	return kd_rwsem_park_slow(sem) &&
	       kd_rw_era_queue(sem) >= n * KD_ERA_PRESS_ONE;
}

static int __kd_down_write_sleep(struct kd_rwsem *sem, int why, unsigned int state)
{
	int ret;

	might_sleep();
	if (why != KD_WAIT_SLEEP_HELD) {
		bool era = READ_ONCE(kd_rw_era_ns);
		u64 t0 = 0;
		long nr;

		ret = kd_mutex_sleep(&sem->m, state, NULL);
		if (ret)
			return ret;
		/*
		 * A parked writer that got ->m is a queue head like the one in
		 * kd_rwsem_post() and reports the same measurements; otherwise a
		 * lock whose writers all park (kd_rwsem_park()) would keep the
		 * average that sent them there.
		 */
		nr = atomic_long_fetch_or(KD_RWSEM_WWAIT, &sem->count) >> KD_RWSEM_RSHIFT;
		if (era && nr) {
			t0 = local_clock();
			/* Nobody spins behind a writer that slept; the parked ones are added. */
			if (kd_rwsem_park_slow(sem))
				kd_rw_era_queue_note(sem, 0);
		}
		if (kd_rwsem_spin_for(sem, true)) {
			if (era)
				kd_rw_era_writer(sem, nr, 0, t0 ? local_clock() - t0 : 0);
			kd_rwsem_phase_change(sem);
			kd_mutex_unlock(&sem->m);
			return 0;
		}
		if (era)
			kd_rw_era_writer(sem, nr, 0, READ_ONCE(kd_rwsem_wspin_ns));
	}
	ret = kd_rwsem_write_sleep_on(sem, state);
	if (ret) {
		/* Give up: let queued readers use the fast path again. */
		atomic_long_andnot(KD_RWSEM_WWAIT, &sem->count);
	}
	kd_rwsem_phase_change(sem);
	kd_mutex_unlock(&sem->m);
	return ret;
}

/* Tail-called by the entry stubs on the task's own stack, unpinned. */
int kd_down_write_sleep(struct kd_rwsem *sem, int why)
{
	return __kd_down_write_sleep(sem, why, TASK_UNINTERRUPTIBLE);
}

int kd_down_write_sleep_killable(struct kd_rwsem *sem, int why)
{
	return __kd_down_write_sleep(sem, why, TASK_KILLABLE);
}

/*
 * Slow path of the delegable write entries, on the caller's own stack; see
 * __kd_mutex_lock_slow(). A contended writer publishes its continuation
 * whenever it can (kd_family.always_deleg).
 */
static __always_inline int __kd_down_write_slow(struct kd_rwsem *sem, unsigned long site,
						unsigned int state)
{
	int ret;

	might_sleep();
	/* The holder of the queue sleeps: do not queue behind it for a free lock. */
	if (READ_ONCE(kd_rwsem_steal) && kd_rwsem_steal_wait(sem))
		return 0;
	/* The lock is in use and serves another node: wait for our era (kd_era.c). */
	if (kd_rw_era_other(sem)) {
		kd_rw_era_wait(sem, kd_rwsem_era_bound());
		if (kd_down_write_trylock_raw(sem))
			return 0;
	}
	preempt_disable();
	if (kd_can_offer(site))
		return KD_SLOW_OFFER;
	if (kd_rwsem_park(sem)) {
		/* Readers stay long in this lock: wait asleep, not in the queue. */
		preempt_enable();
		kd_rw_era_parked(sem, 1);
		ret = __kd_down_write_sleep(sem, KD_WAIT_SLEEP, state);
		kd_rw_era_parked(sem, -1);
		return ret;
	}
	ret = kd_wait_sleepable(&sem->m, sem, &kd_rwsem_family, NULL, NULL, false);
	preempt_enable();
	if (ret == KD_WAIT_LOCAL)
		return 0;
	return __kd_down_write_sleep(sem, ret, state);
}

int kd_down_write_slow(struct kd_rwsem *sem, unsigned long site)
{
	return __kd_down_write_slow(sem, site, TASK_UNINTERRUPTIBLE);
}

int kd_down_write_slow_killable(struct kd_rwsem *sem, unsigned long site)
{
	return __kd_down_write_slow(sem, site, TASK_KILLABLE);
}

bool kd_down_write_trylock_raw(struct kd_rwsem *sem)
{
	long c = 0;

	return atomic_long_try_cmpxchg_acquire(&sem->count, &c, KD_RWSEM_WLOCKED);
}

int kd_down_write_trylock(struct kd_rwsem *sem)
{
	return kd_down_write_trylock_raw(sem);
}
EXPORT_SYMBOL(kd_down_write_trylock);

/*
 * The count says a release does not match what the caller holds: a write
 * release or downgrade without the writer bit, or a read release while the
 * writer bit is set (an admitted reader never coexists with it; readers
 * registered behind a writer leave through kd_rwsem_read_undo()). Each of
 * them corrupts ->count for good, so say where it happened.
 */
static noinline void kd_rwsem_bad_release(struct kd_rwsem *sem, const char *what, long c)
{
	WARN_ONCE(1, "kdlock: %s of rwsem %px with count %#lx\n", what, sem, c);
	pr_err_ratelimited("kdlock: %s of rwsem %px with count %#lx by %s/%d\n",
			   what, sem, c, current->comm, current->pid);
}

/*
 * One locked subtraction, and no look at ->count before it; see
 * kd_mutex_unlock(). The writer bit is set, so subtracting it clears it.
 *
 * KD_RWSEM_XHEAD (role exchange): a queue head waits to be taken over.
 * That needs the writer bit, which is already released; take it again
 * unless a reader or writer got in first, serve the queued writers, and
 * release again.
 */
void kd_up_write(struct kd_rwsem *sem)
{
	long c;

	/* Role exchange, known on this CPU: take over while the bit is held. */
	if (unlikely(raw_cpu_read(kd_cpu.xs_hint) == sem)) {
		raw_cpu_write(kd_cpu.xs_hint, NULL);
		if (kd_release_combine(&sem->m.q, &sem->m, sem, &kd_rwsem_family))
			return;
	}
	c = atomic_long_fetch_sub_release(KD_RWSEM_WLOCKED, &sem->count);
	if (unlikely(!(c & KD_RWSEM_WLOCKED)))
		kd_rwsem_bad_release(sem, "write release", c);
	if (kd_rwsem_readers(c))
		kd_rwsem_phase_change(sem);

	while (unlikely(c & KD_RWSEM_XHEAD)) {
		if (!kd_rwsem_write_try(sem)) {
			kd_release_decline(sem, &kd_rwsem_family);
			break;
		}
		if (kd_release_combine(&sem->m.q, &sem->m, sem, &kd_rwsem_family))
			return;			/* the writer bit left with a waiter */
		c = atomic_long_fetch_sub_release(KD_RWSEM_WLOCKED, &sem->count);
		if (kd_rwsem_readers(c))
			kd_rwsem_phase_change(sem);
	}
	if (unlikely(c & KD_RWSEM_NEEDWAKE))
		kd_rwsem_wake(sem);
}
EXPORT_SYMBOL(kd_up_write);

/*
 * Write to read without a window: one atomic adds the reader and removes
 * the writer bit. Inside a delegated section this call is always handed
 * back, because the read-side remainder belongs to the origin.
 */
void kd_downgrade_write(struct kd_rwsem *sem)
{
	long c = atomic_long_fetch_add(KD_RWSEM_RBIAS - KD_RWSEM_WLOCKED, &sem->count);

	if (unlikely(!(c & KD_RWSEM_WLOCKED)))
		kd_rwsem_bad_release(sem, "downgrade", c);
	if (kd_rwsem_readers(c))
		kd_rwsem_phase_change(sem);
	/* The caller stays in as a reader, so it cannot serve writers here. */
	if (unlikely(c & KD_RWSEM_XHEAD))
		kd_release_decline(sem, &kd_rwsem_family);
	if (unlikely(c & KD_RWSEM_NEEDWAKE))
		kd_rwsem_wake(sem);
}
EXPORT_SYMBOL(kd_downgrade_write);

/* ---- readers ---------------------------------------------------------------- */

static __always_inline void kd_rwsem_read_undo(struct kd_rwsem *sem)
{
	long c = atomic_long_sub_return(KD_RWSEM_RBIAS, &sem->count);

	if (unlikely((c & KD_RWSEM_NEEDWAKE) && !kd_rwsem_readers(c)))
		kd_rwsem_wake(sem);
}

bool kd_down_read_trylock_raw(struct kd_rwsem *sem)
{
	long c = atomic_long_read(&sem->count);

	while (!(c & KD_RWSEM_WMASK)) {
		if (atomic_long_try_cmpxchg_acquire(&sem->count, &c, c + KD_RWSEM_RBIAS))
			return true;
	}
	return false;
}

int kd_down_read_trylock(struct kd_rwsem *sem)
{
	return kd_down_read_trylock_raw(sem);
}
EXPORT_SYMBOL(kd_down_read_trylock);

/*
 * Reader admission without the queue mutex (D11).
 *
 * A reader that finds a writer inside (KD_RWSEM_WLOCKED) stays registered
 * and waits for that writer, or the combiner's whole session, to leave.
 * The registered count keeps the next writer out (a writer takes the lock
 * only with no reader in), so the readers that arrived during one writer
 * phase enter together right after it, and the next writer waits for
 * exactly that batch. A reader that finds a writer only waiting
 * (KD_RWSEM_WWAIT: the head of ->m waits for the readers in to leave) does
 * not register, which would keep that writer out indefinitely; it waits
 * for the writer to get in and then registers behind it.
 *
 * This replaces a passage through ->m per reader: ->m serialised the
 * readers (one handoff of the queue each, across nodes on a two-node
 * machine), and every queued reader ended the session of the combiner
 * in front of it, so writer sessions stayed short. With readers out of
 * ->m, ->m orders writers only, as the writer queue does in TCLocks.
 *
 * A waiting reader does not poll ->count but the phase counter
 * (kd_rwsem_phase()), so the readers that are in can leave without first
 * taking the line from every waiter. Waiting is bounded by time and by
 * need_resched(): then the reader deregisters and queues on ->m, where it
 * can sleep and from where it cannot be passed by later writers.
 *
 * @reg: the reader is registered (its increment is in ->count, behind an
 * active writer). Returns true with the read side held.
 */
static bool __kd_down_read_admit(struct kd_rwsem *sem, long c, bool reg);

static bool kd_down_read_admit(struct kd_rwsem *sem, long c, bool reg)
{
	struct kd_rwsem_phase *p = kd_rwsem_phase_of(sem);
	bool ret;

	/* Counted before the first look: see kd_rwsem_phase_change(). */
	atomic_inc(&p->waiters);
	ret = __kd_down_read_admit(sem, c, reg);
	atomic_dec(&p->waiters);
	return ret;
}

static bool __kd_down_read_admit(struct kd_rwsem *sem, long c, bool reg)
{
	atomic_t *phase = kd_rwsem_phase(sem);
	u64 end = 0;
	int seq, i = 0;

	for (;;) {
		/*
		 * The counter first, then ->count: whoever changes ->count
		 * in a way that matters here changes the counter afterwards.
		 */
		seq = atomic_read(phase);
		c = atomic_long_read(&sem->count);
		if (reg) {
			/* Registered behind an active writer: wait for it to leave. */
			if (!(c & KD_RWSEM_WLOCKED)) {
				smp_acquire__after_ctrl_dep();
				kd_stat_inc(raw_cpu_ptr(&kd_cpu), KD_STAT_RD_BEHIND);
				return true;
			}
		} else if (!(c & KD_RWSEM_WMASK)) {
			if (atomic_long_try_cmpxchg_acquire(&sem->count, &c,
							    c + KD_RWSEM_RBIAS))
				return true;
			continue;
		} else if (c & KD_RWSEM_WLOCKED) {
			/* A writer is in: register behind it. */
			c = atomic_long_add_return_acquire(KD_RWSEM_RBIAS, &sem->count);
			if (!(c & KD_RWSEM_WLOCKED))
				return true;	/* it left already: we are in */
			reg = true;
		}
		/* else only a writer waiting: stay out until it is in. */

		for (;;) {
			if (need_resched())
				goto out;
			/*
			 * Bounded by time, and a look at ->count without a
			 * phase change now and then.
			 */
			if (!(i++ & 63)) {
				u64 now = local_clock();

				if (!end)
					end = now + READ_ONCE(kd_rwsem_rspin_ns);
				else if (now > end)
					goto out;
				else
					break;
			}
			cpu_relax();
			if (atomic_read(phase) != seq)
				break;
		}
	}
out:
	if (reg)
		kd_rwsem_read_undo(sem);
	return false;
}

static noinline int kd_down_read_slow(struct kd_rwsem *sem, unsigned int state, long c,
				      bool added)
{
	int ret;
	bool reg = added && (c & KD_RWSEM_WLOCKED);

	/* Behind an active writer the fast path's increment stays. */
	if (added && !reg)
		kd_rwsem_read_undo(sem);
	/* Not in yet, and the lock serves another node: wait for our era. */
	if (!reg && kd_rw_era_other(sem))
		kd_rw_era_wait(sem, kd_rwsem_era_bound());
	if (kd_down_read_admit(sem, c, reg))
		return 0;

	/* Queue behind earlier writers and readers. */
	kd_stat_inc(raw_cpu_ptr(&kd_cpu), KD_STAT_RD_QUEUE);
	ret = kd_mutex_sleep(&sem->m, state, NULL);
	if (ret)
		return ret;
	/*
	 * Holding ->m keeps queued writers out. Register as reader first so
	 * a fast-path or trylock writer cannot slip in, then wait for an
	 * active writer to leave.
	 */
	atomic_long_add(KD_RWSEM_RBIAS, &sem->count);
	/*
	 * The writer still inside is usually a combiner running its own
	 * section right after releasing ->m, which takes nanoseconds. Spin
	 * for it before sleeping: a holder of ->m that sleeps makes every
	 * queued writer see an off-CPU owner and park.
	 */
	kd_rwsem_spin_for(sem, false);
	ret = kd_rwsem_sleep_on(sem, state,
				!(atomic_long_read(&sem->count) & KD_RWSEM_WLOCKED));
	if (ret)
		atomic_long_sub(KD_RWSEM_RBIAS, &sem->count);
	kd_mutex_unlock(&sem->m);
	return ret;
}

static __always_inline int __kd_down_read(struct kd_rwsem *sem, unsigned int state)
{
	long c;

	might_sleep();
	/*
	 * Look before adding: while a writer is in or waiting, the increment
	 * and its undo are two more locked operations on the line that the
	 * readers leaving and the waiting writer need (measured, in-boot A/B,
	 * build #55: 20% writes +5-18% at 4-32 workers; 1% writes +3-8% from
	 * 8 workers, -4% at 4). Rechecked with waiting readers off ->count
	 * (build #59, 2 rounds): without the look, 1% writes is 9-11% lower
	 * at 8-64 workers.
	 */
	c = atomic_long_read(&sem->count);
	if (unlikely(c & KD_RWSEM_WMASK))
		return kd_down_read_slow(sem, state, c, false);
	/*
	 * No look at the era here: only a reader that meets a writer waits
	 * for its node's era (kd_down_read_slow()). Checking the era word on
	 * this path whenever two readers were in cost every reader of every
	 * rwsem 3-12% on one node, and across nodes the lock was faster
	 * without it as well (build #81, in-boot, 32 workers: one node
	 * 0.93-0.98 -> 0.99-1.00 of the rate without any era code; 16+16
	 * with 1% writes 10.87 -> 12.17 Mops/s).
	 */
	c = atomic_long_add_return_acquire(KD_RWSEM_RBIAS, &sem->count);
	if (likely(!(c & KD_RWSEM_WMASK)))
		return 0;
	return kd_down_read_slow(sem, state, c, true);
}

void kd_down_read(struct kd_rwsem *sem)
{
	__kd_down_read(sem, TASK_UNINTERRUPTIBLE);
}
EXPORT_SYMBOL(kd_down_read);

int kd_down_read_interruptible(struct kd_rwsem *sem)
{
	return __kd_down_read(sem, TASK_INTERRUPTIBLE);
}
EXPORT_SYMBOL(kd_down_read_interruptible);

int kd_down_read_killable(struct kd_rwsem *sem)
{
	return __kd_down_read(sem, TASK_KILLABLE);
}
EXPORT_SYMBOL(kd_down_read_killable);

void kd_up_read(struct kd_rwsem *sem)
{
	long c = atomic_long_sub_return_release(KD_RWSEM_RBIAS, &sem->count);

	if (unlikely(c & KD_RWSEM_WLOCKED))
		kd_rwsem_bad_release(sem, "read release", c);
	if (unlikely((c & KD_RWSEM_NEEDWAKE) && !kd_rwsem_readers(c)))
		kd_rwsem_wake(sem);
}
EXPORT_SYMBOL(kd_up_read);
