// SPDX-License-Identifier: GPL-2.0
/* Actual queue slowpath/count/wait helpers with deterministic peer boundaries.
 * CPU/stack setup, physical acquisition and proxy bodies are substitutes.
 * This checks source control flow, not assembly execution or weak memory. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef struct { int counter; } atomic_t;
struct task_struct { int id; } __attribute__((aligned(8)));
struct kd_mutex { atomic_t delegation_state; u32 delegation_tail; struct task_struct *owner; };
struct kd_mutex_node {
 struct kd_mutex_node *next;
 struct kd_mutex *lock, *counted_lock;
 u64 count_seq, queued_at_ns;
 unsigned long stack, gsbase, ip;
 int tail;
 unsigned int entry_abi, packet_state;
 u8 locked, completed, native_resume;
};
struct kd_mutex_cpu_state { struct kd_mutex_node *resume_node; };
#define U64_MAX UINT64_MAX
#define KDLOCK_MUTEX_SPIN_BUDGET 8
#define KD_MUTEX_TAIL_CPU_OFFSET 8
#define unlikely(value) (value)
#define CHECK(value) do { if (!(value)) { \
 fprintf(stderr,"FAIL publication line %d: %s\n",__LINE__,#value); exit(1); } } while(0)
#define BUG_ON(value) CHECK(!(value))
#define KD_PR_ERR(...) CHECK(false)
static void before_write(const void *word);
static void before_release(const void *word,uintptr_t value);
static void after_release(const void *word);
static void before_cas(const void *word,uintptr_t before,uintptr_t after);
#define READ_ONCE(value) __atomic_load_n(&(value),__ATOMIC_RELAXED)
#define WRITE_ONCE(value,after) do { before_write(&(value)); \
 __atomic_store_n(&(value),(after),__ATOMIC_RELAXED); } while(0)
#define smp_load_acquire(word) __atomic_load_n((word),__ATOMIC_ACQUIRE)
#define smp_store_release(word,value) do { \
 __typeof__(*(word)) publication_value=(value); \
 before_release((word),(uintptr_t)publication_value); \
 __atomic_store_n((word),publication_value,__ATOMIC_RELEASE); after_release(word); \
} while(0)
#define smp_wmb() __atomic_thread_fence(__ATOMIC_RELEASE)
#define cmpxchg(word,before,after) ({ \
 __typeof__(*(word)) publication_expected=(before); \
 before_cas((word),(uintptr_t)(before),(uintptr_t)(after)); \
 __atomic_compare_exchange_n((word),&publication_expected,(after),false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST); \
 publication_expected; })
#define atomic_read(word) __atomic_load_n(&(word)->counter,__ATOMIC_RELAXED)
#define atomic_read_acquire(word) __atomic_load_n(&(word)->counter,__ATOMIC_ACQUIRE)
#define atomic_long_read(word) ((unsigned long)__atomic_load_n((word),__ATOMIC_RELAXED))
#define atomic_cmpxchg(word,before,after) ({ int gate_expected=(before); \
 __atomic_compare_exchange_n(&(word)->counter,&gate_expected,(after),false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST); gate_expected; })
#define atomic_fetch_andnot_release(mask,word) __atomic_fetch_and(&(word)->counter,~(u32)(mask),__ATOMIC_RELEASE)
#define this_cpu_ptr(word) (word)
#define this_cpu_read(value) (value)
#define this_cpu_write(value,after) ((value)=(after))
#define this_cpu_inc(value) (++(value))
#define this_cpu_inc_return(value) (++(value))
#define this_cpu_dec_return(value) (--(value))
#define this_cpu_cmpxchg(word,before,after) ({ int cpu_seen=(word); if(cpu_seen==(before))(word)=(after); cpu_seen; })
static struct kd_mutex_cpu_state kd_mutex_shadows;
static int kd_mutex_active_waiters, kd_mutex_max_waiters, kd_mutex_frame_failure_count;
static struct kd_mutex lock;
static struct kd_mutex_node request, previous, later;
static struct task_struct task={1};
static struct task_struct *current=&task;
enum route { READY_BODY, DONE_LINK, WAIT_LINK, CLAIMED_LINK, NATIVE_LINK, HEAD_LINK, FIRST_HEAD };
static enum route route;
static unsigned int pins, migration, publications, links, debug_calls, pauses, schedules;
static unsigned int node_cas, acquisitions, tail_exchanges, peer_bodies;
static unsigned int selected_abi, unpins;
static u64 original_seq;
static bool shadow_active, append_later, incoming_link, proxy_access, result_returned;
static void cpu_relax(void);
static bool need_resched(void);
static void preempt_enable(void);
static void preempt_disable(void);
static void cond_resched(void);
static u64 kd_exe_queue_timing_start(void);
static void kd_exe_queue_timing_end(bool valid,u64 *stamp,u64 now);
static u32 tail_exchange(u32 *word,u32 value);
#define xchg(word,value) tail_exchange((word),(value))
static struct kd_mutex_node *kd_mutex_decode_tail(u32 tail);
static void kd_mutex_wait_and_lock_node(struct kd_mutex *value,struct kd_mutex_node *node);
static int kd_mutex_run_combiner(struct kd_mutex *value,struct kd_mutex_node *next,
                                 struct kd_mutex_node *head,bool after_body);
static void debug_waiter(const char *format);
#define mutex_debug(format) debug_waiter(format)
static inline int raw_smp_processor_id(void) { return 0; }
#include "publication_production.h"

static void exact_packet(void)
{
 CHECK(shadow_active && pins==1 && migration==1);
 CHECK(request.lock==&lock && request.counted_lock==&lock);
 CHECK(request.count_seq==original_seq+2 && !(request.count_seq&1));
 CHECK(kd_mutex_active_waiters==1 && kd_mutex_max_waiters==1);
 CHECK(request.stack==0x10000 && request.gsbase==0x20000 && request.ip==0x30000);
 CHECK(request.entry_abi==selected_abi && request.packet_state==0x55);
 CHECK(request.tail==2<<KD_MUTEX_TAIL_CPU_OFFSET && request.queued_at_ns==123);
 CHECK(previous.counted_lock==&lock && previous.count_seq==2);
}
static void before_write(const void *word)
{
 /* Once READY is visible, only peer result publication owns the packet until
  * zero is observed. Count exit belongs to the original pinned reservation. */
 if(word==&request.counted_lock) CHECK(request.count_seq&1);
 if(publications && !result_returned && !proxy_access) {
  CHECK(word==&request.count_seq || word==&request.counted_lock ||
        word==&kd_mutex_shadows.resume_node);
  CHECK(!request.locked); /* No origin mutation while execution is possible. */
 }
}
static void before_release(const void *word,uintptr_t value)
{
 if(word==&request.locked) {
  CHECK(value==KD_MUTEX_PROXY_READY && request.locked==KD_MUTEX_QUEUE_INIT);
  CHECK(route!=FIRST_HEAD && !publications && !links && !incoming_link);
  exact_packet();CHECK(debug_calls==1);
  publications++;
 } else {
  CHECK(word==&previous.next && (struct kd_mutex_node *)value==&request);
  CHECK(publications==1 && request.locked==KD_MUTEX_PROXY_READY);
  CHECK(!previous.next && !links);exact_packet();links++;
 }
}
static void finish_peer(bool native)
{
 exact_packet();CHECK(incoming_link && request.locked!=KD_MUTEX_WAIT);
 CHECK(!proxy_access && !peer_bodies);proxy_access=true;peer_bodies++;
 /* Peer frame/source access ends before the result-zero publication. The
  * actual frame implementation is covered by custody/terminal fixtures. */
 request.native_resume=native;
 request.completed=!native;
 if(!append_later)lock.delegation_tail=0;
 __atomic_store_n(&request.locked,0,__ATOMIC_RELEASE);
 proxy_access=false;
}
static void after_release(const void *word)
{
 if(word!=&previous.next)return;
 incoming_link=true;CHECK(previous.next==&request);exact_packet();
 CHECK(request.next==(append_later?&later:NULL));
 if(route==DONE_LINK || route==NATIVE_LINK || route==CLAIMED_LINK) {
  CHECK(kd_mutex_gate_try_combine(&lock));
  CHECK(kd_mutex_proxy_request(&lock,&request));
  if(route==CLAIMED_LINK)request.locked=KD_MUTEX_PROXY_CLAIMED;
  else finish_peer(route==NATIVE_LINK);
  kd_mutex_gate_set(&lock,KD_MUTEX_GATE_HELD);
 } else if(route==WAIT_LINK)request.locked=KD_MUTEX_WAIT;
 else if(route==HEAD_LINK)request.locked=0;
}
static void before_cas(const void *word,uintptr_t before,uintptr_t after)
{
 if(word==&request.locked) {
  node_cas++;
  CHECK(route==FIRST_HEAD && !incoming_link && !publications && !debug_calls);
  CHECK(before==KD_MUTEX_QUEUE_INIT && after==KD_MUTEX_WAIT && request.locked==before);
  exact_packet();
 } else CHECK(word==&lock.delegation_tail && after==0);
}
static u32 tail_exchange(u32 *word,u32 value)
{
 CHECK(word==&lock.delegation_tail && value==(u32)request.tail);
 CHECK(shadow_active && pins==1 && migration==1 && request.locked==KD_MUTEX_QUEUE_INIT);
 CHECK(!request.counted_lock && request.count_seq==original_seq && !tail_exchanges++);
 u32 old=*word;*word=value;
 if(append_later) {
  /* A later producer may reserve and publish the outgoing link before this
   * request publishes its own incoming link. Its separate count must survive. */
  CHECK(old==(u32)previous.tail);
  kd_mutex_count_enter(&lock,&later);
  *word=(u32)later.tail;
  __atomic_store_n(&request.next,&later,__ATOMIC_RELEASE);
 }
 return old;
}
static struct kd_mutex_node *kd_mutex_decode_tail(u32 tail)
{ CHECK(tail==(u32)previous.tail);return &previous; }
static void debug_waiter(const char *format)
{
 CHECK(!strcmp(format,"Mutex waiter spinning\n"));
 CHECK(request.locked==KD_MUTEX_QUEUE_INIT && !publications && !links && !debug_calls++);
 exact_packet();
}
static void cpu_relax(void)
{
 CHECK(++pauses<=3 && migration==1);
 if(!pins) { CHECK(route==WAIT_LINK && request.locked==KD_MUTEX_WAIT);return; }
 CHECK(request.locked==KD_MUTEX_PROXY_READY || request.locked==KD_MUTEX_PROXY_CLAIMED);
 CHECK(route==READY_BODY || route==CLAIMED_LINK);
 if(route==READY_BODY) {
  CHECK(kd_mutex_gate_try_combine(&lock));
  CHECK(kd_mutex_proxy_request(&lock,&request));
 }
 finish_peer(false);
 kd_mutex_gate_set(&lock,KD_MUTEX_GATE_HELD);
}
static bool need_resched(void) { CHECK(!pins && route==WAIT_LINK);return true; }
static void preempt_enable(void)
{
 CHECK(pins==1 && migration==1 && request.locked==KD_MUTEX_WAIT);
 CHECK(!(atomic_read(&lock.delegation_state)&KD_MUTEX_GATE_WITHDRAW));
 pins--;unpins++;
}
static void preempt_disable(void) { CHECK(!pins && migration==1);pins++; }
static void cond_resched(void)
{
 CHECK(route==WAIT_LINK && !pins && migration==1 && request.locked==KD_MUTEX_WAIT);
 schedules++;request.completed=KD_MUTEX_WAITER_PROCESSED;
 if(!append_later)lock.delegation_tail=0;
 __atomic_store_n(&request.locked,0,__ATOMIC_RELEASE);
}
static u64 kd_exe_queue_timing_start(void) { return 123; }
static void kd_exe_queue_timing_end(bool valid,u64 *stamp,u64 now)
{ CHECK(valid && stamp==&request.queued_at_ns && now==123 && pins==1); }
static void kd_mutex_wait_and_lock_node(struct kd_mutex *value,struct kd_mutex_node *node)
{
 CHECK(value==&lock && node==&request && pins==1 && migration==1);
 CHECK((route==FIRST_HEAD && request.locked==KD_MUTEX_WAIT) ||
       (route==HEAD_LINK && !request.locked));
 CHECK(!proxy_access);acquisitions++;
 kd_mutex_gate_set(&lock,KD_MUTEX_GATE_HELD);
}
static int kd_mutex_run_combiner(struct kd_mutex *value,struct kd_mutex_node *next,
                                 struct kd_mutex_node *head,bool after_body)
{
 CHECK(value==&lock && next==&later && head==&request && !after_body);
 CHECK(route==HEAD_LINK && append_later && !request.locked);
 /* No synthetic role exchange here: actual retirement/READY/source ordering
  * remains in the separate source-derived custody fixture. */
 return 0;
}
static void invocation(enum route selected,unsigned int abi,bool later_first)
{
 CHECK(!request.counted_lock && !(request.count_seq&1));
 original_seq=request.count_seq;
 memset(&previous,0,sizeof(previous));memset(&later,0,sizeof(later));
 route=selected;selected_abi=abi;append_later=later_first;
 pins=migration=1;shadow_active=true;incoming_link=proxy_access=result_returned=false;
 publications=links=debug_calls=pauses=schedules=node_cas=acquisitions=tail_exchanges=peer_bodies=unpins=0;
 kd_mutex_active_waiters=kd_mutex_max_waiters=kd_mutex_frame_failure_count=0;
 kd_mutex_shadows.resume_node=NULL;
 lock.owner=current;lock.delegation_state.counter=KD_MUTEX_GATE_HELD;
 previous.tail=3<<KD_MUTEX_TAIL_CPU_OFFSET;previous.lock=&lock;
 kd_mutex_count_enter(&lock,&previous);
 later.tail=4<<KD_MUTEX_TAIL_CPU_OFFSET;later.lock=&lock;later.locked=KD_MUTEX_PROXY_READY;
 request.next=NULL;request.lock=&lock;request.tail=2<<KD_MUTEX_TAIL_CPU_OFFSET;
 request.locked=KD_MUTEX_QUEUE_INIT;request.completed=request.native_resume=0;
 request.stack=0x10000;request.gsbase=0x20000;request.ip=0x30000;
 request.entry_abi=abi;request.packet_state=0x55;
 lock.delegation_tail=selected==FIRST_HEAD?0:(u32)previous.tail;
 int result=__kd_mutex_lock_slowpath(&lock,request.tail,&request);
 result_returned=true;
 CHECK(!kd_mutex_active_waiters && kd_mutex_max_waiters==1 && !kd_mutex_frame_failure_count);
 CHECK(!request.counted_lock && request.count_seq==original_seq+4);
 CHECK(pins==1 && migration==1 && !proxy_access && tail_exchanges==1);
 CHECK(request.next==(later_first?&later:NULL));
 CHECK(previous.counted_lock==&lock && previous.count_seq==2);
 if(selected==FIRST_HEAD || selected==HEAD_LINK) {
  CHECK(result==2 && acquisitions==1 && !peer_bodies && !request.completed && !request.native_resume);
  CHECK(!kd_mutex_shadows.resume_node);
 } else {
  CHECK(result==(selected==NATIVE_LINK?5:3) && !acquisitions);
  CHECK(kd_mutex_shadows.resume_node==&request && !request.locked);
  CHECK(peer_bodies==(selected==WAIT_LINK?0U:1U));
 }
 CHECK(node_cas==(selected==FIRST_HEAD?1U:0U));
 CHECK(publications==(selected==FIRST_HEAD?0U:1U) && publications==links && links==debug_calls);
 CHECK(schedules==(selected==WAIT_LINK?1U:0U) && schedules==unpins);
 if(later_first) {
  CHECK(lock.delegation_tail==(u32)later.tail && later.counted_lock==&lock && later.count_seq==2);
  kd_mutex_count_exit(&lock,&later);CHECK(later.count_seq==4);
 } else CHECK(!lock.delegation_tail);
 kd_mutex_count_exit(&lock,&previous);CHECK(previous.count_seq==4);
 shadow_active=false;
}
int main(void)
{
 unsigned int cases=0;
 for(unsigned int abi=KD_ENTRY_ABI_LEGACY;abi<=KD_ENTRY_ABI_MUTEX_CLOBBER_V1;abi++) {
  if(abi!=KD_ENTRY_ABI_LEGACY && abi!=KD_ENTRY_ABI_MUTEX_CLOBBER_V1)continue;
  for(unsigned int selected=READY_BODY;selected<=FIRST_HEAD;selected++)
   for(unsigned int later_first=0;later_first<2;later_first++) {
    if(selected==FIRST_HEAD && later_first)continue;
    for(unsigned int reuse=0;reuse<2;reuse++) {
     invocation((enum route)selected,abi,later_first);cases++;
    }
   }
 }
 CHECK(cases==52 && request.count_seq==cases*4);
 puts("PASS production publication: 52 ABI-tag/reuse routes, complete count/debug before READY before release link, early zero/WAIT/CLAIMED, late producer, private first-head and exact count drain");
 return 0;
}
