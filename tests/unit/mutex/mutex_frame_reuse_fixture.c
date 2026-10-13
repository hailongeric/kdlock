/* SPDX-License-Identifier: GPL-2.0 */
/* Production frame construction/rebind/retirement; source, CPU context and
 * original Linux-owner checks are controlled substitutes. */
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int atomic_t;
typedef struct { void *opaque; } wait_queue_head_t;
struct task_struct { int pid; };
struct list_head { struct list_head *next, *prev; };
#include "types.h"

static struct kd_exec_context context;
static struct task_struct owner = {1}, waiters[] = {{2}, {3}};
static struct task_struct *current = &owner;
struct mutex { struct task_struct *owner; };
static bool source_open = true;
static unsigned int checks;
#define CHECK(c) do { checks++; if (!(c)) { fprintf(stderr, "FAIL frame reuse line=%d: %s\n", __LINE__, #c); exit(1); } } while (0)
#define READ_ONCE(x) (x)
static struct kd_exec_context *kd_exec_current_context(void) { return &context; }
static bool kd_source_is_open(void) { return source_open; }
static bool kd_origin_mutex_owned(struct mutex *lock, struct task_struct *task)
{ return lock->owner == task; }
static bool list_empty(const struct list_head *head) { return head->next == head; }
bool kd_exec_frame_remote_pending(const struct kd_exec_frame *frame)
{ return frame->remote_request != NULL; }
#include "production.h"

static void finish(struct kd_exec_frame *frame, struct kd_mutex *lock)
{
    frame->executed = true;
    frame->packet_state = KD_PACKET_COMPLETE;
    CHECK(!kd_exec_frame_retire_mutex_batch(frame, lock));
    CHECK(!context.depth && !context.owner && !context.top);
    CHECK(frame->state == KD_EXEC_FRAME_UNUSED && frame->completion_seen);
}

int main(void)
{
    struct mutex native = {.owner = current};
    struct kd_mutex lock = {.origin_mutex_addr = (unsigned long)&native,
                            .physical_owner = current}, other_lock = {0};
    struct kd_exec_outer_unlock hook = {0};
    struct kd_regs packets[2] = {0}, poison;
    struct kd_exec_frame *frame, saved, wrong_slot;
    struct kd_exec_context before;

    frame = kd_exec_frame_push_mutex_batch(&packets[0], 0x1000, 0x2000,
                                           &waiters[0], &lock, &hook);
    CHECK(frame == &context.frames[0] && frame->regs_borrowed && frame->batch_lease);
    /* A live request cannot be replaced, even by a pointer to the right slot. */
    before = context;
    CHECK(!kd_exec_frame_rebind_mutex_batch(frame, &packets[1], 0x1100, 0x2100,
                                            &waiters[1], &lock, &hook));
    CHECK(!memcmp(&context, &before, sizeof(context)));
    finish(frame, &lock);

    saved = *frame;
    /* Refusal leaves both the empty CPU context and retired record intact. */
    for (unsigned int bad = 0; bad < 11; bad++) {
        struct kd_exec_frame *candidate = frame;
        struct kd_mutex *candidate_lock = &lock;
        *frame = saved;
        switch (bad) {
        case 0: source_open = false; break;
        case 1: frame->complex_ready = true; frame->native_request = (void *)1; break;
        case 2: wrong_slot = *frame; candidate = &wrong_slot; break;
        case 3: context.depth = 1; break;
        case 4: candidate_lock = &other_lock; break;
        case 5: hook.released = true; break;
        case 6: frame->completion_seen = false; break;
        case 7: frame->outer_unlock_seen = false; break;
        case 8: frame->jit_lock_released[0] = false; break;
        case 9: context.owner = &waiters[0]; break;
        case 10: frame->state = KD_EXEC_FRAME_RUNNING; break;
        }
        before = context;
        CHECK(!kd_exec_frame_rebind_mutex_batch(candidate, &packets[1], 0x1100,
                                                0x2100, &waiters[1], candidate_lock, &hook));
        CHECK(!memcmp(&context, &before, sizeof(context)));
        source_open = true; hook.released = false;
        context.depth = 0; context.owner = NULL;
    }
    *frame = saved;
    for (unsigned int round = 0; round < 64; round++) {
        unsigned int next = (round + 1) & 1, old = round & 1;
        /* A completed caller has already repurposed all its packet bytes. */
        memset(&packets[old], 0xa5, sizeof(packets[old]));
        poison = packets[old];
        packets[next].ip = 0x1000 + round;
        packets[next].sp = 0x4000 + round;
        CHECK(kd_exec_frame_rebind_mutex_batch(frame, &packets[next],
                    packets[next].ip, 0x2000 + round, &waiters[next], &lock, &hook) == frame);
        CHECK(context.depth == 1 && context.owner == current && context.top == frame);
        CHECK(kd_exec_frame_regs(frame) == &packets[next] && frame->logical_task == &waiters[next]);
        CHECK(frame->entry_ip == 0x1000 + round && frame->gsbase == 0x2000 + round);
        CHECK(frame->packet_state == KD_PACKET_MINIMAL && !frame->executed &&
              !frame->completion_seen && !frame->outer_unlock_seen && !frame->jit_lock_released[0]);
        CHECK(frame->jit_lock_addr[0] == (unsigned long)&native &&
              frame->jit_lock_kind[0] == KD_EXEC_LOCK_QUEUE_OWNER && frame->jit_lock_depth == 1);
        /* Reuse never weakens the existing real-owner retirement condition. */
        frame->executed = true; frame->packet_state = KD_PACKET_COMPLETE;
        native.owner = &waiters[0];
        CHECK(kd_exec_frame_retire_mutex_batch(frame, &lock) == -EINVAL && context.depth == 1);
        native.owner = current;
        finish(frame, &lock);
        CHECK(!memcmp(&packets[old], &poison, sizeof(poison)));
    }
    printf("mutex frame reuse: %u checks passed\n", checks);
    return 0;
}
