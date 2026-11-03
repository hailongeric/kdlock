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
#define KD_ORIGIN_CALL_EXECUTION_TARGET 40
#define KD_ORIGIN_CALL_ARGUMENTS 48

#ifndef __ASSEMBLER__
#include <linux/list.h>
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
	KD_SERVICE_CALL_ATOMIC_ORIGIN,
	KD_SERVICE_CALL_PTE_LOCK,
	KD_SERVICE_CALL_SPIN_LOCK,
	KD_SERVICE_CALL_SPIN_TRYLOCK,
	KD_SERVICE_CALL_SPIN_UNLOCK,
	KD_SERVICE_CALL_RCU_LOCK,
	KD_SERVICE_CALL_RCU_UNLOCK,
	KD_SERVICE_CALL_PTE_RCU,
	/* Native preemption entry: no spin/preempt pin may survive its CALL. */
	KD_SERVICE_CALL_SCHEDULE_ORIGIN,
	/* Exact Native terminal; its original source CALL word must remain live. */
	KD_SERVICE_CALL_NONRETURNING_ORIGIN,
	KD_SERVICE_CALL_RWSEM_WRITE_LOCK,
	KD_SERVICE_CALL_RWSEM_WRITE_UNLOCK,
};

enum kd_native_owner_kind {
	KD_NATIVE_OWNER_FREE,
	KD_NATIVE_OWNER_SPIN,
	KD_NATIVE_OWNER_RCU,
	KD_NATIVE_OWNER_PREEMPT,
	KD_NATIVE_OWNER_RWSEM_WRITE,
};

/* Each live record is authority for one actual Native acquisition. Context
 * depth observations validate these records; they never create ownership. */
struct kd_native_owner {
	struct list_head link;
	struct task_struct *origin;
	void *identity;
	unsigned long object;
	u64 generation;
	u64 sequence;
	unsigned int kind;
	bool held;
};

struct kd_service_call_desc {
	const char *symbol;
	unsigned long target;
	unsigned char nargs;
	unsigned char result_kind;
	unsigned char context_kind;
	unsigned char reserved;
};

#define KD_SERVICE_CALL_MAP_V1 1U
enum kd_service_call_argument {
	KD_SERVICE_ARG_UNUSED,
	KD_SERVICE_ARG_SOURCE0,
	KD_SERVICE_ARG_SOURCE1,
	KD_SERVICE_ARG_SOURCE2,
	KD_SERVICE_ARG_SOURCE3,
	KD_SERVICE_ARG_SOURCE4,
	KD_SERVICE_ARG_SOURCE5,
	KD_SERVICE_ARG_ZERO,
	KD_SERVICE_ARG_MINUS_ONE,
	KD_SERVICE_ARG_RETURN_IP,
};

/* Separate registration preserves the ordinary descriptor's compiled stride.
 * Unused selectors and reserved fields must be zero. Both targets are retained
 * before publication; discovery continues to describe only the source API. */
struct kd_service_call_mapped_desc {
	struct kd_service_call_desc source;
	unsigned long execution_target;
	unsigned int version;
	unsigned char execution_nargs;
	unsigned char arguments[6];
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
	/* Zero execution target selects the unchanged identity bridge path. */
	unsigned long execution_target;
	unsigned long execution_arguments[6];
	struct kd_service_call_entry *entry;
	struct task_struct *origin;
	struct task_struct *executor;
	struct kd_call_state call;
	void *identity;
	u64 generation;
	u64 sequence;
	unsigned long irq_flags;
	unsigned long executor_irq_flags;
	unsigned long object;
	unsigned long object_out;
	struct kd_native_owner *spin_owner;
	struct kd_native_owner *rcu_owner;
	unsigned int baseline_preempt;
	unsigned int baseline_rcu;
	unsigned int context_kind;
	unsigned int phase;
	bool servicing;
	bool executor_pinned;
	/* Cold Native writer custody; assembly consumes only the scalar prefix. */
	struct kd_native_owner *rwsem_owner;
	/* A cold CALL retains its exact reached artifact through O's final ACK.
	 * Zero selects the existing immutable-image transaction. */
	u64 artifact_sequence;
};

/* Descriptors are copied into provider-owned immutable slots. Configuration
 * does not retain a permanent module reference. Each transaction retains its
 * target owner; source/image pins separately cover committed future calls.
 * Unregister requires closed source admission and exact execution drain. */
int kd_service_call_register(const struct kd_service_call_desc *descs,
	unsigned int count, struct module *owner);
int kd_service_call_register_mapped(const struct kd_service_call_mapped_desc *descs,
	unsigned int count, struct module *owner);
int kd_service_call_unregister(struct module *owner);
int kd_service_calls_init(void);
void kd_service_calls_exit(void);
int kd_service_calls_pin(void);
struct kd_service_call_entry *kd_service_call_get(unsigned long target);
void kd_service_call_put(struct kd_service_call_entry *entry);
bool kd_service_call_matches(const struct kd_service_call_entry *entry,
	unsigned long target);
bool kd_service_call_invocation_matches(const struct kd_service_call_entry *entry,
	unsigned long source_target, unsigned long execution_target);
int kd_service_call_arguments(const struct kd_service_call_entry *entry,
	const struct kd_regs *packet, unsigned long return_ip,
	unsigned long *execution_target, unsigned long arguments[6]);
unsigned int kd_service_call_context(const struct kd_service_call_entry *entry);

int kd_exec_cont_native_prepare(struct kd_exec_frame *frame);
int kd_exec_cont_native_complete(struct kd_exec_continuation *continuation,
	u64 sequence);
void kd_service_origin_bridge(struct kd_origin_call *call);
void kd_service_origin_terminal_bridge(struct kd_origin_call *call) __noreturn;
void kd_service_origin_terminal_restore(struct kd_origin_call *call) __noreturn;
void kd_service_origin_context_begin(struct kd_origin_call *call);
void kd_service_origin_context_end(struct kd_origin_call *call);
#endif
#endif
