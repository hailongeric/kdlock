// SPDX-License-Identifier: GPL-2.0
/*
 * Nano benchmark bodies for kdlock and the native locks.
 *
 * Each lock family has the same small body: a writer increments `lines`
 * padded counters, a reader checks that they are equal, followed by `post`
 * register-only rounds outside the lock. Workers are pinned kernel
 * threads; one ioctl runs one timed point. The body functions are
 * noinline so each lock call keeps one stable return address, which is the
 * call site the kdlock translator keys its images on.
 *
 * Only the lock calls differ between backends.
 */
#include <linux/module.h>
#include <linux/kthread.h>
#include <linux/miscdevice.h>
#include <linux/fs.h>
#include <linux/spinlock.h>
#include <linux/mutex.h>
#include <linux/rwsem.h>
#include <linux/delay.h>
#include <linux/sched.h>
#include <linux/uaccess.h>
#include <linux/slab.h>
#include <linux/rcupdate.h>
#include <linux/ww_mutex.h>
#include <linux/interrupt.h>
#include <kdlock/kd_api.h>
#include "kd_bench_uapi.h"

MODULE_LICENSE("GPL");

#define MAX_LINES 16

/*
 * Every shared object of the bench sits in its own 128-byte block: a cache
 * line plus the partner line the adjacent-line prefetcher fetches with it.
 * Otherwise the rates depend on where the linker happens to put a lock
 * relative to the counters, the run flags and the other backends' locks
 * (measured: kd spin at 8 workers moved from about 4.9 to 4.0 Mops between
 * two builds that differed only in such placement).
 */
#define KDB_BLOCK __aligned(128)

struct kdb_line {
	u64 v;
} KDB_BLOCK;

static struct kdb_line cnt[MAX_LINES];
static unsigned int g_lines KDB_BLOCK = 1;

static spinlock_t n_spin KDB_BLOCK = __SPIN_LOCK_UNLOCKED(n_spin);
static struct mutex n_mutex KDB_BLOCK = __MUTEX_INITIALIZER(n_mutex);
static rwlock_t n_rwl KDB_BLOCK = __RW_LOCK_UNLOCKED(n_rwl);
static struct rw_semaphore n_rwsem KDB_BLOCK = __RWSEM_INITIALIZER(n_rwsem);
static struct kd_spinlock k_spin KDB_BLOCK;
static struct kd_mutex k_mutex KDB_BLOCK;
static struct kd_rwlock k_rwl KDB_BLOCK;
static struct kd_rwsem k_rwsem KDB_BLOCK;


#define DEFINE_OPS(name, WLOCK, WUNLOCK, RLOCK, RUNLOCK)		\
static noinline void name##_w(void)					\
{									\
	unsigned int i;							\
	WLOCK;								\
	for (i = 0; i < g_lines; i++)					\
		cnt[i].v++;						\
	WUNLOCK;							\
}									\
static noinline bool name##_r(void)					\
{									\
	unsigned int i;							\
	u64 a;								\
	bool bad = false;						\
	RLOCK;								\
	a = cnt[0].v;							\
	for (i = 1; i < g_lines; i++)					\
		if (cnt[i].v != a)					\
			bad = true;					\
	RUNLOCK;							\
	return bad;							\
}

DEFINE_OPS(nspin, spin_lock(&n_spin), spin_unlock(&n_spin),
	   spin_lock(&n_spin), spin_unlock(&n_spin))
DEFINE_OPS(nmutex, mutex_lock(&n_mutex), mutex_unlock(&n_mutex),
	   mutex_lock(&n_mutex), mutex_unlock(&n_mutex))
DEFINE_OPS(nrwl, write_lock(&n_rwl), write_unlock(&n_rwl),
	   read_lock(&n_rwl), read_unlock(&n_rwl))
DEFINE_OPS(nrwsem, down_write(&n_rwsem), up_write(&n_rwsem),
	   down_read(&n_rwsem), up_read(&n_rwsem))
DEFINE_OPS(kspin, kd_spin_lock(&k_spin), kd_spin_unlock(&k_spin),
	   kd_spin_lock(&k_spin), kd_spin_unlock(&k_spin))
DEFINE_OPS(kmutex, kd_mutex_lock(&k_mutex), kd_mutex_unlock(&k_mutex),
	   kd_mutex_lock(&k_mutex), kd_mutex_unlock(&k_mutex))
DEFINE_OPS(krwl, kd_write_lock(&k_rwl), kd_write_unlock(&k_rwl),
	   kd_read_lock(&k_rwl), kd_read_unlock(&k_rwl))
DEFINE_OPS(krwsem, kd_down_write(&k_rwsem), kd_up_write(&k_rwsem),
	   kd_down_read(&k_rwsem), kd_up_read(&k_rwsem))

/*
 * The spin and mutex bodies with one use of `current` inside the section.
 * The body functions are separate so each has its own call site and image.
 */
#define DEFINE_CUR(name, LOCK, UNLOCK, CUR)				\
static noinline void name##_w(void)					\
{									\
	unsigned int i;							\
	LOCK;								\
	for (i = 0; i < g_lines; i++)					\
		cnt[i].v++;						\
	CUR;								\
	UNLOCK;								\
}

#define KDB_CUR_READ	do { if (unlikely(READ_ONCE(current->pid) < 0)) cnt[0].v++; } while (0)
#define KDB_CUR_WRITE	do { rcu_read_lock(); rcu_read_unlock(); } while (0)

DEFINE_CUR(nspin_curr, spin_lock(&n_spin), spin_unlock(&n_spin), KDB_CUR_READ)
DEFINE_CUR(nspin_curw, spin_lock(&n_spin), spin_unlock(&n_spin), KDB_CUR_WRITE)
DEFINE_CUR(nmutex_curr, mutex_lock(&n_mutex), mutex_unlock(&n_mutex), KDB_CUR_READ)
DEFINE_CUR(nmutex_curw, mutex_lock(&n_mutex), mutex_unlock(&n_mutex), KDB_CUR_WRITE)
DEFINE_CUR(kspin_curr, kd_spin_lock(&k_spin), kd_spin_unlock(&k_spin), KDB_CUR_READ)
DEFINE_CUR(kspin_curw, kd_spin_lock(&k_spin), kd_spin_unlock(&k_spin), KDB_CUR_WRITE)
DEFINE_CUR(kmutex_curr, kd_mutex_lock(&k_mutex), kd_mutex_unlock(&k_mutex), KDB_CUR_READ)
DEFINE_CUR(kmutex_curw, kd_mutex_lock(&k_mutex), kd_mutex_unlock(&k_mutex), KDB_CUR_WRITE)

/*
 * The native queued spinlock code on the kd lock object (the two have the
 * same layout), with the preempt count handled as the raw API does. Tells
 * a difference between the algorithms from one between the objects.
 */
#define NK_LOCK		do { preempt_disable(); arch_spin_lock((arch_spinlock_t *)&k_spin); } while (0)
#define NK_UNLOCK	do { arch_spin_unlock((arch_spinlock_t *)&k_spin); preempt_enable(); } while (0)
DEFINE_OPS(nkspin, NK_LOCK, NK_UNLOCK, NK_LOCK, NK_UNLOCK)

/* The spin body through the raw acquire, which never publishes. */
DEFINE_OPS(kspin_raw, kd_raw_spin_lock(&k_spin), kd_spin_unlock(&k_spin),
	   kd_raw_spin_lock(&k_spin), kd_spin_unlock(&k_spin))

/*
 * Write sections of which every sixteenth meets something only its own
 * task may run: an instruction with a fault fixup for the spin class,
 * yield() for the rwsem. A delegated section is handed back there.
 */
#define KDB_HB_FIXUP	do {						\
	if (!(cnt[0].v & 15)) {						\
		u64 t;							\
		if (copy_from_kernel_nofault(&t, &cnt[0].v, sizeof(t)) || \
		    t != cnt[0].v)					\
			hb_bad.v++;					\
	}								\
} while (0)
#define KDB_HB_YIELD	do { if (!(cnt[0].v & 15)) yield(); } while (0)

static struct kdb_line hb_bad;

DEFINE_CUR(nspin_hb, spin_lock(&n_spin), spin_unlock(&n_spin), KDB_HB_FIXUP)
DEFINE_CUR(kspin_hb, kd_spin_lock(&k_spin), kd_spin_unlock(&k_spin), KDB_HB_FIXUP)
DEFINE_CUR(nrwl_hb, write_lock(&n_rwl), write_unlock(&n_rwl), KDB_HB_FIXUP)
DEFINE_CUR(krwl_hb, kd_write_lock(&k_rwl), kd_write_unlock(&k_rwl), KDB_HB_FIXUP)
DEFINE_CUR(nrwsem_hb, down_write(&n_rwsem), up_write(&n_rwsem), KDB_HB_YIELD)
DEFINE_CUR(krwsem_hb, kd_down_write(&k_rwsem), kd_up_write(&k_rwsem), KDB_HB_YIELD)

#ifdef KDB_WITH_TCLOCK
/*
 * Original TCLock (tclock_backend/, upstream rs3lab/TCLocks RCUHT locks).
 * The calls follow the direct adapters of the earlier project's
 * rwlock_bench (not in this tree): spin and rwlock callers disable
 * preemption themselves; the rwlock pair restores interrupts after the
 * unlock because the original inline return paths can leave them off;
 * mutex and rwsem workers register their fixed CPU before the first lock
 * call, and the registrations are drained after all workers exited.
 */
#include "mutex/komb_mutex.h"
#include "rwlock/komb_rwlock.h"
#include "rwsem/komb_rwsem.h"
void komb_spin_lock(struct qspinlock *lock);
void komb_spin_unlock(struct qspinlock *lock);
int tc_mutex_worker_register(void);
int tc_mutex_workers_drain(void);
int tc_rwsem_worker_register(void);
int tc_rwsem_workers_drain(void);

static arch_spinlock_t t_spin KDB_BLOCK = __ARCH_SPIN_LOCK_UNLOCKED;
static struct komb_mutex t_mutex KDB_BLOCK = __KOMBMUTEX_INITIALIZER(t_mutex);
static struct komb_rwlock t_rwl KDB_BLOCK = __KOMB_RWLOCK_UNLOCKED;
static struct komb_rwsem t_rwsem KDB_BLOCK = __KOMB_RWSEM_INITIALIZER(t_rwsem);

#define TC_SPIN_LOCK	do { preempt_disable(); komb_spin_lock(&t_spin); } while (0)
#define TC_SPIN_UNLOCK	do { komb_spin_unlock(&t_spin); preempt_enable(); } while (0)
#define TC_WLOCK	do { preempt_disable(); komb_write_lock(&t_rwl); } while (0)
#define TC_WUNLOCK	do { komb_write_unlock(&t_rwl); local_irq_enable(); preempt_enable(); } while (0)
#define TC_RLOCK	do { preempt_disable(); komb_read_lock(&t_rwl); } while (0)
#define TC_RUNLOCK	do { komb_read_unlock(&t_rwl); local_irq_enable(); preempt_enable(); } while (0)

DEFINE_OPS(tspin, TC_SPIN_LOCK, TC_SPIN_UNLOCK, TC_SPIN_LOCK, TC_SPIN_UNLOCK)
DEFINE_OPS(tmutex, komb_mutex_lock(&t_mutex), komb_mutex_unlock(&t_mutex),
	   komb_mutex_lock(&t_mutex), komb_mutex_unlock(&t_mutex))
DEFINE_OPS(trwl, TC_WLOCK, TC_WUNLOCK, TC_RLOCK, TC_RUNLOCK)
DEFINE_OPS(trwsem, komb_rwsem_down_write(&t_rwsem), komb_rwsem_up_write(&t_rwsem),
	   komb_rwsem_down_read(&t_rwsem), komb_rwsem_up_read(&t_rwsem))

static void tc_reset(void)
{
	t_spin = (arch_spinlock_t)__ARCH_SPIN_LOCK_UNLOCKED;
	komb_mutex_init(&t_mutex);
	t_rwl = (struct komb_rwlock)__KOMB_RWLOCK_UNLOCKED;
	t_rwsem = (struct komb_rwsem)__KOMB_RWSEM_INITIALIZER(t_rwsem);
}
#endif

/*
 * Test bodies. Each returns KDB_T_BAD if it saw a broken invariant and
 * KDB_T_OUTER if it incremented the outer counter (checked at the end).
 */
#define KDB_T_BAD	1u
#define KDB_T_OUTER	2u

static struct kdb_line ocnt;
static spinlock_t n_spin2 KDB_BLOCK = __SPIN_LOCK_UNLOCKED(n_spin2);
static struct mutex n_mutex2 KDB_BLOCK = __MUTEX_INITIALIZER(n_mutex2);
static struct kd_spinlock k_spin2 KDB_BLOCK;
static struct kd_mutex k_mutex2 KDB_BLOCK;

static noinline void kdb_touch(void)
{
	barrier();
}
/* Called through a pointer so generated code meets an indirect call. */
static void (*kdb_fp)(void) = kdb_touch;

/*
 * `current` read by a call the compiler cannot see through: inside one
 * function it would otherwise read current_task once and fold every
 * comparison. Here each call really loads %gs:current_task, which a
 * delegated copy must redirect to the origin's task.
 */
static noinline __attribute__((__noipa__)) struct task_struct *kdb_current(void)
{
	return current;
}

/*
 * Outer lock, then inner lock: the outer counter must not change while
 * this section holds the outer lock, including across the inner section.
 */
#define DEFINE_NEST(name, OLOCK, OUNLOCK, ILOCK, IUNLOCK)		\
static noinline u32 name##_outer(void)					\
{									\
	unsigned int i;							\
	u64 a;								\
	u32 f = KDB_T_OUTER;						\
	OLOCK;								\
	a = READ_ONCE(ocnt.v);						\
	WRITE_ONCE(ocnt.v, a + 1);					\
	ILOCK;								\
	for (i = 0; i < g_lines; i++)					\
		cnt[i].v++;						\
	IUNLOCK;							\
	if (READ_ONCE(ocnt.v) != a + 1)					\
		f |= KDB_T_BAD;						\
	OUNLOCK;							\
	return f;							\
}									\
static noinline u32 name##_inner(void)					\
{									\
	unsigned int i;							\
	ILOCK;								\
	for (i = 0; i < g_lines; i++)					\
		cnt[i].v++;						\
	IUNLOCK;							\
	return 0;							\
}

DEFINE_NEST(nnest_spin, spin_lock(&n_spin), spin_unlock(&n_spin),
	    spin_lock(&n_spin2), spin_unlock(&n_spin2))
DEFINE_NEST(nnest_mutex, mutex_lock(&n_mutex), mutex_unlock(&n_mutex),
	    spin_lock(&n_spin2), spin_unlock(&n_spin2))
DEFINE_NEST(knest_spin, kd_spin_lock(&k_spin), kd_spin_unlock(&k_spin),
	    kd_spin_lock(&k_spin2), kd_spin_unlock(&k_spin2))
DEFINE_NEST(knest_mutex, kd_mutex_lock(&k_mutex), kd_mutex_unlock(&k_mutex),
	    kd_spin_lock(&k_spin2), kd_spin_unlock(&k_spin2))

/*
 * A section that leaves delegated code in several ways. `me` is read before
 * the lock call, so it is the origin's task; inside the section `current`
 * must still be that task wherever the section runs.
 */
#define DEFINE_MIX(name, LOCK, UNLOCK, LOCK2, UNLOCK2)			\
static noinline u32 name##_mix(u32 r)					\
{									\
	struct task_struct *me = kdb_current();				\
	unsigned int i;							\
	u32 f = 0;							\
	LOCK;								\
	for (i = 0; i < g_lines; i++)					\
		cnt[i].v++;						\
	if (kdb_current() != me)					\
		f |= KDB_T_BAD;						\
	READ_ONCE(kdb_fp)();						\
	if ((r & 15) == 0)						\
		yield();						\
	if ((r & 15) == 1) {						\
		LOCK2;							\
		WRITE_ONCE(ocnt.v, READ_ONCE(ocnt.v) + 1);		\
		UNLOCK2;						\
		f |= KDB_T_OUTER;					\
	}								\
	if (kdb_current() != me)					\
		f |= KDB_T_BAD;						\
	UNLOCK;								\
	return f;							\
}

DEFINE_MIX(nmix, mutex_lock(&n_mutex), mutex_unlock(&n_mutex),
	   mutex_lock(&n_mutex2), mutex_unlock(&n_mutex2))
DEFINE_MIX(kmix, kd_mutex_lock(&k_mutex), kd_mutex_unlock(&k_mutex),
	   kd_mutex_lock(&k_mutex2), kd_mutex_unlock(&k_mutex2))

/*
 * Two of four ww mutexes in random order under one acquire context, with
 * the documented back-off: on -EDEADLK release what is held, wait for the
 * lock that was lost, then take the other one again. cnt[i] is protected
 * by k_ww[i]; a lost update shows up in the counter sum.
 */
#define KDB_WW_LOCKS	4
static DEFINE_WD_CLASS(kdb_ww_class);
static struct kd_ww_mutex k_ww[KDB_WW_LOCKS];

static noinline u32 kww_t(u32 r, u32 pct)
{
	struct ww_acquire_ctx ctx;
	unsigned int ia = r % KDB_WW_LOCKS, ib = (r >> 8) % KDB_WW_LOCKS;
	struct kd_ww_mutex *a, *b;
	u32 f = 0;

	if (ia == ib)
		ib = (ia + 1) % KDB_WW_LOCKS;
	a = &k_ww[ia];
	b = &k_ww[ib];
	ww_acquire_init(&ctx, &kdb_ww_class);
	if (kd_ww_mutex_lock(a, &ctx))
		f |= KDB_T_BAD;		/* a context that holds nothing never backs off */
	while (kd_ww_mutex_lock(b, &ctx)) {
		kd_ww_mutex_unlock(a);
		kd_ww_mutex_lock_slow(b, &ctx);
		swap(a, b);
	}
	if (kd_ww_mutex_lock(a, &ctx) != -EALREADY)
		f |= KDB_T_BAD;
	cnt[ia].v++;
	cnt[ib].v++;
	kd_ww_mutex_unlock(a);
	kd_ww_mutex_unlock(b);
	ww_acquire_fini(&ctx);
	return f;
}

static u32 nnest_spin_t(u32 r, u32 pct)
{
	return r % 100 < pct ? nnest_spin_outer() : nnest_spin_inner();
}
static u32 nnest_mutex_t(u32 r, u32 pct)
{
	return r % 100 < pct ? nnest_mutex_outer() : nnest_mutex_inner();
}
static u32 knest_spin_t(u32 r, u32 pct)
{
	return r % 100 < pct ? knest_spin_outer() : knest_spin_inner();
}
static u32 knest_mutex_t(u32 r, u32 pct)
{
	return r % 100 < pct ? knest_mutex_outer() : knest_mutex_inner();
}
static u32 nmix_t(u32 r, u32 pct)
{
	return nmix_mix(r);
}
static u32 kmix_t(u32 r, u32 pct)
{
	return kmix_mix(r);
}

struct ops {
	void (*w)(void);
	bool (*r)(void);
	u32 (*t)(u32 r, u32 pct);	/* test bodies; w/r unused when set */
	int (*reg)(void);		/* per-worker registration before the first lock */
	int (*drain)(void);		/* after all workers exited */
};

static const struct ops op_table[3][KDB_NR_FAMILY] = {
	[KDB_NATIVE] = { { nspin_w, nspin_r }, { nmutex_w, nmutex_r },
			 { nrwl_w, nrwl_r }, { nrwsem_w, nrwsem_r },
			 { .t = nnest_spin_t }, { .t = nnest_mutex_t },
			 { .t = nmix_t },
			 { nspin_curr_w, nspin_r }, { nspin_curw_w, nspin_r },
			 { nmutex_curr_w, nmutex_r }, { nmutex_curw_w, nmutex_r },
			 { }, { nkspin_w, nkspin_r },
			 { nspin_hb_w, nspin_r }, { nrwl_hb_w, nrwl_r },
			 { nrwsem_hb_w, nrwsem_r } },
	[KDB_KD]     = { { kspin_w, kspin_r }, { kmutex_w, kmutex_r },
			 { krwl_w, krwl_r }, { krwsem_w, krwsem_r },
			 { .t = knest_spin_t }, { .t = knest_mutex_t },
			 { .t = kmix_t },
			 { kspin_curr_w, kspin_r }, { kspin_curw_w, kspin_r },
			 { kmutex_curr_w, kmutex_r }, { kmutex_curw_w, kmutex_r },
			 { .t = kww_t }, { kspin_raw_w, kspin_raw_r },
			 { kspin_hb_w, kspin_r }, { krwl_hb_w, krwl_r },
			 { krwsem_hb_w, krwsem_r } },
#ifdef KDB_WITH_TCLOCK
	[KDB_TCLOCK] = { { tspin_w, tspin_r },
			 { tmutex_w, tmutex_r, .reg = tc_mutex_worker_register,
			   .drain = tc_mutex_workers_drain },
			 { trwl_w, trwl_r },
			 { trwsem_w, trwsem_r, .reg = tc_rwsem_worker_register,
			   .drain = tc_rwsem_workers_drain } },
#endif
};

/* Register-only work between operations; the asm keeps it from folding. */
static __always_inline u64 post_work(u64 x, unsigned int rounds)
{
	while (rounds--) {
		asm volatile("" : "+r"(x));
		x = x * 6364136223846793005ULL + 1442695040888963407ULL;
	}
	return x;
}

struct worker {
	struct task_struct *task;
	const struct ops *ops;
	unsigned int cpu, idx, pct, post;
	u64 ops_done, writes, bad, outer;
	int reg_err;
	struct completion done;
} ____cacheline_aligned;

/* Read by every worker on every iteration: kept apart from the locks. */
static atomic_t ready KDB_BLOCK;
static bool go KDB_BLOCK, stop KDB_BLOCK;

static int worker_fn(void *arg)
{
	struct worker *w = arg;
	u64 rng = 0x9e3779b97f4a7c15ULL * (w->idx + 1), sink = 0;
	u64 n = 0;

	if (w->ops->reg)
		w->reg_err = w->ops->reg();
	atomic_inc(&ready);
	while (!smp_load_acquire(&go))
		cpu_relax();
	while (!w->reg_err && !READ_ONCE(stop)) {
		rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
		if (w->ops->t) {
			u32 f = w->ops->t((u32)(rng >> 32), w->pct);

			w->writes++;
			w->bad += f & KDB_T_BAD;
			w->outer += !!(f & KDB_T_OUTER);
		} else if (w->pct >= 100 || (u32)(rng >> 32) % 100 < w->pct) {
			w->ops->w();
			w->writes++;
		} else {
			w->bad += w->ops->r();
		}
		sink = post_work(sink + rng, w->post);
		if (!(++n & 0x3ff))
			cond_resched();
	}
	w->ops_done = n;
	/*
	 * Keep the post-work result live. This must not touch cnt[]: other
	 * workers may still be writing it under the lock.
	 */
	barrier_data(&sink);
	complete(&w->done);
	while (!kthread_should_stop())
		msleep(1);
	return 0;
}

static u64 counter_sum(void)
{
	u64 s = 0;
	unsigned int i;

	for (i = 0; i < MAX_LINES; i++)
		s += cnt[i].v;
	return s;
}

static DEFINE_MUTEX(run_lock);

static int do_run(struct kdb_run *r)
{
	const struct ops *ops;
	struct worker *ws;
	u64 before, outer;
	ktime_t t0;
	unsigned int i, cpus = r->cpus ?: r->workers;
	int ret = 0, started = 0;

	if (r->family >= KDB_NR_FAMILY || r->backend > KDB_TCLOCK || r->lines < 1 ||
	    r->lines > MAX_LINES || !r->workers || r->workers > KDB_MAX_WORKERS ||
	    cpus > r->workers || r->first_cpu + cpus > nr_cpu_ids || !r->ms)
		return -EINVAL;
	for (i = 0; i < cpus; i++)
		if (!cpu_online(r->first_cpu + i))
			return -EINVAL;
	ops = &op_table[r->backend][r->family];
	if (!ops->w && !ops->t)
		return -EOPNOTSUPP;
	/* These adapters allow one registered task per CPU. */
	if (ops->reg && cpus < r->workers)
		return -EOPNOTSUPP;
	ws = kcalloc(r->workers, sizeof(*ws), GFP_KERNEL);
	if (!ws)
		return -ENOMEM;

	g_lines = r->lines;
	/*
	 * Start every run with equal counters: a previous run with fewer lines
	 * leaves the higher lines behind, which readers would report as torn.
	 * No worker is running here.
	 */
	memset(cnt, 0, sizeof(cnt));
	ocnt.v = 0;
	hb_bad.v = 0;
	kd_spin_lock_init(&k_spin);
	kd_spin_lock_init(&k_spin2);
	kd_mutex_init(&k_mutex2);
	kd_mutex_init(&k_mutex);
	kd_rwlock_init(&k_rwl);
	kd_rwsem_init(&k_rwsem);
	for (i = 0; i < KDB_WW_LOCKS; i++)
		kd_ww_mutex_init(&k_ww[i], &kdb_ww_class);
#ifdef KDB_WITH_TCLOCK
	tc_reset();
#endif
	atomic_set(&ready, 0);
	WRITE_ONCE(stop, false);
	smp_store_release(&go, false);
	before = counter_sum();

	for (i = 0; i < r->workers; i++) {
		struct worker *w = &ws[i];

		w->cpu = r->first_cpu + i % cpus;
		w->idx = i;
		w->ops = ops;
		w->pct = (r->family == KDB_RWLOCK || r->family == KDB_RWSEM ||
			  r->family == KDB_NEST_SPIN || r->family == KDB_NEST_MUTEX ||
			  r->family == KDB_RWLOCK_HB || r->family == KDB_RWSEM_HB) ?
			 r->write_pct : 100;
		w->post = r->post;
		init_completion(&w->done);
		w->task = kthread_create(worker_fn, w, "kdb/%u.%u", w->cpu, i / cpus);
		if (IS_ERR(w->task)) {
			ret = PTR_ERR(w->task);
			w->task = NULL;
			break;
		}
		kthread_bind(w->task, w->cpu);
		wake_up_process(w->task);
		started++;
	}
	if (!ret) {
		while (atomic_read(&ready) != started)
			msleep(1);
		t0 = ktime_get();
		smp_store_release(&go, true);
		msleep(r->ms);
		WRITE_ONCE(stop, true);
		r->elapsed_ns = ktime_to_ns(ktime_sub(ktime_get(), t0));
	} else {
		WRITE_ONCE(stop, true);
		smp_store_release(&go, true);
	}
	for (i = 0; i < r->workers; i++) {
		if (!ws[i].task)
			continue;
		wait_for_completion(&ws[i].done);
		kthread_stop(ws[i].task);
		if (ws[i].reg_err && !ret)
			ret = ws[i].reg_err;
	}
	/*
	 * Registrations are released only once every registered task has
	 * exited, which follows kthread_stop() shortly; retry until then.
	 */
	if (ops->drain) {
		int d, tries = 0;

		while ((d = ops->drain()) == -EBUSY && ++tries < 1000)
			msleep(1);
		if (d && !ret)
			ret = d;
	}
	if (ret)
		goto out;

	r->ops = r->writes = r->mismatches = 0;
	outer = 0;
	for (i = 0; i < r->workers; i++) {
		r->worker_ops[i] = ws[i].ops_done;
		r->worker_writes[i] = ws[i].writes;
		r->ops += ws[i].ops_done;
		r->writes += ws[i].writes;
		r->mismatches += ws[i].bad;
		outer += ws[i].outer;
	}
	r->mismatches += hb_bad.v;
	/* Lost or extra outer-counter updates. */
	if (ocnt.v != outer)
		r->mismatches += ocnt.v > outer ? ocnt.v - outer : outer - ocnt.v;
	r->sum_delta = counter_sum() - before;
out:
	kfree(ws);
	return ret;
}

/*
 * Every kd lock API variant once, on one task: the call must leave the
 * lock, the interrupt flag and the preempt count as the native variant
 * does. Contended behaviour is covered by the timed runs.
 */
#define CK(cond) do {							\
	step++;								\
	if (!(cond)) {							\
		pr_err("kd_bench: api check %d failed: %s\n", step, #cond); \
		bad++;							\
	}								\
} while (0)

static noinline int kdb_api_test(void)
{
	static DEFINE_WD_CLASS(cls);
	struct kd_spinlock s;
	struct kd_rwlock rw;
	struct kd_mutex m;
	struct kd_rwsem sem;
	struct kd_ww_mutex w1, w2;
	struct ww_acquire_ctx ctx;
	unsigned long fl, fl2;
	int bad = 0, step = 0, pc = preempt_count();

	kd_spin_lock_init(&s);
	kd_rwlock_init(&rw);
	kd_mutex_init(&m);
	kd_rwsem_init(&sem);
	kd_ww_mutex_init(&w1, &cls);
	kd_ww_mutex_init(&w2, &cls);

	/* spinlock_t */
	kd_spin_lock(&s);
	CK(kd_spin_is_locked(&s) && preempt_count() == pc + 1);
	CK(!kd_spin_trylock(&s) && preempt_count() == pc + 1);
	CK(!kd_spin_is_contended(&s));
	kd_spin_unlock(&s);
	CK(!kd_spin_is_locked(&s) && preempt_count() == pc);
	kd_spin_lock_irq(&s);
	CK(irqs_disabled());
	kd_spin_unlock_irq(&s);
	CK(!irqs_disabled() && preempt_count() == pc);
	fl = kd_spin_lock_irqsave(&s);
	CK(irqs_disabled() && !raw_irqs_disabled_flags(fl));
	kd_spin_unlock_irqrestore(&s, fl);
	CK(!irqs_disabled() && preempt_count() == pc);
	kd_spin_lock_bh(&s);
	CK(softirq_count() && kd_spin_is_locked(&s));
	kd_spin_unlock_bh(&s);
	CK(!softirq_count() && preempt_count() == pc);
	CK(kd_spin_trylock(&s));
	kd_spin_unlock(&s);
	CK(kd_spin_trylock_bh(&s) && softirq_count());
	kd_spin_unlock_bh(&s);
	CK(kd_spin_trylock_irq(&s) && irqs_disabled());
	kd_spin_unlock_irq(&s);
	CK(kd_spin_trylock_irqsave(&s, &fl) && irqs_disabled());
	CK(!kd_spin_trylock_irqsave(&s, &fl2) && irqs_disabled());
	kd_spin_unlock_irqrestore(&s, fl);
	CK(!irqs_disabled() && preempt_count() == pc && !kd_spin_is_locked(&s));

	/* raw_spinlock_t and the arch_ level */
	kd_raw_spin_lock(&s);
	CK(kd_spin_is_locked(&s) && preempt_count() == pc + 1);
	kd_spin_unlock(&s);
	kd_raw_spin_lock_irq(&s);
	CK(irqs_disabled());
	kd_spin_unlock_irq(&s);
	fl = kd_raw_spin_lock_irqsave(&s);
	CK(irqs_disabled());
	kd_spin_unlock_irqrestore(&s, fl);
	kd_raw_spin_lock_bh(&s);
	CK(softirq_count());
	kd_spin_unlock_bh(&s);
	preempt_disable();
	kd_arch_spin_lock(&s);
	CK(kd_spin_is_locked(&s) && !kd_arch_spin_trylock(&s) && preempt_count() == pc + 1);
	kd_arch_spin_unlock(&s);
	CK(kd_arch_spin_trylock(&s));
	kd_arch_spin_unlock(&s);
	preempt_enable();
	CK(!irqs_disabled() && preempt_count() == pc && !kd_spin_is_locked(&s));

	/* rwlock_t */
	kd_write_lock(&rw);
	CK(!kd_read_trylock(&rw) && !kd_write_trylock(&rw) && preempt_count() == pc + 1);
	kd_write_unlock(&rw);
	kd_write_lock_irq(&rw);
	CK(irqs_disabled());
	kd_write_unlock_irq(&rw);
	fl = kd_write_lock_irqsave(&rw);
	CK(irqs_disabled());
	kd_write_unlock_irqrestore(&rw, fl);
	kd_write_lock_bh(&rw);
	CK(softirq_count());
	kd_write_unlock_bh(&rw);
	CK(kd_write_trylock(&rw));
	kd_write_unlock(&rw);
	CK(kd_write_trylock_irqsave(&rw, &fl) && irqs_disabled());
	kd_write_unlock_irqrestore(&rw, fl);
	kd_read_lock(&rw);
	CK(kd_read_trylock(&rw) && !kd_write_trylock(&rw));
	kd_read_unlock(&rw);
	kd_read_unlock(&rw);
	kd_read_lock_irq(&rw);
	CK(irqs_disabled());
	kd_read_unlock_irq(&rw);
	fl = kd_read_lock_irqsave(&rw);
	CK(irqs_disabled());
	kd_read_unlock_irqrestore(&rw, fl);
	kd_read_lock_bh(&rw);
	CK(softirq_count());
	kd_read_unlock_bh(&rw);
	preempt_disable();
	kd_arch_write_lock(&rw);
	CK(!kd_arch_read_trylock(&rw) && !kd_arch_write_trylock(&rw));
	kd_arch_write_unlock(&rw);
	kd_arch_read_lock(&rw);
	CK(kd_arch_read_trylock(&rw));
	kd_arch_read_unlock(&rw);
	kd_arch_read_unlock(&rw);
	CK(kd_arch_write_trylock(&rw));
	kd_arch_write_unlock(&rw);
	preempt_enable();
	CK(!kd_rwlock_is_contended(&rw) && !irqs_disabled() && preempt_count() == pc);

	/* struct mutex */
	kd_mutex_lock(&m);
	CK(kd_mutex_is_locked(&m) && !kd_mutex_trylock(&m));
	CK(kd_mutex_get_owner(&m) == (unsigned long)current);
	kd_mutex_unlock(&m);
	CK(!kd_mutex_is_locked(&m) && !kd_mutex_get_owner(&m));
	CK(kd_mutex_lock_interruptible(&m) == 0);
	kd_mutex_unlock(&m);
	CK(kd_mutex_lock_killable(&m) == 0);
	kd_mutex_unlock(&m);
	kd_mutex_lock_io(&m);
	CK(kd_mutex_is_locked(&m));
	kd_mutex_unlock(&m);
	CK(kd_mutex_trylock(&m));
	kd_mutex_unlock(&m);
	CK(preempt_count() == pc);

	/* struct ww_mutex */
	ww_acquire_init(&ctx, &cls);
	CK(kd_ww_mutex_lock(&w1, &ctx) == 0);
	CK(kd_ww_mutex_lock(&w1, &ctx) == -EALREADY);
	CK(kd_ww_mutex_lock_interruptible(&w2, &ctx) == 0);
	CK(kd_ww_mutex_is_locked(&w1) && kd_ww_mutex_is_locked(&w2) && ctx.acquired == 2);
	kd_ww_mutex_unlock(&w2);
	kd_ww_mutex_unlock(&w1);
	kd_ww_mutex_lock_slow(&w1, &ctx);
	CK(!kd_ww_mutex_trylock(&w1, &ctx) && kd_ww_mutex_trylock(&w2, &ctx));
	kd_ww_mutex_unlock(&w1);
	kd_ww_mutex_unlock(&w2);
	CK(kd_ww_mutex_lock_slow_interruptible(&w2, &ctx) == 0);
	kd_ww_mutex_unlock(&w2);
	CK(ctx.acquired == 0 && !kd_ww_mutex_is_locked(&w1) && !kd_ww_mutex_is_locked(&w2));
	ww_acquire_fini(&ctx);
	CK(kd_ww_mutex_lock(&w1, NULL) == 0);
	kd_ww_mutex_unlock(&w1);

	/* struct rw_semaphore */
	kd_down_write(&sem);
	CK(kd_rwsem_is_locked(&sem) && kd_rwsem_is_write_locked(&sem));
	CK(!kd_down_read_trylock(&sem) && !kd_down_write_trylock(&sem));
	kd_downgrade_write(&sem);
	CK(kd_rwsem_is_locked(&sem) && !kd_rwsem_is_write_locked(&sem));
	CK(kd_down_read_trylock(&sem));
	kd_up_read(&sem);
	kd_up_read(&sem);
	CK(!kd_rwsem_is_locked(&sem));
	CK(kd_down_write_killable(&sem) == 0);
	kd_up_write(&sem);
	CK(kd_down_write_trylock(&sem));
	kd_up_write(&sem);
	kd_down_read(&sem);
	CK(kd_down_read_interruptible(&sem) == 0);
	CK(kd_down_read_killable(&sem) == 0);
	CK(!kd_down_write_trylock(&sem));
	kd_up_read(&sem);
	kd_up_read(&sem);
	kd_up_read(&sem);
	CK(!kd_rwsem_is_locked(&sem) && !kd_rwsem_is_contended(&sem));
	CK(!irqs_disabled() && preempt_count() == pc);

	pr_info("kd_bench: api test: %d checks, %d failed\n", step, bad);
	return bad;
}

static long kdb_ioctl(struct file *f, unsigned int cmd, unsigned long arg)
{
	struct kdb_run *r;
	long ret;

	if (cmd == KDB_IOC_APITEST)
		return kdb_api_test();
	if (cmd != KDB_IOC_RUN)
		return -ENOTTY;
	r = kzalloc(sizeof(*r), GFP_KERNEL);
	if (!r)
		return -ENOMEM;
	ret = copy_from_user(r, (void __user *)arg, sizeof(*r)) ? -EFAULT : 0;
	if (!ret) {
		mutex_lock(&run_lock);
		ret = do_run(r);
		mutex_unlock(&run_lock);
	}
	if (!ret && copy_to_user((void __user *)arg, r, sizeof(*r)))
		ret = -EFAULT;
	kfree(r);
	return ret;
}

static const struct file_operations kdb_fops = {
	.owner		= THIS_MODULE,
	.unlocked_ioctl	= kdb_ioctl,
	.compat_ioctl	= compat_ptr_ioctl,
};

static struct miscdevice kdb_dev = {
	.minor	= MISC_DYNAMIC_MINOR,
	.name	= "kdbench",
	.fops	= &kdb_fops,
};

module_misc_device(kdb_dev);
