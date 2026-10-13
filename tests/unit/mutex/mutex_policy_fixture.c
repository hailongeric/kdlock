// SPDX-License-Identifier: GPL-2.0
/* Production policy/routing with deterministic clock and publication races. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); exit(1); } } while (0)
typedef struct { unsigned long value; } atomic_long_t;
struct kernel_param { void *arg; };
struct kernel_param_ops {
    int (*set)(const char *, const struct kernel_param *);
    int (*get)(char *, const struct kernel_param *);
};
struct kd_mutex {
    int waiter_slot;
    unsigned int tail;
    unsigned long physical_owner;
    unsigned int locked, waiter_count;
    unsigned long origin_mutex_addr;
};
struct mutex { int unused; };
struct task_struct { int pid; char comm[16]; };
static struct task_struct task = {.pid = 7};
static struct task_struct *current = &task;
enum kd_entry_abi { KD_ENTRY_ABI_MUTEX_CLOBBER_V1 = 2 };

#define KD_MUTEX_WAITER_SLOTS 1024
#define ____cacheline_aligned __attribute__((aligned(64)))
#define DEFINE_PER_CPU(type, name) type name[2]
#define per_cpu(name, cpu) ((name)[cpu])
#define this_cpu_inc(name) (++(name)[fixture_cpu])
#define this_cpu_ptr(ptr) ({ CHECK(pin > 0); &(*(ptr))[fixture_cpu]; })
#define for_each_possible_cpu(cpu) for ((cpu) = 0; (cpu) < 2; (cpu)++)
#define module_param(name, type, mode)
#define module_param_cb(name, ops, arg, mode) \
    static const void *param_##name __attribute__((unused)) = (ops)
#define MODULE_PARM_DESC(name, description)
#define PAGE_SIZE 4096
#define scnprintf snprintf
#define max_t(type, a, b) ((type)(a) > (type)(b) ? (type)(a) : (type)(b))
#define likely(value) (value)
#define unlikely(value) (value)
#define READ_ONCE(value) (value)
#define WRITE_ONCE(value, new) ((value) = (new))
#define smp_rmb() do {} while (0)
#define time_before(a, b) ((long)((a) - (b)) < 0)

static unsigned long jiffies;
static int pin, node, numa_queries, native_calls, refs, queued, observations;
static int fixture_cpu, pins, samples, source_queries, comm_queries, active_queries, shadow_queries;
static bool admitted = true, source_open = true, active, comm_match = true;
static bool mutex_native_route;
static struct kd_mutex *shadow;
static int race_kind, compare_calls;
static unsigned long competing_word, competing_deadline;
static unsigned long *deadline_address;

static void preempt_disable(void) { pin++; pins++; }
static void preempt_enable(void) { CHECK(pin > 0); pin--; }
static int numa_node_id(void) { CHECK(pin > 0); numa_queries++; return node; }
static unsigned long msecs_to_jiffies(unsigned int ms) { return ((unsigned long)ms * TEST_HZ + 999) / 1000; }
static unsigned long atomic_long_read(const atomic_long_t *v) { return v->value; }
static unsigned long atomic_long_read_acquire(const atomic_long_t *v) { return v->value; }
static void atomic_long_set_release(atomic_long_t *v, unsigned long n) { v->value = n; }
static unsigned long atomic_long_cmpxchg(atomic_long_t *v, unsigned long old, unsigned long next)
{
    unsigned long seen;
    compare_calls++;
    if (race_kind == 1) {
        race_kind = 0;
        v->value = competing_word;
        *deadline_address = competing_deadline;
    } else if (race_kind == 2) {
        v->value += 1UL << 35;
    }
    seen = v->value;
    if (seen == old)
        v->value = next;
    return seen;
}
static int kstrtouint(const char *value, unsigned int base, unsigned int *out)
{
    char *end;
    unsigned long parsed = strtoul(value, &end, base);
    if (*end || parsed > UINT_MAX)
        return -EINVAL;
    *out = parsed;
    return 0;
}
static int param_get_uint(char *buffer, const struct kernel_param *kp)
{ return snprintf(buffer, PAGE_SIZE, "%u", *(unsigned int *)kp->arg); }

static void kd_hotlock_mutex_entry(void) { CHECK(pin > 0); observations++; }
static bool kd_hotlock_record_mutex_pinned(unsigned long address)
{ CHECK(pin > 0 && address); samples++; return admitted; }
static void kd_origin_mutex_lock(struct mutex *lock)
{ CHECK(!pin && lock); native_calls++; }
static bool kd_source_is_open(void) { source_queries++; return source_open; }
#define kd_comm_matches(target, name) (comm_queries++, comm_match)
static bool kd_mutex_task_active(struct task_struct *t) { CHECK(t == current); active_queries++; return active; }
static struct kd_mutex *get_kd_mutex_shadow(struct mutex *lock) { CHECK(lock); shadow_queries++; return shadow; }
static bool kd_mutex_task_get(struct task_struct *t) { CHECK(t == current && !pin); refs++; return true; }
static void kd_exe_add_abi(int a, unsigned long ip, int kind, enum kd_entry_abi abi)
{ CHECK(!a && ip && kind == 1 && abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1); }
static void _kd_mutex_lock_abi(struct kd_mutex *lock, unsigned long sp,
                             unsigned long ip, unsigned long bp, enum kd_entry_abi abi)
{ CHECK(lock && sp && ip && bp && abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1 && !pin); queued++; }
#define KD_EXE_LOCK_MUTEX 1
static void kd_pr_info(const char *format, ...) { (void)format; }
#define KD_PR_INFO(...) kd_pr_info(__VA_ARGS__)
#define raw_smp_processor_id() 0U

#include "policy_code.h"

static void reset(void)
{
    memset(kd_mutex_policy_slots, 0, sizeof(kd_mutex_policy_slots));
    mutex_native_epoch_ms = 128;
    mutex_native_probe_ms = 1;
    mutex_native_epoch_cache = false;
    mutex_native_epoch_cross_node = false;
    memset(kd_mutex_policy_cache, 0, sizeof(kd_mutex_policy_cache));
    memset(kd_mutex_policy_native_epochs, 0, sizeof(kd_mutex_policy_native_epochs));
    memset(kd_mutex_policy_probes, 0, sizeof(kd_mutex_policy_probes));
    memset(kd_mutex_policy_remote_vetoes, 0, sizeof(kd_mutex_policy_remote_vetoes));
    pin = numa_queries = native_calls = refs = queued = observations = 0;
    fixture_cpu = pins = samples = source_queries = comm_queries = active_queries = shadow_queries = 0;
    admitted = source_open = comm_match = true;
    active = mutex_native_route = false;
    race_kind = compare_calls = 0;
    node = 66666;
    jiffies = 123;
}

static void expect_mode(int slot, enum kd_mutex_policy_mode mode)
{ CHECK((kd_mutex_policy_slots[slot].word.value & KD_MUTEX_POLICY_MODE_MASK) == (unsigned long)mode); }

static void phases(void)
{
    struct kd_mutex lock = {.waiter_slot = 0, .tail = 113, .physical_owner = 17,
                            .locked = 3, .waiter_count = 19};
    struct kd_mutex saved = lock, other = {.waiter_slot = 1};
    unsigned long deadline;
    char stats[PAGE_SIZE];
    reset();
    mutex_native_epoch_ms = 0;
    CHECK(!kd_mutex_policy_native(&lock));
    CHECK(!numa_queries && !compare_calls && !pin);
    mutex_native_epoch_ms = 128;
    CHECK(!kd_mutex_policy_native(&lock));
    expect_mode(0, KD_MUTEX_POLICY_PROBE);
    CHECK((unsigned int)(kd_mutex_policy_slots[0].word.value >> KD_MUTEX_POLICY_NODE_SHIFT) == 66666);
    CHECK(!kd_mutex_policy_native(&lock));
    deadline = kd_mutex_policy_slots[0].deadline;
    CHECK(deadline == jiffies + msecs_to_jiffies(1));
    jiffies = deadline;
    CHECK(kd_mutex_policy_native(&lock));
    expect_mode(0, KD_MUTEX_POLICY_NATIVE);
    CHECK(!kd_mutex_policy_native(&other));
    expect_mode(1, KD_MUTEX_POLICY_PROBE);
    deadline = kd_mutex_policy_slots[0].deadline;
    jiffies = deadline - 1;
    CHECK(kd_mutex_policy_native(&lock));
    jiffies++;
    CHECK(!kd_mutex_policy_native(&lock));
    expect_mode(0, KD_MUTEX_POLICY_PROBE);
    node = INT_MAX;
    CHECK(!kd_mutex_policy_native(&lock));
    expect_mode(0, KD_MUTEX_POLICY_MULTINODE);
    deadline = kd_mutex_policy_slots[0].deadline;
    node = 66666;
    jiffies = deadline - 1;
    CHECK(!kd_mutex_policy_native(&lock));
    CHECK(kd_mutex_policy_slots[0].deadline == deadline);
    jiffies = deadline;
    CHECK(!kd_mutex_policy_native(&lock));
    expect_mode(0, KD_MUTEX_POLICY_PROBE);
    jiffies = kd_mutex_policy_slots[0].deadline;
    CHECK(kd_mutex_policy_native(&lock));
    node = INT_MAX;
    CHECK(!kd_mutex_policy_native(&lock));
    expect_mode(0, KD_MUTEX_POLICY_MULTINODE);
    CHECK(!memcmp(&lock, &saved, sizeof(lock)) && !pin);
    CHECK(kd_mutex_policy_stats_get(stats, NULL) > 0);
    CHECK(!strcmp(stats, "2 4 2\n"));
    other.waiter_slot = -1;
    CHECK(!kd_mutex_policy_native(&other));
    other.waiter_slot = KD_MUTEX_WAITER_SLOTS;
    CHECK(!kd_mutex_policy_native(&other));
}

static void clocks_and_races(void)
{
    struct kd_mutex lock = {.waiter_slot = 2};
    struct kd_mutex_policy_slot *slot = &kd_mutex_policy_slots[2];
    unsigned long before;
    reset();
    jiffies = ULONG_MAX - 4;
    CHECK(!kd_mutex_policy_native(&lock));
    jiffies = slot->deadline;
    CHECK(kd_mutex_policy_native(&lock));
    CHECK(slot->deadline < msecs_to_jiffies(128));
    jiffies = slot->deadline - 1;
    CHECK(kd_mutex_policy_native(&lock));
    jiffies++;
    CHECK(!kd_mutex_policy_native(&lock));
    jiffies = slot->deadline;
    CHECK(kd_mutex_policy_native(&lock));
    jiffies = slot->deadline + (1UL << 32);
    CHECK(!kd_mutex_policy_native(&lock));
    expect_mode(2, KD_MUTEX_POLICY_PROBE);

    reset();
    CHECK(!kd_mutex_policy_native(&lock));
    jiffies = slot->deadline;
    competing_word = kd_mutex_policy_word(KD_MUTEX_POLICY_MULTINODE, node, slot->word.value);
    competing_deadline = jiffies + msecs_to_jiffies(128);
    deadline_address = &slot->deadline;
    race_kind = 1;
    CHECK(!kd_mutex_policy_native(&lock));
    CHECK(slot->word.value == competing_word && slot->deadline == competing_deadline);
    CHECK(!kd_mutex_policy_native_epochs[0]);

    slot->word.value = kd_mutex_policy_word(KD_MUTEX_POLICY_UPDATING, node, slot->word.value);
    before = slot->word.value;
    compare_calls = 0;
    CHECK(!kd_mutex_policy_native(&lock));
    CHECK(slot->word.value == before && !compare_calls);

    reset();
    CHECK(!kd_mutex_policy_native(&lock));
    jiffies = slot->deadline;
    compare_calls = 0;
    race_kind = 2;
    CHECK(!kd_mutex_policy_native(&lock));
    CHECK(compare_calls == 4 && !pin && !kd_mutex_policy_native_epochs[0]);
}

static void routing_and_parameters(void)
{
    struct kd_mutex lock = {.waiter_slot = 3, .tail = 77, .physical_owner = 44,
                            .locked = 3, .waiter_count = 9};
    struct kd_mutex saved = lock;
    struct mutex original;
    struct kernel_param kp = {.arg = &mutex_native_epoch_ms};
    unsigned long result;
    reset();
    CHECK(!kd_mutex_policy_ms_set("0", &kp) && !mutex_native_epoch_ms);
    CHECK(kd_mutex_policy_ms_set("1001", &kp) == -EINVAL && !mutex_native_epoch_ms);
    CHECK(!kd_mutex_policy_ms_set("128", &kp) && mutex_native_epoch_ms == 128);
    kp.arg = &mutex_native_probe_ms;
    CHECK(kd_mutex_policy_ms_set("0", &kp) == -EINVAL && mutex_native_probe_ms == 1);
    CHECK(!kd_mutex_policy_ms_set("1000", &kp) && mutex_native_probe_ms == 1000);
    CHECK(!kd_mutex_policy_ms_set("1", &kp));
    shadow = &lock;
    CHECK(!kd_mutex_policy_native(&lock));
    jiffies = kd_mutex_policy_slots[3].deadline;
    result = kd_mutex_contended_acquire(&original, 1, 2, 3, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
    CHECK(result == (unsigned long)current && native_calls == 1 && !refs && !queued);
    CHECK(observations == 1 && !memcmp(&lock, &saved, sizeof(lock)) && !pin);
    jiffies = kd_mutex_policy_slots[3].deadline;
    result = kd_mutex_contended_acquire(&original, 1, 2, 3, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
    CHECK(!result && refs == 1 && queued == 1 && native_calls == 1 && observations == 2);
    CHECK(!memcmp(&lock, &saved, sizeof(lock)) && !pin);
    /* Fresh policy is never consulted when ordinary admission/source refuses. */
    admitted = false;
    numa_queries = 0;
    CHECK(kd_mutex_contended_acquire(&original, 1, 2, 3, KD_ENTRY_ABI_MUTEX_CLOBBER_V1) == (unsigned long)current);
    CHECK(!numa_queries && refs == 1 && queued == 1 && observations == 3);
    admitted = true;
    source_open = false;
    CHECK(kd_mutex_contended_acquire(&original, 1, 2, 3, KD_ENTRY_ABI_MUTEX_CLOBBER_V1) == (unsigned long)current);
    CHECK(!numa_queries && refs == 1 && queued == 1 && observations == 4);
}

static void clear_traffic(void)
{
    CHECK(!pin);
    pins = numa_queries = native_calls = refs = queued = observations = samples = 0;
    source_queries = comm_queries = active_queries = shadow_queries = 0;
}

static unsigned long acquire(struct mutex *lock)
{
    unsigned long result = kd_mutex_contended_acquire(lock, 1, 2, 3,
                                                     KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
    CHECK(!pin && observations == 1 && samples == 1);
    return result;
}

static void cached_routing(void)
{
    struct mutex original, other_original;
    struct kd_mutex lock = {.waiter_slot = 4, .tail = 13, .physical_owner = 47,
                            .locked = 3, .waiter_count = 7,
                            .origin_mutex_addr = (unsigned long)&original};
    struct kd_mutex saved = lock;
    struct kd_mutex other = {.waiter_slot = 5,
                             .origin_mutex_addr = (unsigned long)&other_original};
    struct kd_mutex_policy_slot *slot = &kd_mutex_policy_slots[4];
    unsigned long remote_before;
    reset();
    mutex_native_epoch_cache = true;
    shadow = &lock;
    CHECK(!acquire(&original));
    CHECK(refs == 1 && queued == 1 && source_queries == 1 && shadow_queries == 1);
    CHECK(numa_queries == 1 && pins == 2);
    CHECK(kd_mutex_policy_cache[0].address == (unsigned long)&original);
    CHECK(kd_mutex_policy_cache[0].shadow == &lock && !kd_mutex_policy_cache[1].shadow);

    /* A native hit shares the sampler pin and precedes all KD eligibility,
     * task references, address-table lookup and publication, even while old
     * queue/owner state remains live. Source closing is not native exclusion. */
    jiffies = slot->deadline;
    source_open = comm_match = false;
    active = true;
    clear_traffic();
    CHECK(acquire(&original) == (unsigned long)current);
    CHECK(native_calls == 1 && !refs && !queued && numa_queries == 1 && pins == 1);
    CHECK(!source_queries && !comm_queries && !active_queries && !shadow_queries);
    CHECK(!memcmp(&lock, &saved, sizeof(lock)));

    /* A cached KD decision does not grant admission or re-observe locality. */
    jiffies = slot->deadline;
    clear_traffic();
    CHECK(acquire(&original) == (unsigned long)current);
    CHECK(source_queries == 1 && !shadow_queries && !refs && !queued);
    CHECK(pins == 1 && numa_queries == 1);
    source_open = comm_match = true;
    active = false;
    clear_traffic();
    CHECK(!acquire(&original));
    CHECK(source_queries == 1 && shadow_queries == 1 && refs == 1 && queued == 1);
    CHECK(pins == 1 && numa_queries == 1);

    jiffies = slot->deadline;
    clear_traffic();
    CHECK(acquire(&original) == (unsigned long)current);
    remote_before = kd_mutex_policy_remote_vetoes[0];
    node = INT_MAX;
    clear_traffic();
    CHECK(!acquire(&original));
    expect_mode(4, KD_MUTEX_POLICY_MULTINODE);
    CHECK(kd_mutex_policy_remote_vetoes[0] == remote_before + 1);
    CHECK(numa_queries == 1 && pins == 1 && source_queries == 1 && shadow_queries == 1);
    CHECK(refs == 1 && queued == 1 && !memcmp(&lock, &saved, sizeof(lock)));

    /* Migration observes a different CPU's cache, which must first miss. */
    fixture_cpu = 1;
    clear_traffic();
    CHECK(!acquire(&original));
    CHECK(numa_queries == 1 && pins == 2 && shadow_queries == 1);
    CHECK(kd_mutex_policy_cache[1].shadow == &lock && kd_mutex_policy_cache[0].shadow == &lock);

    /* A valid but stale hint for a different original address cannot select
     * its native epoch for the new lock; the real table supplies a new slot. */
    fixture_cpu = 0;
    node = 66666;
    slot->word.value = kd_mutex_policy_word(KD_MUTEX_POLICY_NATIVE, node, slot->word.value);
    slot->deadline = jiffies + msecs_to_jiffies(128);
    shadow = &other;
    clear_traffic();
    CHECK(!acquire(&other_original));
    CHECK(source_queries == 1 && shadow_queries == 1 && refs == 1 && queued == 1);
    CHECK(numa_queries == 1 && pins == 2);
    CHECK(kd_mutex_policy_cache[0].address == (unsigned long)&other_original);
    CHECK(kd_mutex_policy_cache[0].shadow == &other);
    CHECK(kd_mutex_policy_cache[1].address == (unsigned long)&original);

    /* Ordinary cooling wins before the cache and cannot alter queued work. */
    admitted = false;
    clear_traffic();
    CHECK(acquire(&other_original) == (unsigned long)current);
    CHECK(!numa_queries && pins == 1 && !source_queries && !shadow_queries && !refs && !queued);
    CHECK(!memcmp(&lock, &saved, sizeof(lock)));
    admitted = true;
    mutex_native_epoch_ms = 0;
    clear_traffic();
    CHECK(!acquire(&other_original));
    CHECK(!numa_queries && pins == 1 && source_queries == 1 && shadow_queries == 1 && refs == 1);
}

static void cross_node_epochs(bool cached)
{
    struct mutex original;
    struct kd_mutex lock = {.waiter_slot = 6, .tail = 37, .physical_owner = 81,
                            .locked = 3, .waiter_count = 13,
                            .origin_mutex_addr = (unsigned long)&original};
    struct kd_mutex saved = lock;
    struct kd_mutex_policy_slot *slot = &kd_mutex_policy_slots[6];
    unsigned long deadline;
    reset();
    mutex_native_epoch_cross_node = true;
    mutex_native_epoch_cache = cached;
    shadow = &lock;
    CHECK(!acquire(&original));
    expect_mode(6, KD_MUTEX_POLICY_PROBE);
    deadline = slot->deadline;
    CHECK(refs == 1 && queued == 1 && !native_calls);
    CHECK(!memcmp(&lock, &saved, sizeof(lock)));

    /* A different origin cannot veto this explicit policy. It still waits
     * for the existing probe deadline instead of opening native early. */
    fixture_cpu = 1;
    node = INT_MAX;
    clear_traffic();
    CHECK(!acquire(&original));
    expect_mode(6, KD_MUTEX_POLICY_PROBE);
    CHECK(slot->deadline == deadline && refs == 1 && queued == 1);
    CHECK(!kd_mutex_policy_remote_vetoes[0] && !kd_mutex_policy_remote_vetoes[1]);
    jiffies = deadline;
    clear_traffic();
    CHECK(acquire(&original) == (unsigned long)current);
    expect_mode(6, KD_MUTEX_POLICY_NATIVE);
    CHECK(native_calls == 1 && !refs && !queued && numa_queries == 1);
    CHECK(pins == (cached ? 1 : 2));
    CHECK(!memcmp(&lock, &saved, sizeof(lock)));

    fixture_cpu = 0;
    node = 777777;
    deadline = slot->deadline;
    jiffies = deadline - 1;
    clear_traffic();
    CHECK(acquire(&original) == (unsigned long)current);
    CHECK(slot->deadline == deadline && native_calls == 1 && !refs && !queued);
    CHECK(!memcmp(&lock, &saved, sizeof(lock)));

    /* Cross-node mode cannot extend a native epoch past its deadline. The
     * next attempt delegates through the ordinary task/queue path, while
     * previously queued ownership and drain state remain unchanged. */
    fixture_cpu = 1;
    node = INT_MAX;
    jiffies = deadline;
    clear_traffic();
    CHECK(!acquire(&original));
    expect_mode(6, KD_MUTEX_POLICY_PROBE);
    CHECK(refs == 1 && queued == 1 && !native_calls && numa_queries == 1);
    CHECK(!memcmp(&lock, &saved, sizeof(lock)));
    fixture_cpu = 0;
    node = 0;
    jiffies = slot->deadline;
    clear_traffic();
    CHECK(acquire(&original) == (unsigned long)current);
    expect_mode(6, KD_MUTEX_POLICY_NATIVE);
    CHECK(!kd_mutex_policy_remote_vetoes[0] && !kd_mutex_policy_remote_vetoes[1]);

    admitted = false;
    clear_traffic();
    CHECK(acquire(&original) == (unsigned long)current);
    CHECK(!numa_queries && !refs && !queued && pins == 1);
    CHECK(!memcmp(&lock, &saved, sizeof(lock)));
}

int main(void)
{
    phases();
    clocks_and_races();
    routing_and_parameters();
    cached_routing();
    cross_node_epochs(false);
    cross_node_epochs(true);
    printf("mutex locality policy: phases, races, time wrap, queued/cached routing (%d Hz) passed\n", TEST_HZ);
    return 0;
}
