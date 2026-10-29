// SPDX-License-Identifier: GPL-2.0
/* Production pin-window helpers; atomic observers substitute origin execution.
 * Each origin ACK is deliberately delayed. No kernel, JIT or scheduler runs. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef unsigned long atomic_long_t;
typedef unsigned int atomic_t;
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

#define NODE_COUNT 8
static struct kd_mutex lock, other_lock;
static struct kd_mutex_node nodes[NODE_COUNT];
static struct kd_mutex_batch batch;
static unsigned int checks, requests, acknowledgements, cancellations, completions;
static unsigned int requested[NODE_COUNT], acked[NODE_COUNT], delayed[NODE_COUNT];
static bool poisoned[NODE_COUNT];
static int polled, executor_cpu;

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
 if (address == &nodes[index].locked) polled = index;
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
 if (value == KD_MUTEX_PROXY_REQUEST) {
  CHECK(nodes[index].locked == KD_MUTEX_WAIT && !requested[index] && !acked[index]);
  requested[index] = 1;
  delayed[index] = 0;
  requests++;
 } else {
  CHECK(value == KD_MUTEX_WAIT || value == 0);
  CHECK(requested[index] && acked[index] && nodes[index].locked == KD_MUTEX_PROXY_PINNED);
  descriptor_absent(&nodes[index]);
  requested[index] = acked[index] = 0;
  if (value == KD_MUTEX_WAIT) cancellations++;
  else completions++;
 }
}

#define READ_ONCE(value) (observe_read(&(value)), __atomic_load_n(&(value), __ATOMIC_RELAXED))
#define smp_load_acquire(word) (observe_read(word), __atomic_load_n((word), __ATOMIC_ACQUIRE))
#define smp_store_release(word, value) do { \
 observe_store((word), (value)); __atomic_store_n((word), (value), __ATOMIC_RELEASE); \
} while (0)
static int raw_smp_processor_id(void) { return executor_cpu; }
static void cpu_relax(void)
{
 CHECK(polled >= 0 && polled < NODE_COUNT && !poisoned[polled]);
 CHECK(requested[polled] && !acked[polled] &&
       nodes[polled].locked == KD_MUTEX_PROXY_REQUEST);
 CHECK(++delayed[polled] <= 2);
 if (delayed[polled] == 2) {
  /* The origin's real preemption pin is represented by this exact ACK. */
  acked[polled] = 1;
  acknowledgements++;
  __atomic_store_n(&nodes[polled].locked, KD_MUTEX_PROXY_PINNED, __ATOMIC_RELEASE);
 }
}
#include "pin_window_production.h"

static void setup(void)
{
 memset(&batch, 0, sizeof(batch));
 memset(nodes, 0, sizeof(nodes));
 memset(requested, 0, sizeof(requested));
 memset(acked, 0, sizeof(acked));
 memset(delayed, 0, sizeof(delayed));
 memset(poisoned, 0, sizeof(poisoned));
 requests = acknowledgements = cancellations = completions = 0;
 polled = -1;
 executor_cpu = 0;
 batch.lock = &lock;
 batch.numa_node = 0;
 batch.pin_budget = 20;
 for (unsigned int i = 0; i < NODE_COUNT; i++) {
  nodes[i].next = i + 1 < NODE_COUNT ? &nodes[i + 1] : NULL;
  nodes[i].tail = (i + 2) << KD_MUTEX_TAIL_CPU_OFFSET;
  nodes[i].locked = KD_MUTEX_WAIT;
  nodes[i].counted_lock = nodes[i].lock = &lock;
  nodes[i].count_seq = 2 * i + 2;
  nodes[i].entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
  nodes[i].packet_state = KD_PACKET_MINIMAL;
  nodes[i].regs.ip = 0xcafe;
 }
}

static void consume(unsigned int index)
{
 kd_mutex_proxy_wait_pinned(&nodes[index]);
 CHECK(acked[index] && delayed[index] == 2);
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
 CHECK(KD_MUTEX_PIN_WINDOW == 4);
 CHECK(kd_mutex_batch_pin_select(&batch, &nodes[0], true));
 CHECK(batch.nr_pins == 4 && requests == 4 && !acknowledgements);
 kd_mutex_proxy_wait_pinned(&nodes[0]);
 CHECK(acknowledgements == 1 && acked[0] && !acked[1] && !acked[2] && !acked[3]);
 CHECK(nodes[4].locked == KD_MUTEX_WAIT && !requested[4]);
 /* Six requests remain in this batch; the last two must never be selected. */
 for (unsigned int i = 0; i < 6; i++) {
  batch.pin_budget = 6 - i;
  CHECK(kd_mutex_batch_pin_select(&batch, &nodes[i], true));
  CHECK(batch.nr_pins <= 4 && batch.nr_pins <= batch.pin_budget);
  consume(i);
 }
 CHECK(!batch.nr_pins && requests == 6 && completions == 6 && acknowledgements == 6);
 CHECK(!requested[6] && !requested[7] && !cancellations);
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
  CHECK(cancellations == 2 && acknowledgements == 2);
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
 for (unsigned int limit = 1; limit <= 3; limit++) {
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
 CHECK(batch.nr_pins == 4); /* Existing FIFO rejoin permits other NUMA nodes. */
 kd_mutex_batch_unpin(&batch, false);
}

static void cancellation(void)
{
 setup();
 CHECK(kd_mutex_batch_pin_select(&batch, &nodes[0], true));
 /* None has ACKed yet. Closing a dispatch/ownership window must drain each
  * selected successor's late ACK before WAIT, keeping only current. */
 CHECK(!acknowledgements);
 kd_mutex_batch_unpin(&batch, true);
 CHECK(batch.nr_pins == 1 && batch.pins[0].node == &nodes[0]);
 CHECK(cancellations == 3 && acknowledgements == 3 && !acked[0]);
 for (unsigned int i = 1; i < 4; i++)
  CHECK(nodes[i].locked == KD_MUTEX_WAIT && delayed[i] == 2);
 kd_mutex_batch_unpin(&batch, false);
 CHECK(!batch.nr_pins && cancellations == 4 && acknowledgements == 4);
 /* A cancelled invocation may be selected again with the same generation;
  * each new REQUEST independently needs its own acknowledgement. */
 batch.pin_budget = 1;
 CHECK(kd_mutex_batch_pin_select(&batch, &nodes[0], true));
 consume(0);
 CHECK(requests == 5 && acknowledgements == 5 && completions == 1);
}

static void invalid_identity(const char *name)
{
 setup();
 if (!strcmp(name, "odd-generation")) {
  nodes[0].count_seq++;
  kd_mutex_batch_pin_select(&batch, &nodes[0], false);
 } else {
  CHECK(kd_mutex_batch_pin_select(&batch, &nodes[0], false));
  if (!strcmp(name, "generation")) nodes[0].count_seq += 2;
  else if (!strcmp(name, "wrong-lock")) nodes[0].counted_lock = &other_lock;
  else if (!strcmp(name, "wrong-current")) {
   kd_mutex_batch_pin_select(&batch, &nodes[1], false);
   CHECK(false);
  } else if (!strcmp(name, "complete-unacked")) {
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
 bounded_refill();
 selection_boundaries();
 cancellation();
 printf("PASS pin window: %u checks; bound4/refill, exact current ACK, CPU/image/NUMA/deferred/cap boundaries, delayed cancellation and slot reuse\n", checks);
 return 0;
}
