/* SPDX-License-Identifier: GPL-2.0 */
/* Production release/CALL consumers and service routing with supplied physical
 * operations. The separate Native join fixture exercises its real ACK registry. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>

typedef uint64_t u64;
#include "release_types.h"

struct list_head { struct list_head *next, *prev; };
static void list_init(struct list_head *head) { head->next = head->prev = head; }
static void list_add(struct list_head *item, struct list_head *head)
{ item->next = head->next; item->prev = head; head->next->prev = item; head->next = item; }
#define container_of(pointer, type, field) ((type *)((char *)(pointer) - offsetof(type, field)))
#define list_for_each_entry(item, head, field) \
	for (struct list_head *cursor = (head)->next; cursor != (head) && \
	     ((item) = container_of(cursor, __typeof__(*(item)), field), true); cursor = cursor->next)
#define list_for_each_entry_reverse(item, head, field) \
	for (struct list_head *cursor = (head)->prev; cursor != (head) && \
	     ((item) = container_of(cursor, __typeof__(*(item)), field), true); cursor = cursor->prev)
struct task_struct { int pid; } origin = { 11 }, executor = { 22 };
static struct task_struct *current = &executor;
struct kd_wait_request {
	void *identity;
	u64 generation;
	struct task_struct *logical_origin, *physical_waiter;
	enum kd_wait_state state;
};
struct kd_exec_frame {
	struct kd_call_state control_call;
	unsigned long continuation_ip, continuation_sp, entry_ip;
	bool outer_unlock_seen, jit_lock_released[1];
};
struct kd_exec_continuation;
struct kd_exec_service_ops {
	bool (*validate)(const void *, const struct kd_exec_continuation *);
	bool (*all_released)(const void *);
	bool (*outer_released)(const void *);
};
struct kd_exec_continuation {
	struct kd_exec_frame frame;
	struct kd_regs *packet;
	struct kd_wait_request *request;
	struct kd_exec_continuation *root, *packet_owner;
	const struct kd_exec_service_ops *service_ops;
	void *service_scope;
	struct task_struct *executor, *resume_executor;
	u64 generation, reached_artifact_sequence;
	bool reached_active;
	enum kd_exec_cont_state state;
	struct kd_exec_service_call service_call;
	struct kd_origin_call origin_call;
};
enum { KD_SERVICE_NATIVE_READY = 10, KD_NATIVE_OWNER_RCU = 20 };
struct kd_rwsem { unsigned int readers; } sem;
struct kd_admission {
	struct kd_wait_request *request;
	u64 request_generation;
	void *object;
	struct kd_rwsem *sem;
	bool committed, gate_held;
	unsigned int read_state;
};
struct kd_service_owner {
	struct list_head link;
	struct kd_wait_request request;
	struct kd_admission admission;
	u64 root_generation;
	bool released;
};
struct kd_service_scope {
	struct list_head owners;
	struct kd_service_owner *outer;
	struct kd_exec_continuation *continuation;
};
struct kd_native_owner {
	struct list_head link;
	struct task_struct *origin;
	void *identity;
	u64 generation;
	bool held, native_custody;
};
struct kd_service_root {
	struct kd_exec_continuation continuation;
	struct kd_service_owner owner;
	struct kd_service_scope scope;
	struct list_head native_owners;
	bool native_handoff;
	unsigned int transport;
};
struct kd_service_call_entry { unsigned long target; } native_entry;
static struct kd_service_root root;
static struct kd_service_owner child;
static struct kd_regs packet;
static unsigned long words[16];
static unsigned int releases, downgrades, read_finishes, read_transfers, retired_children;
static unsigned int resumes, handoffs, native_waits, rpc_acks, entry_puts, module_refs;
static unsigned int preceding_effects;
static unsigned int expected_resumes;
static unsigned int native_pins, native_rcu_depth;
static unsigned long expected_ip, expected_sp;

#define BUG_ON(value) assert(!(value))
#define BUG() assert(false)
#define pr_err(...) ((void)0)
#define smp_load_acquire(pointer) (*(pointer))
#define smp_store_release(pointer, value) (*(pointer) = (value))
#define THIS_MODULE (&module_refs)
static void __module_get(unsigned int *module) { ++*module; }
static struct kd_exec_frame *kd_exec_current_frame(void) { return &root.continuation.frame; }
static bool kd_exec_cont_valid(const struct kd_exec_continuation *cont)
{ return cont == &root.continuation && cont->generation == cont->request->generation; }
static int kd_exec_cont_call_word(struct kd_exec_continuation *cont, unsigned long *return_ip)
{
	if (cont->packet->sp != (unsigned long)&words[4]) return -EFAULT;
	*return_ip = words[4]; return 0;
}
static bool validate(const void *scope, const struct kd_exec_continuation *cont)
{ return scope == &root.scope && cont == &root.continuation; }
static bool kd_service_scope_released(const void *scope);
static bool kd_service_scope_outer_released(const void *scope);
static const struct kd_exec_service_ops ops = {
	.validate = validate, .all_released = kd_service_scope_released,
	.outer_released = kd_service_scope_outer_released,
};
static bool kd_service_call_invocation_matches(const struct kd_service_call_entry *entry,
	unsigned long source, unsigned long execution)
{ return entry == &native_entry && source == entry->target && !execution; }
static void kd_service_call_put(struct kd_service_call_entry *entry)
{ assert(entry == &native_entry && rpc_acks == 1); ++entry_puts; }
static void kd_exec_frame_save_continuation(struct kd_exec_frame *frame, struct kd_regs *regs)
{
	assert(frame == &root.continuation.frame && regs == &packet);
	frame->continuation_ip = regs->ip; frame->continuation_sp = regs->sp;
}
static void kd_admission_release(struct kd_admission *admission)
{ assert(admission->gate_held); admission->gate_held = false; ++releases; }
static void kd_admission_downgrade_proxy(struct kd_admission *admission)
{
	assert(admission->sem && admission->gate_held && admission->committed);
	assert(admission->read_state == KD_ADMISSION_READ_NONE && !admission->sem->readers);
	admission->read_state = KD_ADMISSION_READ_PROXY_LIVE;
	++downgrades;
}
static void kd_admission_finish_read(struct kd_admission *admission)
{
	if (admission->read_state == KD_ADMISSION_READ_PROXY_LIVE) {
		assert(admission->sem && admission->gate_held && !admission->sem->readers);
		admission->read_state = KD_ADMISSION_READ_PROXY_CONSUMING;
		kd_admission_release(admission);
		admission->read_state = KD_ADMISSION_READ_RELEASED;
		++read_finishes;
		return;
	}
	assert(admission->sem && admission->read_state == KD_ADMISSION_READ_LIVE);
	assert(admission->sem->readers == 1);
	--admission->sem->readers; admission->read_state = KD_ADMISSION_READ_RELEASED; ++read_finishes;
}
static void kd_admission_read_to_native(struct kd_admission *admission)
{
	assert(!admission->gate_held && admission->read_state == KD_ADMISSION_READ_LIVE);
	assert(admission->sem->readers == 1);
	admission->read_state = KD_ADMISSION_READ_NATIVE; ++read_transfers;
}
static void kd_service_trace_event(const char *event, struct kd_service_root *scope,
	const struct kd_service_owner *owner)
{ (void)event; assert(scope == &root && owner); }
static void kd_service_retire_child(struct kd_service_owner *owner)
{ assert(owner == &child && owner->released); ++retired_children; }
static unsigned int kd_service_native_pins(struct kd_service_root *scope)
{ assert(scope == &root); return native_pins; }
static unsigned int kd_service_native_depth(struct kd_service_root *scope, unsigned int kind)
{ assert(scope == &root && kind == KD_NATIVE_OWNER_RCU); return native_rcu_depth; }
static int kd_service_acquire_into(struct kd_service_root *scope, struct kd_service_owner *owner)
{ (void)scope; (void)owner; assert(false); return 0; }
static int kd_service_nested(struct kd_service_root *scope)
{ (void)scope; assert(false); return 0; }
static int kd_service_memory_call(struct kd_service_root *scope)
{ (void)scope; assert(false); return 0; }
static int kd_exe_resume_retained(struct kd_exec_frame *frame)
{ assert(frame == &root.continuation.frame); ++resumes; return KD_EXE_RUN_TO_UNLOCK; }
static void kd_service_unpin(struct kd_exec_continuation *cont)
{
	assert(cont->state == KD_CONT_BOUND && cont->executor == current);
	cont->state = KD_CONT_SUSPENDED; cont->executor = NULL; cont->resume_executor = current;
}
static void kd_service_pin_resume(struct kd_exec_continuation *cont)
{
	assert(cont->state == KD_CONT_SUSPENDED && cont->resume_executor == current);
	cont->state = KD_CONT_BOUND; cont->executor = current; cont->resume_executor = NULL;
}
static int kd_exec_cont_suspend(struct kd_exec_continuation *cont, enum kd_exec_cont_wait wait)
{ assert(wait == KD_CONT_WAIT_SERVICE); kd_service_unpin(cont); return 0; }
static struct kd_exec_frame *kd_exec_cont_resume(struct kd_exec_continuation *cont)
{ kd_service_pin_resume(cont); return &cont->frame; }
static int kd_service_native_prepare(struct kd_service_root *scope)
{ assert(scope == &root); return 0; }
static int kd_service_native_spill(struct kd_service_root *scope)
{ (void)scope; assert(false); return 0; }
static void kd_service_primitive_trace(const char *event, struct kd_service_root *scope)
{ (void)event; assert(scope == &root); }
static bool need_resched(void) { return false; }
static void cond_resched(void) { assert(false); }
static void cpu_relax(void)
{
	struct kd_origin_call *call = &root.continuation.origin_call;
	assert(call->phase == KD_ORIGIN_CALL_REQUESTED && !rpc_acks);
	assert(root.continuation.state == KD_CONT_SUSPENDED);
	/* Supplied Native operation returns its ACK without consuming the source
	 * CALL. Its production completion consumer owns that word. */
	++rpc_acks; call->phase = KD_ORIGIN_CALL_DONE;
}
static int kd_exec_native_service_begin(struct kd_exec_frame *frame)
{
	assert(frame == &root.continuation.frame && root.native_handoff);
	assert(root.continuation.state == KD_CONT_SUSPENDED);
	assert(frame->control_call.phase == KD_CALL_COMPLETE);
	assert(packet.orig_ax == KD_REG_ORIGIN_SUFFIX_TAG);
	assert(packet.ip == expected_ip && packet.sp == expected_sp);
	assert(frame->continuation_ip == packet.ip && frame->continuation_sp == packet.sp);
	assert(packet.flags == 0xad7 && packet.ax == 0x55 && packet.di == 0x66);
	assert(preceding_effects == 1 && resumes == expected_resumes);
	++handoffs; return 0;
}
static int kd_exec_native_wait(struct kd_exec_frame *frame)
{ assert(frame == &root.continuation.frame && handoffs == 1); ++native_waits; return 0; }

#include "release_production.h"

static void add_owner(struct kd_service_owner *owner, bool rwsem, unsigned int generation)
{
	owner->request = (struct kd_wait_request) { .identity = owner, .generation = generation,
		.logical_origin = &origin, .physical_waiter = current, .state = KD_WAIT_EXECUTING };
	owner->admission = (struct kd_admission) { .object = owner, .sem = rwsem ? &sem : NULL,
		.request = &owner->request, .request_generation = generation,
		.committed = true, .gate_held = true };
	owner->root_generation = 7;
	list_add(&owner->link, &root.scope.owners);
}
static void reset(bool nested, bool rwsem)
{
	memset(&root, 0, sizeof(root)); memset(&child, 0, sizeof(child));
	memset(&packet, 0, sizeof(packet)); memset(words, 0, sizeof(words)); sem.readers = 0;
	releases = downgrades = read_finishes = read_transfers = retired_children = 0;
	resumes = handoffs = native_waits = rpc_acks = entry_puts = module_refs = 0;
	preceding_effects = 1;
	expected_resumes = 0;
	native_pins = native_rcu_depth = 0;
	list_init(&root.scope.owners); list_init(&root.native_owners);
	root.scope.outer = &root.owner; root.scope.continuation = &root.continuation;
	add_owner(&root.owner, rwsem, 7);
	if (nested) add_owner(&child, false, 9);
	struct kd_exec_continuation *cont = &root.continuation;
	cont->request = &root.owner.request; cont->generation = 7;
	cont->packet = &packet; cont->root = cont->packet_owner = cont;
	cont->executor = current; cont->state = KD_CONT_BOUND;
	cont->service_ops = &ops; cont->service_scope = &root.scope;
	cont->frame.entry_ip = 0x1000;
	packet.flags = 0xad7; packet.ax = 0x55; packet.di = 0x66;
	packet.sp = (unsigned long)&words[4]; words[4] = 0x4000;
	expected_ip = words[4]; expected_sp = packet.sp + sizeof(unsigned long);
}
static void prepare_release(struct kd_service_owner *owner, enum kd_exec_service_api api)
{
	packet.ip = 0x2000 + api;
	root.continuation.service_call = (struct kd_exec_service_call) {
		.api = api, .object = (unsigned long)owner,
		.call = { .target = packet.ip, .stack = packet.sp, .return_ip = words[4],
			.phase = KD_CALL_PENDING } };
}
static void check_kd_releases(void)
{
	reset(true, true); prepare_release(&child, KD_SERVICE_MUTEX_UNLOCK);
	assert(kd_service_run_scope(&root, KD_EXE_RUN_SERVICE) == KD_EXE_RUN_HANDOFF);
	assert(child.released && root.owner.admission.gate_held && !root.owner.released);
	assert(releases == 1 && retired_children == 1 && handoffs == 1 && native_waits == 1 && !resumes);
	assert(!root.continuation.frame.outer_unlock_seen);
	reset(true, true); prepare_release(&root.owner, KD_SERVICE_RWSEM_UP_WRITE);
	assert(kd_service_run_scope(&root, KD_EXE_RUN_SERVICE) == KD_EXE_RUN_HANDOFF);
	assert(root.owner.released && child.admission.gate_held && !child.released);
	assert(releases == 1 && !retired_children && root.continuation.frame.outer_unlock_seen);
	reset(false, false); prepare_release(&root.owner, KD_SERVICE_MUTEX_UNLOCK);
	unsigned long call_ip = packet.ip, call_sp = packet.sp;
	assert(kd_service_run_scope(&root, KD_EXE_RUN_SERVICE) == KD_EXE_RUN_TO_UNLOCK);
	assert(packet.ip == call_ip && packet.sp == call_sp && !packet.orig_ax);
	assert(root.owner.released && releases == 1 && !handoffs && !resumes);
	reset(false, true); root.owner.admission.gate_held = false;
	root.owner.admission.read_state = KD_ADMISSION_READ_LIVE; sem.readers = 1;
	prepare_release(&root.owner, KD_SERVICE_RWSEM_UP_READ);
	assert(kd_service_run_scope(&root, KD_EXE_RUN_SERVICE) == KD_EXE_RUN_TO_UNLOCK);
	assert(root.owner.released && !sem.readers && read_finishes == 1 && !releases && !handoffs);
}
static void next_release(struct kd_service_owner *owner, enum kd_exec_service_api api)
{
	assert(root.continuation.frame.control_call.phase == KD_CALL_COMPLETE);
	assert(packet.ip == expected_ip && packet.sp == expected_sp);
	assert(packet.flags == 0xad7 && packet.ax == 0x55 && packet.di == 0x66);
	packet.sp = (unsigned long)&words[4]; words[4] += 0x100;
	expected_ip = words[4]; expected_sp = packet.sp + sizeof(unsigned long);
	prepare_release(owner, api);
}
static void check_proxy_read_suffix(void)
{
	/* A completed downgrade CALL resumes the same image without a real reader
	 * credit. The later matching read release consumes that writer once. */
	reset(false, true); prepare_release(&root.owner, KD_SERVICE_RWSEM_DOWNGRADE);
	assert(kd_service_release_call(&root) == KD_EXE_RUN_TO_UNLOCK);
	assert(!root.owner.released && root.owner.admission.gate_held && !sem.readers);
	assert(root.owner.admission.read_state == KD_ADMISSION_READ_PROXY_LIVE);
	assert(downgrades == 1 && !releases && !read_transfers && !read_finishes && resumes == 1);
	assert(packet.ip == expected_ip && packet.sp == expected_sp && !packet.orig_ax);
	next_release(&root.owner, KD_SERVICE_RWSEM_UP_READ);
	assert(kd_service_run_scope(&root, KD_EXE_RUN_SERVICE) == KD_EXE_RUN_TO_UNLOCK);
	assert(root.owner.released && !root.owner.admission.gate_held && !sem.readers);
	assert(releases == 1 && read_finishes == 1 && !handoffs && resumes == 1);

	/* Releasing the logically read outer acquisition is non-LIFO when a child
	 * still exists. Its exact CALL completes, then the other release contract
	 * preserves the child's physical gate through the ordinary Native handoff. */
	reset(true, true); prepare_release(&root.owner, KD_SERVICE_RWSEM_DOWNGRADE);
	assert(kd_service_release_call(&root) == KD_EXE_RUN_TO_UNLOCK);
	assert(child.admission.gate_held && !child.released && !releases);
	next_release(&root.owner, KD_SERVICE_RWSEM_UP_READ); expected_resumes = 1;
	assert(kd_service_run_scope(&root, KD_EXE_RUN_SERVICE) == KD_EXE_RUN_HANDOFF);
	assert(root.owner.released && child.admission.gate_held && !child.released);
	assert(releases == 1 && read_finishes == 1 && !sem.readers && handoffs == 1);
	assert(root.continuation.frame.outer_unlock_seen && !retired_children);

	/* An unrelated inner release still ends its unit while the logically read
	 * outer acquisition keeps the actual writer across Native handback. */
	reset(true, true); prepare_release(&root.owner, KD_SERVICE_RWSEM_DOWNGRADE);
	assert(kd_service_release_call(&root) == KD_EXE_RUN_TO_UNLOCK);
	next_release(&child, KD_SERVICE_MUTEX_UNLOCK); expected_resumes = 1;
	assert(kd_service_run_scope(&root, KD_EXE_RUN_SERVICE) == KD_EXE_RUN_HANDOFF);
	assert(child.released && root.owner.admission.gate_held && !root.owner.released);
	assert(root.owner.admission.read_state == KD_ADMISSION_READ_PROXY_LIVE);
	assert(!sem.readers && !read_transfers && !read_finishes && releases == 1 && handoffs == 1);

	/* A nested rwsem has its own logical-read state; its final release must not
	 * release the unrelated outer mutex or turn that release into image resume. */
	reset(true, false); child.admission.sem = &sem;
	prepare_release(&child, KD_SERVICE_RWSEM_DOWNGRADE);
	assert(kd_service_release_call(&root) == KD_EXE_RUN_TO_UNLOCK);
	assert(root.owner.admission.gate_held && child.admission.gate_held && !sem.readers);
	next_release(&child, KD_SERVICE_RWSEM_UP_READ); expected_resumes = 1;
	assert(kd_service_run_scope(&root, KD_EXE_RUN_SERVICE) == KD_EXE_RUN_HANDOFF);
	assert(child.released && root.owner.admission.gate_held && !root.owner.released);
	assert(releases == 1 && read_finishes == 1 && retired_children == 1 && handoffs == 1);
	assert(!root.continuation.frame.outer_unlock_seen);
}
static void check_native_calls(void)
{
	const unsigned int contexts[] = { KD_SERVICE_CALL_SPIN_UNLOCK, KD_SERVICE_CALL_RCU_UNLOCK,
		KD_SERVICE_CALL_RWSEM_WRITE_UNLOCK, KD_SERVICE_CALL_BALANCED_ORIGIN };
	for (unsigned int i = 0; i < sizeof(contexts) / sizeof(contexts[0]); i++) {
		reset(false, true);
		struct kd_exec_continuation *cont = &root.continuation;
		native_entry.target = packet.ip = 0x5000;
		cont->origin_call = (struct kd_origin_call) { .packet = &packet, .target = packet.ip,
			.entry = &native_entry, .origin = &origin, .executor = current,
			.identity = cont->request->identity, .generation = 7, .sequence = 3,
			.context_kind = contexts[i], .phase = KD_ORIGIN_CALL_PREPARED,
			.executor_pinned = i == 0,
			.call = { .target = packet.ip, .stack = packet.sp, .return_ip = words[4],
				.phase = KD_CALL_PENDING } };
		assert(kd_service_run_scope(&root, KD_EXE_RUN_ORIGIN_CALL) ==
			(i < 3 ? KD_EXE_RUN_HANDOFF : KD_EXE_RUN_TO_UNLOCK));
		assert(rpc_acks == 1 && entry_puts == 1 && cont->origin_call.phase == KD_ORIGIN_CALL_CONSUMED);
		assert(packet.ip == expected_ip && packet.sp == expected_sp);
		assert(handoffs == (i < 3) && resumes == (i == 3));
		assert(root.owner.admission.gate_held && !root.owner.released && !releases);
	}
}
static void check_completion_refusals(void)
{
	reset(true, true); prepare_release(&child, KD_SERVICE_MUTEX_UNLOCK);
	words[4]++;
	assert(kd_exec_cont_service_complete(&root.continuation, NULL, 0) == -EINVAL);
	assert(packet.sp == (unsigned long)&words[4] && !child.released && !handoffs);
	words[4]--;
	root.continuation.packet_owner = NULL;
	assert(kd_exec_cont_service_complete(&root.continuation, NULL, 0) == -EINVAL);
	assert(!releases && !handoffs);
	reset(true, true); prepare_release(&child, KD_SERVICE_MUTEX_UNLOCK);
	root.continuation.generation++;
	assert(kd_exec_cont_service_complete(&root.continuation, NULL, 0) == -EINVAL);
	assert(!releases && !handoffs && packet.sp == (unsigned long)&words[4]);
	reset(false, true);
	assert(kd_exec_cont_native_complete(&root.continuation, 3) == -EINVAL);
	assert(!rpc_acks && !entry_puts && packet.sp == (unsigned long)&words[4]);
	reset(true, true);
	assert(kd_service_release_boundary(&root, -ESTALE) == -ESTALE && !handoffs && !packet.orig_ax);
}
int main(int argc, char **argv)
{
	if (argc == 2) {
		if (!strcmp(argv[1], "proxy-pin") || !strcmp(argv[1], "proxy-rcu")) {
			reset(false, true); prepare_release(&root.owner, KD_SERVICE_RWSEM_DOWNGRADE);
			assert(kd_service_release_call(&root) == KD_EXE_RUN_TO_UNLOCK);
			next_release(&root.owner, KD_SERVICE_RWSEM_UP_READ);
			native_pins = !strcmp(argv[1], "proxy-pin");
			native_rcu_depth = !strcmp(argv[1], "proxy-rcu");
			(void)kd_service_release_call(&root);
			return 0;
		}
		reset(true, true); prepare_release(&child, KD_SERVICE_MUTEX_UNLOCK);
		root.continuation.service_call.api = KD_SERVICE_NONE;
		root.continuation.frame.control_call.phase = !strcmp(argv[1], "pending") ?
			KD_CALL_PENDING : KD_CALL_COMPLETE;
		if (!strcmp(argv[1], "pending")) {
			root.continuation.frame.continuation_ip = packet.ip;
			root.continuation.frame.continuation_sp = packet.sp;
		}
		/* Neither a still-pushed CALL nor an unsaved continuation is an
		 * authorized post-release packet. The production helper must refuse. */
		(void)kd_service_release_boundary(&root, 0);
		return 0;
	}
	assert(argc == 1);
	check_kd_releases(); check_proxy_read_suffix(); check_native_calls(); check_completion_refusals();
	puts("PASS production release units: proxy read suffix, matching final release, nested/non-LIFO boundaries, Native releases and refusal ordering");
	return 0;
}
