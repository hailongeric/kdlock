/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_REACHED_H
#define KD_REACHED_H

#include <linux/types.h>
#include "kd_regs.h"
#include "exe_info.h"

/* A source instruction is decoded only at the canonical source IP. There is
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

enum kd_reached_atomic_op {
	KD_REACHED_ATOMIC_ADD,
	KD_REACHED_ATOMIC_SUB,
	KD_REACHED_ATOMIC_INC,
	KD_REACHED_ATOMIC_DEC,
	KD_REACHED_ATOMIC_XADD,
	KD_REACHED_ATOMIC_XCHG,
	KD_REACHED_ATOMIC_CMPXCHG,
	KD_REACHED_ATOMIC_BTS_UNLOCKED,
	KD_REACHED_ATOMIC_BTR_UNLOCKED,
	KD_REACHED_ATOMIC_BTC_UNLOCKED,
	KD_REACHED_ATOMIC_BTS_LOCKED,
	KD_REACHED_ATOMIC_BTR_LOCKED,
	KD_REACHED_ATOMIC_BTC_LOCKED,
	KD_REACHED_ATOMIC_AND,
	KD_REACHED_ATOMIC_OR,
	KD_REACHED_ATOMIC_XOR,
};

enum kd_reached_scalar_op {
	KD_REACHED_SCALAR_ROL,
	KD_REACHED_SCALAR_ROR,
	KD_REACHED_SCALAR_RCL,
	KD_REACHED_SCALAR_RCR,
	KD_REACHED_SCALAR_SHL,
	KD_REACHED_SCALAR_SHR,
	KD_REACHED_SCALAR_SAR,
	KD_REACHED_SCALAR_IMUL,
	KD_REACHED_SCALAR_BT,
	KD_REACHED_SCALAR_BTS,
	KD_REACHED_SCALAR_BTR,
	KD_REACHED_SCALAR_BTC,
	KD_REACHED_SCALAR_BSF,
	KD_REACHED_SCALAR_BSR,
	KD_REACHED_SCALAR_TZCNT,
	KD_REACHED_SCALAR_LZCNT,
	KD_REACHED_SCALAR_BT_MEMORY,
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
	/* Optional exact Native-width RMW. Bit operations distinguish unlocked and
	 * LOCK forms; their address already selects the word and input its bit.
	 * NULL refuses before any data access. */
	int (*atomic)(void *context, unsigned long address, unsigned int width,
		enum kd_reached_atomic_op operation, u64 input, u64 accumulator,
		unsigned long input_flags, u64 *old, unsigned long *output_flags);
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
	/* Diagnostic source edges only; never owner or return-routing records. */
	struct { unsigned long ip, target; } calls[8];
	unsigned int call_next, call_count;
	/* Generated code writes entry/retirement witnesses. The reference engine
	 * alone increments interpreted_steps; selected JIT execution must keep it0. */
	u64 jit_entries, jit_retired, interpreted_steps;
	u64 jit_value;
	unsigned long jit_flags;
	unsigned long jit_code;
};

/* FULL is mandatory. REP STOS/MOVS consumes one step/budget unit per stored
 * element; a zero-count REP consumes one step without a memory access. SI/DI/CX
 * and source IP retain completed progress, so an element failure cannot replay
 * its completed prefix. A failed MOVS store also leaves SI/DI/CX unchanged.
 * In particular, this never reads unspecified MINIMAL GPRs
 * or resets the persistent instruction budget at an edge or service return.
 * Unsupported instructions are reported before packet or data effects; that
 * result is not successful public lock completion or permission to run on O.
 */
enum kd_reached_result kd_reached_step(struct kd_reached_state *state);
enum kd_reached_result kd_reached_run(struct kd_reached_state *state,
				    unsigned int instruction_limit);
int kd_reached_begin(struct kd_reached_state *state, struct kd_regs *regs,
		     unsigned int packet_state, u64 budget);
int kd_reached_atomic_apply(void *address, unsigned int width,
	enum kd_reached_atomic_op operation, u64 input, u64 accumulator,
	unsigned long input_flags, u64 *old, unsigned long *output_flags);
int kd_reached_scalar_apply(unsigned int width, enum kd_reached_scalar_op operation,
	u64 left, u64 right, unsigned long input_flags, u64 *result,
	unsigned long *output_flags);

#endif
