// SPDX-License-Identifier: GPL-2.0-only
/* Production function excerpts with controlled source and lifetime endpoints. */
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/mman.h>
#include <unistd.h>

#define CHECK(test) do { if (!(test)) { \
	fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #test); exit(1); \
} } while (0)
#define BUG_ON(test) CHECK(!(test))

/* Match the intrusive-list operations used by the unchanged excerpts. */
struct list_head { struct list_head *next, *prev; };
static void INIT_LIST_HEAD(struct list_head *head) { head->next = head->prev = head; }
static bool list_empty(const struct list_head *head) { return head->next == head; }
static void list_add_tail(struct list_head *entry, struct list_head *head)
{
	entry->prev = head->prev; entry->next = head;
	head->prev->next = entry; head->prev = entry;
}
static void list_del_init(struct list_head *entry)
{
	entry->prev->next = entry->next; entry->next->prev = entry->prev;
	INIT_LIST_HEAD(entry);
}
#define list_entry(ptr, type, member) ((type *)((char *)(ptr) - offsetof(type, member)))
#define list_for_each(pos, head) for ((pos) = (head)->next; (pos) != (head); (pos) = (pos)->next)
#define list_next_entry(pos, member) list_entry((pos)->member.next, __typeof__(*(pos)), member)
#define list_for_each_entry_safe(pos, n, head, member) \
	for ((pos) = list_entry((head)->next, __typeof__(*(pos)), member), \
	     (n) = list_next_entry(pos, member); &(pos)->member != (head); \
	     (pos) = (n), (n) = list_next_entry(n, member))

enum kd_operation_kind { KD_OPERATION_MUTEX_LOCK, KD_OPERATION_SPIN_LOCK };
enum kd_lock_family { KD_LOCK_FAMILY_MUTEX, KD_LOCK_FAMILY_SPIN, KD_LOCK_FAMILY_COUNT };
static bool kd_lock_family_is_atomic(enum kd_lock_family family)
{
	return family == KD_LOCK_FAMILY_SPIN;
}
struct task_struct { int unused; };
struct kd_thread_state { struct task_struct *origin; };
struct kd_execution_binding { bool current; };
struct kd_request_user { bool active; int kind; };
struct kd_task_cancel_actor { int unused; };
struct kd_jit_image_use { int unused; };
struct kd_request_slot {
	struct { char acquisition_identity; struct { bool linked; } grant; } call;
	struct kd_jit_image_use source_use;
};
struct kd_request_pool {
	struct kd_thread_state *state;
	struct kd_request_slot *slots;
	unsigned int capacity;
};
struct kd_source_stack_ops { void *read_word, *write_word; };
struct kd_episode_config {
	bool atomic_spin;
	enum kd_lock_family family;
	void *image_slot, *feedback;
	struct kd_source_stack_ops *stack;
	void *resolve, *classify_target, *report;
};
struct kd_episode_frame;
/* Ordinary record construction is an external cold endpoint in this fixture;
 * the admission and live integration fixtures cover its actual ownership.
 */
struct kd_rw_local { struct list_head free_link; };
static void kd_rw_local_init(struct kd_rw_local *local, struct list_head *free)
{ list_add_tail(&local->free_link, free); }
#include "episode_types.h"

static void kd_request_user_init(struct kd_request_user *user) { user->active = false; user->kind = 0; }
static void kd_task_cancel_actor_init(struct kd_task_cancel_actor *actor) { actor->unused = 0; }
static int kd_request_user_finish(struct kd_request_user *user, const void *identity);
static int kd_jit_image_use_put(struct kd_jit_image_use *use, const void *identity);
static int kd_jit_collect_grants(struct kd_thread_state *state, struct kd_execution_binding *binding);
static unsigned int kd_request_pool_collect(struct kd_request_pool *pool);
#include "episode_functions.h"

enum event_kind { SOURCE_PUT = 1, IMAGE_FINISH, GRANT_FINISH };
enum release_action { KEEP_FRAME, OVERWRITE_FRAME, INACCESSIBLE_FRAME };
static struct {
	struct kd_episode_resources resources;
	struct kd_request_pool pool;
	struct kd_thread_state state;
	struct kd_execution_binding binding;
	struct kd_source_stack_ops stack;
	struct kd_episode_frame *frames;
	struct kd_request_slot *slots;
	size_t map_bytes;
	int events[32], event_count, source_checks, pool_checks;
	int fail_kind, fail_slot, unlink_slot;
	enum release_action release;
} fixture;

static void event(int index, int kind)
{
	CHECK(fixture.event_count < 32);
	fixture.events[fixture.event_count++] = index * 10 + kind;
}

static int kd_jit_collect_grants(struct kd_thread_state *state, struct kd_execution_binding *binding)
{
	CHECK(state == &fixture.state);
	++fixture.source_checks;
	if (!binding || !binding->current)
		return -EPERM;
	if (fixture.unlink_slot >= 0)
		fixture.slots[fixture.unlink_slot].call.grant.linked = false;
	return 0;
}

static unsigned int kd_request_pool_collect(struct kd_request_pool *pool)
{
	CHECK(pool == &fixture.pool);
	++fixture.pool_checks;
	return 0;
}

static int kd_jit_image_use_put(struct kd_jit_image_use *use, const void *identity)
{
	struct kd_episode_frame *frame = list_entry(identity, struct kd_episode_frame, image_user);
	int index = frame - fixture.frames;

	CHECK(frame->source_image && frame->grant_held && frame->image_held);
	CHECK(use == &fixture.slots[index].source_use);
	if (fixture.fail_kind == SOURCE_PUT && fixture.fail_slot == index)
		return -EIO;
	event(index, SOURCE_PUT);
	return 0;
}

static int kd_request_user_finish(struct kd_request_user *user, const void *identity)
{
	int kind = user->kind, index;
	struct kd_episode_frame *frame;

	CHECK(user == identity && user->active);
	CHECK(kind == IMAGE_FINISH || kind == GRANT_FINISH);
	frame = kind == IMAGE_FINISH ? list_entry(user, struct kd_episode_frame, image_user) :
		list_entry(user, struct kd_episode_frame, grant_user);
	index = frame - fixture.frames;
	if (kind == IMAGE_FINISH) {
		CHECK(!frame->image_held && !frame->source_image && !frame->return_image &&
		      !frame->execution_image && !frame->exit_pending);
	} else {
		CHECK(!frame->grant_held && list_empty(&frame->grant_collect_link));
	}
	if (fixture.fail_kind == kind && fixture.fail_slot == index)
		return -EIO;
	user->active = false;
	event(index, kind);
	if (kind == GRANT_FINISH && fixture.release == OVERWRITE_FRAME)
		memset(frame, 0xa5, sizeof(*frame));
	if (kind == GRANT_FINISH && fixture.release == INACCESSIBLE_FRAME) {
		CHECK(fixture.pool.capacity == 1);
		CHECK(!mprotect(fixture.frames, fixture.map_bytes, PROT_NONE));
	}
	return 0;
}

static void initialize(unsigned int capacity)
{
	struct kd_episode_config config;
	unsigned int index;
	long page = sysconf(_SC_PAGESIZE);

	CHECK(page > 0);
	fixture.map_bytes = ((capacity * sizeof(*fixture.frames) + page - 1) / page + 1) * page;
	fixture.frames = mmap(NULL, fixture.map_bytes, PROT_READ | PROT_WRITE,
		MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	CHECK(fixture.frames != MAP_FAILED);
	fixture.slots = calloc(capacity ? capacity : 1, sizeof(*fixture.slots));
	CHECK(fixture.slots);
	fixture.pool = (struct kd_request_pool) { &fixture.state, fixture.slots, capacity };
	fixture.stack = (struct kd_source_stack_ops) { &fixture, &fixture };
	config = (struct kd_episode_config) {
		.family = KD_LOCK_FAMILY_MUTEX, .image_slot = &fixture, .feedback = &fixture,
		.stack = &fixture.stack, .resolve = &fixture, .classify_target = &fixture, .report = &fixture,
	};
	CHECK(!kd_episode_resources_init(&fixture.resources, &fixture.pool, fixture.frames, capacity, &config));
	CHECK(list_empty(&fixture.resources.grant_collect));
	for (index = 0; index < capacity; ++index) {
		CHECK(!fixture.frames[index].grant_held && !fixture.frames[index].grant_started);
		CHECK(list_empty(&fixture.frames[index].grant_collect_link));
	}
	fixture.binding.current = true;
	fixture.unlink_slot = -1;
}

static void retain_grant(unsigned int index)
{
	fixture.frames[index].grant_held = true;
	fixture.frames[index].grant_user = (struct kd_request_user) { true, GRANT_FINISH };
}

static void start(unsigned int index, bool linked)
{
	struct kd_episode_frame *frame = &fixture.frames[index];

	retain_grant(index);
	frame->source_image = frame->image_held = true;
	frame->image_user = (struct kd_request_user) { true, IMAGE_FINISH };
	fixture.slots[index].call.grant.linked = linked;
	start_grant_actor(frame);
}

static int collect(void) { return kd_episode_collect(&fixture.resources, &fixture.binding); }

static void require_order(const int *order, size_t count)
{
	struct list_head *position;
	size_t index = 0;

	list_for_each(position, &fixture.resources.grant_collect) {
		CHECK(index < count);
		CHECK(list_entry(position, struct kd_episode_frame, grant_collect_link) ==
		      &fixture.frames[order[index++]]);
	}
	CHECK(index == count);
}

int main(int argc, char **argv)
{
	const char *name;
	int index;

	CHECK(argc == 2);
	name = argv[1];
	if (!strcmp(name, "authority")) {
		initialize(0);
		fixture.binding.current = false;
		CHECK(collect() == -EPERM && fixture.source_checks == 1 && !fixture.pool_checks);
		fixture.binding.current = true;
		CHECK(!collect() && fixture.source_checks == 2 && fixture.pool_checks == 1);
	} else if (!strcmp(name, "pending")) {
		initialize(3);
		retain_grant(0); /* Private or cancelled before run: never indexed. */
		start(2, true);
		fixture.binding.current = false;
		CHECK(collect() == -EPERM && !fixture.event_count && !fixture.pool_checks);
		fixture.binding.current = true;
		CHECK(!collect() && !fixture.event_count);
		fixture.unlink_slot = 2;
		CHECK(!collect() && fixture.event_count == 3);
		CHECK(fixture.frames[0].grant_held && !fixture.frames[0].grant_started);
		CHECK(!finish_grant_actor(&fixture.frames[0]));
		CHECK(!finish_grant_actor(&fixture.frames[0]));
		CHECK(!collect() && fixture.event_count == 4);
		require_order(NULL, 0);
	} else if (!strcmp(name, "order_reuse")) {
		initialize(4);
		start(2, false); start(0, false); start(3, false); start(1, false);
		require_order((int[]) { 0, 1, 2, 3 }, 4);
		fixture.release = OVERWRITE_FRAME;
		CHECK(!collect() && fixture.event_count == 12);
		for (index = 0; index < 12; ++index)
			CHECK(fixture.events[index] == (index / 3) * 10 + index % 3 + 1);
		require_order(NULL, 0);
		frame_init(&fixture.frames[1], &fixture.resources, &fixture.slots[1], NULL);
		start(1, true);
		CHECK(!collect() && fixture.event_count == 12);
		fixture.unlink_slot = 1;
		CHECK(!collect() && fixture.event_count == 15);
		require_order(NULL, 0);
	} else if (!strcmp(name, "return_image")) {
		initialize(1); start(0, false);
		fixture.frames[0].return_image = true;
		CHECK(!collect() && fixture.event_count == 2);
		CHECK(fixture.events[0] == SOURCE_PUT && fixture.events[1] == GRANT_FINISH);
		CHECK(fixture.frames[0].image_held && fixture.frames[0].image_user.active);
		fixture.frames[0].return_image = false;
		CHECK(!finish_image_actor(&fixture.frames[0]) && fixture.event_count == 3);
		require_order(NULL, 0);
	} else if (!strcmp(name, "source_failure") || !strcmp(name, "image_failure") ||
		   !strcmp(name, "grant_failure")) {
		initialize(3); start(1, false); start(2, true); start(0, false);
		fixture.fail_slot = 1;
		fixture.fail_kind = !strcmp(name, "source_failure") ? SOURCE_PUT :
			!strcmp(name, "image_failure") ? IMAGE_FINISH : GRANT_FINISH;
		CHECK(collect() == -EIO && !fixture.pool_checks);
		CHECK(fixture.frames[1].grant_held && fixture.frames[1].grant_user.active);
		require_order((int[]) { 1, 2 }, 2);
		fixture.fail_kind = 0;
		CHECK(!collect() && fixture.event_count == 6);
		for (index = 0; index < 6; ++index)
			CHECK(fixture.events[index] == (index / 3) * 10 + index % 3 + 1);
		require_order((int[]) { 2 }, 1);
		fixture.unlink_slot = 2;
		if (!strcmp(name, "grant_failure")) {
			fixture.fail_slot = 2;
			fixture.fail_kind = GRANT_FINISH;
			CHECK(collect() == -EIO && fixture.frames[2].grant_held);
			require_order((int[]) { 2 }, 1);
			fixture.fail_kind = 0;
		}
		CHECK(!collect() && fixture.event_count == 9);
		require_order(NULL, 0);
	} else if (!strcmp(name, "final_access")) {
		initialize(1); start(0, false);
		fixture.release = INACCESSIBLE_FRAME;
		CHECK(!collect() && fixture.event_count == 3 && fixture.pool_checks == 1);
		require_order(NULL, 0);
	} else {
		CHECK(false);
	}
	CHECK(!munmap(fixture.frames, fixture.map_bytes));
	free(fixture.slots);
	printf("PASS %s\n", name);
	return 0;
}
