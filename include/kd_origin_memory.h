/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_ORIGIN_MEMORY_H
#define KD_ORIGIN_MEMORY_H

#define KD_ORIGIN_MEMORY_PACKET 0
#define KD_ORIGIN_MEMORY_NATIVE_SP 112
#define KD_ORIGIN_MEMORY_SHADOW_SP 120
#define KD_ORIGIN_MEMORY_SHADOW_BP 128

#ifndef __ASSEMBLER__
#include <linux/types.h>

struct kd_regs;
struct kd_exec_frame;
struct kd_exec_continuation;
struct kd_jit_image;
struct task_struct;
struct kd_native_owner;

#define KD_ORIGIN_MEMORY_MAX 1024U
#define KD_ORIGIN_MEMORY_INC 1U
#define KD_ORIGIN_MEMORY_DEC 2U
#define KD_ORIGIN_MEMORY_LOAD 3U
#define KD_ORIGIN_MEMORY_TEST 4U
#define KD_ORIGIN_MEMORY_READ 1U

struct kd_origin_memory_site {
	unsigned long ip;
	unsigned long next_ip;
	u32 continuation_offset;
	u8 length;
	u8 operation;
	u8 width;
	u8 flags;
	u8 opcode[16];
} __attribute__((packed));
/* operation=width=continuation_offset=0 records an exact reached refusal.
 * It never authorizes CPU execution or a source/JIT successor. */

struct kd_origin_memory_footer {
	u8 magic[8];
	u32 offset;
	u32 count;
} __attribute__((packed));

struct kd_origin_memory_read_footer {
	u8 magic[8];
	u32 offset;
	u32 count;
	unsigned long preempt_symbol;
} __attribute__((packed));

enum kd_origin_memory_phase {
	KD_ORIGIN_MEMORY_IDLE,
	KD_ORIGIN_MEMORY_PREPARED,
	KD_ORIGIN_MEMORY_REQUESTED,
	KD_ORIGIN_MEMORY_RUNNING,
	KD_ORIGIN_MEMORY_DONE,
	KD_ORIGIN_MEMORY_CONSUMED,
};

/* Cold retained transaction, separate from the source CALL/RET protocol.
 * Only O owns packet access between REQUESTED and DONE; its exact ACK ends
 * source-stack and instruction custody before E resumes the same image. */
struct kd_origin_memory {
	struct kd_regs *packet;
	const struct kd_jit_image *image;
	const struct kd_origin_memory_site *site;
	struct task_struct *origin;
	struct task_struct *executor;
	void *identity;
	u64 generation;
	u64 sequence;
	unsigned long gsbase;
	unsigned long effective_offset;
	unsigned long source_sp;
	unsigned long input_flags;
	unsigned long result_flags;
	unsigned long executor_irq_flags;
	unsigned long native_sp;
	unsigned long shadow_sp;
	unsigned long shadow_bp;
	unsigned int phase;
	int result;
	bool executor_pinned;
	bool preempt_operand;
	struct kd_native_owner *preempt_owner;
	unsigned int baseline_preempt;
	unsigned int baseline_rcu;
	bool servicing;
	unsigned long result_value;
	u32 immediate;
	u8 destination;
	/* These cold fields follow every assembly-consumed prefix word. A reached
	 * descriptor remains immutable until DONE is acknowledged on E. */
	u64 artifact_sequence;
	struct kd_origin_memory_site reached_site;
};

const struct kd_origin_memory_site *kd_image_memory_sites(
	const struct kd_jit_image *image, unsigned int *count);
int kd_image_validate_memory_sites(const struct kd_jit_image *image);
int kd_origin_memory_decode(const struct kd_origin_memory_site *site,
	const struct kd_regs *regs, unsigned long *effective_offset);
typedef int (*kd_origin_memory_reader)(void *context, unsigned long address,
	void *out, unsigned int size);
int kd_origin_memory_reached_decode(struct kd_origin_memory_site *site,
	unsigned long ip, kd_origin_memory_reader reader, void *context);
int kd_exec_cont_memory_prepare(struct kd_exec_frame *frame);
int kd_exec_cont_memory_prepare_reached(struct kd_exec_frame *frame);
int kd_exec_cont_memory_complete(struct kd_exec_continuation *cont, u64 sequence);
/* Runs on O with its Native context already normalized. This writes only
 * retained outputs; complete applies a decoded MOV destination after ACK. */
void kd_origin_memory_apply(struct kd_origin_memory *operation);
void kd_service_memory_bridge(struct kd_origin_memory *operation);
void kd_service_memory_context_begin(struct kd_origin_memory *operation);
void kd_service_memory_context_end(struct kd_origin_memory *operation);

#endif
#endif
