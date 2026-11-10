/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_REGS_H
#define KDLOCK_REGS_H

/* New private source-rebuilt entry ABI, unrelated to legacy ABI labels. */
#define KD_JIT_ABI_VERSION 1

/* Private x86_64 packet for the selected KD R11-base mapping. The physical
 * backing lives once in the original thread's canonical state. This preserves
 * the coordinated 21-word KD layout for source reuse, not an old binary ABI.
 * All source values needed by an entry must already be materialized here.
 */
#define KD_REG_IP 0
#define KD_REG_SP 8
#define KD_REG_BP 16
#define KD_REG_R15 24
#define KD_REG_R14 32
#define KD_REG_R13 40
#define KD_REG_R12 48
#define KD_REG_R11 56
#define KD_REG_BX 64
#define KD_REG_R10 72
#define KD_REG_R9 80
#define KD_REG_R8 88
#define KD_REG_AX 96
#define KD_REG_CX 104
#define KD_REG_DX 112
#define KD_REG_SI 120
#define KD_REG_DI 128
#define KD_REG_ORIG_AX 136
#define KD_REG_CS 144
#define KD_REG_FLAGS 152
#define KD_REG_SS 160
#define KD_REG_SIZE 168

/* Fresh inputs on every entry; the output words are a control result, never
 * another packet. regs.ip remains the authoritative first-unexecuted cursor.
 */
#define KD_JIT_IO_ORIGIN_GS 0
#define KD_JIT_IO_ORIGIN_TASK 8
#define KD_JIT_IO_KIND 16
#define KD_JIT_IO_DETAIL 24
#define KD_JIT_IO_SOURCE_IP 32
#define KD_JIT_IO_TARGET 40
#define KD_JIT_IO_PHASE 48
#define KD_JIT_IO_SIZE 56

#define KD_JIT_EXIT_NONE 0
#define KD_JIT_EXIT_LOCK_OPERATION 1
#define KD_JIT_EXIT_SPECIAL_FRONTIER 2
#define KD_JIT_EXIT_COVERAGE_MISS 3
#define KD_JIT_EXIT_UNMODELED_TRANSFER 4
#define KD_JIT_EXIT_RESOURCE_BOUNDARY 5
#define KD_JIT_EXIT_ENTRY_REFUSED 6
#define KD_JIT_EXIT_INVARIANT_FAILURE 7

#define KD_JIT_PHASE_BEFORE_INSTRUCTION 0
#define KD_JIT_PHASE_TARGET_READY 1
#define KD_JIT_PHASE_CALL_STAGED 2
#define KD_JIT_PHASE_RETURN_CONSUMED 3
#define KD_JIT_PHASE_JUMP_RESOLVED 4

#define KD_JIT_OP_LOCK 1
#define KD_JIT_OP_UNLOCK 2
#define KD_JIT_OP_MODE_CHANGE 3

/* Detail identifies the recorded cause, not a newly selected resource cap. */
#define KD_JIT_DETAIL_NONE 0
#define KD_JIT_DETAIL_SOURCE_UNAVAILABLE 1
#define KD_JIT_DETAIL_DECODE_FAILURE 2
#define KD_JIT_DETAIL_UNMODELED 3
#define KD_JIT_DETAIL_DISCOVERY_RESOURCE 4
#define KD_JIT_DETAIL_LOWERING_UNSUPPORTED 5
#define KD_JIT_DETAIL_REGISTER_PRESSURE 6
#define KD_JIT_DETAIL_LOWERED_SITES 7
#define KD_JIT_DETAIL_LOWERED_TEXT_BYTES 8
#define KD_JIT_DETAIL_RUNTIME_BLOCK_VISITS 9
#define KD_JIT_DETAIL_UNRESOLVED_TARGET 10
#define KD_JIT_DETAIL_RETURN_TARGET 11
#define KD_JIT_DETAIL_DECODE_SITE_LIMIT 12
#define KD_JIT_DETAIL_DECODE_WINDOW_LIMIT 13
#define KD_JIT_DETAIL_CFG_WORK_LIMIT 14
#define KD_JIT_DETAIL_DIRECT_CALL_LIMIT 15

#ifndef __ASSEMBLER__
struct kd_regs {
	unsigned long ip;
	unsigned long sp;
	unsigned long bp;
	unsigned long r15;
	unsigned long r14;
	unsigned long r13;
	unsigned long r12;
	unsigned long r11;
	unsigned long bx;
	unsigned long r10;
	unsigned long r9;
	unsigned long r8;
	unsigned long ax;
	unsigned long cx;
	unsigned long dx;
	unsigned long si;
	unsigned long di;
	unsigned long orig_ax;
	unsigned long cs;
	unsigned long flags;
	unsigned long ss;
};

enum kd_jit_exit_kind {
	KD_JIT_EXIT_NONE_CODE = KD_JIT_EXIT_NONE,
	KD_JIT_EXIT_LOCK_OPERATION_CODE = KD_JIT_EXIT_LOCK_OPERATION,
	KD_JIT_EXIT_SPECIAL_FRONTIER_CODE = KD_JIT_EXIT_SPECIAL_FRONTIER,
	KD_JIT_EXIT_COVERAGE_MISS_CODE = KD_JIT_EXIT_COVERAGE_MISS,
	KD_JIT_EXIT_UNMODELED_TRANSFER_CODE = KD_JIT_EXIT_UNMODELED_TRANSFER,
	KD_JIT_EXIT_RESOURCE_BOUNDARY_CODE = KD_JIT_EXIT_RESOURCE_BOUNDARY,
	KD_JIT_EXIT_ENTRY_REFUSED_CODE = KD_JIT_EXIT_ENTRY_REFUSED,
	KD_JIT_EXIT_INVARIANT_FAILURE_CODE = KD_JIT_EXIT_INVARIANT_FAILURE,
};

enum kd_jit_exit_phase {
	KD_JIT_PHASE_BEFORE_INSTRUCTION_CODE = KD_JIT_PHASE_BEFORE_INSTRUCTION,
	KD_JIT_PHASE_TARGET_READY_CODE = KD_JIT_PHASE_TARGET_READY,
	KD_JIT_PHASE_CALL_STAGED_CODE = KD_JIT_PHASE_CALL_STAGED,
	KD_JIT_PHASE_RETURN_CONSUMED_CODE = KD_JIT_PHASE_RETURN_CONSUMED,
	KD_JIT_PHASE_JUMP_RESOLVED_CODE = KD_JIT_PHASE_JUMP_RESOLVED,
};

enum kd_jit_operation {
	KD_JIT_OP_LOCK_CODE = KD_JIT_OP_LOCK,
	KD_JIT_OP_UNLOCK_CODE = KD_JIT_OP_UNLOCK,
	KD_JIT_OP_MODE_CHANGE_CODE = KD_JIT_OP_MODE_CHANGE,
};

struct kd_jit_io {
	unsigned long origin_gs;
	unsigned long origin_task;
	unsigned long kind;
	unsigned long detail;
	unsigned long source_ip;
	unsigned long target;
	unsigned long phase;
};

/* The caller retains packet, IO, source, generated code and context through
 * the call and result publication, and imports fresh origin inputs each time.
 * Entry names the same canonical packet under exclusive source execution.
 * This wrapper admits a physical executor distinct from the source origin.
 * Its active native stack, the origin's stopped source stack, and any origin
 * waiting/control stack must be admitted disjoint live regions. Retaining a
 * source stack alone does not prove this; no alternate-stack policy is chosen.
 * Flags/SIMD use AS01's assumption; this interface proves no equivalence.
 */
typedef void (*kd_jit_entry_fn)(struct kd_regs *regs, struct kd_jit_io *io);

_Static_assert(sizeof(unsigned long) == 8, "KD x86_64 word size");
_Static_assert(__builtin_offsetof(struct kd_regs, ip) == KD_REG_IP, "KD ip offset");
_Static_assert(__builtin_offsetof(struct kd_regs, sp) == KD_REG_SP, "KD sp offset");
_Static_assert(__builtin_offsetof(struct kd_regs, bp) == KD_REG_BP, "KD bp offset");
_Static_assert(__builtin_offsetof(struct kd_regs, r15) == KD_REG_R15, "KD r15 offset");
_Static_assert(__builtin_offsetof(struct kd_regs, r14) == KD_REG_R14, "KD r14 offset");
_Static_assert(__builtin_offsetof(struct kd_regs, r13) == KD_REG_R13, "KD r13 offset");
_Static_assert(__builtin_offsetof(struct kd_regs, r12) == KD_REG_R12, "KD r12 offset");
_Static_assert(__builtin_offsetof(struct kd_regs, r11) == KD_REG_R11, "KD r11 offset");
_Static_assert(__builtin_offsetof(struct kd_regs, bx) == KD_REG_BX, "KD bx offset");
_Static_assert(__builtin_offsetof(struct kd_regs, r10) == KD_REG_R10, "KD r10 offset");
_Static_assert(__builtin_offsetof(struct kd_regs, r9) == KD_REG_R9, "KD r9 offset");
_Static_assert(__builtin_offsetof(struct kd_regs, r8) == KD_REG_R8, "KD r8 offset");
_Static_assert(__builtin_offsetof(struct kd_regs, ax) == KD_REG_AX, "KD ax offset");
_Static_assert(__builtin_offsetof(struct kd_regs, cx) == KD_REG_CX, "KD cx offset");
_Static_assert(__builtin_offsetof(struct kd_regs, dx) == KD_REG_DX, "KD dx offset");
_Static_assert(__builtin_offsetof(struct kd_regs, si) == KD_REG_SI, "KD si offset");
_Static_assert(__builtin_offsetof(struct kd_regs, di) == KD_REG_DI, "KD di offset");
_Static_assert(__builtin_offsetof(struct kd_regs, orig_ax) == KD_REG_ORIG_AX, "KD orig_ax offset");
_Static_assert(__builtin_offsetof(struct kd_regs, cs) == KD_REG_CS, "KD cs offset");
_Static_assert(__builtin_offsetof(struct kd_regs, flags) == KD_REG_FLAGS, "KD flags offset");
_Static_assert(__builtin_offsetof(struct kd_regs, ss) == KD_REG_SS, "KD ss offset");
_Static_assert(sizeof(struct kd_regs) == KD_REG_SIZE, "KD packet size");
_Static_assert(__builtin_offsetof(struct kd_jit_io, origin_gs) == KD_JIT_IO_ORIGIN_GS, "KD origin GS offset");
_Static_assert(__builtin_offsetof(struct kd_jit_io, origin_task) == KD_JIT_IO_ORIGIN_TASK, "KD origin task offset");
_Static_assert(__builtin_offsetof(struct kd_jit_io, kind) == KD_JIT_IO_KIND, "KD exit kind offset");
_Static_assert(__builtin_offsetof(struct kd_jit_io, detail) == KD_JIT_IO_DETAIL, "KD exit detail offset");
_Static_assert(__builtin_offsetof(struct kd_jit_io, source_ip) == KD_JIT_IO_SOURCE_IP, "KD source IP offset");
_Static_assert(__builtin_offsetof(struct kd_jit_io, target) == KD_JIT_IO_TARGET, "KD target offset");
_Static_assert(__builtin_offsetof(struct kd_jit_io, phase) == KD_JIT_IO_PHASE, "KD phase offset");
_Static_assert(sizeof(struct kd_jit_io) == KD_JIT_IO_SIZE, "KD entry IO size");
#endif
#endif
