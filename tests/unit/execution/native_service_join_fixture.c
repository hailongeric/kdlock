/* SPDX-License-Identifier: GPL-2.0 */
/* Run production acceptance/release/ACK and terminal joins with actual threads.
 * Task/CPU bindings, physical release and source leases are supplied primitives. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>

typedef uint64_t u64;
struct kd_spin_ref { void *unused; };
#include "join_types.h"
struct list_head { struct list_head *next, *prev; };
static void list_init(struct list_head *head) { head->next = head->prev = head; }
static bool list_empty(const struct list_head *head)
{ return __atomic_load_n(&head->next, __ATOMIC_RELAXED) == head; }
static void list_add(struct list_head *item, struct list_head *head)
{ item->next = head->next; item->prev = head; head->next->prev = item; head->next = item; }
static void list_del_init(struct list_head *item)
{ item->prev->next = item->next; item->next->prev = item->prev; list_init(item); }
#define container_of(pointer, type, field) ((type *)((char *)(pointer) - offsetof(type, field)))
#define list_for_each_entry(item, head, field) \
	for (struct list_head *entry = (head)->next; entry != (head) && \
	     ((item) = container_of(entry, __typeof__(*(item)), field), true); entry = entry->next)
#define list_for_each_entry_reverse(item, head, field) \
	for (struct list_head *entry = (head)->prev; entry != (head) && \
	     ((item) = container_of(entry, __typeof__(*(item)), field), true); entry = entry->prev)
struct guard { pthread_mutex_t mutex; };
struct task_struct { atomic_uint refs; unsigned int id; void *stack; };
static struct task_struct origin __attribute__((aligned(8))) = { .refs = 2, .id = 101 };
static struct task_struct executor __attribute__((aligned(8))) = { .refs = 2, .id = 202 };
static struct task_struct other __attribute__((aligned(8))) = { .refs = 1, .id = 303 };
static _Thread_local struct task_struct *current;
static _Thread_local unsigned int guards;
struct kd_wait_request {
	void *identity;
	u64 generation;
	struct task_struct *logical_origin;
	enum kd_wait_state state;
	void *memberships, *selection, *acquisition;
};
struct kd_exec_continuation;
struct kd_exec_frame {
	struct kd_exec_continuation *continuation;
	struct task_struct *logical_task;
	struct kd_native_request *native_request;
	struct list_head native_link;
	struct kd_regs regs;
	const struct kd_jit_image *image;
	void *resume_target, *remote_request;
	struct { unsigned int phase; } control_call;
	unsigned int packet_state, state, role, entry_abi;
	bool executed, completion_seen, complex_ready, mutex_backend;
};
struct kd_exec_service_ops {
	bool (*native_match)(const void *, unsigned long, enum kd_exec_native_operation,
		struct kd_exec_native_route *);
	int (*native_release)(void *, const struct kd_exec_native_route *);
	bool (*native_finished)(const void *);
};
struct kd_exec_continuation {
	struct kd_wait_request *request;
	u64 generation, root_generation, parent_generation;
	struct kd_exec_continuation *root, *parent, *packet_owner;
	struct task_struct *executor, *resume_executor;
	const struct kd_exec_service_ops *service_ops;
	void *service_scope;
	struct kd_exec_frame frame;
	struct guard guard;
	struct list_head children, owners, storage_owners, child_link;
	struct { unsigned int api; } service_call;
	struct { void *entry; bool servicing; unsigned int phase; } origin_call;
	struct { unsigned int phase; } origin_memory;
	enum kd_exec_cont_state state;
	enum kd_exec_cont_wait wait;
	int result;
	bool native_accepted, source_lease, stack_lease;
	void (*stack_put)(struct task_struct *);
};
typedef long atomic_long_t;
struct kd_mutex { atomic_long_t owner; };
struct kd_rwsem {
	struct kd_mutex gate;
	atomic_long_t admission, readers;
	unsigned int selected_kind;
	struct task_struct *selected_owner;
	void *selected_identity;
	u64 phase_generation;
};
struct kd_admission {
	struct kd_wait_request *request;
	u64 request_generation;
	void *object;
	struct kd_mutex *gate;
	struct kd_rwsem *sem;
	struct task_struct *physical_owner, *phase_owner;
	void *phase_identity;
	u64 phase_generation;
	unsigned int kind, phase_kind, read_state;
	bool committed, gate_held, phase_held, pickup_pending;
};
struct kd_service_owner {
	struct list_head link;
	struct kd_wait_request request;
	struct kd_admission admission;
	u64 root_generation;
	bool released;
};
struct kd_service_scope { struct kd_exec_continuation *continuation; struct list_head owners; };
struct kd_native_owner { struct list_head link; bool held, native_custody; };
struct kd_service_root {
	struct kd_exec_continuation continuation;
	struct kd_service_owner owner;
	struct kd_service_scope scope;
	struct list_head native_owners;
	struct task_struct *worker;
	bool native_handoff;
};
enum { KD_SERVICE_NONE = 0, KD_CALL_NONE = 0,
	KD_CALL_COMPLETE = 1, KD_CALL_PENDING = 2, KD_ORIGIN_CALL_IDLE = 0,
	KD_ORIGIN_CALL_CONSUMED = 1, KD_ORIGIN_MEMORY_IDLE = 0,
	KD_ORIGIN_MEMORY_CONSUMED = 1, KD_EXEC_FRAME_UNUSED = 0, KD_ROLE_DONE = 1,
	KD_ADMISSION_MUTEX = 1, KD_ADMISSION_RWSEM_WRITE = 2,
	KD_ADMISSION_READ_NONE = 0, KD_ADMISSION_READ_LIVE = 1,
	KD_ADMISSION_READ_NATIVE = 2 };
#define KD_MUTEX_OWNER_FLAGS 7UL
#define BUG_ON(value) assert(!(value))
#define READ_ONCE(value) __atomic_load_n(&(value), __ATOMIC_RELAXED)
#define WRITE_ONCE(value, next) __atomic_store_n(&(value), (next), __ATOMIC_RELAXED)
#define smp_load_acquire(pointer) __atomic_load_n((pointer), __ATOMIC_ACQUIRE)
#define smp_store_release(pointer, value) __atomic_store_n((pointer), (value), __ATOMIC_RELEASE)
#define cmpxchg(pointer, old, next) ({ __typeof__(*(pointer)) expected = (old); \
	__atomic_compare_exchange_n((pointer), &expected, (next), false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST); expected; })
#define raw_spin_lock_irqsave(lock, flags) do { \
	assert(!pthread_mutex_lock(&(lock)->mutex)); ++guards; (flags) = 0; } while (0)
#define raw_spin_unlock_irqrestore(lock, flags) do { \
	assert(!(flags) && guards); --guards; assert(!pthread_mutex_unlock(&(lock)->mutex)); } while (0)
#define atomic64_inc(pointer) atomic_fetch_add_explicit((pointer), 1, memory_order_relaxed)
static struct list_head kd_native_frames;
static struct guard kd_native_lock = { .mutex = PTHREAD_MUTEX_INITIALIZER };
static atomic_long kd_native_started, kd_native_completed, kd_native_handed_off, kd_native_unlocks;
static atomic_uint ready, released, source_puts, stack_puts;
static unsigned int mode;
static struct kd_service_root root;
static struct kd_rwsem sem;
static struct kd_mutex nested;
static unsigned long origin_words[64];
static unsigned char frontier_text[] = { 0x67, 0x48, 0x0f, 0xb9, 0x3a };
static struct kd_exe_info frontier_entry;
static const struct kd_jit_image frontier_image = {
	.entry = &frontier_entry, .entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1,
	.immutable = 1,
	.requirements = KD_IMAGE_REQUIRE_SERVICE_QUEUE | KD_IMAGE_REQUIRE_SOURCE_FRONTIER,
};
static unsigned int preceding_effects, frontier_calls;
static int frontier_source_error, frontier_read_error;
#define THREAD_SIZE sizeof(origin_words)
#define task_stack_page(task) ((task)->stack)
static struct kd_exec_frame *kd_exec_current_frame(void) { return &root.continuation.frame; }
static int kd_source_pin_text_range(unsigned long address, unsigned long size)
{ assert(address == (unsigned long)frontier_text && size == sizeof(frontier_text)); return frontier_source_error; }
static int copy_from_kernel_nofault(void *out, const void *in, size_t size)
{ assert(in == frontier_text && size == sizeof(frontier_text));
  if (frontier_read_error) return frontier_read_error; memcpy(out, in, size); return 0; }
static void kd_exec_frame_save_continuation(struct kd_exec_frame *frame, struct kd_regs *regs)
{ assert(frame == &root.continuation.frame && regs == &frame->regs); ++frontier_calls; }
static bool need_resched(void) { return true; }
static unsigned int preempt_count(void) { return 0; }
static bool irqs_disabled(void) { return false; }
static void cpu_relax(void) { sched_yield(); }
static void cond_resched(void) { assert(!guards); sched_yield(); }
static struct kd_exec_continuation *kd_exec_frame_continuation(struct kd_exec_frame *frame)
{ return frame->continuation; }
static struct kd_regs *kd_exec_frame_regs(struct kd_exec_frame *frame) { return &frame->regs; }
static bool kd_exec_frame_remote_pending(const struct kd_exec_frame *frame) { (void)frame; return false; }
static long atomic_long_read(const atomic_long_t *value) { return __atomic_load_n(value, __ATOMIC_RELAXED); }
static bool atomic_long_dec_and_test(atomic_long_t *value)
{ return __atomic_sub_fetch(value, 1, __ATOMIC_SEQ_CST) == 0; }
static void put_task_struct(struct task_struct *task)
{ assert(atomic_fetch_sub(&task->refs, 1) > 1); }
static void stack_put(struct task_struct *task)
{ assert(task == &origin && !guards && list_empty(&kd_native_frames)); ++stack_puts; }
static void kd_source_frame_put(void)
{ assert(!guards && stack_puts == 1 && origin.refs == 1); ++source_puts; }
static void kd_service_trace_event(const char *event, struct kd_service_root *scope,
	const struct kd_service_owner *owner)
{ (void)event; assert(scope == &root && owner && current == &executor); }
static void kd_admission_release(struct kd_admission *a)
{
	assert(current == &executor && !guards && a->gate_held && a->physical_owner == current);
	assert((unsigned long)a->gate->owner == (unsigned long)current);
	a->gate->owner = 0; a->gate_held = false; a->physical_owner = NULL;
	if (a->sem) { a->sem->admission = 0; a->phase_held = false; }
	++released;
}
static void kd_admission_downgrade(struct kd_admission *a)
{ assert(a->sem && a->read_state == KD_ADMISSION_READ_NONE); ++a->sem->readers;
	a->read_state = KD_ADMISSION_READ_LIVE; kd_admission_release(a); }
#include "join_production.h"
#include "native_service_join_frontier.inc"

static const struct kd_exec_service_ops ops = {
	.native_match = kd_service_native_match,
	.native_release = kd_service_native_release,
	.native_finished = kd_service_native_finished,
};
static void initialize_owner(struct kd_service_owner *owner, struct kd_mutex *gate,
	struct kd_rwsem *rwsem, u64 generation)
{
	owner->root_generation = 7;
	owner->request = (struct kd_wait_request) { .identity = owner, .generation = generation,
		.logical_origin = &origin, .state = KD_WAIT_EXECUTING };
	owner->admission = (struct kd_admission) { .request = &owner->request,
		.request_generation = generation, .object = rwsem ? (void *)rwsem : (void *)gate,
		.gate = gate, .sem = rwsem, .physical_owner = &executor, .phase_owner = &executor,
		.phase_identity = owner, .phase_generation = generation, .phase_kind = 2,
		.kind = rwsem ? KD_ADMISSION_RWSEM_WRITE : KD_ADMISSION_MUTEX,
		.committed = true, .gate_held = true, .phase_held = rwsem != NULL };
	gate->owner = (unsigned long)&executor;
	if (rwsem) { rwsem->admission = -1; rwsem->selected_kind = 2;
		rwsem->selected_owner = &executor; rwsem->selected_identity = owner;
		rwsem->phase_generation = generation; }
	list_add(&owner->link, &root.scope.owners);
}
static void *execute(void *unused)
{
	struct kd_service_owner child = { 0 };
	struct kd_exec_continuation *cont = &root.continuation;
	struct kd_exec_native_route route;
	struct list_head anchor;
	(void)unused; current = &executor;
	initialize_owner(&root.owner, &sem.gate, &sem, 7);
	if (mode == 2) {
		root.owner.admission.gate_held = root.owner.admission.phase_held = false;
		root.owner.admission.physical_owner = NULL;
		root.owner.admission.read_state = KD_ADMISSION_READ_LIVE;
		sem.gate.owner = sem.admission = 0; sem.readers = 1;
	} else {
		initialize_owner(&child, &nested, NULL, 9);
		assert(kd_service_native_match(&root.scope, (unsigned long)&sem,
			KD_NATIVE_OPERATION_RWSEM_UP_WRITE, &route));
		++route.generation;
		assert(kd_service_native_release(&root.scope, &route) == -EINVAL && !released);
		++root.owner.admission.request_generation;
		assert(!kd_service_native_match(&root.scope, (unsigned long)&sem,
			KD_NATIVE_OPERATION_RWSEM_UP_WRITE, &route));
		--root.owner.admission.request_generation;
	}
	{
		struct kd_regs before = cont->frame.regs;
		++preceding_effects;
		/* Supply the active executor context for the frontier consumer, then
		 * its established suspended context for the existing registry join. */
		cont->state = KD_CONT_BOUND;
		cont->executor = current;
		check_frontier_refusals(cont);
		/* The dispatcher maps this successful dedicated outcome to retained
		 * HANDOFF. Execute the real consumer before the existing ACCEPT join. */
		assert(!kd_jit_source_frontier(&frontier_entry, &cont->frame, &cont->frame.regs));
		before.orig_ax = KD_REG_ORIGIN_SUFFIX_TAG;
		assert(!memcmp(&before, &cont->frame.regs, sizeof(before)));
		assert(!frontier_entry.status_code && !frontier_entry.tgt_addr && !frontier_entry.jump_from);
		cont->executor = NULL;
		cont->state = KD_CONT_SUSPENDED;
	}
	if (mode == 2) kd_admission_read_to_native(&root.owner.admission);
	assert(!kd_exec_native_service_begin(&cont->frame));
	atomic_store_explicit(&ready, 1, memory_order_release);
	assert(!kd_exec_native_service_wait(&cont->frame));
	assert(list_empty(&kd_native_frames) && !cont->frame.native_request && cont->native_accepted);
	if (mode != 2) { assert(child.released); list_del_init(&child.link); }
	cont->request->state = KD_WAIT_RETURN_ACK;
	list_add(&anchor, &cont->children);
	assert(kd_exec_cont_handoff(cont) == -EINVAL);
	list_del_init(&anchor);
	assert(!kd_exec_cont_handoff(cont) && !cont->frame.completion_seen);
	assert(cont->state == KD_CONT_HANDED_OFF && executor.refs == 1);
	assert(!kd_exec_cont_retire(cont));
	assert(cont->state == KD_CONT_RETIRED && !cont->packet_owner && !cont->source_lease && !cont->stack_lease);
	return NULL;
}
int main(int argc, char **argv)
{
	struct kd_exec_continuation *cont = &root.continuation;
	pthread_t worker;
	assert(argc == 2); mode = !strcmp(argv[1], "read") ? 2 : !strcmp(argv[1], "downgrade") ? 1 : 0;
	current = &origin;
	list_init(&kd_native_frames); list_init(&root.scope.owners); list_init(&root.native_owners);
	cont->generation = cont->root_generation = 7; cont->root = cont; cont->packet_owner = cont;
	cont->request = &root.owner.request; cont->resume_executor = &executor;
	cont->state = KD_CONT_SUSPENDED; cont->source_lease = cont->stack_lease = true;
	cont->stack_put = stack_put; cont->service_ops = &ops; cont->service_scope = &root.scope;
	cont->guard = (struct guard) { .mutex = PTHREAD_MUTEX_INITIALIZER };
	list_init(&cont->children); list_init(&cont->owners); list_init(&cont->storage_owners);
	list_init(&cont->frame.native_link);
	cont->frame.continuation = cont; cont->frame.logical_task = &origin;
	cont->frame.executed = cont->frame.complex_ready = true; cont->frame.packet_state = KD_PACKET_FULL;
	origin.stack = origin_words;
	cont->frame.entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	cont->frame.mutex_backend = true; cont->frame.image = &frontier_image;
	cont->frame.regs = (struct kd_regs) { .ip = (unsigned long)frontier_text,
		.sp = (unsigned long)&origin_words[8], .ax = 7, .di = 11, .si = 13, .dx = 17, .flags = 2 };
	root.scope.continuation = cont; root.worker = &executor; root.native_handoff = true;
	assert(!pthread_create(&worker, NULL, execute, NULL));
	while (!atomic_load_explicit(&ready, memory_order_acquire)) sched_yield();
	assert(!kd_exec_native_accept(&cont->frame));
	if (mode != 2) {
		assert(kd_exec_native_service_owned((unsigned long)&sem));
		current = &other;
		assert(!kd_exec_native_service_unlock((unsigned long)&sem, KD_NATIVE_OPERATION_RWSEM_UP_WRITE));
		current = &origin;
		assert(!kd_exec_native_service_unlock((unsigned long)&nested, KD_NATIVE_OPERATION_RWSEM_UP_WRITE));
		assert(kd_exec_native_service_unlock((unsigned long)&sem,
			mode ? KD_NATIVE_OPERATION_RWSEM_DOWNGRADE : KD_NATIVE_OPERATION_RWSEM_UP_WRITE));
		assert(kd_exec_native_service_active(&origin) && !kd_exec_native_service_owned((unsigned long)&sem));
		assert(!sem.gate.owner && (unsigned long)nested.owner == (unsigned long)&executor);
		assert(kd_exec_native_service_unlock((unsigned long)&nested, KD_NATIVE_OPERATION_MUTEX_UNLOCK));
	}
	assert(!pthread_join(worker, NULL));
	assert(!kd_exec_native_service_active(&origin));
	assert(!kd_exec_native_service_unlock((unsigned long)&sem, KD_NATIVE_OPERATION_RWSEM_UP_WRITE));
	assert(kd_native_started == 1 && kd_native_handed_off == 1 && kd_native_completed == 0);
	assert(kd_native_unlocks == (mode == 2 ? 0 : 2) && released == (mode == 2 ? 0U : 2U));
	assert(source_puts == 1 && stack_puts == 1 && origin.refs == 1 && executor.refs == 1);
	assert(preceding_effects == 1 && frontier_calls == 1);
	assert(sem.readers == (mode ? 1 : 0));
	memset(&root, 0xa5, sizeof(root));
	if (mode) { kd_up_read_non_owner(&sem); assert(!sem.readers); }
	printf("PASS production Native service join: %s; acceptance, exact typed release, final ACK and terminal retirement; supplied physical/task primitives\n", argv[1]);
	return 0;
}
