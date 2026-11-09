/* SPDX-License-Identifier: GPL-2.0 */
/* Actual production code with deterministic primitives. The model below is an
 * ownership/notification oracle, not another queue or a scheduler model. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t u64;
#define U64_MAX UINT64_MAX
#define TASK_UNINTERRUPTIBLE 1U
#define TASK_INTERRUPTIBLE 2U
#define TASK_KILLABLE 4U
typedef struct { bool held, valid; } raw_spinlock_t;
struct wake_q_node { struct wake_q_node *next; };
struct task_struct { struct wake_q_node wake_q; bool fatal, ordinary; unsigned int refs, wakes; };
struct wake_q_head { struct wake_q_node *first, **lastp; };
#define WAKE_Q_TAIL ((struct wake_q_node *)1UL)
static unsigned int held_guards, pins, checks;
static bool irq_disabled;
#define BUG_ON(value) assert(!(value))
#define READ_ONCE(value) __atomic_load_n(&(value), __ATOMIC_RELAXED)
#define WRITE_ONCE(value, next) __atomic_store_n(&(value), (next), __ATOMIC_RELAXED)
#define smp_store_release(ptr, value) __atomic_store_n((ptr), (value), __ATOMIC_RELEASE)
#define lockdep_assert_held(guard) assert((guard)->valid && (guard)->held)
#define DEFINE_PER_CPU(type, name) type name
#define this_cpu_ptr(ptr) (ptr)
#define local_irq_save(flags) do { (flags) = irq_disabled; irq_disabled = true; } while (0)
#define local_irq_restore(flags) do { irq_disabled = (flags); } while (0)
#define cmpxchg_relaxed(ptr, old, next) ({ \
    __typeof__(*(ptr)) expected = (old); \
    __atomic_compare_exchange_n((ptr), &expected, (next), false, \
                               __ATOMIC_RELAXED, __ATOMIC_RELAXED); expected; })
static void preempt_disable(void) { ++pins; }
static void preempt_enable(void) { assert(pins); --pins; }
static void smp_mb__before_atomic(void) { __atomic_thread_fence(__ATOMIC_SEQ_CST); }
static bool signal_pending_state(unsigned int state, struct task_struct *task)
{ return state == TASK_INTERRUPTIBLE ? task->fatal || task->ordinary : state == TASK_KILLABLE && task->fatal; }
static void get_task_struct(struct task_struct *task) { assert(task->refs); ++task->refs; }
#include "wait_queue_production.h"

static void hold(raw_spinlock_t *guard)
{ assert(guard->valid && !guard->held); guard->held = true; ++held_guards; }
static void drop(raw_spinlock_t *guard)
{ assert(guard->valid && guard->held && held_guards); guard->held = false; --held_guards; }
static void wake_init(struct wake_q_head *wake)
{ wake->first = WAKE_Q_TAIL; wake->lastp = &wake->first; }
static void wake_deliver(struct wake_q_head *wake)
{
    struct wake_q_node *node = wake->first;
    assert(!held_guards);
    while (node != WAKE_Q_TAIL) {
        struct wake_q_node *next = node->next;
        struct task_struct *task = (void *)((char *)node - offsetof(struct task_struct, wake_q));
        assert(task->refs > 1); node->next = NULL; --task->refs; ++task->wakes; node = next;
    }
    wake_init(wake);
}
struct item { struct kd_wait_request request; struct kd_wait_node node; struct task_struct origin, waiter; };
struct model { void *owner; unsigned int readers, calls; };
static unsigned long holder;
static struct task_struct executor = { .refs = 1 };
static void init_item(struct item *item, bool delegate, unsigned int state)
{
    memset(item, 0, sizeof(*item)); item->origin.refs = item->waiter.refs = 1;
    kd_wait_request_init(&item->request, NULL, 0, &item->origin, &item->waiter, state, delegate, NULL);
    kd_wait_node_init(&item->node, &item->request, KD_WAIT_ACQUISITION);
    assert(!pins && !irq_disabled);
}
static bool grant(struct kd_wait_request *request, void *argument)
{
    struct model *model = argument;
    lockdep_assert_held(request->guard); ++model->calls;
    if (model->owner || model->readers) return false;
    model->owner = request->identity; return true;
}
static void ring(const struct kd_wait_queue *queue, struct kd_wait_node *const *expected, unsigned int count)
{
    struct kd_wait_node *node = kd_wait_first_locked(queue);
    assert(!!node == !!count);
    for (unsigned int i = 0; i < count; ++i) {
        assert(node == expected[i] && node->queue_head == queue->head);
        assert(node->next && node->prev);
        assert(node->next->prev == node && node->prev->next == node);
        assert(node->generation == node->request->generation && node->request->memberships);
        node = kd_wait_next_locked(queue, node);
    }
    assert(!node); ++checks;
}
static void cancel(const struct kd_wait_queue *queue, struct item *item, struct model *model)
{
    item->origin.fatal = true;
    assert(kd_wait_decide_locked(queue, &item->request, item->request.generation, grant, model) == KD_WAIT_CANCELED);
    assert(!item->node.queue_head && !item->request.memberships);
    kd_wait_set_state_locked(&item->request, KD_WAIT_RETIRED);
}

static void test_heads(void)
{
    raw_spinlock_t guard = { .valid = true };
    struct kd_wait_node *head = NULL;
    struct kd_wait_queue queue = kd_wait_queue_view(&guard, &head);
    struct item a, b, c; struct model model = { .owner = &holder };
    struct kd_wait_node *abc[3] = { &a.node, &b.node, &c.node };
    init_item(&a, true, TASK_KILLABLE); init_item(&b, false, TASK_KILLABLE);
    init_item(&c, true, TASK_KILLABLE);
    hold(&guard); ring(&queue, abc, 0);
    kd_wait_publish_locked(&queue, &a.node); ring(&queue, abc, 1);
    kd_wait_publish_locked(&queue, &b.node); kd_wait_publish_locked(&queue, &c.node); ring(&queue, abc, 3);
    cancel(&queue, &b, &model);
    struct kd_wait_node *ac[2] = { &a.node, &c.node }; ring(&queue, ac, 2);
    assert(!b.request.memberships && !b.request.acquisition);
    cancel(&queue, &a, &model);
    struct kd_wait_node *only_c[1] = { &c.node }; ring(&queue, only_c, 1);
    model.owner = NULL;
    assert(kd_wait_decide_locked(&queue, &c.request, c.request.generation, grant, &model) == KD_WAIT_GRANTED);
    ring(&queue, abc, 0); assert(!c.request.acquisition);
    kd_wait_finish_local_locked(&c.request);
    assert(model.owner == c.request.identity); /* Result delivery is not unlock. */
    kd_wait_set_state_locked(&c.request, KD_WAIT_RETIRED);
    void *identity = c.request.identity; u64 generation = c.request.generation;
    model.owner = NULL;
    kd_wait_request_init(&c.request, NULL, 0, &c.origin, &c.waiter, TASK_KILLABLE, true, NULL);
    assert(c.request.identity == identity && c.request.generation > generation);
    kd_wait_node_init(&c.node, &c.request, KD_WAIT_ACQUISITION);
    kd_wait_publish_locked(&queue, &c.node); ring(&queue, only_c, 1);
    assert(!kd_wait_find_locked(&queue, identity, generation));
    assert(kd_wait_find_locked(&queue, identity, c.request.generation) == &c.request);
    unsigned int calls = model.calls;
    assert(kd_wait_decide_locked(&queue, &c.request, generation, grant, &model) == KD_WAIT_STALE);
    assert(c.request.state == KD_WAIT_QUEUED && model.calls == calls);
    model.owner = &holder; cancel(&queue, &c, &model); ring(&queue, abc, 0); drop(&guard);
}

static void test_roles_move_wake_cancel(void)
{
    raw_spinlock_t guard = { .valid = true };
    struct kd_wait_node *head = NULL;
    struct kd_wait_queue queue = kd_wait_queue_view(&guard, &head);
    struct item a, b, c, local; struct kd_wait_selection selection = { 0 };
    struct model model = { .owner = &holder }; struct wake_q_head wake;
    init_item(&a, true, TASK_KILLABLE); init_item(&b, true, TASK_KILLABLE); init_item(&c, true, TASK_KILLABLE);
    init_item(&local, false, TASK_KILLABLE);
    wake_init(&wake); hold(&guard);
    kd_wait_publish_locked(&queue, &a.node); kd_wait_publish_locked(&queue, &b.node); kd_wait_publish_locked(&queue, &c.node);
    kd_wait_publish_locked(&queue, &local.node);
    assert(!kd_wait_select_locked(&queue, &local.request, &selection, &executor));
    assert(local.request.state == KD_WAIT_QUEUED && !local.request.selection);
    cancel(&queue, &local, &model);
    kd_wait_move_before_locked(&queue, &c.node, &a.node);
    struct kd_wait_node *cab[3] = { &c.node, &a.node, &b.node }; ring(&queue, cab, 3);
    assert(c.request.acquisition == &c.node && c.request.state == KD_WAIT_QUEUED);
    kd_wait_move_before_locked(&queue, &b.node, &a.node);
    struct kd_wait_node *cba[3] = { &c.node, &b.node, &a.node }; ring(&queue, cba, 3);
    kd_wait_move_before_locked(&queue, &a.node, &c.node); /* Circular tail before head. */
    struct kd_wait_node *acb[3] = { &a.node, &c.node, &b.node }; ring(&queue, acb, 3);
    kd_wait_collect_wake_locked(&queue, &wake); kd_wait_collect_request_wake_locked(&a.request, &wake);
    assert(a.waiter.refs == 2 && b.waiter.refs == 2 && c.waiter.refs == 2);
    drop(&guard); wake_deliver(&wake);
    assert(a.waiter.refs == 1 && a.waiter.wakes == 1 && !a.origin.wakes);
    hold(&guard); cancel(&queue, &a, &model); cancel(&queue, &b, &model); cancel(&queue, &c, &model);
    assert(model.owner == &holder && !head); drop(&guard);
    for (unsigned int position = 0; position < 3; ++position) {
        struct item items[3]; struct kd_wait_node *remaining[2]; unsigned int count = 0;
        hold(&guard);
        for (unsigned int i = 0; i < 3; ++i) { init_item(&items[i], i != 1, TASK_KILLABLE); kd_wait_publish_locked(&queue, &items[i].node); }
        cancel(&queue, &items[position], &model);
        for (unsigned int i = 0; i < 3; ++i) if (i != position) remaining[count++] = &items[i].node;
        ring(&queue, remaining, 2);
        for (unsigned int i = 0; i < 3; ++i) if (i != position) cancel(&queue, &items[i], &model);
        assert(!head && model.owner == &holder); drop(&guard);
    }
}

static void test_signal_and_selection(void)
{
    raw_spinlock_t guard = { .valid = true };
    struct kd_wait_node *head = NULL, *condition_head = NULL;
    struct kd_wait_queue queue = kd_wait_queue_view(&guard, &head);
    struct kd_wait_queue condition_queue = kd_wait_queue_view(&guard, &condition_head);
    struct item item; struct model model = { 0 }; struct kd_wait_node condition;
    struct kd_wait_selection selection = { 0 };
    init_item(&item, false, TASK_KILLABLE); item.origin.fatal = true;
    hold(&guard); kd_wait_publish_locked(&queue, &item.node);
    assert(kd_wait_decide_locked(&queue, &item.request, item.request.generation, grant, &model) == KD_WAIT_GRANTED);
    assert(kd_wait_decide_locked(&queue, &item.request, item.request.generation, grant, &model) == KD_WAIT_GRANTED);
    assert(model.calls == 1 && item.request.state == KD_WAIT_ACQUIRED);
    kd_wait_finish_local_locked(&item.request); kd_wait_set_state_locked(&item.request, KD_WAIT_RETIRED); drop(&guard);
    init_item(&item, false, TASK_KILLABLE); item.origin.ordinary = true; item.waiter.fatal = true; model.owner = &holder;
    hold(&guard); kd_wait_publish_locked(&queue, &item.node);
    assert(kd_wait_decide_locked(&queue, &item.request, item.request.generation, grant, &model) == KD_WAIT_PENDING);
    cancel(&queue, &item, &model); assert(model.owner == &holder); drop(&guard);
    init_item(&item, false, TASK_INTERRUPTIBLE); item.origin.ordinary = true;
    hold(&guard); kd_wait_publish_locked(&queue, &item.node);
    assert(kd_wait_decide_locked(&queue, &item.request, item.request.generation, grant, &model) == KD_WAIT_CANCELED);
    kd_wait_set_state_locked(&item.request, KD_WAIT_RETIRED); drop(&guard);
    init_item(&item, true, TASK_KILLABLE); model.owner = NULL; model.readers = 1;
    kd_wait_node_init(&condition, &item.request, KD_WAIT_CONDITION);
    hold(&guard); kd_wait_publish_locked(&queue, &item.node);
    assert(kd_wait_select_locked(&queue, &item.request, &selection, &executor));
    kd_wait_link_locked(&condition_queue, &condition); item.origin.fatal = true;
    assert(kd_wait_decide_locked(&queue, &item.request, item.request.generation, grant, &model) == KD_WAIT_CLEANUP_REQUIRED);
    assert(!head && condition_head == &condition && !kd_wait_cancel_ack_locked(&item.request));
    kd_wait_selection_drop_locked(&item.request, &selection);
    assert(item.request.state == KD_WAIT_CANCELING && !selection.request);
    kd_wait_unlink_locked(&condition_queue, &condition);
    assert(kd_wait_cancel_ack_locked(&item.request) && model.readers == 1);
    kd_wait_set_state_locked(&item.request, KD_WAIT_RETIRED); drop(&guard);
    init_item(&item, false, TASK_UNINTERRUPTIBLE);
    kd_wait_node_init(&item.node, &item.request, KD_WAIT_CONDITION); kd_wait_node_init(&condition, &item.request, KD_WAIT_CONDITION);
    hold(&guard); kd_wait_link_locked(&queue, &item.node); kd_wait_link_locked(&condition_queue, &condition);
    assert(item.request.state == KD_WAIT_PRIVATE && !item.request.acquisition);
    kd_wait_unlink_locked(&queue, &item.node); assert(item.request.memberships == &condition);
    kd_wait_unlink_locked(&condition_queue, &condition); kd_wait_set_state_locked(&item.request, KD_WAIT_RETIRED); drop(&guard);
}

static void test_rebind_handoff(void)
{
  for (unsigned int handoff = 0; handoff < 2; ++handoff) {
    raw_spinlock_t old = { .valid = true }, retained = { .valid = true };
    struct kd_wait_node *head = NULL; struct kd_wait_queue queue = kd_wait_queue_view(&old, &head);
    struct item item; struct model model = { 0 }; struct kd_wait_selection selection = { 0 };
    init_item(&item, true, TASK_KILLABLE); hold(&old); kd_wait_publish_locked(&queue, &item.node);
    assert(kd_wait_select_locked(&queue, &item.request, &selection, &executor));
    assert(kd_wait_decide_locked(&queue, &item.request, item.request.generation, grant, &model) == KD_WAIT_GRANTED);
    kd_wait_selection_drop_locked(&item.request, &selection);
    /* Fixture has no cached old-guard actor. Production transport must prove
     * that separately before any body can perform the final object release. */
    assert(kd_wait_rebind_locked(&item.request, &retained) == &old);
    drop(&old); old.valid = false;
    hold(&retained); kd_wait_set_state_locked(&item.request, KD_WAIT_EXECUTING);
    assert(model.owner == item.request.identity); /* Ongoing authority transferred. */
    if (handoff) {
        kd_wait_handoff_locked(&item.request);
    } else {
        model.owner = NULL;
        kd_wait_set_state_locked(&item.request, KD_WAIT_RELEASED);
        kd_wait_set_state_locked(&item.request, KD_WAIT_RETURN_ACK);
    }
    assert(item.request.state == KD_WAIT_RETURN_ACK && !!model.owner == !!handoff);
    kd_wait_set_state_locked(&item.request, KD_WAIT_RETIRED); drop(&retained);
  }
}
int main(int argc, char **argv)
{
    test_heads();
    if (argc == 1 || strcmp(argv[1], "head")) {
        test_roles_move_wake_cancel(); test_signal_and_selection(); test_rebind_handoff();
    }
    assert(!held_guards && !pins && !irq_disabled);
    printf("PASS production common queue: %u topology checks; deterministic primitives only\n", checks);
    return 0;
}
