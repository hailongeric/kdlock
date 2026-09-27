/* SPDX-License-Identifier: GPL-2.0 */
/* Guest userspace primitives around actual queue selection and trace code. */
#include <assert.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define NUMA_AWARE
#define KDLOCK_SELFTEST
#define noinline __attribute__((noinline))
#define IRQ_NUMA_NODE 255
#define module_param_named(...)
#define module_param_array_named(...)
#define MODULE_PARM_DESC(...)
#define READ_ONCE(x) (x)
#define this_cpu_ptr(p) (p)
#define raw_smp_processor_id() 2U
#define numa_node_id() 0U
#define min(a, b) ((a) < (b) ? (a) : (b))
#define smp_store_release(p, v) __atomic_store_n(p, v, __ATOMIC_RELEASE)
#define smp_load_acquire(p) __atomic_load_n(p, __ATOMIC_ACQUIRE)

typedef uint16_t u16;
typedef atomic_int atomic_t;
#define ATOMIC_INIT(v) ATOMIC_VAR_INIT(v)
#define atomic_read(p) atomic_load(p)
#define atomic_set(p, v) atomic_store(p, v)
static int atomic_cmpxchg(atomic_t *value, int expected, int replacement)
{
	atomic_compare_exchange_strong(value, &expected, replacement);
	return expected;
}

struct task_struct {
	int pid;
} task = { 99 }, request_task = { 10 }, rtask = { 40 }, stask = { 41 };
static struct task_struct *current = &task;
struct qspinlock {
	int value;
} lock, child_lock;
struct kd_spin_continuation {
 struct { struct task_struct *logical_task; unsigned long outer_lock_addr; } frame;
};
struct kd_spin_node {
	struct kd_spin_node *next;
	struct kd_spin_continuation *execution;
	int socket_id, cpuid;
	unsigned long rsp;
};
struct kd_spin_cpu_state {
	struct kd_spin_node *local_queue_head, *local_queue_tail;
	unsigned long lock_addr[8];
} kd_spin_cpu;
static unsigned int kd_spin_lock_stack_depth(const struct kd_spin_cpu_state *ptr)
{
	(void)ptr;
	return 2;
}

static char messages[512][2048];
static unsigned int events, checks;
#define message messages[events - 1]
#define pr_info(...)                                              \
	do {                                                      \
		assert(events < 512);                             \
		snprintf(messages[events++], sizeof(messages[0]), \
			 __VA_ARGS__);                            \
	} while (0)
#define CHECK(x)           \
	do {               \
		assert(x); \
		checks++;  \
	} while (0)

#include "deferred_trace_production.h"

static void reset_trace(void)
{
	memset(kd_deferred_events, 0, sizeof(kd_deferred_events));
	memset(kd_deferred_trace_locks, 0, sizeof(kd_deferred_trace_locks));
	kd_deferred_trace_lock_count = 0;
	kd_deferred_trace_lock = 0;
	kd_deferred_buffered = false;
	atomic_set(&kd_deferred_event_count, 0);
	atomic_set(&kd_deferred_overflow, 0);
	kd_spin_cpu = (struct kd_spin_cpu_state){};
	task.pid = 99;
	events = 0;
}

static void live_trace(void)
{
	u16 scan_left = 512;
	struct kd_spin_node s = { .execution = &(struct kd_spin_continuation){ .frame = { .logical_task = &stask, .outer_lock_addr = (unsigned long)&lock } },
				  .cpuid = 3 };
	struct kd_spin_node r = { .execution = &(struct kd_spin_continuation){ .frame = { .logical_task = &rtask, .outer_lock_addr = (unsigned long)&lock } },
				  .cpuid = 20,
				  .socket_id = 1,
				  .next = &s };
	struct kd_spin_node w = { .execution = &(struct kd_spin_continuation){ .frame = { .logical_task = &request_task, .outer_lock_addr = (unsigned long)&lock } },
				  .cpuid = 0,
				  .next = &r };

	reset_trace();
	kd_deferred_trace_lock = (unsigned long)&lock;
	CHECK(get_next_node(&w, &scan_left) == &s && scan_left == 511);
	CHECK(kd_spin_cpu.local_queue_head == &r &&
	      kd_spin_cpu.local_queue_tail == &r);
	CHECK(events == 1 && strstr(message, "kd_defer append:"));
	CHECK(strstr(message, "request_task=10") && strstr(message, "task=40"));
	CHECK(strstr(message, "node_cpu=20") &&
	      strstr(message, "node_socket=1"));
	r.next = &s;
	kd_spin_selftest_splice(&lock, &s, true);
	CHECK(events == 2 && strstr(message, "outer=1") &&
	      strstr(message, "linked=1"));
	kd_spin_selftest_splice(&lock, &s, false);
	CHECK(events == 3 && strstr(message, "outer=0"));
	/* A predecessor can be recycled after publication: cached identity only. */
	kd_spin_selftest_link(&r, (void *)0x1234, 32, 7);
	CHECK(events == 4 && strstr(message, "previous=1234"));
	CHECK(strstr(message, "previous_task=32") &&
	      strstr(message, "previous_cpu=7"));
	kd_spin_cpu = (struct kd_spin_cpu_state){};
	r.next = NULL;
	CHECK(get_next_node(&w, &scan_left) == &r &&
	      !kd_spin_cpu.local_queue_head && events == 4);
	r.next = &s;
	r.socket_id = 0;
	CHECK(get_next_node(&w, &scan_left) == &r && events == 4);
	r.socket_id = 1;
	s.socket_id = IRQ_NUMA_NODE;
	CHECK(get_next_node(&w, &scan_left) == &r && events == 4);
	s.socket_id = 0;
	/* Saved SP does not classify nodes; only the published socket tag
	 * stops delegation, including an immediate non-combinable successor. */
	r.rsp = 0xdeadbeef;
	CHECK(!check_irq_node(&r));
	r.socket_id = IRQ_NUMA_NODE;
	CHECK(get_next_node(&w, &scan_left) == &r && events == 4 &&
	      scan_left == 511);
	kd_spin_selftest_restore(&lock, &w, &r, 2);
	CHECK(events == 5 && strstr(message, "kd_defer restore:"));
	CHECK(strstr(message, "head=0 tail=0") && strstr(message, "result=2"));
	CHECK(!kd_spin_cpu.local_queue_head &&
	      !kd_spin_cpu.local_queue_tail);
	CHECK(w.next == &r && r.next == &s);
	struct kd_spin_node prefix = { .next = &r };
	kd_spin_cpu.local_queue_head = &prefix;
	kd_spin_cpu.local_queue_tail = &prefix;
	kd_spin_selftest_restore(&lock, &w, &r, 3);
	CHECK(events == 6 && strstr(message, "result=3"));
	CHECK(kd_spin_cpu.local_queue_head == &prefix &&
	      kd_spin_cpu.local_queue_tail == &prefix);
	CHECK(prefix.next == &r && w.next == &r && r.next == &s);
	kd_spin_selftest_queue_context(&child_lock, true);
	kd_spin_selftest_deferred_report();
	CHECK(events == 6 && atomic_read(&kd_deferred_event_count) == 0);
	kd_deferred_trace_lock = 0;
	kd_spin_selftest_link(&r, (void *)0x1234, 32, 7);
	kd_spin_selftest_restore(&lock, &w, &r, 2);
	CHECK(events == 6);
}

static void selection(void)
{
	reset_trace();
	CHECK(!kd_deferred_selected(NULL) && !kd_deferred_selected(&lock));
	kd_deferred_trace_locks[7] = (unsigned long)&lock;
	CHECK(!kd_deferred_selected(&lock));
	kd_deferred_trace_lock_count = 7;
	CHECK(!kd_deferred_selected(&lock));
	kd_deferred_trace_lock_count = 8;
	CHECK(kd_deferred_selected(&lock));
	kd_deferred_trace_lock_count = 100;
	CHECK(kd_deferred_selected(&lock) &&
	      !kd_deferred_selected(&child_lock));
	kd_deferred_trace_lock = (unsigned long)&child_lock;
	CHECK(kd_deferred_selected(&lock) && kd_deferred_selected(&child_lock));
	CHECK(!kd_deferred_selected(NULL));
}

static void buffered_trace(void)
{
	u16 scan_left = 512;
	struct kd_spin_node s = { .execution = &(struct kd_spin_continuation){ .frame = { .logical_task = &stask, .outer_lock_addr = (unsigned long)&lock } },
				  .cpuid = 3 };
	struct kd_spin_node r = { .execution = &(struct kd_spin_continuation){ .frame = { .logical_task = &rtask, .outer_lock_addr = (unsigned long)&lock } },
				  .cpuid = 20,
				  .socket_id = 1,
				  .next = &s };
	struct kd_spin_node w = { .execution = &(struct kd_spin_continuation){ .frame = { .logical_task = &request_task, .outer_lock_addr = (unsigned long)&lock } },
				  .cpuid = 0,
				  .next = &r };
	struct kd_deferred_trace_event *e = kd_deferred_events;

	reset_trace();
	kd_deferred_buffered = true;
	kd_deferred_trace_locks[0] = (unsigned long)&lock;
	kd_deferred_trace_lock_count = 1;
	kd_spin_cpu.lock_addr[1] = (unsigned long)&lock;
	CHECK(get_next_node(&w, &scan_left) == &s && scan_left == 511);
	kd_spin_selftest_queue_context(&child_lock, true);
	kd_spin_selftest_queue_context(&child_lock, false);
	kd_spin_selftest_splice(&lock, &s, true);
	kd_spin_cpu = (struct kd_spin_cpu_state){};
	kd_spin_selftest_restore(&lock, &w, (void *)0x1234, 2);
	CHECK(events == 0 && atomic_read(&kd_deferred_event_count) == 5);
	CHECK(e[0].kind == KD_DEFER_APPEND &&
	      e[0].request == (unsigned long)&w);
	CHECK(e[0].request_task == 10 && e[0].request_cpu == 0);
	CHECK(e[0].node == (unsigned long)&r && e[0].task == 40);
	CHECK(e[0].node_cpu == 20 && e[0].node_socket == 1);
	CHECK(e[0].head == (unsigned long)&r && e[0].tail == (unsigned long)&r);
	CHECK(e[1].kind == KD_DEFER_SAVE && e[2].kind == KD_DEFER_RESUME);
	for (int i = 1; i <= 2; i++) {
		CHECK(e[i].lock == (unsigned long)&child_lock &&
		      e[i].parent == (unsigned long)&lock);
		CHECK(e[i].head == (unsigned long)&r &&
		      e[i].tail == (unsigned long)&r);
		CHECK(!e[i].next);
	}
	CHECK(e[3].kind == KD_DEFER_SPLICE && e[3].head_task == 40 &&
	      e[3].head_cpu == 20);
	CHECK(e[3].next == (unsigned long)&s && e[3].next_task == 41 &&
	      e[3].next_cpu == 3);
	CHECK(e[3].outer && e[3].linked);
	CHECK(e[4].kind == KD_DEFER_RESTORE &&
	      e[4].request == (unsigned long)&w);
	CHECK(e[4].request_task == 10 && e[4].request_cpu == 0);
	CHECK(e[4].first == (unsigned long)&r && e[4].last == 0x1234);
	CHECK(e[4].next == (unsigned long)&r && e[4].result == 2);
	CHECK(!e[4].head && !e[4].tail);
	for (int i = 0; i < 5; i++) {
		CHECK(e[i].ready && e[i].owner == 99 && e[i].cpu == 2);
		CHECK(e[i].socket == 0 && e[i].depth == 2);
	}
	CHECK(w.next == &r && r.next == &s && !s.next);
	kd_spin_selftest_link(&r, (void *)0x1234, 32, 7);
	CHECK(events == 1 && strstr(message, "kd_defer link:"));
	/* Teardown must use only the captured values, not any live pointer. */
	memset(&w, 0xcc, sizeof(w));
	memset(&r, 0xcc, sizeof(r));
	memset(&s, 0xcc, sizeof(s));
	task.pid = 101;
	kd_spin_selftest_deferred_report();
	CHECK(events == 7);
	CHECK(strstr(messages[1], "event=0 kind=1") &&
	      strstr(messages[1], "owner=99"));
	CHECK(strstr(messages[1], "request_task=10") &&
	      strstr(messages[1], "task=40"));
	CHECK(strstr(messages[4], "next_task=41") &&
	      strstr(messages[4], "linked=1"));
	CHECK(strstr(messages[5], "last=1234") &&
	      strstr(messages[5], "result=2"));
	CHECK(strstr(message, "events=5 capacity=256 overflow=0 incomplete=0"));
	/* Saved node addresses are identities, never a license to dereference. */
	kd_spin_cpu.lock_addr[1] = (unsigned long)&lock;
	kd_spin_cpu.local_queue_head = (void *)0x1234;
	kd_spin_cpu.local_queue_tail = (void *)0x5678;
	kd_spin_selftest_queue_context(&child_lock, false);
	CHECK(atomic_read(&kd_deferred_event_count) == 6);
	CHECK(e[5].head == 0x1234 && e[5].tail == 0x5678 && !e[5].next);
}

static void capacity(int attempts, bool leave_incomplete)
{
	int count = min(attempts, KD_DEFER_TRACE_EVENTS);
	int incomplete = leave_incomplete && count;
	char expected[100];

	reset_trace();
	kd_deferred_buffered = true;
	for (int i = 0; i < attempts; i++) {
		struct kd_deferred_trace_event *event =
			kd_deferred_event(KD_DEFER_APPEND, &lock);

		CHECK(!!event == (i < KD_DEFER_TRACE_EVENTS));
		if (event) {
			CHECK(event == &kd_deferred_events[i]);
			if (!leave_incomplete || i)
				smp_store_release(&event->ready, true);
		}
	}
	CHECK(!events && atomic_read(&kd_deferred_event_count) == count);
	kd_spin_selftest_deferred_report();
	CHECK(events == (unsigned int)(count - incomplete + 1));
	snprintf(expected, sizeof(expected),
		 "events=%d capacity=256 overflow=%d incomplete=%d", count,
		 attempts > KD_DEFER_TRACE_EVENTS, incomplete);
	CHECK(strstr(message, expected));
}

struct writer {
	int id, attempts;
	pthread_barrier_t *barrier;
};

static void *record_events(void *arg)
{
	const struct writer *writer = arg;

	pthread_barrier_wait(writer->barrier);
	for (int i = 0; i < writer->attempts; i++) {
		struct kd_deferred_trace_event *event =
			kd_deferred_event(KD_DEFER_APPEND, &lock);

		if (event) {
			event->node = writer->id * writer->attempts + i + 1;
			smp_store_release(&event->ready, true);
		}
	}
	return NULL;
}

static void concurrent_reservations(int workers, int attempts)
{
	pthread_t threads[8];
	struct writer writers[8];
	pthread_barrier_t barrier;
	bool seen[641] = { false };
	int total = workers * attempts;

	reset_trace();
	kd_deferred_buffered = true;
	CHECK(!pthread_barrier_init(&barrier, NULL, workers));
	for (int i = 0; i < workers; i++) {
		writers[i] = (struct writer){ i, attempts, &barrier };
		CHECK(!pthread_create(&threads[i], NULL, record_events,
				      &writers[i]));
	}
	for (int i = 0; i < workers; i++)
		CHECK(!pthread_join(threads[i], NULL));
	CHECK(!pthread_barrier_destroy(&barrier));
	CHECK(atomic_read(&kd_deferred_event_count) == KD_DEFER_TRACE_EVENTS);
	CHECK(atomic_read(&kd_deferred_overflow) ==
	      (total > KD_DEFER_TRACE_EVENTS));
	for (int i = 0; i < KD_DEFER_TRACE_EVENTS; i++) {
		const struct kd_deferred_trace_event *event =
			&kd_deferred_events[i];

		CHECK(event->ready && event->node &&
		      event->node <= (unsigned long)total);
		CHECK(!seen[event->node]);
		seen[event->node] = true;
	}
	CHECK(!events);
	kd_spin_selftest_deferred_report();
	CHECK(events == KD_DEFER_TRACE_EVENTS + 1 &&
	      strstr(message, "incomplete=0"));
}

int main(void)
{
	const int attempts[] = { 0, 255, 256, 257, 1024 };

	live_trace();
	selection();
	buffered_trace();
	for (unsigned int i = 0; i < sizeof(attempts) / sizeof(attempts[0]);
	     i++)
		for (int incomplete = 0; incomplete <= 1; incomplete++)
			capacity(attempts[i], incomplete);
	concurrent_reservations(4, 64);
	concurrent_reservations(8, 80);
	printf("deferred queue production: %u checks PASS\n", checks);
	return 0;
}
