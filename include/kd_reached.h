/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_REACHED_H
#define KD_REACHED_H

#include <linux/types.h>
#include "kd_regs.h"
#include "exe_info.h"

/* A scalar instruction is decoded only at the canonical source IP. There is
 * no graph, code cache or original-task continuation in this component. */
#define KD_REACHED_MAX_BYTES 15
#define KD_REACHED_SEGMENT_MAX 64U

enum kd_reached_result {
	KD_REACHED_NEXT,
	KD_REACHED_EDGE,
	KD_REACHED_UNSUPPORTED,
	KD_REACHED_MEMORY,
	KD_REACHED_SOURCE,
	KD_REACHED_BUDGET,
	KD_REACHED_PACKET,
};

enum kd_reached_edge {
	KD_REACHED_FALLTHROUGH,
	KD_REACHED_JCC,
	KD_REACHED_CALL,
	KD_REACHED_JUMP,
	KD_REACHED_RETURN,
};

struct kd_reached_event {
	unsigned long source_ip;
	unsigned long next_ip;
	unsigned long target;
	u64 sequence;
	u8 bytes[KD_REACHED_MAX_BYTES];
	u8 length;
	u8 edge;
	u8 result;
};

/* Callbacks must not allocate, sleep or consult a userspace compiler. fetch
 * must retain exact source residency/epoch authority before reading bytes;
 * it is deliberately called for current instruction bytes only. Data memory
 * callbacks operate on O's retained source addresses, never E's runtime SP.
 * An unsuccessful write must have no partial effect. Ordinary memory accesses
 * must preserve the Native width/access granularity on qualified ordinary RAM;
 * arbitrary bytewise copies, MMIO and exception/fixup behavior are not a
 * qualified production memory contract merely because a callback returns zero.
 * The isolated fixture's arrays prove operand semantics, not those contracts.
 * Ordinary accesses do not emulate LOCK or implicit-atomic operations.
 * The surrounding frame owns source/stack lifetimes and must have no pending
 * service on entry.
 */
struct kd_reached_ops {
	int (*fetch)(void *context, unsigned long address, void *out, unsigned int size);
	int (*read)(void *context, unsigned long address, void *out, unsigned int size);
	int (*write)(void *context, unsigned long address, const void *in, unsigned int size);
};

struct kd_reached_state {
	struct kd_regs *regs;
	const struct kd_reached_ops *ops;
	void *context;
	/* The frame adapter binds these to the exact queue request generation.
	 * Pointer equality alone cannot authorize a state after slot reuse. The
	 * scalar component initializes them but never grants custody with them. */
	const void *owner_identity;
	u64 owner_generation;
	u64 budget;
	u64 sequence;
	unsigned int packet_state;
	struct kd_reached_event event;
};

/* FULL is mandatory. In particular, this never reads unspecified MINIMAL GPRs
 * or resets the persistent instruction budget at an edge or service return.
 * Unsupported instructions are reported before packet or data effects; that
 * result is not successful public lock completion or permission to run on O.
 */
enum kd_reached_result kd_reached_step(struct kd_reached_state *state);
enum kd_reached_result kd_reached_run(struct kd_reached_state *state,
				    unsigned int instruction_limit);
int kd_reached_begin(struct kd_reached_state *state, struct kd_regs *regs,
		     unsigned int packet_state, u64 budget);

#endif
