/*
 * Approximate CPU-local frequency admission. Unpromoted addresses, counters
 * and windows never enter shared storage. The append-only global set contains
 * promoted identities only, and lives until hooks and protocol readers drain.
 */
#include <asm/tsc.h>
#include <linux/errno.h>
#include <linux/hash.h>
#include <linux/percpu.h>
#include <linux/preempt.h>
#include <linux/vmalloc.h>
#ifdef KDLOCK_SELFTEST
#include <linux/module.h>
#endif

#include "kd_hotlock.h"
#include "utils.h"

#define KD_HOTLOCK_TABLE_SIZE 131071
#define KD_HOTLOCK_CHECK_INTERVAL 10240U
/* Preserve the old CPU rate of 256 observations / 1e9 TSC ticks while
 * checking larger blocks. This trades detection latency for fewer clocks. */
#define KD_HOTLOCK_CPU_WINDOW 40000000000UL
#define KD_HOTLOCK_INITIAL_WINDOW 2500000000UL
#define KD_HOTLOCK_SAMPLE_TARGET 10000U
#define KD_HOTLOCK_LOCAL_BITS 6

struct kd_hotlock_local {
	unsigned long lock_addr;
	unsigned long begin_cycles;
	unsigned int samples;
	unsigned int promoted;
};

struct kd_hotlock_cpu {
	unsigned int busy;
	unsigned int rate_samples;
	unsigned long rate_begin;
	unsigned int rate_hot;
	struct kd_hotlock_local slots[1 << KD_HOTLOCK_LOCAL_BITS];
} ____cacheline_aligned;

/* Allocated once before hooks start; no static module-percpu reserve or
 * per-call allocation. This pointer is infrastructure, not shared rate state. */
static struct kd_hotlock_cpu __percpu *kd_hotlock_cpu;
static unsigned long *kd_hotlocks;

/* Each nonzero word is a complete, immutable promoted identity. Inspect the
 * winning key after a failed CAS before probing ahead, so concurrent publishers
 * of the same address converge on one slot. No counters/timestamps are shared. */
static bool kd_hotlock_lookup(unsigned long lock_addr, bool publish)
{
	unsigned long *table = READ_ONCE(kd_hotlocks);
	unsigned int pos = lock_addr % KD_HOTLOCK_TABLE_SIZE;
	unsigned int probes;

	if (!lock_addr || !table)
		return false;
	for (probes = 0; probes < KD_HOTLOCK_TABLE_SIZE; probes++) {
		unsigned long addr = READ_ONCE(table[pos]);

		if (!addr && publish) {
			addr = cmpxchg(&table[pos], 0, lock_addr);
			if (!addr) {
				KD_PR_INFO("uaddr %lx begin delegate\n", lock_addr);
				return true;
			}
		}
		if (addr == lock_addr)
			return true;
		if (!addr)
			return false;
		if (++pos == KD_HOTLOCK_TABLE_SIZE)
			pos = 0;
	}
	return false;
}

int kd_hotlock_init(void)
{
	unsigned int cpu;

	kd_hotlocks = vzalloc(array_size(KD_HOTLOCK_TABLE_SIZE,
				       sizeof(*kd_hotlocks)));
	if (!kd_hotlocks)
		return -ENOMEM;
	kd_hotlock_cpu = alloc_percpu(struct kd_hotlock_cpu);
	if (!kd_hotlock_cpu) {
		vfree(kd_hotlocks);
		kd_hotlocks = NULL;
		return -ENOMEM;
	}
	for_each_possible_cpu(cpu)
		memset(per_cpu_ptr(kd_hotlock_cpu, cpu), 0,
		       sizeof(struct kd_hotlock_cpu));
	return 0;
}

void kd_hotlock_exit(void)
{
	/* No flush: shutdown must not turn pending local counts into promotions.
	 * No global discovery diagnostics remain; publication logs identify hot keys. */
	vfree(kd_hotlocks);
	kd_hotlocks = NULL;
	free_percpu(kd_hotlock_cpu);
	kd_hotlock_cpu = NULL;
}

/* Called only at a CPU clock boundary. All 64 candidates share this one clock
 * sample. Their origins use the preceding CPU boundary, conservatively earlier
 * than the actual first hit: a cache miss or collision never reads the clock.
 * Expired candidates restart locally, so a formerly cold lock can heat up later.
 * A full global set rejects admission and retries only after another local quota. */
static void kd_hotlock_check_local(struct kd_hotlock_cpu *cpu,
				   unsigned long now, bool continuous)
{
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(cpu->slots); i++) {
		struct kd_hotlock_local *local = &cpu->slots[i];

		if (!local->lock_addr || local->promoted)
			continue;
		if (!continuous || now < local->begin_cycles ||
		    now - local->begin_cycles >= KD_HOTLOCK_INITIAL_WINDOW) {
			local->begin_cycles = now ?: 1;
			local->samples = 0;
		} else if (local->samples >= KD_HOTLOCK_SAMPLE_TARGET) {
			local->promoted = kd_hotlock_lookup(local->lock_addr, true);
			local->begin_cycles = now ?: 1;
			local->samples = 0;
		}
	}
}

/* All ordinary acquisitions contribute before task selection. After the first
 * origin read, exactly one TSC read per 10240 observations also evaluates local
 * lock windows. Cooling closes new admission at the next boundary (up to 10239
 * further observations); no timer or shared rate flag is needed. Retained hot
 * identities survive cooling, while outstanding unlocks never use this gate. */
static bool kd_hotlock_cpu_frequent(struct kd_hotlock_cpu *cpu)
{
	unsigned long now;
	bool was_hot;

	if (!cpu->rate_begin) {
		cpu->rate_begin = rdtsc_ordered() ?: 1;
		cpu->rate_samples = 1;
		return false;
	}
	if (++cpu->rate_samples < KD_HOTLOCK_CHECK_INTERVAL)
		return cpu->rate_hot;
	now = rdtsc_ordered();
	was_hot = cpu->rate_hot;
	cpu->rate_hot = now >= cpu->rate_begin &&
		       now - cpu->rate_begin < KD_HOTLOCK_CPU_WINDOW;
	cpu->rate_begin = now ?: 1;
	cpu->rate_samples = 0;
	kd_hotlock_check_local(cpu, now, was_hot && cpu->rate_hot);
	return cpu->rate_hot;
}

int kd_hotlock_record(unsigned long lock_addr)
{
	struct kd_hotlock_cpu *cpu;
	struct kd_hotlock_local *local;
	int promoted = 0;

	if (!lock_addr || !READ_ONCE(kd_hotlock_cpu))
		return 0;
	/* Stable CPU plus a non-waiting CPU-local cmpxchg; IRQ/NMI reentry drops
	 * its sample without IRQ masking or a global statistics lock. */
	preempt_disable();
	if (this_cpu_cmpxchg(kd_hotlock_cpu->busy, 0, 1)) {
		preempt_enable();
		return 0;
	}
	cpu = this_cpu_ptr(kd_hotlock_cpu);
	if (!kd_hotlock_cpu_frequent(cpu))
		goto out;
	local = &cpu->slots[hash_long(lock_addr, KD_HOTLOCK_LOCAL_BITS)];
	if (local->lock_addr != lock_addr) {
		/* A collision discards approximate local history, never transfers
		 * counts or a positive hint to another address. No shared lookup. */
		local->lock_addr = lock_addr;
		local->begin_cycles = cpu->rate_begin;
		local->samples = 0;
		local->promoted = 0;
	}
	promoted = local->promoted;
	if (!promoted && local->samples < KD_HOTLOCK_SAMPLE_TARGET)
		local->samples++;
out:
	barrier();
	this_cpu_write(kd_hotlock_cpu->busy, 0);
	preempt_enable();
	return promoted;
}

bool kd_hotlock_is_promoted(unsigned long lock_addr)
{
	/* Existing/nested protocols may query the immutable shared identity.
	 * Fresh roots must establish their own CPU/local frequency via record(). */
	return kd_hotlock_lookup(lock_addr, false);
}

#ifdef KDLOCK_SELFTEST
/* Controlled identity publication for existing/nested protocol tests only.
 * It does not bypass fresh roots' CPU/local frequency checks. */
static unsigned long spin_selftest_promote;

static int kd_hotlock_test_promote_set(const char *value,
				       const struct kernel_param *param)
{
	unsigned long addr;
	int ret = kstrtoul(value, 0, &addr);

	if (ret || !addr)
		return ret ? ret : -EINVAL;
	if (!kd_hotlocks)
		return -EAGAIN;
	if (!kd_hotlock_lookup(addr, true))
		return -ENOSPC;
	*(unsigned long *)param->arg = addr;
	KD_PR_INFO("kd_hotlock selftest promote: lock=%lx\n", addr);
	return 0;
}

static const struct kernel_param_ops kd_hotlock_test_promote_ops = {
	.set = kd_hotlock_test_promote_set,
	.get = param_get_ulong,
};
module_param_cb(spin_selftest_promote, &kd_hotlock_test_promote_ops,
		&spin_selftest_promote, 0600);
MODULE_PARM_DESC(
	spin_selftest_promote,
	"Recovery test only: publish one original hot lock identity");
#endif
