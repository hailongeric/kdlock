/* Deterministic primitives around the extracted production queue-head exit. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <setjmp.h>
#include <stddef.h>

#include "spin_shadow_types.h"

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;

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
	unsigned long ip, sp, di, bx, r12, r13, r14, r15, bp;
};
struct task_struct {
	int pid;
};
struct kd_spin_ref {
	void *entry;
	unsigned long sequence;
};
#include "spin_request_type.h"
struct kd_exec_frame {
 unsigned char role;
	struct pt_regs regs, *regs_ref;
	unsigned long entry_ip, delegated_lock_addr, outer_lock_addr;
	unsigned int entry_abi, packet_state;
	struct kd_exec_outer_unlock *outer_unlock_hook;
	bool request_frame;
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

typedef int atomic_t;
struct kd_spin_diag_slot;
struct kd_spin_jit_context {
	struct kd_exec_frame *requester;
	unsigned int lock_depth;
};
struct kd_spin_exec_request {
	struct kd_spin_diag_slot *diag;
	struct kd_exec_frame frame;
	struct kd_spin_exec_request *packet_owner;
	atomic_t users;
	/* Request-owned return/routing state survives recycling of the node. */
	unsigned long irq_flags;
	bool jit_waiter;
	bool jit_retry;
	bool native_resume;
	bool pinned_context;
	bool native_regs_decoded;
	struct kd_spin_jit_context jit_context;
	u64 queued_at_ns;
};
#define KD_SPIN_REQUEST_SLOTS 12
static struct kd_spin_exec_request request_pool[KD_SPIN_REQUEST_SLOTS];
static struct kd_spin_exec_request *kd_spin_requests = request_pool;
#define atomic_read_acquire(p) (*(p))
#define atomic_set(p,v) (*(p) = (v))
#define atomic_inc(p) (++*(p))
#define atomic_dec(p) (--*(p))
#define atomic_dec_and_test(p) (--*(p) == 0)
#define container_of(p,t,m) ((t *)((char *)(p) - offsetof(t,m)))
static bool kd_source_frame_get(void) { return true; }
static void kd_source_frame_put(void) { }
static struct pt_regs *kd_exec_frame_regs(struct kd_exec_frame *frame)
{ return frame->regs_ref ? frame->regs_ref : &frame->regs; }
static void kd_exec_frame_prepare(struct kd_exec_frame *frame, unsigned long ip,
	unsigned long lock, unsigned long gs, struct task_struct *task)
{
	(void)lock;
	frame->entry_ip = ip;
	frame->gsbase = gs;
	frame->logical_task = task;
	frame->regs_ref = &frame->regs;
	frame->outer_lock_addr = lock;
	frame->request_frame = true;
	frame->entry_abi = KD_ENTRY_ABI_LEGACY;
	frame->packet_state = KD_PACKET_FULL;
}
static void kd_exec_frame_prepare_complex(struct kd_exec_frame *frame) { (void)frame; }
struct kd_spin_node {
	struct kd_spin_node *next;
	int socket_id;
	int cpuid;
	/* Scheduler stack sentinel, not the logical register packet. */
	uint64_t rsp;
	/* Queue notification only; execution completion belongs to frame.state. */
	union {
		struct { u8 completed; u8 locked; };
		struct { u16 locked_completed; };
	};
	struct kd_spin_exec_request *execution;
};


static struct kd_spin_exec_request *fixture_request(struct kd_spin_node *node)
{
	if (!node->execution)
		node->execution = calloc(1, sizeof(*node->execution));
	return node->execution;
}

/* This queue/node fixture runs with optional timing disabled. The production
 * timer and enabled dispatch endpoints are covered by the executor/outer units. */
static u64 kd_exe_queue_timing_start(void)
{
	return 0;
}
static void kd_exe_queue_timing_end(bool mutex, uint64_t *queued_at, u64 end)
{
	(void)mutex;
	(void)queued_at;
	(void)end;
}

struct kd_spin_cpu_state;
static struct kd_spin_cpu_state kd_spin_cpu;
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
static bool mailbox_case;
static int mailbox_token;
static int peer_result, poll_calls, relax_calls, try_calls, ticket_count;
static int begin_error, producer_preempt = 1, producer_count, producer_peak;
static struct kd_spin_node peer, follower;
static struct kd_spin_node *produced_node;
static struct kd_spin_node *producer_successor;
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
#define local_irq_save(flags) ((flags) = 0)
#define local_irq_restore(flags) ((void)(flags))
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
	CHECK(frame == fixture_request(produced_node)->jit_context.requester);
	CHECK(kd_spin_cpu.node_count == producer_count + 1);
	CHECK(mailbox_case && fixture_request(produced_node)->jit_context.requester->remote_request ==
	      &mailbox_token);
	fixture_request(produced_node)->jit_context.requester->remote_request = NULL;
	poll_calls++;
}
static void cpu_relax(void)
{
	if (!producer_case)
		abort();
	relax_calls++;
	if (mailbox_case && relax_calls < 3) {
		struct kd_exec_frame *parent = fixture_request(produced_node)->jit_context.requester;

		if (relax_calls == 1) {
			CHECK(!poll_calls);
			parent->remote_request = &mailbox_token;
		} else {
			CHECK(poll_calls == 1 && !parent->remote_request);
		}
		return;
	}
	CHECK(relax_calls == (mailbox_case ? 3 : 1));
	if (!produced_node) /* Native full-pool direct-spin retry. */
		return;
	CHECK(kd_spin_cpu.node_count == producer_count + 1);
	produced_node->locked = false;
	fixture_request(produced_node)->native_resume = peer_result == 5;
	produced_node->completed = peer_result != 5;
	if (producer_virtual)
		fixture_request(produced_node)->jit_context.requester->remote_result =
			peer_result == 5 ? KD_EXEC_REMOTE_NATIVE :
					   KD_EXEC_REMOTE_DONE;
}
static struct qspinlock *kd_spin_request_word(const struct kd_spin_ref *ref)
{
	CHECK(ref->entry == active_lock);
	return &scheduling_word;
}

static bool kd_spin_is_ooo(struct qspinlock *lock)
{
	(void)lock;
	return parent_ooo;
}

static void kd_spin_claim_origin(const struct kd_spin_request *request)
{
	struct qspinlock *lock = active_lock;
	CHECK(request->word == &scheduling_word && scheduling_word.locked);
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
/* The handoff counter belongs to the queue-head capacity fallback. Ordinary
 * combiner publication now uses release too, but is not that refusal event;
 * spin_outer_progress_fixture checks its packet/reuse boundary separately. */
#define smp_store_release(p, value)                                      \
	do {                                                           \
		if (!producer_case) {                                  \
			CHECK(active_lock->locked == 1);               \
			if (!strcmp(__func__, "__kd_spin_lock_longjmp")) \
				handoffs++;                           \
		}                                                      \
		*(p) = (value);                                        \
	} while (0)

static int xchg_tail(struct qspinlock *lock, int tail)
{
	CHECK(lock == &scheduling_word);
	int old = lock->val;

	if (producer_case) {
		produced_node = &kd_spin_nodes[producer_count];
		CHECK(kd_spin_cpu.node_count == producer_count + 1);
		CHECK(produced_node->locked && !produced_node->completed);
		CHECK(!produced_node->next && tail == ((producer_count + 1) << 16));
		CHECK(fixture_request(produced_node)->jit_waiter == producer_virtual);
		CHECK(produced_node->cpuid == 0 && fixture_request(produced_node)->frame.gsbase);
		CHECK(fixture_request(produced_node)->frame.logical_task ==
		      (producer_virtual ? &logical_task : current));
		/* Observe readiness at queue publication, before any peer can run JIT. */
		if (!producer_virtual) {
			CHECK(fixture_request(produced_node)->native_regs_decoded);
			CHECK(fixture_request(produced_node)->frame.regs_ref->bx == 1 && fixture_request(produced_node)->frame.regs_ref->r12 == 2 &&
			      fixture_request(produced_node)->frame.regs_ref->r13 == 3 && fixture_request(produced_node)->frame.regs_ref->r14 == 4 &&
			      fixture_request(produced_node)->frame.regs_ref->r15 == 5 && fixture_request(produced_node)->frame.regs_ref->bp == 6);
		}
		if (kd_spin_cpu.node_count > producer_peak)
			producer_peak = kd_spin_cpu.node_count;
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
	CHECK(lock == &scheduling_word);
	lock->locked = 1;
}

static void check_and_set_combiner(struct qspinlock *lock)
{
	CHECK(lock == &scheduling_word);
	CHECK(!lock->locked && !lock->pending);
	lock->locked = 3;
}

/* The fixture's synthetic 2/9 tail codes refer to the last linked node;
 * code 3 retains the existing producer-predecessor meaning. */
static struct kd_spin_node *mock_tail_node;
static struct kd_spin_node *decode_tail(int tail)
{
	if (tail != 0x30000) {
		CHECK((tail == 0x20000 || tail == 0x90000) && mock_tail_node);
		return mock_tail_node;
	}
	CHECK(producer_case && tail == 0x30000);
	return &peer;
}

static bool kd_spin_trylock(struct qspinlock *lock)
{
	CHECK(producer_case && !producer_virtual && lock == &scheduling_word);
	CHECK(kd_spin_cpu.node_count == producer_count);
	if (++try_calls == 1)
		return false;
	CHECK(try_calls == 2);
	scheduling_word.val = 1;
	struct kd_spin_request request = { .word = lock };
	kd_spin_claim_origin(&request);
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

static struct kd_spin_diag_slot *kd_spin_diag_waiter_enter(struct qspinlock *lock)
{
	CHECK(lock == active_lock);
	entries++;
	return (void *)lock;
}

static void kd_spin_diag_waiter_exit(struct kd_spin_diag_slot *slot)
{
	CHECK((void *)slot == active_lock);
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

static void kd_spin_diag_validate_lock_stack(const struct kd_spin_cpu_state *ptr);
static void run_combiner(struct qspinlock *lock, struct kd_spin_node *next,
			 struct kd_spin_request *request);
static int execute_cs(struct qspinlock *lock, struct kd_spin_node *node,
		      struct kd_spin_batch *batch);
/* Address/bounds semantics use real layouts in spin_batch_fixture. */
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
static int kd_exec_frame_retire_single_spin(struct kd_exec_frame *frame)
{ (void)frame; abort(); }

static void kd_spin_jit_prepare_complex(struct kd_exec_frame *frame)
{ (void)frame; abort(); }
static void kd_spin_debug_jit_success(struct kd_spin_diag_slot *lock, unsigned int depth)
{ (void)lock; (void)depth; abort(); }

/* Real hint preparation/bounds and protected-page checks live in the
 * batch fixture; this queue fixture retains only its publication interface. */
static void kd_spin_prepare_prefetch(struct kd_spin_node *node,
                                     struct pt_regs *regs)
{ (void)node; (void)regs; }

static void kd_spin_prefetch_request(struct kd_spin_node *node)
{
	(void)node;
}
static int kd_spin_release_outer(void *frame, struct kd_exec_outer_unlock *hook)
{
	(void)frame;
	(void)hook;
	abort(); /* Early outer release is covered by spin_outer_progress_fixture. */
}
static void kd_spin_reclaim_outer(struct kd_spin_request *request)
{
	(void)request;
	abort();
}
static struct kd_spin_diag_slot *kd_spin_diag_find(unsigned long lock)
{ return (void *)lock; }
static void kd_spin_debug_combiner(struct kd_spin_diag_slot *lock, unsigned int depth)
{
	CHECK((void *)lock == active_lock);
	CHECK(depth == (unsigned int)initial_depth + 1);
}

#include "spin_node_observer.h"
#define kd_node_observations (*kd_node_records)
/* Physical completion no longer returns through the production queue frame.
 * Model only that transfer here; test_spin_wait executes the real assembly
 * against destructively overwritten C frames. */
static jmp_buf *native_return;
static void kd_spin_request_put(struct kd_spin_exec_request *request);
static void kd_spin_publish_wait(struct kd_spin_node *node,
				 struct kd_spin_node *previous, void *wait_stack_top)
{
	(void)wait_stack_top;
	previous->next = node;
	while (node->locked)
		cpu_relax();
	if (node->completed || fixture_request(node)->native_resume) {
		kd_spin_cpu.node_count--;
		kd_spin_selftest_node_event(fixture_request(node)->native_resume ?
			KD_NODE_NATIVE_RETURN : KD_NODE_REMOTE_RETURN);
		kd_spin_diag_waiter_exit(fixture_request(node)->diag);
		kd_spin_set_resume_node(node);
		CHECK(native_return != NULL);
		if (node->execution)
			kd_spin_request_put(node->execution);
		longjmp(*native_return, fixture_request(node)->native_resume ? 5 : 3);
	}
}
#include "spin_shadow_production.h"

static int test_longjmp(struct qspinlock *lock, int tail, struct kd_spin_node *node)
{
	struct kd_spin_request request = { .word = &scheduling_word };
	(void)fixture_request(node);
	CHECK(kd_spin_entry_find(lock, &request.ref));
	jmp_buf continuation;
	jmp_buf *saved = native_return;
	int ret = setjmp(continuation);

	native_return = &continuation;
	if (!ret)
		ret = __kd_spin_lock_longjmp(lock, tail, node, &request);
	native_return = saved;
	return ret;
}
static int test_slowpath(struct qspinlock *lock)
{
	struct kd_spin_request request = { .word = &scheduling_word };
	CHECK(kd_spin_entry_find(lock, &request.ref));
	jmp_buf continuation;
	jmp_buf *saved = native_return;
	int ret = setjmp(continuation);

	native_return = &continuation;
	if (!ret)
		ret = __kd_spin_lock_slowpath(lock, &request, &kd_spin_native_inputs);
	native_return = saved;
	return ret;
}
#define __kd_spin_lock_longjmp test_longjmp
#define __kd_spin_lock_slowpath test_slowpath


static void kd_spin_diag_validate_lock_stack(const struct kd_spin_cpu_state *ptr)
{
	bool empty = false;

	for (unsigned int i = 0; i < ARRAY_SIZE(ptr->lock_addr); i++) {
		if (ptr->lock_addr[i])
			CHECK(!empty);
		else
			empty = true;
	}
}

static void run_combiner(struct qspinlock *lock, struct kd_spin_node *next,
			 struct kd_spin_request *request)
{
	combined++;
	CHECK(lock->val == 1 && origin_claims >= 1);
	CHECK(kd_spin_cpu.node_count == initial_count - 1);
	CHECK(kd_spin_lock_stack_depth(&kd_spin_cpu) ==
	      initial_depth + 1);
	CHECK(kd_spin_cpu.lock_addr[initial_depth] == (uintptr_t)lock);
	CHECK(kd_spin_cpu.curr_cs_cpu == UINT32_MAX);
#ifdef NUMA_AWARE
	CHECK(!kd_spin_cpu.local_queue_head);
	CHECK(!kd_spin_cpu.local_queue_tail);
#endif
	struct kd_spin_node *saved_tail_node = mock_tail_node;
	mock_tail_node = next;
	while (mock_tail_node->next)
		mock_tail_node = mock_tail_node->next;
	production_run_combiner(lock, next, request);
	mock_tail_node = saved_tail_node;
#ifdef NUMA_AWARE
	CHECK(!kd_spin_cpu.local_queue_head);
	CHECK(!kd_spin_cpu.local_queue_tail);
#endif
}

static void run_case(int depth, int count, bool queued, bool retry)
{
	struct qspinlock lock = { 0 };
	struct kd_spin_node next = { .locked = true };
	struct kd_spin_node *node = &kd_spin_nodes[count - 1];
	struct kd_spin_cpu_state before;
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
	memset(&kd_spin_cpu, 0, sizeof(kd_spin_cpu));
	kd_spin_cpu.node_count = count;
	(void)fixture_request(node);
	(void)fixture_request(&next);
	node->next = &next;
	node->rsp = 0x12345678;
	fixture_request(node)->jit_retry = retry;
	kd_spin_cpu.curr_cs_cpu = 19;
#ifdef NUMA_AWARE
	kd_spin_cpu.local_queue_head = &next;
	kd_spin_cpu.local_queue_tail = node;
#endif
	for (int i = 0; i < depth; i++)
		kd_spin_cpu.lock_addr[i] = 0x1000 + i * 8;
	before = kd_spin_cpu;
	CHECK(kd_spin_nested_shadow_has_space() == (depth < 8));

	ret = __kd_spin_lock_longjmp(&lock, 0x10000, node);
	CHECK(ret == (retry ? 4 : (queued && depth < 8 ? 2 : 0)));
	CHECK(kd_spin_cpu.node_count == count - 1);
	CHECK(node->rsp == 0x12345678);
	CHECK(resume_node == node);
	CHECK(entries == 1 && exits == 1);
	CHECK(lock.val == 1 && origin_claims == 1);
	CHECK(scheduling_word.locked == 1 && scheduling_word.pending == 0);
	CHECK(scheduling_word.tail == (queued ? 2 : 0));
	CHECK(combined == (queued && depth < 8));
	CHECK(next.locked == !queued);
	CHECK(handoffs == (queued && depth == 8));
	/* The reservation count is CPU metadata and must retire exactly once. */
	before.node_count--;
	CHECK(!memcmp(&kd_spin_cpu, &before, sizeof(before)));
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
	CHECK(kd_spin_cpu.node_count == 0);
	level->executions++;
#ifdef NUMA_AWARE
	CHECK(index % stride == 0);
	CHECK(batch->next == &level->queue[(request + 1) * stride]);
	CHECK(kd_spin_cpu.local_queue_head == &level->queue[1]);
	CHECK(kd_spin_cpu.local_queue_tail ==
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
		struct kd_spin_cpu_state shadow_before = kd_spin_cpu;

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
		CHECK(!memcmp(&shadow_before, &kd_spin_cpu,
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
	struct kd_spin_cpu_state before = kd_spin_cpu;
	struct qspinlock saved_word = scheduling_word;
	struct qspinlock *saved_lock = active_lock;
	const int saved_depth = initial_depth, saved_count = initial_count;
	const int saved_level = current_level;
	const uint64_t rsp = 0x10000 + number * 0x100;
	unsigned long saved[8] = {0, 1, 2, 3, 4, 5, 6, 0x800};
	struct kd_spin_native_input saved_input = kd_spin_native_inputs;
	struct kd_spin_node *saved_successor = producer_successor;

	current_level = initial_depth = number;
	initial_count = 1;
	active_lock = &level->lock;
	memset(&scheduling_word, 0, sizeof(scheduling_word));
	CHECK(kd_spin_cpu.node_count == 0);
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
		kd_spin_native_inputs.regs_sp = (unsigned long)saved;
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
		CHECK(kd_spin_cpu.node_count == 0 &&
		      resume_node == &kd_spin_nodes[0]);
		/* Child producers may reuse all metadata except the saved parent RSP. */
		CHECK(kd_spin_nodes[0].rsp == rsp && producer_peak == 1);
	} else {
		kd_spin_cpu.node_count = 1;
		level->head.next = &level->queue[0];
		level->head.rsp = rsp;
		CHECK(__kd_spin_lock_longjmp(&level->lock, 0x10000,
					     &level->head) == 2);
		CHECK(kd_spin_cpu.node_count == 0 &&
		      resume_node == &level->head);
		CHECK(level->head.rsp == rsp &&
		      level->head.next == &level->queue[0]);
	}
	CHECK(level->lock.val == 1 && scheduling_word.locked == 1);
	CHECK(scheduling_word.tail == (producer_chain ? 9 : 2) &&
	      scheduling_word.pending == 0);
	CHECK(!memcmp(&kd_spin_cpu, &before, sizeof(before)));
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
	memset(&kd_spin_cpu, 0, sizeof(kd_spin_cpu));
	memset(&scheduling_word, 0, sizeof(scheduling_word));
	memset(&kd_node_observations, 0, sizeof(kd_node_observations));
	active_lock = NULL;
	current_level = 0;
	entries = exits = combined = handoffs = origin_claims = 0;
	kd_spin_cpu.curr_cs_cpu = 19;
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
	CHECK(kd_spin_lock_stack_depth(&kd_spin_cpu) == 0);
	CHECK(kd_spin_cpu.curr_cs_cpu == 19);
	CHECK(kd_spin_cpu.node_count == 0);
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
	run_mailbox_cases();
	kd_node_trace = true;
	run_producer_cases(true);
	run_observer_checks();
	kd_spin_selftest_nodes_report();
	run_observer_allocation_checks();
	return failures ? 1 : 0;
}
