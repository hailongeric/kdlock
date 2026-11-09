/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_REACHED_DECODE_H
#define KD_REACHED_DECODE_H
#include "kd_reached.h"

enum operation {
	OP_NONE, OP_MOV, OP_LEA, OP_ZX, OP_SX,
	OP_ADD, OP_OR, OP_ADC, OP_SBB, OP_AND, OP_SUB, OP_XOR, OP_CMP,
	OP_TEST, OP_INC, OP_DEC, OP_NOT, OP_NEG,
	OP_PUSH, OP_POP, OP_LEAVE, OP_JCC, OP_CALL, OP_JMP, OP_RET,
	OP_CMOV, OP_SET, OP_PAUSE, OP_LFENCE, OP_MFENCE, OP_SFENCE,
	OP_SHIFT, OP_IMUL, OP_XADD, OP_XCHG, OP_CMPXCHG,
	OP_CLC, OP_STC, OP_CMC, OP_LAHF, OP_SAHF, OP_SIGN_PAIR,
	OP_BIT, OP_STOS, OP_MOVS, OP_SCAN,
};

struct operand {
	u64 immediate;
	s64 displacement;
	u8 reg, base, index, scale;
	u8 width;
	bool memory, literal, high8, rip_relative, has_base, has_index;
};

struct decoded {
	struct kd_reached_state *state;
	struct operand dst, src;
	u64 multiplier;
	u8 bytes[KD_REACHED_MAX_BYTES];
	u8 length, rex, width, operation, condition;
	u16 adjustment;
	bool rex_seen, op16, rep, locked, multiply_immediate, cs_prefix;
	int error;
};

int kd_reached_decode(struct kd_reached_state *state, struct decoded *decoded);
#endif
