/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_ORIGIN_SERVICE_H
#define KD_ORIGIN_SERVICE_H
#include <linux/types.h>

struct kd_exec_frame;
struct kd_mutex_node;
struct kd_regs;

enum kd_origin_instruction {
	KD_ORIGIN_RDTSC = 1,
	KD_ORIGIN_RDTSCP = 2,
	KD_ORIGIN_CPUID = 3,
};

/* Cold synchronous request on the physical executor's stack. Publication lends
 * the existing FULL packet, never a copy. The waiter rearms its node before
 * returned=true and makes no further request/packet access after that release.
 * The executor cannot return or reuse this storage until its acquire ACK. */
struct kd_origin_request {
	struct kd_exec_frame *frame;
	struct kd_mutex_node *node;
	struct kd_regs *regs;
	unsigned long sequence;
	unsigned long count_sequence;
	unsigned long source_ip;
	unsigned long source_sp;
	unsigned int instruction;
	int origin_cpu;
	int origin_pid;
	int result;
	bool executed;
	bool returned;
};

/* 1: instruction executed, 0: refused before any effect, negative: invariant
 * failure. Returned FULL registers remain owned by the retained frame. */
int kd_mutex_origin_instruction(struct kd_exec_frame *frame,
				unsigned int instruction,
				unsigned long sequence);

#endif
