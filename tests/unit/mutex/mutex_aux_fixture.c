/* SPDX-License-Identifier: GPL-2.0 */
/* Compile the production fixed-slot registry unchanged. Pthreads exercise real
 * atomic reference races; deterministic pauses expose key reuse and observation
 * windows. Kernel allocation, weak-memory ordering and KD physical fallback
 * still require source review and the affected live/queue probes. */
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL aux line %d: %s\n", __LINE__, #c); exit(1); } } while (0)
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef struct { int counter; } atomic_t;
typedef unsigned long atomic_long_t;
typedef unsigned int raw_spinlock_t;
struct task_struct { unsigned long identity; };
static _Thread_local struct task_struct *current;
struct optimistic_spin_queue { atomic_t tail; };
struct list_head { struct list_head *next, *prev; };
#include "aux_types.h"

struct pause_gate {
 pthread_mutex_t mutex;
 pthread_cond_t changed;
 unsigned int reached;
 bool released;
};
#define PAUSE_GATE { PTHREAD_MUTEX_INITIALIZER, PTHREAD_COND_INITIALIZER, 0, false }
static struct pause_gate pause_gate=PAUSE_GATE;
static void wait_changed(pthread_cond_t *condition,pthread_mutex_t *mutex)
{
 struct timespec deadline;
 if(clock_gettime(CLOCK_REALTIME,&deadline)) {
  perror("ERROR aux clock");exit(2);
 }
 deadline.tv_sec+=5;
 int error=pthread_cond_timedwait(condition,mutex,&deadline);
 if(error) {
  fprintf(stderr,"ERROR aux pause wait: %s\n",strerror(error));exit(2);
 }
}
static void gate_reset(void)
{
 CHECK(!pthread_mutex_lock(&pause_gate.mutex));
 pause_gate.reached=0;pause_gate.released=false;
 CHECK(!pthread_mutex_unlock(&pause_gate.mutex));
}
static void gate_reach(void)
{
 CHECK(!pthread_mutex_lock(&pause_gate.mutex));pause_gate.reached++;
 CHECK(!pthread_cond_broadcast(&pause_gate.changed));
 while(!pause_gate.released)wait_changed(&pause_gate.changed,&pause_gate.mutex);
 CHECK(!pthread_mutex_unlock(&pause_gate.mutex));
}
static void gate_wait(unsigned int count)
{
 CHECK(!pthread_mutex_lock(&pause_gate.mutex));
 while(pause_gate.reached<count)wait_changed(&pause_gate.changed,&pause_gate.mutex);
 CHECK(!pthread_mutex_unlock(&pause_gate.mutex));
}
static void gate_release(void)
{
 CHECK(!pthread_mutex_lock(&pause_gate.mutex));pause_gate.released=true;
 CHECK(!pthread_cond_broadcast(&pause_gate.changed));
 CHECK(!pthread_mutex_unlock(&pause_gate.mutex));
}

enum pause_mode { NONE, REF_BEFORE, CLAIM_AFTER, DEC_BEFORE, RETIRE_OWNER_READ, OBSERVER_KEY_READ, OBSERVER_OWNER_READ };
static _Thread_local enum pause_mode pause_mode;
static _Thread_local unsigned int rmw_calls;
static struct kd_mutex_aux *pause_aux;
static void read_watch(const volatile void *address)
{
 if(pause_aux &&
    (((pause_mode==RETIRE_OWNER_READ || pause_mode==OBSERVER_OWNER_READ) && address==&pause_aux->physical_owner) ||
     (pause_mode==OBSERVER_KEY_READ && address==&pause_aux->lock))) {
  pause_mode=NONE;gate_reach();
 }
}
#define READ_ONCE(v) ({ __typeof__(v) value=__atomic_load_n(&(v),__ATOMIC_RELAXED); read_watch(&(v)); value; })
#define WRITE_ONCE(v,n) __atomic_store_n(&(v),(n),__ATOMIC_RELAXED)
#define smp_load_acquire(p) ({ __typeof__(*(p)) value=__atomic_load_n((p),__ATOMIC_ACQUIRE); read_watch(p); value; })
#define smp_store_release(p,v) __atomic_store_n((p),(v),__ATOMIC_RELEASE)
#define smp_rmb() __atomic_thread_fence(__ATOMIC_ACQUIRE)
#define smp_wmb() __atomic_thread_fence(__ATOMIC_RELEASE)
#define atomic_set(p,v) __atomic_store_n(&(p)->counter,(v),__ATOMIC_RELAXED)
#define atomic_set_release(p,v) __atomic_store_n(&(p)->counter,(v),__ATOMIC_RELEASE)
#define atomic_read(p) __atomic_load_n(&(p)->counter,__ATOMIC_RELAXED)
#define atomic_read_acquire(p) __atomic_load_n(&(p)->counter,__ATOMIC_ACQUIRE)
static bool atomic_try_cmpxchg(atomic_t *value,int *old,int next)
{
 rmw_calls++;
 if(pause_aux && value==&pause_aux->refs && pause_mode==REF_BEFORE && *old>0 && next==*old+1) {
  pause_mode=NONE;gate_reach();
 }
 int expected=*old;
 bool changed=__atomic_compare_exchange_n(&value->counter,old,next,false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST);
 if(changed && expected==-1 && next==0 && pause_mode==CLAIM_AFTER) {
  pause_mode=NONE;gate_reach();
 }
 return changed;
}
#define atomic_try_cmpxchg_acquire atomic_try_cmpxchg
static inline int atomic_cmpxchg(atomic_t *value,int old,int next)
{ (void)atomic_try_cmpxchg(value,&old,next);return old; }
#define atomic_cmpxchg_acquire atomic_cmpxchg
static int atomic_dec_return(atomic_t *value)
{
 rmw_calls++;
 if(pause_aux && value==&pause_aux->refs && pause_mode==DEC_BEFORE) {
  pause_mode=NONE;gate_reach();
 }
 return __atomic_sub_fetch(&value->counter,1,__ATOMIC_SEQ_CST);
}
#define cmpxchg(p,o,n) ({ __typeof__(*(p)) old=(o); rmw_calls++; __atomic_compare_exchange_n((p),&old,(n),false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST); old; })
#define __read_mostly
#define L1_CACHE_BYTES 64
#define U64_MAX UINT64_MAX
#define BUILD_BUG_ON(c) _Static_assert(!(c), "production layout")
#define BUG_ON(c) CHECK(!(c))
#define likely(v) (v)
#define unlikely(v) (v)
#define hash_ptr(p,b) ((unsigned long)(((uint64_t)(uintptr_t)(p)*UINT64_C(0x61c8864680b583eb))>>(64-(b))))
#define module_param_named(...)
#define EXPORT_SYMBOL_GPL(...)
#define KD_MUTEX_STAT(name) static u64 name
#define KD_MUTEX_STAT_READ(name) __atomic_load_n(&(name),__ATOMIC_RELAXED)
#define this_cpu_inc(name) __atomic_add_fetch(&(name),1,__ATOMIC_RELAXED)
#define pr_info(...) do {} while (0)
static bool allocation_failure;
static unsigned int allocations,frees;
static void *allocated_table;
static size_t allocated_bytes;
static void *vzalloc(size_t bytes)
{
 if(allocation_failure)return NULL;
 CHECK(!allocated_table && bytes && !(bytes%4096));
 allocated_table=aligned_alloc(4096,bytes);CHECK(allocated_table);
 memset(allocated_table,0,bytes);allocated_bytes=bytes;allocations++;
 return allocated_table;
}
static void vfree(void *pointer)
{
 CHECK(pointer && pointer==allocated_table);
 struct kd_mutex_aux *table=pointer;
 for(size_t i=0;i<allocated_bytes/sizeof(*table);i++)CHECK(atomic_read(&table[i].refs)==-1);
 free(pointer);allocated_table=NULL;allocated_bytes=0;frees++;
}
#include "aux_production.h"

/* More possible keys than slots: address reuse must not impose a lifetime cap
 * on the number of mutex objects. Real objects also give deterministic hash
 * collisions without dereferencing fabricated addresses. */
#define OBJECTS 131072
#define WORKERS 8
static struct kd_mutex locks[OBJECTS];
static struct kd_mutex *key_a,*key_b;
static struct task_struct owner={1},other={2};
static void drained(void)
{ CHECK(kd_mutex_aux_all_idle() && !kd_mutex_debug_aux_count()); }
static void find_collision(void)
{
 int *first=malloc((1U<<KD_MUTEX_AUX_BITS)*sizeof(*first));CHECK(first);
 for(unsigned int i=0;i<(1U<<KD_MUTEX_AUX_BITS);i++)first[i]=-1;
 for(unsigned int i=0;i<OBJECTS;i++) {
  unsigned int bucket=hash_ptr(&locks[i],KD_MUTEX_AUX_BITS);
  if(first[bucket]>=0) { key_a=&locks[first[bucket]];key_b=&locks[i];break; }
  first[bucket]=(int)i;
 }
 free(first);CHECK(key_a && key_b && key_a!=key_b);
 CHECK(hash_ptr(key_a,KD_MUTEX_AUX_BITS)==hash_ptr(key_b,KD_MUTEX_AUX_BITS));
}
static void check_lifetime(void)
{
 CHECK(!kd_mutex_aux_get(NULL) && !kd_mutex_aux_lookup(NULL) && !kd_mutex_aux_borrow_owned(NULL));
 CHECK(kd_mutex_aux_waiter_count(NULL)==-EINVAL);
 CHECK(kd_mutex_aux_is_idle(key_a) && !kd_mutex_aux_lookup(key_a));
 CHECK(!kd_mutex_combiner_active(key_a) && !kd_mutex_delegation_owned(key_a,&owner));
 CHECK(!kd_mutex_aux_waiter_count(key_a));
 struct kd_mutex_aux *invocation=kd_mutex_aux_get(key_a);
 CHECK(invocation && atomic_read(&invocation->refs)==1 && !kd_mutex_aux_is_idle(key_a));
 CHECK(!kd_mutex_aux_all_idle() && kd_mutex_debug_aux_count()==1);
 CHECK(!atomic_read(&invocation->state) && !invocation->tail && !atomic_read(&invocation->waiter_count));
 kd_mutex_aux_ref(invocation); /* Exact gate owner, separate from invocation. */
 WRITE_ONCE(invocation->physical_owner,&owner);WRITE_ONCE(invocation->locked,KD_MUTEX_GATE_COMBINER);
 WRITE_ONCE(invocation->tail,17);atomic_set(&invocation->waiter_count,2);
 unsigned int before=rmw_calls;
 CHECK(kd_mutex_delegation_owned(key_a,&owner) && !kd_mutex_delegation_owned(key_a,&other));
 CHECK(kd_mutex_combiner_active(key_a) && kd_mutex_aux_waiter_count(key_a)==2);
 CHECK(!kd_mutex_delegation_owned(key_b,&owner) && !kd_mutex_combiner_active(key_b));
 CHECK(rmw_calls==before); /* The hot ownership/hint observations remain read-only. */
 CHECK(!kd_mutex_aux_get(key_b) && !kd_mutex_aux_lookup(key_b));
 before=rmw_calls;
 struct kd_mutex_aux *unlock=kd_mutex_aux_borrow_owned(key_a);
 CHECK(unlock==invocation && atomic_read(&invocation->refs)==2 && rmw_calls==before);
 WRITE_ONCE(invocation->physical_owner,NULL);atomic_set(&invocation->state,0);
 WRITE_ONCE(invocation->tail,0);atomic_set(&invocation->waiter_count,0);
 kd_mutex_aux_put(unlock);
 CHECK(atomic_read(&invocation->refs)==1 && !kd_mutex_aux_is_idle(key_a));
 CHECK(!kd_mutex_aux_all_idle()); /* Pending frame/ACK outlives empty queue. */
 CHECK(!kd_mutex_aux_get(key_b)); /* That exact invocation still reserves the key. */
 struct kd_mutex_aux *next=kd_mutex_aux_get(key_a);
 CHECK(next==invocation && atomic_read(&next->refs)==2);
 kd_mutex_aux_ref(next); /* Next owner enters before the old frame retires. */
 kd_mutex_aux_put(invocation);kd_mutex_aux_put(next);
 CHECK(atomic_read(&next->refs)==1 && !kd_mutex_aux_all_idle());
 kd_mutex_aux_put(next);drained();
 CHECK(kd_mutex_aux_is_idle(key_a) && !kd_mutex_aux_lookup(key_a));
 for(unsigned int i=0;i<1000;i++) {
  next=kd_mutex_aux_get((i&1)?key_b:key_a);CHECK(next==invocation);
  CHECK(!next->physical_owner && !atomic_read(&next->state) && !next->tail && !atomic_read(&next->waiter_count));
  kd_mutex_aux_put(next);
 }
 drained();CHECK(allocations==1 && !frees);
}

static void check_borrowed_owner(void)
{
 CHECK(!kd_mutex_aux_borrow_owned(key_a));
 struct kd_mutex_aux *aux=kd_mutex_aux_get(key_a);CHECK(aux);
 /* The pre-node acquisition transfers its one invocation reference to OWNER. */
 WRITE_ONCE(aux->locked,1);WRITE_ONCE(aux->physical_owner,&owner);
 unsigned int before=rmw_calls;
 CHECK(kd_mutex_aux_borrow_owned(key_a)==aux);
 CHECK(!kd_mutex_aux_borrow_owned(key_b));
 current=&other;CHECK(!kd_mutex_aux_borrow_owned(key_a));current=&owner;
 CHECK(atomic_read(&aux->refs)==1 && rmw_calls==before);
 /* Clearing the identity ends borrowing, but the retained OWNER reference
  * still excludes collision reuse through physical/gate release. */
 WRITE_ONCE(aux->physical_owner,NULL);
 CHECK(!kd_mutex_aux_borrow_owned(key_a) && atomic_read(&aux->refs)==1);
 CHECK(rmw_calls==before && !kd_mutex_aux_get(key_b));
 atomic_set(&aux->state,0);kd_mutex_aux_put(aux);drained();
 struct kd_mutex_aux *replacement=kd_mutex_aux_get(key_b);CHECK(replacement==aux);
 CHECK(!kd_mutex_aux_borrow_owned(key_a) && !kd_mutex_aux_borrow_owned(key_b));
 kd_mutex_aux_put(replacement);drained();
}

static struct kd_mutex_aux *race_aux,*race_result;
static struct kd_mutex *race_key;
static enum pause_mode thread_mode;
static bool observed,borrow_observer;
static void *held_lookup(void *unused)
{ (void)unused;pause_mode=REF_BEFORE;race_result=kd_mutex_aux_lookup(race_key);return NULL; }
static void *held_put(void *unused)
{ (void)unused;pause_mode=thread_mode;kd_mutex_aux_put(race_aux);return NULL; }
static void *held_claim(void *unused)
{ (void)unused;pause_mode=CLAIM_AFTER;race_result=kd_mutex_aux_get(race_key);return NULL; }
static void *held_observer(void *unused)
{
 (void)unused;pause_mode=thread_mode;current=&owner;
 unsigned int before=rmw_calls;
 observed=borrow_observer ? kd_mutex_aux_borrow_owned(race_key)!=NULL :
                           kd_mutex_delegation_owned(race_key,&owner);
 CHECK(rmw_calls==before);return NULL;
}
static void check_lookup_reuse(bool same_key)
{
 pthread_t reader;
 race_aux=kd_mutex_aux_get(key_a);CHECK(race_aux);pause_aux=race_aux;
 u64 sequence=READ_ONCE(race_aux->sequence);
 race_key=key_a;race_result=NULL;gate_reset();
 CHECK(!pthread_create(&reader,NULL,held_lookup,NULL));gate_wait(1);
 CHECK(atomic_read(&race_aux->refs)==1);kd_mutex_aux_put(race_aux);drained();
 struct kd_mutex_aux *replacement=kd_mutex_aux_get(same_key?key_a:key_b);
 CHECK(replacement==race_aux && READ_ONCE(replacement->sequence)>sequence);
 CHECK(atomic_read(&replacement->refs)==1);gate_release();CHECK(!pthread_join(reader,NULL));
 if(same_key) {
  CHECK(race_result==replacement && race_result->lock==key_a);
  CHECK(atomic_read(&replacement->refs)==2);kd_mutex_aux_put(race_result);
 } else CHECK(!race_result && replacement->lock==key_b);
 CHECK(atomic_read(&replacement->refs)==1);pause_aux=NULL;kd_mutex_aux_put(replacement);drained();
}
static void check_lookup_wins_put(void)
{
 pthread_t thread;race_aux=kd_mutex_aux_get(key_a);CHECK(race_aux);pause_aux=race_aux;
 thread_mode=DEC_BEFORE;gate_reset();
 CHECK(!pthread_create(&thread,NULL,held_put,NULL));gate_wait(1);
 struct kd_mutex_aux *lookup=kd_mutex_aux_lookup(key_a);
 CHECK(lookup==race_aux && atomic_read(&lookup->refs)==2);
 gate_release();CHECK(!pthread_join(thread,NULL));
 CHECK(atomic_read(&lookup->refs)==1 && kd_mutex_debug_aux_count()==1);
 pause_aux=NULL;kd_mutex_aux_put(lookup);drained();
}
static void check_two_puts(void)
{
 pthread_t threads[2];race_aux=kd_mutex_aux_get(key_a);CHECK(race_aux);kd_mutex_aux_ref(race_aux);
 pause_aux=race_aux;thread_mode=DEC_BEFORE;gate_reset();
 for(unsigned int i=0;i<2;i++)CHECK(!pthread_create(&threads[i],NULL,held_put,NULL));
 gate_wait(2);CHECK(atomic_read(&race_aux->refs)==2);gate_release();
 for(unsigned int i=0;i<2;i++)CHECK(!pthread_join(threads[i],NULL));
 pause_aux=NULL;drained();
}
static void check_busy_lifetimes(void)
{
 pthread_t thread;
 /* Interrupt a creator after claiming BUSY, before initializing its key. */
 race_key=key_a;race_result=NULL;gate_reset();
 CHECK(!pthread_create(&thread,NULL,held_claim,NULL));gate_wait(1);
 CHECK(!kd_mutex_aux_get(key_a) && !kd_mutex_aux_get(key_b));
 CHECK(!kd_mutex_aux_lookup(key_a) && !kd_mutex_aux_all_idle());
 gate_release();CHECK(!pthread_join(thread,NULL));CHECK(race_result);
 race_aux=race_result;pause_aux=race_aux;thread_mode=RETIRE_OWNER_READ;gate_reset();
 CHECK(!pthread_create(&thread,NULL,held_put,NULL));gate_wait(1);
 /* Final reference has left LIVE, but retirement has not finished. Publishing
  * FREE here would let another key overwrite the retiring generation. */
 CHECK(!kd_mutex_aux_get(key_b) && !kd_mutex_aux_get(key_a));
 CHECK(!kd_mutex_aux_lookup(key_a) && !kd_mutex_aux_all_idle());
 gate_release();CHECK(!pthread_join(thread,NULL));pause_aux=NULL;drained();
}
static void check_observer_reuse(void)
{
 pthread_t thread;race_aux=kd_mutex_aux_get(key_a);CHECK(race_aux);pause_aux=race_aux;
 race_key=key_a;observed=true;thread_mode=OBSERVER_KEY_READ;gate_reset();
 CHECK(!pthread_create(&thread,NULL,held_observer,NULL));gate_wait(1);
 /* Reader already copied A's key; B now supplies the queried owner. Only
  * sequence validation can reject this cross-generation combination. */
 kd_mutex_aux_put(race_aux);
 struct kd_mutex_aux *replacement=kd_mutex_aux_get(key_b);CHECK(replacement==race_aux);
 kd_mutex_aux_ref(replacement);
 WRITE_ONCE(replacement->locked,1);WRITE_ONCE(replacement->physical_owner,&owner);
 gate_release();CHECK(!pthread_join(thread,NULL));CHECK(!observed);
 CHECK(kd_mutex_delegation_owned(key_b,&owner));
 WRITE_ONCE(replacement->physical_owner,NULL);atomic_set(&replacement->state,0);
 pause_aux=NULL;kd_mutex_aux_put(replacement);kd_mutex_aux_put(replacement);drained();
}


static void check_observer_aba(void)
{
 pthread_t thread;race_aux=kd_mutex_aux_get(key_a);CHECK(race_aux);pause_aux=race_aux;
 kd_mutex_aux_ref(race_aux);WRITE_ONCE(race_aux->locked,1);
 WRITE_ONCE(race_aux->physical_owner,&owner);
 race_key=key_a;observed=true;thread_mode=OBSERVER_OWNER_READ;gate_reset();
 CHECK(!pthread_create(&thread,NULL,held_observer,NULL));gate_wait(1);
 /* Reader copied A's true owner before A -> B -> A reuse. Rechecking only
  * the address would accept that obsolete owner for the new A generation. */
 WRITE_ONCE(race_aux->physical_owner,NULL);atomic_set(&race_aux->state,0);
 kd_mutex_aux_put(race_aux);kd_mutex_aux_put(race_aux);
 struct kd_mutex_aux *replacement=kd_mutex_aux_get(key_b);CHECK(replacement==race_aux);
 kd_mutex_aux_put(replacement);
 replacement=kd_mutex_aux_get(key_a);CHECK(replacement==race_aux);
 kd_mutex_aux_ref(replacement);WRITE_ONCE(replacement->locked,1);
 WRITE_ONCE(replacement->physical_owner,&other);
 gate_release();CHECK(!pthread_join(thread,NULL));CHECK(!observed);
 CHECK(kd_mutex_delegation_owned(key_a,&other) && !kd_mutex_delegation_owned(key_a,&owner));
 WRITE_ONCE(replacement->physical_owner,NULL);atomic_set(&replacement->state,0);
 pause_aux=NULL;kd_mutex_aux_put(replacement);kd_mutex_aux_put(replacement);drained();
}

static pthread_barrier_t start_barrier,acquired_barrier,release_barrier;
static struct kd_mutex_aux *results[WORKERS];
static void *duplicate_creator(void *arg)
{
 unsigned int id=(uintptr_t)arg;
 pthread_barrier_wait(&start_barrier);results[id]=kd_mutex_aux_get(key_a);
 pthread_barrier_wait(&acquired_barrier);pthread_barrier_wait(&release_barrier);
 if(results[id])kd_mutex_aux_put(results[id]);
 return NULL;
}
static void check_duplicate_publication(void)
{
 pthread_t threads[WORKERS];
 CHECK(!pthread_barrier_init(&start_barrier,NULL,WORKERS));
 CHECK(!pthread_barrier_init(&acquired_barrier,NULL,WORKERS+1));
 CHECK(!pthread_barrier_init(&release_barrier,NULL,WORKERS+1));
 for(uintptr_t i=0;i<WORKERS;i++)CHECK(!pthread_create(&threads[i],NULL,duplicate_creator,(void *)i));
 pthread_barrier_wait(&acquired_barrier);
 unsigned int live=0;struct kd_mutex_aux *unique=NULL;
 for(unsigned int i=0;i<WORKERS;i++)if(results[i]) {
  if(!unique)unique=results[i];
  CHECK(results[i]==unique && results[i]->lock==key_a);live++;
 }
 CHECK(live && atomic_read(&unique->refs)==(int)live && kd_mutex_debug_aux_count()==1);
 pthread_barrier_wait(&release_barrier);
 for(unsigned int i=0;i<WORKERS;i++)CHECK(!pthread_join(threads[i],NULL));
 CHECK(!pthread_barrier_destroy(&start_barrier));CHECK(!pthread_barrier_destroy(&acquired_barrier));
 CHECK(!pthread_barrier_destroy(&release_barrier));drained();
}
static unsigned int accepted,refused;
static void *lookup_stress(void *arg)
{
 unsigned int id=(uintptr_t)arg;
 for(unsigned int i=0;i<4000;i++) {
  struct kd_mutex *lock=(i%4==0)?key_a:(i%4==1)?key_b:&locks[(i+id)%128];
  struct kd_mutex_aux *aux=kd_mutex_aux_get(lock);
  if(!aux) { __atomic_add_fetch(&refused,1,__ATOMIC_RELAXED);continue; }
  __atomic_add_fetch(&accepted,1,__ATOMIC_RELAXED);CHECK(aux->lock==lock);
  u64 sequence=READ_ONCE(aux->sequence);CHECK(!(sequence&1));
  kd_mutex_aux_ref(aux);
  struct kd_mutex_aux *lookup=kd_mutex_aux_lookup(lock);CHECK(lookup==aux);
  CHECK(READ_ONCE(aux->sequence)==sequence);
  kd_mutex_aux_put(lookup);kd_mutex_aux_put(aux);kd_mutex_aux_put(aux);
 }
 return NULL;
}
static void check_stress(void)
{
 pthread_t threads[WORKERS];
 for(uintptr_t i=0;i<WORKERS;i++)CHECK(!pthread_create(&threads[i],NULL,lookup_stress,(void *)i));
 for(unsigned int i=0;i<WORKERS;i++)CHECK(!pthread_join(threads[i],NULL));
 CHECK(accepted && accepted+refused==WORKERS*4000);drained();
}
static void check_capacity_and_reuse(void)
{
 struct kd_mutex *objects[2048];struct kd_mutex_aux *many[2048];
 unsigned int n=0,live=0,collisions=0;
 objects[n++]=key_a;objects[n++]=key_b;
 for(unsigned int i=0;n<2048;i++)if(&locks[i]!=key_a && &locks[i]!=key_b)objects[n++]=&locks[i];
 for(unsigned int i=0;i<2048;i++) {
  many[i]=kd_mutex_aux_get(objects[i]);
  if(many[i]) { CHECK(many[i]->lock==objects[i]);live++; }
  else { CHECK(!kd_mutex_aux_lookup(objects[i]));collisions++; }
 }
 CHECK(live && collisions && live+collisions==2048 && kd_mutex_debug_aux_count()==live);
 for(unsigned int i=0;i<2048;i++)if(many[i])kd_mutex_aux_put(many[i]);
 drained();
 /* More distinct lifetime keys than slots, each with an otherwise empty table. */
 for(unsigned int i=0;i<OBJECTS;i++) {
  struct kd_mutex_aux *aux=kd_mutex_aux_get(&locks[i]);CHECK(aux && aux->lock==&locks[i]);
  kd_mutex_aux_put(aux);
 }
 CHECK(allocations==1 && !frees);drained();
}
static void check_refusal(void)
{
 kd_mutex_aux_fail_once=1;CHECK(!kd_mutex_aux_get(key_a));
 CHECK(!kd_mutex_aux_fail_once);drained();
 allocation_failure=true; /* Admission and retirement never allocate storage. */
 struct kd_mutex_aux *live=kd_mutex_aux_get(key_a);CHECK(live);
 kd_mutex_aux_fail_once=1;
 CHECK(kd_mutex_aux_get(key_a)==live && atomic_read(&live->refs)==2);
 CHECK(kd_mutex_aux_fail_once==1);
 kd_mutex_aux_put(live);kd_mutex_aux_put(live);
 allocation_failure=false;kd_mutex_aux_fail_once=0;drained();
}
static void check_sequence_saturation(void)
{
 struct kd_mutex_aux *aux=kd_mutex_aux_get(key_a);CHECK(aux);kd_mutex_aux_put(aux);
 WRITE_ONCE(aux->sequence,U64_MAX-3);
 CHECK(kd_mutex_aux_get(key_a)==aux && READ_ONCE(aux->sequence)==U64_MAX-1);
 kd_mutex_aux_put(aux);
 CHECK(!kd_mutex_aux_get(key_a) && READ_ONCE(aux->sequence)==U64_MAX);
 CHECK(!kd_mutex_aux_get(key_b) && READ_ONCE(aux->sequence)==U64_MAX);
 CHECK(atomic_read(&aux->refs)==-1 && kd_mutex_aux_is_idle(key_a));
 CHECK(!kd_mutex_combiner_active(key_a) && !kd_mutex_delegation_owned(key_a,&owner));drained();
}
int main(void)
{
 current=&owner;
 CHECK(sizeof(struct kd_mutex)==32 && _Alignof(struct kd_mutex)==8);
 struct layout { char prefix; struct kd_mutex lock; char suffix; };
 CHECK(offsetof(struct layout,lock)==8 && offsetof(struct layout,suffix)==40);
 allocation_failure=true;CHECK(kd_mutex_aux_init()==-ENOMEM && kd_mutex_aux_all_idle());
 allocation_failure=false;CHECK(!kd_mutex_aux_init());CHECK(allocations==1 && !frees);
 find_collision();check_lifetime();check_borrowed_owner();check_lookup_reuse(false);check_lookup_reuse(true);
 check_lookup_wins_put();check_two_puts();check_busy_lifetimes();
 for(unsigned int kind=0;kind<2;kind++) {
  borrow_observer=kind;check_observer_reuse();check_observer_aba();
 }
 check_refusal();check_capacity_and_reuse();check_duplicate_publication();check_stress();
 check_sequence_saturation();kd_mutex_aux_exit();CHECK(!allocated_table && allocations==frees);
 puts("PASS aux fixed slots: 32-byte/8-byte layout, exact owner/frame/ACK references, current-only borrowed owner with no reference RMW, key-validated lookup across reuse, read-only sequence observations and A-to-B-to-A reuse, busy claim/retirement refusal, racing puts, collision fallback, 2048 objects, lifetime keys beyond capacity, 8 creators and 8x4000 operations, init failure, sequence exhaustion, idle exit");
 return 0;
}
