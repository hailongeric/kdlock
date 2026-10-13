/* SPDX-License-Identifier: GPL-2.0 */
/* Production cache algorithm with deterministic collision and eviction races.
 * Scheduling and RCU primitives are substitutes; the kernel probe tests them. */
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <limits.h>
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL cache line %d: %s\n", __LINE__, #c); exit(1); } } while (0)
typedef struct { int counter; } atomic_t;
typedef int raw_spinlock_t;
struct task_struct { int usage; };
static struct task_struct *current;
struct hlist_node { struct hlist_node *next, **pprev; };
struct hlist_head { struct hlist_node *first; };
struct rcu_head { struct rcu_head *next; void (*fn)(struct rcu_head *); };
#define container_of(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define hlist_for_each_entry(e, h, m) \
 for (struct hlist_node *cursor = (h)->first; cursor && ((e) = container_of(cursor, __typeof__(*(e)), m), 1); cursor = cursor->next)
#define hlist_for_each_entry_rcu hlist_for_each_entry
#define hlist_for_each_entry_safe(e, n, h, m) \
 for (struct hlist_node *cursor = (h)->first; cursor && ((n) = cursor->next, (e) = container_of(cursor, __typeof__(*(e)), m), 1); cursor = (n))
static void hlist_add_head_rcu(struct hlist_node *n, struct hlist_head *h)
{
 n->next=h->first; n->pprev=&h->first;
 if(n->next)n->next->pprev=&n->next;
 h->first=n;
}
static void hlist_del_rcu(struct hlist_node *n)
{ *n->pprev=n->next; if(n->next)n->next->pprev=n->pprev; }
static unsigned int readers, allocations, frees, warnings;
static bool allocation_fail;
static atomic_t *reactivate;
static struct rcu_head *callbacks;
static void rcu_read_lock(void) { readers++; }
static void rcu_read_unlock(void) { CHECK(readers); readers--; }
static void call_rcu(struct rcu_head *r, void (*fn)(struct rcu_head *))
{ r->next=callbacks; r->fn=fn; callbacks=r; }
static void rcu_barrier(void)
{
 CHECK(!readers);
 while(callbacks) { struct rcu_head *r=callbacks; callbacks=r->next; r->fn(r); }
}
static void *kmalloc(size_t size, int flags)
{ (void)flags; if(allocation_fail)return NULL; allocations++; return malloc(size); }
static void kfree(void *p) { if(p) { frees++; free(p); } }
static void get_task_struct(struct task_struct *p) { CHECK(p->usage>0); p->usage++; }
static void put_task_struct(struct task_struct *p) { CHECK(p->usage>1); p->usage--; }
static int atomic_read(const atomic_t *p) { return p->counter; }
static void atomic_set(atomic_t *p, int n) { p->counter=n; }
static void atomic_inc(atomic_t *p) { p->counter++; }
static int atomic_dec_return(atomic_t *p) { return --p->counter; }
static bool atomic_add_unless(atomic_t *p, int n, int unless)
{ if(p->counter==unless)return false; p->counter+=n; return true; }
static int atomic_cmpxchg(atomic_t *p, int old, int value)
{
 if(p==reactivate && old==0 && value==-1) {
  CHECK(p->counter==0); p->counter=1; reactivate=NULL;
 }
 int seen=p->counter; if(seen==old)p->counter=value; return seen;
}
static int cmpxchg(int *p, int old, int value)
{ int seen=*p; if(seen==old)*p=value; return seen; }
#define raw_spin_lock_irqsave(p, f) do { CHECK(!*(p)); *(p)=1; (f)=0; } while(0)
#define raw_spin_unlock_irqrestore(p, f) do { CHECK(*(p)==1 && !(f)); *(p)=0; } while(0)
#define __RAW_SPIN_LOCK_UNLOCKED(n) 0
#define ____cacheline_aligned_in_smp
#define __read_mostly
#define GFP_ATOMIC 0
#define hash_ptr(p, b) ((void)(p), (void)(b), 0U)
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, v) ((x)=(v))
#define unlikely(x) (x)
static bool warned(bool value) { if(value)warnings++; return value; }
#define WARN_ON_ONCE(x) warned(!!(x))
#define BUG_ON(x) CHECK(!(x))
#define KD_MUTEX_STAT(n) static long n
#define KD_MUTEX_STAT_READ(n) (n)
#define this_cpu_inc(n) (++(n))
#define module_param_named(...)
#define pr_info(...) do { if(0)printf(__VA_ARGS__); } while(0)
#define pr_warn pr_info
#include "task_cache_production.h"

static struct task_struct tasks[16];
static struct kd_mutex_task *identity(unsigned int i)
{
 struct kd_mutex_task *e;
 hlist_for_each_entry(e,&kd_mutex_task_buckets[0].tasks,link)
  if(e->task==&tasks[i])return e;
 return NULL;
}
static void drain(void)
{
 CHECK(kd_mutex_tasks_idle()); kd_mutex_tasks_purge();
 CHECK(!callbacks && !readers && !kd_mutex_task_buckets[0].count);
 for(unsigned int i=0;i<16;i++)CHECK(tasks[i].usage==1);
 CHECK(allocations==frees && !warnings);
}
int main(void)
{
 for(unsigned int i=0;i<16;i++)tasks[i].usage=1;
 for(unsigned int i=0;i<10000;i++) {
  CHECK(kd_mutex_task_get(&tasks[0]) && kd_mutex_task_get(&tasks[0]));
  CHECK(kd_mutex_task_count()==1 && atomic_read(&identity(0)->refs)==2);
  kd_mutex_task_put(&tasks[0]); CHECK(kd_mutex_task_reroute(&tasks[0]));
  kd_mutex_task_put(&tasks[0]); CHECK(!kd_mutex_task_reroute(&tasks[0]));
 }
 CHECK(allocations==1 && !frees && tasks[0].usage==2);
 kd_mutex_task_fail_once=1;
 CHECK(!kd_mutex_task_get(&tasks[0]) && !kd_mutex_task_active(&tasks[0]));
 CHECK(kd_mutex_task_failures==1 && allocations==1); drain();
 for(unsigned int i=0;i<8;i++) { CHECK(kd_mutex_task_get(&tasks[i])); kd_mutex_task_put(&tasks[i]); }
 CHECK(kd_mutex_task_buckets[0].count==KD_MUTEX_TASK_CACHE_PER_BUCKET);
 struct kd_mutex_task *old=identity(7);
 rcu_read_lock();
 CHECK(kd_mutex_task_get(&tasks[8]));
 CHECK(!identity(7) && atomic_read(&old->refs)==-1 && old->task==&tasks[7]);
 CHECK(tasks[7].usage==2 && callbacks && !kd_mutex_task_active(&tasks[7]));
 rcu_read_unlock(); rcu_barrier(); CHECK(tasks[7].usage==1);
 kd_mutex_task_put(&tasks[8]);
 /* Simulate a cache hit winning the exact zero-to-evicted CAS. */
 reactivate=&identity(8)->refs;
 CHECK(kd_mutex_task_get(&tasks[9]) && !reactivate);
 CHECK(kd_mutex_task_active(&tasks[8]) && kd_mutex_task_count()==2);
 kd_mutex_task_put(&tasks[8]); kd_mutex_task_put(&tasks[9]);
 allocation_fail=true;
 CHECK(!kd_mutex_task_get(&tasks[10]) && !kd_mutex_task_active(&tasks[10]));
 CHECK(kd_mutex_task_failures==2 && kd_mutex_task_buckets[0].count==8);
 allocation_fail=false; drain();
 /* Active collisions may exceed the inactive-cache bound, and must never
  * be evicted. Final puts trim that overflow without losing any reference. */
 for(unsigned int i=0;i<12;i++)CHECK(kd_mutex_task_get(&tasks[i]));
 CHECK(kd_mutex_task_count()==12 && kd_mutex_task_buckets[0].count==12);
 CHECK(kd_mutex_task_get(&tasks[0])); kd_mutex_task_put(&tasks[0]);
 CHECK(kd_mutex_task_count()==12);
 for(unsigned int i=0;i<12;i++) {
  kd_mutex_task_put(&tasks[i]); CHECK(kd_mutex_task_count()==11-i);
 }
 CHECK(kd_mutex_task_buckets[0].count==8); drain();
 /* Ordinary B protects its native continuation from unlock-side A batching.
  * One record reference survives nesting and may coexist with an ACK ref. */
 current=&tasks[0]; CHECK(kd_owned_mutex_task_can_combine());
 kd_owned_mutex_task_enter(); kd_owned_mutex_task_enter();
 CHECK(!kd_owned_mutex_task_can_combine() && identity(0)->owned_holds==2);
 CHECK(atomic_read(&identity(0)->refs)==1);
 CHECK(kd_mutex_task_get(current));
 kd_owned_mutex_task_leave(); CHECK(!kd_owned_mutex_task_can_combine());
 kd_owned_mutex_task_leave(); CHECK(kd_owned_mutex_task_can_combine());
 CHECK(atomic_read(&identity(0)->refs)==1);
 kd_mutex_task_put(current); drain();
 /* Exhaustion keeps acquisition available through SELF and disables batching
  * without losing any tracked task's outstanding depth or routing reference. */
 current=&tasks[0]; kd_owned_mutex_task_enter();
 current=&tasks[1]; allocation_fail=true; kd_owned_mutex_task_enter();
 CHECK(kd_owned_tracking_exhausted && !kd_owned_mutex_task_can_combine());
 allocation_fail=false; kd_owned_mutex_task_enter();
 CHECK(!identity(1)); kd_owned_mutex_task_leave(); kd_owned_mutex_task_leave();
 current=&tasks[0]; kd_owned_mutex_task_enter();
 CHECK(identity(0)->owned_holds==2);
 kd_owned_mutex_task_leave(); kd_owned_mutex_task_leave();
 CHECK(!kd_owned_mutex_task_can_combine()); drain(); kd_mutex_tasks_exit();
 puts("PASS production task cache: exact nested refs, reuse, collisions, active overflow, eviction/reactivation race, deferred free, allocation refusal and drain");
 return 0;
}
