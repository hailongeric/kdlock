// SPDX-License-Identifier: GPL-2.0
/* Included by kd_lock.c in SELFTEST builds only. Observe the real map under
 * acquire-published immutable keys; do not shrink it, populate entries or retain owners.
 */
static int kd_mutex_shadow_count_get(char *buffer,
				     const struct kernel_param *param)
{
	unsigned int i, count = 0;

	(void)param;
	for (i = 0; i < ARRAY_SIZE(kd_mutex_shadows); i++)
		count += !!smp_load_acquire(&kd_mutex_shadows[i].kd_mtx.origin_mutex_addr);
	return scnprintf(buffer, PAGE_SIZE, "%u\n", count);
}

static const struct kernel_param_ops kd_mutex_shadow_count_ops = {
	.get = kd_mutex_shadow_count_get,
};
module_param_cb(mutex_selftest_shadow_count, &kd_mutex_shadow_count_ops, NULL,
		0444);
MODULE_PARM_DESC(mutex_selftest_shadow_count,
		 "selftest-only: read the allocated native-mutex shadow count");
