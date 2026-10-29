/* SPDX-License-Identifier: GPL-2.0 */
/* Actual frame construction/retirement and mutex completion/caller transitions.
 * The wrapper and peer atomics are deterministic substitutes; this does not
 * execute generated code or establish Linux scheduling/memory-order behavior. */
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef struct { int counter; } atomic_t;
struct task_struct { int pid; } __attribute__((aligned(8)));
typedef struct task_struct *atomic_long_t;
typedef int raw_spinlock_t;
struct optimistic_spin_queue { atomic_t tail; };
struct list_head { struct list_head *next, *prev; };
struct hlist_node { struct hlist_node *next, **pprev; };
struct rcu_head { struct rcu_head *next; void (*fn)(struct rcu_head *); };
#define DECLARE_PER_CPU(type, name) extern type name
#define raw_cpu_read(name) ((void)sizeof(name), 0UL)
#define unlikely(x) (x)
#define KDLOCK_MUTEX_NUMA_BOUNDARY 1024
#define KD_MUTEX_TAIL_CPU_OFFSET 4
#define KD_MUTEX_OWNER_FLAGS 7UL
#include "../../../include/kd_regs.h"
#include "complete_types.h"

static struct task_struct executor = {1}, origin = {2}, outsider = {3};
static struct task_struct *current = &executor;
static struct kd_mutex gate, other_lock;
static struct kd_mutex_node nodes[3];
static struct kd_exec_context kd_exec_context;
static struct kd_exe_info image;
static struct kd_mutex_batch direct_batch, *live_batch;
static struct kd_exec_outer_unlock wrong_hook;
static struct kd_mutex_batch_diag final_diag;
static unsigned char poisoned[3][sizeof(struct kd_mutex_node)];
static bool node_poisoned[3], normal_loop, source_open, expect_bug;
static bool delay_link, insert_head, close_source, materialize, corrupt_after_pop;
static unsigned int checks, cases, case_id, bodies, wakes, handoffs, tail_attempts;
static unsigned int pending_polls, source_leases, source_puts, queue_finishes;
static unsigned int witnesses, observers, retired_observers, finish_calls;
static unsigned int pin_claims, pin_retired_claims, pin_cancelled_claims, pin_full_resumes;
static unsigned int pin_selections, pin_selection_ends, pin_drains, pin_retains;
static unsigned int owner_reads, fail_owner_read, physical_releases;
static unsigned long kd_exec_invariant_failures;
static unsigned long kd_mutex_frame_failure_count, kd_mutex_jit_not_ready_count;
static unsigned long kd_mutex_context_busy_count, kd_mutex_jit_failure_count;
static unsigned long kd_mutex_combiner_count, kd_mutex_handoff_count, kd_mutex_jit_success_count;
static int kd_mutex_batch_size = 8;
static jmp_buf bug_target;
#ifdef KDLOCK_SELFTEST
bool kd_hotlock_role_trace;
#endif

static void failed(int line, const char *condition)
{
    fprintf(stderr, "FAIL complete case=%u line=%d: %s\n", case_id, line, condition);
    exit(1);
}
#define CHECK(c) do { checks++; if (!(c)) failed(__LINE__, #c); } while (0)
static void fixture_bug(int line, const char *condition)
{
    if (expect_bug) longjmp(bug_target, 1);
    failed(line, condition);
}
#define BUG_ON(c) do { if (c) fixture_bug(__LINE__, #c); } while (0)
#define BUG() BUG_ON(true)
#define WARN_ON_ONCE(c) ((void)(c))
#define atomic64_inc(p) (++*(p))
#define this_cpu_inc(value) (++(value))
#define this_cpu_ptr(p) (p)
#define INIT_LIST_HEAD(p) do { (p)->next = (p)->prev = (p); } while (0)
static bool list_empty(const struct list_head *p) { return p->next == p; }
#define pr_info(...) do { if (0) printf(__VA_ARGS__); } while (0)
#define KD_PR_ERR(...) pr_info(__VA_ARGS__)
#define KD_PR_DEBUG(...) pr_info(__VA_ARGS__)
#define mutex_debug(...) do { } while (0)
#define prefetch(p) ((void)(p))
#define prefetchw(p) ((void)(p))
#define container_of(p, type, member) ((type *)((char *)(p) - offsetof(type, member)))
static int raw_smp_processor_id(void) { return 0; }
static int numa_node_id(void) { return 0; }
static void observe_address(const void *p)
{
    uintptr_t address = (uintptr_t)p;
    for (unsigned int i = 0; i < 3; i++)
        CHECK(!node_poisoned[i] || address < (uintptr_t)&nodes[i] ||
              address >= (uintptr_t)(&nodes[i] + 1));
}
#define READ_ONCE(value) ({ observe_address(&(value)); (value); })
#define WRITE_ONCE(target, value) ({ observe_address(&(target)); (target) = (value); })
#define smp_load_acquire(p) ({ __auto_type load_p = (p); observe_address(load_p); *load_p; })
static void before_store(const void *p, unsigned long value);
static void after_store(const void *p, unsigned long value);
#define smp_store_release(p, value) do { \
    __auto_type store_p = (p); __typeof__(*store_p) store_value = (value); \
    before_store(store_p, (unsigned long)store_value); \
    *store_p = store_value; after_store(store_p, (unsigned long)store_value); \
} while (0)
static unsigned long owner_snapshot(atomic_long_t *p)
{
    if (++owner_reads == fail_owner_read) return (unsigned long)&outsider;
    return (unsigned long)*p;
}
#define atomic_long_read(p) owner_snapshot(p)
#include "mutex_state_mock.h"
static void before_cas(const void *p);
#define cmpxchg(p, old, value) ({ \
    __auto_type cas_p = (p); __typeof__(*cas_p) cas_old = (old), cas_new = (value); \
    observe_address(cas_p); before_cas(cas_p); \
    __typeof__(*cas_p) cas_seen = *cas_p; \
    if (cas_seen == cas_old) { *cas_p = cas_new; } cas_seen; \
})
#define cmpxchg_acquire(p, old, value) cmpxchg(p, old, value)

static bool kd_source_is_open(void) { return source_open; }
static bool kd_source_frame_get(void)
{
    if (!source_open) return false;
    CHECK(!source_leases); source_leases++; return true;
}
static void kd_source_frame_put(void)
{
    CHECK(source_leases == 1 && !kd_exec_context.depth && !kd_exec_context.top);
    CHECK(!live_batch || !live_batch->nr_pins);
    source_leases--; source_puts++; live_batch = NULL;
}
static bool kd_exec_mutex_custody_accepted(const struct kd_exec_frame *frame)
{ (void)frame; return false; }
static bool kd_origin_mutex_owned(struct kd_mutex *lock, struct task_struct *task)
{
    return (atomic_long_read(&lock->owner) & ~KD_MUTEX_OWNER_FLAGS) == (unsigned long)task;
}
#ifdef KDLOCK_SELFTEST
static void kd_exec_selftest_relay_pop(struct kd_exec_frame *frame)
{
    CHECK(frame == kd_exec_context.top && frame->completion_seen);
    CHECK(source_leases == 1 && live_batch && live_batch->nr_pins == 1);
    CHECK(!live_batch->pin.node->completed && frame->state == KD_EXEC_FRAME_COMPLETE);
    observers++;
}
static void kd_exec_selftest_relay_retired(struct kd_exec_frame *frame)
{
    CHECK(frame->state == KD_EXEC_FRAME_UNUSED && !kd_exec_context.depth);
    CHECK(source_leases == 1 && live_batch && !live_batch->pin.node->completed);
    retired_observers++;
    if (corrupt_after_pop) gate.owner = &outsider;
}
#endif
/* Observe the commit boundary without replacing any production store. */
static void complete_commit_observe(struct kd_exec_context *ctx, struct kd_exec_frame *frame)
{
    CHECK(ctx == &kd_exec_context && ctx->top == frame && ctx->depth == 1);
    CHECK(live_batch && live_batch->nr_pins == 1 && live_batch->pin.node);
    CHECK(!live_batch->pin.node->completed && source_leases == 1);
}
#include "complete_frame.h"

/* No cold dispatcher, registration or native continuation is authorized by
 * these fast-COMPLETE cases. Retaining the branches in the actual executor
 * makes any accidental rerouting a fixture assertion, rather than a success. */
#define UNREACHABLE() CHECK(false)
struct kd_exec_frame *kd_exec_frame_push(const struct kd_regs *r, unsigned long ip,
    unsigned long lock, unsigned int depth, unsigned long gs, struct task_struct *task)
{ (void)r; (void)ip; (void)lock; (void)depth; (void)gs; (void)task; UNREACHABLE(); return NULL; }
struct kd_exec_frame *kd_exec_frame_push_borrowed(struct kd_regs *r, unsigned long ip,
    unsigned long lock, unsigned int depth, unsigned long gs, struct task_struct *task)
{ return kd_exec_frame_push(r, ip, lock, depth, gs, task); }
int kd_exec_frame_set_lock_entries(struct kd_exec_frame *f, const unsigned long *a,
    const enum kd_exec_lock_kind *k, void *const *n, const bool *r, unsigned int d)
{ (void)f; (void)a; (void)k; (void)n; (void)r; (void)d; UNREACHABLE(); return -EINVAL; }
int kd_exec_frame_record_event(struct kd_exec_frame *f, enum kd_exec_event e, const struct kd_regs *r)
{ (void)f; (void)e; (void)r; UNREACHABLE(); return -EINVAL; }
int kd_exec_frame_complete(struct kd_exec_frame *f)
{ (void)f; UNREACHABLE(); return -EINVAL; }
int kd_exec_frame_abort(struct kd_exec_frame *f)
{ (void)f; UNREACHABLE(); return -EINVAL; }
static int kd_mutex_jit_abort_cleanup(struct kd_exec_frame *f)
{ (void)f; UNREACHABLE(); return -EINVAL; }
int kd_exec_native_begin(struct kd_exec_frame *f, bool mutex)
{ (void)f; (void)mutex; UNREACHABLE(); return -EINVAL; }
int kd_exec_native_wait(struct kd_exec_frame *f)
{ (void)f; UNREACHABLE(); return -EINVAL; }
bool kd_exec_mutex_transfer_allowed(const struct kd_exec_frame *f)
{ (void)f; UNREACHABLE(); return false; }
unsigned int kd_exec_mutex_spin_count(const struct kd_exec_frame *f)
{ (void)f; UNREACHABLE(); return 0; }
int kd_mutex_transfer_owner(struct kd_mutex *lock, struct task_struct *task)
{ (void)lock; (void)task; UNREACHABLE(); return -EINVAL; }
static bool kd_mutex_try_role_swap(struct kd_mutex *lock, struct kd_mutex_node *node,
    struct kd_mutex_batch *batch, struct kd_exec_frame *frame)
{ (void)lock; (void)node; (void)batch; (void)frame; UNREACHABLE(); return false; }
static int kd_mutex_release_outer(struct kd_exec_frame *frame, struct kd_exec_outer_unlock *hook)
{ (void)frame; (void)hook; UNREACHABLE(); return -EINVAL; }
static void kd_mutex_wait_and_lock(struct kd_mutex *lock)
{ (void)lock; UNREACHABLE(); }
int _kd_mutex_unlock_checked(struct kd_mutex *lock)
{
    CHECK(lock == &gate && lock->owner == current && live_batch && !live_batch->nr_pins);
    CHECK(kd_mutex_gate_read(lock) == KD_MUTEX_GATE_HELD && source_leases == 1);
    CHECK(!kd_exec_context.depth && !kd_exec_context.top);
    lock->owner = NULL; kd_mutex_gate_set(lock, KD_MUTEX_GATE_FREE);
    physical_releases++; return 0;
}
static struct kd_exe_info *kd_get_exe(int pid, unsigned long ip)
{ CHECK(!pid && ip == 0x800); return &image; }
static bool kd_exe_entry_is_ready(struct kd_exe_info *exe, int pid, unsigned long ip)
{ return exe == &image && !pid && ip == 0x800; }
static void kd_exe_add_abi(int pid, unsigned long ip, int kind, unsigned int abi)
{ (void)pid; (void)ip; (void)kind; (void)abi; UNREACHABLE(); }
static int kd_exe_on_call_hl_entry(struct kd_exe_info *e, struct kd_regs *r,
    unsigned long ip, unsigned long lock)
{ (void)e; (void)r; (void)ip; (void)lock; UNREACHABLE(); return KD_EXE_RUN_ERROR; }
static int kd_exe_mutex_batch_resume(struct kd_exe_info *e, const struct kd_jit_batch_call *c)
{ (void)e; (void)c; UNREACHABLE(); return KD_EXE_RUN_ERROR; }
static u64 kd_exe_native_timing_start(void) { UNREACHABLE(); return 0; }
static void kd_exe_native_handoff_timing_end(bool mutex, u64 stamp)
{ (void)mutex; (void)stamp; UNREACHABLE(); }
static u64 kd_exe_queue_timing_start(void) { return 100; }
static void kd_exe_queue_timing_end(bool mutex, u64 *stamp, u64 end)
{
    CHECK(mutex && *stamp == 50 && end == 100 && live_batch);
    CHECK(kd_exec_context.depth == 1 && live_batch->nr_pins == 1);
    observe_address(stamp); *stamp = 0; queue_finishes++;
}
static void kd_jit_timing_end(unsigned int kind, u64 stamp)
{ (void)kind; (void)stamp; UNREACHABLE(); }
#define KD_JIT_TIME_WRAPPER 1
#define KD_JIT_TIME_DISPATCH 2
static void kd_exe_note_body(unsigned long ip, unsigned long lock, unsigned long value)
{ CHECK(ip == 0x800 && lock == (unsigned long)&gate && value == 1); witnesses++; }
#include "complete_wrapper.h"
static bool kd_exe_mutex_batch_prepare(struct kd_exe_info *exe,
    struct kd_exec_frame *frame, struct kd_jit_batch_call *call)
{
    CHECK(exe == &image && frame == kd_exec_context.top && frame->batch_lease);
    live_batch = container_of(frame->outer_unlock_hook, struct kd_mutex_batch, outer);
    CHECK(live_batch->pin.node == live_batch->current_node && live_batch->nr_pins == 1);
    CHECK(frame->borrowed_regs == &live_batch->current_node->regs);
    CHECK(frame->packet_state == KD_PACKET_MINIMAL && !frame->executed);
    memset(call, 0, sizeof(*call));
    call->entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
    call->packet_state = &frame->packet_state;
    call->lock = (unsigned long)&gate;
    call->complete = true;
    return true;
}
static void kd_jit_clobber_call_v1(struct kd_jit_batch_call *call)
{
    struct kd_exec_frame *frame = kd_exec_context.top;
    CHECK(frame && frame->executed && live_batch->proxy_epoch);
    CHECK(live_batch->pin.node->locked == KD_MUTEX_PROXY_READY);
    if (materialize) CHECK(!kd_exec_frame_prepare_mutex_complex(frame));
    if (close_source) source_open = false;
    *call->packet_state = KD_PACKET_COMPLETE;
    call->args[0] = KD_EXE_CLOBBER_COMPLETE;
    call->args[1] = 1;
    bodies++;
}

#define KD_MUTEX_PIN_INC(batch, name) ((void)(batch), pin_##name++)
#define KD_MUTEX_PIN_BEGIN(batch) ((void)(batch), pin_selections++)
#define KD_MUTEX_PIN_END(batch) ((void)(batch), pin_selection_ends++)
#define KD_MUTEX_PIN_STOP(batch, reason) do { } while (0)
#define KD_MUTEX_PIN_CONDITION(batch, condition, reason) (condition)
#define KD_MUTEX_PIN_EPOCH_RESULT(batch, accepted) do { (void)(batch); (void)(accepted); } while (0)
#define KD_MUTEX_PIN_EPOCH_READY(batch, head) do { (void)(batch); (void)(head); } while (0)
#define KD_MUTEX_PIN_ASSERT(batch, node) kd_mutex_batch_pin_assert(batch, node)
#define KD_MUTEX_PIN_DRAIN(batch, keep) do { (void)(batch); pin_drains++; pin_retains += !!(keep); } while (0)
static void kd_mutex_diag_finish(struct kd_mutex_batch_diag *diag)
{ final_diag = *diag; finish_calls++; }
static void cpu_relax(void);
#include "complete_mutex.h"

static void before_store(const void *p, unsigned long value)
{
    observe_address(p);
    for (unsigned int i = 0; i < 3; i++) {
        if (p != &nodes[i].locked) continue;
        if (value == KD_MUTEX_PROXY_CLAIMED) {
            CHECK(delay_link && !normal_loop && source_leases == 1);
            CHECK(!kd_exec_context.depth && live_batch->pin.node == &nodes[i]);
            CHECK(kd_mutex_gate_read(&gate) == KD_MUTEX_GATE_COMBINER);
        }
        if (value) continue;
        CHECK(source_leases == 1 && !kd_exec_context.depth && !kd_exec_context.top);
        CHECK(!live_batch->nr_pins && !live_batch->pin.node);
        if (nodes[i].completed) {
            CHECK(nodes[i].completed == KD_MUTEX_WAITER_PROCESSED);
            CHECK(nodes[i].packet_state == KD_PACKET_COMPLETE);
            CHECK(live_batch->current_retired && kd_mutex_jit_success_count == wakes + 1);
            CHECK(pin_retired_claims == wakes + 1);
            CHECK(nodes[i].counted_lock == &gate && nodes[i].count_seq == 2);
        } else {
            CHECK(delay_link && i == 1 && !normal_loop);
            handoffs++;
        }
    }
}
static void after_store(const void *p, unsigned long value)
{
    if (value) return;
    for (unsigned int i = 0; i < 3; i++) {
        if (p != &nodes[i].locked || !nodes[i].completed) continue;
        wakes++;
        if (insert_head) {
            CHECK(gate.delegation_tail == 0 && live_batch->current_retired);
            CHECK(gate.owner == current && kd_mutex_gate_read(&gate) == KD_MUTEX_GATE_COMBINER);
            /* A newly arriving head cannot acquire this still-owned gate. */
            gate.delegation_tail = nodes[2].tail;
            CHECK(!kd_mutex_gate_trylock(&gate));
        }
        memset(&nodes[i], 0xa5, sizeof(nodes[i]));
        memcpy(poisoned[i], &nodes[i], sizeof(nodes[i]));
        node_poisoned[i] = true;
    }
}
static void before_cas(const void *p)
{
    if (p != &gate.delegation_tail) return;
    tail_attempts++;
    CHECK(source_leases == 1 && live_batch && live_batch->nr_pins == 1);
    if (delay_link && tail_attempts == 1) gate.delegation_tail = nodes[1].tail;
}
static void cpu_relax(void)
{
    CHECK(delay_link && !normal_loop && source_leases == 1 && !wakes);
    CHECK(!kd_exec_context.depth && !kd_exec_context.top);
    CHECK(live_batch->nr_pins == 1 && live_batch->pin.node == &nodes[0]);
    CHECK(nodes[0].locked == KD_MUTEX_PROXY_CLAIMED && !nodes[0].completed);
    CHECK(nodes[0].packet_state == KD_PACKET_COMPLETE);
    CHECK(gate.owner == current && kd_mutex_gate_read(&gate) == KD_MUTEX_GATE_HELD);
    CHECK(++pending_polls <= 2);
    if (pending_polls == 2) nodes[0].next = &nodes[1];
}

static void reset_case(void)
{
    cases++; case_id++;
    memset(&gate, 0, sizeof(gate)); memset(&other_lock, 0, sizeof(other_lock));
    memset(nodes, 0, sizeof(nodes)); memset(&kd_exec_context, 0, sizeof(kd_exec_context));
    memset(&kd_exec_context.frames[0], 0xa5, sizeof(kd_exec_context.frames[0]));
    memset(&direct_batch, 0, sizeof(direct_batch)); memset(&wrong_hook, 0, sizeof(wrong_hook));
    memset(&final_diag, 0, sizeof(final_diag)); memset(node_poisoned, 0, sizeof(node_poisoned));
    memset(&image, 0, sizeof(image));
    current = &executor; gate.owner = current; gate.delegation_state.counter = KD_MUTEX_GATE_HELD;
    image.RIP = 0x800; image.lock_kind = KD_EXE_LOCK_MUTEX;
    for (unsigned int i = 0; i < 3; i++) {
        nodes[i].locked = KD_MUTEX_PROXY_READY; nodes[i].tail = (i + 2) << KD_MUTEX_TAIL_CPU_OFFSET;
        nodes[i].entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1; nodes[i].packet_state = KD_PACKET_MINIMAL;
        nodes[i].counted_lock = nodes[i].lock = &gate; nodes[i].count_seq = 2;
        nodes[i].task_struct_ptr = &origin; nodes[i].gsbase = 0x100;
        nodes[i].regs.ip = 0x800; nodes[i].regs.sp = 0x1000; nodes[i].queued_at_ns = 50;
        nodes[i].numa_node = i & 1;
    }
    gate.delegation_tail = nodes[0].tail;
    live_batch = NULL; normal_loop = false; source_open = true; expect_bug = false;
    delay_link = insert_head = close_source = materialize = corrupt_after_pop = false;
    bodies = wakes = handoffs = tail_attempts = pending_polls = source_leases = source_puts = 0;
    queue_finishes = witnesses = observers = retired_observers = finish_calls = 0;
    pin_claims = pin_retired_claims = pin_cancelled_claims = pin_full_resumes = 0;
    pin_selections = pin_selection_ends = pin_drains = pin_retains = 0;
    owner_reads = fail_owner_read = physical_releases = 0;
    kd_exec_invariant_failures = kd_mutex_frame_failure_count = kd_mutex_jit_not_ready_count = 0;
    kd_mutex_context_busy_count = kd_mutex_jit_failure_count = kd_mutex_combiner_count = 0;
    kd_mutex_handoff_count = kd_mutex_jit_success_count = 0;
}

static struct kd_exec_frame *direct_frame(void)
{
    source_leases = 1;
    direct_batch.lock = &gate; direct_batch.current_node = &nodes[0];
    direct_batch.outer.release = kd_mutex_release_outer;
    live_batch = &direct_batch;
    CHECK(kd_mutex_batch_epoch_begin(&direct_batch));
    CHECK(kd_mutex_batch_pin_select(&direct_batch, &nodes[0]));
    struct kd_exec_frame *frame = kd_exec_frame_push_mutex_batch(&nodes[0].regs,
        0x800, nodes[0].gsbase, &origin, &gate, &direct_batch.outer);
    CHECK(frame && frame == kd_exec_context.top && frame->borrowed_regs == &nodes[0].regs);
    frame->executed = true; frame->packet_state = KD_PACKET_COMPLETE;
    return frame;
}

static void caller_cases(void)
{
    for (unsigned int route = 0; route < 6; route++) {
        reset_case();
        if (route == 0 || route == 4) {
            nodes[0].next = &nodes[1]; gate.delegation_tail = nodes[1].tail;
        }
        insert_head = route == 2;
        delay_link = route == 3;
        close_source = route == 4;
        materialize = route == 1 || route == 4;
        unsigned int completed = (route == 0 || route == 4) ? 2 : 1;
        /* Closing source while the first body is admitted permits its return,
         * but the next private constructor correctly refuses new admission.
         * Keep that scenario to one already-admitted terminal body. */
        if (close_source) { nodes[0].next = NULL; gate.delegation_tail = nodes[0].tail; completed = 1; }
        CHECK(kd_mutex_run_combiner(&gate, &nodes[0], NULL, route == 5) ==
              (route == 5 ? KD_MUTEX_BATCH_RELEASED : KD_MUTEX_BATCH_OWNED));
        CHECK(bodies == completed && wakes == completed && witnesses == completed);
        CHECK(queue_finishes == completed && kd_mutex_jit_success_count == completed);
        CHECK(pin_claims == completed && pin_retired_claims == completed && !pin_cancelled_claims);
        CHECK(pin_selections == completed && pin_selection_ends == completed && !pin_full_resumes);
        CHECK(!source_leases && source_puts == 1 && !live_batch && !kd_exec_context.depth && !kd_exec_context.top);
        CHECK(finish_calls == 1 && final_diag.attempts == completed && final_diag.jit_completed == completed);
        CHECK(final_diag.jit_local == 1 && final_diag.jit_remote == completed - 1);
        CHECK(!final_diag.native_completed && !final_diag.owner_transfers && !final_diag.execution_refusals);
        CHECK(!kd_mutex_handoff_count && !kd_mutex_jit_failure_count && !kd_mutex_frame_failure_count);
        CHECK(final_diag.reason == (delay_link ? KD_MUTEX_DIAG_DELAYED_TAIL : KD_MUTEX_DIAG_EMPTY_TAIL));
        CHECK(pending_polls == (delay_link ? 2U : 0U) && handoffs == (delay_link ? 1U : 0U));
        CHECK(pin_retains == (delay_link ? 1U : 0U));
        CHECK(tail_attempts == (delay_link ? 2U : 1U));
        CHECK(gate.owner == (route == 5 ? NULL : current) &&
              kd_mutex_gate_read(&gate) == (route == 5 ? KD_MUTEX_GATE_FREE : KD_MUTEX_GATE_HELD));
        CHECK(physical_releases == (route == 5 ? 1U : 0U));
        CHECK(!insert_head || gate.delegation_tail == (u32)nodes[2].tail);
        for (unsigned int i = 0; i < completed; i++)
            CHECK(node_poisoned[i] && !memcmp(poisoned[i], &nodes[i], sizeof(nodes[i])));
#ifdef KDLOCK_SELFTEST
        CHECK(observers == completed && retired_observers == completed);
#else
        CHECK(!observers && !retired_observers);
#endif
    }
}

/* Every existing shape field plus explicit frame/batch/node pairing and the
 * fresh strict-READY proof must reject before changing queue publication. */
static void rejection_cases(void)
{
#ifndef KDLOCK_SELFTEST
    for (volatile unsigned int bad = 0; bad < 55; bad++) {
        reset_case();
        struct kd_exec_frame *frame = direct_frame();
        if (bad >= 24 && bad <= 29) CHECK(!kd_exec_frame_prepare_mutex_complex(frame));
        switch (bad) {
        case 0: frame->mutex_backend = false; break;
        case 1: frame->batch_lease = false; break;
        case 2: frame->spin_simple = true; break;
        case 3: frame->request_frame = true; break;
        case 4: frame->regs_borrowed = false; break;
        case 5: frame->parent = frame; break;
        case 6: frame->depth = 1; break;
        case 7: kd_exec_context.depth = 2; break;
        case 8: kd_exec_context.owner = &outsider; break;
        case 9: kd_exec_context.top = NULL; break;
        case 10: frame->entry_abi = KD_ENTRY_ABI_LEGACY; break;
        case 11: frame->packet_state = KD_PACKET_FULL; break;
        case 12: frame->executed = false; break;
        case 13: frame->state = KD_EXEC_FRAME_ERROR; break;
        case 14: frame->completion_seen = true; break;
        case 15: frame->outer_unlock_seen = true; break;
        case 16: frame->held_lock_depth = 2; break;
        case 17: frame->outer_lock_depth = 2; break;
        case 18: frame->jit_lock_depth = 2; break;
        case 19: frame->outer_lock_index = 1; break;
        case 20: frame->jit_lock_released[0] = true; break;
        case 21: frame->outer_lock_addr = (unsigned long)&other_lock; break;
        case 22: frame->jit_lock_addr[0] = (unsigned long)&other_lock; break;
        case 23: frame->jit_lock_kind[0] = KD_EXEC_LOCK_NATIVE; break;
        case 24: frame->control_call.phase = KD_CALL_ENTERED; break;
        case 25: frame->remote_result = KD_EXEC_REMOTE_WAITING; break;
        case 26: frame->resume_target = frame; break;
        case 27: frame->remote_request = (void *)1; break;
        case 28: frame->native_request = (void *)1; break;
        case 29: frame->native_link.next = NULL; break;
        case 30: frame->jit_lock_node[0] = &other_lock; break;
        case 31: frame->outer_unlock_hook = NULL; break;
        case 32: direct_batch.outer.released = true; break;
        case 33: frame->outer_unlock_hook = &wrong_hook; break;
        case 34: frame->borrowed_regs = &nodes[1].regs; break;
        case 35: direct_batch.lock = &other_lock; break;
        case 36: direct_batch.current_node = &nodes[1]; break;
        case 37: direct_batch.pin.node = &nodes[1]; break;
        case 38: direct_batch.nr_pins = 0; break;
        case 39: direct_batch.nr_pins = 2; break;
        case 40: nodes[0].counted_lock = &other_lock; break;
        case 41: nodes[0].count_seq += 2; break;
        case 42: nodes[0].locked = KD_MUTEX_WAIT; break;
        case 43: nodes[0].locked = KD_MUTEX_PROXY_CLAIMED; break;
        case 44: nodes[0].locked = 0; break;
        case 45: direct_batch.proxy_epoch = false; break;
        case 46: gate.owner = &outsider; break;
        case 47: gate.owner = (void *)((uintptr_t)&executor | 4UL); break;
        case 48: gate.delegation_state.counter = KD_MUTEX_GATE_HELD; break;
        case 49: gate.delegation_state.counter = KD_MUTEX_GATE_FREE; break;
        case 50: current = &outsider; break;
        case 51: fail_owner_read = owner_reads + 2; break; /* independent origin reread */
        case 52: CHECK(!kd_exec_frame_prepare_mutex_complex(frame));
                 frame->remote_result = KD_EXEC_REMOTE_NATIVE; break;
        case 53: frame->regs_ref = &nodes[1].regs; break;
        case 54: direct_batch.current_retired = true; break;
        }
        struct kd_exec_context before = kd_exec_context;
        struct kd_mutex_batch before_batch = direct_batch;
        struct kd_mutex_node before_node = nodes[0];
        expect_bug = true;
        if (!setjmp(bug_target)) {
            (void)kd_mutex_batch_complete_inline(&gate, &nodes[0], &direct_batch, frame);
            CHECK(false);
        }
        expect_bug = false;
        CHECK(!tail_attempts && !wakes && !pin_retired_claims && !source_puts);
        CHECK(!memcmp(&before, &kd_exec_context, sizeof(before)));
        CHECK(!memcmp(&before_batch, &direct_batch, sizeof(before_batch)));
        CHECK(!memcmp(&before_node, &nodes[0], sizeof(before_node)));
    }
#else
    /* Production SELFTEST deliberately uses generic retirement, preserving the
     * real pop observers. A changed owner in the retired observer must be
     * rejected by the caller's fresh pin proof before its publication. */
    reset_case(); corrupt_after_pop = true; expect_bug = true;
    if (!setjmp(bug_target)) {
        (void)kd_mutex_run_combiner(&gate, &nodes[0], NULL, false);
        CHECK(false);
    }
    expect_bug = false;
    CHECK(observers == 1 && retired_observers == 1 && !kd_exec_context.depth);
    CHECK(bodies == 1 && !wakes && source_leases == 1 && !source_puts);
    CHECK(!pin_retired_claims && nodes[0].locked == KD_MUTEX_PROXY_READY);
#endif
}

int main(void)
{
    caller_cases();
    rejection_cases();
    /* Keep direct construction linked into SELFTEST builds too, independently
     * checking actual pristine construction and generic frame retirement. */
    reset_case();
    struct kd_exec_frame *frame = direct_frame();
    /* Generic frame retirement still permits an exact HELD owner. */
    gate.delegation_state.counter = KD_MUTEX_GATE_HELD;
    CHECK(!kd_exec_frame_retire_mutex_batch(frame, &gate));
    CHECK(!kd_exec_context.depth && source_leases == 1 && !wakes);
    printf("mutex complete composition: %u cases, %u checks (%s)\n", cases, checks,
#ifdef KDLOCK_SELFTEST
           "SELFTEST observers"
#else
           "joint COMPLETE"
#endif
    );
    return 0;
}
