// SPDX-License-Identifier: GPL-2.0
/* Exercise the actual module's admission helpers with an in-flight writer
 * and a snapshot reader. Only Linux atomic primitives are substituted. */
#include <assert.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <stdint.h>

typedef atomic_int atomic_t;
#define SC_LINE_BYTES 64
#define __aligned(n) __attribute__((aligned(n)))
#define ATOMIC_INIT(v) ATOMIC_VAR_INIT(v)

static bool atomic_add_unless(atomic_t *p, int n, int unless)
{
	int old = atomic_load(p);
	while (old != unless) {
		if (atomic_compare_exchange_weak(p, &old, old + n))
			return true;
	}
	return false;
}

static int atomic_dec_return_release(atomic_t *p)
{
	return atomic_fetch_sub_explicit(p, 1, memory_order_release) - 1;
}

static int atomic_cmpxchg_acquire(atomic_t *p, int old, int value)
{
	atomic_compare_exchange_strong_explicit(p, &old, value,
					       memory_order_acquire, memory_order_relaxed);
	return old;
}

static void atomic_set_release(atomic_t *p, int value)
{
	atomic_store_explicit(p, value, memory_order_release);
}

/* Extracted from module.c by the guest test; no duplicate admission policy. */
#include "control.inc"

static atomic_bool ready, finish;
static int value;

static void *writer(void *arg)
{
	if (!sc_run_enter())
		return (void *)1;
	value = (intptr_t)arg;
	atomic_store_explicit(&ready, true, memory_order_release);
	while (!atomic_load_explicit(&finish, memory_order_acquire))
		__asm__ __volatile__("pause");
	sc_run_exit();
	return NULL;
}

int main(void)
{
	pthread_t thread;
	void *result;

	assert(sc_run_enter());
	assert(!pthread_create(&thread, NULL, writer, (void *)123));
	while (!atomic_load_explicit(&ready, memory_order_acquire))
		__asm__ __volatile__("pause");
	assert(!sc_snapshot_begin());
	sc_run_exit();
	assert(!sc_snapshot_begin()); /* The other writer is still admitted. */
	atomic_store_explicit(&finish, true, memory_order_release);
	assert(!pthread_join(thread, &result) && result == NULL);
	assert(sc_snapshot_begin());
	assert(value == 123);
	/* A reader must reserve the whole snapshot, not merely observe active=0. */
	assert(!pthread_create(&thread, NULL, writer, (void *)456));
	assert(!pthread_join(thread, &result) && result == (void *)1);
	assert(value == 123 && !sc_snapshot_begin());
	sc_snapshot_end();
	assert(sc_run_enter());
	value = 456;
	sc_run_exit();
	assert(sc_snapshot_begin() && value == 456);
	sc_snapshot_end();
	return 0;
}
