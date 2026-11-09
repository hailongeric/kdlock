/* SPDX-License-Identifier: GPL-2.0 */
/* Production retirement ordering with deterministic CPU/work and lease APIs.
 * The retired root becomes inaccessible exactly when its slot is reusable. */
#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <pthread.h>

typedef uint32_t u32;
#define CPUS 2
#define KD_MUTEX_MAX_NODES 4
#define KD_MUTEX_TAIL_CPU_OFFSET 4
#define KD_MUTEX_TAIL_IDX_OFFSET 0
#define KD_MUTEX_OSQ_IDLE 0
#define BIT(index) (1UL << (index))
#define READ_ONCE(value) (value)
#define BUG_ON(value) assert(!(value))
#define KD_PR_ERR(...) ((void)0)
#define unlikely(value) (value)
struct guard { pthread_mutex_t mutex; pthread_t owner; bool held; };
struct list_head { bool linked; };
static bool list_empty(const struct list_head *head) { return !head->linked; }
static void list_del_init(struct list_head *head) { assert(head->linked); head->linked = false; }
struct module { unsigned int refs; } worker_module, capture_module;
#define THIS_MODULE (&worker_module)
struct task_struct { unsigned int id; };
struct kd_wait_request { unsigned int state; struct guard *guard; void *selection; };
struct kd_wait_node { void *queue_head; };
struct kd_mutex_node {
	int slot;
	struct { u32 tail; unsigned int locked; } osq;
	void *counted_lock;
	unsigned long count_seq;
	struct kd_mutex_node *next;
	void *lock;
	struct task_struct *task_struct_ptr;
	unsigned long gsbase;
	void *shadow_stack_base;
};
struct kd_mutex_cpu_state { unsigned long node_slots; };
struct kd_service_root;
struct kd_mutex_wait_record {
	struct kd_wait_request request;
	struct kd_wait_node member;
	bool request_live;
	struct kd_service_root *service;
};
struct kd_exec_continuation { unsigned int state; };
struct kd_service_root {
	struct kd_mutex_node *node;
	struct kd_mutex_node spill_node;
	struct { struct kd_wait_request request; } owner;
	struct kd_exec_continuation continuation;
	struct { struct module *owner; } completion;
	struct kd_wait_node dispatch_member;
	struct list_head active_link;
	struct guard lifecycle_guard;
	int origin_cpu;
	unsigned int actor;
	bool pooled, native_handoff;
};
enum { KD_SERVICE_EXECUTOR = 1, KD_SERVICE_FINISHED = 2,
	KD_CONT_HANDED_OFF = 1, KD_CONT_RETIRED = 2,
	KD_WAIT_RETURN_ACK = 3, KD_WAIT_RETIRED = 4,
	KD_WAIT_CANCEL_ACK = 5, KD_WAIT_ACQUIRED = 6 };
static struct kd_mutex_node kd_mutex_nodes[KD_MUTEX_MAX_NODES][CPUS];
static struct kd_mutex_wait_record records[KD_MUTEX_MAX_NODES][CPUS];
static struct kd_mutex_cpu_state kd_mutex_shadows[CPUS];
static int kd_mutex_reserved_nodes[CPUS], kd_mutex_frame_failure_count[CPUS];
static struct guard kd_service_dispatch_guard = { .mutex = PTHREAD_MUTEX_INITIALIZER };
static int nr_cpu_ids = CPUS;
static unsigned int current_cpu = 1, pins, hotplug_readers, held_guards;
static unsigned int dispatched, source_puts, stack_puts, spill_frees;
static bool online[CPUS] = { true, true };
static bool observe_reuse, root_accessible, offline_pair;
static unsigned int offline_publications;
static pthread_barrier_t offline_barrier;
static size_t page_size;
static struct kd_service_root *observed_root;
#define per_cpu_ptr(pointer, cpu) (&(*(pointer))[cpu])
#define per_cpu(name, cpu) ((name)[cpu])
#define this_cpu_ptr(pointer) per_cpu_ptr(pointer, current_cpu)
#define this_cpu_inc(name) (++(name)[current_cpu])
#define this_cpu_dec_return(name) (--(name)[current_cpu])
static bool cpu_possible(int cpu) { return cpu >= 0 && cpu < CPUS; }
static bool cpu_online(int cpu) { assert(cpu_possible(cpu)); return online[cpu]; }
static unsigned int raw_smp_processor_id(void) { assert(pins); return current_cpu; }
static void preempt_disable(void) { ++pins; }
static void preempt_enable(void)
{
	assert(pins); --pins;
	if (!pins && !root_accessible)
		assert(!kd_mutex_reserved_nodes[current_cpu]);
}
static unsigned long _raw_spin_lock_irqsave(struct guard *guard)
{
	assert(!pthread_mutex_lock(&guard->mutex));
	assert(!guard->held); guard->owner = pthread_self();
	guard->held = true; ++held_guards; return 0;
}
static void _raw_spin_unlock_irqrestore(struct guard *guard, unsigned long flags)
{
	assert(!flags && guard->held && held_guards && pthread_equal(guard->owner, pthread_self()));
	guard->held = false; --held_guards;
	assert(!pthread_mutex_unlock(&guard->mutex));
}
static void make_root_inaccessible(void)
{
	assert(root_accessible && source_puts == 1 && stack_puts == 1);
	assert(!mprotect(observed_root, page_size, PROT_NONE));
	root_accessible = false;
}
static void observe_write(void *address)
{
	if (offline_pair && address == &kd_mutex_shadows[0].node_slots) {
		assert(kd_service_dispatch_guard.held &&
		       pthread_equal(kd_service_dispatch_guard.owner, pthread_self()));
		assert(kd_mutex_reserved_nodes[0] == __builtin_popcountl(kd_mutex_shadows[0].node_slots));
		++offline_publications;
	}
	if (!observe_reuse)
		return;
	for (unsigned int cpu = 0; cpu < CPUS; ++cpu)
		if (address == &kd_mutex_shadows[cpu].node_slots && !kd_mutex_shadows[cpu].node_slots) {
			if (!online[cpu])
				assert(!kd_mutex_reserved_nodes[cpu] && kd_service_dispatch_guard.held);
			make_root_inaccessible();
		}
}
#define WRITE_ONCE(value, next) do { (value) = (next); observe_write(&(value)); } while (0)
static struct kd_mutex_wait_record *kd_mutex_wait_record(struct kd_mutex_node *node)
{
	for (unsigned int slot = 0; slot < KD_MUTEX_MAX_NODES; ++slot)
		for (unsigned int cpu = 0; cpu < CPUS; ++cpu)
			if (node == &kd_mutex_nodes[slot][cpu])
				return &records[slot][cpu];
	abort();
}
static struct kd_wait_node *kd_mutex_request_member(struct kd_mutex_node *node)
{ return &kd_mutex_wait_record(node)->member; }
static void kd_wait_finish_local_locked(struct kd_wait_request *request)
{ (void)request; abort(); }
static void kd_wait_set_state_locked(struct kd_wait_request *request, unsigned int state)
{
	assert(root_accessible && request == &observed_root->owner.request);
	assert(observed_root->lifecycle_guard.held && state == KD_WAIT_RETIRED);
	assert(observed_root->continuation.state == KD_CONT_RETIRED);
	request->state = state;
}
static int kd_exec_cont_retire(struct kd_exec_continuation *cont)
{
	assert(root_accessible && cont == &observed_root->continuation);
	assert(!observed_root->active_link.linked && !held_guards && !pins);
	assert(cont->state == KD_CONT_HANDED_OFF);
	cont->state = KD_CONT_RETIRED;
	++source_puts; ++stack_puts;
	return 0;
}
static void cpus_read_lock(void) { assert(!held_guards && !pins); ++hotplug_readers; }
static void cpus_read_unlock(void) { assert(hotplug_readers == 1); --hotplug_readers; }
static long work_on_cpu(int cpu, long (*function)(void *), void *argument)
{
	unsigned int saved_cpu = current_cpu;
	long result;
	assert(hotplug_readers == 1 && !held_guards && !pins && online[cpu]);
	++dispatched; current_cpu = (unsigned int)cpu;
	result = function(argument);
	assert(hotplug_readers == 1 && !root_accessible);
	current_cpu = saved_cpu;
	return result;
}
static void module_put(struct module *owner)
{ assert(!root_accessible && !held_guards && !hotplug_readers && owner->refs); --owner->refs; }
static void vfree(void *pointer)
{ assert(!pins && !held_guards && pointer); free(pointer); ++spill_frees; }
static void kfree(void *pointer)
{ assert(pointer == observed_root && !pins && !held_guards); make_root_inaccessible(); }
#include "retirement_production.h"

static void *offline_release_thread(void *argument)
{
	int result = pthread_barrier_wait(&offline_barrier);
	assert(!result || result == PTHREAD_BARRIER_SERIAL_THREAD);
	kd_service_release_offline_node(argument);
	return NULL;
}

static void run_offline_pair(void)
{
	struct kd_service_root roots[2] = { 0 };
	pthread_t tasks[2];

	offline_pair = true; online[0] = false;
	/* Stand in for the dispatchers' hotplug exclusion; the real shared read
	 * lock is not the serialization between these two simultaneous cleanups. */
	hotplug_readers = 1;
	kd_mutex_reserved_nodes[0] = 2;
	kd_mutex_shadows[0].node_slots = BIT(0) | BIT(1);
	assert(!pthread_barrier_init(&offline_barrier, NULL, 2));
	for (unsigned int slot = 0; slot < 2; ++slot) {
		struct kd_mutex_node *node = &kd_mutex_nodes[slot][0];
		roots[slot].pooled = true;
		roots[slot].origin_cpu = 0;
		roots[slot].node = node;
		roots[slot].owner.request.state = KD_WAIT_RETIRED;
		node->slot = (int)slot;
		node->osq.tail = kd_mutex_encode_tail(0, (int)slot);
		records[slot][0].service = &roots[slot];
		assert(!pthread_create(&tasks[slot], NULL, offline_release_thread, &roots[slot]));
	}
	for (unsigned int slot = 0; slot < 2; ++slot)
		assert(!pthread_join(tasks[slot], NULL));
	assert(!pthread_barrier_destroy(&offline_barrier));
	assert(offline_publications == 2 && !held_guards && !kd_service_dispatch_guard.held);
	assert(!kd_mutex_reserved_nodes[0] && !kd_mutex_shadows[0].node_slots);
	hotplug_readers = 0;
	puts("PASS production offline service retirement: two simultaneous slot releases serialized by the supplied dispatch guard; count before reuse");
}

int main(int argc, char **argv)
{
	struct kd_service_root *root;
	struct kd_mutex_node *node;
	bool spill;
	assert(argc == 2);
	if (!strcmp(argv[1], "offline_pair")) {
		run_offline_pair();
		return 0;
	}
	page_size = (size_t)sysconf(_SC_PAGESIZE);
	assert(sizeof(*root) <= page_size);
	root = mmap(NULL, page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	assert(root != MAP_FAILED);
	observed_root = root; root_accessible = true;
	spill = !strcmp(argv[1], "spill");
	root->pooled = !spill; root->native_handoff = true;
	root->origin_cpu = 0; root->actor = KD_SERVICE_EXECUTOR;
	root->continuation.state = KD_CONT_HANDED_OFF;
	root->owner.request.state = KD_WAIT_RETURN_ACK;
	root->active_link.linked = true; root->completion.owner = &capture_module;
	root->lifecycle_guard = (struct guard) { .mutex = PTHREAD_MUTEX_INITIALIZER };
	worker_module.refs = capture_module.refs = 1;
	node = spill ? &root->spill_node : &kd_mutex_nodes[2][0];
	root->node = node; node->slot = 2; node->osq.tail = kd_mutex_encode_tail(0, 2);
	if (spill)
		node->shadow_stack_base = malloc(64);
	else {
		records[2][0].service = root;
		kd_mutex_shadows[0].node_slots = BIT(2);
		kd_mutex_reserved_nodes[0] = 1;
	}
	if (!strcmp(argv[1], "offline")) online[0] = false;
	if (!strcmp(argv[1], "wrong_home")) root->origin_cpu = 1;
	if (!strcmp(argv[1], "wrong_tail")) ++node->osq.tail;
	if (!strcmp(argv[1], "wrong_root")) records[2][0].service = NULL;
	if (!strcmp(argv[1], "live_request")) records[2][0].request_live = true;
	if (!strcmp(argv[1], "queue")) records[2][0].member.queue_head = root;
	if (!strcmp(argv[1], "selection")) records[2][0].request.selection = root;
	if (!strcmp(argv[1], "count")) node->count_seq = 1;
	if (!strcmp(argv[1], "osq")) node->osq.locked = 1;
	if (!strcmp(argv[1], "missing_slot")) kd_mutex_shadows[0].node_slots = 0;
	observe_reuse = true;
	kd_service_finish_handoff(root);
	assert(!root_accessible && !worker_module.refs && !capture_module.refs);
	assert(!pins && !held_guards && !hotplug_readers);
	assert(source_puts == 1 && stack_puts == 1);
	assert(dispatched == (unsigned int)(!spill && online[0]));
	assert(spill_frees == spill);
	for (unsigned int cpu = 0; cpu < CPUS; ++cpu)
		assert(!kd_mutex_shadows[cpu].node_slots && !kd_mutex_reserved_nodes[cpu] &&
		       !kd_mutex_frame_failure_count[cpu]);
	assert(!munmap(root, page_size));
	printf("PASS production service retirement: %s; final slot access, observation/lease order and saved module references; supplied CPU/work APIs\n", argv[1]);
	return 0;
}
