/* SPDX-License-Identifier: GPL-2.0 */
/* Production stable task records with C atomics and mock task references.
 * Kernel task lifetime/final ACK are separately exercised in SELFTEST. */
#include <stdbool.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <string.h>
#define CHECK(c) do { if (!(c)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#c); exit(1); } } while(0)
#define BUG_ON(c) CHECK(!(c))
#define unlikely(c) (c)
#define ____cacheline_aligned __attribute__((aligned(64)))
#define module_param_named(...)
#define pr_info(...) printf(__VA_ARGS__)
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_RELAXED)
#define smp_load_acquire(p) __atomic_load_n((p), __ATOMIC_ACQUIRE)
typedef struct { atomic_int value; } atomic_t;
typedef struct { atomic_llong value; } atomic64_t;
#define ATOMIC64_INIT(v) { .value = (v) }
#define atomic_read(p) atomic_load(&(p)->value)
#define atomic_inc(p) ((void)atomic_fetch_add(&(p)->value,1))
#define atomic_dec_return(p) (atomic_fetch_sub(&(p)->value,1)-1)
#define KD_MUTEX_STAT(name) static atomic64_t name
#define KD_MUTEX_STAT_READ(name) atomic64_read(&(name))
#define this_cpu_inc(x) atomic64_inc(&(x))
#define atomic64_inc(p) ((void)atomic_fetch_add(&(p)->value,1))
#define atomic64_read(p) atomic_load(&(p)->value)
struct task_struct { atomic_int usage; };
static void get_task_struct(struct task_struct *task)
{ CHECK(atomic_fetch_add(&task->usage,1)>0); }
static void put_task_struct(struct task_struct *task)
{ CHECK(atomic_fetch_sub(&task->usage,1)>1); }
static unsigned long hash_long(unsigned long key,unsigned int bits)
{ return (key*0x61c8864680b583ebUL)>>(64-bits); }
static pthread_barrier_t publication;
static bool race_enabled;
static _Thread_local bool raced;
static void before_cas(size_t size)
{
 if(race_enabled && !raced && size==sizeof(void *)) {
  raced=true;
  int ret=pthread_barrier_wait(&publication);
  CHECK(ret==0 || ret==PTHREAD_BARRIER_SERIAL_THREAD);
 }
}
#define cmpxchg(p, old, value) ({ \
 __typeof__(*(p)) expected=(old); before_cas(sizeof(*(p))); \
 __atomic_compare_exchange_n((p),&expected,(value),false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE); expected; })
#include "mutex_tasks_production.h"
static struct task_struct shared;
static void *exercise(void *unused)
{
 (void)unused;
 for(unsigned int i=0;i<10000;i++) {
  CHECK(kd_mutex_task_get(&shared));
  CHECK(kd_mutex_task_active(&shared));
  if(!(i%7)) { CHECK(kd_mutex_task_get(&shared)); kd_mutex_task_put(&shared); }
  kd_mutex_task_put(&shared);
 }
 return NULL;
}
int main(void)
{
 pthread_t threads[8];
 atomic_init(&shared.usage,1);
 CHECK(sizeof(struct kd_mutex_task)==64 && kd_mutex_tasks_idle());
 CHECK(!kd_mutex_task_active(&shared));
 CHECK(!pthread_barrier_init(&publication,NULL,8)); race_enabled=true;
 for(unsigned int i=0;i<8;i++) CHECK(!pthread_create(&threads[i],NULL,exercise,NULL));
 for(unsigned int i=0;i<8;i++) CHECK(!pthread_join(threads[i],NULL));
 race_enabled=false; CHECK(!pthread_barrier_destroy(&publication));
 CHECK(kd_mutex_tasks_idle() && !kd_mutex_task_reroute(&shared));
 CHECK(kd_mutex_tasks_retained_count()==1 && atomic_load(&shared.usage)==2);
 struct kd_mutex_task *saved=kd_mutex_task_find(&shared);
 CHECK(saved && kd_mutex_task_get(&shared) && kd_mutex_task_reroute(&shared));
 CHECK(saved==kd_mutex_task_find(&shared)); kd_mutex_task_put(&shared);
 CHECK(!kd_mutex_task_active(&shared) && atomic_load(&shared.usage)==2);
 kd_mutex_task_fail_once=1;
 CHECK(!kd_mutex_task_get(&shared) && !kd_mutex_task_active(&shared));
 CHECK(kd_mutex_task_fail_once==0 && atomic64_read(&kd_mutex_task_failures)==1);
 /* Fill the real 1024-slot table using distinct allocated tasks whose real
  * addresses hash into one bucket. No task pointer is fabricated/dereferenced. */
 const unsigned int pool_size=3*1024*1024;
 struct task_struct *pool=calloc(pool_size,sizeof(*pool)); CHECK(pool);
 struct task_struct *keys[KD_MUTEX_TASK_CAPACITY]; unsigned int found=0;
 unsigned int bucket=hash_long((unsigned long)&shared,KD_MUTEX_TASK_BITS);
 for(unsigned int i=0;i<pool_size && found<KD_MUTEX_TASK_CAPACITY;i++)
  if(hash_long((unsigned long)&pool[i],KD_MUTEX_TASK_BITS)==bucket) {
   atomic_init(&pool[i].usage,1); keys[found++]=&pool[i];
  }
 CHECK(found==KD_MUTEX_TASK_CAPACITY);
 for(unsigned int i=0;i<KD_MUTEX_TASK_CAPACITY-1;i++) {
  CHECK(kd_mutex_task_get(keys[i]) && kd_mutex_task_active(keys[i]));
  kd_mutex_task_put(keys[i]); CHECK(!kd_mutex_task_active(keys[i]));
  CHECK(atomic_load(&keys[i]->usage)==2);
 }
 CHECK(kd_mutex_tasks_retained_count()==KD_MUTEX_TASK_CAPACITY && kd_mutex_tasks_idle());
 struct task_struct *extra=keys[KD_MUTEX_TASK_CAPACITY-1];
 CHECK(!kd_mutex_task_get(extra) && !kd_mutex_task_active(extra));
 CHECK(atomic_load(&extra->usage)==1 && atomic64_read(&kd_mutex_task_failures)==2);
 CHECK(kd_mutex_task_get(&shared) && !kd_mutex_tasks_idle());
 CHECK(kd_mutex_tasks_active_count()==1); kd_mutex_task_put(&shared);
 for(unsigned int i=0;i<KD_MUTEX_TASK_CAPACITY-1;i++) {
  CHECK(kd_mutex_task_get(keys[i])); kd_mutex_task_put(keys[i]);
 }
 kd_mutex_tasks_exit();
 CHECK(atomic_load(&shared.usage)==1);
 for(unsigned int i=0;i<KD_MUTEX_TASK_CAPACITY;i++) CHECK(atomic_load(&keys[i]->usage)==1);
 free(pool);
 puts("PASS stable mutex tasks: racing publication, exact refs, inactive cache, collisions, 1024 capacity, retained task lifetime and teardown");
 return 0;
}
