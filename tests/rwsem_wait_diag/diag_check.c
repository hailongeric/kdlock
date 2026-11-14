/* SPDX-License-Identifier: GPL-2.0-only */
/* VM-only helper excerpts with controlled scheduling and queue endpoints. */
#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include "kd_rw_wait_diag.h"

#define __aligned(n) __attribute__((aligned(n)))
#define WQ_FLAG_EXCLUSIVE 1
#define TASK_NORMAL 3
struct list_head { struct list_head *next, *prev; };
typedef struct wait_queue_entry wait_queue_entry_t;
struct wait_queue_entry {
	unsigned int flags;
	void *private;
	int (*func)(wait_queue_entry_t *, unsigned int, int, void *);
	struct list_head entry;
};
typedef struct { int lock; struct list_head head; } wait_queue_head_t;
#include "diag_row.h"
static int *held_lock;
static unsigned int state_sets, plain_prepares, plain_wakes;
static void *retire_page;
static size_t page_bytes;

static void init_list(struct list_head *entry) { entry->next = entry->prev = entry; }
static bool list_empty(struct list_head *entry) { return entry->next == entry; }
static void remove_entry(struct list_head *entry)
{
	entry->prev->next = entry->next;
	entry->next->prev = entry->prev;
	init_list(entry);
}
#define spin_lock_irqsave(lock, flags) do { (flags) = 0; assert(!held_lock); \
	held_lock = (lock); assert(!*held_lock); *held_lock = 1; } while (0)
#define spin_unlock_irqrestore(lock, flags) do { (void)(flags); assert(held_lock == (lock)); \
	*held_lock = 0; held_lock = NULL; } while (0)
static void __add_wait_queue(wait_queue_head_t *queue, wait_queue_entry_t *wait)
{
	assert(held_lock == &queue->lock && list_empty(&wait->entry));
	wait->entry.next = queue->head.next;
	wait->entry.prev = &queue->head;
	queue->head.next->prev = &wait->entry;
	queue->head.next = &wait->entry;
}
static void set_current_state(int state)
{
	assert(held_lock && state == TASK_NORMAL);
	state_sets++;
}
static int autoremove_wake_function(wait_queue_entry_t *wait, unsigned int mode, int flags, void *key)
{
	int accepted = *(int *)wait->private;
	assert(held_lock && mode == TASK_NORMAL && !flags && !key);
	if (accepted) {
		remove_entry(&wait->entry);
		if (wait == retire_page)
			assert(mprotect(retire_page, page_bytes, PROT_NONE) == 0);
	}
	return accepted;
}
static void prepare_to_wait(wait_queue_head_t *queue, wait_queue_entry_t *wait, int state)
{
	unsigned long flags;
	plain_prepares++;
	wait->flags &= ~WQ_FLAG_EXCLUSIVE;
	spin_lock_irqsave(&queue->lock, flags);
	if (list_empty(&wait->entry))
		__add_wait_queue(queue, wait);
	set_current_state(state);
	spin_unlock_irqrestore(&queue->lock, flags);
}
static int __wake_up(wait_queue_head_t *queue, unsigned int mode, int nr, void *key)
{
	struct list_head *entry, *next;
	unsigned long flags;
	assert(!nr);
	if (!key)
		plain_wakes++;
	spin_lock_irqsave(&queue->lock, flags);
	for (entry = queue->head.next; entry != &queue->head; entry = next) {
		wait_queue_entry_t *wait = (void *)((char *)entry - offsetof(wait_queue_entry_t, entry));
		next = entry->next;
		wait->func(wait, mode, 0, key);
	}
	spin_unlock_irqrestore(&queue->lock, flags);
	return 0;
}
#define wake_up_all(queue) ((void)__wake_up(queue, TASK_NORMAL, 0, NULL))
#include "diag_functions.h"

static void init_wait(wait_queue_entry_t *wait, int *accept)
{
	wait->flags = WQ_FLAG_EXCLUSIVE;
	wait->private = accept;
	wait->func = autoremove_wake_function;
	init_list(&wait->entry);
}
int main(int argc, char **argv)
{
	struct kd_rw_wait_diag_row row = { 0 };
	wait_queue_head_t queue = { 0 };
	wait_queue_entry_t read, write;
	bool registered = false, other = false;
	int accept = 1, reject = 0;
	assert(argc == 2);
	init_list(&queue.head);
	init_wait(&read, &accept);
	init_wait(&write, &reject);
	if (!strcmp(argv[1], "registration")) {
		kd_rw_wait_diag_prepare(&row, false, &registered, &queue, &read, TASK_NORMAL);
		kd_rw_wait_diag_prepare(&row, false, &registered, &queue, &read, TASK_NORMAL);
		kd_rw_wait_diag_wake(&row, &queue, KD_RW_DIAG_WAKE_WRITE);
		kd_rw_wait_diag_prepare(&row, false, &registered, &queue, &read, TASK_NORMAL);
		assert(row.counts.value[KD_RW_DIAG_READ_PREPARE] == 3 && state_sets == 3);
		assert(row.counts.value[KD_RW_DIAG_READ_FIRST] == 1);
		assert(row.counts.value[KD_RW_DIAG_READ_REINSERT] == 1);
		assert(row.counts.value[KD_RW_DIAG_READ_LINKED] == 1);
		assert(!(read.flags & WQ_FLAG_EXCLUSIVE));
		remove_entry(&read.entry);
	} else if (!strcmp(argv[1], "callbacks")) {
		kd_rw_wait_diag_prepare(&row, false, &registered, &queue, &read, TASK_NORMAL);
		kd_rw_wait_diag_prepare(&row, true, &other, &queue, &write, TASK_NORMAL);
		kd_rw_wait_diag_wake(&row, &queue, KD_RW_DIAG_WAKE_READ);
		assert(row.counts.value[KD_RW_DIAG_READ_VISITS] == 1);
		assert(row.counts.value[KD_RW_DIAG_READ_ACCEPT] == 1);
		assert(row.counts.value[KD_RW_DIAG_WRITE_VISITS] == 1);
		assert(row.counts.value[KD_RW_DIAG_WRITE_ACCEPT] == 0);
		assert(row.counts.value[KD_RW_DIAG_WAKE_READ] == 1);
		assert(list_empty(&read.entry) && !list_empty(&write.entry));
		remove_entry(&write.entry);
	} else if (!strcmp(argv[1], "final_callback")) {
		wait_queue_entry_t *wait;
		page_bytes = (size_t)sysconf(_SC_PAGESIZE);
		retire_page = mmap(NULL, page_bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
		assert(retire_page != MAP_FAILED);
		wait = retire_page;
		init_wait(wait, &accept);
		kd_rw_wait_diag_prepare(&row, true, &registered, &queue, wait, TASK_NORMAL);
		kd_rw_wait_diag_wake(&row, &queue, KD_RW_DIAG_WAKE_QUEUE);
		assert(row.counts.value[KD_RW_DIAG_WRITE_ACCEPT] == 1 && list_empty(&queue.head));
		assert(munmap(retire_page, page_bytes) == 0);
	} else if (!strcmp(argv[1], "disabled")) {
		kd_rw_wait_diag_prepare(NULL, false, &registered, &queue, &read, TASK_NORMAL);
		assert(read.func == autoremove_wake_function && !registered && plain_prepares == 1);
		kd_rw_wait_diag_wake(NULL, &queue, KD_RW_DIAG_WAKE_WRITE);
		assert(plain_wakes == 1 && list_empty(&queue.head));
	} else if (!strcmp(argv[1], "cancel_cleanup")) {
		kd_rw_wait_diag_prepare(&row, true, &registered, &queue, &write, TASK_NORMAL);
		/* A completed finish_wait removes this temporary entry even if an
		 * independently retained canceled MCS record has not departed yet. */
		remove_entry(&write.entry);
		kd_rw_wait_diag_wake(&row, &queue, KD_RW_DIAG_WAKE_CANCEL);
		assert(!row.counts.value[KD_RW_DIAG_WRITE_VISITS] && list_empty(&queue.head));
	} else {
		return 2;
	}
	printf("PASS %s\n", argv[1]);
	return 0;
}
