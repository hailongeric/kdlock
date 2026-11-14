/* SPDX-License-Identifier: GPL-2.0-only */
/* Cold control and preallocated physical-worker rows for the temporary probe. */
#include <linux/slab.h>
#include <linux/vmalloc.h>
#include "../../kernel/rw_wait_diag.h"
#if defined(RB_KDLOCK) && defined(RB_RWSEM)
#include "../../kernel/rw_native.h"
#endif

static struct kd_rw_wait_diag_row rb_wait_rows[RB_MAX_WORKERS];
static unsigned int rb_wait_finished[RB_MAX_WORKERS];
static bool rb_wait_enabled, rb_wait_phase_enabled, rb_wait_phase_valid;

static bool rb_wait_supported(void)
{
#if defined(RB_RWSEM) && !defined(RB_TCLOCK)
	return IS_ENABLED(CONFIG_KDLOCK_RW_WAIT_DIAG);
#else
	return false;
#endif
}

static int rb_wait_quiescent(void)
{
	struct rw_bench_snapshot snap = { 0 };
#ifdef RB_KDLOCK
	unsigned int i;

	/* The caller holds rb_control at -1, excluding all worker ioctls.
	 * Exact leave must have ended every task/control user, not just a timer.
	 */
	if (!rb_runtime || !rb_evidence)
		return -ESHUTDOWN;
	for (i = 0; i < RB_MAX_WORKERS; ++i)
		if (rb_evidence[i].storage)
			return -EBUSY;
#endif
	rb_lock_snapshot(&snap);
	if (snap.gate || snap.cnts)
		return -EBUSY;
#if defined(RB_KDLOCK) && defined(RB_RWSEM)
	if (waitqueue_active(&rb_lock.core.changed) ||
	    (rb_lock.core.native_pool && !kd_rw_native_pool_idle(rb_lock.core.native_pool)))
		return -EBUSY;
#endif
	return 0;
}

static int rb_wait_reset(void)
{
	int error = rb_wait_quiescent();

	if (error)
		return error;
	/* Only independent counter storage is cleared, after complete drain. */
	memset(rb_wait_rows, 0, sizeof(rb_wait_rows));
	memset(rb_wait_finished, 0, sizeof(rb_wait_finished));
	rb_wait_phase_enabled = rb_wait_enabled;
	rb_wait_phase_valid = true;
	return 0;
}

static int rb_wait_set(struct rb_wait_diag_mode *mode)
{
	int error;

	if (mode->enabled > 1 || mode->supported)
		return -EINVAL;
	if (mode->enabled && !rb_wait_supported())
		return -EOPNOTSUPP;
#ifdef RB_KDLOCK
	if (mode->enabled && delegation)
		return -EINVAL;
#endif
	error = rb_wait_quiescent();
	if (error)
		return error;
	if (rb_wait_enabled != mode->enabled)
		rb_wait_phase_valid = false;
	rb_wait_enabled = mode->enabled;
	mode->supported = rb_wait_supported();
	return 0;
}

static int rb_wait_enter(unsigned int worker)
{
	if (!rb_wait_phase_valid)
		return -EINVAL;
#if defined(RB_KDLOCK) && defined(RB_RWSEM)
	if (rb_wait_phase_enabled)
		return kd_rw_wait_diag_attach(&rb_lock.core, &rb_wait_rows[worker]);
#endif
	return 0;
}

static void rb_wait_end(unsigned int worker, int error)
{
	/* Own worker only; later readers are excluded until rb_control drains. */
	rb_wait_finished[worker] = error ? 2 : 1;
}

static int rb_wait_snapshot(void __user *user)
{
	struct rb_wait_diag_snapshot *snap;
	unsigned int i;
	int error = rb_wait_quiescent();

	if (error)
		return error;
	if (!rb_wait_phase_valid || !rb_config.started_ns)
		return -EINVAL;
	snap = kvzalloc(sizeof(*snap), GFP_KERNEL);
	if (!snap)
		return -ENOMEM;
	snap->version = KD_RW_WAIT_DIAG_VERSION;
	snap->counter_count = KD_RW_DIAG_COUNT;
	snap->enabled = rb_wait_phase_enabled;
	snap->supported = rb_wait_supported();
	snap->workers = rb_config.workers;
	snap->backend = RB_BACKEND;
	snap->started_ns = rb_config.started_ns;
	snap->complete = 1;
#if defined(RB_KDLOCK) && defined(RB_RWSEM)
	snap->node_wait = IS_ENABLED(CONFIG_KDLOCK_RWSEM_NODE_WAIT);
#endif
	for (i = 0; i < RB_MAX_WORKERS; ++i) {
		snap->rows[i] = rb_wait_rows[i].counts;
		if (i < rb_config.workers && rb_wait_finished[i] != 1)
			snap->complete = 0;
	}
	error = copy_to_user(user, snap, sizeof(*snap)) ? -EFAULT : 0;
	kvfree(snap);
	return error;
}
