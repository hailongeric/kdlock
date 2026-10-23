/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MM_UNMAP_TEST_API_H
#define KD_MM_UNMAP_TEST_API_H
#include <linux/types.h>
#include <linux/ioctl.h>
#define UB_WORKERS 16
#define UB_GROUPS 48
#define UB_PAGES (UB_GROUPS * 5)
struct ub_config { __u64 start, end, base, stride, groups, width, wide; };
struct ub_counts {
	__u64 calls, removed, delegated, native, post_ban;
	__u64 handbacks, acks, cancelled, refused, failed, native_only;
	__u64 populated, populated_remote;
};
struct ub_status {
	struct ub_counts counts;
	__u64 mm, gate, pending, idle, held, ready, readers, pgdir_size, task_size;
	__s64 admission;
	__u64 checks, errors, reader_peak, pending_peak;
	__u64 cancel_tid[2], cancel_mapped[2];
	__s64 cancel_result[2];
	__u64 pins_owned, pins_released;
};
struct ub_page { __u64 address, pfn, hash, mapcount, refs, charged_same, value, locked; };
struct ub_pages { __u64 count; struct ub_page page[UB_PAGES]; };
#define UB_ENABLE _IOW('U', 0x61, struct ub_config)
#define UB_STATUS _IOR('U', 0x62, struct ub_status)
#define UB_HOLD _IO('U', 0x63)
#define UB_CANCEL _IO('U', 0x64)
#define UB_RELEASE _IO('U', 0x65)
#define UB_PIN _IO('U', 0x66)
#define UB_PAGESTATE _IOR('U', 0x67, struct ub_pages)
#define UB_DROP _IO('U', 0x68)
#define UB_UNPIN_MAPPED _IO('U', 0x69)
#define UB_BUSY_LOCK _IO('U', 0x6a)
#define UB_BUSY_UNLOCK _IO('U', 0x6b)

static inline unsigned int ub_group_pages(const struct ub_config *c, unsigned int group)
{
	if (c->groups == UB_GROUPS && group >= 16 && group < 32) return 3;
	return c->wide && group == 1 ? 5 : c->width;
}
static inline unsigned int ub_group_pins(const struct ub_config *c, unsigned int group)
{
	return c->groups == UB_GROUPS && group >= 16 && group < 32 ? 1 : ub_group_pages(c, group);
}
static inline unsigned int ub_pin_total(const struct ub_config *c)
{
	unsigned int group, count = 0;
	for (group = 0; group < c->groups; group++) count += ub_group_pins(c, group);
	return count;
}
static inline void ub_pin_location(const struct ub_config *c, unsigned int index,
				  unsigned int *group, unsigned int *page)
{
	*group = 0;
	while (index >= ub_group_pins(c, *group)) index -= ub_group_pins(c, (*group)++);
	*page = c->groups == UB_GROUPS && *group >= 16 && *group < 32 ? 1 : index;
}
#endif
