/* Execute the production resident-list payload with substituted userspace
 * locks. This verifies business data and its oracle, not kernel delegation. */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>

typedef uint64_t u64;
#define __aligned(n) __attribute__((aligned(n)))
#define BUILD_BUG_ON(c) _Static_assert(!(c), #c)
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define WRITE_ONCE(x, v) (*(volatile __typeof__(x) *)&(x) = (v))
#include "../../../workload_modules/spin_cacheline/list_payload.h"

static pthread_rwlock_t lock = PTHREAD_RWLOCK_INITIALIZER;
static pthread_barrier_t start;

__attribute__((noipa)) void fixture_write(void)
{
	assert(!pthread_rwlock_wrlock(&lock));
	sc_list_write_locked();
	assert(!pthread_rwlock_unlock(&lock));
}

__attribute__((noipa)) bool fixture_read(void)
{
	bool bad;

	assert(!pthread_rwlock_rdlock(&lock));
	bad = sc_list_read_locked();
	assert(!pthread_rwlock_unlock(&lock));
	return bad;
}

static void *worker(void *argument)
{
	unsigned long index = (unsigned long)argument;
	int barrier = pthread_barrier_wait(&start);
	unsigned int i;

	assert(!barrier || barrier == PTHREAD_BARRIER_SERIAL_THREAD);
	for (i = 0; i < 1000; i++) {
		if (index < 4)
			fixture_write();
		else
			assert(!fixture_read());
	}
	return NULL;
}

int main(void)
{
	pthread_t threads[8];
	u64 values[16] = { 0 };
	unsigned long i;

	sc_list_init();
	assert(!sc_list_snapshot(values) && values[0] == 0);
	assert(!pthread_barrier_init(&start, NULL, 8));
	for (i = 0; i < 8; i++)
		assert(!pthread_create(&threads[i], NULL, worker, (void *)i));
	for (i = 0; i < 8; i++)
		assert(!pthread_join(threads[i], NULL));
	assert(!pthread_barrier_destroy(&start));
	assert(!sc_list_snapshot(values) && values[0] == 4000);
	for (i = 1; i < 16; i++)
		assert(values[i] == 0);

	sc_list_nodes[3].value++;
	assert(sc_list_snapshot(values) == -EUCLEAN);
	assert(fixture_read());
	sc_list_nodes[3].value--;
	assert(!sc_list_snapshot(values));
	/* The oracle must reject bad pointers without following them. */
	sc_list_nodes[0].next = (void *)1;
	assert(sc_list_snapshot(values) == -EUCLEAN);
	sc_list_nodes[0].next = &sc_list_nodes[0];
	assert(sc_list_snapshot(values) == -EUCLEAN);
	sc_list_nodes[0].next = &sc_list_nodes[10];
	assert(sc_list_snapshot(values) == -EUCLEAN);
	sc_list_nodes[0].next = &sc_list_nodes[5];
	assert(!sc_list_snapshot(values) && values[0] == 4000);
	return 0;
}
