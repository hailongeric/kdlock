/* SPDX-License-Identifier: GPL-2.0 */
/* Execute the production custody policy against supplied Native-return
 * observations. This does not substitute for a real kernel down_write wait. */
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

typedef uint64_t u64;
struct task_struct { int pid; };
struct kd_native_owner {
	struct kd_native_owner *next;
	struct task_struct *origin;
	void *identity;
	unsigned long object;
	u64 generation, sequence;
	unsigned int kind;
	bool held;
};
struct kd_regs { unsigned long ax; };
struct kd_origin_call {
	struct kd_regs *packet;
	struct task_struct *origin;
	void *identity;
	u64 generation, sequence;
	unsigned long executor_irq_flags, object, object_out;
	struct kd_native_owner *spin_owner, *rcu_owner, *rwsem_owner;
	unsigned int baseline_preempt, baseline_rcu, context_kind;
	bool executor_pinned;
};
struct kd_exec_continuation { struct kd_origin_call origin_call; };
struct kd_service_root {
	struct { struct { struct task_struct *logical_origin; void *identity; u64 generation; } request; } owner;
	struct kd_exec_continuation continuation;
	struct kd_native_owner *native_owners;
};
struct kd_service_scope { struct kd_exec_continuation *continuation; unsigned int depth; };
static struct task_struct origin = { .pid = 101 };
static struct task_struct *current = &origin;
static unsigned int actual_preempt = 1, actual_rcu;
static unsigned int trace_count;
static struct { unsigned int kind; unsigned long object; u64 sequence; bool grant; } trace[64];

#define CONFIG_PREEMPT_RCU 1
#define IS_ENABLED(option) (option)
#define X86_EFLAGS_IF 0x200UL
#define list_for_each_entry(owner, head, link) \
	for ((owner) = *(head); (owner); (owner) = (owner)->next)
#define container_of(pointer, type, field) ((type *)((char *)(pointer) - offsetof(type, field)))
#define BUG_ON(condition) do { if (condition) { \
	fprintf(stderr, "FAIL line=%d: production context assertion: %s\n", __LINE__, #condition); exit(1); \
} } while (0)
#define BUG() BUG_ON(true)
static inline unsigned int preempt_count(void) { return actual_preempt; }
static inline unsigned int kd_service_origin_rcu_depth(void) { return actual_rcu; }
static inline bool irqs_disabled(void) { return false; }
static inline unsigned int kd_service_scope_depth(const void *argument)
{ return ((const struct kd_service_scope *)argument)->depth; }
static inline int copy_from_kernel_nofault(void *to, const void *from, size_t size)
{ memcpy(to, from, size); return 0; }
static void kd_service_native_trace(const char *, struct kd_service_root *, struct kd_native_owner *);

#include "production.h"

static void kd_service_native_trace(const char *stage, struct kd_service_root *root,
	struct kd_native_owner *owner)
{
	(void)root;
	BUG_ON(trace_count == sizeof(trace) / sizeof(trace[0]));
	trace[trace_count].kind = owner->kind;
	trace[trace_count].object = owner->object;
	trace[trace_count].sequence = owner->sequence;
	trace[trace_count++].grant = !strcmp(stage, "grant");
}

static int prepare(struct kd_service_root *root, unsigned int context,
	unsigned long object, u64 sequence)
{
	struct kd_origin_call *call = &root->continuation.origin_call;
	static struct kd_regs packet;

	memset(call, 0, sizeof(*call));
	call->packet = &packet;
	call->origin = current;
	call->identity = root->owner.request.identity;
	call->generation = root->owner.request.generation;
	call->sequence = sequence;
	call->context_kind = context;
	call->object = object;
	call->executor_irq_flags = X86_EFLAGS_IF;
	actual_preempt = 1;
	actual_rcu = 0;
	return kd_service_native_prepare(root);
}

static void returned(struct kd_service_root *root)
{
	struct kd_origin_call *call = &root->continuation.origin_call;

	call->baseline_preempt = kd_service_native_pins(root);
	call->baseline_rcu = kd_service_native_depth(root, KD_NATIVE_OWNER_RCU);
	actual_preempt = call->baseline_preempt;
	actual_rcu = call->baseline_rcu;
	kd_service_native_finish(root);
}

#define CHECK(condition) do { if (!(condition)) { \
	fprintf(stderr, "FAIL line=%d: %s\n", __LINE__, #condition); return 1; \
} ++checks; } while (0)

int main(void)
{
	struct kd_native_owner owners[10] = { 0 }, retained[10];
	struct kd_service_root root = { .owner.request = {
		.logical_origin = &origin, .identity = (void *)0x1234, .generation = 7,
	}, .native_owners = owners };
	struct kd_service_scope scope = { .continuation = &root.continuation };
	struct kd_origin_call *call = &root.continuation.origin_call;
	const unsigned long objects[] = { 0x1100, 0x2200, 0x3300 };
	const u64 expected_sequences[] = { 1, 2, 3, 1, 3, 2 };
	unsigned int checks = 0, i;

	CHECK(KD_SERVICE_CALL_RWSEM_WRITE_LOCK == 12 && KD_SERVICE_CALL_RWSEM_WRITE_UNLOCK == 13);
	CHECK(KD_NATIVE_OWNER_RWSEM_WRITE == 4);
	owners[0].next = &owners[1];
	owners[1].next = &owners[2];
	owners[2].kind = KD_NATIVE_OWNER_SPIN;
	owners[2].held = true;
	memcpy(retained, owners, sizeof(owners));
	CHECK(prepare(&root, KD_SERVICE_CALL_RWSEM_WRITE_LOCK, objects[0], 1) == -EOPNOTSUPP);
	CHECK(!memcmp(retained, owners, sizeof(owners)));
	owners[2].kind = KD_NATIVE_OWNER_RCU;
	CHECK(prepare(&root, KD_SERVICE_CALL_RWSEM_WRITE_LOCK, objects[0], 1) == -EOPNOTSUPP);
	owners[2].kind = KD_NATIVE_OWNER_FREE;
	owners[2].held = false;
	owners[1].next = NULL;
	CHECK(prepare(&root, KD_SERVICE_CALL_RWSEM_WRITE_LOCK, 0, 1) == -EINVAL);
	CHECK(!prepare(&root, KD_SERVICE_CALL_RWSEM_WRITE_LOCK, objects[0], 1));
	CHECK(call->rwsem_owner == &owners[0] && !owners[0].held && !call->executor_pinned);
	CHECK(owners[0].kind == KD_NATIVE_OWNER_RWSEM_WRITE &&
		owners[0].origin == current && owners[0].identity == root.owner.request.identity &&
		owners[0].generation == 7 && owners[0].sequence == 1);
	returned(&root);
	CHECK(owners[0].held && !kd_service_native_pins(&root) && !kd_service_scope_released(&scope));
	CHECK(!prepare(&root, KD_SERVICE_CALL_RWSEM_WRITE_LOCK, objects[1], 2));
	returned(&root);
	memcpy(retained, owners, sizeof(owners));
	CHECK(prepare(&root, KD_SERVICE_CALL_RWSEM_WRITE_LOCK, objects[0], 3) == -EINVAL);
	CHECK(!memcmp(retained, owners, sizeof(owners)));
	CHECK(prepare(&root, KD_SERVICE_CALL_RWSEM_WRITE_LOCK, objects[2], 3) == -EAGAIN);
	CHECK(!memcmp(retained, owners, sizeof(owners)));
	/* The retained storage extension is supplied before retry/Native effects. */
	owners[1].next = &owners[2];
	CHECK(!prepare(&root, KD_SERVICE_CALL_RWSEM_WRITE_LOCK, objects[2], 3));
	returned(&root);
	CHECK(prepare(&root, KD_SERVICE_CALL_RWSEM_WRITE_UNLOCK, 0x9900, 4) == -EINVAL);
	CHECK(!prepare(&root, KD_SERVICE_CALL_RWSEM_WRITE_UNLOCK, objects[0], 4));
	CHECK(call->rwsem_owner == &owners[0] && owners[0].held && !call->executor_pinned);
	returned(&root);
	CHECK(!owners[0].held && owners[0].kind == KD_NATIVE_OWNER_FREE && owners[1].held && owners[2].held);
	CHECK(!kd_service_scope_released(&scope));
	CHECK(!prepare(&root, KD_SERVICE_CALL_RWSEM_WRITE_UNLOCK, objects[2], 5));
	returned(&root);
	CHECK(!kd_service_scope_released(&scope));
	CHECK(!prepare(&root, KD_SERVICE_CALL_RWSEM_WRITE_UNLOCK, objects[1], 6));
	returned(&root);
	CHECK(kd_service_scope_released(&scope));
	CHECK(trace_count == 6);
	for (i = 0; i < 6; ++i) {
		CHECK(trace[i].kind == KD_NATIVE_OWNER_RWSEM_WRITE && trace[i].sequence == expected_sequences[i]);
		CHECK(trace[i].grant == (i < 3));
	}
	/* All ten exact records can be live without becoming a CPU pin. The
	 * list uses the same policy as cold slots plus retained spill records. */
	for (i = 0; i < 9; ++i)
		owners[i].next = &owners[i + 1];
	owners[9].next = NULL;
	for (i = 0; i < 10; ++i) {
		CHECK(!prepare(&root, KD_SERVICE_CALL_RWSEM_WRITE_LOCK, 0x4000 + 16 * i, 100 + i));
		returned(&root);
		CHECK(!call->executor_pinned && !kd_service_native_pins(&root));
	}
	CHECK(!kd_service_scope_released(&scope));
	for (i = 0; i < 10; ++i) {
		CHECK(!prepare(&root, KD_SERVICE_CALL_RWSEM_WRITE_UNLOCK, 0x4000 + 16 * i, 200 + i));
		returned(&root);
	}
	CHECK(kd_service_scope_released(&scope));
	printf("Native writer exact custody: checks=%u, non-LIFO objects, ten records, no CPU pin\n", checks);
	return 0;
}
