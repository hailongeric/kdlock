// SPDX-License-Identifier: GPL-2.0
/* Retry registered-context drain only after the probe has joined its workers. */
#include <linux/module.h>
extern int tc_rwsem_workers_drain(void);
static int __init reap_init(void)
{
	int ret = tc_rwsem_workers_drain();
	pr_info("tc-original-reap: drain=%d\n", ret);
	return ret;
}
static void __exit reap_exit(void) {}
module_init(reap_init);
module_exit(reap_exit);
MODULE_LICENSE("GPL");
