/* SPDX-License-Identifier: GPL-2.0 */
/* Compile the real registry unchanged. Pthreads race its atomic references and
 * RCU lists. This conservative RCU substitute waits for all readers, including
 * readers arriving after call_rcu; it never holds a reader lock across lookup
 * or prevents writers from unlinking/publishing another record. Kernel RCU,
 * slab allocation and physical locking remain live-test responsibilities. */
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
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
typedef struct { int counter; } atomic_t;
typedef unsigned long atomic_long_t;
typedef unsigned int raw_spinlock_t;
struct task_struct { unsigned long identity; };
struct optimistic_spin_queue { atomic_t tail; };
struct list_head { struct list_head *next, *prev; };
struct hlist_node { struct hlist_node *next, **pprev; };
struct hlist_head { struct hlist_node *first; };
struct rcu_head { struct rcu_head *next; void (*fn)(struct rcu_head *); };
#include "aux_types.h"
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define READ_ONCE(v) __atomic_load_n(&(v),__ATOMIC_RELAXED)
#define atomic_set(p,v) __atomic_store_n(&(p)->counter,(v),__ATOMIC_RELAXED)
#define atomic_read(p) __atomic_load_n(&(p)->counter,__ATOMIC_RELAXED)
#define hlist_for_each_entry(e,h,m) \
 for (struct hlist_node *n=__atomic_load_n(&(h)->first,__ATOMIC_ACQUIRE); \
      n && ((e)=container_of(n,__typeof__(*(e)),m),1); \
      n=__atomic_load_n(&n->next,__ATOMIC_ACQUIRE))
static struct hlist_head *rcu_head_checked(struct hlist_head *head);
#define hlist_for_each_entry_rcu(e,h,m) hlist_for_each_entry(e,rcu_head_checked(h),m)
static void hlist_add_head_rcu(struct hlist_node *n, struct hlist_head *h)
{
 n->next=h->first;n->pprev=&h->first;
 if(n->next)n->next->pprev=&n->next;
 __atomic_store_n(&h->first,n,__ATOMIC_RELEASE);
}
static void hlist_del_rcu(struct hlist_node *n)
{
 __atomic_store_n(n->pprev,n->next,__ATOMIC_RELEASE);
 if(n->next)n->next->pprev=n->pprev;
 /* An already-positioned RCU reader can still follow n->next. */
}
static bool hlist_empty(const struct hlist_head *h)
{ return !__atomic_load_n(&h->first,__ATOMIC_ACQUIRE); }

static void wait_changed(pthread_cond_t *condition, pthread_mutex_t *mutex)
{
 struct timespec deadline;
 CHECK(!clock_gettime(CLOCK_REALTIME,&deadline));deadline.tv_sec+=5;
 CHECK(!pthread_cond_timedwait(condition,mutex,&deadline));
}
struct pause_gate {
 pthread_mutex_t mutex;pthread_cond_t changed;
 unsigned int reached;bool released;
};
#define PAUSE_GATE { PTHREAD_MUTEX_INITIALIZER, PTHREAD_COND_INITIALIZER, 0, false }
static struct pause_gate cas_gate=PAUSE_GATE,put_gate=PAUSE_GATE;
static void gate_reset(struct pause_gate *gate)
{ CHECK(!pthread_mutex_lock(&gate->mutex));gate->reached=0;gate->released=false;CHECK(!pthread_mutex_unlock(&gate->mutex)); }
static void gate_reach(struct pause_gate *gate,bool wait)
{
 CHECK(!pthread_mutex_lock(&gate->mutex));gate->reached++;
 CHECK(!pthread_cond_broadcast(&gate->changed));
 while(wait && !gate->released)wait_changed(&gate->changed,&gate->mutex);
 CHECK(!pthread_mutex_unlock(&gate->mutex));
}
static void gate_wait(struct pause_gate *gate,unsigned int count)
{
 CHECK(!pthread_mutex_lock(&gate->mutex));
 while(gate->reached<count)wait_changed(&gate->changed,&gate->mutex);
 CHECK(!pthread_mutex_unlock(&gate->mutex));
}
static void gate_release(struct pause_gate *gate)
{
 CHECK(!pthread_mutex_lock(&gate->mutex));gate->released=true;
 CHECK(!pthread_cond_broadcast(&gate->changed));CHECK(!pthread_mutex_unlock(&gate->mutex));
}

static pthread_mutex_t rcu_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t rcu_changed=PTHREAD_COND_INITIALIZER;
static unsigned int rcu_readers,rcu_pending,barrier_waits,barrier_calls;
static struct rcu_head *rcu_callbacks;
static _Thread_local unsigned int rcu_depth,callback_depth,held;
static struct hlist_head *rcu_head_checked(struct hlist_head *head)
{ CHECK(rcu_depth);return head; }
static void rcu_read_lock(void)
{
 CHECK(!pthread_mutex_lock(&rcu_mutex));rcu_readers++;rcu_depth++;
 CHECK(!pthread_mutex_unlock(&rcu_mutex));
}
static void rcu_read_unlock(void)
{
 CHECK(!pthread_mutex_lock(&rcu_mutex));CHECK(rcu_depth && rcu_readers);
 rcu_depth--;rcu_readers--;CHECK(!pthread_cond_broadcast(&rcu_changed));
 CHECK(!pthread_mutex_unlock(&rcu_mutex));
}
static void call_rcu(struct rcu_head *head,void (*fn)(struct rcu_head *))
{
 CHECK(!held && fn);CHECK(!pthread_mutex_lock(&rcu_mutex));
 head->next=rcu_callbacks;head->fn=fn;rcu_callbacks=head;rcu_pending++;
 CHECK(!pthread_mutex_unlock(&rcu_mutex));
}
static unsigned int pending_callbacks(void)
{
 unsigned int result;CHECK(!pthread_mutex_lock(&rcu_mutex));result=rcu_pending;
 CHECK(!pthread_mutex_unlock(&rcu_mutex));return result;
}
static void rcu_barrier(void)
{
 CHECK(!held && !rcu_depth);CHECK(!pthread_mutex_lock(&rcu_mutex));barrier_calls++;
 while(rcu_readers) {
  barrier_waits++;CHECK(!pthread_cond_broadcast(&rcu_changed));
  wait_changed(&rcu_changed,&rcu_mutex);
 }
 struct rcu_head *callbacks=rcu_callbacks;rcu_callbacks=NULL;rcu_pending=0;
 CHECK(!pthread_mutex_unlock(&rcu_mutex));
 while(callbacks) {
  struct rcu_head *head=callbacks;callbacks=head->next;
  callback_depth++;head->fn(head);callback_depth--;
 }
}
static void wait_for_barrier(unsigned int before)
{
 CHECK(!pthread_mutex_lock(&rcu_mutex));
 while(barrier_waits==before)wait_changed(&rcu_changed,&rcu_mutex);
 CHECK(!pthread_mutex_unlock(&rcu_mutex));
}

static _Thread_local unsigned int cas_pause;
static _Thread_local bool announce_put;
static atomic_t *cas_target;
static bool atomic_try_cmpxchg(atomic_t *value,int *old,int next)
{
 if(value==cas_target && ((cas_pause==1 && next==*old+1) ||
                          (cas_pause==2 && *old==2 && next==1))) {
  if(cas_pause==1)CHECK(rcu_depth); /* Hold the actual lookup's read section. */
  cas_pause=0;gate_reach(&cas_gate,true);
 }
 return __atomic_compare_exchange_n(&value->counter,old,next,false,
                                     __ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST);
}
static bool atomic_dec_and_test(atomic_t *value)
{ return __atomic_sub_fetch(&value->counter,1,__ATOMIC_SEQ_CST)==0; }
static unsigned long _raw_spin_lock_irqsave(raw_spinlock_t *lock)
{
 if(announce_put) { announce_put=false;gate_reach(&put_gate,false); }
 while(__atomic_exchange_n(lock,1,__ATOMIC_ACQUIRE))sched_yield();
 CHECK(!held);held++;return 0;
}
static void _raw_spin_unlock_irqrestore(raw_spinlock_t *lock,unsigned long flags)
{ CHECK(held==1 && !flags);held--;__atomic_store_n(lock,0,__ATOMIC_RELEASE); }
#define __RAW_SPIN_LOCK_UNLOCKED(n) 0
#define ____cacheline_aligned_in_smp
#define __read_mostly
#define L1_CACHE_BYTES 64
#define BUILD_BUG_ON(c) _Static_assert(!(c), "production layout")
#define BUG_ON(c) CHECK(!(c))
#define unlikely(v) (v)
#define hash_ptr(p,b) (((uintptr_t)(p)>>3)&((1U<<(b))-1))
#define cmpxchg(p,o,n) ({ __typeof__(*(p)) old=(o); __atomic_compare_exchange_n((p),&old,(n),false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST); old; })
#define module_param_named(...)
#define EXPORT_SYMBOL_GPL(...)
#define GFP_ATOMIC 0
struct kmem_cache { size_t size,alignment; };
static bool cache_failure;
static unsigned int allocations,frees,allocation_failures;
static pthread_barrier_t *allocation_barrier;
static struct kmem_cache *kmem_cache_create(const char *name,size_t size,size_t alignment,unsigned long flags,void *ctor)
{
 CHECK(!held && !strcmp(name,"kd_mutex_aux") && !flags && !ctor);
 if(cache_failure)return NULL;
 struct kmem_cache *cache=malloc(sizeof(*cache));CHECK(cache);
 cache->size=size;cache->alignment=alignment;return cache;
}
static void *kmem_cache_alloc(struct kmem_cache *cache,int flags)
{
 CHECK(!held && cache && flags==GFP_ATOMIC);
 if(allocation_barrier)pthread_barrier_wait(allocation_barrier);
 if(READ_ONCE(allocation_failures))return NULL;
 void *p=aligned_alloc(cache->alignment,cache->size);CHECK(p);
 memset(p,0xa5,cache->size);
 __atomic_add_fetch(&allocations,1,__ATOMIC_RELAXED);return p;
}
static void kmem_cache_free(struct kmem_cache *cache,void *p)
{
 CHECK(!held && cache && p);
 /* Unpublished losing candidates have refs=1 and may free immediately.
  * A zero-ref allocation must arrive through a grace-period callback. */
 if(!atomic_read(&((struct kd_mutex_aux *)p)->refs))CHECK(callback_depth);
 memset(p,0xdd,cache->size);free(p);
 __atomic_add_fetch(&frees,1,__ATOMIC_RELAXED);
}
static void kmem_cache_destroy(struct kmem_cache *cache)
{ CHECK(!held && !pending_callbacks() && allocations==frees);free(cache); }
#include "aux_production.h"

static struct kd_mutex locks[2048];
static struct task_struct owner={1},other={2};
static void drained_callbacks(void)
{ rcu_barrier();CHECK(kd_mutex_aux_all_idle() && !pending_callbacks() && allocations==frees); }
static void check_lifetime(void)
{
 struct kd_mutex *lock=&locks[0];
 CHECK(!kd_mutex_aux_get(NULL) && !kd_mutex_aux_lookup(NULL));
 CHECK(kd_mutex_aux_waiter_count(NULL)==-EINVAL);
 CHECK(kd_mutex_aux_is_idle(lock) && !kd_mutex_aux_lookup(lock));
 CHECK(!kd_mutex_combiner_active(lock) && !kd_mutex_delegation_owned(lock,&owner));
 CHECK(!kd_mutex_aux_waiter_count(lock) && !allocations);
 struct kd_mutex_aux *invocation=kd_mutex_aux_get(lock);
 CHECK(invocation && atomic_read(&invocation->refs)==1 && !kd_mutex_aux_is_idle(lock));
 CHECK(!kd_mutex_aux_all_idle() && kd_mutex_debug_aux_count()==1);
 CHECK(!invocation->state.counter && !invocation->tail && !invocation->waiter_count.counter);
 kd_mutex_aux_ref(invocation); /* Exact gate owner, separate from invocation. */
 invocation->physical_owner=&owner;invocation->locked=KD_MUTEX_GATE_COMBINER;
 invocation->tail=17;atomic_set(&invocation->waiter_count,2);
 CHECK(kd_mutex_delegation_owned(lock,&owner) && !kd_mutex_delegation_owned(lock,&other));
 CHECK(kd_mutex_combiner_active(lock) && kd_mutex_aux_waiter_count(lock)==2);
 struct kd_mutex_aux *unlock=kd_mutex_aux_lookup(lock);
 CHECK(unlock==invocation && atomic_read(&invocation->refs)==3);
 invocation->physical_owner=NULL;atomic_set(&invocation->state,0);
 invocation->tail=0;atomic_set(&invocation->waiter_count,0);
 kd_mutex_aux_put(unlock);kd_mutex_aux_put(unlock);
 CHECK(atomic_read(&invocation->refs)==1 && !kd_mutex_aux_is_idle(lock));
 CHECK(!kd_mutex_aux_all_idle()); /* Pending frame/ACK survives empty queue. */
 struct kd_mutex_aux *next=kd_mutex_aux_get(lock);
 CHECK(next==invocation && atomic_read(&invocation->refs)==2);
 kd_mutex_aux_ref(next); /* Next owner enters before old frame retires. */
 kd_mutex_aux_put(invocation);kd_mutex_aux_put(next);
 CHECK(atomic_read(&next->refs)==1 && !kd_mutex_aux_all_idle());
 kd_mutex_aux_put(next);
 CHECK(kd_mutex_aux_is_idle(lock) && !kd_mutex_aux_lookup(lock));
 CHECK(kd_mutex_aux_all_idle() && pending_callbacks()==1 && allocations==frees+1);
 drained_callbacks();
 for(unsigned int i=0;i<1000;i++) {
  next=kd_mutex_aux_get(lock);CHECK(next && atomic_read(&next->refs)==1);
  CHECK(!next->physical_owner && !next->state.counter && !next->tail && !next->waiter_count.counter);
  kd_mutex_aux_put(next);CHECK(kd_mutex_aux_is_idle(lock));
 }
 drained_callbacks();
}

static struct kd_mutex_aux *race_aux,*race_lookup;
static bool barrier_done,put_done;
static void *held_lookup(void *unused)
{ (void)unused;cas_pause=1;race_lookup=kd_mutex_aux_lookup(&locks[0]);return NULL; }
static void *barrier_thread(void *unused)
{ (void)unused;rcu_barrier();__atomic_store_n(&barrier_done,true,__ATOMIC_RELEASE);return NULL; }
static void *final_put(void *unused)
{ (void)unused;announce_put=true;kd_mutex_aux_put(race_aux);__atomic_store_n(&put_done,true,__ATOMIC_RELEASE);return NULL; }
static void *racing_put(void *unused)
{ (void)unused;cas_pause=2;kd_mutex_aux_put(race_aux);return NULL; }

static void check_reader_across_retirement(void)
{
 pthread_t reader,barrier;unsigned int before=frees,waits=barrier_waits;
 race_aux=kd_mutex_aux_get(&locks[0]);CHECK(race_aux);
 cas_target=&race_aux->refs;gate_reset(&cas_gate);barrier_done=false;
 CHECK(!pthread_create(&reader,NULL,held_lookup,NULL));gate_wait(&cas_gate,1);
 /* The reader discovered the old node but holds no reference yet. */
 CHECK(atomic_read(&race_aux->refs)==1);kd_mutex_aux_put(race_aux);
 CHECK(kd_mutex_aux_is_idle(&locks[0]) && !kd_mutex_debug_aux_count());
 CHECK(pending_callbacks()==1 && frees==before);
 CHECK(!pthread_create(&barrier,NULL,barrier_thread,NULL));wait_for_barrier(waits);
 CHECK(!READ_ONCE(barrier_done) && frees==before);
 struct kd_mutex_aux *replacement=kd_mutex_aux_get(&locks[0]);
 CHECK(replacement && replacement!=race_aux && replacement->lock==race_aux->lock);
 CHECK(kd_mutex_debug_aux_count()==1 && atomic_read(&replacement->refs)==1);
 rcu_read_lock();CHECK(!kd_mutex_aux_try_ref(race_aux));rcu_read_unlock();
 CHECK(!atomic_read(&race_aux->refs) && !READ_ONCE(barrier_done));
 gate_release(&cas_gate);
 CHECK(!pthread_join(reader,NULL));CHECK(!pthread_join(barrier,NULL));
 CHECK(!race_lookup && READ_ONCE(barrier_done) && frees==before+1);
 CHECK(atomic_read(&replacement->refs)==1 && kd_mutex_debug_aux_count()==1);
 cas_target=NULL;kd_mutex_aux_put(replacement);drained_callbacks();
}
static void check_lookup_wins_last_put(void)
{
 pthread_t thread;race_aux=kd_mutex_aux_get(&locks[0]);CHECK(race_aux);
 struct kd_mutex_aux_bucket *bucket=kd_mutex_aux_bucket(&locks[0]);
 gate_reset(&put_gate);put_done=false;
 unsigned long flags=_raw_spin_lock_irqsave(&bucket->lock);
 CHECK(!pthread_create(&thread,NULL,final_put,NULL));gate_wait(&put_gate,1);
 /* Final put waits for publication serialization. RCU lookup still progresses
  * and increments 1->2 without acquiring the held bucket. */
 struct kd_mutex_aux *lookup=kd_mutex_aux_lookup(&locks[0]);
 CHECK(lookup==race_aux && atomic_read(&lookup->refs)==2 && !READ_ONCE(put_done));
 _raw_spin_unlock_irqrestore(&bucket->lock,flags);
 CHECK(!pthread_join(thread,NULL));CHECK(READ_ONCE(put_done));
 CHECK(atomic_read(&lookup->refs)==1 && kd_mutex_debug_aux_count()==1 && !pending_callbacks());
 kd_mutex_aux_put(lookup);drained_callbacks();
}
static void check_two_puts(void)
{
 pthread_t threads[2];race_aux=kd_mutex_aux_get(&locks[0]);kd_mutex_aux_ref(race_aux);
 cas_target=&race_aux->refs;gate_reset(&cas_gate);
 for(unsigned int i=0;i<2;i++)CHECK(!pthread_create(&threads[i],NULL,racing_put,NULL));
 gate_wait(&cas_gate,2);CHECK(atomic_read(&race_aux->refs)==2);gate_release(&cas_gate);
 for(unsigned int i=0;i<2;i++)CHECK(!pthread_join(threads[i],NULL));
 cas_target=NULL;CHECK(kd_mutex_aux_all_idle() && pending_callbacks()==1);drained_callbacks();
}

#define WORKERS 8
static pthread_barrier_t allocate,acquired,release;
static struct kd_mutex_aux *results[WORKERS];
static void *duplicate_creator(void *arg)
{
 unsigned int id=(uintptr_t)arg;
 results[id]=kd_mutex_aux_get(&locks[0]);CHECK(results[id]);
 pthread_barrier_wait(&acquired);pthread_barrier_wait(&release);
 kd_mutex_aux_put(results[id]);return NULL;
}
static void check_duplicate_publication(void)
{
 pthread_t threads[WORKERS];unsigned int before=allocations,freed=frees;
 CHECK(!pthread_barrier_init(&allocate,NULL,WORKERS));
 CHECK(!pthread_barrier_init(&acquired,NULL,WORKERS+1));
 CHECK(!pthread_barrier_init(&release,NULL,WORKERS+1));allocation_barrier=&allocate;
 for(uintptr_t i=0;i<WORKERS;i++)CHECK(!pthread_create(&threads[i],NULL,duplicate_creator,(void *)i));
 pthread_barrier_wait(&acquired);
 CHECK(kd_mutex_debug_aux_count()==1 && atomic_read(&results[0]->refs)==WORKERS);
 for(unsigned int i=0;i<WORKERS;i++)CHECK(results[i]==results[0]);
 CHECK(allocations==before+WORKERS && frees==freed+WORKERS-1);
 pthread_barrier_wait(&release);
 for(unsigned int i=0;i<WORKERS;i++)CHECK(!pthread_join(threads[i],NULL));
 allocation_barrier=NULL;CHECK(pending_callbacks()==1);drained_callbacks();
 pthread_barrier_destroy(&allocate);pthread_barrier_destroy(&acquired);pthread_barrier_destroy(&release);
}
static void *lookup_stress(void *arg)
{
 unsigned int id=(uintptr_t)arg;
 for(unsigned int i=0;i<4000;i++) {
  /* Same key, different keys in one bucket, and distinct buckets. */
  struct kd_mutex *lock=&locks[(i%3==0)?0:(i%3==1)?64*(id+1):(i+id)%64];
  struct kd_mutex_aux *aux=kd_mutex_aux_get(lock);CHECK(aux && aux->lock==lock);
  kd_mutex_aux_ref(aux);
  struct kd_mutex_aux *lookup=kd_mutex_aux_lookup(lock);CHECK(lookup==aux);
  kd_mutex_aux_put(lookup);kd_mutex_aux_put(aux);kd_mutex_aux_put(aux);
 }
 return NULL;
}
static void check_stress(void)
{
 pthread_t threads[WORKERS];
 for(uintptr_t i=0;i<WORKERS;i++)CHECK(!pthread_create(&threads[i],NULL,lookup_stress,(void *)i));
 for(unsigned int i=0;i<WORKERS;i++)CHECK(!pthread_join(threads[i],NULL));
 CHECK(kd_mutex_aux_all_idle());drained_callbacks();
}
int main(void)
{
 CHECK(sizeof(struct kd_mutex)==32 && _Alignof(struct kd_mutex)==8);
 struct layout { char prefix; struct kd_mutex lock; char suffix; };
 CHECK(offsetof(struct layout,lock)==8 && offsetof(struct layout,suffix)==40);
 cache_failure=true;CHECK(kd_mutex_aux_init()==-ENOMEM && kd_mutex_aux_all_idle());
 cache_failure=false;CHECK(!kd_mutex_aux_init());check_lifetime();
 check_reader_across_retirement();check_lookup_wins_last_put();check_two_puts();
 kd_mutex_aux_fail_once=1;CHECK(!kd_mutex_aux_get(&locks[0]));
 CHECK(!kd_mutex_aux_fail_once && kd_mutex_aux_all_idle());
 allocation_failures=1;CHECK(!kd_mutex_aux_get(&locks[0]) && kd_mutex_aux_all_idle());allocation_failures=0;
 struct kd_mutex_aux *live=kd_mutex_aux_get(&locks[0]);CHECK(live);
 allocation_failures=1;kd_mutex_aux_fail_once=1;
 CHECK(kd_mutex_aux_get(&locks[0])==live && atomic_read(&live->refs)==2);
 CHECK(kd_mutex_aux_fail_once==1); /* Existing records never allocate. */
 kd_mutex_aux_put(live);kd_mutex_aux_put(live);
 allocation_failures=0;kd_mutex_aux_fail_once=0;drained_callbacks();
 struct kd_mutex_aux *many[2048];
 for(unsigned int i=0;i<2048;i++){many[i]=kd_mutex_aux_get(&locks[i]);CHECK(many[i]);}
 CHECK(kd_mutex_debug_aux_count()==2048);
 for(unsigned int i=0;i<2048;i++)kd_mutex_aux_put(many[i]);
 CHECK(kd_mutex_aux_all_idle() && pending_callbacks()==2048);drained_callbacks();
 check_duplicate_publication();check_stress();
 /* Empty membership is not callback completion. Exit must retain the slab
  * until its own rcu_barrier has executed the deferred free. */
 live=kd_mutex_aux_get(&locks[0]);kd_mutex_aux_put(live);
 CHECK(kd_mutex_aux_all_idle() && pending_callbacks()==1 && allocations==frees+1);
 unsigned int barriers=barrier_calls;kd_mutex_aux_exit();
 CHECK(barrier_calls==barriers+1 && !kd_mutex_aux_cache && allocations==frees && !held && !rcu_depth);
 puts("PASS aux RCU registry: 32-byte/8-byte layout, held reader/grace period, unlink and same-address replacement, no resurrection, lookup versus last put, racing 2-to-1 puts, exact owner/frame/ACK lifetime, allocation refusal, 2048 objects, 8 creators and 8x4000 concurrent operations, exit callback drain");
 return 0;
}
