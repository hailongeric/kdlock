/* SPDX-License-Identifier: GPL-2.0 */
/* Execute production hash/list/window and admission code with controlled clocks
 * and CPUs. Logical acquisitions and MCS publications are distinct events so
 * disabled delegation must recover using the same native sampling boundaries. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
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
static unsigned int cpu_id, pins, clocks, disables, enables, guards;
static unsigned long now = 1;
static size_t stride;
static bool fail_alloc;
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
#define preempt_count() pins
#define preempt_disable() do { ++pins; ++disables; } while(0)
#define preempt_enable() do { assert(pins); --pins; ++enables; } while(0)
#define barrier() asm volatile("" ::: "memory")
static unsigned int local_cmpxchg(unsigned int *p, unsigned int old, unsigned int value)
{ unsigned int found=*p; guards++; if(found==old) *p=value; return found; }
/* The expression names an offset in the dynamically allocated CPU area. */
#define this_cpu_cmpxchg(name, old, value) local_cmpxchg((unsigned int *)((char *)&(name)+stride*cpu_id),old,value)
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
/* Static CPU arrays are independent of the dynamic exact-table stride. */
#define raw_cpu_ptr(p) (&(*(p))[cpu_id])
#define per_cpu(name, c) (name[c])
#define this_cpu_read(name) (name[cpu_id])
#define this_cpu_inc(name) (++name[cpu_id])
#define this_cpu_inc_return(name) (++name[cpu_id])
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, value) ((x)=(value))
#include "hotlock_production.h"
static struct kd_hotlock_table *table(unsigned int kind)
{ return &this_cpu_ptr(kd_hotlock_cpu)->tables[kind]; }
static struct kd_hotlock_spin_ratio *ratio(void)
{ return &per_cpu(kd_hotlock_spin_ratio,cpu_id); }
/* These calls isolate exact-key sampling from real lock-entry accounting. */
static void hits(unsigned long addr, unsigned int n)
{ while(n--) { kd_hotlock_record_spin(addr); assert(!pins); } }
static void mcs(unsigned int n)
{
 unsigned int before_disable=disables, before_enable=enables;
 pins++;
 while(n--) kd_hotlock_record_spin_mcs_pinned();
 assert(pins==1 && disables==before_disable && enables==before_enable);
 pins--;
}
static void reset_policy(unsigned int percentage, const char *mode)
{
 if(kd_hotlock_cpu) kd_hotlock_exit();
 cpu_id=pins=clocks=guards=0; now=1; hotlock_mode=(char *)mode;
 spin_contention_pct=percentage; kd_spin_delegate=true; reentry=NULL;
 assert(!kd_hotlock_init());
}
/* Time/hash tests explicitly disable the additional contention policy. */
static void reset(void) { reset_policy(0,"adaptive"); }
static void warm_spin(unsigned long addr)
{ mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL); hits(addr,KD_HOTLOCK_SPIN_SAMPLE_TARGET+1); }
static void check_chains(struct kd_hotlock_table *t)
{
 bool seen[KD_HOTLOCK_ENTRIES]={false}; unsigned int count=0;
 for(unsigned int b=0;b<KD_HOTLOCK_BUCKETS;b++) {
  for(u16 i=t->buckets[b];i;i=t->entries[i-1].next) {
   assert(i<=t->used && !seen[i-1]); seen[i-1]=true; count++;
   assert(kd_hotlock_bucket(t->entries[i-1].address)==b);
   assert(kd_hotlock_find(t,t->entries[i-1].address)==&t->entries[i-1]);
  }
 }
 assert(count==t->used);
}
/* Simulate an IRQ reentering while its interrupted sampler owns the guard.
 * Fixed observe admission must survive a dropped record; queries stay cold. */
static void busy_reentry(void)
{
 struct kd_hotlock_table before=*table(0);
 struct kd_hotlock_spin_ratio before_ratio=*ratio();
 assert(before.busy==1);
 assert(kd_hotlock_record_spin(0xdead)==kd_hotlock_observe);
 assert(!kd_hotlock_query_spin(0x1000));
 unsigned long raw=this_cpu_read(kd_hotlock_spin_mcs);
 for(unsigned int i=0;i<KD_HOTLOCK_SPIN_MCS_INTERVAL;i++) {
  kd_hotlock_spin_entry_pinned();
  kd_hotlock_record_spin_mcs_pinned();
 }
 assert(this_cpu_read(kd_hotlock_spin_mcs)==raw+KD_HOTLOCK_SPIN_MCS_INTERVAL);
 assert(!memcmp(&before,table(0),sizeof(before)) && pins==1);
 assert(!memcmp(&before_ratio,ratio(),sizeof(before_ratio)));
}
static void init_and_pins(void)
{
 reset(); assert(sizeof(struct kd_hotlock_entry)==24 && clocks==1);
 /* Preserve the original exact-key working sets, including the mutex table
  * stride and the complete allocation request, not just spin entry offsets. */
 assert(offsetof(struct kd_hotlock_table,busy)==0);
 assert(offsetof(struct kd_hotlock_table,rate_samples)==4);
 assert(offsetof(struct kd_hotlock_table,rate_hot)==8);
 assert(offsetof(struct kd_hotlock_table,rate_begin)==16);
 assert(offsetof(struct kd_hotlock_table,buckets)==24);
 assert(offsetof(struct kd_hotlock_table,used)==536);
 assert(offsetof(struct kd_hotlock_table,entries)==544);
 assert(sizeof(struct kd_hotlock_table)==6688 && __alignof__(struct kd_hotlock_table)==8);
 assert(offsetof(struct kd_hotlock_cpu,tables[1])==6688);
 assert(sizeof(struct kd_hotlock_cpu)==13376 && __alignof__(struct kd_hotlock_cpu)==64);
 assert(sizeof(struct kd_hotlock_spin_ratio)==48 && __alignof__(struct kd_hotlock_spin_ratio)==8);
 assert(stride==13376);
 for(unsigned int c=0;c<TEST_CPUS;c++) {
  assert(!per_cpu(kd_hotlock_spin_entries,c));
  assert(!per_cpu(kd_hotlock_spin_mcs,c));
  struct kd_hotlock_spin_ratio *r=&per_cpu(kd_hotlock_spin_ratio,c);
  assert(r->ratio_hot && !r->ratio_cooldown && !r->ratio_cools && !r->ratio_low_windows);
  assert(!r->entry_begin && !r->mcs_total && !r->ratio_samples);
  assert(r->entry_limit==ULONG_MAX && !r->ratio_enforced && !r->freq_hot);
  for(unsigned int k=0;k<2;k++) {
   struct kd_hotlock_table *t=&per_cpu_ptr(kd_hotlock_cpu,c)->tables[k];
   assert(t->rate_begin==now && !t->rate_samples && !t->rate_hot && !t->used && !t->busy);
   if(!k) {
    assert(per_cpu(kd_hotlock_spin_gate,c)==&t->rate_hot);
   }
  }
 }
 pins=1;
 unsigned int before_disable=disables, before_enable=enables;
 kd_hotlock_spin_entry_pinned();
 assert(this_cpu_read(kd_hotlock_spin_entries)==1);
 kd_hotlock_record_spin_pinned(0x1000); kd_hotlock_record_spin(0x1000);
 kd_hotlock_record_spin_mcs_pinned(); kd_hotlock_query_spin(0x1000);
 assert(pins==1 && disables==before_disable && enables==before_enable);
 assert(this_cpu_read(kd_hotlock_spin_entries)==1 && !table(0)->busy);
 pins=0; kd_hotlock_record_mutex(0x2000);
 assert(!pins && disables==before_disable+1 && enables==before_enable+1);
}
static void boundaries(void)
{
 reset();
 assert(KD_HOTLOCK_SPIN_MCS_INTERVAL==128 && KD_HOTLOCK_CHECK_INTERVAL==1024 && KD_HOTLOCK_SAMPLE_TARGET==1024 && KD_HOTLOCK_SPIN_SAMPLE_TARGET==512);
 assert(KD_HOTLOCK_CPU_WINDOW==40000000000UL && KD_HOTLOCK_INITIAL_WINDOW==2500000000UL && KD_HOTLOCK_SPIN_INITIAL_WINDOW==1250000000UL);
 hits(0x1000,5000);
 assert(clocks==1 && !table(0)->used && !table(0)->rate_hot && !table(0)->rate_samples);
 unsigned long origin=table(0)->rate_begin; now+=100;
 unsigned int initial_guards=guards;
 for(unsigned int i=1;i<KD_HOTLOCK_SPIN_MCS_INTERVAL;i++) {
  mcs(1); assert(clocks==1 && !table(0)->rate_samples && !table(0)->rate_hot);
  assert(this_cpu_read(kd_hotlock_spin_mcs)==i && guards==initial_guards && !ratio()->mcs_total);
  assert(table(0)->rate_begin==origin && !table(0)->used);
 }
 mcs(1);
 assert(clocks==2 && table(0)->rate_hot && !table(0)->rate_samples && !table(0)->used);
 assert(guards==initial_guards+1 && ratio()->mcs_total==128 && this_cpu_read(kd_hotlock_spin_mcs)==128);
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET);
 struct kd_hotlock_entry *s=kd_hotlock_find(table(0),0x1000);
 assert(s && s->count==KD_HOTLOCK_SPIN_SAMPLE_TARGET && !s->hot && s->begin==now && clocks==2);
 assert(kd_hotlock_record_spin(0x1000)); assert(clocks==3 && !s->count && s->hot);
 struct kd_hotlock_table before=*table(0);
 struct kd_hotlock_spin_ratio before_ratio=*ratio();
 unsigned long entries=this_cpu_read(kd_hotlock_spin_entries);
 unsigned long raw=this_cpu_read(kd_hotlock_spin_mcs);
 for(unsigned int i=0;i<2000;i++) assert(kd_hotlock_query_spin(0x1000));
 assert(clocks==3 && !memcmp(&before,table(0),sizeof(before)));
 assert(!memcmp(&before_ratio,ratio(),sizeof(before_ratio)));
 assert(this_cpu_read(kd_hotlock_spin_entries)==entries && !kd_hotlock_query_mutex(0x1000));
 assert(this_cpu_read(kd_hotlock_spin_mcs)==raw);
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET); origin=table(0)->rate_begin; now+=100;
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL);
 assert(clocks==4 && s->count==KD_HOTLOCK_SPIN_SAMPLE_TARGET && s->hot && s->begin==origin);
 assert(kd_hotlock_record_spin(0x1000)); assert(clocks==5 && !s->count);
 now+=100; assert(!kd_hotlock_record_spin(0x2000));
 s=kd_hotlock_find(table(0),0x2000);
 assert(s && s->begin==table(0)->rate_begin && s->begin<now && clocks==5);
}
static void windows(void)
{
 reset(); warm_spin(0x1000);
 struct kd_hotlock_entry *s=kd_hotlock_find(table(0),0x1000);
 now=s->begin+KD_HOTLOCK_SPIN_INITIAL_WINDOW-1;
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET);
 assert(kd_hotlock_record_spin(0x1000) && s->hot && !s->count);
 now=s->begin+KD_HOTLOCK_SPIN_INITIAL_WINDOW;
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL);
 assert(s->hot && !s->count); /* Continuous admission keeps entry-side timing. */
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET); assert(s->hot);
 assert(!kd_hotlock_record_spin(0x1000)); /* Equality is cold. */
 assert(!s->hot && !s->count && s->begin==now && table(0)->rate_hot);
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET+1); assert(s->hot);
 reset(); warm_spin(0x1000); s=kd_hotlock_find(table(0),0x1000);
 now=table(0)->rate_begin+KD_HOTLOCK_CPU_WINDOW;
 hits(0x1000,2000); assert(table(0)->rate_hot); /* No MCS tick yet. */
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL);
 assert(!table(0)->rate_hot && !s->hot && !s->count && !kd_hotlock_query_spin(0x1000));
 hits(0x1000,2000); assert(!table(0)->rate_hot && !s->count);
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL);
 assert(table(0)->rate_hot && !s->hot && !s->count && s->begin==now);
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET+1); assert(s->hot);
 reset(); now+=KD_HOTLOCK_CPU_WINDOW-1;
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL); assert(table(0)->rate_hot);
 reset(); now+=KD_HOTLOCK_CPU_WINDOW;
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL); assert(!table(0)->rate_hot);
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL); assert(table(0)->rate_hot);
}
static void backwards_and_zero(void)
{
 reset(); now=100; warm_spin(0x1000); hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET);
 struct kd_hotlock_entry *s=kd_hotlock_find(table(0),0x1000);
 unsigned int before=clocks; now=50;
 assert(!kd_hotlock_record_spin(0x1000));
 assert(clocks==before+1 && table(0)->rate_hot && !s->hot && s->begin==50);
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL); assert(!table(0)->rate_hot && !s->count);
 reset(); now=0; mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL);
 assert(!table(0)->rate_hot && !table(0)->used && clocks==2);
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL);
 assert(table(0)->rate_hot && table(0)->rate_begin==0 && clocks==3);
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET); before=clocks;
 assert(kd_hotlock_record_spin(0x1000)); assert(clocks==before+1);
}
static void hash_and_capacity(void)
{
 unsigned long keys[KD_HOTLOCK_ENTRIES+1]; unsigned int n=0;
 reset();
 for(unsigned long k=1;n<KD_HOTLOCK_ENTRIES+1;k++)
  if(kd_hotlock_bucket(k)==0) keys[n++]=k;
 warm_spin(keys[0]);
 for(unsigned int i=1;i<KD_HOTLOCK_ENTRIES;i++) {
  hits(keys[i],i%32+1); assert(kd_hotlock_find(table(0),keys[i])->count==i%32+1);
 }
 check_chains(table(0)); assert(table(0)->used==KD_HOTLOCK_ENTRIES);
 assert(kd_hotlock_query_spin(keys[0]));
 struct kd_hotlock_entry saved[KD_HOTLOCK_ENTRIES]; memcpy(saved,table(0)->entries,sizeof(saved));
 hits(keys[KD_HOTLOCK_ENTRIES],2048);
 assert(!kd_hotlock_find(table(0),keys[KD_HOTLOCK_ENTRIES]));
 assert(!memcmp(saved,table(0)->entries,sizeof(saved)) && !kd_hotlock_query_spin(keys[KD_HOTLOCK_ENTRIES]));
 for(unsigned int i=0;i<KD_HOTLOCK_ENTRIES;i++) assert(kd_hotlock_find(table(0),keys[i]));
 hits(keys[0],KD_HOTLOCK_SPIN_SAMPLE_TARGET+1); assert(kd_hotlock_query_spin(keys[0]));
 now=table(0)->rate_begin+KD_HOTLOCK_CPU_WINDOW; mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL);
 assert(!table(0)->rate_hot && table(0)->used==KD_HOTLOCK_ENTRIES);
 for(unsigned int i=0;i<KD_HOTLOCK_ENTRIES;i++) {
  struct kd_hotlock_entry *s=kd_hotlock_find(table(0),keys[i]); assert(s && !s->hot && !s->count);
 }
 check_chains(table(0));
}
static void mutex_sampling(void)
{
 reset();
 struct kd_hotlock_spin_ratio before_ratio=*ratio();
 for(unsigned int i=0;i<KD_HOTLOCK_CHECK_INTERVAL-1;i++) assert(!kd_hotlock_record_mutex(0x1000));
 assert(clocks==1 && !table(1)->rate_hot && !table(1)->used);
 assert(!kd_hotlock_record_mutex(0x1000)); assert(clocks==2 && table(1)->rate_hot);
 assert(!memcmp(&before_ratio,ratio(),sizeof(before_ratio)));
 struct kd_hotlock_entry *s=kd_hotlock_find(table(1),0x1000); assert(s && s->count==1);
 for(unsigned int i=1;i<KD_HOTLOCK_SAMPLE_TARGET;i++) assert(!kd_hotlock_record_mutex(0x1000));
 assert(s->count==KD_HOTLOCK_SAMPLE_TARGET);
 assert(kd_hotlock_record_mutex(0x1000)); assert(s->hot && !s->count);
 /* Spin's shorter epoch must not change the mutex frequency criterion.
  * Just below 2.5e9 remains hot, equality cools, and a fresh batch can reheat. */
 now=s->begin+KD_HOTLOCK_INITIAL_WINDOW-1;
 for(unsigned int i=0;i<KD_HOTLOCK_SAMPLE_TARGET;i++) assert(kd_hotlock_record_mutex(0x1000));
 assert(kd_hotlock_record_mutex(0x1000) && s->hot && !s->count);
 now=s->begin+KD_HOTLOCK_INITIAL_WINDOW;
 for(unsigned int i=0;i<KD_HOTLOCK_SAMPLE_TARGET;i++) assert(kd_hotlock_record_mutex(0x1000));
 assert(!kd_hotlock_record_mutex(0x1000) && !s->hot && !s->count);
 for(unsigned int i=0;i<KD_HOTLOCK_SAMPLE_TARGET;i++) assert(!kd_hotlock_record_mutex(0x1000));
 assert(kd_hotlock_record_mutex(0x1000) && s->hot && !s->count);
 /* Drive natural records until CPU and lock windows close together; their
  * relatively prime intervals make the shared timestamp case infrequent. */
 for(unsigned int i=0;;i++) {
  assert(i<2*KD_HOTLOCK_CHECK_INTERVAL*(KD_HOTLOCK_SAMPLE_TARGET+1));
  if(table(1)->rate_samples==KD_HOTLOCK_CHECK_INTERVAL-1 && s->count==KD_HOTLOCK_SAMPLE_TARGET) break;
  assert(kd_hotlock_record_mutex(0x1000));
 }
 unsigned int before_clocks=clocks;
 assert(kd_hotlock_record_mutex(0x1000));
 assert(clocks==before_clocks+1 && !table(1)->rate_samples && !s->count);
 struct kd_hotlock_table before=*table(1);
 for(unsigned int i=0;i<100;i++) assert(kd_hotlock_query_mutex(0x1000));
 assert(!memcmp(&before,table(1),sizeof(before)) && clocks==before_clocks+1);
 assert(!table(0)->rate_samples && !table(0)->rate_hot && !table(0)->used);
 now=table(1)->rate_begin+KD_HOTLOCK_CPU_WINDOW-1;
 for(unsigned int i=0;i<KD_HOTLOCK_CHECK_INTERVAL;i++) kd_hotlock_record_mutex(0x1000);
 assert(table(1)->rate_hot && !table(1)->rate_samples);
 now=table(1)->rate_begin+KD_HOTLOCK_CPU_WINDOW;
 for(unsigned int i=0;i<KD_HOTLOCK_CHECK_INTERVAL-1;i++) kd_hotlock_record_mutex(0x1000);
 assert(table(1)->rate_hot); assert(!kd_hotlock_record_mutex(0x1000));
 assert(!table(1)->rate_hot && !s->count && !s->hot && s->begin==now);
 assert(!memcmp(&before_ratio,ratio(),sizeof(before_ratio)));
}
static void isolation_and_reentry(void)
{
 reset(); warm_spin(0x1000);
 cpu_id=1; assert(!kd_hotlock_query_spin(0x1000));
 assert(!kd_hotlock_record_mutex(0x1000) && !pins);
 cpu_id=0; assert(kd_hotlock_query_spin(0x1000));
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET); reentry=busy_reentry;
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL); assert(!reentry);
 assert(kd_hotlock_find(table(0),0x1000)->count==KD_HOTLOCK_SPIN_SAMPLE_TARGET);
 reentry=busy_reentry; hits(0x1000,1); assert(!reentry && !table(0)->busy);
 reset_policy(0,"observe");
 assert(kd_hotlock_record_mutex(0x1000) && !pins && !kd_hotlock_query_mutex(0x1000));
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL);
 for(unsigned int i=0;i<KD_HOTLOCK_ENTRIES;i++) assert(kd_hotlock_record_spin(0x10000+i));
 assert(kd_hotlock_record_spin(0x20000) && !kd_hotlock_query_spin(0x20000));
 reentry=busy_reentry; mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL); assert(!reentry && !table(0)->busy);
}
static void queue_event(void)
{
 struct qspinlock word={0}; unsigned int before_disable=disables, before_enable=enables;
 pins++; assert(!xchg_tail(&word,1U<<16) && word.tail==1);
 assert(pins==1 && disables==before_disable && enables==before_enable); pins--;
}
static void mcs_publications(void)
{
 reset();
 for(unsigned int i=1;i<KD_HOTLOCK_SPIN_MCS_INTERVAL;i++) {
  queue_event(); assert(!table(0)->rate_hot && !table(0)->rate_samples && clocks==1);
  assert(this_cpu_read(kd_hotlock_spin_mcs)==i && !ratio()->mcs_total);
 }
 queue_event(); assert(table(0)->rate_hot && !table(0)->rate_samples && clocks==2);
 reset(); kd_spin_delegate=false;
 for(unsigned int i=0;i<KD_HOTLOCK_SPIN_MCS_INTERVAL;i++) queue_event();
 assert(!table(0)->rate_hot && !table(0)->rate_samples && clocks==1);
 assert(!this_cpu_read(kd_hotlock_spin_mcs) && !ratio()->mcs_total);
 kd_spin_delegate=true;
 for(unsigned int i=0;i<KD_HOTLOCK_SPIN_MCS_INTERVAL;i++) queue_event();
 assert(table(0)->rate_hot && clocks==2);
 cpu_id=1; assert(!kd_hotlock_spin_cpu_hot_pinned() && !table(0)->rate_samples);
 for(unsigned int i=0;i<KD_HOTLOCK_SPIN_MCS_INTERVAL;i++) queue_event();
 assert(table(0)->rate_hot && clocks==3); cpu_id=0;
 assert(this_cpu_read(kd_hotlock_spin_mcs)==128 && ratio()->mcs_total==128);
}
/* Every simulated native acquisition counts once. Fast entries add only to
 * the denominator; queued entries also execute the real publication hook. */
static void native_batch(unsigned int entries, unsigned int publications)
{
 assert(entries>=publications);
 unsigned int initial_clocks=clocks;
 unsigned long initial_raw=this_cpu_read(kd_hotlock_spin_mcs);
 unsigned long initial_entries=this_cpu_read(kd_hotlock_spin_entries);
 for(unsigned int i=0;i<entries;i++) {
  pins++; kd_hotlock_spin_entry_pinned(); pins--;
  if(i>=entries-publications) queue_event();
 }
 assert(clocks==initial_clocks+((initial_raw%KD_HOTLOCK_SPIN_MCS_INTERVAL)+publications)/KD_HOTLOCK_SPIN_MCS_INTERVAL);
 assert(this_cpu_read(kd_hotlock_spin_mcs)==initial_raw+publications);
 assert(this_cpu_read(kd_hotlock_spin_entries)==initial_entries+entries);
}
static void rejected_batch_and_wrap(void)
{
 /* A full IRQ batch arrives while the first CPU timestamp owns the guard.
  * Its raw entries/publications survive, but none enter the policy numerator. */
 reset_policy(100,"adaptive"); reentry=busy_reentry;
 unsigned int before=clocks;
 for(unsigned int i=0;i<512;i++) {
  pins++; kd_hotlock_spin_entry_pinned(); pins--;
  queue_event();
 }
 assert(!reentry && clocks==before+4 && !table(0)->busy);
 assert(this_cpu_read(kd_hotlock_spin_entries)==640 && this_cpu_read(kd_hotlock_spin_mcs)==640);
 assert(ratio()->mcs_total==512 && !ratio()->ratio_samples && ratio()->entry_begin==640);
 assert(ratio()->ratio_hot && table(0)->rate_hot && ratio()->ratio_low_windows==1);
 assert(!ratio()->ratio_cooldown && !ratio()->ratio_cools);
 native_batch(512,512); assert(table(0)->rate_hot && ratio()->mcs_total==1024);
 assert(!ratio()->ratio_low_windows);
 assert(this_cpu_read(kd_hotlock_spin_mcs)==1152 && this_cpu_read(kd_hotlock_spin_entries)==1152);
 /* Counter wrap owns the zero boundary exactly once, with no lost clock. */
 reset_policy(0,"adaptive");
 per_cpu(kd_hotlock_spin_mcs,0)=ULONG_MAX-127;
 native_batch(127,127);
 assert(this_cpu_read(kd_hotlock_spin_mcs)==ULONG_MAX && !ratio()->mcs_total && !table(0)->rate_hot);
 native_batch(1,1);
 assert(!this_cpu_read(kd_hotlock_spin_mcs) && ratio()->mcs_total==128 && table(0)->rate_hot);
}
static void contention_ratio(void)
{
 assert(KD_HOTLOCK_SPIN_RATIO_INTERVAL==512 && KD_HOTLOCK_SPIN_RETRY_WINDOWS==8 && KD_HOTLOCK_SPIN_COOL_WINDOWS==2);
 reset_policy(75,"adaptive");
 /* Optimistic ratio admission cannot bypass the 128-publication CPU clock.
  * Once that clock warms, per-lock progress need not wait for ratio512. */
 native_batch(127,127);
 assert(!table(0)->rate_hot && ratio()->ratio_hot);
 native_batch(1,1);
 assert(table(0)->rate_hot && ratio()->ratio_hot);
 hits(0x1000,480);
 struct kd_hotlock_entry *s=kd_hotlock_find(table(0),0x1000);
 assert(s && s->count==480 && !s->hot);
 native_batch(193,193);
 assert(table(0)->rate_hot && ratio()->ratio_hot && ratio()->ratio_samples==256);
 assert(s->count==480);
 assert(!table(0)->rate_samples && ratio()->mcs_total==256 && !ratio()->entry_begin);
 assert(this_cpu_read(kd_hotlock_spin_mcs)==321);
 native_batch(190,190);
 assert(table(0)->rate_hot && ratio()->ratio_hot && ratio()->ratio_samples==384);
 assert(s->count==480);
 assert(!table(0)->rate_samples && ratio()->mcs_total==384 && !ratio()->entry_begin);
 assert(this_cpu_read(kd_hotlock_spin_mcs)==511);
 native_batch(1,1);
 assert(table(0)->rate_hot && ratio()->ratio_hot && !ratio()->ratio_samples);
 assert(!ratio()->ratio_cooldown && !ratio()->ratio_cools);
 assert(s->count==480 && !s->hot); /* First measured high preserves warmup. */
 assert(!table(0)->rate_samples && ratio()->mcs_total==512 && ratio()->entry_begin==512);
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET+1-480); assert(kd_hotlock_query_spin(0x1000));
 /* Many fast entries cannot change the cached verdict at an incomplete ratio
  * window. Neither those entries nor the next clock tick erase lock heat. */
 native_batch(512,0); native_batch(128,128);
 assert(table(0)->rate_hot && ratio()->ratio_hot && ratio()->ratio_samples==128);
 assert(ratio()->entry_begin==512 && kd_hotlock_query_spin(0x1000));
 native_batch(384,384); assert(table(0)->rate_hot && ratio()->ratio_hot);
 assert(!ratio()->ratio_samples && ratio()->mcs_total==1024 && ratio()->entry_begin==1536);
 assert(ratio()->ratio_low_windows==1 && !ratio()->ratio_cooldown && !ratio()->ratio_cools);
 assert(kd_hotlock_query_spin(0x1000)); /* An isolated low does not erase heat. */
 native_batch(512,512);
 assert(table(0)->rate_hot && !ratio()->ratio_low_windows && !ratio()->ratio_cooldown);
 native_batch(1024,512);
 assert(table(0)->rate_hot && ratio()->ratio_low_windows==1 && !ratio()->ratio_cools);
 native_batch(1024,512);
 assert(!table(0)->rate_hot && !ratio()->ratio_hot && !ratio()->ratio_low_windows);
 assert(ratio()->mcs_total==2560 && ratio()->entry_begin==4096);
 assert(!kd_hotlock_query_spin(0x1000) && ratio()->ratio_cooldown==8 && ratio()->ratio_cools==1);
 /* Native publications must recover after exactly eight complete windows.
  * An intervening low window consumes retry time instead of restarting it;
  * partial windows cannot consume it or readmit new delegated requests. */
 native_batch(128,128);
 assert(!table(0)->rate_hot && ratio()->ratio_cooldown==8 && ratio()->ratio_cools==1);
 native_batch(384,384);
 assert(!table(0)->rate_hot && ratio()->ratio_cooldown==7 && ratio()->ratio_cools==1);
 native_batch(1024,512);
 assert(!table(0)->rate_hot && ratio()->ratio_cooldown==6 && ratio()->ratio_cools==1);
 for(unsigned int remaining=5;remaining;remaining--) {
  native_batch(512,512);
  assert(!table(0)->rate_hot && !ratio()->ratio_hot);
  assert(ratio()->ratio_cooldown==remaining && ratio()->ratio_cools==1);
 }
 native_batch(512,512);
 assert(kd_hotlock_spin_cpu_hot_pinned() && !ratio()->ratio_cooldown && ratio()->ratio_cools==1);
 s=kd_hotlock_find(table(0),0x1000);
 assert(s && s->hot && !s->count && kd_hotlock_query_spin(0x1000));
 assert(ratio()->mcs_total==6656 && !ratio()->ratio_samples);
 /* Startup uses the same confirmation rule: a first low preserves warmup,
  * and a high second window cancels that streak without rebasing the lock. */
 reset_policy(75,"adaptive");
 native_batch(299,128); assert(kd_hotlock_spin_cpu_hot_pinned());
 hits(0x1000,480); s=kd_hotlock_find(table(0),0x1000);
 unsigned long startup_begin=s->begin;
 native_batch(384,384); /* 512/683 <75%, but only one low window. */
 assert(table(0)->rate_hot && ratio()->ratio_hot && ratio()->ratio_low_windows==1);
 assert(s->count==480 && !s->hot && s->begin==startup_begin);
 assert(!ratio()->ratio_cooldown && !ratio()->ratio_cools);
 native_batch(682,512); assert(kd_hotlock_spin_cpu_hot_pinned()); /* Above75%. */
 assert(!ratio()->ratio_low_windows && !ratio()->ratio_cooldown && !ratio()->ratio_cools);
 assert(s->count==480 && !s->hot && s->begin==startup_begin);

 /* Many fast entries can warm a lock during the initial grace period; the
  * publication count alone does not bound the number of lock records. Two
  * startup lows must still close admission and start all eight retry windows. */
 reset_policy(100,"adaptive"); native_batch(129,128);
 hits(0x1000,480); s=kd_hotlock_find(table(0),0x1000);
 native_batch(384,384);
 assert(table(0)->rate_hot && ratio()->ratio_low_windows==1 && !ratio()->ratio_cooldown);
 native_batch(KD_HOTLOCK_SPIN_SAMPLE_TARGET+1-480,0);
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET+1-480);
 assert(kd_hotlock_query_spin(0x1000) && this_cpu_read(kd_hotlock_spin_mcs)==512);
 native_batch(513,512);
 assert(!table(0)->rate_hot && !kd_hotlock_query_spin(0x1000) && s->hot);
 assert(ratio()->ratio_cooldown==8 && ratio()->ratio_cools==1 && !ratio()->ratio_low_windows);
 for(unsigned int remaining=7;remaining;remaining--) {
  native_batch(remaining==4 ? 513 : 512,512);
  assert(!table(0)->rate_hot && ratio()->ratio_cooldown==remaining && ratio()->ratio_cools==1);
 }
 native_batch(129,128);
 assert(!table(0)->rate_hot && ratio()->ratio_cooldown==1);
 native_batch(384,384); /* A low eighth window expires cooldown but stays cold. */
 assert(!table(0)->rate_hot && !ratio()->ratio_hot && !ratio()->ratio_cooldown);
 native_batch(513,512);
 assert(!table(0)->rate_hot && !ratio()->ratio_low_windows && !ratio()->ratio_cooldown);
 assert(ratio()->ratio_cools==1); /* Cold low windows do not restart holdoff. */
 native_batch(512,512);
 assert(kd_hotlock_query_spin(0x1000) && !ratio()->ratio_cooldown && ratio()->ratio_cools==1);
 reset_policy(80,"adaptive");
 assert(ratio()->entry_limit==640 && ratio()->ratio_enforced);
 native_batch(640,512); assert(kd_hotlock_spin_cpu_hot_pinned()); /* Exact 80%. */
 assert(!ratio()->ratio_low_windows);
 native_batch(641,512); assert(kd_hotlock_spin_cpu_hot_pinned() && ratio()->ratio_low_windows==1);
 native_batch(641,512); assert(!kd_hotlock_spin_cpu_hot_pinned());
 /* A longer ratio window must represent 97% independently of the 128-event
  * clock: 512/527 passes and 512/528 fails, without demanding 100%. */
 reset_policy(97,"adaptive");
 assert(ratio()->entry_limit==527 && ratio()->ratio_enforced);
 native_batch(527,512); assert(kd_hotlock_spin_cpu_hot_pinned());
 assert(!ratio()->ratio_low_windows);
 native_batch(528,512); assert(kd_hotlock_spin_cpu_hot_pinned() && ratio()->ratio_low_windows==1);
 native_batch(528,512); assert(!kd_hotlock_spin_cpu_hot_pinned());
 reset_policy(75,"adaptive");
 ratio()->entry_begin=ULONG_MAX-255;
 per_cpu(kd_hotlock_spin_entries,0)=ULONG_MAX-255;
 native_batch(512,512); assert(this_cpu_read(kd_hotlock_spin_entries)==256 && table(0)->rate_hot);
 /* Optimistic admission alone cannot distinguish a correct wrapped delta
  * from one falsely classified as the first low window. */
 assert(ratio()->ratio_hot && !ratio()->ratio_low_windows && !ratio()->ratio_cooldown);
 cpu_id=1; native_batch(2048,512); assert(table(0)->rate_hot && ratio()->ratio_low_windows==1);
 native_batch(2048,512); assert(!table(0)->rate_hot && ratio()->ratio_cooldown==8);
 cpu_id=0; assert(table(0)->rate_hot && this_cpu_read(kd_hotlock_spin_entries)==256);
 /* A large spin denominator must never suppress the independent mutex clock. */
 reset_policy(75,"adaptive"); native_batch(3000,0);
 for(unsigned int i=0;i<KD_HOTLOCK_CHECK_INTERVAL;i++) kd_hotlock_record_mutex(0x2000);
 assert(table(1)->rate_hot && !table(0)->rate_hot && !ratio()->ratio_samples);
 /* Disabled ratio and observe retain immediate 128-MCS frequency admission.
  * Their ratio statistics still advance on the independent 512-event clock. */
 reset_policy(0,"adaptive"); native_batch(3200,128);
 assert(table(0)->rate_hot && ratio()->ratio_hot && ratio()->ratio_samples==128);
 native_batch(384,384); assert(table(0)->rate_hot && ratio()->ratio_hot);
 assert(!ratio()->ratio_samples && ratio()->mcs_total==512);
 reset_policy(75,"observe"); native_batch(3200,128);
 assert(ratio()->entry_limit==682 && !ratio()->ratio_enforced);
 assert(table(0)->rate_hot && ratio()->ratio_hot && ratio()->ratio_samples==128);
 native_batch(384,384); assert(table(0)->rate_hot && ratio()->ratio_hot && ratio()->ratio_low_windows==1);
 assert(!ratio()->ratio_samples && ratio()->mcs_total==512);
 assert(kd_hotlock_record_spin(0x1000));
 /* Observe bypasses admission even while its diagnostic policy would cool.
  * Build this transition naturally with high then low ratio windows. */
 native_batch(512,512); assert(ratio()->ratio_hot && table(0)->rate_hot);
 native_batch(1024,512);
 assert(table(0)->rate_hot && ratio()->ratio_hot && ratio()->ratio_low_windows==1);
 native_batch(1024,512);
 assert(table(0)->rate_hot && !ratio()->ratio_hot && ratio()->ratio_cooldown==8);
 assert(ratio()->ratio_cools==1 && kd_hotlock_record_spin(0x1000));
 native_batch(128,128);
 assert(table(0)->rate_hot && ratio()->ratio_cooldown==8);
 /* Ratio bypass never removes the independent CPU time deadline. */
 now=table(0)->rate_begin+KD_HOTLOCK_CPU_WINDOW;
 native_batch(128,128); assert(!table(0)->rate_hot);
 assert(kd_hotlock_record_spin(0x1000));
 reset_policy(100,"adaptive"); native_batch(512,512); assert(table(0)->rate_hot);
 assert(!ratio()->ratio_low_windows);
 native_batch(513,512); assert(table(0)->rate_hot && ratio()->ratio_low_windows==1);
 native_batch(513,512); assert(!table(0)->rate_hot);
}
static void close_ratio_gate(void)
{
 native_batch(513,512); native_batch(513,512);
 assert(!table(0)->rate_hot && ratio()->freq_hot && ratio()->ratio_cooldown==8);
}
/* The ratio controls admission, not the lifetime of still-recent frequency
 * evidence. Reopening must distinguish a paused epoch from an expired one. */
static void retained_lock_epochs(void)
{
 reset_policy(100,"adaptive"); native_batch(512,512);
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET+1); hits(0x1000,7); hits(0x2000,17);
 struct kd_hotlock_entry *a=kd_hotlock_find(table(0),0x1000);
 struct kd_hotlock_entry *b=kd_hotlock_find(table(0),0x2000);
 struct kd_hotlock_entry saved_a=*a, saved_b=*b;
 now+=100; close_ratio_gate();
 unsigned int before=clocks;
 assert(!kd_hotlock_query_spin(0x1000) && !kd_hotlock_record_spin(0x1000));
 assert(clocks==before && !memcmp(a,&saved_a,sizeof(*a)) && !memcmp(b,&saved_b,sizeof(*b)));
 native_batch(7*512,7*512); assert(!kd_hotlock_spin_cpu_hot_pinned());
 now+=100; native_batch(512,512);
 assert(kd_hotlock_query_spin(0x1000) && !kd_hotlock_query_spin(0x2000));
 assert(!memcmp(a,&saved_a,sizeof(*a)) && !memcmp(b,&saved_b,sizeof(*b)));
 hits(0x2000,KD_HOTLOCK_SPIN_SAMPLE_TARGET+1-17); assert(kd_hotlock_query_spin(0x2000));

 /* Equality expires the older hot epoch, while a newer hot epoch survives
  * at the same reopen. Keeping count must never rebase its original time. */
 reset_policy(100,"adaptive"); native_batch(512,512);
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET+1); hits(0x1000,17);
 a=kd_hotlock_find(table(0),0x1000); now=a->begin+KD_HOTLOCK_SPIN_INITIAL_WINDOW-1;
 hits(0x2000,KD_HOTLOCK_SPIN_SAMPLE_TARGET+1); hits(0x2000,7);
 b=kd_hotlock_find(table(0),0x2000); saved_b=*b;
 now++; close_ratio_gate(); assert(a->hot && a->count==17);
 native_batch(4096,4096);
 assert(table(0)->rate_hot && !a->hot && !a->count && a->begin==now);
 assert(!memcmp(b,&saved_b,sizeof(*b)) && kd_hotlock_query_spin(0x2000));
 assert(!kd_hotlock_query_spin(0x1000));

 /* A lock can have a later timestamp than the last CPU sample. A backward
  * lock epoch must expire even when the CPU frequency clock stays forward. */
 reset_policy(100,"adaptive"); native_batch(512,512);
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET+1);
 a=kd_hotlock_find(table(0),0x1000); saved_a=*a;
 now=100; hits(0x2000,KD_HOTLOCK_SPIN_SAMPLE_TARGET+1);
 b=kd_hotlock_find(table(0),0x2000); assert(b->begin==100);
 now=50; close_ratio_gate(); native_batch(4096,4096);
 assert(table(0)->rate_hot && !b->hot && !b->count && b->begin==now);
 assert(!memcmp(a,&saved_a,sizeof(*a)) && kd_hotlock_query_spin(0x1000));

 /* True CPU frequency loss, including a backward clock, clears all epochs
  * during suppression; the subsequent frequency reheat starts them afresh. */
 for(unsigned int backwards=0;backwards<2;backwards++) {
  reset_policy(100,"adaptive"); now=100; native_batch(512,512);
  hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET+1); hits(0x1000,7);
  a=kd_hotlock_find(table(0),0x1000); close_ratio_gate();
  now=backwards ? table(0)->rate_begin-1 : table(0)->rate_begin+KD_HOTLOCK_CPU_WINDOW;
  native_batch(128,128);
  assert(!ratio()->freq_hot && !table(0)->rate_hot && !a->hot && !a->count && a->begin==now);
  now++; native_batch(128,128);
  assert(ratio()->freq_hot && !table(0)->rate_hot && !a->hot && !a->count && a->begin==now);
 }
}
int main(void)
{
 assert(spin_contention_pct==100);
 init_and_pins(); boundaries(); windows(); backwards_and_zero(); hash_and_capacity();
 mutex_sampling(); isolation_and_reentry(); mcs_publications(); rejected_batch_and_wrap(); contention_ratio();
 retained_lock_epochs();
 kd_hotlock_exit(); hotlock_mode="invalid"; assert(kd_hotlock_init()==-EINVAL);
 hotlock_mode="adaptive"; spin_contention_pct=101; assert(kd_hotlock_init()==-EINVAL);
 spin_contention_pct=75; assert(!kd_hotlock_init()); kd_hotlock_exit();
 fail_alloc=true; assert(kd_hotlock_init()==-ENOMEM); assert(!kd_hotlock_cpu);
 puts("PASS hotlock: inline MCS128/CPU-window4e10/spin513/mutex1025, exact keys/capacity, busy batch rejection, raw/sample totals, pins, queries, independent mutex timing");
 puts("PASS contention admission: optimistic clock128 warmup, ratio512, consecutive-low confirmation/high reset, 75/80/97/100% boundaries, eight-window native recovery, uniform startup confirmation, wrap, CPU isolation, observe/zero bypass");
 puts("PASS ratio retention: gated queries, preserved recent heat/count/time, selective expiry/backward epochs, true frequency reset and unchanged storage geometry");
 return 0;
}
