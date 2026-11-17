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
 */
#define KD_RWSEM_PHASE_BITS	8

static struct kd_rwsem_phase {
	atomic_t	seq;
} ____cacheline_aligned_in_smp kd_rwsem_phases[1 << KD_RWSEM_PHASE_BITS];

static __always_inline atomic_t *kd_rwsem_phase(struct kd_rwsem *sem)
{
	return &kd_rwsem_phases[hash_ptr(sem, KD_RWSEM_PHASE_BITS)].seq;
}

static __always_inline void kd_rwsem_phase_change(struct kd_rwsem *sem)
{
	atomic_inc(kd_rwsem_phase(sem));
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

/* Writer holding ->m: take the writer bit if no reader and no writer is in. */
static __always_inline bool kd_rwsem_write_try(struct kd_rwsem *sem)
{
	long c = atomic_long_read(&sem->count);

	while (!(c & KD_RWSEM_WLOCKED) && !kd_rwsem_readers(c)) {
		if (atomic_long_try_cmpxchg_acquire(&sem->count, &c,
				(c & ~KD_RWSEM_WWAIT) | KD_RWSEM_WLOCKED))
			return true;
	}
	return false;
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

static bool kd_rwsem_post(void *root, struct kd_node *head)
{
	struct kd_rwsem *sem = root;
	u64 rphase = READ_ONCE(kd_rwsem_rphase_ns);
	/* Without eras nothing is measured: kd_rw_era_ns=0 costs this one load. */
	bool era = READ_ONCE(kd_rw_era_ns);
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
	if (era && nr)
		t0 = local_clock();
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

static int __kd_down_write_sleep(struct kd_rwsem *sem, int why, unsigned int state)
{
	int ret;

	might_sleep();
	if (why != KD_WAIT_SLEEP_HELD) {
		ret = kd_mutex_sleep(&sem->m, state, NULL);
		if (ret)
			return ret;
		atomic_long_or(KD_RWSEM_WWAIT, &sem->count);
		if (kd_rwsem_spin_for(sem, true)) {
			kd_rwsem_phase_change(sem);
			kd_mutex_unlock(&sem->m);
			return 0;
		}
	}
	ret = kd_rwsem_sleep_on(sem, state, kd_rwsem_write_try(sem));
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
	/* The lock is in use and serves another node: wait for our era (kd_era.c). */
	if (kd_rw_era_other(sem)) {
		kd_rw_era_wait(sem, READ_ONCE(kd_rw_era_ns));
		if (kd_down_write_trylock_raw(sem))
			return 0;
	}
	preempt_disable();
	if (kd_can_offer(site))
		return KD_SLOW_OFFER;
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
static bool kd_down_read_admit(struct kd_rwsem *sem, long c, bool reg)
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
		kd_rw_era_wait(sem, READ_ONCE(kd_rw_era_ns));
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

	if (unlikely((c & KD_RWSEM_NEEDWAKE) && !kd_rwsem_readers(c)))
		kd_rwsem_wake(sem);
}
EXPORT_SYMBOL(kd_up_read);
