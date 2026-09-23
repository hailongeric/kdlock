/* SPDX-License-Identifier: GPL-2.0 */
/* Execute production hash/list/window code with a controlled clock and CPUs.
 * Exact-key counts and bucket membership use independent test identities. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* Mutation failures must be distinguished from crashes/timeouts. */
#undef assert
#define assert(c) do { if (!(c)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#c); exit(1); } } while(0)
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef unsigned long long u64;
#define U64_MAX UINT64_MAX
#define ____cacheline_aligned __attribute__((aligned(64)))
#define __percpu
#define __read_mostly
#define pr_info(...) do { if(0) printf(__VA_ARGS__); } while(0)
#define module_param(...)
#define module_param_named(...)
#define MODULE_PARM_DESC(...)
#define EXPORT_PER_CPU_SYMBOL_GPL(...)
#define TEST_CPUS 3
static unsigned int cpu_id, pins, clocks, disables, enables;
static unsigned long now = 1;
static size_t stride;
static bool fail_alloc, interrupt_context;
static bool kd_spin_delegate = true;
struct qspinlock { u16 tail; };
#define _Q_TAIL_OFFSET_HL 16
#define xchg(address, value) ({ __typeof__(*(address)) previous=*(address); *(address)=(value); previous; })
static void (*reentry)(void);
#define alloc_percpu(type) (stride=sizeof(type), fail_alloc ? NULL : calloc(TEST_CPUS, sizeof(type)))
#define free_percpu(p) free(p)
#define per_cpu_ptr(p,c) ((__typeof__(p))((char *)(p)+stride*(c)))
#define this_cpu_ptr(p) per_cpu_ptr(p,cpu_id)
#define for_each_possible_cpu(c) for ((c)=0;(c)<TEST_CPUS;(c)++)
#define in_task() (!interrupt_context)
#define preempt_count() pins
#define preempt_disable() do { ++pins; ++disables; } while(0)
#define preempt_enable() do { assert(pins); --pins; ++enables; } while(0)
static unsigned long hash_long(unsigned long key,unsigned int bits)
{ return (key*0x61c8864680b583ebUL)>>(64-bits); }
static unsigned long rdtsc_ordered(void)
{
 void (*f)(void)=reentry; reentry=NULL; clocks++;
 if(f) f();
 return now;
}
#define DECLARE_PER_CPU(type, name) extern type name[TEST_CPUS]
#define DEFINE_PER_CPU(type, name) type name[TEST_CPUS]
#define per_cpu(name, c) (name[c])
#define this_cpu_read(name) (name[cpu_id])
#define READ_ONCE(x) (x)
#include "hotlock_production.h"
static struct kd_hotlock_table *table(unsigned int kind)
{ return &this_cpu_ptr(kd_hotlock_cpu)->tables[kind]; }
static void hits(unsigned long addr, unsigned int n)
{ while(n--) { kd_hotlock_record_spin(addr); assert(!pins); } }
/* Simulate already-pinned MCS publishers, independently of lock API entries. */
static void mcs(unsigned int n)
{
 unsigned int before_disable=disables, before_enable=enables;
 pins++;
 while(n--) kd_hotlock_record_spin_mcs_pinned();
 assert(pins==1 && disables==before_disable && enables==before_enable);
 pins--;
}
static void warm_spin(unsigned long addr)
{ mcs(1); hits(addr,33); }
static void reset(void)
{
 if(kd_hotlock_cpu) kd_hotlock_exit();
 cpu_id=pins=clocks=0; now=1; hotlock_mode="adaptive";
 interrupt_context=false;
 kd_spin_delegate=true;
 assert(!kd_hotlock_init());
}
static void check_chains(struct kd_hotlock_table *t)
{
 bool seen[KD_HOTLOCK_ENTRIES]={false}; unsigned int count=0;
 for(unsigned int b=0;b<KD_HOTLOCK_BUCKETS;b++) {
  for(u16 i=t->buckets[b];i;i=t->entries[i-1].next) {
   assert(i<=t->used && !seen[i-1]);
   seen[i-1]=true; count++;
   assert(kd_hotlock_bucket(t->entries[i-1].address)==b);
   assert(kd_hotlock_find(t,t->entries[i-1].address)==&t->entries[i-1]);
  }
 }
 assert(count==t->used);
}
static void irq_reentry(void)
{
 struct kd_hotlock_table before=*table(0);
 interrupt_context=true;
 assert(kd_hotlock_record_spin(0xdead)==kd_hotlock_observe);
 assert(!kd_hotlock_query_spin(0x1000));
 kd_hotlock_record_spin_mcs_pinned();
 interrupt_context=false;
 assert(!memcmp(&before,table(0),sizeof(before)));
 assert(pins==1);
}
/* The API accepts initialized, valid identities. Invalid initialization is
 * checked separately; an invalid-address hot-path branch is not its contract. */
static void init_and_pins(void)
{
 reset();
 assert(sizeof(struct kd_hotlock_entry)==24);
 assert(sizeof(struct kd_hotlock_table)==6680 && sizeof(struct kd_hotlock_cpu)==13376);
 assert(clocks==1);
 for(unsigned int c=0;c<TEST_CPUS;c++)
  for(unsigned int k=0;k<2;k++) {
   struct kd_hotlock_table *t=&per_cpu_ptr(kd_hotlock_cpu,c)->tables[k];
   assert(t->rate_begin==now && !t->rate_samples && !t->rate_hot && !t->used);
   if (!k) assert(per_cpu(kd_hotlock_spin_gate,c)==&t->rate_hot);
  }
 pins=1;
 unsigned int before_disable=disables, before_enable=enables;
 kd_hotlock_record_spin_pinned(0x1000); kd_hotlock_record_spin(0x1000);
 kd_hotlock_record_spin_mcs_pinned();
 kd_hotlock_query_spin(0x1000);
 /* Interrupt samples are deliberately lost, even with no active table writer. */
 interrupt_context=true;
 struct kd_hotlock_table before=*table(0);
 assert(!kd_hotlock_record_spin(0x1000));
 assert(!memcmp(&before,table(0),sizeof(before)));
 kd_hotlock_record_spin_mcs_pinned();
 assert(!memcmp(&before,table(0),sizeof(before)));
 interrupt_context=false;
 assert(pins==1 && disables==before_disable && enables==before_enable);
 pins=0;
 kd_hotlock_record_mutex(0x2000);
 assert(!pins && disables==before_disable+1 && enables==before_enable+1);
}
/* Spin entries never advance the CPU clock. Every eligible MCS hit checks CPU heat;
 * the lock counter needs 33 subsequent entries to become hot. */
static void boundaries(void)
{
 reset();
 assert(KD_HOTLOCK_SPIN_MCS_INTERVAL==1 && KD_HOTLOCK_CHECK_INTERVAL==1024 && KD_HOTLOCK_SAMPLE_TARGET==32);
 assert(KD_HOTLOCK_CPU_WINDOW==40000000000UL);
 hits(0x1000,5000);
 assert(clocks==1 && !table(0)->used && !table(0)->rate_hot && !table(0)->rate_samples);
 unsigned long origin=table(0)->rate_begin;
 now+=100;
 assert(clocks==1 && !table(0)->rate_samples && !table(0)->rate_hot);
 assert(table(0)->rate_begin==origin && !table(0)->used);
 mcs(1);
 assert(clocks==2 && table(0)->rate_hot && !table(0)->rate_samples && !table(0)->used);
 assert(table(0)->rate_begin==now);
 assert(!kd_hotlock_record_spin(0x1000));
 struct kd_hotlock_entry *s=kd_hotlock_find(table(0),0x1000);
 assert(clocks==2 && table(0)->rate_hot && !table(0)->rate_samples);
 assert(s && s->count==1 && !s->hot && s->begin==now);
 hits(0x1000,31);
 assert(clocks==2 && s->count==32 && !s->hot);
 assert(kd_hotlock_record_spin(0x1000));
 assert(clocks==3 && !s->count && s->hot); /* spin reads its own lock timestamp */
 struct kd_hotlock_table before=*table(0);
 for(unsigned int i=0;i<2000;i++) assert(kd_hotlock_query_spin(0x1000));
 assert(clocks==3 && !memcmp(&before,table(0),sizeof(before)));
 assert(!kd_hotlock_query_mutex(0x1000) && clocks==3);
 hits(0x1000,32);
 origin=table(0)->rate_begin;
 now+=100;
 assert(clocks==3 && !table(0)->rate_samples && table(0)->rate_begin==origin);
 assert(s->count==32 && s->hot && s->begin==origin);
 mcs(1);
 assert(clocks==4 && !table(0)->rate_samples && s->count==32 && s->hot);
 assert(table(0)->rate_begin==now && s->begin==origin);
 assert(kd_hotlock_record_spin(0x1000));
 assert(clocks==5 && !s->count); /* only the lock checks this time */
 now+=100;
 assert(!kd_hotlock_record_spin(0x2000));
 s=kd_hotlock_find(table(0),0x2000);
 assert(s && s->begin==table(0)->rate_begin && s->begin<now && clocks==5);
}
static void windows(void)
{
 reset(); warm_spin(0x1000);
 struct kd_hotlock_entry *s=kd_hotlock_find(table(0),0x1000);
 now=s->begin+KD_HOTLOCK_INITIAL_WINDOW;
 hits(0x1000,32);
 assert(s->hot && s->count==32);
 assert(!kd_hotlock_record_spin(0x1000)); /* equality is cold */
 assert(!s->hot && !s->count && s->begin==now && table(0)->rate_hot);
 hits(0x1000,33); assert(s->hot);
 now=table(0)->rate_begin+KD_HOTLOCK_CPU_WINDOW;
 hits(0x1000,2000); /* no MCS event: cached CPU heat remains unchanged */
 assert(table(0)->rate_hot);
 mcs(1);
 assert(!table(0)->rate_hot && !s->hot && !s->count);
 assert(!kd_hotlock_query_spin(0x1000));
 hits(0x1000,2000); assert(!table(0)->rate_hot && !s->count);
 mcs(1);
 assert(table(0)->rate_hot && !s->hot && !s->count && s->begin==now);
 hits(0x1000,33); assert(s->hot);
 reset(); now+=KD_HOTLOCK_CPU_WINDOW;
 mcs(1); assert(!table(0)->rate_hot && !table(0)->used);
 mcs(1); assert(table(0)->rate_hot && !table(0)->used);
}
/* A single eligible event includes startup idle. After that, every event
 * measures its own interval; the exact deadline stays cold. */
static void cpu_batch_window(void)
{
 reset();
 unsigned long origin=now;
 now=origin+39999999999UL;
 mcs(1);
 assert(table(0)->rate_hot && table(0)->rate_begin==now && clocks==2);
 reset();origin=now;
 now=origin+40000000000UL;
 mcs(1);
 assert(clocks==2 && !table(0)->rate_hot && !table(0)->rate_samples);
 assert(table(0)->rate_begin==now && !table(0)->used);
 now++;
 mcs(1);assert(clocks==3 && table(0)->rate_hot && !table(0)->rate_samples);
 for(unsigned int i=0;i<3;i++) {
  now+=39999999999UL;
  mcs(1);
  assert(clocks==4+i && table(0)->rate_hot && !table(0)->rate_samples);
  assert(table(0)->rate_begin==now);
 }
}
static void backwards_and_zero(void)
{
 reset(); now=100; warm_spin(0x1000); hits(0x1000,32);
 struct kd_hotlock_entry *s=kd_hotlock_find(table(0),0x1000);
 assert(s->hot && s->count==32 && !table(0)->rate_samples);
 unsigned int before=clocks; now=50;
 assert(!kd_hotlock_record_spin(0x1000));
 assert(clocks==before+1 && table(0)->rate_hot && !s->hot && s->begin==50);
 mcs(1);
 assert(!table(0)->rate_hot && !s->count && !s->hot);
 reset(); now=0; mcs(1);
 assert(!table(0)->rate_hot && !table(0)->used && clocks==2);
 mcs(1);
 assert(table(0)->rate_hot && table(0)->rate_begin==0 && clocks==3);
 hits(0x1000,32); before=clocks;
 assert(kd_hotlock_record_spin(0x1000));
 assert(clocks==before+1); /* zero CPU counter is not a timestamp for spin */
}
/* More than six locks must retain independent counters, even when every key
 * hashes to the same bucket. Full tables keep all existing identities intact. */
static void hash_and_capacity(void)
{
 unsigned long keys[KD_HOTLOCK_ENTRIES+1]; unsigned int n=0;
 reset();
 for(unsigned long k=1;n<KD_HOTLOCK_ENTRIES+1;k++)
  if(kd_hotlock_bucket(k)==0) keys[n++]=k;
 warm_spin(keys[0]);
 for(unsigned int i=1;i<KD_HOTLOCK_ENTRIES;i++) {
  hits(keys[i],i%32+1);
  assert(kd_hotlock_find(table(0),keys[i])->count==i%32+1);
 }
 check_chains(table(0));
 assert(table(0)->used==KD_HOTLOCK_ENTRIES);
 for(unsigned int i=1;i<KD_HOTLOCK_ENTRIES;i++) {
  struct kd_hotlock_entry *s=kd_hotlock_find(table(0),keys[i]);
  assert(s && s->count==i%32+1 && !s->hot);
 }
 assert(kd_hotlock_query_spin(keys[0]));
 struct kd_hotlock_entry saved[KD_HOTLOCK_ENTRIES];
 memcpy(saved,table(0)->entries,sizeof(saved));
 hits(keys[KD_HOTLOCK_ENTRIES],2048);
 assert(!kd_hotlock_find(table(0),keys[KD_HOTLOCK_ENTRIES]));
 assert(!memcmp(saved,table(0)->entries,sizeof(saved)));
 assert(!kd_hotlock_query_spin(keys[KD_HOTLOCK_ENTRIES]));
 for(unsigned int i=0;i<KD_HOTLOCK_ENTRIES;i++) assert(kd_hotlock_find(table(0),keys[i]));
 hits(keys[0],33);assert(kd_hotlock_query_spin(keys[0]));
 assert(table(0)->used==KD_HOTLOCK_ENTRIES);check_chains(table(0));
 /* Stable membership survives CPU cooling; heat and counts do not. */
 now=table(0)->rate_begin+KD_HOTLOCK_CPU_WINDOW;
 mcs(1);
 assert(!table(0)->rate_hot && table(0)->used==KD_HOTLOCK_ENTRIES);
 for(unsigned int i=0;i<KD_HOTLOCK_ENTRIES;i++) {
  struct kd_hotlock_entry *s=kd_hotlock_find(table(0),keys[i]);
  assert(s && !s->hot && !s->count);
 }
}
/* Mutex retains entry-count CPU sampling and same-call timestamp sharing. */
static void mutex_sampling(void)
{
 reset();
 for(unsigned int i=0;i<1023;i++) assert(!kd_hotlock_record_mutex(0x1000));
 assert(clocks==1 && !table(1)->rate_hot && !table(1)->used);
 assert(!kd_hotlock_record_mutex(0x1000));
 assert(clocks==2 && table(1)->rate_hot && !table(1)->rate_samples);
 struct kd_hotlock_entry *s=kd_hotlock_find(table(1),0x1000);
 assert(s && s->count==1);
 for(unsigned int i=0;i<31;i++) assert(!kd_hotlock_record_mutex(0x1000));
 assert(clocks==2 && s->count==32);
 assert(kd_hotlock_record_mutex(0x1000));
 assert(clocks==3 && s->hot && !s->count);
 /* The 1024-entry CPU batch and 33-hit lock batch first coincide at entry
  * 33792. Natural continuous sampling must still share that one timestamp. */
 for(unsigned int i=1056;i<33791;i++) assert(kd_hotlock_record_mutex(0x1000));
 assert(table(1)->rate_samples==1023 && s->count==32);
 unsigned int before_clocks=clocks;
 assert(kd_hotlock_record_mutex(0x1000));
 assert(clocks==before_clocks+1 && !table(1)->rate_samples && !s->count);
 struct kd_hotlock_table before=*table(1);
 for(unsigned int i=0;i<100;i++) assert(kd_hotlock_query_mutex(0x1000));
 assert(!memcmp(&before,table(1),sizeof(before)) && clocks==before_clocks+1);
 assert(!table(0)->rate_samples && !table(0)->rate_hot && !table(0)->used);
 /* Mutex keeps 1024 entry samples and shares the 40-billion CPU window. */
 now=table(1)->rate_begin+39999999999UL;
 for(unsigned int i=0;i<1024;i++) kd_hotlock_record_mutex(0x1000);
 assert(table(1)->rate_hot && !table(1)->rate_samples && table(1)->rate_begin==now);
 unsigned long origin=table(1)->rate_begin;
 now=origin+40000000000UL;
 for(unsigned int i=0;i<1023;i++) kd_hotlock_record_mutex(0x1000);
 assert(table(1)->rate_hot && table(1)->rate_samples==1023 && table(1)->rate_begin==origin);
 assert(!kd_hotlock_record_mutex(0x1000));
 assert(!table(1)->rate_hot && !table(1)->rate_samples && table(1)->rate_begin==now);
 assert(!s->count && !s->hot && s->begin==now);
}
static void isolation_and_reentry(void)
{
 reset();warm_spin(0x1000);
 cpu_id=1;assert(!kd_hotlock_query_spin(0x1000));
 assert(!kd_hotlock_record_mutex(0x1000) && !pins);
 cpu_id=0;assert(kd_hotlock_query_spin(0x1000));
 hits(0x1000,32);reentry=irq_reentry;mcs(1);assert(!reentry);
 assert(kd_hotlock_find(table(0),0x1000)->count==32);
 reentry=irq_reentry;hits(0x1000,1);assert(!reentry);
 /* Both types use the same strict lock threshold but independent tables. */
 for(unsigned int i=0;i<1055;i++) assert(!kd_hotlock_record_mutex(0x1000));
 assert(kd_hotlock_record_mutex(0x1000) && kd_hotlock_query_mutex(0x1000));
 kd_hotlock_exit();hotlock_mode="observe";assert(!kd_hotlock_init());
 interrupt_context=true;
 assert(kd_hotlock_record_spin(0x1000) && !pins);
 assert(kd_hotlock_record_mutex(0x1000) && !pins && !table(1)->rate_samples);
 interrupt_context=false;
 assert(kd_hotlock_record_mutex(0x1000) && !pins);
 assert(!kd_hotlock_query_mutex(0x1000));
 hits(0x1000,5000); assert(!table(0)->rate_hot && !table(0)->used);
 mcs(1);
 for(unsigned int i=0;i<KD_HOTLOCK_ENTRIES;i++) assert(kd_hotlock_record_spin(0x10000+i));
 assert(kd_hotlock_record_spin(0x20000)); /* fixed policy, even at capacity */
 assert(!kd_hotlock_query_spin(0x20000));
}
/* Exercise the actual tail-publication hook without supplying any queue node
 * or successor links. Heat must depend only on publication times on this CPU. */
static void queue_event(void)
{
 struct qspinlock word={0};
 unsigned int before_disable=disables, before_enable=enables;
 pins++;
 assert(!xchg_tail(&word,1U<<16) && word.tail==1);
 assert(pins==1 && disables==before_disable && enables==before_enable);
 pins--;
}
static void mcs_publications(void)
{
 reset();
 /* Even a publisher without a linked successor contributes one sample. */
 queue_event();
 assert(table(0)->rate_hot && !table(0)->rate_samples && clocks==2);
 for(unsigned int i=0;i<64;i++) queue_event();
 assert(table(0)->rate_hot && !table(0)->rate_samples && clocks==66);
 /* A publication can cool the CPU; there is no later queue-head sample to
  * reheat it during the same acquisition. The next publication may reheat. */
 now=table(0)->rate_begin+KD_HOTLOCK_CPU_WINDOW;
 queue_event();
 assert(!table(0)->rate_hot && !table(0)->rate_samples && clocks==67);
 queue_event();
 assert(table(0)->rate_hot && !table(0)->rate_samples && clocks==68);

 reset(); interrupt_context=true;
 for(unsigned int i=0;i<4;i++) queue_event();
 assert(!table(0)->rate_hot && !table(0)->rate_samples && clocks==1);
 interrupt_context=false; kd_spin_delegate=false;
 for(unsigned int i=0;i<4;i++) queue_event();
 assert(!table(0)->rate_hot && !table(0)->rate_samples && clocks==1);
 kd_spin_delegate=true;
 queue_event();
 assert(table(0)->rate_hot && clocks==2);
 cpu_id=1;
 assert(!kd_hotlock_spin_cpu_hot_pinned() && !table(0)->rate_samples);
 queue_event();
 assert(table(0)->rate_hot && clocks==3);
 cpu_id=0;
}
int main(void)
{
 init_and_pins();boundaries();windows();cpu_batch_window();backwards_and_zero();
 hash_and_capacity();mutex_sampling();isolation_and_reentry();mcs_publications();
 kd_hotlock_exit();hotlock_mode="invalid";assert(kd_hotlock_init()==-EINVAL);
 hotlock_mode="adaptive";assert(!kd_hotlock_init());kd_hotlock_exit();
 fail_alloc=true;assert(kd_hotlock_init()==-ENOMEM);
 assert(!kd_hotlock_cpu);
 puts("PASS exact hash: spin-MCS-entry1/CPU-window4e10/mutex-CPU1024/lock33/collision/256-capacity/no-eviction/independent/query/window/zero/drop-interrupt/observe");
 return 0;
}
