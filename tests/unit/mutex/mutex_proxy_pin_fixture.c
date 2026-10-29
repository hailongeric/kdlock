// SPDX-License-Identifier: GPL-2.0
/* Deterministic scheduler/peer hooks around production origin wait helpers. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef uint8_t u8;
/* Only fields touched by these helpers are modeled; this is not an ABI test. */
struct kd_mutex_node { int tail; u8 locked; };
struct kd_mutex { unsigned int gate; };
#define KD_MUTEX_TAIL_CPU_OFFSET 8
#define CHECK(value) do { if (!(value)) { \
 fprintf(stderr, "FAIL proxy pin line %d: %s\n", __LINE__, #value); exit(1); \
} } while (0)
#define BUG_ON(value) CHECK(!(value))
#define READ_ONCE(value) __atomic_load_n(&(value), __ATOMIC_RELAXED)
#define smp_load_acquire(word) __atomic_load_n((word), __ATOMIC_ACQUIRE)
static void observe_release(u8 *word, u8 value);
#define smp_store_release(word, value) do { \
 observe_release((word), (value)); __atomic_store_n((word), (value), __ATOMIC_RELEASE); \
} while (0)

enum route { PROXY, HANDOFF, EXECUTOR, PHYSICAL, CANCEL_RESELECT, CANCEL_COALESCE };
static enum route route;
static struct kd_mutex_node node;
static struct kd_mutex lock;
static int pins, pauses, schedules, ack_seen, acquired, cpu;
static unsigned int origin_acks, pin_calls, unpin_calls;
static void preempt_disable(void) { CHECK(pins == 0); pins++; pin_calls++; }
static void preempt_enable(void) { CHECK(pins == 1); pins--; unpin_calls++; }
static __attribute__((unused)) int raw_smp_processor_id(void) { return cpu; }
static bool need_resched(void) { return true; }
static void cond_resched(void)
{
 CHECK(!pins);
 schedules++;
 if (route == PHYSICAL) lock.gate = 0;
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

static void observe_release(u8 *word, u8 value)
{
 CHECK(word == &node.locked && pins == 1);
 if (value == KD_MUTEX_PROXY_PINNED) {
  CHECK(route == PROXY || route == CANCEL_RESELECT || route == CANCEL_COALESCE);
  CHECK(node.locked == KD_MUTEX_PROXY_REQUEST);
  origin_acks++;
 } else {
  CHECK(value == KD_MUTEX_PROXY_REQUEST && route == EXECUTOR);
  CHECK(node.locked == KD_MUTEX_WAIT);
 }
}

static void cpu_relax(void)
{
 CHECK(++pauses <= 10);
 if (route == PHYSICAL) {
  CHECK(!pins);
 } else if (route == EXECUTOR) {
  CHECK(pins == 1 && node.locked == KD_MUTEX_PROXY_REQUEST);
  /* Substitute the other CPU's pin and ACK. The executor keeps its own pin. */
  __atomic_store_n(&node.locked, KD_MUTEX_PROXY_PINNED, __ATOMIC_RELEASE);
  ack_seen++;
 } else if (node.locked == KD_MUTEX_WAIT) {
  CHECK(!pins);
  if (schedules) node.locked = route != HANDOFF ? KD_MUTEX_PROXY_REQUEST : 0;
 } else {
  CHECK((route == PROXY || route == CANCEL_RESELECT || route == CANCEL_COALESCE) &&
        node.locked == KD_MUTEX_PROXY_PINNED && pins == 1);
  CHECK(schedules > 0 && origin_acks == (unsigned int)ack_seen + 1);
  ack_seen++;
  /* Completion follows the executor's last origin access. Cancellation may
   * instead expose WAIT, or a new selection may overwrite WAIT before this
   * origin observes it. The latter requires a fresh ACK without repinning. */
  if (ack_seen == 1 && route == CANCEL_RESELECT)
   node.locked = KD_MUTEX_WAIT;
  else if (ack_seen == 1 && route == CANCEL_COALESCE) {
   node.locked = KD_MUTEX_WAIT;
   node.locked = KD_MUTEX_PROXY_REQUEST;
  } else node.locked = 0;
 }
}

static void reset(enum route selected)
{
 route = selected;
 pins = 1;
 pauses = schedules = ack_seen = acquired = 0;
 origin_acks = pin_calls = unpin_calls = 0;
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
 CHECK(origin_acks == 1 && pin_calls == 1 && unpin_calls == 1);
 reset(CANCEL_RESELECT);
 kd_mutex_wait_for_result(&node);
 CHECK(pins == 1 && schedules >= 2 && ack_seen == 2 && !node.locked);
 CHECK(origin_acks == 2 && pin_calls == 2 && unpin_calls == 2);
 reset(CANCEL_COALESCE);
 kd_mutex_wait_for_result(&node);
 CHECK(pins == 1 && schedules && ack_seen == 2 && !node.locked);
 CHECK(origin_acks == 2 && pin_calls == 1 && unpin_calls == 1);
 reset(HANDOFF);
 kd_mutex_wait_for_result(&node);
 CHECK(pins == 1 && schedules && !ack_seen && !origin_acks && !node.locked);
 CHECK(pin_calls == 1 && unpin_calls == 1);
 reset(EXECUTOR);
 CHECK(kd_mutex_proxy_request(&node));
 CHECK(node.locked == KD_MUTEX_PROXY_REQUEST && !ack_seen && !pauses);
 kd_mutex_proxy_wait_pinned(&node);
 CHECK(pins == 1 && ack_seen == 1 && node.locked == KD_MUTEX_PROXY_PINNED);
 reset(EXECUTOR);
 node.tail = (cpu + 1) << KD_MUTEX_TAIL_CPU_OFFSET;
 CHECK(!kd_mutex_proxy_request(&node));
 CHECK(node.locked == KD_MUTEX_WAIT && !pauses && !ack_seen && pins == 1);
 reset(PHYSICAL);
 kd_mutex_wait_and_lock_node(&lock, &node);
 CHECK(pins == 1 && schedules && acquired == 1 && lock.gate == 1);
 CHECK(pin_calls == 1 && unpin_calls == 1);
 puts("PASS production proxy pin: preemptible queue/head, origin ACK before access, cancellation/reselection including unobserved WAIT, balanced pins and same-CPU refusal");
 return 0;
}
