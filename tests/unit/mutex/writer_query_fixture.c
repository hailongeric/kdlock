/* SPDX-License-Identifier: GPL-2.0 */
/* Production query and initialization against supplied O/E and frame state.
 * Registry execution/pins and concurrent MM lifetimes need their live checks. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <stddef.h>

typedef uint32_t u32;
typedef uint64_t u64;
typedef long atomic_long_t;
struct module { unsigned long id; } module;
struct task_struct { unsigned long id; } origin, executor, other;
static struct task_struct *current;
#define CONFIG_KDLOCK_MMAP 1
#define __noreturn __attribute__((noreturn))
#define THIS_MODULE (&module)
#define READ_ONCE(value) (value)
#define WRITE_ONCE(value, next) ((value) = (next))
#define ARRAY_SIZE(values) (sizeof(values) / sizeof((values)[0]))
#define scnprintf snprintf
#include "provider_types.h"

struct list_head { struct list_head *next, *prev; };
#define container_of(pointer, type, field) ((type *)((char *)(pointer) - offsetof(type, field)))
#define list_for_each_entry(item, head, field) \
	for (struct list_head *entry = (head)->next; \
	     entry != (head) && ((item) = container_of(entry, __typeof__(*(item)), field), true); \
	     entry = entry->next)
static void list_init(struct list_head *head) { head->next = head->prev = head; }
static void list_add(struct list_head *head, struct list_head *item)
{
	item->next = head; item->prev = head->prev;
	head->prev->next = item; head->prev = item;
}
struct kd_mutex { atomic_long_t owner; };
struct kd_rwsem {
	long admission;
	unsigned int selected_kind;
	struct task_struct *selected_owner;
	void *selected_identity;
	u64 phase_generation;
};
struct kd_wait_request {
	void *identity;
	u64 generation;
	struct task_struct *logical_origin;
	unsigned int state;
};
struct kd_admission {
	void *object;
	struct kd_mutex *gate;
	struct kd_rwsem *sem;
	bool committed, gate_held, pickup_pending, phase_held;
	struct task_struct *physical_owner, *phase_owner;
	void *phase_identity;
	unsigned int phase_kind;
	u64 phase_generation;
};
struct kd_service_owner {
	struct kd_wait_request request;
	struct kd_admission admission;
	struct list_head link;
	bool released;
};
struct kd_origin_call {
	struct task_struct *origin;
	void *identity;
	u64 generation;
	unsigned int phase;
	bool servicing;
};
struct kd_exec_continuation {
	struct kd_wait_request *request;
	u64 generation;
	const void *service_ops;
	struct task_struct *executor;
	unsigned int state;
	struct kd_origin_call origin_call;
};
struct kd_exec_frame { struct kd_exec_continuation *continuation; };
struct kd_service_root {
	struct kd_service_owner owner;
	struct kd_exec_continuation continuation;
	struct { struct list_head owners; } scope;
	struct list_head active_link;
};
static const unsigned char kd_service_scope_ops;
static struct list_head kd_service_active;
static struct kd_exec_frame *active_frame;
static int kd_service_dispatch_guard;
static unsigned int pins, fallbacks, register_calls, registered, fail_registration;
static bool kd_rwsem_provider_initialized;
enum { KD_WAIT_EXECUTING = 4, KD_CONT_BOUND = 1, KD_CONT_SUSPENDED = 2,
	KD_ORIGIN_CALL_RUNNING = 3, KD_SERVICE_CALL_WORD = 1,
	KD_SERVICE_CALL_ATOMIC_ORIGIN = 2, KD_SERVICE_CALL_BALANCED_ORIGIN = 1 };
static void preempt_disable(void) { ++pins; }
static void preempt_enable(void) { assert(pins); --pins; }
static unsigned long _raw_spin_lock_irqsave(int *guard)
{ assert(!*guard); *guard = 1; return 0; }
static void _raw_spin_unlock_irqrestore(int *guard, unsigned long flags)
{ assert(*guard && !flags); *guard = 0; }
static struct kd_exec_frame *kd_exec_current_frame(void)
{ assert(pins); return current == &executor ? active_frame : NULL; }
static struct kd_exec_continuation *kd_exec_frame_continuation(struct kd_exec_frame *frame)
{ return frame->continuation; }
static bool kd_exec_native_service_owned(unsigned long object)
{ assert(object); ++fallbacks; return false; }
static long atomic_long_read(const atomic_long_t *value) { return *value; }
struct kd_service_call_desc {
	const char *symbol;
	unsigned long target;
	unsigned int nargs, result_kind, context_kind;
};
static struct kd_rwsem_control_binding control_rows[] = {
	{ .target = 0x3000, .operation = KD_RWSEM_OP_DOWN_WRITE_KILLABLE,
	  .flags = KD_RWSEM_CONTROL_CAPTURE | KD_RWSEM_CONTROL_INTEGER },
	{ .target = 0x6000, .operation = KD_RWSEM_OP_DOWNGRADE_WRITE },
	{ .target = 0x1400, .operation = KD_RWSEM_OP_ASSERT_HELD, .flags = KD_RWSEM_CONTROL_PRIMITIVE },
	{ .target = 0x1500, .operation = KD_RWSEM_OP_ASSERT_HELD_WRITE, .flags = KD_RWSEM_CONTROL_PRIMITIVE },
	{ .target = 0x1600, .operation = KD_RWSEM_OP_IS_LOCKED, .flags = KD_RWSEM_CONTROL_PRIMITIVE },
	{ .target = 0x1700, .operation = KD_RWSEM_OP_IS_CONTENDED, .flags = KD_RWSEM_CONTROL_PRIMITIVE },
	{ .target = 0x1800, .operation = KD_RWSEM_OP_IS_WRITE_OWNER, .flags = KD_RWSEM_CONTROL_PRIMITIVE },
};
const struct kd_rwsem_control_binding *kd_rwsem_provider_controls(unsigned int *count)
{ *count = ARRAY_SIZE(control_rows); return control_rows; }
static struct kd_service_call_desc records[3];
static struct module *record_owners[3];
static char record_labels[3][32];
static int kd_service_call_register(const struct kd_service_call_desc *descriptors,
	unsigned int count, struct module *owner)
{
	++register_calls;
	if (register_calls == fail_registration)
		return -ENOMEM;
	assert(count <= ARRAY_SIZE(records) - registered);
	for (unsigned int i = 0; i < count; ++i, ++registered) {
		records[registered] = descriptors[i];
		snprintf(record_labels[registered], sizeof(record_labels[registered]), "%s", descriptors[i].symbol);
		records[registered].symbol = record_labels[registered];
		record_owners[registered] = owner;
	}
	return 0;
}
#include "query_production.h"

static void initialize_owner(struct kd_service_owner *owner, struct kd_mutex *gate,
	struct kd_rwsem *sem, void *identity, u64 generation)
{
	owner->request.identity = identity;
	owner->request.generation = generation;
	owner->request.logical_origin = &origin;
	owner->request.state = KD_WAIT_EXECUTING;
	owner->admission = (struct kd_admission) {
		.object = sem, .gate = gate, .sem = sem, .committed = true, .gate_held = true,
		.physical_owner = &executor, .phase_held = true, .phase_owner = &executor,
		.phase_kind = 2, .phase_identity = identity, .phase_generation = generation,
	};
	gate->owner = (unsigned long)&executor;
	*sem = (struct kd_rwsem) { .admission = -1, .selected_kind = 2,
		.selected_owner = &executor, .selected_identity = identity, .phase_generation = generation };
}

int main(void)
{
	struct kd_service_root root = { 0 };
	struct kd_service_owner child = { 0 };
	struct kd_rwsem outer_sem, inner_sem;
	struct kd_mutex outer_gate, inner_gate;
	struct kd_exec_frame frame = { .continuation = &root.continuation };
	struct kd_exec_continuation *cont = &root.continuation;
	void *identity = &root;

	assert(!kd_rwsem_provider_init());
	assert(kd_rwsem_provider_initialized && register_calls == 2 && registered == 3);
	assert(records[0].target == 0x1700 && records[1].target == 0x1800);
	assert(!record_owners[0] && !record_owners[1]);
	assert(records[0].nargs == 1 && records[1].context_kind == KD_SERVICE_CALL_BALANCED_ORIGIN);
	assert(!strcmp(records[2].symbol, "kd_service_write_owned"));
	assert(records[2].target == (unsigned long)kd_service_write_owned && record_owners[2] == THIS_MODULE);
	assert(records[2].nargs == 2 && records[2].result_kind == KD_SERVICE_CALL_WORD);
	assert(records[2].context_kind == KD_SERVICE_CALL_ATOMIC_ORIGIN);
	registered = register_calls = 0; fail_registration = 2; kd_rwsem_provider_initialized = false;
	assert(kd_rwsem_provider_init() == -ENOMEM && !kd_rwsem_provider_initialized && registered == 2);
	registered = register_calls = 0; fail_registration = 0;
	control_rows[2].flags |= KD_RWSEM_CONTROL_CAPTURE;
	assert(kd_rwsem_provider_init() == -EINVAL && !registered);
	control_rows[2].flags = KD_RWSEM_CONTROL_PRIMITIVE;

	list_init(&kd_service_active); list_init(&root.scope.owners);
	initialize_owner(&root.owner, &outer_gate, &outer_sem, identity, 7);
	list_add(&root.scope.owners, &root.owner.link);
	list_add(&kd_service_active, &root.active_link);
	cont->request = &root.owner.request; cont->generation = 7;
	cont->service_ops = &kd_service_scope_ops; cont->executor = &executor;
	cont->state = KD_CONT_BOUND; active_frame = &frame; current = &executor;
	assert(kd_service_write_owned(&outer_sem, &executor));
	assert(!kd_service_write_owned(&outer_sem, &origin));
	current = &origin; cont->executor = NULL; cont->state = KD_CONT_SUSPENDED;
	cont->origin_call = (struct kd_origin_call) { .origin = &origin, .identity = identity,
		.generation = 7, .phase = KD_ORIGIN_CALL_RUNNING, .servicing = true };
	assert(kd_service_write_owned(&outer_sem, &origin));
	assert(!kd_service_write_owned(&outer_sem, &other));
	assert(!kd_service_write_owned(&inner_sem, &origin));
	outer_sem.selected_identity = &child;
	assert(!kd_service_write_owned(&outer_sem, &origin)); outer_sem.selected_identity = identity;
	++outer_sem.phase_generation;
	assert(!kd_service_write_owned(&outer_sem, &origin)); --outer_sem.phase_generation;
	outer_gate.owner |= 4UL;
	assert(!kd_service_write_owned(&outer_sem, &origin)); outer_gate.owner &= ~4UL;
	root.owner.admission.pickup_pending = true;
	assert(!kd_service_write_owned(&outer_sem, &origin)); root.owner.admission.pickup_pending = false;
	outer_gate.owner = (unsigned long)&other;
	assert(!kd_service_write_owned(&outer_sem, &origin)); outer_gate.owner = (unsigned long)&executor;
	outer_sem.admission = 1;
	assert(!kd_service_write_owned(&outer_sem, &origin)); outer_sem.admission = -1;
	++cont->generation;
	assert(!kd_service_write_owned(&outer_sem, &origin)); --cont->generation;
	cont->origin_call.identity = &child;
	assert(!kd_service_write_owned(&outer_sem, &origin)); cont->origin_call.identity = identity;
	assert(fallbacks == 1);
	initialize_owner(&child, &inner_gate, &inner_sem, &child, 9);
	list_add(&root.scope.owners, &child.link); root.owner.released = true;
	assert(!kd_service_write_owned(&outer_sem, &origin));
	assert(kd_service_write_owned(&inner_sem, &origin));
	child.released = true;
	assert(!kd_service_write_owned(&inner_sem, &origin));
	assert(!pins && !kd_service_dispatch_guard);
	puts("PASS production writer query: exact O/E ownership, nested/post-release state and descriptor registration; supplied runtime observations");
	return 0;
}
