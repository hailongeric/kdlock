/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RWSEM_POLL_PROBE_API_H
#define KD_RWSEM_POLL_PROBE_API_H
#include <linux/ioctl.h>
#include <linux/types.h>
#define KD_POLL_CASES 4
struct kd_poll_case {
	__u64 id, signal, busy, send_error;
	__u64 pending_before, fatal_before, preempt_before, irq_before;
	__u64 reserve_calls, reserve_wins, resched_calls, resched_true;
	__u64 signal_calls, signal_true, relax_calls, returned;
	__u64 admission_after, cleanup_ok, preempt_after, irq_after;
	__u64 errors, inconclusive;
};
struct kd_poll_report {
	__u64 abi, cases, errors, inconclusive, joined, phase_idle, complete, timeouts;
	struct kd_poll_case rows[KD_POLL_CASES];
};
#define KD_POLL_RUN _IOR('K', 0x73, struct kd_poll_report)
#endif
