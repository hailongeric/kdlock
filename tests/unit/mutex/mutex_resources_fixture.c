/* SPDX-License-Identifier: GPL-2.0 */
/* Join real mutex resource decisions without executing a kernel stack switch.
 * CPU scheduling, task allocation, physical locks and peers are substitutes.
 */
#include <errno.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "exe_info.h"

typedef struct { unsigned long opaque[3]; } wait_queue_head_t;
struct rcuwait { void *task; };
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef struct {
	int counter;
} atomic_t;
struct task_struct {
	int pid;
	char comm[16];
};
struct mutex {
	struct task_struct *owner;
};
#include "mutex_resource_types.h"

static struct task_struct waiter = { .pid = 1 }, peer = { .pid = 2 };
static struct task_struct *current = &waiter;
static const char *target_process = "target";
static unsigned int checks, errors, preempt, migration, table_irq;
static unsigned int gets, task_puts, refs, adds, acquires, releases, schedules;
static unsigned int slow_calls, notify_calls, samples, mode;
static unsigned int native_waits;
static unsigned long kd_mutex_multi_slot_count, kd_mutex_frame_failure_count;
static unsigned long kd_mutex_node_overflow_count, kd_mutex_jit_resume_count;
static unsigned long kd_mutex_origin_acquires, kd_mutex_origin_releases;
static int kd_mutex_reserved_nodes;
static bool promoted, task_failure, active_override, borrowed;
static bool cpu_hot = true, trace_admission, sampled_first;
static unsigned int comm_queries, table_lock_entries;
/* Inject one competing get after a reader observes a hole, before its
 * insertion lock is acquired. This is a deterministic interleaving, not a
 * replacement for live concurrent publication and owner/ACK validation. */
static void (*shadow_before_lock)(void);
static struct mutex *shadow_racing_origin;
static struct kd_mutex *shadow_racing_entry;
static struct kd_mutex shadow_racing_snapshot;
static bool schedule_wanted, recycle_on_enable, direct_packet;
static bool source_open, native_owner_wait;
/* Most resource cases substitute a failed first CAS followed by a racing
 * release. The native-first case below substitutes a successful acquisition. */
static bool fast_available;
static unsigned int entry_attempts, entry_pins, fast_probes;
static struct kd_mutex *waiting_gate, *release_gate;
static struct kd_mutex_node *recycle_node, *poll_node;
static unsigned int polls;
static struct kd_regs expected_regs, captured_regs;
static unsigned long native_stack[32];
static jmp_buf resume_target;

/* Stop on the first observed invariant violation, before a broken mutant can
 * send an invalid pointer to a substitute primitive. BUG-only exits stay distinct. */
#define CHECK(c)                                                             \
	do {                                                                 \
		checks++;                                                    \
		if (!(c)) {                                                  \
			fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); \
			exit(1);                                             \
		}                                                            \
	} while (0)
#define BUG()                                               \
	do {                                                \
		fprintf(stderr, "BUG line %d\n", __LINE__); \
		exit(2);                                    \
	} while (0)
#define BUG_ON(c)              \
	do {                   \
		if (c)         \
			BUG(); \
	} while (0)
#define TASK_COMM_LEN 16
#define BUILD_BUG_ON(c) _Static_assert(!(c), "kernel build contract")
#define likely(c) (c)
#define unlikely(c) (c)
#define READ_ONCE(v) (v)
#define WRITE_ONCE(v, value) ((v) = (value))
#define smp_load_acquire(p) (*(p))
#define smp_store_release(p, v) (*(p) = (v))
#define atomic_set(p, v) ((p)->counter = (v))
#define atomic_inc(p) (++(p)->counter)
#define atomic_dec(p) (--(p)->counter)
#define this_cpu_inc(x) (++(x))
#define this_cpu_dec_return(x) (--(x))
#define atomic64_inc(p) (++*(p))
#define BIT(n) (1UL << (n))
#define DEFINE_PER_CPU_SHARED_ALIGNED(type, name) type name __attribute__((unused))
#define this_cpu_ptr(p) (p)
#define per_cpu_ptr(p, cpu) tail_node_for_cpu(p, cpu)
#define DEFINE_RAW_SPINLOCK(name) int name
#define raw_spin_lock_irqsave(p, flags)     \
	do {                                \
		if (shadow_before_lock) {   \
			void (*publish)(void) = shadow_before_lock; \
			shadow_before_lock = NULL; \
			publish();          \
		}                          \
		CHECK(!*(p) && !table_irq); \
		*(p) = 1;                   \
		table_irq++;                \
		table_lock_entries++;       \
		(flags) = 0;                \
	} while (0)
#define raw_spin_unlock_irqrestore(p, flags)                    \
	do {                                                    \
		CHECK(*(p) == 1 && table_irq == 1 && !(flags)); \
		*(p) = 0;                                       \
		table_irq--;                                    \
	} while (0)
#define smp_processor_id() 3
#define raw_smp_processor_id() smp_processor_id()
#define _Q_LOCKED_VAL 1
#define _RET_IP_ 0x9000UL
#define KD_PR_DEBUG(...)                     \
	do {                                 \
		if (0)                       \
			printf(__VA_ARGS__); \
	} while (0)
/* Preserve diagnostic argument type checking without requiring kernel logging. */
#define KD_PR_INFO(...) KD_PR_DEBUG(__VA_ARGS__)
#define KD_PR_ERR(...)                    \
	do {                              \
		errors++;                 \
		KD_PR_DEBUG(__VA_ARGS__); \
	} while (0)
#define cmpxchg(p, old, value)                \
	({                                    \
		__typeof__(*(p)) seen = *(p); \
		if (seen == (old))            \
			*(p) = (value);       \
		seen;                         \
	})

static void preempt_enable(void);
static void preempt_disable(void);
static void migrate_enable(void);
static void migrate_disable(void);
static bool need_resched(void) __attribute__((unused));
static void schedule(void) __attribute__((unused));
static void cpu_relax(void);
static void kd_origin_mutex_lock(struct mutex *lock);
static void kd_origin_mutex_unlock(struct mutex *lock, unsigned long ip);
static bool kd_mutex_task_active(struct task_struct *task);
static bool kd_mutex_task_reroute(struct task_struct *task);
static bool kd_source_is_open(void);
static bool kd_mutex_task_get(struct task_struct *task);
static void kd_mutex_task_put(struct task_struct *task);
static int kd_hotlock_record_mutex_pinned(unsigned long addr);
static void kd_exe_add_abi(int pid, unsigned long ip, enum kd_exe_lock_kind kind, enum kd_entry_abi abi);
static bool kd_exec_native_unlock(unsigned long addr, bool mutex);
static unsigned long kd_read_kernel_gsbase(void);
static int kd_mutex_lock_slowpath_asm(struct kd_mutex *lock,
				      struct kd_mutex_node *node);
static void jump_to_saved_regs(struct kd_regs *regs);
static void jump_to_saved_regs_in_cs(struct kd_regs *regs);
static struct kd_mutex_node *tail_node_for_cpu(struct kd_mutex_node *node,
					       int cpu);
static int kd_mutex_clobber_wait(struct kd_mutex *lock, struct kd_mutex_node *node);
static void might_sleep(void) { CHECK(!preempt); }
static void kd_hotlock_mutex_entry(void)
{
	CHECK(preempt <= 1);
	entry_attempts++;
}
static bool kd_mutex_trylock_fast(struct mutex *lock)
{
	fast_probes++;
	CHECK(!preempt);
	if (!fast_available || lock->owner)
		return false;
	lock->owner = current;
	acquires++;
	return true;
}
/* Resource cases complete within the bounded polling budget. Parking itself
 * is exercised by the production parking fixture and real scheduler probe. */
static const unsigned int kd_mutex_spin_limit = 4096;
static void init_waitqueue_head(wait_queue_head_t *w) { memset(w, 0, sizeof(*w)); }
static void kd_mutex_park_result(struct kd_mutex_node *n) { (void)n; CHECK(false); }
static void kd_mutex_wait_gate(struct kd_mutex *g)
{
	while (smp_load_acquire(&g->locked))
		cpu_relax();
}
static void kd_mutex_open_gate(struct kd_mutex *g) { smp_store_release(&g->locked, 0); }
#include "mutex_resource_code.h"

/* Equal table-sized strides force collisions using actual mutex addresses;
 * unlike the removed model, the full 1024-entry table is filled through get(). */
struct origin_slot {
	struct mutex mutex;
	char padding[KD_MUTEX_SHADOW_TABLE_SIZE - sizeof(struct mutex)];
};
static struct origin_slot origins[KD_MUTEX_SHADOW_TABLE_SIZE + 1];
static char shadow_stacks[KD_MUTEX_MAX_NODES][KD_MUTEX_SHADOW_STACK_SIZE];

/* Model only per-CPU storage, not the codec. Use distinct addresses for the
 * recorded 40-CPU topology; this_cpu_ptr still uses the existing local pool.
 * These are finite codec inputs, not a claim about Linux per-CPU concurrency. */
#define TAIL_TEST_CPUS 40
static struct kd_mutex_node remote_nodes[TAIL_TEST_CPUS][KD_MUTEX_MAX_NODES];

static struct kd_mutex_node *tail_node_for_cpu(struct kd_mutex_node *node,
					       int cpu)
{
	CHECK(cpu >= 0 && cpu < TAIL_TEST_CPUS);
	for (int idx = 0; idx < KD_MUTEX_MAX_NODES; idx++) {
		if (node == &kd_mutex_nodes[idx])
			return cpu == smp_processor_id() ? node :
						  &remote_nodes[cpu][idx];
	}
	CHECK(false);
	return NULL;
}

static void preempt_disable(void)
{
	entry_pins++;
	preempt++;
}
static void preempt_enable(void)
{
	CHECK(preempt != 0);
	preempt--;
	if (!preempt && recycle_on_enable) {
		struct kd_mutex_node *node;

		/* A scheduled peer may immediately reuse a released CPU-local slot.
		 * Exercise the real reservation API before the old waiter resumes. */
		CHECK(migration == 1 && cpu_shadows.resume_node == NULL);
		recycle_on_enable = false;
		preempt_disable();
		node = kd_mutex_reserve_node();
		CHECK(node == recycle_node);
		memset(&node->regs, 0xa7, sizeof(node->regs));
		kd_mutex_release_node(node);
		preempt_enable();
	}
}
static void migrate_disable(void)
{
	migration++;
}
static void migrate_enable(void)
{
	CHECK(migration != 0);
	migration--;
}
static bool need_resched(void)
{
	return schedule_wanted;
}
static void schedule(void)
{
	CHECK(!preempt && migration == 1);
	schedules++;
	schedule_wanted = false;
}
static void release_peer(struct kd_mutex *gate)
{
	struct task_struct *saved_task = current;
	unsigned int saved_preempt = preempt, saved_migration = migration;

	current = &peer;
	preempt = migration = 0;
	release_gate = gate;
	CHECK(_kd_mutex_unlock_checked(gate) == 0);
	release_gate = NULL;
	preempt = saved_preempt;
	migration = saved_migration;
	current = saved_task;
}
static void cpu_relax(void)
{
	if (poll_node) {
		/* The bounded polling phase must keep preemption disabled.
		 * Simulate the remote completion only after several PAUSE iterations. */
		CHECK(preempt == 1 && migration == 1 && current == &waiter);
		CHECK(!schedule_wanted && !schedules);
		CHECK(++polls <= 8);
		if (polls == 8) {
			poll_node->regs = expected_regs;
			smp_store_release(&poll_node->locked, 0);
		}
		return;
	}
	CHECK(waiting_gate && preempt == 1 && migration == 1);
	CHECK(waiting_gate->physical_owner == &peer);
	release_peer(waiting_gate);
	waiting_gate = NULL;
}
static void kd_origin_mutex_lock(struct mutex *lock)
{
	CHECK(lock && !preempt && !table_irq);
	if (native_owner_wait) {
		struct kd_mutex *gate = find_kd_mutex_shadow(lock);

		/* A native peer acquired L between private-queue owners. Claiming
		 * S cannot bypass that owner; substitute only its eventual unlock. */
		CHECK(lock->owner == &peer && current == &waiter);
		CHECK(gate && gate->locked == _Q_LOCKED_VAL &&
		      !gate->physical_owner && !release_gate && refs == 1);
		native_owner_wait = false;
		native_waits++;
		current = &peer;
		kd_origin_mutex_unlock(lock, 0x9000);
		current = &waiter;
	}
	CHECK(!lock->owner);
	lock->owner = current;
	acquires++;
}
static void kd_origin_mutex_unlock(struct mutex *lock, unsigned long ip)
{
	(void)ip;
	CHECK(lock && lock->owner == current && !preempt && !table_irq);
	if (release_gate)
		CHECK(!release_gate->physical_owner && release_gate->locked);
	lock->owner = NULL;
	releases++;
}
static bool kd_mutex_task_active(struct task_struct *task)
{
	CHECK(task == current);
	return refs || active_override;
}
/* Task membership is a substitute; the real unlock hook must consult it
 * when the CPU cools, the name changes or source admission has closed. */
static bool kd_mutex_task_reroute(struct task_struct *task)
{
	return kd_mutex_task_active(task);
}
static bool kd_source_is_open(void)
{
	return source_open;
}
static bool kd_mutex_task_get(struct task_struct *task)
{
	CHECK(task == current && !preempt && !table_irq);
	gets++;
	if (task_failure)
		return false;
	refs++;
	return true;
}
static void kd_mutex_task_put(struct task_struct *task)
{
	CHECK(task == current && refs && !preempt && !migration);
	refs--;
	task_puts++;
}
static int kd_hotlock_record_mutex_pinned(unsigned long addr)
{
	/* Contention sampling may touch several CPU-local fields; it remains
	 * pinned even though the first native CAS is now unpinned. */
	CHECK(addr && preempt == 1 && entry_attempts > samples);
	samples++;
	sampled_first = true;
	return cpu_hot && promoted;
}
static void kd_exe_add_abi(int pid, unsigned long ip, enum kd_exe_lock_kind kind, enum kd_entry_abi abi)
{
	CHECK(!pid && ip == 0x8000 && kind == KD_EXE_LOCK_MUTEX && refs);
	CHECK(abi == KD_ENTRY_ABI_LEGACY || abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
	adds++;
}
static bool kd_exec_native_unlock(unsigned long addr, bool mutex)
{
	CHECK(addr && mutex);
	notify_calls++;
	return borrowed;
}
static unsigned long kd_read_kernel_gsbase(void)
{
	return 0xdead0000UL;
}

static int kd_mutex_lock_slowpath_asm(struct kd_mutex *lock,
				      struct kd_mutex_node *node)
{
	struct kd_regs entry = { .sp = (unsigned long)&native_stack[16] };

	slow_calls++;
	CHECK(preempt == 1 && migration == 1 && refs == 1);
	CHECK(node->lock == lock && node->task_struct_ptr == current);
	CHECK(node->gsbase == kd_read_kernel_gsbase());
	CHECK(node->tail == (int)kd_mutex_encode_tail(smp_processor_id(), node->slot));
	CHECK(kd_mutex_decode_tail(node->tail) == node);
	CHECK(node->locked && !node->completed && !node->native_resume &&
	      !node->next);
	CHECK(node->saved_ret_addr == 0x8000);
	CHECK(memcmp(&node->regs, &entry, sizeof(entry)) == 0);
	if (mode == 2) {
		release_peer(lock);
		lock->locked = _Q_LOCKED_VAL;
		preempt_enable();
		kd_mutex_claim_origin(lock);
		preempt_disable();
	} else {
		CHECK(mode == 3 || mode == 5);
		node->regs = expected_regs;
		node->native_resume = mode == 5;
		cpu_shadows.resume_node = node;
		recycle_node = node;
		recycle_on_enable = true;
	}
	return mode;
}
/* Exercise the real minimal entry producer without simulating its nonlocal
 * restoration here; that assembly is run separately and in live mutex tests. */
static int kd_mutex_clobber_wait(struct kd_mutex *lock, struct kd_mutex_node *node)
{
	CHECK(node->entry_abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
	CHECK(node->packet_state == KD_PACKET_MINIMAL);
	CHECK(node->regs.ip == 0x8000 && node->regs.bp == 0xabc0);
	CHECK(node->regs.sp == (unsigned long)&native_stack[16]);
	struct kd_regs before = node->regs;
	before.ip = before.sp = before.bp = 0xa7a7a7a7a7a7a7a7UL;
	struct kd_regs poison;
	memset(&poison, 0xa7, sizeof(poison));
	CHECK(!memcmp(&before, &poison, sizeof(before)));
	release_peer(lock);
	lock->locked = _Q_LOCKED_VAL;
	preempt_enable();
	kd_mutex_claim_origin(lock);
	preempt_disable();
	return 2;
}

static void capture_resume(struct kd_regs *regs, int result)
{
	CHECK(!preempt && !migration && !table_irq);
	CHECK(!cpu_shadows.node_slots && !cpu_shadows.resume_node);
	CHECK(!kd_mutex_reserved_nodes && !recycle_on_enable);
	CHECK(memcmp(regs, &expected_regs, sizeof(*regs)) == 0);
	captured_regs = *regs;
	longjmp(resume_target, result);
}
static void jump_to_saved_regs(struct kd_regs *regs)
{
	capture_resume(regs, 3);
}
static void jump_to_saved_regs_in_cs(struct kd_regs *regs)
{
	capture_resume(regs, 5);
}

static void reset(void)
{
	memset(origins, 0, sizeof(origins));
	memset(kd_mutex_shadows, 0, sizeof(kd_mutex_shadows));
	memset(kd_mutex_nodes, 0, sizeof(kd_mutex_nodes));
	memset(&cpu_shadows, 0, sizeof(cpu_shadows));
	for (int i = 0; i < KD_MUTEX_MAX_NODES; i++) {
		kd_mutex_nodes[i].slot = i;
		kd_mutex_nodes[i].shadow_stack_base = shadow_stacks[i];
		kd_mutex_nodes[i].shadow_stack_ptr =
			(unsigned long)&shadow_stacks[i]
						     [KD_MUTEX_SHADOW_STACK_SIZE];
	}
	current = &waiter;
	strcpy(waiter.comm, "target");
	strcpy(peer.comm, "peer");
	source_open = true;
	native_owner_wait = false;
	fast_available = false;
	entry_attempts = entry_pins = fast_probes = 0;
	native_waits = 0;
	errors = preempt = migration = table_irq = table_lock_entries = 0;
	gets = task_puts = refs = adds = acquires = releases = schedules = 0;
	slow_calls = notify_calls = samples = mode = 0;
	kd_mutex_multi_slot_count = kd_mutex_frame_failure_count = 0;
	kd_mutex_node_overflow_count = kd_mutex_jit_resume_count = 0;
	kd_mutex_origin_acquires = kd_mutex_origin_releases = 0;
	kd_mutex_reserved_nodes = 0;
	promoted = cpu_hot = true;
	trace_admission = sampled_first = false;
	comm_queries = 0;
	shadow_before_lock = NULL;
	shadow_racing_origin = NULL;
	shadow_racing_entry = NULL;
	kd_comm_init(&kd_spin_target, target_process);
	task_failure = active_override = borrowed = false;
	schedule_wanted = recycle_on_enable = direct_packet = false;
	waiting_gate = release_gate = NULL;
	recycle_node = NULL;
	memset(&expected_regs, 0x51, sizeof(expected_regs));
	expected_regs.sp = (unsigned long)&native_stack[20];
	expected_regs.ip = 0x8765;
	memset(&captured_regs, 0, sizeof(captured_regs));
}

static void check_tails(void)
{
	const struct {
		int cpu, idx;
		u32 word;
	} golden[] = {
		{ 0, 0, 0x10 },
		{ 7, 3, 0x8c },
		{ 39, 2, 0x288 },
	};
	u32 previous = 0;

	/* Fixed wire values prevent matching bugs in encoder/decoder from hiding
	 * behind a round trip. Zero is the caller's empty-queue sentinel: never
	 * feed it to kd_mutex_decode_tail(), which requires a published nonzero tail. */
	for (unsigned int i = 0; i < sizeof(golden) / sizeof(golden[0]); i++)
		CHECK(kd_mutex_encode_tail(golden[i].cpu, golden[i].idx) == golden[i].word);
	for (int cpu = 0; cpu < TAIL_TEST_CPUS; cpu++) {
		for (int idx = 0; idx < KD_MUTEX_MAX_NODES; idx++) {
			struct kd_mutex_node *expected =
				cpu == smp_processor_id() ? &kd_mutex_nodes[idx] :
							 &remote_nodes[cpu][idx];
			u32 tail = kd_mutex_encode_tail(cpu, idx);

			/* Ascending distinct words also rule out zero and collisions
			 * across CPUs/slots. Reserved low bits must not select a node. */
			CHECK(tail > previous && !(tail & 3));
			CHECK(kd_mutex_decode_tail(tail) == expected);
			CHECK(kd_mutex_decode_tail(tail | 3) == expected);
			previous = tail;
		}
	}
}

static void check_nodes(void)
{
	struct kd_mutex_node before[KD_MUTEX_MAX_NODES], *node;
	const unsigned int masks = 1U << KD_MUTEX_MAX_NODES;

	/* Exhaust the bounded reservation inputs, preserving all other slots and
	 * the fields that release must leave for stack reuse and diagnostics. */
	for (unsigned int occupied = 0; occupied < masks; occupied++) {
		for (unsigned int available = 0; available < masks;
		     available++) {
			int chosen = -1;
			reset();
			preempt = migration = 1;
			cpu_shadows.node_slots = occupied;
			kd_mutex_reserved_nodes =
				__builtin_popcount(occupied);
			for (int i = 0; i < KD_MUTEX_MAX_NODES; i++) {
				kd_mutex_nodes[i].shadow_stack_base =
					available & BIT(i) ? shadow_stacks[i] :
							     NULL;
				kd_mutex_nodes[i].next =
					&kd_mutex_nodes[(i + 1) %
							KD_MUTEX_MAX_NODES];
				kd_mutex_nodes[i].task_struct_ptr = &peer;
				kd_mutex_nodes[i].lock =
					&kd_mutex_shadows[0].kd_mtx;
				kd_mutex_nodes[i].gsbase = 0xabcd;
				if (chosen < 0 && !(occupied & BIT(i)) &&
				    (available & BIT(i)))
					chosen = i;
			}
			memcpy(before, kd_mutex_nodes, sizeof(before));
			node = kd_mutex_reserve_node();
			CHECK(node ==
			      (chosen < 0 ? NULL : &kd_mutex_nodes[chosen]));
			CHECK(memcmp(before, kd_mutex_nodes, sizeof(before)) ==
			      0);
			CHECK(cpu_shadows.node_slots ==
			      (occupied | (chosen < 0 ? 0 : BIT(chosen))));
			CHECK(kd_mutex_multi_slot_count ==
			      (unsigned long)(occupied && chosen >= 0));
			CHECK(kd_mutex_reserved_nodes ==
			      __builtin_popcount(occupied) + (chosen >= 0));
			if (node) {
				kd_mutex_release_node(node);
				before[chosen].next = NULL;
				before[chosen].lock = NULL;
				before[chosen].task_struct_ptr = NULL;
				before[chosen].gsbase = 0;
				CHECK(memcmp(before, kd_mutex_nodes,
					     sizeof(before)) == 0);
				CHECK(cpu_shadows.node_slots == occupied);
				CHECK(kd_mutex_reserved_nodes ==
				      __builtin_popcount(occupied));
			}
			CHECK(!errors && !kd_mutex_frame_failure_count);
		}
	}
	reset();
	preempt = migration = 1;
	for (int i = 0; i < 1000; i++) {
		node = kd_mutex_reserve_node();
		CHECK(node == &kd_mutex_nodes[0]);
		kd_mutex_release_node(node);
	}
	node = kd_mutex_reserve_node();
	CHECK(kd_mutex_reserve_node() == &kd_mutex_nodes[1]);
	CHECK(kd_mutex_reserve_node() == &kd_mutex_nodes[2]);
	kd_mutex_release_node(node);
	CHECK(kd_mutex_reserve_node() == node && cpu_shadows.node_slots == 7);
	for (int i = 0; i < 3; i++)
		kd_mutex_release_node(&kd_mutex_nodes[i]);
	CHECK(!cpu_shadows.node_slots && !kd_mutex_reserved_nodes);
	memcpy(before, kd_mutex_nodes, sizeof(before));
	kd_mutex_release_node(node);
	kd_mutex_release_node(NULL);
	struct kd_mutex_node bad = { .slot = -1 };
	kd_mutex_release_node(&bad);
	bad.slot = KD_MUTEX_MAX_NODES;
	kd_mutex_release_node(&bad);
	CHECK(errors == 4 && kd_mutex_frame_failure_count == 4);
	CHECK(!cpu_shadows.node_slots && !kd_mutex_reserved_nodes);
	CHECK(memcmp(before, kd_mutex_nodes, sizeof(before)) == 0);
}

static unsigned int shadow_count(void)
{
	unsigned int count = 0;
	for (int i = 0; i < KD_MUTEX_SHADOW_TABLE_SIZE; i++)
		count += kd_mutex_shadows[i].kd_mtx.origin_mutex_addr != 0;
	return count;
}
static void check_shadow_table(void)
{
	struct kd_mutex_shadow_entry before[KD_MUTEX_SHADOW_TABLE_SIZE];
	struct kd_mutex *entries[KD_MUTEX_SHADOW_TABLE_SIZE];
	struct mutex *missing = &origins[KD_MUTEX_SHADOW_TABLE_SIZE].mutex;

	reset();
	CHECK(!find_kd_mutex_shadow(&origins[0].mutex) && !shadow_count());
	CHECK(!table_lock_entries);
	for (int i = 0; i < KD_MUTEX_SHADOW_TABLE_SIZE; i++) {
		entries[i] = get_kd_mutex_shadow(&origins[i].mutex);
		CHECK(entries[i] && entries[i]->origin_mutex_addr ==
					    (unsigned long)&origins[i].mutex);
		CHECK((unsigned long)entries[i]->waiter_slot ==
		      (((unsigned long)&origins[0].mutex % KD_MUTEX_SHADOW_TABLE_SIZE + i) %
		       KD_MUTEX_SHADOW_TABLE_SIZE));
		CHECK(!entries[i]->tail && !entries[i]->state.counter &&
		      !entries[i]->waiter_count.counter &&
		      !entries[i]->physical_owner);
		CHECK((unsigned long)&origins[i] % KD_MUTEX_SHADOW_TABLE_SIZE ==
		      (unsigned long)&origins[0] % KD_MUTEX_SHADOW_TABLE_SIZE);
		CHECK(shadow_count() == (unsigned int)i + 1);
	}
	/* Keep a pre-existing native owner intact when a different address cannot
	 * obtain a shadow; unlock lookup must never create another entry. */
	entries[0]->locked = _Q_LOCKED_VAL;
	entries[0]->physical_owner = &peer;
	origins[0].mutex.owner = &peer;
	memcpy(before, kd_mutex_shadows, sizeof(before));
	CHECK(table_lock_entries == KD_MUTEX_SHADOW_TABLE_SIZE);
	for (int i = 0; i < KD_MUTEX_SHADOW_TABLE_SIZE; i++) {
		CHECK(get_kd_mutex_shadow(&origins[i].mutex) == entries[i]);
		CHECK(find_kd_mutex_shadow(&origins[i].mutex) == entries[i]);
	}
	CHECK(!find_kd_mutex_shadow(missing));
	/* Existing queue owners stay intact without the insertion lock. */
	CHECK(table_lock_entries == KD_MUTEX_SHADOW_TABLE_SIZE);
	__kd_mutex_lock(missing, (unsigned long)&native_stack[16], 0x8000);
	CHECK(errors == 1 && !gets && !adds && !slow_calls && !refs);
	CHECK(missing->owner == current && acquires == 1);
	__kd_mutex_unlock(missing, 0, 0x9000);
	CHECK(!missing->owner && releases == 1 && !task_puts);
	CHECK(!cpu_shadows.node_slots && !kd_mutex_reserved_nodes);
	CHECK(memcmp(before, kd_mutex_shadows, sizeof(before)) == 0);
	CHECK(!table_irq && !kd_mutex_shadow_lock);
}

static void publish_shadow_before_lock(void)
{
	CHECK(shadow_racing_origin && !table_irq && !kd_mutex_shadow_lock);
	shadow_racing_entry = get_kd_mutex_shadow(shadow_racing_origin);
	CHECK(shadow_racing_entry);
	/* An actual gate may already be in use when the losing inserter reaches
	 * the lock. Rechecking an existing key must never reinitialize that gate. */
	shadow_racing_entry->tail = kd_mutex_encode_tail(1, 2);
	shadow_racing_entry->locked = _Q_LOCKED_COMBINER_VAL;
	shadow_racing_entry->physical_owner = &peer;
	shadow_racing_entry->waiter_count.counter = 2;
	shadow_racing_origin->owner = &peer;
	memcpy(&shadow_racing_snapshot, shadow_racing_entry,
	       sizeof(shadow_racing_snapshot));
}

static void check_shadow_insert_race(void)
{
	for (unsigned int collision = 0; collision < 2; collision++) {
		struct mutex *lock = &origins[0].mutex;
		struct kd_mutex *entry;

		reset();
		shadow_racing_origin = &origins[collision].mutex;
		CHECK((unsigned long)lock % KD_MUTEX_SHADOW_TABLE_SIZE ==
		      (unsigned long)shadow_racing_origin % KD_MUTEX_SHADOW_TABLE_SIZE);
		shadow_before_lock = publish_shadow_before_lock;
		entry = get_kd_mutex_shadow(lock);
		CHECK(!shadow_before_lock && shadow_racing_entry && entry);
		CHECK(entry->origin_mutex_addr == (unsigned long)lock);
		CHECK((entry != shadow_racing_entry) == !!collision);
		CHECK(shadow_count() == 1 + collision);
		CHECK(!memcmp(&shadow_racing_snapshot, shadow_racing_entry,
			      sizeof(shadow_racing_snapshot)));
		CHECK(shadow_racing_origin->owner == &peer);
		CHECK(find_kd_mutex_shadow(shadow_racing_origin) == shadow_racing_entry);
		CHECK(find_kd_mutex_shadow(lock) == entry);
		if (collision)
			CHECK(!entry->tail && !entry->state.counter &&
			      !entry->physical_owner && !entry->waiter_count.counter);
		CHECK(table_lock_entries == 2 && !table_irq && !kd_mutex_shadow_lock);
	}
}

static void check_hook_fallbacks(void)
{
	/* Exercise each early routing decision, both with a cold shadow and with
	 * an existing unused shadow. Native-only paths never reserve a node. */
	for (int existing = 0; existing < 2; existing++) {
		for (int reason = 0; reason < 4; reason++) {
			struct mutex *lock = &origins[0].mutex;
			reset();
			if (existing)
				CHECK(get_kd_mutex_shadow(lock));
			active_override = reason == 0;
			promoted = reason != 1;
			task_failure = reason == 2;
			mutex_native_route = reason == 3;
			__kd_mutex_lock(lock, (unsigned long)&native_stack[16],
					0x8000);
			CHECK(lock->owner == current && acquires == 1);
			CHECK(gets == (unsigned int)(reason == 2) &&
			      !task_puts && !refs && !adds);
			CHECK(shadow_count() ==
			      (unsigned int)(existing || reason == 2));
			CHECK(samples == 1);
			CHECK(!slow_calls && !cpu_shadows.node_slots &&
			      !kd_mutex_reserved_nodes);
			__kd_mutex_unlock(lock, 0, 0x9000);
			CHECK(!lock->owner && releases == 1 && !task_puts);
			CHECK(shadow_count() ==
			      (unsigned int)(existing || reason == 2));
			CHECK(!errors && !preempt && !migration && !table_irq);
			mutex_native_route = false;
		}
	}
}

/* Reproduce a queue head suspended before original-mutex acquisition. A local
 * follower must stay unpublished and acquire natively with scheduling enabled;
 * neither its return nor unlock may touch the predecessor's gate/reservation. */
static void check_local_predecessor(void)
{
	struct mutex *lock = &origins[0].mutex;
	struct kd_mutex_node *head;
	struct kd_mutex *gate;
	struct kd_mutex other = {0};

	reset();
	gate = get_kd_mutex_shadow(lock);
	preempt = migration = 1;
	head = kd_mutex_reserve_node();
	head->lock = gate;
	head->task_struct_ptr = &peer;
	gate->locked = _Q_LOCKED_VAL;
	CHECK(kd_mutex_has_local_predecessor(gate));
	CHECK(!kd_mutex_has_local_predecessor(&other));
	preempt = migration = 0;
	__kd_mutex_lock(lock, (unsigned long)&native_stack[16], 0x8000);
	CHECK(!preempt && !migration && !slow_calls && !refs && task_puts == 1);
	CHECK(lock->owner == current && gate->locked && !gate->physical_owner);
	CHECK(head->lock == gate && cpu_shadows.node_slots == BIT(head->slot));
	__kd_mutex_unlock(lock, 0, 0x9000);
	CHECK(!lock->owner && gate->locked && !gate->physical_owner);
	CHECK(task_puts == 1 && releases == 1 && !errors);
	preempt = migration = 1;
	kd_mutex_release_node(head);
	CHECK(!kd_mutex_has_local_predecessor(gate));
}

static void hold_peer(struct kd_mutex *gate)
{
	gate->locked = _Q_LOCKED_COMBINER_VAL;
	gate->physical_owner = &peer;
	((struct mutex *)gate->origin_mutex_addr)->owner = &peer;
	kd_mutex_origin_acquires = 1;
}

/* Connect promotion and renamed-owner routing to the actual hooks. The native
 * wait is deterministic; real Linux exclusion and RCU remain live-test duties. */
static void check_frequency_order(void)
{
	for (unsigned int abi = 0; abi < 2; abi++) {
		for (unsigned int stage = 0; stage < 4; stage++) {
			reset();
			struct mutex *lock = &origins[0].mutex;
			cpu_hot = stage != 0;
			promoted = stage != 1;
			source_open = stage != 3;
			if (stage != 3) strcpy(current->comm, "non-target");
			trace_admission = true;
			CHECK(!comm_queries);
			if (abi) __kd_mutex_lock_clobber_v1(lock, (unsigned long)&native_stack[16], 0x8000, 0);
			else __kd_mutex_lock(lock, (unsigned long)&native_stack[16], 0x8000);
			CHECK(samples == 1 && lock->owner == current && !gets && !adds);
			CHECK(comm_queries == (stage == 2));
			unsigned int queries = comm_queries;
			__kd_mutex_unlock(lock, 0, 0x9000);
			CHECK(!lock->owner && comm_queries == queries && samples == 1);
			CHECK(!notify_calls && !refs && !shadow_count());
		}
	}
}

static void check_promotion_and_routing(void)
{
	struct mutex *lock = &origins[0].mutex;
	struct kd_mutex *gate;

	reset();
	promoted = false;
	__kd_mutex_lock(lock, (unsigned long)&native_stack[16], 0x8000);
	CHECK(lock->owner == current && !refs && !shadow_count());
	promoted = true;
	__kd_mutex_unlock(lock, 0, 0x9000);
	CHECK(!lock->owner && !task_puts && !shadow_count());

	/* A native peer may win L before the promoted target's next acquisition;
	 * no queue handoff is allowed to manufacture native ownership. */
	current = &peer;
	__kd_mutex_lock(lock, (unsigned long)&native_stack[16], 0x8000);
	CHECK(!refs && !shadow_count());
	current = &waiter;
	native_owner_wait = true;
	__kd_mutex_lock(lock, (unsigned long)&native_stack[16], 0x8000);
	gate = find_kd_mutex_shadow(lock);
	CHECK(!native_owner_wait && native_waits == 1);
	CHECK(gate && gate->physical_owner == current && lock->owner == current);
	CHECK(refs == 1 && gets == 1 && !task_puts);

	cpu_hot = false;
	source_open = false;
	strcpy(current->comm, "renamed");
	__kd_mutex_unlock(lock, 0, 0x9000);
	CHECK(!lock->owner && !gate->physical_owner && !gate->locked);
	CHECK(!refs && task_puts == 1);
	strcpy(current->comm, "target");
	source_open = true;
	CHECK(acquires == 3 && releases == 3 && !errors);
	CHECK(kd_mutex_origin_acquires == kd_mutex_origin_releases);
}

static void check_hook_nodes(void)
{
	/* Full slots and absent stacks converge on the real no-node wait path.
	 * It must poll with preemption disabled, then acquire L and unlock L before S. */
	for (int resource = 0; resource < 3; resource++) {
		struct mutex *lock = &origins[0].mutex;
		struct kd_mutex *gate;
		struct kd_mutex_node before[KD_MUTEX_MAX_NODES];
		unsigned long occupied;

		reset();
		gate = get_kd_mutex_shadow(lock);
		if (resource) {
			hold_peer(gate);
			waiting_gate = gate;
			schedule_wanted = true;
			if (resource == 1) {
				preempt = migration = 1;
				for (int i = 0; i < KD_MUTEX_MAX_NODES; i++)
					CHECK(kd_mutex_reserve_node());
				preempt = migration = 0;
			} else {
				for (int i = 0; i < KD_MUTEX_MAX_NODES; i++)
					kd_mutex_nodes[i].shadow_stack_base =
						NULL;
			}
		}
		occupied = cpu_shadows.node_slots;
		memcpy(before, kd_mutex_nodes, sizeof(before));
		__kd_mutex_lock(lock, (unsigned long)&native_stack[16], 0x8000);
		CHECK(gets == 1 && refs == 1 && adds == 1 && !slow_calls &&
		      !task_puts);
		CHECK(lock->owner == current &&
		      gate->physical_owner == current &&
		      gate->locked == _Q_LOCKED_VAL);
		CHECK(acquires == 1 && kd_mutex_node_overflow_count ==
					       (unsigned long)(resource != 0));
		CHECK(!schedules && !preempt && !migration);
		CHECK(cpu_shadows.node_slots == occupied &&
		      memcmp(before, kd_mutex_nodes, sizeof(before)) == 0);
		release_gate = gate;
		__kd_mutex_unlock(lock, 0, 0x9000);
		CHECK(!lock->owner && !gate->physical_owner && !gate->locked);
		CHECK(task_puts == 1 && !refs &&
		      kd_mutex_origin_acquires == kd_mutex_origin_releases);
		CHECK(!errors && !kd_mutex_frame_failure_count);
	}
}

static void check_slowpath_packets(void)
{
	static int scenario;

	/* Exercise hook-to-producer flow, then independently check marked saved
	 * arguments at the direct API. The assembly boundary supplies valid queue
	 * outcomes; these do not prove the substituted queue's JIT correctness. */
	for (scenario = 0; scenario < 6; scenario++) {
		struct mutex *lock = &origins[0].mutex;
		struct kd_mutex *gate;
		int resumed;

		reset();
		gate = get_kd_mutex_shadow(lock);
		hold_peer(gate);
		mode = scenario % 3 == 0 ? 2 : scenario % 3 == 1 ? 3 : 5;
		direct_packet = scenario >= 3;
		if (direct_packet)
			CHECK(kd_mutex_task_get(current));
		resumed = setjmp(resume_target);
		if (!resumed) {
			if (direct_packet)
				_kd_mutex_lock_abi(gate,
					       (unsigned long)&native_stack[16],
					       0x8000, 0, KD_ENTRY_ABI_LEGACY);
			else
				__kd_mutex_lock(
					lock, (unsigned long)&native_stack[16],
					0x8000);
			CHECK(mode == 2);
		} else {
			CHECK(resumed == (int)mode);
			CHECK(memcmp(&captured_regs, &expected_regs,
				     sizeof(expected_regs)) == 0);
			CHECK(memcmp(&recycle_node->regs, &expected_regs,
				     sizeof(expected_regs)) != 0);
		}
		CHECK(slow_calls == 1 && !cpu_shadows.node_slots &&
		      !cpu_shadows.resume_node);
		CHECK(!kd_mutex_reserved_nodes && !preempt &&
		      !migration);
		CHECK(!kd_mutex_frame_failure_count && !errors);
		CHECK(gets == 1 && adds == (unsigned int)!direct_packet);
		CHECK(kd_mutex_jit_resume_count == (unsigned long)(mode == 3));
		if (mode == 2) {
			CHECK(gate->physical_owner == current &&
			      lock->owner == current);
			release_gate = gate;
			__kd_mutex_unlock(lock, 0, 0x9000);
			CHECK(task_puts == 1 && !refs);
		} else {
			CHECK(gate->physical_owner == &peer &&
			      lock->owner == &peer);
			CHECK(task_puts == (unsigned int)(mode == 3) &&
			      refs == (unsigned int)(mode == 5));
			if (mode == 5) {
				struct mutex *nested = &origins[1].mutex;
				unsigned int count;

				/* A borrowed suffix keeps its acquisition routing reference
				 * after rename and closing; C still belongs to the waiter. */
				strcpy(current->comm, "renamed");
				source_open = false;

				/* The native suffix owns its unrelated C, not borrowed A.
				 * Exercise absent and idle C shadows without consuming the
				 * pre-existing routing ref or modifying A's physical owner.
				 * Actual rename/ACK scheduling is checked in the live gate. */
				if (direct_packet)
					CHECK(get_kd_mutex_shadow(nested));
				count = shadow_count();
				__kd_mutex_lock(
					nested,
					(unsigned long)&native_stack[16],
					0x8000);
				CHECK(nested->owner == current &&
				      acquires == 1);
				__kd_mutex_unlock(nested, 0, 0x9000);
				CHECK(!nested->owner && releases == 1);
				CHECK(refs == 1 && gets == 1 && !task_puts &&
				      shadow_count() == count && !errors);
				CHECK(gate->physical_owner == &peer &&
				      lock->owner == &peer);
				borrowed = true;
				__kd_mutex_unlock(lock, 0, 0x9000);
				CHECK(notify_calls == 2 && releases == 1 &&
				      !task_puts && refs == 1);
				CHECK(gate->physical_owner == &peer &&
				      lock->owner == &peer);
			}
			release_peer(gate);
			if (mode == 5) {
				/* The owner/ACK boundary is substituted here. Consume its
				 * final routing ref only after the retained L is released. */
				kd_mutex_task_put(current);
				CHECK(!refs && task_puts == 1);
			}
		}
		CHECK(!lock->owner && !gate->physical_owner && !gate->locked);
		CHECK(kd_mutex_origin_acquires == kd_mutex_origin_releases);
	}
}

/* Exercise the production acquire/PAUSE loop against a delayed publication,
 * including completion already visible at entry. No kernel scheduler is mocked
 * into the loop to create progress; the peer publishes from cpu_relax(). */
static void check_poll_result(void)
{
	reset();
	preempt = migration = 1;
	schedule_wanted = false;
	poll_node = &kd_mutex_nodes[0];
	poll_node->locked = 1;
	polls = 0;
	kd_mutex_wait_for_result(poll_node);
	CHECK(polls == 8 && !schedules && preempt == 1 && migration == 1);
	CHECK(memcmp(&poll_node->regs, &expected_regs, sizeof(expected_regs)) == 0);
	kd_mutex_wait_for_result(poll_node);
	CHECK(polls == 8 && !schedule_wanted);
	poll_node = NULL;
}

static void check_minimal_entry(void)
{
	reset();
	struct mutex *lock = &origins[0].mutex;
	struct kd_mutex *gate = get_kd_mutex_shadow(lock);
	hold_peer(gate);
	for (unsigned int i = 0; i < KD_MUTEX_MAX_NODES; i++)
		memset(&kd_mutex_nodes[i].regs, 0xa7, sizeof(struct kd_regs));
	__kd_mutex_lock_clobber_v1(lock, (unsigned long)&native_stack[16], 0x8000, 0xabc0);
	CHECK(!preempt && !migration && !cpu_shadows.node_slots);
	CHECK(gate->physical_owner == current && refs == 1);
	__kd_mutex_unlock(lock, 0, 0x9000);
	CHECK(!refs && !gate->locked);
}

/* Only pre-reference native fallbacks may return a native cookie. Existing
 * unrelated task activity does not change this lock's exact native owner. */
static void check_outer_native_result(void)
{
	for (unsigned int scenario = 0; scenario < 6; scenario++) {
		reset();
		struct mutex *lock = &origins[0].mutex;
		if (scenario == 0) cpu_hot = false;
		if (scenario == 1) source_open = false;
		if (scenario == 2) strcpy(current->comm, "non-target");
		if (scenario == 3) refs = 1; /* An unrelated acquisition remains live. */
		if (scenario == 4) task_failure = true;
		if (scenario == 5) { cpu_hot = false; refs = 1; borrowed = true; }
		unsigned int inherited_refs = refs;
		unsigned long route = kd_mutex_outer_contended_clobber_v1(
			lock, (unsigned long)&native_stack[16], 0x8000, 0);
		CHECK(route == (unsigned long)current && lock->owner == current);
		CHECK(refs == inherited_refs && !task_puts && !fast_probes && entry_attempts == 1 && samples == 1);
		kd_origin_mutex_unlock(lock, 0x9000);
		CHECK(!lock->owner && refs == inherited_refs && !notify_calls && !task_puts);
	}
	reset();
	struct mutex *lock = &origins[0].mutex;
	unsigned long route = kd_mutex_outer_contended_clobber_v1(
		lock, (unsigned long)&native_stack[16], 0x8000, 0);
	struct kd_mutex *gate = find_kd_mutex_shadow(lock);
	CHECK(!route && refs == 1 && gate && gate->physical_owner == current);
	__kd_mutex_unlock(lock, 0, 0x9000);
	CHECK(!refs && task_puts == 1 && !gate->locked);

	/* A later native fallback has already entered the KD queue contract.
	 * Keep ROUTED even though local-predecessor refusal drops its own ref. */
	reset();
	gate = get_kd_mutex_shadow(lock);
	preempt = migration = 1;
	struct kd_mutex_node *head = kd_mutex_reserve_node();
	head->lock = gate;
	head->task_struct_ptr = &peer;
	gate->locked = _Q_LOCKED_VAL;
	preempt = migration = 0;
	route = kd_mutex_outer_contended_clobber_v1(
		lock, (unsigned long)&native_stack[16], 0x8000, 0);
	CHECK(!route && !refs && task_puts == 1 && lock->owner == current);
	CHECK(gate->locked && !gate->physical_owner && !slow_calls);
	__kd_mutex_unlock(lock, 0, 0x9000);
	CHECK(!lock->owner && gate->locked && task_puts == 1);
	preempt = migration = 1;
	kd_mutex_release_node(head);
}

int main(void)
{
	/* Even a hot lock with task/shadow work otherwise eligible must bypass all
	 * of it when the original owner CAS succeeds. Unlock still uses Linux. */
	reset();
	fast_available = true;
	__kd_mutex_lock_clobber_v1(&origins[0].mutex, 0x7000, 0x8000, 0);
	CHECK(origins[0].mutex.owner == current && entry_attempts == 1);
	CHECK(!samples && !gets && !adds && !refs && !comm_queries && !entry_pins);
	CHECK(!preempt && !migration && !shadow_count());
	__kd_mutex_unlock(&origins[0].mutex, 0, 0x9000);
	CHECK(!origins[0].mutex.owner && acquires == 1 && releases == 1);
	/* This endpoint consumes a caller's failed CAS; it must not retry the CAS
	 * or count twice even if the original mutex becomes free before entry. */
	reset();
	fast_available = true;
	cpu_hot = false;
	kd_mutex_direct_contended_clobber_v1(&origins[0].mutex, 0x7000, 0x8000, 0);
	CHECK(!fast_probes && entry_attempts == 1 && samples == 1);
	CHECK(origins[0].mutex.owner == current && !refs && !gets);
	__kd_mutex_unlock(&origins[0].mutex, 0, 0x9000);
	check_outer_native_result();
	check_minimal_entry();
	check_poll_result();
	check_tails();
	check_nodes();
	check_shadow_table();
	check_shadow_insert_race();
	check_hook_fallbacks();
	check_local_predecessor();
	check_frequency_order();
	check_promotion_and_routing();
	check_hook_nodes();
	check_slowpath_packets();
	printf("production mutex resources: %u checks, 0 failures; nodes=%d shadow=%d regs=%zu\n",
	       checks, KD_MUTEX_MAX_NODES, KD_MUTEX_SHADOW_TABLE_SIZE,
	       sizeof(struct kd_regs));
	return 0;
}
