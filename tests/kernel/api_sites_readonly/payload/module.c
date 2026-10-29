// SPDX-License-Identifier: GPL-2.0
/* Inspect only the fixed built-in site table; never attempt a write probe. */
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/kd_api_provider.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/preempt.h>
#include <asm/pgtable.h>

#if !defined(CONFIG_X86_64) || !defined(CONFIG_KD_API_LOCKS) || \
    !defined(CONFIG_STRICT_KERNEL_RWX)
#error "The scoped x86-64 kernel with strict kernel RWX is required"
#endif
#if defined(CONFIG_PREEMPT_RT) || defined(CONFIG_DEBUG_MUTEXES) || \
    defined(CONFIG_DEBUG_LOCK_ALLOC) || defined(CONFIG_LOCKDEP)
#error "Unsupported kernel lock configuration"
#endif

#define SITE_BYTES 48U
#define SITE_COUNT 3U
#define MAX_PAGES 2U

static unsigned long expected_address;
module_param(expected_address, ulong, 0444);
MODULE_PARM_DESC(expected_address, "Reviewed fixed linked address of the 48-byte site table");

static struct {
	unsigned long address;
	u64 entry;
	unsigned int level;
} pages[MAX_PAGES];
static struct kd_api_site sites[SITE_COUNT];
static unsigned int nr_pages;
static bool captured;

static int report_get(char *buf, const struct kernel_param *kp)
{
	unsigned int i;
	int n;

	(void)kp;
	if (!captured)
		return -EAGAIN;
	n = scnprintf(buf, PAGE_SIZE,
		"{\"schema\":1,\"address\":\"0x%lx\",\"bytes\":48,\"readonly\":true,\"pages\":[",
		expected_address);
	for (i = 0; i < nr_pages; i++)
		n += scnprintf(buf + n, PAGE_SIZE - n,
			"%s{\"address\":\"0x%lx\",\"entry\":\"0x%llx\",\"level\":%u}",
			i ? "," : "", pages[i].address,
			(unsigned long long)pages[i].entry, pages[i].level);
	n += scnprintf(buf + n, PAGE_SIZE - n, "],\"sites\":[");
	for (i = 0; i < SITE_COUNT; i++)
		n += scnprintf(buf + n, PAGE_SIZE - n,
			"%s{\"entry\":\"0x%lx\",\"site\":%u,\"reserved\":%u}",
			i ? "," : "", sites[i].entry, sites[i].site, sites[i].reserved);
	return n + scnprintf(buf + n, PAGE_SIZE - n, "]}\n");
}

static const struct kernel_param_ops report_ops = { .get = report_get };
module_param_cb(report, &report_ops, NULL, 0444);
MODULE_PARM_DESC(report, "Read-only snapshot; no setter and no live address selection");

static int __init api_sites_readonly_init(void)
{
	const struct kd_api_site *table;
	unsigned long address, last;
	unsigned int count, seen = 0, i;
	int error = -EINVAL;

	static_assert(sizeof(struct kd_api_site) * SITE_COUNT == SITE_BYTES);
	table = kd_api_sites(&count);
	if (!expected_address || (unsigned long)table != expected_address ||
	    count != SITE_COUNT || expected_address > ULONG_MAX - SITE_BYTES)
		return -EINVAL;
	last = expected_address + SITE_BYTES - 1;

	/* Built-in rodata mappings are stable after boot. Read each covering
	 * leaf once; this does not change PTEs, flush TLBs or disable CR0.WP. */
	preempt_disable();
	for (address = expected_address; address <= last;
	     address = (address & PAGE_MASK) + PAGE_SIZE) {
		unsigned int level;
		pte_t *entry = lookup_address(address, &level);
		u64 value;

		if (!entry || nr_pages == MAX_PAGES ||
		    (level != PG_LEVEL_4K && level != PG_LEVEL_2M && level != PG_LEVEL_1G))
			goto done;
		value = pte_val(READ_ONCE(*entry));
		if (!(value & _PAGE_PRESENT) || (value & (_PAGE_RW | _PAGE_USER)))
			goto done;
		pages[nr_pages].address = address;
		pages[nr_pages].entry = value;
		pages[nr_pages++].level = level;
	}
	for (i = 0; i < SITE_COUNT; i++) {
		sites[i].entry = READ_ONCE(table[i].entry);
		sites[i].site = READ_ONCE(table[i].site);
		sites[i].reserved = READ_ONCE(table[i].reserved);
		if (!sites[i].entry || sites[i].reserved || !sites[i].site ||
		    sites[i].site > SITE_COUNT || (seen & BIT(sites[i].site - 1)))
			goto done;
		seen |= BIT(sites[i].site - 1);
	}
	captured = true;
	error = 0;
done:
	preempt_enable();
	return error;
}

static void __exit api_sites_readonly_exit(void)
{
	/* No hooks, allocations, tasks, providers or page-table changes to undo. */
}

module_init(api_sites_readonly_init);
module_exit(api_sites_readonly_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Read-only mapping proof for the exact scoped API site table");
