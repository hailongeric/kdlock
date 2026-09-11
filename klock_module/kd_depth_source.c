// SPDX-License-Identifier: GPL-2.0
#include <linux/init.h>
#include <linux/module.h>
#include <linux/mutex.h>

#include "kd_depth_source.h"

/* The first visit is an ordinary CALL miss, not a combiner-side service.
 * Once learned, these instructions must run in JIT with A already retained.
 * Seven child acquisitions fill the real frame. RET returns to the translated
 * caller, whose record stores and eighth acquisition trigger native recovery.
 * Keep record mutation in that caller instead of adding extra aliasing inputs
 * across this source boundary; no admission rule or ownership check is relaxed.
 * The native link from klock_module is separate from the additional source pin.
 */
__attribute__((noipa)) noinline void kd_depth_source_enter(struct mutex *locks)
{
	mutex_lock(&locks[0]);
	mutex_lock(&locks[1]);
	mutex_lock(&locks[2]);
	mutex_lock(&locks[3]);
	mutex_lock(&locks[4]);
	mutex_lock(&locks[5]);
	mutex_lock(&locks[6]);
}
EXPORT_SYMBOL_GPL(kd_depth_source_enter);

static int __init kd_depth_source_init(void)
{
	pr_info("kd_depth_source: loaded\n");
	return 0;
}

static void __exit kd_depth_source_exit(void)
{
	pr_info("kd_depth_source: unloaded\n");
}

module_init(kd_depth_source_init);
module_exit(kd_depth_source_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Second source module for kdlock learned-depth validation");
