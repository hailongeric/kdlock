// SPDX-License-Identifier: GPL-2.0
/* Production single-current claim helpers; atomic observers substitute origin execution.
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
static int allowed_node = -1;

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
 CHECK(allowed_node < 0 || index == allowed_node);
}

static void descriptor_absent(struct kd_mutex_node *node)
{
 CHECK(batch.nr_pins <= KD_MUTEX_CLAIM_SLOTS);
 CHECK(batch.pin.node != node);
}

static void observe_store(void *address, unsigned long value)
{
 int index = node_at(address);

 CHECK(index >= 0 && address == &nodes[index].locked && !poisoned[index]);
 if(value==KD_MUTEX_PROXY_CLAIMED) {
  CHECK(batch.proxy_epoch && lock.delegation_state.counter==KD_MUTEX_GATE_COMBINER);
  CHECK(!batch.nr_pins && !batch.pin.node && (allowed_node < 0 || index == allowed_node));
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
 memset(nodes, 0, sizeof(nodes));
 memset(requested, 0, sizeof(requested));
 memset(poisoned, 0, sizeof(poisoned));
 requests = cancellations = completions = cas_attempts = 0;
 allowed_node = -1; executor_cpu = 0;
 batch.lock = &lock; lock.owner = (unsigned long)current;
 lock.delegation_state.counter = KD_MUTEX_GATE_HELD;
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

static bool select_current(unsigned int index)
{
 bool selected;
 allowed_node = (int)index;
 selected = kd_mutex_batch_pin_select(&batch, &nodes[index]);
 allowed_node = -1;
 return selected;
}

static void consume(unsigned int index)
{
 kd_mutex_proxy_assert_claimed(&nodes[index]);
 CHECK(requested[index]);
 kd_mutex_batch_pin_complete(&batch, &nodes[index]);
 descriptor_absent(&nodes[index]);
 smp_store_release(&nodes[index].locked, 0);
 /* Completed slots may be reused immediately; stale descriptor reads fail. */
 poisoned[index] = true;
 nodes[index].counted_lock = NULL;
 nodes[index].count_seq += 2;
 nodes[index].next = (void *)(uintptr_t)1;
 nodes[index].regs.ip = 0xdead;
}

static void sequential_currents(void)
{
 setup(); CHECK(KD_MUTEX_CLAIM_SLOTS == 1);
 for (unsigned int i = 0; i < 24; i++) {
  CHECK(select_current(i));
  CHECK(batch.nr_pins == 1 && batch.pin.node == &nodes[i]);
  CHECK(batch.pin.generation == nodes[i].count_seq);
  CHECK(nodes[i + 1].locked == KD_MUTEX_PROXY_READY && !requested[i + 1]);
  consume(i);
 }
 CHECK(!batch.nr_pins && !batch.pin.node && requests == 24 && completions == 24);
 CHECK(!cancellations && !cas_attempts);
 kd_mutex_batch_epoch_end(&batch, true);
 CHECK(!batch.proxy_epoch && kd_mutex_gate_read(&lock) == KD_MUTEX_GATE_HELD);
 /* Reuse the same slot with a fresh generation after the previous wake. */
 poisoned[0] = false; nodes[0].locked = KD_MUTEX_PROXY_READY;
 nodes[0].counted_lock = &lock; nodes[0].next = NULL;
 CHECK(kd_mutex_batch_epoch_begin(&batch));
 CHECK(select_current(0)); consume(0);
 kd_mutex_batch_epoch_end(&batch, false);
 CHECK(requests == completions && !cancellations && !cas_attempts);
}

static void selection_boundaries(void)
{
 setup();
 nodes[0].tail = (executor_cpu + 1) << KD_MUTEX_TAIL_CPU_OFFSET;
 CHECK(!select_current(0) && !batch.nr_pins && !requests);
 kd_mutex_batch_epoch_end(&batch, false);
 /* A later invocation on the same origin CPU is legal after current retired;
  * no simultaneous future claim is retained to justify a duplicate-CPU walk. */
 setup(); nodes[1].tail = nodes[0].tail;
 CHECK(select_current(0)); consume(0);
 CHECK(select_current(1)); consume(1);
 kd_mutex_batch_epoch_end(&batch, false);
 /* Future packet/NUMA fields and terminal links are not claim inputs. The
  * actual combiner fixtures retain queue policy, total and locality limits. */
 for (unsigned int shape = 0; shape < 5; shape++) {
  setup();
  if (shape == 0) nodes[0].next = NULL;
  if (shape == 1) { nodes[1].regs.ip++; nodes[1].numa_node = 1; }
  if (shape == 2) nodes[1].packet_state = KD_PACKET_FULL;
  if (shape == 3) { batch.deferred_head = &nodes[7]; nodes[1].next = NULL; }
  if (shape == 4) nodes[1].locked = KD_MUTEX_WAIT;
  CHECK(select_current(0)); CHECK(requests == 1 && !requested[1]);
  kd_mutex_batch_epoch_end(&batch, false);
  CHECK(cancellations == 1 && nodes[0].locked == KD_MUTEX_WAIT);
 }
}

static void cold_boundaries(void)
{
 setup(); CHECK(select_current(0));
 CHECK(!kd_mutex_gate_try_withdraw(&lock)); /* Epoch blocks every READY origin. */
 kd_mutex_batch_epoch_end(&batch, true);
 CHECK(!batch.proxy_epoch && batch.nr_pins == 1 && batch.pin.node == &nodes[0]);
 CHECK(nodes[0].locked == KD_MUTEX_PROXY_CLAIMED && nodes[1].locked == KD_MUTEX_PROXY_READY);
 CHECK(!cancellations && kd_mutex_gate_try_withdraw(&lock));
 nodes[1].locked = KD_MUTEX_WAIT; kd_mutex_gate_end_withdraw(&lock);
 consume(0); /* Current's exact claim survives the cold service. */
 CHECK(kd_mutex_batch_epoch_begin(&batch));
 CHECK(!select_current(1) && !batch.nr_pins && !batch.pin.node);
 CHECK(select_current(2)); consume(2); kd_mutex_batch_epoch_end(&batch, false);
 CHECK(!cas_attempts);
 /* Even an empty current must reopen withdrawal before a cold service. */
 setup(); kd_mutex_batch_epoch_end(&batch, true);
 CHECK(!batch.proxy_epoch && kd_mutex_gate_try_withdraw(&lock));
 CHECK(!kd_mutex_batch_epoch_begin(&batch) && !batch.proxy_epoch && !batch.nr_pins);
 kd_mutex_gate_end_withdraw(&lock); CHECK(kd_mutex_batch_epoch_begin(&batch));
 CHECK(select_current(0)); kd_mutex_batch_epoch_end(&batch, false);
 CHECK(!batch.pin.node && !batch.nr_pins && cancellations == 1);
 CHECK(nodes[0].locked == KD_MUTEX_WAIT && nodes[1].locked == KD_MUTEX_PROXY_READY);
 CHECK(kd_mutex_batch_epoch_begin(&batch));
 CHECK(!select_current(0)); /* Cancellation never rearms the invocation. */
 kd_mutex_batch_epoch_end(&batch, false);
}

static void invalid_identity(const char *name)
{
 setup();
 if (!strcmp(name, "occupied-slot")) {
  batch.pin.node = &nodes[7]; select_current(0);
 } else if (!strcmp(name, "excess-count")) {
  batch.nr_pins = 2; kd_mutex_batch_unpin(&batch, false);
 } else if (!strcmp(name, "odd-generation")) {
  nodes[0].count_seq++; select_current(0);
 } else if (!strcmp(name, "without-epoch")) {
  kd_mutex_batch_epoch_end(&batch, false); select_current(0);
 } else {
  CHECK(select_current(0));
  if (!strcmp(name, "generation")) nodes[0].count_seq += 2;
  else if (!strcmp(name, "wrong-lock")) nodes[0].counted_lock = &other_lock;
  else if (!strcmp(name, "wrong-current")) { select_current(1); CHECK(false); }
  else if (!strcmp(name, "complete-unclaimed")) {
   nodes[0].locked = KD_MUTEX_PROXY_READY;
   kd_mutex_batch_pin_complete(&batch, &nodes[0]); CHECK(false);
  } else CHECK(false);
  kd_mutex_batch_unpin(&batch, false);
 }
 CHECK(false);
}

int main(int argc, char **argv)
{
 if (argc == 2) invalid_identity(argv[1]);
 CHECK(argc == 1);
 sequential_currents(); selection_boundaries(); cold_boundaries();
 printf("PASS pin window: %u checks; one exact current, sequential slot reuse, no future access, self-CPU refusal, cold epoch closure, fresh arbitration and no rearm\n", checks);
 return 0;
}
