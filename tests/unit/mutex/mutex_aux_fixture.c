/* SPDX-License-Identifier: GPL-2.0 */
/* The production registry is compiled unchanged. Atomic bucket locks and real
 * pthreads test unique publication and final-reference retirement; slab storage
 * and task identities are controlled substitutes for the kernel allocator. */
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
#include "aux_types.h"
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define hlist_for_each_entry(e,h,m) \
 for (struct hlist_node *n=(h)->first; n && ((e)=container_of(n,__typeof__(*(e)),m),1); n=n->next)
static void hlist_add_head(struct hlist_node *n, struct hlist_head *h)
{
 n->next=h->first; n->pprev=&h->first;
 if(n->next)n->next->pprev=&n->next;
 h->first=n;
}
static void hlist_del(struct hlist_node *n)
{ *n->pprev=n->next; if(n->next)n->next->pprev=n->pprev; }
static bool hlist_empty(const struct hlist_head *h) { return !h->first; }
static _Thread_local unsigned int held;
static unsigned long _raw_spin_lock_irqsave(raw_spinlock_t *lock)
{
 while (__atomic_exchange_n(lock,1,__ATOMIC_ACQUIRE)) sched_yield();
 CHECK(!held); held++; return 0;
}
static void _raw_spin_unlock_irqrestore(raw_spinlock_t *lock,unsigned long flags)
{ CHECK(held==1 && !flags); held--; __atomic_store_n(lock,0,__ATOMIC_RELEASE); }
#define __RAW_SPIN_LOCK_UNLOCKED(n) 0
#define ____cacheline_aligned_in_smp
#define __read_mostly
#define L1_CACHE_BYTES 64
#define BUILD_BUG_ON(c) _Static_assert(!(c), "production layout")
#define BUG_ON(c) CHECK(!(c))
#define READ_ONCE(v) __atomic_load_n(&(v),__ATOMIC_RELAXED)
#define atomic_set(p,v) __atomic_store_n(&(p)->counter,(v),__ATOMIC_RELAXED)
#define atomic_read(p) __atomic_load_n(&(p)->counter,__ATOMIC_RELAXED)
#define unlikely(v) (v)
#define hash_ptr(p,b) (((uintptr_t)(p)>>3)&((1U<<(b))-1))
#define cmpxchg(p,o,n) ({ __typeof__(*(p)) old=(o); __atomic_compare_exchange_n((p),&old,(n),false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST); old; })
#define module_param_named(...)
#define EXPORT_SYMBOL_GPL(...)
#define GFP_ATOMIC 0
struct kmem_cache { size_t size, alignment; };
static bool cache_failure;
static unsigned int allocations, frees, allocation_failures;
static pthread_barrier_t *allocation_barrier;
static struct kmem_cache *kmem_cache_create(const char *name,size_t size,size_t alignment,unsigned long flags,void *ctor)
{
 CHECK(!held && !strcmp(name,"kd_mutex_aux") && !flags && !ctor);
 if(cache_failure)return NULL;
 struct kmem_cache *cache=malloc(sizeof(*cache)); CHECK(cache);
 cache->size=size;cache->alignment=alignment;return cache;
}
static void *kmem_cache_alloc(struct kmem_cache *cache,int flags)
{
 CHECK(!held && cache && flags==GFP_ATOMIC);
 if (allocation_barrier) pthread_barrier_wait(allocation_barrier);
 if (__atomic_load_n(&allocation_failures,__ATOMIC_RELAXED)) return NULL;
 void *p=aligned_alloc(cache->alignment,cache->size);CHECK(p);
 memset(p,0xa5,cache->size);
 __atomic_add_fetch(&allocations,1,__ATOMIC_RELAXED);return p;
}
static void kmem_cache_free(struct kmem_cache *cache,void *p)
{
 CHECK(!held && cache && p);
 memset(p,0xdd,cache->size);free(p);
 __atomic_add_fetch(&frees,1,__ATOMIC_RELAXED);
}
static void kmem_cache_destroy(struct kmem_cache *cache)
{ CHECK(!held && allocations==frees);free(cache); }
#include "aux_production.h"

static struct kd_mutex locks[2048];
static struct task_struct owner={1},other={2};
static void check_lifetime(void)
{
 struct kd_mutex *lock=&locks[0];
 CHECK(!kd_mutex_aux_get(NULL) && !kd_mutex_aux_lookup(NULL));
 CHECK(kd_mutex_aux_waiter_count(NULL)==-EINVAL);
 CHECK(kd_mutex_aux_is_idle(lock) && !kd_mutex_aux_lookup(lock));
 CHECK(!kd_mutex_combiner_active(lock) && !kd_mutex_delegation_owned(lock,&owner));
 CHECK(!kd_mutex_aux_waiter_count(lock) && !allocations);
 struct kd_mutex_aux *invocation=kd_mutex_aux_get(lock);
 CHECK(invocation && invocation->refs==1 && !kd_mutex_aux_is_idle(lock));
 CHECK(!kd_mutex_aux_all_idle() && kd_mutex_debug_aux_count()==1);
 CHECK(!invocation->state.counter && !invocation->tail && !invocation->waiter_count.counter);
 kd_mutex_aux_ref(invocation); /* Exact gate owner, separate from invocation. */
 invocation->physical_owner=&owner; invocation->locked=KD_MUTEX_GATE_COMBINER;
 invocation->tail=17;atomic_set(&invocation->waiter_count,2);
 CHECK(kd_mutex_delegation_owned(lock,&owner) && !kd_mutex_delegation_owned(lock,&other));
 CHECK(kd_mutex_combiner_active(lock) && kd_mutex_aux_waiter_count(lock)==2);
 struct kd_mutex_aux *unlock=kd_mutex_aux_lookup(lock);
 CHECK(unlock==invocation && invocation->refs==3);
 invocation->physical_owner=NULL;atomic_set(&invocation->state,0);
 invocation->tail=0;atomic_set(&invocation->waiter_count,0);
 kd_mutex_aux_put(unlock);kd_mutex_aux_put(unlock);
 CHECK(invocation->refs==1 && !kd_mutex_aux_is_idle(lock));
 CHECK(!kd_mutex_aux_all_idle()); /* Pending frame/ACK survives empty queue. */
 struct kd_mutex_aux *next=kd_mutex_aux_get(lock);
 CHECK(next==invocation && invocation->refs==2);
 kd_mutex_aux_ref(next); /* Next owner can enter before old frame retires. */
 kd_mutex_aux_put(invocation);kd_mutex_aux_put(next);
 CHECK(next->refs==1 && !kd_mutex_aux_all_idle());
 kd_mutex_aux_put(next);
 CHECK(kd_mutex_aux_is_idle(lock) && !kd_mutex_aux_lookup(lock));
 CHECK(kd_mutex_aux_all_idle() && allocations==frees);
 /* Same caller address is valid after all old references retire. Allocator
  * address reuse is allowed; no old pointer is used to inspect the new record. */
 for(unsigned int i=0;i<1000;i++) {
  next=kd_mutex_aux_get(lock);CHECK(next && next->refs==1);
  CHECK(!next->physical_owner && !next->state.counter && !next->tail && !next->waiter_count.counter);
  kd_mutex_aux_put(next);CHECK(kd_mutex_aux_is_idle(lock));
 }
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
 CHECK(!pthread_barrier_init(&release,NULL,WORKERS+1));
 allocation_barrier=&allocate;
 for(uintptr_t i=0;i<WORKERS;i++)CHECK(!pthread_create(&threads[i],NULL,duplicate_creator,(void *)i));
 pthread_barrier_wait(&acquired);
 CHECK(kd_mutex_debug_aux_count()==1 && results[0]->refs==WORKERS);
 for(unsigned int i=0;i<WORKERS;i++)CHECK(results[i]==results[0]);
 CHECK(allocations==before+WORKERS && frees==freed+WORKERS-1);
 pthread_barrier_wait(&release);
 for(unsigned int i=0;i<WORKERS;i++)CHECK(!pthread_join(threads[i],NULL));
 allocation_barrier=NULL;
 CHECK(kd_mutex_aux_all_idle() && allocations==frees);
 pthread_barrier_destroy(&allocate);pthread_barrier_destroy(&acquired);pthread_barrier_destroy(&release);
}
static void *lookup_stress(void *arg)
{
 unsigned int id=(uintptr_t)arg;
 for(unsigned int i=0;i<4000;i++) {
  /* Mix same-address contention, same-bucket collisions and other buckets. */
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
 CHECK(kd_mutex_aux_all_idle() && allocations==frees);
}
int main(void)
{
 CHECK(sizeof(struct kd_mutex)==32 && _Alignof(struct kd_mutex)==8);
 struct layout { char prefix; struct kd_mutex lock; char suffix; };
 CHECK(offsetof(struct layout,lock)==8 && offsetof(struct layout,suffix)==40);
 cache_failure=true;CHECK(kd_mutex_aux_init()==-ENOMEM && kd_mutex_aux_all_idle());
 cache_failure=false;CHECK(!kd_mutex_aux_init());
 check_lifetime();
 kd_mutex_aux_fail_once=1;CHECK(!kd_mutex_aux_get(&locks[0]));
 CHECK(!kd_mutex_aux_fail_once && kd_mutex_aux_all_idle());
 allocation_failures=1;CHECK(!kd_mutex_aux_get(&locks[0]) && kd_mutex_aux_all_idle());
 allocation_failures=0;
 struct kd_mutex_aux *live=kd_mutex_aux_get(&locks[0]);CHECK(live);
 allocation_failures=1;kd_mutex_aux_fail_once=1;
 CHECK(kd_mutex_aux_get(&locks[0])==live && live->refs==2);
 CHECK(kd_mutex_aux_fail_once==1); /* Existing records never need allocation. */
 kd_mutex_aux_put(live);kd_mutex_aux_put(live);
 allocation_failures=0;kd_mutex_aux_fail_once=0;
 struct kd_mutex_aux *many[2048];
 for(unsigned int i=0;i<2048;i++){many[i]=kd_mutex_aux_get(&locks[i]);CHECK(many[i]);}
 CHECK(kd_mutex_debug_aux_count()==2048);
 for(unsigned int i=0;i<2048;i++)kd_mutex_aux_put(many[i]);
 CHECK(kd_mutex_aux_all_idle() && allocations==frees);
 check_duplicate_publication();check_stress();kd_mutex_aux_exit();
 CHECK(!kd_mutex_aux_cache && allocations==frees && !held);
 puts("PASS aux registry: 32-byte/8-byte layout, allocation refusal, exact owner/frame lifetime, address reuse, 2048 objects, duplicate publication and 8x4000 concurrent get/lookup/put operations");
 return 0;
}
