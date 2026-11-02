/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SERVICE_CALLS_H
#define KD_SERVICE_CALLS_H

/* The assembly bridge only consumes this fixed scalar prefix. The original
 * source CALL word and all source frames remain above its Native caller SP. */
#define KD_ORIGIN_CALL_PACKET 0
#define KD_ORIGIN_CALL_TARGET 8
#define KD_ORIGIN_CALL_NATIVE_SP 16
#define KD_ORIGIN_CALL_SHADOW_SP 24
#define KD_ORIGIN_CALL_SHADOW_BP 32

#ifndef __ASSEMBLER__
#include <linux/types.h>
#include "kd_call.h"

struct module;
struct task_struct;
struct kd_regs;
struct kd_exec_frame;
struct kd_exec_continuation;
struct kd_service_call_entry;

enum kd_service_call_result {
	KD_SERVICE_CALL_WORD = 1,
	KD_SERVICE_CALL_VOID = 2,
};

enum kd_service_call_context {
	KD_SERVICE_CALL_BALANCED_ORIGIN = 1,
};

struct kd_service_call_desc {
	const char *symbol;
	unsigned long target;
	unsigned char nargs;
	unsigned char result_kind;
	unsigned char context_kind;
	unsigned char reserved;
};

enum kd_origin_call_phase {
	KD_ORIGIN_CALL_IDLE,
	KD_ORIGIN_CALL_PREPARED,
	KD_ORIGIN_CALL_REQUESTED,
	KD_ORIGIN_CALL_RUNNING,
	KD_ORIGIN_CALL_DONE,
	KD_ORIGIN_CALL_CONSUMED,
};

struct kd_origin_call {
	struct kd_regs *packet;
	unsigned long target;
	unsigned long native_sp;
	unsigned long shadow_sp;
	unsigned long shadow_bp;
	struct kd_service_call_entry *entry;
	struct task_struct *origin;
	struct task_struct *executor;
	struct kd_call_state call;
	void *identity;
	u64 generation;
	u64 sequence;
	unsigned long irq_flags;
	unsigned int baseline_preempt;
	unsigned int phase;
	bool servicing;
};

/* Descriptors are copied into provider-owned immutable slots. Configuration
 * does not retain a permanent module reference. Each transaction retains its
 * target owner; source/image pins separately cover committed future calls.
 * Unregister requires closed source admission and exact execution drain. */
int kd_service_call_register(const struct kd_service_call_desc *descs,
	unsigned int count, struct module *owner);
int kd_service_call_unregister(struct module *owner);
int kd_service_calls_init(void);
void kd_service_calls_exit(void);
int kd_service_calls_pin(void);
struct kd_service_call_entry *kd_service_call_get(unsigned long target);
void kd_service_call_put(struct kd_service_call_entry *entry);
bool kd_service_call_matches(const struct kd_service_call_entry *entry,
	unsigned long target);

int kd_exec_cont_native_prepare(struct kd_exec_frame *frame);
int kd_exec_cont_native_complete(struct kd_exec_continuation *continuation,
	u64 sequence);
void kd_service_origin_bridge(struct kd_origin_call *call);
void kd_service_origin_context_begin(struct kd_origin_call *call);
void kd_service_origin_context_end(struct kd_origin_call *call);
#endif
#endif
