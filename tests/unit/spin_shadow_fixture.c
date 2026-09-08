/* Deterministic primitives around the extracted production queue-head exit. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

#include "spin_shadow_types.h"

typedef uint32_t u32;

struct qspinlock {
	union {
		int val;
		struct {
			uint8_t locked;
			uint8_t pending;
			uint16_t tail;
		};
	};
};
typedef struct qspinlock raw_spinlock_t;

/* Only producer-visible fields; this fixture does not test the register ABI. */
struct pt_regs {
	unsigned long ip, sp, di;
};
struct task_struct {
	int pid;
};
struct kd_spin_ref {
	void *entry;
	unsigned long sequence;
};
struct kd_exec_frame {
	bool valid, complete;
	unsigned int jit_lock_depth;
	unsigned long gsbase, jit_lock_addr[KD_EXEC_MAX_LOCK_DEPTH];
	enum kd_exec_lock_kind jit_lock_kind[KD_EXEC_MAX_LOCK_DEPTH];
	void *jit_lock_node[KD_EXEC_MAX_LOCK_DEPTH];
	bool jit_lock_released[KD_EXEC_MAX_LOCK_DEPTH];
	struct task_struct *logical_task;
	struct kd_spin_ref spin_origin;
	int remote_result;
	void *remote_request;
	struct {
		enum kd_call_phase phase;
	} control_call;
};

struct kd_spin_jit_context {
	struct kd_exec_frame *requester;
	unsigned int lock_depth;
	unsigned long lock_addr[KD_EXEC_MAX_LOCK_DEPTH];
	enum kd_exec_lock_kind lock_kind[KD_EXEC_MAX_LOCK_DEPTH];
	void *lock_node[KD_EXEC_MAX_LOCK_DEPTH];
	bool lock_released[KD_EXEC_MAX_LOCK_DEPTH];
};
struct kd_spin_node {
	struct kd_spin_node *next;
	struct qspinlock *lock;
	uint64_t rsp;
	int count, socket_id, tail, cpuid;
	bool locked, completed, native_resume, jit_retry, irqs_disabled,
		jit_waiter, pinned_context, native_regs_decoded;
	struct kd_spin_jit_context *jit_context;
	struct pt_regs regs;
	struct kd_exec_frame *exec_frame;
	struct task_struct *task_struct_ptr;
	unsigned long gsbase;
	struct kd_spin_ref spin_origin;
};

struct shadow_stack;
static struct shadow_stack local_shadow_stack;
static struct kd_spin_node kd_spin_nodes[MAX_NODES];
static struct kd_spin_node *resume_node;
static int entries, exits, combined, checks, failures, handoffs;
static int initial_count, initial_depth;
static bool contended;
static struct qspinlock *active_lock;
static struct qspinlock scheduling_word;
static int origin_claims;
static bool nested_case;
static bool producer_case, producer_virtual, parent_ooo;
static bool producer_chain, producer_chain_virtual;
static int peer_result, poll_calls, relax_calls, try_calls, ticket_count;
static int begin_error, producer_preempt = 1, producer_count, producer_peak;
static struct kd_spin_node peer, follower;
static struct kd_spin_node *produced_node;
static struct kd_spin_node *producer_successor;
static struct kd_spin_jit_context producer_contexts[MAX_NODES];
static struct kd_spin_jit_context *kd_spin_jit_contexts = producer_contexts;
static struct kd_spin_native_input kd_spin_native_inputs;
static struct task_struct task = { .pid = 101 };
static struct task_struct logical_task = { .pid = 202 };
#define current (&task)
static const unsigned int kd_combiner_batch_size = 1024;

struct kd_exec_outer_unlock {
	int (*release)(void *frame, struct kd_exec_outer_unlock *hook);
	bool released;
};
struct kd_spin_batch;

#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define READ_ONCE(x) (x)
#define smp_load_acquire(p) (*(p))
#define WRITE_ONCE(x, v) ((x) = (v))
#define this_cpu_ptr(p) (p)
#define per_cpu_ptr(p, cpu) ((void)(cpu), (p))
#define unlikely(x) (x)
#define print_debug(...) ((void)0)
#define prefetchw(p) ((void)(p))
#define smp_rmb() ((void)0)
#define smp_mb() ((void)0)
#define numa_node_id() 0
#define IRQ_NUMA_NODE 255
#define _Q_LOCKED_VAL_HL 1
#define _Q_LOCKED_COMBINER_VAL 3
#define _Q_UNLOCKED_OOO_VAL 7
#define _Q_LOCKED_PENDING_MASK 0xffff
#define _Q_TAIL_MASK_HL 0xffff0000u
#define KD_SPIN_DIAG_SLOWPATH 0
#define KD_SPIN_ENTRY_VIRTUAL 1
#define PREEMPT_MASK 255
#define preempt_count() producer_preempt
#define smp_processor_id() 0
#define BUG_ON(x) CHECK(!(x))
#define in_task() true
#define irqs_disabled() false
#define module_param_named(...)
#define MODULE_PARM_DESC(...)
#define __percpu
#define alloc_percpu(type) node_record_alloc(sizeof(type))
#define free_percpu(ptr) node_record_free(ptr)
#define for_each_possible_cpu(cpu) for ((cpu) = 0; (cpu) < 1; (cpu)++)
#define pr_info(...) printf(__VA_ARGS__)
#define pr_err(...) fprintf(stderr, __VA_ARGS__)

static bool node_alloc_fail;
static int node_allocs, node_frees;

static void *node_record_alloc(size_t size)
{
	node_allocs++;
	return node_alloc_fail ? NULL : calloc(1, size);
}

static void node_record_free(void *ptr)
{
	if (ptr)
		node_frees++;
	free(ptr);
}

#define CHECK(x)                                                        \
	do {                                                            \
		checks++;                                               \
		if (!(x)) {                                             \
			fprintf(stderr, "FAIL depth=%d count=%d: %s\n", \
				initial_depth, initial_count, #x);      \
			failures++;                                     \
		}                                                       \
	} while (0)

/* A scripted peer only publishes completion; it cannot invoke a producer. */
static void kd_exec_remote_poll(void *frame)
{
	CHECK(producer_case && producer_virtual && produced_node);
	CHECK(frame == produced_node->jit_context->requester);
	CHECK(kd_spin_nodes[0].count == producer_count + 1);
	poll_calls++;
}
static void cpu_relax(void)
{
	if (!producer_case || ++relax_calls != 1)
		abort();
	if (!produced_node) /* Native full-pool direct-spin retry. */
		return;
	CHECK(kd_spin_nodes[0].count == producer_count + 1);
	produced_node->locked = false;
	produced_node->native_resume = peer_result == 5;
	produced_node->completed = peer_result != 5;
	if (producer_virtual)
		produced_node->jit_context->requester->remote_result =
			peer_result == 5 ? KD_EXEC_REMOTE_NATIVE :
					   KD_EXEC_REMOTE_DONE;
}
static struct qspinlock *kd_spin_word(struct qspinlock *lock)
{
	CHECK(lock == active_lock);
	return &scheduling_word;
}

static bool kd_spin_is_ooo(struct qspinlock *lock)
{
	(void)lock;
	return parent_ooo;
}

static void kd_spin_claim_origin(struct qspinlock *lock)
{
	CHECK(lock == active_lock && scheduling_word.locked);
	if (!lock->locked)
		origin_claims++;
	lock->locked = 1;
}

#define smp_cond_load_relaxed_sched(p, condition) \
	({                                        \
		typeof(*(p)) VAL = *(p);          \
		if (!(condition))                 \
			abort();                  \
		VAL;                              \
	})
#define atomic_cond_read_acquire(p, condition) \
	smp_cond_load_relaxed_sched(p, condition)
#define smp_store_release(p, value)                      \
	do {                                             \
		if (!producer_case) {                    \
			CHECK(active_lock->locked == 1); \
			handoffs++;                      \
		}                                        \
		*(p) = (value);                          \
	} while (0)

static int xchg_tail(struct qspinlock *lock, int tail)
{
	lock = kd_spin_word(lock);
	int old = lock->val;

	if (producer_case) {
		produced_node = &kd_spin_nodes[producer_count];
		CHECK(kd_spin_nodes[0].count == producer_count + 1);
		CHECK(produced_node->locked && !produced_node->completed);
		CHECK(!produced_node->next && produced_node->tail == tail);
		CHECK(produced_node->jit_waiter == producer_virtual);
		CHECK(produced_node->cpuid == 0 && produced_node->gsbase);
		CHECK(produced_node->task_struct_ptr ==
		      (producer_virtual ? &logical_task : current));
		if (kd_spin_nodes[0].count > producer_peak)
			producer_peak = kd_spin_nodes[0].count;
		if (contended)
			produced_node->next = producer_successor;
		/* The scripted prior owner releases S before the head can claim it. */
		lock->locked = 0;
		lock->pending = 0;
	}
	/* Publish a successor before the head's tail-clearing CAS. */
	lock->tail = (contended ? (producer_case ? 0x90000 : 0x20000) : tail) >>
		     16;
	return old;
}

static bool atomic_try_cmpxchg_relaxed(int *value, int *old, int replacement)
{
	if (*value != *old) {
		*old = *value;
		return false;
	}
	*value = replacement;
	return true;
}

static void set_locked(struct qspinlock *lock)
{
	lock = kd_spin_word(lock);
	lock->locked = 1;
}

static void check_and_set_combiner(struct qspinlock *lock)
{
	lock = kd_spin_word(lock);
	CHECK(!lock->locked && !lock->pending);
	lock->locked = 3;
}

static struct kd_spin_node *decode_tail(int tail)
{
	CHECK(producer_case && tail == 0x30000);
	return &peer;
}

static bool kd_spin_trylock(struct qspinlock *lock)
{
	CHECK(producer_case && !producer_virtual && lock == active_lock);
	CHECK(kd_spin_nodes[0].count == producer_count);
	if (++try_calls == 1)
		return false;
	CHECK(try_calls == 2);
	scheduling_word.val = 1;
	kd_spin_claim_origin(lock);
	return true;
}
static int encode_tail(int cpu, int index)
{
	CHECK(cpu == 0 && index >= 0 && index < MAX_NODES);
	return (index + 1) << 16;
}
static unsigned long kd_read_kernel_gsbase(void)
{
	return 0x12000;
}
static void kd_spin_diag_record(struct qspinlock *lock, int event,
				unsigned int depth)
{
	CHECK(lock == active_lock && event == KD_SPIN_DIAG_SLOWPATH);
	CHECK(depth == (unsigned int)initial_depth);
}
static bool kd_spin_entry_find(raw_spinlock_t *lock, struct kd_spin_ref *ref)
{
	CHECK(lock == active_lock);
	*ref = (struct kd_spin_ref){ lock, 1 };
	return true;
}
static int kd_spin_entry_begin(raw_spinlock_t *lock, int kind,
			       struct kd_spin_ref *ref)
{
	CHECK(lock == active_lock && kind == KD_SPIN_ENTRY_VIRTUAL);
	CHECK(!ref->entry && ticket_count >= 0);
	if (begin_error)
		return begin_error;
	ticket_count++;
	*ref = (struct kd_spin_ref){ lock, 1 };
	return 0;
}
static int kd_spin_entry_end(struct kd_spin_ref *ref)
{
	CHECK(ref->entry == active_lock && ticket_count > 0);
	ticket_count--;
	return 0;
}
static bool kd_exec_frame_validate(const struct kd_exec_frame *frame)
{
	return frame && frame->valid;
}
static unsigned int kd_exec_frame_lock_depth(const struct kd_exec_frame *frame)
{
	return frame->jit_lock_depth;
}
static bool kd_exec_frame_can_complete(const struct kd_exec_frame *frame)
{
	return frame->complete;
}
static bool kd_exec_frame_remote_pending(const struct kd_exec_frame *frame)
{
	return frame->remote_result == KD_EXEC_REMOTE_WAITING ||
	       frame->remote_result == KD_EXEC_REMOTE_NATIVE;
}
static int atomic_cmpxchg_acquire(int *value, int old, int replacement)
{
	int seen = *value;

	if (seen == old)
		*value = replacement;
	return seen;
}

static void kd_spin_diag_waiter_enter(struct qspinlock *lock)
{
	CHECK(lock == active_lock);
	entries++;
}

static void kd_spin_diag_waiter_exit(struct qspinlock *lock)
{
	CHECK(lock == active_lock);
	exits++;
}

static void kd_spin_set_resume_node(struct kd_spin_node *node)
{
	resume_node = node;
}

static void clear_locked_set_completed(struct kd_spin_node *node)
{
	node->locked = false;
	node->completed = true;
}

static void kd_spin_diag_validate_lock_stack(const struct shadow_stack *ptr);
static void run_combiner(struct qspinlock *lock, struct kd_spin_node *next);
static int execute_cs(struct qspinlock *lock, struct kd_spin_node *node,
		      struct kd_spin_batch *batch);
static int kd_spin_release_outer(void *frame, struct kd_exec_outer_unlock *hook)
{
	(void)frame;
	(void)hook;
	abort(); /* Early outer release is covered by spin_outer_progress_fixture. */
}
static void kd_spin_reclaim_outer(struct qspinlock *lock)
{
	(void)lock;
	abort();
}
static void kd_spin_debug_combiner(struct qspinlock *lock, unsigned int depth)
{
	CHECK(lock == active_lock);
	CHECK(depth == (unsigned int)initial_depth + 1);
}

#include "spin_node_observer.h"
#define kd_node_observations (*kd_node_records)
#include "spin_shadow_production.h"

static void kd_spin_diag_validate_lock_stack(const struct shadow_stack *ptr)
{
	bool empty = false;

	for (unsigned int i = 0; i < ARRAY_SIZE(ptr->lock_addr); i++) {
		if (ptr->lock_addr[i])
			CHECK(!empty);
		else
			empty = true;
	}
}

static void run_combiner(struct qspinlock *lock, struct kd_spin_node *next)
{
	combined++;
	CHECK(lock->val == 1 && origin_claims >= 1);
	CHECK(kd_spin_nodes[0].count == initial_count - 1);
	CHECK(kd_spin_lock_stack_depth(&local_shadow_stack) ==
	      initial_depth + 1);
	CHECK(local_shadow_stack.lock_addr[initial_depth] == (uintptr_t)lock);
	CHECK(local_shadow_stack.curr_cs_cpu == UINT32_MAX);
	CHECK(!local_shadow_stack.irqs_disabled);
#ifdef NUMA_AWARE
	CHECK(!local_shadow_stack.local_queue_head);
	CHECK(!local_shadow_stack.local_queue_tail);
#endif
	production_run_combiner(lock, next);
#ifdef NUMA_AWARE
	CHECK(!local_shadow_stack.local_queue_head);
	CHECK(!local_shadow_stack.local_queue_tail);
#endif
}

static void run_case(int depth, int count, bool queued, bool retry)
{
	struct qspinlock lock = { 0 };
	struct kd_spin_node next = { .locked = true };
	struct kd_spin_node *node = &kd_spin_nodes[count - 1];
	struct shadow_stack before;
	int ret;

	initial_depth = depth;
	initial_count = count;
	contended = queued;
	active_lock = &lock;
	memset(&scheduling_word, 0, sizeof(scheduling_word));
	origin_claims = 0;
	entries = exits = combined = handoffs = 0;
	resume_node = NULL;
	memset(kd_spin_nodes, 0, sizeof(kd_spin_nodes));
	memset(&local_shadow_stack, 0, sizeof(local_shadow_stack));
	kd_spin_nodes[0].count = count;
	node->next = &next;
	node->rsp = 0x12345678;
	node->jit_retry = retry;
	local_shadow_stack.curr_cs_cpu = 19;
	local_shadow_stack.prev_cs_cpu = UINT32_MAX;
	local_shadow_stack.irqs_disabled = 1;
	local_shadow_stack.ptr = &lock;
	local_shadow_stack.local_shadow_stack_ptr = 0x87654321;
#ifdef NUMA_AWARE
	local_shadow_stack.local_queue_head = &next;
	local_shadow_stack.local_queue_tail = node;
#endif
	for (int i = 0; i < depth; i++)
		local_shadow_stack.lock_addr[i] = 0x1000 + i * 8;
	before = local_shadow_stack;
	CHECK(kd_spin_nested_shadow_has_space() == (depth < 8));

	ret = __kd_spin_lock_longjmp(&lock, 0x10000, node);
	CHECK(ret == (retry ? 4 : (queued && depth < 8 ? 2 : 0)));
	CHECK(kd_spin_nodes[0].count == count - 1);
	CHECK(node->rsp == 0x12345678);
	CHECK(resume_node == node);
	CHECK(entries == 1 && exits == 1);
	CHECK(lock.val == 1 && origin_claims == 1);
	CHECK(scheduling_word.locked == 1 && scheduling_word.pending == 0);
	CHECK(scheduling_word.tail == (queued ? 2 : 0));
	CHECK(combined == (queued && depth < 8));
	CHECK(next.locked == !queued);
	CHECK(handoffs == (queued && depth == 8));
	/* Normal combiner execution deliberately resets its IRQ tracking. */
	if (queued && depth < 8)
		before.irqs_disabled = 0;
	CHECK(!memcmp(&local_shadow_stack, &before, sizeof(before)));
}

enum {
	NESTED_DEPTH = 8,
	REQUESTS = 3,
	MAX_FOLLOWERS = 3,
	QUEUE_NODES = REQUESTS * (MAX_FOLLOWERS + 1) + 1,
};

struct nested_level {
	struct qspinlock lock;
	struct kd_spin_node head, queue[QUEUE_NODES];
	unsigned int executions;
};

static struct nested_level levels[NESTED_DEPTH];
static int current_level, nested_depth, follower_count;
static int parent_result, leaf_result, leaf_reject_at;

static int rejection_result(int level)
{
	return level + 1 == nested_depth ? leaf_result : parent_result;
}

static int rejected_request(int level)
{
	return level + 1 == nested_depth ? leaf_reject_at : REQUESTS - 1;
}

static void run_level(int level);

static int execute_cs(struct qspinlock *lock, struct kd_spin_node *node,
		      struct kd_spin_batch *batch)
{
	struct nested_level *level = &levels[current_level];
	const int stride = follower_count + 1;
	int index = node - level->queue;
	int request = index / stride;

	CHECK(nested_case && lock == &level->lock && lock == active_lock);
	CHECK(index >= 0 && index < REQUESTS * stride);
	CHECK(scheduling_word.locked == _Q_LOCKED_COMBINER_VAL);
	CHECK(!node->completed && node->locked && !batch->outer.released);
	CHECK(kd_spin_nodes[0].count == 0);
	level->executions++;
#ifdef NUMA_AWARE
	CHECK(index % stride == 0);
	CHECK(batch->next == &level->queue[(request + 1) * stride]);
	CHECK(local_shadow_stack.local_queue_head == &level->queue[1]);
	CHECK(local_shadow_stack.local_queue_tail ==
	      &level->queue[request * stride + follower_count]);
#else
	CHECK(batch->next == node->next);
#endif
	if (index % stride)
		return 0;
	if (rejection_result(current_level) &&
	    request == rejected_request(current_level))
		return rejection_result(current_level);

	if (request == 1 && current_level + 1 < nested_depth) {
		struct kd_spin_node before[QUEUE_NODES];
		struct shadow_stack shadow_before = local_shadow_stack;

		/* Request 0 committed the first group. The scan for request 1
		 * appended a second group before this child combiner entry. */
		memcpy(before, level->queue, sizeof(before));
#ifdef NUMA_AWARE
		CHECK(level->queue[stride - 1].next ==
		      &level->queue[stride + 1]);
#endif
		run_level(current_level + 1);
		CHECK(lock == active_lock && lock->locked == 1);
		CHECK(!memcmp(before, level->queue, sizeof(before)));
		CHECK(!memcmp(&shadow_before, &local_shadow_stack,
			      sizeof(shadow_before)));
	}
	return 0;
}

static void check_level_queue(int number)
{
	struct nested_level *level = &levels[number];
	const int stride = follower_count + 1;
	const int last = REQUESTS * stride;
	const bool rejected = rejection_result(number) != 0;
	const int committed = rejected ? rejected_request(number) : REQUESTS;
	const int rejected_index = committed * stride;
	int published = rejected_index;
	unsigned int executions = rejected_index + rejected;

#ifdef NUMA_AWARE
	published = committed ? 1 : 0;
	executions = committed + rejected;
#endif
	CHECK(level->executions == executions);
	for (int i = 0; i <= last; i++) {
		struct kd_spin_node *node = &level->queue[i];
		struct kd_spin_node *next = i == last ? NULL : node + 1;
		bool completed = i < rejected_index;

#ifdef NUMA_AWARE
		completed = completed && i % stride == 0;
		if (i < rejected_index && i % stride == follower_count) {
			int group = i / stride;

			next = &level->queue[group + 1 < committed ?
						     (group + 1) * stride + 1 :
						     rejected_index];
		}
#endif
		CHECK(node->next == next);
		CHECK(node->completed == completed);
		CHECK(node->locked == (!completed && i != published));
	}
	/* Walk only the published chain: every uncompleted node occurs once,
	 * and rejected requests precede their still-speculative followers. */
	struct kd_spin_node *node = &level->queue[published];
	bool seen[QUEUE_NODES] = { false };
	int visited = 0;

	while (node && visited <= last) {
		int index = node - level->queue;

		CHECK(index >= 0 && index <= last);
		if (index < 0 || index > last)
			break;
		CHECK(!seen[index] && !node->completed);
		seen[index] = true;
		visited++;
		node = node->next;
	}
	CHECK(!node);
	for (int i = 0; i <= last; i++)
		CHECK(seen[i] == !level->queue[i].completed);
}

static void run_level(int number)
{
	struct nested_level *level = &levels[number];
	struct shadow_stack before = local_shadow_stack;
	struct qspinlock saved_word = scheduling_word;
	struct qspinlock *saved_lock = active_lock;
	const int saved_depth = initial_depth, saved_count = initial_count;
	const int saved_level = current_level;
	const uint64_t rsp = 0x10000 + number * 0x100;
	struct kd_spin_native_input saved_input = kd_spin_native_inputs;
	struct kd_spin_node *saved_successor = producer_successor;

	current_level = initial_depth = number;
	initial_count = 1;
	active_lock = &level->lock;
	memset(&scheduling_word, 0, sizeof(scheduling_word));
	CHECK(kd_spin_nodes[0].count == 0);
	if (producer_chain) {
		struct kd_exec_frame parent = {
			.valid = true,
			.jit_lock_depth = 1,
			.logical_task = &logical_task,
			.gsbase = 0x34000,
		};
		struct pt_regs regs = { .ip = 0x1000, .sp = rsp };
		struct kd_spin_ref ref = { &level->lock, 1 };
		int tickets_before = ticket_count;

		producer_case = true;
		producer_virtual = producer_chain_virtual;
		producer_count = 0;
		producer_successor = &level->queue[0];
		kd_spin_native_inputs.rsp = rsp;
		kd_spin_native_inputs.regs_sp = rsp + 64;
		if (producer_chain_virtual) {
			scheduling_word.locked = 1;
			CHECK(kd_spin_nested_lock(&level->lock, &regs,
						  &parent) ==
			      KD_SPIN_NESTED_ACQUIRED_QUEUE);
			CHECK(parent.control_call.phase == KD_CALL_ACQUIRED);
			CHECK(ticket_count == tickets_before + 1);
			CHECK(kd_spin_entry_end(&ref) == 0);
		} else {
			CHECK(__kd_spin_lock_slowpath(&level->lock) == 2);
		}
		CHECK(ticket_count == tickets_before);
		CHECK(kd_spin_nodes[0].count == 0 &&
		      resume_node == &kd_spin_nodes[0]);
		/* Child producers may reuse all metadata except the saved parent RSP. */
		CHECK(kd_spin_nodes[0].rsp == rsp && producer_peak == 1);
	} else {
		kd_spin_nodes[0].count = 1;
		level->head.next = &level->queue[0];
		level->head.rsp = rsp;
		CHECK(__kd_spin_lock_longjmp(&level->lock, 0x10000,
					     &level->head) == 2);
		CHECK(kd_spin_nodes[0].count == 0 &&
		      resume_node == &level->head);
		CHECK(level->head.rsp == rsp &&
		      level->head.next == &level->queue[0]);
	}
	CHECK(level->lock.val == 1 && scheduling_word.locked == 1);
	CHECK(scheduling_word.tail == (producer_chain ? 9 : 2) &&
	      scheduling_word.pending == 0);
	before.irqs_disabled = false;
	CHECK(!memcmp(&local_shadow_stack, &before, sizeof(before)));
	check_level_queue(number);
	/* Model the caller's eventual unlock, not the native release protocol. */
	level->lock.locked = 0;
	scheduling_word = saved_word;
	active_lock = saved_lock;
	initial_depth = saved_depth;
	initial_count = saved_count;
	current_level = saved_level;
	kd_spin_native_inputs = saved_input;
	producer_successor = saved_successor;
}

static void run_nested_case(int depth, int followers, int parent, int leaf,
			    int reject_at)
{
	const int last = REQUESTS * (followers + 1);

	nested_case = contended = true;
	nested_depth = depth;
	follower_count = followers;
	parent_result = parent;
	leaf_result = leaf;
	leaf_reject_at = reject_at;
	memset(levels, 0, sizeof(levels));
	memset(kd_spin_nodes, 0, sizeof(kd_spin_nodes));
	memset(&local_shadow_stack, 0, sizeof(local_shadow_stack));
	memset(&scheduling_word, 0, sizeof(scheduling_word));
	memset(&kd_node_observations, 0, sizeof(kd_node_observations));
	active_lock = NULL;
	current_level = 0;
	entries = exits = combined = handoffs = origin_claims = 0;
	local_shadow_stack.curr_cs_cpu = 19;
	local_shadow_stack.prev_cs_cpu = UINT32_MAX;
	local_shadow_stack.local_shadow_stack_ptr = 0x87654321;
	local_shadow_stack.irqs_disabled = true;
	for (int level = 0; level < depth; level++) {
		for (int i = 0; i <= last; i++) {
			struct kd_spin_node *node = &levels[level].queue[i];

			node->next = i == last ? NULL : node + 1;
			node->locked = true;
			node->rsp = 0x20000 + level * 0x100 + i;
			node->socket_id = i % (followers + 1) ? 1 : 0;
		}
	}
	run_level(0);
	CHECK(entries == depth && exits == depth && combined == depth);
	CHECK(origin_claims == depth && handoffs == 0);
	CHECK(kd_spin_lock_stack_depth(&local_shadow_stack) == 0);
	CHECK(local_shadow_stack.curr_cs_cpu == 19);
	CHECK(kd_spin_nodes[0].count == 0);
	for (int level = 0; level < depth; level++)
		CHECK(!levels[level].lock.locked);
	nested_case = false;
	producer_case = false;
}

#include "spin_node_pool_fixture.c"

int main(void)
{
	const int depths[] = { 0, 7, 8 };
	const int results[] = { 0, KD_EXE_NO_RUN, KD_EXE_RUN_ERROR };

	kd_node_trace = true;
	if (kd_spin_selftest_nodes_init())
		return 2;
	kd_node_trace = false;
	/* Refusal mutations must not recurse with an intentionally corrupt count. */
	if (getenv("KD_NODE_MUTATION")) {
		run_producer_cases(false);
		kd_spin_selftest_nodes_free();
		return failures ? 1 : 0;
	}
	for (unsigned int i = 0; i < ARRAY_SIZE(depths); i++)
		for (int count = 1; count <= 4; count++)
			for (int queued = 0; queued <= 1; queued++)
				for (int retry = 0; retry <= 1; retry++)
					run_case(depths[i], count, queued,
						 retry);
	printf("spin shadow: 48 queue-head cases, %d checks, %d failures\n",
	       checks, failures);
	int previous_checks = checks, previous_failures = failures, cases = 0;

	for (int depth = 2; depth <= NESTED_DEPTH; depth++)
		for (int followers = 1; followers <= MAX_FOLLOWERS; followers++)
			for (unsigned int parent = 0;
			     parent < ARRAY_SIZE(results); parent++)
				for (unsigned int leaf = 0;
				     leaf < ARRAY_SIZE(results); leaf++)
					for (int reject = 0; reject < REQUESTS;
					     reject++) {
						/* Successful leaves have no rejection site. */
						if (!results[leaf] && reject)
							continue;
						run_nested_case(depth,
								followers,
								results[parent],
								results[leaf],
								reject);
						cases++;
					}
	printf("spin nested lists: %d cases, %d checks, %d failures\n", cases,
	       checks - previous_checks, failures - previous_failures);
	run_producer_cases(true);
	kd_node_trace = true;
	run_producer_cases(true);
	run_observer_checks();
	kd_spin_selftest_nodes_report();
	run_observer_allocation_checks();
	return failures ? 1 : 0;
}
