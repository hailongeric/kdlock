/* SPDX-License-Identifier: GPL-2.0 */
/* Real waiter/gate/origin accounting with explicit deterministic event traces.
 * No reference waiter algorithm, kernel scheduler or hardware timer is used. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>

typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef struct { int counter; } atomic_t;
struct kd_mutex { atomic_t delegation_state; };
struct kd_mutex_node { u8 locked; struct kd_mutex *lock, *counted_lock; u64 count_seq; };
#define U64_MAX UINT64_MAX
#define __percpu
#define unlikely(value) (value)
#define smp_wmb() __atomic_thread_fence(__ATOMIC_RELEASE)
#define READ_ONCE(value) __atomic_load_n(&(value), __ATOMIC_RELAXED)
#define WRITE_ONCE(target, value) __atomic_store_n(&(target), (value), __ATOMIC_RELAXED)
#define atomic_read(p) __atomic_load_n(&(p)->counter, __ATOMIC_RELAXED)
#define atomic_read_acquire(p) __atomic_load_n(&(p)->counter, __ATOMIC_ACQUIRE)

/* Trace alphabet: L=notification load, P=PAUSE, E=expiry assignment,
 * N=need_resched, A=withdrawal gate CAS, C=node CAS, R=reservation release,
 * F=actual pinned merge, U=unpin, S=schedule, D=restore original pin. */
enum scenario {
    DONE_ENTRY, WAIT_ENTRY, EARLY_ZERO, EARLY_CANCEL,
    READY_ZERO_LAST, READY_WAIT_LAST, READY_CLAIMED_LAST,
    CLAIMED_ZERO_LAST, CLAIMED_READY_LAST, CLAIMED_ZERO_LATE, NO_RESCHED, GATE_REFUSED,
    GATE_CAS_LOSS, GATE_RETRY_SUCCESS, CAS_WAIT_ZERO, CAS_ZERO,
    WITHDRAW_SUCCESS, WAKE_AT_UNPIN, FORCED_WAKE_AT_UNPIN,
    INVALID_ENTRY, INVALID_INITIAL, INVALID_POST, INVALID_WITHDRAWN, INVALID_CAS,
};
static enum scenario scenario;
static struct kd_mutex lock;
static struct kd_mutex_node node;
static unsigned int pins, migration, loads, pinned_pauses, unpinned_pauses;
static unsigned int needs, gate_attempts, node_attempts, releases, expiry_events;
static unsigned int finishes, unpins, repins, schedules, cases, checks;
static unsigned int invalid_byte;
static bool expect_bug, caught_bug, peer;
static jmp_buf bug_target;
static char trace[256];
static size_t trace_length;

static void failure(int line, const char *condition)
{
    fprintf(stderr, "FAIL wait budget B=%u scenario=%u line=%d: %s trace=%s state=%u gate=%u\n",
        (unsigned int)KDLOCK_MUTEX_SPIN_BUDGET, (unsigned int)scenario, line,
        condition, trace, (unsigned int)node.locked, (unsigned int)atomic_read(&lock.delegation_state));
    exit(1);
}
#define CHECK(condition) do { checks++; if (!(condition)) failure(__LINE__, #condition); } while (0)
static void bug(int line, const char *condition)
{
    if (expect_bug) { caught_bug = true; longjmp(bug_target, 1); }
    failure(line, condition);
}
#define BUG_ON(condition) do { if (condition) bug(__LINE__, #condition); } while (0)
static void event(char value)
{
    CHECK(trace_length + 1 < sizeof(trace));
    trace[trace_length++] = value; trace[trace_length] = 0;
}
static void observe_expiry(void)
{
    CHECK(pins == 1 && migration == 1 && !expiry_events);
    CHECK(pinned_pauses == KDLOCK_MUTEX_SPIN_BUDGET);
    expiry_events++; event('E');
}
static void observe_merge(void);
#define this_cpu_inc(value) do { observe_merge(); (value)++; } while (0)
#define this_cpu_add(target, value) do { CHECK(pins == 1); (target) += (value); } while (0)
static __attribute__((noinline)) u8 node_acquire(const u8 *word);
static int gate_cas(atomic_t *word, int before, int after);
static int gate_clear(unsigned int mask, atomic_t *word);
static u8 node_cas(u8 *word, u8 before, u8 after);
static void cpu_relax(void);
static bool need_resched(void);
static void preempt_enable(void);
static void preempt_disable(void);
static void cond_resched(void);
#define smp_load_acquire(word) node_acquire(word)
#define atomic_cmpxchg(word, before, after) gate_cas((word), (before), (after))
#define atomic_fetch_andnot_release(mask, word) gate_clear((mask), (word))
#define cmpxchg(word, before, after) node_cas((word), (before), (after))
#include "wait_budget_production.h"
static struct kd_mutex_pin_cpu storage;

static void observe_merge(void)
{
    CHECK(pins == 1 && migration == 1 && !finishes);
    CHECK(!(atomic_read(&lock.delegation_state) & KD_MUTEX_GATE_WITHDRAW));
    finishes++; event('F');
}

/* Keep the real notification acquire behind the same noinline mock boundary
 * used by the existing production-helper fixture; no production qualifier is
 * weakened. Peers modify only their simulated state at explicit events. */
static __attribute__((noinline)) u8 node_acquire(const u8 *word)
{
    CHECK(word == &node.locked && migration == 1);
    CHECK(++loads <= KDLOCK_MUTEX_SPIN_BUDGET + 12);
    event('L');
    return __atomic_load_n(word, __ATOMIC_ACQUIRE);
}
static void peer_phase(u32 phase)
{
    peer = true; kd_mutex_gate_set(&lock, phase); peer = false;
}
static int gate_cas(atomic_t *word, int before, int after)
{
    CHECK(word == &lock.delegation_state && pins == 1 && migration == 1);
    if (!peer) {
        CHECK(((u32)after & KD_MUTEX_GATE_WITHDRAW) && !((u32)before & KD_MUTEX_GATE_WITHDRAW));
        gate_attempts++; event('A');
        if (scenario == GATE_CAS_LOSS && gate_attempts == 1) {
            peer = true; CHECK(kd_mutex_gate_try_combine(&lock)); peer = false;
            node.locked = KD_MUTEX_PROXY_CLAIMED;
        }
        if (scenario == GATE_RETRY_SUCCESS && gate_attempts == 1)
            peer_phase(KD_MUTEX_GATE_RELEASING);
    }
    int seen = atomic_read(word);
    if (seen == before) __atomic_store_n(&word->counter, after, __ATOMIC_SEQ_CST);
    return seen;
}
static u8 node_cas(u8 *word, u8 before, u8 after)
{
    CHECK(word == &node.locked && before == KD_MUTEX_PROXY_READY && after == KD_MUTEX_WAIT);
    CHECK(pins == 1 && migration == 1 && expiry_events == 1 && needs);
    CHECK(atomic_read(&lock.delegation_state) & KD_MUTEX_GATE_WITHDRAW);
    node_attempts++; event('C');
    if (scenario == CAS_WAIT_ZERO) node.locked = KD_MUTEX_WAIT;
    if (scenario == CAS_ZERO) node.locked = 0;
    if (scenario == INVALID_CAS) node.locked = (u8)invalid_byte;
    u8 seen = __atomic_load_n(word, __ATOMIC_RELAXED);
    if (seen == before) __atomic_store_n(word, after, __ATOMIC_SEQ_CST);
    return seen;
}
static int gate_clear(unsigned int mask, atomic_t *word)
{
    CHECK(word == &lock.delegation_state && pins == 1 && migration == 1);
    CHECK(mask == KD_MUTEX_GATE_WITHDRAW && (atomic_read(word) & mask));
    releases++; event('R');
    int seen = __atomic_fetch_and(&word->counter, ~mask, __ATOMIC_RELEASE);
    if (scenario == CAS_WAIT_ZERO) node.locked = 0;
    return seen;
}
static bool need_resched(void)
{
    CHECK(migration == 1);
    if (pins) CHECK(pinned_pauses >= KDLOCK_MUTEX_SPIN_BUDGET && expiry_events == 1);
    needs++; event('N');
    return scenario != NO_RESCHED;
}
static void cpu_relax(void)
{
    CHECK(migration == 1); event('P');
    if (!pins) {
        CHECK(node.locked == KD_MUTEX_WAIT); unpinned_pauses++; return;
    }
    CHECK(++pinned_pauses <= KDLOCK_MUTEX_SPIN_BUDGET + 4);
    if (scenario == EARLY_ZERO && pinned_pauses == 1) node.locked = 0;
    if (scenario == EARLY_CANCEL && pinned_pauses == 1) node.locked = KD_MUTEX_WAIT;
    if (scenario == INVALID_INITIAL && pinned_pauses == 1) node.locked = (u8)invalid_byte;
    if (pinned_pauses == KDLOCK_MUTEX_SPIN_BUDGET) {
        if (scenario == READY_ZERO_LAST || scenario == CLAIMED_ZERO_LAST) node.locked = 0;
        if (scenario == READY_WAIT_LAST) node.locked = KD_MUTEX_WAIT;
        if (scenario == READY_CLAIMED_LAST) node.locked = KD_MUTEX_PROXY_CLAIMED;
        if (scenario == CLAIMED_READY_LAST) node.locked = KD_MUTEX_PROXY_READY;
        if (scenario == INVALID_POST) node.locked = (u8)invalid_byte;
    }
    if (pinned_pauses == KDLOCK_MUTEX_SPIN_BUDGET + 1 &&
        (scenario == READY_CLAIMED_LAST || scenario == CLAIMED_ZERO_LATE ||
         scenario == GATE_CAS_LOSS || scenario == GATE_REFUSED)) {
        node.locked = 0;
        if (scenario == GATE_CAS_LOSS) peer_phase(KD_MUTEX_GATE_HELD);
    }
    if (scenario == NO_RESCHED && pinned_pauses == KDLOCK_MUTEX_SPIN_BUDGET + 2) node.locked = 0;
}
static void preempt_enable(void)
{
    CHECK(pins == 1 && migration == 1 && finishes == 1);
    CHECK(!(atomic_read(&lock.delegation_state) & KD_MUTEX_GATE_WITHDRAW));
    CHECK(node.locked == KD_MUTEX_WAIT || !node.locked);
    pins--; unpins++; event('U');
    if (scenario == WAKE_AT_UNPIN || scenario == FORCED_WAKE_AT_UNPIN) node.locked = 0;
    if (scenario == INVALID_WITHDRAWN) node.locked = (u8)invalid_byte;
}
static void preempt_disable(void)
{
    CHECK(!pins && migration == 1 && !node.locked);
    pins++; repins++; event('D');
}
static void cond_resched(void)
{
    CHECK(!pins && migration == 1 && node.locked == KD_MUTEX_WAIT);
    schedules++; event('S'); node.locked = 0;
}
static void reset(enum scenario value, u8 initial)
{
    scenario = value; cases++;
    memset(&storage, 0, sizeof(storage)); kd_mutex_pin_cpus = &storage;
    memset(&node, 0, sizeof(node)); memset(&lock, 0, sizeof(lock));
    node.lock = &lock; node.locked = initial;
    lock.delegation_state.counter = value == GATE_REFUSED ? KD_MUTEX_GATE_COMBINER : KD_MUTEX_GATE_HELD;
    pins = migration = 1;
    loads = pinned_pauses = unpinned_pauses = needs = gate_attempts = node_attempts = releases = 0;
    expiry_events = finishes = unpins = repins = schedules = 0;
    trace_length = 0; trace[0] = 0; expect_bug = caught_bug = peer = false;
}
static void expected_trace(unsigned int repeats, const char *suffix)
{
    char expected[256] = {0}; size_t at = 0;
    for (unsigned int i = 0; i < repeats; i++) { expected[at++] = 'L'; expected[at++] = 'P'; }
    CHECK(at + strlen(suffix) < sizeof(expected)); strcpy(expected + at, suffix);
    CHECK(!strcmp(trace, expected));
}
struct expectation {
    enum scenario scenario;
    u8 initial;
    unsigned int prefix, pinned, unpinned, loads, needs, gate, cas, release;
    bool expired, retained, withdrawn, cancelled;
    const char *suffix;
};
static void run_case(const struct expectation *e)
{
    reset(e->scenario, e->initial);
    kd_mutex_wait_for_result(&node);
    expected_trace(e->prefix, e->suffix);
    CHECK(pinned_pauses == e->pinned && unpinned_pauses == e->unpinned);
    CHECK(loads == e->loads && needs == e->needs && gate_attempts == e->gate);
    CHECK(node_attempts == e->cas && releases == e->release && expiry_events == e->expired);
    CHECK(pins == 1 && migration == 1 && !node.locked && finishes == 1);
    CHECK(unpins == !e->retained && repins == unpins && schedules == e->unpinned);
    CHECK(!(atomic_read(&lock.delegation_state) & KD_MUTEX_GATE_WITHDRAW));
    CHECK(storage.totals.wait_episodes == 1);
    CHECK(storage.totals.initial_pin_retained == e->retained && storage.totals.initial_pin_dropped == !e->retained);
    CHECK(storage.totals.initial_budget_completed == (e->retained && !e->expired));
    CHECK(storage.totals.budget_expired_episodes == e->expired);
    CHECK(storage.totals.expiry_checks == e->needs - e->unpinned);
    CHECK(storage.totals.withdrawal_reservations == e->release);
    CHECK(storage.totals.withdrawals == e->withdrawn && storage.totals.forced_cancellations == e->cancelled);
}
static void invalid_case(enum scenario where, unsigned int value)
{
    unsigned int b = KDLOCK_MUTEX_SPIN_BUDGET;
    u8 initial = where == INVALID_ENTRY ? (u8)value :
        where == INVALID_WITHDRAWN ? KD_MUTEX_WAIT :
        where == INVALID_POST ? KD_MUTEX_PROXY_CLAIMED : KD_MUTEX_PROXY_READY;
    reset(where, initial); invalid_byte = value; expect_bug = true;
    if (!setjmp(bug_target)) { kd_mutex_wait_for_result(&node); CHECK(false); }
    expect_bug = false; CHECK(caught_bug && !schedules && !repins);
    CHECK(!(atomic_read(&lock.delegation_state) & KD_MUTEX_GATE_WITHDRAW));
    if (where == INVALID_ENTRY) {
        expected_trace(0, "L"); CHECK(!pinned_pauses && !expiry_events && !finishes);
    } else if (where == INVALID_INITIAL) {
        expected_trace(1, "L"); CHECK(pinned_pauses == 1 && !expiry_events && !finishes);
    } else if (where == INVALID_POST) {
        expected_trace(b, "EL"); CHECK(pinned_pauses == b && expiry_events == 1 && !finishes);
    } else if (where == INVALID_CAS) {
        expected_trace(b, "ENACR"); CHECK(releases == 1 && !finishes && pins == 1);
    } else {
        expected_trace(0, "LFUL"); CHECK(!pins && finishes == 1 && storage.totals.forced_cancellations == 1);
    }
}
int main(void)
{
    const unsigned int b = KDLOCK_MUTEX_SPIN_BUDGET;
    /* Each suffix is an explicit peer-event oracle, not a second wait loop. */
    const struct expectation cases_to_run[] = {
        {DONE_ENTRY, 0, 0, 0,0,1,0,0,0,0, false,true,false,false, "LF"},
        {WAIT_ENTRY, KD_MUTEX_WAIT, 0, 0,1,3,1,0,0,0, false,false,false,true, "LFULPNSLD"},
        {READY_ZERO_LAST, KD_MUTEX_PROXY_READY, b, b,0,b+1,1,1,1,1, true,true,false,false, "ENACRLF"},
        {READY_WAIT_LAST, KD_MUTEX_PROXY_READY, b, b,1,b+3,2,1,1,1, true,false,false,true, "ENACRLFULPNSLD"},
        {READY_CLAIMED_LAST, KD_MUTEX_PROXY_READY, b, b+1,0,b+2,1,1,1,1, true,true,false,false, "ENACRLPLF"},
        {CLAIMED_ZERO_LAST, KD_MUTEX_PROXY_CLAIMED, b, b,0,b+1,0,0,0,0, true,true,false,false, "ELF"},
        {CLAIMED_READY_LAST, KD_MUTEX_PROXY_CLAIMED, b, b+1,1,b+3,2,1,1,1, true,false,true,false, "ELPNACRFULPNSLD"},
        {CLAIMED_ZERO_LATE, KD_MUTEX_PROXY_CLAIMED, b, b+1,0,b+2,0,0,0,0, true,true,false,false, "ELPLF"},
        {NO_RESCHED, KD_MUTEX_PROXY_READY, b, b+2,0,b+3,3,0,0,0, true,true,false,false, "ENLPNLPNLF"},
        {GATE_REFUSED, KD_MUTEX_PROXY_READY, b, b+1,0,b+2,2,0,0,0, true,true,false,false, "ENLPNLF"},
        {GATE_CAS_LOSS, KD_MUTEX_PROXY_READY, b, b+1,0,b+2,1,1,0,0, true,true,false,false, "ENALPLF"},
        {GATE_RETRY_SUCCESS, KD_MUTEX_PROXY_READY, b, b+1,1,b+3,3,2,1,1, true,false,true,false, "ENALPNACRFULPNSLD"},
        {CAS_WAIT_ZERO, KD_MUTEX_PROXY_READY, b, b,0,b+1,1,1,1,1, true,true,false,false, "ENACRLF"},
        {CAS_ZERO, KD_MUTEX_PROXY_READY, b, b,0,b+1,1,1,1,1, true,true,false,false, "ENACRLF"},
        {WITHDRAW_SUCCESS, KD_MUTEX_PROXY_READY, b, b,1,b+2,2,1,1,1, true,false,true,false, "ENACRFULPNSLD"},
        {WAKE_AT_UNPIN, KD_MUTEX_PROXY_READY, b, b,0,b+1,1,1,1,1, true,false,true,false, "ENACRFULD"},
        {FORCED_WAKE_AT_UNPIN, KD_MUTEX_WAIT, 0, 0,0,2,0,0,0,0, false,false,false,true, "LFULD"},
    };
    for (unsigned int i = 0; i < sizeof(cases_to_run)/sizeof(cases_to_run[0]); i++) run_case(&cases_to_run[i]);
    if (b > 1) {
        const struct expectation early[] = {
            {EARLY_ZERO, KD_MUTEX_PROXY_READY, 1, 1,0,2,0,0,0,0, false,true,false,false, "LF"},
            {EARLY_CANCEL, KD_MUTEX_PROXY_READY, 1, 1,1,4,1,0,0,0, false,false,false,true, "LFULPNSLD"},
        };
        for (unsigned int i = 0; i < 2; i++) run_case(&early[i]);
    }
    const unsigned int invalid[] = {KD_MUTEX_QUEUE_INIT, 5, 255};
    for (unsigned int i = 0; i < 3; i++) {
        invalid_case(INVALID_ENTRY, invalid[i]);
        if (b > 1) invalid_case(INVALID_INITIAL, invalid[i]);
        invalid_case(INVALID_POST, invalid[i]);
        invalid_case(INVALID_WITHDRAWN, invalid[i]);
        invalid_case(INVALID_CAS, invalid[i]);
    }
    printf("PASS actual waiter budget=%u: %u cases, %u event/state/count checks\n", b, cases, checks);
    return 0;
}
