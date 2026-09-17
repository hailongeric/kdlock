/* SPDX-License-Identifier: GPL-2.0 */
/* Exercise production map publication and colliding creators. pthread mutexes
 * substitute only the writer lock; release/acquire accesses are real atomics.
 * This is a userspace ordering/API regression, not an LKMM proof. */
#include "spin_gate_mock.h"
#include <pthread.h>
#include <sched.h>

static pthread_mutex_t writer = PTHREAD_MUTEX_INITIALIZER;
static pthread_barrier_t start;
static unsigned int writer_locks, publications, acquire_reads;
static void before_publish(void *address, raw_spinlock_t *origin);

#undef raw_spin_lock_irqsave
#undef raw_spin_unlock_irqrestore
#define raw_spin_lock_irqsave(lock, flags)                       \
	do {                                                    \
		(void)(lock);                                   \
		(flags) = 0;                                    \
		assert(!pthread_mutex_lock(&writer));           \
		writer_locks++;                                 \
	} while (0)
#define raw_spin_unlock_irqrestore(lock, flags)                  \
	do {                                                    \
		(void)(lock);                                   \
		(void)(flags);                                  \
		assert(!pthread_mutex_unlock(&writer));         \
	} while (0)
#define smp_store_release(p, v)                                  \
	do {                                                    \
		before_publish((p), (v));                       \
		__atomic_store_n((p), (v), __ATOMIC_RELEASE);    \
	} while (0)
#define smp_load_acquire(p)                                      \
	({                                                      \
		__atomic_add_fetch(&acquire_reads, 1, __ATOMIC_RELAXED); \
		__atomic_load_n((p), __ATOMIC_ACQUIRE);          \
	})
/* The deterministic base fixture's hash counter is not shared by threads. */
#define hash_long(key, bits) ((void)(key), (void)(bits), 0U)
#include "gate_production.h"

static void before_publish(void *address, raw_spinlock_t *origin)
{
	struct kd_spin_gate *gate = (void *)((char *)address -
					  __builtin_offsetof(struct kd_spin_gate, origin));

	assert(!gate->origin && gate->owner_cpu == -1);
	assert(!gate->owner && !gate->held && !gate->generation);
	assert(!atomic_read(&gate->word.val));
	/* Even while initialized, this slot must remain invisible until publish.
	 * A locking find would deadlock here while the creator owns writer. */
	assert(kd_spin_gate_find(origin) == NULL);
	publications++;
}

enum { THREADS = 12, LOCKS = 48, ROUNDS = 100 };
static raw_spinlock_t origins[LOCKS];

static void *creator(void *argument)
{
	unsigned long offset = (unsigned long)argument;

	pthread_barrier_wait(&start);
	for (unsigned int round = 0; round < ROUNDS; round++)
		for (unsigned int i = 0; i < LOCKS; i++) {
			raw_spinlock_t *origin = &origins[(i + offset) % LOCKS];
			struct kd_spin_gate *gate = kd_spin_gate_get(origin);

			assert(gate && gate->origin == origin);
			assert(gate->owner_cpu == -1 && !gate->owner &&
			       !gate->held && !gate->generation && !gate->word.val.counter);
			assert(kd_spin_gate_find(origin) == gate);
		}
	return NULL;
}

int main(void)
{
	pthread_t threads[THREADS];
	unsigned int before, occupied = 0;

	/* Other mock primitives belong to the physical-owner fixture. */
	(void)mock_map_lock;
	(void)mock_map_unlock;
	(void)hash_long;
	assert(!pthread_barrier_init(&start, NULL, THREADS));
	for (unsigned long i = 0; i < THREADS; i++)
		assert(!pthread_create(&threads[i], NULL, creator, (void *)i));
	for (unsigned int i = 0; i < THREADS; i++)
		assert(!pthread_join(threads[i], NULL));
	assert(!pthread_barrier_destroy(&start));
	for (unsigned int i = 0; i < KD_SPIN_GATE_SLOTS; i++)
		occupied += kd_spin_gates[i].origin != NULL;
	assert(occupied == LOCKS && publications == LOCKS && acquire_reads);
	before = writer_locks;
	for (unsigned int i = 0; i < LOCKS; i++)
		assert(kd_spin_gate_get(&origins[i]) ==
		       kd_spin_gate_find(&origins[i]));
	assert(writer_locks == before);
	assert(kd_spin_gates_check_idle() == 0);
	printf("[PASS] gate publication (%u threads, %u colliding keys, %u published slots)\n",
	       THREADS, LOCKS, publications);
	return 0;
}
