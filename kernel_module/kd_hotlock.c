/*
 * Hot-lock detection for deciding when delegation is worth its setup cost.
 *
 * The table is append-only for the lifetime of the module. A single raw lock
 * serializes writers because hooks may run with IRQs off. Promotion queries
 * only read published slots; teardown still requires callers to be drained.
 */
#include <asm/tsc.h>
#include <linux/errno.h>
#include <linux/spinlock.h>
#include <linux/vmalloc.h>
#ifdef KDLOCK_SELFTEST
#include <linux/module.h>
#endif

#include "kd_hotlock.h"
#include "utils.h"

#define KD_HOTLOCK_TABLE_SIZE 131071
#define KD_HOTLOCK_WARMUP_CYCLES 1000000000UL
#define KD_HOTLOCK_INITIAL_WINDOW 2500000000UL
#define KD_HOTLOCK_SAMPLE_TARGET 10000U

static struct kd_hotlock_state *kd_hotlocks;
static DEFINE_RAW_SPINLOCK(kd_hotlock_table_lock);
static atomic_long_t kd_hotlock_start_cycles;

static struct kd_hotlock_state *
kd_hotlock_get_locked(unsigned long lock_addr)
{
	unsigned int pos = lock_addr % KD_HOTLOCK_TABLE_SIZE;
	unsigned int probes;

	for (probes = 0; probes < KD_HOTLOCK_TABLE_SIZE; probes++) {
		struct kd_hotlock_state *state = &kd_hotlocks[pos];

		if (state->lock_addr == lock_addr)
			return state;
		if (!state->lock_addr) {
			/* Publish the zero-initialized slot to lockless readers. Slots
			 * are never removed, reused or moved while hooks can run. */
			smp_store_release(&state->lock_addr, lock_addr);
			return state;
		}
		pos = (pos + 1) % KD_HOTLOCK_TABLE_SIZE;
	}

	return NULL;
}

int kd_hotlock_init(void)
{
	kd_hotlocks = vzalloc(
		array_size(KD_HOTLOCK_TABLE_SIZE, sizeof(*kd_hotlocks)));
	if (!kd_hotlocks)
		return -ENOMEM;

	atomic_long_set(&kd_hotlock_start_cycles, 0);
	return 0;
}

void kd_hotlock_exit(void)
{
	unsigned int i;

	if (!kd_hotlocks)
		return;

	for (i = 0; i < KD_HOTLOCK_TABLE_SIZE; i++) {
		struct kd_hotlock_state *state = &kd_hotlocks[i];

		if (state->lock_addr && state->samples > 100)
			KD_PR_INFO(
				"hotlock: addr=%lx cycles=%lu status=%d samples=%u\n",
				state->lock_addr,
				state->end_cycles - state->begin_cycles,
				state->status, state->samples);
	}

	vfree(kd_hotlocks);
	kd_hotlocks = NULL;
}

struct kd_hotlock_state *kd_hotlock_state_get(unsigned long lock_addr)
{
	struct kd_hotlock_state *state;
	unsigned long flags;

	if (!lock_addr || !kd_hotlocks)
		return NULL;

	raw_spin_lock_irqsave(&kd_hotlock_table_lock, flags);
	state = kd_hotlock_get_locked(lock_addr);
	raw_spin_unlock_irqrestore(&kd_hotlock_table_lock, flags);
	return state;
}

int kd_hotlock_record(unsigned long lock_addr)
{
	struct kd_hotlock_state *state;
	unsigned long flags;
	unsigned long now = rdtsc_ordered();
	unsigned long start;
	int promoted = 0;

	start = atomic_long_read(&kd_hotlock_start_cycles);
	if (!start) {
		atomic_long_cmpxchg(&kd_hotlock_start_cycles, 0, now);
		return 0;
	}
	if (now - start < KD_HOTLOCK_WARMUP_CYCLES)
		return 0;
	if (!lock_addr || !kd_hotlocks)
		return 0;

	raw_spin_lock_irqsave(&kd_hotlock_table_lock, flags);
	state = kd_hotlock_get_locked(lock_addr);
	if (!state)
		goto out;

	if (state->status == KD_HOTLOCK_DELEGATE) {
		promoted = 1;
		goto out;
	}

	/* A caller can sample TSC first but acquire this lock after another
	 * caller started the window. Read again in update order, otherwise an
	 * older timestamp underflows elapsed time and permanently selects IGNORE.
	 * The earlier read is only the module-wide warmup fast check. */
	now = rdtsc_ordered();
	state->samples++;
	if (state->status == KD_HOTLOCK_IGNORE) {
		if (state->samples == KD_HOTLOCK_SAMPLE_TARGET)
			state->end_cycles = now;
		goto out;
	}

	if (state->status == KD_HOTLOCK_INIT) {
		WRITE_ONCE(state->status, KD_HOTLOCK_CHECKING);
		state->begin_cycles = now;
		/* Judge each lock against the same frequency threshold. A fast A
		 * must not permanently suppress a later B by shrinking its window;
		 * discovery order is not evidence of B's contention or JIT benefit.
		 * This changes promotion only, never lock exclusion or admission. */
		state->sample_window = KD_HOTLOCK_INITIAL_WINDOW;
		goto out;
	}

	state->end_cycles = now;
	if (state->end_cycles - state->begin_cycles >= state->sample_window) {
		WRITE_ONCE(state->status, KD_HOTLOCK_IGNORE);
	} else if (state->samples == KD_HOTLOCK_SAMPLE_TARGET) {
		WRITE_ONCE(state->status, KD_HOTLOCK_DELEGATE);
		KD_PR_INFO("uaddr %lx begin delegate\n", lock_addr);
		promoted = 1;
	}

out:
	raw_spin_unlock_irqrestore(&kd_hotlock_table_lock, flags);
	return promoted;
}

bool kd_hotlock_is_promoted(unsigned long lock_addr)
{
	struct kd_hotlock_state *table = READ_ONCE(kd_hotlocks);
	unsigned int pos = lock_addr % KD_HOTLOCK_TABLE_SIZE;
	unsigned int probes;

	if (!lock_addr || !table)
		return false;

	/* Match the writer's probe order. An empty slot ends the search because
	 * entries are append-only. A racing insertion/promotion may return false;
	 * callers then use the serialized sampler and the original native lock.
	 * Status is only an admission hint, not publication of sampling data or
	 * JIT code. No reader lock/RMW or IRQ masking is needed here. */
	for (probes = 0; probes < KD_HOTLOCK_TABLE_SIZE; probes++) {
		struct kd_hotlock_state *state = &table[pos];
		unsigned long addr = smp_load_acquire(&state->lock_addr);

		if (addr == lock_addr)
			return READ_ONCE(state->status) == KD_HOTLOCK_DELEGATE;
		if (!addr)
			return false;
		pos = (pos + 1) % KD_HOTLOCK_TABLE_SIZE;
	}

	return false;
}

#ifdef KDLOCK_SELFTEST
/* Recovery fixtures control promotion before a chain or while a native owner
 * holds L. Real acquisitions/queues/JIT stay unchanged; production excludes it. */
static unsigned long spin_selftest_promote;

static int kd_hotlock_test_promote_set(const char *value,
				       const struct kernel_param *param)
{
	struct kd_hotlock_state *state;
	unsigned long addr, flags;
	int ret = kstrtoul(value, 0, &addr);

	if (ret || !addr)
		return ret ? ret : -EINVAL;
	if (!kd_hotlocks)
		return -EAGAIN;
	raw_spin_lock_irqsave(&kd_hotlock_table_lock, flags);
	state = kd_hotlock_get_locked(addr);
	if (state) {
		WRITE_ONCE(state->status, KD_HOTLOCK_DELEGATE);
		*(unsigned long *)param->arg = addr;
	}
	raw_spin_unlock_irqrestore(&kd_hotlock_table_lock, flags);
	if (!state)
		return -ENOSPC;
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
	"Recovery test only: promote one original lock at a controlled boundary");
#endif
