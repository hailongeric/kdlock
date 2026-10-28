/* Deterministic scheduler and remote-origin hooks around production helpers. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef uint8_t u8;
struct kd_mutex_node { int tail; u8 locked; };
struct kd_mutex { unsigned int gate; };
#define KD_MUTEX_TAIL_CPU_OFFSET 8
#define CHECK(value) do { if (!(value)) { \
 fprintf(stderr, "FAIL proxy pin line %d: %s\n", __LINE__, #value); exit(1); \
} } while (0)
#define BUG_ON(value) CHECK(!(value))
#define READ_ONCE(value) __atomic_load_n(&(value), __ATOMIC_RELAXED)
#define smp_load_acquire(word) __atomic_load_n((word), __ATOMIC_ACQUIRE)
#define smp_store_release(word, value) __atomic_store_n((word), (value), __ATOMIC_RELEASE)

enum route { PROXY, HANDOFF, EXECUTOR, PHYSICAL, CANCEL_RESELECT };
static enum route route;
static struct kd_mutex_node node;
static struct kd_mutex lock;
static int pins, pauses, schedules, ack_seen, acquired, cpu;
static void preempt_disable(void) { CHECK(pins == 0); pins++; }
static void preempt_enable(void) { CHECK(pins == 1); pins--; }
static __attribute__((unused)) int raw_smp_processor_id(void) { return cpu; }
static bool need_resched(void) { return true; }
static void cond_resched(void)
{
 CHECK(!pins);
 schedules++;
 if (route == PHYSICAL)
  lock.gate = 0;
}
static unsigned int kd_mutex_gate_read(struct kd_mutex *value)
{
 CHECK(value == &lock);
 return value->gate;
}
static bool kd_mutex_gate_trylock(struct kd_mutex *value)
{
 CHECK(value == &lock && !pins && !value->gate);
 value->gate = 2;
 return true;
}
static void kd_mutex_claim_origin_node(struct kd_mutex *value,
                                       struct kd_mutex_node *request)
{
 CHECK(value == &lock && request == &node && !pins && value->gate == 2);
 acquired++;
 value->gate = 1;
}
static void cpu_relax(void);
#include "proxy_production.h"

static void cpu_relax(void)
{
 CHECK(++pauses <= 8);
 if (route == PHYSICAL) {
  CHECK(!pins);
 } else if (route == EXECUTOR) {
  CHECK(pins == 1 && node.locked == KD_MUTEX_PROXY_REQUEST);
  /* The other CPU's origin acknowledges only after its own pin. */
  node.locked = KD_MUTEX_PROXY_PINNED;
  ack_seen++;
 } else if (node.locked == KD_MUTEX_WAIT) {
  CHECK(!pins);
  if (schedules)
   node.locked = route != HANDOFF ? KD_MUTEX_PROXY_REQUEST : 0;
 } else {
	 CHECK((route == PROXY || route == CANCEL_RESELECT) &&
	       node.locked == KD_MUTEX_PROXY_PINNED && pins == 1);
  CHECK(schedules > 0);
  ack_seen++;
  /* Executor's release completion follows its last origin-CPU access. */
  node.locked = route == CANCEL_RESELECT && ack_seen == 1 ? KD_MUTEX_WAIT : 0;
 }
}
static void reset(enum route selected)
{
 route = selected;
 pins = 1;
 pauses = schedules = ack_seen = acquired = 0;
 cpu = 1;
 node.tail = (2 + 1) << KD_MUTEX_TAIL_CPU_OFFSET;
 node.locked = KD_MUTEX_WAIT;
 lock.gate = 1;
}
int main(void)
{
 reset(PROXY);
 kd_mutex_wait_for_result(&node);
 CHECK(pins == 1 && schedules && ack_seen == 1 && !node.locked);
 reset(CANCEL_RESELECT);
 kd_mutex_wait_for_result(&node);
 CHECK(pins == 1 && schedules >= 2 && ack_seen == 2 && !node.locked);
 reset(HANDOFF);
 kd_mutex_wait_for_result(&node);
 CHECK(pins == 1 && schedules && !ack_seen && !node.locked);
 reset(EXECUTOR);
 CHECK(kd_mutex_proxy_pin(&node));
 CHECK(pins == 1 && ack_seen == 1 && node.locked == KD_MUTEX_PROXY_PINNED);
 reset(EXECUTOR);
 node.tail = (cpu + 1) << KD_MUTEX_TAIL_CPU_OFFSET;
 CHECK(!kd_mutex_proxy_pin(&node));
 CHECK(node.locked == KD_MUTEX_WAIT && !pauses && !ack_seen && pins == 1);
 reset(PHYSICAL);
 kd_mutex_wait_and_lock_node(&lock, &node);
 CHECK(pins == 1 && schedules && acquired == 1 && lock.gate == 1);
 puts("PASS production proxy pin: preemptible queue/head, selected origin ACK, completion and same-CPU refusal");
 return 0;
}
