/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_API_CONTROL_H
#define KD_API_CONTROL_H
#include <linux/ioctl.h>
#include <linux/types.h>

#define KD_API_VERSION 1U
#define KD_API_KIND_FILES 1U
#define KD_API_KIND_PIPE 2U
#define KD_API_BACKEND_NATIVE 0U
#define KD_API_BACKEND_KD 1U
#define KD_API_SITE_SETFD 1U
#define KD_API_SITE_FIONREAD 2U
#define KD_API_SITE_GETPIPE_SZ 3U
#define KD_API_SITE_COUNT 3U

/* Exact current-task setup, tied to this open description. Each budget is
 * zero or one; both zero verifies Native default with no outstanding selector.
 * Selection never changes an already initialized object. */
struct kd_api_select {
	__u32 version;
	__u32 files_budget;
	__u32 pipes_budget;
	__u32 reserved;
};

/* fd=-1 names current->files; otherwise fd must name a pipe. Object identity
 * is valid while the caller retains that object, not across destruction/reuse.
 * Addresses are privileged setup receipts, never acquisition authority. */
struct kd_api_query {
	__u32 version;
	__s32 fd;
	__u32 kind;
	__u32 backend;
	__u64 object;
	__u64 lock;
	__u64 provider;
	__u64 entries[KD_API_SITE_COUNT];
};

#define KD_API_SELECT _IOW('K', 0x74, struct kd_api_select)
#define KD_API_CANCEL _IO('K', 0x75)
#define KD_API_QUERY _IOWR('K', 0x76, struct kd_api_query)
#endif
