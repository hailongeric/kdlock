/* Deterministic scheduler and remote-origin hooks around production helpers. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef uint8_t u8;
/* Only the metadata used by the extracted helpers is modeled here. */
struct task_struct { int pid; };
struct kd_regs { unsigned long ip; };
struct kd_mutex_node {
 int tail;
 u8 locked;
 struct kd_regs regs;
 unsigned long gsbase;
 struct task_struct *task_struct_ptr;
};
struct kd_mutex { unsigned int gate; };
struct kd_exec_frame { unsigned int private_cookie; };
struct kd_exec_outer_unlock { unsigned int identity; };
struct kd_mutex_batch { struct kd_exec_outer_unlock outer; };
#ifndef __always_inline
#define __always_inline inline
#endif
#define KD_MUTEX_TAIL_CPU_OFFSET 8
#define CHECK(value) do { if (!(value)) { \
 fprintf(stderr, "FAIL proxy pin line %d: %s\n", __LINE__, #value); exit(1); \
} } while (0)
#define BUG_ON(value) CHECK(!(value))
#define READ_ONCE(value) __atomic_load_n(&(value), __ATOMIC_RELAXED)
#define smp_load_acquire(word) __atomic_load_n((word), __ATOMIC_ACQUIRE)
#define smp_store_release(word, value) __atomic_store_n((word), (value), __ATOMIC_RELEASE)

enum route { PROXY, HANDOFF, EXECUTOR, PHYSICAL, CANCEL_RESELECT,
             PREPARE, PREPARE_FAIL };
static enum route route;
static struct kd_mutex_node node;
static struct kd_mutex lock;
static struct kd_mutex_batch batch;
static struct kd_exec_frame private_frame, untouched_frame;
static struct task_struct waiter = { 17 };
static int pins, pauses, schedules, ack_seen, acquired, cpu;
static unsigned int preparations, origin_uses, cleanups;
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
static struct kd_exec_frame *kd_exec_frame_push_mutex_batch(
 struct kd_regs *regs, unsigned long entry_ip, unsigned long gsbase,
 struct task_struct *task, struct kd_mutex *value,
 struct kd_exec_outer_unlock *hook);
#include "proxy_production.h"

static struct kd_exec_frame *kd_exec_frame_push_mutex_batch(
 struct kd_regs *regs, unsigned long entry_ip, unsigned long gsbase,
 struct task_struct *task, struct kd_mutex *value,
 struct kd_exec_outer_unlock *hook)
{
 CHECK(route == PREPARE || route == PREPARE_FAIL);
 CHECK(regs == &node.regs && entry_ip == 0x1234 && gsbase == 0x5678);
 CHECK(task == &waiter && value == &lock && hook == &batch.outer);
 /* The REQUEST must already be published, but its origin ACK must still
  * be pending when executor-private preparation starts. */
 CHECK(node.locked == KD_MUTEX_PROXY_REQUEST && !ack_seen && pins == 1);
 CHECK(!preparations && !origin_uses && !cleanups);
 preparations++;
 if (route == PREPARE_FAIL)
  return NULL;
 private_frame.private_cookie = 29;
 return &private_frame;
}

static void use_origin(struct kd_exec_frame *frame)
{
 CHECK(node.locked == KD_MUTEX_PROXY_PINNED && ack_seen == 1);
 CHECK(preparations == 1 && !origin_uses && !cleanups);
 CHECK(frame == &private_frame && frame->private_cookie == 29);
 origin_uses++;
}

static void cancel_unstarted(struct kd_exec_frame *frame)
{
 /* NULL construction does not authorize withdrawal of an unacknowledged
  * request. The actual caller's frame cleanup is tested by outer-progress. */
 CHECK(!frame && node.locked == KD_MUTEX_PROXY_PINNED && ack_seen == 1);
 CHECK(preparations == 1 && !origin_uses && !cleanups);
 cleanups++;
 smp_store_release(&node.locked, KD_MUTEX_WAIT);
}

static void cpu_relax(void)
{
 CHECK(++pauses <= 8);
 if (route == PHYSICAL) {
  CHECK(!pins);
 } else if (route == PREPARE || route == PREPARE_FAIL) {
  CHECK(pins == 1 && node.locked == KD_MUTEX_PROXY_REQUEST);
  CHECK(preparations == 1 && !ack_seen && !origin_uses && !cleanups);
  /* Keep the ACK pending for two polls. No cleanup or origin access may
   * occur in that interval, including when preparation returned NULL. */
  if (pauses == 2) {
   node.locked = KD_MUTEX_PROXY_PINNED;
   ack_seen++;
  }
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
 preparations = origin_uses = cleanups = 0;
 private_frame.private_cookie = untouched_frame.private_cookie = 0;
 cpu = 1;
 node.tail = (2 + 1) << KD_MUTEX_TAIL_CPU_OFFSET;
 node.locked = KD_MUTEX_WAIT;
 node.regs.ip = 0x1234;
 node.gsbase = 0x5678;
 node.task_struct_ptr = &waiter;
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
 reset(PREPARE);
 struct kd_exec_frame *frame = NULL;
 CHECK(kd_mutex_proxy_prepare_batch(&lock, &node, &batch, &frame));
 CHECK(preparations == 1 && pauses == 2 && ack_seen == 1 && pins == 1);
 use_origin(frame);
 CHECK(origin_uses == 1 && !cleanups);
 reset(PREPARE_FAIL);
 frame = &untouched_frame;
 CHECK(kd_mutex_proxy_prepare_batch(&lock, &node, &batch, &frame));
 CHECK(!frame && preparations == 1 && pauses == 2 && ack_seen == 1 && pins == 1);
 cancel_unstarted(frame);
 CHECK(cleanups == 1 && !origin_uses && node.locked == KD_MUTEX_WAIT);
 reset(PREPARE);
 node.tail = (cpu + 1) << KD_MUTEX_TAIL_CPU_OFFSET;
 frame = &untouched_frame;
 CHECK(!kd_mutex_proxy_prepare_batch(&lock, &node, &batch, &frame));
 CHECK(frame == &untouched_frame && !preparations && !origin_uses && !cleanups);
 CHECK(node.locked == KD_MUTEX_WAIT && !pauses && !ack_seen && pins == 1);
 puts("PASS production proxy pin: queued scheduling, cancellation/reselection, same-CPU refusal and current-request preparation before mandatory ACK");
 return 0;
}
