// SPDX-License-Identifier: GPL-2.0
/* Real owner-transfer/pickup code with pthread peers and atomic owner words.
 * Final native unlock is a substitute; retained-owner ACKs have their own
 * fixture. A third task attempts to steal A throughout the transferred suffix. */
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

struct task_struct { unsigned int id; } __attribute__((aligned(8)));
struct kd_mutex { unsigned long owner; pthread_mutex_t wait_lock; };
static struct task_struct combiner = {1}, waiter = {2}, thief = {3};
static _Thread_local struct task_struct *current;
static struct kd_mutex lock = { .wait_lock = PTHREAD_MUTEX_INITIALIZER };
static atomic_int stage, attempts, failures, thief_ready, thief_stop, thief_done;
static unsigned int protected_prefix, protected_suffix;
static unsigned long wanted_flags;
#define KD_WAITERS 1UL
#define KD_HANDOFF 2UL
#define KD_PICKUP 4UL
#define KD_FLAGS 7UL
#undef __always_inline
#define __always_inline inline __attribute__((always_inline))
#define BUG_ON(c) do { if (c) { fputs("FAIL invariant\n", stderr); exit(1); } } while (0)
#define atomic_long_read(p) __atomic_load_n((p), __ATOMIC_RELAXED)
#define atomic_long_try_cmpxchg_acquire(p,o,n) __atomic_compare_exchange_n((p),(o),(n),false,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED)
#define atomic_long_try_cmpxchg_release(p,o,n) __atomic_compare_exchange_n((p),(o),(n),false,__ATOMIC_RELEASE,__ATOMIC_RELAXED)
#define _raw_spin_lock(p) pthread_mutex_lock(p)
#define _raw_spin_unlock(p) pthread_mutex_unlock(p)
#define CHECK(c) do { if (!(c)) { fprintf(stderr,"FAIL line=%d: %s\n",__LINE__,#c); atomic_fetch_add(&failures,1); } } while (0)
#include "owner_production.h"

static void *steal(void *unused)
{
	(void)unused;
	current = &thief;
	atomic_store_explicit(&thief_ready, 1, memory_order_release);
	while (!atomic_load_explicit(&thief_stop, memory_order_acquire)) {
		unsigned long zero = 0;
		bool acquired = atomic_long_try_cmpxchg_acquire(&lock.owner, &zero,
							(unsigned long)current);
		CHECK(!acquired);
		atomic_fetch_add_explicit(&attempts, 1, memory_order_release);
	}
	atomic_store_explicit(&thief_done, 1, memory_order_release);
	return NULL;
}

static void *resume(void *unused)
{
	unsigned long owner;
	int ret;

	(void)unused;
	current = &waiter;
	while (!atomic_load_explicit(&stage, memory_order_acquire))
		sched_yield();
	ret = kd_mutex_transfer_pickup(&lock);
	CHECK(!ret);
	owner = atomic_long_read(&lock.owner);
	CHECK((owner & ~KD_FLAGS) == (unsigned long)current);
	CHECK((owner & KD_FLAGS) == wanted_flags);
	CHECK(protected_prefix == 1 && protected_suffix == 0);
	atomic_store_explicit(&stage, 2, memory_order_release);
	while (atomic_load_explicit(&attempts, memory_order_acquire) < 10000)
		sched_yield();
	atomic_store_explicit(&thief_stop, 1, memory_order_release);
	while (!atomic_load_explicit(&thief_done, memory_order_acquire))
		sched_yield();
	protected_suffix++;
	/* Stand in for W's native physical unlock only after the protected suffix.
	 * No source prefix is rerun and no other task acquired between them. */
	CHECK(protected_prefix == 1 && protected_suffix == 1);
	__atomic_store_n(&lock.owner, 0, __ATOMIC_RELEASE);
	return NULL;
}

int main(void)
{
	const unsigned long flags[] = { 0, KD_WAITERS, KD_WAITERS | KD_HANDOFF };

	for (unsigned int i = 0; i < sizeof(flags) / sizeof(flags[0]); i++) {
		pthread_t worker, contender;

		current = &combiner;
		wanted_flags = flags[i];
		atomic_store(&stage, 0); atomic_store(&attempts, 0);
		atomic_store(&thief_ready, 0); atomic_store(&thief_stop, 0);
		atomic_store(&thief_done, 0);
		protected_prefix = protected_suffix = 0;
		lock.owner = (unsigned long)current | wanted_flags;
		CHECK(kd_mutex_transfer_owner(&lock, current) == -EINVAL);
		CHECK(!pthread_create(&worker, NULL, resume, NULL));
		CHECK(!pthread_create(&contender, NULL, steal, NULL));
		while (!atomic_load_explicit(&thief_ready, memory_order_acquire))
			sched_yield();
		protected_prefix++;
		CHECK(!kd_mutex_transfer_owner(&lock, &waiter));
		CHECK((atomic_long_read(&lock.owner) & ~KD_FLAGS) == (unsigned long)&waiter);
		CHECK(kd_mutex_transfer_pickup(&lock) == -EPERM);
		atomic_store_explicit(&stage, 1, memory_order_release);
		pthread_join(worker, NULL); pthread_join(contender, NULL);
		CHECK(!atomic_long_read(&lock.owner));
		CHECK(protected_prefix == 1 && protected_suffix == 1);
	}
	if (atomic_load(&failures))
		return 1;
	puts("PASS production owner transfer: no-gap pickup, three flag states, >=30000 thief attempts across transfer, exact-once prefix/suffix");
	return 0;
}
