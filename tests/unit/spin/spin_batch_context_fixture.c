/* Actual batch loop; scripted services change physical executor context.
 * Queue, source leases, frame lifecycle and real context capture are tested by
 * their existing fixtures. This file isolates refresh/next-root control flow. */
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint64_t u64;
struct kd_regs;
struct kd_exec_frame;
struct kd_spin_node;
struct kd_spin_request;
struct kd_exe_info;
struct kd_spin_diag_slot;
struct qspinlock { int unused; };
#include "types.h"
struct kd_exec_frame {
    bool rwlock_admitted;
    unsigned int spin_kind;
    struct kd_exec_outer_unlock *outer_unlock_hook;
};
struct execution { struct kd_exec_frame frame; uint64_t queued_at_ns; };
struct kd_spin_node {
    struct kd_spin_node *next;
    struct execution *execution;
    u8 proxy_context;
    bool completed, locked;
};
struct kd_spin_cpu_state { struct kd_spin_node *local_queue_head, *local_queue_tail; };
static struct kd_spin_cpu_state kd_spin_cpu;
static int failures, checks, context_reads, calls, prepared, clears, fast_returns;
static int first_result;
static bool release_outer, fast_complete;
static u8 current_context, after_context;
static struct kd_spin_node *first_node;
#define CHECK(x) do { checks++; if (!(x)) { \
    fprintf(stderr, "FAIL line=%d: %s\n", __LINE__, #x); failures++; } } while (0)
#define BUG_ON(x) CHECK(!(x))
#define __maybe_unused __attribute__((unused))
#undef __always_inline
#define __always_inline inline __attribute__((always_inline))
#define this_cpu_ptr(p) (p)
#define unlikely(x) (x)
#define print_debug(...) ((void)0)
/* The omission mutant deliberately removes every call to this accessor. */
static u8 __maybe_unused kd_spin_proxy_context(void)
{ context_reads++; return current_context; }
static bool kd_exe_spin_batch_completed(const struct kd_jit_batch_call *call,
                                        const struct kd_exec_frame *frame)
{ (void)call; (void)frame; return fast_complete; }
static int kd_exec_frame_retire_single_spin(struct kd_exec_frame *frame)
{ CHECK(frame == &first_node->execution->frame); fast_returns++; return 0; }
static void kd_exe_queue_timing_end(bool mutex, uint64_t *queued, u64 end)
{ (void)mutex; (void)queued; (void)end; CHECK(false); }
static void kd_spin_debug_jit_success_simple(struct kd_spin_diag_slot *diag)
{ (void)diag; }
static void kd_spin_jit_prepare_complex(struct kd_exec_frame *frame)
{ CHECK(frame == &first_node->execution->frame); prepared++; }
static int execute_cs(struct qspinlock *lock, struct kd_spin_node *node,
                      struct kd_spin_batch *batch)
{
    CHECK(lock == batch->lock && node->locked && !node->completed);
    calls++;
    batch->pending = false; /* production execute_cs consumes a pending return */
    if (node != first_node)
        return KD_EXE_NO_RUN; /* next root reaches dispatcher exactly once */
    current_context = after_context;
    batch->outer.released = release_outer;
    if (first_result == KD_EXE_NATIVE_DONE) {
        node->locked = false;
        node->completed = true; /* native transaction already completed */
    }
    return first_result;
}
static struct kd_spin_node *get_next_node(struct kd_spin_node *node, u16 *budget)
{ CHECK(*budget); --*budget; return node->next; }
static void kd_spin_prefetch_request(struct kd_spin_node *node) { (void)node; }
static bool kd_spin_batch_prepare_simple(struct kd_spin_batch *batch,
                                        struct kd_spin_node *node)
{ (void)batch; (void)node; return false; }
static int kd_entry_abi_spin_clobber(unsigned int abi) { (void)abi; return 1; }
static void kd_jit_clobber_call_v1(struct kd_jit_batch_call *call)
{ (void)call; CHECK(false); }
static void kd_jit_legacy_batch_call(struct kd_jit_batch_call *call)
{ (void)call; CHECK(false); }
static void clear_locked_set_completed(struct kd_spin_node *node)
{ CHECK(node->locked && !node->completed); node->locked = false; node->completed = true; clears++; }
static bool kd_spin_batch_can_continue(struct kd_spin_node *node, unsigned int count)
{ return node && node->next && count < 1024; }
#include "production.h"

static void one_case(bool pending, int result, bool released, u8 after, u8 next_context)
{
    struct qspinlock lock = { 0 };
    struct execution execution[3] = { 0 };
    struct kd_spin_node nodes[3] = { 0 };
    struct kd_spin_batch batch = {
        .lock = &lock, .cursor = nodes, .next = &nodes[1], .pending = pending,
        .numa_scan_left = 1024, .counter = pending ? 1 : 0, .proxy_context = 1,
    };
    bool terminal = result == KD_EXE_NO_RUN || result == KD_EXE_RUN_ERROR || released;
    bool next_admitted = !terminal && after && after == next_context;
    memset(&kd_spin_cpu, 0, sizeof(kd_spin_cpu));
    context_reads = calls = prepared = clears = fast_returns = 0;
    first_result = result; release_outer = released; after_context = after;
    current_context = 1; first_node = nodes; fast_complete = false;
    for (unsigned int i = 0; i < 3; i++) {
        nodes[i].next = i < 2 ? &nodes[i + 1] : NULL;
        nodes[i].execution = &execution[i];
        nodes[i].locked = true;
        nodes[i].proxy_context = i ? next_context : 1;
    }
    kd_spin_batch_run(&batch);
    CHECK(context_reads == (terminal ? 0 : 1));
    CHECK(calls == 1 + (int)next_admitted);
    CHECK(prepared == (int)pending && !fast_returns);
    CHECK(batch.counter == (terminal ? 1 : 2));
    CHECK(batch.proxy_context == (terminal ? 1 : after));
    CHECK(batch.outer.released == released);
    CHECK(clears == (result == 0));
    CHECK(nodes[0].completed == (result == 0 || result == KD_EXE_NATIVE_DONE));
    CHECK(!nodes[1].completed && nodes[1].locked && !nodes[2].completed);
    if (result == KD_EXE_NO_RUN || result == KD_EXE_RUN_ERROR)
        CHECK(batch.next == nodes);
    else if (!released)
        CHECK(batch.next == &nodes[1]);
}

static void fast_case(void)
{
    struct qspinlock lock = { 0 };
    struct execution execution[3] = { 0 };
    struct kd_spin_node nodes[3] = { 0 };
    struct kd_spin_batch batch = {
        .lock = &lock, .cursor = nodes, .next = &nodes[1], .pending = true,
        .numa_scan_left = 1024, .counter = 1, .proxy_context = 1,
    };
    memset(&kd_spin_cpu, 0, sizeof(kd_spin_cpu));
    context_reads = calls = prepared = clears = fast_returns = 0;
    current_context = 1; first_node = nodes; fast_complete = true;
    for (unsigned int i = 0; i < 3; i++) {
        nodes[i].next = i < 2 ? &nodes[i + 1] : NULL;
        nodes[i].execution = &execution[i]; nodes[i].locked = true;
        nodes[i].proxy_context = 1;
    }
    kd_spin_batch_run(&batch);
    CHECK(!context_reads && !prepared && fast_returns == 1 && calls == 1);
    CHECK(clears == 1 && nodes[0].completed && !nodes[1].completed);
    CHECK(batch.counter == 2 && batch.next == &nodes[1]);
    fast_complete = false;
}

int main(void)
{
    const int results[] = { 0, KD_EXE_NO_RUN, KD_EXE_RUN_ERROR, KD_EXE_NATIVE_DONE };
    const u8 contexts[] = { 0, 1, 3 };
#ifdef NUMA_AWARE
    CHECK(sizeof(struct kd_spin_batch) == 200);
#else
    CHECK(sizeof(struct kd_spin_batch) == 192);
#endif
    CHECK(sizeof(((struct kd_spin_batch *)0)->counter) == sizeof(u16));
    CHECK(offsetof(struct kd_spin_batch, counter) ==
          offsetof(struct kd_spin_batch, numa_scan_left) + sizeof(u16));
    for (int pending = 0; pending < 2; pending++)
        for (unsigned int r = 0; r < sizeof(results) / sizeof(results[0]); r++)
            for (int released = 0; released < 2; released++)
                for (unsigned int c = 0; c < sizeof(contexts) / sizeof(contexts[0]); c++)
                    for (u8 next = 1; next <= 3; next += 2)
                        one_case(pending, results[r], released, contexts[c], next);
    fast_case();
    printf("spin batch context: %d checks, %d failures; batch=%zu counter=%zu NUMA=%u\n",
           checks, failures, sizeof(struct kd_spin_batch),
           sizeof(((struct kd_spin_batch *)0)->counter),
#ifdef NUMA_AWARE
           1U
#else
           0U
#endif
    );
    return failures ? 1 : 0;
}
