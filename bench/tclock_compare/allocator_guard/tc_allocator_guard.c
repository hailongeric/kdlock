// SPDX-License-Identifier: GPL-2.0
/* Linux 6.1 reserved-percpu hint refresh for alternating module experiments.
 * Freeing a sub-page provider can leave overlapping chunk scan/contig hints:
 * pcpu_next_hint then skips a valid cross-page hole for the larger provider.
 * A whole-page allocation/free makes pcpu_block_update_hint_free refresh the
 * chunk hints through the allocator's normal path. No metadata is patched.
 * This module installs no hooks and is unloaded before EVERY backend session.
 */
#include <linux/module.h>
#include <linux/percpu.h>

static DEFINE_PER_CPU(char, reservation[PAGE_SIZE]) __used;

static int __init guard_init(void)
{
    return 0;
}
static void __exit guard_exit(void)
{
}
module_init(guard_init);
module_exit(guard_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Benchmark preparation: refresh reserved per-CPU hints");
