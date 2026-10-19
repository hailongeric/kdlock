/* SPDX-License-Identifier: GPL-2.0 */
/* Actual abortable OSQ and node-pool decisions; callbacks replace hardware
 * atomics and scheduling with explicit adversarial queue interleavings. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef struct { int counter; } atomic_t;
typedef struct { unsigned long counter; } atomic_long_t;
typedef int raw_spinlock_t;
struct optimistic_spin_queue { atomic_t tail; };
struct task_struct { int id; bool on_cpu; };
#include "mutex_osq_types.h"

#define CPUS 4
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL osq line %d: %s\n", __LINE__, #c); exit(1); } } while (0)
static bool expecting_bug;
static jmp_buf bug_target;
#define BUG_ON(c) do { if (c) { if (expecting_bug) longjmp(bug_target, 1); CHECK(!(c)); } } while (0)
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x) = (v))
#define likely(x) (x)
#define unlikely(x) (x)
#define BIT(x) (1UL << (x))
#define barrier() __asm__ __volatile__("" : : : "memory")
#define smp_wmb() barrier()
#define smp_load_acquire(p) (*(p))
#define data_race(x) (x)
#define OSQ_UNLOCKED_VAL 0
#define TASK_RUNNING 0
#define container_of(p,t,m) ((t *)((char *)(p) - offsetof(t,m)))
static int cpu, preempt_depth = 1;
static unsigned int steps, schedules, checks;
static unsigned long expected_schedule_slots;
static bool resched, acquire_now = true;
static struct task_struct task = { 1, true }, peer = { 2, true };
static struct task_struct *current = &task;
static struct kd_mutex lock, other_lock;
static struct kd_mutex_node kd_mutex_nodes[KD_MUTEX_MAX_NODES][CPUS];
static struct kd_mutex_cpu_state kd_mutex_shadows[CPUS];
static int kd_mutex_reserved_nodes[CPUS];
static unsigned long kd_mutex_multi_slot_count[CPUS], kd_mutex_frame_failure_count[CPUS];
#define smp_processor_id() cpu
#define this_cpu_ptr(p) (*(p) + cpu)
#define per_cpu_ptr(p,c) (*(p) + (c))
#define this_cpu_inc(v) (++(v)[cpu])
#define this_cpu_dec_return(v) (--(v)[cpu])
#define KD_PR_ERR(...) CHECK(false)
static void (*poll_hook)(void), (*relax_hook)(void), (*cas_hook)(void *);
static void before_cas(void *address)
{
	CHECK(++steps < 200);
	if (cas_hook)
		cas_hook(address);
}
#define cmpxchg(p,o,n) ({ __typeof__(p) ptr_ = (p); __typeof__(*ptr_) old_ = (o); before_cas(ptr_); __typeof__(*ptr_) got_ = *ptr_; if (got_ == old_) *ptr_ = (n); got_; })
#define xchg(p,n) ({ __typeof__(p) ptr_ = (p); __typeof__(*ptr_) got_ = *ptr_; *ptr_ = (n); got_; })
#define atomic_xchg(p,n) xchg(&(p)->counter,n)
#define atomic_read(p) ((p)->counter)
#define atomic_cmpxchg_acquire(p,o,n) cmpxchg(&(p)->counter,o,n)
#define atomic_cmpxchg_release(p,o,n) cmpxchg(&(p)->counter,o,n)
static bool need_resched(void) { return resched; }
static bool vcpu_is_preempted(int id) { CHECK(id >= 0 && id < CPUS); return false; }
static void cpu_relax(void)
{
	CHECK(++steps < 200);
	if (relax_hook)
		relax_hook();
}
static void before_poll(void)
{
	CHECK(++steps < 200);
	if (poll_hook)
		poll_hook();
}
#define smp_cond_load_relaxed(p,cond) ({ int VAL; for (;;) { before_poll(); VAL = *(p); if (cond) break; cpu_relax(); } VAL; })
static struct task_struct *kd_owner(struct kd_mutex *word)
{
	return (struct task_struct *)word->owner.counter;
}
static bool owner_on_cpu(struct task_struct *owner) { return owner->on_cpu; }
static struct task_struct *kd_try_common(struct kd_mutex *word, bool handoff)
{
	CHECK(!handoff && preempt_depth == 1);
	if (acquire_now) {
		word->owner.counter = (unsigned long)current;
		return NULL;
	}
	return kd_owner(word);
}
static void __set_current_state(int state) { CHECK(state == TASK_RUNNING); }
static void kd_local_schedule(void)
{
	CHECK(preempt_depth == 1);
	CHECK(kd_mutex_shadows[cpu].node_slots == expected_schedule_slots);
	for (int slot = 0; slot < KD_MUTEX_MAX_NODES; slot++)
		CHECK(kd_mutex_nodes[slot][cpu].osq.locked == KD_MUTEX_OSQ_IDLE);
	schedules++;
}
#include "mutex_osq_actual.h"

static struct kd_mutex_osq_node *a, *b, *c, *p;
static void reset(void)
{
	memset(kd_mutex_nodes, 0, sizeof(kd_mutex_nodes));
	memset(kd_mutex_shadows, 0, sizeof(kd_mutex_shadows));
	memset(kd_mutex_reserved_nodes, 0, sizeof(kd_mutex_reserved_nodes));
	memset(kd_mutex_multi_slot_count, 0, sizeof(kd_mutex_multi_slot_count));
	memset(kd_mutex_frame_failure_count, 0, sizeof(kd_mutex_frame_failure_count));
	memset(&lock, 0, sizeof(lock));
	memset(&other_lock, 0, sizeof(other_lock));
	for (int slot = 0; slot < KD_MUTEX_MAX_NODES; slot++) {
		for (int id = 0; id < CPUS; id++) {
			struct kd_mutex_node *node = &kd_mutex_nodes[slot][id];
			node->slot = slot;
			node->shadow_stack_base = node;
			node->count_seq = 42;
			node->osq.tail = kd_mutex_encode_tail(id, slot);
			node->osq.locked = KD_MUTEX_OSQ_IDLE;
		}
	}
	cpu = steps = schedules = 0;
	preempt_depth = 1;
	resched = false;
	acquire_now = true;
	expected_schedule_slots = 0;
	poll_hook = relax_hook = NULL;
	cas_hook = NULL;
	a = b = c = p = NULL;
	lock.owner.counter = (unsigned long)&peer;
}
static struct kd_mutex_osq_node *reserve_at(int id)
{
	int save = cpu;
	cpu = id;
	struct kd_mutex_osq_node *node = kd_mutex_osq_node_get(&lock);
	CHECK(node && kd_mutex_reserved_nodes[cpu] == 1);
	cpu = save;
	return node;
}
static void head_at(int id)
{
	a = reserve_at(id);
	int save = cpu;
	cpu = id;
	CHECK(kd_mutex_osq_lock(&lock.osq, a));
	cpu = save;
}
static void release_at(struct kd_mutex_osq_node *node)
{
	int save = cpu;
	cpu = node_cpu(node);
	kd_mutex_osq_node_put(node);
	CHECK(!kd_mutex_reserved_nodes[cpu] && !kd_mutex_shadows[cpu].node_slots);
	cpu = save;
}
static void cancel_poll(void)
{
	poll_hook = NULL;
	resched = true;
}
static void grant_poll(void)
{
	poll_hook = NULL;
	CHECK(a->next == b && b->prev == a);
	kd_mutex_osq_unlock(&lock.osq, a);
}
static void add_successor_poll(void)
{
	poll_hook = NULL;
	c = reserve_at(3);
	c->locked = KD_MUTEX_OSQ_WAITING;
	c->prev = b;
	CHECK(atomic_xchg(&lock.osq.tail, c->tail) == (int)b->tail);
	WRITE_ONCE(b->next, c);
	resched = true;
}
static void grant_during_cancel(void *address)
{
	if (address != &a->next)
		return;
	cas_hook = NULL;
	CHECK(a->next == b);
	kd_mutex_osq_unlock(&lock.osq, a);
}
static void replace_predecessor(void *address)
{
	if (address != &a->next)
		return;
	cas_hook = NULL;
	/* Predecessor A's unqueue has stabilized this B and is completing C. */
	a->next = NULL;
	WRITE_ONCE(b->prev, p);
	WRITE_ONCE(p->next, b);
	osq_retire(a);
}
static void delayed_link(void)
{
	relax_hook = NULL;
	CHECK(a->next == NULL && b->prev == a);
	WRITE_ONCE(a->next, b);
}

static void encoding_and_reuse(void)
{
	reset();
	for (int id = 0; id < CPUS; id++) {
		for (int slot = 0; slot < KD_MUTEX_MAX_NODES; slot++) {
			struct kd_mutex_osq_node *node = &kd_mutex_nodes[slot][id].osq;
			CHECK(decode_tail(node->tail) == node && node_cpu(node) == id);
		}
	}
	a = kd_mutex_osq_node_get(&lock);
	CHECK(a == &kd_mutex_nodes[0][0].osq && kd_mutex_reserved_nodes[0] == 1);
	a->next = a->prev = &kd_mutex_nodes[3][3].osq;
	CHECK(kd_mutex_osq_lock(&lock.osq, a) && !a->next && !a->prev);
	kd_mutex_osq_unlock(&lock.osq, a);
	CHECK(!lock.osq.tail.counter && a->locked == KD_MUTEX_OSQ_IDLE);
	release_at(a);
	CHECK(kd_mutex_nodes[0][0].count_seq == 42);
	/* A live OSQ subrecord must not be returned to the shared pool. */
	a = kd_mutex_osq_node_get(&lock);
	a->locked = KD_MUTEX_OSQ_WAITING;
	expecting_bug = true;
	if (!setjmp(bug_target)) {
		kd_mutex_release_node(&kd_mutex_nodes[0][0]);
		CHECK(false);
	}
	expecting_bug = false;
	a->locked = KD_MUTEX_OSQ_IDLE;
	release_at(a);
	checks++;
}
static void queued_grant_and_cancel(void)
{
	for (int mode = 0; mode < 4; mode++) {
		reset();
		head_at(2);
		b = kd_mutex_osq_node_get(&lock);
		poll_hook = mode == 0 ? grant_poll : mode == 2 ? add_successor_poll : cancel_poll;
		if (mode == 3)
			cas_hook = grant_during_cancel;
		bool acquired = kd_mutex_osq_lock(&lock.osq, b);
		CHECK(acquired == (mode == 0 || mode == 3));
		CHECK(kd_mutex_reserved_nodes[0] == 1 && kd_mutex_reserved_nodes[2] == 1);
		if (acquired) {
			CHECK(a->locked == KD_MUTEX_OSQ_IDLE && b->locked == KD_MUTEX_OSQ_GRANTED);
			kd_mutex_osq_unlock(&lock.osq, b);
			CHECK(!lock.osq.tail.counter);
		} else if (mode == 1) {
			CHECK(b->locked == KD_MUTEX_OSQ_IDLE && !a->next);
			CHECK(lock.osq.tail.counter == (int)a->tail);
			kd_mutex_osq_unlock(&lock.osq, a);
		} else {
			CHECK(a->next == c && c->prev == a && b->locked == KD_MUTEX_OSQ_IDLE);
			CHECK(lock.osq.tail.counter == (int)c->tail);
			kd_mutex_osq_unlock(&lock.osq, a);
			CHECK(c->locked == KD_MUTEX_OSQ_GRANTED);
			kd_mutex_osq_unlock(&lock.osq, c);
			release_at(c);
		}
		release_at(b);
		release_at(a);
		checks++;
	}
}
static void predecessor_replacement_and_delayed_link(void)
{
	reset();
	head_at(2);
	p = reserve_at(1);
	p->locked = KD_MUTEX_OSQ_WAITING;
	p->next = a;
	a->prev = p;
	b = kd_mutex_osq_node_get(&lock);
	poll_hook = cancel_poll;
	cas_hook = replace_predecessor;
	CHECK(!kd_mutex_osq_lock(&lock.osq, b));
	CHECK(lock.osq.tail.counter == (int)p->tail && !p->next);
	CHECK(b->locked == KD_MUTEX_OSQ_IDLE && a->locked == KD_MUTEX_OSQ_IDLE);
	kd_mutex_osq_unlock(&lock.osq, p);
	release_at(a);
	release_at(b);
	release_at(p);
	checks++;
	reset();
	head_at(2);
	b = kd_mutex_osq_node_get(&lock);
	b->locked = KD_MUTEX_OSQ_WAITING;
	b->prev = a;
	CHECK(atomic_xchg(&lock.osq.tail, b->tail) == (int)a->tail);
	relax_hook = delayed_link;
	kd_mutex_osq_unlock(&lock.osq, a);
	CHECK(!relax_hook && b->locked == KD_MUTEX_OSQ_GRANTED);
	kd_mutex_osq_unlock(&lock.osq, b);
	release_at(a);
	release_at(b);
	checks++;
}
static void shared_spin_lifetimes(void)
{
	for (int borrowed = 0; borrowed < 2; borrowed++) {
		for (int cancel = 0; cancel < 2; cancel++) {
			struct kd_mutex_node *origin = NULL, before;
			reset();
			if (borrowed) {
				origin = kd_mutex_reserve_node();
				origin->lock = &lock;
				origin->task_struct_ptr = current;
				origin->counted_lock = &lock;
				origin->next = &kd_mutex_nodes[2][3];
				origin->completed = 1;
				origin->locked = 1;
				origin->regs.r10 = 0xfeed;
				origin->gsbase = 0xbeef;
				before = *origin;
			}
			if (cancel) {
				head_at(2);
				poll_hook = cancel_poll;
				expected_schedule_slots = borrowed ? 1 : 0;
			}
			CHECK(kd_local_spin(&lock, false, origin) == !cancel);
			CHECK(kd_mutex_reserved_nodes[0] == borrowed);
			CHECK(kd_mutex_shadows[0].node_slots == (unsigned long)borrowed);
			CHECK(schedules == (unsigned int)cancel);
			if (borrowed) {
				CHECK(!memcmp(origin, &before, sizeof(before)));
				origin->counted_lock = NULL;
				kd_mutex_release_node(origin);
			}
			if (cancel) {
				kd_mutex_osq_unlock(&lock.osq, a);
				release_at(a);
			}
			checks++;
		}
	}
	reset();
	/* A sleeping delegation anchor occupies slot 0. Native OSQ uses slot 1
	 * and retires it without changing that anchor's reservation or packet. */
	struct kd_mutex_node *anchor = kd_mutex_reserve_node();
	anchor->lock = &other_lock;
	anchor->counted_lock = &other_lock;
	anchor->regs.ip = 0x1234;
	struct kd_mutex_node saved = *anchor;
	CHECK(kd_local_spin(&lock, false, NULL));
	CHECK(kd_mutex_multi_slot_count[0] == 1 && kd_mutex_reserved_nodes[0] == 1);
	CHECK(kd_mutex_shadows[0].node_slots == 1 && !memcmp(anchor, &saved, sizeof(saved)));
	anchor->counted_lock = NULL;
	kd_mutex_release_node(anchor);
	checks++;
	reset();
	for (int slot = 0; slot < KD_MUTEX_MAX_NODES; slot++)
		CHECK(kd_mutex_reserve_node());
	struct kd_mutex_node full[KD_MUTEX_MAX_NODES][CPUS];
	memcpy(full, kd_mutex_nodes, sizeof(full));
	CHECK(!kd_local_spin(&lock, false, NULL));
	CHECK(kd_mutex_reserved_nodes[0] == KD_MUTEX_MAX_NODES && kd_mutex_shadows[0].node_slots == 15);
	CHECK(!memcmp(full, kd_mutex_nodes, sizeof(full)) && !lock.osq.tail.counter && !schedules);
	for (int slot = 0; slot < KD_MUTEX_MAX_NODES; slot++)
		kd_mutex_release_node(&kd_mutex_nodes[slot][0]);
	checks++;
}
int main(void)
{
	CHECK(sizeof(struct kd_mutex) == 32 && _Alignof(struct kd_mutex) == 8);
	CHECK(sizeof(struct kd_mutex_node) == 320 && _Alignof(struct kd_mutex_node) == 64);
	CHECK(sizeof(struct kd_mutex_osq_node) == 24 && offsetof(struct kd_mutex_node, osq) == 104);
	encoding_and_reuse();
	queued_grant_and_cancel();
	predecessor_replacement_and_delayed_link();
	shared_spin_lifetimes();
	printf("mutex osq production: %u scenarios PASS\n", checks);
	return 0;
}
