// SPDX-License-Identifier: GPL-2.0-only
/* Production batch selection, logical release, physical ACK and reaping.
 * Controlled source callbacks execute foreign bodies and model exact handback;
 * this does not execute generated instructions or model weak-memory scheduling.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include "spin_policy.h"
static struct kd_spin_contention_cache kd_spin_contention_state;
#define this_cpu_ptr(p) (p)
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
#define BUG_ON(x) CHECK(!(x))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
static void before_load(const void *p);
#define smp_load_acquire(p) ({ before_load(p); *(p); })
static void after_store(const void *p);
#define smp_store_release(p,v) do { *(p)=(v); after_store(p); } while (0)
static void after_exchange(const void *p, const void *n);
#define xchg(p,n) ({ __typeof__(*(p)) old=*(p); *(p)=(n); after_exchange(p,n); old; })
#define cmpxchg(p,o,n) ({ __typeof__(*(p)) old=*(p); if(old==(o)) *(p)=(n); old; })
typedef long atomic_long_t;
static atomic_long_t spin_policy_sequence;
static long atomic_long_read(atomic_long_t *p) { return *p; }
static bool atomic_long_try_cmpxchg(atomic_long_t *p, long *old, long next)
{ if (*p!=*old) { *old=*p; return false; } *p=next; return true; }
typedef int atomic_t;
#define atomic_read(p) (*(p))
#define atomic_cmpxchg(p,o,n) cmpxchg(p,o,n)
typedef struct { bool held; } raw_spinlock_t;
static void raw_spin_lock_init(raw_spinlock_t *g) { g->held=false; }
static void raw_spin_lock(raw_spinlock_t *g) { CHECK(!g->held); g->held=true; }
static void raw_spin_unlock(raw_spinlock_t *g) { CHECK(g->held); g->held=false; }
struct list_head { struct list_head *next, *prev; };
static void INIT_LIST_HEAD(struct list_head *h) { h->next=h->prev=h; }
static bool list_empty(const struct list_head *h) { return h->next==h; }
static void list_add_tail(struct list_head *n, struct list_head *h)
{ n->prev=h->prev; n->next=h; h->prev->next=n; h->prev=n; }
static void list_del_init(struct list_head *n)
{ n->prev->next=n->next; n->next->prev=n->prev; INIT_LIST_HEAD(n); }
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define list_for_each_entry(p,h,m) \
 for(p=container_of((h)->next,__typeof__(*p),m); &p->m!=(h); p=container_of(p->m.next,__typeof__(*p),m))
struct task_struct { unsigned int refs, id; };
struct kd_thread_state { struct task_struct *origin; unsigned int effects; };
struct kd_mutex_node;
struct kd_mutex { struct kd_mutex_node *tail; struct kd_mutex_batch *owner; };
struct kd_spinlock { struct kd_mutex queue; unsigned long policy_epoch; };
static void kd_mutex_init(struct kd_mutex *l) { l->tail=NULL; l->owner=NULL; }
typedef void (*kd_mutex_backend_unlock_fn)(void *);
#include "batch_types.h"
struct kd_mutex_ops { enum kd_mutex_outcome (*execute_proxy)(struct kd_mutex_node *, void *); };
struct kd_mutex_node {
 struct kd_mutex_node *next;
 struct kd_mutex *lock;
 struct kd_mutex_batch *batch, *possible_batch;
 struct kd_thread_state *state;
 struct task_struct *requester;
 const struct kd_mutex_ops *ops;
 void *context;
 const void *acquisition, *grant_user, *result_user;
 struct kd_mutex_release release;
 enum kd_mutex_service_policy service_policy;
 enum kd_mutex_outcome outcome;
 atomic_t selection;
 int turn, queue_done, result_ready, retirable;
 bool atomic_spin, spin_batch_ready, spin_batch_allowed, spin_batch_probe, ready, source_granted, enqueued, wait_started;
 void *rw, *native_local;
 bool synchronous_outer;
};
struct kd_owner_batch { struct kd_mutex_batch *batch; bool control_stopped; };
static struct task_struct tasks[8], *current;
static struct kd_thread_state states[8];
static struct kd_mutex_node nodes[8];
static struct kd_mutex_batch batches[8], *active;
static struct kd_spinlock object;
static struct kd_mutex *const fixture_lock = &object.queue;
static unsigned int queue_samples;
static unsigned int foreign, physical_releases, rejoins, post_unlocks, handbacks, progress_calls;
static unsigned int witness[8];
static bool physical_held, appended;
static const char *scenario;
static bool is(const char *s) { return !strcmp(scenario,s); }
static void get_task_struct(struct task_struct *t) { ++t->refs; }
static void put_task_struct(struct task_struct *t) { CHECK(t->refs>1); --t->refs; }
static int wake_up_process(struct task_struct *t) { CHECK(t); return 0; }
static bool spin_context(void) { return true; }
static void cpu_relax(void) { CHECK(progress_calls<32); }
static void rw_queue_get(struct kd_mutex_node *n) { CHECK(!n->rw); }
static void rw_queue_put(struct kd_mutex_node *n) { CHECK(!n->rw); }
static struct kd_mutex_node *wait_link(struct kd_mutex_node *n) { CHECK(n->next); return n->next; }
static int kd_rw_writer_enter(void *rw, struct kd_mutex_batch *b, void *conversion)
{ (void)rw; (void)b; (void)conversion; CHECK(false); return -EINVAL; }
static int kd_rw_write_grant(void *rw, struct kd_mutex_batch *b, struct kd_mutex_node *n)
{ (void)rw; (void)b; (void)n; CHECK(false); return -EINVAL; }
static void observe_event(struct kd_observation *o) { (void)o; }
#define kd_observe(k,...) do { struct kd_observation o={.kind=(k),__VA_ARGS__}; observe_event(&o); } while (0)
static bool progress_wait(struct kd_mutex_node *n);
static void mcs_physical_unlock(void *opaque);
static void link_request(struct kd_mutex *l, struct kd_mutex_node *n, enum kd_mutex_selection selection);
int kd_mutex_finish_batch(struct kd_mutex_batch *b);
static int spin_source_unlock(struct kd_mutex_node *n, struct kd_thread_state *s, enum kd_mutex_unlock_action *a);
static void publish_condition(struct kd_mutex_node *n, int *p);
#include "batch_functions.h"

static void mcs_physical_unlock(void *opaque)
{
 struct kd_mutex *l=opaque;
 struct kd_mutex_node *h=active->head;
 CHECK(l==fixture_lock && l->owner==active && physical_held && !physical_releases);
 CHECK(active->release_owner.task==current);
 physical_held=false; ++physical_releases; l->owner=NULL;
 h->queue_done=1;
 if(h->next) h->next->turn=1;
 else { CHECK(l->tail==h); l->tail=NULL; }
}
static void before_load(const void *p)
{
 if(!active && (p==&nodes[0].next || p==&nodes[1].next)) ++queue_samples;
}
static void after_exchange(const void *p, const void *n)
{
 if(p==&object.queue.tail && n==&nodes[0] && nodes[0].wait_started) {
  CHECK(!physical_held && physical_releases==1);
  CHECK(++rejoins==1);
 }
}

static bool progress_wait(struct kd_mutex_node *n)
{
 struct task_struct *saved=current;
 struct kd_mutex_release *rel;
 struct kd_owner_batch item={.batch=active,.control_stopped=true};
 CHECK(++progress_calls<32 && n);
 current=&tasks[0];
 if(active->release_owner.phase==KD_MUTEX_OWNER_OPEN) {
  list_for_each_entry(rel,&active->release_owner.obligations,owner_link)
   if(rel->phase==KD_MUTEX_UNLOCK_REQUESTED) CHECK(!kd_mutex_release_owner_handle(rel));
  if(finish_ready_locked(&item)) CHECK(!kd_mutex_finish_batch(active));
 }
 current=saved;
 return false;
}
static enum kd_mutex_outcome execute_body(struct kd_mutex_node *n, void *context)
{
 enum kd_mutex_unlock_action action;
 unsigned int id=(unsigned int)(n-nodes);
 CHECK(context==n && current==&tasks[0] && n->state->origin!=current);
 if(!active) { active=n->batch; physical_held=true; }
 CHECK(object.queue.owner==active && n->batch==active && physical_held && !physical_releases && !rejoins);
 CHECK(n->release.owner==&active->release_owner && n->release.acquisition==n->acquisition);
 CHECK(!active->release_owner.single_grant && active->spin_batch);
 CHECK(active->release_owner.task==&tasks[0]);
 ++foreign; ++n->state->effects; witness[id]=foreign;
 CHECK(!kd_mutex_release_hold_return(&n->release,n));
 CHECK(kd_mutex_release_retire(&n->release)==-EBUSY);
 if(id==2 && (is("miss") || is("nested"))) {
  /* The real episode driver closes admission before exact native transfer. */
  active->release_owner.close_requested=true;
  return KD_MUTEX_PROXY_ORIGIN_SUFFIX;
 }
 CHECK(!spin_source_unlock(n,n->state,&action));
 CHECK(action==KD_MUTEX_UNLOCK_ATOMIC && n->release.phase==KD_MUTEX_UNLOCK_OWNER_HANDLED);
 CHECK(physical_held && !physical_releases);
 return KD_MUTEX_PROXY_ORIGIN_SUFFIX;
}
static const struct kd_mutex_ops ops={.execute_proxy=execute_body};
static void init_node(unsigned int i)
{
 struct kd_mutex_node *n=&nodes[i];
 tasks[i].refs=2; tasks[i].id=i; states[i].origin=&tasks[i];
 n->state=&states[i]; n->requester=&tasks[i]; n->lock=fixture_lock;
 n->possible_batch=&batches[i]; n->ops=&ops; n->context=n;
 n->acquisition=n; n->grant_user=&n->grant_user; n->result_user=&n->result_user;
 n->atomic_spin=n->spin_batch_ready=n->spin_batch_allowed=n->spin_batch_probe=n->ready=n->enqueued=true;
 n->selection=KD_MUTEX_OFFERED;
}
static void after_store(const void *p)
{
 unsigned int i;
 for(i=1;i<8;i++) {
  struct kd_mutex_node *n=&nodes[i];
  if(p!=&n->result_ready) continue;
  CHECK(n->result_ready && n->batch==active);
  if(n->release.phase==KD_MUTEX_UNLOCK_OWNER_HANDLED) {
   CHECK(physical_held && !physical_releases);
   ++post_unlocks;
   if(is("reacquire") && i==1) {
    /* Same canonical origin, a distinct request and acquisition identity.
     * Old grant/return users remain retained before physical ACK.
     */
    CHECK(!appended && n->release.source_user && n->release.return_user);
    init_node(5); nodes[5].state=n->state;
    nodes[5].requester=n->requester; ++n->requester->refs;
    CHECK(object.queue.tail); object.queue.tail->next=&nodes[5]; object.queue.tail=&nodes[5]; appended=true;
   }
  } else {
   enum kd_mutex_unlock_action action;
   struct task_struct *saved=current;
   CHECK(i==2 && (is("miss") || is("nested")) && post_unlocks==1);
   CHECK(witness[1] && witness[2] && !witness[3]);
   current=n->requester;
   CHECK(!spin_source_unlock(n,n->state,&action));
   CHECK(n->release.phase==KD_MUTEX_UNLOCK_PHYSICALLY_RELEASED);
   current=saved; ++handbacks;
  }
 }
}
int main(int argc,char **argv)
{
 unsigned int i,count=2,limit=4,expected=2;
 bool started;
 CHECK(argc==2); scenario=argv[1]; current=&tasks[0];
 kd_spin_init(&object);
 if(is("policy")) {
  struct kd_spin_contention_cache a={0},b={0};
  unsigned char objects[8192];
  const void *key=&objects[0], *other=NULL, *collision=NULL;
  bool probe;
  for(i=64;i<sizeof(objects);i+=64) {
   if(kd_spin_contention_slot(&a,key)==kd_spin_contention_slot(&a,&objects[i])) collision=&objects[i];
   else other=&objects[i];
  }
  CHECK(other && collision);
  for(i=0;i<99;i++) { CHECK(!kd_spin_contention_sample(&a,key,1,true,&probe)); CHECK(!probe); }
  CHECK(kd_spin_contention_sample(&a,key,1,false,&probe) && probe);
  for(i=1;i<16;i++) CHECK(kd_spin_contention_sample(&a,key,1,true,&probe) && !probe);
  CHECK(kd_spin_contention_sample(&a,key,1,true,&probe) && probe);
  CHECK(!kd_spin_contention_sample(&b,key,1,true,&probe) && !probe);
  for(i=0;i<100;i++) CHECK(!kd_spin_contention_sample(&a,other,1,i<98,&probe));
  CHECK(kd_spin_contention_slot(&a,key)->strong);
  CHECK(!kd_spin_contention_sample(&a,key,2,true,&probe) && !probe);
  CHECK(kd_spin_contention_slot(&a,key)->samples==1);
  CHECK(!kd_spin_contention_sample(&a,collision,1,true,&probe) && !probe);
  CHECK(kd_spin_contention_slot(&a,key)->object==collision);
  CHECK(!kd_spin_contention_sample(&a,key,0,true,&probe) && !probe);
  printf("PASS %s\n",scenario); return 0;
 }
 if(is("epoch")) {
  unsigned long old=object.policy_epoch;
  CHECK(old);
  kd_spin_init(&object); CHECK(object.policy_epoch && object.policy_epoch!=old);
  spin_policy_sequence=-2L;
  CHECK(new_spin_policy_epoch()==~0UL && new_spin_policy_epoch()==0);
  kd_spin_init(&object); CHECK(!object.policy_epoch);
  printf("PASS %s\n",scenario); return 0;
 }
 if(is("accounting")) {
  init_node(0); init_node(1); init_node(2);
  link_request(fixture_lock,&nodes[0],KD_MUTEX_SELECTED_LOCAL);
  CHECK(kd_spin_contention_slot(&kd_spin_contention_state,fixture_lock)->samples==1 && kd_spin_contention_slot(&kd_spin_contention_state,fixture_lock)->slow==0);
  link_request(fixture_lock,&nodes[1],KD_MUTEX_OFFERED);
  CHECK(kd_spin_contention_slot(&kd_spin_contention_state,fixture_lock)->samples==2 && kd_spin_contention_slot(&kd_spin_contention_state,fixture_lock)->slow==1);
  nodes[2].wait_started=true;
  link_request(fixture_lock,&nodes[2],KD_MUTEX_SELECTED_LOCAL);
  CHECK(kd_spin_contention_slot(&kd_spin_contention_state,fixture_lock)->samples==2 && kd_spin_contention_slot(&kd_spin_contention_state,fixture_lock)->slow==1);
  printf("PASS %s\n",scenario); return 0;
 }
 if(is("light") || is("not_due")) count=3,expected=0;
 if(is("zero")) count=expected=0;
 if(is("one")) count=1,expected=0;
 if(is("cap")) count=4,limit=2;
 if(is("second_ineligible")) count=3,expected=1;
 if(is("head_hole")) count=3,expected=0;
 if(is("later_hole")) count=4;
 if(is("miss") || is("nested")) count=3;
 if(is("reacquire")) expected=3;
 if(is("proxy_off")) limit=expected=0;
 if(is("cap_one")) limit=1,expected=0;
 for(i=0;i<=count;i++) init_node(i);
 nodes[0].selection=KD_MUTEX_SELECTED_LOCAL; nodes[0].turn=1; nodes[0].wait_started=true;
 for(i=0;i<count;i++) nodes[i].next=&nodes[i+1];
 object.queue.tail=&nodes[count];
 if(is("light")) nodes[0].spin_batch_allowed=false;
 if(is("not_due")) nodes[0].spin_batch_probe=false;
 if(is("head_hole")) nodes[1].spin_batch_ready=false;
 if(is("second_ineligible")) nodes[2].spin_batch_ready=false;
 if(is("later_hole")) nodes[3].spin_batch_ready=false;
 started=spin_serve_batch(&nodes[0],limit);
 CHECK(foreign==expected && started==!!expected);
 if(is("light") || is("not_due")) CHECK(!queue_samples);
 else CHECK(queue_samples==(count?2U:1U) || is("proxy_off") || is("cap_one"));
 if(!expected) {
  CHECK(!active && !physical_releases && !rejoins && nodes[0].turn==1);
  for(i=1;i<=count;i++) CHECK(!nodes[i].state->effects && !nodes[i].result_ready);
 } else {
  CHECK(active==&batches[1] && active->head==&nodes[1]);
  CHECK(physical_releases==1 && rejoins==1 && !physical_held);
  CHECK(active->proxy_served==expected && !active->cohort_active);
  CHECK(witness[1]==1);
  if(expected>=2) CHECK(witness[2]==2);
  if(is("second_ineligible")) CHECK(nodes[2].turn && !witness[2] && !witness[3]);
  if(is("cap") || is("later_hole") || is("miss") || is("nested"))
   CHECK(!witness[3] && nodes[3].turn && object.queue.tail==&nodes[0]);
  if(is("miss") || is("nested")) CHECK(handbacks==1);
  if(is("reacquire")) CHECK(appended && witness[5]==3 && states[1].effects==2);
  CHECK(kd_mutex_reap_batch(active)==-EBUSY);
  for(i=1;i<8;i++) if(witness[i]) {
   CHECK(nodes[i].queue_done && nodes[i].result_ready && !nodes[i].retirable);
   CHECK(nodes[i].release.phase==KD_MUTEX_UNLOCK_PHYSICALLY_RELEASED);
   CHECK(!kd_mutex_release_drop_source(&nodes[i].release,nodes[i].grant_user));
   nodes[i].result_user=NULL;
  }
  /* Every independent return user still prevents reaping after ACK. */
  CHECK(kd_mutex_reap_batch(active)==-EBUSY);
  for(i=1;i<8;i++) if(witness[i]) CHECK(!kd_mutex_release_drop_return(&nodes[i].release,&nodes[i]));
  CHECK(!kd_mutex_reap_batch(active));
  for(i=1;i<8;i++) if(witness[i]) CHECK(nodes[i].retirable && nodes[i].release.phase==KD_MUTEX_UNLOCK_RETIRED);
  CHECK(tasks[1].refs==1);
  if(witness[2]) CHECK(tasks[2].refs==1);
 }
 printf("PASS %s\n",scenario);
 return 0;
}
