/* SPDX-License-Identifier: GPL-2.0 */
/* Production spin batch/frame decisions around a substituted JIT body.
 * Preserve tickets and complete packets across outer release and pool refusal. */
#include "spin_single_mock.h"
#include <stddef.h>

typedef uint32_t u32;
typedef uint64_t u64;
struct list_head {
	struct list_head *next, *prev;
};
/* Native routing is empty for this scripted pool user; keep the production
 * frame constructor/pop contract rather than replacing its new predicate. */
#define INIT_LIST_HEAD(head)                         \
	do {                                        \
		(head)->next = (head)->prev = (head); \
	} while (0)
static bool list_empty(const struct list_head *head)
{
	return head->next == head;
}
#define kd_exec_frame_push real_frame_push
#define kd_exec_frame_push_borrowed real_frame_push_spin
#define kd_exec_frame_bind real_frame_bind
#define kd_exec_frame_pop real_frame_pop
#include "spin_outer_types.h"
#undef kd_exec_frame_push
#undef kd_exec_frame_push_borrowed
#undef kd_exec_frame_bind
#undef kd_exec_frame_pop

static struct kd_spin_exec_request *fixture_request(struct kd_spin_node *node)
{
	if (!node->execution)
		node->execution = calloc(1, sizeof(*node->execution));
	return node->execution;
}

static raw_spinlock_t origins[2];
static struct kd_spin_ref executor_ref, b_ref, next_ref;
static struct task_struct waiter = { .pid = 3 };
static struct kd_spin_node kd_spin_nodes[MAX_NODES], successor, deferred;
#define request kd_spin_nodes[0]
static struct shadow_stack shadow_states[2];
#define local_shadow_stack shadow_states[0]
static struct kd_spin_exec_request test_execution;
static struct kd_exec_frame *active_frame = &test_execution.frame;
#define active (*active_frame)
static struct kd_exec_frame requester;
static struct kd_spin_exec_request request_pool[12];
static struct kd_spin_exec_request *kd_spin_requests = request_pool;
static void reset_request(void)
{
	memset(&request, 0, sizeof(request));
	active_frame = &test_execution.frame;
	memset(&test_execution, 0, sizeof(test_execution));
	request.execution = &test_execution;
	fixture_request(&request)->frame.regs_ref = &active.regs;
	test_execution.users.counter = 1;
}
static struct kd_exec_context kd_exec_context[2], pool_before[2];
static struct task_struct pressure_tasks[KD_EXEC_MAX_NESTING];
static unsigned int full_pool_calls, full_pool_batches;
static struct kd_spin_jit_context request_context;

/* Model the omitted producer's direct preparation of the child ledger. The
 * real combiner must validate and reuse these columns without staging them. */
static void prepare_virtual_ledger(void)
{
	struct kd_exec_frame *frame = &request.execution->frame;

	request_context = (struct kd_spin_jit_context){
		.requester = &requester,
		.lock_depth = 2,
	};
	frame->complex_ready = true;
	frame->jit_lock_addr[0] = requester.outer_lock_addr;
	frame->jit_lock_addr[1] = (unsigned long)&origins[0];
	for (unsigned int i = 0; i < 2; i++) {
		frame->jit_lock_kind[i] = KD_EXEC_LOCK_QUEUE_OWNER;
		frame->jit_lock_node[i] = NULL;
		frame->jit_lock_released[i] = false;
	}
}
static struct pt_regs readmission_regs;
static unsigned long kd_exec_invariant_failures;
static unsigned int mode, failures, scripts, pops, native_waits;
static unsigned int early_releases, waits, stage;
static unsigned int jit_disables;
static bool next_holds;
static bool preentry_queue_case;
static void preentry_queue_peer(void);
static const unsigned int kd_combiner_batch_size = 1024;
static bool queue_probe;
static unsigned int queue_finishes;
static unsigned int handoff_starts, handoff_ends;

/* Observe the release API and the packet visible at that boundary. This is a
 * deterministic compiler-contract check, not a Linux memory-order litmus. */
static struct {
	struct kd_spin_node *node;
	struct pt_regs regs;
	unsigned int count;
	bool enabled, completed;
} wake_probe;
static void wake_before(const void *address, size_t size, uintptr_t value);
static void wake_after(const void *address);

#undef CHECK
#ifdef KD_OUTER_MUTATION
#define STOP_MUTATION() exit(1)
#else
#define STOP_MUTATION() ((void)0)
#endif
#define CHECK(c)                                                            \
	do {                                                                \
		checks++;                                                   \
		if (!(c)) {                                                 \
			failures++;                                         \
			fprintf(stderr, "FAIL mode=%u line=%d: %s\n", mode, \
				__LINE__, #c);                              \
			STOP_MUTATION();                                    \
		}                                                           \
	} while (0)
#define BUG_ON(c)                                                      \
	do {                                                           \
		if (c) {                                               \
			fprintf(stderr, "BUG mode=%u line=%d\n", mode, \
				__LINE__);                             \
			exit(2);                                       \
		}                                                      \
	} while (0)
#define BUG() BUG_ON(true)
#define WARN_ON_ONCE(c) ((void)(c))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define unlikely(x) (x)
#define smp_store_release(p, v)                                            \
	do {                                                             \
		__auto_type publish_ptr = (p);                            \
		__typeof__(*publish_ptr) publish_value = (v);              \
		wake_before(publish_ptr, sizeof(*publish_ptr),             \
			    (uintptr_t)publish_value);                    \
		*publish_ptr = publish_value;                             \
		wake_after(publish_ptr);                                  \
	} while (0)
#define smp_load_acquire(p) (*(p))
#define smp_mb() ((void)0)
#define KD_SPIN_REQUEST_SLOTS 12
#define atomic_read_acquire(p) ((p)->counter)
#define atomic_set(p, v) ((p)->counter = (v))
#define atomic_inc(p) (++(p)->counter)
#define atomic_dec(p) (--(p)->counter)
#define atomic_dec_and_test(p) (--(p)->counter == 0)
#define atomic64_inc(p) (++*(p))
#define atomic_cmpxchg_acquire(p, old, v) cmpxchg(&(p)->counter, old, v)
#define alloc_percpu(type) calloc(2, sizeof(type))
#define free_percpu(p) free(p)
#define container_of(p, type, member) \
	((type *)((char *)(p) - offsetof(type, member)))
#define _Q_LOCKED_VAL_HL 1
#define _Q_LOCKED_COMBINER_VAL 3
#define _Q_UNLOCKED_OOO_VAL 7
#define IRQ_NUMA_NODE 255
#define KD_SPIN_DIAG_NATIVE_FALLBACK 0
#define get_rsp_from_regs(name, regs, i) ((unsigned long *)(regs))[i]
#define KD_EXE_LOCK_SPIN 1
#define numa_node_id() mock_cpu
#define smp_processor_id() mock_cpu
#define pr_info(...)                         \
	do {                                 \
		if (0)                       \
			printf(__VA_ARGS__); \
	} while (0)
#define pr_warn_ratelimited(...) pr_info(__VA_ARGS__)
#define KD_PR_ERR(...) pr_info(__VA_ARGS__)
#define KD_PR_INFO(...) pr_info(__VA_ARGS__)
#define KD_PR_DEBUG(...) pr_info(__VA_ARGS__)
#define print_debug(...) pr_info(__VA_ARGS__)

/* Observe the producer's endpoint before any wake/pop, not duplicate executor
 * statistics. test_jit_entry_scope compiles the real counter/clock policy. */
static u64 kd_exe_queue_timing_start(void)
{
	return queue_probe ? 100 : 0;
}
static void kd_exe_queue_timing_end(bool mutex, uint64_t *queued_at, u64 end)
{
	if (!queue_probe)
		return;
	CHECK(!mutex && queued_at == &fixture_request(&request)->queued_at_ns && end == 100);
	CHECK(*queued_at == 50 && active.executed && scripts == 1);
	CHECK(request.locked && !fixture_request(&request)->native_resume && !pops && !native_waits);
	*queued_at = 0;
	queue_finishes++;
}

/* The production envelope must begin before borrowing/remote publication and
 * consume only local scalars after the native wait has allowed node reuse. */
static u64 kd_exe_native_timing_start(void)
{
	CHECK(request.locked && !fixture_request(&request)->native_resume && !native_waits && !pops);
	handoff_starts++;
	return 150;
}
static void kd_exe_native_handoff_timing_end(bool mutex, u64 start)
{
	CHECK(!mutex && start == 150 && native_waits == 1 && !pops);
	handoff_ends++;
}

static void cpu_relax(void) __attribute__((unused));
static struct kd_spin_diag_slot *kd_spin_diag_find(unsigned long lock)
{ return (void *)lock; }
static bool kd_spin_jit_is_disabled(const struct kd_spin_diag_slot *lock)
{
	(void)lock;
	return mode == 9;
}
static void kd_spin_jit_disable(struct qspinlock *lock)
{
	(void)lock;
	CHECK(mode == 11);
	jit_disables++;
}
static void kd_spin_diag_record(struct qspinlock *lock, int event,
				unsigned int depth)
{
	(void)lock;
	(void)event;
	(void)depth;
}
static void kd_spin_debug_jit_not_ready(struct kd_spin_diag_slot *lock,
					unsigned int depth)
{
	(void)lock;
	(void)depth;
}
static void kd_spin_debug_jit_success(struct kd_spin_diag_slot *lock,
				      unsigned int depth)
{
	(void)lock;
	(void)depth;
}
static void kd_spin_debug_combiner(struct kd_spin_diag_slot *lock, unsigned int depth)
{
	(void)lock;
	(void)depth;
}
static void kd_spin_debug_ooo_unlock(struct qspinlock *lock, unsigned int depth)
{
	(void)lock;
	(void)depth;
	early_releases++;
}
static void kd_spin_diag_invariant_failure(void)
{
	CHECK(false);
}
/* Opaque lookup token: the production backend must pass this exact slot. */
static struct kd_exe_info { int lock_kind; } ready_entry = {
	.lock_kind = KD_EXE_LOCK_SPIN,
};
static bool kd_exe_entry_is_ready(const struct kd_exe_info *exe, int pid,
				 unsigned long ip)
{
	(void)pid;
	CHECK(ip == (fixture_request(&request)->jit_waiter ? 0x900UL : 0x800UL));
	return exe == &ready_entry && mode != 4;
}
/* Hint address selection is exercised with real layouts by spin_batch_fixture.
 * Here observe its position before any execution/wake in the real batch. */
struct kd_spin_batch;
#define __maybe_unused __attribute__((unused))
/* Queue/owner scenarios substitute JIT; the actual alternate ABI is executed
 * separately by test_spin_wwjump. A fabricated request cannot enter that ABI. */
static bool kd_spin_batch_prepare_simple(struct kd_spin_batch *batch,
					 struct kd_spin_node *node)
{ (void)batch; (void)node; return false; }
static bool kd_exe_spin_batch_completed(const struct kd_jit_batch_call *call)
{ (void)call; abort(); }
static void kd_jit_clobber_call_v1(struct kd_jit_batch_call *call)
{ (void)call; abort(); }
static void kd_jit_legacy_batch_call(struct kd_jit_batch_call *call)
{ (void)call; abort(); }
static int execute_cs(struct qspinlock *, struct kd_spin_node *, struct kd_spin_batch *);
static int kd_exe_spin_batch_resume(struct kd_exe_info *exe,
				    const struct kd_jit_batch_call *call)
{ (void)exe; (void)call; abort(); }

/* Real hint preparation/bounds and protected-page checks live in the
 * batch fixture; this queue fixture retains only its publication interface. */
static void kd_spin_prepare_prefetch(struct kd_spin_node *node,
                                     struct pt_regs *regs)
{ (void)node; (void)regs; }

static void kd_spin_prefetch_request(struct kd_spin_node *node)
{
	if (node)
		CHECK(node->locked && !node->completed);
}
static struct kd_exe_info *kd_get_exe(int pid, unsigned long ip)
{
	(void)pid;
	CHECK(ip == (fixture_request(&request)->jit_waiter ? 0x900UL : 0x800UL));
	return mode != 4 ? &ready_entry : NULL;
}
static void kd_exe_add_abi(int pid, unsigned long ip, int kind, unsigned int abi)
{
	(void)pid;
	(void)ip;
	CHECK(kind == KD_EXE_LOCK_SPIN);
	CHECK(abi == KD_ENTRY_ABI_LEGACY);
}
static int kd_exe_on_call_hl_entry(struct kd_exe_info *exe,
				   struct pt_regs *regs, unsigned long ip,
				   unsigned long lock);

static int kd_exec_invariant_failure(void);
/* Only the real pool takes leases; scripted outer frames are boundary packets. */
static unsigned int source_frames;
static bool kd_source_is_open(void) { return true; }
static bool kd_source_frame_get(void)
{
	source_frames++;
	return true;
}
static void kd_source_frame_put(void)
{
	CHECK(source_frames > 0);
	source_frames--;
}
/* Frame storage is an array in this CPU substitute; keep the allocator body. */
#undef this_cpu_ptr
#define this_cpu_ptr(p) (&(*(p))[mock_cpu])
#define kd_exec_frame_push real_frame_push
#define kd_exec_frame_push_borrowed real_frame_push_spin
#define kd_exec_frame_bind real_frame_bind
#define kd_exec_frame_pop real_frame_pop
#include "spin_frame_pool_production.h"
#undef kd_exec_frame_push
#undef kd_exec_frame_push_borrowed
#undef kd_exec_frame_bind
#undef kd_exec_frame_pop
#undef this_cpu_ptr
#define this_cpu_ptr(p) (&(p)[mock_cpu])

int kd_exec_frame_bind(struct kd_exec_frame *frame, unsigned int depth, bool lease)
{
	active_frame = frame;
	CHECK(frame == &request.execution->frame);
	CHECK(fixture_request(&request)->frame.regs_ref == kd_exec_frame_regs(frame));
	if (mode == 8) {
		CHECK(kd_exec_current_context()->depth == KD_EXEC_MAX_NESTING &&
		      kd_exec_context_validate(kd_exec_current_context()));
		full_pool_calls++;
		return real_frame_bind(frame, depth, lease);
	}
	frame->held_lock_depth = frame->outer_lock_depth = depth;
	frame->batch_lease = lease;
	return 0;
}
int kd_exec_frame_pop(struct kd_exec_frame *frame, struct pt_regs *regs)
{
	CHECK(frame == &active &&
	      (frame->completion_seen ||
	       (!frame->executed && frame->state == KD_EXEC_FRAME_ERROR)));
	if (regs && regs != kd_exec_frame_regs(frame))
		*regs = *kd_exec_frame_regs(frame);
	pops++;
	return 0;
}
int kd_exec_native_begin(struct kd_exec_frame *frame, bool mutex)
{
	CHECK(frame == &active && !mutex && origins[1].held);
	CHECK(handoff_starts == 1 && !handoff_ends);
	return 0;
}
int kd_exec_native_wait(struct kd_exec_frame *frame);
int kd_spin_jit_nested_cleanup(struct kd_exec_frame *frame)
{
	CHECK(frame == &active && !origins[1].held);
	return 0;
}
int kd_spin_jit_abort_cleanup(struct kd_exec_frame *frame)
{
	(void)frame;
	return 0;
}
void kd_spin_unlock_protocol(struct qspinlock *lock)
{
	kd_spinlock_t *gate = (kd_spinlock_t *)lock;
	CHECK(gate && gate->locked == 3);
	kd_spin_debug_ooo_unlock(lock, 2);
	if (gate)
		gate->locked = 7;
}

/* These scripted combiner requests enter through real tickets, never the
 * root native-fast hook. Keep its unrelated per-CPU ownership empty here;
 * test_spin_routing exercises the production fast path and retirement guard. */
static bool kd_spin_fast_active(void) { return false; }
static bool kd_spin_fast_idle(void) { return true; }

#undef request
/* Deterministic producer pause between tail exchange and release-link. The
 * consumer must wait only when tail proves a successor, never for a true tail. */
#define _Q_TAIL_MASK_HL 0xffff0000u
static struct kd_spin_node *link_tail, *link_parent, *link_publish;
static unsigned int link_waits;
static struct kd_spin_node *link_decode_tail(int tail)
{
	CHECK(((unsigned int)tail & _Q_TAIL_MASK_HL) && link_tail);
	return link_tail;
}
#define smp_cond_load_relaxed_sched(p, condition) \
	({ \
		if (!*(p) && link_publish) { \
			CHECK((p) == &link_parent->next); \
			*(p) = link_publish; \
			link_publish = NULL; \
			link_waits++; \
		} \
		__typeof__(*(p)) VAL = *(p); \
		CHECK(condition); \
		VAL; \
	})

#define decode_tail link_decode_tail
#include "spin_outer_production.h"
#undef decode_tail
#define request kd_spin_nodes[0]

static struct kd_spin_request test_request(struct qspinlock *lock)
{
	struct kd_spin_request physical = { 0 };

	CHECK(kd_spin_entry_find((raw_spinlock_t *)lock, &physical.ref));
	physical.word = kd_spin_request_word(&physical.ref);
	return physical;
}
static void test_claim_origin(struct qspinlock *lock)
{
	struct kd_spin_request physical = test_request(lock);
	kd_spin_claim_origin(&physical);
}
static void test_release_origin(struct qspinlock *lock)
{
	struct kd_spin_request physical = test_request(lock);
	kd_spin_release_origin(&physical);
}
#define kd_spin_claim_origin test_claim_origin
#define kd_spin_release_origin test_release_origin


/* Only the designated node is disposable. Other releases still use the same
 * substituted primitive without inventing an extra waiter or reference. */
static bool wake_address(const void *address)
{
	if (!wake_probe.enabled)
		return false;
	return address == (wake_probe.completed ?
			   (void *)&wake_probe.node->locked_completed :
			   (void *)&wake_probe.node->locked);
}

static void wake_before(const void *address, size_t size, uintptr_t value)
{
	struct kd_spin_node *node = wake_probe.node;

	if (!wake_address(address))
		return;
	CHECK(!wake_probe.count++);
	CHECK(size == (wake_probe.completed ? sizeof(u16) : sizeof(u8)));
	CHECK(value == (wake_probe.completed ? 1 : 0));
	CHECK(node->locked && !node->completed && !fixture_request(node)->native_resume);
	CHECK((kd_exec_current_frame() != &fixture_request(&request)->frame) && fixture_request(node)->frame.logical_task == &waiter);
	CHECK(!memcmp(fixture_request(node)->frame.regs_ref, &wake_probe.regs, sizeof(*fixture_request(node)->frame.regs_ref)));
	CHECK(scripts == wake_probe.completed && pops == scripts);
	CHECK(origins[0].held &&
	      kd_spin_entry_owner((raw_spinlock_t *)kd_spin_entry_word(&executor_ref)) == (unsigned long)current);
	CHECK(kd_spin_entry_word(&executor_ref)->locked ==
	      (wake_probe.completed ? _Q_LOCKED_COMBINER_VAL : _Q_LOCKED_VAL_HL));
}

static void wake_after(const void *address)
{
	if (!wake_address(address))
		return;
	/* Model immediate slot reuse after the acquire-side waiter wakes. The
	 * publisher must use its saved successor and never rewrite this packet. */
	memset(fixture_request(wake_probe.node)->frame.regs_ref, 0xa5, sizeof(*fixture_request(wake_probe.node)->frame.regs_ref));
	wake_probe.node->next = NULL;
	fixture_request(wake_probe.node)->frame.logical_task = NULL;
}

static void checked_run_combiner(struct qspinlock *lock,
				 struct kd_spin_node *node)
{
	unsigned int calls = full_pool_calls;
	bool full = mode == 8 && node == &request;

	if (full) {
		CHECK(sizeof(struct pt_regs) == 168 &&
		      offsetof(struct kd_exec_frame, regs) == 72 &&
		      sizeof(struct kd_exec_context) == 5400);
		CHECK(!kd_exec_current_context()->depth);
		for (unsigned int i = 0; i < KD_EXEC_MAX_NESTING; i++) {
			struct pt_regs regs;
			struct kd_exec_frame *frame;

			memset(&regs, 0x31 + i, sizeof(regs));
			pressure_tasks[i].pid = 100 + i;
			frame = real_frame_push(&regs, 0x1000 + i, 0, NULL,
						NULL, 0, 0x3000 + i,
						&pressure_tasks[i]);
			CHECK(frame == &kd_exec_current_context()->frames[i]);
			CHECK(frame &&
			      !memcmp(&frame->regs, &regs, sizeof(regs)));
		}
		memcpy(pool_before, kd_exec_context, sizeof(pool_before));
	}
	struct kd_spin_request physical = test_request(lock);
	/* These existing fixtures use synthetic tail codes. Map them to the
	 * actual last node of their prepared chain; the delayed-link test sets
	 * a distinct in-flight tail explicitly before calling the helper. */
	struct kd_spin_node *saved_link_tail = link_tail;
	link_tail = node;
	while (link_tail->next)
		link_tail = link_tail->next;
	run_combiner(lock, node, &physical);
	link_tail = saved_link_tail;
	if (full) {
		CHECK(full_pool_calls == calls + 1);
		CHECK(!memcmp(pool_before, kd_exec_context,
			      sizeof(pool_before)));
		CHECK(kd_exec_context_validate(kd_exec_current_context()));
		CHECK(!node->completed && !fixture_request(node)->native_resume &&
		      (kd_exec_current_frame() != &fixture_request(&request)->frame));
		/* Retire only the unexecuted, API-created test frames after queue return. */
		while (kd_exec_current_frame()) {
			struct kd_exec_frame *frame = kd_exec_current_frame();

			CHECK(kd_exec_frame_abort(frame) == 0);
			CHECK(real_frame_pop(frame, NULL) == 0);
		}
		CHECK(!kd_exec_current_context()->owner &&
		      kd_exec_context_validate(kd_exec_current_context()));
		full_pool_batches++;
	}
}

#define run_combiner checked_run_combiner

static void checked_queue_combiner(struct qspinlock *lock,
		struct kd_spin_node *node, struct kd_spin_request *physical)
{
	struct kd_spin_request local = test_request(lock);
	CHECK(local.word == physical->word &&
	      local.ref.entry == physical->ref.entry &&
	      local.ref.sequence == physical->ref.sequence);
	checked_run_combiner(lock, node);
}

static struct qspinlock *a_lock(void)
{
	return (struct qspinlock *)&origins[0];
}

/* The old executor must not steal an unlocked word with pending/tail state.
 * Deterministic scheduling advances each state on a separate failed trylock. */
static void cpu_relax(void)
{
	if (preentry_queue_case) {
		preentry_queue_peer();
		return;
	}
	kd_spinlock_t *gate = kd_spin_entry_word(&executor_ref);
	CHECK(next_holds && gate && current == &tasks[0] && mock_preempt == 1);
	waits++;
	if (!stage) {
		mock_cpu = 1;
		current = &tasks[1];
		CHECK(kd_spin_entry_release_origin(&next_ref) == 0);
		gate->locked = 0;
		CHECK(kd_spin_entry_end(&next_ref) == 0);
		mock_cpu = 0;
		current = &tasks[0];
		gate->pending = 1;
	} else if (stage == 1) {
		gate->pending = 0;
	} else {
		gate->tail = 0;
		next_holds = false;
	}
	stage++;
}

static void successor_progress(void)
{
	kd_spinlock_t *gate = kd_spin_entry_word(&executor_ref);
	struct kd_spin_node *published = &successor;
#ifdef NUMA_AWARE
	if (mode == 5)
		published = &deferred;
#endif
	CHECK(!origins[0].held && !gate->locked && !published->locked);
	CHECK(origins[1].held && mock_preempt == 2);
	if (origins[0].held || gate->locked || published->locked)
		return;
#ifdef NUMA_AWARE
	if (mode == 5) {
		CHECK(!deferred.locked && deferred.next == &successor);
		CHECK(!shadow_states[0].local_queue_head &&
		      !shadow_states[0].local_queue_tail);
	}
#endif
	mock_cpu = 1;
	current = &tasks[1];
	CHECK(kd_spin_entry_begin(&origins[0], KD_SPIN_ENTRY_HOOK, &next_ref) ==
	      0);
	gate->locked = 1;
	CHECK(kd_spin_entry_claim(&next_ref) == 0);
	mock_cpu = 0;
	current = &tasks[0];
	successor.locked = 1;
	successor.next = (void *)0xdeadbeef;
	deferred.locked = 1;
	next_holds = true;
}

static void release_b(void)
{
	CHECK(kd_exec_frame_lock_mark_released(
		      &active, (unsigned long)&origins[1]) == 0);
	kd_spin_release_origin((struct qspinlock *)&origins[1]);
	shadow_states[0].lock_addr[1] = 0;
}

static void early_a(bool native)
{
	if (native)
		CHECK(kd_exec_frame_record_event(
			      &active, KD_EXEC_EVENT_OUTER_UNLOCK, NULL) == 0);
	else
		CHECK(kd_spin_jit_outer_unlock_ooo_ctx(
			      &origins[0], &active.regs, &active) == 0);
	CHECK(kd_exec_frame_record_event(&active, KD_EXEC_EVENT_OUTER_UNLOCK,
					 NULL) == -EINVAL);
	successor_progress();
}

static int kd_exe_on_call_hl_entry(struct kd_exe_info *exe,
				   struct pt_regs *regs, unsigned long ip,
				   unsigned long lock)
{
	CHECK(exe == &ready_entry);
	CHECK(regs == kd_exec_frame_regs(&active) &&
	      ip == (fixture_request(&request)->jit_waiter ? 0x900UL : 0x800UL) &&
	      lock == (unsigned long)&origins[0]);
	scripts++;
	if (mode == 11 || mode == 12) {
		CHECK(!active.executed && &request.execution->frame == &active);
		CHECK(!memcmp(fixture_request(&request)->frame.regs_ref, &readmission_regs,
			      sizeof(*fixture_request(&request)->frame.regs_ref)));
		/* A prebody refusal preserves the single shared input packet. */
		return mode == 11 ? KD_EXE_RUN_ERROR : KD_EXE_NO_RUN;
	}
	active.executed = true;
	if (mode == 10) {
		CHECK(!memcmp(regs, &readmission_regs, sizeof(*regs)));
		CHECK(active.gsbase == 0x20000 &&
		      active.logical_task == &waiter);
		/* Give the publication observer an output packet that differs from
		 * entry, so waking before the final register copy cannot pass. */
		if (wake_probe.enabled)
			regs->ax ^= 0x12345678UL;
		return KD_EXE_RUN_TO_UNLOCK;
	}
	if (mode == 6) {
		CHECK(regs->ip == 0x801 && active.resume_target == &requester);
		CHECK(active.outer_lock_index == 1 &&
		      active.jit_lock_depth == 2);
		return KD_EXE_RUN_TO_UNLOCK;
	}
	/* Substitute the dispatch boundary, then use the real checkpoint helper
	 * before mutating nested ownership just as the production dispatcher does. */
	kd_spin_jit_prepare_complex(&active);
	regs = &active.regs;
	CHECK(kd_spin_entry_begin(&origins[1], KD_SPIN_ENTRY_VIRTUAL, &b_ref) ==
	      0);
	kd_spin_word((struct qspinlock *)&origins[1])->locked = 1;
	kd_spin_claim_origin((struct qspinlock *)&origins[1]);
	active.jit_lock_depth = active.held_lock_depth = 2;
	active.jit_lock_addr[1] = (unsigned long)&origins[1];
	active.jit_lock_kind[1] = KD_EXEC_LOCK_FAST;
	shadow_states[0].lock_addr[1] = (unsigned long)&origins[1];
	if (mode == 2)
		return KD_EXE_RUN_NATIVE;
	if (mode != 0)
		early_a(false);
	if (mode == 3)
		return KD_EXE_RUN_NATIVE;
	release_b();
	return KD_EXE_RUN_TO_UNLOCK;
}

int kd_exec_native_wait(struct kd_exec_frame *frame)
{
	CHECK(frame == &active && fixture_request(&request)->native_resume && !request.locked);
	native_waits++;
	if (mode == 2)
		early_a(true);
	release_b();
	return 0;
}

/* Selection may append remote nodes before admission rejects the current
 * waiter. Walk a bounded expected chain: a regression must fail, not hang. */
static unsigned int rejected_selection(bool virtual, unsigned int cpu)
{
	const unsigned int rejection_modes[] = { 4, 7, 8, 9 };
	unsigned int cases = 0;
	unsigned int max_prefix = 0;

#ifdef NUMA_AWARE
	max_prefix = 2;
#endif
	mock_cpu = cpu;
	current = &tasks[cpu];
	for (unsigned int reason = 0; reason < ARRAY_SIZE(rejection_modes);
	     reason++) {
		mode = rejection_modes[reason];
		if (virtual && mode != 8)
			continue;
		for (unsigned int prefix = 0; prefix <= max_prefix; prefix++) {
			for (unsigned int count = 0; count <= 8; count++) {
				struct kd_spin_node nodes[10] = { 0 };
				struct kd_spin_node *expected[12], *cursor;
				unsigned long saved[8] = { 0, 1, 2, 3,
							   4, 5, 6, 0x800 };
				unsigned int length = 0;
				kd_spinlock_t *gate;
				struct pt_regs expected_regs;
				struct kd_exec_frame parent_before;
				struct kd_spin_jit_context context_before;

				reset_request();
				memset(&successor, 0, sizeof(successor));
				memset(shadow_states, 0, sizeof(shadow_states));
				executor_ref = (struct kd_spin_ref){ 0 };
				CHECK(kd_spin_entry_begin(&origins[0],
							  KD_SPIN_ENTRY_HOOK,
							  &executor_ref) == 0);
				gate = kd_spin_entry_word(&executor_ref);
				gate->locked = 3;
				kd_spin_claim_origin(a_lock());
				shadow_states[cpu].lock_addr[0] =
					(unsigned long)&origins[0];
				shadow_states[cpu].curr_cs_cpu =
					shadow_states[cpu].prev_cs_cpu = -1;
				memset(fixture_request(&request)->frame.regs_ref, 0x5a,
				       sizeof(*fixture_request(&request)->frame.regs_ref));
				fixture_request(&request)->frame.regs_ref->sp = (unsigned long)saved;
				fixture_request(&request)->frame.regs_ref->di = (unsigned long)&origins[0];
				fixture_request(&request)->frame.regs_ref->ip = 0x801;
				fixture_request(&request)->frame.gsbase = 0x20000;
				fixture_request(&request)->frame.logical_task = &waiter;
				request.cpuid = cpu ^ 1;
				fixture_request(&request)->pinned_context = mode == 7;
				request.locked = successor.locked = 1;
				request.next = count ? &nodes[prefix] :
						       &successor;
				fixture_request(&successor)->frame.logical_task = &tasks[cpu ^ 1];
				expected_regs = *fixture_request(&request)->frame.regs_ref;
				if (virtual) {
					requester = (struct kd_exec_frame){
						.regs = *fixture_request(&request)->frame.regs_ref,
						.entry_ip = 0x900,
						.outer_lock_addr = 0x1000,
						.logical_task = &waiter,
						.gsbase = fixture_request(&request)->frame.gsbase,
						.state = KD_EXEC_FRAME_RUNNING,
						.remote_result =
							KD_EXEC_REMOTE_WAITING,
					};
					prepare_virtual_ledger();
					fixture_request(&request)->jit_waiter = true;
					fixture_request(&request)->jit_context = &request_context;
					parent_before = requester;
					context_before = request_context;
				} else {
					expected_regs.bx = 1;
					expected_regs.r12 = 2;
					expected_regs.r13 = 3;
					expected_regs.r14 = 4;
					expected_regs.r15 = 5;
					expected_regs.bp = 6;
					expected_regs.ip = 0x800;
					expected_regs.sp =
						(unsigned long)&saved[8];
				}
				for (unsigned int i = 0; i < prefix + count;
				     i++) {
					nodes[i].locked = 1;
					nodes[i].socket_id = cpu ^ 1;
					nodes[i].cpuid = cpu ^ 1;
					fixture_request(&nodes[i])->frame.logical_task =
						&tasks[cpu ^ 1];
					nodes[i].next = i + 1 < prefix + count ?
								&nodes[i + 1] :
								&successor;
				}
#ifdef NUMA_AWARE
				for (unsigned int i = 0; i < prefix; i++) {
					add_to_local_queue(&nodes[i]);
					expected[length++] = &nodes[i];
				}
				if (prefix)
					nodes[prefix - 1].next = &request;
#endif
				expected[length++] = &request;
				for (unsigned int i = 0; i < count; i++)
					expected[length++] = &nodes[prefix + i];
				expected[length++] = &successor;
				scripts = pops = 0;
				run_combiner(a_lock(), &request);

				CHECK(!scripts && !pops && !request.completed);
				CHECK(!fixture_request(&request)->native_resume &&
				      (kd_exec_current_frame() != &fixture_request(&request)->frame) &&
				      !fixture_request(&request)->jit_retry &&
				      fixture_request(&request)->frame.gsbase == 0x20000 &&
				      fixture_request(&request)->frame.logical_task == &waiter);
				CHECK(!memcmp(fixture_request(&request)->frame.regs_ref, &expected_regs,
					      sizeof(expected_regs)));
				CHECK(fixture_request(&request)->native_regs_decoded ==
				      !virtual);
				if (virtual) {
					CHECK(!memcmp(&requester,
						      &parent_before,
						      sizeof(parent_before)));
					CHECK(!memcmp(&request_context,
						      &context_before,
						      sizeof(context_before)));
				}
				CHECK(origins[0].held &&
				      kd_spin_entry_owner((raw_spinlock_t *)gate) == (unsigned long)current &&
				      mock_preempt == 1);
				cursor = expected[0];
				for (unsigned int i = 0; i < length; i++) {
					CHECK(cursor == expected[i]);
					CHECK(expected[i]->locked == (i != 0));
					CHECK(!expected[i]->completed);
					if (cursor)
						cursor = cursor->next;
				}
				CHECK(!cursor);
#ifdef NUMA_AWARE
				CHECK(!shadow_states[cpu].local_queue_head &&
				      !shadow_states[cpu].local_queue_tail);
#endif
				gate->val.counter = 1;
				kd_spin_release_origin(a_lock());
				CHECK(!mock_preempt &&
				      kd_spin_entries_check_idle() == 0);
				cases++;
			}
		}
	}
	mock_cpu = 0;
	current = &tasks[0];
	return cases;
}

/* Distinct owners retry one packet. NUMA-on publishes a committed prefix
 * before each retry; scheduling and prefix consumption remain deterministic. */
static unsigned int repeated_admission(void)
{
	unsigned int cases = 0;

	for (unsigned int pattern = 0; pattern < 3; pattern++) {
		for (unsigned int refusals = 1; refusals <= 4; refusals++) {
			unsigned long saved[40];

			/* Keep erroneous repeated reads in bounds so the old code
			 * produces failed register checks, not an accidental fault. */
			for (unsigned int i = 0; i < ARRAY_SIZE(saved); i++)
				saved[i] = 0x1000 + i;
			for (unsigned int i = 0; i < 7; i++)
				saved[i] = i;
			saved[7] = 0x800;
			reset_request();
			memset(&successor, 0, sizeof(successor));
			memset(shadow_states, 0, sizeof(shadow_states));
			fixture_request(&request)->frame.regs_ref->sp = (unsigned long)saved;
			fixture_request(&request)->frame.regs_ref->di = (unsigned long)&origins[0];
			fixture_request(&request)->frame.logical_task = &waiter;
			request.cpuid = 2;
			fixture_request(&request)->frame.gsbase = 0x20000;
			request.next = &successor;
			fixture_request(&successor)->frame.logical_task = &waiter;
			successor.cpuid = 2;
			successor.locked = 1;
			readmission_regs = (struct pt_regs){
				.ip = 0x800,
				.sp = (unsigned long)&saved[8],
				.di = (unsigned long)&origins[0],
				.bx = 1,
				.r12 = 2,
				.r13 = 3,
				.r14 = 4,
				.r15 = 5,
				.bp = 6,
			};
			scripts = pops = 0;
			for (unsigned int attempt = 0; attempt <= refusals;
			     attempt++) {
				kd_spinlock_t *gate;
				bool ready = attempt == refusals;
#ifdef NUMA_AWARE
				struct kd_spin_node prefix = {
					.locked = 1,
					.cpuid = (attempt & 1) ^ 1,
					.execution = &(struct kd_spin_exec_request){ .frame.logical_task = &tasks[(attempt & 1) ^ 1] },
					.next = &request,
				};
#endif
				mode = ready	     ? 10 :
				       pattern == 0  ? 4 :
				       pattern == 1  ? 8 :
				       (attempt & 1) ? 8 :
						       4;
				mock_cpu = attempt & 1;
				current = &tasks[mock_cpu];
				executor_ref = (struct kd_spin_ref){ 0 };
				CHECK(kd_spin_entry_begin(&origins[0],
							  KD_SPIN_ENTRY_HOOK,
							  &executor_ref) == 0);
				gate = kd_spin_entry_word(&executor_ref);
				gate->locked = 3;
				kd_spin_claim_origin(a_lock());
				shadow_states[mock_cpu].lock_addr[0] =
					(unsigned long)&origins[0];
				shadow_states[mock_cpu].curr_cs_cpu = -1;
				shadow_states[mock_cpu].prev_cs_cpu = -1;
				request.locked = 1;
#ifdef NUMA_AWARE
				add_to_local_queue(&prefix);
#endif
				run_combiner(a_lock(), &request);
				CHECK(!memcmp(fixture_request(&request)->frame.regs_ref, &readmission_regs,
					      sizeof(*fixture_request(&request)->frame.regs_ref)));
				CHECK(request.completed == ready &&
				      scripts == ready && pops == ready &&
				      (kd_exec_current_frame() != &fixture_request(&request)->frame));
				CHECK(request.next == &successor &&
				      !successor.next && !successor.completed);
				CHECK(origins[0].held &&
				      kd_spin_entry_owner((raw_spinlock_t *)gate) == (unsigned long)current &&
				      mock_preempt == 1);
#ifdef NUMA_AWARE
				CHECK(!prefix.locked && !prefix.completed &&
				      prefix.next ==
					      (ready ? &successor : &request));
				CHECK(request.locked == !ready &&
				      successor.locked);
				CHECK(!shadow_states[mock_cpu].local_queue_head &&
				      !shadow_states[mock_cpu].local_queue_tail);
#else
				CHECK(!request.locked &&
				      successor.locked == !ready);
#endif
				gate->val.counter = 1;
				kd_spin_release_origin(a_lock());
				shadow_states[mock_cpu].lock_addr[0] = 0;
				CHECK(!mock_preempt &&
				      kd_spin_entries_check_idle() == 0);
			}
			cases++;
		}
	}
	mock_cpu = 0;
	current = &tasks[0];
	return cases;
}

/* Rejected pre-entry frames must recover the node's original packet, for
 * both native and virtual inputs, before publishing any completion. */
static unsigned int preentry_packet(void)
{
	unsigned int cases = 0;

	for (unsigned int virtual = 0; virtual < 2; virtual++) {
		for (mode = 11; mode <= 12; mode++) {
			unsigned long saved[8] = { 0, 1, 2, 3, 4, 5, 6, 0x800 };
			kd_spinlock_t *gate;

			reset_request();
			memset(&successor, 0, sizeof(successor));
			memset(shadow_states, 0, sizeof(shadow_states));
			executor_ref = (struct kd_spin_ref){ 0 };
			CHECK(kd_spin_entry_begin(&origins[0],
						  KD_SPIN_ENTRY_HOOK,
						  &executor_ref) == 0);
			gate = kd_spin_entry_word(&executor_ref);
			gate->locked = 3;
			kd_spin_claim_origin(a_lock());
			shadow_states[0].lock_addr[0] =
				(unsigned long)&origins[0];
			shadow_states[0].curr_cs_cpu =
				shadow_states[0].prev_cs_cpu = -1;
			readmission_regs = (struct pt_regs){
				.ip = 0x800,
				.sp = (unsigned long)&saved[8],
				.di = (unsigned long)&origins[0],
				.bx = 1,
				.r12 = 2,
				.r13 = 3,
				.r14 = 4,
				.r15 = 5,
				.bp = 6,
			};
			*fixture_request(&request)->frame.regs_ref = readmission_regs;
			fixture_request(&request)->frame.regs_ref->sp = (unsigned long)saved;
			fixture_request(&request)->frame.gsbase = 0x20000;
			request.cpuid = 1;
			fixture_request(&request)->frame.logical_task = &waiter;
			request.locked = successor.locked = 1;
			request.next = &successor;
			fixture_request(&successor)->frame.logical_task = &tasks[1];
			if (virtual) {
				readmission_regs.ip = 0x801;
				readmission_regs.sp = (unsigned long)saved;
				*fixture_request(&request)->frame.regs_ref = readmission_regs;
				requester = (struct kd_exec_frame){
					.entry_ip = 0x900,
					.outer_lock_addr = 0x1000,
					.logical_task = &waiter,
					.gsbase = 0x20000,
					.state = KD_EXEC_FRAME_RUNNING,
					.remote_result = KD_EXEC_REMOTE_WAITING,
				};
				prepare_virtual_ledger();
				fixture_request(&request)->jit_waiter = true;
				fixture_request(&request)->jit_context = &request_context;
			}
			scripts = pops = jit_disables = 0;
			run_combiner(a_lock(), &request);
			CHECK(scripts == 1 && pops == 1);
			CHECK(jit_disables == (mode == 11));
			CHECK(!active.executed && !active.completion_seen &&
			      active.state == KD_EXEC_FRAME_ERROR);
			CHECK(!memcmp(fixture_request(&request)->frame.regs_ref, &readmission_regs,
				      sizeof(*fixture_request(&request)->frame.regs_ref)));
			CHECK(!memcmp(kd_exec_frame_regs(&active), &readmission_regs,
				      sizeof(active.regs)));
			CHECK((kd_exec_current_frame() != &fixture_request(&request)->frame) && !request.completed &&
			      !fixture_request(&request)->native_resume &&
			      fixture_request(&request)->jit_retry == !virtual);
			CHECK(fixture_request(&request)->native_regs_decoded == !virtual);
			CHECK(!request.locked && successor.locked &&
			      request.next == &successor && !successor.next);
			CHECK(origins[0].held && !origins[1].held &&
			      kd_spin_entry_owner((raw_spinlock_t *)gate) == (unsigned long)current && mock_preempt == 1);
			if (virtual)
				CHECK(requester.remote_result ==
					      KD_EXEC_REMOTE_WAITING &&
				      !active.resume_target);
			gate->val.counter = 1;
			kd_spin_release_origin(a_lock());
			CHECK(!mock_preempt &&
			      kd_spin_entries_check_idle() == 0);
			cases++;
		}
	}
	return cases;
}

#undef smp_cond_load_relaxed_sched
#include "spin_queue_return_fixture.c"

/* Exercise completion, cold batch handoff, lone waiter and both IRQ/native
 * handoffs through the real combiner. No new routine test entry is needed. */
static unsigned int publication_boundaries(void)
{
	unsigned long saved[8] = { 0 };
	struct pt_regs reused;

	memset(&reused, 0xa5, sizeof(reused));
	for (unsigned int path = 0; path < 5; path++) {
		kd_spinlock_t *gate;

		mode = path == 1 ? 4 : 10;
		reset_request();
		memset(&successor, 0, sizeof(successor));
		memset(shadow_states, 0, sizeof(shadow_states));
		executor_ref = (struct kd_spin_ref){ 0 };
		CHECK(kd_spin_entry_begin(&origins[0], KD_SPIN_ENTRY_HOOK,
					  &executor_ref) == 0);
		gate = kd_spin_entry_word(&executor_ref);
		gate->locked = _Q_LOCKED_COMBINER_VAL;
		kd_spin_claim_origin(a_lock());
		shadow_states[0].lock_addr[0] = (unsigned long)&origins[0];
		shadow_states[0].curr_cs_cpu = shadow_states[0].prev_cs_cpu = -1;
		memset(&readmission_regs, 0x3c, sizeof(readmission_regs));
		readmission_regs.ip = 0x800;
		readmission_regs.sp = (unsigned long)&saved[8];
		readmission_regs.di = (unsigned long)&origins[0];
		*fixture_request(&request)->frame.regs_ref = readmission_regs;
		fixture_request(&request)->native_regs_decoded = true;
		fixture_request(&request)->frame.gsbase = 0x20000;
		request.cpuid = 1;
		fixture_request(&request)->frame.logical_task = fixture_request(&successor)->frame.logical_task = &waiter;
		request.locked = successor.locked = 1;
		request.next = path == 2 ? NULL : &successor;
		if (path == 3)
			request.socket_id = IRQ_NUMA_NODE;
		if (path == 4)
			successor.socket_id = IRQ_NUMA_NODE;
		wake_probe.node = &request;
		wake_probe.regs = readmission_regs;
		wake_probe.completed = path == 0;
		if (wake_probe.completed)
			wake_probe.regs.ax ^= 0x12345678UL;
		wake_probe.count = scripts = pops = 0;
		wake_probe.enabled = true;
		run_combiner(a_lock(), &request);
		wake_probe.enabled = false;
		CHECK(wake_probe.count == 1);
		CHECK(!memcmp(fixture_request(&request)->frame.regs_ref, &reused, sizeof(reused)));
		CHECK(!request.next && !fixture_request(&request)->frame.logical_task);
		CHECK(!request.locked && request.completed == (path == 0));
		CHECK(successor.locked == (path != 0));
		gate->val.counter = _Q_LOCKED_VAL_HL;
		kd_spin_release_origin(a_lock());
		CHECK(!mock_preempt && kd_spin_entries_check_idle() == 0);
	}
	return 5;
}

/* Saturate the actual append-only map through its API, not by writing its
 * occupancy. A still owns its native lock and each CPU has 31 free tickets.
 * Compare the complete producer state at ENOMEM; only the existing PENDING
 * helper may subsequently restore callee/SP. JIT execution and Linux waiting
 * are covered by the live gate-pressure case, not this deterministic fixture. */

static void tail_before_link(void)
{
	struct kd_spin_node node = { 0 }, next = { 0 };
	struct kd_spinlock word = { .val.counter = 3 };

	CHECK(!kd_spin_linked_successor(&word, &node));
	word.val.counter = 0x10003;
	link_tail = &node;
	CHECK(!kd_spin_linked_successor(&word, &node) && !link_waits);
	link_tail = &next;
	link_parent = &node;
	link_publish = &next;
	CHECK(kd_spin_linked_successor(&word, &node) == &next);
	CHECK(link_waits == 1 && !link_publish && word.val.counter == 0x10003);
	CHECK(kd_spin_linked_successor(&word, &node) == &next && link_waits == 1);
	link_tail = link_parent = NULL;
}

int main(void)
{
	tail_before_link();
#ifdef KD_OUTER_BUG_ONLY
	BUG_ON(true);
#endif
	unsigned long saved[8] = { 0, 1, 2, 3, 4, 5, 6, 0x800 };
	tasks[0].pid = 1;
	tasks[1].pid = 2;
	CHECK(kd_spin_entries_init() == 0);
	unsigned int wake_cases = publication_boundaries();
	queue_probe = true;
	for (mode = 0; mode < 8; mode++) {
		kd_spinlock_t *gate;
		bool early = mode != 0 && mode != 4 && mode != 6 && mode != 7;
		reset_request();
		memset(&successor, 0, sizeof(successor));
		memset(&deferred, 0, sizeof(deferred));
		memset(shadow_states, 0, sizeof(shadow_states));
		executor_ref = (struct kd_spin_ref){ 0 };
		b_ref = (struct kd_spin_ref){ 0 };
		CHECK(kd_spin_entry_begin(&origins[0], KD_SPIN_ENTRY_HOOK,
					  &executor_ref) == 0);
		gate = kd_spin_entry_word(&executor_ref);
		gate->locked = 3;
		gate->tail = 4;
		kd_spin_claim_origin(a_lock());
		CHECK(!kd_spin_trylock(kd_spin_word(a_lock())));
		shadow_states[0].lock_addr[0] = (unsigned long)&origins[0];
		shadow_states[0].curr_cs_cpu = shadow_states[0].prev_cs_cpu =
			-1;
		shadow_states[0].local_shadow_stack_ptr = 0x10000;
		fixture_request(&request)->frame.regs_ref->sp = (unsigned long)saved;
		fixture_request(&request)->queued_at_ns = 50;
		queue_finishes = 0;
		handoff_starts = handoff_ends = 0;
		fixture_request(&request)->frame.regs_ref->di = (unsigned long)&origins[0];
		fixture_request(&request)->frame.logical_task = &waiter;
		fixture_request(&request)->frame.gsbase = 0x20000;
		fixture_request(&request)->pinned_context = mode == 7;
		if (mode == 6) {
			requester = (struct kd_exec_frame){
				.entry_ip = 0x900,
				.outer_lock_addr = 0x1000,
				.logical_task = &waiter,
				.gsbase = 0x20000,
				.state = KD_EXEC_FRAME_RUNNING,
				.remote_result = KD_EXEC_REMOTE_WAITING,
			};
			prepare_virtual_ledger();
			fixture_request(&request)->jit_waiter = true;
			fixture_request(&request)->jit_context = &request_context;
			fixture_request(&request)->frame.regs_ref->ip = 0x801;
		}
		request.cpuid = 1;
		request.next = &successor;
		request.locked = successor.locked = deferred.locked = 1;
		fixture_request(&successor)->frame.logical_task = fixture_request(&deferred)->frame.logical_task =
			&tasks[1];
#ifdef NUMA_AWARE
		if (mode == 5) {
			request.next = &deferred;
			deferred.next = &successor;
			deferred.socket_id = 1;
		}
#endif
		scripts = pops = native_waits = early_releases = waits = stage =
			0;
		next_holds = false;
		run_combiner(a_lock(), &request);
		CHECK(scripts == (mode != 4 && mode != 7) && pops == scripts);
		CHECK(queue_finishes == scripts);
		CHECK(fixture_request(&request)->queued_at_ns == (scripts ? 0 : 50));
		CHECK(native_waits == (mode == 2 || mode == 3));
		CHECK(handoff_starts == native_waits && handoff_ends == native_waits);
		CHECK(origins[0].held && kd_spin_entry_owner((raw_spinlock_t *)gate) == (unsigned long)current &&
		      !origins[1].held);
		CHECK(mock_preempt == 1 && mock_preempts[1] == 0 &&
		      !next_holds);
		CHECK(waits == (early ? 3 : 0));
		CHECK(successor.locked == (early || mode == 4 || mode == 7));
#ifdef NUMA_AWARE
		if (mode == 5)
			CHECK(deferred.locked == early);
#endif
		CHECK(request.completed ==
		      (mode == 0 || mode == 1 || mode == 5 || mode == 6));
		if (mode == 6)
			CHECK(requester.remote_result == KD_EXEC_REMOTE_DONE &&
			      !active.resume_target);
		gate->val.counter = 1;
		kd_spin_release_origin(a_lock());
		CHECK(!mock_preempt && kd_spin_entries_check_idle() == 0);
	}
	queue_probe = false;
	unsigned int rejection_cases = 0;
	for (unsigned int cpu = 0; cpu < 2; cpu++) {
		rejection_cases += rejected_selection(false, cpu);
		rejection_cases += rejected_selection(true, cpu);
	}
	unsigned int readmission_cases = repeated_admission();
	unsigned int preentry_cases = preentry_packet();
	unsigned int queue_cases = preentry_queue_return();
	CHECK(!kd_exec_invariant_failures);
	CHECK(full_pool_calls == full_pool_batches && full_pool_calls > 0);
	kd_spin_entries_exit();
	printf("spin outer production progress: %u checks, %u failures, 8 progress + %u rejection + %u readmission + %u preentry scenarios NUMA=%u\n",
	       checks, failures, rejection_cases, readmission_cases,
	       preentry_cases,
#ifdef NUMA_AWARE
	       1U
#else
	       0U
#endif
	);
	printf("spin full frame refusal: %u real API failures, regs=%zu frame=%zu context=%zu\n",
	       full_pool_calls, sizeof(struct pt_regs),
	       sizeof(struct kd_exec_frame), sizeof(struct kd_exec_context));
	printf("spin preentry queue return: %u joined producer/combiner/acquisition cases\n",
	       queue_cases);
	printf("spin wake publication: %u release/packet/reuse boundaries\n",
	       wake_cases);
	return failures ? 1 : 0;
}
