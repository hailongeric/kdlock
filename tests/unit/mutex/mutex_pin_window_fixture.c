// SPDX-License-Identifier: GPL-2.0
/* Production single-current claim helpers; atomic observers substitute origin execution.
 * Actual gate epochs protect READY reservations; cold boundaries promote retained pins. No kernel, JIT or scheduler runs. */
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
struct task_struct { unsigned int pid; } __attribute__((aligned(8)));
struct kd_exec_frame;
#include "kd_regs.h"
#define KD_MUTEX_DIAG_MEMBER
#define KD_MUTEX_TAIL_CPU_OFFSET 4
#include "pin_window_types.h"

#define NODE_COUNT 40
static struct kd_mutex lock, other_lock;
static struct kd_mutex_node nodes[NODE_COUNT];
static struct kd_mutex_batch batch;
static unsigned int checks, requests, promotions, cancellations, completions, cas_attempts, expiry_probes;
static unsigned int requested[NODE_COUNT];
static bool poisoned[NODE_COUNT];
static bool require_withdrawn_on_bug;
static int executor_cpu;
static struct task_struct owner={1}, later_owner={2};
static struct task_struct *current=&owner;
static int allowed_node = -1;
static bool admission_active, admission_injected;
static unsigned int owner_reads, gate_reads, ready_reads, generation_reads, key_reads, cpu_reads;
enum admission_change { ADMISSION_STABLE, ADMISSION_GENERATION, ADMISSION_KEY, ADMISSION_NODE };
static enum admission_change admission_change;

#define CHECK(value) do { checks++; if (!(value)) { \
 fprintf(stderr, "FAIL pin window line %d: %s\n", __LINE__, #value); exit(1); \
} } while (0)
#define BUG_ON(value) do { if (value) { \
 if(require_withdrawn_on_bug)CHECK(nodes[0].locked==KD_MUTEX_WAIT && !promotions); \
 if(admission_change!=ADMISSION_STABLE)CHECK(admission_injected); \
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
 if (!admission_active) return;
 if (address==&nodes[index].count_seq) {
  generation_reads++;
  if (admission_change==ADMISSION_NODE && generation_reads==2) {
   /* Deliberate descriptor corruption after the checked node was captured.
    * The selector must still reject a different successfully recorded node. */
   CHECK(batch.nr_pins==1 && batch.pin.node==&nodes[index]);
   batch.pin.node=&nodes[index+1];admission_injected=true;
  }
 }
 if (address==&nodes[index].counted_lock)key_reads++;
 if (address==&nodes[index].locked) {
  ready_reads++;
  if (admission_change==ADMISSION_GENERATION || admission_change==ADMISSION_KEY) {
   CHECK(generation_reads==1 && key_reads==1 && !admission_injected);
   /* Inject only after preflight captured both fields and before the final
    * production re-read. Valid execution cannot recycle a live reservation. */
   if (admission_change==ADMISSION_GENERATION)nodes[index].count_seq+=2;
   else nodes[index].counted_lock=&other_lock;
   admission_injected=true;
  }
 }
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
  CHECK(batch.nr_pins==1 && batch.pin.node==&nodes[index]);
  CHECK(nodes[index].locked==KD_MUTEX_PROXY_READY && requested[index]);
  promotions++;return;
 }
 CHECK(value == KD_MUTEX_WAIT || value == 0);
 CHECK(requested[index]);
 CHECK(nodes[index].locked==KD_MUTEX_PROXY_CLAIMED ||
       (nodes[index].locked==KD_MUTEX_PROXY_READY && batch.proxy_epoch &&
        !batch.outer.released && lock.owner==(unsigned long)current &&
        lock.delegation_state.counter==KD_MUTEX_GATE_COMBINER));
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
/* Count accesses at the actual gate helper boundary; keep its masked acquire
 * read unchanged, including its treatment of withdrawal and unrelated bits. */
#define kd_mutex_gate_read kd_mutex_gate_read_unobserved
#include "mutex_state_mock.h"
#undef kd_mutex_gate_read
static u32 kd_mutex_gate_read(struct kd_mutex *value)
{
 if(admission_active)gate_reads++;
 return kd_mutex_gate_read_unobserved(value);
}
static void kd_mutex_set_locked(struct kd_mutex *value)
{
 CHECK(value==&lock);
 /* No unpin window may open before a live current is independently retained. */
 if(batch.nr_pins)CHECK(batch.pin.node && batch.pin.node->locked==KD_MUTEX_PROXY_CLAIMED);
 kd_mutex_gate_set(value,KD_MUTEX_GATE_HELD);
 if(batch.nr_pins) {
  u8 ready=KD_MUTEX_PROXY_READY;
  CHECK(kd_mutex_gate_try_withdraw(value));
  /* An origin with a stale READY poll cannot withdraw the promoted current. */
  CHECK(!__atomic_compare_exchange_n(&batch.pin.node->locked,&ready,KD_MUTEX_WAIT,
                                    false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST));
  CHECK(ready==KD_MUTEX_PROXY_CLAIMED);expiry_probes++;
  kd_mutex_gate_end_withdraw(value);
 }
}
/* The generated production predicate reads the actual owner word. Explicit
 * task alignment keeps its three flag bits independent of pointer identity. */
static unsigned long owner_read(const atomic_long_t *word)
{
 CHECK(word==&lock.owner);
 if(admission_active)owner_reads++;
 return __atomic_load_n(word,__ATOMIC_RELAXED);
}
#define atomic_long_read(word) owner_read(word)
static int raw_smp_processor_id(void)
{ if(admission_active)cpu_reads++;return executor_cpu; }
static void __attribute__((unused)) cpu_relax(void) { CHECK(false); }
#include "pin_window_production.h"

static void setup(void)
{
 memset(&batch, 0, sizeof(batch));
 memset(nodes, 0, sizeof(nodes));
 memset(requested, 0, sizeof(requested));
 memset(poisoned, 0, sizeof(poisoned));
 requests = promotions = cancellations = completions = cas_attempts = expiry_probes = 0;
 allowed_node = -1; executor_cpu = 0; current=&owner;require_withdrawn_on_bug=false;
 admission_active=admission_injected=false;admission_change=ADMISSION_STABLE;
 owner_reads=gate_reads=ready_reads=generation_reads=key_reads=cpu_reads=0;
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
 owner_reads=gate_reads=ready_reads=generation_reads=key_reads=cpu_reads=0;
 admission_active=true;
 selected = kd_mutex_batch_pin_select(&batch, &nodes[index]);
 admission_active=false;
 if(selected) {
  CHECK(nodes[index].locked==KD_MUTEX_PROXY_READY && !requested[index]);
  requested[index]=1;requests++;
 }
 allowed_node = -1;
 return selected;
}

static void consume(unsigned int index)
{
 kd_mutex_batch_pin_assert(&batch,&nodes[index]);
 CHECK(requested[index]);
 if(batch.proxy_epoch)kd_mutex_batch_pin_complete(&batch,&nodes[index]);
 else kd_mutex_batch_pin_complete_retained(&batch,&nodes[index]);
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
 CHECK(!cancellations && !promotions && !cas_attempts);
 kd_mutex_batch_epoch_end(&batch, true);
 CHECK(!batch.proxy_epoch && kd_mutex_gate_read(&lock) == KD_MUTEX_GATE_HELD);
 /* Reuse the same slot with a fresh generation after the previous wake. */
 poisoned[0] = false; nodes[0].locked = KD_MUTEX_PROXY_READY;
 nodes[0].counted_lock = &lock; nodes[0].next = NULL;
 CHECK(kd_mutex_batch_epoch_begin(&batch));
 CHECK(select_current(0)); consume(0);
 kd_mutex_batch_epoch_end(&batch, false);
 CHECK(requests == completions && !promotions && !cancellations && !cas_attempts);
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

static void predicate_contract(void)
{
 const u32 extra_bits[]={0,KD_MUTEX_GATE_WITHDRAW,0x10U,0x80000000U,
                         U32_MAX & ~KD_MUTEX_GATE_PHASE_MASK};
 struct task_struct *tasks[]={current,&later_owner,NULL};
 unsigned long owners[]={0,(unsigned long)current,(unsigned long)&later_owner};

 setup();
 admission_active=true;owner_reads=gate_reads=0;
 CHECK(!kd_mutex_combiner_owned(NULL,current));
 CHECK(!kd_mutex_combiner_owned(&lock,&later_owner));
 CHECK(!kd_mutex_combiner_owned(&lock,NULL));
 admission_active=false;
 CHECK(!owner_reads && !gate_reads);
 lock.delegation_state.counter=KD_MUTEX_GATE_COMBINER|KD_MUTEX_GATE_WITHDRAW|0x10U;
 CHECK(kd_mutex_combiner_owned(&lock,current));
 /* The old conjunction and specialized helper must agree on snapshots.
  * Impossible phase/extra-bit combinations are predicate compatibility cases,
  * not states the gate transition protocol is permitted to publish. */
 for(unsigned int owner_index=0;owner_index<3;owner_index++)
  for(unsigned long flags=0;flags<8;flags++)
   for(unsigned int task_index=0;task_index<3;task_index++)
    for(u32 phase=0;phase<=KD_MUTEX_GATE_PHASE_MASK;phase++)
     for(unsigned int extra=0;extra<sizeof(extra_bits)/sizeof(extra_bits[0]);extra++) {
      bool actual,previous,owned;
      struct task_struct *task=tasks[task_index];
      lock.owner=owners[owner_index]|flags;
      lock.delegation_state.counter=phase|extra_bits[extra];
      owner_reads=gate_reads=0;admission_active=true;
      actual=kd_mutex_combiner_owned(&lock,task);
      admission_active=false;
      previous=kd_mutex_delegation_owned(&lock,task) &&
               kd_mutex_gate_read(&lock)==KD_MUTEX_GATE_COMBINER;
      CHECK(actual==previous);
      owned=task==current && owner_index==1 && !(flags&4UL);
      CHECK(owner_reads==(unsigned int)(task==current));
      CHECK(gate_reads==(unsigned int)owned);
     }
}

static void admission_contract(void)
{
 /* Count only the actual selection region, not prior epoch admission or the
  * fresh post-execution/cold assertions. The capture and re-read both remain. */
 for (unsigned long flags=0;flags<4;flags++) {
  setup();lock.owner=(unsigned long)current|flags;
  CHECK(select_current(0));
  CHECK(owner_reads==1 && gate_reads==1 && ready_reads==1 && cpu_reads==1);
  CHECK(generation_reads==2 && key_reads==2 && !promotions && !cas_attempts);
  CHECK(batch.nr_pins==1 && batch.pin.node==&nodes[0] && batch.pin.generation==2);
  /* A later READY boundary performs its own fresh exact-phase proof. */
  owner_reads=gate_reads=ready_reads=generation_reads=key_reads=cpu_reads=0;
  admission_active=true;kd_mutex_batch_pin_assert(&batch,&nodes[0]);admission_active=false;
  CHECK(owner_reads==1 && gate_reads==1 && ready_reads==1 && !cpu_reads);
  CHECK(generation_reads==1 && key_reads==1);
  lock.owner=(unsigned long)current;consume(0);kd_mutex_batch_epoch_end(&batch,false);
 }
 for (unsigned int state=0;state<=KD_MUTEX_QUEUE_INIT;state++) {
  if(state==KD_MUTEX_PROXY_READY)continue;
  setup();nodes[0].locked=state;
  CHECK(!select_current(0));
  CHECK(!batch.nr_pins && !batch.pin.node && !requests && !requested[0]);
  CHECK(nodes[0].locked==state && owner_reads==1 && gate_reads==1 && ready_reads==1 && cpu_reads==2);
  CHECK(generation_reads==1 && key_reads==1 && !promotions && !cas_attempts);
  kd_mutex_batch_epoch_end(&batch,false);
 }
 for (unsigned int state=0;state<=KD_MUTEX_QUEUE_INIT;state++) {
  setup();nodes[0].tail=(executor_cpu+1)<<KD_MUTEX_TAIL_CPU_OFFSET;nodes[0].locked=state;
  CHECK(!select_current(0));
  CHECK(!batch.nr_pins && !batch.pin.node && !requests && nodes[0].locked==state);
  CHECK(owner_reads==1 && gate_reads==1 && !ready_reads && cpu_reads==2 && generation_reads==1 && key_reads==1);
  kd_mutex_batch_epoch_end(&batch,false);
 }
}

static void cold_boundaries(void)
{
 setup(); CHECK(select_current(0));
 CHECK(!kd_mutex_gate_try_withdraw(&lock)); /* Epoch blocks every READY origin. */
 kd_mutex_batch_epoch_end(&batch, true);
 CHECK(!batch.proxy_epoch && batch.nr_pins == 1 && batch.pin.node == &nodes[0]);
 CHECK(nodes[0].locked == KD_MUTEX_PROXY_CLAIMED && nodes[1].locked == KD_MUTEX_PROXY_READY);
 CHECK(!cancellations && promotions==1 && expiry_probes==1);
 kd_mutex_batch_pin_assert_retained(&batch,&nodes[0]);
 kd_mutex_batch_epoch_end(&batch,true); /* Already retained: no new promotion. */
 CHECK(promotions==1 && expiry_probes==1 && kd_mutex_gate_try_withdraw(&lock));
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
 /* Retained cold proof survives early release and an unrelated later owner. */
 setup();CHECK(select_current(0));kd_mutex_batch_epoch_end(&batch,true);
 batch.outer.released=true;lock.owner=(unsigned long)&later_owner;
 lock.delegation_state.counter=KD_MUTEX_GATE_COMBINER;
 kd_mutex_batch_pin_assert_retained(&batch,&nodes[0]);consume(0);
 kd_mutex_batch_assert_cold(&batch); /* Empty native callback must not read reused node. */
 CHECK(promotions==1 && completions==1 && !batch.nr_pins);
}

static void invalid_identity(const char *name)
{
 setup();
 if (!strcmp(name,"admission-generation-change") || !strcmp(name,"admission-key-change") ||
     !strcmp(name,"admission-wrong-current")) {
  admission_change=!strcmp(name,"admission-generation-change")?ADMISSION_GENERATION:
                   !strcmp(name,"admission-key-change")?ADMISSION_KEY:ADMISSION_NODE;
  select_current(0);CHECK(false);
 } else if (!strcmp(name,"admission-pickup") || !strcmp(name,"admission-other-owner") ||
            !strcmp(name,"admission-released") || !strcmp(name,"admission-private-epoch") ||
            !strcmp(name,"admission-wrong-key") || !strcmp(name,"admission-held") ||
            !strcmp(name,"admission-free") || !strcmp(name,"admission-acquiring")) {
  if(!strcmp(name,"admission-pickup"))lock.owner|=4UL;
  else if(!strcmp(name,"admission-other-owner"))lock.owner=(unsigned long)&later_owner;
  else if(!strcmp(name,"admission-released"))batch.outer.released=true;
  else if(!strcmp(name,"admission-private-epoch"))batch.proxy_epoch=false;
  else if(!strcmp(name,"admission-wrong-key"))nodes[0].counted_lock=&other_lock;
  else if(!strcmp(name,"admission-held"))lock.delegation_state.counter=KD_MUTEX_GATE_HELD;
  else if(!strcmp(name,"admission-free"))lock.delegation_state.counter=KD_MUTEX_GATE_FREE;
  else lock.delegation_state.counter=KD_MUTEX_GATE_ACQUIRING;
  select_current(0);CHECK(false);
 } else if (!strcmp(name, "occupied-slot")) {
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
   nodes[0].locked = KD_MUTEX_WAIT;
   kd_mutex_batch_pin_complete(&batch, &nodes[0]); CHECK(false);
  } else if (!strcmp(name,"expiry-before-promotion")) {
   /* Deliberately violate the ordering: expiry owns the pin before retention. */
   kd_mutex_gate_set(&lock,KD_MUTEX_GATE_HELD);
   CHECK(kd_mutex_gate_try_withdraw(&lock));
   u8 ready=KD_MUTEX_PROXY_READY;
   CHECK(__atomic_compare_exchange_n(&nodes[0].locked,&ready,KD_MUTEX_WAIT,
                                     false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST));
   kd_mutex_gate_end_withdraw(&lock);require_withdrawn_on_bug=true;
   kd_mutex_batch_epoch_end(&batch,true);CHECK(false);
  } else if (!strcmp(name,"ready-without-epoch")) {
   batch.proxy_epoch=false;kd_mutex_batch_pin_complete(&batch,&nodes[0]);CHECK(false);
  } else if (!strcmp(name,"later-owner-combiner")) {
   lock.owner=(unsigned long)&later_owner;
   kd_mutex_batch_pin_assert(&batch,&nodes[0]);CHECK(false);
  } else if (!strcmp(name,"released-epoch")) {
   batch.outer.released=true;kd_mutex_batch_pin_assert(&batch,&nodes[0]);CHECK(false);
  } else if (!strcmp(name,"ready-held")) {
   lock.delegation_state.counter=KD_MUTEX_GATE_HELD;
   kd_mutex_batch_pin_assert(&batch,&nodes[0]);CHECK(false);
  } else if (!strcmp(name,"retained-ready")) {
   batch.proxy_epoch=false;lock.delegation_state.counter=KD_MUTEX_GATE_HELD;
   kd_mutex_batch_pin_complete_retained(&batch,&nodes[0]);CHECK(false);
  } else if (!strcmp(name,"retained-open-epoch")) {
   smp_store_release(&nodes[0].locked,KD_MUTEX_PROXY_CLAIMED);
   kd_mutex_batch_pin_complete_retained(&batch,&nodes[0]);CHECK(false);
  } else CHECK(false);
  kd_mutex_batch_unpin(&batch, false);
 }
 CHECK(false);
}

int main(int argc, char **argv)
{
 if (argc == 2) invalid_identity(argv[1]);
 CHECK(argc == 1);
 predicate_contract(); sequential_currents(); selection_boundaries(); admission_contract(); cold_boundaries();
 printf("PASS pin window: %u checks; one exact READY current, delayed cold promotion, sequential slot reuse, no future access, exact admission loads and real owner flags, one fresh gate read, masked-phase predicate equivalence, self-CPU refusal, cold epoch closure, fresh arbitration and no rearm\n", checks);
 return 0;
}
