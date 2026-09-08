/*
 * Hot-lock detection for deciding when delegation is worth its setup cost.
 *
 * The table is append-only for the lifetime of the module. A single raw lock
 * protects slot publication and sampling because hooks may run with IRQs off.
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
static atomic_long_t kd_hotlock_window_cycles;

static struct kd_hotlock_state *
kd_hotlock_lookup_locked(unsigned long lock_addr, bool create)
{
	unsigned int pos = lock_addr % KD_HOTLOCK_TABLE_SIZE;
	unsigned int probes;

	for (probes = 0; probes < KD_HOTLOCK_TABLE_SIZE; probes++) {
		struct kd_hotlock_state *state = &kd_hotlocks[pos];

		if (state->lock_addr == lock_addr)
			return state;
		if (!state->lock_addr) {
			if (!create)
				return NULL;
			state->lock_addr = lock_addr;
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
	atomic_long_set(&kd_hotlock_window_cycles, KD_HOTLOCK_INITIAL_WINDOW);
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
	state = kd_hotlock_lookup_locked(lock_addr, true);
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
	state = kd_hotlock_lookup_locked(lock_addr, true);
	if (!state)
		goto out;

	if (state->status == KD_HOTLOCK_DELEGATE) {
		promoted = 1;
		goto out;
	}

	state->samples++;
	if (state->status == KD_HOTLOCK_IGNORE) {
		if (state->samples == KD_HOTLOCK_SAMPLE_TARGET)
			state->end_cycles = now;
		goto out;
	}

	if (state->status == KD_HOTLOCK_INIT) {
		state->status = KD_HOTLOCK_CHECKING;
		state->begin_cycles = now;
		/* Another lock may tighten the global window while this sample is
		 * in flight. Apply that threshold only to newly started samples. */
		state->sample_window = atomic_long_read(&kd_hotlock_window_cycles);
		goto out;
	}

	state->end_cycles = now;
	if (state->end_cycles - state->begin_cycles >= state->sample_window) {
		state->status = KD_HOTLOCK_IGNORE;
	} else if (state->samples == KD_HOTLOCK_SAMPLE_TARGET) {
		unsigned long old_window;
		unsigned long new_window;
		unsigned long elapsed = state->end_cycles - state->begin_cycles;

		state->status = KD_HOTLOCK_DELEGATE;
		KD_PR_INFO("uaddr %lx begin delegate\n", lock_addr);
		old_window = atomic_long_read(&kd_hotlock_window_cycles);
		new_window = old_window;
		while (elapsed && new_window / elapsed >= 10)
			new_window /= 10;
		if (new_window != old_window)
			atomic_long_cmpxchg(&kd_hotlock_window_cycles,
					    old_window, new_window);
		promoted = 1;
	}

out:
	raw_spin_unlock_irqrestore(&kd_hotlock_table_lock, flags);
	return promoted;
}

bool kd_hotlock_is_promoted(unsigned long lock_addr)
{
	struct kd_hotlock_state *state;
	unsigned long flags;
	bool promoted = false;

	if (!lock_addr || !kd_hotlocks)
		return false;

	raw_spin_lock_irqsave(&kd_hotlock_table_lock, flags);
	state = kd_hotlock_lookup_locked(lock_addr, false);
	if (state)
		promoted = state->status == KD_HOTLOCK_DELEGATE;
	raw_spin_unlock_irqrestore(&kd_hotlock_table_lock, flags);
	return promoted;
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
	state = kd_hotlock_lookup_locked(addr, true);
	if (state) {
		state->status = KD_HOTLOCK_DELEGATE;
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
