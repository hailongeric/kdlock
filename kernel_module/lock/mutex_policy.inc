// SPDX-License-Identifier: GPL-2.0
/* Opt-in locality epochs change only admission for a future acquisition.
 * They never authorize ownership, cancel a published request, or retire a
 * frame. Linux's original mutex excludes native peers while older KD work
 * drains through the ordinary queue, including a late policy reader. */
#include <linux/jiffies.h>
#include <linux/topology.h>

static unsigned int mutex_native_epoch_ms;
static unsigned int mutex_native_probe_ms = 1;
static bool mutex_native_epoch_cache;
static bool mutex_native_epoch_cross_node;
module_param(mutex_native_epoch_cache, bool, 0444);
MODULE_PARM_DESC(mutex_native_epoch_cache,
	"Cache exact-address epoch hints on each CPU and share the admission pin");
module_param(mutex_native_epoch_cross_node, bool, 0444);
MODULE_PARM_DESC(mutex_native_epoch_cross_node,
	"Permit bounded native epochs across NUMA nodes instead of applying the remote veto");

struct kd_mutex_policy_cache {
	unsigned long address;
	struct kd_mutex *shadow;
};
static DEFINE_PER_CPU(struct kd_mutex_policy_cache, kd_mutex_policy_cache);

/* A hit supplies only a resident shadow identity, never an acquisition.
 * The table's immutable exact-address lookup created this pair; neither that
 * shadow nor this per-CPU cache can outlive the provider. Pinned task-context
 * readers/writers cannot observe a partially refreshed local pair. */
static __always_inline struct kd_mutex *
kd_mutex_policy_cached_pinned(struct mutex *lock)
{
	struct kd_mutex_policy_cache *cache = this_cpu_ptr(&kd_mutex_policy_cache);

	if (cache->address != (unsigned long)lock)
		return NULL;
	return cache->shadow;
}

static int kd_mutex_policy_ms_set(const char *value,
				  const struct kernel_param *kp)
{
	unsigned int milliseconds;
	int ret = kstrtouint(value, 0, &milliseconds);

	if (ret)
		return ret;
	if (milliseconds > 1000 ||
	    (!milliseconds && kp->arg == &mutex_native_probe_ms))
		return -EINVAL;
	*(unsigned int *)kp->arg = milliseconds;
	return 0;
}

static const struct kernel_param_ops kd_mutex_policy_ms_ops = {
	.set = kd_mutex_policy_ms_set,
	.get = param_get_uint,
};
module_param_cb(mutex_native_epoch_ms, &kd_mutex_policy_ms_ops,
		&mutex_native_epoch_ms, 0444);
MODULE_PARM_DESC(mutex_native_epoch_ms,
	"Locality policy native/cross-node cooldown duration, 0 disables (0..1000 ms)");
module_param_cb(mutex_native_probe_ms, &kd_mutex_policy_ms_ops,
		&mutex_native_probe_ms, 0444);
MODULE_PARM_DESC(mutex_native_probe_ms,
	"Locality policy delegation probe, rounded up to at least one jiffy (1..1000 ms)");

enum kd_mutex_policy_mode {
	KD_MUTEX_POLICY_EMPTY,
	KD_MUTEX_POLICY_PROBE,
	KD_MUTEX_POLICY_NATIVE,
	KD_MUTEX_POLICY_MULTINODE,
	KD_MUTEX_POLICY_UPDATING,
};

/* Atomic phase/home/generation publication preserves a remote veto racing
 * with probe expiry. All 32 bits of the NUMA ID and the full jiffies deadline
 * are retained. Updating readers conservatively delegate; policy may not wait
 * for a descheduled publisher. A generation distinguishes repeated phases. */
#define KD_MUTEX_POLICY_MODE_MASK 7UL
#define KD_MUTEX_POLICY_NODE_SHIFT 3
#define KD_MUTEX_POLICY_GEN_SHIFT 35
#define KD_MUTEX_POLICY_GEN_UNIT (1UL << KD_MUTEX_POLICY_GEN_SHIFT)
#define KD_MUTEX_POLICY_GEN_MASK (~(KD_MUTEX_POLICY_GEN_UNIT - 1))

struct kd_mutex_policy_slot {
	atomic_long_t word;
	unsigned long deadline;
} ____cacheline_aligned;

/* Shadow slots are exact-address identities and never recycled before unload.
 * Keep policy traffic off the actual owner, queue tail and waiter counters. */
static struct kd_mutex_policy_slot
	kd_mutex_policy_slots[KD_MUTEX_WAITER_SLOTS];
static DEFINE_PER_CPU(unsigned long, kd_mutex_policy_native_epochs);
static DEFINE_PER_CPU(unsigned long, kd_mutex_policy_probes);
static DEFINE_PER_CPU(unsigned long, kd_mutex_policy_remote_vetoes);

static int kd_mutex_policy_stats_get(char *buffer,
				     const struct kernel_param *kp)
{
	unsigned long native = 0, probes = 0, remote = 0;
	int cpu;

	(void)kp;
	for_each_possible_cpu(cpu) {
		native += per_cpu(kd_mutex_policy_native_epochs, cpu);
		probes += per_cpu(kd_mutex_policy_probes, cpu);
		remote += per_cpu(kd_mutex_policy_remote_vetoes, cpu);
	}
	return scnprintf(buffer, PAGE_SIZE, "%lu %lu %lu\n", native, probes, remote);
}
static const struct kernel_param_ops kd_mutex_policy_stats_ops = {
	.get = kd_mutex_policy_stats_get,
};
module_param_cb(mutex_native_epoch_stats, &kd_mutex_policy_stats_ops, NULL, 0444);
MODULE_PARM_DESC(mutex_native_epoch_stats,
	"Locality policy transitions: native epochs, delegation probes, remote vetoes");

static unsigned long kd_mutex_policy_word(enum kd_mutex_policy_mode mode,
					  unsigned int node, unsigned long old)
{
	return (unsigned long)mode |
	       ((unsigned long)node << KD_MUTEX_POLICY_NODE_SHIFT) |
	       ((old + KD_MUTEX_POLICY_GEN_UNIT) & KD_MUTEX_POLICY_GEN_MASK);
}

/* The caller owns a short preemption pin only for the locality observation.
 * A decision is a routing hint. An older KD entry may still publish afterwards;
 * neither native epochs nor their expiry wait for or rewrite that queue. */
static bool kd_mutex_policy_native_pinned(struct kd_mutex *lock)
{
	struct kd_mutex_policy_slot *slot;
	unsigned int node = (unsigned int)numa_node_id();
	unsigned long now = jiffies;
	unsigned int retry;

	if (lock->waiter_slot < 0 || lock->waiter_slot >= KD_MUTEX_WAITER_SLOTS)
		return false;
	slot = &kd_mutex_policy_slots[lock->waiter_slot];
	/* A competing transition can delay this observation, never the caller.
	 * Four attempts bound policy work independently of another CPU's progress. */
	for (retry = 0; retry < 4; retry++) {
		unsigned long old = atomic_long_read_acquire(&slot->word);
		enum kd_mutex_policy_mode mode = old & KD_MUTEX_POLICY_MODE_MASK;
		unsigned int home = (unsigned int)(old >> KD_MUTEX_POLICY_NODE_SHIFT);
		unsigned long deadline, next, updating;
		unsigned int period;
		bool remote = false;

		if (mode == KD_MUTEX_POLICY_UPDATING)
			return false;
		deadline = READ_ONCE(slot->deadline);
		/* Recheck after metadata; a changed generation rejects the sample. */
		smp_rmb();
		if (atomic_long_read(&slot->word) != old)
			continue;
		if (mode == KD_MUTEX_POLICY_EMPTY) {
			mode = KD_MUTEX_POLICY_PROBE;
			home = node;
		} else if (!mutex_native_epoch_cross_node &&
			   (mode == KD_MUTEX_POLICY_PROBE ||
			    mode == KD_MUTEX_POLICY_NATIVE) && node != home) {
			/* Locality is a profitability hypothesis, not exclusion. The
			 * opt-in cross-node experiment retains both bounded phases and
			 * changes only this veto; queued work/owners are untouched. */
			mode = KD_MUTEX_POLICY_MULTINODE;
			remote = true;
		} else if (time_before(now, deadline)) {
			return mode == KD_MUTEX_POLICY_NATIVE;
		} else if (mode == KD_MUTEX_POLICY_PROBE) {
			mode = KD_MUTEX_POLICY_NATIVE;
		} else {
			/* Native time is bounded; multicore locality is periodically
			 * observed anew after a remote cohort disappears as well. */
			mode = KD_MUTEX_POLICY_PROBE;
			home = node;
		}
		next = kd_mutex_policy_word(mode, home, old);
		updating = (old & ~KD_MUTEX_POLICY_MODE_MASK) | KD_MUTEX_POLICY_UPDATING;
		if (atomic_long_cmpxchg(&slot->word, old, updating) == old) {
			period = mode == KD_MUTEX_POLICY_PROBE ?
				mutex_native_probe_ms : mutex_native_epoch_ms;
			WRITE_ONCE(slot->deadline, now +
				max_t(unsigned long, 1, msecs_to_jiffies(period)));
			atomic_long_set_release(&slot->word, next);
			if (mode == KD_MUTEX_POLICY_NATIVE)
				this_cpu_inc(kd_mutex_policy_native_epochs);
			else if (mode == KD_MUTEX_POLICY_PROBE)
				this_cpu_inc(kd_mutex_policy_probes);
			if (remote)
				this_cpu_inc(kd_mutex_policy_remote_vetoes);
			return mode == KD_MUTEX_POLICY_NATIVE;
		}
	}
	return false;
}

static bool kd_mutex_policy_native(struct kd_mutex *lock)
{
	bool native;

	if (likely(!mutex_native_epoch_ms))
		return false;
	preempt_disable();
	if (mutex_native_epoch_cache) {
		struct kd_mutex_policy_cache *cache = this_cpu_ptr(&kd_mutex_policy_cache);

		cache->shadow = lock;
		cache->address = READ_ONCE(lock->origin_mutex_addr);
	}
	native = kd_mutex_policy_native_pinned(lock);
	preempt_enable();
	return native;
}
