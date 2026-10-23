/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MM_UNMAP_TEST_API_H
#define KD_MM_UNMAP_TEST_API_H
#include <linux/types.h>
#include <linux/ioctl.h>
#define UB_WORKERS 16
struct ub_config { __u64 start, end, base, stride; };
struct ub_counts {
	__u64 calls, removed, delegated, native, post_ban;
	__u64 handbacks, acks, cancelled, refused, failed, native_only;
};
struct ub_status {
	struct ub_counts counts;
	__u64 mm, gate, pending, idle, held, ready, readers, pgdir_size, task_size;
	__s64 admission;
	__u64 checks, errors, reader_peak, pending_peak;
	__u64 cancel_tid[2], cancel_mapped[2];
	__s64 cancel_result[2];
};
#define UB_ENABLE _IOW('U', 0x61, struct ub_config)
#define UB_STATUS _IOR('U', 0x62, struct ub_status)
#define UB_HOLD _IO('U', 0x63)
#define UB_CANCEL _IO('U', 0x64)
#define UB_RELEASE _IO('U', 0x65)
/* Read one exact VMA and explicit-mm accounting under local read ownership.
 * Existing control structures/ioctl encodings remain binary-compatible. */
struct ub_layout {
	__u64 address, start, end, pgoff, flags;
	__u64 map_count, total_vm, data_vm, stack_vm, exec_vm, pgtables;
};
#define UB_LAYOUT _IOWR('U', 0x66, struct ub_layout)
#define UB_CANCEL_PARTIAL _IO('U', 0x67)
/* New controls do not change any existing ioctl or client structure. */
struct ub_experiment { struct ub_config region; __u64 mode, groups, fail_after; };
struct ub_rmap { __u64 address, anon, root, link, links, active, refs, intervals; };
struct ub_page { __u64 address, pfn, hash, mapcount, refs, charged_same, value, locked; };
#define UB_EXT_PAGES 9
struct ub_pages { __u64 count; struct ub_page page[UB_EXT_PAGES]; };
struct ub_extra { __u64 fail_after, fail_seen, pins_owned, pins_released; };
#define UB_EXPERIMENT _IOW('U', 0x68, struct ub_experiment)
#define UB_RMAP _IOWR('U', 0x69, struct ub_rmap)
#define UB_PIN _IO('U', 0x6a)
#define UB_PAGESTATE _IOR('U', 0x6b, struct ub_pages)
#define UB_DROP _IO('U', 0x6c)
#define UB_BUSY_LOCK _IO('U', 0x6d)
#define UB_BUSY_UNLOCK _IO('U', 0x6e)
#define UB_UNPIN_MAPPED _IO('U', 0x6f)
#define UB_EXTRA _IOR('U', 0x70, struct ub_extra)
/* Sparse test references never fault untouched slots into existence. */
#define UB_PIN_MASK _IO('U', 0x71)
struct ub_ptes { __u64 address, none, anon, zero, other, pfn[3]; };
#define UB_PTES _IOWR('U', 0x72, struct ub_ptes)
/* Controlled native write fault while an existing reader holds its share.
 * Original ioctl layouts remain unchanged for the frozen preservation clients. */
struct ub_change {
	struct ub_page page;
	__u64 index, actor, pending, readers, zero_pfn, before_zero, after_private, done;
	__s64 admission, result;
};
#define UB_CHANGE_ARM _IO('U', 0x73)
#define UB_CHANGE_NOW _IO('U', 0x74)
#define UB_CHANGE_RESULT _IOR('U', 0x75, struct ub_change)
/* Distinguish an empty leaf in an existing table from an absent upper level.
 * These new encodings leave every frozen client ABI unchanged. */
struct ub_pte_tables {
	struct ub_ptes ptes;
	__u64 leaf, higher_none, table_pfn[3];
};
#define UB_PTE_TABLES _IOWR('U', 0x76, struct ub_pte_tables)
struct ub_change_more {
	struct ub_change state;
	__u64 mode, before_none, after_zero, table_before, table_after;
	__u64 anon_before, anon_after;
};
#define UB_CHANGE_EMPTY_ZERO_ARM _IO('U', 0x77)
#define UB_CHANGE_EMPTY_PRIVATE_ARM _IO('U', 0x78)
#define UB_CHANGE_RESULT_MORE _IOR('U', 0x79, struct ub_change_more)
/* Missing leaf tables are PMD-none with all required upper levels present.
 * Keep UB_PTE_TABLES unchanged for the frozen kdmm13 clients. */
struct ub_table_walk {
	struct ub_pte_tables tables;
	__u64 pmd_none, upper_none, parent_pfn[3];
};
#define UB_TABLE_WALK _IOWR('U', 0x7a, struct ub_table_walk)
#define UB_CHANGE_TABLE_EMPTY_ARM _IO('U', 0x7b)
#define UB_CHANGE_TABLE_ZERO_ARM _IO('U', 0x7c)
#define UB_CHANGE_TABLE_PRIVATE_ARM _IO('U', 0x7d)
/* Boundary fixtures keep a same-table whole-VMA queue head for error tests.
 * Explicit bases affect test observations only, never production admission. */
struct ub_bases { __u64 base[3]; };
#define UB_EDGE_BASES _IOW('U', 0x7e, struct ub_bases)
#define UB_CANCEL_EDGE _IO('U', 0x7f)
#define UB_CHANGE_EDGE_TABLE_ARM _IO('U', 0x80)
#define UB_CHANGE_EDGE_EMPTY_ZERO_ARM _IO('U', 0x81)
#define UB_CHANGE_EDGE_EMPTY_PRIVATE_ARM _IO('U', 0x82)
#endif
