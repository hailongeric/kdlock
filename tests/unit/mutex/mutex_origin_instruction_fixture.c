/* SPDX-License-Identifier: GPL-2.0 */
/* Real cold producer/consumer and CPU instructions, explicit kernel-context
 * doubles. This proves packet/node handshake ordering, not Linux scheduling,
 * per-CPU allocation layout, module lifetime or JIT execution. */
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "kd_regs.h"
#include "kd_origin_service.h"

typedef uint32_t u32;
#define KD_ENTRY_ABI_MUTEX_CLOBBER_V1 2
#define KD_PACKET_FULL 0
#define KD_EXEC_LOCK_QUEUE_OWNER 1
#define KD_CALL_NONE 0
#define KD_CALL_COMPLETE 1
#define KD_CALL_ORIGIN_INSTRUCTION 2
#define KD_MUTEX_RESUME_INSTRUCTION 2
#define KD_MUTEX_GATE_COMBINER 3
#define KD_MUTEX_TAIL_CPU_OFFSET 2
#define KD_MUTEX_MAX_NODES 4
#define noinline __attribute__((noinline))
#define container_of(p,t,m) ((t *)((char *)(p) - offsetof(t,m)))
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL line=%d: %s\n", __LINE__, #c); exit(1); } } while (0)
#define BUG_ON(c) CHECK(!(c))
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_RELAXED)
#define WRITE_ONCE(x,v) __atomic_store_n(&(x),v,__ATOMIC_RELAXED)
#define smp_load_acquire(p) __atomic_load_n(p,__ATOMIC_ACQUIRE)
#define cpu_relax() __asm__ volatile("pause" ::: "memory")

/* Only fields reached by the actual cold service are represented. The real
 * headers and 320-byte node layout are checked by the provider build. */
struct task_struct { int pid; bool migration_disabled; };
struct list_head { bool empty; };
struct kd_mutex { struct task_struct *owner; int gate; };
struct kd_exec_outer_unlock {
    int (*release)(struct kd_exec_outer_unlock *);
    bool released;
};
struct kd_exec_frame {
    bool mutex_backend, complex_ready, regs_borrowed, request_frame;
    unsigned int entry_abi, packet_state, depth;
    void *parent, *resume_target, *remote_request, *native_request;
    bool remote_pending;
    struct list_head native_link;
    unsigned int jit_lock_depth, outer_lock_index, jit_lock_kind[1];
    bool jit_lock_released[1], outer_unlock_seen, completion_seen, executed;
    struct { bool transfer_requested, transferred, picked_up; } mutex_mixed;
    struct kd_exec_outer_unlock *outer_unlock_hook;
    struct { unsigned long target, stack, return_ip; unsigned int phase; } control_call;
    unsigned long outer_lock_addr;
    void *jit_lock_node[1];
    struct task_struct *logical_task;
    struct kd_regs regs;
};
struct kd_mutex_node {
    struct kd_mutex *lock, *counted_lock;
    struct task_struct *task_struct_ptr;
    unsigned int entry_abi;
    unsigned long count_seq, gsbase;
    int tail, slot;
    unsigned char locked, completed, native_resume;
    struct kd_origin_request *origin_request;
};
struct kd_mutex_batch {
    struct kd_exec_outer_unlock outer;
    struct kd_mutex *lock;
    struct kd_mutex_node *current_node;
    bool current_retired;
};
static struct task_struct executor = { 100, true }, waiter = { 200, true };
static _Thread_local struct task_struct *current;
static _Thread_local int fixture_cpu, fixture_preempt = 1;
static _Thread_local bool fixture_irq;
static const int nr_cpu_ids = 2;
static struct kd_mutex_node kd_mutex_nodes[KD_MUTEX_MAX_NODES][2];
static struct kd_mutex_node *node;
static struct kd_mutex lock;
static struct kd_mutex_batch batch;
static struct kd_exec_frame frame;
static unsigned int publications, acks, first_returned, second_published, ack_unstalled;
static unsigned int stop_waiter, reject_waiter;

#define this_cpu_ptr(p) (&(*(p))[fixture_cpu])
#define per_cpu_ptr(p,cpu) (&(*(p))[cpu])
static int raw_smp_processor_id(void) { return fixture_cpu; }
static int preempt_count(void) { return fixture_preempt; }
static bool irqs_disabled(void) { return fixture_irq; }
static unsigned long kd_read_kernel_gsbase(void) { return 0x1000 + fixture_cpu; }
static bool list_empty(struct list_head *list) { return list->empty; }
static bool kd_exec_frame_remote_pending(struct kd_exec_frame *f) { return f->remote_pending; }
static struct kd_regs *kd_exec_frame_regs(struct kd_exec_frame *f) { return &f->regs; }
static bool kd_exec_frame_can_borrow_locks(struct kd_exec_frame *f) { return f == &frame; }
static bool kd_mutex_delegation_owned(struct kd_mutex *l, struct task_struct *task) { return l->owner == task; }
static bool kd_origin_mutex_owned(struct kd_mutex *l, struct task_struct *task) { return l->owner == task; }
static int kd_mutex_gate_read(struct kd_mutex *l) { return l->gate; }
static int kd_mutex_release_outer(struct kd_exec_outer_unlock *hook) { (void)hook; CHECK(false); return -EINVAL; }

static void fixture_store_release(void *address, unsigned char value)
{
    if (current == &executor) {
        CHECK(address == &node->locked && !value);
        unsigned int count = __atomic_add_fetch(&publications, 1, __ATOMIC_RELAXED);
        __atomic_store_n((unsigned char *)address, value, __ATOMIC_RELEASE);
        if (count == 2) {
            CHECK(smp_load_acquire(&first_returned));
            CHECK(!smp_load_acquire(&ack_unstalled));
            __atomic_store_n(&second_published, 1, __ATOMIC_RELEASE);
        }
        return;
    }
    /* Inspect the cold request before publishing its final ACK. After that
     * store neither this hook nor the production waiter may touch it again. */
    struct kd_origin_request *request = READ_ONCE(node->origin_request);
    CHECK(request && address == &request->returned && value);
    CHECK(READ_ONCE(node->locked) == 1);
    CHECK(request->frame == &frame && request->regs == &frame.regs);
    CHECK(node->count_seq == request->count_sequence && node->counted_lock == &lock);
    unsigned int count = __atomic_add_fetch(&acks, 1, __ATOMIC_RELAXED);
    __atomic_store_n((unsigned char *)address, value, __ATOMIC_RELEASE);
    /* C returns from service 1 and can reuse its stack for service 2 while W
     * is still inside this ACK hook. No reset-to-zero ACK may be required. */
    if (count == 1) {
        while (!smp_load_acquire(&second_published)) cpu_relax();
        __atomic_store_n(&ack_unstalled, 1, __ATOMIC_RELEASE);
    }
}
#define smp_store_release(p,v) fixture_store_release((p),(v))
#include "production.h"

static void initialize(void)
{
    current = &executor;
    fixture_cpu = 0;
    lock = (struct kd_mutex){ &executor, KD_MUTEX_GATE_COMBINER };
    node = &kd_mutex_nodes[0][1];
    *node = (struct kd_mutex_node){
        .lock = &lock, .counted_lock = &lock, .task_struct_ptr = &waiter,
        .entry_abi = 2, .count_seq = 37, .gsbase = 0x1001,
        .tail = 2 << KD_MUTEX_TAIL_CPU_OFFSET, .slot = 0, .locked = 1,
    };
    batch = (struct kd_mutex_batch){ .outer.release = kd_mutex_release_outer,
        .lock = &lock, .current_node = node };
    frame = (struct kd_exec_frame){
        .mutex_backend = true, .complex_ready = true, .entry_abi = 2,
        .packet_state = KD_PACKET_FULL, .native_link.empty = true,
        .jit_lock_depth = 1, .jit_lock_kind = { KD_EXEC_LOCK_QUEUE_OWNER },
        .executed = true, .outer_unlock_hook = &batch.outer,
        .outer_lock_addr = (unsigned long)&lock, .jit_lock_node = { &lock },
        .logical_task = &waiter,
    };
}

static void *waiter_thread(void *unused)
{
    unsigned int serviced = 0;

    (void)unused;
    current = &waiter;
    fixture_cpu = 1;
    for (;;) {
        while (smp_load_acquire(&node->locked)) {
            if (smp_load_acquire(&stop_waiter)) return NULL;
            cpu_relax();
        }
        CHECK(READ_ONCE(node->native_resume) == KD_MUTEX_RESUME_INSTRUCTION);
        fixture_preempt = smp_load_acquire(&reject_waiter) ? 0 : 1;
        kd_mutex_origin_instruction_waiter(node);
        if (++serviced == 1) {
            /* The ACK hook returns only after C published service 2. A stale
             * post-ACK rearm must not overwrite that notification. Detect it
             * here as an assertion instead of accepting a later timeout. */
            CHECK(smp_load_acquire(&second_published));
            CHECK(smp_load_acquire(&node->locked) == 0);
            CHECK(READ_ONCE(node->native_resume) == KD_MUTEX_RESUME_INSTRUCTION);
        }
    }
}

int main(void)
{
    pthread_t thread;
    initialize();
    /* Refuse before publication for incompatible executor/root state. */
    for (unsigned int bad = 0; bad < 8; bad++) {
        initialize();
        switch (bad) {
        case 0: frame.regs_borrowed = true; break;
        case 1: frame.depth = 1; break;
        case 2: frame.jit_lock_depth = 2; break;
        case 3: frame.remote_pending = true; break;
        case 4: node->counted_lock = NULL; break;
        case 5: batch.current_retired = true; break;
        case 6: lock.owner = &waiter; break;
        case 7: fixture_irq = true; break;
        }
        CHECK(!kd_mutex_origin_instruction(&frame, KD_ORIGIN_RDTSC, 1));
        CHECK(!publications && !acks && !node->origin_request);
        fixture_irq = false;
    }
    initialize();
    CHECK(!pthread_create(&thread, NULL, waiter_thread, NULL));
    for (unsigned int sequence = 1; sequence <= 32; sequence++) {
        unsigned int kind = 1 + (sequence - 1) % 3;
        struct kd_regs before;
        for (unsigned int i = 0; i < sizeof(frame.regs)/sizeof(unsigned long); i++)
            ((unsigned long *)&frame.regs)[i] = 0xfeed000000000000UL + i;
        frame.regs.ip = 0x1000;
        frame.regs.sp = 0x8000;
        frame.regs.ax = frame.regs.cx = 0; /* CPUID leaf/subleaf zero. */
        before = frame.regs;
        __atomic_store_n(&reject_waiter, sequence == 10, __ATOMIC_RELEASE);
        int result = kd_mutex_origin_instruction(&frame, kind, sequence);
        if (sequence == 1) __atomic_store_n(&first_returned, 1, __ATOMIC_RELEASE);
        CHECK(result == (sequence == 10 ? 0 : 1));
        if (result) {
            CHECK(frame.regs.ax <= UINT32_MAX && frame.regs.dx <= UINT32_MAX);
            before.ax = frame.regs.ax; before.dx = frame.regs.dx;
            if (kind == KD_ORIGIN_RDTSCP || kind == KD_ORIGIN_CPUID) {
                CHECK(frame.regs.cx <= UINT32_MAX); before.cx = frame.regs.cx;
            }
            if (kind == KD_ORIGIN_CPUID) {
                CHECK(frame.regs.bx <= UINT32_MAX && frame.regs.bx);
                before.bx = frame.regs.bx;
            }
        }
        CHECK(!memcmp(&frame.regs, &before, sizeof(before)));
        CHECK(node->count_seq == 37 && node->counted_lock == &lock);
        CHECK(node->locked == 1 && !node->native_resume && !node->origin_request);
        CHECK(!node->completed && batch.current_node == node && !batch.current_retired);
        CHECK(lock.owner == &executor && lock.gate == KD_MUTEX_GATE_COMBINER);
        CHECK(frame.control_call.phase == KD_CALL_NONE && !frame.outer_unlock_seen);
    }
    CHECK(publications == 32 && acks == 32 && ack_unstalled);
    __atomic_store_n(&stop_waiter, 1, __ATOMIC_RELEASE);
    CHECK(!pthread_join(thread, NULL));
    puts("origin instruction: production two-thread handshake, retained packet/owner/node, refusal and post-ACK next publication passed");
    return 0;
}
