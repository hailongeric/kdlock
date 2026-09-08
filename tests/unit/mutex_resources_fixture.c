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

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef struct {
	int counter;
} atomic_t;
struct task_struct {
	int pid;
};
struct mutex {
	struct task_struct *owner;
};
#include "mutex_resource_types.h"

static struct task_struct waiter = { 1 }, peer = { 2 };
static struct task_struct *current = &waiter;
static unsigned int checks, errors, preempt, migration, table_irq;
static unsigned int gets, task_puts, refs, adds, acquires, releases, schedules;
static unsigned int slow_calls, notify_calls, samples, mode;
static unsigned long kd_mutex_multi_slot_count, kd_mutex_frame_failure_count;
static unsigned long kd_mutex_node_overflow_count, kd_mutex_jit_resume_count;
static unsigned long kd_mutex_origin_acquires, kd_mutex_origin_releases;
static atomic_t kd_mutex_reserved_nodes;
static bool promoted, enabled, task_failure, active_override, borrowed;
static bool schedule_wanted, recycle_on_enable, direct_packet;
static struct kd_mutex *waiting_gate, *release_gate;
static struct kd_mutex_node *recycle_node;
static struct pt_regs expected_regs, captured_regs;
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
#define likely(c) (c)
#define unlikely(c) (c)
#define READ_ONCE(v) (v)
#define WRITE_ONCE(v, value) ((v) = (value))
#define smp_load_acquire(p) (*(p))
#define smp_store_release(p, v) (*(p) = (v))
#define atomic_set(p, v) ((p)->counter = (v))
#define atomic_inc(p) (++(p)->counter)
#define atomic_dec(p) (--(p)->counter)
#define atomic64_inc(p) (++*(p))
#define BIT(n) (1UL << (n))
#define DEFINE_PER_CPU_SHARED_ALIGNED(type, name) type name
#define this_cpu_ptr(p) (p)
#define DEFINE_RAW_SPINLOCK(name) int name
#define raw_spin_lock_irqsave(p, flags)     \
	do {                                \
		CHECK(!*(p) && !table_irq); \
		*(p) = 1;                   \
		table_irq++;                \
		(flags) = 0;                \
	} while (0)
#define raw_spin_unlock_irqrestore(p, flags)                    \
	do {                                                    \
		CHECK(*(p) == 1 && table_irq == 1 && !(flags)); \
		*(p) = 0;                                       \
		table_irq--;                                    \
	} while (0)
#define smp_processor_id() 3
#define numa_node_id() 1
#define _Q_LOCKED_VAL 1
#define _RET_IP_ 0x9000UL
#define KD_PR_DEBUG(...)                     \
	do {                                 \
		if (0)                       \
			printf(__VA_ARGS__); \
	} while (0)
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
static bool need_resched(void);
static void schedule(void);
static void cpu_relax(void);
static void kd_origin_mutex_lock(struct mutex *lock);
static void kd_origin_mutex_unlock(struct mutex *lock, unsigned long ip);
static bool kd_mutex_task_active(struct task_struct *task);
static bool kd_mutex_task_get(struct task_struct *task);
static void kd_mutex_task_put(struct task_struct *task);
static bool kd_hotlock_is_promoted(unsigned long addr);
static void kd_hotlock_record(unsigned long addr);
static void kd_exe_add(int pid, unsigned long ip, enum kd_exe_lock_kind kind);
static bool kd_exec_native_unlock(unsigned long addr, bool mutex);
static unsigned long kd_read_kernel_gsbase(void);
static int kd_mutex_lock_slowpath_asm(struct kd_mutex *lock,
				      struct kd_mutex_node *node);
static void jump_to_saved_regs(struct pt_regs *regs);
static void jump_to_saved_regs_in_cs(struct pt_regs *regs);
#include "mutex_resource_code.h"

/* Equal table-sized strides force collisions using actual mutex addresses;
 * unlike the removed model, the full 1024-entry table is filled through get(). */
struct origin_slot {
	struct mutex mutex;
	char padding[KD_MUTEX_SHADOW_TABLE_SIZE - sizeof(struct mutex)];
};
static struct origin_slot origins[KD_MUTEX_SHADOW_TABLE_SIZE + 1];
static char shadow_stacks[KD_MUTEX_MAX_NODES][KD_MUTEX_SHADOW_STACK_SIZE];

static void preempt_disable(void)
{
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
	CHECK(waiting_gate && preempt == 1 && migration == 1);
	CHECK(waiting_gate->physical_owner == &peer);
	release_peer(waiting_gate);
	waiting_gate = NULL;
}
static void kd_origin_mutex_lock(struct mutex *lock)
{
	CHECK(lock && !lock->owner && !preempt && !table_irq);
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
static bool kd_hotlock_is_promoted(unsigned long addr)
{
	CHECK(addr);
	return promoted;
}
static void kd_hotlock_record(unsigned long addr)
{
	CHECK(addr);
	samples++;
}
bool kd_mutex_jit_is_enabled(void)
{
	return enabled;
}
static void kd_exe_add(int pid, unsigned long ip, enum kd_exe_lock_kind kind)
{
	CHECK(!pid && ip == 0x8000 && kind == KD_EXE_LOCK_MUTEX && refs);
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
	struct pt_regs entry = { .sp = (unsigned long)&native_stack[16] };

	slow_calls++;
	CHECK(preempt == 1 && migration == 1 && refs == 1);
	CHECK(node->lock == lock && node->task_struct_ptr == current);
	CHECK(node->gsbase == kd_read_kernel_gsbase());
	CHECK(node->cpuid == smp_processor_id() &&
	      node->socket_id == numa_node_id());
	CHECK(node->tail == (int)encode_tail(smp_processor_id(), node->slot));
	CHECK(node->locked && !node->completed && !node->native_resume &&
	      !node->next);
	CHECK(node->saved_ret_addr == 0x8000);
	CHECK(memcmp(&node->regs, &entry, sizeof(entry)) == 0);
	if (direct_packet)
		CHECK(node->saved_rbx == 11 && node->saved_r12 == 12 &&
		      node->saved_r13 == 13 && node->saved_r14 == 14 &&
		      node->saved_r15 == 15 && node->saved_rbp == 16);
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
static void capture_resume(struct pt_regs *regs, int result)
{
	CHECK(!preempt && !migration && !table_irq);
	CHECK(!cpu_shadows.node_slots && !cpu_shadows.resume_node);
	CHECK(!kd_mutex_reserved_nodes.counter && !recycle_on_enable);
	CHECK(memcmp(regs, &expected_regs, sizeof(*regs)) == 0);
	captured_regs = *regs;
	longjmp(resume_target, result);
}
static void jump_to_saved_regs(struct pt_regs *regs)
{
	capture_resume(regs, 3);
}
static void jump_to_saved_regs_in_cs(struct pt_regs *regs)
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
	errors = preempt = migration = table_irq = 0;
	gets = task_puts = refs = adds = acquires = releases = schedules = 0;
	slow_calls = notify_calls = samples = mode = 0;
	kd_mutex_multi_slot_count = kd_mutex_frame_failure_count = 0;
	kd_mutex_node_overflow_count = kd_mutex_jit_resume_count = 0;
	kd_mutex_origin_acquires = kd_mutex_origin_releases = 0;
	kd_mutex_reserved_nodes.counter = 0;
	promoted = enabled = true;
	task_failure = active_override = borrowed = false;
	schedule_wanted = recycle_on_enable = direct_packet = false;
	waiting_gate = release_gate = NULL;
	recycle_node = NULL;
	memset(&expected_regs, 0x51, sizeof(expected_regs));
	expected_regs.sp = (unsigned long)&native_stack[20];
	expected_regs.ip = 0x8765;
	memset(&captured_regs, 0, sizeof(captured_regs));
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
			kd_mutex_reserved_nodes.counter =
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
			CHECK(kd_mutex_reserved_nodes.counter ==
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
				CHECK(kd_mutex_reserved_nodes.counter ==
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
	CHECK(!cpu_shadows.node_slots && !kd_mutex_reserved_nodes.counter);
	memcpy(before, kd_mutex_nodes, sizeof(before));
	kd_mutex_release_node(node);
	kd_mutex_release_node(NULL);
	struct kd_mutex_node bad = { .slot = -1 };
	kd_mutex_release_node(&bad);
	bad.slot = KD_MUTEX_MAX_NODES;
	kd_mutex_release_node(&bad);
	CHECK(errors == 4 && kd_mutex_frame_failure_count == 4);
	CHECK(!cpu_shadows.node_slots && !kd_mutex_reserved_nodes.counter);
	CHECK(memcmp(before, kd_mutex_nodes, sizeof(before)) == 0);
}

static unsigned int shadow_count(void)
{
	unsigned int count = 0;
	for (int i = 0; i < KD_MUTEX_SHADOW_TABLE_SIZE; i++)
		count += kd_mutex_shadows[i].mutex_addr != 0;
	return count;
}
static void check_shadow_table(void)
{
	struct kd_mutex_shadow_entry before[KD_MUTEX_SHADOW_TABLE_SIZE];
	struct kd_mutex *entries[KD_MUTEX_SHADOW_TABLE_SIZE];
	struct mutex *missing = &origins[KD_MUTEX_SHADOW_TABLE_SIZE].mutex;

	reset();
	CHECK(!find_kd_mutex_shadow(&origins[0].mutex) && !shadow_count());
	for (int i = 0; i < KD_MUTEX_SHADOW_TABLE_SIZE; i++) {
		entries[i] = get_kd_mutex_shadow(&origins[i].mutex);
		CHECK(entries[i] && entries[i]->origin_mutex_addr ==
					    (unsigned long)&origins[i].mutex);
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
	for (int i = 0; i < KD_MUTEX_SHADOW_TABLE_SIZE; i++) {
		CHECK(get_kd_mutex_shadow(&origins[i].mutex) == entries[i]);
		CHECK(find_kd_mutex_shadow(&origins[i].mutex) == entries[i]);
	}
	CHECK(!find_kd_mutex_shadow(missing));
	__kd_mutex_lock(missing, (unsigned long)&native_stack[16], 0x8000);
	CHECK(errors == 1 && !gets && !adds && !slow_calls && !refs);
	CHECK(missing->owner == current && acquires == 1);
	__kd_mutex_unlock(missing, 0, 0x9000);
	CHECK(!missing->owner && releases == 1 && !task_puts);
	CHECK(!cpu_shadows.node_slots && !kd_mutex_reserved_nodes.counter);
	CHECK(memcmp(before, kd_mutex_shadows, sizeof(before)) == 0);
	CHECK(!table_irq && !kd_mutex_shadow_lock);
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
			enabled = reason != 2;
			task_failure = reason == 3;
			__kd_mutex_lock(lock, (unsigned long)&native_stack[16],
					0x8000);
			CHECK(lock->owner == current && acquires == 1);
			CHECK(gets == (unsigned int)(reason == 3) &&
			      !task_puts && !refs && !adds);
			CHECK(shadow_count() ==
			      (unsigned int)(existing || reason == 3));
			CHECK(samples == (unsigned int)(reason == 1));
			CHECK(!slow_calls && !cpu_shadows.node_slots &&
			      !kd_mutex_reserved_nodes.counter);
			__kd_mutex_unlock(lock, 0, 0x9000);
			CHECK(!lock->owner && releases == 1 && !task_puts);
			CHECK(shadow_count() ==
			      (unsigned int)(existing || reason == 3));
			CHECK(!errors && !preempt && !migration && !table_irq);
		}
	}
}

static void hold_peer(struct kd_mutex *gate)
{
	gate->locked = _Q_LOCKED_COMBINER_VAL;
	gate->physical_owner = &peer;
	((struct mutex *)gate->origin_mutex_addr)->owner = &peer;
	kd_mutex_origin_acquires = 1;
}
static void check_hook_nodes(void)
{
	/* Full slots and absent stacks converge on the real no-node wait path.
	 * It must release scheduler state, acquire L, then later unlock L before S. */
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
		CHECK(schedules == (unsigned int)(resource != 0) && !preempt &&
		      !migration);
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
				_kd_mutex_lock(gate,
					       (unsigned long)&native_stack[16],
					       0x8000, 11, 12, 13, 14, 15, 16);
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
		CHECK(!kd_mutex_reserved_nodes.counter && !preempt &&
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
				borrowed = true;
				__kd_mutex_unlock(lock, 0, 0x9000);
				CHECK(notify_calls == 1 && !releases &&
				      !task_puts && refs == 1);
				CHECK(gate->physical_owner == &peer &&
				      lock->owner == &peer);
			}
			release_peer(gate);
		}
		CHECK(!lock->owner && !gate->physical_owner && !gate->locked);
		CHECK(kd_mutex_origin_acquires == kd_mutex_origin_releases);
	}
}

int main(void)
{
	check_nodes();
	check_shadow_table();
	check_hook_fallbacks();
	check_hook_nodes();
	check_slowpath_packets();
	printf("production mutex resources: %u checks, 0 failures; nodes=%d shadow=%d regs=%zu\n",
	       checks, KD_MUTEX_MAX_NODES, KD_MUTEX_SHADOW_TABLE_SIZE,
	       sizeof(struct pt_regs));
	return 0;
}
