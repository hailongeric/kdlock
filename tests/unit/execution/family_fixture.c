/* SPDX-License-Identifier: GPL-2.0 */
/* Execute the production family component with a userspace raw-lock/list
 * model. Source bytes are declared fixture inputs, not live-text evidence. */
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned char u8;
typedef unsigned long long u64;
typedef atomic_bool raw_spinlock_t;
static atomic_uint checks;
static _Thread_local unsigned int raw_depth;
#define CHECK(expression) do { \
	atomic_fetch_add(&checks, 1); \
	if (!(expression)) { \
		fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #expression); \
		exit(1); \
	} \
} while (0)
#define READ_ONCE(value) __atomic_load_n(&(value), __ATOMIC_RELAXED)
#define raw_spin_lock_init(lock) atomic_init((lock), false)
#define raw_spin_lock_irqsave(lock, flags) do { \
	(flags) = raw_depth++; \
	while (atomic_exchange_explicit((lock), true, memory_order_acquire)) \
		sched_yield(); \
} while (0)
#define raw_spin_unlock_irqrestore(lock, flags) do { \
	CHECK(raw_depth == (flags) + 1); \
	atomic_store_explicit((lock), false, memory_order_release); \
	raw_depth = (flags); \
} while (0)

struct list_head {
	struct list_head *next, *prev;
};
static void INIT_LIST_HEAD(struct list_head *head)
{
	head->next = head;
	head->prev = head;
}
static bool list_empty(const struct list_head *head)
{
	return head->next == head;
}
static void list_add_tail(struct list_head *node, struct list_head *head)
{
	node->prev = head->prev;
	node->next = head;
	head->prev->next = node;
	head->prev = node;
}
static void list_del_init(struct list_head *node)
{
	node->prev->next = node->next;
	node->next->prev = node->prev;
	INIT_LIST_HEAD(node);
}
#define list_for_each_entry(position, head, member) \
	for (struct list_head *cursor = (head)->next; \
	     cursor != (head) && ((position) = (void *)((char *)cursor - \
		     offsetof(__typeof__(*(position)), member)), 1); \
	     cursor = cursor->next)

#include "production.h"

static struct kd_family family;
static struct kd_family_ref root, child, later;
static struct kd_family_artifact artifact;
static char owner, nested_owner, replacement_owner;

static void start(u64 generation)
{
	CHECK(!kd_family_init(&family, &owner, generation, generation, 0x1000, 2));
	kd_family_ref_init(&root);
	kd_family_ref_init(&child);
	kd_family_ref_init(&later);
	kd_family_artifact_init(&artifact);
	CHECK(!kd_family_ref_get(&family, &root, NULL, &owner, generation, 0));
	CHECK(kd_family_ref_valid(&root));
	CHECK(kd_family_live_refs(&family) == 1);
}

static void finish(u64 generation)
{
	CHECK(!kd_family_begin_retire(&family, &owner, generation));
	CHECK(!kd_family_ref_put(&root));
	CHECK(!kd_family_finish_retire(&family, &owner, generation));
	CHECK(family.state == KD_FAMILY_RETIRED);
	CHECK(!kd_family_live_refs(&family));
}

static void references(void)
{
	struct kd_family_ref stale;

	CHECK(kd_family_init(NULL, &owner, 1, 1, 0x1000, 2) == -EINVAL);
	CHECK(kd_family_init(&family, NULL, 1, 1, 0x1000, 2) == -EINVAL);
	CHECK(kd_family_init(&family, &owner, 0, 1, 0x1000, 2) == -EINVAL);
	CHECK(kd_family_init(&family, &owner, 1, 0, 0x1000, 2) == -EINVAL);
	CHECK(kd_family_init(&family, &owner, 1, 1, 0, 2) == -EINVAL);
	CHECK(kd_family_init(&family, &owner, 1, 1, 0x1000, 0) == -EINVAL);
	start(1);
	CHECK(kd_family_ref_get(&family, &root, NULL, &owner, 1, 0) == -EINVAL);
	CHECK(kd_family_ref_get(&family, &child, NULL, &nested_owner, 8, 0) == -ESTALE);
	CHECK(!kd_family_ref_get(&family, &child, &root, &nested_owner, 8, 11));
	CHECK(kd_family_live_refs(&family) == 2);
	/* A field copy is not a concrete reference node in the family's list. */
	stale = child;
	CHECK(!kd_family_ref_valid(&stale));
	CHECK(kd_family_ref_put(&stale) == -ESTALE);
	CHECK(kd_family_finish_retire(&family, &owner, 1) == -EINVAL);
	CHECK(kd_family_begin_retire(&family, &replacement_owner, 1) == -ESTALE);
	CHECK(!kd_family_begin_retire(&family, &owner, 1));
	CHECK(kd_family_ref_get(&family, &later, NULL, &owner, 1, 0) == -ESHUTDOWN);
	CHECK(!kd_family_ref_get(&family, &later, &child, &nested_owner, 9, 12));
	CHECK(kd_family_finish_retire(&family, &owner, 1) == -EBUSY);
	/* Parent references may finish before independent descendants. */
	CHECK(!kd_family_ref_put(&root));
	CHECK(!kd_family_ref_put(&child));
	CHECK(kd_family_ref_valid(&later));
	CHECK(kd_family_live_refs(&family) == 1);
	CHECK(kd_family_ref_get(&family, &child, &root, &nested_owner, 8, 13) == -ESTALE);
	CHECK(kd_family_finish_retire(&family, &owner, 1) == -EBUSY);
	CHECK(!kd_family_ref_put(&later));
	CHECK(kd_family_ref_put(&later) == -EINVAL);
	CHECK(!kd_family_finish_retire(&family, &owner, 1));
	CHECK(kd_family_ref_get(&family, &root, NULL, &owner, 1, 0) == -ESHUTDOWN);
	CHECK(kd_family_begin_retire(&family, &owner, 1) == -ESHUTDOWN);
}

static void cache(void)
{
	const struct kd_family_instruction *first, *second;
	u8 bytes[] = { 0x48, 0x31, 0xc0 };
	u8 changed[] = { 0x48, 0x31, 0xc3 };
	struct kd_family_ref old;
	unsigned int index;

	start(2);
	++root.family_generation;
	CHECK(!kd_family_ref_valid(&root));
	CHECK(!kd_family_cache_find(&root, 0x1000, bytes, sizeof(bytes)));
	--root.family_generation;
	CHECK(kd_family_ref_valid(&root));
	CHECK(!kd_family_cache_find(&root, 0x1000, bytes, sizeof(bytes)));
	first = kd_family_cache_publish(&root, 0x1000, bytes, sizeof(bytes));
	CHECK(first && first->generation == 1 && first->length == sizeof(bytes));
	CHECK(!memcmp(first->bytes, bytes, sizeof(bytes)) && family.cached == 1);
	CHECK(kd_family_cache_find(&root, 0x1000, bytes, sizeof(bytes)) == first);
	CHECK(kd_family_cache_publish(&root, 0x1000, bytes, sizeof(bytes)) == first);
	CHECK(family.cached == 1 && family.cache_hits == 1 && family.cache_misses == 1);
	CHECK(!kd_family_cache_find(&root, 0x1000, changed, sizeof(changed)));
	second = kd_family_cache_publish(&root, 0x1000, changed, sizeof(changed));
	CHECK(second && second != first && second->generation == 2);
	CHECK(!memcmp(first->bytes, bytes, sizeof(bytes)));
	for (index = family.cached; index < KD_FAMILY_CACHE_ENTRIES; ++index)
		CHECK(kd_family_cache_publish(&root, 0x1000 + index * 16,
			bytes, sizeof(bytes)) != NULL);
	CHECK(family.cached == KD_FAMILY_CACHE_ENTRIES);
	CHECK(!kd_family_cache_publish(&root, 0x2000, bytes, sizeof(bytes)));
	CHECK(kd_family_cache_find(&root, 0x1000, bytes, sizeof(bytes)) == first);
	CHECK(!kd_family_cache_find(&root, 0x1000, bytes, 0));
	CHECK(!kd_family_cache_publish(&root, 0x1000, bytes, KD_FAMILY_INSN_BYTES + 1));
	CHECK(!kd_family_cache_publish(&root, ULONG_MAX - 1, bytes, sizeof(bytes)));
	old = root;
	finish(2);
	CHECK(!kd_family_ref_valid(&old));
	start(3);
	CHECK(!family.cached && family.source_epoch == 3);
	CHECK(!kd_family_cache_find(&old, 0x1000, bytes, sizeof(bytes)));
	CHECK(!kd_family_cache_find(&root, 0x1000, bytes, sizeof(bytes)));
	finish(3);
}

static void artifacts(void)
{
	u8 bytes[] = { 0xe8, 1, 2, 3, 4 };
	struct kd_family_ref other_parent;
	unsigned int index;

	start(4);
	for (index = 0; index < KD_FAMILY_CACHE_ENTRIES; ++index)
		CHECK(kd_family_cache_publish(&root, 0x1000 + index * 16,
			bytes, sizeof(bytes)) != NULL);
	CHECK(!kd_family_cache_publish(&root, 0x8000, bytes, sizeof(bytes)));
	/* Services retain their instruction metadata even with a full cache. */
	CHECK(!kd_family_artifact_get(&artifact, &root, KD_FAMILY_ARTIFACT_NATIVE_CALL,
		0x8000, bytes, sizeof(bytes), 17));
	CHECK(kd_family_live_refs(&family) == 2);
	CHECK(kd_family_artifact_valid(&artifact, &root, 17));
	CHECK(!kd_family_artifact_valid(&artifact, &root, 18));
	CHECK(artifact.source_epoch == 4 && artifact.source_ip == 0x8000);
	bytes[1] = 9;
	CHECK(artifact.bytes[1] == 1);
	CHECK(kd_family_artifact_get(&artifact, &root, KD_FAMILY_ARTIFACT_KD_CALL,
		0x9000, bytes, sizeof(bytes), 18) == -EINVAL);
	other_parent = root;
	other_parent.request_generation++;
	CHECK(!kd_family_artifact_valid(&artifact, &other_parent, 17));
	artifact.sequence++;
	CHECK(kd_family_artifact_put(&artifact) == -ESTALE);
	CHECK(kd_family_live_refs(&family) == 2);
	artifact.sequence--;
	CHECK(!kd_family_begin_retire(&family, &owner, 4));
	CHECK(!kd_family_ref_put(&root));
	CHECK(kd_family_artifact_valid(&artifact, &root, 17));
	CHECK(kd_family_finish_retire(&family, &owner, 4) == -EBUSY);
	CHECK(!kd_family_artifact_put(&artifact));
	CHECK(!kd_family_artifact_valid(&artifact, &root, 17));
	CHECK(kd_family_artifact_put(&artifact) == -ESTALE);
	CHECK(!kd_family_finish_retire(&family, &owner, 4));
	start(5);
	CHECK(kd_family_artifact_get(&artifact, &root, KD_FAMILY_ARTIFACT_NONE,
		0x1000, bytes, sizeof(bytes), 1) == -EINVAL);
	CHECK(kd_family_artifact_get(&artifact, &root, KD_FAMILY_ARTIFACT_MEMORY,
		0x1000, bytes, sizeof(bytes), 0) == -EINVAL);
	CHECK(kd_family_artifact_get(&artifact, &root, KD_FAMILY_ARTIFACT_MEMORY,
		0x1000, bytes, 0, 1) == -EINVAL);
	CHECK(kd_family_live_refs(&family) == 1);
	finish(5);
}

#define THREADS 4
#define LOOPS 128
static void *publisher(void *argument)
{
	struct kd_family_ref local;
	u8 bytes[] = { 0x90 };
	const void *identity = argument;
	unsigned int iteration;

	kd_family_ref_init(&local);
	for (iteration = 0; iteration < LOOPS; ++iteration) {
		CHECK(!kd_family_ref_get(&family, &local, &root, identity, 10, iteration + 1));
		CHECK(kd_family_cache_publish(&local, 0x1000, bytes, sizeof(bytes)) != NULL);
		CHECK(kd_family_cache_find(&local, 0x1000, bytes, sizeof(bytes)) != NULL);
		CHECK(!kd_family_ref_put(&local));
	}
	CHECK(!raw_depth);
	return NULL;
}

static void simultaneous_publication(void)
{
	pthread_t workers[THREADS];
	unsigned int index;

	start(6);
	for (index = 0; index < THREADS; ++index)
		CHECK(!pthread_create(&workers[index], NULL, publisher, &workers[index]));
	/* Retained parent authority keeps derived work valid during drainage. */
	CHECK(!kd_family_begin_retire(&family, &owner, 6));
	CHECK(kd_family_finish_retire(&family, &owner, 6) == -EBUSY);
	for (index = 0; index < THREADS; ++index)
		CHECK(!pthread_join(workers[index], NULL));
	CHECK(family.cached == 1 && family.cache_hits == THREADS * LOOPS);
	CHECK(kd_family_live_refs(&family) == 1);
	finish(6);
}

int main(void)
{
	references();
	cache();
	artifacts();
	simultaneous_publication();
	CHECK(!raw_depth);
	printf("production family cache: %u checks, 0 failures; cache=%u\n",
		atomic_load(&checks), KD_FAMILY_CACHE_ENTRIES);
	return 0;
}
