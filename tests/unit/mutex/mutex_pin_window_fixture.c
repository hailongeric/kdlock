// SPDX-License-Identifier: GPL-2.0
/* Production pin-window helpers; atomic observers substitute origin execution.
 * Actual gate epochs exclude withdrawal while plain stores claim pinned origins. No kernel, JIT or scheduler runs. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef unsigned long atomic_long_t;
typedef struct { int counter; } atomic_t;
typedef unsigned int raw_spinlock_t;
struct optimistic_spin_queue { atomic_t tail; };
struct task_struct { unsigned int pid; };
struct kd_exec_frame;
#include "kd_regs.h"
#define KD_MUTEX_DIAG_MEMBER
#define KD_MUTEX_TAIL_CPU_OFFSET 4
#define KDLOCK_MUTEX_NUMA_BOUNDARY 256
static const int kd_mutex_batch_size = 1024;
#include "pin_window_types.h"

#define NODE_COUNT 40
static struct kd_mutex lock, other_lock;
static struct kd_mutex_node nodes[NODE_COUNT];
static struct kd_mutex_batch batch;
static unsigned int checks, requests, cancellations, completions, cas_attempts;
static unsigned int requested[NODE_COUNT];
static bool poisoned[NODE_COUNT];
static int executor_cpu;
static struct task_struct owner={1};
static struct task_struct *current=&owner;
static unsigned int start_head;

#define CHECK(value) do { checks++; if (!(value)) { \
 fprintf(stderr, "FAIL pin window line %d: %s\n", __LINE__, #value); exit(1); \
} } while (0)
#define BUG_ON(value) do { if (value) { \
 fprintf(stderr, "BUG pin window: %s\n", #value); exit(86); \
} } while (0)

static int node_at(const void *address)
{
 uintptr_t value = (uintptr_t)address;

 for (unsigned int i = 0; i < NODE_COUNT; i++)
  if (value >= (uintptr_t)&nodes[i] && value < (uintptr_t)(&nodes[i] + 1))
   return (int)i;
 return -1;
}

static void observe_read(const void *address)
{
 int index = node_at(address);

 if (index < 0) return;
 CHECK(!poisoned[index]);

}

static void descriptor_absent(struct kd_mutex_node *node)
{
 CHECK(batch.nr_pins <= KD_MUTEX_PIN_WINDOW);
 /* Also inspect inactive slots: they must not retain a consumed identity. */
 for (unsigned int i = 0; i < KD_MUTEX_PIN_WINDOW; i++)
  CHECK(batch.pins[i].node != node);
}

static void observe_store(void *address, unsigned long value)
{
 int index = node_at(address);

 CHECK(index >= 0 && address == &nodes[index].locked && !poisoned[index]);
 if(value==KD_MUTEX_PROXY_CLAIMED) {
  CHECK(batch.proxy_epoch && lock.delegation_state.counter==KD_MUTEX_GATE_COMBINER);
  CHECK(nodes[index].locked==KD_MUTEX_PROXY_READY && !requested[index]);
  requested[index]=1;requests++;return;
 }
 CHECK(value == KD_MUTEX_WAIT || value == 0);
 CHECK(requested[index] && nodes[index].locked == KD_MUTEX_PROXY_CLAIMED);
 descriptor_absent(&nodes[index]);
 requested[index] = 0;
 if (value == KD_MUTEX_WAIT) cancellations++;
 else completions++;
}

#define READ_ONCE(value) (observe_read(&(value)), __atomic_load_n(&(value), __ATOMIC_RELAXED))
#define smp_load_acquire(word) (observe_read(word), __atomic_load_n((word), __ATOMIC_ACQUIRE))
#define smp_store_release(word, value) do { \
 observe_store((word), (value)); __atomic_store_n((word), (value), __ATOMIC_RELEASE); \
} while (0)
/* A per-node RMW in the claim path violates the gate-amortized contract. */
#define cmpxchg(word,before,after) ({ (void)(word);(void)(before);(void)(after);cas_attempts++;CHECK(false);(u8)0; })
#define WRITE_ONCE(value,after) ((value)=(after))
#include "mutex_state_mock.h"
static void kd_mutex_set_locked(struct kd_mutex *value)
{ kd_mutex_gate_set(value,KD_MUTEX_GATE_HELD); }
static bool kd_mutex_delegation_owned(struct kd_mutex *value,struct task_struct *task)
{ return value==&lock && value->owner==(unsigned long)task; }
static int raw_smp_processor_id(void) { return executor_cpu; }
static void __attribute__((unused)) cpu_relax(void) { CHECK(false); }
#include "pin_window_production.h"

static void setup(void)
{
 memset(&batch, 0, sizeof(batch));
 batch.pin_head = start_head;
 memset(nodes, 0, sizeof(nodes));
 memset(requested, 0, sizeof(requested));
 memset(poisoned, 0, sizeof(poisoned));
 requests = cancellations = completions = cas_attempts = 0;
 executor_cpu = 0;
 batch.lock = &lock;lock.owner=(unsigned long)current;lock.delegation_state.counter=KD_MUTEX_GATE_HELD;
 batch.numa_node = 0;
 batch.pin_budget = 20;
 for (unsigned int i = 0; i < NODE_COUNT; i++) {
  nodes[i].next = i + 1 < NODE_COUNT ? &nodes[i + 1] : NULL;
  nodes[i].tail = (i + 2) << KD_MUTEX_TAIL_CPU_OFFSET;
  nodes[i].locked = KD_MUTEX_PROXY_READY;
  nodes[i].counted_lock = nodes[i].lock = &lock;
  nodes[i].count_seq = 2 * i + 2;
  nodes[i].entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
  nodes[i].packet_state = KD_PACKET_MINIMAL;
  nodes[i].regs.ip = 0xcafe;
 }
 CHECK(kd_mutex_batch_epoch_begin(&batch));
}

static void consume(unsigned int index)
{
 kd_mutex_proxy_assert_claimed(&nodes[index]);
 CHECK(requested[index]);
 kd_mutex_batch_pin_complete(&batch, &nodes[index]);
 descriptor_absent(&nodes[index]);
 smp_store_release(&nodes[index].locked, 0);
 /* Result publication permits immediate slot reuse. Any remaining helper
  * read through a stale descriptor now fails the access observer. */
 poisoned[index] = true;
 nodes[index].counted_lock = NULL;
 nodes[index].count_seq += 2;
 nodes[index].next = (void *)(uintptr_t)1;
 nodes[index].regs.ip = 0xdead;
}

static void bounded_refill(void)
{
 setup();
 CHECK(KD_MUTEX_PIN_WINDOW == 8);
 CHECK(kd_mutex_batch_pin_select(&batch, &nodes[0], true));
 CHECK(batch.nr_pins == 8 && requests == 8 && cas_attempts == 0);
 kd_mutex_proxy_assert_claimed(&nodes[0]);
 CHECK(nodes[8].locked == KD_MUTEX_PROXY_READY && !requested[8]);
 /* Three full ring turns, with an unselected linked anchor throughout. */
 for (unsigned int i = 0; i < 24; i++) {
  batch.pin_budget = 24 - i;
  CHECK(kd_mutex_batch_pin_select(&batch, &nodes[i], true));
  CHECK(batch.nr_pins <= 8 && batch.nr_pins <= batch.pin_budget);
  consume(i);
 }
 CHECK(!batch.nr_pins && requests == 24 && completions == 24 && cas_attempts == 0);
 CHECK(!requested[24] && !requested[25] && !cancellations);
 CHECK(batch.pin_head == start_head);
 kd_mutex_batch_unpin(&batch, false);
}

static void selection_boundaries(void)
{
 setup();
 nodes[0].tail = (raw_smp_processor_id() + 1) << KD_MUTEX_TAIL_CPU_OFFSET;
 CHECK(!kd_mutex_batch_pin_select(&batch, &nodes[0], true));
 CHECK(!batch.nr_pins && !requests);
 for (unsigned int duplicate = 0; duplicate < 2; duplicate++) {
  setup();
  nodes[2].tail = duplicate ? nodes[1].tail + 1 :
      (raw_smp_processor_id() + 1) << KD_MUTEX_TAIL_CPU_OFFSET;
  CHECK(kd_mutex_batch_pin_select(&batch, &nodes[0], true));
  CHECK(batch.nr_pins == 2 && requests == 2 && !requested[2]);
  kd_mutex_batch_unpin(&batch, false);
  CHECK(cancellations == 2);
 }
 /* Stop at the first boundary; do not skip it to select a later request. */
 for (unsigned int reason = 0; reason < 7; reason++) {
  setup();
  if (reason == 0) nodes[1].regs.ip++;
  if (reason == 1) nodes[1].numa_node = 1;
  if (reason == 2) nodes[1].entry_abi = KD_ENTRY_ABI_LEGACY;
  if (reason == 3) nodes[1].packet_state = KD_PACKET_FULL;
  if (reason == 4) nodes[0].next = NULL;
  if (reason == 5) { batch.deferred_head = &nodes[7]; nodes[1].next = NULL; }
  CHECK(kd_mutex_batch_pin_select(&batch, &nodes[0], reason != 6));
  CHECK(batch.nr_pins == 1 && requests == 1 && !requested[1]);
  kd_mutex_batch_unpin(&batch, false);
 }
 for (unsigned int limit = 1; limit < KD_MUTEX_PIN_WINDOW; limit++) {
  setup(); batch.pin_budget = limit;
  CHECK(kd_mutex_batch_pin_select(&batch, &nodes[0], true));
  CHECK(batch.nr_pins == limit && requests == limit);
  kd_mutex_batch_unpin(&batch, false);
 }
 /* Existing detached prefix does not stop immediate linked local service. */
 setup(); batch.deferred_head = &nodes[7]; nodes[4].next = NULL;
 CHECK(kd_mutex_batch_pin_select(&batch, &nodes[0], true));
 CHECK(batch.nr_pins == 4 && !requested[4]);
 consume(0);
 CHECK(kd_mutex_batch_pin_select(&batch, &nodes[1], true));
 CHECK(batch.nr_pins == 3 && !requested[4]); /* Terminal stays unselected. */
 kd_mutex_batch_unpin(&batch, false);
 setup(); batch.deferred_head = &nodes[7];
 kd_mutex_batch_pin_budget(&batch, KDLOCK_MUTEX_NUMA_BOUNDARY - 2);
 CHECK(batch.pin_budget == 3);
 CHECK(kd_mutex_batch_pin_select(&batch, &nodes[0], true));
 CHECK(batch.nr_pins == 3); kd_mutex_batch_unpin(&batch, false);
 kd_mutex_batch_pin_budget(&batch, KDLOCK_MUTEX_NUMA_BOUNDARY);
 CHECK(batch.pin_budget == 1);
 kd_mutex_batch_pin_budget(&batch, KDLOCK_MUTEX_NUMA_BOUNDARY + 1);
 CHECK(batch.pin_budget == 1); /* Late first deferral cannot underflow. */
 batch.deferred_head = NULL;
 kd_mutex_batch_pin_budget(&batch, kd_mutex_batch_size - 1);
 CHECK(batch.pin_budget == 2);
 kd_mutex_batch_pin_budget(&batch, kd_mutex_batch_size);
 CHECK(batch.pin_budget == 1);
 setup(); batch.numa_node = -1; nodes[1].numa_node = 1;
 CHECK(kd_mutex_batch_pin_select(&batch, &nodes[0], true));
 CHECK(batch.nr_pins == 8); /* Existing FIFO rejoin permits other NUMA nodes. */
 kd_mutex_batch_unpin(&batch, false);
}

static void cancellation(void)
{
 setup();
 CHECK(kd_mutex_batch_pin_select(&batch, &nodes[0], true));
 kd_mutex_batch_unpin(&batch, true);
 CHECK(batch.nr_pins == 1 && batch.pins[batch.pin_head].node == &nodes[0]);
 CHECK(cancellations == 7 && requests == 8 && cas_attempts == 0);
 for (unsigned int i = 1; i < 8; i++) CHECK(nodes[i].locked == KD_MUTEX_WAIT);
 kd_mutex_batch_unpin(&batch, false);
 CHECK(!batch.nr_pins && cancellations == 8);
 /* Withdrawn invocations never rearm. A later executor may hand them off,
  * but a fresh nonblocking claim must fail without a descriptor or PAUSE. */
 batch.pin_budget = 1;
 CHECK(!kd_mutex_batch_pin_select(&batch, &nodes[0], true));
 CHECK(!batch.nr_pins && requests == 8 && cas_attempts == 0);
}

static void claim_expiry_and_terminal(void)
{
 setup();kd_mutex_batch_epoch_end(&batch,false);
 CHECK(kd_mutex_gate_try_withdraw(&lock));nodes[0].locked=KD_MUTEX_WAIT;
 kd_mutex_gate_end_withdraw(&lock);CHECK(kd_mutex_batch_epoch_begin(&batch));
 CHECK(!kd_mutex_batch_pin_select(&batch, &nodes[0], true));
 CHECK(!batch.nr_pins && !requests && cas_attempts == 0 && nodes[0].locked == KD_MUTEX_WAIT);
 setup();kd_mutex_batch_epoch_end(&batch,false);
 CHECK(kd_mutex_gate_try_withdraw(&lock));nodes[3].locked=KD_MUTEX_WAIT;
 kd_mutex_gate_end_withdraw(&lock);CHECK(kd_mutex_batch_epoch_begin(&batch));
 CHECK(kd_mutex_batch_pin_select(&batch, &nodes[0], true));
 CHECK(batch.nr_pins == 3 && requests == 3 && cas_attempts == 0);
 CHECK(nodes[3].locked == KD_MUTEX_WAIT && !requested[3] && !requested[4]);
 kd_mutex_batch_unpin(&batch, false);
 setup(); nodes[0].next = NULL;
 CHECK(kd_mutex_batch_pin_select(&batch, &nodes[0], true));
 CHECK(batch.nr_pins == 1 && requests == 1 && cas_attempts == 0);
 kd_mutex_batch_unpin(&batch, false);
 setup(); nodes[5].next = NULL;
 CHECK(kd_mutex_batch_pin_select(&batch, &nodes[0], true));
 CHECK(batch.nr_pins == 6 && requests == 6 && requested[5]);
 CHECK(nodes[5].locked == KD_MUTEX_PROXY_CLAIMED);
 kd_mutex_batch_unpin(&batch, false);
}

static void invalid_identity(const char *name)
{
 setup();
 if (!strcmp(name, "bad-head")) {
  batch.pin_head = KD_MUTEX_PIN_WINDOW;
  kd_mutex_batch_pin_select(&batch, &nodes[0], false);
 } else if (!strcmp(name, "occupied-slot")) {
  batch.pins[batch.pin_head].node = &nodes[7];
  kd_mutex_batch_pin_select(&batch, &nodes[0], false);
 } else if (!strcmp(name, "odd-generation")) {
  nodes[0].count_seq++;
  kd_mutex_batch_pin_select(&batch, &nodes[0], false);
 } else {
  CHECK(kd_mutex_batch_pin_select(&batch, &nodes[0], false));
  if (!strcmp(name, "generation")) nodes[0].count_seq += 2;
  else if (!strcmp(name, "wrong-lock")) nodes[0].counted_lock = &other_lock;
  else if (!strcmp(name, "wrong-current")) {
   kd_mutex_batch_pin_select(&batch, &nodes[1], false);
   CHECK(false);
  } else if (!strcmp(name, "complete-unclaimed")) {
   nodes[0].locked = KD_MUTEX_PROXY_READY;
   kd_mutex_batch_pin_complete(&batch, &nodes[0]);
   CHECK(false);
  } else CHECK(false);
  kd_mutex_batch_unpin(&batch, false);
 }
 CHECK(false); /* Production must reject an invalid exact invocation. */
}

int main(int argc, char **argv)
{
 if (argc == 2) invalid_identity(argv[1]);
 CHECK(argc == 1);
 for (start_head = 0; start_head < KD_MUTEX_PIN_WINDOW; start_head++) {
  bounded_refill();
  selection_boundaries();
  cancellation();
  claim_expiry_and_terminal();
 }
 printf("PASS pin window: %u checks; bound8/three ring turns/all heads, exact nonblocking claims, CPU/image/NUMA/deferred/cap boundaries, expiry arbitration, no rearm and slot reuse\n", checks);
 return 0;
}
